"""Plan and rehearse a local FORGE/PF-001 restore using disposable fixtures."""

from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
from io import BytesIO
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
import unittest
import uuid

FORGE = "ceeb92157f4d7179a3ad5cd3d4af9e9aa4ff6b4f"
ATLAS = "769a0966da251da4d08633cc7663af9869da70e6"
ORACLE = "7825b02093d280321af34af88aed96da44b33594"
PROVENANCE = "7be9ea31c6c68643573afdf37ccfa0a41901a368"
REFERENCE = "research/mse/reference-v0.1.0/prototype"
COMBINED = "877eeb66ae2c26ab8ee2144d34adeba87c988e8f"
SOURCE_PINS = dict(atlas=ATLAS, forge=FORGE, oracle=ORACLE, provenance=PROVENANCE)
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
        "source_pins": SOURCE_PINS,
        "members": {name: file_digest(backup / name) for name in MEMBERS},
    }
    (backup / "manifest.json").write_text(json.dumps(manifest))


def restore(backup, destination, expected_original):
    manifest = json.loads((backup / "manifest.json").read_text())
    if manifest["source_pins"] != SOURCE_PINS:
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


def load_siblings(checkout, directory):
    for commit, *paths in (
        (ORACLE, "integrations/healthbridge"),
        (PROVENANCE, "integrations/mse_snapshot", REFERENCE),
    ):
        data = git(checkout, "archive", commit, *paths)
        with tarfile.open(fileobj=BytesIO(data)) as source:
            source.extractall(directory, filter="data")
    sys.path[:0] = [str(directory), str(directory / REFERENCE), str(checkout)]


def run_rehearsal(checkout, directory, *, combined=False):
    expected = COMBINED if combined else FORGE
    if (
        git(checkout, "rev-parse", "HEAD").decode().strip() != expected
        or git(checkout, "status", "--porcelain", "--untracked-files=all").strip()
    ):
        raise SystemExit(f"Use a clean dependency checkout at {expected}")
    schema = json.loads(
        git(checkout, "show", f"{ATLAS}:{CONTRACTS}/offline-integration.schema.json")
    )
    vectors = json.loads(
        git(checkout, "show", f"{ATLAS}:{CONTRACTS}/golden-vectors.json")
    )
    if combined:
        sys.path[:0] = [str(checkout), str(checkout / REFERENCE)]
    else:
        load_siblings(checkout, directory)
    from integrations.healthbridge.ingest import ingest_capture
    from integrations.mse_ingest import RecoveryError, Scope
    from integrations.mse_ingest.connected import ConnectedIngest, NORMALIZER_VERSION
    from integrations.mse_snapshot.ledger import replay_ledger_snapshot
    from mse.contracts import canonical

    class PairedRestore(unittest.TestCase):
        def setUp(self):
            temporary = TemporaryDirectory(prefix="mse-paired-restore-")
            self.addCleanup(temporary.cleanup)
            self.root = Path(temporary.name).resolve()
            self.primary = self.root / "primary"
            self.backup = self.root / "backup"
            self.backup.mkdir(mode=0o700)
            self.original = vectors["source_utf8"].encode()
            self.scope = vectors["snapshot"]["scope"]
            self.archive_id = vectors["snapshot"]["archive_id"]
            self.batch = "recovery-" + uuid.uuid4().hex

        def service(self, directory):
            return ConnectedIngest(
                directory,
                archive_id=self.archive_id,
                scope=Scope(**self.scope),
                schema=schema,
            )

        def ingest(self, service):
            return ingest_capture(
                service,
                self.original,
                batch_id=self.batch,
                capture_id=self.batch,
                capture_kind="full_file",
            ).receipt

        def snapshot(self, service, sequence):
            return service.build_snapshot(
                measurement_start=vectors["snapshot"]["measurement_start"],
                measurement_end=vectors["snapshot"]["measurement_end"],
                knowledge_cutoff_sequence=sequence,
                normalizer_version=NORMALIZER_VERSION,
            )

        def replay(self, service, snapshot):
            return replay_ledger_snapshot(
                canonical(snapshot).encode(),
                ledger=service,
                expected_scope=self.scope,
                expected_archive_id=self.archive_id,
                max_bytes=64_000,
                max_members=128,
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
            before = self.snapshot(source, first["commit_sequence"])
            expected = self.replay(source, before)
            self.assertEqual(expected["epistemic_class"], "derived")
            self.assertEqual(
                expected["reference_result"]["active_observation_count"], 1
            )
            self.assertEqual(len(expected["lineage"]["deletion_facts"]), 1)
            target, saved = self.take_backup(source, first)
            self.assertEqual(target.verify_receipt(saved), first)
            restored = self.snapshot(target, first["commit_sequence"])
            self.assertEqual(restored, before)
            self.assertEqual(self.replay(target, restored), expected)
            self.assertEqual(self.ingest(target), first)

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
            pending = source.read_receipt(self.batch)
            self.assertEqual(pending["status"], "durably_received")
            sequence = pending["commit_sequence"]
            precommit = self.snapshot(source, sequence)
            self.assertEqual(precommit["observations"], [])
            target, saved = self.take_backup(source, pending)
            self.assertEqual(target.verify_receipt(saved), pending)
            self.assertEqual(self.snapshot(target, sequence), precommit)

            def checkpoint(phase):
                if phase == "archive":
                    self.fail("The archived run must be recovered without re-commit")

            target._checkpoint = checkpoint
            accepted = self.ingest(target)
            self.assertEqual(accepted["status"], "normalized")
            self.assertEqual(target.verify_receipt(accepted), accepted)
            restored = self.snapshot(target, accepted["commit_sequence"])
            self.assertEqual(
                self.replay(target, restored)["reference_result"][
                    "active_observation_count"
                ],
                1,
            )
            self.assertEqual(self.snapshot(target, sequence), precommit)

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
    mode.add_argument("--combined-checkout", type=Path)
    args = parser.parse_args()
    if args.plan:
        print(json.dumps(LAYOUT, indent=2))
    else:
        with TemporaryDirectory(prefix="mse-pinned-source-") as source:
            checkout = args.combined_checkout or args.forge_checkout
            sys.exit(
                run_rehearsal(
                    checkout.resolve(),
                    Path(source),
                    combined=args.combined_checkout is not None,
                )
            )
