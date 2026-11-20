# MOTHER-only integration candidate — 2026-11-20

**Scope isolation:** Does not access, modify, merge, or deploy the separate `ctmansfield/mother-health-bridge` repository. User is integrating MotherHealthBridge in other sessions; its integration is intentionally deferred. No Coach repository writes.

Review: https://github.com/ctmansfield/mother/pull/17
Branch: `integration/mother-only-candidate-20261120`
Starting main HEAD: `c05f38096406965496d7d4a09edf4b3575235311`

## What exists / what does not
- This branch initially publishes only the offline staging builder (`docs/integration/prepare_mother_only_candidate.py`) and this context. It is not yet a combined feature implementation or a passed integration test.
- Host staging runs under a **new separate worktree** `~/mother-only-candidate-20261120`, local branch `integration/mother-only-staging-20261120`. It does not alter current main, running services, or the user's ongoing MotherHealthBridge work.
- Staging order: #1 PF-001, #2 LW-001, #3 LW-002, #4 R02, #5–9 I01 ingestion/replay/receipt chain. This order preserves dependency provenance.
- The builder checks source file paths for bridge markers before each merge, disallows any bridge-related changes in candidate diff, stops and aborts an in-progress merge on first conflict, and posts compact status to PR #17 via existing `gh` credentials. It does not push merged feature code nor claim tests have passed.
- #14 GPU/behavioral and #15 guard review are **not** included in this first candidate; #14 Black/Ruff failure and guard-policy divergence need a separate candidate. Preserve original Protocol B HOLD.
- #12 MSE and #13 E1 are already merged to main; no need to re-import them.

## Operator action
From an existing local Mother checkout (avoid the uncommitted guard-patch checkout), run:
```bash
cd /home/chad/fw-gpu-guard-review-20261120
git fetch origin integration/mother-only-candidate-20261120
git worktree add -b integration/mother-only-candidate-20261120 /home/chad/mother-only-candidate-bootstrap-20261120 origin/integration/mother-only-candidate-20261120
python3 -B /home/chad/mother-only-candidate-bootstrap-20261120/docs/integration/prepare_mother_only_candidate.py
```
A worktree command may refuse if the branch or destination already exists. Do not force or overwrite; inspect the existing path and branch first. Expected GitHub receipt: PR #17. On conflict, preserve failure details; do not merge or force.

## Qualification gates after staging
1. Inspect candidate diff and conflict receipt and ensure no MotherHealthBridge code paths are touched.
2. Run offline Mother unit and integration tests, and exact Coach cross-repository pinned acceptance checks. Note Coach PRs #1–6 are still unmerged.
3. Run formatting/lint, GitHub CI and targeted regression tests on candidate SHA, record skipped separately, post SHA/digests and results to GitHub.
4. When all gates pass, push candidate branch from the isolated worktree to a distinct integration review ref, open a reviewed PR targeting main, merge only after confirming latest main and dependencies. Do not deploy or run GPU inference as a side effect.

## Session rollover
Read this file and `docs/integration/RECONCILIATION_2026-11-20.md` from main; inspect PR #17's most recent host receipts. The MOTHER-only candidate is separate from MotherHealthBridge. Continue at the latest verified integration checkpoint, never infer that a branch is already merged.
