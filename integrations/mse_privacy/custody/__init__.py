"""Separate synthetic evidence, linkage, and analytical projection custody."""

from dataclasses import dataclass
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
CREATE TABLE view_grants (
    view_id TEXT PRIMARY KEY, scope TEXT NOT NULL, purpose TEXT NOT NULL,
    policy_version TEXT NOT NULL, generation INTEGER NOT NULL,
    recipient TEXT NOT NULL, expires_at TEXT NOT NULL
);
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
    evidence_root,
    vault_root,
    projection_root,
    grants,
    initialize=False,
    clock=lambda: datetime.now(timezone.utc),
):
    """Trusted bootstrap. Give each local consumer only its assigned credential."""
    configured = {}
    for grant in grants.values():
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
    roots = tuple(
        Path(path).absolute() for path in (evidence_root, vault_root, projection_root)
    )
    if any(
        left == right or left in right.parents
        for index, left in enumerate(roots)
        for right in roots[:index] + roots[index + 1 :]
    ):
        raise ValueError("Evidence, vault and projection roots must be disjoint")
    stores = tuple(
        PrivateDatabase(path, ident)
        for path, ident in zip(
            roots,
            (0x4D534501, 0x4D534502, 0x4D534503),
        )
    )
    if initialize:
        if any(store._files() is not None for store in stores):
            raise StoreUnavailable("Initialization requires three fresh private stores")
        for store, schema in zip(
            stores, (EVIDENCE_SCHEMA, VAULT_SCHEMA, PROJECTION_SCHEMA)
        ):
            store.create(schema)
    for store in stores:
        with store.open():
            pass
    credentials = {name: token_urlsafe(32) for name in grants}
    return (
        Custody(
            stores,
            {credentials[name]: grant for name, grant in grants.items()},
            clock,
            configured,
        ),
        credentials,
    )


class Custody:
    """Application-level policy over caller-owned, exclusive private roots."""

    def __init__(self, stores, grants, clock, configured):
        self._evidence, self._vault, self._projection = stores
        self._grants = grants
        self._clock = clock
        self._active = configured

    def _authorize(self, credential, *roles):
        grant = self._grants.get(credential) if isinstance(credential, str) else None
        if (
            grant is None
            or grant.role not in roles
            or _utc(grant.expires_at) <= _utc(self._clock())
            or self._active[(grant.scope_key(), grant.purpose, grant.recipient)]
            != (grant.policy_version, grant.generation)
        ):
            raise AccessDenied("Access denied")
        return grant

    @staticmethod
    def _token(value, pattern=TOKEN):
        if not isinstance(value, str) or not pattern.fullmatch(value):
            raise AccessDenied("Access denied")
        return value

    def put_evidence(self, credential, original):
        grant = self._authorize(credential, "evidence_writer")
        if (
            not isinstance(original, bytes)
            or not 0 < len(original) <= MAX_ARTIFACT_BYTES
        ):
            raise ValueError("Invalid synthetic evidence")
        handle = token_urlsafe(32)
        with self._evidence.open(write=True) as db:
            db.execute(
                "INSERT INTO originals VALUES (?,?,?)",
                (handle, grant.scope_key(), original),
            )
        return handle

    def read_evidence(self, credential, handle):
        grant = self._authorize(credential, "evidence_writer")
        with self._evidence.open() as db:
            entry = db.execute(
                "SELECT content FROM originals WHERE handle=? AND scope=?",
                (self._token(handle), grant.scope_key()),
            ).fetchone()
        if entry is None:
            raise AccessDenied("Access denied")
        return entry[0]

    def pseudonym(self, credential):
        grant = self._authorize(credential, "linkage_custodian")
        with self._vault.open(write=True) as db:
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
        grant = self._authorize(credential, "linkage_custodian")
        with self._vault.open() as db:
            row = db.execute(
                "SELECT scope FROM pseudonyms WHERE token=? AND scope=? AND purpose=? "
                "AND policy_version=? AND generation=? AND recipient=?",
                (self._token(token), *grant.context()),
            ).fetchone()
        if row is None:
            raise AccessDenied("Access denied")
        return json.loads(row[0])

    def issue_view(self, credential):
        grant = self._authorize(credential, "projection_writer")
        handle = "av_" + token_hex(16)
        with self._vault.open(write=True) as db:
            db.execute(
                "INSERT INTO view_grants VALUES (?,?,?,?,?,?,?)",
                (handle, *grant.context(), _utc(grant.expires_at)),
            )
        return handle

    def _view(self, grant, handle):
        with self._vault.open() as db:
            row = db.execute(
                "SELECT expires_at FROM view_grants WHERE view_id=? AND scope=? AND purpose=? "
                "AND policy_version=? AND generation=? AND recipient=?",
                (self._token(handle, VIEW), *grant.context()),
            ).fetchone()
        if row is None or row[0] <= _utc(self._clock()):
            raise AccessDenied("Access denied")
        return row[0]

    def authorize_lineage(self, credential, view_id, *, operation):
        if operation == "bind":
            grant = self._authorize(credential, "projection_writer")
        elif operation == "resolve":
            grant = self._authorize(credential, "lineage_auditor")
        else:
            raise AccessDenied("Access denied")
        expiry = self._view(grant, view_id)
        return dict(
            scope=dict(grant.scope),
            purpose=grant.purpose,
            policy_version=grant.policy_version,
            generation=grant.generation,
            recipient=grant.recipient,
            expires_at=expiry,
        )

    def revoke(self, credential):
        """Fence the configured context in memory; trusted bootstrap owns restart state."""
        grant = self._authorize(credential, "retention_recovery")
        self._active[(grant.scope_key(), grant.purpose, grant.recipient)] = (
            grant.policy_version,
            grant.generation + 1,
        )
        return grant.generation + 1

    def put_projection(self, credential, view_id, payload):
        grant = self._authorize(credential, "projection_writer")
        self._view(grant, view_id)
        safe = validate_projection(payload, view_id=view_id, grant=grant)
        encoded = json.dumps(
            safe, separators=(",", ":"), sort_keys=True, allow_nan=False
        )
        with self._projection.open(write=True) as db:
            stored = db.execute(
                "SELECT payload FROM projections WHERE view_id=?", (view_id,)
            ).fetchone()
            if stored is None:
                db.execute("INSERT INTO projections VALUES (?,?)", (view_id, encoded))
            elif stored[0] != encoded:
                raise AccessDenied("Access denied")

    def read_projection(self, credential, view_id):
        grant = self._authorize(credential, "analyst")
        self._view(grant, view_id)
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
