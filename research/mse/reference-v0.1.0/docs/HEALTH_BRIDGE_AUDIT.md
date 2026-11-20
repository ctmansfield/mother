# Health bridge source audit — pinned source, no runtime changes

Inspected the parent-provided, Git-blob-verified snapshot of `ctmansfield/mother-health-bridge` at SQLite branch SHA `b2baa2e6bd2d018b6e34a07c783b7c3523366374`, and glucose-specific source/report files at `e84a848796689b9bcb247a57024bc9f8d6e576c1`. Paths and line numbers below refer to those pinned snapshots. Read `AGENTS.md`. No Swift/Xcode/device tests were run in this environment; no source, service, production data, credentials or authority settings were changed.

## 1. What is actually active

`MotherHealthBridge/ContentView.swift` contains `HealthCollector`. It reads/writes Application Support `mother-health-v03.json` (`:26–47`), requests read authorization only for **heart rate and HRV SDNN** (`:70–94`), and starts two anchored queries with their respective saved anchor and fixed archive backfill predicate (`:146–213`). `HealthArchive.swift:24–27` initializes that predicate's start to seven days before creation of a new archive; it is then persisted. This is not a promise of unlimited historical acquisition.

The active queries use `HKObjectQueryNoLimit` plus a long-running `updateHandler` (`ContentView.swift:179–209`). Saved query identity fences callbacks from stopped/replaced queries (`:223–225`). The UI starts collection when active and stops it on background (`:388–396`), so continuous foreground ingestion is not background-delivery qualification. No `HKObserverQuery` or autonomous background acquisition is established by this path.

The active app does not acquire meals, activity, sleep, raw RR, ECG, BP, ketones, lactate, temperature, CPAP or microbiome data. Those are future adapters/context feeds. The separate glucose feature is a MOTHER **read/display** client, not HealthKit glucose acquisition or an upload route.

## 2. Actual record/provenance and deletion semantics

`HealthArchive.swift:5–21` defines:

```text
SavedReading: id(UUID), kind, value(Double), unit, start(Date), end(Date),
              source, bundleID, receivedAt(Date), deletedAt(Date?)
HealthArchive: readings[], anchors[String:Data], tombstones[String:Date], backfillStart
```

The original HealthKit UUID, sample interval, source app name/bundle, normalized value/unit and local receipt are retained. The active converter (`ContentView.swift:259–271`) does **not** retain the complete source revision, source version, operating-system version, device identity/firmware, HealthKit metadata, original timezone spelling, per-reading calibration/error model or acquisition conditions. Consequently this archive is a useful normalized acquisition record, not a lossless serialization of every available HealthKit field. Unknown provenance must remain null/unknown in MSE; it cannot be reconstructed reliably from the source name.

`ContentView.swift:237–319` copies the archive, skips already-known UUIDs and previously tombstoned UUIDs, processes additions then deletions, encodes the returned secure anchor into that same copy, and atomically writes all of it before publishing the in-memory archive. A deletion in the same callback wins over an addition (`:278–289`). Unknown UUID tombstones are retained. On write error the previous archive/anchor remain selected and that query is stopped (`:320–325`). This is strong reusable batch/anchor coupling.

The active path keeps the first encountered sample for a UUID rather than checking a duplicate's physiological fields for equality. Tombstone dictionary entries can receive a later receipt time on repeated deletion, while an existing reading's first `deletedAt` is retained; these are local processing timestamps, not the HealthKit deletion occurrence time. The JSON tombstone dictionary does not record a measurement channel for an unknown deleted UUID. These facts matter for downstream provenance, but source inspection alone does not show corruption or actual conflicting UUIDs.

The current source has explicit stale-query fencing. The newer one-shot ticket contract cannot simply be attached to the active streaming `updateHandler`: `CollectorHandoffSeam.swift:4–7` explicitly rejects that equivalence. Callback ordering/recovery must be qualified at the integration boundary; no observed active-collector ordering failure is claimed here.

## 3. Four separate SQLite/candidate roles

