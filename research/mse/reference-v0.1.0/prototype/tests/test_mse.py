from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import UUID

from mse.adapters import healthkit_archive, native_replay
from mse.contracts import (ContractError, identifier, read_json, swift_date,
                           validate_observation)
from mse.features import meal_area
from mse.model import Config, estimate, predict, replay
from mse.storage import Store

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def iso(seconds=0):
    return (START + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def observation(index, value=60, *, channel="heart_rate", subject="synthetic-person", source="synthetic-watch", seconds=None):
    native = str(UUID(int=index + 1))
    return validate_observation({
        "schema_version": "mse.observation/0.1", "observation_id": identifier("observation", subject, source, native),
        "native_id": native, "subject_id": subject, "source_instance": source,
        "channel": channel, "value": str(value), "unit": {"heart_rate": "bpm", "hrv_sdnn": "ms", "glucose": "mmol/L"}[channel],
        "event_start": iso(index * 900 if seconds is None else seconds),
        "event_end": iso(index * 900 if seconds is None else seconds),
        "received_at": iso((index * 900 if seconds is None else seconds) + 30),
        "epistemic_type": "vendor_derived" if channel == "hrv_sdnn" else "measured",
        "context": "unknown", "provenance": {"fixture": "synthetic", "bundle_id": "example.synthetic.watch", "device_id": None},
        "quality_flags": ["synthetic", "acquisition_conditions_unknown"],
    })


def archive(readings=None, tombstones=None):
    return json.dumps({"readings": readings or [], "anchors": {"heartRate": "AQID"},
                       "tombstones": tombstones or {}, "backfillStart": 0.0}, sort_keys=True).encode()


def saved_reading(index=1, **changes):
    item = {"id": str(UUID(int=index)), "kind": "Heart rate", "value": 60.0, "unit": "bpm", "start": 0.0,
            "end": 5.0, "source": "Synthetic Watch", "bundleID": "example.watch", "receivedAt": 10.0}
    item.update(changes)
    return item


def batch(records, deleted=None):
    raw = json.dumps({"schema_version": "mse.replay/0.1", "synthetic": True,
                      "observations": records, "tombstones": deleted or []}, sort_keys=True).encode()
    observations, tombstones, metadata = native_replay(raw)
    return raw, observations, tombstones, metadata


class ContractTests(unittest.TestCase):
    def test_swift_epoch_is_not_unix(self):
        self.assertEqual(swift_date(0), "2001-01-01T00:00:00.000000Z")
        self.assertEqual(swift_date(60.5), "2001-01-01T00:01:00.500000Z")

    def test_healthkit_retains_uuid_source_and_anchor_bytes(self):
        rows, _, meta = healthkit_archive(archive([saved_reading()]), subject_id="p", source_instance="s")
        self.assertEqual(rows[0]["native_id"], "00000000-0000-0000-0000-000000000001")
        self.assertEqual(rows[0]["provenance"]["bundle_id"], "example.watch")
        self.assertIsNone(rows[0]["provenance"]["device_id"])
        self.assertEqual(meta["anchor_sha256"]["heartRate"], hashlib.sha256(b"\x01\x02\x03").hexdigest())

    def test_sdnn_is_vendor_derived_and_never_rmssd(self):
        rows, _, _ = healthkit_archive(archive([saved_reading(kind="HRV (SDNN)", value=43.5, unit="ms")]), subject_id="p", source_instance="s")
        self.assertEqual(rows[0]["channel"], "hrv_sdnn")
        self.assertEqual(rows[0]["epistemic_type"], "vendor_derived")

    def test_wrong_units_fail_closed(self):
        record = observation(0)
        record["unit"] = "ms"
        with self.assertRaises(ContractError):
            validate_observation(record)

    def test_nonfinite_json_and_nonfinite_scalar_rejected(self):
        for data in (b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}'):
            with self.assertRaises(ContractError):
                read_json(data)
        record = observation(0)
        for value in ("NaN", "Infinity", "1e1000"):
            record["value"] = value
            with self.assertRaises(ContractError):
                validate_observation(record)

    def test_reversed_interval_rejected(self):
        record = observation(0)
        record["event_end"] = iso(-1)
        with self.assertRaises(ContractError):
            validate_observation(record)

    def test_naive_timestamp_and_boolean_value_rejected(self):
        record = observation(0)
        record["event_start"] = "2026-01-01T00:00:00"
        with self.assertRaises(ContractError):
            validate_observation(record)
        record = observation(0)
        record["value"] = True
        with self.assertRaises(ContractError):
            validate_observation(record)

    def test_inferred_value_cannot_enter_observed_stream(self):
        record = observation(0)
        record["epistemic_type"] = "inferred"
        with self.assertRaises(ContractError):
            validate_observation(record)

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ContractError):
            read_json(b'{"value":60,"value":90}')

    def test_unsupported_healthkit_type_not_silently_reinterpreted(self):
        with self.assertRaises(ContractError):
            healthkit_archive(archive([saved_reading(kind="Glucose", unit="mg/dL")]), subject_id="p", source_instance="s")


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mse-test-")
        self.path = Path(self.tmp.name) / "evidence.sqlite"
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_import_replay_is_idempotent_and_preserves_original_bytes(self):
        payload = batch([observation(0)])
        first = self.store.import_batch(*payload)
        second = self.store.import_batch(*payload)
        self.assertEqual(first["added"], 1)
        self.assertEqual(second["added"], 0)
        self.assertEqual(second["duplicates"], 1)
        self.assertEqual(self.store.db.execute("SELECT content FROM artifacts").fetchone()[0], payload[0])

    def test_changed_receipt_is_duplicate_not_sample_conflict(self):
        record = observation(0)
        self.store.import_batch(*batch([record]))
        changed = dict(record, received_at=iso(3600))
        outcome = self.store.import_batch(*batch([changed]))
        self.assertEqual(outcome["duplicates"], 1)
        self.assertEqual(self.store.active_observations()[0]["received_at"], record["received_at"])

    def test_conflict_rejects_entire_import_and_retains_rejected_raw(self):
        original = observation(0)
        self.store.import_batch(*batch([original]))
        changed = dict(original, value="61")
        with self.assertRaises(ContractError):
            self.store.import_batch(*batch([changed, observation(1)]))
        self.assertEqual(len(self.store.active_observations()), 1)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM rejected_imports").fetchone()[0], 1)
        self.assertEqual(self.store.active_observations()[0]["value"], "60")

    def test_conflicting_duplicates_in_same_batch_rejected(self):
        a = observation(0)
        with self.assertRaises(ContractError):
            self.store.import_batch(*batch([a, dict(a, value="70")]))
        self.assertEqual(self.store.active_observations(), [])

    def test_delete_before_add_never_resurrects(self):
        record = observation(0)
        self.store.import_batch(*batch([], [{"observation_id": record["observation_id"], "deleted_at": iso(60)}]))
        self.store.import_batch(*batch([record]))
        self.assertEqual(self.store.active_observations(), [])
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM observations").fetchone()[0], 1)

    def test_source_and_subject_identity_isolate_same_native_uuid(self):
        self.store.import_batch(*batch([observation(0), observation(0, subject="other"), observation(0, source="other")]))
        self.assertEqual(len(self.store.active_observations()), 3)

    def test_source_receipt_cutoff_filters_late_arrivals(self):
        record = dict(observation(0), received_at=iso(10000))
        self.store.import_batch(*batch([record]))
        self.assertEqual(self.store.active_observations(iso(100)), [])
        self.assertEqual(len(self.store.active_observations(iso(10000))), 1)

    def test_snapshot_cutoff_excludes_incomplete_interval_even_with_bad_receipt_clock(self):
        record = dict(observation(0), event_end=iso(3600), received_at=iso(30))
        self.store.import_batch(*batch([record]))
        self.assertEqual(self.store.active_observations(iso(60)), [])

    def test_snapshot_filter_is_machine_labeled_retrospective_only(self):
        records = [observation(i) for i in range(10)]
        records[0] = dict(records[0], received_at=iso(20000))
        self.store.import_batch(*batch(records))
        result = replay(self.store, source_receipt_cutoff=iso(30000))
        self.assertEqual(result["replay_mode"], "retrospective_snapshot")
        self.assertFalse(result["historical_source_availability_established"])
        self.assertFalse(result["historical_mother_availability_established"])
        with self.assertRaises(ContractError):
            replay(self.store, replay_mode="source_as_available")

    def test_tombstone_cutoff_retains_earlier_as_known_view(self):
        record = observation(0)
        self.store.import_batch(*batch([record], [{"observation_id": record["observation_id"], "deleted_at": iso(3600)}]))
        self.assertEqual(len(self.store.active_observations(iso(60))), 1)
        self.assertEqual(self.store.active_observations(), [])

    def test_unrecognized_existing_database_not_modified(self):
        path = Path(self.tmp.name) / "foreign.sqlite"
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE important(value TEXT)")
        connection.commit()
        connection.close()
        original = path.read_bytes()
        with self.assertRaises(ContractError):
            Store(path)
        self.assertEqual(path.read_bytes(), original)

    def test_immutable_rows_cannot_be_updated_or_deleted(self):
        self.store.import_batch(*batch([observation(0)]))
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.db.execute("DELETE FROM observations")
        self.store.db.rollback()

    def test_deletion_invalidates_old_run_and_changes_dependency_lineage(self):
        records = [observation(i, 60 + i % 2) for i in range(12)]
        self.store.import_batch(*batch(records))
        old = replay(self.store)
        removed = records[2]["observation_id"]
        self.store.import_batch(*batch([], [{"observation_id": removed, "deleted_at": iso(20000)}]))
        new = replay(self.store)
        self.assertNotEqual(old["run_id"], new["run_id"])
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM runs").fetchone()[0], 2)
        self.assertGreater(self.store.db.execute("SELECT count(*) FROM run_invalidations").fetchone()[0], 0)
        for state in new["states"]:
            self.assertNotIn(removed, state["supporting_observation_ids"] + state["baseline_observation_ids"])

    def test_replay_is_deterministic(self):
        self.store.import_batch(*batch([observation(i) for i in range(10)]))
        self.assertEqual(replay(self.store), replay(self.store))


