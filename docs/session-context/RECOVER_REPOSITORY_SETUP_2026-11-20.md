# SESSION_CONTEXT — MOTHER GPU Protocol B / Repository Setup
Last reconciled: 2026-11-20 (Guam local). Status: INVESTIGATION / REVIEW ONLY.
Repository: https://github.com/ctmansfield/mother
Review branch: review/gpu-guard-protocol-b-20261120
Source revision observed clean on llm: 8711a81b15880bdca7a7e050839073138556d442
The assistant's review branch does NOT imply deployment or host verification.

## Mandatory operating contract
- GitHub is the preferred patch transport and durable evidence channel. Operator pulls patches on `llm`; install/verify scripts should post compact qualification receipts (including SHA, tests, exit codes, fingerprints) back to an agreed GitHub review issue/PR using existing, verified host credentials/conventions. Never require manual archive copy unless GitHub route fails.
- Keep a running change log and all state necessary to resume in-repo. Use discrete patches with release notes, explicit install/verify commands, checksums, and rollback. Never assume a command passed merely because it was proposed.
- No automatic GPU inference/replay, deployment, merges, model unloads, process kills, resets, secrets/credential changes, or deleting original evidence. Do not use shell strict-mode `set -e`, `set -u`, or `set -o pipefail`; never exit the operator shell.
- Treat historical guard HOLD as immutable, and distinguish source, observed host output, inference, and future qualification.
- User prefers compact outputs, reproducible engineering, explicit progress fingerprints and qualification receipts.

## Investigation checkpoints (operator-provided output)
Host: `chad@llm`; original run `/home/chad/fw-protocol-b-run.Z4GS2MGv/results`.
`telemetry-01.jsonl`: 118 NVIDIA samples across ordinals 1-13. Each request had exactly one NVIDIA GPU process PID. Across all samples: no simultaneous multi-PID observations.
Request 13: `deepseek-r1:14b`, PID `3791544`, GPU UUID `GPU-59ffe7a0-5ab9-9d95-12f1-4ba621956c85` (RTX 3090). Samples 1-8 identify `/usr/local/lib/ollama/llama-server`; sample 9 at 9.316s reports same PID / GPU UUID and 9002 MiB as `[No data]`, GPU 99% and total used 9009 MiB.
Request-13 record: `gpu_evidence=GPU_RESIDENT_OBSERVED`; `monitor_errors=[]`; `error=null`; `http_attempted=true`; `hold='unattributed or multiple GPU compute processes observed; future requests held'`; Ollama response `done=true`, `done_reason=length`, `eval_count=520`, `total_duration=9303505013` ns, `load_duration=2257797323` ns. Protocol complete but semantic answer may be truncated.
Earlier current-state inspection: NVIDIA process list empty and `ollama ps` empty; this is point-in-time only. Original Protocol B remains HOLD (exit code 4). Do NOT overwrite `fw-protocol-b-run.Z4GS2MGv` or presume remaining 2 prompts may be resumed without explicit qualification/approval.
Source inspected: `/home/chad/fw-gpu-20261120.NPGt2w/mother/docs/reviews/gpu-round-20261120/scientific/scientific_compare.py`. Host HEAD `8711a81b15880bdca7a7e050839073138556d442`, status --short empty. GitHub fetch by same ref succeeded.
Relevant source:
- `unattributed_processes` currently uses `Path(p["process_name"]).name.lower().startswith("ollama")` OR >1 distinct PID. **This does not recognize the observed `llama-server` basename**: provenance/guard-behavior discrepancy must be resolved; do not assert the only trigger was `[No data]`.
- `ObservedAPI.__call__` polling loop: after `nvidia()` it appends sample and evaluates HOLD WITHOUT rechecking the HTTP-completion event. Snapshot can cross completion boundary.
- `settle_idle()` is strict and requires GPU process-free before fresh request. The hold is sticky within an observer.
- `nvidia_snapshot()` executes GPU utilization and compute-process queries separately, so measurements are non-atomic.
- Existing tests include foreign GPU process pre-request and mid-request HOLD cases. Add regression coverage for real Ollama `llama-server` path, `[No data]`, new PID, multiple PIDs, and completed-request boundary.
Historical candidate set: gpt-oss:20b, medgemma1.5:4b, medgemma:27b, deepseek-r1:14b, ministral-3:14b; comparative screen planned 15 protected prompts each; all results experimental, no scientific promotion.

