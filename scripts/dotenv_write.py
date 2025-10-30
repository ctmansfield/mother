#!/usr/bin/env python3
import os
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".env")
    ap.add_argument("--nightscout-url", default=os.getenv("NIGHTSCOUT_URL", ""))
    ap.add_argument("--nightscout-token", default=os.getenv("NIGHTSCOUT_TOKEN", ""))
    ap.add_argument(
        "--nightscout-secret", default=os.getenv("NIGHTSCOUT_API_SECRET", "")
    )
    ap.add_argument(
        "--nightscout-verify", default=os.getenv("NIGHTSCOUT_VERIFY", "true")
    )
    args = ap.parse_args()

    lines = []
    if args.nightscout_url:
        lines.append(f"NIGHTSCOUT_URL={args.nightscout_url}")
    if args.nightscout_token:
        lines.append(f"NIGHTSCOUT_TOKEN={args.nightscout_token}")
    if args.nightscout_secret:
        lines.append(f"NIGHTSCOUT_API_SECRET={args.nightscout_secret}")
    if args.nightscout_verify:
        lines.append(f"NIGHTSCOUT_VERIFY={args.nightscout_verify}")

    if not lines:
        print("No values provided; nothing written.")
        return

    # Create or update .env (overwrites existing keys by appending; not idempotent merge)
    with open(args.out, "a") as f:
        for line in lines:
            f.write(line + "\n")
    print({"wrote": args.out, "keys": [key.split("=")[0] for key in lines]})


if __name__ == "__main__":
    main()
