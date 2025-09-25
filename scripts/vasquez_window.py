#!/usr/bin/env python3
import json
from datetime import datetime


def load_yaml(path):
    try:
        import yaml

        with open(path, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default="movement")
    ap.add_argument("--hour", type=int)  # optional override
    args = ap.parse_args()

    vw = (load_yaml("content/vasquez_windows.yaml") or {}).get("vasquez_windows") or {}
    by = vw.get("by_category") or {}
    hours = (by.get(args.category) or {}).get("hours") or []
    now = datetime.now()
    hour = args.hour if args.hour is not None else now.hour
    allowed = hour in set(int(h) for h in hours)
    # compute next hour in hours list
    nxt = None
    if hours:
        cur = hour
        for i in range(1, 25):
            hh = (cur + i) % 24
            if hh in hours:
                nxt = hh
                break
    wait_s = None
    if nxt is not None:
        delta = (nxt - hour) % 24
        wait_s = int(delta * 3600)
    print(
        json.dumps(
            {
                "category": args.category,
                "hour": hour,
                "allowed": allowed,
                "allowed_hours": hours,
                "next_hour": nxt,
                "wait_s": wait_s,
            }
        )
    )


if __name__ == "__main__":
    main()
