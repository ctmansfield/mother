#!/usr/bin/env python3
import json
import csv
import random
import argparse
from pathlib import Path
from models.bishop.bandit import BishopBandit


def reward_for_arm(arm):
    base = 0.18
    if "afternoon" in arm:
        base += 0.03
    if "gentle" in arm:
        base += 0.02
    if "hydration" in arm:
        base += 0.01
    return min(max(base, 0.01), 0.8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--out", default="out/report.json")
    args = ap.parse_args()
    Path("out").mkdir(parents=True, exist_ok=True)
    arms = [
        f"{t}|{tone}|{ch}|{cat}"
        for t in ["morning", "midday", "afternoon", "evening"]
        for tone in ["gentle", "humor", "strict"]
        for ch in ["push", "in_app"]
        for cat in ["hydration", "posture", "movement", "focus"]
    ]
    bandit = BishopBandit(arms)
    nudges_csv = "out/nudges.csv"
    shows = 0
    clicks = 0
    base_clicks = 0
    with open(nudges_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ts", "arm", "reward"])
        ts = 0
        for d in range(args.days):
            for i in range(40):
                arm = bandit.select()
                prob = reward_for_arm(arm)
                r = 1.0 if random.random() < prob else 0.0
                bandit.update(arm, r)
                w.writerow([ts, arm, int(r)])
                ts += 1
                shows += 1
                clicks += r
                base = 0.18
                base_clicks += 1.0 if random.random() < base else 0.0
    report = {
        "CTR_bandit": round(clicks / shows, 4),
        "CTR_baseline": round(base_clicks / shows, 4),
        "shows": shows,
    }
    with open(args.out, "w") as f:
        json.dump(report, f)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
