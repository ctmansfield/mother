from copy import deepcopy
import hashlib
import unittest
from unittest.mock import patch

from integrations.mse_snapshot.snapshot import replay_snapshot, select_fact_sighting
from mse.contracts import ContractError, canonical, digest, read_json

START = "2001-01-01T00:00:00.000000Z"
END = "2001-01-01T00:00:01.000000Z"
COLLECTED = "2001-01-01T00:00:02.000000Z"
RECEIVED = "2001-01-01T00:00:04.000000Z"
COMMITTED = "2001-01-01T00:00:06.000000Z"
SCOPE = {"subject_id": "synthetic", "source_system": "healthkit",
         "source_instance": "fixture", "collection": "healtharchive"}
OPTIONS = {"expected_scope": SCOPE, "expected_archive_id": "synthetic-archive",
           "max_bytes": 20000, "max_members": 100}


def revision(i, *, delete_time=None, hr=False):
    native = f"00000000-0000-4000-8000-{i:012x}"
    member = {
        "pf001_revision_id": f"revision-{i}-{delete_time}",
        "artifact_sha256": "a" * 64, "receipt_id": "b" * 64,
        "mother_received_at": RECEIVED, "committed_at": COMMITTED, "commit_sequence": 3,
    }
    if delete_time is not None:
        revision = {
            "native_id": native, "operation": "delete",
            "deleted_at": "2001-01-01T00:00:03.000000Z",
            "original_deleted_at": [delete_time], "locators": ["/tombstones/example"],
            "revision_sha256": digest(["mse.source-revision/0.2", SCOPE, native, "delete", delete_time]),
        }
        return dict(member, source_revision=revision)

    normalized = {
        "channel": "heart_rate" if hr else "hrv_sdnn", "unit": "bpm" if hr else "ms",
        "epistemic_type": "unknown" if hr else "vendor_derived", "value": "42",
        "event_start": START, "event_end": END,
        "classification_basis": "capture_derivation_unavailable" if hr else "healthkit_sdnn",
        "classification_evidence_sha256": None,
    }
    fact = {"channel": normalized["channel"], "value": "42", "unit": normalized["unit"],
            "start": "0.0000005", "end": "1", "source_name": "Synthetic Device", "bundle_id": None}
    source_hash = digest(["mse.source-revision/0.2", SCOPE, native, "upsert", fact])
    observation = dict(
        normalized, original_value="4.20e1", original_unit=normalized["unit"],
        original_start="0.0000005", original_end="1", original_received_at="2",
        collector_received_at=COLLECTED, source_name=fact["source_name"],
        bundle_id=None, device_id=None, calibration_id=None, source_available_at=None,
    )
    return dict(
        member, source_revision={"native_id": native, "operation": "upsert",
                                 "observation": observation, "revision_sha256": source_hash,
                                 "locators": ["/readings/0"]},
        processing_revision_sha256=digest(["mse.processing-revision/0.2", source_hash, "fixture-1", normalized]),
    )


def snapshot(observations=(), tombstones=()):
    return {
        "schema_version": "mse.evidence-snapshot/0.2",
        "scope": SCOPE.copy(), "archive_id": "synthetic-archive",
        "purpose": "offline_synthetic_replay",
        "measurement_start": START, "measurement_end": END, "knowledge_cutoff_sequence": 3,
        "normalizer_version": "fixture-1",
        "coverage": {"capture_kind": "partial", "backfill_start": None,
                     "observed_start": None, "observed_end": None,
                     "permissions": "unknown", "completeness": "unknown"},
        "observations": list(observations), "tombstones": list(tombstones),
        "losses": [{"field": "device_id", "reason": "unavailable", "locator": None}],
    }


def replay_fixture(raw, **changes):
    # Test-only independent membership oracle assembled from synthetic ledger
    # rows. Production integration must use FORGE's reopened authoritative state.
    committed_rows = [revision(1), revision(2, hr=True),
                      revision(2, delete_time="3"), revision(2, delete_time="3.0000001")]
    def verify(archive_id, scope, member):
        return archive_id == OPTIONS["expected_archive_id"] and scope == SCOPE and member in committed_rows
    return replay_snapshot(raw, **dict(OPTIONS, verify_membership=verify, **changes))


def encode(body):
    return canonical(dict(body, snapshot_sha256=digest(["mse.snapshot/0.2", body]))).encode()


