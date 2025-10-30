#!/usr/bin/env python3
from __future__ import annotations
import os
import argparse

from analytics.preprocess.sources.nightscout_adapter import incremental_sync
from analytics.events.window_builder import build_windows
from analytics.eval.run_mi_te import compute_mi_synergy
from analytics.rules.mine_rules import mine_rules
import pandas as pd
import json


def run_pipeline(
    days: int = 14,
    cgm_path: str = "storage/analytics/cgm.parquet",
    treatments_path: str = "storage/analytics/treatments.parquet",
    windows_path: str = "storage/analytics/windows.parquet",
    feat_imp_path: str = "analytics/eval/feature_importance.json",
    rules_out: str = "analytics/rules/rules.json",
):
    # 1) Nightscout sync
    incremental_sync(days=days)

    # 2) Windows
    build_windows(cgm_path, treatments_path, windows_path)

    # 3) MI / Synergy with bootstrap CI & permutation
    win = pd.read_parquet(windows_path)
    target_cols = [c for c in win.columns if c.startswith("y_")]
    res = compute_mi_synergy(win, target_cols, k=5, n_boot=200, block=24)
    os.makedirs(os.path.dirname(feat_imp_path) or ".", exist_ok=True)
    with open(feat_imp_path, "w") as f:
        json.dump(res, f, indent=2)

    # 4) Rule mining with stability filters
    event = target_cols[0] if target_cols else "y_night_hypo_60m"
    # candidate features: top 6 from MI rank
    uniq = res.get(event.replace("y_", ""), {}).get("unique_rank", [])
    candidates = (
        uniq[:6]
        if uniq
        else ["cgm_delta_10", "minutes_since_meal", "cgm_delta_30", "slope_15"]
    )
    mine_rules(
        windows_path,
        event,
        candidates,
        rules_out,
        topn=5,
        min_support=20,
        min_ppv=0.25,
        n_boot=200,
        block=24,
    )

    return {"feature_importance": feat_imp_path, "rules": rules_out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--windows", default="storage/analytics/windows.parquet")
    ap.add_argument("--feat_imp", default="analytics/eval/feature_importance.json")
    ap.add_argument("--rules_out", default="analytics/rules/rules.json")
    args = ap.parse_args()
    res = run_pipeline(
        days=args.days,
        windows_path=args.windows,
        feat_imp_path=args.feat_imp,
        rules_out=args.rules_out,
    )
    print(res)


if __name__ == "__main__":
    main()
