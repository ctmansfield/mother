-- 20250925_add_memory_tables.sql
-- pgvector-powered long-term memory schema for mother

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

-- Core memory table
CREATE TABLE IF NOT EXISTS memory_item (
  id               TEXT PRIMARY KEY,
  user_id          TEXT NOT NULL,
  type             TEXT NOT NULL CHECK (type IN ('autobio','episodic','semantic','procedural')),
  text             TEXT NOT NULL,
  tags             TEXT[] DEFAULT '{}',
  ts_created       TIMESTAMPTZ NOT NULL DEFAULT now(),
  ts_seen          TIMESTAMPTZ NOT NULL DEFAULT now(),
  confidence       REAL NOT NULL DEFAULT 0.9,
  ttl_days         INTEGER NOT NULL DEFAULT 0,         -- 0 = pinned
  retention_policy TEXT NOT NULL DEFAULT 'LRFU(21d)',
  embedding_model  TEXT NOT NULL DEFAULT 'bge-large-en-v1.5',
  embedding_dim    INTEGER NOT NULL DEFAULT 1024,
  embedding        vector(1024),                       -- match embedding_dim if using fixed model
  payload          JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- General filters
CREATE INDEX IF NOT EXISTS idx_memory_user_type_seen ON memory_item (user_id, type, ts_seen DESC);
CREATE INDEX IF NOT EXISTS idx_memory_tags ON memory_item USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_memory_payload ON memory_item USING GIN (payload jsonb_path_ops);

-- Vector ANN index (choose one depending on pgvector version/features)
-- IVF Flat (requires ANALYZE; tweak lists per data size)
CREATE INDEX IF NOT EXISTS idx_memory_embedding_ivf ON memory_item USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- If pgvector >= 0.7.0 supports HNSW, you can alternatively use:
-- CREATE INDEX IF NOT EXISTS idx_memory_embedding_hnsw ON memory_item USING hnsw (embedding vector_cosine_ops);

-- TTL helper view
CREATE OR REPLACE VIEW memory_item_expiring AS
SELECT * FROM memory_item
WHERE ttl_days > 0 AND now() - ts_seen > (ttl_days || ' days')::interval;

COMMIT;