| Component | Actual schema and role | Authority status |
|---|---|---|
| `HealthSQLiteStore.swift:88–145` | `mother-health-v04.sqlite`: `readings(uuid PK,kind,value,unit,start_time,end_time,source_name,source_bundle,received_time,deleted_time)`, index `(kind,start_time)`, `tombstones`, `anchors(BLOB)`, `settings`, single-row `migration_manifest(snapshot_filename,source_sha256,counts)`; SQLite user_version 1, DELETE/FULL | Snapshot migration/verification, not live acquisition |
| `SQLiteHealthKitAdapter.swift:68–114` | Explicitly enabled, separate `mother-health-acquisition-v04.sqlite`: `acquisition_readings(uuid,type,payload)`, typed `acquisition_tombstones`, per-type `acquisition_progress`, `acquisition_cursors(type,token,anchor,batch_digest)` | Diagnostic acquisition; normal JSON path preserved |
| `CandidateArchiveBuilder.swift:35,170–180` | Nine immutable candidate tables: observations, reading_provenance, tombstones, deletion_provenance, anchor_provenance, sources, verification_metadata, future_cursors and checkpoint; rows stored as identity/payload | Preserved source union/candidate, not an active store |
| `IncrementalCandidateRepository.swift:1,48–60,297–304` | macOS-only, temporary-root-only, explicit opt-in schema-v2 copy; original candidate tables preserved; adds acquisition tables, append-only `acquisition_receipts`, `repository_state` and independent cursors | Synthetic production-design prototype; no iPhone caller |

The migration implementation preserves original JSON and an immutable snapshot; repeat migration verifies the prior snapshot rather than importing current live JSON anew (`HealthSQLiteStore.swift:156–275,393–466`). Snapshot agreement is not equivalence to a dashboard measured at another moment.

The diagnostic adapter atomically validates query token/digest, rejects conflicting repeated UUID content, retains effective deletion state, and commits data/deletions/cursor/progress (`SQLiteHealthKitAdapter.swift:139–235`). Identical batch retry is idempotent; a replaced token is stale. The next query starts from **committed** anchor bytes (`:117–132`). Anchors remain opaque and channel-local; no numeric ordering or cross-database transplant is valid.

`OneShotHealthKitSource.swift:45–84` uses a nil history predicate, independent initial nil anchor and bounded sample-plus-deletion page size. It fails instead of truncating a page while retaining its advanced anchor. It intentionally has no updateHandler. Its normalization (`:89–107`) retains the same SavedReading fields as JSON, so it does not solve the provenance omissions above by itself.

The incremental v2 implementation preserves imported historical observations separately from its current canonical `acquisition_readings`. Future dashboard/export readers must use the canonical acquired union plus effective tombstones, **not only the immutable imported `observations` table**. Page receipts preserve batch provenance, including exact returned anchors; source anchors imported from JSON/diagnostics remain non-executable provenance.

`SyntheticIncrementalHandoff.swift` and `SyntheticCrossFileHandoff.swift` model fenced authority/recovery under macOS temporary fixtures. Their existence does not mean iOS cutover is implemented. `docs/reports/v0.4/incremental-authority-integration.md:76–83` explicitly leaves live collector durable acknowledgment, trusted high-water/rollback policy, authoritative dashboard/outbox reads and physical interruption validation open.

## 4. Glucose feature: useful read boundary, distinct acquisition authority

At `e84a848...`, `MotherHealthBridge/MotherGlucose.swift:82–115` preserves exact decimal strings, original units/values, measurement/source-arrival/ingestion times, source system/namespace/native ID/revision/device, trend, noise and quality flags. It is explicitly scoped to Nightscout interstitial glucose in mg/dL; it is not yet a generic physiological schema.

`MotherGlucoseClient` requires an HTTPS origin without embedded credentials/query/path, uses an ephemeral no-cookie/no-cache URLSession, rejects redirects, sends scoped bearer authorization and calls GET `/v1/physiology/glucose/{latest,observations,coverage}` (`:227–325`). No new credential was requested or changed by this audit.

`MotherGlucoseCache` is session-only and in memory (`:329–484`). It validates half-open windows, stable snapshot metadata, unique IDs and timestamp/ID ordering across pages, then publishes a complete snapshot atomically. It handles cursor expiry/invalidation with bounded restarts, remap/sign-out fences and authorization purge. Failed partial refresh does not publish partial rows. Measurement freshness, sync state and coverage remain distinct. Coverage is separately requested, so it is not automatically the exact same transactional snapshot as the paginated data.

This branch was integrated against SQLite base `9c89bea...`, not the later pinned `b2baa2e6...`; combined package registrations/changelog and integration tests require reconciliation before merge. No merge or branch edits were made here. The N3 server implementation remains inaccessible in the related-repository audit; the Swift consumer does not independently prove its server behavior.

