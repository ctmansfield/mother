"""Offline restore rehearsal using a pinned PF-001 checkout and fresh synthetic data."""

from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
import uuid

PF_COMMIT = "b4e70b7123689ec164ba09e2974645ae36b184a2"
WHEN = "2026-11-20T00:00:00Z"
DATABASE = "archive.sqlite3"
MEMBERS = (DATABASE, "original.json", "checkpoint.json")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_only(path):
    return sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)


def verify_restore(backup, destination):
    manifest = json.loads((backup / "manifest.json").read_text())
    if manifest.get("pf_commit") != PF_COMMIT or set(manifest.get("members", {})) != set(MEMBERS):
        raise ValueError("Unexpected restore manifest")
    for member in MEMBERS:
        source = backup / member
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"Missing or unsafe backup member: {member}")
        if digest(source.read_bytes()) != manifest["members"][member]:
            raise ValueError(f"Backup digest mismatch: {member}")
    destination.mkdir(mode=0o700)
    for member in MEMBERS:
        shutil.copyfile(backup / member, destination / member)
    fixture = json.loads((destination / "checkpoint.json").read_text())
    original = (destination / "original.json").read_bytes()

    with closing(read_only(destination / DATABASE)) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("SQLite integrity failed")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("SQLite foreign key integrity failed")
        version = db.execute("SELECT version, contract_version FROM schema_versions").fetchall()
        if version != [(1, "1.0.0")]:
            raise ValueError("Unexpected archive schema version")
        artifacts = db.execute("SELECT sha256, content FROM raw_artifacts").fetchall()
        if artifacts != [(digest(original), original)]:
            raise ValueError("Original artifact binding mismatch")
        revisions = db.execute(
            """SELECT revision_id, native_id, disposition, artifact_sha256
               FROM source_revisions WHERE import_run_id = ? ORDER BY disposition""",
            (fixture["run_id"],),
        ).fetchall()
        if revisions != [tuple(row) for row in fixture["revisions"]] or any(
            row[3] != digest(original) for row in revisions
        ):
            raise ValueError("Accepted revision or tombstone linkage mismatch")
        checkpoint = db.execute(
            """SELECT i.status, c.checkpoint_json, c.run_id
               FROM checkpoints c JOIN import_runs i ON i.run_id = c.run_id
               WHERE c.source_instance = ? AND c.collection = ?""",
            (fixture["source"], fixture["collection"]),
        ).fetchall()
        if len(checkpoint) != 1 or (
            checkpoint[0][0], json.loads(checkpoint[0][1]), checkpoint[0][2]
        ) != ("complete", fixture["checkpoint"], fixture["run_id"]):
            raise ValueError("Completed run and checkpoint linkage mismatch")


def build_backup(root):
    from mother.physiology.archive import Archive
    from mother.physiology.contracts import canonical_json, content_hash, stable_id

    source = "synthetic:recovery:" + uuid.uuid4().hex
    collection = "synthetic_recovery"
    payload = [
        {"id": str(uuid.uuid4()), "synthetic": True, "operation": "upsert"},
        {"id": str(uuid.uuid4()), "synthetic": True, "operation": "delete"},
    ]
    original = (json.dumps(payload, indent=2) + "\n").encode()
    checkpoint = {"synthetic_offset": 2}
    primary = root / "primary.sqlite3"
    backup = root / "backup"
    backup.mkdir(mode=0o700)
    with Archive(primary) as archive:
        archive.connection.execute("PRAGMA journal_mode=WAL")
        run_id = archive.begin_run(source, collection, "recovery-fixture/1", {}, started_at=WHEN)
        revisions = []
        for record, disposition in zip(payload, ("accepted", "deleted")):
            key = "native:" + record["id"]
            value_hash = content_hash(record)
            revisions.append(dict(
                revision_id=stable_id("revision", source, collection, key, value_hash),
                source_instance=source, collection=collection, source_key=key,
                native_id=record["id"], revision_hash=value_hash, raw_json=canonical_json(record),
                first_seen_at=WHEN, ingested_at=WHEN, import_run_id=run_id,
                disposition=disposition, artifact_sha256=digest(original),
            ))
        archive.commit_batch(
            run_id, revisions, artifacts=[{"sha256": digest(original), "content": original}],
            checkpoint=checkpoint, complete=True,
        )
        # In-flight writer state must stay out of a second connection's backup.
        archive.connection.execute("BEGIN IMMEDIATE")
        archive.connection.execute("DELETE FROM checkpoints")
        try:
            with closing(read_only(primary)) as reader, closing(sqlite3.connect(backup / DATABASE)) as copy:
                reader.backup(copy)
        finally:
            archive.connection.rollback()
    with closing(sqlite3.connect(backup / DATABASE)) as copy:
        if copy.execute("PRAGMA journal_mode=DELETE").fetchone() != ("delete",):
            raise ValueError("Backup could not be sealed as a standalone file")
    primary.unlink()
    (backup / "original.json").write_bytes(original)
    (backup / "checkpoint.json").write_text(json.dumps(dict(
        run_id=run_id, source=source, collection=collection, checkpoint=checkpoint,
        revisions=[[r[key] for key in ("revision_id", "native_id", "disposition", "artifact_sha256")]
                   for r in revisions],
    )))
    write_manifest(backup)
    return backup


def write_manifest(backup):
    (backup / "manifest.json").write_text(json.dumps({
        "pf_commit": PF_COMMIT,
        "members": {member: digest((backup / member).read_bytes()) for member in MEMBERS},
    }))


class RestoreTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="mse-synthetic-recovery-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.backup = build_backup(self.root)
        self.restored = self.root / "restored"

    def test_restore_without_primary(self):
        self.assertFalse((self.root / "primary.sqlite3").exists())
        verify_restore(self.backup, self.restored)

    def test_missing_original(self):
        (self.backup / "original.json").unlink()
        with self.assertRaisesRegex(ValueError, "Missing or unsafe"):
            verify_restore(self.backup, self.restored)
        self.assertFalse(self.restored.exists())

    def test_changed_backup_member(self):
        (self.backup / "original.json").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            verify_restore(self.backup, self.restored)
        self.assertFalse(self.restored.exists())

    def test_rehashed_mismatched_original(self):
        (self.backup / "original.json").write_bytes(b"unrelated synthetic artifact")
        write_manifest(self.backup)
        with self.assertRaisesRegex(ValueError, "artifact binding"):
            verify_restore(self.backup, self.restored)

    def test_rehashed_missing_checkpoint(self):
        with closing(sqlite3.connect(self.backup / DATABASE)) as db:
            db.execute("DELETE FROM checkpoints")
            db.commit()
        write_manifest(self.backup)
        with self.assertRaisesRegex(ValueError, "checkpoint linkage"):
            verify_restore(self.backup, self.restored)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pf-checkout", required=True, type=Path)
    checkout = parser.parse_args().pf_checkout.resolve()
    commit = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if commit != PF_COMMIT or subprocess.check_output(
        ["git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=all"], text=True
    ).strip():
        parser.error(f"Use an isolated clean PF-001 checkout at {PF_COMMIT}")
    sys.path.insert(0, str(checkout))
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RestoreTests))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
