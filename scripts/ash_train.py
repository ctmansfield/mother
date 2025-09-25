#!/usr/bin/env python3
import csv
import os
from collections import defaultdict
from datetime import datetime


def load_yaml(p):
    try:
        import yaml

        with open(p, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return {}


def read_csv_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        r = csv.DictReader(f)
        return [dict(row) for row in r]


def to_int(x, d=0):
    try:
        return int(float(x))
    except Exception:
        return d


def to_float(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


def main():
    cfg = (load_yaml("content/ash.yaml") or {}).get("ash", {})
    psv = (load_yaml("content/passive_actions.yaml") or {}).get("passive", {})
    default_join = int(cfg.get("join_window_s", 1800))
    join_by_cat = psv.get("join_window_s", {}) if isinstance(psv, dict) else {}
    method = str(cfg.get("method", "to")).lower()
    feats = list(cfg.get("features", ["category", "daypart", "tone", "channel"]))
    alpha = float(cfg.get("alpha", 1.0))
    beta = float(cfg.get("beta", 1.0))
    min_cell = int(cfg.get("min_cell", 20))
    default_uplift = float(cfg.get("default_uplift", 0.01))
    holdout = float(cfg.get("holdout_rate", 0.10))
    # Data
    exps = read_csv_rows("out/ash_log.csv")
    fbs = read_csv_rows("out/nudges.csv")  # explicit rewards
    pas = read_csv_rows("out/passive_actions.csv")  # passive actions
    # Normalize
    for e in exps:
        e["ts"] = to_int(e.get("ts", 0))
        e["treatment"] = to_int(e.get("treatment", 0))
        e["category"] = e.get("category", "")
        e["daypart"] = e.get("daypart", "")
        e["tone"] = e.get("tone", "")
        e["channel"] = e.get("channel", "")
    fbs = [
        {
            "ts": to_int(r.get("ts")),
            "arm": r.get("arm", ""),
            "reward": to_int(r.get("reward", 0)),
        }
        for r in fbs
        if str(r.get("reward", "")).strip() != ""
    ]
    pas = [
        {
            "ts": to_int(r.get("ts")),
            "category": r.get("category", ""),
            "event": r.get("event", ""),
        }
        for r in pas
    ]
    fbs.sort(key=lambda x: x["ts"])
    pas.sort(key=lambda x: x["ts"])
    # Build per-category index of passive actions (ts list)
    pidx = defaultdict(list)
    for p in pas:
        pidx[p["category"]].append(p["ts"])

    # Reward function: treatment → explicit OR passive in window; control → passive in window
    def has_passive(cat, ts, win):
        arr = pidx.get(cat, [])
        # binary search window [ts, ts+win]
        import bisect

        i = bisect.bisect_left(arr, ts)
        j = bisect.bisect_right(arr, ts + win)
        return (j - i) > 0

    def explicit_reward(arm, ts, win):
        # first explicit feedback within window
        for r in fbs:
            if r["arm"] != arm:
                continue
            if r["ts"] < ts:
                continue
            if r["ts"] - ts <= win:
                return 1
        return 0

    # Aggregate per exposure
    rows = []
    for e in exps:
        win = int(join_by_cat.get(e["category"], default_join))
        arm = f'{e["daypart"]}|{e["tone"]}|{e["channel"]}|{e["category"]}'
        y_explicit = explicit_reward(arm, e["ts"], win)
        y_passive = 1 if has_passive(e["category"], e["ts"], win) else 0
        y = y_explicit if e["treatment"] == 1 else y_passive
        rows.append({**e, "y": y})
    # Cells with hierarchical backoff masks
    n = len(feats)
    masks = [[1] * k + [0] * (n - k) for k in range(n, -1, -1)]
    cells = defaultdict(list)

    def key(row, mask):
        vals = [row[f] if u else "*" for f, u in zip(feats, mask)]
        return "|".join(vals)

    for r in rows:
        for m in masks:
            cells[key(r, m)].append(r)
    uplift = {}
    for k, rows_k in cells.items():
        if len(rows_k) < min_cell:
            continue
        t = [r for r in rows_k if r["treatment"] == 1]
        c = [r for r in rows_k if r["treatment"] == 0]
        if method == "diff":
            rt = (
                (sum(r["y"] for r in t) + alpha) / (len(t) + alpha + beta)
                if (len(t) + alpha + beta) > 0
                else 0.0
            )
            rc = (
                (sum(r["y"] for r in c) + alpha) / (len(c) + alpha + beta)
                if (len(c) + alpha + beta) > 0
                else 0.0
            )
            up = rt - rc
        else:
            # Transformed Outcome using known propensity (holdout rate)
            p_t = max(1e-3, 1.0 - holdout)
            zo = [
                (
                    (r["treatment"] * r["y"]) / p_t
                    - ((1 - r["treatment"]) * r["y"]) / (1.0 - p_t)
                )
                for r in rows_k
            ]
            up = sum(zo) / len(zo)
        uplift[k] = round(up, 4)
    # Write table
    out = ["ash_table:"]
    out.append(f'  generated_at: "{datetime.now().isoformat()}"')
    out.append(f'  tau: {cfg.get("tau",0.01)}')
    out.append(f"  default: {default_uplift}")
    out.append("  features: [" + ",".join(feats) + "]")
    out.append("  uplift:")
    for k in sorted(uplift.keys()):
        out.append(f'    "{k}": {uplift[k]}')
    with open("content/ash_table.yaml", "w") as f:
        f.write("\n".join(out) + "\n")
    print("wrote content/ash_table.yaml")


if __name__ == "__main__":
    main()
