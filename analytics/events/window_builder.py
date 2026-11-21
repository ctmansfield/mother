"""Causal analytics views and explicitly eligible future glucose targets.

These are glucose-event targets, not physiological recovery labels. Features
use records known by each cutoff. Targets use measured samples, never feature
forward fills. Unknown availability requires an explicit replay assumption.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
import pandas as pd
import yaml

from mother.physiology.time import parse_timestamp

CFG_PATH = str(Path(__file__).resolve().parents[1] / "config" / "pipeline.yaml")
PROCESSING_VERSION = "physiology-windows/1.0.0"
AVAILABILITY_FIELDS = ("source_available_at", "known_at", "recorded_at")


def load_cfg(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r") as handle:
        return yaml.safe_load(handle) or {}


def _step(cfg: Dict[str, Any]) -> int:
    value = cfg.get("resample_minutes", 5)
    if isinstance(value, bool) or int(value) != value or int(value) <= 0:
        raise ValueError("resample_minutes must be a positive integer")
    return int(value)


def _times(values, cfg: Dict[str, Any]) -> pd.DatetimeIndex:
    parsed = []
    for value in values:
        try:
            parsed.append(
                parse_timestamp(value, naive_timezone=cfg.get("source_timezone"))
            )
        except (ValueError, TypeError, OverflowError):
            parsed.append(pd.NaT)
    return pd.DatetimeIndex(parsed, tz="UTC")


def _is_missing(value: Any) -> bool:
    return (
        value is None
        or (isinstance(value, str) and not value.strip())
        or bool(pd.isna(value))
    )


def _prepare(frame, cfg, diagnostics, name, value_col=None, index_time=False):
    """Parse each row and retain an explicit conservative knowledge bound.

    Multiple supplied availability/annotation times use the latest. Invalid
    supplied times never fall back to occurrence or ingestion time.
    """
    policy = cfg.get("availability_policy", "strict")
    if policy not in {"strict", "assume_at_measurement"}:
        raise ValueError("availability_policy must be strict or assume_at_measurement")
    data = frame.copy().reset_index(drop=True)
    data["_time"] = _times(frame.index if index_time else frame["ts"], cfg)
    stats = {
        "input_rows": len(data),
        "invalid_timestamps": int(data["_time"].isna().sum()),
        "unknown_availability": 0,
        "assumed_availability": 0,
        "invalid_availability": 0,
        "invalid_values": 0,
    }
    available = []
    for _, row in data.iterrows():
        known = []
        invalid = False
        for field in AVAILABILITY_FIELDS:
            if field not in row or _is_missing(row[field]):
                continue
            try:
                known.append(
                    parse_timestamp(
                        row[field], naive_timezone=cfg.get("source_timezone")
                    )
                )
            except (ValueError, TypeError, OverflowError):
                invalid = True
        if invalid:
            stats["invalid_availability"] += 1
            available.append(pd.NaT)
        elif known:
            available.append(max(known))
        else:
            stats["unknown_availability"] += 1
            if policy == "assume_at_measurement" and pd.notna(row["_time"]):
                stats["assumed_availability"] += 1
                available.append(row["_time"])
            else:
                available.append(pd.NaT)
    data["_available"] = pd.DatetimeIndex(available, tz="UTC")
    if value_col is not None:
        data["_value"] = pd.to_numeric(data[value_col], errors="coerce")
        valid = np.isfinite(data["_value"])
        stats["invalid_values"] = int((~valid).sum())
        data = data.loc[valid]
    diagnostics[name] = stats
    return data.loc[data["_time"].notna()].copy()


def _asof_buckets(data: pd.DataFrame, index: pd.DatetimeIndex, step: int):
    """Yield measurement buckets as known at each cutoff, without retroactivity."""
    total = np.zeros(len(index), dtype=float)
    count = np.zeros(len(index), dtype=np.int64)
    mean = np.full(len(index), np.nan)
    arrivals = []
    for _, row in data.loc[data["_available"].notna()].iterrows():
        # Older history cannot be relabeled as a sample in the first bucket.
        if row["_time"] <= index[0] - pd.Timedelta(minutes=step):
            continue
        bucket = int(index.searchsorted(row["_time"], side="left"))
        arrival = int(
            index.searchsorted(max(row["_time"], row["_available"]), side="left")
        )
        if bucket < len(index) and arrival < len(index):
            arrivals.append((arrival, bucket, float(row["_value"])))
    arrivals.sort()
    cursor = 0
    for i in range(len(index)):
        while cursor < len(arrivals) and arrivals[cursor][0] <= i:
            _, bucket, value = arrivals[cursor]
            total[bucket] += value
            count[bucket] += 1
            mean[bucket] = total[bucket] / count[bucket]
            cursor += 1
        # Arrays are reused in place and must be consumed immediately.
        yield i, mean, count


def _filled_at(values: np.ndarray, position: int, limit: int) -> float:
    if position < 0:
        return np.nan
    for i in range(position, max(-1, position - limit - 1), -1):
        if np.isfinite(values[i]):
            return float(values[i])
    return np.nan


def _measured_glucose(df: pd.DataFrame) -> pd.Series:
    values = pd.to_numeric(df["sgv"], errors="coerce").where(lambda x: np.isfinite(x))
    if "value_kind" in df:
        values = values.where(df["value_kind"].isin(["measured", "vendor_derived"]))
    if "is_imputed" in df:
        values = values.where(~df["is_imputed"].fillna(False).astype(bool))
    return pd.Series(values.to_numpy(), index=df.index, name="measured_glucose")


def compute_features(
    df: pd.DataFrame,
    treatments: Optional[pd.DataFrame],
    cfg: Dict[str, Any],
    hrv: Optional[pd.DataFrame] = None,
    intake: Optional[pd.DataFrame] = None,
    meds: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    step = _step(cfg)
    if any(minutes % step for minutes in (10, 15, 30, 60, 120, 240, 1440)):
        raise ValueError(
            "resample_minutes must divide all declared feature lags/windows"
        )
    diagnostics = {}
    cgm = _prepare(df, cfg, diagnostics, "cgm", "sgv", index_time=True)
    if cgm.empty:
        raise ValueError("CGM has no valid timestamps and numeric values")
    if "unit" in cgm and not cgm["unit"].dropna().eq("mg/dL").all():
        raise ValueError(
            "CGM analytics requires normalized mg/dL; normalize units at import"
        )
    if "value_kind" in cgm:
        cgm = cgm.loc[cgm["value_kind"].isin(["measured", "vendor_derived"])]
    if "is_imputed" in cgm:
        cgm = cgm.loc[~cgm["is_imputed"].fillna(False).astype(bool)]
    if cgm.empty:
        raise ValueError("CGM has no measured observations")
    freq = f"{step}min"
    index = pd.date_range(
        cgm["_time"].min().floor(freq), cgm["_time"].max().ceil(freq), freq=freq
    )
    out = pd.DataFrame(index=index)
    columns = [
        "glucose",
        "cgm_delta_10",
        "cgm_delta_30",
        "slope_15",
        "pct_time_below_70_2h",
        "pct_time_below_70_4h",
        "cgm_coverage_2h",
        "cgm_coverage_4h",
    ]
    features = np.full((len(index), len(columns)), np.nan)
    imputed = np.zeros(len(index), dtype=bool)
    fill_minutes = cfg.get("feature_ffill_minutes", 15)
    if (
        isinstance(fill_minutes, bool)
        or int(fill_minutes) != fill_minutes
        or fill_minutes < 0
        or fill_minutes % step
    ):
        raise ValueError(
            "feature_ffill_minutes must be a nonnegative whole multiple of the step"
        )
    fill_limit = int(fill_minutes) // step
    for i, values, count in _asof_buckets(cgm, index, step):
        current = _filled_at(values, i, fill_limit)
        features[i, :4] = [
            current,
            current - _filled_at(values, i - 10 // step, fill_limit),
            current - _filled_at(values, i - 30 // step, fill_limit),
            (current - _filled_at(values, i - 15 // step, fill_limit)) / 15.0,
        ]
        imputed[i] = np.isfinite(current) and count[i] == 0
        for j, hours in enumerate((2, 4)):
            width = hours * 60 // step
            window = values[max(0, i - width + 1) : i + 1]
            valid = np.isfinite(window)
            features[i, 6 + j] = valid.sum() / width
            if valid.any():
                features[i, 4 + j] = 100.0 * np.mean(window[valid] < 70)
    out[columns] = features
    out["glucose_is_imputed"] = imputed
    out["minutes_since_meal"] = np.nan

    if treatments is not None and not treatments.empty:
        tr = _prepare(treatments, cfg, diagnostics, "treatments")
        carbs = pd.to_numeric(
            tr.get("carbs", pd.Series(np.nan, index=tr.index)), errors="coerce"
        )
        events = tr.get("event", pd.Series("", index=tr.index)).fillna("").astype(str)
        meals = tr.loc[(carbs > 0) | events.str.contains("meal", case=False)]
        records = sorted(
            (max(occurred, known), occurred)
            for occurred, known in meals[["_time", "_available"]].itertuples(
                index=False, name=None
            )
            if pd.notna(known)
        )
        cursor, latest = 0, None
        for i, cutoff in enumerate(index):
            while cursor < len(records) and records[cursor][0] <= cutoff:
                occurred = records[cursor][1]
                latest = occurred if latest is None else max(latest, occurred)
                cursor += 1
            if latest is not None:
                out.iloc[i, out.columns.get_loc("minutes_since_meal")] = (
                    cutoff - latest
                ).total_seconds() / 60

    if hrv is not None and not hrv.empty:
        for metric in ("rmssd", "sdnn"):
            if "metric" in hrv and "value" in hrv:
                selected = hrv.loc[
                    hrv["metric"].astype(str).str.lower() == metric
                ].copy()
                value_col = "value"
            elif metric in hrv:
                selected = hrv.loc[
                    pd.to_numeric(hrv[metric], errors="coerce").notna()
                ].copy()
                value_col = metric
            else:
                continue
            if selected.empty:
                continue
            if "unit" in selected and not selected["unit"].dropna().eq("ms").all():
                raise ValueError(f"{metric} features require normalized milliseconds")
            for field in (
                "source_instance",
                "device_id",
                "recording_app",
                "method",
                "window_seconds",
                "native_type",
            ):
                if (
                    field in selected
                    and selected[field].fillna("unknown").nunique() > 1
                ):
                    raise ValueError(
                        f"Select a homogeneous {metric} series: multiple {field} values"
                    )
            hh = _prepare(selected, cfg, diagnostics, f"hrv_{metric}", value_col)
            # HRV can precede the displayed CGM interval; retain the declared
            # baseline and lag history without collapsing it into the first bin.
            hrv_index = pd.date_range(
                index[0] - pd.Timedelta(hours=24), index[-1], freq=freq
            )
            result = np.full((len(hrv_index), 4), np.nan)
            for i, values, _ in _asof_buckets(hh, hrv_index, step):
                result[i, :3] = [
                    _filled_at(values, i - lag // step, fill_limit)
                    for lag in (15, 30, 60)
                ]
                historical = values[max(0, i - 1440 // step) : i]
                historical = historical[np.isfinite(historical)]
                if len(historical) >= 12:
                    baseline = float(np.median(historical))
                    if baseline != 0:
                        result[i, 3] = (
                            100
                            * (_filled_at(values, i, fill_limit) - baseline)
                            / baseline
                        )
            out[
                [
                    f"{metric}_lag15",
                    f"{metric}_lag30",
                    f"{metric}_lag60",
                    f"{metric}_pct_baseline",
                ]
            ] = result[-len(index) :]

    if intake is not None and not intake.empty:
        ii = _prepare(intake, cfg, diagnostics, "intake", "amount")
        for key, hours in (("Na", 6), ("K", 6), ("Mg", 12)):
            selected = ii.loc[ii.get("type", pd.Series("", index=ii.index)).eq(key)]
            unit = (cfg.get("intake_units") or {}).get(key)
            result, count = np.zeros(len(index)), np.zeros(len(index), dtype=int)
            missing_unit = (
                int(selected["unit"].isna().sum())
                if "unit" in selected
                else len(selected)
            )
            wrong_unit = (
                int((selected["unit"].notna() & selected["unit"].ne(unit)).sum())
                if "unit" in selected and unit
                else 0
            )
            diagnostics["intake"].setdefault("unit_checks", {})[key] = {
                "configured_unit": unit,
                "missing_source_unit": missing_unit,
                "mismatched_source_unit": wrong_unit,
                "source_unit_assumed_from_configuration": (
                    len(selected) if unit and "unit" not in selected else 0
                ),
            }
            if unit:
                if "unit" in selected:
                    selected = selected.loc[selected["unit"].eq(unit)]
                for _, event in selected.loc[selected["_available"].notna()].iterrows():
                    start = index.searchsorted(
                        max(event["_time"], event["_available"]), side="left"
                    )
                    end = index.searchsorted(
                        event["_time"] + pd.Timedelta(hours=hours), side="left"
                    )
                    if start < end:
                        result[start:end] += event["_value"]
                        count[start:end] += 1
            result[count == 0] = np.nan
            out[f"{key.lower()}_intake_{hours}h"] = result
        diagnostics["intake"]["units"] = cfg.get("intake_units") or {}
        diagnostics["intake"][
            "semantics"
        ] = "recorded amounts only; missing events/undeclared units remain unknown"

    if meds is not None and not meds.empty:
        if "dose" not in meds:
            diagnostics["meds"] = {"input_rows": len(meds), "reason": "dose_missing"}
        else:
            mm = _prepare(meds, cfg, diagnostics, "meds", "dose")
            for med, params in (cfg.get("meds_decay") or {}).items():
                half_life = float(params.get("half_life_h", 0))
                if not np.isfinite(half_life) or half_life <= 0:
                    raise ValueError("Configured half_life_h must be positive")
                selected = mm.loc[
                    mm.get("med", pd.Series("", index=mm.index))
                    .fillna("")
                    .str.lower()
                    .eq(med.lower())
                ]
                result, count = np.zeros(len(index)), np.zeros(len(index), dtype=int)
                unit = params.get("unit")
                if unit:
                    if "unit" in selected:
                        selected = selected.loc[selected["unit"].eq(unit)]
                    for _, event in selected.loc[
                        selected["_available"].notna()
                    ].iterrows():
                        start = index.searchsorted(
                            max(event["_time"], event["_available"]), side="left"
                        )
                        elapsed = (
                            index[start:] - event["_time"]
                        ).total_seconds() / 3600
                        result[start:] += event["_value"] * (
                            0.5 ** (elapsed / half_life)
                        )
                        count[start:] += 1
                result[count == 0] = np.nan
                out[f"med_{med.lower()}_decay"] = result
            diagnostics["meds"][
                "semantics"
            ] = "configured exploratory exposure kernel; not drug concentration or dosing guidance"

    out.attrs["processing"] = {
        "version": PROCESSING_VERSION,
        "availability_policy": cfg.get("availability_policy", "strict"),
        "source_diagnostics": diagnostics,
        "feature_bins": "(cutoff-step, cutoff]; late records update past buckets only after becoming known",
        "feature_ffill_minutes": fill_limit * step,
        "pct_time_below_semantics": "fraction of measured bins; unobserved bins excluded with coverage reported",
        "historical_timezone": cfg.get("timezone"),
        "timezone_basis": cfg.get("timezone_basis", "explicit_run_configuration"),
    }
    return out


def label_events(
    feats: pd.DataFrame, cfg: Dict[str, Any], observations: Optional[pd.Series] = None
) -> pd.DataFrame:
    """Label measured minima in (t, t+H], requiring every future bin measured.

    Missing horizons/bins and out-of-scope cutoffs produce nullable targets.
    When observations is omitted, glucose_is_imputed identifies excluded fills.
    """
    step = _step(cfg)
    out = feats.copy()
    if not isinstance(out.index, pd.DatetimeIndex) or out.index.tz is None:
        raise ValueError("Cutoffs must be a timezone-aware DatetimeIndex")
    out.index = out.index.tz_convert("UTC")
    if not out.index.is_monotonic_increasing or out.index.has_duplicates:
        raise ValueError("Cutoffs must be unique and chronological")
    if not out.index.equals(out.index.floor(f"{step}min")):
        raise ValueError("Cutoffs must align to resample_minutes")
    if out.empty:
        return out
    night_mask = pd.Series(True, index=out.index)
    if cfg.get("night_hours_only", True):
        zone = cfg.get("timezone")
        if not zone:
            raise ValueError(
                "Night filtering requires an explicit historical IANA timezone"
            )
        try:
            local = out.index.tz_convert(ZoneInfo(zone))
        except (ZoneInfoNotFoundError, TypeError) as exc:
            raise ValueError("Invalid historical timezone") from exc
        bounds = cfg.get("night_hours", [22, 8])
        if len(bounds) != 2:
            raise ValueError("night_hours must contain two distinct hours")
        start, end = bounds
        if (
            any(isinstance(x, bool) or int(x) != x or not 0 <= x <= 23 for x in bounds)
            or start == end
        ):
            raise ValueError(
                "night_hours must contain two distinct hours from 0 through 23"
            )
        hours = local.hour
        mask = (
            ((hours >= start) | (hours < end))
            if start > end
            else ((hours >= start) & (hours < end))
        )
        night_mask = pd.Series(mask, index=out.index)
    if observations is None:
        observations = out["glucose"].copy()
        if "glucose_is_imputed" in out:
            observations = observations.where(
                ~out["glucose_is_imputed"].fillna(True).astype(bool)
            )
    if (
        not isinstance(observations.index, pd.DatetimeIndex)
        or observations.index.tz is None
    ):
        raise ValueError("Observation times must be timezone aware")
    observed = (
        pd.to_numeric(observations, errors="coerce")
        .where(lambda x: np.isfinite(x))
        .sort_index()
    )
    observed.index = observed.index.tz_convert("UTC")
    valid_times = observed.dropna().index
    last_time = valid_times.max() if len(valid_times) else pd.NaT
    grid_end = (
        max(out.index[-1], observed.index.max()) if len(observed) else out.index[-1]
    )
    grid = pd.date_range(out.index[0], grid_end.ceil(f"{step}min"), freq=f"{step}min")
    measured = (
        observed.resample(f"{step}min", closed="right", label="right")
        .min()
        .reindex(grid)
    )
    threshold = float(cfg.get("hypo_threshold_mgdl", 70))
    if not np.isfinite(threshold):
        raise ValueError("hypo_threshold_mgdl must be finite")
    target_report = {}
    for horizon in cfg.get("horizon_minutes", [60]):
        if (
            isinstance(horizon, bool)
            or int(horizon) != horizon
            or horizon <= 0
            or horizon % step
        ):
            raise ValueError(
                "Every horizon must be a positive whole multiple of resample_minutes"
            )
        horizon = int(horizon)
        steps = horizon // step
        future_min = (
            measured.iloc[::-1]
            .rolling(steps, min_periods=steps)
            .min()
            .iloc[::-1]
            .shift(-1)
            .reindex(out.index)
        )
        horizon_covered = (
            pd.Series(False, index=out.index)
            if pd.isna(last_time)
            else out.index + pd.Timedelta(minutes=horizon) <= last_time
        )
        complete = future_min.notna() & horizon_covered
        eligible = complete & night_mask
        name = f"y_night_hypo_{horizon}m"
        target = pd.Series(pd.NA, index=out.index, dtype="Int8")
        target.loc[eligible] = (future_min.loc[eligible] < threshold).astype("int8")
        out[name] = target
        status = pd.Series(
            "missing_future_measurements", index=out.index, dtype="string"
        )
        if pd.notna(last_time):
            status.loc[~horizon_covered] = "incomplete_horizon"
        status.loc[complete] = "eligible"
        status.loc[~night_mask] = "outside_analysis_hours"
        out[f"target_status_{horizon}m"] = status
        target_report[name] = {
            "interval": "(t, t+H]",
            "horizon_minutes": horizon,
            "threshold_mgdl": threshold,
            "coverage": "all future bins measured; no imputation",
            "counts": {str(k): int(v) for k, v in status.value_counts().items()},
        }
    out.attrs["targets"] = target_report
    return out


def build_windows(
    cgm_path: str,
    treatments_path: Optional[str],
    out_path: str,
    cfg_path: str = CFG_PATH,
    hrv_path: Optional[str] = None,
    intake_path: Optional[str] = None,
    meds_path: Optional[str] = None,
):
    cfg = load_cfg(cfg_path)
    cgm = pd.read_parquet(cgm_path)
    if cgm.empty:
        raise RuntimeError("CGM parquet is empty")
    parsed = _times(cgm["ts"], cfg)
    rejected_timestamps = int(parsed.isna().sum())
    cgm = cgm.copy()
    cgm["ts"] = parsed
    cgm = cgm.loc[cgm["ts"].notna()].sort_values("ts").set_index("ts")

    def optional(path):
        return pd.read_parquet(path) if path and os.path.exists(path) else None

    feats = compute_features(
        cgm,
        optional(treatments_path),
        cfg,
        hrv=optional(hrv_path),
        intake=optional(intake_path),
        meds=optional(meds_path),
    )
    win = label_events(feats, cfg, observations=_measured_glucose(cgm))
    before = len(win)
    win = win.dropna(subset=["glucose", "cgm_delta_10", "cgm_delta_30", "slope_15"])
    target_metadata = win.attrs.get("targets", {})
    for target, details in target_metadata.items():
        horizon = details["horizon_minutes"]
        details["counts_before_feature_eligibility"] = details.pop("counts")
        details["written_counts"] = {
            str(k): int(v)
            for k, v in win[f"target_status_{horizon}m"].value_counts().items()
        }
    report = {
        "processing": feats.attrs["processing"],
        "targets": target_metadata,
        "rows_before_feature_eligibility": before,
        "rows": len(win),
        "invalid_cgm_timestamps": rejected_timestamps,
        "inputs": {
            name: {
                "path": str(path),
                "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            }
            for name, path in (
                ("cgm", cgm_path),
                ("treatments", treatments_path),
                ("hrv", hrv_path),
                ("intake", intake_path),
                ("meds", meds_path),
                ("config", cfg_path),
            )
            if path and os.path.exists(path)
        },
        "purpose": "legacy glucose-event exploration; not a recovery model or held-out evaluation",
    }
    win.attrs.clear()
    result = win.rename_axis("t0").reset_index()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    result.to_parquet(out_path, index=False)
    metadata_path = f"{out_path}.metadata.json"
    with open(metadata_path, "w") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write("\n")
    return {
        "rows": len(win),
        "out": out_path,
        "ycols": [c for c in result if c.startswith("y_")],
        "metadata": metadata_path,
        "invalid_cgm_timestamps": rejected_timestamps,
    }


def main():
    parser = argparse.ArgumentParser()
    for name in ("cgm", "treatments", "hrv", "intake", "meds"):
        parser.add_argument(f"--{name}", default=f"storage/analytics/{name}.parquet")
    parser.add_argument("--out", default="storage/analytics/windows.parquet")
    parser.add_argument("--cfg", default=CFG_PATH)
    args = parser.parse_args()
    print(
        build_windows(
            args.cgm,
            args.treatments,
            args.out,
            args.cfg,
            hrv_path=args.hrv,
            intake_path=args.intake,
            meds_path=args.meds,
        )
    )


if __name__ == "__main__":
    main()
