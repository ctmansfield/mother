# Offline snapshot-to-MSE lineage

Under [MSE-INTEGRATION-20261120-01 r2](https://github.com/ctmansfield/mother/pull/23#issuecomment-7041572809), `replay_snapshot(snapshot_bytes)` derives the reference projection internally from one validated synthetic snapshot. It accepts no caller-supplied projection. The adapter follows the offline 0.2 contract frozen at ATLAS `769a0966da251da4d08633cc7663af9869da70e6` under [r5](https://github.com/ctmansfield/mother/pull/23#issuecomment-7045375231).

## Reference and projection

The unchanged reference at main `c05f38096406965496d7d4a09edf4b3575235311` uses `native_replay`, a new disposable `Store` per execution and the existing default-config retrospective `replay`. The reference manifest digest is `112ccb8df17d6afc6d8b7f932fbdeac31b1663ccd04c5538b9bd9a32e94a25f1`. The executable Python implementation digest is checked before execution. PR #18 remains an upstream archive dependency for the combined pipeline, while this runner has no PF-001 imports.

Current mapping, with provisional wire fields:

| Snapshot evidence | Reference projection and retained lineage |
| --- | --- |
| Subject and qualified source namespace plus native UUID | Reference observation identity derived using its existing identifier function. Require one source scope per run. Bind the original full scope beside the projection since the native ID omits source system and collection. |
| Selected HR / SDNN revision | Keep positive decimal value, bpm / ms, subject and native UUID, event start and end. Withhold measured HR assertions until the referenced independent classification evidence can be verified. Withhold unknown HR derivation from the native stream and record a projection loss. Preserve SDNN as vendor-derived. Retain PF-001 revision, artifact and receipt lineage outside the reference envelope. |
| Collector clock and authoritative availability | Map collector receipt alone to the required reference `received_at`. Keep source availability and MOTHER commit/sequence distinct. The snapshot owns selection; leave the reference's optional global time cutoff unset. Historical as-available flags remain false. |
| Explicit tombstones, including unknown UUID | Reference identity from the same scope and UUID with the observed deletion timestamp. Preserve distinct explicit delete facts and their archive references. No inferred deletion from omission, and no source resurrection in this increment. |
| Context, device, method, calibration, measurement uncertainty and coverage | Pass genuinely known stratum fields, use explicit unknown/null for unavailable fields, and retain typed coverage and losses beside the reference envelope. No conversions to RMSSD, hidden imputation, or inferred coverage. |
| No eligible active records | Explicit unavailable with an empty reference state array. Sparse baseline history remains unknown inside each supported reference state. |

Derived identity covers the exact snapshot and replay-envelope bytes, runner version/source digest, reference adapter and implementation, model/config, reference run identity, and result digest. The mapper adds its code/version, canonical snapshot hash, complete scope, interval, cutoff, clock and revision/receipt lineage. Coverage and typed losses remain alongside the result. A private temporary reference DB is discarded after each run. Current evidence snapshots and original captures remain with their authoritative producer. This scope does not provide authorization, deployment, live data handling, historical online replay, or current-result invalidation.

## Provisional wire boundary

The candidate uses flat commitment bindings and nested `source_revision`, with separate source and processing digests. The caller provides expected scope and archive, synthetic byte/member limits, and a trusted membership verifier. The verifier must check the complete member against the reopened authoritative receipt/archive view and return exactly true before replay. The runner cannot establish archive membership from caller-controlled hashes. The standalone seam tests use synthetic rows. The combined entry point, `replay_ledger_snapshot` in `integrations.mse_snapshot.ledger`, instead requires FORGE #31's trusted reopened `ConnectedIngest` and its full `verify_snapshot` check. Selected-member verification by itself cannot detect omitted observations or tombstones. The combined entry point accepts no caller-provided membership oracle.

The producer helper follows the representative rule at ATLAS `3fe247446f03b7ee3e8a36a0a18bd19eb5a1329c`. It excludes later receipts, selects the earliest eligible binding for the requested normalizer, and rejects sequence collisions or ambiguous processing. The consumer rejects duplicate or unsorted selected members. The connected path uses the authoritative FORGE producer and verifier. Distinct original delete facts that round to the same reference pair remain in lineage and emit an explicit projection loss.

Published golden verification pins the native envelope, source and processing hashes to ATLAS 0.2. The checkout for the golden comparison comes from the pinned ATLAS head. The bridge tests use bounded synthetic inputs and a separate membership oracle.

## Verify the bridge

From the repository root:

```sh
PYTHONPATH=research/mse/reference-v0.1.0/prototype python3 -B -m unittest discover -s tests/integration/mse_snapshot -v
```

## Verify the connected bridge

In an isolated exact-head assembly containing PRs #30, #31, and #27 plus PF-001 #18, set `MSE_ATLAS_CONTRACT_DIR` to the pinned ATLAS schema and golden vectors. Use the dependency-enabled Python environment and run:

```sh
PYTHONPATH=.:research/mse/reference-v0.1.0/prototype python -B tests/integration/mse_snapshot/connected_replay.py -v
```

The connected suite parses exact synthetic capture bytes, commits to a disposable PF-001 ledger, reopens it, builds a cutoff snapshot and checks real MSE output lineage. It also tampers with receipt/source/processing and cutoff claims, recomputes the outer digest, and exercises omission rejection.

## Verify a saved derived manifest

`verify_ledger_replay_manifest` takes exact snapshot bytes and a saved JSON result, trusted reopened ledger, expected archive/scope and explicit snapshot/result bounds. It reruns the pinned reference over the verified full snapshot and compares canonical bytes of the entire result. This checks scope, receipt/source/processing and deletion lineage, implementation, model/config, result digest and derived identity together. A modified manifest with recomputed caller-controlled hashes still fails. No archived observation or artifact is written by MSE replay.

The connected command above is also a standalone synthetic manifest audit. It exercises the public ORACLE capture entry, actual FORGE custody and paired SQLite backup/reopen. The result is exact before and after the restore. This audit demonstrates equality in a quiescent disposable local fixture. It covers neither live backup coordination nor host recovery.
