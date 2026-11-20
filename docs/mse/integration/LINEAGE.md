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

## Privacy assessment contribution

Source review for [MSE-DATABASE-PRIVACY-20261121-01 r1](https://github.com/ctmansfield/mother/pull/23#issuecomment-7045683925) used the frozen 0.2 interface, this bridge, FORGE `e4219cdf3dba73f586e3820990f3ab34f1a7c1d9`, and the MOTHER memory source at `c05f38096406965496d7d4a09edf4b3575235311`. The exact custody view and replay output should be handled as restricted physiological evidence.

| Surface | Observed source fields and exposure |
| --- | --- |
| Snapshot and native projection | The scope holds subject ID, source system, source instance and collection, with archive ID and commitment cutoff in the snapshot. Members carry stable native UUID, source and processing digest, PF-001 revision ID, artifact SHA, receipt ID and commit sequence. The source revision contains exact decimal value and lexeme, original and normalized times, source name and app bundle. Deletion times, UUIDs, JSON-pointer locators, coverage times and loss findings remain visible. Native projection carries scope subject/source, native ID, exact event bounds, collector receipt, channel/value, app/source provenance and deterministic observation ID. |
| Derived result and custody verification | The outer lineage retains scope, archive, snapshot/projection digests, commit cutoff and clock/revision bindings. It embeds complete deletion members. Reference state fields include subject/source, exact observation reference time, maximum supporting collector receipt, measurement stratum including app/device/method where supported, states and supporting/baseline/excluded observation IDs. Reference evidence lists artifact, observation and tombstone digests. Model/config/code-only pins can be shared when they are separated from per-run lineage. Dataset, state, run, result and derived IDs are deterministic content-based correlation keys. |
| Memory and embeddings | The existing migration `ops/migrations/20250925_add_memory_tables.sql` defines pgvector `memory_item`, an index over embeddings, and an expiry view. This migration declares no row-level policy or expiry job. `mother/memory/adapter.py` embeds text and stores the vector together with user ID, text, tags and arbitrary payload. Its default row ID is a truncated SHA-256 of user ID and text, and it accepts an override. Retrieval in `mother/memory/sql.py` filters by user ID and optional type/tags, with no purpose parameter. The upsert resolves conflicts on ID alone, so any future purpose-specific memory route must enforce write identity and avoid caller-supplied cross-purpose row keys. No production ACL or runtime membership is established by that query. There is no snapshot-to-memory write or embedding invocation in the inspected bridge/replay path. The addendum's model-memory separation is a design boundary. Keep raw observations, source identifiers and reversible provenance out of text, tags, payload, keys and vector inputs. |
| Paths and output | The bridge stages a temporary SQLite reference store containing the native envelope and replay rows. Successful result shapes contain no explicit local filesystem path field. Loss locators are input JSON pointers, and the native envelope retains source free text in restricted provenance. Paths embedded in input text or supplied to wrapper tracebacks, stderr or logs can still leak. Successful synthetic output lacked the absolute scratch path. Crash remnants, WAL/sidecars, delegated logs, unrelated stores and actual host configuration were outside this check. |

The connected synthetic test ingests one exact capture under two distinct archive and batch identities. Receipt and derived IDs differ, but artifact/source/processing digests, native UUID and supporting reference observation ID join both outputs. A plain hash permits equality tests and known-input matching without revealing the original bytes. When candidate inputs are constrained, it can also permit offline guessing. Neither domain-specific identities nor time binning alone breaks linkage from distinctive time series, repeated patterns, rare events or external timestamped data. No runtime attack or personal linkage was performed.

### Recommended versioned view boundary

1. Keep exact `mse.evidence-snapshot/0.2`, original bytes, clocks, digests and replay manifests in restricted custody. Put identity lookup in a separately authorized vault with its own key and backup custody. Prevent ordinary analytical, model-memory and vector-store credentials from querying vault mappings or exact manifests.
2. Define a separate, proposed `mse.analytics-projection/0.1` with a purpose/audience policy version, bounded interval and expiry, random purpose-scoped subject token only when longitudinal joins are necessary, and job-scoped record/run tokens. Never give two destinations the same token or expose raw UUID/scope, custody hashes/IDs, sequence, source name, original pointers or logs. Keep any reversible lineage mapping private with a scoped resolver and audit trail. Tokens still support linkage within their authorized scope.
3. Permit only the time and measurement precision needed for the purpose. If binning, grouping, shifting or suppressing sparse windows, record field-level loss and transformation version, assess chronology/fidelity and residual linkage risk, and do not present the reduced-identity view as exact replay evidence. With a single-subject longitudinal series, use an access-controlled query surface unless disclosure risk has been separately assessed.
4. Enforce an allowlist before any export, embedding, logging or backup copy to a lower-trust purpose. Suppress free-form source metadata and local paths. Test two-purpose token isolation, no join through shared hashes or reusable vector metadata, low-cardinality leakage, error/redaction, expired authorization, and deletion/revocation invalidation of downstream results, caches and embeddings. Record residual risks for DB-only, artifact/log/backup, credential and host/key compromise separately.

These are proposed boundaries and synthetic checks. Live stores, ACLs, key separation, backup inventory, vector contents, and disclosure risk against actual auxiliary datasets remain unverified. [NIST SP 800-188](https://csrc.nist.gov/pubs/sp/800/188/final)
