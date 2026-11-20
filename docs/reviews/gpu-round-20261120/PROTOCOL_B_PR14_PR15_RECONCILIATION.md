# Protocol B + PR14/PR15 integration — review release notes

**Status: offline review candidate; not cleared for live GPU inference.**

## Origin and integration decisions
- Base: MOTHER PR #14 commit `bfddc895cb7303004c9217a687bd100755e84b37` (scientific, native, behavioral, Protocol B and role-replay packages).
- Integrated from #15: record `http_completed_at_sample_end` for NVIDIA samples; add deterministic HTTP-boundary regression; restore GitHub host qualification receipt workflow; preserve session recovery context.
- **Canonical GPU guard:** retain #14's `trusted_ollama_gpu_process` with validated positive decimal PID and exact `/usr/local/lib/ollama/llama-server` recognition. This is stricter than the alternate implementation in PR #15.
- **Unknown NVIDIA `[No data]` names remain fail-closed HOLD**. A separate archive patch accepts certain same-PID transitions based on process lifetime verification; it is not automatically imported. Historical Protocol B ordinal 13 HOLD and its original evidence are unchanged.
- Explicit exclusion: MotherHealthBridge is being developed elsewhere; this candidate does not import, merge, or deploy that repository. No runtime activation, service or database changes.

## Outstanding source qualification
1. PR #14 Black/Ruff CI failure must be fixed in an isolated worktree. The host should run approved formatters and inspect their diff rather than bypass checks. Use the actual repo-configured formatter versions.
2. Changing `scientific_compare.py` or `test_scientific_compare.py` invalidates tracked SHA256SUMS. Regenerate all affected nested and top-level source hash manifests according to their actual relative paths; verify every line. Do not update hashes without reviewing associated source changes. Do not run the live `RUN-SCIENTIFIC.sh`.
3. Run all offline tests: `test_scientific_compare.py`, `test_gpu_guard_regression.py`, `protocol_b/test_runner.py`, `role_replay/test_replay.py`, native/behavior packages, and relevant pre-commit/GitHub workflows. Some FW00412 integration tests require the correct pinned broker checkout; distinguish skips from passes.
4. Publish exact host commit SHA, test/format results, skipped tests, manifest verification, and log digests to the integration PR. Use existing `gh` credentials; no credential changes.
5. Reconcile against the latest `main` and the concurrent MOTHER/COACH candidate PRs (#18/#8) before a canonical main merge. Avoid overwriting shared `context/index.json` or duplicate scientific source versions.

## Operator preflight (no GPU)
```bash
cd /home/chad/fw-gpu-guard-review-20261120
git fetch origin integration/protocol-b-pr14-pr15-20261120
git worktree add -b integration/protocol-b-pr14-pr15-20261120 /home/chad/protocol-b-reconcile-20261120 origin/integration/protocol-b-pr14-pr15-20261120
python3 -B /home/chad/protocol-b-reconcile-20261120/docs/reviews/gpu-round-20261120/scientific/verify_and_post.py
```
The last command performs offline tests only and posts a compact receipt to PR #20; it does not update hash manifests or qualify the full source tree. The branch must remain clean when invoking it.

**Future Protocol B:** Never edit or reuse the original held campaign directory. A fresh comparison requires new reviewed design/authorization, preserved source pins, and a new exclusive state directory; `done_reason=length` is not evidence of answer completeness. No silent resumption of ordinal 14.
