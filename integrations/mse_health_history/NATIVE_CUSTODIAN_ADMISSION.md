# Protected native import admission

This runner is an offline Mac source candidate. Independently review the
exact parser and runner package, the reviewed age executable, real
ciphertext readback, protected filesystem and operator plan before
issuing any real admission. The author qualification uses fabricated data.

The approval authority signs a private JSON policy with HMAC SHA-256 over
the ASCII domain `mse.native-custodian-admission/0.1`, a zero byte and the
UTF-8 canonical JSON policy bytes. The envelope contains only `policy`
and `hmac_sha256`. The 32-byte authority key must be delivered through a
trusted private channel independently of this policy. Use a separate
provenance key and keep both keys, the native ZIP and the age identity in
Mac custody. Treat the policy itself as sensitive.

The closed policy fields are listed in `native_custodian.py`. The policy
binds the exact archive, enrollment and source instance, a finite UTC
execution window, and the complete ciphertext receipt, recipient,
plaintext length and digest and age executable digest. The authority
must compare the receipt to independently verified ciphertext custody
and verify the plaintext pins from the original custodian. The policy
also pins filesystem UUID, mount and private catalog and scratch roots,
typed database cap, disk reserve, wall timer, expanded archive bytes and
top-level row cap. Use absolute canonical paths.

The runner checks the exact mounted APFS volume reports encryption for
that volume, verifies both private roots are on the pinned filesystem,
and budgets room for anonymous plaintext scratch, a typed DB, its
rollback journal and a disk reserve. SQLite temp files are directed
to protected scratch. Its output is the protected typed catalog on that
same volume. The operator must independently verify owner isolation,
approved scratch and volume, locking and remount controls, encrypted
swap or an approved host policy, and capacity before admission. Use a
fresh dedicated root. Keep the encrypted original and detached private
key under independent custody.

```sh
python -B -m integrations.mse_health_history.native_custodian \
  --admission "$approved_policy" --approval-key "$trusted_authority_key"
```

The runner inventories the original only after age authentication and
an exact plaintext digest and length check. Successful output is a
generic status after the receipt is reopened. If the final outcome is
uncertain, preserve the private catalog and journal, check the exact
receipt under the same authorized scope and use exact authenticated replay
during the lease as needed. Keep the sealed original and custody receipt.
No service activation or guest transfer forms part of this runner.

## Proposed private diagnostic

The optional `--diagnostic-category` changes refusal reporting only.
Use it on a separately reviewed invocation. It prints one static label
in place of the generic refusal and never renders exception text.

- `ADMISSION`, `ENVIRONMENT` and `PRECOMMIT_WINDOW` identify preflight
  or precommit authorization and environment phases.
- `BINDING` covers input binding, the executable and ciphertext pins,
  and exact plaintext checks. `AUTHENTICATION` identifies an age
  authentication failure after the ciphertext pin matched.
- `ARCHIVE_OR_XML` identifies refusal during inventory.
  `INVENTORY_LIMIT` identifies an approved archive or parser quota.
  `RESOURCE_LIMIT` covers recognized storage or file limits elsewhere.
  `RUNTIME_LIMIT` identifies a wall-time limit.
- `CATALOG` identifies a catalog operation. Older Python SQLite
  bindings may expose only this coarse phase for database capacity errors.
- `COMMIT` and `READBACK` require receipt reconciliation before any
  authorized retry. A category reports the observed failure phase.
  Acceptance still depends on an exact receipt reopened read-only.

Do not share exception strings, paths, identifiers, member names, record
values, credentials, or digests through the diagnostic. A previously
completed generic refusal cannot be reclassified from the category
implementation. Preserve the original failed state and treat any real
replay as a separate authorization decision.

### Named resource budgets

The diagnostic can identify archive bytes, ZIP directory bytes, member
count, member bytes, expansion ratio, and total expanded bytes. XML
categories distinguish declaration size, token/attribute bytes, depth,
element count, top-level rows, correlation child count and type buckets.
Storage categories distinguish the filesystem reserve, scratch capacity,
catalog file size, journal size, SQLite page-limit configuration, and
file-size limit or configuration. Typed OS errors distinguish filesystem
full, filesystem quota and file size. `SQLITE_FULL` means SQLite reported
that result code. It can represent its configured page cap or filesystem
capacity. Older Python runtimes may report only the catalog phase.

