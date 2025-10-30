#!/usr/bin/env python3
from __future__ import annotations
import os
import argparse
import json
from datetime import datetime, timezone
import hashlib
import requests

NS_URL = os.getenv("NIGHTSCOUT_URL", "")
NS_TOKEN = os.getenv("NIGHTSCOUT_TOKEN", "")
NS_SECRET = os.getenv("NIGHTSCOUT_API_SECRET", "")
NS_VERIFY = os.getenv("NIGHTSCOUT_VERIFY", "true").lower() not in ("0", "false", "no")


def api_secret_header() -> dict:
    if not NS_SECRET:
        return {}
    sec = NS_SECRET.strip()
    already_hex = len(sec) == 40 and all(c in "0123456789abcdefABCDEF" for c in sec)
    api_secret = sec if already_hex else hashlib.sha1(sec.encode("utf-8")).hexdigest()
    return {"API-SECRET": api_secret}


def post_treatment(
    carbs: float, insulin: float | None, notes: str | None, created_at: str | None
) -> dict:
    assert NS_URL, "Set NIGHTSCOUT_URL env var"
    url = f"{NS_URL.rstrip('/')}/api/v1/treatments.json"
    params = {}
    if NS_TOKEN:
        params["token"] = NS_TOKEN
    headers = {"Content-Type": "application/json"}
    headers.update(api_secret_header())
    if created_at is None:
        created_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "eventType": "Meal Bolus",
        "created_at": created_at,
        "carbs": carbs,
    }
    if insulin is not None:
        payload["insulin"] = insulin
    if notes:
        payload["notes"] = notes
    r = requests.post(
        url, params=params, headers=headers, json=payload, timeout=15, verify=NS_VERIFY
    )
    r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser(
        description="Add a meal (carbs) to Nightscout treatments via API"
    )
    ap.add_argument("--carbs", type=float, required=True, help="grams of carbohydrate")
    ap.add_argument(
        "--insulin", type=float, default=None, help="bolus units (optional)"
    )
    ap.add_argument("--notes", default=None, help="notes (optional)")
    ap.add_argument(
        "--created-at", default=None, help="ISO8601 UTC timestamp, default now"
    )
    args = ap.parse_args()

    res = post_treatment(args.carbs, args.insulin, args.notes, args.created_at)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
