#!/usr/bin/env python3
import csv
import os
import time
import yaml
import json
import random

try:
    import numpy as np
except Exception:
    np = None

FEATS = [
    "daypart_morning",
    "daypart_midday",
    "daypart_afternoon",
    "daypart_evening",
    "tone_gentle",
    "tone_humor",
    "tone_strict",
    "channel_push",
    "channel_in_app",
    "category_hydration",
    "category_posture",
    "category_movement",
    "category_focus",
    "category_sleep",
]
D = len(FEATS)


def _cfg():
    try:
        return (yaml.safe_load(open("content/acheron.yaml")) or {}).get("acheron", {})
    except Exception:
        return {}


def _parts(arm):
    p = (arm or "").split("|")
    return (
        p[0] if len(p) > 0 else "",
        p[1] if len(p) > 1 else "",
        p[2] if len(p) > 2 else "",
        p[3] if len(p) > 3 else "",
    )


def _x_from_arm(arm):
    dp, tn, ch, ct = _parts(arm)
    x = [0.0] * D

    def set1(name):
        if name in FEATS:
            x[FEATS.index(name)] = 1.0

    set1(f"daypart_{dp}")
    set1(f"tone_{tn}")
    set1(f"channel_{ch}")
    set1(f"category_{ct}")
    if np is not None:
        return np.array(x, dtype=float)
    return x


def _decay(now, ts, half):
    if not half or half <= 0:
        return 1.0
    age = (now - ts) / 86400.0
    return 0.5 ** (age / half)


def _read_rows(path, start_ts):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r") as f:
        rd = csv.reader(f)
        for r in rd:
            if not r or len(r) < 2:
                continue
            try:
                ts = int(r[0])
                arm = r[1]
                rw = None if len(r) < 3 or r[2] == "" else float(r[2])
            except Exception:
                continue
            if ts < start_ts:
                continue
            rows.append((ts, arm, 1.0 if (rw or 0.0) > 0 else 0.0))
    rows.sort(key=lambda t: t[0])
    return rows


def _kmeans(X, W, k, iters):
    # X: list/np (n,D), W: weights (n,)
    n = len(X)
    idx = list(range(n))
    random.shuffle(idx)
    pick = idx[:k] if n >= k else [0] * k
    if np is not None:
        C = np.stack([X[i] for i in pick], axis=0).astype(float)
        w = np.array(W, dtype=float)
        for _ in range(iters):
            # assign
            dists = ((X[:, None, :] - C[None, :, :]) ** 2).sum(axis=2)  # (n,k)
            A = np.argmin(dists, axis=1)
            # update
            for j in range(k):
                mask = A == j
                ww = w[mask]
                if ww.size == 0 or ww.sum() <= 0:
                    C[j] = X[random.randrange(n)]
                else:
                    C[j] = (X[mask] * ww[:, None]).sum(axis=0) / max(ww.sum(), 1e-9)
        return C, A
    else:
        # pure python
        C = [X[i][:] for i in pick]
        A = [0] * n
        for _ in range(iters):
            # assign
            for i in range(n):
                bestj = 0
                bestd = 1e18
                for j in range(k):
                    d = sum((X[i][d] - C[j][d]) ** 2 for d in range(len(X[i])))
                    if d < bestd:
                        bestd = d
                        bestj = j
                A[i] = bestj
            # update
            for j in range(k):
                num = [0.0] * len(X[0])
                den = 0.0
                for i in range(n):
                    if A[i] == j:
                        w = W[i]
                        den += w
                        for d in range(len(X[i])):
                            num[d] += X[i][d] * w
                if den > 0:
                    C[j] = [v / den for v in num]
        return C, A


def main():
    cfg = _cfg()
    now = time.time()
    start = (
        now - int(cfg.get("half_life_days", 21)) * 86400 * 3
    )  # read a few half-lives
    rows = _read_rows("out/nudges.csv", start)
    if len(rows) < int(cfg.get("min_events", 40)):
        print(json.dumps({"status": "insufficient_data", "rows": len(rows)}))
        return
    X = []
    W = []
    Y = []
    for ts, arm, rw in rows:
        x = _x_from_arm(arm)
        w = _decay(now, ts, float(cfg.get("half_life_days", 21)))
        X.append(x)
        W.append(w)
        Y.append(rw)
    if np is not None:
        X = np.array(X, dtype=float)
    k = int(cfg.get("k", 4))
    iters = int(cfg.get("iters", 25))
    C, A = _kmeans(X, W, k, iters)
    # stats
    seg_stats = [{"shows": 0, "clicks": 0} for _ in range(k)]
    for i, seg in enumerate(list(A if np is not None else A)):
        seg_stats[seg]["shows"] += 1
        seg_stats[seg]["clicks"] += 1 if Y[i] > 0 else 0
    for s in seg_stats:
        s["ctr"] = (s["clicks"] / s["shows"]) if s["shows"] > 0 else 0.0
    # names
    names = cfg.get("names", {}) or {}
    seg_names = {}
    for j in range(k):
        seg_names[str(j)] = names.get(j, names.get(str(j), f"Segment-{j}"))
    # write model
    model = {
        "feats": FEATS,
        "k": k,
        "centroids": (C.tolist() if np is not None else C),
        "stats": seg_stats,
        "names": seg_names,
        "generated_at": int(now),
    }
    os.makedirs("content", exist_ok=True)
    with open("content/acheron_model.yaml", "w") as f:
        yaml.safe_dump({"acheron_model": model}, f, sort_keys=False)
    print(json.dumps({"status": "ok", "k": k, "rows": len(rows)}))


if __name__ == "__main__":
    main()
