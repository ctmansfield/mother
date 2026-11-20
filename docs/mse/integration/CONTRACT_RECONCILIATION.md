# MSE contract reconciliation

MSE-INTEGRATION-20261120-01 r1 · ATLASv2 · Source reconciliation and offline interface proposal.

[Dispatch](https://github.com/ctmansfield/mother/pull/23#issuecomment-7041443650) · [30 requirements](https://github.com/ctmansfield/mother/blob/91d67e387e91d93a7a60aec03c8164c11c7aa994/docs/mse/HEALTH_DATA_INGESTION_REQUIREMENTS.md) · [Plan](https://github.com/ctmansfield/mother/blob/91d67e387e91d93a7a60aec03c8164c11c7aa994/docs/mse/IMPLEMENTATION_PLAN.md) · [Integration addendum](../INTEGRATION_ADDENDUM_2026-11-19.md) · [Draft interfaces](contracts/README.md)

## Source seams and mismatches

| Seam | Observed at exact source | Proposed first-slice mapping |
| --- | --- | --- |
| HealthArchive | [Active ContentView.swift](https://github.com/ctmansfield/mother-health-bridge/blob/9b85cf1a12ecb1f91f414e8f5366d81f3dbb81d6/MotherHealthBridge/ContentView.swift) embeds SavedReading/HealthArchive. Default Codable JSON contains readings, opaque Data anchors, dictionary tombstones and backfillStart. HR is bpm and SDNN is ms. Deletion can exist in both the reading and dictionary, including a UUID without a reading. receivedAt and deletion time are collector clocks. | ORACLE consumes captured bytes read-only, supplies declared scope, normalizes Swift Date, preserves a locator for each original fact and records unavailable device/calibration/source revision and permission evidence. Recheck source digest/length when reopening. |
| PF-001 archive | [PR #18 archive.py](https://github.com/ctmansfield/mother/blob/b4e70b7123689ec164ba09e2974645ae36b184a2/mother/physiology/archive.py), [schema](https://github.com/ctmansfield/mother/blob/b4e70b7123689ec164ba09e2974645ae36b184a2/mother/physiology/schemas/v1.schema.json), [I01 recovery](https://github.com/ctmansfield/mother/blob/b4e70b7123689ec164ba09e2974645ae36b184a2/mother/physiology/receipt_recovery.py). Unmerged dependency. Archive.begin_run and commit_batch support originals, source revisions, normalized records, source heads and checkpoint only on completion. Source head uses observed_at, and current_records has no as-of query or explicit HealthKit delete operation. The I01 receipt verifies a single event envelope; its wire schema is distinct. | FORGE uses PF-001 artifact bytes and commit seam. Bind scope to both run and receipt. Preserve delete as a raw typed source revision with no invented normalized observation. Resolve current and cutoff views over retained committed operations; a late upsert cannot revive a tombstoned UUID. Keep one acceptance ledger tied to PF-001 run identity. If a separate journal is needed, prove reopen/reconciliation at artifact, archive and receipt boundaries. |
| PF-001 observation | make_observation validates source_revision_id, lineage, enum, timestamps and derivative method. Existing first_seen_at and ingested_at mean this system's observation and ingestion. Neither is the collector clock. | Use scoped stable source key and immutable source revision. Map original_value/original_unit and decimal value/unit; SDNN is vendor_derived with declared HealthKit SDNN method and unknown device/calibration. Carry collector receipt in metadata and retain authoritative commitment separately. Different processing versions require distinct immutable normalized IDs. |
| MSE | [adapters.py](https://github.com/ctmansfield/mother/blob/c05f38096406965496d7d4a09edf4b3575235311/research/mse/reference-v0.1.0/prototype/mse/adapters.py), [contracts.py](https://github.com/ctmansfield/mother/blob/c05f38096406965496d7d4a09edf4b3575235311/research/mse/reference-v0.1.0/prototype/mse/contracts.py), [storage.py](https://github.com/ctmansfield/mother/blob/c05f38096406965496d7d4a09edf4b3575235311/research/mse/reference-v0.1.0/prototype/mse/storage.py) and model.replay. Native replay takes strict observation rows with positive scalars, canonical scope/native IDs and received_at, and separate {observation_id, deleted_at} tombstones. Reference Store rejects conflicting immutable values under one observation ID. Its optional global receipt cutoff filters source receipt and event end and is retrospective. | PROVENANCE projects one selected revision per UUID into an isolated reference store per snapshot, using identifier("observation", subject_id, source_instance, native_id) and preserving the full authoritative scope outside the envelope. Use collector_received_at for the reference received_at slot, with its meaning explicit in provenance. Filter authoritative eligibility upstream using MOTHER commit sequence. Do not ask the reference cutoff to reconstruct archive availability. Bind projected input digest, snapshot, adapter/code/config/run and unknowns externally. |

A record revision digest binds source content independently of capture path or ingest clocks. A receipt binds a batch to a capture and export; a snapshot binds exact accepted revisions to a local cutoff. These identities are distinct from a HealthKit anchor. Equal artifacts establish byte identity. Authorization, evidence quality and medical meaning are separate gates.

## Requirement matrix

**Existing** records source capability only. **Next evidence** describes implementation/acceptance still to obtain unless expressly identified as existing. Rows do not assert synthetic, runtime or production PASS.

| ID | Existing evidence / gap | Next offline evidence or separate dependency |
| --- | --- | --- |
| ACQ-01 | Collector persists its own JSON; reference adapter accepts captured bytes. No capture handoff qualified. | ORACLE/NICKY verify read-only digest and stable captured snapshot with inference absent. |
| ACQ-02 | PF-001 can store original digest/bytes; no HealthArchive capture manifest. | ORACLE export binds file digest, length, scope, schema and exporter version; reject mismatches. |
| ACQ-03 | SavedReading carries UUID, metric, interval, value/unit, source/bundle and collector receipt. Device/calibration absent. | ORACLE maps exact source fields and demonstrates explicit loss using NICKY fixtures. |
| ACQ-04 | Source has dictionary and embedded deletion; MSE reference permits unseen UUID tombstone; PF-001 lacks typed delete schema. | FORGE/ORACLE retain both source forms, test delete-before-add and partial absence. |
| ACQ-05 | HealthKit anchors opaque; PF-001 checkpoint only on complete range. | ORACLE/FORGE keep anchor, export batch and receipt separate; test stale scope/reopen. |
| ACQ-06 | No bounded phone exporter/outbox or disk-pressure policy qualified. | ORACLE/FORGE use finite synthetic fixtures; Stage C proves interruption and limits before upload. |
| ACQ-07 | Backfill start is configuration, not permission/completeness. | NICKY adds empty, partial and sparse captures with explicit coverage unknown. |
| ING-01 | Earlier foreground messaging/transport is a separate authority and purpose. | Stage C/E require scoped HTTPS, redirect/size/auth denial, placement and owned qualification. No listener in this slice. |
| ING-02 | PF-001 dedupes immutable revisions; I01 has event-specific retry/recovery. | FORGE proves same scoped batch returns original receipt, changed bytes conflict, lost response/reopen stable; concurrency later. |
| ING-03 | No HealthArchive delivery outbox. | Stage C durable outbox and restart/uncertain-response fixture. |
| ING-04 | I01 receipt ties one event envelope to archive; no capture receipt. | FORGE reopens exact artifact and PF-001 run; cross-check receipt scope/hash/time/sequence. |
| ING-05 | PF-001 has run state and dispositions; coverage/normalization must stay separate. | FORGE tests durably_received, normalized, quarantined and rejected transitions. |
| ING-06 | PF-001 commit_batch can atomically retain original/revisions/records; separate ledger boundary unproven. | FORGE injects faults at custody, archive commit and receipt publication; journal recovers exact identity. |
| ING-07 | PF-001 supports dispositions; HealthArchive mixed-validity quarantine unproven. | FORGE/NICKY reject or quarantine whole ambiguous batch and prove no checkpoint advancement. |
| ING-08 | No HealthArchive grant/remap lifecycle. | FORGE checks scope mismatch locally; Stage C fences generation, expiry, sign-out and late receipt. |
| STO-01 | PF-001 artifacts/records and MSE derived store have distinct roles. | FORGE/PROVENANCE demonstrate separate evidence and scratch replay; PHOENIX maps production custodians under D-01–D-03. |
| STO-02 | PF-001 immutable revisions and heads exist; heads alone cannot resolve delete/late arrival. | FORGE/PROVENANCE prove corrected/current/historical synthetic views, preserving originals and delete facts. |
| STO-03 | HealthArchive receipt and PF-001 clock fields available with different meanings. | Bind collector time, MOTHER receipt/commit/sequence and unknown source availability; cutoff and late-arrival checks. |
| STO-04 | PF-001 and MSE validate unit/class; current source loses metadata. | ORACLE/PROVENANCE verify Swift epoch, decimal policy, units, SDNN classification and explicit loss. |
| STO-05 | No production identity, custody or at-rest decision. | SENTINEL verifies synthetic-only fixtures and sanitized reports; infrastructure/private policy separate. |
| STO-06 | Capacity, quotas, retention and RPO/RTO unselected. | PHOENIX proposes measurable limits and backup/alert tradeoffs; no live inventory. |
| STO-07 | Archive reopen exists; independent complete restore remains open. | PHOENIX rehearses synthetic artifact/ledger/DB restore with schema and linkage checks. |
| STO-08 | Source delete and reference invalidation exist; protected erasure policy absent. | Demonstrate tombstone suppression without erasure; owner policy governs backups, derived and memory references. |
| STO-09 | PF-001 schema migration and separate phone migration work exist. | PHOENIX rehearses isolated rollback and reader compatibility; active JSON collector unchanged. |
| LLM-01 | MSE reference runs from files/local DB; no authorized query enforcement. | PROVENANCE passes scoped snapshots only; SENTINEL checks scope mismatch; service auth remains Stage C. |
| LLM-02 | Reference global cutoff is retrospective and lacks revision-bound authoritative coverage. | Build deterministic snapshot scoped by cutoff, revision/artifact/receipt and coverage; test later commit exclusion. |
| LLM-03 | Numerical reference is separate from proposed semantic memory. | Preserve direct revision locators; no embedding-based measurement substitution. |
| LLM-04 | Reference returns model/config/dataset lineage and explicit unknowns, with uncalibrated uncertainty. | Attach exact bridge/snapshot digest, versions and unavailable result; derived-only namespace. |
| LLM-05 | Reference conservatively invalidates on new data; no auth-revocation serving layer. | Verify synthetic cutoff/correction/deletion changes current eligibility, preserves prior manifests; retraction/access enforcement later. |
| LLM-06 | Offline invocation is separable from PF-001 writes; backlog/throughput unqualified. | FORGE/PROVENANCE show archive acceptance without model; Stage C/D define quotas and backlog state. |

## Decision register

| ID | Offline choice for review | Production owner / remaining decision |
| --- | --- | --- |
| D-01 | Separate local ingestion from offline inference. | MOTHER + infrastructure select topology, volume and isolation. |
| D-02 | Reuse pinned PF-001 SQLite seam in disposable synthetic storage. | Archive owner decides concurrency, support and migration model. |
| D-03 | Use digest-bound original bytes and a recoverable acceptance ledger. | MOTHER + infrastructure choose protected artifact placement and recovery strategy. |
| D-04 | Captured JSON adapter first. | HealthBridge + ingest determine bounded upload/outbox and capabilities. |
| D-05 | Keep synthetic originals during acceptance. | Chad + custodian choose quotas, erasure/retention, backups, RPO/RTO. |
| D-06 | Immutable evidence snapshot plus isolated reference bridge. | MOTHER/MSE decide authorized query interface and derived retention. |
| D-07 | New synthetic HR/SDNN and tombstones only. | Chad decides any later dataset, purpose, scope and recipients. |
| D-08 | Ingestion remains independent of model. | Operations define identity lifecycle, lag, failures, alert and recovery ownership. |

GADGET owns interface freeze and shared context registration. Authors own implementation and tests on separate heads. Current matrix is source review; it makes no deployment or live-data claim.
