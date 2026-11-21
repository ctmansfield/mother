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
custodian assertions. The sink stages each batch, operations and receipt in one synchronous SQLite
transaction. After that commit, it observes trusted time and separately
persists the in-lease durability witness. Only witnessed batches can be
read as accepted, and only a witnessed terminal batch allows snapshots.
Keep any staged batch without a witness sealed. Preserve the store and
journal for operator reconciliation. Exact replay cannot infer acceptance.

Use `TypedClient.receipt` with the independent receipt-reader certificate
after lost or indeterminate responses and verify the returned receipt
with the exact retained batch bytes. First acceptance is 201 and exact
in-lease replay is 200. Sequence, predecessor and immutable byte
conflicts are 409. Before the terminal receipt commits the snapshot is
absent. A terminal receipt can still be read after the writer lease
closes, within the receipt reader's separate lease.

## Protected snapshot accounting

The Mac projector applies the same full-interval rule as guest ingress.
The root and every included child must independently satisfy
`lower <= start <= end < upper`. It excludes the entire out-of-window
upsert and continues through the artifact. Preserve its original facts
and membership in the protected catalog. The optional `record_accounting`
callback receives the private totals once the source iterator is consumed,
before the terminal batch is produced. Record those totals in the
protected Mac ledger. The totals reconcile source occurrences into
normalized and unnormalized rows, and normalized BP into emitted and
snapshot-excluded rows. Snapshot exclusions do not alter the terminal
manifest's source occurrence or parser quarantine assertions. The latter
counts invalid BP within unnormalized inventory. Non-BP inventory is
not parser quarantine. The terminal
upsert count reflects only emitted operations.

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
yet to be exercised. The private catalog records physical child ordinals and roles before
sorting. Projection derives opaque component occurrence references from that
private ledger. Use a fresh catalog with the successor package. Any prior
catalog lacks this child ledger and must be retained for its original scope.
Real-data enablement and backup/restore are outside this candidate.

## Admitted real-input guest candidate

The existing `typed_vm_https` entry point remains synthetic-only.
`typed_vm_admitted` is a separate real-input source candidate with an
explicit, independently provisioned admission. It never reads original
archives, Mac ciphertext, mapping keys, or provenance keys. A reviewed
Mac run supplies only the exact typed batch files under a separately
authorized transfer. Keep the Mac accounting file private.

PHOENIX owns guest deployment. Use a private dedicated Linux non-login
account, a fresh empty protected database directory on its own reviewed
LUKS2 mapping, and an assigned private listener outside 8446, 8447 and
8448. First independently qualify the exact guest source, encryption,
isolation, capacity, private TLS address and grant ownership. The admission
authority approves the exact private JSON policy and distributes its
SHA-256 to the trusted launcher independently of that file. Passing a
digest computed from an unapproved file is not admission. No private
signing key needs to be supplied to the guest.

The closed policy includes `schema_version`
`mse.native-bp-real-guest-admission/0.1`, `mode`
`admitted-native-bp-import`, `encrypted_device_uuid`, `reserve_bytes`,
`catalog_bytes`, `server_certificate_sha256`, `client_ca_sha256`, and
`guest`. The nested guest object uses the pinned fields above, with a
non-synthetic enrollment. Pin the exact dm-crypt LUKS2 mapping UUID
reported for the approved filesystem, session quotas, certificate and CA
digests, writer/receipt/purpose roles and immutable snapshot descriptors.
The admission digest binds the database identity and remains fixed for
readback and recovery. The database page cap and reserve are separate from
the wire quota.

Use `typed_vm_admitted init ADMISSION --trusted-admission-sha256 PIN`
with an empty directory to initialize without binding the listener. Use
`typed_vm_admitted serve ADMISSION --trusted-admission-sha256 PIN` only
under the separately authorized environment and lease. Both are Python
module invocations. Recover acceptance by scoped receipt readback and
the already reviewed witness and terminal rules. Preserve the prior
parent-only PR #61 catalog and the retained originals. Real transfer
and consumer release remain independent decisions. Fabricated loopback
tests use the admitted route with simulated Linux encrypted-storage
attestation. They do not qualify the real guest.
