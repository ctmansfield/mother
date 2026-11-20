# Offline snapshot-to-MSE lineage

Under [MSE-INTEGRATION-20261120-01 r1](https://github.com/ctmansfield/mother/pull/23#issuecomment-7041443650), this draft implements the reference-facing runner. The shared snapshot-to-projection mapper awaits the ATLAS field reconciliation and GADGET freeze. The runner is an internal seam and its two input digests establish which bytes were paired. The mapper must establish semantic correspondence before callers can use it.

## Reference and projection

The unchanged reference at main `c05f38096406965496d7d4a09edf4b3575235311` uses `native_replay`, a new disposable `Store` per execution and the existing default-config retrospective `replay`. The reference manifest digest is `112ccb8df17d6afc6d8b7f932fbdeac31b1663ccd04c5538b9bd9a32e94a25f1`. The executable Python implementation digest is checked before execution. PR #18 remains an upstream archive dependency for the combined pipeline, while this runner has no PF-001 imports.

Proposed mapping for ATLAS/GADGET to freeze:

| Snapshot evidence | Reference projection and retained lineage |
| --- | --- |
| Subject and qualified source namespace plus native UUID | Reference observation identity derived using its existing identifier function. Require one source scope per run. Bind the original full scope beside the projection since the native ID omits source system and collection. |
| Selected HR / SDNN revision | Keep positive decimal value, bpm / ms, subject and native UUID, event start and end. Preserve measured HR and vendor-derived SDNN. Retain PF-001 revision, artifact and receipt lineage outside the reference envelope. |
| Collector clock and authoritative availability | Map collector receipt alone to the required reference `received_at`. Keep source availability and MOTHER commit/sequence distinct. The snapshot owns selection; leave the reference's optional global time cutoff unset. Historical as-available flags remain false. |
| Explicit tombstones, including unknown UUID | Reference identity from the same scope and UUID with the observed deletion timestamp. Preserve distinct explicit delete facts and their archive references. No inferred deletion from omission, and no source resurrection in this increment. |
| Context, device, method, calibration, measurement uncertainty and coverage | Pass genuinely known stratum fields, use explicit unknown/null for unavailable fields, and retain typed coverage and losses beside the reference envelope. No conversions to RMSSD, hidden imputation, or inferred coverage. |
| No eligible active records | Explicit unavailable with an empty reference state array. Sparse baseline history remains unknown inside each supported reference state. |

Derived identity covers the exact snapshot and replay-envelope bytes, runner version/source digest, reference adapter and implementation, model/config, reference run identity, and result digest. The final mapper will bind its own code and the frozen contract version. A private temporary reference DB is discarded after each run. Current evidence snapshots and original captures remain with their authoritative producer. This scope does not provide authorization, deployment, live data handling, historical online replay, or current-result invalidation.

## Verify the internal runner

From the repository root:

```sh
PYTHONPATH=research/mse/reference-v0.1.0/prototype python3 -B -m unittest discover -s tests/integration/mse_snapshot -v
```
