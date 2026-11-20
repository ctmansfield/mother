# Verification observed in this session

Date: 13 November 2026 (Guam). Runtime: Linux, Python 3.12.14, standard-library
SQLite and `unittest`. Inputs: synthetic only. No existing repository or service
was modified. The release is a plain isolated directory, not a Git commit.

## Results

| Check | Observed result |
|---|---|
| Core behavioral suite after initial implementation | 37 tests passed |
| Additional complete-lineage and same-timestamp baseline tests | 39 total tests passed |
| Initial suite including install/retirement behaviors, before independent review | 43 tests passed; did not cover R1–R3 |
| Independent recheck after review corrections | **52 core tests passed**; original R1–R3 probes resolved |
| Final corrected suite including lifecycle checks | **56 tests passed**, 0 failures |
| Installation into a fresh isolated directory | PASS; explicit copy-only `deployed: false` result |
| Verification from the final corrected installed copy | **56 tests passed**, 0 failures; code hashes matched manifest |
| First synthetic v0.3 import | 26 added; 0 duplicates; raw artifact retained |
| Repeat identical synthetic import | 0 added; 26 duplicates; no new tombstones |
| Replay | 26 outputs: 16 insufficient-baseline unknown, 10 reference estimates |
| Installed replay versus included example | Exact byte-for-byte JSON match |
| Non-deleting retirement | PASS; every installed file hash preserved after rename |
| Attempt to retire modified code or untracked data | Refused by behavioral tests; existing files retained |
| Attempt to open unrelated SQLite DB | Refused; byte-for-byte existing DB preservation checked |

The initial 37-test run passed. Review then found ancestry and simultaneous-sample
coverage risks, corrected the implementation, and added the two targeted
regression tests before adding lifecycle tests. Independent review later found
three concrete gaps in interval/availability semantics, method compatibility and
quality propagation. Those were corrected, thirteen targeted tests were added,
and an independent recheck confirmed the original probes were resolved. The
43-test pass is not evidence that those uncovered gaps were absent. The recorded
sequence retains what each run established; it is not biological validation.

## Commands actually exercised

Source and installed verification:

```bash
python3 -B -m unittest discover -s tests -v
bash verify.sh
bash install.sh /workspace/scratch/d8b6cef2becf/prototype_verification/p001-installed-01
bash /workspace/scratch/d8b6cef2becf/prototype_verification/p001-installed-01/verify.sh
```

From the installed directory:

```bash
python3 -B -m mse import-healthkit examples/synthetic_healthkit_v03.json \
  --subject synthetic-person --source-instance synthetic-healthkit \
  --db /workspace/scratch/d8b6cef2becf/prototype_verification/synthetic-run-01/evidence.sqlite
python3 -B -m mse replay \
  --db /workspace/scratch/d8b6cef2becf/prototype_verification/synthetic-run-01/evidence.sqlite \
  --output /workspace/scratch/d8b6cef2becf/prototype_verification/synthetic-run-01/states.json
bash /workspace/scratch/d8b6cef2becf/prototype_verification/p001-installed-01/rollback.sh \
  /workspace/scratch/d8b6cef2becf/prototype_verification/p001-installed-01
```

The import command was run twice to verify idempotence. Retirement renamed the
installation to a new sibling path and retained its bytes. The working source and
the separate synthetic run DB were retained.

After independent-review corrections, the complete installation, installed suite,
two imports, byte-identical replay and retirement sequence was repeated with new
isolated paths `prototype_verification/p001-reviewed-install-03` and
`prototype_verification/reviewed-synthetic-run-03`. No original verification
directory or evidence was overwritten.

## Stable fingerprints

- Synthetic input SHA-256:
  `c3677708f2245d279bccd651d0ca978ff061258d97795039cb8d8dc3789e80a3`.
- Executable Python package SHA-256:
  `998ad8654a801945bd0fa10b93de75755bee929317b49b3701584372e0e7dbf1`.
- Synthetic run ID:
  `run:2bc95da1d8a97242a3ea2be041cf19c2a25b8114364cf874d9259a3cd021ac67`.

Each state embeds the implementation, configuration and model-version identity.
`RELEASE_MANIFEST.json` contains individual hashes of all shipped payload files.

## What remains unverified

No real iPhone export was imported; no physical HealthKit/Watch source, Swift
compiler, Xcode test suite, private N3/PF001 server, VPS queue or NAS filesystem was
exercised. Parameter fitting, interval coverage, biological identifiability,
interindividual generalization, prospective drift detection, causal effects and
intervention benefit remain untested. Software checks passing establishes none
of those scientific claims.

The baseline count and fixed OU parameters are engineering demonstration choices.
Serial correlation, measurement errors, informative missingness, clock drift,
source/device bias and unrecorded context are not empirically estimated.
Future-event invariance verifies ordering for already supplied intervals; it does
not establish historical receipt-time invariance. Late-received old measurements
can revise retrospective outputs. `source_as_available` and online replay modes
are explicitly refused; every state declares retrospective snapshot semantics
and marks historical source/MOTHER availability unestablished. Exact-duration
stratification may fragment irregular real exports; compatibility calibration is
future qualification work.
