# Offline MSE integration interfaces, draft 0.1

For GADGET review under MSE-INTEGRATION-20261120-01 r1. These are local exchange objects, without a transport, storage placement, authorization mechanism or production limits.

## Common encoding and identity

Use UTF-8 JSON with unique keys and finite values. For derived digests use SHA-256 over compact, sorted-key JSON, UTF-8, unescaped Unicode, no trailing newline, and no floats in shared objects. Decimal measurement values are strings without exponents. Raw artifact SHA-256 is over original bytes, independently of the derived encoding. Time is canonical UTC with six fractional digits. Convert Swift numeric Date from 2001-01-01 UTC using exact decimal arithmetic rounded to the nearest microsecond, ties to even. Preserve the input number lexeme in the export or via a lossless locator and record introduced precision loss. Reject unrepresentable dates, reversed intervals and malformed units. No confidence or acquisition window is inferred from the interval alone.

Scope is `{subject_id, source_system, source_instance, collection}`, with first-slice source_system `healthkit` and collection `healtharchive`. Use a synthetic, nonempty namespace from the caller, scoped to a single store and subject. The logical key is scope plus canonical lowercase UUID. A batch ID is a caller-assigned nonempty token stable across retries within scope. Original capture identity and batch identity remain separate.

## Captured export — mse.healtharchive-export/0.1

Required top-level fields:

- `schema_version`, `scope`, `batch_id`, `capture_id`, `exporter_version`.
- `artifact` with `sha256`, `byte_length`, `media_type` (application/json) and `source_schema` (healtharchive-codable-json/0.1). Pass the original bytes separately.
- `coverage` with `capture_kind` (full_file or partial), `backfill_start`, `observed_start`, `observed_end`, `permissions` and `completeness`. Unavailable values are null or explicit unknown. Full file means complete bytes for one captured file, with no implied lifetime or permission coverage.
- `anchor_sha256`, keyed by metric, on decoded opaque anchor bytes. No ordering or cross-store reuse.
- `revisions`, a deterministic ordered array. Each entry has `native_id`, `operation` (upsert or delete), `revision_sha256`, `locators` (JSON pointers into the original capture) and either `observation` or `deleted_at`. Digest the scope, native ID, operation and typed source payload, excluding capture locators and server clocks.
- `losses`, a deterministic array of typed findings with field, reason and optional locator. Include absent device/calibration/source-availability/source-revision metadata. Findings do not silently admit invalid records.

Observation payload fields are `channel`, `original_value`, `original_unit`, `value`, `unit`, `event_start`, `event_end`, `collector_received_at`, `source_name`, `bundle_id`, `epistemic_type`, `device_id`, `calibration_id`, and `source_available_at`. Map Heart rate to heart_rate/bpm/measured and HRV (SDNN) to hrv_sdnn/ms/vendor_derived. Keep source/clock uncertainty. `collector_received_at` is preserved as its own clock.

Read embedded deletedAt and the separate UUID tombstones dictionary. Merge identical delete facts with all locators. Preserve distinct explicit delete facts. Tombstone for an unobserved UUID is valid. For this first slice a known tombstone suppresses that UUID in current projection even if an older upsert arrives later. Keep the prior upsert and deletion evidence. Any resurrection policy needs separate source evidence and review. Missing UUIDs, empty exports and absent anchors create no deletions. Reject ambiguous unequal upserts for the same UUID within one capture.

## Local acceptance receipt — mse.ingest-receipt/0.1

Required fields: `schema_version`, `scope`, `batch_id`, `artifact_sha256`, `byte_length`, `source_schema`, `export_sha256`, `receipt_id`, `status`, `mother_received_at`, `committed_at`, `commit_sequence`, `pf001_run_id`, and `reason_code`. Use a local authoritative transaction/journal identifier for the commitment and an injected clock for reproducible synthetic tests. No synthesized commit time for uncommitted states. A durable receipt records custody and commitment stage. It conveys no authentication/signature claim.

States are durably_received (verified original bytes retained), normalized (PF-001 and receipt bindings reopen and agree), quarantined (retained but withheld), and rejected (no acceptance commitment). An interrupted normalization remains durably_received or explicitly quarantined pending reconciliation. Terminal normalized retries return the original receipt and clocks. Same scoped batch with unequal artifact or bound export digest is conflict, leaving original receipt and archive unchanged. Claims of successful normalization require the exact run/artifact/scope binding and reopen checks. Use one serialized local writer in this trial; concurrency, storage quotas and production recovery are separate gates. Never advance an acquisition anchor from this receipt.

## Evidence snapshot — mse.evidence-snapshot/0.1

Required fields: `schema_version`, `scope`, `purpose` (offline_synthetic_replay), `measurement_start`, `measurement_end`, `knowledge_cutoff_sequence`, `normalizer_version`, `coverage`, `observations`, `tombstones`, `losses`, and `snapshot_sha256`. The digest covers the object excluding snapshot_sha256. Use a half-open measurement interval with events complete by its end. Only committed normalized revisions at or before the recorded local cutoff are eligible. Select one active revision per UUID and carry explicit available tombstones, including unknown UUIDs. Bind each selected revision/tombstone to its PF-001 revision ID, artifact digest, scoped native ID, receipt/commit and normalized or delete payload. Sort by stable logical/revision identity. Never query a mutable current head and label it as a past cutoff without reconstruction evidence.

Project into existing `mse.replay/0.1` using validated `mse.observation/0.1` rows and reference tombstones. See the reconciliation for the clock and immutable-ID mismatch. Keep snapshot, losses and input digest outside the reference envelope alongside code/config/run identity. Each snapshot replay uses an isolated disposable reference store. Outputs are derived or unavailable. No averaging, hidden coercion, archival writes or historical online inference claim.
