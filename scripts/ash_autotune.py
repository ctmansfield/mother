#!/usr/bin/env python3
import yaml
import json
import statistics
from datetime import datetime


def load_yaml(p):
    try:
        with open(p, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return {}


def main():
    tab = (load_yaml("content/ash_table.yaml") or {}).get("ash_table", {})
    upl = tab.get("uplift") or {}
    # collect per-category values from exact keys "cat|..."
    by = {}
    for k, v in upl.items():
        parts = k.split("|")
        if not parts or parts[0] in ("*", "", None):
            continue
        cat = parts[0]
        by.setdefault(cat, []).append(float(v))
    tau_by = {}
    for cat, vals in by.items():
        vals = sorted(vals, reverse=True)
        best_tau = None
        best_obj = -1
        # objective: maximize (#>=tau)*mean(>=tau)
        for i, x in enumerate(vals):
            n = i + 1
            mean = sum(vals[:n]) / n
            obj = n * mean
            if obj > best_obj:
                best_obj = obj
                best_tau = x
        if best_tau is None and vals:
            best_tau = statistics.median(vals)
        tau_by[cat] = round(float(best_tau if best_tau is not None else 0.01), 4)
    # write
    out = {
        "ash_tau": {
            "generated_at": datetime.now().isoformat(),
            "tau_by_category": tau_by,
        }
    }
    with open("content/ash_tau.yaml", "w") as f:
        yaml.safe_dump(out, f, sort_keys=False)
    print(json.dumps(out))


if __name__ == "__main__":
    main()
