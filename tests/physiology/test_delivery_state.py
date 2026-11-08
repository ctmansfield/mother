"""Synthetic read-only delivery-state acceptance using pinned real Coach UI.

No personal files, services, notifications or live transport. The tests
assert that a detached receipt does not establish archive acceptance.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from mother.physiology.archive import Archive
from mother.physiology.delivery_state import (
    reconcile_delivery,
    open_readonly,
)
from mother.physiology.receipt_recovery import (
    ingest_with_receipt,
)

HELPER = Path(__file__).with_name("generate_ui_fixture.cjs")
WHEN = "2026-11-07T04:15:00Z"


def packet(kind="marker"):
    if not os.getenv("COACH_CHECKOUT"):
        raise RuntimeError("COACH_CHECKOUT requires the pinned Coach UI checkout")
    result = subprocess.run(
        ["node", str(HELPER), kind],
        capture_output=True,
        check=True,
        text=True,
        timeout=15,
        env=os.environ.copy(),
    )
    return base64.b64decode(result.stdout.strip(), validate=True)


def changed_envelope(envelope):
    data = json.loads(envelope)
    original = json.loads(base64.b64decode(data["event_base64"], validate=True))
    original["payload"]["text"] = "Different wording for the same event identity"
    modified = json.dumps(original, sort_keys=True).encode()
    data["event_base64"] = base64.b64encode(modified).decode("ascii")
    data["event_sha256"] = hashlib.sha256(modified).hexdigest()
    return (json.dumps(data, sort_keys=True) + "\n").encode()


@unittest.skipUnless(
    os.environ.get("COACH_CHECKOUT"),
    "Pinned Coach UI checkout required",
)
class DeliveryStateTests(unittest.TestCase):
    def test_prepared_draft_is_not_confirmed(self):
        state = reconcile_delivery(packet())
        self.assertEqual(state["state"], "prepared_pending")
        self.assertFalse(state["archive_checked"])
        self.assertFalse(state["safe_to_delete_original"])
        self.assertEqual(state["evidence_level"], "sender_assertion_only")
        self.assertFalse(state["authenticated_sender"])
        self.assertNotIn("subject_id", state)
        self.assertNotIn("payload", state)

    def test_attempted_without_receipt_stays_unknown(self):
        state = reconcile_delivery(packet(), attempted=True)
        self.assertEqual(state["state"], "delivery_unknown")
        self.assertFalse(state["receipt_checked"])
        self.assertFalse(state["safe_to_delete_original"])

    def test_copied_receipt_never_confirms_without_archive(self):
        envelope = packet()
        with TemporaryDirectory() as root:
            with Archive(Path(root) / "archive.sqlite3") as archive:
                receipt = ingest_with_receipt(
                    archive,
                    envelope,
                    receipt_directory=Path(root) / "receipts",
                    received_at=WHEN,
                )
                detached = Path(receipt["receipt_path"]).read_bytes()
        unverified = reconcile_delivery(envelope, receipt_bytes=detached)
        self.assertEqual(unverified["state"], "delivery_unknown")
        self.assertTrue(unverified["receipt_present"])
        self.assertFalse(unverified["archive_checked"])
        self.assertFalse(unverified["receipt_checked"])

    def test_empty_archive_does_not_establish_delivery_failure(self):
        envelope = packet()
        with TemporaryDirectory() as root:
            path = Path(root) / "archive.sqlite3"
            with Archive(path):
                pass
            result = reconcile_delivery(envelope, attempted=True, archive_path=path)
            self.assertEqual(result["state"], "delivery_unknown")
            self.assertTrue(result["archive_checked"])
            self.assertFalse(result["safe_to_delete_original"])

    def test_committed_without_receipt_is_verified_only_by_archive(self):
        envelope = packet()
        with TemporaryDirectory() as root:
            path = Path(root) / "archive.sqlite3"
            with Archive(path) as archive:
                from mother.physiology.handoff import accept_envelope

                accept_envelope(archive, envelope, received_at=WHEN)
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            report = reconcile_delivery(
                envelope,
                attempted=True,
                archive_path=path,
            )
            after = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(before, after)
            self.assertEqual(report["state"], "archive_verified_receipt_missing")
            self.assertTrue(report["archive_checked"])
            self.assertFalse(report["receipt_present"])
            self.assertFalse(report["safe_to_delete_original"])

    def test_valid_receipt_requires_exact_archive_evidence(self):
        envelope = packet()
        with TemporaryDirectory() as root:
            path = Path(root) / "archive.sqlite3"
            with Archive(path) as archive:
                receipt = ingest_with_receipt(
                    archive,
                    envelope,
                    receipt_directory=Path(root) / "receipts",
                    received_at=WHEN,
                )
            body = Path(receipt["receipt_path"]).read_bytes()
            report = reconcile_delivery(
                envelope, attempted=True, archive_path=path, receipt_bytes=body
            )
            self.assertEqual(report["state"], "archive_verified_receipt_valid")
            self.assertTrue(report["receipt_checked"])
            self.assertEqual(report["evidence_level"], "local_archive_snapshot")
            self.assertFalse(report["authenticated_sender"])
            self.assertFalse(report["safe_to_delete_original"])

    def test_lost_receipt_after_commit_can_be_reconciled_without_write(self):
        envelope = packet()
        with TemporaryDirectory() as root:
            path = Path(root) / "archive.sqlite3"
            directory = Path(root) / "receipts"
            with Archive(path) as archive:
                with patch(
                    "mother.physiology.receipt_recovery._store_receipt",
                    side_effect=OSError("synthetic receipt failure"),
                ):
                    with self.assertRaises(OSError):
                        ingest_with_receipt(
                            archive,
                            envelope,
                            receipt_directory=directory,
                            received_at=WHEN,
                        )
            report = reconcile_delivery(envelope, archive_path=path, attempted=True)
            self.assertEqual(report["state"], "archive_verified_receipt_missing")
            self.assertFalse(directory.exists())
            with Archive(path) as archive:
                recovered = ingest_with_receipt(
                    archive,
                    envelope,
                    receipt_directory=directory,
                    received_at="2026-11-08T04:15:00Z",
                )
                self.assertEqual(recovered["new_records"], 0)
            verified = reconcile_delivery(
                envelope,
                archive_path=path,
                receipt_bytes=Path(recovered["receipt_path"]).read_bytes(),
            )
            self.assertEqual(verified["state"], "archive_verified_receipt_valid")

    def test_invalid_receipt_never_becomes_verified(self):
        envelope = packet()
        with TemporaryDirectory() as root:
            path = Path(root) / "archive.sqlite3"
            with Archive(path) as archive:
                receipt = ingest_with_receipt(
                    archive,
                    envelope,
                    receipt_directory=Path(root) / "receipts",
                )
            malformed = json.loads(Path(receipt["receipt_path"]).read_bytes())
            malformed["envelope_sha256"] = "f" * 64
            result = reconcile_delivery(
                envelope,
                archive_path=path,
                receipt_bytes=json.dumps(malformed).encode(),
            )
            self.assertEqual(result["state"], "archive_verified_receipt_invalid")
            self.assertTrue(result["archive_checked"])
            self.assertTrue(result["receipt_checked"])
            self.assertFalse(result["safe_to_delete_original"])

    def test_same_identity_modified_contents_is_conflict(self):
        envelope = packet()
        with TemporaryDirectory() as root:
            path = Path(root) / "archive.sqlite3"
            with Archive(path) as archive:
                ingest_with_receipt(
                    archive, envelope, receipt_directory=Path(root) / "receipts"
                )
            changed = reconcile_delivery(
                changed_envelope(envelope), archive_path=path, attempted=True
            )
            self.assertEqual(changed["state"], "archive_conflict")
            self.assertFalse(changed["safe_to_delete_original"])

    def test_readonly_sqlite_rejects_write(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "archive.sqlite3"
            with Archive(path):
                pass
            with open_readonly(path, "event:synthetic") as view:
                with self.assertRaises(sqlite3.DatabaseError):
                    view.connection.execute(
                        "INSERT INTO schema_versions VALUES (2,'2.0','now')"
                    )

    def test_cli_missing_archive_is_error_and_never_creates_one(self):
        envelope = packet()
        with TemporaryDirectory() as root:
            input_file = Path(root) / "envelope.json"
            input_file.write_bytes(envelope)
            nonexistent = Path(root) / "never-create.sqlite3"
            cmd = [
                sys.executable,
                "-m",
                "mother.physiology.delivery_state",
                "--input",
                str(input_file),
                "--archive",
                str(nonexistent),
                "--attempted",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(nonexistent.exists())
            self.assertIn("not_reconciled", result.stderr)
            self.assertNotIn("synthetic-subject", result.stderr)

    def test_cli_report_is_private_exclusive_and_source_preserving(self):
        envelope = packet()
        with TemporaryDirectory() as root:
            folder = Path(root)
            input_file = folder / "envelope.json"
            output = folder / "state.json"
            input_file.write_bytes(envelope)
            cmd = [
                sys.executable,
                "-m",
                "mother.physiology.delivery_state",
                "--input",
                str(input_file),
                "--output",
                str(output),
            ]
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            self.assertEqual(
                json.loads(output.read_bytes())["state"], "prepared_pending"
            )
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            self.assertEqual(input_file.read_bytes(), envelope)
            self.assertEqual(
                json.loads(output.read_bytes())["state"], "prepared_pending"
            )

    def test_cli_refuses_report_over_input(self):
        with TemporaryDirectory() as root:
            input_file = Path(root) / "envelope.json"
            envelope = packet()
            input_file.write_bytes(envelope)
            cmd = [
                sys.executable,
                "-m",
                "mother.physiology.delivery_state",
                "--input",
                str(input_file),
                "--output",
                str(input_file),
            ]
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)
            self.assertEqual(input_file.read_bytes(), envelope)

    def test_symlinked_archive_is_refused(self):
        envelope = packet()
        with TemporaryDirectory() as root:
            path = Path(root) / "archive.sqlite3"
            with Archive(path):
                pass
            link = Path(root) / "alias.sqlite3"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                reconcile_delivery(envelope, archive_path=link, attempted=True)


if __name__ == "__main__":
    unittest.main()
