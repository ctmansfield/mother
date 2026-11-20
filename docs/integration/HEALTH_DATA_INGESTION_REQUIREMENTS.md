# HealthBridge → MOTHER data ingestion and storage requirements

Document ID: MHB-MOTHER-DATA-001 · Revision 1 · 20 November 2026, Pacific/Guam

**Status: proposed requirements for joint review.** GADGET/HealthBridge contributes the acquisition and delivery requirements; MOTHER owns reconciliation with its archive, ingestion and inference architecture. This document establishes a review baseline, not a selected production topology or permission to move personal data.

## Purpose and authority

Chad requested: “lets build a requirements doc on our side of it that we can put into mother to help establish that. for the time being we can shift our work to mother.” The objective is a recoverable path from collected phone data to evidence MOTHER can supply to local models, with explicit storage ownership and provenance.

Current authorization covers requirements, repository documentation and a review branch/PR. Production placement, live ingestion, personal-data transfer, collector cutover, new credentials and service activation require a subsequent concrete decision. The prior temporary notification route is closed. Do not reuse its connection, certificate, grants, database or delivery cursor for health ingestion. No further phone-cleanup verification is required: Chad waived it after confirming cleanup.

## Existing decisions and implementation boundaries

| Area | Observed baseline | Implication for this increment |
| --- | --- | --- |
| Active phone collector | JSON HealthArchive for HR and HRV SDNN; existing acquisition/anchor behavior retained through foreground release qualification | Start with a read-only export of a captured authoritative archive; do not silently switch acquisition to SQLite |
| Phone SQLite work | Migration, diagnostic acquisition, candidate union and synthetic authority/recovery implementations have different roles | An available SQLite file is not automatically the live authoritative store or a complete-history claim |
| Upload proof | Earlier four synthetic fixtures and signed receipts were reconciled once each | Useful transport evidence, not production real-data authorization or a completed physiological pipeline; never replay those committed fixtures |
| Notification proof | Foreground server → phone alerts passed; test route closed | Opposite direction from ingestion; no ingestion or background-acquisition claim follows |
| PF-001 | Separate immutable SQLite physiological archive and replay implementation exists on review source | Reconcile and reuse its contracts rather than invent a second incompatible archive; integration PR #18 remains unmerged at this review |
| MSE addendum | MOTHER owns source evidence and scoped snapshots; models write separate derived results | Preserve this ownership boundary in ingestion and retrieval |
| Long-term memory ADRs | PostgreSQL/pgvector memory adapter design exists; ADR status is Proposed | Model memory is a separate concern from canonical measurement history; no production database choice is implied |
| Legacy storage | CSV/optional SQLite logging and Parquet analytics coexist with other persistence | Inventory each role; file presence does not decide the new system of record |

This baseline is a source/document review, not a fresh host inventory. It does not establish which database, disk, container or backup is running today.

## Target information flow

```text
Phone acquisition archive (continues independently)
  → read-only export + durable delivery outbox
  → private authenticated MOTHER ingestion boundary
  → retained received artifact + durable acceptance ledger
  → versioned normalization + authoritative physiological archive
  → scoped immutable evidence snapshot / query API
  → model or MSE run
  → separate derived result store linked to exact inputs
```

Artifact retention and database commitment need an explicit recoverable protocol; the diagram does not assume a transaction spanning a filesystem and database. Receipt status must distinguish received bytes, durable custody, normalization and model processing.

## Acquisition and export requirements

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| ACQ-01 | Collection continues when network, MOTHER or inference is unavailable. Export reads a coherent captured view without modifying acquisition anchors, tombstones or original files. | Offline/network-failure tests; unchanged acquisition state; snapshot consistency checks |
| ACQ-02 | Identify the authoritative export source and export revision. Preserve original snapshots and a manifest binding artifact digest, byte length, schema, exporter version and source scope. | Reproduce the manifest from exact captured bytes; fail if capture changes |
| ACQ-03 | Preserve native UUID, metric, interval, original available value/unit representation, source app/bundle, receipt time and deletions. Missing device/calibration/source-revision metadata stays explicitly unknown. | Field mapping and loss report; unknown-field fixtures; no invented provenance |
| ACQ-04 | Preserve source tombstones, including unknown-UUID tombstones. Absence from a partial export is never interpreted as deletion. | Unknown deletion, late arrival and delete-before-add cases |
| ACQ-05 | Separate HealthKit acquisition anchors, export progress and server acceptance checkpoints. Never transplant opaque anchors between stores or derive ordering from anchor bytes. | Restart and stale-scope tests; independently inspect each checkpoint |
| ACQ-06 | Use finite page/batch sizes, bounded session work and a disk-pressure policy. Do not truncate a committed page while retaining its advanced checkpoint. | Boundary-size, interruption and full-disk tests |
| ACQ-07 | Declare actual history interval, permissions/coverage limitations and first-capture semantics. Empty data is not proof of complete permissions or no events. | Partial/empty/sparse-source manifests retain unknown coverage |

