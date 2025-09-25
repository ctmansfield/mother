#!/usr/bin/env python3
import argparse
import json
import scripts.lambert_runtime as lambert


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--category",
        required=True,
        choices=["hydration", "posture", "movement", "focus", "sleep"],
    )
    ap.add_argument("--tone", default="gentle", choices=["gentle", "humor", "strict"])
    ap.add_argument("--reasons", default="")
    args = ap.parse_args()
    text, meta = lambert.pick_text(args.category, args.tone, args.reasons)
    print(
        json.dumps(
            {"category": args.category, "tone": args.tone, "text": text, "meta": meta},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
