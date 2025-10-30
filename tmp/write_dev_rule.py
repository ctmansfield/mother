#!/usr/bin/env python3
from __future__ import annotations
import os
import json
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feature", default="cgm_delta_10")
    ap.add_argument("--op", default="<=")
    ap.add_argument("--value", type=float, default=-5)
    ap.add_argument("--event", default="night_hypo_60m")
    ap.add_argument("--action", default="slow_carb_protein_snack")
    ap.add_argument("--out", default="analytics/rules/rules.json")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    rule = {
        "id": "dev_rule_1",
        "event": args.event,
        "if_all": [{"feature": args.feature, "op": args.op, "value": args.value}],
        "action": args.action,
    }
    with open(args.out, "w") as f:
        json.dump({"rules": [rule]}, f, indent=2)
    print({"wrote": args.out, "rule": rule})


if __name__ == "__main__":
    main()
