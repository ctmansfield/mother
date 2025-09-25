#!/usr/bin/env python3
import os
import json
import csv
import time
from collections import deque, defaultdict


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


def _cfg():
    return (load_yaml("content/gorman.yaml") or {}).get("gorman", {})


def _model():
    cfg = _cfg()
    path = cfg.get("model_path", "out/gorman_model.json")
    if not os.path.exists(path):
        return {"order": int(cfg.get("order", 3)), "counts": {}}
    try:
        return json.load(open(path))
    except Exception:
        return {"order": int(cfg.get("order", 3)), "counts": {}}


def _recent_context(order, window_days):
    start = time.time() - window_days * 86400
    ctx = []
    try:
        with open("out/nudges.csv", "r") as f:
            rd = csv.reader(f)
            for r in rd:
                if not r or len(r) < 2:
                    continue
                ts = int(r[0])
                arm = r[1]
                if ts < start:
                    continue
                ct = parts(arm)[3]
                if ct:
                    ctx.append((ts, ct))
    except Exception:
        pass
    ctx.sort(key=lambda t: t[0])
    last = deque([c for _, c in ctx[-order:]], maxlen=order)
    return list(last)


def _normalize(d):
    s = sum(max(0.0, v) for v in d.values())
    if s <= 0:
        return {k: 0.0 for k in d}
    return {k: max(0.0, v) / s for k, v in d.items()}


def _prior(fallback):
    cats = ["hydration", "posture", "movement", "focus", "sleep"]
    if fallback == "uniform":
        return {c: 1.0 / len(cats) for c in cats}
    # frequency prior from all-time logs (unweighted)
    freq = defaultdict(float)
    try:
        with open("out/nudges.csv", "r") as f:
            rd = csv.reader(f)
            for r in rd:
                if not r or len(r) < 2:
                    continue
                ct = parts(r[1])[3]
                if ct:
                    freq[ct] += 1.0
    except Exception:
        pass
    if not freq:
        return {c: 1.0 / len(cats) for c in cats}
    return _normalize(freq)


def _interp(d_high, d_low, lam):
    out = defaultdict(float)
    for k, v in d_low.items():
        out[k] += (1.0 - lam) * v
    for k, v in d_high.items():
        out[k] += lam * v
    return dict(out)


def _predict_dist():
    cfg = _cfg()
    order = int(cfg.get("order", 3))
    window_days = int(cfg.get("window_days", 45))
    min_events = float(cfg.get("min_events", 20))
    add_alpha = float(cfg.get("add_alpha", 0.5))
    backoff = float(cfg.get("backoff", 0.4))
    fallback = str(cfg.get("fallback_prior", "uniform"))

    M = _model()
    ctx = _recent_context(order, window_days)
    # backoff from full order -> 1
    dist = None
    for k in range(order, 0, -1):
        key = "|".join(ctx[-(k - 1) :]) if (k - 1) > 0 else ""
        table = (M.get("counts") or {}).get(str(k)) or {}
        row = table.get(key) or {}
        tot = sum(row.values())
        if tot >= min_events:
            sm = {
                c: (row.get(c, 0.0) + add_alpha)
                for c in ["hydration", "posture", "movement", "focus", "sleep"]
            }
            sm = _normalize(sm)
            dist = sm if dist is None else _interp(sm, dist, backoff)
    if dist is None:
        dist = _prior(fallback)
    return dist


def score_candidates(candidates):
    """Return {arm: score in [0,1]} from predicted P(next category | recent ctx)."""
    dist = _predict_dist()
    out = {}
    for a in candidates:
        ct = parts(a)[3]
        out[a] = float(dist.get(ct, 0.0))
    # rescale to [0,1]
    vals = list(out.values())
    if vals:
        lo = min(vals)
        hi = max(vals)
        if hi > lo:
            for k in out:
                out[k] = (out[k] - lo) / (hi - lo)
    return out


def score_arm(arm):
    return score_candidates([arm]).get(arm, 0.0)
