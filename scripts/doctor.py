#!/usr/bin/env python3
import os
import json
import time
from datetime import datetime

FILES = {
    "nudges": "out/nudges.csv",
    "passive": "out/passive_actions.csv",
    "vasquez_cfg": "content/vasquez.yaml",
    "vasquez_windows": "content/vasquez_windows.yaml",
    "policy": "content/policy.yaml",
    "feedback_policy": "content/feedback_policy.yaml",
    "weights": "content/propensity_weights.yaml",
    "ash_cfg": "content/ash.yaml",
    "ash_table": "content/ash_table.yaml",
    "acheron_cfg": "content/acheron.yaml",
    "acheron_model": "content/acheron_model.yaml",
    "newt_state": "out/newt_state.json",
    "bishop_state": "out/bishop_state.json",
}


def age_sec(p):
    try:
        return round(time.time() - os.path.getmtime(p), 2)
    except Exception:
        return None


def count_lines(p):
    try:
        with open(p, "r") as f:
            return sum(1 for _ in f)
    except Exception:
        return None


def read_yaml(path):
    try:
        import yaml

        return yaml.safe_load(open(path)) or {}
    except Exception:
        return {}


def in_quiet(quiet_hours):
    if not quiet_hours:
        return False
    now = datetime.now()
    minutes = now.hour * 60 + now.minute
    for rng in quiet_hours:
        try:
            a, b = rng.split("-")
            ah, am = map(int, a.split(":"))
            bh, bm = map(int, b.split(":"))
            start = ah * 60 + am
            end = bh * 60 + bm
            if start <= end:
                if start <= minutes <= end:
                    return True
            else:
                if minutes >= start or minutes <= end:
                    return True
        except Exception:
            pass
    return False


def main():
    stats = {
        k: {
            "present": os.path.exists(p),
            "age_s": age_sec(p) if os.path.exists(p) else None,
            "lines": (
                count_lines(p) if os.path.exists(p) and p.endswith(".csv") else None
            ),
        }
        for k, p in FILES.items()
    }

    pol = read_yaml(FILES["policy"]).get("policy", {})
    quiet = in_quiet(pol.get("quiet_hours", []))
    newt = {}
    try:
        if os.path.exists(FILES["newt_state"]):
            import json as _json

            newt = _json.load(open(FILES["newt_state"]))
    except Exception:
        newt = {}

    vw = read_yaml(FILES["vasquez_windows"]).get("windows", {})
    am = read_yaml(FILES["acheron_model"]).get("acheron_model", {})

    out = {
        "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "files": stats,
        "policy": {
            "quiet_hours": pol.get("quiet_hours"),
            "quiet_active": quiet,
            "budget_per_day": pol.get("budget_per_day"),
            "send_threshold": pol.get("send_threshold"),
        },
        "newt": {
            "cooldowns": (newt.get("cooldowns") or {}),
            "escalations": (newt.get("escalations") or {}),
        },
        "vasquez": {
            "categories": list(vw.keys()) if isinstance(vw, dict) else [],
            "count": len(vw) if isinstance(vw, dict) else 0,
        },
        "acheron": {
            "k": am.get("k"),
            "segments": list((am.get("names") or {}).values()),
            "generated_at": am.get("generated_at"),
        },
    }

    # lightweight suggestions
    sugg = []
    if stats["nudges"]["lines"] is not None and stats["nudges"]["lines"] < 50:
        sugg.append(
            "Low exposures in out/nudges.csv; consider: python3 scripts/replay_synthetic.py --days 14"
        )
    if not stats["vasquez_windows"]["present"]:
        sugg.append(
            "Train Vasquez windows: python3 scripts/vasquez_train_v2.py --days 30"
        )
    if not stats["acheron_model"]["present"]:
        sugg.append("Train Acheron segments: python3 scripts/acheron_train.py")
    if not stats["ash_table"]["present"]:
        sugg.append(
            "Train Ash uplift: python3 scripts/ash_train.py && python3 scripts/ash_report.py"
        )
    if quiet:
        sugg.append("Quiet hours active; sends will be gated.")

    out["suggestions"] = sugg
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
