"""Actual Mother snapshot report -> pinned Coach status interpreter acceptance."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from mother.physiology.archive import Archive
from mother.physiology.delivery_state import reconcile_delivery
from mother.physiology.receipt_recovery import ingest_with_receipt

HELPER = Path(__file__).with_name("generate_ui_fixture.cjs")
INTERPRET = Path(__file__).with_name("interpret_delivery_report.cjs")


def envelope():
    if not os.environ.get("COACH_CHECKOUT"):
        raise RuntimeError("COACH_CHECKOUT required")
    run = subprocess.run(
        ["node", str(HELPER), "marker"],
        capture_output=True,
        check=True,
        text=True,
        timeout=15,
        env=os.environ.copy(),
    )
    return base64.b64decode(run.stdout.strip(), validate=True)


def coach_interpret(packet, report=None, attempted=False):
    payload = {
        "envelope_base64": base64.b64encode(packet).decode(),
        "report": report,
        "attempted": attempted,
    }
    return subprocess.run(
        ["node", str(INTERPRET)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=15,
        env=os.environ.copy(),
    )


@unittest.skipUnless(
    os.environ.get("COACH_CHECKOUT"), "Real pinned Coach source required"
)
class ActualMotherReportToCoachTests(unittest.TestCase):
    def test_prepared_and_attempted_states_are_compatible(self):
        packet = envelope()
        for attempted, expected in [
            (False, "prepared_pending"),
            (True, "delivery_unknown"),
        ]:
            with self.subTest(attempted=attempted):
                report = reconcile_delivery(packet, attempted=attempted)
                proc = coach_interpret(packet, report=report, attempted=attempted)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                outcome = json.loads(proc.stdout)
                self.assertEqual(outcome["state"], expected)
                self.assertFalse(outcome["safe_to_delete_original"])

    def test_actual_snapshot_missing_receipt_shows_copied_report_warning(self):
        packet = envelope()
        with TemporaryDirectory() as directory:
            archive_file = Path(directory) / "archive.sqlite3"
            with Archive(archive_file) as archive:
                from mother.physiology.handoff import accept_envelope

                accept_envelope(
                    archive, packet, received_at="2026-11-07T04:15:00Z"
                )
            report = reconcile_delivery(
                packet, attempted=True, archive_path=archive_file
            )
            self.assertEqual(report["state"], "archive_verified_receipt_missing")
            proc = coach_interpret(packet, report=report, attempted=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            view = json.loads(proc.stdout)
            self.assertEqual(view["state"], report["state"])
            self.assertTrue(view["archive_claimed"])
            self.assertFalse(view["is_authenticated_confirmation"])

    def test_actual_archive_and_receipt_still_cannot_authenticate_copied_report(self):
        packet = envelope()
        with TemporaryDirectory() as directory:
            archive_file = Path(directory) / "archive.sqlite3"
            with Archive(archive_file) as archive:
                response = ingest_with_receipt(
                    archive,
                    packet,
                    receipt_directory=Path(directory) / "receipts",
                )
            report = reconcile_delivery(
                packet,
                archive_path=archive_file,
                receipt_bytes=Path(response["receipt_path"]).read_bytes(),
            )
            self.assertEqual(report["state"], "archive_verified_receipt_valid")
            proc = coach_interpret(packet, report=report)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            view = json.loads(proc.stdout)
            self.assertEqual(view["state"], report["state"])
            self.assertFalse(view["is_authenticated_confirmation"])
            self.assertFalse(view["safe_to_delete_original"])

    def test_forged_mother_report_cannot_be_mapped_as_confirmed(self):
        packet = envelope()
        with TemporaryDirectory() as directory:
            archive_file = Path(directory) / "archive.sqlite3"
            with Archive(archive_file) as archive:
                response = ingest_with_receipt(
                    archive,
                    packet,
                    receipt_directory=Path(directory) / "receipts",
                )
            report = reconcile_delivery(
                packet,
                archive_path=archive_file,
                receipt_bytes=Path(response["receipt_path"]).read_bytes(),
            )
            forged = dict(report, envelope_sha256="f" * 64)
            proc = coach_interpret(packet, report=forged)
            self.assertEqual(proc.returncode, 2)
            self.assertNotIn("synthetic-subject", proc.stderr)

    def test_receipt_without_archive_remains_unknown_to_coach(self):
        packet = envelope()
        with TemporaryDirectory() as directory:
            with Archive(Path(directory) / "archive.sqlite3") as archive:
                response = ingest_with_receipt(
                    archive,
                    packet,
                    receipt_directory=Path(directory) / "receipts",
                )
            detached_receipt = Path(response["receipt_path"]).read_bytes()
            reported = reconcile_delivery(
                packet,
                attempted=True,
                receipt_bytes=detached_receipt,
            )
            self.assertEqual(reported["state"], "delivery_unknown")
            proc = coach_interpret(packet, report=reported, attempted=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(
                json.loads(proc.stdout)["state"], "delivery_unknown"
            )


if __name__ == "__main__":
    unittest.main()
