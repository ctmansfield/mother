"""Transactional local evidence archive; Parquet files are rebuildable views.

Use a filesystem with reliable SQLite locking. Initialization only installs the
package-owned, additive SQLite migration; it never touches PostgreSQL or an
existing unrecognized database. Original bytes and normalized records are
immutable. A source head is a projection of the latest response we observed,
not an assertion that a server modification time was an original arrival time.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from . import CONTRACT_VERSION
from .contracts import canonical_json, content_hash, validate_record
from .time import parse_timestamp, utc_iso

SCHEMA_VERSION = 1
_REVISION_COLUMNS = (
    "revision_id",
    "source_instance",
    "collection",
    "source_key",
    "native_id",
    "revision_hash",
    "raw_json",
    "first_seen_at",
    "ingested_at",
    "source_available_at",
    "source_modified_at",
    "measurement_start",
    "measurement_end",
    "import_run_id",
    "disposition",
    "rejection_reason",
    "artifact_sha256",
)


def _now() -> str:
    return utc_iso(datetime.now(timezone.utc))


class Archive:
    """One local SQLite connection, with explicit short write transactions."""

    def __init__(self, path: str | Path = "storage/physiology/archive.sqlite3"):
        self.path = str(path)
        if self.path != ":memory:":
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                target.touch(mode=0o600, exist_ok=False)
            except FileExistsError:
                pass
        self.connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA synchronous = FULL")
        try:
            self._initialize()
        except BaseException:
            self.connection.close()
            raise

    def _initialize(self):
        tables = {
            row[0]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if tables and "schema_versions" not in tables:
            raise ValueError("Refusing an unrecognized existing SQLite database")
        if "schema_versions" in tables:
            versions = self.connection.execute(
                "SELECT version, contract_version FROM schema_versions ORDER BY version"
            ).fetchall()
            if [(r[0], r[1]) for r in versions] != [(SCHEMA_VERSION, CONTRACT_VERSION)]:
                raise ValueError("Unsupported or incomplete physiology archive schema")
            return
        migration = (
            Path(__file__).parent / "migrations" / "0001_archive.sql"
        ).read_text(encoding="utf-8")
        try:
            self.connection.executescript("BEGIN IMMEDIATE;\n" + migration)
            self.connection.execute(
                "INSERT INTO schema_versions(version,contract_version,applied_at) VALUES (?,?,?)",
                (SCHEMA_VERSION, CONTRACT_VERSION, _now()),
            )
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    @contextmanager
    def _transaction(self):
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()

    def begin_run(
        self,
        source_instance: str,
        collection: str,
        adapter_version: str,
        request: dict,
        started_at=None,
    ) -> str:
        if not all(
            isinstance(v, str) and v
            for v in (source_instance, collection, adapter_version)
        ):
            raise ValueError(
                "Source instance, collection and adapter version are required"
            )
        run_id = "import:" + uuid.uuid4().hex
        with self._transaction():
            self.connection.execute(
                """INSERT INTO import_runs
                (run_id,source_instance,collection,adapter_version,contract_version,
                 started_at,status,request_json) VALUES (?,?,?,?,?,?,'running',?)""",
                (
                    run_id,
                    source_instance,
                    collection,
                    adapter_version,
                    CONTRACT_VERSION,
                    utc_iso(started_at) if started_at else _now(),
                    canonical_json(request),
                ),
            )
        return run_id

    def commit_batch(
        self,
        run_id: str,
        revisions=(),
        normalized_records=(),
        *,
        artifacts=(),
        checkpoint: dict | None = None,
        complete: bool = False,
        counts: dict | None = None,
    ) -> dict:
        """Durably write evidence; a checkpoint is allowed only with completion.

        ``counts`` is the caller's cumulative manifest, not a per-batch delta.
        ``observed_at`` may accompany a revision for the current sighting; it
        never changes that revision's immutable first_seen_at or ingested_at.
        """
        if checkpoint is not None and not complete:
            raise ValueError("A checkpoint requires a completed import range")
        result = {"new_revisions": 0, "repeated_revisions": 0, "new_records": 0}
        with self._transaction():
            run = self.connection.execute(
                "SELECT * FROM import_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if run is None or run["status"] != "running":
                raise ValueError("Import run is absent or already finalized")
            for artifact in artifacts:
                content = artifact["content"]
                if not isinstance(content, bytes):
                    raise ValueError("An original artifact must contain bytes")
                digest = hashlib.sha256(content).hexdigest()
                if digest != artifact["sha256"]:
                    raise ValueError("Original artifact byte hash mismatch")
                existing = self.connection.execute(
                    "SELECT content,media_type FROM raw_artifacts WHERE sha256=?",
                    (digest,),
                ).fetchone()
                if existing is not None and bytes(existing["content"]) != content:
                    raise ValueError("Original artifact collision")
                self.connection.execute(
                    "INSERT OR IGNORE INTO raw_artifacts VALUES (?,?,?,?)",
                    (
                        digest,
                        artifact.get("media_type", "application/json"),
                        content,
                        utc_iso(artifact.get("created_at") or _now()),
                    ),
                )
            for revision in revisions:
                if (revision["source_instance"], revision["collection"]) != (
                    run["source_instance"],
                    run["collection"],
                ):
                    raise ValueError(
                        "A revision must belong to its import source and collection"
                    )
                raw = json.loads(revision["raw_json"])
                if content_hash(raw) != revision["revision_hash"]:
                    raise ValueError("Canonical source revision hash mismatch")
                if canonical_json(raw) != revision["raw_json"]:
                    raise ValueError(
                        "raw_json must be canonical; original bytes belong in artifacts"
                    )
                if parse_timestamp(revision["ingested_at"]) < parse_timestamp(
                    revision["first_seen_at"]
                ):
                    raise ValueError("Revision ingestion precedes first observation")
                existing = self.connection.execute(
                    "SELECT * FROM source_revisions WHERE revision_id=?",
                    (revision["revision_id"],),
                ).fetchone()
                if existing is None:
                    if revision["import_run_id"] != run_id:
                        raise ValueError(
                            "A new revision must name the current import run"
                        )
                    columns = ",".join(_REVISION_COLUMNS)
                    placeholders = ",".join("?" for _ in _REVISION_COLUMNS)
                    self.connection.execute(
                        f"INSERT INTO source_revisions ({columns}) VALUES ({placeholders})",
                        [revision.get(k) for k in _REVISION_COLUMNS],
                    )
                    result["new_revisions"] += 1
                else:
                    if any(
                        existing[k] != revision[k]
                        for k in (
                            "source_instance",
                            "collection",
                            "source_key",
                            "native_id",
                            "revision_hash",
                            "raw_json",
                        )
                    ):
                        raise ValueError(
                            "An immutable source revision cannot be replaced"
                        )
                    result["repeated_revisions"] += 1
                observed_at = utc_iso(
                    revision.get("observed_at") or revision["first_seen_at"]
                )
                previous_sighting = self.connection.execute(
                    "SELECT observed_at FROM run_revisions WHERE run_id=? AND revision_id=?",
                    (run_id, revision["revision_id"]),
                ).fetchone()
                if previous_sighting is None or parse_timestamp(
                    observed_at
                ) >= parse_timestamp(previous_sighting[0]):
                    self.connection.execute(
                        """INSERT INTO run_revisions VALUES (?,?,?) ON CONFLICT(run_id,revision_id)
                        DO UPDATE SET observed_at=excluded.observed_at""",
                        (run_id, revision["revision_id"], observed_at),
                    )
                head = self.connection.execute(
                    """SELECT observed_at FROM source_heads
                    WHERE source_instance=? AND collection=? AND source_key=?""",
                    (
                        revision["source_instance"],
                        revision["collection"],
                        revision["source_key"],
                    ),
                ).fetchone()
                if head is None or parse_timestamp(observed_at) >= parse_timestamp(
                    head[0]
                ):
                    self.connection.execute(
                        """INSERT INTO source_heads VALUES (?,?,?,?,?,?)
                        ON CONFLICT(source_instance,collection,source_key) DO UPDATE SET
                        revision_id=excluded.revision_id, observed_at=excluded.observed_at,
                        run_id=excluded.run_id""",
                        (
                            revision["source_instance"],
                            revision["collection"],
                            revision["source_key"],
                            revision["revision_id"],
                            observed_at,
                            run_id,
                        ),
                    )
            for record in normalized_records:
                validate_record(record)
                revision_id = record.get("source_revision_id")
                if record["record_type"] == "session":
                    # The first declared source anchors the current-revision
                    # projection; the complete list is retained in record_json.
                    references = record["source_revision_ids"]
                    revision_id = references[0] if references else None
                if not revision_id:
                    raise ValueError(
                        "An imported normalized record requires source lineage"
                    )
                source = self.connection.execute(
                    "SELECT source_instance,collection FROM source_revisions WHERE revision_id=?",
                    (revision_id,),
                ).fetchone()
                if source is None or tuple(source) != (
                    run["source_instance"],
                    run["collection"],
                ):
                    raise ValueError(
                        "Normalized record source is not in this import namespace"
                    )
                subject = self.connection.execute(
                    """SELECT n.record_json FROM normalized_records n
                    JOIN source_revisions r ON r.revision_id=n.revision_id
                    WHERE r.source_instance=? AND r.collection=? LIMIT 1""",
                    (run["source_instance"], run["collection"]),
                ).fetchone()
                if (
                    subject is not None
                    and json.loads(subject[0])["subject_id"] != record["subject_id"]
                ):
                    raise ValueError(
                        "Source namespace is already bound to a different subject"
                    )
                references = set(
                    record.get("lineage", [])
                    + record.get("source_revision_ids", [])
                    + [revision_id]
                )
                for reference in references:
                    referenced = self.connection.execute(
                        """SELECT r.source_instance,r.collection,i.request_json
                        FROM source_revisions r
                        JOIN import_runs i ON i.run_id=r.import_run_id
                        WHERE r.revision_id=?""",
                        (reference,),
                    ).fetchone()
                    if referenced is None:
                        raise ValueError(
                            "Normalized record has unresolved source lineage"
                        )
                    declared_subject = json.loads(referenced["request_json"]).get(
                        "subject_id"
                    )
                    bound = self.connection.execute(
                        """SELECT n.record_json FROM normalized_records n
                        JOIN source_revisions r ON r.revision_id=n.revision_id
                        WHERE r.source_instance=? AND r.collection=? LIMIT 1""",
                        (referenced["source_instance"], referenced["collection"]),
                    ).fetchone()
                    bound_subject = (
                        json.loads(bound[0])["subject_id"] if bound else None
                    )
                    if any(
                        subject_id is not None and subject_id != record["subject_id"]
                        for subject_id in (declared_subject, bound_subject)
                    ):
                        raise ValueError(
                            "Source lineage belongs to a different subject"
                        )
                body = canonical_json(record)
                existing = self.connection.execute(
                    "SELECT record_json FROM normalized_records WHERE record_id=?",
                    (record["id"],),
                ).fetchone()
                if existing is not None and existing[0] != body:
                    raise ValueError(
                        "An immutable normalized record needs a new processing-version ID"
                    )
                if existing is None:
                    self.connection.execute(
                        "INSERT INTO normalized_records VALUES (?,?,?,?,?)",
                        (
                            record["id"],
                            revision_id,
                            record["record_type"],
                            body,
                            record["processing_version"],
                        ),
                    )
                    result["new_records"] += 1
            if counts is not None:
                self.connection.execute(
                    "UPDATE import_runs SET counts_json=? WHERE run_id=?",
                    (canonical_json(counts), run_id),
                )
            if complete:
                self.connection.execute(
                    "UPDATE import_runs SET status='complete',completed_at=? WHERE run_id=?",
                    (_now(), run_id),
                )
                if checkpoint is not None:
                    self.connection.execute(
                        """INSERT INTO checkpoints VALUES (?,?,?,?)
                        ON CONFLICT(source_instance,collection) DO UPDATE SET
                        checkpoint_json=excluded.checkpoint_json,run_id=excluded.run_id""",
                        (
                            run["source_instance"],
                            run["collection"],
                            canonical_json(checkpoint),
                            run_id,
                        ),
                    )
        return result

    def fail_run(
        self,
        run_id: str,
        error: str,
        counts: dict | None = None,
        *,
        incomplete: bool = False,
    ):
        """Record a controlled, credential-free failure; retain already saved evidence."""
        with self._transaction():
            changed = self.connection.execute(
                """UPDATE import_runs SET status=?,completed_at=?,error=?,
                counts_json=COALESCE(?,counts_json) WHERE run_id=? AND status='running'""",
                (
                    "incomplete" if incomplete else "failed",
                    _now(),
                    error,
                    canonical_json(counts) if counts is not None else None,
                    run_id,
                ),
            ).rowcount
            if not changed:
                raise ValueError("Import run is absent or already finalized")

    def checkpoint(self, source_instance: str, collection: str) -> dict | None:
        row = self.connection.execute(
            "SELECT checkpoint_json FROM checkpoints WHERE source_instance=? AND collection=?",
            (source_instance, collection),
        ).fetchone()
        return json.loads(row[0]) if row else None

    def import_run(self, run_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM import_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["request"] = json.loads(result.pop("request_json"))
        result["counts"] = json.loads(result.pop("counts_json"))
        return result

    def import_runs(self, source_instance=None, collection=None) -> list[dict]:
        clauses, params = [], []
        for field, value in (
            ("source_instance", source_instance),
            ("collection", collection),
        ):
            if value is not None:
                clauses.append(f"{field}=?")
                params.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        ids = self.connection.execute(
            "SELECT run_id FROM import_runs" + where, params
        ).fetchall()
        return sorted(
            (self.import_run(row[0]) for row in ids),
            key=lambda run: (parse_timestamp(run["started_at"]), run["run_id"]),
        )

    def revision(self, revision_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM source_revisions WHERE revision_id=?", (revision_id,)
        ).fetchone()
        return dict(row) if row else None

    def revisions(self, source_instance=None, collection=None) -> list[dict]:
        clauses, params = [], []
        for field, value in (
            ("source_instance", source_instance),
            ("collection", collection),
        ):
            if value is not None:
                clauses.append(f"{field}=?")
                params.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT * FROM source_revisions" + where, params
            )
        ]

    def records(
        self, kind=None, source_instance=None, collection=None, *, current=True
    ) -> list[dict]:
        query = "SELECT n.record_json FROM normalized_records n JOIN source_revisions r ON r.revision_id=n.revision_id"
        if current:
            query += " JOIN source_heads h ON h.revision_id=r.revision_id"
        clauses, params = ["r.disposition='accepted'"], []
        for field, value in (
            ("n.kind", kind),
            ("r.source_instance", source_instance),
            ("r.collection", collection),
        ):
            if value is not None:
                clauses.append(f"{field}=?")
                params.append(value)
        query += " WHERE " + " AND ".join(clauses)
        records = [json.loads(row[0]) for row in self.connection.execute(query, params)]
        earliest = datetime.min.replace(tzinfo=timezone.utc)

        def ordering(record):
            timestamp = (
                record.get("measurement_start")
                or record.get("occurrence_start")
                or record.get("start")
            )
            return (parse_timestamp(timestamp) if timestamp else earliest, record["id"])

        return sorted(records, key=ordering)

    def current_records(
        self, kind=None, source_instance=None, collection=None
    ) -> list[dict]:
        return self.records(kind, source_instance, collection, current=True)
