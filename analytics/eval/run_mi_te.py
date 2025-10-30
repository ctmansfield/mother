#!/usr/bin/env python3
from __future__ import annotations
import os
import json
import argparse
from typing import Dict, Any, List, Tuple

import numpy as np
import pandas as pd

from analytics.phiid_core.api import InfoDecomposition
import random


def _event_key(col: str) -> str:
    return col[2:] if col.startswith("y_") else col


def _numeric_cols(df: pd.DataFrame) -> List[str]:
    return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]


def _bootstrap_indices(n: int, block: int) -> np.ndarray:
    # simple non-overlapping block bootstrap indices
    blocks = list(range(0, n, block))
    draws = [random.choice(blocks) for _ in blocks]
    idx = []
    for b in draws:
        idx.extend(list(range(b, min(b + block, n))))
    return np.array(idx[:n])


def _permute_preserve_autocorr(x: np.ndarray, block: int) -> np.ndarray:
    n = len(x)
    blocks = [x[i : i + block] for i in range(0, n, block)]
    random.shuffle(blocks)
    return np.concatenate(blocks)[:n]


def compute_mi_synergy(
    win: pd.DataFrame,
    target_cols: List[str],
    topn_pairs: int = 10,
    k: int = 5,
    n_boot: int = 200,
    block: int = 24,
) -> Dict[str, Any]:
    phi = InfoDecomposition()
    results: Dict[str, Any] = {}

    # ensure sorted by time if present
    if "t0" in win.columns:
        try:
            win = win.sort_values("t0")
        except Exception:
            pass

    all_numeric = _numeric_cols(win)

    for ycol in target_cols:
        # features are numeric and not target columns
        feats = [c for c in all_numeric if c != ycol and not c.startswith("y_")]
        df_y = win.dropna(subset=[ycol])
        if df_y.empty or df_y[ycol].nunique() < 2:
            continue
        # MI ranking + bootstrap CIs
        mi_scores = {}
        mi_ci = {}
        for f in feats:
            sub = df_y[[f, ycol]].replace([np.inf, -np.inf], np.nan).dropna()
            if sub.empty or sub[f].nunique() < 2:
                mi_scores[f] = 0.0
                mi_ci[f] = [0.0, 0.0]
                continue
            X = sub[f].to_numpy()
            Y = sub[ycol].to_numpy()
            try:
                mi0 = float(phi.mi(X, Y, k=k))
            except Exception:
                mi0 = 0.0
            mi_scores[f] = mi0
            # bootstrap CI (block bootstrap)
            if len(sub) >= (block * 2):
                vals = []
                for _ in range(n_boot):
                    idxb = _bootstrap_indices(len(sub), block)
                    vals.append(float(phi.mi(X[idxb], Y[idxb], k=k)))
                lo, hi = float(np.percentile(vals, 2.5)), float(
                    np.percentile(vals, 97.5)
                )
            else:
                lo, hi = mi0, mi0
            mi_ci[f] = [lo, hi]
        unique_rank = [k for k, _ in sorted(mi_scores.items(), key=lambda kv: -kv[1])]

        # synergy pairs among top 8 features, with permutation p-value
        top_feats = unique_rank[:8]
        pairs: List[Tuple[str, str, float, float]] = []  # f1,f2,synergy,pval
        for i in range(len(top_feats)):
            for j in range(i + 1, len(top_feats)):
                f1, f2 = top_feats[i], top_feats[j]
                sub = df_y[[f1, f2, ycol]].replace([np.inf, -np.inf], np.nan).dropna()
                if sub.empty or sub[ycol].nunique() < 2:
                    continue
                X1 = sub[f1].to_numpy().reshape(-1, 1)
                X2 = sub[f2].to_numpy().reshape(-1, 1)
                X12 = np.concatenate([X1, X2], axis=1)
                Y = sub[ycol].to_numpy()
                try:
                    mi12 = float(phi.mi(X12, Y, k=k))
                except Exception:
                    mi12 = 0.0
                m1 = mi_scores.get(f1, 0.0)
                m2 = mi_scores.get(f2, 0.0)
                syn = mi12 - max(m1, m2)
                if syn <= 0:
                    continue
                # permutation test preserving autocorr with block shuffling on Y
                if len(sub) >= (block * 2):
                    greater = 0
                    n_perm = max(100, int(n_boot / 2))
                    for _ in range(n_perm):
                        Yp = _permute_preserve_autocorr(Y, block)
                        mi12p = float(phi.mi(X12, Yp, k=k))
                        synp = mi12p - max(m1, m2)
                        if synp >= syn:
                            greater += 1
                    pval = (greater + 1) / (n_perm + 1)
                else:
                    pval = 1.0
                pairs.append((f1, f2, syn, pval))
        pairs = [p for p in pairs if p[3] <= 0.05]
        pairs = sorted(pairs, key=lambda x: -x[2])[:topn_pairs]
        synergy_sets = [[a, b] for a, b, _, _ in pairs]

        # assemble
        results[_event_key(ycol)] = {
            "unique_rank": unique_rank,
            "mi_scores": mi_scores,
            "mi_ci": mi_ci,
            "synergy_sets": synergy_sets,
        }
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--windows", default="storage/analytics/windows.parquet")
    ap.add_argument("--out", default="analytics/eval/feature_importance.json")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--n_boot", type=int, default=200)
    ap.add_argument("--block", type=int, default=24)
    args = ap.parse_args()

    assert os.path.exists(args.windows), args.windows
    win = pd.read_parquet(args.windows)
    tcols = [c for c in win.columns if c.startswith("y_")]
    res = compute_mi_synergy(win, tcols, k=args.k, n_boot=args.n_boot, block=args.block)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(res, f, indent=2)
    print({"events": list(res.keys()), "out": args.out})


if __name__ == "__main__":
    main()
