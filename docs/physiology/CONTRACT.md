# Physiology evidence contract 1.0.0

Canonical machine schema: `mother/physiology/schemas/v1.schema.json`.
Implementation owner: PM/integration. The Coach copy is pinned byte for byte
and verified by the release compatibility check. Schemas/migrations have one
writer. This contract extends the existing file/database boundaries and does
not create a new production service.

## Records and clocks

| Record | Meaning and required provenance |
| --- | --- |
| `source_revision` | Source instance/collection/native identity or declared fallback; canonical payload hash distinct from original byte hash; original record; first-seen and ingestion time; genuine source availability if supported; import-run ID |
| `observation` | Subject and exact channel/native type; measurement interval; original value/unit plus normalized value/unit; valid/missing/invalid/unobserved; epistemic type; source revision and lineage; method/device/app/site/specimen/session/group; quality and processing version |
| `stream` | Original waveform/beat artifact hash and reference; channel/unit; count; regular rate or irregular timing; gaps; session and clock mapping. Irregular RR is not reconstructed from average HR |
| `session` | Recording interval and source revisions; device/app/firmware/configuration; body site; clock information; garment/contact configuration |
| `event` | Context/exercise/sleep/exposure/instrument condition/user marker/question/answer/recommendation/acknowledgment/reported action/observed action/outcome; occurrence interval, known and recorded time; links and original payload |
| `import_run` | Adapter/schema/processing versions, source scope, input hashes or requested API range, counts and rejection/unsupported records, completion state and durable checkpoint |

Measurement/occurrence time answers when the event happened. Source availability
means a documented time the source had the information. First-seen means the
first observation by this importer of that exact revision. Ingestion means this
system's durable processing time. Server modification timestamps remain
separate. Historical source availability is null unless actually supported;
neither ingestion nor a source modification timestamp fills it.

All canonical times include an offset and normalize to UTC for comparison.
Original timestamp value, offset, precision and units belong in retained raw
records and `clock`/metadata. Numeric auto parsing is per row: absolute values
below 1e11 are epoch seconds, from 1e11 to below 1e14 are epoch milliseconds.
Use explicit units for early millisecond epochs or ambiguous sources. Naive
times require an explicit IANA timezone; ambiguous/nonexistent DST local times
require an actual source offset. No host timezone is silently substituted.

Unknown future outcomes remain null/ineligible. Zero remains a valid value.
`epistemic_type` distinguishes `measured`, `vendor_derived`, `derived`, `imputed`,
`inferred`, `clinical_interpretation`, and `reported`. Derivatives name their
method and processing version. Original records are never rewritten by a
cleaning or inference pass. Sleep stages remain vendor-derived. SDNN and RMSSD
remain separate exact metric identities. BP components share a group ID.
Specimen/analyte remains null/unknown when the source cannot establish it.

## Identity and revision rules

Native identity is scoped by source instance and collection. A canonical payload
hash identifies an immutable revision. Original response/file bytes have their
own SHA-256. Repeat sightings are recorded without adding a logical observation;
first-seen time of an existing revision is preserved. A returned change creates
a new revision. A reversion may point the current head back to a preserved old
revision; current state is not selected by maximum first-seen time alone.

An imported session uses its first declared `source_revision_ids` entry as the
anchor for the current-revision projection. Every declared reference is checked
for existence and subject consistency; the complete list remains immutable in
the normalized record. Replay includes those references and any recording
session referenced by a displayed observation/event, even when the session's
declared interval falls outside the selected view. Unknown-occurrence events
may be selected by `recorded_at`; that selection does not invent occurrence or
historical availability.

Without native identity, the adapter declares its fingerprint/position rule and
flags ambiguity. Equal value/time from separate sources never merges records.
Relayed copies require explicit provenance evidence and remain linked without
counting as independent corroboration. Partial-response absence never means
deletion. An explicitly supported deletion marker may update the current head
while preserving all historical evidence.

## Additive archive and migration

`mother/physiology/migrations/0001_archive.sql` initializes a selected SQLite
archive. It does not apply to existing PostgreSQL databases. Tables retain raw
artifacts, source revisions, normalized records, repeat sightings, source heads,
import runs and checkpoints. Only a completed durable acquisition may advance a
checkpoint. Incomplete acquisition remains visible and preserves prior data.

The archive path is explicit. Local SQLite belongs on a filesystem with suitable
locking/durability; deployment storage must be verified before using a network
mount. This release has no evidence qualifying the user's NAS mount for SQLite.
Parquet is regenerated from retained current records, and is not the source of
truth. Existing Parquet files require provenance reconciliation before import;
this release does not silently convert them into original records.

## Compatibility and scope

Existing legacy analytics columns (`ts` epoch milliseconds and `sgv` mg/dL)
remain a view with additional source identity, availability and processing
metadata. Consumers must explicitly choose a strict availability policy or
declare historical timing assumptions. A display can replay measured occurrence
times without claiming it represents what a live predictor knew then.

Contract 1.0.0 does not define treatment policy, a clinical diagnosis, a recovery
score, device operating limits, prompt thresholds or deployment authority.
