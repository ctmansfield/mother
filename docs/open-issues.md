# Open Issues


## Storage Engine Strategy (CSV → DuckDB/Postgres mirror)
- **Current**: CSV appends (nudges.csv, ash_log.csv, text_log.csv) for zero-latency selection.
- **Option A**: DuckDB for analytics (compact CSV→Parquet; run OLAP in-process). No changes to selection path.
- **Option B**: Postgres mirror (COPY batches) for dashboards/cross-data joins; keep selection path CSV-only.
- **Do later**
  - Add DuckDB helper (`scripts/duck_reports.py`) to compact to Parquet + common KPI queries.
  - Add Postgres backend toggle in `scripts/storage.py` (outbox → batch COPY).
  - Materialized views in PG: CTR by segment×tone×hour; retention & compression.
  - Decision checkpoint after N=1M events or when dashboards needed.
