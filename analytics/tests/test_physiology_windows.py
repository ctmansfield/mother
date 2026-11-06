"""Synthetic acceptance checks; no personal performance or live-service claims."""

import json

import numpy as np
import pandas as pd
import pytest

from analytics.events.window_builder import (
    build_windows,
    compute_features,
    label_events,
)


def config(**changes):
    return {
        "resample_minutes": 5,
        "horizon_minutes": [15],
        "hypo_threshold_mgdl": 70,
        "night_hours_only": False,
        "availability_policy": "assume_at_measurement",
        **changes,
    }


def samples(values, start="2025-01-01T00:00:00Z"):
    return pd.DataFrame(
        {"sgv": values}, index=pd.date_range(start, periods=len(values), freq="5min")
    )


def labels(values, **changes):
    frame = samples(values).rename(columns={"sgv": "glucose"})
    return label_events(frame, config(**changes))


def test_future_window_includes_endpoint_and_excludes_current_past_and_after_endpoint():
    out = labels([40, 100, 100, 60, 100, 100, 100, 100, 60, 100])
    target = out["y_night_hypo_15m"]
    assert target.iloc[0] == 1  # low exactly +15 minutes
    assert target.iloc[3] == 0  # current low excluded
    assert target.iloc[4] == 0  # old low excluded, later low outside H
    assert target.iloc[5] == 1  # low exactly at t+H
    assert pd.isna(target.iloc[-1])
    assert out["target_status_15m"].iloc[-1] == "incomplete_horizon"


def test_missing_bins_and_missing_horizon_are_not_negatives_even_with_observed_low():
    out = labels([100, 60, np.nan, 100, 100, 100, 100])
    assert pd.isna(out["y_night_hypo_15m"].iloc[0])
    assert out["target_status_15m"].iloc[0] == "missing_future_measurements"
    assert out["y_night_hypo_15m"].iloc[3] == 0
    assert out["y_night_hypo_15m"].iloc[-3:].isna().all()


def test_feature_imputation_does_not_fill_an_outcome():
    raw = samples([100, 100, np.nan, 100, 100, 100])
    features = compute_features(raw, None, config())
    assert features["glucose"].iloc[2] == 100
    assert features["glucose_is_imputed"].iloc[2]
    out = label_events(features, config())
    assert pd.isna(out["y_night_hypo_15m"].iloc[0])


def test_irregular_measured_minimum_is_not_averaged_away():
    ix = pd.date_range("2025-01-01T00:00Z", periods=5, freq="5min")
    feats = pd.DataFrame({"glucose": [100] * 5}, index=ix)
    observed = pd.Series(
        [100, 60, 140, 100, 100, 100],
        index=pd.to_datetime(
            [
                "2025-01-01T00:00Z",
                "2025-01-01T00:04Z",
                "2025-01-01T00:05Z",
                "2025-01-01T00:10Z",
                "2025-01-01T00:15Z",
                "2025-01-01T00:20Z",
            ]
        ),
    )
    out = label_events(feats, config(), observations=observed)
    assert out["y_night_hypo_15m"].iloc[0] == 1


@pytest.mark.parametrize(
    "timezone,start,hours,expected",
    [
        ("Pacific/Guam", "2025-01-01T12:00Z", [22, 8], True),
        ("Pacific/Guam", "2025-01-01T02:00Z", [22, 8], False),
        ("America/New_York", "2025-07-01T02:00Z", [22, 8], True),
        ("America/New_York", "2025-01-01T02:00Z", [22, 8], False),
        ("UTC", "2025-01-01T12:00Z", [9, 17], True),
        ("UTC", "2025-01-01T20:00Z", [9, 17], False),
    ],
)
def test_night_hours_use_declared_historical_zone_and_handle_nonwrapping_hours(
    timezone, start, hours, expected
):
    feats = samples([100] * 8, start).rename(columns={"sgv": "glucose"})
    out = label_events(
        feats, config(night_hours_only=True, timezone=timezone, night_hours=hours)
    )
    assert bool(pd.notna(out["y_night_hypo_15m"].iloc[0])) is expected
    if not expected:
        assert out["target_status_15m"].iloc[0] == "outside_analysis_hours"


def test_dst_repeated_hour_is_distinct_absolute_time():
    feats = samples([100] * 25, "2025-11-02T05:00Z").rename(columns={"sgv": "glucose"})
    out = label_events(
        feats,
        config(night_hours_only=True, timezone="America/New_York", night_hours=[1, 2]),
    )
    assert out.loc["2025-11-02T05:00Z", "y_night_hypo_15m"] == 0
    assert out.loc["2025-11-02T06:00Z", "y_night_hypo_15m"] == 0
    assert out.index.is_unique


def test_night_filter_without_timezone_fails_explicitly():
    with pytest.raises(ValueError, match="explicit historical"):
        labels([100] * 8, night_hours_only=True)


def test_nonmultiple_horizon_cannot_silently_shorten_target():
    with pytest.raises(ValueError, match="whole multiple"):
        labels([100] * 8, horizon_minutes=[7])


