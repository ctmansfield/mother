# VERIFY — PF-001 / 0.1.0

Run the bundle's `verify.py` against the new installation created by
`install.py`, using the separate verification environment from `INSTALL.md`.
The verifier first checks the exact reviewed Git trees, absence of extra
untracked/ignored code, and byte-identical Coach/Mother schema copies. It then
runs the offline suites and produces a synthetic four-source replay.

The result directory is outside the repositories and contains command logs,
exit results, `verification.json`, the retained synthetic archive, import
accounting, replay JSON and self-contained HTML. A failed stage is recorded and
returns nonzero. Successful verification has `status: offline_verified` and
`evidence_level: synthetic_integration`. No deployment or personal-performance
flag becomes true.

## Checks and acceptance

| Area | Required evidence |
| --- | --- |
| Contract/time | Offset-aware timestamps; mixed per-row epoch/ISO input; DST ambiguity rejection; null versus zero; exact channel/method identity |
| Targets | Hand-calculated `(t,t+H]` results; incomplete/gapped horizons remain null; changes after a cutoff cannot alter earlier features; local-time configuration is explicit |
| Archive | Original byte hashes; repeat-import stability; corrections and reversions; history survives later rolling sync/reopen; checkpoint commits are atomic; saturated/failed API ranges do not claim completeness |
| File readers | Original XML/TCX/CSV retained; rejected/unsupported items counted; no ECG/RR inferred; unknown specimen/device/availability retained |
| Replay | Visible absent/partial/unknown coverage; untimed annotations retained without invented occurrence; complete session/source links; explicit processing-version selection |
| Evaluation | Earlier-only baseline; shared-outcome groups; purging across the split; supported label availability; zero versus null; overlap rejection; uncalibrated interval labeling |
| Coach | Strict flow JSON; source-ID/time-preserving candidate preview; no blanket spike classification; escaped offline replay; explicit live-test gate |
| Packaging | Dirty checkout preservation; local hooks suppressed; untracked/ignored Python shadowing rejected; exact patch/tree checks; failures propagate; clean rerun |

## Direct development commands

These are the actual bounded suites used by the release verifier. Do not
substitute a broad default test command that might run notifications.

```bash
cd /path/to/review/mother
/path/to/venv/bin/python -m pytest -q tests/physiology \
  analytics/tests/test_physiology_hrv.py \
  analytics/tests/test_physiology_rules.py \
  analytics/tests/test_physiology_windows.py \
  analytics/tests/test_archive_nightscout.py
cd /path/to/review/coach
COACH_RUN_NETWORK_TESTS=0 /path/to/venv/bin/python -m pytest -q \
  tests/test_physiology_flows.py tests/test_physiology_replay.py \
  tests/test_end_to_end.py
```

The bundle verifier additionally disables bytecode output, pytest cache/plugin
autoload and inherited import overrides. Existing Coach live tests are skipped
unless explicitly opted in. Do not enable `COACH_RUN_NETWORK_TESTS=1` during
ordinary development: those older tests can send real notifications.

The independent acceptance suite builds a local wheel without network/build
isolation and verifies schema, migration, fixture and analytics YAML resources.
It also loads the default configuration from outside the repository directory.
Release preparation separately exercised an installed package's synthetic demo.

## Evidence boundaries

Source inspection, isolated tests, synthetic integration, real-data integration,
deployment and verified live behavior are separate evidence levels. The final
bundle contains exact release revisions/hashes and the executed result logs;
`VERIFICATION.md` explains the scope. The earlier tracked Parquets were not used
as a representative personal dataset. No accuracy, recovery, clinical or
treatment-benefit claim follows from the synthetic arithmetic fixtures.

The old optional MI/bootstrap integration run was interrupted with exit 130 and
is not counted as passed. Existing Makefile/shell wrappers can mask errors;
they are not the release gate. Browser layout inspection remains open because
a browser binary was unavailable; tested HTML generation/validation is a
separate result. No service, device, network interruption or production restart
was verified here.
