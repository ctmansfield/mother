#!/usr/bin/env python3
import csv
import time
import argparse


def load_yaml(path):
    try:
        import yaml

        with open(path, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def decay_weight(ts, now, half_days):
    if not half_days or half_days <= 0:
        return 1.0
    age_days = (now - ts) / 86400.0
    return 0.5 ** (age_days / half_days)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--algo", choices=["linucb", "thompson"], required=True)
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--nudges", default="out/nudges.csv")
    args = ap.parse_args()

    cfg = (load_yaml("content/bishop.yaml") or {}).get("bishop", {})
    half = float(cfg.get("half_life_days", 21))
    reward_cap = float(cfg.get("reward_cap", 1.0))

    now = time.time()
    start = now - args.days * 86400

    if args.algo == "linucb":
        import scripts.bishop_linucb as B

        band = B.LinUCBBandit()
    else:
        import scripts.bishop_thompson as B

        band = B.ThompsonBandit()

    # Only consume rows that include reward (feedback events)
    try:
        with open(args.nudges, "r") as f:
            rd = csv.reader(f)
            for r in rd:
                if not r or len(r) < 3 or r[2] == "":
                    continue
                try:
                    ts = int(r[0])
                    arm = r[1]
                    rw = float(r[2])
                except Exception:
                    continue
                if ts < start:
                    continue
                w = decay_weight(ts, now, half)
                band.update(arm, max(0.0, min(reward_cap, rw)) * w)
    except Exception:
        pass
    print({"trained": args.algo})


if __name__ == "__main__":
    main()
