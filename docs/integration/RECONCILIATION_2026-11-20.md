# MOTHER integration reconciliation — 2026-11-20

**Status:** planning + dependency audit; not a merged qualification receipt. **Base:** current `main` at integration branch creation `818426fe90fab1bfd9583640363d4001b30e633f`.

## Objective
Reconcile actively developed features into the main branch with reproducible qualification and intact provenance. Do not merge a large stale branch wholesale; isolate changes into coherent feature families, with paired Coach dependencies handled explicitly. GPU evaluations are held until separately authorized.

## Open PR inventory and dependency order

| Stream | PRs | Merge order/dependencies | Qualification/merge conditions |
|---|---|---|---|
| Physiology PF-001 | #1 | Rebase onto current main, merge first | Archive/contract/migrations review; synthetic tests; check paired Coach commit compatibility |
| Local-worker qualification | #2 → #3 | #2 after #1; #3 after #2 | Offline worker/protocol tests, provenance; no unreviewed generated output promoted |
| Replay R02 | #4 | after #1 | Offline qualification tests and source ownership |
| Coach→Mother ingest | #5 → #6 → #7 → #8 → #9 | after #1, strict sequential chain | Paired Coach sender pins, actual cross-repo tests, retry/receipt lineage; no live service activation |
| MSE reference/design | #12 | independent on main, but touches README, context index, pre-commit | Manifest, schemas, prototype/test suite, source provenance, cross-stream context conflict review; proposed SQL not deployed |
| E1 bibliography | #13 | independent, data only | Execute verify_register.py in clean checkout, validate provenance/alias retention, no evidentiary promotion |
| Scientific GPU and behavioral | #14 | independent main branch, touches context index | Offline/full regression suites and manifest validation; GPU launch gated and original Protocol B HOLD preserved |
| GPU guard + session recovery | #15 | reconcile onto #14 rather than merge stale branch wholesale | Prefer #14 trusted_ollama_gpu_process() predicate; independently port boundary metadata, focused tests, receipt poster, session context. Explicitly resolve differing archived-patch identity-continuity policy |

All listed PRs are currently draft. PR #1's `mergeable` metadata was inconsistent across reads; check live before merging. Main contains changes after the earlier PF-001 base. CI combined status API returned empty statuses for #12–#15; that is **not** a test pass.

## Verified GPU guard reconciliation facts
- #14 `scientific_compare.py` has `trusted_ollama_gpu_process`, verifies PID is a positive decimal string, recognizes exact `/usr/local/lib/ollama/llama-server`, legacy `ollama` and `ollama_llama_server`, and rejects multiple distinct GPU PIDs. Six focused guard regressions.
- #15 added the HTTP-completion-boundary sample annotation and host offline verifier/receipt poster and permanent context; its alternate path predicate is less strict about malformed PID. Keep #14's guard semantics, carry forward only independently qualified additions.
- A separate archive patch v0.1 was installed *uncommitted* in host source tree `/home/chad/fw-gpu-20261120.NPGt2w/mother` under branch `review/protocol-b-gpu-identity-20261120`. Eight synthetic tests passed. Its conditional `[No data]` acceptance is a divergent experimental design and must NOT be silently combined.
- #15 host receipt: https://github.com/ctmansfield/mother/pull/15#issuecomment-7028321516 confirms 18 tests run, 16 passed, 2 skipped; log SHA256 `222b225b022fab80dd3a7dacbe23127939b4b3c961e5b782787517df281de766` at `696f1456c96d8d818b9e99e0c76b06de749719b5`.
- Original run `/home/chad/fw-protocol-b-run.Z4GS2MGv` is HOLD and must not be modified. Request 13 `deepseek-r1:14b` finished `done=true`, `done_reason=length`, but the NVIDIA sample returned `[No data]` for prior PID `3791544`. No simultaneous multi-PID sample was observed. **Provenance discrepancy:** original code at `8711a81b` would reject `llama-server` even before name dropout, so verify executed wrapper hash before root-cause closure.