## 5. Latest documented validation, correctly scoped

| Evidence | Reported result | What remains unestablished |
|---|---|---|
| Physical bounded catch-up, user report 2026-11-11, `bounded-catchup.md:87–98` | HR 7 committed pages / 700 unique observations; HRV SDNN 6 / 600; five-page session budget reached; other channel unchanged; JSON operational | Complete history, exact UUID/anchor reconciliation, post-catch-up restart, cancellation/interruption recovery |
| Latest physical reconciliation, user report 2026-11-12, `device-validation.md:3–9`, `storage-reconciliation.md:3–11` | Four stores available; migration snapshot verified; zero physiological-field conflicts; no changed/unreadable warnings; JSON operational | Exact installed SHA/time, pairwise UUID differences, unknown tombstone/duplicate membership, history completeness; four-reading discrepancy still unresolved |
| Latest SQLite authority implementation report, `incremental-authority-integration.md:53–68` | Reported host run: 194 functions / 374 cases, 22 suites; app build passed | Tests are synthetic/macOS; iPhone app compilation does not execute macOS-only repository; no tests rerun in this audit |
| Glucose draft report `mother-glucose.md:3–10` | Reported host run: 190 functions / 353 executed cases; unsigned Simulator build passed | Private HTTPS staging, interactive dashboard and physical-device checks explicitly skipped at that report's pin; not rerun here |

Reconciliation compares each captured source safely, but does not make all files one globally atomic snapshot; it detects endpoint changes and can fail closed on protected/WAL/recovery-required SQLite. Zero conflicts among shared records does not establish equal record sets. The current top sections supersede older pending-first-run statements; do not repeat the stale claim that the user has never completed bounded catch-up or reconciliation.

## 6. Recommended seam and prioritized gaps

**Best existing storage seam:** `HealthAcquisitionRepository.swift:3–12` exposes `beginQuery`, `apply`, `committedAnchor`, `progress`, `isRetryable`, with successful apply defined as whole-page-plus-cursor commit. Reuse the driver/coordinator protocol for later acquisition evolution; do not rewrite or silently activate the JSON collector.

**Best immediate MSE seam:** an offline, read-only exporter/normalizer from a captured authoritative JSON archive, plus separately qualified server glucose export/read data, mapped into the existing MOTHER physiology evidence contract. Emit archived UUID and source namespace, sample interval, local receipt, metric identity, tombstones and explicit unknown provenance. A future export of the v2 store must select current acquired records and durable receipts. This allows scientific development before production cutover.

Priority order:

1. **Source qualification and available-time semantics:** identify what was actually measured/available and when; retain sparse sampling and missingness. Existing HR/SDNN cannot identify substrate oxidation, mitochondrial function or inflammatory state.
2. **A versioned bridge-to-MOTHER mapping and replay manifest:** preserve UUID/tombstone semantics, original snapshot hash, adapter version, subject/source namespaces and genuine unknown fields. Do not treat a source app label as sensor identity.
3. **Typed contextual events:** meals/activity/sleep/medications must enter as separately sourced observations or reports. They are not currently acquired by this bridge.
4. **Production export/outbox and durable authenticated receipt:** an actual upload pipeline remains new work. Keep MSE read-only with respect to source stores.
5. **Authority/cutover and recovery:** complete the iOS production resolver, coherent dashboard/outbox reader, high-water rollback strategy and device interruption checks independently of the MSE.
6. **Richer future provenance:** version the acquisition schema for source revision/device/metadata/timezone, then add individually qualified sensor adapters. Never retroactively invent omitted metadata for existing history.

Pinned source links: [active collector](https://github.com/ctmansfield/mother-health-bridge/blob/b2baa2e6bd2d018b6e34a07c783b7c3523366374/MotherHealthBridge/ContentView.swift), [repository protocol](https://github.com/ctmansfield/mother-health-bridge/blob/b2baa2e6bd2d018b6e34a07c783b7c3523366374/MotherHealthBridge/HealthAcquisitionRepository.swift), [latest authority report](https://github.com/ctmansfield/mother-health-bridge/blob/b2baa2e6bd2d018b6e34a07c783b7c3523366374/docs/reports/v0.4/incremental-authority-integration.md), [glucose client](https://github.com/ctmansfield/mother-health-bridge/blob/e84a848796689b9bcb247a57024bc9f8d6e576c1/MotherHealthBridge/MotherGlucose.swift).
