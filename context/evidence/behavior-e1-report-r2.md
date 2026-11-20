# Behavioral and E1 library next-round review

Task: `behavior-e1-review-20261119` · 19 November 2026

**Source corrections and the next-round design are ready for review.** The current tested suites pass **294 local CPU tests**, plus four scientific deterministic checks. Behavioral and literature corrections are saved in their existing draft PRs; all 19 changed files were fetched from their new commits and matched the tested bytes. Host/GPU testing and actual E1 article acquisition remain pending because this session has no connection to `llm` and its live metadata probe timed out.

## Completed workflow

The [FW00567 host campaign](https://github.com/ctmansfield/production-framework/issues/133#issuecomment-7008931692), source `d18ee0350cbfecd3bda3984f8deeb8a9cfa194b0`, completed 400 sequential role calls across 80 workflows. Protected code passed in 46 workflows, while three became eligible for human review.

| Experimental coder/contrast | Strict code PASS | Guided code PASS | Human-review eligible, strict/guided |
|---|---:|---:|---:|
| GPT-OSS 20B baseline | 7/8 | 8/8 | 0/8; 0/8 |
| Qwen2.5-Coder 14B Q8 | 0/8 | 5/8 | 0/8; 1/8 |
| Devstral Small 2 24B | 0/8 | 4/8 | 0/8; 0/8 |
| Qwen3-Coder 30B | 0/8 | 7/8 | 0/8; 2/8 |
| Planning/QA control, GPT-OSS coder | 7/8 | 8/8 | 0/8; 0/8 |

The immediate diagnostic is review/QA protocol validity and HOLD reasons in the existing host summary. The aggregate table does not establish why individual workflows were held. The guided treatment combines JSON guidance and code-fence recovery; separate these factors in the next experiment. The source's false-approval counter includes QA and both reviewers; interpret the reported zero alongside valid-decision denominators. See CODING-HANDOFF-DIAGNOSTIC.md for a hash-verified, read-only host command.

## Scientific qualification

The [FW00412 host receipt](https://github.com/ctmansfield/production-framework/issues/139#issuecomment-7009907399), source `ba6fbb90c031f122b7db61d2f67f2b22ef1cf130`, records three protected offline suites passing, five scientific roles, 15 candidate/abstain cases and zero model/GPU calls. The independent local rerun reproduced the same graph and source-metadata hashes.

The original FW00411 refusal occurred before tests because its qualifier expected a stale inherited Git blob. [Correction `8f9907e7f6b5c4f639123ff1e8b8fe629b8d0308`](https://github.com/ctmansfield/production-framework/commit/8f9907e7f6b5c4f639123ff1e8b8fe629b8d0308) pins actual blob `521261fe0a8f9ba09f152f95319d705283d9aba7` while preserving source verification. It does not retroactively pass the refused attempt. The standalone correction's two checkout-specific regression tests are included in the host handoff, not in this session's 294-test count.

| Current local suite | Tests | Result |
|---|---:|---|
| FW00410 scientific graph/ledger | 59 | PASS |
| FW00411 original Scout source | 50 | PASS |
| FW00412 proposal broker | 70 | PASS |
| FW00413 corrected behavior screen | 46 | PASS |
| FW00414 corrected article library | 69 | PASS |
| Total | 294 | PASS |

Both corrections applied successfully to fresh isolated baseline copies. Installed bytes matched the intended source, checksums passed, and the corrected tests passed after application. The original behavioral 38-test and library 39-test baselines also passed before correction; those repeated baseline runs are not added to the total above. Full source/installation/read-back evidence is in FINAL-VERIFICATION.json.

## Behavioral next round

[Draft PR #148](https://github.com/ctmansfield/production-framework/pull/148) now points to [`7666e95f7d9b761515496141bf5e6fd647b6f82e`](https://github.com/ctmansfield/production-framework/commit/7666e95f7d9b761515496141bf5e6fd647b6f82e). Eight changed files were individually read back and matched.

The review reproduced a pooled association of +0.904762 while both individual participants had -1 associations. A second fixture produced +1 despite no within-person variation. The correction reports each participant separately and no pooled scalar, holds trait predictors and outcomes, and holds both endpoints of an explicit contradiction. It preserves the published single-participant result and records insufficient individual samples separately.

BEHAVIORAL-NEXT-ROUND.md develops six proposed responsibilities: construct/measurement, state/context, learning/decision, dynamic quantitative analysis, behavioral strategy/experiment design, and psychophysiology/host feedback. A proposed 24-case role pack precedes four integrated episodes and restart/successor continuity checks. These are proposed model tests, not already-run model evaluations. Recommendations, acknowledgments, actions, behavioral outcomes and physiological outcomes remain distinct records. State, trait, latent construct, measurement, source timing, context and bidirectional mechanistic feedback remain distinct.

## E1 local literature trial

[Draft PR #149](https://github.com/ctmansfield/production-framework/pull/149) now points to [`a5c946c858081470aa59dfb9e00f1cf88559b524`](https://github.com/ctmansfield/production-framework/commit/a5c946c858081470aa59dfb9e00f1cf88559b524). Eleven changed files were individually read back and matched.

The seed was compared against all 27 numbered references in the original Draft 0.2: 25 journal entries, one preprint and one dataset, containing 25 DOIs and 23 PMIDs. All supplied identifiers and normalized titles match that document. Two source PMCIDs omitted from the original fixture are preserved in a supplementary binding. The original DOCX SHA-256 is `4ab9d95e44a728b995d63d9c270d83fab44bcf5018b795e40cec25c9db4192a8`. This verifies bibliography coverage for that draft, not every article ever associated with E1 or the current provider's records.

The intended repository is `/mnt/nas_storage/research/e1-literature`. The trial verifies the NAS mount and connectivity before initialization, cross-checks source identifiers/titles, preserves bounded raw metadata and provenance, validates main-article JATS and a nonempty body, archives eligible OA XML, and reconciles manually imported PDFs by reference assignment and hash. It stops on a network failure and retains explicit, hash-linked retry history.

| Queue | Meaning |
|---|---|
| Main access CSV | Provider reports non-OA; candidate for university download |
| Review CSV | Unchecked entries, identity/title/license/content/integrity questions |
| Retry CSV | Observed connectivity failure |
| OA-pending CSV | OA verified but full-text acquisition not yet requested |
| Dataset CSV | Related data, separate from journal articles |

Imported PDFs are operator-associated with an article; framing/hash validation does not independently establish bibliographic identity. Valid local XML/PDF copies clear pending requests. This version downloads permitted XML automatically and imports PDFs; an automated PDF/media adapter remains future work. Europe PMC describes supported REST/OAI/bulk retrieval in its [developer resources](https://dev.europepmc.org/developers) and [copyright guidance](https://dev.europepmc.org/Copyright). A future PDF adapter should use current supported [PMC Cloud interfaces](https://pmc.ncbi.nlm.nih.gov/tools/cloud), including article-level rights and version metadata.

**Observed acquisition result here: zero downloaded articles.** The exact-ID Europe PMC metadata probe timed out; it created no archive attempts. The actual university download list therefore remains undetermined. E1-LIBRARY-TRIAL.md contains the verified host commands; successful processing must be assessed from actual acquisition/queue counts, not just exit code 0. E1 remains the project's foundational working premise; downstream evidence retains its own context and uncertainty.

## Host handoff

HOST-HANDOFF.sh creates a new source checkout with three detached worktrees, verifies exact commits and package manifests, runs the source suites and separate Scout pin regressions, and saves logs under a new `~/fw-next-round.*` directory. Existing worktrees and services are not edited. With `--run-e1`, it then runs the bounded 27-reference library trial on the mounted NAS. It sends no issue comments and runs no model inference. This wrapper's Bash syntax was checked here; actual host execution is pending.

The scientific live run remains a separate 15-case trial using an explicitly supplied installed-model roster and the already qualified FW00412 source. See SCIENTIFIC-TRIAL-RUNBOOK.md. The present session did not observe the current host model inventory or GPU state.

## Release and continuation record

The source patches, release notes, verification evidence and this design record are ready for review. Both production-framework PRs remain drafts and unmerged. This MOTHER snapshot preserves the report, runbooks and source-bound context; it does not deploy software. The current task's canonical source request and measured evidence are retained under context/evidence, with the initial local projection preserved as r1 and the reconciled continuation in r2.

Next evidence: the host helper's CPU result and E1 acquisition receipt; the existing coding summary's review/QA denominators; then a frozen scientific-role roster and the behavioral benchmark. No article availability, real-person psychological inference or scientific causal conclusion is inferred from the software tests.
