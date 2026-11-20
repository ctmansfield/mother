# MSE storage and recovery options

Proposed decisions for the offline increment under MSE-INTEGRATION-20261120-01 r1. Chad and the named custodians decide production placement, retention and objectives after qualification. The [requirements](https://github.com/ctmansfield/mother/blob/91d67e387e91d93a7a60aec03c8164c11c7aa994/docs/mse/HEALTH_DATA_INGESTION_REQUIREMENTS.md) and [integration addendum](../INTEGRATION_ADDENDUM_2026-11-19.md) define the evidence boundary. The local archive evidence is [PF-001 PR #18](https://github.com/ctmansfield/mother/pull/18) at `b4e70b7123689ec164ba09e2974645ae36b184a2`, an unmerged dependency. Main observed at intake was `c05f38096406965496d7d4a09edf4b3575235311`.

| Decision | Recommendation for the next increment | Tradeoff and evidence required for a later decision |
| --- | --- | --- |
| D-01 Compute and storage | Keep ingestion, durable commit and backup independent of inference. Use a temporary local filesystem for this increment. | Co-location could reduce administrative overhead but shares resource and failure domains. A dedicated service/volume can isolate I/O and recovery at higher operating cost. Verify durable-volume semantics, write ownership, capacity and model-offline commit before choosing a host. |
| D-02 Canonical database | Exercise the existing PF-001 SQLite archive and retain its logical identities, artifact linkage and commit semantics. Serialize writer work for the prototype. | PF-001 uses short `BEGIN IMMEDIATE` transactions and full synchronous writes on a filesystem with reliable locking. PostgreSQL is an option when measured concurrent writes, cross-host consumers or recovery objectives justify operating a separate database. Qualify isolation, commit ordering, idempotency, constraints, migration and reverse reconciliation before adopting it. Existing PostgreSQL infrastructure does not establish a physiology schema or data owner. |
| D-03 Originals | Preserve the PF-001 BLOB as the original during SQLite qualification. Evaluate external protected digest-addressed originals only as a coordinated storage change. | BLOBs offer one transaction and one recovery unit, at the cost of database and backup growth. An external immutable store can scale capacity separately but needs publish-before-commit, digest recheck, orphan handling and backup-set reconciliation. A receipt may become accepted only after a durable commit references verified bytes. |
| D-04 Delivery | Start with offline captured synthetic files and the current collector format. Preserve original bytes and scope. | The future outbox keeps unacknowledged bytes, retries the same identity and digest after an uncertain response, and treats content changes under the same identity as conflict. No phone storage cutover is needed. Define quota and retry/backoff before any transport pilot. |
| D-05 Retention and recovery | Keep every accepted synthetic artifact until the qualification receipt is reconciled. Select backup cadence, authorized retention, erasure and named custodian before any real-data pilot. | Recovery must include original bytes, archive/ledger linkage, schema versions and an inventory or watermark. A source tombstone adds history. Owner erasure requires a different approved policy covering backups, derived outputs and memory references. A restored historical backup must reapply current erasure and access policy before serving. |
| D-06 Model consumption | Feed inference an authorized immutable snapshot with source scope, revisions, cutoff and lineage. Keep derived artifacts and model memory in separate stores. | Archive ownership and authorization remain with the evidence custodian. A rebuilt vector index is derived and cannot restore missing source evidence. Validate snapshot generation and invalidation across restore. Test model unavailability without loss of ingest or acceptance. |
| D-07 Dataset and purpose | Use newly generated synthetic additions and tombstones. Require a separate approved subject/source, interval, purpose, recipient and retention scope for any later captured pilot. | Unknown or partial coverage stays explicit. Preserve scope and unknowns through restore. Keep fixture IDs disjoint from prior uploader deliveries. |
| D-08 Operations | Name one archive writer owner, backup custodian and independent restore reviewer. Monitor queue age, failed/unresolved receipts, storage headroom, backup age and last verified restore. | Set thresholds from measured volumes and recovery promises. Stop admission before exhausting durable capacity and preserve queued bytes. Later operations need least privilege, key custody/rotation, auditable recovery, sanitized logs and an owned rollback decision. |

## Capacity and recovery choices

Synthetic sizing hypotheses for planning, not measured throughput or capacity:

| Scenario | Assumption | Original bytes before replication and normalized/index overhead |
| --- | --- | --- |
| Small qualification | 100 batches/day × 100 KiB | About 10 MiB/day or 293 MiB over 30 days |
| Stress qualification | 1,000 batches/day × 1 MiB | About 1 GiB/day or 29.3 GiB over 30 days |

Measure rows per batch, original and retained bytes, write transaction latency, queue growth, backup size and full restore time at both scales. Include independent backup copies, WAL, indexes, filesystem overhead, verification space and rebuildable derived storage in quota calculations. Establish queue and volume limits separately. Owner and storage custodian should choose an at-rest protection and backup-key recovery design before a live pilot.

| Option | Candidate RPO | Candidate RTO | Qualification evidence |
| --- | --- | --- | --- |
| Periodic separate sealed SQLite backup | At most 24 hours for a verified daily backup, if that loss is acceptable | 4 hours | Unavailable primary, standalone backup, manifest/member checks and isolated restore with lineage |
| Higher frequency SQLite backup plus retained outbox | At most 1 hour if hourly backup and outbox retention are actually met | 2 hours | Prove committed-result reconciliation and lost-response replay from the selected cut without double acceptance |
| PostgreSQL with base backup/WAL recovery | Candidate 15 minutes, subject to archive-lag measurement and recoverable originals | 1 hour, subject to rehearsal | Restore to a verified point, reconstruct external artifact linkage, preserve ledger semantics and measure complete recovery |

These are options for owner review. RPO is the maximum tolerable data loss and RTO is time to verified service readiness. A backup with no tested restore cannot substantiate either objective. If durable acceptance promises survive primary loss, define what redundancy is required before acknowledging, and account for outbox pruning accordingly.

## Offline recovery checkpoint

Run this from the requirements-based topic checkout with a separate clean, isolated PR #18 checkout at the pinned dependency above:

```sh
python3 -I -B tools/mse_integration/recovery/rehearse.py --pf-checkout /path/to/pinned-pf001
```

The harness seeds fresh synthetic originals through the actual PF-001 Archive API and commits an accepted revision, a tombstone and a checkpoint. While a WAL writer holds an uncommitted checkpoint deletion, a separate reader takes a SQLite application backup. The backup copy is sealed into standalone rollback-journal format. The synthetic primary is removed and the retained backup is restored into a fresh directory. Checks cover SQLite and foreign-key integrity, schema and contract versions, exact original bytes and digest, revision/tombstone lineage, and the completed import-run checkpoint. Negative cases reject a missing artifact, a changed member, an unrelated artifact with recomputed outer hashes, and a rehashed database with a missing checkpoint. Data and temporary stores exist only for the duration of each test.

The local manifest is a unit-test fixture and checks internal consistency. Production backup manifests need trusted provenance, a committed generation/high-water mark, explicit publication rules and destination access controls. This harness uses PF-001's import run/checkpoint, with no FORGE receipt-ledger, normalized-record or MSE snapshot restoration. Once those interfaces are pinned, rehearse backup publication, crash recovery and reconciliation on their exact schemas. Test pre-commit interruption, committed-but-unacknowledged retry, already-accepted identity with changed bytes, stale backup generations and stale access-view/snapshot invalidation before selecting a storage option.

**Next decision.** FORGE and ATLAS supply the pinned artifact/receipt contract for a combined restore rehearsal. GADGET and Chad then select which capacity case and recovery objectives to measure before deciding placement and storage.
