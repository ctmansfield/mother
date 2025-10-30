from __future__ import annotations
import os
import argparse
from typing import Optional, Dict, Any

import pandas as pd
import numpy as np
import yaml

CFG_PATH = "analytics/config/pipeline.yaml"


def load_cfg(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def _to_dt(ms: int) -> pd.Timestamp:
    return pd.to_datetime(ms, unit="ms", utc=True)


def _align_series_to_index(
    ts: pd.Series, idx: pd.DatetimeIndex, how: str = "ffill"
) -> pd.Series:
    s = ts.reindex(idx, method=how)
    return s


def _impulse_series(
    events: pd.DataFrame,
    idx: pd.DatetimeIndex,
    ts_col: str,
    val_col: Optional[str] = None,
) -> pd.Series:
    s = pd.Series(0.0, index=idx)
    if events is None or events.empty:
        return s
    e = events.copy()
    e[ts_col] = pd.to_datetime(e[ts_col], unit="ms", utc=True)
    e = e.sort_values(ts_col)
    for _, row in e.iterrows():
        t = row[ts_col]
        if t < idx[0] or t > idx[-1]:
            continue
        v = float(row.get(val_col, 1.0)) if val_col else 1.0
        # place on nearest bin
        pos = idx.get_indexer([t], method="nearest")[0]
        s.iloc[pos] += v
    return s


def _decay_feature(
    impulse: pd.Series, half_life_h: float, step_minutes: int
) -> pd.Series:
    alpha = 0.5 ** (step_minutes / (half_life_h * 60.0))
    out = np.zeros(len(impulse), dtype=float)
    imp = impulse.to_numpy(dtype=float)
    for i in range(len(imp)):
        out[i] = out[i - 1] * alpha + imp[i] if i > 0 else imp[i]
    return pd.Series(out, index=impulse.index)


def compute_features(
    df: pd.DataFrame,
    treatments: Optional[pd.DataFrame],
    cfg: Dict[str, Any],
    hrv: Optional[pd.DataFrame] = None,
    intake: Optional[pd.DataFrame] = None,
    meds: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    # df: index datetime UTC, column 'sgv'
    resample_min = int(cfg.get("resample_minutes", 5))
    # Resample and forward-fill within reasonable gap
    g = df["sgv"].resample(f"{resample_min}min").mean()
    g = g.ffill(limit=int(15 / resample_min))

    # Compute features
    out = pd.DataFrame(index=g.index)
    out["glucose"] = g
    # deltas and slopes
    out["cgm_delta_10"] = g - g.shift(int(10 / resample_min))
    out["cgm_delta_30"] = g - g.shift(int(30 / resample_min))
    out["slope_15"] = (g - g.shift(int(15 / resample_min))) / 15.0
    # pct time below 70 in last 2h/4h (if present in cfg)
    for hours in [2, 4]:
        win = int(hours * 60 / resample_min)
        below = (g < 70).rolling(win, min_periods=1).mean()
        out[f"pct_time_below_70_{hours}h"] = 100.0 * below

    # minutes since meal using treatments carbs>0 if provided
    msm = None
    if treatments is not None and not treatments.empty:
        tr = treatments.copy()
        tr["ts"] = pd.to_datetime(tr["ts"], unit="ms", utc=True)
        tr = tr.sort_values("ts")
        meal_mask = (tr.get("carbs").fillna(0) > 0) | (
            tr.get("event").fillna("").str.contains("meal", case=False)
        )
        meals = tr.loc[meal_mask, ["ts"]].set_index("ts").sort_index()
        if not meals.empty:
            base = out.index.to_series().rename("ts").sort_values()
            last_meal = pd.merge_asof(
                base.to_frame(),
                meals,
                left_on="ts",
                right_index=True,
                direction="backward",
            )
            msm = (base - last_meal["ts"]).dt.total_seconds() / 60.0
    out["minutes_since_meal"] = msm if msm is not None else np.nan

    # HRV features (rmssd) lagged
    if hrv is not None and not hrv.empty:
        hh = hrv.copy()
        # expected columns: ts (ms), rmssd
        hh["ts"] = pd.to_datetime(hh["ts"], unit="ms", utc=True)
        hh = (
            hh.sort_values("ts")
            .set_index("ts")
            .resample(f"{resample_min}min")
            .mean()
            .ffill(limit=3)
        )
        for L in [15, 30, 60]:
            steps = int(L / resample_min)
            out[f"rmssd_lag{L}"] = hh["rmssd"].reindex(out.index).shift(steps)
            # percent change vs 24h rolling baseline if available
        # optional baseline pct
        base = hh["rmssd"].rolling(int(24 * 60 / resample_min), min_periods=12).median()
        cur = hh["rmssd"].reindex(out.index)
        pct = 100.0 * (cur - base.reindex(out.index)) / (base.reindex(out.index) + 1e-9)
        out["rmssd_pct_baseline"] = pct

    # Electrolytes rolling intake (Na/K/Mg)
    if intake is not None and not intake.empty:
        ii = intake.copy()
        # expected columns: ts (ms), type (e.g., 'Na','K','Mg'), amount (in consistent units)
        ii["ts"] = pd.to_datetime(ii["ts"], unit="ms", utc=True)
        ii = ii.sort_values("ts")
        for key, window_h in [("Na", 6), ("K", 6), ("Mg", 12)]:
            imp = _impulse_series(ii[ii["type"] == key], out.index, "ts", "amount")
            out[f"{key.lower()}_intake_{window_h}h"] = imp.rolling(
                int(window_h * 60 / resample_min), min_periods=1
            ).sum()

    # Meds decay kernels
    if meds is not None and not meds.empty:
        mm = meds.copy()
        # expected columns: ts (ms), med (string), dose (optional)
        mm["ts"] = pd.to_datetime(mm["ts"], unit="ms", utc=True)
        mm = mm.sort_values("ts")
        mcfg = cfg.get("meds_decay") or {}
        for med, params in mcfg.items():
            half_life_h = float(params.get("half_life_h", 6))
            imp = _impulse_series(
                mm[mm["med"].str.lower() == med.lower()], out.index, "ts", "dose"
            )
            out[f"med_{med.lower()}_decay"] = _decay_feature(
                imp, half_life_h, resample_min
            )

    return out


def label_events(feats: pd.DataFrame, cfg: Dict[str, Any]) -> pd.DataFrame:
    horizons = cfg.get("horizon_minutes", [60])
    resample_min = int(cfg.get("resample_minutes", 5))
    threshold = float(cfg.get("hypo_threshold_mgdl", 70))
    night_only = bool(cfg.get("night_hours_only", True))
    night_bounds = cfg.get("night_hours", [22, 8])  # [start_hour, end_hour)
    out = feats.copy()
    # Night mask if requested
    if night_only:
        start_h, end_h = int(night_bounds[0]), int(night_bounds[1])
        night_mask = (out.index.hour >= start_h) | (out.index.hour < end_h)
    else:
        night_mask = pd.Series(True, index=out.index)
    for H in horizons:
        steps = int(H / resample_min)
        # future min in (t0, t0+H]
        future_min = out["glucose"].shift(-1).rolling(steps, min_periods=1).min()
        lab = (future_min < threshold).astype(int)
        # apply night mask if enabled
        lab = lab.where(night_mask, other=0)
        out[f"y_night_hypo_{H}m"] = lab
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
    if not os.path.exists(cgm_path):
        raise FileNotFoundError(cgm_path)
    cgm = pd.read_parquet(cgm_path)
    if cgm.empty:
        raise RuntimeError("CGM parquet is empty")
    cgm["ts"] = pd.to_datetime(cgm["ts"], unit="ms", utc=True)
    cgm = cgm.sort_values("ts").set_index("ts")
    treatments = None
    if treatments_path and os.path.exists(treatments_path):
        treatments = pd.read_parquet(treatments_path)
    hrv = pd.read_parquet(hrv_path) if hrv_path and os.path.exists(hrv_path) else None
    intake = (
        pd.read_parquet(intake_path)
        if intake_path and os.path.exists(intake_path)
        else None
    )
    meds = (
        pd.read_parquet(meds_path) if meds_path and os.path.exists(meds_path) else None
    )

    feats = compute_features(cgm, treatments, cfg, hrv=hrv, intake=intake, meds=meds)
    win = label_events(feats, cfg)
    # Drop rows with NaNs in critical features
    crit = ["glucose", "cgm_delta_10", "cgm_delta_30", "slope_15"]
    win = win.dropna(subset=[c for c in crit if c in win.columns])
    # Serialize windows with robust t0 naming
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    df_out = win.reset_index()
    # Ensure first column (former index) is named t0
    if df_out.columns[0] != "t0":
        df_out = df_out.rename(columns={df_out.columns[0]: "t0"})
    df_out.to_parquet(out_path, index=False)
    # Sanity: ensure y_ columns exist in output
    ycols = [c for c in df_out.columns if c.startswith("y_")]
    return {"rows": len(win), "out": out_path, "ycols": ycols}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cgm", default="storage/analytics/cgm.parquet")
    ap.add_argument("--treatments", default="storage/analytics/treatments.parquet")
    ap.add_argument("--hrv", default="storage/analytics/hrv.parquet")
    ap.add_argument("--intake", default="storage/analytics/intake.parquet")
    ap.add_argument("--meds", default="storage/analytics/meds.parquet")
    ap.add_argument("--out", default="storage/analytics/windows.parquet")
    ap.add_argument("--cfg", default=CFG_PATH)
    args = ap.parse_args()
    res = build_windows(
        args.cgm,
        args.treatments,
        args.out,
        args.cfg,
        hrv_path=args.hrv,
        intake_path=args.intake,
        meds_path=args.meds,
    )
    print(res)


if __name__ == "__main__":
    main()
