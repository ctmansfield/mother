# ADR-0002: Memory Adapter & CLI for mother

**Status:** Proposed
**Date:** 2025-09-25

This ADR ships a minimal, pluggable **memory framework** that matches ADR‑0001 (pgvector). It introduces:

- `mother/memory/adapter.py`: read/write API to Postgres+pgvector
- `mother/memory/embedders.py`: pluggable embedders (local SentenceTransformer; fast fallback hashing)
- `mother/memory/sql.py`: parameterized SQL
- `scripts/memory_cli.py`: CLI for upsert/search smoke tests

All files are **additive**; no edits to existing files. Integration with FastAPI/worker can happen next.

## Configuration

The adapter reads from environment variables (all optional, with sane defaults):

```
PGHOST=192.168.1.225
PGPORT=55432
PGDATABASE=mother
PGUSER=mother
PGPASSWORD=***

EMBEDDING_MODEL=bge-large-en-v1.5  # SentenceTransformer model id; if not installed, fallback embedder is used
EMBEDDING_DIM=1024                 # dimension for pgvector column; adapter pads/truncates as needed
MEMORY_TOPK=50
MEMORY_DISTANCE=cosine             # cosine|l2|ip
```

## CLI examples

```
# Upsert a memory
python -m scripts.memory_cli upsert --user u_chad --text "Repo root is /root/genomics-stack" --type autobio --pin

# Search memories
python -m scripts.memory_cli search --user u_chad --query "genomics repo path" --limit 10
```

## Notes

- If `sentence-transformers` (and its backend, e.g., PyTorch) is not installed, the adapter uses a **hash-based fallback** so smoke tests still run.
- The SQL assumes ADR‑0001 migration was applied and the table `memory_item(embedding vector(1024))` exists.
- Retrieval uses `embedding <-> query` distance with appropriate operator for the chosen metric.