class ModelTests(unittest.TestCase):
    def test_insufficient_data_emits_unknown_not_zero(self):
        states = estimate([observation(i) for i in range(7)])
        self.assertTrue(all(s["status"] == "unknown" and s["mean"] is None for s in states))

    def test_future_observations_do_not_change_past_estimates(self):
        records = [observation(i, 60 + i % 2) for i in range(10)]
        early = estimate(records)
        extended = estimate(records + [observation(20, 150)])
        self.assertEqual(early, extended[:len(early)])

    def test_current_sample_does_not_enter_its_baseline(self):
        records = [observation(i, 60) for i in range(8)] + [observation(8, 100)]
        result = estimate(records)[-1]
        self.assertEqual(result["baseline"]["mean"], 60)
        self.assertEqual(result["baseline_count"], 8)
        self.assertNotIn(records[-1]["observation_id"], result["baseline_observation_ids"])

    def test_positive_and_negative_shifts_keep_direction(self):
        stable = [observation(i, 60) for i in range(8)]
        self.assertGreater(estimate(stable + [observation(8, 80)])[-1]["mean"], 0)
        self.assertLess(estimate(stable + [observation(8, 50)])[-1]["mean"], 0)

    def test_sdnn_model_uses_log_ratio(self):
        rows = [observation(i, 50, channel="hrv_sdnn") for i in range(8)] + [observation(8, 25, channel="hrv_sdnn")]
        result = estimate(rows)[-1]
        self.assertEqual(result["unit"], "log(ms/ms)")
        self.assertLess(result["mean"], 0)
        self.assertEqual(result["mechanism_status"], "unknown")

    def test_model_never_pools_people_or_sources(self):
        records = [observation(i, subject="a") for i in range(4)] + [observation(i, subject="b") for i in range(4)]
        records += [observation(i, source="other") for i in range(4)]
        self.assertTrue(all(s["status"] == "unknown" for s in estimate(records)))

    def test_device_or_bundle_changes_require_new_baseline(self):
        records = [observation(i) for i in range(8)]
        new = observation(8)
        new["provenance"] = dict(new["provenance"], bundle_id="other.bundle")
        state = estimate(records + [new])[-1]
        self.assertEqual(state["status"], "unknown")
        self.assertEqual(state["baseline_count"], 0)

    def test_elapsed_time_grows_prediction_uncertainty(self):
        short = predict(1, 1, 60, tau=7200, equilibrium_variance=100)
        long = predict(1, 1, 3600, tau=7200, equilibrium_variance=100)
        self.assertGreater(long[1], short[1])
        self.assertLess(abs(long[0]), abs(short[0]))

    def test_long_gap_withholds_latent_continuity(self):
        records = [observation(i) for i in range(10)] + [observation(10, seconds=36000)]
        result = estimate(records, Config(max_gap_seconds=3600))[-1]
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason"], "gap_reset_reacquisition")
        self.assertIsNone(result["reference_95_interval"])

    def test_same_timestamp_not_independent_updates(self):
        records = [observation(i) for i in range(10)] + [observation(100, seconds=8100)]
        last = [s for s in estimate(records) if s["observation_reference_time"].startswith("2026-01-01T02:15:00")]
        self.assertEqual(sum(s["reason"] == "simultaneous_samples_not_assumed_independent" for s in last), 1)

    def test_same_timestamp_does_not_inflate_baseline_count(self):
        records = [observation(i, seconds=0) for i in range(20)] + [observation(100, seconds=900)]
        last = estimate(records)[-1]
        self.assertEqual(last["baseline_count"], 1)
        self.assertEqual(last["status"], "unknown")

    def test_filter_retains_prior_baseline_ancestry_after_window_moves(self):
        records = [observation(i, 60 + i % 2) for i in range(12)]
        last = estimate(records, Config(min_baseline=2, baseline_window_seconds=1800))[-1]
        self.assertNotIn(records[0]["observation_id"], last["baseline_observation_ids"])
        self.assertIn(records[0]["observation_id"], last["supporting_observation_ids"])

    def test_uncertainty_explicitly_uncalibrated_and_context_unknown(self):
        result = estimate([observation(i) for i in range(10)])[-1]
        self.assertEqual(result["uncertainty_status"], "uncalibrated_reference_model")
        self.assertEqual(result["context"], "unknown")
        self.assertTrue(any("not adjusted" in x for x in result["limits"]))

    def test_review_probe_long_interval_never_contributes_before_completion(self):
        records = [observation(i, seconds=i * 60) for i in range(10)]
        records[0] = dict(records[0], event_end=iso(39 * 60), received_at=iso(39 * 60))
        outputs = estimate(records)
        target = next(s for s in outputs if s["observation_reference_time"].startswith("2026-01-01T00:09:00"))
        self.assertNotIn(records[0]["observation_id"], target["baseline_observation_ids"])
        self.assertNotIn(records[0]["observation_id"], target["supporting_observation_ids"])
        self.assertEqual(target["baseline_count"], 8)

    def test_overlapping_equal_duration_aggregates_cannot_inflate_support(self):
        records = []
        for i in range(10):
            record = observation(i, seconds=i * 60)
            record.update(event_end=iso(i * 60 + 600), received_at=iso(i * 60 + 630))
            records.append(record)
        outputs = estimate(records)
        self.assertTrue(all(s["status"] == "unknown" for s in outputs))
        self.assertEqual(outputs[-1]["reason"], "overlapping_acquisition_intervals")

    def test_aggregate_reference_uses_end_not_start(self):
        record = observation(0)
        record.update(event_end=iso(60), received_at=iso(90))
        result = estimate([record])[0]
        self.assertEqual(result["observation_reference_time"], iso(60))
        self.assertEqual(result["observation_reference_policy"], "aggregate_interval_end")
        self.assertNotIn("as_of_event_time", result)

    def test_late_receipt_is_disclosed_and_source_as_available_mode_refused(self):
        records = [observation(i) for i in range(10)]
        records[0] = dict(records[0], received_at=iso(20000))
        result = estimate(records)[-1]
        self.assertGreater(result["support_source_receipt_max"], result["observation_reference_time"])
        self.assertFalse(result["historical_source_availability_established"])
        self.assertEqual(result["availability_policy"], "retrospective_snapshot")
        with self.assertRaises(ContractError):
            estimate(records, replay_mode="source_as_available")

    def test_review_probe_changed_method_requires_new_baseline(self):
        records = [observation(i, 50, channel="hrv_sdnn") for i in range(10)]
        records[-1]["provenance"] = dict(records[-1]["provenance"], method="different-SDNN-method")
        result = estimate(records)[-1]
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["baseline_count"], 0)

    def test_changed_interval_duration_requires_new_baseline(self):
        records = [observation(i, 50, channel="hrv_sdnn") for i in range(10)]
        records[-1]["event_end"] = iso(9 * 900 + 1)
        result = estimate(records)[-1]
        self.assertEqual(result["baseline_count"], 0)
        self.assertEqual(result["measurement_stratum"]["observed_interval_seconds"], 1)

    def test_declared_unknown_window_and_explicit_window_do_not_pool(self):
        records = [observation(i) for i in range(10)]
        records[-1]["provenance"] = dict(records[-1]["provenance"], acquisition_window_seconds=60)
        self.assertEqual(estimate(records)[-1]["baseline_count"], 0)

    def test_changed_calibration_identity_requires_new_baseline(self):
        records = [observation(i) for i in range(10)]
        records[-1]["provenance"] = dict(records[-1]["provenance"], calibration_id="new-calibration")
        self.assertEqual(estimate(records)[-1]["baseline_count"], 0)

    def test_review_probe_known_motion_artifact_is_excluded_and_disclosed(self):
        records = [observation(i) for i in range(10)]
        records[0]["quality_flags"].append("known_motion_artifact")
        result = estimate(records)[-1]
        artifact_id = records[0]["observation_id"]
        self.assertNotIn(artifact_id, result["baseline_observation_ids"])
        self.assertNotIn(artifact_id, result["supporting_observation_ids"])
        self.assertIn(artifact_id, result["excluded_observation_ids"])
        self.assertIn("known_motion_artifact", result["excluded_quality_flags"])
        self.assertIn("known_motion_artifact", result["measurement_quality_flags"])

    def test_known_invalid_current_observation_produces_unknown(self):
        records = [observation(i) for i in range(10)]
        records[-1]["quality_flags"].append("known_motion_artifact")
        result = estimate(records)[-1]
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason"], "known_invalid_measurement_quality")
        self.assertIsNone(result["mean"])

    def test_quality_flags_propagate_from_recursive_baseline_ancestry(self):
        records = [observation(i) for i in range(12)]
        records[0]["quality_flags"].append("unqualified_sensor_bias")
        result = estimate(records, Config(min_baseline=2, baseline_window_seconds=1800))[-1]
        self.assertNotIn(records[0]["observation_id"], result["baseline_observation_ids"])
        self.assertIn("unqualified_sensor_bias", result["filter_ancestor_quality_flags"])
        self.assertIn("unqualified_sensor_bias", result["measurement_quality_flags"])


