"""Plan and rehearse a local FORGE/PF-001 restore using disposable fixtures."""

from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
import uuid

FORGE = "c29f4426c0e598d07ea9b1b5d019c48cd90253c9"
ATLAS = "928a60b704c342c091eabd25ba41c8eb84d562de"
CONTRACTS = "docs/mse/integration/contracts"
MEMBERS = ("custody.sqlite3", "physiology.sqlite3", "original.json")
LAYOUT = {
    "root": "<APPROVED_LOCAL_EXT4_ROOT>/mse-synthetic",
    "state": "state/{custody.sqlite3,physiology.sqlite3}",
    "staging": "staging/",
    "backup": "<APPROVED_SEPARATE_BACKUP_ROOT>/mse-synthetic/<generation>",
    "restore": "<APPROVED_ISOLATED_RESTORE_ROOT>/<generation>",
    "owner": "<APPROVED_DEDICATED_WRITER_UID>",
    "directory_mode": "0700",
    "file_mode": "0600",
}


def git(checkout, *arguments):
    return subprocess.check_output(["git", "-C", str(checkout), *arguments])


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_sqlite(source, target):
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as reader:
        with closing(sqlite3.connect(target)) as writer:
            reader.backup(writer)
            if writer.execute("PRAGMA journal_mode=DELETE").fetchone() != ("delete",):
                raise ValueError("Backup is not standalone")


def seal(backup, receipt):
    manifest = {
        "receipt": receipt,
        "forge": FORGE,
        "atlas": ATLAS,
        "members": {name: file_digest(backup / name) for name in MEMBERS},
    }
    (backup / "manifest.json").write_text(json.dumps(manifest))


def restore(backup, destination, expected_original):
    manifest = json.loads((backup / "manifest.json").read_text())
    if (manifest["forge"], manifest["atlas"]) != (FORGE, ATLAS):
        raise ValueError("Unexpected backup source pins")
    if set(manifest["members"]) != set(MEMBERS):
        raise ValueError("Unexpected backup inventory")
    for name, digest in manifest["members"].items():
        path = backup / name
        if not path.is_file() or path.is_symlink() or file_digest(path) != digest:
            raise ValueError("Missing or changed backup member")
    if (backup / "original.json").read_bytes() != expected_original:
        raise ValueError("Backup original differs from trusted fixture")
    destination.mkdir(mode=0o700)
    for name in MEMBERS[:2]:
        target = destination / name
        shutil.copyfile(backup / name, target)
        target.chmod(0o600)
        with closing(sqlite3.connect(target.as_uri() + "?mode=ro", uri=True)) as db:
            if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError("Invalid SQLite backup")
            if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise ValueError("Invalid SQLite foreign keys")
    return manifest["receipt"]


def run_rehearsal(checkout):
    if (
        git(checkout, "rev-parse", "HEAD").decode().strip() != FORGE
        or git(checkout, "status", "--porcelain", "--untracked-files=all").strip()
    ):
        raise SystemExit(f"Use a clean FORGE checkout at {FORGE}")
    schema = json.loads(
        git(checkout, "show", f"{ATLAS}:{CONTRACTS}/offline-integration.schema.json")
    )
    vectors = json.loads(
        git(checkout, "show", f"{ATLAS}:{CONTRACTS}/golden-vectors.json")
    )
    sys.path.insert(0, str(checkout))
    from integrations.mse_ingest import RecoveryError, Scope
    from integrations.mse_ingest.v02 import IngestV02

    path = checkout / "tests/integration/mse_ingest/test_atlas_v02.py"
    spec = importlib.util.spec_from_file_location("forge_fixture", path)
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)

    class PairedRestore(unittest.TestCase):
        def setUp(self):
            temporary = TemporaryDirectory(prefix="mse-paired-restore-")
            self.addCleanup(temporary.cleanup)
            self.root = Path(temporary.name)
            self.primary = self.root / "primary"
            self.backup = self.root / "backup"
            self.backup.mkdir(mode=0o700)
            self.export = dict(
                vectors["export"], batch_id="recovery-" + uuid.uuid4().hex
            )
            self.original = vectors["source_utf8"].encode()

        def service(self, directory):
            return IngestV02(
                directory,
                archive_id=vectors["receipt"]["archive_id"],
                scope=Scope(**self.export["scope"]),
                schema=schema,
            )

        def ingest(self, service, normalize=None):
            if normalize is None:
                normalize = lambda raw, context: fixture.Atlas02Tests.map(
                    self.export, context
                )
            return service.ingest(
                self.original,
                self.export,
                adapter_version="recovery-fixture/1",
                normalize=normalize,
            )

        def take_backup(self, source, receipt):
            # The fixture has no other writers. Both databases are quiesced at this cut.
            copy_sqlite(source.journal, self.backup / MEMBERS[0])
            copy_sqlite(source.archive, self.backup / MEMBERS[1])
            (self.backup / MEMBERS[2]).write_bytes(self.original)
            seal(self.backup, receipt)
            shutil.rmtree(self.primary)
            restored = self.root / "restored"
            saved = restore(self.backup, restored, self.original)
            return self.service(restored), saved

        def test_finalized_restore_and_exact_retry(self):
            source = self.service(self.primary)
            first = self.ingest(source)
            target, saved = self.take_backup(source, first)
            self.assertEqual(target.verify_receipt(saved), first)

            def unexpected(*args):
                self.fail("Restored finalized retry must not normalize again")

            self.assertEqual(self.ingest(target, unexpected), first)

        def test_archive_committed_before_receipt_restore(self):
            class Interrupted(Exception):
                pass

            def interrupt(phase):
                if phase == "archive":
                    raise Interrupted()

            source = self.service(self.primary)
            source._checkpoint = interrupt
            with self.assertRaises(Interrupted):
                self.ingest(source)
            pending = source.read_receipt(self.export["batch_id"])
            self.assertEqual(pending["status"], "durably_received")
            target, saved = self.take_backup(source, pending)
            self.assertEqual(target.verify_receipt(saved), pending)

            def unexpected(*args):
                self.fail("The archived run must be recovered without normalization")

            accepted = self.ingest(target, unexpected)
            self.assertEqual(accepted["status"], "normalized")
            self.assertEqual(target.verify_receipt(accepted), accepted)

        def test_rehashed_unrelated_original_is_rejected(self):
            source = self.service(self.primary)
            final = self.ingest(source)
            self.take_backup(source, final)
            (self.backup / "original.json").write_bytes(b"unrelated synthetic bytes")
            seal(self.backup, final)
            with self.assertRaisesRegex(ValueError, "original differs"):
                restore(self.backup, self.root / "other", self.original)

        def test_final_receipt_with_stale_archive(self):
            source = self.service(self.primary)
            final = self.ingest(source)
            target, saved = self.take_backup(source, final)
            with closing(sqlite3.connect(target.archive)) as db:
                # Simulate an older intact archive with no accepted run.
                for table in (
                    "normalized_records",
                    "source_heads",
                    "run_revisions",
                    "source_revisions",
                    "raw_artifacts",
                    "import_runs",
                ):
                    db.execute("DELETE FROM " + table)
                db.commit()
                self.assertEqual(
                    db.execute("PRAGMA integrity_check").fetchone(), ("ok",)
                )
            with self.assertRaises(RecoveryError):
                target.verify_receipt(saved)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PairedRestore)
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--forge-checkout", type=Path)
    args = parser.parse_args()
    if args.plan:
        print(json.dumps(LAYOUT, indent=2))
    else:
        sys.exit(run_rehearsal(args.forge_checkout.resolve()))
