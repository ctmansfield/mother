#!/usr/bin/env python3
from __future__ import annotations
import os
import argparse
import pandas as pd


def ingest_meds_csv(source: str, out: str = "storage/analytics/meds.parquet") -> dict:
    """
    Ingest meds events from CSV. Expected columns:
      - ts: timestamp in ms or ISO8601
      - med: string (e.g., 'tadalafil', 'clonidine')
      - dose: numeric dose (optional; default 1)
    """
    assert os.path.exists(source), source
    df = pd.read_csv(source)
    if "ts" not in df.columns or "med" not in df.columns:
        raise ValueError("CSV must contain 'ts' and 'med' columns")

    try:
        ts = pd.to_numeric(df["ts"], errors="coerce")
        if ts.dropna().median() > 1e12:
            df["ts"] = ts.astype("Int64")
        else:
            df["ts"] = (ts * 1000.0).astype("Int64")
    except Exception:
        df["ts"] = (
            pd.to_datetime(df["ts"], errors="coerce", utc=True).astype("int64")
            // 1_000_000
        )

    if "dose" not in df.columns:
        df["dose"] = 1.0

    df = df[["ts", "med", "dose"]]
    df["med"] = df["med"].astype(str).str.strip()

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    df.to_parquet(out, index=False)
    return {"rows": len(df), "out": out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="Input CSV with ts,med[,dose]")
    ap.add_argument("--out", default="storage/analytics/meds.parquet")
    args = ap.parse_args()
    res = ingest_meds_csv(args.source, args.out)
    print(res)


if __name__ == "__main__":
    main()
