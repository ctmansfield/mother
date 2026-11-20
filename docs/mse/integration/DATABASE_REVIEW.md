# MSE database readiness for current HealthArchive captures

**Disposition: NOT READY.** PF-001 SQLite is the source-backed archive for the
local synthetic trial. No deployed MSE archive, reserved custody location, intake route,
writer identity or verified recovery was established. No live destination is selected. [Readiness directive](https://github.com/ctmansfield/mother/pull/23#issuecomment-7041665721)

## Evidence and scope

- Current data shape comes from immutable HealthBridge collector source at
  `9b85cf1a12ecb1f91f414e8f5366d81f3dbb81d6` and the parser owner's source
  inventory. This establishes emitted fields, not today's personal observations
  or collection completeness. [Collector inventory](https://github.com/ctmansfield/mother/pull/23#issuecomment-7041480667)
- Structural evidence comes from MOTHER main
  `c05f38096406965496d7d4a09edf4b3575235311`, open PF-001 #18
  `b4e70b7123689ec164ba09e2974645ae36b184a2`, FORGE #31
  `b32f30d0b2e42ce16ae1b21363feaef2006e15f7`, the 0.2 follow-up
  `c29f4426c0e598d07ea9b1b5d019c48cd90253c9`, and ATLAS's provisional 0.2
  candidate `928a60b704c342c091eabd25ba41c8eb84d562de`. [PF-001 SQLite migration](https://github.com/ctmansfield/mother/blob/b4e70b7123689ec164ba09e2974645ae36b184a2/mother/physiology/migrations/0001_archive.sql) · [Custody harness](https://github.com/ctmansfield/mother/pull/31) · [ATLAS 0.2](https://github.com/ctmansfield/mother/pull/23#issuecomment-7041661287)
- FORGE inspected source and the sanitized PHOENIX catalog report. PHOENIX
  observed the established environment on November 21 at 00:12–00:13 Guam.
  FORGE did not query the host, catalog or physiological rows/files and did
  not execute DDL. [PHOENIX audit at exact head](https://github.com/ctmansfield/mother/blob/b05acb390557152a6e26ad5f74b8c1f47696e174/docs/mse/integration/DESTINATION_READINESS.md)

## Current data and source structures

| Data or boundary | Existing representation and constraints | Gap for the first complete slice |
| --- | --- | --- |
| Original HealthArchive JSON | PF-001 `raw_artifacts` stores exact bytes as a BLOB keyed by SHA-256 with media type and creation time. The archive write verifies the digest before insertion. `source_revisions.artifact_sha256` optionally references it. #31 retains the original in its separate custody journal before the PF-001 transaction. | Preserve byte count, source schema, capture/export version and stable capture locator. A repeated fact can occur in several artifacts. A revision's original artifact FK cannot enumerate later sightings or their JSON pointers. |
| Scoped batch and custody | #31 `deliveries` has a primary key over canonical scope and batch ID, unique receipt ID and optional unique commit sequence. `commits` allocates final sequences. Exact bytes and export digest are bound on retry. PF-001 `import_runs` carries subject and correlation in request JSON and state in a checked column. | Bind trusted archive identity and actual canonical export digest. Version the journal schema and persist explicit state/timestamp/sequence rules. The 0.2 follow-up adds provisional custody, normalization and quarantine stages. The actual ORACLE adapter binding and complete snapshot producer remain open. There is no cross-database FK. Reconciliation must prove exact bindings and report missing or ambiguous members. |
| UUID, source and intervals | `source_revisions` stores native ID, source namespace, collection, logical source key, revision hash, original canonical JSON, event start/end and import-run FK. Unique namespace/collection/key/revision hash allows multiple revisions. `idx_revision_source` and `idx_revision_time` support key and start-time access. #31 derives the PF-001 namespace from the complete scope. | Validate canonical UUID, interval and scope at the adapter boundary. Bind exact source facts with original lexemes and stable digests. Whole-batch quarantine of unequal upserts under one scoped UUID needs an explicit policy check; the existing SQL unique key permits those rows. |
| HR and SDNN, source/bundle and uncertainty | PF-001 `normalized_records` has a record ID primary key, revision FK, kind, JSON and processing version, with `idx_record_revision`. JSON Schema checks records. Retain HR bpm, SDNN ms, source name, bundle and supported channel while keeping the raw numeric tokens in custody and locator lineage. | Add a reviewed adapter mapping and processing digest. Keep HR derivation unknown unless qualified and SDNN vendor-derived. Preserve source/bundle, original value/unit, conversion loss, device/calibration/source-availability unknowns. Do not use a default measured classification or fill unknown metadata. |
| Separate clocks and opaque anchors | PF-001 separates biological start/end, optional source availability, first seen, ingested and run completion. `run_revisions.observed_at` records sightings. #31 records first MOTHER receipt separately. PF-001 `checkpoints` requires a completed run through the archive API. | Retain collector receipt separately from MOTHER receipt and commit. Bind per-channel anchor digests to capture and scope in metadata. Backfill markers, anchor presence and a receipt provide no completeness or server checkpoint authority. |
| Tombstones and previous facts | PF-001 supports `disposition='deleted'`, nullable measurement fields and immutable revision history. `source_heads` keeps one observed head per namespace/collection/source key using observed time. Its current projection can change on a later sighting. | Keep every distinct explicit deletion fact and its locators including unknown UUIDs. Merge equivalent facts and never derive deletion from absence. The existing current head cannot enforce deletion dominance against a late upsert or reconstruct earlier cutoff state. Define the cutoff projection over committed facts. |
| Reopened receipt and model snapshot | #31 rechecks run, exact original bytes, run revision membership and normalized record digests. PF-001 `run_revisions` keys membership by run/revision. The pinned MSE proposal has `evidence_snapshots`, `snapshot_inputs`, `inference_runs` and a source revision input index. The MSE reference uses disposable derived storage. | No approved operational receipt/snapshot schema or producer binds cutoff, exact receipt, source/processing revisions and replay members. Keep stable snapshots and results outside the authoritative measurement write path. Use the proposed design as reference only. [Original MSE design](https://github.com/ctmansfield/mother/blob/c05f38096406965496d7d4a09edf4b3575235311/research/mse/reference-v0.1.0/design/001_mse_proposed.sql) |

## Smallest additive plan for review

1. Keep PF-001 migration 0001 and its archive API intact. Complete the local
   journal and receipt boundary under the integration paths first. Introduce
   explicit schema version, trusted archive identity, scoped unique batch key,
   exact artifact/size/schema/export binding and durable stage records with
   checked state-dependent fields and journal-assigned sequences. Old 0.1
   trial output requires explicit version handling.
2. Bind the validated export to the PF-001 run and normalized processing
   identities. Reuse immutable revision hashes, run membership and artifact
   storage. If the cutoff/lineage queries need persistent relational links,
   propose a new additive PF-001 migration for run/revision/capture sightings
   with artifact FK and exact locators. Keep normalized records and raw bytes
   in their existing authorities. Add a journal sequence/scope index and an
   archive run or reverse-membership index only if actual query plans show
   the pinned primary and secondary indexes are insufficient.
3. Produce immutable cutoff-bound snapshot manifests with observed/deleted
   membership, exact committed receipts, scope, interval, coverage, losses
   and source/processing digests. Validate late upsert suppression and
   historical cutoffs before considering any new serving table. Keep MSE
   inference outputs in separate derived storage.
4. Qualify a disposable pair end to end with new synthetic captures, multiple
   and unknown-UUID tombstones, conflicting batches, rejected validation,
   interrupted commits, process recovery and a separate backup restore.
   Require both stores and linkage after restore. #31's exceptions, retries
   and reopen results do not establish crash/power-loss or restored-backup
   behavior. No DDL or readiness promotion follows from this proposal alone.

## SQLite and PostgreSQL evidence

SQLite has concrete PF-001 SQL, transaction code and local tests. That supports
the synthetic trial and does not establish production concurrency, filesystem
durability, multi-host access, capacity, or an accepted recovery objective.
The paired custody and archive stores need a coordinated recovery rehearsal.

At pinned main, the application PostgreSQL migration paths describe reminders,
behavior events, vector-backed memory and Nerdle. They do not define the PF-001
artifact/revision/receipt contract. A healthy PostgreSQL process or an installed
vector extension would establish availability only. Selecting PostgreSQL for this
archive would require a separately reviewed mapping and validation of transaction
semantics, identities, access boundaries, backups and restore. The source review
cannot justify a port or a production SQLite choice. [Application migrations](https://github.com/ctmansfield/mother/tree/c05f38096406965496d7d4a09edf4b3575235311/db/migrations) · [Operations migrations](https://github.com/ctmansfield/mother/tree/c05f38096406965496d7d4a09edf4b3575235311/ops/migrations)

PHOENIX observed locally available native PostgreSQL 16.15 on loopback with
SSL configured. Its bounded catalog returned only the administrative
database among connectable non-template databases. No visible MOTHER
physiological schema or catalog counterpart for PF-001, custody receipts or
snapshot lineage was identified. The earlier container was exited. This is
evidence about the sampled catalog, with other unobserved environments outside
scope. Local ext4 is a candidate for protected single-writer storage after
allocation and failure-domain review. Available capacity is not reserved.
The repository's NFS mount has unqualified SQLite lock and failure behavior.
The audit found no verified ingestion route, dedicated writer identity or
matching active backup/restore evidence in scope. [Sanitized catalog and persistence observations](https://github.com/ctmansfield/mother/pull/33)

**Next owners.** PHOENIX and the storage custodian provide the concrete private
allocation and protected identity, quota, retention and coherent recovery
proposal. GADGET and SENTINEL reconcile this source mapping and the sanitized
inventory with combined synthetic acceptance, paired backup/restore and the
owner's destination decision. The current dispositions remain NOT READY.
