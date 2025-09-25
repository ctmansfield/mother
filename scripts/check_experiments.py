#!/usr/bin/env python3
from datetime import datetime

ALLOWED_TONES = {"gentle", "humor", "strict"}
ALLOWED_CHANNELS = {"push", "in_app"}


def load_yaml(path):
    try:
        import yaml

        with open(path, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def main():
    cfg = load_yaml("content/experiments.yaml") or {}
    exps = cfg.get("experiments") or []
    problems = 0
    for e in exps:
        eid = e.get("id")
        cat = e.get("category")
        var = e.get("variants") or {}
        if not eid:
            print("error: experiment missing id")
            problems += 1
        if not cat:
            print(f"error: {eid}: missing category")
            problems += 1
        # dates
        for k in ("start", "end"):
            v = e.get(k)
            if v:
                try:
                    datetime.fromisoformat(v)
                except Exception:
                    print(f"error: {eid}: bad {k}='{v}' (YYYY-MM-DD)")
                    problems += 1
        # traffic
        t = e.get("traffic", 1.0)
        try:
            t = float(t)
            if not (0.0 <= t <= 1.0):
                raise ValueError()
        except Exception:
            print(f"error: {eid}: traffic must be 0..1 (got {t})")
            problems += 1
        # variants & weights
        if not var:
            print(f"error: {eid}: no variants")
            problems += 1
            continue
        wsum = 0.0
        for name, meta in var.items():
            tone = meta.get("tone")
            ch = meta.get("channel")
            w = meta.get("weight", 0.0)
            if tone not in ALLOWED_TONES:
                print(f"error: {eid}.{name}: bad tone '{tone}'")
                problems += 1
            if ch not in ALLOWED_CHANNELS:
                print(f"error: {eid}.{name}: bad channel '{ch}'")
                problems += 1
            try:
                w = float(w)
            except Exception:
                print(f"error: {eid}.{name}: weight not a number")
                problems += 1
                w = 0.0
            if w < 0:
                print(f"error: {eid}.{name}: weight negative")
                problems += 1
            wsum += w
        if wsum <= 0:
            print(f"error: {eid}: total weight must be >0")
            problems += 1
    if problems == 0:
        print("experiments.yaml: OK")
    else:
        print(f"experiments.yaml: {problems} problem(s) found")


if __name__ == "__main__":
    main()
