#!/usr/bin/env python3
import os
import csv
import time

try:
    import numpy as np
except Exception:
    np = None

NUDGES = "out/nudges.csv"


def load_yaml(path):
    try:
        import yaml

        with open(path, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _cfg():
    return (load_yaml("content/dallas.yaml") or {}).get("dallas", {})


def _read_feedback(start_ts):
    """Yield (ts, arm, reward) where reward in {0,1}. Ignores exposure-only rows."""
    if not os.path.exists(NUDGES):
        return []
    out = []
    with open(NUDGES, "r") as f:
        rd = csv.reader(f)
        for r in rd:
            if not r:
                continue
            try:
                ts = int(r[0])
                arm = r[1]
                rw = r[2] if len(r) > 2 and r[2] != "" else None
            except Exception:
                continue
            if ts < start_ts or rw is None:
                continue
            try:
                reward = int(rw)
                if reward in (0, 1):
                    out.append((ts, arm, reward))
            except Exception:
                continue
    return out


def _arm_parts(arm):
    p = (arm or "").split("|")
    return (
        p[0] if len(p) > 0 else "",
        p[1] if len(p) > 1 else "",
        p[2] if len(p) > 2 else "",
        p[3] if len(p) > 3 else "",
    )


def _key_for(arm, level):
    dp, tn, ch, ct = _arm_parts(arm)
    if level == "category_tone_channel":
        return f"{ct}|{tn}|{ch}"
    return f"{dp}|{tn}|{ch}|{ct}"  # full arm


def score_candidates(candidates, now=None):
    """Return dict {arm: dallas_score in [0,1]} with recency-decayed, smoothed CTR."""
    cfg = _cfg()
    window_days = int(cfg.get("window_days", 45))
    half = float(cfg.get("half_life_days", 14))
    alpha = float(cfg.get("alpha", 1.0))
    beta = float(cfg.get("beta", 3.0))
    level = str(cfg.get("level", "arm"))
    start_ts = int((now or time.time())) - window_days * 86400
    fb = _read_feedback(start_ts)
    if not fb:
        return {a: 0.0 for a in candidates}
    # aggregate
    pos = {}
    tot = {}

    def add(k, w, r):
        tot[k] = tot.get(k, 0.0) + w
        if r == 1:
            pos[k] = pos.get(k, 0.0) + w

    for ts, arm, r in fb:
        age_days = ((now or time.time()) - ts) / 86400.0
        w = 0.5 ** (age_days / half) if half > 0 else 1.0
        k = _key_for(arm, level)
        add(k, w, r)
    # compute scores
    scores = {}
    for a in candidates:
        k = _key_for(a, level)
        t = tot.get(k, 0.0)
        p = pos.get(k, 0.0)
        if t < float(cfg.get("min_events", 12)):
            scores[a] = 0.0
        else:
            scores[a] = (alpha + p) / (alpha + beta + t)
    # normalize to [0,1] for mixing
    if scores:
        vals = [v for v in scores.values()]
        lo = min(vals)
        hi = max(vals)
        if hi > lo:
            for k in scores:
                scores[k] = (scores[k] - lo) / (hi - lo)
    return scores
