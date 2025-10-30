#!/usr/bin/env python3
from __future__ import annotations
import pandas as pd

cols = [
    "cgm_delta_10",
    "cgm_delta_30",
    "slope_15",
    "pct_time_below_70_2h",
    "pct_time_below_70_4h",
    "rmssd_lag15",
    "med_tadalafil_decay",
    "minutes_since_meal",
]

df = pd.read_parquet("storage/analytics/windows.parquet")
row = df.iloc[-1]
print("latest row index:", row.name)
for c in cols:
    if c in row.index:
        v = None if pd.isna(row[c]) else float(row[c])
        print(f"{c} = {v}")
