# Protected evidence archive topology options

[MSE-EVIDENCE-INFRA-20261121-01 r1](https://github.com/ctmansfield/mother/pull/23#issuecomment-7055804570). Design for discussion. Host, database engine, network exposure, key custody and operator mechanism remain owner decisions. Destination remains **NOT READY**.

## Archive scope and baseline

The archive must let Chad and authorized operators locate, verify and retrieve protected evidence through explicitly granted, auditable paths. The archive preserves exact originals, typed source revisions and deletions, immutable receipts, current authorized readback, and recoverable linkage among them. Model inference, wider vault/privacy features and external projection serving are parked. Source evidence and original times remain intact.

The last qualified synthetic baseline is [#35 at b7aae4f](https://github.com/ctmansfield/mother/commit/b7aae4f2216d27f0544eab9fe9698286fe49d716). Its local PF-001 SQLite and custody journal prove a concrete source and paired recovery seam at that pin. They do not establish a deployed database, approved data allocation or a production security boundary. In the current source the custody journal and PF-001 can both retain original bytes. Account for both copies until a separately reviewed design changes custody without breaking prior receipt verification.

## Topology options

| Option | Boundary gained | Shared dependencies and evidence needed |
| --- | --- | --- |
| Dedicated archive process on an existing host | Separate service identity, application runtime, private data allocation and explicit operator path. Lowest infrastructure overhead if supported. | Shares host kernel, privileged administration and host outage. Show independent filesystem permissions, backup custody, resource contention limits and recovery if inference fills storage or stalls the host. Container isolation, if used, does not create a host boundary. |
| Dedicated archive guest on an existing hypervisor | Guest OS, process identity and guest-local policy isolated from unrelated guests; dedicated durable disk and operator entry. | Hypervisor administrators and backing-volume access remain privileged. Host/storage outage may affect both inference and archive. Verify guest boot/mount identity, management access, real snapshot consistency and restore independently from VM restart. |
| Dedicated archive physical host | Separate physical failure boundary when power, storage and administration actually differ. Allows a narrow archive-only operating footprint. | Hardware alone gives no key, operator or backup isolation. Validate distinct storage and failure dependencies, remote recovery, operational support, replacement and restore with the original host unavailable. |

Keep engine choice orthogonal. A pinned local SQLite deployment is a candidate where one authoritative writer and consistent paired backup satisfy measured workload and recovery needs. A separately reviewed database service is a candidate where writer concurrency, DB operations or recovery needs justify it. It would still require exact migrations, typed mappings, consistent artifact/journal coordination and compatibility evidence. Engine availability alone does not establish suitability or a running archive.

## Boundaries to select explicitly

| Boundary | Required owner decision and evidence |
| --- | --- |
| Physical host and hypervisor/guest | Name failure and administration domains, shared dependencies with inference, sole operating owner and recovery custodian. Document host maintenance and reboot consequences. |
| Process/service | Separate writer/runtime identity from operators, readers and backup users. List authorized operations and limits. A read/export request cannot modify evidence or access arbitrary local files. |
| Storage | Identify durable allocation, mount/volume identity, capacity and quota alarms, protected artifact location and DB/journal consistency method. Verify missing or wrong mount denies startup instead of creating fresh state. Inventory original copies, staging, logs, WAL/sidecars and backup media. |
| Network | Identify exact approved private reachability and management path. Decide whether each operator flow needs local, private remote or brokered access. Separate ingestion, read/export, administration and backup trust. Choose authorization, transport protection and failure behavior before opening a path. |
| Operator access | Chad and named authorized operators have scoped, traceable lookup, read, digest verification and controlled export. Specify role grant/expiry/revocation, unavailable-access escalation, auditing and any break-glass owner. Avoid shared operator identity and broad archive mutation for routine retrieval. |
| Keys and credentials | Select keys and custody for copies at rest, transit and backup separately. Decide which roles can access plaintext, recovery authorization, rotation/revocation, and consequence of host/root or key loss. No keys or credentials in reproduction material. |
| Backup and restores | Assign backup and restore ownership and a separate failure domain. Bind originals, authoritative receipts, versions and ledger state at one consistent recovery boundary. Protect backups and sidecars as archive data and document custody, retention and erasure dependencies. Confirm recovered operators use current authorization. |

## Acceptance before choosing or activating a destination

1. **Documented build and startup.** An independent operator reproduces the same source-bound archive environment from a manifest identifying physical/virtual resources, OS/runtime, exact package and source versions, dependency hashes, config templates, service/directory ownership, named mount identities, migrations/schema checksums and expected checks. Do not infer compatibility from version strings alone. Logs and templates contain no secrets or raw evidence.
2. **Initialization and restart are separate.** Fresh setup explicitly requires an empty dedicated allocation. Ordinary start detects expected schema and existing identity, refuses missing/wrong mount or incompatible schema, never initializes over protected evidence, and can stop with durable state preserved. Document readiness probe and controlled shutdown order. Provide versioned runnable commands and safe-stop instructions once choices exist.
3. **Authorized retrieval works.** With new synthetic evidence, an authorized operator locates a receipt and retrieves only the requested artifact and verification metadata by a scoped path. Recomputed bytes/digest and reopened lineage match. Wrong scope, refused role, stale grant and malformed request deny without leaking protected details or changing evidence. Verify audit trace, limits and controlled export destination.
4. **Writer and failures are bounded.** Exercise same-byte retry, changed content conflict, incomplete write recovery, disk-full, unexpected shutdown and stale/mismatched input. No authority claim until originals and receipts agree. Show the archive can start, recover and serve authorized requests with inference unavailable.
5. **Restore is demonstrated.** Restore from a separate consistent backup into an isolated fresh allocation with primary unavailable. Reconcile original bytes, receipts, source revisions, tombstones and schema identities, and prove authorized readback. Exercise a stale or mismatched restore and missing key/mount refusal. Measure recovery time and accepted data-loss boundary against owner-selected objectives.
6. **Rollback keeps evidence.** Specify version rollback versus data recovery, allowed reversible steps, abort triggers, preserved store/backup custody, post-rollback verification and responsible operator. A source revert does not reverse a data migration. Preserve failures, checksums, log digests and accepted version pins.

**Next owners.** PHOENIX supplies the verified metadata baseline and unknowns. FORGE supplies archive-only dependency, startup and schema manifests. SENTINEL reviews failure and operator trust boundaries. GADGET consolidates options for Chad. No physical placement, owner credential model or runtime activation follows from this review.
