-- Additive local archive. This is SQLite, not a production PostgreSQL migration.
-- Contract/migration owner: PM integration. Never edit an applied migration.
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS schema_versions (
    version INTEGER PRIMARY KEY,
    contract_version TEXT NOT NULL,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS import_runs (
    run_id TEXT PRIMARY KEY,
    source_instance TEXT NOT NULL,
    collection TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    contract_version TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running','complete','incomplete','failed')),
    request_json TEXT NOT NULL,
    counts_json TEXT NOT NULL DEFAULT '{}',
    error TEXT
);
CREATE TABLE IF NOT EXISTS raw_artifacts (
    sha256 TEXT PRIMARY KEY,
    media_type TEXT NOT NULL,
    content BLOB NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source_revisions (
    revision_id TEXT PRIMARY KEY,
    source_instance TEXT NOT NULL,
    collection TEXT NOT NULL,
    source_key TEXT NOT NULL,
    native_id TEXT,
    revision_hash TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    source_available_at TEXT,
    source_modified_at TEXT,
    measurement_start TEXT,
    measurement_end TEXT,
    import_run_id TEXT NOT NULL REFERENCES import_runs(run_id),
    disposition TEXT NOT NULL CHECK (disposition IN ('accepted','rejected','unsupported','deleted')),
    rejection_reason TEXT,
    artifact_sha256 TEXT REFERENCES raw_artifacts(sha256),
    UNIQUE (source_instance, collection, source_key, revision_hash)
);
CREATE TABLE IF NOT EXISTS normalized_records (
    record_id TEXT PRIMARY KEY,
    revision_id TEXT NOT NULL REFERENCES source_revisions(revision_id),
    kind TEXT NOT NULL,
    record_json TEXT NOT NULL,
    processing_version TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_revisions (
    run_id TEXT NOT NULL REFERENCES import_runs(run_id),
    revision_id TEXT NOT NULL REFERENCES source_revisions(revision_id),
    observed_at TEXT NOT NULL,
    PRIMARY KEY (run_id, revision_id)
);
CREATE TABLE IF NOT EXISTS source_heads (
    source_instance TEXT NOT NULL,
    collection TEXT NOT NULL,
    source_key TEXT NOT NULL,
    revision_id TEXT NOT NULL REFERENCES source_revisions(revision_id),
    observed_at TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES import_runs(run_id),
    PRIMARY KEY (source_instance, collection, source_key)
);
CREATE TABLE IF NOT EXISTS checkpoints (
    source_instance TEXT NOT NULL,
    collection TEXT NOT NULL,
    checkpoint_json TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES import_runs(run_id),
    PRIMARY KEY (source_instance, collection)
);
CREATE INDEX IF NOT EXISTS idx_revision_source ON source_revisions(source_instance, collection, source_key);
CREATE INDEX IF NOT EXISTS idx_revision_time ON source_revisions(measurement_start);
CREATE INDEX IF NOT EXISTS idx_record_revision ON normalized_records(revision_id);