class SnapshotTests(unittest.TestCase):
    def test_projection_keeps_clocks_scope_unknowns_and_hashes(self):
        body = snapshot([revision(1), revision(2, hr=True)])
        raw = encode(body)
        result = replay_fixture(raw)
        self.assertEqual(result, replay_fixture(raw))
        lineage = result["lineage"]
        self.assertEqual(lineage["snapshot_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(lineage["snapshot_manifest_sha256"], digest(["mse.snapshot/0.2", body]))
        self.assertEqual(lineage["snapshot_scope"], SCOPE)
        self.assertEqual(lineage["observation_revisions"][0]["committed_at"], COMMITTED)
        self.assertEqual(lineage["observation_revisions"][0]["collector_received_at"], COLLECTED)
        self.assertIsNone(lineage["observation_revisions"][0]["source_available_at"])
        run = result["reference_result"]
        self.assertIsNone(run["source_receipt_cutoff"])
        self.assertEqual(run["active_observation_count"], 1)
        self.assertEqual(run["states"][0]["support_source_receipt_max"], COLLECTED)
        self.assertEqual(run["states"][0]["status"], "unknown")
        self.assertEqual(result["projection_losses"][0]["reason"], "heart_rate_derivation_unknown")
        self.assertEqual(result["input_losses"], body["losses"])

    def test_rounded_delete_collision_retains_both_source_facts_and_reports_loss(self):
        members = sorted(
            [revision(2, delete_time="3"), revision(2, delete_time="3.0000001")],
            key=lambda m: m["source_revision"]["revision_sha256"],
        )
        result = replay_fixture(encode(snapshot([revision(1)], members)))
        self.assertEqual(len(result["lineage"]["deletion_facts"]), 2)
        self.assertEqual(len(result["reference_result"]["evidence_manifest"]["tombstone_ids"]), 1)
        self.assertEqual(result["projection_losses"][0]["reason"], "reference_deletion_time_collision")

    def test_projection_is_derived_internally(self):
        raw = encode(snapshot([revision(1)]))
        with self.assertRaises(TypeError):
            replay_snapshot(raw, b"unrelated projection", verify_membership=lambda *_: True, **OPTIONS)
        with patch("integrations.mse_snapshot.snapshot._replay_projection") as runner:
            runner.return_value = {"lineage": {}}
            replay_fixture(raw)
            self.assertEqual(runner.call_args.args[0], raw)
            projected = read_json(runner.call_args.args[1])
            self.assertEqual(projected["observations"][0]["provenance"]["received_at_semantics"], "collector_receipt")

    def test_rejects_wrong_scope_archive_and_limits(self):
        raw = encode(snapshot([revision(1)]))
        for changes in ({"expected_scope": {}}, {"expected_archive_id": "other"},
                        {"max_bytes": 1}, {"max_members": 1}):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                replay_fixture(raw, **changes)

    def test_invalid_commit_and_source_or_processing_digest_fail_closed(self):
        for key, value in (
            ("commit_sequence", 4), ("commit_sequence", True), ("committed_at", COLLECTED),
            ("processing_revision_sha256", "c" * 64),
        ):
            with self.subTest(field=key, value=value):
                row = revision(1)
                row[key] = value
                with self.assertRaises(ContractError):
                    replay_fixture(encode(snapshot([row])))
        row = revision(1)
        row["source_revision"]["revision_sha256"] = "c" * 64
        with self.assertRaisesRegex(ContractError, "source revision digest mismatch"):
            replay_fixture(encode(snapshot([row])))

    def test_rejects_tampered_digest_and_invalid_encoding(self):
        body = snapshot([revision(1)])
        invalid = deepcopy(body)
        invalid["coverage"]["ratio"] = 0.5
        for raw in (encode(body).replace(b'"42"', b'"43"'), encode(invalid),
                    b'{"scope":null,"scope":null}', b'\xff'):
            with self.subTest(raw_length=len(raw)), self.assertRaises(ContractError):
                replay_fixture(raw)

    def test_rejects_unordered_duplicate_and_active_deleted_members(self):
        for body in (snapshot([revision(2), revision(1)]),
                     snapshot([revision(1), revision(1)]),
                     snapshot([revision(1)], [revision(1, delete_time="3")])):
            with self.subTest(body=body), self.assertRaises(ContractError):
                replay_fixture(encode(body))

    def test_rejects_conflicting_receipt_identity(self):
        one, two = revision(1), revision(2)
        two["commit_sequence"] = 2
        with self.assertRaisesRegex(ContractError, "Conflicting snapshot receipt"):
            replay_fixture(encode(snapshot([one, two])))

    def test_reopened_membership_rejects_self_invented_consistent_receipt(self):
        row = revision(1)
        row["receipt_id"] = "e" * 64
        with patch("integrations.mse_snapshot.snapshot._replay_projection") as runner:
            with self.assertRaisesRegex(ContractError, "not verified in reopened"):
                replay_fixture(encode(snapshot([row])))
            runner.assert_not_called()

    def test_membership_failure_never_replays(self):
        raw = encode(snapshot([revision(1)]))
        with self.assertRaisesRegex(ContractError, "not verified in reopened"):
            replay_snapshot(raw, **OPTIONS, verify_membership=lambda *_: None)

    def test_repeated_fact_selection_is_permutation_and_cutoff_stable(self):
        first = revision(1)
        later = dict(first, receipt_id="c" * 64, artifact_sha256="d" * 64, commit_sequence=5)
        def select(members, cutoff):
            return select_fact_sighting(members, cutoff, normalizer_version="fixture-1")

        a, b = ("fixture-1", first), ("fixture-1", later)
        self.assertIsNone(select([b, a], 2))
        self.assertIsNone(select([("other-normalizer", first)], 3))
        for cutoff in (3, 4, 5, 20):
            self.assertEqual(select([b, a], cutoff), first)
            self.assertEqual(select([a, b, a], cutoff), first)
        same_sequence = dict(later, commit_sequence=3)
        with self.assertRaisesRegex(ContractError, "commitment sequence"):
            select([a, ("fixture-1", same_sequence)], 5)
        unequal_same_receipt = dict(first, artifact_sha256="f" * 64)
        with self.assertRaisesRegex(ContractError, "Unequal sightings"):
            select([a, ("fixture-1", unequal_same_receipt)], 5)
        variant = dict(later, processing_revision_sha256="e" * 64)
        self.assertEqual(select([a, ("fixture-1", variant)], 3), first)
        with self.assertRaisesRegex(ContractError, "Ambiguous processing"):
            select([a, ("fixture-1", variant)], 5)
        with self.assertRaisesRegex(ContractError, "distinct revisions"):
            select([a, ("fixture-1", revision(2))], 5)

    def test_unknown_hr_only_is_unavailable(self):
        result = replay_fixture(encode(snapshot([revision(2, hr=True)])))
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reference_result"]["states"], [])
