"""Local synthetic artifact custody with PF-001 as the physiological archive."""

from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re
import sqlite3
from uuid import uuid4

from mother.physiology.archive import Archive
from mother.physiology.contracts import canonical_json
from mother.physiology.time import utc_iso

from .receipt import encode_receipt


class BatchConflict(ValueError):
    """The scoped batch is already bound to different immutable inputs."""


class RecoveryError(RuntimeError):
    """The journal and archive require reconciliation before proceeding."""


@dataclass(frozen=True)
class Scope:
    subject_id: str
    source_system: str
    source_instance: str
    collection: str

    def fields(self):
        return {
            "subject_id": self.subject_id,
            "source_system": self.source_system,
            "source_instance": self.source_instance,
            "collection": self.collection,
        }

    @property
    def archive_source(self):
        digest = hashlib.sha256(canonical_json(self.fields()).encode()).hexdigest()
        return f"mse:scope:{digest}"


@dataclass(frozen=True)
class NormalizationContext:
    scope: Scope
    run_id: str
    artifact_sha256: str
    mother_received_at: str


class LocalIngest:
    """One private synthetic journal/archive pair in a caller-selected directory."""

    def __init__(self, root, *, clock=lambda: datetime.now(timezone.utc)):
        root.mkdir(mode=0o700, exist_ok=True)
        if root.is_symlink() or root.stat().st_mode & 0o077:
            raise ValueError("Select a private local ingest directory")
        self.journal = root / "custody.sqlite3"
        self.archive = root / "physiology.sqlite3"
        self.clock = clock

    @contextmanager
    def _write(self):
        if self.journal.is_symlink() or self.archive.is_symlink():
            raise RecoveryError("Store paths must be local files")
        if self.archive.exists() and not self.journal.is_file():
            raise RecoveryError("PF-001 archive is missing its custody journal")
        self.journal.touch(mode=0o600, exist_ok=True)
        with closing(sqlite3.connect(self.journal, timeout=30)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA synchronous=FULL")
            with db:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS deliveries (
                        scope TEXT NOT NULL, batch_id TEXT NOT NULL,
                        artifact BLOB NOT NULL, artifact_sha256 TEXT NOT NULL,
                        export_sha256 TEXT NOT NULL, source_schema TEXT NOT NULL,
                        adapter_version TEXT NOT NULL, receipt_id TEXT NOT NULL UNIQUE,
                        received_at TEXT NOT NULL, run_id TEXT, committed_at TEXT,
                        commit_sequence INTEGER UNIQUE,
                        PRIMARY KEY (scope, batch_id)
                    )
                """
                )
                db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS commits (sequence INTEGER PRIMARY KEY)
                """
                )
                yield db

    def _checkpoint(self, phase):
        """Fault injection point for local tests."""

    def ingest(
        self,
        scope,
        batch_id,
        original,
        *,
        export_sha256,
        source_schema,
        adapter_version,
        normalize,
    ):
        """Bind exact bytes, then commit (PF-001 revisions, records) from normalize.

        The local adapter callback receives the retained bytes and a
        NormalizationContext. The caller binds its provisional export digest.
        """
        fields = (*scope.fields().values(), batch_id, source_schema, adapter_version)
        if any(not isinstance(value, str) or not value.strip() for value in fields):
            raise ValueError("Scope, batch identity and versions must be nonempty text")
        if not isinstance(original, bytes) or not original:
            raise ValueError("Artifact must contain original bytes")
        if not isinstance(export_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", export_sha256
        ):
            raise ValueError("Export digest must be lowercase SHA-256")
        digest = hashlib.sha256(original).hexdigest()
        key = (canonical_json(scope.fields()), batch_id)
        with self._write() as db:
            row = self._delivery(db, key)
            if row is None:
                db.execute(
                    """
                    INSERT INTO deliveries
                        (scope, batch_id, artifact, artifact_sha256, export_sha256,
                         source_schema, adapter_version, receipt_id, received_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        *key,
                        original,
                        digest,
                        export_sha256,
                        source_schema,
                        adapter_version,
                        "local:" + uuid4().hex,
                        utc_iso(self.clock()),
                    ),
                )
            else:
                if (
                    hashlib.sha256(row["artifact"]).hexdigest()
                    != row["artifact_sha256"]
                ):
                    raise RecoveryError("Retained artifact digest mismatch")
                if (
                    row["artifact"],
                    row["export_sha256"],
                    row["source_schema"],
                    row["adapter_version"],
                ) != (original, export_sha256, source_schema, adapter_version):
                    raise BatchConflict("Scoped batch already binds different inputs")
        self._checkpoint("custody")
        with self._write() as db:
            row = self._delivery(db, key)
            if row["run_id"] and not self.archive.is_file():
                raise RecoveryError("Accepted delivery is missing its PF-001 archive")
            with Archive(self.archive) as archive:
                run = self._archive_run(archive, scope, row, normalize)
                if row["commit_sequence"] is None:
                    sequence = db.execute(
                        "INSERT INTO commits DEFAULT VALUES"
                    ).lastrowid
                    db.execute(
                        """
                        UPDATE deliveries SET run_id=?, committed_at=?, commit_sequence=?
                        WHERE scope=? AND batch_id=?
                    """,
                        (run["run_id"], run["completed_at"], sequence, *key),
                    )
                    row = self._delivery(db, key)
                elif row["committed_at"] != run["completed_at"]:
                    raise RecoveryError(
                        "Receipt does not match the PF-001 completion time"
                    )
                receipt = encode_receipt(scope, row)
        self._checkpoint("receipt")
        return receipt

    @staticmethod
    def _delivery(db, key):
        return db.execute(
            "SELECT * FROM deliveries WHERE scope=? AND batch_id=?", key
        ).fetchone()

    def _archive_run(self, archive, scope, row, normalize):
        request = {
            "mse_receipt_id": row["receipt_id"],
            "subject_id": scope.subject_id,
            "scope": scope.fields(),
            "batch_id": row["batch_id"],
            "artifact_sha256": row["artifact_sha256"],
            "export_sha256": row["export_sha256"],
            "source_schema": row["source_schema"],
        }
        candidates = [
            run
            for run in archive.import_runs(scope.archive_source, scope.collection)
            if run["request"].get("mse_receipt_id") == row["receipt_id"]
        ]
        if len(candidates) > 1 or (row["run_id"] and not candidates):
            raise RecoveryError("Missing or ambiguous PF-001 run binding")
        if candidates:
            run = candidates[0]
            if (
                run["request"] != request
                or run["adapter_version"] != row["adapter_version"]
                or (row["run_id"] and row["run_id"] != run["run_id"])
            ):
                raise RecoveryError("PF-001 run does not match the journal binding")
            run_id = run["run_id"]
        else:
            run_id = archive.begin_run(
                scope.archive_source,
                scope.collection,
                row["adapter_version"],
                request,
                started_at=row["received_at"],
            )
            self._checkpoint("run")
            run = archive.import_run(run_id)
        if run["status"] == "running" and row["run_id"] is None:
            context = NormalizationContext(
                scope, run_id, row["artifact_sha256"], row["received_at"]
            )
            revisions, records = normalize(row["artifact"], context)
            revisions, records = list(revisions), list(records)
            if any(record.get("subject_id") != scope.subject_id for record in records):
                raise ValueError(
                    "Normalized record subject does not match delivery scope"
                )
            if any(
                revision.get("artifact_sha256") != row["artifact_sha256"]
                for revision in revisions
            ):
                raise ValueError("Source revision lacks the delivery artifact binding")
            archive.commit_batch(
                run_id,
                revisions,
                records,
                artifacts=[
                    {
                        "sha256": row["artifact_sha256"],
                        "content": row["artifact"],
                        "created_at": row["received_at"],
                    }
                ],
                complete=True,
                counts={
                    "revisions": sorted(
                        {revision["revision_id"] for revision in revisions}
                    ),
                    "records": {
                        record["id"]: hashlib.sha256(
                            canonical_json(record).encode()
                        ).hexdigest()
                        for record in records
                    },
                },
            )
            self._checkpoint("archive")
            run = archive.import_run(run_id)
        if run["status"] != "complete" or not run["completed_at"]:
            raise RecoveryError("PF-001 run has no verified completion")
        retained = archive.connection.execute(
            "SELECT content FROM raw_artifacts WHERE sha256=?",
            (row["artifact_sha256"],),
        ).fetchone()
        if retained is None or retained[0] != row["artifact"]:
            raise RecoveryError("PF-001 artifact does not match retained custody bytes")
        self._verify_members(archive, run)
        return run

    @staticmethod
    def _verify_members(archive, run):
        manifest = run["counts"]
        if not isinstance(manifest, dict) or set(manifest) != {"revisions", "records"}:
            raise RecoveryError("PF-001 run is missing its membership manifest")
        revisions = archive.connection.execute(
            """SELECT r.revision_id FROM run_revisions s
               JOIN source_revisions r ON r.revision_id=s.revision_id
               WHERE s.run_id=? ORDER BY r.revision_id""",
            (run["run_id"],),
        )
        if [revision[0] for revision in revisions] != manifest["revisions"]:
            raise RecoveryError("PF-001 run revision membership mismatch")
        for record_id, digest in manifest["records"].items():
            record = archive.connection.execute(
                "SELECT record_json FROM normalized_records WHERE record_id=?",
                (record_id,),
            ).fetchone()
            if (
                record is None
                or hashlib.sha256(record[0].encode()).hexdigest() != digest
            ):
                raise RecoveryError("PF-001 normalized record digest mismatch")
