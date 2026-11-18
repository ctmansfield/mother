-- MSE-001 v0.1.0 DESIGN PROPOSAL. Initialize a NEW selected MSE database only.
-- Not the executable prototype schema; not a PF001/HealthKit migration.
-- Source references are external, verified against an immutable snapshot manifest.
PRAGMA foreign_keys = ON;

CREATE TABLE model_versions (
  model_id TEXT NOT NULL,
  version TEXT NOT NULL,
  code_sha256 TEXT NOT NULL CHECK(length(code_sha256)=64),
  config_sha256 TEXT NOT NULL CHECK(length(config_sha256)=64),
  configuration_json TEXT NOT NULL CHECK(json_valid(configuration_json)),
  model_card_json TEXT NOT NULL CHECK(json_valid(model_card_json)),
  created_at TEXT NOT NULL,
  PRIMARY KEY(model_id, version)
);

CREATE TABLE mechanism_bundles (
  bundle_id TEXT PRIMARY KEY,
  manifest_sha256 TEXT NOT NULL CHECK(length(manifest_sha256)=64),
  manifest_json TEXT NOT NULL CHECK(json_valid(manifest_json)),
  review_status TEXT NOT NULL CHECK(review_status IN ('candidate','reviewed','retired')),
  created_at TEXT NOT NULL
);

CREATE TABLE evidence_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  manifest_sha256 TEXT NOT NULL CHECK(length(manifest_sha256)=64),
  contract_version TEXT NOT NULL,
  manifest_json TEXT NOT NULL CHECK(json_valid(manifest_json)),
  knowledge_policy TEXT NOT NULL CHECK(knowledge_policy IN
    ('strict_authoritative_availability','source_receipt_only','retrospective')),
  availability_cutoff TEXT,
  created_at TEXT NOT NULL,
  CHECK(knowledge_policy='retrospective' OR availability_cutoff IS NOT NULL)
);

CREATE TABLE snapshot_inputs (
  snapshot_id TEXT NOT NULL REFERENCES evidence_snapshots(snapshot_id),
  record_id TEXT NOT NULL,
  source_revision_id TEXT NOT NULL,
  artifact_sha256 TEXT NOT NULL CHECK(length(artifact_sha256)=64),
  record_sha256 TEXT NOT NULL CHECK(length(record_sha256)=64),
  subject_id TEXT NOT NULL,
  source_instance TEXT NOT NULL,
  measurement_start TEXT,
  measurement_end TEXT,
  available_at TEXT,
  disposition TEXT NOT NULL CHECK(disposition IN ('active','deleted','invalid','unsupported')),
  PRIMARY KEY(snapshot_id,record_id,source_revision_id)
);

CREATE TABLE inference_runs (
  run_id TEXT PRIMARY KEY,
  model_id TEXT NOT NULL,
  model_version TEXT NOT NULL,
  snapshot_id TEXT NOT NULL REFERENCES evidence_snapshots(snapshot_id),
  bundle_id TEXT REFERENCES mechanism_bundles(bundle_id),
  parent_run_id TEXT REFERENCES inference_runs(run_id),
  execution_mode TEXT NOT NULL CHECK(execution_mode IN
    ('retrospective','as_available_replay','shadow','simulation')),
  environment_json TEXT NOT NULL CHECK(json_valid(environment_json)),
  random_seed INTEGER,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  status TEXT NOT NULL CHECK(status IN ('running','complete','failed')),
  output_sha256 TEXT CHECK(output_sha256 IS NULL OR length(output_sha256)=64),
  FOREIGN KEY(model_id,model_version) REFERENCES model_versions(model_id,version)
);

CREATE TABLE feature_values (
  feature_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES inference_runs(run_id),
  subject_id TEXT NOT NULL,
  definition_id TEXT NOT NULL,
  definition_version TEXT NOT NULL,
  window_start TEXT NOT NULL,
  window_end TEXT NOT NULL,
  available_as_of TEXT,
  value_json TEXT CHECK(value_json IS NULL OR json_valid(value_json)),
  unit TEXT NOT NULL,
  coverage_json TEXT NOT NULL CHECK(json_valid(coverage_json)),
  quality_json TEXT NOT NULL CHECK(json_valid(quality_json)),
  input_lineage_json TEXT NOT NULL CHECK(json_valid(input_lineage_json))
);

