#!/usr/bin/env python3
import csv
import random
import argparse
from datetime import date, timedelta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--out", default="data/fixtures/vitals.csv")
    args = ap.parse_args()

    start = date.today() - timedelta(days=args.days - 1)
    rhr_base = random.randint(58, 66)
    hrv_base = random.randint(55, 70)
    steps_base = 7500
    sleep_base = 420  # minutes

    rows = [["date", "resting_hr", "hrv", "steps", "sleep_min"]]
    for i in range(args.days):
        d = start + timedelta(days=i)
        # gentle variance
        rhr = rhr_base + random.choice([-2, -1, 0, 0, 1, 2, 3])
        hrv = hrv_base + random.choice([-6, -4, -2, 0, 2, 4, 6])
        steps = int(
            steps_base + random.choice([-2500, -1500, -800, 0, 800, 1500, 2500])
        )
        sleep = sleep_base + random.choice([-60, -30, 0, 0, 30, 60])
        # inject signals
        if i in (args.days - 2, args.days - 1):  # last two days higher HR
            rhr += 8
        if i == args.days - 1:  # last day lower HRV
            hrv -= 12
        rows.append([d.isoformat(), rhr, hrv, steps, sleep])

    with open(args.out, "w", newline="") as f:
        csv.writer(f).writerows(rows)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
