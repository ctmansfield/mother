# Behavioral and E1 library next-round review

Task: `behavior-e1-review-20261119` · Owner: `/root` · 19 November 2026

**State: source-only work in progress.** This report records verified qualification evidence, source corrections and the next bounded experiments. The MOTHER report branch is planned from `818426fe90fab1bfd9583640363d4001b30e633f`; existing MSE12 design and runtime files are preserved. This local preparation has not created a MOTHER commit or pull request.

## Completed workflow and local checks

The [FW00567 host campaign](https://github.com/ctmansfield/production-framework/issues/133#issuecomment-7008931692), source `d18ee0350cbfecd3bda3984f8deeb8a9cfa194b0`, completed 400 sequential role calls across 80 workflows. Protected code passed in 46 workflows, while only three became eligible for human review. GPT-OSS 20B passed 7/8 strict and 8/8 guided tasks; the other coder contrasts improved materially under the guided treatment. Review/QA protocol validity and HOLD reasons are the next diagnostic. The aggregate result does not establish the reason for each held workflow or a permanent model assignment.

The [FW00412 host receipt](https://github.com/ctmansfield/production-framework/issues/139#issuecomment-7009907399), source `ba6fbb90c031f122b7db61d2f67f2b22ef1cf130`, records protected offline suites PASS with five scientific roles, 15 candidate/abstain cases and zero model/GPU calls. An independent local source-snapshot rerun passed **59 FW00410 + 50 FW00411 + 70 FW00412 = 179 tests**, all 37 package-manifest entries, and four deterministic smokes. The FW00412 graph/source hashes match the host receipt. This is software-boundary evidence; live scientific model ability remains unmeasured.

The original FW00411 refusal occurred before tests because its qualifier expected a stale inherited Git blob. [Correction `8f9907e7f6b5c4f639123ff1e8b8fe629b8d0308`](https://github.com/ctmansfield/production-framework/commit/8f9907e7f6b5c4f639123ff1e8b8fe629b8d0308) pins actual blob `521261fe0a8f9ba09f152f95319d705283d9aba7` and preserves source verification. Its new host qualification remains pending; the original refusal is retained.

## Behavioral next round

The Behavioral/Psychophysiological COACH work is [issue #144 / draft PR #148](https://github.com/ctmansfield/production-framework/pull/148). Baseline pin: `8fe26e762f33315d18a167f703688ef13feb9474`. Root reports correction candidate `7666e95f7d9b761515496141bf5e6fd647b6f82e`, eight changed files, and 46 local tests versus 38 baseline tests. Root's exact-commit read-back of all eight files is **PENDING_ROOT_FILL** at this report revision.

The next-round design proposes six roles and 24 benchmark cases across four episodes. Preserve distinctions among observed events, transient states, traits, context/lag alignment, contradictions and measured outcomes. Keep the recommendation, acknowledgment, actual action and outcome stages separate. The completed code/synthetic tests do not establish a real-person behavioral model or causal effect.

## E1 local literature trial

The E1 article work is [issue #145](https://github.com/ctmansfield/production-framework/issues/145), baseline `9a7d38a1786bb5e851da59d4596830563a36e72d`. It starts with all 27 numbered Draft 0.2 references and the intended host repository `/mnt/nas_storage/research/e1-literature`.

Download and retain legally accessible full text with source/version identifiers and byte hashes. Preserve an explicit per-reference acquisition state. Papers requiring account access belong in a university-download queue for user import; a metadata record or queue entry is not a downloaded article. The trial should report verified full-text successes, unavailable/account-required items, identity conflicts and transport errors separately. E1 remains the project's foundational working premise; downstream evidence carries its own context and uncertainty.

| Final integration field | Current state |
|---|---|
| Literature correction commit | PENDING_ROOT_FILL |
| Literature patch verification and test count | PENDING_ROOT_FILL |
| Verified local full-text acquisitions | PENDING_ROOT_FILL — no count claimed here |
| University account queue and unresolved references | PENDING_ROOT_FILL |
| Provider probe | Root reports a timeout; live retrieval remains unverified |

## Remaining execution boundary

The `llm` host is unavailable from this work session. No new host scientific inference, live article-library completion, deployment or production-memory update is claimed. Follow the accompanying scientific trial runbook only after confirming the current installed roster, exact offline receipt and idle GPU. The coding diagnostic can first read the existing aggregate summary without any new model calls.

## Evidence and continuation

- `LOCAL-TEST-REPORT.json`: measured local tests, manifests and smoke hashes.
- `SOURCE-RECEIPTS.json`: exact fetched GitHub receipt bodies and immutable source pins.
- `SCIENTIFIC-TRIAL-RUNBOOK.md`: source-defined roster and bounded live steps.
- `CODING-HANDOFF-DIAGNOSTIC.md`: aggregate inspection and protocol-calibration design.
- `INTAKE.md`: actual reader/intake observations and unresolved source freshness.

Before source publication, root must fill the pending rows from observed results, synchronize the context report copy, recompute reference/capsule digests, register against the current index hash, and validate the resulting packet. Publication does not mark the task merged, deployed or runtime-verified.