def test_irregular_cutoffs_cannot_silently_change_window_duration():
    feats = samples([100] * 8).rename(columns={"sgv": "glucose"})
    feats.index = feats.index + pd.Timedelta(minutes=1)
    with pytest.raises(ValueError, match="align"):
        label_events(feats, config())


def test_all_missing_measured_targets_stay_unknown():
    out = labels([np.nan] * 8)
    assert out["y_night_hypo_15m"].isna().all()


def test_right_closed_feature_bins_prevent_future_resampling_leak():
    ix = pd.to_datetime(["2025-01-01T00:00Z", "2025-01-01T00:01Z", "2025-01-01T00:05Z"])
    raw = pd.DataFrame({"sgv": [100, 50, 100]}, index=ix)
    out = compute_features(raw, None, config())
    assert out["glucose"].iloc[0] == 100
    assert out["glucose"].iloc[1] == 75


def test_strict_availability_never_infers_arrival_from_first_seen_or_ingestion():
    raw = samples([100] * 10)
    raw["source_available_at"] = None
    raw["first_observed_at"] = "2025-01-01T00:00Z"
    raw["ingested_at"] = "2025-01-01T00:00Z"
    out = compute_features(raw, None, config(availability_policy="strict"))
    assert out["glucose"].isna().all()
    stats = out.attrs["processing"]["source_diagnostics"]["cgm"]
    assert stats["unknown_availability"] == 10
    assert stats["assumed_availability"] == 0


def test_invalid_availability_does_not_fall_back_to_replay_assumption():
    raw = samples([100] * 10)
    raw["source_available_at"] = "invalid"
    out = compute_features(raw, None, config())
    assert out["glucose"].isna().all()
    assert (
        out.attrs["processing"]["source_diagnostics"]["cgm"]["invalid_availability"]
        == 10
    )


def test_later_revision_or_arrival_cannot_change_earlier_features():
    raw = samples([100, 40, 102, 103, 104, 105, 106, 107, 108])
    raw["source_available_at"] = raw.index
    raw.loc[raw.index[1], "source_available_at"] = raw.index[4]
    changed = raw.copy()
    changed.loc[changed.index[1], "sgv"] = 400
    before = compute_features(raw, None, config(availability_policy="strict"))
    after = compute_features(changed, None, config(availability_policy="strict"))
    pd.testing.assert_frame_equal(before.iloc[:4], after.iloc[:4])
    assert before["slope_15"].iloc[4] != after["slope_15"].iloc[4]


def test_missing_measurements_are_excluded_from_low_percentage_denominator():
    out = compute_features(samples([60, np.nan, np.nan, 100]), None, config())
    assert out["pct_time_below_70_2h"].iloc[2] == 100
    assert out["cgm_coverage_2h"].iloc[2] == pytest.approx(1 / 24)
    assert out["pct_time_below_70_2h"].iloc[3] == 50


@pytest.mark.parametrize("fields", [{"carbs": [20]}, {"event": ["Meal"]}])
def test_meal_age_uses_actual_occurrence_and_handles_sparse_columns(fields):
    raw = samples([100] * 10)
    meals = pd.DataFrame({"ts": ["2025-01-01T00:05Z"], **fields})
    out = compute_features(raw, meals, config())
    assert pd.isna(out["minutes_since_meal"].iloc[0])
    assert out["minutes_since_meal"].iloc[4] == 15


def test_late_annotation_uses_known_at_and_preserves_true_occurrence_time():
    raw = samples([100] * 10)
    meals = pd.DataFrame(
        {
            "ts": ["2025-01-01T00:01Z"],
            "carbs": [20],
            "source_available_at": ["2025-01-01T00:01Z"],
            "known_at": ["2025-01-01T00:20Z"],
        }
    )
    out = compute_features(raw, meals, config())
    assert out["minutes_since_meal"].iloc[:4].isna().all()
    assert out["minutes_since_meal"].iloc[4] == 19


def test_optional_channels_have_no_nearest_bin_leak_and_preserve_metric_types():
    raw = samples([100] * 20)
    times = ["2025-01-01T00:01Z", "2025-01-01T00:01Z"]
    hrv = pd.DataFrame(
        {
            "ts": times,
            "metric": ["rmssd", "sdnn"],
            "value": [40, 80],
            "unit": ["ms", "ms"],
            "method": ["vendor_a", "vendor_b"],
        }
    )
    intake = pd.DataFrame(
        {"ts": times[:1], "type": ["Na"], "amount": [10], "unit": ["mg"]}
    )
    meds = pd.DataFrame(
        {"ts": times[:1], "med": ["test_exposure"], "dose": [2], "unit": ["mg"]}
    )
    out = compute_features(
        raw,
        None,
        config(
            intake_units={"Na": "mg"},
            meds_decay={"test_exposure": {"half_life_h": 1, "unit": "mg"}},
        ),
        hrv=hrv,
        intake=intake,
        meds=meds,
    )
    assert pd.isna(out["na_intake_6h"].iloc[0])
    assert out["na_intake_6h"].iloc[1] == 10
    assert pd.isna(out["med_test_exposure_decay"].iloc[0])
    assert out["med_test_exposure_decay"].iloc[1] == pytest.approx(2 * 0.5 ** (4 / 60))
    assert pd.isna(out["rmssd_lag15"].iloc[3])
    assert out["rmssd_lag15"].iloc[4] == 40
    assert out["sdnn_lag15"].iloc[4] == 80


