"""Separate synthetic evidence, linkage, and analytical projection custody."""

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from secrets import token_hex, token_urlsafe
from types import MappingProxyType

from .projection import POLICY, PURPOSE, validate_projection
from .storage import PrivateDatabase, StoreUnavailable

ROLES = {
    "evidence_writer",
    "restricted_mse",
    "linkage_custodian",
    "projection_writer",
    "analyst",
    "lineage_auditor",
    "retention_recovery",
}
VIEW_ROLES = {"projection_writer", "analyst", "lineage_auditor"}
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}")
VIEW = re.compile(r"av_[0-9a-f]{32}")
MAX_ARTIFACT_BYTES = 4 * 1024 * 1024
SCOPE_FIELDS = {"subject_id", "source_system", "source_instance", "collection"}

EVIDENCE_SCHEMA = """
CREATE TABLE originals (
    handle TEXT PRIMARY KEY, scope TEXT NOT NULL, content BLOB NOT NULL
);
"""
VAULT_SCHEMA = """
CREATE TABLE pseudonyms (
    scope TEXT NOT NULL, purpose TEXT NOT NULL, policy_version TEXT NOT NULL,
    generation INTEGER NOT NULL, recipient TEXT NOT NULL, token TEXT NOT NULL UNIQUE,
    PRIMARY KEY(scope,purpose,policy_version,generation,recipient)
);
"""
AUTHORITY_SCHEMA = """
CREATE TABLE epoch (id INTEGER PRIMARY KEY CHECK(id=1), value INTEGER NOT NULL, pair TEXT NOT NULL);
CREATE TABLE contexts (
    scope TEXT NOT NULL, purpose TEXT NOT NULL, recipient TEXT NOT NULL,
    policy_version TEXT NOT NULL, generation INTEGER NOT NULL,
    PRIMARY KEY(scope,purpose,recipient)
);
CREATE TABLE credentials (
    digest TEXT PRIMARY KEY, role TEXT NOT NULL, scope TEXT NOT NULL,
    purpose TEXT NOT NULL, policy_version TEXT NOT NULL, generation INTEGER NOT NULL,
    recipient TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE TABLE view_grants (
    view_id TEXT PRIMARY KEY, scope TEXT NOT NULL, purpose TEXT NOT NULL,
    policy_version TEXT NOT NULL, generation INTEGER NOT NULL,
    recipient TEXT NOT NULL, expires_at TEXT NOT NULL
);
"""
FENCE_SCHEMA = """
CREATE TABLE epoch (id INTEGER PRIMARY KEY CHECK(id=1), value INTEGER NOT NULL, pair TEXT NOT NULL);
"""
PROJECTION_SCHEMA = """
CREATE TABLE projections (
    view_id TEXT PRIMARY KEY, payload TEXT NOT NULL
);
"""


class AccessDenied(PermissionError):
    """Uniform denial with no protected input or location in its text."""


@dataclass(frozen=True)
class Grant:
    role: str
    scope: dict
    purpose: str
    policy_version: str
    generation: int
    recipient: str
    expires_at: datetime

    def __post_init__(self):
        if (
            not isinstance(self.scope, (dict, MappingProxyType))
            or set(self.scope) != SCOPE_FIELDS
            or not all(
                isinstance(value, str) and LABEL.fullmatch(value)
                for value in self.scope.values()
            )
        ):
            raise ValueError("Invalid trusted grant scope")
        object.__setattr__(self, "scope", MappingProxyType(dict(self.scope)))

    def scope_key(self):
        return json.dumps(dict(self.scope), separators=(",", ":"), sort_keys=True)

    def context(self):
        return (
            self.scope_key(),
            self.purpose,
            self.policy_version,
            self.generation,
            self.recipient,
        )


