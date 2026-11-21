"""Private lineage across opaque analytical handles and exact offline replay."""
from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3

from mse.contracts import canonical, read_json

_DENIED = "Lineage unavailable for this authorization"
_VIEW = re.compile(r"av_[0-9a-f]{32}")


class LineageDenied(PermissionError):
    """A fixed denial without restricted paths, IDs, or exception details."""


@dataclass(frozen=True)
class ViewBinding:
    """Trusted custody decision, never constructed from analytical payload fields."""

    scope: dict
    purpose: str
    policy_version: str
    generation: int
    recipient: str
    expires_at: str


@dataclass(frozen=True)
class ExactLineage:
    """Restricted view evidence. Return only via the authorized audit boundary."""

    binding: ViewBinding
    archive_id: str
    projection_version: str
    snapshot_sha256: str
    projection_sha256: str


def _digest(data):
    return sha256(data).hexdigest()


def _require_file(path, *, directory=False):
    info = path.lstat()
    is_expected = path.is_dir() if directory else path.is_file() and info.st_nlink == 1
    if path.is_symlink() or not is_expected or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise LineageDenied(_DENIED)


class LineageResolver:
    """Privileged registry using current authorization from the separate custody store.

    Custody is a trusted dependency, constructed by local bootstrap. Public clients
    supply only a credential and opaque ID and have no access to this registry or
    its directory. No authority state is restored from this private mapping file.
    """

    def __init__(self, private_root, *, custody, archive_id):
        root = Path(private_root)
        self._custody = custody
        self._archive_id = archive_id
        self._path = root / "lineage.sqlite3"
        try:
            if not root.is_absolute() or root != root.resolve():
                raise LineageDenied(_DENIED)
            root.mkdir(mode=0o700, exist_ok=True)
            _require_file(root, directory=True)
            try:
                descriptor = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(descriptor)
            with closing(self._connect()) as db, db:
                db.execute("CREATE TABLE IF NOT EXISTS handles (view_id TEXT PRIMARY KEY, lineage TEXT NOT NULL)")
        except (OSError, ValueError, sqlite3.Error):
            raise LineageDenied(_DENIED) from None

    def _connect(self):
        if self._path.parent != self._path.parent.resolve():
            raise LineageDenied(_DENIED)
        _require_file(self._path.parent, directory=True)
        _require_file(self._path)
        return sqlite3.connect(self._path.as_uri() + "?mode=rw", uri=True, timeout=5)

    def _authorize(self, credential, view_id, operation):
        if not isinstance(view_id, str) or not _VIEW.fullmatch(view_id):
            raise LineageDenied(_DENIED)
        decision = self._custody.authorize_lineage(credential, view_id, operation=operation)
        if not isinstance(decision, dict):
            raise LineageDenied(_DENIED)
        return ViewBinding(**decision)

    def bind(self, credential, view_id, *, ledger, snapshot_bytes, projection_bytes,
             max_snapshot_bytes, max_projection_bytes):
        """Privately bind an authorized projection to a verified exact snapshot.

        The bootstrap supplies the trusted ledger and custody implementations.
        The authoritative archive is read only through its complete verifier.
        The established projection path owns analytical schema/semantic checks.
        """
        try:
            limits = (max_snapshot_bytes, max_projection_bytes)
            if any(type(n) is not int or n <= 0 for n in limits):
                raise LineageDenied(_DENIED)
            if len(snapshot_bytes) > max_snapshot_bytes or len(projection_bytes) > max_projection_bytes:
                raise LineageDenied(_DENIED)
            binding = self._authorize(credential, view_id, "bind")
            snapshot = read_json(snapshot_bytes.decode("utf-8"))
            projection = read_json(projection_bytes.decode("utf-8"))
            if (not isinstance(snapshot, dict) or not isinstance(projection, dict)
                    or snapshot.get("archive_id") != self._archive_id
                    or snapshot.get("scope") != binding.scope
                    or projection.get("view_id") != view_id
                    or projection.get("purpose") != binding.purpose
                    or projection.get("policy_version") != binding.policy_version
                    or projection.get("schema_version") != "mse.analytics-view/0.1"
                    or projection.get("projection_version") != "relative-hour-mean/0.1"):
                raise LineageDenied(_DENIED)
            if ledger.verify_snapshot(snapshot) is not True:
                raise LineageDenied(_DENIED)
            lineage = ExactLineage(
                binding=binding, archive_id=self._archive_id,
                projection_version=projection["projection_version"],
                snapshot_sha256=_digest(snapshot_bytes),
                projection_sha256=_digest(projection_bytes),
            )
            if self._authorize(credential, view_id, "bind") != binding:
                raise LineageDenied(_DENIED)
            encoded = canonical(asdict(lineage))
            with closing(self._connect()) as db, db:
                db.execute("INSERT OR IGNORE INTO handles VALUES(?,?)", (view_id, encoded))
                row = db.execute("SELECT lineage FROM handles WHERE view_id=?", (view_id,)).fetchone()
                if row is None or row[0] != encoded:
                    raise LineageDenied(_DENIED)
        except (ValueError, OSError, RuntimeError, RecursionError, TypeError, sqlite3.Error):
            raise LineageDenied(_DENIED) from None

    def resolve(self, credential, view_id):
        """Resolve only with present audit permission and a matching current binding."""
        try:
            current = self._authorize(credential, view_id, "resolve")
            with closing(self._connect()) as db:
                row = db.execute("SELECT lineage FROM handles WHERE view_id=?", (view_id,)).fetchone()
            if row is None:
                raise LineageDenied(_DENIED)
            record = json.loads(row[0])
            stored = ViewBinding(**record.pop("binding"))
            if (record.get("archive_id") != self._archive_id
                    or current != stored or self._authorize(credential, view_id, "resolve") != current):
                raise LineageDenied(_DENIED)
            return ExactLineage(binding=stored, **record)
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, sqlite3.Error):
            raise LineageDenied(_DENIED) from None

    def verify_replay(self, credential, view_id, *, ledger, snapshot_bytes, result_bytes,
                      projection_bytes, max_bytes, max_members, max_manifest_bytes,
                      max_projection_bytes):
        """Verify exact authorized input, output projection bytes and a saved MSE run."""
        from integrations.mse_snapshot.ledger import verify_ledger_replay_manifest

        try:
            evidence = self.resolve(credential, view_id)
            if (type(max_projection_bytes) is not int
                    or not 0 < max_projection_bytes
                    or len(projection_bytes) > max_projection_bytes
                    or _digest(snapshot_bytes) != evidence.snapshot_sha256
                    or _digest(projection_bytes) != evidence.projection_sha256):
                raise LineageDenied(_DENIED)
            result = verify_ledger_replay_manifest(
                snapshot_bytes, result_bytes, ledger=ledger,
                expected_scope=evidence.binding.scope,
                expected_archive_id=evidence.archive_id,
                max_bytes=max_bytes, max_members=max_members, max_manifest_bytes=max_manifest_bytes,
            )
            if self.resolve(credential, view_id) != evidence:
                raise LineageDenied(_DENIED)
            return result
        except (ValueError, OSError, RuntimeError, RecursionError, TypeError, sqlite3.Error):
            raise LineageDenied(_DENIED) from None