def test_future_optional_measurements_and_annotations_cannot_change_earlier_features():
    raw = samples([100] * 20)
    meals = pd.DataFrame(
        {"ts": ["2025-01-01T00:10Z"], "known_at": ["2025-01-01T00:40Z"], "carbs": [20]}
    )
    hrv = pd.DataFrame(
        {
            "ts": ["2025-01-01T00:10Z"],
            "source_available_at": ["2025-01-01T00:40Z"],
            "rmssd": [40],
        }
    )
    first = compute_features(raw, meals, config(), hrv=hrv)
    hrv["rmssd"] = 400
    meals["ts"] = "2025-01-01T00:20Z"
    second = compute_features(raw, meals, config(), hrv=hrv)
    pd.testing.assert_frame_equal(first.iloc[:8], second.iloc[:8])


def test_hrv_sources_or_methods_are_not_silently_pooled():
    raw = samples([100] * 20)
    hrv = pd.DataFrame(
        {
            "ts": ["2025-01-01T00:05Z", "2025-01-01T00:10Z"],
            "rmssd": [40, 80],
            "method": ["a", "b"],
        }
    )
    with pytest.raises(ValueError, match="homogeneous"):
        compute_features(raw, None, config(), hrv=hrv)


def test_hrv_prior_history_keeps_its_time_and_supports_actual_lags():
    raw = samples([100] * 20)
    hrv = pd.DataFrame(
        {
            "ts": ["2024-12-30T00:00Z", "2024-12-31T23:45Z"],
            "rmssd": [999, 40],
        }
    )
    out = compute_features(raw, None, config(), hrv=hrv)
    assert out["rmssd_lag15"].iloc[0] == 40
    assert pd.isna(out["rmssd_lag15"].iloc[6])


def test_zero_recorded_intake_is_distinct_from_no_known_record():
    raw = samples([100] * 20)
    intake = pd.DataFrame(
        {"ts": ["2025-01-01T00:05Z"], "type": ["Na"], "amount": [0], "unit": ["mg"]}
    )
    out = compute_features(raw, None, config(intake_units={"Na": "mg"}), intake=intake)
    assert pd.isna(out["na_intake_6h"].iloc[0])
    assert out["na_intake_6h"].iloc[1] == 0


def test_intake_unit_mismatch_is_counted_and_not_summed():
    raw = samples([100] * 20)
    intake = pd.DataFrame(
        {"ts": ["2025-01-01T00:05Z"], "type": ["Na"], "amount": [10], "unit": ["mEq"]}
    )
    out = compute_features(raw, None, config(intake_units={"Na": "mg"}), intake=intake)
    assert out["na_intake_6h"].isna().all()
    assert (
        out.attrs["processing"]["source_diagnostics"]["intake"]["unit_checks"]["Na"][
            "mismatched_source_unit"
        ]
        == 1
    )


def test_undeclared_intake_or_dose_units_remain_unknown():
    raw = samples([100] * 20)
    intake = pd.DataFrame({"ts": ["2025-01-01T00:05Z"], "type": ["Na"], "amount": [10]})
    meds = pd.DataFrame({"ts": ["2025-01-01T00:05Z"], "med": ["test"], "dose": [2]})
    out = compute_features(
        raw,
        None,
        config(meds_decay={"test": {"half_life_h": 1}}),
        intake=intake,
        meds=meds,
    )
    assert out["na_intake_6h"].isna().all()
    assert out["med_test_decay"].isna().all()


def test_cgm_unconverted_units_are_rejected():
    raw = samples([5.5] * 10)
    raw["unit"] = "mmol/L"
    with pytest.raises(ValueError, match="mg/dL"):
        compute_features(raw, None, config())


def test_build_windows_emits_auditable_metadata_and_nullable_targets(tmp_path):
    raw = samples([100] * 25)
    source = tmp_path / "cgm.parquet"
    raw.rename_axis("ts").reset_index().to_parquet(source, index=False)
    cfg = tmp_path / "pipeline.yaml"
    cfg.write_text(
        "resample_minutes: 5\nhorizon_minutes: [15]\nnight_hours_only: false\n"
        "availability_policy: assume_at_measurement\ntimezone: UTC\n"
        "timezone_basis: engineering_fallback_not_verified_personal_history\n"
    )
    output = tmp_path / "windows.parquet"
    result = build_windows(str(source), None, str(output), str(cfg))
    values = pd.read_parquet(output)
    meta = json.loads((tmp_path / "windows.parquet.metadata.json").read_text())
    assert result["rows"] == len(values) > 0
    assert values["y_night_hypo_15m"].iloc[-3:].isna().all()
    assert meta["processing"]["source_diagnostics"]["cgm"]["assumed_availability"] == 25
    assert (
        meta["processing"]["timezone_basis"]
        == "engineering_fallback_not_verified_personal_history"
    )
    assert len(meta["inputs"]["cgm"]["sha256"]) == 64