def _utc(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("A trusted UTC expiration is required")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def open_custody(
    *,
    authority_root,
    fence_root,
    projection_root,
    evidence_root=None,
    vault_root=None,
    grants=None,
    initialize=False,
    clock=lambda: datetime.now(timezone.utc),
):
    """Trusted bootstrap. Give each local consumer only its assigned credential."""
    if initialize != (grants is not None):
        raise ValueError("Trusted grants may only be supplied for fresh initialization")
    configured = {}
    for grant in (grants or {}).values():
        if (
            not isinstance(grant, Grant)
            or grant.role not in ROLES
            or not all(
                isinstance(value, str) and LABEL.fullmatch(value)
                for value in (grant.purpose, grant.policy_version, grant.recipient)
            )
            or type(grant.generation) is not int
            or not 1 <= grant.generation <= (1 << 53) - 1
        ):
            raise ValueError("Invalid trusted grant configuration")
        _utc(grant.expires_at)
        if grant.role in VIEW_ROLES and (grant.purpose, grant.policy_version) != (
            PURPOSE,
            POLICY,
        ):
            raise ValueError("Invalid analytical grant policy")
        if grant.role == "evidence_writer" and grant.purpose != "evidence_ingest":
            raise ValueError("Invalid evidence grant purpose")
        binding = grant.scope_key(), grant.purpose, grant.recipient
        current = grant.policy_version, grant.generation
        if configured.setdefault(binding, current) != current:
            raise ValueError(
                "One policy and generation must be current per scope and purpose"
            )
    specifications = (
        (evidence_root, 0x4D534501, EVIDENCE_SCHEMA),
        (vault_root, 0x4D534502, VAULT_SCHEMA),
        (projection_root, 0x4D534503, PROJECTION_SCHEMA),
        (authority_root, 0x4D534504, AUTHORITY_SCHEMA),
        (fence_root, 0x4D534505, FENCE_SCHEMA),
    )
    if any(root is None for root, _, _ in specifications[2:]):
        raise ValueError("Authority, fence and projection roots are required")
    roots = [Path(root).absolute() for root, _, _ in specifications if root is not None]
    if any(
        left == right or left in right.parents
        for index, left in enumerate(roots)
        for right in roots[:index] + roots[index + 1 :]
    ):
        raise ValueError("Custody roots must be disjoint")
    stores = tuple(
        PrivateDatabase(root, ident) if root is not None else None
        for root, ident, _ in specifications
    )
    authority, fence = stores[-2:]
    credentials = {}
    if initialize:
        if any(store is not None and store._files() is not None for store in stores):
            raise StoreUnavailable("Initialization requires fresh private stores")
        for store, (_, _, schema) in zip(stores, specifications):
            if store is not None:
                store.create(schema)
        pair = token_hex(16)
        with fence.open(write=True) as db:
            db.execute("INSERT INTO epoch VALUES (1,0,?)", (pair,))
        with authority.open(write=True) as db:
            db.execute("INSERT INTO epoch VALUES (1,0,?)", (pair,))
            db.executemany(
                "INSERT INTO contexts VALUES (?,?,?,?,?)",
                ((*key, *current) for key, current in configured.items()),
            )
            for name, grant in grants.items():
                credential = token_urlsafe(32)
                db.execute(
                    "INSERT INTO credentials VALUES (?,?,?,?,?,?,?,?)",
                    (
                        _digest(credential),
                        grant.role,
                        *grant.context(),
                        _utc(grant.expires_at),
                    ),
                )
                credentials[name] = credential
    service = Custody(stores, clock)
    with authority.open() as db:
        service._epoch(db)
    return service, credentials


def _digest(credential):
    return sha256(credential.encode("ascii")).hexdigest()


class Custody:
    """Application-level policy over caller-owned, exclusive private roots."""

    def __init__(self, stores, clock):
        self._evidence, self._vault, self._projection, self._authority, self._fence = (
            stores
        )
        self._clock = clock

    def _epoch(self, db):
        current = db.execute("SELECT value,pair FROM epoch WHERE id=1").fetchone()
        with self._fence.open() as fence:
            floor = fence.execute("SELECT value,pair FROM epoch WHERE id=1").fetchone()
        if current is None or current != floor:
            raise StoreUnavailable("Current authorization is unavailable")
        return current[0]

    @contextmanager
    def _decision(self, credential, *roles):
        credential = self._token(credential)
        with self._authority.open(write=True) as db:
            self._epoch(db)
            row = db.execute(
                """SELECT c.role,c.scope,c.purpose,c.policy_version,c.generation,c.recipient,c.expires_at
                   FROM credentials c JOIN contexts a USING(scope,purpose,recipient)
                   WHERE c.digest=? AND c.generation=a.generation
                     AND c.policy_version=a.policy_version""",
                (_digest(credential),),
            ).fetchone()
            if row is None or row[0] not in roles or row[-1] <= _utc(self._clock()):
                raise AccessDenied("Access denied")
            role, scope, purpose, policy, generation, recipient, expiry = row
            yield db, Grant(
                role,
                json.loads(scope),
                purpose,
                policy,
                generation,
                recipient,
                datetime.fromisoformat(expiry),
            )

    @staticmethod
    def _store(store):
        if store is None:
            raise StoreUnavailable("Private store is unavailable")
        return store

    @staticmethod
    def _token(value, pattern=TOKEN):
        if not isinstance(value, str) or not pattern.fullmatch(value):
            raise AccessDenied("Access denied")
        return value

    def put_evidence(self, credential, original):
        with self._decision(credential, "evidence_writer") as (_, grant):
            if (
                not isinstance(original, bytes)
                or not 0 < len(original) <= MAX_ARTIFACT_BYTES
            ):
                raise ValueError("Invalid synthetic evidence")
            handle = token_urlsafe(32)
            with self._store(self._evidence).open(write=True) as db:
                db.execute(
                    "INSERT INTO originals VALUES (?,?,?)",
                    (handle, grant.scope_key(), original),
                )
            return handle

    def read_evidence(self, credential, handle):
        with self._decision(credential, "evidence_writer") as (_, grant):
            with self._store(self._evidence).open() as db:
                entry = db.execute(
                    "SELECT content FROM originals WHERE handle=? AND scope=?",
                    (self._token(handle), grant.scope_key()),
                ).fetchone()
            if entry is None:
                raise AccessDenied("Access denied")
            return entry[0]

    def pseudonym(self, credential):
        with self._decision(credential, "linkage_custodian") as (_, grant):
            with self._store(self._vault).open(write=True) as db:
                values = grant.context()
                db.execute(
                    "INSERT INTO pseudonyms VALUES (?,?,?,?,?,?) "
                    "ON CONFLICT(scope,purpose,policy_version,generation,recipient) DO NOTHING",
                    (*values, token_urlsafe(32)),
                )
                return db.execute(
                    "SELECT token FROM pseudonyms WHERE scope=? AND purpose=? "
                    "AND policy_version=? AND generation=? AND recipient=?",
                    values,
                ).fetchone()[0]

    def resolve_pseudonym(self, credential, token):
        with self._decision(credential, "linkage_custodian") as (_, grant):
            with self._store(self._vault).open() as db:
                row = db.execute(
                    "SELECT scope FROM pseudonyms WHERE token=? AND scope=? AND purpose=? "
                    "AND policy_version=? AND generation=? AND recipient=?",
                    (self._token(token), *grant.context()),
                ).fetchone()
            if row is None:
                raise AccessDenied("Access denied")
            return json.loads(row[0])

    def issue_view(self, credential):
        with self._decision(credential, "projection_writer") as (db, grant):
            handle = "av_" + token_hex(16)
            db.execute(
                "INSERT INTO view_grants VALUES (?,?,?,?,?,?,?)",
                (handle, *grant.context(), _utc(grant.expires_at)),
            )
            return handle

    def _view(self, db, grant, handle):
        row = db.execute(
            "SELECT expires_at FROM view_grants WHERE view_id=? AND scope=? AND purpose=? "
            "AND policy_version=? AND generation=? AND recipient=?",
            (self._token(handle, VIEW), *grant.context()),
        ).fetchone()
        if row is None or row[0] <= _utc(self._clock()):
            raise AccessDenied("Access denied")
        return row[0]

    @staticmethod
    def _binding(grant, expiry):
        return dict(
            scope=dict(grant.scope),
            purpose=grant.purpose,
            policy_version=grant.policy_version,
            generation=grant.generation,
            recipient=grant.recipient,
            expires_at=expiry,
        )

    def authorize_projection(self, credential, view_id=None):
        with self._decision(credential, "projection_writer") as (db, grant):
            expiry = (
                _utc(grant.expires_at)
                if view_id is None
                else self._view(db, grant, view_id)
            )
            return self._binding(grant, expiry)

    def authorize_lineage(self, credential, view_id, *, operation):
        role = {"bind": "projection_writer", "resolve": "lineage_auditor"}.get(
            operation
        )
        if role is None:
            raise AccessDenied("Access denied")
        with self._decision(credential, role) as (db, grant):
            return self._binding(grant, self._view(db, grant, view_id))

    def revoke(self, credential):
        with self._decision(credential, "retention_recovery") as (db, grant):
            epoch = self._epoch(db)
            # Persist the independent fence first. A crash between commits
            # leaves unequal epochs and denies until trusted reconciliation.
            with self._fence.open(write=True) as fence:
                fence.execute("UPDATE epoch SET value=? WHERE id=1", (epoch + 1,))
            db.execute("UPDATE epoch SET value=? WHERE id=1", (epoch + 1,))
            db.execute(
                "UPDATE contexts SET generation=? WHERE scope=? AND purpose=? AND recipient=?",
                (
                    grant.generation + 1,
                    grant.scope_key(),
                    grant.purpose,
                    grant.recipient,
                ),
            )
            return grant.generation + 1

    def put_projection(self, credential, view_id, payload):
        with self._decision(credential, "projection_writer") as (authority, grant):
            self._view(authority, grant, view_id)
            safe = validate_projection(payload, view_id=view_id, grant=grant)
            encoded = json.dumps(
                safe, separators=(",", ":"), sort_keys=True, allow_nan=False
            )
            with self._projection.open(write=True) as db:
                stored = db.execute(
                    "SELECT payload FROM projections WHERE view_id=?", (view_id,)
                ).fetchone()
                if stored is None:
                    db.execute(
                        "INSERT INTO projections VALUES (?,?)", (view_id, encoded)
                    )
                elif stored[0] != encoded:
                    raise AccessDenied("Access denied")

    def _published(self, grant, view_id):
        with self._projection.open() as db:
            stored = db.execute(
                "SELECT payload FROM projections WHERE view_id=?", (view_id,)
            ).fetchone()
        if stored is None:
            raise AccessDenied("Access denied")
        try:
            return validate_projection(
                json.loads(stored[0]), view_id=view_id, grant=grant
            )
        except ValueError:
            raise StoreUnavailable("Stored projection is invalid") from None

    def read_projection(self, credential, view_id):
        with self._decision(credential, "analyst") as (authority, grant):
            self._view(authority, grant, view_id)
            return self._published(grant, view_id)

    def published_projection_digest(self, credential, view_id):
        """Privately verify an immutable publication for lineage."""
        with self._decision(credential, "projection_writer", "lineage_auditor") as (
            authority,
            grant,
        ):
            self._view(authority, grant, view_id)
            payload = self._published(grant, view_id)
            encoded = json.dumps(
                payload, separators=(",", ":"), sort_keys=True, allow_nan=False
            )
            return sha256(encoded.encode("utf-8")).hexdigest()
