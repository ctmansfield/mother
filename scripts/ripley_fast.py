#!/usr/bin/env python3
# Ripley: propensity scoring with NumPy fast path and pure-Python fallback.
import os
import math

try:
    import numpy as np
except Exception:
    np = None

FEATS = [
    "bias",
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


def load_yaml(path):
    try:
        import yaml

        with open(path, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def load_weights_map():
    w = load_yaml(os.path.join("content", "propensity_weights.yaml")) or {}
    wm = w.get("weights") if isinstance(w, dict) else None
    return wm or {"bias": -0.5}


def weights_vec():
    wm = load_weights_map()
    if np is not None:
        v = np.zeros(D, dtype=float)
        for i, k in enumerate(FEATS):
            v[i] = float(wm.get(k, 0.0))
        return v
    else:
        return [float(wm.get(k, 0.0)) for k in FEATS]


def feat_vec_from_arm(arm: str):
    parts = (arm or "").split("|")
    dp = parts[0] if len(parts) > 0 else ""
    tn = parts[1] if len(parts) > 1 else ""
    ch = parts[2] if len(parts) > 2 else ""
    ct = parts[3] if len(parts) > 3 else ""
    x = [0.0] * D
    x[0] = 1.0

    def set1(name):
        if name in FEATS:
            x[FEATS.index(name)] = 1.0

    set1(f"daypart_{dp}")
    set1(f"tone_{tn}")
    set1(f"channel_{ch}")
    set1(f"category_{ct}")
    return np.array(x, dtype=float) if np is not None else x


def sigmoid(z):
    try:
        return 1.0 / (1.0 + math.exp(-float(z)))
    except Exception:
        return 0.5


def score_arm(arm: str):
    w = weights_vec()
    x = feat_vec_from_arm(arm)
    if np is not None:
        z = float(x @ w)
    else:
        z = sum(xi * wi for xi, wi in zip(x, w))
    return sigmoid(z), z


def batch_score(candidates):
    """Return list of tuples (arm, p, z) sorted by p desc."""
    if not candidates:
        return []
    w = weights_vec()
    if np is not None:
        X = np.vstack([feat_vec_from_arm(a) for a in candidates])  # (n,D)
        z = X @ w
        ps = 1.0 / (1.0 + np.exp(-z))
        rows = [(a, float(ps[i]), float(z[i])) for i, a in enumerate(candidates)]
    else:
        rows = []
        for a in candidates:
            p, z = score_arm(a)
            rows.append((a, float(p), float(z)))
    rows.sort(key=lambda t: t[1], reverse=True)
    return rows
