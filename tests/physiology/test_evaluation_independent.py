"""Independent E01 timing/grouping checks using hand-calculated synthetic cases."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from mother.physiology.evaluation import evaluate_baseline


ZERO = datetime(2026, 1, 1, tzinfo=timezone.utc)


def row(
    name,
    hours,
    value,
    *,
    group=None,
    end_hours=None,
    available_hours=None,
    channel="fixture.scalar",
):
    end_hours = hours + 1 if end_hours is None else end_hours
    available_hours = end_hours + 1 if available_hours is None else available_hours
    return {
        "episode_id": name,
        "outcome_group_id": group or name,
        "cutoff": (ZERO + timedelta(hours=hours)).isoformat(),
        "outcome_end": (ZERO + timedelta(hours=end_hours)).isoformat(),
        "outcome_available_at": (ZERO + timedelta(hours=available_hours)).isoformat(),
        "channel": channel,
        "unit": "fixture-unit",
        "value": value,
        "eligibility": "eligible",
    }


def run(records, split_hours):
    return evaluate_baseline(
        records,
        data_version="independent-synthetic/1",
        processing_version="caller-defined-scalar/1",
        split_cutoff=ZERO + timedelta(hours=split_hours),
    )


def test_e01_different_exercise_cutoffs_sharing_one_outcome_count_once():
    records = [
        row("exercise-a", 1, 30, group="same-night", end_hours=24, available_hours=25),
        row("exercise-b", 7, 30, group="same-night", end_hours=24, available_hours=25),
        row("exercise-c", 12, 30, group="same-night", end_hours=24, available_hours=25),
        row("second-night", 48, 50, end_hours=72, available_hours=73),
        row("heldout-a", 96, 40, end_hours=120, available_hours=121),
        row("heldout-b", 144, 80, end_hours=168, available_hours=169),
    ]
    report = run(records, 96)
    channel = report["channels"][0]
    assert report["unique_episode_count"] == 6
    assert report["independent_outcome_groups"] == 4
    assert channel["baseline"]["training_independent_groups"] == 2
    assert (
        channel["baseline"]["value"] == 40
    )  # median of two nights, not four exercise rows
    assert channel["metrics"]["mae"] == 20
    shared = next(
        g
        for g in report["split_manifest"]["groups"]
        if g["outcome_group_id"] == "same-night"
    )
    assert shared["episode_ids"] == ["exercise-a", "exercise-b", "exercise-c"]


def test_e01_label_becoming_available_exactly_at_fit_boundary_is_excluded():
    records = [
        row("train-a", 0, 10),
        row("train-b", 24, 20),
        row("boundary-label", 48, 1000, available_hours=72),
        row("heldout", 72, 15),
    ]
    channel = run(records, 72)["channels"][0]
    assert channel["baseline"]["value"] == 15
    assert channel["baseline"]["training_group_ids"] == ["train-a", "train-b"]
    assert channel["training_exclusions"] == [
        {
            "outcome_group_id": "boundary-label",
            "reason": "outcome_unavailable_before_fit_cutoff",
        }
    ]


def test_e01_group_purge_is_atomic_when_one_channel_reaches_the_boundary():
    records = []
    for name, hours, value_a, value_b in [
        ("train-a", 0, 10, 30),
        ("train-b", 24, 20, 50),
        ("heldout", 72, 15, 40),
    ]:
        records.extend(
            [
                row(name, hours, value_a, channel="channel-a"),
                row(name, hours, value_b, channel="channel-b"),
            ]
        )
    records.extend(
        [
            row("cross-channel-group", 48, 1000, channel="channel-a"),
            row(
                "cross-channel-group",
                48,
                2000,
                channel="channel-b",
                end_hours=72,
                available_hours=73,
            ),
        ]
    )
    report = run(records, 72)
    group = next(
        g
        for g in report["split_manifest"]["groups"]
        if g["outcome_group_id"] == "cross-channel-group"
    )
    assert group["partition"] == "purged"
    assert group["purge_reason"] == "training_outcome_reaches_evaluation"
    assert {c["channel"]: c["baseline"]["value"] for c in report["channels"]} == {
        "channel-a": 15,
        "channel-b": 40,
    }
    changed = deepcopy(records)
    for record in changed:
        if record["episode_id"] == "heldout":
            record["value"] = -999
    changed_report = run(changed, 72)
    assert changed_report["split_manifest"] == report["split_manifest"]
    assert [c["baseline"] for c in changed_report["channels"]] == [
        c["baseline"] for c in report["channels"]
    ]


def test_e01_zero_is_observed_but_null_never_enters_the_error_denominator():
    records = [
        row("train-a", 0, -2),
        row("train-b", 24, 0),
        row("train-c", 48, 2),
        row("unobserved", 72, None),
        row("observed-zero", 96, 0),
    ]
    channel = run(records, 72)["channels"][0]
    assert channel["baseline"]["value"] == 0
    assert channel["metrics"]["mae"] == 0
    assert channel["metrics"]["scored_independent_groups"] == 1
    assert channel["metrics"]["interval_scored_independent_groups"] == 1
    assert channel["metrics"]["heldout_interval_coverage"] == 1
    assert channel["evaluation_counts"]["unobserved_outcome"] == 1
    assert channel["predictions"][0]["observed"] is None
    assert (
        channel["empirical_training_interval"]["status"]
        == "uncalibrated_empirical_range"
    )


def test_e01_unresolved_overlap_in_heldout_groups_cannot_inflate_evaluation():
    records = [
        row("train-a", 0, 10),
        row("train-b", 24, 20),
        row("heldout-a", 72, 15, end_hours=76),
        row("heldout-b", 74, 15, end_hours=78),
    ]
    with pytest.raises(ValueError, match="Unresolved overlapping"):
        run(records, 72)
