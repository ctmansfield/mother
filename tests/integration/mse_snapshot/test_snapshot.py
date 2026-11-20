from copy import deepcopy
import hashlib
import unittest
from unittest.mock import patch

from integrations.mse_snapshot.snapshot import replay_snapshot
from mse.contracts import ContractError, canonical, digest, read_json

START = "2026-01-01T00:00:00.000000Z"
END = "2026-01-01T00:01:00.000000Z"
COLLECTED = "2026-01-01T00:02:00.000000Z"
RECEIVED = "2026-01-02T00:00:00.000000Z"
COMMITTED = "2026-01-02T00:00:01.000000Z"
DELETED_AGAIN = "2026-01-02T00:00:02.000000Z"
SCOPE = {"subject_id": "synthetic", "source_system": "healthkit",
         "source_instance": "fixture", "collection": "healtharchive"}


def native(i):
    return f"00000000-0000-4000-8000-{i:012x}"


def revision(i, *, deleted=None, hr=False):
    entry = {
        "native_id": native(i),
        "pf001_revision_id": f"revision-{i}" if deleted is None else f"deletion-{i}-{deleted}",
        "artifact_sha256": "a" * 64,
        "receipt": {"scope": SCOPE.copy(), "receipt_id": "synthetic-receipt",
                    "status": "normalized", "artifact_sha256": "a" * 64,
                    "mother_received_at": RECEIVED, "committed_at": COMMITTED,
                    "commit_sequence": 3},
    }
    if deleted is not None:
        return dict(entry, deleted_at=deleted)
    unit = "bpm" if hr else "ms"
    return dict(entry, observation={
        "channel": "heart_rate" if hr else "hrv_sdnn",
        "original_value": "42.0", "original_unit": unit, "value": "42.0", "unit": unit,
        "event_start": START, "event_end": END, "collector_received_at": COLLECTED,
        "source_name": "Synthetic Device", "bundle_id": None,
        "epistemic_type": "unknown" if hr else "vendor_derived",
        "device_id": None, "calibration_id": None, "source_available_at": None,
    })


def snapshot(observations=(), tombstones=()):
    return {
        "schema_version": "mse.evidence-snapshot/0.1",
        "scope": SCOPE.copy(), "purpose": "offline_synthetic_replay",
        "measurement_start": START, "measurement_end": END, "knowledge_cutoff_sequence": 3,
        "normalizer_version": "synthetic-normalizer/0.1",
        "coverage": {"completeness": "unknown"},
        "observations": list(observations), "tombstones": list(tombstones),
        "losses": [{"field": "device_id", "reason": "unavailable"}],
    }


def encode(body):
    return canonical(dict(body, snapshot_sha256=digest(body))).encode()


class SnapshotTests(unittest.TestCase):
    def test_projection_uses_collector_receipt_and_retains_commit_and_full_scope(self):
        body = snapshot([revision(1), revision(2, hr=True)])
        raw = encode(body)
        result = replay_snapshot(raw)
        self.assertEqual(result, replay_snapshot(raw))
        lineage = result["lineage"]
        self.assertEqual(lineage["snapshot_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(lineage["snapshot_manifest_sha256"], digest(body))
        self.assertEqual(lineage["snapshot_scope"], SCOPE)
        self.assertEqual(lineage["observation_revisions"][0]["receipt"]["committed_at"], COMMITTED)
        self.assertEqual(lineage["observation_revisions"][0]["collector_received_at"], COLLECTED)
        self.assertIsNone(lineage["observation_revisions"][0]["source_available_at"])
        run = result["reference_result"]
        self.assertIsNone(run["source_receipt_cutoff"])
        self.assertEqual(run["active_observation_count"], 1)
        self.assertEqual(run["states"][0]["support_source_receipt_max"], COLLECTED)
        self.assertEqual(run["states"][0]["status"], "unknown")
        self.assertEqual(result["projection_losses"][0]["reason"], "heart_rate_derivation_unknown")
        self.assertEqual(result["input_losses"], body["losses"])

    def test_projection_reorders_by_identity_and_keeps_distinct_unknown_deletions(self):
        a, b = revision(2, deleted=COMMITTED), revision(2, deleted=DELETED_AGAIN)
        one = replay_snapshot(encode(snapshot([revision(1)], [a, b])))
        two = replay_snapshot(encode(snapshot([revision(1)], [b, a])))
        self.assertEqual(one["lineage"]["projection_sha256"], two["lineage"]["projection_sha256"])
        self.assertNotEqual(one["result_id"], two["result_id"])
        self.assertEqual(len(one["lineage"]["deletion_facts"]), 2)
        self.assertEqual(len(one["reference_result"]["evidence_manifest"]["tombstone_ids"]), 2)

    def test_projection_is_derived_internally_from_validated_snapshot(self):
        raw = encode(snapshot([revision(1)]))
        with self.assertRaises(TypeError):
            replay_snapshot(raw, b"unrelated projection")
        with patch("integrations.mse_snapshot.snapshot._replay_projection") as runner:
            runner.return_value = {"lineage": {}}
            replay_snapshot(raw)
            self.assertEqual(runner.call_args.args[0], raw)
            projected = read_json(runner.call_args.args[1])
            self.assertEqual(projected["observations"][0]["native_id"], native(1))

    def test_invalid_scope_artifact_cutoff_and_member_state_fail_closed(self):
        for key, value in (
            ("scope", dict(SCOPE, subject_id="other")),
            ("commit_sequence", 4),
            ("commit_sequence", True),
            ("status", "durably_received"),
            ("artifact_sha256", "b" * 64),
            ("committed_at", COLLECTED),
        ):
            with self.subTest(field=key, value=value):
                row = revision(1)
                row["receipt"][key] = value
                with self.assertRaises(ContractError):
                    replay_snapshot(encode(snapshot([row])))

    def test_rejects_tampered_digest_and_invalid_encoding(self):
        body = snapshot([revision(1)])
        invalid = deepcopy(body)
        invalid["coverage"] = {"ratio": 0.5}
        for raw in (
            encode(body).replace(b'"42.0"', b'"43.0"'),
            encode(invalid),
            b'{"scope":null,"scope":null}',
            b'\xff',
        ):
            with self.subTest(raw_length=len(raw)), self.assertRaises(ContractError):
                replay_snapshot(raw)

    def test_rejects_duplicate_active_deleted_conflict_and_half_open_boundary(self):
        at_end = revision(1)
        at_end["observation"]["event_start"] = END
        for body in (
            snapshot([revision(1), revision(1)]),
            snapshot([revision(1)], [revision(1, deleted=COMMITTED)]),
            snapshot([at_end]),
        ):
            with self.subTest(body=body), self.assertRaises(ContractError):
                replay_snapshot(encode(body))

    def test_rejects_conflicting_receipt_identity(self):
        one, two = revision(1), revision(2)
        two["receipt"]["commit_sequence"] = 2
        with self.assertRaisesRegex(ContractError, "Conflicting snapshot receipt"):
            replay_snapshot(encode(snapshot([one, two])))

    def test_unknown_hr_only_is_unavailable(self):
        result = replay_snapshot(encode(snapshot([revision(1, hr=True)])))
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reference_result"]["states"], [])
