"""Isolated SQLite replay store. Existing unrecognized databases are never opened writable."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3

from .contracts import ContractError, canonical, digest, measurement_identity, timestamp, utc

APPLICATION_ID = 0x4D534531

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE artifacts(sha256 TEXT PRIMARY KEY, content BLOB NOT NULL, metadata_json TEXT NOT NULL);
CREATE TABLE observations(id TEXT PRIMARY KEY, measurement_hash TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE TABLE observation_artifacts(observation_id TEXT NOT NULL REFERENCES observations(id),
    artifact_sha256 TEXT NOT NULL REFERENCES artifacts(sha256), PRIMARY KEY(observation_id, artifact_sha256));
CREATE TABLE tombstones(id TEXT PRIMARY KEY, observation_id TEXT NOT NULL, deleted_at TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL REFERENCES artifacts(sha256));
CREATE TABLE rejected_imports(artifact_sha256 TEXT PRIMARY KEY REFERENCES artifacts(sha256), reason TEXT NOT NULL);
CREATE TABLE runs(run_id TEXT PRIMARY KEY, dataset_hash TEXT NOT NULL, model_version TEXT NOT NULL,
    config_hash TEXT NOT NULL, output_json TEXT NOT NULL);
CREATE TABLE run_invalidations(run_id TEXT NOT NULL REFERENCES runs(run_id), artifact_sha256 TEXT NOT NULL,
    reason TEXT NOT NULL, PRIMARY KEY(run_id, artifact_sha256));
"""


class Store:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.is_symlink():
            raise ContractError("Refusing a symlink database")
        new = not self.path.exists()
        if not new:
            check = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)
            try:
                if check.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
                    raise ContractError("Refusing an unrecognized database")
                version = check.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
                if version != ("mse.sqlite/0.1",):
                    raise ContractError("Unsupported replay database version")
            finally:
                check.close()
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
        self.db = sqlite3.connect(self.path)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA journal_mode=DELETE")
        if new:
            self.db.executescript(SCHEMA)
            self.db.execute(f"PRAGMA application_id={APPLICATION_ID}")
            self.db.execute("INSERT INTO metadata VALUES('schema_version','mse.sqlite/0.1')")
            for table in ("artifacts", "observations", "observation_artifacts", "tombstones", "runs", "run_invalidations", "rejected_imports"):
                for operation in ("UPDATE", "DELETE"):
                    self.db.execute(f"CREATE TRIGGER immutable_{table}_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'immutable replay evidence'); END")
            self.db.commit()

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def import_batch(self, data, observations, tombstones, metadata):
        artifact_hash = hashlib.sha256(data).hexdigest()
        incoming = {}
        conflict = False
        for record in observations:
            key = record["observation_id"]
            identity_hash = digest(measurement_identity(record))
            if key in incoming and incoming[key][0] != identity_hash:
                conflict = True
            incoming.setdefault(key, (identity_hash, record))
            prior = self.db.execute("SELECT measurement_hash FROM observations WHERE id=?", (key,)).fetchone()
            if prior and prior[0] != identity_hash:
                conflict = True
        if conflict:
            with self.db:
                self.db.execute("INSERT OR IGNORE INTO artifacts VALUES(?,?,?)", (artifact_hash, data, canonical(metadata)))
                self.db.execute("INSERT OR IGNORE INTO rejected_imports VALUES(?,?)", (artifact_hash, "conflicting_immutable_sample"))
            raise ContractError("Conflicting immutable sample; entire import rejected and raw artifact retained")
        added = duplicate = deleted = 0
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO artifacts VALUES(?,?,?)", (artifact_hash, data, canonical(metadata)))
            for key, (identity_hash, record) in incoming.items():
                cursor = self.db.execute("INSERT OR IGNORE INTO observations VALUES(?,?,?)", (key, identity_hash, canonical(record)))
                added += cursor.rowcount
                duplicate += 1 - cursor.rowcount
                self.db.execute("INSERT OR IGNORE INTO observation_artifacts VALUES(?,?)", (key, artifact_hash))
            duplicate += len(observations) - len(incoming)
            for tombstone in tombstones:
                deletion_id = digest([tombstone["observation_id"], tombstone["deleted_at"]])
                cursor = self.db.execute("INSERT OR IGNORE INTO tombstones VALUES(?,?,?,?)", (
                    deletion_id, tombstone["observation_id"], tombstone["deleted_at"], artifact_hash))
                deleted += cursor.rowcount
            if added or deleted:
                # Conservative invalidation of every historical run. They remain auditable.
                self.db.execute("INSERT OR IGNORE INTO run_invalidations SELECT run_id, ?, 'observation_set_changed_replay_required' FROM runs", (artifact_hash,))
        return {"artifact_sha256": artifact_hash, "added": added, "duplicates": duplicate,
                "new_tombstones": deleted, "raw_artifact_retained": True}

    def active_observations(self, source_receipt_cutoff=None):
        """Final retrospective snapshot filter, never a per-target historical knowledge set."""
        cutoff = timestamp(source_receipt_cutoff) if source_receipt_cutoff else None
        deleted = {key for key, when in self.db.execute("SELECT observation_id, deleted_at FROM tombstones")
                   if cutoff is None or timestamp(when) <= cutoff}
        result = []
        for key, payload in self.db.execute("SELECT id,payload_json FROM observations ORDER BY id"):
            record = json.loads(payload)
            if key not in deleted and (cutoff is None or (
                    timestamp(record["received_at"]) <= cutoff and timestamp(record["event_end"]) <= cutoff)):
                result.append(record)
        return sorted(result, key=lambda r: (r["event_start"], r["observation_id"]))

    def evidence_manifest(self):
        return {
            "artifact_sha256": [r[0] for r in self.db.execute("SELECT sha256 FROM artifacts ORDER BY sha256")],
            "accepted_observation_ids": [r[0] for r in self.db.execute("SELECT id FROM observations ORDER BY id")],
            "tombstone_ids": [r[0] for r in self.db.execute("SELECT id FROM tombstones ORDER BY id")],
            "rejected_artifact_sha256": [r[0] for r in self.db.execute("SELECT artifact_sha256 FROM rejected_imports ORDER BY artifact_sha256")],
        }

    def save_run(self, output):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO runs VALUES(?,?,?,?,?)", (
                output["run_id"], output["dataset_hash"], output["model_version"],
                output["config_hash"], canonical(output)))
