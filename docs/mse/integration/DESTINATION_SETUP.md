# Proposed synthetic destination setup

**Source-only package. Destination NOT READY.** This is the PHOENIX implementation under [MSE integration r3](https://github.com/ctmansfield/mother/pull/23#issuecomment-7041939410) following the [readiness audit](https://github.com/ctmansfield/mother/pull/33). No host directory, service account, listener, route, database or backup allocation exists by virtue of this proposal.

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

## Rehearse locally

```sh
python3 -I -B tools/mse_integration/recovery/paired.py --plan
python3 -I -B tools/mse_integration/recovery/paired.py --forge-checkout /path/to/clean-pinned-forge
```

Use FORGE [PR #31](https://github.com/ctmansfield/mother/pull/31) at `c29f4426c0e598d07ea9b1b5d019c48cd90253c9`, which includes the [PF-001 PR #18](https://github.com/ctmansfield/mother/pull/18) dependency `b4e70b7123689ec164ba09e2974645ae36b184a2`. Its Git object store must include ATLAS contract/vectors `928a60b704c342c091eabd25ba41c8eb84d562de`, the vector pin named by FORGE. Use Python with the FORGE/PF-001 `jsonschema` dependency. The plan only prints placeholders. The rehearsal operates strictly inside generated temporary directories using the real FORGE 0.2 journal and PF-001 API, the pinned FORGE fixture mapper and fresh synthetic batch IDs. It does not test the new ORACLE adapter or MSE bridge.

1. Quiesce writers at an acceptance boundary. Record durable receipt identity and archive/ledger binding. Write both SQLite application backups into a new generation, seal them as standalone files and verify all member digests. Keep the custody copy, PF-001 BLOB and backup inventory linked.
2. Reopen into fresh isolation. Verify both SQLite integrity and foreign-key checks, exact original bytes, and authoritative receipt against the restored journal and archive. A normalized receipt requires its committed PF-001 run. A durably received stage with an already committed archive must recover without another normalization.
3. Exercise stale/mismatched generations and altered originals. Keep failed generation evidence restricted. To roll back, leave active state untouched and discard only disposable test state, or propose a separately authorized switch to the last coherent verified generation. Reconcile later accepted identities before any proposed switch. Never replay old committed uploader fixtures.

The rehearsal removes its disposable primary to prove restore independence. It does not implement operational generation publication, authorized backup storage, access-generation reconciliation, crash/power-loss certification or runtime failover.

## Proposed owner decisions

- **Capacity.** Begin with a proposed 2 GiB state quota for a bounded synthetic trial and a separate backup/restore reserve. Measure duplicate originals, SQLite overhead, growth and restore headroom before any larger trial. Stop new admission before reaching quota.
- **Retention.** Keep each accepted synthetic artifact and both database copies until independent acceptance and rollback review. Propose a 30-day evidence cap after review, subject to owner-approved exceptions and cleanup boundaries.
- **Recovery.** Propose a 24-hour maximum RPO and four-hour RTO as initial rehearsal targets, with a verified backup immediately before and after the bounded synthetic trial. Require shorter objectives and stronger acknowledgement semantics if owner policy cannot tolerate loss of an accepted batch. These targets are not measured or approved.
- **Next.** FORGE and PHOENIX rerun against the connected mapper/verifier revision as it lands. SENTINEL independently checks file boundaries, coherent recovery and negative cases. GADGET and Chad select the concrete allocation, identity and storage policy before any host action.
