# MSE-001 v0.1.0 — executed verification and limits

This record separates software verification from source-reported testing and
scientific validation. All prototype physiological fixtures are synthetic.

## Executed in this workspace

| Check | Final result | Evidence and interpretation |
|---|---|---|
| Installed reference package | 56 tests passed | 52 core and four lifecycle tests; `PROTOTYPE_RELEASE_VERIFICATION.json` |
| Independent core rerun | 52 tests passed | Subset of the 56; not an additional independent cohort; `INDEPENDENT_REVIEW.md` |
| Isolated release lifecycle | Passed | Fresh install, 22 payload-file hashes verified, synthetic import, repeat import, replay, retirement by rename |
| Synthetic archive import | 26 added initially; zero added and 26 duplicates on repeat | Exact input bytes retained; no source files changed |
| Replay reproducibility | Exact JSON byte match | Run `run:2bc95da1d8a97242a3ea2be041cf19c2a25b8114364cf874d9259a3cd021ac67` |
| Draft mechanism/intervention/causal/measurement contracts | 25 checks passed | `../design/contracts/validation-report.json`; schema, semantic, typed-condition and rejection checks |
| Proposed future MSE SQL | Seven checks passed | `DESIGN_SQL_VERIFICATION.json`; in-memory database only |
| Existing MOTHER evaluation/leakage suite | 35 tests passed | Tree-identical PF001 checkout; full account in `../docs/RELATED_REPOSITORY_AUDIT.md` |

The proposed SQL contains ten tables and a current-valid-state view. Its first
verification script had an incorrect expected count of eleven; that test fixture
was corrected to compare the explicit set of ten intended tables. No table was
added merely to satisfy the mistaken assertion.

## Independent-review corrections

An initial 43-test pass did not cover three material risks. The retained review
records them and the regression tests that resolved them:

1. Aggregate intervals now become eligible only after completion, at interval
   end, and baselines exclude overlapping earlier intervals. Historical source
   and MOTHER availability remain explicitly unestablished. Only retrospective
   snapshot replay is implemented; online/as-available modes are refused.
2. Method, exact interval duration, declared acquisition-window duration and
   calibration identity now join subject/source/channel/context/device strata.
   Unknown declarations are not silently pooled with explicit ones.
3. Known-invalid observations are excluded from inference support, and quality
   information propagates through recursive baseline/filter dependencies.

The exact-duration policy is conservative and can fragment real HealthKit
exports. Resolving that requires a documented compatibility rule and qualified
measurement information, not silent pooling.

## Final reference fingerprints

| Object | SHA-256 |
|---|---|
| `prototype/RELEASE_MANIFEST.json` | `9db2c87fcc940701c437e1e075eec568073ab860eaafb347a12530f24f3f5888` |
| Executable package | `998ad8654a801945bd0fa10b93de75755bee929317b49b3701584372e0e7dbf1` |
| Synthetic HealthKit JSON | `c3677708f2245d279bccd651d0ca978ff061258d97795039cb8d8dc3789e80a3` |
| Included synthetic state JSON | `678984d50a07eb3b06147e399cca43f4b25bab31468f24223ada6c3b18c5edab` |

Final evidence supersedes earlier fingerprints. Earlier failed probes and the
initial 43-test history are retained in the prototype change log and independent
review so subsequent model work does not lose the lessons.

## Boundaries not verified here

- Swift/iOS compilation, live iPhone HealthKit behavior, signing, background
  delivery and physical SQLite cutover were not rerun here. Repository-reported
  Swift test counts are labeled historical reports in the audit.
- The exact N3 server commit was not accessible in the checked repositories.
  Server implementation, staging and live NAS/VPS deployment were not audited.
- No source-to-VPS-to-authority physiological upload or production MSE/COACH
  loop was deployed or certified.
- No human dataset was fitted, no independent physiological reference was used
  to validate latent states, and no intervention effect was established.
- The standalone model has fixed illustrative parameters, uncalibrated
  intervals, no validated resting/activity context and no hormone, immune,
  substrate-oxidation or microbiome inference.

Schema checks test declared invariants, not complete biological correctness.
An exact synthetic replay demonstrates reproducibility under the implemented
model; it does not establish that the model describes a person accurately.

## Packaging and document checks

The final package includes a separate `PACKAGE_VERIFICATION.json` with exact
reconstruction checks for each add-only patch and the archive contents. The PDF
was rendered to page images for visual review; see `PDF_REVIEW.json` for the
reviewed output fingerprint and pagination. These checks concern delivery
integrity and readability only.
