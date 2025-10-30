#!/usr/bin/env python3
from __future__ import annotations
import os
import argparse
import pandas as pd


def ingest_intake_csv(
    source: str, out: str = "storage/analytics/intake.parquet"
) -> dict:
    """
    Ingest electrolytes intake from CSV. Expected columns:
      - ts: timestamp in ms or ISO8601
      - type: one of {'Na','K','Mg'}
      - amount: numeric amount (e.g., mEq for Na/K, mg for Mg)
    """
    assert os.path.exists(source), source
    df = pd.read_csv(source)
    required = {"ts", "type", "amount"}
    if not required.issubset(df.columns):
        raise ValueError(f"CSV must contain {required}")

    # normalize ts
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

    df = df[["ts", "type", "amount"]]
    # sanitize type
    df["type"] = df["type"].str.strip().str.title()
    df = df[df["type"].isin(["Na", "K", "Mg"])]

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    df.to_parquet(out, index=False)
    return {"rows": len(df), "out": out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="Input CSV with ts,type,amount")
    ap.add_argument("--out", default="storage/analytics/intake.parquet")
    args = ap.parse_args()
    res = ingest_intake_csv(args.source, args.out)
    print(res)


if __name__ == "__main__":
    main()
