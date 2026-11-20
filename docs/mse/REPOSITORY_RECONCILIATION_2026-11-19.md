# Repository and evidence reconciliation — 19 November 2026, Pacific/Guam

**Purpose:** preserve the November 13 MSE audit as a historical record, identify subsequent source/coordination changes, and explain what this publication does and does not establish. Companion: [integration addendum](INTEGRATION_ADDENDUM_2026-11-19.md).

**Review interval:** 18 November 2026 UTC / 19 November Pacific/Guam. Evidence is current GitHub source/ref reads, the existing source audit and original synthetic release artifacts. No current NAS/VPS/phone, device, private physiological dataset or scientific-model runtime was inspected for this reconciliation.

## 1. Publication versus prior preservation

The original MSE package is preserved at [`research/mse/reference-v0.1.0/`](../../research/mse/reference-v0.1.0/), including its [A–I report](../../research/mse/reference-v0.1.0/docs/MSE_ARCHITECTURE.md), supporting audits, draft contracts, proposed SQL, prototype, synthetic fixtures, verification records and patches. Its original release notes correctly describe its **then-current** uncommitted/unpushed/undeployed status. This publication records a later preservation step; it does not rewrite those historical statements.

Before this publication, the complete package was not found in the checked current MOTHER, Bridge, COACH or production-framework trees. The [PF hub coordination review](https://github.com/ctmansfield/production-framework/issues/42#issuecomment-6857111350) and [GADGET pointer](https://github.com/ctmansfield/production-framework/issues/49#issuecomment-6857118978) preserved a coordination report, not the complete source/design bundle. Some newer related scientific-specialty designs were committed separately. A comment, source commit, draft PR, merged main, deployed service and runtime observation remain separate states.

The [import report](IMPORT_REPORT_2026-11-19.md) is the publication-specific record for copied artifacts, integrity, checks and resulting publication status. This reconciliation does not invent a future commit SHA or claim a PR merged. The new addendum is a design update, not a change to the reference implementation.

## 2. Pinned source inventory

| Repository / ref at review | Exact commit | Relevance and qualification |
|---|---|---|
| MOTHER main | `818426fe90fab1bfd9583640363d4001b30e633f` | Publication base; context workflow added since original audited main |
| MOTHER PF001 | `5a6f71a45dc64880bc06a0e1a50c7d05ff119cba` | Existing physiological archive, revisions, imports and evaluation; separate feature line |
| MOTHER latest inspected I01 | `81c3fcceadcf5bf7462bf813427b98e4f87721e0` | Offline event/receipt and read-only reconciliation source |
| Bridge main | `1dfced17a1ef88b0e3fa23f5bd3341dc179a618b` | Context workflow added; original main collector source unchanged by that comparison |
| Bridge SQLite feature | `b2baa2e6bd2d018b6e34a07c783b7c3523366374` | Original audited diagnostic/migration/synthetic authority work |
| Bridge glucose-read feature | `e84a848796689b9bcb247a57024bc9f8d6e576c1` | Original audited authenticated read/display client |
| Bridge foreground source preservation | `65e67f5d73ad1bc7011579947972c394d68e09da` | Additional source on `oraclev2/foreground-source-preserve-20261117`; limited inspection, not a full new app audit |
| COACH main | `e5c257f234fe42c4d3d62827dc42972fdceb682f` | Includes context workflow adoption, not merged PF001/I01 or an MSE service |
| COACH latest inspected I01 | `184606fe9d5022997f09a2e4d6ef38e5dca4a9bc` | Offline capture/outbox/delivery viewer source remains on its feature line |
| Production Framework main | `bbe7344b22b0144ddebb6db8462c282f657ebe08` | Coordination/context source; separate from experimental scientific branches |
| PF knowledge/provenance feature | `4798adfb24d9babbd1e862f28480d3d4157392a4` | Scientific federation, memory, model registry and host-response design/source inspected |
| PF federation vertical-slice feature | `588ea8ca2068013967aa5997dca8102604ddba94` | FW-004.5–004.8 candidate contracts and experimental FW-004.9 seed/package inspected |

Current refs were read for this publication; they are not promises that branches will remain at these SHAs. Use the pinned links below to reproduce the source assessment.

### Main-code continuity

The [MOTHER comparison](https://github.com/ctmansfield/mother/compare/e4510efbb05f711f7fdc47fbab0fd6c19e8324fd...818426fe90fab1bfd9583640363d4001b30e633f) contains context-reader/policy/hook/fixture/test additions and its changelog entry; it does not change the previously audited physiological or legacy prediction implementation. The [Bridge comparison](https://github.com/ctmansfield/mother-health-bridge/compare/32aa85ef756186c64e7b747780d522e2e65156d3...1dfced17a1ef88b0e3fa23f5bd3341dc179a618b) likewise adds context workflow files rather than altering the main collector.

Consequently, the original source-level findings about main's HR/SDNN JSON acquisition remain applicable to those unchanged files. This does **not** identify the exact installed app, claim that no later device work occurred, or transfer feature-branch qualifications into main. The newer [foreground inbox source](https://github.com/ctmansfield/mother-health-bridge/tree/65e67f5d73ad1bc7011579947972c394d68e09da/MotherHealthBridge) adds an additional source-preservation record. Its message checkpoint and alert-submission semantics must not be treated as physiological acquisition completeness or a verified intervention exposure.

## 3. What the newer scientific framework contributes

The committed [scientific architecture](https://github.com/ctmansfield/production-framework/blob/4798adfb24d9babbd1e862f28480d3d4157392a4/docs/mother-coach/FW004_SCIENTIFIC_COACH_ARCHITECTURE.md), [federation design](https://github.com/ctmansfield/production-framework/blob/4798adfb24d9babbd1e862f28480d3d4157392a4/docs/mother-coach/FW004_FEDERATED_SPECIALTY_STACKS.md) and [memory/interface design](https://github.com/ctmansfield/production-framework/blob/4798adfb24d9babbd1e862f28480d3d4157392a4/docs/mother-coach/FW004_SPECIALIST_MEMORY_AND_INTERFACES.md) are related later work, not replacements for the MSE package.

| Inspected source | Existing contribution | Gap before MSE integration |
|---|---|---|
| `packages/fw0045/contracts.py` | Series hash/units/missingness, candidate forecast and verification metadata | Revision-aware intervals, authoritative availability, coverage and source qualification |
| `packages/fw0046/contracts.py` | Biological/receptor context, proposed mechanism edges, host-response task/result distinctions | MSE snapshot bindings, typed conditional hyperedges, mechanistic observability and calibrated state inference |
| `packages/fw0047/contracts.py` | Source/claim/evidence relations, contradictions and review objects | Stable mechanism revisions/bundles, joint conditions and evidence-grade/applicability mapping |
| `packages/fw0048/contracts.py` | Typed federation request/result, evidence references, resource budget and candidate review references | Versioned validated adapter, consistent enums, authorization/source scope and missing-dependency semantics |
| `packages/fw0049/README.md` and `seed/` | Source-owned experimental synthetic federation/recovery/receipt assignment | Does not establish deployed physiological federation, live scientific inference or an MSE implementation |

Those contract files describe themselves as draft/untested at the inspected pin. That is a statement about these source artifacts, not a claim that no later framework trial or report exists. No trial was rerun here. In particular, an incomplete seed and its intended protected tests are not the completed product of a live coding mission. Any later result needs its own exact output revision and evidence scope.

The addendum therefore specifies an adapter boundary and compatibility tests. It does not import an evolving private experimental package into the public MOTHER inference runtime.

## 4. Dataset, source and model availability

| Item | What is established for this publication | What remains unestablished here |
|---|---|---|
| Reference HR/SDNN fixtures | Synthetic HealthArchive input and deterministic reference outputs exist in the preserved package | Personal predictive performance, sensor error calibration, causal or clinical validity |
| Captured HealthArchive importer | Source mapping exists for the archive fields preserved by the Swift bridge | Fields never archived, current personal dataset availability, device identity or complete HealthKit history |
| PF001 import boundaries | Previously inspected Apple XML, TCX HR, manual spot CSV and capability-gated Nightscout import source remains at the pinned feature commit | A new working device adapter, a current live dataset, permission scope or operational completeness merely from accepted channel names |
| N3 glucose | Historical coordination records identify a contract/server pin and bounded snapshot acceptance | Exact current serving source/deployment, rolling completeness, live authority or a newly qualified PF001/N3-to-MSE adapter |
| Additional physiology | Proposed source contracts and explicit missing states | Working CPAP, raw ECG/RR, Omron Bluetooth, microbial flux, receptor-state or broad laboratory integrations unless separately qualified |
| Scientific model catalog | A design inventory names retrieval, language, numerical-forecasting and molecular engines and records historical installation observations | Current weights/digests, successful runtime inference, task validation, calibrated uncertainty or active MSE use |

The [model registry](https://github.com/ctmansfield/production-framework/blob/4798adfb24d9babbd1e862f28480d3d4157392a4/docs/mother-coach/FW004_MODEL_CAPABILITY_REGISTRY.md) explicitly differentiates listed assets, imported environments, weights present, inference verified, task validated and active. It reports historical MedCPT/TxGemma/Boltz/TimesFM and other candidate assets with unresolved runtime qualifications. This reconciliation reproduces no host paths or access commands and performs no model/weight probe. A catalog entry is not a live capability advertisement.

The reference OU model has executable software evidence; it has no validated endocrine, immune, substrate-oxidation, mitochondrial or microbial interpretation. A future generic forecaster predicting glucose more accurately would still need an independently justified biological observation model before its hidden state could receive those names.

## 5. Coordination chronology and remaining holds

The November 13 audit is intentionally time-bounded. Subsequent owning records contain historical foreground/uploader acceptance, independent cleanup and successor-intake receipts. The [ORACLE succession closeout](https://github.com/ctmansfield/production-framework/issues/42#issuecomment-6907820371) preserves those completed historical results while explicitly separating them from new runtime activity. Do not relabel closed historical tests as missing; also do not relabel them as current source, phone or server observations.

The [Phase 1 reconciliation](https://github.com/ctmansfield/production-framework/issues/42#issuecomment-6908655745) accepts documentation consolidation while leaving live authority closed and NAS glucose parked. Later [context-adoption closeout](https://github.com/ctmansfield/production-framework/issues/42#issuecomment-6909779598) concerns context/workflow preservation. ACKs, context hashes and successful reader tests are not fresh physiological coverage or production qualification.

**Current planning correction:** earlier recommendations to perform a next live N3/CGM probe are historical suggestions, not an active task. The parked NAS-glucose disposition controls until the owning phase explicitly changes it. The present user authorization concerns saving the MSE prototype, documents, findings and design updates to a reviewable MOTHER branch/PR; it does not reopen source acquisition, model/weight activation, HealthKit authority cutover, phone operations or deployment. Research Scout and Meta-Research schedules are unaffected.

Historical N3 window counts and page acceptance refer to their pinned evidence snapshot. They do not demonstrate today's freshness, generalized pagination/tie safety, correction/deletion completeness or sustained rolling ingestion. The status-permission repair reported in earlier Nightscout coordination concerns scope reporting; it cannot stand in for those source properties. No current host result was produced in this publication review.

## 6. Evidence, verification and handoff limits

For this reconciliation, the reviewer read the staged Mother `AGENTS.md` and context-v1 policy and ran the project reader. It returned `UNSEEDED`; no task, ACK or runtime authority was invented from that result. The current user instruction supplies this publication's scope. Root publication work records its own source-bound report and context handoff.

Source checks performed here were bounded GitHub reads of current refs/trees/PRs, exact main comparisons, the necessary PF owning dispositions, specialist design/contracts and limited preserved foreground source. This was not a fresh infrastructure, security or scientific-validation audit. No source importer, Swift suite, device acquisition, NAS/VPS endpoint or scientific model was run by this reviewer.

The original [verification record](../../research/mse/reference-v0.1.0/verification/VERIFICATION.md) retains the historical 56-test reference package result, 25 draft-contract checks, seven proposed-SQL checks and earlier MOTHER evaluation evidence with their boundaries. Current publication reruns, if performed, are recorded separately in the import/verification report; neither set proves human metabolic validity. Original failed probes and corrected risks remain preserved.

### Next bounded engineering work

1. Review and preserve this publication with its exact artifact fingerprints and explicit source/runtime distinctions.
2. Choose the PF001/I01 integration base and define a read-only captured-source adapter, including revision, clock, normalized-unit and loss/unknown mappings.
3. Implement snapshot/coverage and per-decision availability replay tests using synthetic or separately authorized captured inputs.
4. Add context and a small MSE/federation adapter only after source contracts are qualified. Keep live CGM work parked until its separate disposition changes.
5. Evaluate individual prediction and eventual causal hypotheses through the original validation ladder; do not promote mechanistic precision because a schema or workflow test passes.

These are proposed follow-on increments, not implemented adapters or queued runtime commands. The [integration addendum](INTEGRATION_ADDENDUM_2026-11-19.md) supplies the detailed candidate contracts and successor-memory requirements.
