import os
from typing import Optional, Dict, Any
from datetime import datetime, timezone

import requests
import pandas as pd
import hashlib

NS_URL = os.getenv("NIGHTSCOUT_URL", "")
NS_SECRET = os.getenv("NIGHTSCOUT_API_SECRET", "")
NS_TOKEN = os.getenv("NIGHTSCOUT_TOKEN", "")
NS_VERIFY = os.getenv("NIGHTSCOUT_VERIFY", "true").lower() not in ("0", "false", "no")

# Nightscout expects API-SECRET as a SHA1 hex of the secret in most setups.
# If user provides a 40-hex string, assume it's already hashed; otherwise hash it.
HEADERS = {}
if NS_SECRET:
    sec = NS_SECRET.strip()
    already_hex = len(sec) == 40 and all(c in "0123456789abcdefABCDEF" for c in sec)
    api_secret = sec if already_hex else hashlib.sha1(sec.encode("utf-8")).hexdigest()
    HEADERS["API-SECRET"] = api_secret


def _iso(dt_: datetime) -> str:
    if dt_.tzinfo is None:
        dt_ = dt_.replace(tzinfo=timezone.utc)
    return dt_.astimezone(timezone.utc).isoformat()


def fetch_entries(
    start: Optional[datetime] = None, end: Optional[datetime] = None, count: int = 1000
) -> pd.DataFrame:
    """
    Fetch CGM SGV entries from Nightscout.
    Returns DataFrame with columns: ts (ns), sgv (mg/dL), direction, type
    """
    assert NS_URL, "Set NIGHTSCOUT_URL env var"
    params: Dict[str, Any] = {"count": count}
    if NS_TOKEN:
        params["token"] = NS_TOKEN
    if start:
        params["find[dateString][$gte]"] = _iso(start)
    if end:
        params["find[dateString][$lte]"] = _iso(end)
    url = f"{NS_URL.rstrip('/')}/api/v1/entries/sgv.json"
    r = requests.get(url, headers=HEADERS, params=params, timeout=30, verify=NS_VERIFY)
    r.raise_for_status()
    data = r.json()
    if not data:
        return pd.DataFrame(columns=["ts", "sgv", "direction", "type"])  # empty
    # Nightscout returns ms since epoch in 'date'
    rows = []
    for it in data:
        ts_ms = it.get("date")
        if ts_ms is None:
            ds = it.get("dateString")
            try:
                ts_ms = int(pd.Timestamp(ds).value // 1_000_000)
            except Exception:
                continue
        rows.append(
            {
                "ts": int(ts_ms),
                "sgv": it.get("sgv"),
                "direction": it.get("direction"),
                "type": it.get("type", "sgv"),
            }
        )
    df = pd.DataFrame(rows).sort_values("ts")
    return df


def fetch_treatments(
    start: Optional[datetime] = None, end: Optional[datetime] = None, count: int = 1000
) -> pd.DataFrame:
    assert NS_URL, "Set NIGHTSCOUT_URL env var"
    params: Dict[str, Any] = {"count": count}
    if NS_TOKEN:
        params["token"] = NS_TOKEN
    if start:
        params["find[created_at][$gte]"] = _iso(start)
    if end:
        params["find[created_at][$lte]"] = _iso(end)
    url = f"{NS_URL.rstrip('/')}/api/v1/treatments.json"
    r = requests.get(url, headers=HEADERS, params=params, timeout=30, verify=NS_VERIFY)
    r.raise_for_status()
    data = r.json()
    if not data:
        return pd.DataFrame(
            columns=["ts", "event", "carbs", "insulin", "notes"]
        )  # empty
    rows = []
    for it in data:
        try:
            ts_ms = int(pd.Timestamp(it.get("created_at")).value // 1_000_000)
        except Exception:
            continue
        event = it.get("eventType") or it.get("event_type") or it.get("event")
        rows.append(
            {
                "ts": ts_ms,
                "event": event,
                "carbs": it.get("carbs"),
                "insulin": it.get("insulin"),
                "notes": it.get("notes") or it.get("notes_text"),
            }
        )
    return pd.DataFrame(rows).sort_values("ts")


def save_parquet(df: pd.DataFrame, path: str):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    df.to_parquet(path, index=False)


def incremental_sync(days: int = 14):
    """
    Pull last N days of entries and treatments; write to storage/analytics.
    """
    end = datetime.now(timezone.utc)
    start = end - pd.Timedelta(days=days)
    entries = fetch_entries(start, end, count=10_000)
    treatments = fetch_treatments(start, end, count=10_000)
    save_parquet(entries, "storage/analytics/cgm.parquet")
    save_parquet(treatments, "storage/analytics/treatments.parquet")
    return {"entries": len(entries), "treatments": len(treatments)}


if __name__ == "__main__":
    out = incremental_sync(days=int(os.getenv("NS_SYNC_DAYS", "14")))
    print(out)
