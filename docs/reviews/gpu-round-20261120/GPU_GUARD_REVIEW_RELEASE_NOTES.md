# Protocol B GPU guard review patch — 2026-11-20

Status: REVIEW ONLY. **Do not merge, deploy, or restart Protocol B from this patch.**

## Source
- Repository: https://github.com/ctmansfield/mother
- Branch: `review/gpu-guard-protocol-b-20261120`
- Original operator-confirmed clean source SHA: `8711a81b15880bdca7a7e050839073138556d442`
- Review PR: https://github.com/ctmansfield/mother/pull/15
- Preserved original run: `/home/chad/fw-protocol-b-run.Z4GS2MGv`, original HOLD exit 4; remains untouched.

## Changes
1. Recognize the canonical Ollama GPU worker `/usr/local/lib/ollama/llama-server` in addition to the exact `ollama` executable basename. The old `startswith("ollama")` was over-broad and did not recognize `llama-server`.
2. Retain fail-closed handling for `[No data]`, new/unknown and foreign PIDs, and multiple PIDs. No PID-continuity bypass is made without independent lifetime attestation.
3. Annotate every NVIDIA sample with `http_completed_at_sample_end`, enabling forensic inspection of HTTP-completion boundary samples while retaining raw samples and HOLD behavior.
4. Regression tests cover canonical runner identity, unknown names and multiple PIDs, and HTTP boundary annotation.
5. Add repository SESSION_CONTEXT document for long-chat recovery and a one-command offline verification with automatic GitHub PR qualification receipt.

## Operator commands (read-only on original run; offline tests)
```bash
cd /home/chad/fw-gpu-20261120.NPGt2w/mother
git fetch origin review/gpu-guard-protocol-b-20261120
# For a clean, dedicated review checkout, prefer a separate worktree:
git worktree add /home/chad/fw-gpu-guard-review-20261120 origin/review/gpu-guard-protocol-b-20261120
python3 -B /home/chad/fw-gpu-guard-review-20261120/docs/reviews/gpu-round-20261120/scientific/verify_and_post.py
```

The verifier requires `git branch --show-current` to match the review branch. When creating a worktree from the remote tracking ref, it may be detached, so create a *local branch* at worktree creation using:
```bash
git worktree add -b review/gpu-guard-protocol-b-20261120 /home/chad/fw-gpu-guard-review-20261120 origin/review/gpu-guard-protocol-b-20261120
```
Use this second worktree command **instead of**, not after, the first when no local review branch exists. Do not run both. The verification script uses existing `gh` auth to post a compact result to PR #15, preserves a private local receipt whether posting succeeds or fails, and never starts Ollama inference. If `gh` is not already authenticated, do not change credentials automatically.

## Qualification gate
- GitHub publication: complete on review branch.
- Offline regression qualification: pending host execution.
- Host receipt posted: pending host execution.
- Original 13 request observations remain immutable. No automatic replay, remaining requests, or publication of scientific conclusions.
- **Provenance discrepancy unresolved:** reported earlier successful requests for `llama-server` conflict with the original source's basename predicate; check whether actual executed wrapper/source hash equals the inspected file.
- PR base comparison may include older unrelated commits because branch begins at historical `8711a81b`; inspect and rebase onto an appropriate base before considering merge.
