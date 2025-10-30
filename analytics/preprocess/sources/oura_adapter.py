#!/usr/bin/env python3
from __future__ import annotations
import os
import argparse
import pandas as pd

"""
Oura HRV adapter (CSV to Parquet)

Accepts a CSV export with at least a timestamp and RMSSD value.
Common Oura exports may name columns like:
- 'timestamp' or 'datetime' (ISO8601)
- 'rmssd' or 'hrv_rmssd_ms' or 'rmssd_millisecond'

Usage:
  python analytics/preprocess/sources/oura_adapter.py --source oura_hrv.csv --out storage/analytics/hrv.parquet
Optional:
  --tscol timestamp --rmssdcol rmssd_millisecond
"""


def ingest_oura_hrv_csv(
    source: str,
    out: str = "storage/analytics/hrv.parquet",
    tscol: str | None = None,
    rmssdcol: str | None = None,
) -> dict:
    assert os.path.exists(source), source
    df = pd.read_csv(source)
    # Guess columns if not provided
    if tscol is None:
        for c in ["timestamp", "datetime", "time", "start_time", "date"]:
            if c in df.columns:
                tscol = c
                break
    if rmssdcol is None:
        for c in ["rmssd", "hrv_rmssd_ms", "rmssd_millisecond", "rmssd_ms"]:
            if c in df.columns:
                rmssdcol = c
                break
    if tscol is None or rmssdcol is None:
        raise ValueError(
            "Could not infer ts or rmssd column; provide --tscol and --rmssdcol"
        )

    ts = pd.to_datetime(df[tscol], errors="coerce", utc=True)
    ms = (ts.astype("int64") // 1_000_000).astype("Int64")
    outdf = pd.DataFrame(
        {"ts": ms, "rmssd": pd.to_numeric(df[rmssdcol], errors="coerce")}
    ).dropna()
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    outdf.to_parquet(out, index=False)
    return {"rows": len(outdf), "out": out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", default="storage/analytics/hrv.parquet")
    ap.add_argument("--tscol", default=None)
    ap.add_argument("--rmssdcol", default=None)
    args = ap.parse_args()
    res = ingest_oura_hrv_csv(
        args.source, args.out, tscol=args.tscol, rmssdcol=args.rmssdcol
    )
    print(res)


if __name__ == "__main__":
    main()
