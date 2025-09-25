#!/usr/bin/env python3
import os
import csv
import json
import math
import argparse
import time
from datetime import datetime

try:
    import numpy as np
except Exception:
    np = None


def load_yaml(path):
    try:
        import yaml

        with open(path, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def read_nudges(path="out/nudges.csv", start_ts=None):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r") as f:
        rd = csv.reader(f)
        for r in rd:
            if not r:
                continue
            try:
                ts = int(r[0])
                arm = r[1]
                rw = r[2] if len(r) > 2 and r[2] != "" else None
                if (start_ts is not None) and (ts < start_ts):
                    continue
                reward = int(rw) if rw is not None else None
                rows.append((ts, arm, reward))
            except Exception:
                continue
    return rows


def feats_for_ts(ts):
    dt = datetime.fromtimestamp(ts)
    h = dt.hour
    m = dt.minute
    xh = (h * 60 + m) / 1440.0 * 2 * math.pi
    hour_sin = math.sin(xh)
    hour_cos = math.cos(xh)
    dow = dt.weekday()  # 0..6
    return hour_sin, hour_cos, dow


def build_dataset(nudges, window_days=30):
    if not nudges:
        return [], [], []
    cutoff = int(time.time()) - window_days * 86400
    nudges = [r for r in nudges if r[0] >= cutoff]
    if not nudges:
        return [], [], []
    # global CTRs
    shows = 0
    clicks = 0
    dismiss = 0
    by_cat = {"hydration": [0, 0], "movement": [0, 0]}
    for ts, arm, r in nudges:
        shows += 1
        if r == 1:
            clicks += 1
        if r == 0:
            dismiss += 1
        parts = (arm or "").split("|")
        cat = parts[3] if len(parts) > 3 else ""
        if cat in by_cat:
            by_cat[cat][0] += 1
            if r == 1:
                by_cat[cat][1] += 1
    ctr_overall = (clicks / shows) if shows else 0.0
    ctr_hyd = (
        (by_cat["hydration"][1] / by_cat["hydration"][0])
        if by_cat["hydration"][0]
        else 0.0
    )
    ctr_move = (
        (by_cat["movement"][1] / by_cat["movement"][0])
        if by_cat["movement"][0]
        else 0.0
    )
    dismiss_rate = (dismiss / shows) if shows else 0.0

    X = []
    meta = []
    for ts, arm, r in nudges:
        hour_sin, hour_cos, dow = feats_for_ts(ts)
        night_flag = (
            1.0
            if (
                hour_cos < -0.3
                or (
                    datetime.fromtimestamp(ts).hour >= 22
                    or datetime.fromtimestamp(ts).hour < 7
                )
            )
            else 0.0
        )
        row = [
            hour_sin,
            hour_cos,
            ctr_overall,
            ctr_hyd,
            ctr_move,
            dismiss_rate,
            night_flag,
        ]
        # expand DOW onehot
        for d in range(7):
            row.append(1.0 if d == dow else 0.0)
        X.append(row)
        meta.append((ts, arm, r))
    return (
        X,
        meta,
        [
            "hour_sin",
            "hour_cos",
            "ctr_overall",
            "ctr_hydration",
            "ctr_movement",
            "dismiss_rate",
            "night_flag",
        ]
        + [f"dow_{i}" for i in range(7)],
    )


def kmeans(X, k=4, iters=40):
    # X: list of lists
    if np is None:
        # simple pure python kmeans (cosine-ish via L2)
        import random

        n = len(X)
        d = len(X[0])
        C = [X[i] for i in [int(random.random() * n) for _ in range(k)]]
        for _ in range(iters):
            asn = [
                min(
                    range(k),
                    key=lambda j: sum((X[i][m] - C[j][m]) ** 2 for m in range(d)),
                )
                for i in range(n)
            ]
            newC = [[0.0] * d for _ in range(k)]
            cnt = [0] * k
            for i, a in enumerate(asn):
                cnt[a] += 1
                for m in range(d):
                    newC[a][m] += X[i][m]
            for j in range(k):
                if cnt[j] > 0:
                    newC[j] = [v / cnt[j] for v in newC[j]]
                else:
                    newC[j] = C[j]
            C = newC
        return C, asn
    else:
        Xn = np.array(X, dtype=float)
        n, d = Xn.shape
        rng = np.random.default_rng()
        C = Xn[rng.choice(n, size=k, replace=False)]
        for _ in range(iters):
            # assign
            # squared distances
            dists = ((Xn[:, None, :] - C[None, :, :]) ** 2).sum(axis=2)
            asn = np.argmin(dists, axis=1)
            # update
            for j in range(k):
                pts = Xn[asn == j]
                if len(pts) > 0:
                    C[j] = pts.mean(axis=0)
        return C.tolist(), asn.tolist()


def label_centroids(C, feat_names, cfg):
    labs = []
    rules = cfg.get("label_heuristics", [])
    # index lookup
    idx = {n: i for i, n in enumerate(feat_names)}

    def val(c, name):
        i = idx.get(name)
        return c[i] if i is not None else 0.0

    for c in C:
        chosen = None
        for r in rules:
            ok = True
            for k, expr in (r.get("when") or {}).items():
                v = val(c, k)
                try:
                    expr = expr.strip()
                    if expr.startswith(">="):
                        ok &= v >= float(expr[2:].strip())
                    elif expr.startswith("<="):
                        ok &= v <= float(expr[2:].strip())
                    elif expr.startswith(">"):
                        ok &= v > float(expr[1:].strip())
                    elif expr.startswith("<"):
                        ok &= v < float(expr[1:].strip())
                    else:
                        ok &= False
                except Exception:
                    ok = False
            if ok:
                chosen = r.get("name")
                break
        labs.append(chosen or "baseline-you")
    return labs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="content/acheron_segments.yaml")
    args = ap.parse_args()
    cfg = (load_yaml("content/acheron.yaml") or {}).get("acheron", {})
    k = int(cfg.get("k", 4))
    iters = int(cfg.get("iters", 40))
    window_days = int(cfg.get("window_days", 30))
    min_rows = int(cfg.get("min_rows", 40))
    nudges = read_nudges(
        "out/nudges.csv", start_ts=int(time.time()) - window_days * 86400
    )
    X, meta, feat_names = build_dataset(nudges, window_days)
    if not X or len(X) < min_rows:
        # write empty (fallback to baseline)
        out = {
            "acheron_segments": {
                "trained_at": datetime.now().isoformat(),
                "feat_names": feat_names,
                "centroids": [],
                "labels": [],
            }
        }
    else:
        C, asn = kmeans(X, k=k, iters=iters)
        labels = label_centroids(C, feat_names, cfg)
        out = {
            "acheron_segments": {
                "trained_at": datetime.now().isoformat(),
                "feat_names": feat_names,
                "centroids": C,
                "labels": labels,
            }
        }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    try:
        import yaml

        with open(args.out, "w") as f:
            yaml.safe_dump(out, f, sort_keys=False)
    except Exception:
        # json fallback
        with open(args.out, "w") as f:
            f.write(json.dumps(out))
    print(
        json.dumps({"written": args.out, "k": len(out["acheron_segments"]["labels"])})
    )


if __name__ == "__main__":
    main()
