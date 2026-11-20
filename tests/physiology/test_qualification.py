"""Synthetic, offline acceptance checks for read-only R02 replay qualification."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mother.physiology.qualification import assess_replay

QUALIFY = Path(__file__).parents[2] / "mother" / "physiology" / "qualification.py"


def fixture():
    def record(ident, revision, timestamp, value, status="valid", clock=None):
        return {
            "record_type": "observation",
            "id": ident,
            "source_revision_id": revision,
            "channel": "heart_rate",
            "measurement_start": timestamp,
            "value_status": status,
            "value": value,
            "unit": "beats/min",
            "epistemic_type": "measured",
            "source_available_at": None,
            "first_seen_at": "2026-01-10T12:10:00Z",
            "ingested_at": "2026-01-10T12:10:01Z",
            "clock": clock or {},
            "quality_flags": [],
        }

    return {
        "schema_version": "1.0.0",
        "subject_id": "do-not-output-identity",
        "start": "2026-01-10T11:00:00Z",
        "end": "2026-01-10T13:00:00Z",
        "source_revisions": [
            {
                "id": "rev:a",
                "source_instance": "watch",
                "original_record": {"secret": "raw-secret"},
            },
            {
                "id": "rev:b",
                "source_instance": "polar",
                "original_record": {"secret": "raw-secret"},
            },
        ],
        "observations": [
            record(
                "a",
                "rev:a",
                "2026-01-10T12:00:00Z",
                80,
                clock={"original_timestamp": "2026-01-10T07:00:00-05:00"},
            ),
            record("b", "rev:b", "2026-01-10T22:00:00+10:00", 80),
            record("c", "rev:b", "2026-01-10T12:05:00Z", None, status="missing"),
        ],
        "sessions": [],
        "events": [{"payload": {"text": "private-note"}}],
        "coverage": [
            {
                "channel": "heart_rate",
                "source_instance": "watch",
                "status": "unknown",
                "count": 1,
                "valid_count": 1,
                "expected_cadence_seconds": None,
                "gaps": [],
            }
        ],
        "metadata": {
            "evidence_level": "synthetic_integration",
            "timing_policy": "retrospective_current_revision_projection",
            "import_summaries": [],
        },
    }


class QualificationTests(unittest.TestCase):
    def test_cross_offset_candidates_not_deduplicated(self):
        result = assess_replay(fixture())
        self.assertEqual(
            result["summary"]["possible_cross_source_equal_sample_groups"], 1
        )
        self.assertEqual(result["summary"]["observations"], 3)
        self.assertEqual(
            result["summary"]["value_statuses"], {"missing": 1, "valid": 2}
        )
        self.assertNotIn("original_clock_utc_mismatch", result["review_flags"])

    def test_no_personal_claim_or_output_payload_leak(self):
        result = assess_replay(fixture())
        self.assertFalse(result["real_data_reconciled"])
        self.assertFalse(result["live_device_qualified"])
        payload = json.dumps(result)
        for secret in ("do-not-output-identity", "raw-secret", "private-note"):
            self.assertNotIn(secret, payload)

    def test_missing_availability_is_not_imputed(self):
        rows = assess_replay(fixture())["source_channels"]
        self.assertEqual(sum(row["unknown_source_availability"] for row in rows), 3)

    def test_clock_and_ingestion_inconsistencies(self):
        data = fixture()
        data["observations"][0]["clock"][
            "original_timestamp"
        ] = "2026-01-10T12:00:00-05:00"
        data["observations"][0]["ingested_at"] = "2026-01-10T11:00:00Z"
        flags = assess_replay(data)["review_flags"]
        self.assertEqual(flags["original_clock_utc_mismatch"], 1)
        self.assertEqual(flags["ingested_before_first_seen"], 1)

    def test_same_source_equality_is_not_cross_source(self):
        data = fixture()
        data["observations"][1]["source_revision_id"] = "rev:a"
        self.assertEqual(
            assess_replay(data)["summary"]["possible_cross_source_equal_sample_groups"],
            0,
        )

    def test_unresolved_revision_rejected(self):
        data = fixture()
        data["observations"][0]["source_revision_id"] = "rev:missing"
        with self.assertRaises(ValueError):
            assess_replay(data)

    def test_naive_timestamps_and_wrong_versions_rejected(self):
        data = fixture()
        data["observations"][0]["measurement_start"] = "2026-01-10T12:00:00"
        with self.assertRaises(ValueError):
            assess_replay(data)
        data = fixture()
        data["schema_version"] = "2.0"
        with self.assertRaises(ValueError):
            assess_replay(data)

    def test_command_line_exclusive_private_file(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.json"
            report = Path(folder) / "report.json"
            source.write_text(json.dumps(fixture()), encoding="utf-8")
            command = [
                sys.executable,
                str(QUALIFY),
                "--input",
                str(source),
                "--output",
                str(report),
            ]
            success = subprocess.run(command, capture_output=True)
            self.assertEqual(success.returncode, 0, success.stderr.decode())
            self.assertIn("heart_rate", report.read_text())
            self.assertNotIn("raw-secret", report.read_text())
            if os.name == "posix":
                self.assertEqual(report.stat().st_mode & 0o777, 0o600)
            self.assertNotEqual(
                subprocess.run(command, capture_output=True).returncode, 0
            )

    def test_input_size_is_bounded_before_json_parse(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.json"
            report = Path(folder) / "report.json"
            with source.open("wb") as handle:
                handle.truncate(65 * 1024 * 1024)
            command = [
                sys.executable,
                str(QUALIFY),
                "--input",
                str(source),
                "--output",
                str(report),
            ]
            failed = subprocess.run(command, capture_output=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn(b"64 MiB", failed.stderr)
            self.assertFalse(report.exists())


if __name__ == "__main__":
    unittest.main()
