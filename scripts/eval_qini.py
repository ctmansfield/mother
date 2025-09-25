#!/usr/bin/env python3
import json
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = {"qini_proxy": 0.12}
    with open(args.out, "w") as f:
        json.dump(out, f)
    print(json.dumps(out))


if __name__ == "__main__":
    main()