CREATE TABLE state_estimates (
  estimate_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES inference_runs(run_id),
  subject_id TEXT NOT NULL,
  state_definition_id TEXT NOT NULL,
  state_definition_version TEXT NOT NULL,
  measured_as_of TEXT NOT NULL,
  available_as_of TEXT,
  estimate_status TEXT NOT NULL CHECK(estimate_status IN ('unknown','estimated','prior_dominated')),
  posterior_json TEXT CHECK(posterior_json IS NULL OR json_valid(posterior_json)),
  unknown_reason TEXT,
  uncertainty_calibration TEXT NOT NULL CHECK(uncertainty_calibration IN
    ('unvalidated','synthetic_only','empirically_calibrated')),
  observability_json TEXT NOT NULL CHECK(json_valid(observability_json)),
  context_json TEXT NOT NULL CHECK(json_valid(context_json)),
  feature_lineage_json TEXT NOT NULL CHECK(json_valid(feature_lineage_json)),
  CHECK((estimate_status='unknown' AND posterior_json IS NULL AND unknown_reason IS NOT NULL)
     OR (estimate_status IN ('estimated','prior_dominated') AND posterior_json IS NOT NULL))
);

CREATE TABLE state_validity_events (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,
  estimate_id TEXT NOT NULL REFERENCES state_estimates(estimate_id),
  validity TEXT NOT NULL CHECK(validity IN ('valid','superseded','retracted','source_revised')),
  reason TEXT NOT NULL,
  source_revision_id TEXT,
  replacement_estimate_id TEXT REFERENCES state_estimates(estimate_id),
  recorded_at TEXT NOT NULL
);

CREATE TABLE hypothesis_sets (
  hypothesis_set_id TEXT PRIMARY KEY,
  estimate_id TEXT NOT NULL REFERENCES state_estimates(estimate_id),
  bundle_id TEXT REFERENCES mechanism_bundles(bundle_id),
  hypotheses_json TEXT NOT NULL CHECK(json_valid(hypotheses_json)),
  includes_unmodeled_alternative INTEGER NOT NULL CHECK(includes_unmodeled_alternative=1),
  quantitative_probabilities_validated INTEGER NOT NULL CHECK(quantitative_probabilities_validated IN (0,1)),
  created_at TEXT NOT NULL
);

CREATE TABLE measurement_requests (
  request_id TEXT PRIMARY KEY,
  hypothesis_set_id TEXT NOT NULL REFERENCES hypothesis_sets(hypothesis_set_id),
  contract_version TEXT NOT NULL,
  request_json TEXT NOT NULL CHECK(json_valid(request_json)),
  execution_authority TEXT NOT NULL CHECK(execution_authority='none'),
  created_at TEXT NOT NULL
);

CREATE INDEX idx_feature_subject_time ON feature_values(subject_id,window_start);
CREATE INDEX idx_estimate_subject_time ON state_estimates(subject_id,measured_as_of);
CREATE INDEX idx_validity_estimate ON state_validity_events(estimate_id,sequence);
CREATE INDEX idx_input_revision ON snapshot_inputs(source_revision_id);

CREATE VIEW current_valid_state_estimates AS
SELECT s.* FROM state_estimates AS s
WHERE NOT EXISTS (
  SELECT 1 FROM state_validity_events AS v
  WHERE v.estimate_id=s.estimate_id
    AND v.sequence=(SELECT MAX(v2.sequence) FROM state_validity_events AS v2
                    WHERE v2.estimate_id=s.estimate_id)
    AND v.validity!='valid'
);

-- Time parsing, dimensional validation, external lineage and content-address
-- verification belong in the versioned contract validator. TEXT order alone is
-- not a timestamp parser. This design has no network service or automated runner.
