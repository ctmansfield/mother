# MSE-P001 — 0.1.0 — 13 November 2026 (Guam)

## Scope

New isolated offline prototype built after inspection of the active HealthKit
JSON collector and experimental SQLite branch. No existing repository, deployed
service, source database, credentials, signing materials or automation changed.
No Git commit, push, merge or deployment is included in this deliverable.

## Added

- Exact-byte artifact hashing and source-specific v0.3 JSON importer.
- Explicit Swift date epoch, UUID-scoped identity, provenance and SDNN semantics.
- Separate SQLite replay evidence, immutable observations, artifact associations,
  conflicts retained as rejected imports, tombstones and run invalidation.
- Prior-only scalar OU reference filter with unknown states, irregular timing,
  gap resets and pinned model/source/configuration lineage. Prior means complete
  nonoverlapping event intervals in an explicitly retrospective snapshot; online
  and historical-as-available inference are not implemented.
- Method, exact recorded/declared window and calibration strata; aggregate-end
  timestamps; known-invalid quality exclusions and recursive quality propagation.
- Observed-support signed/positive area integration, without gap filling.
- Synthetic fixture/replay, behavioral tests and add-only installation.
- Non-deleting rollback that refuses modified or untracked installation content.

## Verification and claims

`VALIDATION.md` records checks actually performed and observed counts. The release
manifest checks byte integrity, not authorship or biological correctness.

Uncertainty intervals are uncalibrated reference-model intervals. Neither the
model nor a passing test establishes an autonomic mechanism, insulin action,
mitochondrial dysfunction, inflammation, microbial function or treatment benefit.

## Known limits

No Apple hardware, Swift/Xcode build, real HealthKit export, live PF001/N3 server,
private network or production service was exercised by this Python prototype.
The inherited repository's reported tests are separate from this package's tests.
Default baselines lack acquisition context. Clock errors and cross-device bias
remain unqualified. The glucose replay option is a new explicit test/export
contract; it is not a working CGM integration.

Independent review found three pre-release gaps in temporal support, method/window
compatibility and ancestor quality propagation. These were corrected before the
final package; `CHANGELOG.md` and `VALIDATION.md` retain that review history.

## Installation, upgrade and rollback

Use `bash install.sh NEW_EMPTY_DESTINATION` followed by `bash DESTINATION/verify.sh`.
No in-place upgrade is supported. Install a new version alongside the previous
one and replay a copied evidence set. Use `rollback.sh DESTINATION` to rename an
unchanged installation into a retained retirement directory. Raw input files and
external replay data remain unchanged.
