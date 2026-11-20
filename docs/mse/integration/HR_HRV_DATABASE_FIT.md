# HR and SDNN database fit

**Disposition.** The pinned PF-001 SQLite archive and FORGE custody journal
support the corrected synthetic trial. Real-data destination readiness remains
**NOT READY**. The archive keeps clinical and provenance fidelity by retaining
the original. The current layout also keeps direct linkage across the stores
and has no de-identified projection or verified separate key custody.
[Round 7 and database privacy assessment](https://github.com/ctmansfield/mother/pull/23#issuecomment-7045683925)

## Evidence and scope

| Evidence | Exact pin and status |
| --- | --- |
| Active HealthBridge acquisition source | `9b85cf1a12ecb1f91f414e8f5366d81f3dbb81d6`. Static source inspection. [Collector types and writer](https://github.com/ctmansfield/mother-health-bridge/blob/9b85cf1a12ecb1f91f414e8f5366d81f3dbb81d6/MotherHealthBridge/ContentView.swift) |
| PF-001 archive | Open #18 at `b4e70b7123689ec164ba09e2974645ae36b184a2`. Reviewed DDL, write and query code and JSON validation. [SQLite migration 0001](https://github.com/ctmansfield/mother/blob/b4e70b7123689ec164ba09e2974645ae36b184a2/mother/physiology/migrations/0001_archive.sql) · [Archive implementation](https://github.com/ctmansfield/mother/blob/b4e70b7123689ec164ba09e2974645ae36b184a2/mother/physiology/archive.py) · [PF-001 observation schema](https://github.com/ctmansfield/mother/blob/b4e70b7123689ec164ba09e2974645ae36b184a2/mother/physiology/schemas/v1.schema.json) |
| Corrected source-integrity path | ORACLE #30 `ac3fbf61389ca2a6e82683aa520c15181ac1aa80`, FORGE #31 `e4219cdf3dba73f586e3820990f3ab34f1a7c1d9`, frozen ATLAS `769a0966da251da4d08633cc7663af9869da70e6`. These are the exact inputs to the synthetic run below. [Capture parser](https://github.com/ctmansfield/mother/blob/ac3fbf61389ca2a6e82683aa520c15181ac1aa80/integrations/healthbridge/capture.py) · [Exporter and numeric findings](https://github.com/ctmansfield/mother/blob/ac3fbf61389ca2a6e82683aa520c15181ac1aa80/integrations/healthbridge/export.py) · [Receipt-backed mapper](https://github.com/ctmansfield/mother/blob/e4219cdf3dba73f586e3820990f3ab34f1a7c1d9/integrations/mse_ingest/connected.py) · [Frozen contract](https://github.com/ctmansfield/mother/blob/769a0966da251da4d08633cc7663af9869da70e6/docs/mse/integration/contracts/README.md) |
| Destination metadata | PHOENIX #33 `b05acb390557152a6e26ad5f74b8c1f47696e174`. Bounded read-only metadata at the recorded checkpoint, supplied by PHOENIX. FORGE made no host or catalog requests and accessed no personal rows or captures. [Sanitized destination audit](https://github.com/ctmansfield/mother/pull/33) |

## Capture and physiological fidelity

| Field or boundary | Exact mapping and limitation |
| --- | --- |
| Metric and unit | HealthKit `.heartRate` yields **heart rate in bpm**. The current capture cannot establish raw versus derived HR, so evidence uses an unknown derivation class. ConnectedIngest keeps the source revision and eligible snapshot member, while the MSE bridge excludes it without independent classification evidence. HealthKit `.heartRateVariabilitySDNN` yields **vendor-derived SDNN in ms**. SDNN is a distinct metric from RMSSD and raw RR intervals. The capture supplies no calibrated error or acquisition-window definition. |
| Value representation | Swift `SavedReading.value` is a `Double`. Preserve the actual JSON lexeme and canonical exact decimal of that lexeme, plus source/normalized units. This cannot recover precision that was absent before Swift encoded the reading. Actual PF-001 `original_value` and `value` are auxiliary binary64 JSON numbers in `record_json`. The frozen exchange preserves exact decimal strings. Round 6 uses `Decimal.from_float` to compare each persisted numeric value to its exact decimal, retains per-field exact decimal and binary64 encoding in metadata when rounded, and carries the finding through verified snapshots. Finite negative and signed-zero values remain source-only with explicit exclusion. If an otherwise eligible positive value overflows or underflows to zero in binary64, the original and source fact remain, with field-specific exclusion from normalized observation and replay selection. No clipping, rewriting, unit relabeling or substitute value. |
| Time | Capture `Date` numbers are seconds since 2001-01-01 UTC. Convert exact decimals to six fractional UTC digits using ties-to-even microsecond rounding, and preserve the original tokens and field-specific losses. Keep event start/end, collector receipt, source availability, first MOTHER receipt and stage commit separate. Collector receipt and run sighting time cannot establish source availability. The capture does not provide source availability or time uncertainty. |
| UUID, origin and scope | Preserve the canonical lowercase UUID in the exchange and original spelling in retained bytes. Identity is subject, HealthKit, source instance, collection and native UUID. Preserve source name and bundle. Neither identifies a calibrated device. Capture/export is scoped to one trusted local store and subject. The source fact digest binds scoped UUID, operation, exact source payload and original decimal semantics. The processing digest separately binds that source digest, exact mapper version, event/channel/unit/value and classification. |
| Deletion, repeated sightings and coverage | Explicit per-reading `deletedAt` and the UUID tombstone map can record different collector-observed times for the same UUID. The adapter retains distinct exact delete facts and all locators, including map-only UUIDs with unknown channel. Equivalent upserts select the lowest original numeric reading index within a capture. Repeated sightings across batches keep separate receipt and artifact links. Missing/empty/partial captures infer no deletion. Anchors are opaque, hashed per metric after decoding, and retained exactly in the raw capture. `backfillStart`, anchors and a full-file label do not establish population coverage, permission, source chronology or a transferable server checkpoint. |

## Implemented schema and linkage for privacy review

These are source-backed proposed local stores for the trial. All linkable
identifiers are shown by field name only. A `TEXT` JSON column can expose its
contents to a database reader just as ordinary columns can.

| Store/objects | Types, keys and links | Sensitive linkage and current boundary |
| --- | --- | --- |
| Phone original and acquired capture | Codable `SavedReading` carries UUID, metric/unit/value, measurement interval, source name, bundle ID, collector receipt and optional deletion date. `HealthArchive` carries readings, metric-to-Data anchors, UUID-to-Date tombstones and backfill date. | Exact longitudinal time, UUID and source signatures are joinable. Capture ownership, extraction path and backup copies need separate inventory. [Collector source](https://github.com/ctmansfield/mother-health-bridge/blob/9b85cf1a12ecb1f91f414e8f5366d81f3dbb81d6/MotherHealthBridge/ContentView.swift) |
| Custody `trial_identity`, `deliveries`, `trial_exports` | Singleton `INTEGER PRIMARY KEY CHECK(singleton=1)` with identity JSON `TEXT`. `deliveries` primary key `(scope,batch_id)`, original `BLOB`, SHA-256/export digest/source schema/adapter version `TEXT NOT NULL`, unique internal `receipt_id` `TEXT`, receipt/run timestamps and run ID `TEXT`, nullable unique commit sequence `INTEGER`. `trial_exports` uses batch `TEXT PRIMARY KEY` and export JSON `TEXT NOT NULL`. | Identity JSON contains archive and scope. Export JSON carries exact clocks, native UUIDs, bundle/source strings, lexemes, losses and locators. Batch ID joins all three operational objects. Hashes locate predictable content and equal inputs; they provide no anonymity. |
| Custody `commits`, `stage_receipts` | `commits.sequence INTEGER PRIMARY KEY`. Stage primary key `(batch_id,status)`, unique `sequence INTEGER`, receipt body `TEXT`; status/shape/digest binding is checked in code. Stages include durable receipt, normalization or quarantine. No cross-file FK. | External receipt ID is the domain-separated hash of archive/scope/batch. Receipt body repeats scope, artifact/export digests, exact MOTHER times, sequence and PF-001 run ID. Application reopen checks establish linkage; these identifiers expose linkage to a reader of either store. [Journal DDL](https://github.com/ctmansfield/mother/blob/e4219cdf3dba73f586e3820990f3ab34f1a7c1d9/integrations/mse_ingest/v02.py) · [Delivery DDL](https://github.com/ctmansfield/mother/blob/e4219cdf3dba73f586e3820990f3ab34f1a7c1d9/integrations/mse_ingest/__init__.py) |
| PF-001 `raw_artifacts`, `import_runs`, `schema_versions` | Artifact SHA-256 `TEXT PRIMARY KEY`, media type/time `TEXT`, content `BLOB NOT NULL`. Import run `TEXT PRIMARY KEY`, source/collection/version/clocks and request/counts JSON `TEXT`; state checked against running/complete/incomplete/failed. Migration version `INTEGER PRIMARY KEY` with contract and application time. | Raw bytes duplicate content accepted in custody. `request_json` binds internal receipt, subject/scope, artifact/export and batch. Counts bind run membership. Artifact SHA and run ID bridge custody and archive. |
| PF-001 `source_revisions`, `run_revisions`, `source_heads` | Revision `TEXT PRIMARY KEY`; source key, native ID, revision hash, canonical `raw_json`, first-seen/ingested/source-availability/modified/measurement clocks `TEXT`; import run FK and optional artifact FK. Unique `(source_instance,collection,source_key,revision_hash)`. Disposition checked against accepted/rejected/unsupported/deleted. `run_revisions` has run/revision FKs and composite PK; `source_heads` keyed by namespace/collection/source key with revision and run FKs. | Source instance is a deterministic scope-derived hash. `source_key` and `native_id` still expose the UUID. Connected raw revision JSON holds native ID, operation and source digest; the exact observation/delete payload and later sightings are bound through run and export membership. Tombstone times are export evidence, with measurement times null in the PF-001 delete row. |
| PF-001 `normalized_records`, `checkpoints` | Record `TEXT PRIMARY KEY`, revision FK, kind, validated JSON and processing version `TEXT`; `idx_record_revision` on revision ID. Observation schema permits numeric/string/boolean/null value fields generally. This trial writes eligible positive metrics as JSON numbers and stores decimal evidence separately. Checkpoint PK is namespace/collection and includes JSON plus run FK. | Observation JSON retains subject, interval, bundle mapped to `recording_app`, source name in metadata, first-received clocks and exact lineage. The receipt path does not advance PF-001 checkpoints from a captured anchor. |
| Verified snapshot and MSE result | Read-time versioned JSON. Snapshot binds scope/archive, measurement interval, exact normalizer, authoritative cutoff, artifact/receipt hashes, PF-001/source/processing revision identities, times, losses and selected fact payloads. Existing MSE reference outputs are derived with their own manifest/lineage. | Even a standalone snapshot exposes exact longitudinal event time and cross-store handles. Treat exported snapshot/replay manifests, derived results, logs, temporary files, backups and any future model memory as separate controlled purposes. No source evidence shows a restricted identity vault, token rotation or safe pgvector publication for these records. [Snapshot/bridge contract](https://github.com/ctmansfield/mother/blob/769a0966da251da4d08633cc7663af9869da70e6/docs/mse/integration/contracts/README.md) |

Current file checks require caller-owned canonical parents, a private 0700 root,
and singly linked regular files of mode 0600 for database files and SQLite
sidecars. The writer uses `BEGIN IMMEDIATE` and `synchronous=FULL`. PF-001
enables foreign keys. Reopen checks rederive the capture and reconcile receipt,
artifact, revisions and normalized membership. These controls do not hide
data in a stolen dump, host compromise or accessible backup. No encryption,
separate key custody, service role grants, backup encryption/restore access,
erasure policy or privacy-preserving serving view has been qualified. Do not
use deterministic digests as public pseudonyms. A separately authorized
analytical view should use purpose-scoped opaque IDs and explicitly version
which fields, timing precision and lineage are released. Keep mapping and
keys under separate custody and leave authoritative source bytes untouched.

## Query and write behavior

- PF-001 live `current_records` joins `source_heads` and filters accepted
  revisions. Heads advance by observed sighting time. This projection cannot
  represent historical knowledge or enforce persistent MSE deletion dominance
  across a late upsert. It can also expose multiple processing versions for a
  current revision. Use the receipt-backed snapshot for the MSE query.
- The snapshot accepts only completed normalized stages at or below an
  archive-local receipt sequence, reopening run, exact original and membership.
  After a delete becomes eligible, the UUID stays suppressed even if an upsert
  arrives later. Retain distinct deletes including unknown UUIDs independently
  of the measurement window. Observe exact normalizer selection with no
  fallback. Upserts satisfy start-inclusive/end-exclusive start and complete
  end at or before the requested end. Repeated facts select the earliest intact
  eligible receipt. Earlier cutoff results cannot be updated by later sightings.
- Synthetic plans used `idx_revision_source` on
  `(source_instance,collection,source_key)`, `idx_revision_time` on
  `measurement_start`, and `idx_record_revision` on `revision_id`. The stage
  query searched the unique sequence index and filtered to normalized stages.
  `record_json` has no typed channel/value index. The current snapshot walks
  eligible commits and revalidates originals/membership before windowing.
  It is not an interval-indexed database query. Verification rebuilds the same
  complete selection. Larger historical scans and cross-capture conflict checks
  require explicit bounds and later measurement.
- The journal serializes an archive transaction between durable custody and
  terminal receipt. Snapshot reads using that journal transaction can also
  contend with a writer. A second SQLite connection with a 50 ms wait could
  not acquire `BEGIN IMMEDIATE` during the synthetic first transaction. This
  demonstrates lock exclusion. It does not establish production concurrency,
  service latency or multi-tenant isolation.

## Disposable synthetic sizing

One Python 3.12.14 / SQLite 3.53.1 local run, two fresh database pairs.
Each batch contained 64 new readings (equal HR and SDNN), one new unknown-UUID
delete, and no retained full-history recapture. SDNN used a decimal requiring
rounding; HR derivation remained unknown. Actual public ingest supplied the
capture and validated the stored receipt. Both database integrity checks,
PF-001 foreign-key check, expected observation/tombstone counts and reopened
snapshot verification passed. Sizes are bytes for closed DBs and a compact
reopened snapshot JSON, excluding logs, transient journals and backups.
Timings are one elapsed observation under this synthetic workload.

| New readings | Batches / deletes | Original bytes | Custody SQLite | PF-001 SQLite | Both DBs | Snapshot JSON | Ingest all / build / verify |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 256 | 4 / 4 | 53,716 | 356,352 | 1,028,096 | 1,384,448 | 334,364 | 173 / 73 / 106 ms |
| 1,024 | 16 / 16 | 214,864 | 1,236,992 | 3,850,240 | 5,087,232 | 1,319,157 | 661 / 291 / 419 ms |

The larger set produced 512 normalized PF-001 SDNN records and retained 1,024
source upserts plus 16 deletes. The two-size incremental estimate is roughly
**4.8 kB per new reading** across the pair at this batch size/mix. If sustained
at a purely illustrative 1,000 or 10,000 new readings/day, primary growth
would be about **1.76 or 17.6 GB/year** in decimal units. One same-size clean
backup generation adds a second copy before storage overhead and restore
headroom. Snapshot retention adds its own costs. These are scenarios,
not inferred phone cadence, quota, RPO/RTO or scaling guarantees. Full-file
recapture changes the calculation: keeping successive growing unique files
retains their cumulative bytes in custody and canonical artifacts. A
same-batch identical retry creates no new receipt. Different deliveries of
identical bytes can duplicate the journal BLOB while PF-001 deduplicates by
artifact digest. Short transactions, range limits and sustained-size tests
should precede any representative-scale promise.

Private synthetic run log SHA-256
`de4225cdcf1765ba0f53fa183343b2ddedcda0e585091c9a2932ab8ab6a1fc64`.
No report content was generated from a personal dataset.

## Storage decision and additive roadmap

PHOENIX observed an available local PostgreSQL 16.15 engine and a local ext4
allocation candidate. Its bounded catalog found only the administrative
database among connectable non-template databases. No qualified physiological
schema, reserved artifact allocation, writer role, intake route or verified
restore was identified. The source-backed local trial path is PF-001 SQLite
with one serialized writer, dedicated private local storage and paired
artifact/journal/archive recovery. Current source and metadata support no
production choice between SQLite and PostgreSQL. An established need for
parallel writers, a different failure-domain or operational policy would
trigger a reviewed PostgreSQL schema and compatibility prototype. Availability
and a vector extension do not qualify the archive. [Metadata report](https://github.com/ctmansfield/mother/pull/33)

1. **Before operational qualification**, define artifact-size/record/cutoff and
   request limits, dedicated identity and filesystem allocation, quota,
   storage/backup ownership, retention, erasure and restore objectives. Require
   coherent backup of the pair and originals with independent restore, including
   interrupted commit and permission checks. Keep the identity/linkage
   separation and approved analytical loss policy in the privacy decision.
2. **If query pressure is demonstrated**, propose additive DB changes such as
   `stage_receipts(status,sequence)` and a namespace/collection/time index or
   typed, read-only projection with revision/processing references and
   authoritative cutoff proof. Define scope and interval checks before
   indexing exact times or adding a value column. Exact decimals and original
   bytes remain available. Rehearse backfill/feature-off rollback in isolates
   and verify historical digest/receipt equality.
3. **If stronger operational integrity is needed**, evaluate a versioned
   journal migration for stage checks/FKs within the journal and normalized
   receipt reconciliation. Add capture/revision sighting links only when the
   existing run/export proofs cannot meet bounded queries. Keep applied PF-001
   migration 0001 immutable. No migration is attached or executed here.
4. **Before broader access**, separate restricted identity/linkage custody
   from any purpose-limited analytical projection, cover logs/artifacts/
   WAL/backup/export and derived invalidation, and exercise privacy and
   clinical-fidelity acceptance on authorized synthetic tests. SENTINEL owns
   the cross-store threat and key assessment. PHOENIX owns destination and
   restore design. GADGET and Chad own the concrete destination decision.