## Other project context recovered from previous long chat
MOTHER/COACH framework ongoing architecture: durable verified model successes/failures, successor transfer; specialists retain distinct evolving traits, autonomous skill selection, controlled niche diversity and dissent. FW-005.4 ledger earlier passed 5 tests; later role tournament FW-005.6.2 passed 684/684; FW-005.6.7 host activation pending. MSE design PR #12 pending review. E1 dynamic microbiome/host-response evidence map ongoing with mechanistic provenance and context-dependent receptors, metabolism, constraints. Avoid confusing these distinct workstreams with Protocol B.

## Next actions (not completed)
1. Review and qualify minimal guard patch on this GitHub branch; reconcile why basename `llama-server` passed 12 requests despite inspected guard implementation.
2. Add offline regression tests; preserve fail-closed semantics for unverified process identities and completion-boundary ambiguities; document remaining uncertainty.
3. Verify actual existing host receipt-publishing convention before claiming automatic GitHub posting. Implement verified receipt runner in repo if necessary, without changing credentials.
4. Operator pull the review branch, run offline install/verify, and publish GitHub qualification receipt. Merge/deploy/live evaluation require separately explicit authorization.
5. At next chat, user can say: 'Read docs/session-context/RECOVER_REPOSITORY_SETUP_2026-11-20.md from ct mansfield/mother review/gpu-guard-protocol-b-20261120 and continue at latest posted host receipt.' Always inspect latest GitHub branch / receipts first.

## Host qualification checkpoint — 2026-11-20 (verified through GitHub)
Two **distinct** review implementations were tested on the llm host:
A. Previous archive `fw_gpu_guard_review_v0.1.tgz` (sha256 `674af22f99b8956ba8abed5f26f7228e400b8b20f745816b5018f4a7ee395992`) installed into `/home/chad/fw-gpu-20261120.NPGt2w/mother`. Installer switched to local branch `review/protocol-b-gpu-identity-20261120`, left patch uncommitted. AST syntax and whitespace passed. All 8 guard-focused tests passed (including known-PID name dropout continuity, unknown PID/foreign executable/GPU UUID change/PID reuse/multiple process HOLD). No live GPU testing. This is NOT the same implementation as GitHub PR #15.
B. Review branch `review/gpu-guard-protocol-b-20261120` pulled into separate worktree `/home/chad/fw-gpu-guard-review-20261120` at commit `696f1456c96d8d818b9e99e0c76b06de749719b5`. Offline `test_scientific_compare.py`: **18 tests run, 16 passed, 2 skipped**, exit code **0**, log SHA256 `222b225b022fab80dd3a7dacbe23127939b4b3c961e5b782787517df281de766`. Verified automated GitHub receipt in https://github.com/ctmansfield/mother/pull/15#issuecomment-7028321516 (time 2026-11-20T02:20:18.819183+00:00). Local receipt `/home/chad/.local/state/mother-fw00412/qualifications/protocol-b-guard-696f1456c96d.json`.
The two skipped integration tests require the reviewed FW00412 broker source / `FW00412_TEST_CHECKOUT`; do not misreport them as passed.
Historical Protocol B HOLD still active and original evidence not changed. Neither branch is merged. No full host GPU qualification or inference rerun has been completed.
**Reconciliation next:** inspect the uncommitted diff in the original source tree against the published GitHub review patch, and choose/qualify one canonical implementation. Do not overwrite or cherry-pick over the uncommitted archive patch. Review the original guard/source provenance discrepancy and complete 2 integration tests with pinned broker checkout. Then separate the PR from unrelated historical differences before considering merge.