class AreaTests(unittest.TestCase):
    def test_signed_area_and_positive_zero_crossing_are_distinct(self):
        outcome = meal_area([(iso(0), 4), (iso(600), 6)], start=iso(0), end=iso(600), baseline=5)
        self.assertEqual(outcome["whole_window_signed_incremental_area"], 0)
        self.assertEqual(outcome["whole_window_positive_incremental_area"], 2.5)

    def test_gaps_are_not_bridged_or_counted_as_zero(self):
        outcome = meal_area([(iso(0), 5), (iso(300), 6), (iso(3600), 5)], start=iso(0), end=iso(3600), baseline=5)
        self.assertIsNone(outcome["whole_window_signed_incremental_area"])
        self.assertAlmostEqual(outcome["coverage_fraction"], 1 / 12)
        self.assertAlmostEqual(outcome["observed_signed_incremental_area"], 2.5)

    def test_unbracketed_boundaries_withhold_whole_window_area(self):
        outcome = meal_area([(iso(300), 5), (iso(600), 6)], start=iso(0), end=iso(900), baseline=5)
        self.assertIsNone(outcome["whole_window_signed_incremental_area"])
        self.assertAlmostEqual(outcome["coverage_fraction"], 1 / 3)

    def test_duplicate_area_timestamp_requires_selection_policy(self):
        with self.assertRaises(ContractError):
            meal_area([(iso(0), 5), (iso(0), 7)], start=iso(0), end=iso(600), baseline=5)


if __name__ == "__main__":
    unittest.main()
