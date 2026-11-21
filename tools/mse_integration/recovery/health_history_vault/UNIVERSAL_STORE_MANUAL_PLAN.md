# Universal Health ZIP archive and manual handoff

Governing directive [MSE-ALL-ZIP-DATA-20261121-07 revision 2](https://github.com/ctmansfield/mother/pull/23#issuecomment-7060675355).

The user runs every personal-data operation, including metadata checks,
preflight, admission preparation, verification, transfer, and cleanup.
Agents work only on source, documentation, and ordinary functional
tests with fabricated inputs in isolated development. Live services
and actual data remain unchanged.

## Scope and existing evidence

The target is a queryable protected archive of the authorized Health ZIP,
including typed records, unnormalized records, and retrievable attachments.
The successful PR #61 parent-level catalog and original ciphertext remain
in custody. The PR #58 synthetic BP VM qualification proves encrypted
storage, mTLS roles, receipt and closure mechanics. It does not qualify
other families or attachment retrieval. [PR #62](https://github.com/ctmansfield/mother/pull/62)
is a BP child-lineage and typed-sink candidate. It does not yet supply
the universal schema and payload path required here.

Retain the full exact ZIP under Mac custody. Reconcile every ZIP entry,
including directories, non-XML members, and unsupported families. The
guest archive must contain the retained member payloads and lossless
structured source-record representations, with types and occurrence
links. A custody-only disposition never counts as database availability
and leaves acceptance unresolved. Preserve quarantine content and
reason together under a restricted role. The original ZIP container
and its private identity remain in Mac custody. The database provides
member content and structured records through bounded protected roles.

## Storage and schema

Use a fresh encrypted LUKS2-backed ext4 volume and a single SQLite database
for the first measured deployment. The expected workload is one bounded
import writer with multiple purpose readers. Put payloads in bounded
SQLite BLOB chunk rows in the same transaction domain as their descriptors
and receipts. That keeps the bytes retrievable from the archive and
avoids an independent object store commit. Reconsider a separate store
or database engine if exact-package synthetic measurement cannot meet
the reviewed size, query or writer requirements. Do not reuse the
sealed synthetic image whose unlock key was discarded.

ATLAS should pin the physical schema and query contract for these objects.

| Object | Required behavior |
| --- | --- |
| Archive and member ledger | Bind the exact custody receipt and importer revision to every source entry, order, kind, approved metadata and counted disposition. Include directories without inventing payloads. Treat source paths as sensitive data. |
| Source occurrences | Use source instance, member and ordinal identity for top-level records. Preserve XML namespace and tag identity, complete attributes, text and tail text, ordered children, metadata, and explicit parent and role links in the restricted representation. Preserve unnormalized and quarantined content with reasons. Equal values or timestamps do not collapse occurrences. |
| Typed tables | Retain family-specific versioned rows, source links, units, clocks and normalization disposition. Query by family and bounded time window. Preserve unknown units or types without inventing values. |
| Payload bytes and links | Store exact retained member bytes, including XML, attachments and opaque unsupported formats, in ordered fixed-size chunks under a verified payload digest and length. Retain one link per source occurrence even when identical bytes share storage. Store zero-byte attachments as valid payloads. Keep path or URL references inert. |
| Import and receipt ledger | Bind source, scope, version, ordered batch digests, row totals, payload counts and bytes to the terminal manifest and durable receipt. Preserve immutable acceptance and exact replay semantics. |
| Consumer projections | Pin purpose, subject, family and field allowlists, time range, cursor, row and byte caps, and schema version. Restrict Mother and Coach to separately authorized projections. |

Cap the part size and both stream and stored bytes. Independently verify
chunk order, lengths and digest, and verify the complete payload digest
and length when retrieved. A registered hash with missing bytes is an
incomplete import. Serve approved binary payloads as data, with no
automatic rendering, execution, path extraction, or network fetch.

## Budget, staging, and publication

Measure exact-package SQLite growth with fabricated cases that stress
many small members, large payloads, repeated payloads, unknown records
and concurrent bounded queries. Record explicit caps for admitted ZIP
entries, central directory, expansion, individual payload, total payload
and record bytes, nested structure, rows, batches, temporary work, wall
time and export response. Do not infer space requirements from
compressed ZIP size. Budget Mac anonymous authenticated scratch plus
approved staging, and separately budget full guest data and indexes,
rollback journal or reviewed transaction sidecars, temp files, filesystem
overhead and reserve. Check backing and mounted capacities separately.

The exact PR #64 fabricated run measured 9.00 MiB of expanded member
bytes, 12.06 MiB on the wire, 12.25 MiB of staged SQLite storage, and
21.40 MiB of witnessed SQLite storage. The latter retained the submitted
wire parts alongside decoded records and payload chunks. The sampled
rollback journal was only a lower bound. Do not extrapolate these
ratios to the real archive. The candidate's guest preflight requires
two signed database caps plus reserve on the encrypted filesystem.
Use the final exact spool size and measured terminal growth to choose
that cap. Plan guest backing allocation separately, including the
filesystem overhead and the existing host reserve. The last authorized
readbacks showed 53.21 GiB guest backing free and 75.15 GiB Mac backing
free. Recheck both when a reviewed operation is scheduled. These
numbers do not attest the detached real Mac workspace.

The manual Mac runner verifies the independently reopened 8447 receipt
and detached age authentication, then processes the ZIP from approved
encrypted scratch. Stage exact canonical record operations and payload
chunks on protected storage, outside the guest route. Reconcile the
manifest across both sides: every source member has a disposition,
known-family normalization and restricted unknown counts stay distinct,
attachment references are linked or explicitly unresolved, and every
retained member has verified stored bytes or is an entry type without
bytes. Reconcile top-level typed, fallback and quarantine assignments
without double-counting nested occurrences. Reject undercounts and
mismatched linkage before publication.

The guest accepts only one admitted import through sequenced bounded
batches. Exact retry uses retained staged bytes and the independent
receipt reader. Before a witnessed terminal outcome, both query roles
see the prior qualified snapshot or no snapshot. Invalid, incomplete,
over-quota, interrupted or late attempts must preserve the prior
accepted sequence and visibility. Never publish counts or a successful
receipt for digest-only attachments. Use atomic catalog/batch
transactions and exact receipt reconciliation before any retry.

## Custody, access and closure

Use the persistent key and storage identity guards in the
[typed-store environment plan](real_typed_store_manual_plan.md). Keep
the persistent unlock key under independent encrypted custody and out
of persistent guest files. Reopen empty or synthetic state before any
real admission and prove wrong or missing mounts cannot produce an
ordinary-directory database. Keep the Mac age identity, raw ZIP and
custody, mapping and provenance keys out of the VM.

The finite private mTLS route uses separate writer, receipt-reader,
Mother-purpose and Coach-purpose grants. A separate restricted records
role may retrieve explicitly approved unnormalized fields and payloads
only within its approved scope. Default purpose roles have no raw
record, attachment or receipt access. A new grant binds exact source,
endpoint, certificate, peer, role, import and expiry. Serve read-only
bounded queries and paged exports. For binary downloads require an
authorized occurrence, immutable digest, range bounds and byte budget.
No arbitrary SQL, filesystem lookup, public ingress or shared
credential across roles.

After terminal readback, stop only the owned service and close the
finite route. Verify the listener, scoped firewall, mount, mapper and
loop are gone. 8446 remains active and 8447 remains closed. Publish
only approved counts and boolean receipt, visibility and detach checks.
Keep backup and restore work deferred.

## Isolated development qualification with fabricated data

Run in isolated development using a fresh synthetic store and test-only
credentials. Any checks on an existing actual host, guest, or service
belong to the user-run handoff. The fixture covers BP with physical
child ordinals, another measured family, a quantityless event,
nested records, an unknown family, a directory, a zero-byte attachment,
a populated binary attachment, duplicate bytes at distinct occurrences,
and a file reference that must remain inert.

1. Verify complete ledger reconciliation and separate typed and restricted
   source queries. Download the full exact fabricated payload and a bounded
   range. Match the original bytes, digest and length. Verify the duplicate
   attachment links return the same bytes without collapsing occurrences.
2. Test ordinary Mother and Coach scoped queries and their expected
   role-specific results, bounded occurrence and range handling, and
   the functional behavior of finite writer and reader expiry.
3. Exercise absent or corrupt chunks, oversized payload, wrong predecessor,
   replay and quota refusal. Show that failed or late publication leaves
   prior visibility and accepted sequence intact. Verify the witnessed
   terminal manifest and receipt are exact.
4. Stop, lock, remount and start a fresh process. Reopen the terminal
   receipt, a positive typed query and the actual attachment bytes.
   Verify owner and storage containment and close the test route,
   service, mapper, mount and loop. Read back continued 8446 operation.

## Deliverable for the custodian

After exact source review and isolated fabricated qualification, provide one
cohesive manual launcher and a sanitized readback helper. The launcher
must bind the authenticated original, isolated Mac scratch and catalog,
exact universal schema and version, verified guest storage, approved
payload policy, finite admission and exact destination. Its preflight
must not consume the admission or parse the real ZIP. The manual run
must stop before granting real access when completeness, source
occurrence lineage, approved payloads, or storage checks fail.
The user runs the reviewed preflight, private admission preparation,
projection, transfer, verification and cleanup, and supplies only
sanitized results. Agents perform none of those steps against real data
or services.