## Integration invariants
1. Do not change passwords, credentials, GPU residency, services, model state, original evidence, or database deployments as a side effect of code integration.
2. No generated agent proposals or unverified scientific/microbiome facts are promoted merely by merging references.
3. Preserve feature-specific unit/integration tests, manifests, release notes, changelog and operator rollback instructions.
4. Run checks against the exact candidate SHA in clean isolated worktrees. Record `passed / failed / skipped` distinctly; provide original stdout/stderr digest, toolchain, host timestamp, and CI run URLs.
5. Publish the host receipt automatically on the corresponding GitHub PR using existing authenticated `gh` (no new credentials). On posting failure, keep a private local receipt and report failure, never claim a remote pass.
6. Prefer additive, targeted merge commits/cherry-picks rather than giant cross-cutting PR merges. Preserve fork/branch references and link merges to original PRs.
7. Source and contract changes shared with Coach require checking Coach PR status and pin compatibility before merging.
8. Do not use shell strict-mode flags `set -e`, `set -u`, `set -o pipefail` or commands that exit the operator shell.

## Phase gates
- **Phase A:** collect clean HEAD and exact diff/CI status for each PR; evaluate context/index.json, README.md, and .pre-commit-config.yaml collisions. Establish exact Coach companion merge/pin sequence.
- **Phase B:** run independent, offline tests on the candidate integration tree and record GitHub receipts; resolve failures instead of bypassing them.
- **Phase C:** incorporate isolated feature families in dependency order, using guarded merges with verified target HEAD and explicit audit trail.
- **Phase D:** separately qualify GPU/behavioral runners and native scientific adapters; no live evaluation or protocol resumption by an integration merge.

## Session recovery
In a new conversation: “Read `docs/integration/RECONCILIATION_2026-11-20.md` from `ctmansfield/mother` integration/reconcile-features-20261120; read `docs/session-context/RECOVER_REPOSITORY_SETUP_2026-11-20.md` from review/gpu-guard-protocol-b-20261120; inspect PRs #1–9, #12–15 and their latest host receipts; continue from the latest qualified merge gate, not conversation recollection.”

## Reconciliation execution log (2026-11-20)
- PR #16 merged documentation-only reconciliation plan into main: `9fb948d4863900b275e39f6e2bd06f6190371285`.
- PR #13 merged additive E1 reference registry into main: `1b8ebbfe19e9b60b7399d1ba49fe26d8f061bda7`. Independent connector-side structural checks over actual GitHub files: 248 records and distinct keys, 229 DOI entries with DOI/URL consistency, 248 CSV keys matching JSON, 73 Scout entries, no missing original legacy aliases, consistent predecessor DOI links. **Not** a full execution of the committed Python verifier or scientific source appraisal. No runtime or scientific claim promotion.
- Remaining PRs #1–9, #12, #14–15 remain under reconciliation; their code was not merged by these actions. The original Protocol B GPU HOLD remains.

- PR #12 merged MSE reference/design package: `002ec209bc96b1d23d534023072e4ab2ccf4f5d7`. At PR head `3e652d39d1b5d0b45580fbd7e176c930afb55dcf`, GitHub Actions completed successfully for MSE reference, pre-commit, mother-ci, and Context reader. Reference/proposed SQL preserved as review material; no database migration or runtime deployment was performed.
- GitHub Actions checks at PR heads #1–9 returned success for general CI and pre-commit, and for each available dedicated synthetic offline workflow. **Paired Coach PRs #1–6 are OPEN and UNMERGED**, although their tests may use exact pinned commits. Do not assume a paired Coach branch is on Coach main.
- PR #14 had mother-ci and Context reader success but pre-commit FAILURE at head `bfddc895cb7303004c9217a687bd100755e84b37`; resolve before merging. #15 is divergent and must be reconciled with #14.
- Detailed #14 CI failure readback from workflow run `44556981138`, job `135675580741`: Black reformatted 16 files, Ruff found 12 lint errors (five auto-fixed, seven unresolved). This is a real source hygiene gate, not a GPU failure; patch formatting/lint on review branch and rerun GitHub Actions before merge. Preserve release manifests/hashes when changing reviewed source.
