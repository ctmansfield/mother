#!/usr/bin/env python3
from __future__ import annotations
import os
import argparse
import json
from typing import List

import pandas as pd
import numpy as np


def ppv(y_true: pd.Series, y_pred: pd.Series) -> float:
    tp = ((y_true == 1) & (y_pred == 1)).sum()
    fp = ((y_true == 0) & (y_pred == 1)).sum()
    return float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0


def _bootstrap_ppv(
    y: pd.Series, preds: pd.Series, n_boot: int = 200, block: int = 24
) -> (float, float):
    n = len(y)
    if n < block * 2:
        p = ppv(y, preds)
        return p, p
    import random

    idxs = list(range(0, n, block))
    vals = []
    for _ in range(n_boot):
        draw = [random.choice(idxs) for _ in idxs]
        ii = []
        for b in draw:
            ii.extend(list(range(b, min(b + block, n))))
        ii = ii[:n]
        vals.append(ppv(y.iloc[ii], preds.iloc[ii]))
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def mine_rules(
    windows: str,
    event: str,
    candidates: List[str],
    out: str,
    topn: int = 5,
    min_support: int = 20,
    min_ppv: float = 0.2,
    n_boot: int = 200,
    block: int = 24,
    enable_triads: bool = True,
    max_candidates: int = 6,
    feat_imp_path: str | None = None,
) -> int:
    assert os.path.exists(windows), windows
    df = pd.read_parquet(windows)

    # Exclude non-numeric dtypes explicitly (datetime, timedelta, category, bool)
    def _is_numeric_series(s: pd.Series) -> bool:
        return pd.api.types.is_integer_dtype(s) or pd.api.types.is_float_dtype(s)

    candidates = [
        c
        for c in list(candidates)[:max_candidates]
        if c in df.columns and _is_numeric_series(df[c])
    ]
    df = df.dropna(subset=candidates + [event])

    # Optional synergy-guided pruning
    synergy_pairs = set()
    if feat_imp_path and os.path.exists(feat_imp_path):
        try:
            with open(feat_imp_path, "r") as f:
                fi = json.load(f)
            ev_key = event.replace("y_", "")
            for pair in fi.get(ev_key, {}).get("synergy_sets", []):
                if len(pair) == 2 and all(p in candidates for p in pair):
                    synergy_pairs.add(tuple(pair))
        except Exception:
            pass

    results = []
    # try 2-feature rules: both directions per pair, thresholds on quantiles
    for i, f1 in enumerate(candidates):
        for f2 in candidates[i + 1 :]:
            # synergy-guided pruning for pairs if available
            if (
                synergy_pairs
                and (f1, f2) not in synergy_pairs
                and (f2, f1) not in synergy_pairs
            ):
                continue
            # guard against non-numeric columns that slipped through
            if not (
                pd.api.types.is_numeric_dtype(df[f1])
                and pd.api.types.is_numeric_dtype(df[f2])
            ):
                continue
            q1 = df[f1].quantile([0.1, 0.25, 0.5, 0.75, 0.9]).values
            q2 = df[f2].quantile([0.1, 0.25, 0.5, 0.75, 0.9]).values
            for t1 in q1:
                for t2 in q2:
                    pred1 = ((df[f1] <= t1) & (df[f2] >= t2)).astype(int)
                    pred2 = ((df[f1] >= t1) & (df[f2] <= t2)).astype(int)
                    for ops, pred in ((["<=", ">="], pred1), ([">=", "<="], pred2)):
                        support = int(pred.sum())
                        if support < min_support:
                            continue
                        p = ppv(df[event], pred)
                        if p < min_ppv:
                            continue
                        lo, hi = _bootstrap_ppv(
                            df[event], pred, n_boot=n_boot, block=block
                        )
                        results.append(
                            {
                                "features": [f1, f2],
                                "ops": ops,
                                "values": [float(t1), float(t2)],
                                "ppv": p,
                                "ppv_ci": [lo, hi],
                                "support": support,
                            }
                        )

    # triads
    if enable_triads and len(candidates) >= 3:
        from itertools import combinations

        for f1, f2, f3 in combinations(candidates, 3):
            # synergy-guided pruning for triads: keep only if a subset pair is in synergy_pairs when provided
            if synergy_pairs and not (
                (f1, f2) in synergy_pairs
                or (f2, f1) in synergy_pairs
                or (f1, f3) in synergy_pairs
                or (f3, f1) in synergy_pairs
                or (f2, f3) in synergy_pairs
                or (f3, f2) in synergy_pairs
            ):
                continue
            if not (
                pd.api.types.is_numeric_dtype(df[f1])
                and pd.api.types.is_numeric_dtype(df[f2])
                and pd.api.types.is_numeric_dtype(df[f3])
            ):
                continue
            q1 = df[f1].quantile([0.25, 0.5, 0.75]).values
            q2 = df[f2].quantile([0.25, 0.5, 0.75]).values
            q3 = df[f3].quantile([0.25, 0.5, 0.75]).values
            for t1 in q1:
                for t2 in q2:
                    for t3 in q3:
                        # two direction templates to control combinatorics
                        preds = [
                            ((df[f1] <= t1) & (df[f2] >= t2) & (df[f3] >= t3)).astype(
                                int
                            ),
                            ((df[f1] >= t1) & (df[f2] <= t2) & (df[f3] <= t3)).astype(
                                int
                            ),
                        ]
                        opsets = [["<=", ">=", ">="], [">=", "<=", "<="]]
                        for pred, ops in zip(preds, opsets):
                            support = int(pred.sum())
                            if support < min_support:
                                continue
                            p = ppv(df[event], pred)
                            if p < min_ppv:
                                continue
                            lo, hi = _bootstrap_ppv(
                                df[event], pred, n_boot=n_boot, block=block
                            )
                            results.append(
                                {
                                    "features": [f1, f2, f3],
                                    "ops": ops,
                                    "values": [float(t1), float(t2), float(t3)],
                                    "ppv": p,
                                    "ppv_ci": [lo, hi],
                                    "support": support,
                                }
                            )

    res_sorted = sorted(results, key=lambda x: (-x["ppv"], -x["support"]))[:topn]
    rules = []
    for i, r in enumerate(res_sorted, start=1):
        feats = r["features"]
        ops = r["ops"]
        vals = r["values"]
        if_all = [
            {"feature": f, "op": o, "value": v} for f, o, v in zip(feats, ops, vals)
        ]
        rules.append(
            {
                "id": f"rule_{i:03d}",
                "event": event.replace("y_", ""),
                "if_all": if_all,
                "action": "slow_carb_protein_snack",
                "metadata": {
                    "evaluation_scope": "discovery_only",
                    "held_out_evaluation": None,
                    "ppv": r["ppv"],
                    "ppv_ci": r["ppv_ci"],
                    "support": r["support"],
                },
            }
        )

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w") as f:
        json.dump(
            {
                "rules": rules,
                "evaluation": {
                    "scope": "discovery_only",
                    "held_out_evaluation": None,
                    "note": "Selection and reported precision reuse the discovery data; not personal performance evidence.",
                },
            },
            f,
            indent=2,
        )
    return len(rules)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--windows", default="storage/analytics/windows.parquet")
    ap.add_argument("--event", default="y_night_hypo_60m")
    ap.add_argument(
        "--candidates",
        nargs="*",
        default=["cgm_delta_10", "minutes_since_meal", "cgm_delta_30", "slope_15"],
    )
    ap.add_argument("--out", default="analytics/rules/rules.json")
    ap.add_argument("--topn", type=int, default=5)
    ap.add_argument("--min_support", type=int, default=20)
    ap.add_argument("--min_ppv", type=float, default=0.2)
    ap.add_argument("--n_boot", type=int, default=200)
    ap.add_argument("--block", type=int, default=24)
    ap.add_argument("--no_triads", action="store_true")
    ap.add_argument("--max_candidates", type=int, default=6)
    ap.add_argument("--feat_imp", default="")
    args = ap.parse_args()
    n = mine_rules(
        args.windows,
        args.event,
        args.candidates,
        args.out,
        topn=args.topn,
        min_support=args.min_support,
        min_ppv=args.min_ppv,
        n_boot=args.n_boot,
        block=args.block,
        enable_triads=(not args.no_triads),
        max_candidates=args.max_candidates,
        feat_imp_path=(args.feat_imp or None),
    )
    print({"wrote_rules": n, "out": args.out})


if __name__ == "__main__":
    main()
