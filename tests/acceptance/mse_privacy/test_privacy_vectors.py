"""Synthetic acceptance inputs for the forthcoming privacy-boundary APIs."""

from decimal import Decimal
import json
from pathlib import Path
import unittest


FIXTURE = (
    Path(__file__).resolve().parents[2] / "fixtures" / "mse_integration"
    / "source-compatible" / "baseline.json"
)
FORBIDDEN_KEYS = frozenset({
    "native_id", "subject_id", "source_instance", "bundle_id", "source_name",
    "artifact_sha256", "revision_sha256", "processing_revision_sha256",
    "original_timestamp", "raw_bytes", "local_path",
})
CANARIES = ("SYNTH-PRIVATE-SUBJECT-71", "SYNTH-PRIVATE-SOURCE-83",
            "synthetic-raw-path-41", "synthetic-source-label-96")


def disclosure_hits(value, canaries=CANARIES):
    """Return matching forbidden JSON field names and fixture-specific strings."""
    hits = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_KEYS:
                hits.add(key)
            hits.update(disclosure_hits(key, canaries))
            hits.update(disclosure_hits(child, canaries))
    elif isinstance(value, list):
        for child in value:
            hits.update(disclosure_hits(child, canaries))
    elif isinstance(value, str):
        hits.update(token for token in canaries if token.casefold() in value.casefold())
    return hits


class PrivacyVectors(unittest.TestCase):
    def test_scanner_catches_nested_fields_and_embedded_canaries(self):
        output = {
            "summary": [{"metadata": {"artifact_sha256": "0" * 64}}],
            "note": "input SYNTH-PRIVATE-SUBJECT-71 rejected",
            "synthetic-raw-path-41": 1,
        }
        self.assertEqual(disclosure_hits(output), {
            "artifact_sha256", "SYNTH-PRIVATE-SUBJECT-71", "synthetic-raw-path-41",
        })

    def test_scanner_permits_fields_needed_for_metrics_and_explicit_loss(self):
        output = {"series": [{"metric": "hrv_sdnn", "unit": "ms", "relative_seconds": 0}],
                  "losses": [{"field": "measurement_time", "reason": "relative_time"}]}
        self.assertEqual(disclosure_hits(output), set())

    def test_frozen_fixture_supports_exact_hr_sdnn_and_unknown_deletion(self):
        archive = json.loads(FIXTURE.read_bytes(), parse_float=Decimal)
        hr, sdnn, deleted = archive["readings"]
        self.assertEqual((hr["kind"], hr["unit"], hr["value"]),
                         ("Heart rate", "bpm", Decimal("64.25")))
        self.assertEqual((sdnn["kind"], sdnn["unit"], sdnn["value"]),
                         ("HRV (SDNN)", "ms", Decimal("41.5")))
        self.assertEqual(sdnn["end"] - sdnn["start"], 1)
        self.assertEqual(archive["tombstones"][deleted["id"]], deleted["deletedAt"])
        unknown = archive["tombstones"].keys() - {row["id"] for row in archive["readings"]}
        self.assertEqual(len(unknown), 1)
        self.assertNotIn("device_id", sdnn)
        self.assertNotIn("calibration_id", sdnn)
