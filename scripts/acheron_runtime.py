#!/usr/bin/env python3
import yaml

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


def _model():
    try:
        return (yaml.safe_load(open("content/acheron_model.yaml")) or {}).get(
            "acheron_model", {}
        )
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


def feat_vec_from_arm(arm):
    dp, tn, ch, ct = _parts(arm)
    x = [0.0] * D

    def set1(name):
        if name in FEATS:
            x[FEATS.index(name)] = 1.0

    set1(f"daypart_{dp}")
    set1(f"tone_{tn}")
    set1(f"channel_{ch}")
    set1(f"category_{ct}")
    return np.array(x, dtype=float) if np is not None else x


def assign_segment(arm):
    M = _model()
    C = M.get("centroids") or []
    if not C:
        return {"segment_id": None, "segment_name": "unknown", "ctr": None}
    x = feat_vec_from_arm(arm)
    if np is not None:
        Cnp = np.array(C, dtype=float)
        xnp = np.array(x, dtype=float)
        d = ((Cnp - xnp[None, :]) ** 2).sum(axis=1)
        j = int(np.argmin(d))
    else:
        bestj = 0
        bestd = 1e18
        for j in range(len(C)):
            d = sum((x[i] - C[j][i]) ** 2 for i in range(len(x)))
            if d < bestd:
                bestd = d
                bestj = j
        j = bestj
    names = M.get("names") or {}
    stats = M.get("stats") or []
    name = names.get(str(j), f"Segment-{j}")
    ctr = stats[j].get("ctr") if j < len(stats) else None
    return {"segment_id": j, "segment_name": name, "ctr": ctr}


def threshold_offset(name):
    cfg = _cfg()
    return float((cfg.get("threshold_offset") or {}).get(name, 0.0))


def weight_multipliers(segment_name):
    """Return dict of weight multipliers for w_r,w_d,w_g,w_w,w_u based on segment name."""
    try:
        cfg = _cfg()
        wm = cfg.get("weights_multiplier") or {}
        m = wm.get(segment_name, {})
        # defaults 1.0
        out = {"w_r": 1.0, "w_d": 1.0, "w_g": 1.0, "w_w": 1.0, "w_u": 1.0}
        for k in list(out.keys()):
            try:
                out[k] = float(m.get(k, out[k]))
            except Exception:
                pass
        return out
    except Exception:
        return {"w_r": 1.0, "w_d": 1.0, "w_g": 1.0, "w_w": 1.0, "w_u": 1.0}


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True)
    args = ap.parse_args()
    info = assign_segment(args.arm)
    info["threshold_offset"] = threshold_offset(info["segment_name"])
    print(json.dumps(info))
