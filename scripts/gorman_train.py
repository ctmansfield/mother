#!/usr/bin/env python3
import csv
import os
import json
import time
import argparse
from collections import defaultdict, deque


def load_yaml(p):
    try:
        import yaml

        with open(p, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def parts(arm):
    p = (arm or "").split("|")
    return (
        p[0] if len(p) > 0 else "",
        p[1] if len(p) > 1 else "",
        p[2] if len(p) > 2 else "",
        p[3] if len(p) > 3 else "",
    )


def decay_weight(ts_now, ts_evt, half_days):
    if not half_days or half_days <= 0:
        return 1.0
    age_days = max(0.0, (ts_now - ts_evt) / 86400.0)
    return 0.5 ** (age_days / half_days)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nudges", default="out/nudges.csv")
    args = ap.parse_args()

    cfg = (load_yaml("content/gorman.yaml") or {}).get("gorman", {})
    order = int(cfg.get("order", 3))
    window_days = int(cfg.get("window_days", 45))
    half = float(cfg.get("half_life_days", 14))
    model_path = cfg.get("model_path", "out/gorman_model.json")

    now = time.time()
    start = now - window_days * 86400

    seq = []  # list of (ts, category)
    if os.path.exists(args.nudges):
        with open(args.nudges, "r") as f:
            rd = csv.reader(f)
            for r in rd:
                if not r or len(r) < 2:
                    continue
                try:
                    ts = int(r[0])
                    arm = r[1]
                except Exception:
                    continue
                if ts < start:
                    continue
                ct = parts(arm)[3]
                if not ct:
                    continue
                seq.append((ts, ct))
    seq.sort(key=lambda t: t[0])

    # n-gram counts with decay
    counts = [
        defaultdict(lambda: defaultdict(float)) for _ in range(order + 1)
    ]  # counts[k][ctx_key][next_ct]
    hist = deque(maxlen=order)
    for ts, ct in seq:
        w = decay_weight(now, ts, half)
        ctx = list(hist)
        for k in range(1, order + 1):
            if len(ctx) >= k - 1:
                key = "|".join(ctx[-(k - 1) :]) if (k - 1) > 0 else ""
                counts[k][key][ct] += w
        hist.append(ct)

    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    # to json
    out = {
        "order": order,
        "counts": {
            str(k): {ctx: dict(nexts) for ctx, nexts in counts[k].items()}
            for k in range(1, order + 1)
        },
    }
    json.dump(out, open(model_path, "w"))
    print({"trained_events": len(seq), "order": order, "path": model_path})


if __name__ == "__main__":
    main()
