"""Synthetic failure/retry acceptance for Mother's durable local handoff receipts.

The wire input comes from the actual pinned Coach JavaScript capture builder,
not from a Python rewrite of the sender.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from mother.physiology.archive import Archive
from mother.physiology.handoff import unpack_event
from mother.physiology.manual_ingest import ManualIngestError
from mother.physiology.receipt_recovery import (
    ReceiptError,
    ingest_with_receipt,
    verify_receipt,
)

HELPER = Path(__file__).with_name("generate_ui_fixture.cjs")
SUBJECT = "synthetic-subject"
NOW = "2026-11-07T04:15:00Z"


def packet(kind="marker"):
    if not os.environ.get("COACH_CHECKOUT"):
        raise RuntimeError("The pinned Coach source checkout is mandatory")
    proc = subprocess.run(
        ["node", str(HELPER), kind],
        env=os.environ.copy(),
        capture_output=True,
        check=True,
        text=True,
        timeout=15,
    )
    return base64.b64decode(proc.stdout.strip(), validate=True)


def changed_original_bytes(envelope):
    data = json.loads(envelope)
    original = base64.b64decode(data["event_base64"], validate=True)
    # Same JSON semantics and event ID, but not the original submitted bytes.
    alternate = b"\n  " + original + b"\n"
    data["event_base64"] = base64.b64encode(alternate).decode("ascii")
    data["event_sha256"] = hashlib.sha256(alternate).hexdigest()
    return (json.dumps(data, sort_keys=True) + "\n").encode("utf-8")


class ReceiptRecoveryTests(unittest.TestCase):
    def test_receipt_is_stable_and_approved_only_after_archive_commit(self):
        envelope = packet()
        with TemporaryDirectory() as root:
            db = Path(root) / "archive.sqlite3"
            directory = Path(root) / "receipts"
            with Archive(db) as archive:
                result = ingest_with_receipt(
                    archive,
                    envelope,
                    receipt_directory=directory,
                    received_at=NOW,
                )
                self.assertEqual(result["status"], "receipt_written_and_reconciled")
                self.assertEqual(result["new_records"], 1)
                self.assertFalse(result["authenticated_sender"])
                receipt = Path(result["receipt_path"])
                self.assertEqual(receipt.parent, directory)
                self.assertEqual(len(list(directory.glob("*.mother-receipt.json"))), 1)
                self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
                self.assertEqual(directory.stat().st_mode & 0o077, 0)
                verified = verify_receipt(archive, envelope, receipt.read_bytes())
                self.assertEqual(
                    verified["status"], "archived_in_selected_local_archive"
                )
                self.assertEqual(
                    verified["original_event_sha256"],
                    hashlib.sha256(unpack_event(envelope)).hexdigest(),
                )
                self.assertNotIn("subject_id", verified)
                self.assertNotIn("payload", verified)

    def test_receipt_lost_after_commit_recovers_by_retry_without_duplicate(self):
        envelope = packet()
        with TemporaryDirectory() as root:
            db = Path(root) / "archive.sqlite3"
            directory = Path(root) / "receipts"
            with Archive(db) as archive:
                with patch(
                    "mother.physiology.receipt_recovery._store_receipt",
                    side_effect=OSError("simulated disk receipt write outage"),
                ):
                    with self.assertRaises(OSError):
                        ingest_with_receipt(
                            archive,
                            envelope,
                            receipt_directory=directory,
                            received_at=NOW,
                        )
                self.assertEqual(len(archive.revisions()), 1)
                self.assertEqual(len(archive.current_records(kind="event")), 1)
                self.assertFalse(directory.exists())
            with Archive(db) as archive:
                repaired = ingest_with_receipt(
                    archive,
                    envelope,
                    receipt_directory=directory,
                    received_at="2026-11-08T04:15:00Z",
                )
                self.assertEqual(repaired["new_records"], 0)
                self.assertTrue(Path(repaired["receipt_path"]).is_file())
                self.assertEqual(len(archive.revisions()), 1)
                self.assertEqual(len(archive.current_records("event")), 1)

    def test_duplicate_replay_has_exact_same_receipt_and_inode(self):
        envelope = packet()
        with TemporaryDirectory() as root:
            with Archive(Path(root) / "archive.sqlite3") as archive:
                first = ingest_with_receipt(
                    archive,
                    envelope,
                    receipt_directory=Path(root) / "receipts",
                    received_at=NOW,
                )
                path = Path(first["receipt_path"])
                original = path.read_bytes()
                inode = path.stat().st_ino
                second = ingest_with_receipt(
                    archive,
                    envelope,
                    receipt_directory=Path(root) / "receipts",
                    received_at="2026-11-08T04:15:00Z",
                )
                self.assertEqual(second["new_records"], 0)
                self.assertEqual(second["receipt_path"], first["receipt_path"])
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(path.stat().st_ino, inode)

    def test_forged_receipt_cannot_verify_against_selected_archive(self):
        envelope = packet()
        with TemporaryDirectory() as root:
            with Archive(Path(root) / "archive.sqlite3") as archive:
                result = ingest_with_receipt(
                    archive, envelope, receipt_directory=Path(root) / "receipts"
                )
                body = json.loads(Path(result["receipt_path"]).read_bytes())
                for invalid in (
                    dict(body, event_id="forged"),
                    dict(body, authenticated_sender=True),
                    dict(body, original_event_sha256="f" * 64),
                ):
                    with self.subTest(invalid=invalid):
                        with self.assertRaises(ReceiptError):
                            verify_receipt(
                                archive,
                                envelope,
                                json.dumps(invalid).encode("utf-8"),
                            )

    def test_failed_parent_check_writes_no_receipt(self):
        envelope = packet("outcome")
        with TemporaryDirectory() as root:
            folder = Path(root) / "receipts"
            with Archive(Path(root) / "archive.sqlite3") as archive:
                with self.assertRaises(ManualIngestError):
                    ingest_with_receipt(archive, envelope, receipt_directory=folder)
                self.assertEqual(len(archive.current_records("event")), 0)
                self.assertFalse(folder.exists())

    def test_reformatted_semantic_duplicate_cannot_claim_same_original_bytes(self):
        original = packet()
        alternate = changed_original_bytes(original)
        with TemporaryDirectory() as root:
            folder = Path(root) / "receipts"
            with Archive(Path(root) / "archive.sqlite3") as archive:
                ingest_with_receipt(
                    archive,
                    original,
                    receipt_directory=folder,
                    received_at=NOW,
                )
                with self.assertRaises(ReceiptError):
                    ingest_with_receipt(
                        archive,
                        alternate,
                        receipt_directory=folder,
                        received_at="2026-11-08T04:15:00Z",
                    )
                self.assertEqual(len(archive.revisions()), 1)
                self.assertEqual(len(list(folder.glob("*.mother-receipt.json"))), 1)

    def test_symlink_and_insecure_existing_receipt_are_rejected(self):
        envelope = packet()
        with TemporaryDirectory() as root:
            folder = Path(root) / "receipts"
            with Archive(Path(root) / "archive.sqlite3") as archive:
                first = ingest_with_receipt(archive, envelope, receipt_directory=folder)
                path = Path(first["receipt_path"])
                original = path.read_bytes()
                path.unlink()
                target = Path(root) / "unrelated.txt"
                target.write_text("unchanged")
                path.symlink_to(target)
                with self.assertRaises(ReceiptError):
                    ingest_with_receipt(archive, envelope, receipt_directory=folder)
                self.assertEqual(target.read_text(), "unchanged")
                path.unlink()
                path.write_bytes(original)
                path.chmod(0o644)
                with self.assertRaises(ReceiptError):
                    ingest_with_receipt(archive, envelope, receipt_directory=folder)
                self.assertEqual(path.read_bytes(), original)

    def test_receipt_with_changed_envelope_is_not_accepted(self):
        envelope = packet()
        with TemporaryDirectory() as root:
            with Archive(Path(root) / "archive.sqlite3") as archive:
                result = ingest_with_receipt(
                    archive, envelope, receipt_directory=Path(root) / "receipts"
                )
                received = Path(result["receipt_path"]).read_bytes()
                with self.assertRaises(ReceiptError):
                    verify_receipt(archive, changed_original_bytes(envelope), received)

    def test_cli_retry_does_not_require_a_new_input_or_archive(self):
        envelope = packet()
        with TemporaryDirectory() as root:
            input_path = Path(root) / "input.coach-event.json"
            input_path.write_bytes(envelope)
            archive_path = Path(root) / "archive.sqlite3"
            folder = Path(root) / "receipts"
            command = [
                sys.executable,
                "-m",
                "mother.physiology.receipt_recovery",
                "--input",
                str(input_path),
                "--archive",
                str(archive_path),
                "--receipt-directory",
                str(folder),
            ]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            status = json.loads(first.stdout)
            self.assertEqual(status["new_records"], 1)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(json.loads(second.stdout)["new_records"], 0)
            self.assertEqual(len(list(folder.glob("*.mother-receipt.json"))), 1)
            self.assertEqual(input_path.read_bytes(), envelope)

    def test_malformed_packet_does_not_create_archive_or_receipt(self):
        with TemporaryDirectory() as root:
            file = Path(root) / "bad.coach-event.json"
            file.write_bytes(b'{"envelope_version":"invalid"}')
            archive = Path(root) / "archive.sqlite3"
            folder = Path(root) / "receipts"
            command = [
                sys.executable,
                "-m",
                "mother.physiology.receipt_recovery",
                "--input",
                str(file),
                "--archive",
                str(archive),
                "--receipt-directory",
                str(folder),
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(archive.exists())
            self.assertFalse(folder.exists())
            self.assertNotIn(SUBJECT, result.stderr)


if __name__ == "__main__":
    unittest.main()
