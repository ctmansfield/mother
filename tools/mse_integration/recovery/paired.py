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
CORRECTED = dict(
    atlas=ATLAS,
    forge="e4219cdf3dba73f586e3820990f3ab34f1a7c1d9",
    oracle="ac3fbf61389ca2a6e82683aa520c15181ac1aa80",
    provenance="5799879c1d7dcc0fa684754833f331957ae5deb3",
)
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


def seal(backup, receipt, pins):
    manifest = {
        "receipt": receipt,
        "source_pins": pins,
        "members": {name: file_digest(backup / name) for name in MEMBERS},
    }
    (backup / "manifest.json").write_text(json.dumps(manifest))


def restore(backup, destination, expected_original, pins):
    manifest = json.loads((backup / "manifest.json").read_text())
    if manifest["source_pins"] != pins:
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


def load_siblings(checkout, directory, pins):
    for commit, *paths in (
        (pins["oracle"], "integrations/healthbridge"),
        (pins["provenance"], "integrations/mse_snapshot", REFERENCE),
    ):
        data = git(checkout, "archive", commit, *paths)
        with tarfile.open(fileobj=BytesIO(data)) as source:
            source.extractall(directory, filter="data")
    sys.path[:0] = [str(directory), str(directory / REFERENCE), str(checkout)]


def run_rehearsal(checkout, directory, *, combined=False, corrected=False):
    pins = CORRECTED if corrected else SOURCE_PINS
    expected = COMBINED if combined else pins["forge"]
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
        load_siblings(checkout, directory, pins)
    from integrations.healthbridge.ingest import ingest_capture
    from integrations.mse_ingest import RecoveryError, Scope
    from integrations.mse_ingest.connected import ConnectedIngest, NORMALIZER_VERSION
    from integrations.mse_snapshot.ledger import replay_ledger_snapshot
    from mother.physiology.archive import Archive
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
            seal(self.backup, receipt, pins)
            shutil.rmtree(self.primary)
            restored = self.root / "restored"
            saved = restore(self.backup, restored, self.original, pins)
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
            seal(self.backup, final, pins)
            with self.assertRaisesRegex(ValueError, "original differs"):
                restore(self.backup, self.root / "other", self.original, pins)

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

    class CorrectedRestore(PairedRestore):
        def test_source_binding_and_exact_numeric_loss_survive(self):
            self.assertIn(b"4.20e1", self.original)
            self.original = self.original.replace(b"4.20e1", b"9007199254740993", 1)
            source = self.service(self.primary)
            delivery = ingest_capture(
                source,
                self.original,
                batch_id=self.batch,
                capture_id=self.batch,
                capture_kind="full_file",
            )
            receipt = delivery.receipt
            sequence = receipt["commit_sequence"]
            expected = self.snapshot(source, sequence)
            expected_replay = self.replay(source, expected)
            target, saved = self.take_backup(source, receipt)
            self.assertEqual(target.verify_receipt(saved), receipt)
            restored = self.snapshot(target, sequence)
            self.assertEqual(restored, expected)
            self.assertEqual(self.replay(target, restored), expected_replay)
            self.assertEqual(
                receipt["artifact_sha256"], hashlib.sha256(self.original).hexdigest()
            )

            (member,) = restored["observations"]
            self.assertEqual(
                member["source_revision"]["observation"]["value"], "9007199254740993"
            )
            losses = [
                item
                for item in restored["losses"]
                if item["reason"] == "pf001_binary64_rounding"
            ]
            self.assertEqual(
                {item["field"] for item in losses}, {"original_value", "value"}
            )
            self.assertEqual(expected_replay["input_losses"], restored["losses"])
            with Archive(target.archive) as archive:
                (record,) = archive.records(current=False)
                self.assertEqual(record["value"], 9007199254740992.0)
                numeric = record["metadata"]["numeric_projection_losses"]
                self.assertEqual(
                    {item["exact_decimal"] for item in numeric}, {"9007199254740993"}
                )
                self.assertEqual(
                    {item["projected_binary64_hex"] for item in numeric},
                    {float(9007199254740992).hex()},
                )
                artifact = archive.connection.execute(
                    "SELECT content FROM raw_artifacts"
                ).fetchone()
                self.assertEqual(tuple(artifact), (self.original,))

            incomplete = dict(delivery.export)
            incomplete["revisions"] = [
                item
                for item in incomplete["revisions"]
                if item["operation"] != "delete"
            ]
            self.assertNotEqual(incomplete["revisions"], delivery.export["revisions"])
            with self.assertRaisesRegex(ValueError, "Export"):
                target.ingest_export(self.original, incomplete)
            self.assertEqual(target.verify_receipt(receipt), receipt)
            self.assertEqual(self.snapshot(target, sequence), expected)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        CorrectedRestore if corrected else PairedRestore
    )
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--forge-checkout", type=Path)
    mode.add_argument("--combined-checkout", type=Path)
    mode.add_argument("--corrected-forge-checkout", type=Path)
    args = parser.parse_args()
    if args.plan:
        print(json.dumps(LAYOUT, indent=2))
    else:
        with TemporaryDirectory(prefix="mse-pinned-source-") as source:
            checkout = (
                args.combined_checkout
                or args.corrected_forge_checkout
                or args.forge_checkout
            )
            sys.exit(
                run_rehearsal(
                    checkout.resolve(),
                    Path(source),
                    combined=args.combined_checkout is not None,
                    corrected=args.corrected_forge_checkout is not None,
                )
            )