Before adjusting any budget, reconcile the signed policy with already
recorded measurements from the actual approved workspace. Preflight
requires free space of at least plaintext bytes plus twice the catalog
cap plus the reserve. Just before commit it checks the reserve and each
existing catalog/journal file against its cap. The operative per-file
soft limit is the larger of plaintext bytes and catalog cap. Record only
whether these comparisons passed, whether an explicit host file or CPU
limit was inherited, and whether SQLite exposed a structured result code.
Keep values tied to the protected archive in private custody. Post-run
backing free space cannot substitute for attempt-time capacity or the
child APFS volume quota. An older generic resource refusal alone does not
justify widening any budget.

### Manual wrapper review

Use the package's `native_status.capture_status(exit_code, stdout, stderr)`
with separate byte streams. The function accepts only an exact complete
allowlisted line with the matching exit code and empty opposite stream.
Mixed output, duplicated lines, traceback text and unknown categories
yield only `UNCLASSIFIED`. Keep captured streams private and never echo
unexpected output. Runner-reported success still requires independent
receipt reconciliation. Bind the wrapper to this source/package and test
the exact wrapper's allowlist, authority, detach and exit-code paths using
fabricated input before authorizing any manual use with the real archive.

### Signed ZIP member allowance

A fresh signed policy may include `max_zip_members` from 1 to 25,000.
A policy without the field retains the 4,096 default. Directories count
toward the total. The authority should pin the actual verified member
count when a larger allowance is needed. Never substitute the ceiling
for an unmeasured archive. A count above the ceiling requires separate
review. Editing a signed admission invalidates its authentication.

For an already available, approved private closed ZIP, the operator can
run the pinned metadata-only command locally:

```sh
python -B -m integrations.mse_health_history.native_zip_metadata "$approved_closed_zip"
```

This checks the EOCD and counts the central records without opening or
decompressing members. It emits only the verified total member count and
central-directory byte size, or a fixed refusal. It cannot inspect
ciphertext. Keep the values private and share only the approved
comparison results. The existing 4 MiB central-directory bound remains
in force. Before creating ZipInfo objects, import checks the declared
count and independently counts the central records. The parsed-member
count check still applies. Per-member bytes, aggregate expansion, ratio,
paths, XML quotas, catalog and operational budgets retain their previous
limits.

A fabricated ceiling-sized ZIP with 25,000 entries and a 4,099,912-byte
central directory peaked at 21,699,747 traced Python bytes during the
inventory-only scan on the qualification Mac. This measures allocations
made in that scan. It excludes whole-process memory, native allocations,
SQLite, and the authenticated import workload.

### Physical child lineage handoff

A PR #61 catalog retains artifact, member and top-level parent sightings.
That schema lacks the physical child ledger required by the reviewed PR
#58 projector. Preserve the successful PR #61 catalog for its original
scope. This successor requires a fresh protected catalog and records
direct XML child positions before sorting normalized BP components. It
refuses a parent-only catalog before authenticating or parsing an archive.
Do not generate physical ordinals from sorted components.

For a separately approved manual continuation, bind one fresh single-use
admission to this exact successor and the retained authenticated
ciphertext, using a new empty protected catalog. Keep the previously
verified member allowance and the other bounds. After independently
reconciling that run's receipt, the exact PR #58 projector can reopen the
new catalog on the Mac under the same private catalog scope and produce
opaque child references. Guest ingest is a distinct authorization gate.
The PR #61 receipt remains evidence for its own parent-level import.

An optional signed `projection` object requests a protected projection in
the same manual invocation, after reopening the committed catalog receipt.
It pins `scope`, canonical UTC `bounds`, `mapping_key_file`, fresh
`output`, `max_batches` and `max_bytes`. The mapping key is independent
from the admission and provenance keys and remains on the Mac. The output
must be a new path on the same approved encrypted volume with an
owner-only parent separate from typed catalog and scratch. The runner
preflights the projection bytes in addition to existing storage checks.
All exact batch files appear together in `batches/` only when publication
completes. The private accounting file remains in Mac custody. If catalog
receipt verification succeeded and projection later refuses, preserve
the catalog and reconcile it read-only. Do not authenticate or parse the
archive again merely to recover projection.
