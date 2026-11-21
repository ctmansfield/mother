# Next app build — expanded collection and archival retention

Instruction: [MSE-LIVE-PILOT-PREP-20261121-04 r1](https://github.com/ctmansfield/mother/pull/23#issuecomment-7056948768). Chad selected archival retention and asked for high-value types beyond heart rate and HRV in the next app build. This document records the selected scope; implementation and qualification require the owning source and test receipts.

## Selected read scope

| Group | HealthKit records | Purpose in the pilot |
| --- | --- | --- |
| Cardiovascular | Heart rate, HRV SDNN, resting heart rate, walking heart-rate average | Compare available cardiac measurements across rest and activity |
| Overnight context | Respiratory rate, oxygen saturation, sleeping wrist temperature | Preserve available overnight measures alongside sleep intervals |
| Sleep | Sleep-analysis intervals and available stages | Describe recorded sleep timing and stage coverage without inventing missing intervals |
| Activity | Step count, walking/running distance, active energy, basal energy, Apple exercise time | Put physiological measurements in activity context |
| Workouts | Type, start/end, duration, recorded distance and energy when available | Preserve exercise context without collecting location or route geometry |

All types are read-only. Device/OS availability and partial read permissions must not block core collection. Empty results are not proof of denied permission or of zero activity. Source-specific records and overlap remain explicit. No ECG/waveforms, routes/GPS, reproductive data, names, device serial numbers or arbitrary metadata are in this scope. SDNN is retained as SDNN; it is not converted into an invented RMSSD value.

## Archival retention

Accepted exported originals, source/revision identities, normalized records, receipt/schema versions and processing lineage have no automatic age-based purge. A HealthKit deletion or replacement is represented explicitly; current views exclude deleted records while historical archive versions remain auditable. Deleting a record in Health does not itself erase the archived copy. Explicit archive erasure is a separate user action and must not be confused with stopping collection or the pilot cutoff.

Retention covers only approved exported fields. The private archive may remain identifying through physiology, timestamps and source descriptors; pseudonymous IDs do not establish anonymity. Access controls and at-rest protection remain part of live launch readiness. Archival retention does not establish redundancy or recoverability. Backup/restore remains deferred.

## Next-build acceptance

- Additive collector/store changes preserve existing HR/HRV records and query anchors. Versioned adapters handle quantities, sleep categories and workout summaries without coercing all records into scalar quantities.
- Persistent incremental queries preserve sample IDs, original times, canonical units, source/revision/deletion semantics and bounded query progress. Unavailable or unknown results are reported explicitly.
- Real-data export uses a durable queue, stable batch IDs, bounded batch size/backpressure and receipt-only dequeue. Live transmission is disabled by default pending a separately scoped pilot launch; synthetic testing remains separate.
- Independent synthetic tests cover each selected record shape, partial permission/availability states, migration, restart, offline retry, duplicate/conflict/deletion behavior, and exact app-to-archive/export/downstream lineage.
- A signed artifact is bound to the tested source and preserves existing collector data. No phone install or physical background-delivery qualification is claimed by a host build.
- The app displays collection, queued and acknowledged states separately and supports a clear collection stop. Background entitlement/query behavior and physical acceptance gaps are documented.

The current startup/CI/clean reproduction task remains active. No main merge, current archive migration, route reopening, live upload, historical backfill or LLM forwarding follows from this build-preparation instruction. The proposed pilot is 48 hours; its actual start, selected data window and activation remain to be set after readiness review. Archival retention continues beyond the pilot stop.

## Ownership

ORACLE owns the app candidate. ATLAS owns the additive record/retention contract; FORGE owns compatible schema/API/export source. NICKY independently tests collector preservation and the synthetic path. SENTINEL reviews access, logging and stop/retention behavior. PROVENANCE binds source, signed product and record lineage. PHOENIX prepares runtime-lifetime requirements without reopening ingress. LONESTAR tracks source/build/device/live states separately.
