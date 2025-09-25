# ADR-0001: Long-term Memory via pgvector (RAG) for **mother (Nostromo)**

**Status:** Proposed
**Date:** 2025-09-25

## Context

`mother` runs a local LLM via Ollama (e.g., `llama3.1:8b`) and uses Postgres at `192.168.1.225:55432` for persistence, with FastAPI/API and a worker running via Docker Compose on a coach VM. We want cross-session memory (autobiographical, episodic, semantic, procedural) that is local-first, auditable, and controllable.

## Goals & Constraints

- **Local-first**: no external SaaS calls required for memory.
- **Deterministic-ish**: stable embeddings and reproducible retrieval.
- **Composable**: independent memory service layer callable from API and worker.
- **Minimal drift**: canonical facts update-in-place (not duplicated).
- **Security**: at-rest encryption (disk), redact/avoid volatile secrets.
- **Ops**: SQL-native migrations; easy backup/restore; observability.
- **Performance**: sub-50ms ANN on ≤100k items on single host; degrade gracefully.

## High-Level Architecture

```
+-----------------+           +-------------------------+
| FastAPI (API)   | <-------> | Memory Service (adapter)|
| Worker (nudges) |           |  - write path           |
+-----------------+           |  - read path            |
        ^                     +-----------+-------------+
        |                                 |
        |                                 v
        |                       +------------------+
        |                       | Postgres (pgvec) |
        |                       |  tables & idx    |
        |                       +------------------+
        |                                 ^
        v                                 |
+-----------------+             +---------+--------+
| Ollama LLM      |             | Embedder (bge)   |
| (llama3.1:8b)   |             | sentence-tx local|
+-----------------+             +------------------+
```

- **Embedder**: `BAAI/bge-large-en-v1.5` (1024-dim) by default; allow `gte-small` (384) for speed. Record `embedding_model` and `embedding_dim` on each row.
- **Vector store**: **pgvector** inside existing Postgres instance; IVF/HNSW indexes per pgvector version.
- **Retriever**: k-NN + optional BM25 hybrid; recency/tag boosts.
- **Reranker**: optional `cross-encoder/ms-marco-MiniLM-L-6-v2` when k is large.
- **Memory manager**: write-time dedup/merge, TTL, pinning, consolidation.

## Data Model (DDL excerpt)

See migration `20250925_add_memory_tables.sql`. Summary:

- `memory_item(id, user_id, type, text, tags, ts_created, ts_seen, confidence, ttl_days, retention_policy, embedding_model, embedding_dim, payload)`
- `embedding VECTOR` column sized to model dim (e.g., 1024).
- Indexes:
  - `ivfflat` or `hnsw` on `embedding` (cosine).
  - `GIN` on `tags` (array) and `payload` (jsonb_path_ops).
  - `btree` on `(user_id, type, ts_seen desc)`.

## Write Path

1. **Extract** memory candidates from events (chat/user/tool).
2. **Normalize & chunk** to ≤512 tokens; keep 20–30 token overlap when chunked.
3. **Dedup/canonicalize** via cosine to recent items; merge if sim ≥ 0.88.
4. **Embed** with configured model; store `embedding_model` & `embedding_dim`.
5. **Upsert** row keyed by a stable hash (user_id + canonical key or text hash).

## Read Path

1. Build query from current turn + rolling summary.
2. ANN top‑k with filters (`user_id`, `type in (…)`, `tags`, `ts_seen window`).
3. Score = `α*cosine + β*time_decay + γ*tag_match`.
4. Optional cross-encoder re-rank from k=50→n=8.
5. **Context packing**: cluster near-dupes, respect token budget, attach provenance.

## Retention & Lifecycle

- **Pin** canonical facts (`ttl_days=0`), LRFU decay for others.
- Touch (read) ⇒ update `ts_seen`.
- Periodic consolidation merges fragments.
- Re-embedding migrations: maintain `embedding_model_version`, dual-write to new index, flip alias when done.

## Security

- Disk encryption (system level); optional field-level payload encryption for PII.
- Secrets never stored; detect & reject high-entropy strings unless explicitly allowed.
- Audit log (append-only) of writes/updates (future: `memory_event` table).

## Observability

- Metrics: recall@k, memory token share, injection hit-rate, re-embed throughput.
- Tracing spans: retrieve → rerank → pack with selected IDs & scores.
- Debug mode dumps chosen memories & reasons.

## API & Code Integration Plan (incremental)

**Phase 1 (this ADR + DDL):** establish schema and configuration.
**Phase 2:** implement `mother.memory` adapter with two functions:

```python
retrieve(user_id: str, query: str, limit: int = 24, types: list[str] = None, tags: list[str] = None) -> list[dict]
upsert(user_id: str, text: str, mtype: str = "autobio", tags: list[str] = None, pin: bool = False, payload: dict = None) -> str
```

**Phase 3:** wire into FastAPI and worker; add `MEMORY_ENABLED=1` toggle and embedder model/env.
**Phase 4:** add optional reranker and hybrid BM25.

## Configuration (proposed .env keys)

- `PG_HOST=192.168.1.225`
- `PG_PORT=55432`
- `PGDATABASE=mother`
- `PGUSER=mother`
- `PGPASSWORD=***`
- `EMBEDDING_MODEL=bge-large-en-v1.5`
- `EMBEDDING_DIM=1024`
- `MEMORY_DISTANCE_METRIC=cosine`
- `MEMORY_INDEX=ivfflat`  # or hnsw if available
- `MEMORY_TOPK=50`
- `MEMORY_CONTEXT_MAXTOKENS=1200`

## Rollout & Backout

- Apply migration; verify extension and indexes.
- Enable with feature flag; shadow-write for a week; monitor recall/hit-rate.
- Backout: disable feature flag; drop index only if needed; keep tables for audit.

## Open Questions

- Which reranker latency/quality trade-off is acceptable on current hardware?
- Do we need tenancy beyond `user_id` (e.g., `household_id`)?
- Should we maintain a lightweight cache (e.g., sqlite/duckdb) for hot memories?
