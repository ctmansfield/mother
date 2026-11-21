# Proposed synthetic destination setup

**Source-only package. Destination NOT READY.** This is the PHOENIX implementation under [MSE integration r5](https://github.com/ctmansfield/mother/pull/23#issuecomment-7045375231) following the [readiness audit](https://github.com/ctmansfield/mother/pull/33). No host directory, service account, listener, route, database or backup allocation exists by virtue of this proposal.

## Allocation and permissions

Evaluate a dedicated allocation on the established LLM host's local ext4 data mount. Confirm mount identity, boot availability, free-space threshold, existing consumers and restore failure domain privately before selecting the root. Never fall back to a directory on the root filesystem if the intended mount is absent. Keep both existing PostgreSQL locations, NFS source trees, historical QA, and benchmark paths outside the allocation.

| Proposed path | Purpose and permissions |
| --- | --- |
| `<APPROVED_LOCAL_EXT4_ROOT>/mse-synthetic/` | Dedicated non-login writer and parent containment. Directories `0700`, files `0600`, process umask `0077`. No inference access to this tree. |
| `state/custody.sqlite3` | FORGE journal with exact incoming artifact bytes and receipt stages. |
| `state/physiology.sqlite3` | PF-001 archive, original BLOB and normalized/revision evidence. Keep the state pair co-located. Current FORGE intentionally holds two copies of accepted original bytes. |
| `staging/` | Transient local synthetic inputs with explicit inventory and expiry. No application intake endpoint in this increment. |
| `<APPROVED_SEPARATE_BACKUP_ROOT>/mse-synthetic/<generation>/` | Separate failure domain, named backup custodian and immutable generation inventory. A restore fixture materializes an original-byte copy for comparison. |
| `<APPROVED_ISOLATED_RESTORE_ROOT>/<generation>/` | New restore directory. Never overwrite active state or point consumers at an unverified generation. |

Provisioning inputs still required are the exact mount/device and parent real path, writer UID/GID, backup and restore roots, quota and minimum free headroom, approved archive/scope, and authorized operator. Require safe parent ownership, no symlink traversal, regular files, same mount identity at start, and an explicit failure path for unsupported locking. A service, listener and credentials are outside this offline setup. Later inference receives versioned approved snapshots through a separate boundary and must be able to remain offline.

## Source-only installation and preflight

Preview candidate paths with the planner. The following values are examples, including the writer IDs. Substitute approved values for private review. The planner performs lexical validation without inspecting or touching any supplied path.

```sh
python3 -I -B tools/mse_integration/recovery/destination.py plan \
  --allocation /mnt/example-data/mse-synthetic \
  --backup /mnt/example-backup/mse-synthetic \
  --restore /mnt/example-restore/mse-synthetic --uid 950 --gid 950

python3 -I -B tools/mse_integration/recovery/destination.py local-dry-run
```

The plan rejects relative, non-normalized, overlapping and known protected paths and root writer IDs. The dry run creates the proposed directory shape and permission markers only inside a generated local scratch directory. It checks actual current-user ownership and modes, rejects a symlink and FIFO without opening them, then removes that disposable layout. It has no installation mode against caller-supplied paths.

A later authorized operator must verify the approved mount identity and real parent paths before creating anything. Use same-filesystem exclusive creation under verified parents, with a guarded recheck after creation, reject any unexpected existing path or inode, verify the dedicated UID/GID and modes, and retain baseline plus an exact owned-resource inventory. Create only the empty state and staging directories. FORGE initializes the two databases using the reviewed synthetic entry under the writer identity. Do not attach a consumer until the sealed generation restores into a separate verified location. Filesystem inspection, actual dedicated-UID enforcement, quotas, backup destination durability and operator provisioning remain required later.

## Rehearse locally

```sh
python3 -I -B tools/mse_integration/recovery/paired.py --plan
python3 -I -B tools/mse_integration/recovery/paired.py --combined-checkout /path/to/clean-pinned-nicky
```

Use Python 3.12 with FORGE/PF-001's `jsonschema` dependency. For direct reproduction use [NICKY candidate #34](https://github.com/ctmansfield/mother/pull/34) at `877eeb66ae2c26ab8ee2144d34adeba87c988e8f`, tree `6dadd8cd94ffb4a0091f76624fdd0afd7baad507`, in a clean detached checkout whose object store also contains the frozen ATLAS pin. The alternative `--forge-checkout /path/to/clean-pinned-forge` assembles exact sibling sources from the object store. That checkout must be clean and detached at [FORGE #31](https://github.com/ctmansfield/mother/pull/31) `ceeb92157f4d7179a3ad5cd3d4af9e9aa4ff6b4f`, with [PF-001 #18](https://github.com/ctmansfield/mother/pull/18) `b4e70b7123689ec164ba09e2974645ae36b184a2` as its physiology source. Fetch the sibling PR refs into the same Git object store and retain the following exact commits:

| Component | Rehearsal pin |
| --- | --- |
| [ATLAS contract #28](https://github.com/ctmansfield/mother/pull/28) | `769a0966da251da4d08633cc7663af9869da70e6` |
| [ORACLE capture #30](https://github.com/ctmansfield/mother/pull/30) | `7825b02093d280321af34af88aed96da44b33594` |
| [PROVENANCE bridge #27](https://github.com/ctmansfield/mother/pull/27) | `7be9ea31c6c68643573afdf37ccfa0a41901a368` |

The plan prints placeholders. The rehearsal exports only pinned sibling source into a temporary directory, uses ORACLE’s public `ingest_capture` entry, FORGE `ConnectedIngest` and the PROVENANCE/MSE replay verifier, and creates fresh synthetic batch identities. It reads original synthetic bytes from the ATLAS vector and keeps source files unchanged. Every backup, restore and inference store is disposable.

1. Quiesce writers at an acceptance boundary. Record durable receipt identity and archive/ledger binding. Write both SQLite application backups into a new generation, seal them as standalone files and verify all member digests. Keep the custody copy, PF-001 BLOB and backup inventory linked.
2. Reopen into fresh isolation. Verify both SQLite integrity and foreign-key checks, exact originals and authoritative receipts against the restored journal and archive. Compare the complete cutoff snapshot, replay output and lineage before and after restore. Recover a committed PF-001 run with an unpublished final receipt without recommitting the archive, and verify that the earlier cutoff still excludes the pending evidence.
3. Exercise stale/mismatched generations and altered originals. Keep failed generation evidence restricted. To roll back, leave active state untouched and discard only disposable test state, or propose a separately authorized switch to the last coherent verified generation. Reconcile later accepted identities before any proposed switch. Never replay old committed uploader fixtures.

The rehearsal removes its disposable primary to prove restore independence. It does not implement operational generation publication, authorized backup storage, access-generation reconciliation, crash/power-loss certification or runtime failover.

## Proposed owner decisions

- **Capacity.** Begin with a proposed 2 GiB state quota for a bounded synthetic trial and a separate backup/restore reserve. Measure duplicate originals, SQLite overhead, growth and restore headroom before any larger trial. Stop new admission before reaching quota.
- **Retention.** Keep each accepted synthetic artifact and both database copies until independent acceptance and rollback review. Propose a 30-day evidence cap after review, subject to owner-approved exceptions and cleanup boundaries.
- **Recovery.** Propose a 24-hour maximum RPO and four-hour RTO as initial rehearsal targets, with a verified backup immediately before and after the bounded synthetic trial. Require shorter objectives and stronger acknowledgement semantics if owner policy cannot tolerate loss of an accepted batch. These targets are not measured or approved.
- **Next.** SENTINEL independently reproduces the pinned connected restore and verifies file boundaries, coherent recovery and negative cases. FORGE and PHOENIX rerun if the connected candidate changes. GADGET and Chad select the concrete allocation, identity and storage policy before any host action.

## Corrected source-integrity rehearsal

The separate pinned mode runs the r7 fixes without changing the historical #34 candidate. Use a clean detached FORGE checkout at `e4219cdf3dba73f586e3820990f3ab34f1a7c1d9` with ORACLE `ac3fbf61389ca2a6e82683aa520c15181ac1aa80`, PROVENANCE `5799879c1d7dcc0fa684754833f331957ae5deb3` and normative ATLAS `769a0966da251da4d08633cc7663af9869da70e6` in its Git object store.

```sh
python3 -I -B tools/mse_integration/recovery/paired.py \
  --corrected-forge-checkout /path/to/clean-pinned-forge
```

In addition to the four paired restore cases, this path verifies exact original bytes, decimal `9007199254740993`, its explicitly lossy binary64 projection and per-field warning through reopen, cutoff snapshot and derived replay. Direct ingest of a self-consistent export with the original deletion omitted is rejected after restore, and the genuine receipt and snapshot remain stable. The later immutable combined successor requires its own pinned run. The linked [decision sheet](DESTINATION_DECISION.md) includes evidence, identity, analytics and backup/key separation options for review.