## Private delivery and acceptance requirements

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| ING-01 | Use authenticated HTTPS with hostname verification, scoped subject/source authorization, request size limits and no redirect-based credential forwarding. Network placement must be explicitly selected. | Wrong host/token/scope, redirect, oversized and malformed request tests |
| ING-02 | A batch has a stable delivery identity plus content digest and scope. Identical retries return the original commitment identity; same identity with different bytes is a conflict. | Duplicate/concurrent/changed-body tests, including lost response after commit |
| ING-03 | Persist the delivery outbox before transmission. Retain unacknowledged batches across app/server restart; uncertain responses cause reconciliation or identical retry, not a new batch identity. | Kill before/after send and commit; recover without silent loss or duplicate logical observations |
| ING-04 | A durable receipt binds subject/source scope, batch identity, artifact digest, schema and server commit identity/time. HTTP success alone is insufficient unless its documented semantics provide that binding. | Validate receipt against reopened retained artifact and archive/ledger |
| ING-05 | Define states such as rejected, durably received, normalized and quarantined. Invalid normalization must not masquerade as successful physiological ingestion. | Invalid-record policy and explicit receipt/state transition tests |
| ING-06 | Couple archive changes and acceptance ledger transactionally, or implement a journal/reconciliation protocol for separate stores. Recover orphan artifacts, missing blobs and interrupted normalization. | Fault injection at every durability boundary; deterministic repair report |
| ING-07 | Quarantine conflicts/unsupported schemas with bounded private retention and actionable status. No silent coercion, partial discard or checkpoint advancement past rejected work. | Mixed-validity, schema evolution and conflicting-source fixtures |
| ING-08 | Cancellation, sign-out, grant remap or changed source scope fences in-flight work. A receipt from another scope cannot acknowledge the current outbox. | Late callback, credential expiry and remap/replay tests |

## Storage and lifecycle requirements

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| STO-01 | Keep original received artifacts separate from normalized observations, derived features/results and searchable model memories. Each role has an accountable owner and canonical locator. | Storage inventory and selected architecture decision |
| STO-02 | Preserve immutable observation revisions, explicit deletion/supersession and source artifact links. A correction changes the current projection without erasing prior evidence. | Correction/deletion replay and current-view tests |
| STO-03 | Preserve biological interval, source availability if known, first MOTHER receipt and durable commit time/sequence. Do not backdate later knowledge into historical online decisions. | Late-arrival/correction tests and retrospective-versus-online replay distinction |
| STO-04 | Declare decimal/unit conversion and timestamp precision policies, parser/normalizer versions and any introduced loss. Preserve unknowns and sensor-derived versus measured classifications. | Round-trip mapping/loss report and unit/time boundary fixtures |
| STO-05 | Raw data and credentials never enter GitHub, shared model memory or routine logs. Use least-privilege service identities, secret references, encrypted transport and an explicit at-rest protection decision. | Access-denial and sanitized-log checks; reviewed key custody plan |
| STO-06 | Define capacity, retention, pruning, backup frequency, recovery objectives and custodian for every store. Unacknowledged phone data cannot be pruned silently. | Capacity estimate and retention decision; alert before quota exhaustion |
| STO-07 | Verify recovery from a separate backup, including artifacts, ledgers, schema/migration version and linkage. A checksum or successful backup job alone is not a restore test. | Isolated restore and reopened-store reconciliation |
| STO-08 | Distinguish source tombstones from owner-requested erasure. Retention/erasure must cover backups, projections, derived results and memory references under a documented policy. | Reviewable deletion/retention procedure; invalidated serving references |
| STO-09 | Database migration and rollback preserve old evidence and authoritative commitment boundaries. Do not treat phone SQLite cutover as a prerequisite for the first captured-archive adapter. | Migration/rollback rehearsal against synthetic captured artifacts |

## Model and MSE access requirements

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| LLM-01 | Models consume authorized queries/snapshots through a bounded interface, not unrestricted database/filesystem access or ingestion credentials. | Cross-subject/purpose denial and bounded-query tests |
| LLM-02 | Snapshots bind exact observation revisions, artifacts, scope, measurement interval, knowledge cutoff, normalization version and coverage assessment. | Reproduce exact input manifest and reject mixed pagination/snapshot scope |
| LLM-03 | Keep numerical measurement/feature retrieval distinct from semantic memory search. An embedding hit is not an authoritative sensor record. | Responses resolve evidence references to original archive revisions |
| LLM-04 | Results record model/configuration/code versions, exact input snapshot, run identity, missingness, freshness and uncertainty. Derived or simulated values cannot become measured records. | Output validation, lineage and explicit unavailable/unknown cases |
| LLM-05 | Corrections, deletions and authorization changes invalidate affected current snapshots/results without rewriting historical explanations. | Dependency invalidation and access-revocation tests |
| LLM-06 | Inference unavailability never blocks ingestion. Context size, concurrency and processing backlog have finite limits and observable states. | Model-offline ingestion and bounded backlog/recovery tests |

## Decisions MOTHER must settle before production

The following are **recommendations or questions**, not decisions already made by Chad.

