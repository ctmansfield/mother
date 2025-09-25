#!/usr/bin/env python3
import csv
import os
import argparse


def load_yaml(p):
    try:
        import yaml

        with open(p, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--source", required=True, help="CSV with columns: ts,event,value[,category]"
    )
    ap.add_argument("--out", default="out/passive_actions.csv")
    args = ap.parse_args()
    cfg = (load_yaml("content/passive_actions.yaml") or {}).get("passive", {})
    evmap = cfg.get("map") or {}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    # Write header if missing
    need_header = not os.path.exists(args.out)
    with open(args.out, "a", newline="") as w:
        wr = csv.writer(w)
        if need_header:
            wr.writerow(["ts", "event", "value", "category"])
        with open(args.source, "r") as f:
            r = csv.DictReader(f)
            for row in r:
                ts = int(float(row.get("ts", 0)) or 0)
                ev = row.get("event", "").strip()
                val = row.get("value", "").strip()
                cat = row.get("category", "").strip() or evmap.get(ev, "")
                if ts and ev:
                    wr.writerow([ts, ev, val, cat])
    print({"ingested": args.source, "out": args.out})


if __name__ == "__main__":
    main()
