# Synthetic native BP transfer to a separate guest store

This source candidate is based on native importer PR #51 at
`91cc2cf02f2dd9cc012203bebc629324a9aa8f2e`. It uses only synthetic
enrollment and source names. Its purpose is `mother-bp-review`.
The destination is a fresh private guest database under a dedicated
non-login service account, with an independently granted quota and
listener. The existing 8446, 8447 and 8448 listeners are outside this
candidate. Guest environment qualification and an independent schema
review are pending.

## Sender and payload

On the protected Mac, reopen the authenticated native import catalog and
call `typed_vm.project(catalog, original_sha256)`. The function accepts
only a native original with the paired ciphertext custody receipt.
Retain the exact projected bytes in protected custody until reconciliation.
The guest receives a canonical JSON envelope of at most 4 MiB with at
most 10,000 explicitly paired native BP occurrences. Version 0.1 fields
are enrollment, source instance, purpose, opaque native artifact receipt
ID and sorted typed rows. Each row contains the member number, top-level
ordinal, protected normalized revision, UTC event-end and two canonical
mmHg decimals. Equal clocks and measurements preserve distinct source
occurrences. The projection describes the artifact's paired sightings,
whose semantics are distinct from a reconciled current view across native
and API sources. Non-BP families, standalone or ambiguous measurements,
raw member contents, native identifiers, paths, source clock strings,
original ZIP, age identity and private provenance key stay off the guest.

## Guest and reconciliation

Configure a new private guest address and listener port. The protected
JSON config has fields `bind`, `port`, `db`, `enrollment`,
`source_instance`, `artifact_receipt`, `certificate`, `key`, `client_ca`,
`grants`, `start`, `end` and `snapshot`. Use an exclusive private database
directory. The two grants are `writer` and `reader`, each containing
`[client_certificate_der_sha256, expires_at_utc]`. The pair of snapshot
bounds and all clocks use canonical UTC with six fractional digits.
Pin the artifact receipt from the private Mac catalog out of band.
Provision a dedicated client CA and distinct leaf keys and approve the
guest server CA and hostname before transfer.

The synthetic entry points are
`python -B -m integrations.mse_health_history.typed_vm_https init CONFIG`
and
`python -B -m integrations.mse_health_history.typed_vm_https serve CONFIG`.
Use `TypedClient` with a hostname-verifying TLS context and the assigned
client certificate. Its `put(raw)` targets
`/v1/native-typed/{enrollment}/mother-bp-review/projection`. The writer can
submit only the pinned artifact and has a finite lease. The guest commits
all typed rows and one receipt together in a FULL-synchronous SQLite
transaction. New acceptance returns 201, exact replay returns the same
receipt with 200, and different canonical contents at the pinned artifact
return 409. An incomplete transaction has no visible receipt or rows.

On a lost response, the distinct reader calls `receipt()` and verifies
the returned receipt against the retained bytes with `verify_receipt`.
The receipt binds schema, purpose, enrollment, source, artifact, projection
digest, bytes and pair count. Absent readback permits exact replay only
during the authorized writer lease. Conflict, TLS failure or indeterminate
storage results call for operator reconciliation with the original custody
and guest state preserved. The reader may query `read(start, end)` within
its configured UTC interval using its time-limited certificate grant.
Queries open SQLite read-only and return only event-end, mmHg pairs and
the binding receipt ID. Guest snapshots contain sensitive time and
physiology and require protected consumer custody.

## Qualification boundaries

Synthetic loopback qualification exercises the real mTLS path into a fresh
database, lost final response, reopen, exact replay, conflict, role denial,
cutoffs and the read-only BP query. It uses the authenticated fabricated ZIP
fixture from the native importer. A private guest source pin, isolated service
identity, storage protection, quota/reserve, TLS/lease controls and approved
environment must be independently verified before guest execution with any
real input. Keep backup and restore work deferred.
