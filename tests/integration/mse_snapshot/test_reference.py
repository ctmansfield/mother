import hashlib
import json
import unittest
from unittest.mock import patch

from integrations.mse_snapshot.reference import _replay_projection
from mse.contracts import ContractError, identifier


def observation(native_id):
    return {
        "schema_version": "mse.observation/0.1",
        "observation_id": identifier("observation", "synthetic", "fixture", native_id),
        "native_id": native_id,
        "subject_id": "synthetic",
        "source_instance": "fixture",
        "channel": "hrv_sdnn",
        "unit": "ms",
        "epistemic_type": "vendor_derived",
        "value": "41.25",
        "event_start": "2026-01-01T00:00:00Z",
        "event_end": "2026-01-01T00:01:00Z",
        "received_at": "2026-01-01T00:02:00Z",
        "context": "unknown",
        "quality_flags": ["source_clock_unqualified"],
        "provenance": {"device_id": None, "calibration_id": None},
    }


def projection(observations=(), deleted=(), *, synthetic=True):
    return json.dumps({
        "schema_version": "mse.replay/0.1",
        "synthetic": synthetic,
        "observations": list(observations),
        "tombstones": [
            {"observation_id": key, "deleted_at": "2026-01-01T00:03:00Z"}
            for key in deleted
        ],
    }).encode()


class ReferenceReplayTests(unittest.TestCase):
    def test_deterministic_derived_lineage_for_exact_snapshot_bytes(self):
        payload = projection([observation("1")])
        result = _replay_projection(b"snapshot-a", payload)
        self.assertEqual(result, _replay_projection(b"snapshot-a", payload))
        self.assertNotEqual(
            result["result_id"], _replay_projection(b"snapshot-b", payload)["result_id"]
        )
        self.assertEqual(result["lineage"]["projection_sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(result["epistemic_class"], "derived")
        run = result["reference_result"]
        self.assertFalse(run["historical_mother_availability_established"])
        self.assertFalse(run["historical_source_availability_established"])
        self.assertEqual(run["states"][0]["status"], "unknown")
        self.assertIsNone(run["states"][0]["mean"])

    def test_tombstones_suppress_observations_and_retain_unknown_id(self):
        record = observation("1")
        payload = projection([record], [record["observation_id"], observation("2")["observation_id"]])
        result = _replay_projection(b"snapshot-a", payload)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reference_result"]["states"], [])
        self.assertEqual(len(result["reference_result"]["evidence_manifest"]["tombstone_ids"]), 2)

    def test_rejects_ambiguous_revision_selection_or_non_synthetic_input(self):
        record = observation("1")
        with self.assertRaises(ContractError):
            _replay_projection(b"snapshot-a", projection([record, record]))
        with self.assertRaises(ContractError):
            _replay_projection(b"snapshot-a", projection(synthetic=False))

    def test_refuses_unexpected_reference_code(self):
        with patch("integrations.mse_snapshot.reference.implementation_sha256", return_value="changed"):
            with self.assertRaises(ContractError):
                _replay_projection(b"snapshot-a", projection())
