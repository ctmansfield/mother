"""Chronological, group-aware evaluation of a context-free scalar baseline.

The caller supplies the physiological endpoint, unit, episode boundaries and
eligibility. This module does not define recovery, infer clinical states, or
establish that a dataset is representative. It consumes no episode features.

Required fields per record:
  episode_id, outcome_group_id, cutoff, outcome_end, channel, unit,
  value (finite number or null), eligibility (eligible/ineligible/unknown).

Shared outcomes must use the same group. Repeated group/channel records must
agree on the outcome and its availability. Distinct retained groups with
overlapping target intervals require upstream reconciliation.

Optional outcome_available_at is necessary for strict training availability.
The explicit assume_outcome_end policy permits retrospective exploration while
recording that assumption. Optional feature_cutoff/feature_max_available_at
must not exceed the declared prediction cutoff, even though this baseline
does not use those features.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import math
from numbers import Real
from statistics import median

from . import CONTRACT_VERSION
from .contracts import content_hash
from .time import parse_timestamp, utc_iso

EVALUATION_VERSION = "scalar-baseline-evaluation/1.0.0"
BASELINE_VERSION = "training-median/1.0.0"
ELIGIBILITY = {"eligible", "ineligible", "unknown"}


def _name(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value


def _time(value, field):
    try:
        return parse_timestamp(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"{field} must be an unambiguous timestamp") from exc


def _normalize(records):
    normalized, duplicates = [], 0
    by_episode_channel, episode_groups, episode_cutoffs, units = {}, {}, {}, {}
    required = {
        "episode_id",
        "outcome_group_id",
        "cutoff",
        "outcome_end",
        "channel",
        "unit",
        "value",
        "eligibility",
    }
    feature_checks = Counter()
    for position, item in enumerate(records):
        if not isinstance(item, dict) or not required.issubset(item):
            raise ValueError(f"Episode row {position} is missing required fields")
        row = {
            field: _name(item[field], field)
            for field in (
                "episode_id",
                "outcome_group_id",
                "channel",
                "unit",
                "eligibility",
            )
        }
        if row["eligibility"] not in ELIGIBILITY:
            raise ValueError("eligibility must be eligible, ineligible, or unknown")
        row["cutoff"] = _time(item["cutoff"], "cutoff")
        row["outcome_end"] = _time(item["outcome_end"], "outcome_end")
        if row["outcome_end"] <= row["cutoff"]:
            raise ValueError("outcome_end must follow the prediction cutoff")
        row["outcome_available_at"] = None
        if item.get("outcome_available_at") is not None:
            row["outcome_available_at"] = _time(
                item["outcome_available_at"], "outcome_available_at"
            )
            if row["outcome_available_at"] < row["outcome_end"]:
                raise ValueError("outcome_available_at cannot precede outcome_end")
        for field in ("feature_cutoff", "feature_max_available_at"):
            row[field] = None
            if item.get(field) is not None:
                row[field] = _time(item[field], field)
                if row[field] > row["cutoff"]:
                    raise ValueError(f"{field} exceeds the prediction cutoff")
                feature_checks[field] += 1
        value = item["value"]
        if value is not None:
            if (
                isinstance(value, bool)
                or not isinstance(value, Real)
                or not math.isfinite(value)
            ):
                raise ValueError("value must be a finite number or null")
            value = float(value)
        row["value"] = value
        prior_group = episode_groups.setdefault(
            row["episode_id"], row["outcome_group_id"]
        )
        if prior_group != row["outcome_group_id"]:
            raise ValueError(
                "One episode cannot belong to multiple unresolved outcome groups"
            )
        prior_cutoff = episode_cutoffs.setdefault(row["episode_id"], row["cutoff"])
        if prior_cutoff != row["cutoff"]:
            raise ValueError("One episode has inconsistent prediction cutoffs")
        prior_unit = units.setdefault(row["channel"], row["unit"])
        if prior_unit != row["unit"]:
            raise ValueError(
                "A channel has conflicting units; normalize explicitly before evaluation"
            )
        key = (row["episode_id"], row["channel"])
        if key in by_episode_channel:
            if by_episode_channel[key] != row:
                raise ValueError("Repeated episode/channel records are inconsistent")
            duplicates += 1
            continue
        by_episode_channel[key] = row
        normalized.append(row)
    normalized.sort(
        key=lambda row: (
            row["cutoff"],
            row["outcome_group_id"],
            row["channel"],
            row["episode_id"],
        )
    )
    return normalized, duplicates, dict(feature_checks)


def _groups(records):
    groups = {}
    for row in records:
        gid = row["outcome_group_id"]
        group = groups.setdefault(
            gid,
            {
                "group_id": gid,
                "episode_ids": set(),
                "cutoffs": [],
                "outcome_end": row["outcome_end"],
                "channels": {},
            },
        )
        group["episode_ids"].add(row["episode_id"])
        group["cutoffs"].append(row["cutoff"])
        group["outcome_end"] = max(group["outcome_end"], row["outcome_end"])
        channel = row["channel"]
        target = {
            field: row[field]
            for field in (
                "channel",
                "unit",
                "value",
                "eligibility",
                "outcome_end",
                "outcome_available_at",
            )
        }
        if channel in group["channels"] and group["channels"][channel] != target:
            raise ValueError(
                f"Shared outcome group has inconsistent {channel} outcomes"
            )
        group["channels"][channel] = target
    for group in groups.values():
        cutoffs = group.pop("cutoffs")
        group["first_cutoff"] = min(cutoffs)
        group["last_cutoff"] = max(cutoffs)
        group["episode_ids"] = sorted(group["episode_ids"])
    return sorted(groups.values(), key=lambda g: (g["first_cutoff"], g["group_id"]))


def _quantile(values, probability):
    ordered = sorted(values)
    location = (len(ordered) - 1) * probability
    low, high = math.floor(location), math.ceil(location)
    return ordered[low] + (ordered[high] - ordered[low]) * (location - low)


def _serial(value):
    if isinstance(value, datetime):
        return utc_iso(value)
    if isinstance(value, dict):
        return {key: _serial(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_serial(item) for item in value]
    return value


def _validate_retained_overlap(groups):
    """A shared outcome may overlap internally; distinct groups may not."""
    intervals = defaultdict(list)
    for group in groups:
        if group["partition"] not in {"train", "heldout"}:
            continue
        for channel, target in group["channels"].items():
            intervals[channel].append(
                (group["first_cutoff"], target["outcome_end"], group["group_id"])
            )
    for channel, entries in intervals.items():
        entries.sort()
        latest_end, latest_group = None, None
        for start, end, gid in entries:
            if latest_end is not None and start < latest_end:
                raise ValueError(
                    f"Unresolved overlapping {channel} outcomes in groups {latest_group} and {gid}; reconcile shared groups"
                )
            if latest_end is None or end > latest_end:
                latest_end, latest_group = end, gid


def evaluate_baseline(
    episodes,
    *,
    data_version: str,
    processing_version: str,
    split_cutoff=None,
    holdout_fraction: float | None = None,
    interval_mass: float = 0.8,
    min_training_groups: int = 2,
    training_availability_policy: str = "strict",
) -> dict:
    """Evaluate one frozen training median per declared channel on later groups.

    Supply an explicit split_cutoff OR holdout_fraction (default 0.25). Fractional
    splitting uses ordered group cutoff times only, never values or eligibility.
    Entire groups spanning the partition or whose training labels reach the
    boundary are purged. No future outcomes are converted to negative examples.
    """
    _name(data_version, "data_version")
    _name(processing_version, "processing_version")
    if split_cutoff is not None and holdout_fraction is not None:
        raise ValueError("Choose split_cutoff or holdout_fraction, not both")
    if training_availability_policy not in {"strict", "assume_outcome_end"}:
        raise ValueError(
            "training_availability_policy must be strict or assume_outcome_end"
        )
    if (
        isinstance(min_training_groups, bool)
        or not isinstance(min_training_groups, int)
        or min_training_groups < 1
    ):
        raise ValueError("min_training_groups must be a positive integer")
    if (
        isinstance(interval_mass, bool)
        or not isinstance(interval_mass, Real)
        or not 0 < interval_mass < 1
    ):
        raise ValueError("interval_mass must be between zero and one")
    if holdout_fraction is None and split_cutoff is None:
        holdout_fraction = 0.25
    if holdout_fraction is not None and (
        isinstance(holdout_fraction, bool)
        or not isinstance(holdout_fraction, Real)
        or not 0 < holdout_fraction < 1
    ):
        raise ValueError("holdout_fraction must be between zero and one")

    items = list(episodes)
    records, duplicate_rows, feature_checks = _normalize(items)
    groups = _groups(records)
    if split_cutoff is not None:
        boundary = _time(split_cutoff, "split_cutoff")
    elif groups:
        test_count = max(1, math.ceil(len(groups) * holdout_fraction))
        boundary = groups[len(groups) - test_count]["first_cutoff"]
    else:
        boundary = None
    for group in groups:
        group["purge_reason"] = None
        if group["first_cutoff"] >= boundary:
            group["partition"] = "heldout"
        elif group["last_cutoff"] >= boundary:
            group["partition"] = "purged"
            group["purge_reason"] = "shared_group_spans_split"
        elif group["outcome_end"] >= boundary:
            group["partition"] = "purged"
            group["purge_reason"] = "training_outcome_reaches_evaluation"
        else:
            group["partition"] = "train"
    _validate_retained_overlap(groups)
    split_groups = [
        {
            "outcome_group_id": group["group_id"],
            "episode_ids": group["episode_ids"],
            "first_cutoff": group["first_cutoff"],
            "last_cutoff": group["last_cutoff"],
            "outcome_end": group["outcome_end"],
            "partition": group["partition"],
            "purge_reason": group["purge_reason"],
            "channels": sorted(group["channels"]),
        }
        for group in groups
    ]
    manifest = _serial(
        {
            "method": "chronological_group_cutoff",
            "cutoff": boundary,
            "requested_holdout_fraction": holdout_fraction,
            "groups": split_groups,
            "training_labels_end_before_cutoff": True,
            "shared_group_policy": "atomic assignment; one independent outcome per channel/group",
        }
    )
    manifest["manifest_id"] = "split:" + content_hash(manifest)

    channels = sorted({row["channel"] for row in records})
    channel_reports = []
    for channel in channels:
        rows = [
            (group, group["channels"][channel])
            for group in groups
            if channel in group["channels"]
        ]
        unit = rows[0][1]["unit"]
        training, exclusions, assumed = [], [], []
        for group, target in rows:
            if group["partition"] != "train":
                continue
            reason = None
            if target["eligibility"] != "eligible":
                reason = (
                    "ineligible_outcome"
                    if target["eligibility"] == "ineligible"
                    else "unknown_eligibility"
                )
            elif target["value"] is None:
                reason = "unobserved_outcome"
            else:
                available = target["outcome_available_at"]
                if available is None:
                    if training_availability_policy == "assume_outcome_end":
                        available = target["outcome_end"]
                        assumed.append(group["group_id"])
                    else:
                        reason = "unknown_outcome_availability"
                if available is not None and available >= boundary:
                    reason = "outcome_unavailable_before_fit_cutoff"
            if reason is None:
                training.append((group, target))
            else:
                exclusions.append(
                    {"outcome_group_id": group["group_id"], "reason": reason}
                )
        train_values = [target["value"] for _, target in training]
        baseline = (
            float(median(train_values))
            if len(train_values) >= min_training_groups
            else None
        )
        low, high = None, None
        if baseline is not None and len(train_values) >= 2:
            tail = (1 - interval_mass) / 2
            low, high = _quantile(train_values, tail), _quantile(train_values, 1 - tail)
        predictions, errors, interval_hits = [], [], []
        evaluation_counts = Counter()
        for group, target in rows:
            if group["partition"] != "heldout":
                continue
            if target["eligibility"] != "eligible":
                status = (
                    "ineligible_outcome"
                    if target["eligibility"] == "ineligible"
                    else "unknown_eligibility"
                )
            elif target["value"] is None:
                status = "unobserved_outcome"
            elif baseline is None:
                status = "prediction_abstained"
            else:
                status = "scored"
            evaluation_counts[status] += 1
            predicted = baseline is not None
            if status == "scored":
                errors.append(baseline - target["value"])
                if low is not None:
                    interval_hits.append(low <= target["value"] <= high)
            predictions.append(
                _serial(
                    {
                        "outcome_group_id": group["group_id"],
                        "episode_ids": group["episode_ids"],
                        "cutoff": group["first_cutoff"],
                        "outcome_end": target["outcome_end"],
                        "prediction": baseline,
                        "prediction_status": "predicted" if predicted else "abstained",
                        "abstention_reason": (
                            None if predicted else "insufficient_training_groups"
                        ),
                        "observed": target["value"],
                        "eligibility": target["eligibility"],
                        "evaluation_status": status,
                    }
                )
            )
        metrics = {
            "scored_independent_groups": len(errors),
            "mae": (
                sum(abs(error) for error in errors) / len(errors) if errors else None
            ),
            "rmse": (
                math.sqrt(sum(error**2 for error in errors) / len(errors))
                if errors
                else None
            ),
            "heldout_interval_coverage": (
                sum(interval_hits) / len(interval_hits) if interval_hits else None
            ),
            "interval_scored_independent_groups": len(interval_hits),
        }
        channel_reports.append(
            {
                "channel": channel,
                "unit": unit,
                "status": "evaluated" if errors else "insufficient_scored_heldout_data",
                "baseline": {
                    "version": BASELINE_VERSION,
                    "value": baseline,
                    "status": (
                        "fitted"
                        if baseline is not None
                        else "insufficient_training_groups"
                    ),
                    "training_independent_groups": len(training),
                    "training_group_ids": [group["group_id"] for group, _ in training],
                    "training_eligibility": "eligible finite observed targets only",
                    "minimum_training_groups": min_training_groups,
                    "features_used": [],
                },
                "empirical_training_interval": {
                    "central_mass": interval_mass,
                    "lower": low,
                    "upper": high,
                    "width": high - low if low is not None else None,
                    "method": "linear empirical training quantiles",
                    "status": (
                        "uncalibrated_empirical_range"
                        if low is not None
                        else "insufficient_training_groups"
                    ),
                },
                "metrics": metrics,
                "heldout_independent_groups": len(predictions),
                "predictions_issued": sum(
                    pred["prediction_status"] == "predicted" for pred in predictions
                ),
                "prediction_abstentions": sum(
                    pred["prediction_status"] == "abstained" for pred in predictions
                ),
                "evaluation_counts": {
                    name: evaluation_counts[name]
                    for name in (
                        "scored",
                        "unobserved_outcome",
                        "ineligible_outcome",
                        "unknown_eligibility",
                        "prediction_abstained",
                    )
                },
                "training_exclusions": exclusions,
                "assumed_training_availability_group_ids": assumed,
                "predictions": predictions,
            }
        )
    partitions = Counter(group["partition"] for group in groups)
    report = {
        "evaluation_version": EVALUATION_VERSION,
        "contract_version": CONTRACT_VERSION,
        "data_version": data_version,
        "processing_version": processing_version,
        "normalized_input_sha256": content_hash(_serial(records)),
        "input_hash_scope": "canonical normalized episode records, not original artifact bytes",
        "evidence_scope": "provided scalar episode records; representativeness and endpoint validity not assessed",
        "status": (
            "evaluated"
            if any(
                report["metrics"]["scored_independent_groups"]
                for report in channel_reports
            )
            else "insufficient_data"
        ),
        "input_rows": len(items),
        "duplicate_normalized_rows_ignored": duplicate_rows,
        "unique_episode_count": len({row["episode_id"] for row in records}),
        "independent_outcome_groups": len(groups),
        "partition_counts": {
            name: partitions[name] for name in ("train", "heldout", "purged")
        },
        "training_availability_policy": training_availability_policy,
        "feature_metadata_checks": feature_checks,
        "split_manifest": manifest,
        "channels": channel_reports,
        "interpretation": "Baseline forecasting evaluation only; no causal, intervention, recovery, or clinical claim.",
    }
    report["report_id"] = "evaluation:" + content_hash(report)
    return report
