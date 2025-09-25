#!/usr/bin/env python3
import os
import csv
import math
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


def feats_for_now(window_days=30):
    rows = read_nudges(
        "out/nudges.csv", start_ts=int(time.time()) - window_days * 86400
    )
    # same features as trainer but for "now"
    dt = datetime.now()
    h = dt.hour
    m = dt.minute
    xh = (h * 60 + m) / 1440.0 * 2 * math.pi
    hour_sin = math.sin(xh)
    hour_cos = math.cos(xh)
    dow = dt.weekday()
    shows = len(rows)
    clicks = sum(1 for r in rows if r[2] == 1)
    dismiss = sum(1 for r in rows if r[2] == 0)
    by_cat = {"hydration": [0, 0], "movement": [0, 0]}
    for ts, arm, rw in rows:
        parts = (arm or "").split("|")
        cat = parts[3] if len(parts) > 3 else ""
        if cat in by_cat:
            by_cat[cat][0] += 1
            if rw == 1:
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
    night_flag = 1.0 if (hour_cos < -0.3 or (h >= 22 or h < 7)) else 0.0
    row = [hour_sin, hour_cos, ctr_overall, ctr_hyd, ctr_move, dismiss_rate, night_flag]
    for d in range(7):
        row.append(1.0 if d == dow else 0.0)
    return row


def infer_segment(now_feats=None):
    cfg = (load_yaml("content/acheron.yaml") or {}).get("acheron", {})
    segs = (load_yaml("content/acheron_segments.yaml") or {}).get(
        "acheron_segments", {}
    )
    feat_names = segs.get("feat_names") or []
    C = segs.get("centroids") or []
    labels = segs.get("labels") or []
    if not C or not labels:
        return "baseline-you", {}
    x = now_feats or feats_for_now(cfg.get("window_days", 30))
    # nearest centroid (L2)
    if np is not None:
        X = np.array(x, dtype=float)
        Cn = np.array(C, dtype=float)
        d = ((Cn - X[None, :]) ** 2).sum(axis=1)
        j = int(np.argmin(d))
    else:
        best = 1e18
        j = 0
        for idx, c in enumerate(C):
            d = sum((c[i] - x[i]) ** 2 for i in range(len(c)))
            if d < best:
                best = d
                j = idx
    seg = labels[j] if j < len(labels) else "baseline-you"
    bias_map = cfg.get("bias") or {}
    bias = bias_map.get(
        seg,
        bias_map.get(
            "baseline-you",
            {
                "tone_pref": ["gentle", "humor", "strict"],
                "channel_pref": ["push", "in_app"],
                "threshold_delta": 0.0,
            },
        ),
    )
    return seg, bias