| Decision | Recommended starting point | Required decision/output | Proposed owner |
| --- | --- | --- | --- |
| D-01 Compute and storage placement | Run ingestion/archive independently from GPU inference; assess LLM host versus a dedicated existing VM/service | Exact host/service boundary, durable volume, network path, resource isolation and custodian | MOTHER + infrastructure |
| D-02 Canonical physiological database | Evaluate the existing PF-001 SQLite archive first; compare PostgreSQL only against measured concurrency/operations needs | Accepted ADR with transaction model, writer concurrency and migration strategy | MOTHER archive owner |
| D-03 Original artifact storage | Protected append-only artifact directory/object store with digest references | Selected location, permissions, atomic publication and orphan-recovery protocol | MOTHER + infrastructure |
| D-04 Phone delivery mode | Captured-file adapter first, then durable bounded upload; preserve current collector | Export schema and mapping, outbox/receipt contract, foreground/background limits | HealthBridge + MOTHER ingest |
| D-05 Retention and disaster recovery | Retain accepted originals during initial qualification; set explicit limits before live collection | Data volume estimate, retention/erasure policy, backup destination, RPO/RTO and restore evidence | Chad + storage custodian |
| D-06 Model consumption | Scoped snapshot/query API; derived outputs and pgvector memories separate | Minimal authorized query contract and result lineage schema | MOTHER/MSE |
| D-07 Initial dataset and purpose | Synthetic HR/SDNN and tombstones, then a specifically approved captured interval | Subject/source scope, purpose, interval and authorized recipients | Chad |
| D-08 Operations | No dependency on model uptime; visible ingestion lag and failed batches | Health checks, support ownership, alert thresholds, recovery and credential lifecycle | MOTHER operations |

Performance numbers are not selected yet. Before live use, agree maximum batch bytes/records, phone/server queue quotas, expected daily volume, permitted upload delay, query latency and backup recovery objectives. Measure against representative synthetic scale first; do not invent throughput or completeness guarantees.

## Delivery sequence and completion criteria

1. **Requirements reconciliation:** MOTHER responds to each requirement with existing implementation/evidence, planned change or explicit gap. Resolve D-01 through D-08 in an ADR; record owners and open decisions. A general agreement does not silently select a host/database.
2. **Offline captured-archive adapter:** synthetic HealthArchive → preserved artifact → versioned PF-001 mapping → isolated archive → scoped snapshot. Include additions, tombstones, duplicates, conflicts, late arrivals and explicit unknowns. No live phone or personal records needed.
3. **Durable transport prototype:** test outbox, receipt, uncertain commit, separate-store recovery and authenticated replay in isolation. Use new synthetic identities; never reuse committed historical fixtures.
4. **Operational qualification:** separately authorize selected runtime, backup/restore and network controls. Demonstrate service restart and inference-offline operation; record exact source, artifact, migration and configuration pins.
5. **Bounded personal-data pilot:** after explicit approval of source interval, destination and retention, reconcile exported, transmitted, durably retained, normalized and model-visible records by identities/digests and declared exclusions. Do not infer success from matching counts alone.
6. **Production decision:** accept actual evidence, known gaps, privacy/retention and rollback. Continuous service, phone cutover and richer acquisition remain distinct decisions.

For this document, completion means a reviewable requirements contribution and a concrete MOTHER decision list. It does not mean transport implemented, personal data imported, database selected, deployment approved or model accuracy established.

## Source and evidence register

Reviewed MOTHER main: `c05f38096406965496d7d4a09edf4b3575235311`. Links to main below are navigation aids; this pin identifies the reviewed document versions.

- [MSE integration ownership, observation/snapshot contracts and proposed sequence](../mse/INTEGRATION_ADDENDUM_2026-11-19.md).
- [Preserved HealthBridge source audit and acquisition/export gaps](../../research/mse/reference-v0.1.0/docs/HEALTH_BRIDGE_AUDIT.md). Historical audit pins are retained there; it is not a fresh device inventory.
- [PF-001 source and immutable archive](https://github.com/ctmansfield/mother/pull/1), reviewed head `5a6f71a45dc64880bc06a0e1a50c7d05ff119cba`.
- [Combined MOTHER integration](https://github.com/ctmansfield/mother/pull/18), observed open/unmerged at `b4e70b7123689ec164ba09e2974645ae36b184a2`; MotherHealthBridge is explicitly excluded from that PR.
- [Proposed long-term memory architecture](../architecture/ADR-0001-long-memory.md) and [adapter](../architecture/ADR-0002-memory-adapter.md); neither settles physiological production storage.
- [Foreground qualification and server closure](https://github.com/ctmansfield/mother-health-bridge/issues/4#issuecomment-7041075143), active app source `9b85cf1a12ecb1f91f414e8f5366d81f3dbb81d6`.
- [Owner-confirmed phone cleanup](https://github.com/ctmansfield/mother-health-bridge/issues/4#issuecomment-7041097851). Later chat disposition waives another phone verification.
- [Nightscout source-qualification follow-up](https://github.com/ctmansfield/mother/issues/10). This requirements contribution does not reopen NAS glucose or authorize credential/source access.

A source review or synthetic proof supplies engineering evidence, not new authority to access or publish physiological data.
