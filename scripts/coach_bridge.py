#!/usr/bin/env python3
from __future__ import annotations
import os
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

import pandas as pd
import requests

WIN_PATH = os.getenv("WIN_PATH", "storage/analytics/windows.parquet")
RULES_PATH = os.getenv("AN_RULES_PATH", "analytics/rules/rules.json")
MOTHER_API = os.getenv("MOTHER_API", "http://127.0.0.1:8000")
USER_ID = os.getenv("USER_ID", "me")
CHANNEL = os.getenv("NOTIFY_CHANNEL", "email")
LEAD_MIN = int(os.getenv("NOTIFY_LEAD_MIN", "5"))


def load_latest_features(
    win_path: str, needed: List[str] | None = None
) -> Dict[str, Any]:
    df = pd.read_parquet(win_path)
    if df.empty:
        return {}
    row = df.iloc[-1]
    # If needed specified, use only those; else use numeric columns excluding labels/t0
    if needed:
        feats = {k: float(row[k]) for k in needed if k in row and pd.notna(row[k])}
    else:
        num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        num_cols = [
            c for c in num_cols if not c.startswith("y_") and c not in ("glucose",)
        ]
        feats = {k: float(row[k]) for k in num_cols if pd.notna(row[k])}
    return feats


def load_rule_features(rules_path: str) -> List[str]:
    try:
        with open(rules_path, "r") as f:
            obj = json.load(f)
        rules = obj.get("rules", []) if isinstance(obj, dict) else obj
        feats: List[str] = []
        for r in rules:
            for c in r.get("if_all", []):
                f = c.get("feature")
                if f and f not in feats:
                    feats.append(f)
        return feats
    except Exception:
        return []


def risk_score(features: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{MOTHER_API.rstrip('/')}/risk/score"
    body = {
        "user_id": USER_ID,
        "t0": datetime.now(timezone.utc).isoformat(),
        "current_features": features,
    }
    r = requests.post(url, json=body, timeout=10)
    r.raise_for_status()
    return r.json()


def create_reminder(title: str, note: str) -> Dict[str, Any]:
    url = f"{MOTHER_API.rstrip('/')}/api/reminders"
    due = (datetime.utcnow() + timedelta(minutes=LEAD_MIN)).isoformat() + "Z"
    body = {
        "user_id": USER_ID,
        "title": title,
        "note": note,
        "due_at": due,
        "channel": CHANNEL,
    }
    r = requests.post(url, json=body, timeout=10)
    r.raise_for_status()
    return r.json()


def main():
    rule_feats = load_rule_features(RULES_PATH)
    feats = load_latest_features(WIN_PATH, needed=rule_feats or None)
    if not feats:
        print({"ok": False, "reason": "no_features"})
        return
    res = risk_score(feats)
    trig = res.get("triggered_rules", [])
    if not trig:
        print({"ok": True, "triggered": 0})
        return
    # For each triggered event, create a reminder
    created = []
    for r in trig:
        ev = r.get("event")
        action = r.get("action") or "check_status"
        title = f"Risk: {ev}"
        note = f"Triggered rule {r.get('id')} -> action: {action}"
        try:
            created.append(create_reminder(title, note))
        except Exception as e:
            print({"error": str(e)})
    print(
        {
            "ok": True,
            "triggered": len(trig),
            "reminders": [c.get("id") for c in created],
        }
    )


if __name__ == "__main__":
    main()
