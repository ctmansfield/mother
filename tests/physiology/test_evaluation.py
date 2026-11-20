"""Synthetic evaluator logic checks; these are not wearer performance results."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import math

import pytest

from mother.physiology.evaluation import evaluate_baseline


def episode(day, value, **updates):
    cutoff = datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=day)
    record = {
        "episode_id": f"e{day}",
        "outcome_group_id": f"g{day}",
        "cutoff": cutoff.isoformat(),
        "outcome_end": (cutoff + timedelta(hours=1)).isoformat(),
        "outcome_available_at": (cutoff + timedelta(hours=2)).isoformat(),
        "channel": "declared_scalar",
        "unit": "example_unit",
        "value": value,
        "eligibility": "eligible",
    }
    record.update(updates)
    return record


def run(records, **changes):
    return evaluate_baseline(
        records,
        data_version="synthetic-fixture/1",
        processing_version="declared-target/1",
        **changes,
    )


def five():
    return [episode(day, value) for day, value in enumerate([10, 20, 30, 20, 40])]


def test_chronological_heldout_baseline_and_native_unit_errors_are_hand_calculated():
    report = run(five(), holdout_fraction=0.4)
    channel = report["channels"][0]
    assert channel["baseline"]["value"] == 20
    assert channel["baseline"]["training_group_ids"] == ["g0", "g1", "g2"]
    assert [p["outcome_group_id"] for p in channel["predictions"]] == ["g3", "g4"]
    assert channel["unit"] == "example_unit"
    assert channel["metrics"]["mae"] == 10
    assert channel["metrics"]["rmse"] == pytest.approx(math.sqrt(200))
    assert channel["metrics"]["scored_independent_groups"] == 2
    assert channel["empirical_training_interval"]["lower"] == 12
    assert channel["empirical_training_interval"]["upper"] == 28
    assert channel["empirical_training_interval"]["width"] == 16
    assert channel["metrics"]["heldout_interval_coverage"] == 0.5
    assert (
        channel["empirical_training_interval"]["status"]
        == "uncalibrated_empirical_range"
    )
    json.dumps(report, allow_nan=False)


def test_later_values_and_eligibility_do_not_change_training_or_split():
    records = five()
    first = run(records, holdout_fraction=0.4)
    records[-2]["value"] = 20000
    records[-1]["eligibility"] = "unknown"
    second = run(records, holdout_fraction=0.4)
    assert first["channels"][0]["baseline"] == second["channels"][0]["baseline"]
    assert (
        first["channels"][0]["empirical_training_interval"]
        == second["channels"][0]["empirical_training_interval"]
    )
    assert first["split_manifest"] == second["split_manifest"]
    assert first["normalized_input_sha256"] != second["normalized_input_sha256"]


def test_shared_outcomes_and_exact_reimports_cannot_inflate_independent_counts():
    records = five()
    shared = dict(records[0], episode_id="another_episode_with_same_outcome")
    records += [shared, deepcopy(records[1])]
    report = run(records, holdout_fraction=0.4)
    assert report["input_rows"] == 7
    assert report["duplicate_normalized_rows_ignored"] == 1
    assert report["unique_episode_count"] == 6
    assert report["independent_outcome_groups"] == 5
    assert report["channels"][0]["baseline"]["training_independent_groups"] == 3
    assert report["channels"][0]["baseline"]["value"] == 20


@pytest.mark.parametrize(
    "changes",
    [
        {"value": 99},
        {"unit": "other_unit"},
        {"eligibility": "unknown"},
        {"outcome_end": "2025-01-01T01:30:00Z"},
        {"outcome_available_at": "2025-01-01T03:00:00Z"},
    ],
)
def test_inconsistent_shared_outcomes_are_rejected(changes):
    records = five()
    records.append(dict(records[0], episode_id="shared_alias", **changes))
    with pytest.raises(ValueError, match="inconsistent|conflicting"):
        run(records, holdout_fraction=0.4)


def test_overlaps_with_unresolved_group_identity_are_rejected():
    records = [
        episode(
            0,
            10,
            outcome_end="2025-01-02T12:00:00Z",
            outcome_available_at="2025-01-02T13:00:00Z",
        ),
        episode(
            1,
            20,
            outcome_end="2025-01-02T14:00:00Z",
            outcome_available_at="2025-01-02T15:00:00Z",
        ),
        episode(3, 30),
    ]
    with pytest.raises(ValueError, match="Unresolved overlapping"):
        run(records, split_cutoff="2025-01-04T00:00:00Z")


def test_training_outcome_reaching_evaluation_is_purged():
    records = five()
    records[2]["outcome_end"] = "2025-01-04T01:00:00Z"
    records[2]["outcome_available_at"] = "2025-01-04T02:00:00Z"
    report = run(records, split_cutoff="2025-01-04T00:00:00Z")
    group = next(
        g for g in report["split_manifest"]["groups"] if g["outcome_group_id"] == "g2"
    )
    assert group["partition"] == "purged"
    assert group["purge_reason"] == "training_outcome_reaches_evaluation"
    assert report["channels"][0]["baseline"]["training_group_ids"] == ["g0", "g1"]
    assert report["channels"][0]["baseline"]["value"] == 15


def test_shared_group_spanning_explicit_split_is_purged_atomically():
    records = [
        episode(
            0,
            10,
            outcome_group_id="shared",
            outcome_end="2025-01-05T00:00:00Z",
            outcome_available_at="2025-01-05T01:00:00Z",
        ),
        episode(
            3,
            10,
            outcome_group_id="shared",
            outcome_end="2025-01-05T00:00:00Z",
            outcome_available_at="2025-01-05T01:00:00Z",
        ),
        episode(1, 20),
        episode(5, 30),
    ]
    report = run(records, split_cutoff="2025-01-04T00:00:00Z", min_training_groups=1)
    shared = next(
        g
        for g in report["split_manifest"]["groups"]
        if g["outcome_group_id"] == "shared"
    )
    assert shared["partition"] == "purged"
    assert shared["purge_reason"] == "shared_group_spans_split"
    assert shared["episode_ids"] == ["e0", "e3"]
    assert report["channels"][0]["baseline"]["training_group_ids"] == ["g1"]


def test_unknown_outcomes_are_unscored_and_do_not_become_negative_results():
    records = five()
    records[3]["value"] = None
    records[4]["eligibility"] = "unknown"
    report = run(records, holdout_fraction=0.4)
    channel = report["channels"][0]
    assert channel["metrics"]["mae"] is None
    assert channel["metrics"]["rmse"] is None
    assert channel["metrics"]["heldout_interval_coverage"] is None
    assert channel["metrics"]["scored_independent_groups"] == 0
    assert channel["predictions_issued"] == 2
    assert channel["prediction_abstentions"] == 0
    assert channel["evaluation_counts"] == {
        "scored": 0,
        "unobserved_outcome": 1,
        "unknown_eligibility": 1,
        "ineligible_outcome": 0,
        "prediction_abstained": 0,
    }
    assert [p["prediction"] for p in channel["predictions"]] == [20, 20]


def test_unknown_training_availability_excludes_training_values_in_strict_mode():
    records = five()
    for row in records:
        row.pop("outcome_available_at")
    report = run(records, holdout_fraction=0.4)
    channel = report["channels"][0]
    assert channel["baseline"]["value"] is None
    assert channel["baseline"]["training_independent_groups"] == 0
    assert channel["prediction_abstentions"] == 2
    assert {r["reason"] for r in channel["training_exclusions"]} == {
        "unknown_outcome_availability"
    }
    assert channel["assumed_training_availability_group_ids"] == []


def test_retrospective_availability_assumption_is_explicit_and_counted():
    records = five()
    for row in records:
        row.pop("outcome_available_at")
    report = run(
        records, holdout_fraction=0.4, training_availability_policy="assume_outcome_end"
    )
    channel = report["channels"][0]
    assert channel["baseline"]["value"] == 20
    assert channel["assumed_training_availability_group_ids"] == ["g0", "g1", "g2"]
    assert report["training_availability_policy"] == "assume_outcome_end"


def test_late_training_label_cannot_enter_fitted_baseline():
    records = five()
    records[2]["outcome_available_at"] = "2025-01-04T00:01:00Z"
    report = run(records, holdout_fraction=0.4)
    channel = report["channels"][0]
    assert channel["baseline"]["value"] == 15
    assert channel["training_exclusions"] == [
        {"outcome_group_id": "g2", "reason": "outcome_unavailable_before_fit_cutoff"}
    ]


@pytest.mark.parametrize("field", ["feature_cutoff", "feature_max_available_at"])
def test_declared_future_feature_information_is_rejected(field):
    records = five()
    records[0][field] = "2025-01-01T00:01:00Z"
    with pytest.raises(ValueError, match="exceeds"):
        run(records, holdout_fraction=0.4)


def test_historical_feature_bounds_are_checked_without_claiming_feature_use():
    records = five()
    for row in records:
        row["feature_cutoff"] = row["cutoff"]
        row["feature_max_available_at"] = row["cutoff"]
    report = run(records, holdout_fraction=0.4)
    assert report["feature_metadata_checks"] == {
        "feature_cutoff": 5,
        "feature_max_available_at": 5,
    }
    assert report["channels"][0]["baseline"]["features_used"] == []


def test_channels_are_evaluated_separately_without_mixing_hrv_metrics():
    records = []
    for day in range(5):
        records += [
            episode(day, 10 + day, channel="hrv_rmssd", unit="ms"),
            episode(day, 40 + day, channel="hrv_sdnn", unit="ms"),
        ]
    report = run(records, holdout_fraction=0.4)
    assert report["independent_outcome_groups"] == 5
    assert [(c["channel"], c["baseline"]["value"]) for c in report["channels"]] == [
        ("hrv_rmssd", 11),
        ("hrv_sdnn", 41),
    ]
    assert all(
        c["baseline"]["training_independent_groups"] == 3 for c in report["channels"]
    )


def test_same_channel_with_different_units_requires_explicit_normalization():
    records = five()
    records[3]["unit"] = "other_unit"
    with pytest.raises(ValueError, match="conflicting units"):
        run(records)


def test_single_training_group_cannot_create_a_false_interval():
    report = run(
        [episode(0, 10), episode(1, 20)], holdout_fraction=0.5, min_training_groups=1
    )
    channel = report["channels"][0]
    assert channel["baseline"]["value"] == 10
    assert channel["metrics"]["mae"] == 10
    assert channel["empirical_training_interval"]["lower"] is None
    assert channel["empirical_training_interval"]["width"] is None
    assert channel["metrics"]["heldout_interval_coverage"] is None


def test_default_minimum_training_and_empty_input_return_insufficient_data():
    report = run([episode(0, 10), episode(1, 20)], holdout_fraction=0.5)
    assert report["status"] == "insufficient_data"
    assert report["channels"][0]["prediction_abstentions"] == 1
    empty = run([])
    assert empty["status"] == "insufficient_data"
    assert empty["channels"] == []
    assert empty["split_manifest"]["cutoff"] is None
    json.dumps(empty, allow_nan=False)


def test_explicit_cutoff_and_fraction_cannot_both_control_split():
    with pytest.raises(ValueError, match="not both"):
        run(five(), split_cutoff="2025-01-04T00:00:00Z", holdout_fraction=0.4)


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), "10"])
def test_invalid_values_are_not_coerced_into_outcomes(value):
    records = five()
    records[0]["value"] = value
    with pytest.raises(ValueError, match="finite number"):
        run(records)


def test_outcome_before_cutoff_or_naive_timing_is_rejected():
    records = five()
    records[0]["outcome_end"] = records[0]["cutoff"]
    with pytest.raises(ValueError, match="must follow"):
        run(records)
    records = five()
    records[0]["cutoff"] = "2025-01-01T00:00:00"
    with pytest.raises(ValueError, match="unambiguous"):
        run(records)


def test_one_episode_cannot_leak_between_group_ids():
    records = five()
    records.append(
        dict(records[0], channel="another_channel", outcome_group_id="another_group")
    )
    with pytest.raises(ValueError, match="multiple unresolved"):
        run(records)


def test_one_episode_has_one_prediction_cutoff_across_channels():
    records = five()
    records.append(
        dict(records[0], channel="another_channel", cutoff="2025-01-01T00:30:00Z")
    )
    with pytest.raises(ValueError, match="inconsistent prediction"):
        run(records)
