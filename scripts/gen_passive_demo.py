#!/usr/bin/env python3
# Creates synthetic passive actions around Ash exposures for quick testing.
import csv
import os
import random
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--rate",
        type=float,
        default=0.35,
        help="base action rate for treatment; control ~ base*0.7",
    )
    ap.add_argument("--out", default="out/passive_actions.csv")
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    need_header = not os.path.exists(args.out)
    with open("out/ash_log.csv", "r") as f, open(args.out, "a", newline="") as w:
        r = csv.DictReader(f)
        wr = csv.writer(w)
        if need_header:
            wr.writerow(["ts", "event", "value", "category"])
        for row in r:
            ts = int(row["ts"])
            arm = row["arm"]
            cat = row["category"]
            treat = int(row["treatment"])
            # modest uplift: treatment more likely to act
            p = args.rate if treat == 1 else args.rate * 0.7
            if random.random() < p:
                ev = {
                    "hydration": "water_intake_ml",
                    "movement": "steps_delta",
                    "posture": "posture_corrected",
                    "focus": "focus_session_start",
                    "sleep": "winddown_on",
                }.get(cat, "steps_delta")
                wr.writerow([ts + random.randint(60, 1200), ev, "1", cat])
    print({"demo_written": args.out})


if __name__ == "__main__":
    main()
