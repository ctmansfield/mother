# Offline snapshot-to-MSE lineage

Under [MSE-INTEGRATION-20261120-01 r2](https://github.com/ctmansfield/mother/pull/23#issuecomment-7041572809), `replay_snapshot(snapshot_bytes)` derives the reference projection internally from one validated synthetic snapshot. It accepts no caller-supplied projection. The wire adapter remains provisional pending ATLAS's strict nested schemas and golden examples and GADGET's freeze.

## Reference and projection

The unchanged reference at main `c05f38096406965496d7d4a09edf4b3575235311` uses `native_replay`, a new disposable `Store` per execution and the existing default-config retrospective `replay`. The reference manifest digest is `112ccb8df17d6afc6d8b7f932fbdeac31b1663ccd04c5538b9bd9a32e94a25f1`. The executable Python implementation digest is checked before execution. PR #18 remains an upstream archive dependency for the combined pipeline, while this runner has no PF-001 imports.

Current mapping, with provisional wire fields:

| Snapshot evidence | Reference projection and retained lineage |
| --- | --- |
| Subject and qualified source namespace plus native UUID | Reference observation identity derived using its existing identifier function. Require one source scope per run. Bind the original full scope beside the projection since the native ID omits source system and collection. |
| Selected HR / SDNN revision | Keep positive decimal value, bpm / ms, subject and native UUID, event start and end. Accept HR as measured only when the snapshot explicitly establishes that class. Withhold unknown HR derivation from the native stream and record a projection loss. Preserve SDNN as vendor-derived. Retain PF-001 revision, artifact and receipt lineage outside the reference envelope. |
| Collector clock and authoritative availability | Map collector receipt alone to the required reference `received_at`. Keep source availability and MOTHER commit/sequence distinct. The snapshot owns selection; leave the reference's optional global time cutoff unset. Historical as-available flags remain false. |
| Explicit tombstones, including unknown UUID | Reference identity from the same scope and UUID with the observed deletion timestamp. Preserve distinct explicit delete facts and their archive references. No inferred deletion from omission, and no source resurrection in this increment. |
| Context, device, method, calibration, measurement uncertainty and coverage | Pass genuinely known stratum fields, use explicit unknown/null for unavailable fields, and retain typed coverage and losses beside the reference envelope. No conversions to RMSSD, hidden imputation, or inferred coverage. |
| No eligible active records | Explicit unavailable with an empty reference state array. Sparse baseline history remains unknown inside each supported reference state. |

Derived identity covers the exact snapshot and replay-envelope bytes, runner version/source digest, reference adapter and implementation, model/config, reference run identity, and result digest. The mapper adds its code/version, canonical snapshot hash, complete scope, interval, cutoff, clock and revision/receipt lineage. Coverage and typed losses remain alongside the result. A private temporary reference DB is discarded after each run. Current evidence snapshots and original captures remain with their authoritative producer. This scope does not provide authorization, deployment, live data handling, historical online replay, or current-result invalidation.

## Provisional wire boundary

Top-level fields follow the ATLAS draft at `a732adda92cc79659bf2413c7d45891cf2d13264`. Each member currently carries `native_id`, `pf001_revision_id`, `artifact_sha256`, a nested `receipt`, and either `observation` or `deleted_at`. The receipt subset is `scope`, `receipt_id`, `status`, `artifact_sha256`, `mother_received_at`, `committed_at` and `commit_sequence`. The adapter validates internal consistency, including canonical digest, scope, normalized commitment, cutoff and conflict checks. These checks do not authenticate supplied receipts or prove they exist in the archive. Producer/ledger binding and the final receipt digest preimage still need exact-head integration.

## Verify the bridge

From the repository root:

```sh
PYTHONPATH=research/mse/reference-v0.1.0/prototype python3 -B -m unittest discover -s tests/integration/mse_snapshot -v
```
