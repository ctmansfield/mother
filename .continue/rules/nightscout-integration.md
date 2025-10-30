---
globs: analytics/preprocess/sources/nightscout_adapter.py
description: Use when building ingestion pipelines or referencing CGM data.
---

Add and maintain analytics/preprocess/sources/nightscout_adapter.py to fetch entries and treatments from an existing Nightscout installation using NIGHTSCOUT_URL and NIGHTSCOUT_API_SECRET env vars. Persist Parquet to storage/analytics/.
