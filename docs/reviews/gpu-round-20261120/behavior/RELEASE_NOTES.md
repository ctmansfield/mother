# Behavioral GPU round preparation — 2026-11-20

## State

Ready for root review and integration after the scientific stage. No remote
writes, model calls, GPU calls, model pulls or role assignments occurred during
this package's preparation.

## Changes

- Added 24 immutable synthetic cases covering six responsibilities and four
  evidence conditions each.
- Split visible cases from a host-only expected rubric; manifest verification
  refuses altered input bytes.
- Added a strict response contract and separate protocol, binding, evidence ID,
  evidence relevance, evidence completeness, decision, numeric and critical-error
  results. Rationale remains explicitly unreviewed.
- Clarified that a supported descriptive limitation can be selected; abstention
  is reserved for cases where none of the supplied conclusions is warranted.
- Added relevance distractors and a temporal availability case. Citing all facts
  fails eight cases; blanket abstention answers at most six.
- Added a network-free bounded adapter for the shared serialized local Ollama
  caller. It preserves partial failures and refuses existing output directories.
- Added nineteen focused offline tests, including independent calculation of
  the pooled/within-person sign reversal, adversarial evidence and identity
  cases, protected-prompt separation, mock adapter interruption behavior, and
  continued scoring after completed but truncated or malformed output.
- Integrated the separate behavioral launcher with the unchanged published
  scientific loopback transport and observer. Five additional orchestration
  tests cover predecessor proof, exact digest binding, the shared lock, partial
  failures and all 120 serial mocked calls with identical prompts and seeds.

## Validation

Executed from `/workspace/scratch/59f0fdbd0913`:

```bash
python -m py_compile gpu_round/behavior/adapter.py gpu_round/behavior/benchmark.py
python gpu_round/behavior/benchmark.py validate
python -m unittest discover -s gpu_round/behavior/tests -v
```

Result: pack validated; 24 tests passed (19 pack/adapter and 5 orchestration).
All inference callbacks in those tests
were deterministic local mocks. Actual model calls: **0**. GPU verification:
**not performed**. Model qualification: **not claimed**.

Frozen pack SHA-256:
`803d7c62e0574974ceb729b238f92e02c27d90af787ddc522b92078685e8319b`.

## Source and task context

The design follows the corrected FW00413 package and its
`NEXT_ROUND_DESIGN.md` at production-framework commit
`7666e95f7d9b761515496141bf5e6fd647b6f82e` (draft PR #148).
The separate protected-question/reply boundary is compatible with the
FW00412 broker pattern at
`ba6fbb90c031f122b7db61d2f67f2b22ef1cf130`.

The user's latest ordering supersedes the earlier source-only timing:
scientific GPU comparison first, behavioral GPU comparison afterward, while
behavioral preparation proceeds in parallel with scientific execution.
Literature acquisition remains open and deferred in issue #145.

Root owns publication, the campaign source pin, source verification, candidate
inventory, the exclusive GPU lock, external telemetry and the live decision to
advance from scientific to behavioral. This package supplies one adapter, not
a competing launcher.
