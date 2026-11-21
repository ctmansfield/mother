# Synthetic native BP guest qualification

This candidate implements ATLAS r2 as a separate, private mutual TLS
service. It accepts a single pinned synthetic enrollment, source namespace
and import per fresh store. It leaves 8446, 8447 and 8448 outside this
service. Use the native custodian runner and a separately approved real
environment before any proposal to move real data.

## Mac projection and replay

The protected Mac reopens the exact authenticated native catalog.
`typed_vm.project` requires a private 32-byte mapping key and generates
canonical typed batches plus a terminal manifest. Its namespace is keyed
to the enrollment and source, and logical and component references are
scoped to the exact export. It carries paired, incomplete, ambiguous and
standalone BP sightings. It emits no deletion from an XML omission.
The synthetic sink accepts deletion only for a separately pinned target.
Coordinates, original names and identifiers, original strings, ZIP,
ciphertext, age identity and mapping or provenance keys stay on the Mac.

Persist the exact batch bytes in approved protected storage before send.
The API accepts sequential PUTs at
`/v1/native-bp/stores/{store_id}/enrollments/{enrollment_id}/imports/{import_ref}/batches/{batch_seq}`.
`TypedClient.put` sends the RFC content digest and verifies the complete
returned receipt. Every nonterminal batch carries at most 128 operations
and 1 MiB. The empty final batch binds the artifact and member inventory,
event bounds, previous digest, batch and byte totals, upsert and deletion
totals and normalizer. Source occurrence and quarantine counts are
custodian assertions. The sink verifies accepted batch totals and closes
the import in the same durable SQLite transaction as the terminal receipt.

Use `TypedClient.receipt` with the independent receipt-reader certificate
after lost or indeterminate responses and verify the returned receipt
with the exact retained batch bytes. First acceptance is 201 and exact
in-lease replay is 200. Sequence, predecessor and immutable byte
conflicts are 409. Before the terminal receipt commits the snapshot is
absent. A terminal receipt can still be read after the writer lease
closes, within the receipt reader's separate lease.

## PHOENIX guest handoff

Provision a fresh private guest address and dedicated listener port,
non-login account, encrypted storage and dedicated quota. Verify this
environment independently. Pin the exact reviewed source package and
Python runtime, the store digest and namespace scopes, trust roots,
hostname and finite writer, receipt-reader and purpose grants. Use
dedicated TLS keys and a separately controlled private server trust root.
Verify volume and journal placement, reserved space, resource ceilings and
denials before any authorized guest execution.

The protected config has `bind`, `port`, `db`, `scope`, `bounds`,
`artifact`, `inventory`, `max_batches`, `max_bytes`, `admitted_deletions`,
`certificate`, `key`, `client_ca`, `grants`, `start`, `end` and
`snapshots`. The two-element bounds and all clocks use UTC with six
fractional digits. The artifact and inventory refs come from the terminal
manifest and the separately verified custody ledger. The grant map
contains `writer`, `receipt` and the authorized purposes. Each grant
contains a distinct `[client_certificate_der_sha256, expires_at_utc]`
pair. A snapshot descriptor binds a purpose-specific subject, snapshot
ID, exact terminal receipt ID, projection revision
`native-bp-purpose-0_1` and an event interval within enrollment. Set the descriptor’s
`max_rows` and `max_bytes` inside the service caps.

The synthetic entry points are
`python -B -m integrations.mse_health_history.typed_vm_https init CONFIG`
and
`python -B -m integrations.mse_health_history.typed_vm_https serve CONFIG`.
Use the dedicated purpose reader to fetch a fixed descriptor with
`TypedClient.snapshot`. The store opens SQLite read-only, gates on the
terminal receipt, suppresses conflicting revisions and admitted
tombstones, excludes standalone and incomplete pairs, and returns a
purpose-scoped subject with 15-minute UTC buckets and mmHg pairs.
Independently record the terminal binding, snapshot count and canonical
payload digest. Test all role denials and reopen the guest process before
activation.

## Review status

The synthetic loopback suite covers authenticated import, role and scope
denials, content digest, sequence and manifest conflict, no visibility
before terminal, rollback, lost response, exact replay, expiry,
tombstone suppression and reopened read-only output. The target VM has
yet to be exercised. Independent reviewers must resolve physical child
ordinal mapping from normalized component slots before claiming complete
child lineage. Real-data enablement and backup/restore are outside this
candidate.
