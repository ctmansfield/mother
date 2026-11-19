# Behavioral / psychological stack — next-round draft

Date: 2026-11-19. Baseline: FW00413 `8fe26e762f33315d18a167f703688ef13feb9474`.

Status: source design plus a locally tested correction to the synthetic screen. The role architecture and later statistical/behavioral experiments below remain proposed. They are not runtime capabilities or tested psychological models.

## 1. What exists, and what this round should establish

FW0043 defines Behavioral COACH, its scoped identity, a broker-planned capability request, and a hypothesis that separately names behavioral and physiological endpoints. FW0046 provides Host-Response context, receptor dynamics, conditional mechanism edges, provenance, and reviewer receipts. FW00413 is the first small executable screen: a synthetic participant fixture, exact-lag/context matching, descriptive associations, and refusal/hold behavior.

The baseline's 38 tests pass, but a statistical counterexample exposes a missing requirement: matched observations are paired within participant and then pooled across participants. Pairing correctly does not make the pooled coefficient a within-person estimate. A valid two-participant example with no change within either person returns `r=1`; a second example returns positive pooled `r=0.904762` while both participants have `r=-1`. The correction keeps every participant's association separate and leaves population estimation to a specified later model.

The next round should establish three things in order: correct evidence semantics; specialist ability on controlled behavioral tasks; then repeatable integrated episodes. It should not import the coding stack's rank order as a behavioral model assignment.

## 2. Coordination and role boundaries

MOTHER routes cross-stack work, resource budgets, version bindings and durable experience. Behavioral COACH owns the behavioral question, candidate synthesis and unresolved alternatives. Scientific COACH supplies source interpretation, Quantitative COACH supplies estimators, and Host-Response COACH integrates physiological mechanisms. These are logical responsibilities; a qualified model may serve more than one role with separately measured performance.

| Proposed responsibility | Input | Required output | First discriminating test |
|---|---|---|---|
| Construct and measurement | Scale definition, items, units, sampling protocol, measurement provenance | Observable versus latent construct; reliability/validity limits; incompatible measures; unknowns | Two differently named scales measure the same construct, or similarly named scores measure different constructs |
| State and context | Time-stamped behavior, self-report, sleep/circadian/environment context | State hypotheses, baseline-relative changes, alternative contexts and valid time windows | A temporary sleep/circadian shift must not become a stable trait |
| Learning and decision | Choices, available alternatives, rewards, costs, task history | Competing learning/decision models and distinct out-of-sample predictions | Habit, altered reward value and practical constraints produce the same observed choice |
| Dynamic quantitative analysis | Frozen observation snapshot and preregistered estimand | Per-person effects/associations, uncertainty, diagnostics, exclusions and estimator failure | Within-person and between-person effects have opposite signs |
| Behavioral strategy and experiment design | Goal, constraints, previous offers/actions/outcomes | A reviewable intervention hypothesis, comparison, behavioral endpoint and separate physiological endpoint | Acknowledging a recommendation must not count as performing it or improving physiology |
| Psychophysiology and host feedback | Behavioral candidates plus mechanistic and physiological evidence | Directed, conditional mechanisms with tissue/cell, timing and evidence gaps | Physiological change precedes behavior; the system must preserve reverse direction and shared causes |

Each result is reviewed by two independent qualified reviewers with blind initial judgments, followed by QA reconciliation. Agreement is not source evidence. Record disagreement, missing expertise and unresolved tests explicitly. No model is assigned to a role until its frozen behavioral benchmark is evaluated.

## 3. Represent observations before interpreting them

Keep the following channels distinct:

1. **Trait measurement or trait assumption:** instrument/version, source, assessment time, expected stability, uncertainty and the population in which the instrument was evaluated. This is a different estimand from a short-term state change.
2. **Latent state hypothesis:** affect, motivation, cognitive load or arousal inferred from specified observables. It is not a measurement simply because a model supplies a label.
3. **Subjective report:** exact instrument or question, response scale, reporter and time. A self-report is an observation of a report; its relation to a latent construct requires evidence.
4. **Observed behavior:** recorded action, task performance, timestamp and collection method. Missing observation does not automatically mean no action occurred.
5. **Physiological measurement:** measurement method, unit, quality, context and time. Keep each measured channel separate from predicted physiological states.
6. **Context and exposure:** environment, sleep, diet, inflammation, medications/exposures when available and authorized, social/task constraints, circadian phase, microbial context and relevant time windows.
7. **Offer, acknowledgment, action and outcome:** independent event records. Acknowledgment is not adherence; adherence is not benefit. Behavioral and physiological outcomes need independent measurements.

Proposed observation records extend the current synthetic schema with `observed_at`, `available_at`, `recorded_at`, source revision, method version, uncertainty, missingness reason, and measured/derived/imputed/inferred status. Forecast features use only information available at the prediction boundary. Keep late corrections as revisions, not edits to past knowledge.

For every candidate, declare the target quantity before estimation: within-person association, between-person association, forecast performance, intervention effect or mechanistic dependency. The same dataset can support different targets; a coefficient is uninterpretable without its target and conditioning choices.

## 4. Temporal and mechanistic hypothesis contract

A hypothesis should bind an immutable input snapshot, predictor, endpoint, participant/episode scope, predeclared lag/window, comparator, context variables and why they are included, candidate mechanism, expected direction, alternatives, exclusions and numerical method/version. Include source identifiers and spans, contradiction references and the exact result that would distinguish competing hypotheses.

Condition matching means selecting comparable records. It is not automatically adjustment for confounding. Some variables may be confounders, mediators, effect modifiers or consequences of the outcome; indiscriminately matching all available context can change the question or introduce selection bias. The first implementation should state the matching rule and preserve exclusions; causal models belong in separately evaluated extensions.

Bidirectional host connections are first-class hypotheses. Examples to test synthetically include behavior→autonomic response, prior physiological state→subsequent behavior, and an unobserved/common exposure→both. These are competing model structures, not established biological claims in this draft.

Where the mechanistic graph reaches receptors, retain ligand provenance, tissue/cell expression, occupancy/competition, agonism/antagonism/bias, desensitization/internalization/recycling, inflammatory/circadian state and feedback. Do not collapse ligand abundance, receptor engagement, intracellular signaling and functional response into one endpoint. Use FW0046's existing contracts and E1's source-backed edges rather than creating a separate untraceable mechanism narrative.

## 5. Test packs and acceptance criteria

### Gate A — deterministic evidence handling

The correction in this package addresses the first four rows. The remaining rows are planned, not reported as passing.

| Case | Required behavior | State after this review |
|---|---|---|
| Between-person offsets with zero within-person variance | Hold each participant; no aggregate correlation | Added regression passes locally |
| Simpson reversal | Preserve each negative association; do not emit misleading positive pooled scalar | Added regression passes locally |
| Individually insufficient samples, sufficient total count | Hold individuals; pooled counts cannot create eligibility | Added regression passes locally |
| Trait at either endpoint; one-sided declared contradiction | Hold trait temporal analysis; hold both conflict endpoints with sources retained | Added regressions pass locally |
| Exact-lag versus neighboring time | Use only predeclared matches; report unmatched data and window assumptions | Original exact-match implementation; fuller boundary tests proposed |
| Identical pair counts with serial correlation or missingness | Distinguish effective information and missingness mechanism; do not claim power from count alone | Proposed estimator/diagnostic tests |
| Measurement method/unit or scale changes | Refuse silent combination; preserve method and scale versions | Proposed |
| Late-arriving data/revisions | No future information in historical forecast or model selection | Proposed |
| Context selection and mediator adjustment | Report the target changed by conditioning; preserve competing explanations | Proposed |

### Gate B — specialist ability before assignment

Freeze an initial 24-case behavioral pack: four cases for each of the six responsibilities in Section 2. Within each group, include a straightforward supported case, a relevant-context change, conflicting evidence, and insufficient information. Use synthetic records or verified public literature extracts with exact source spans. Keep a separate held-out pack; do not tune the final rubric after seeing model results.

Score evidence grounding, correct construct/state distinctions, timing, estimator choice, uncertainty calibration, alternative explanations, and whether the proposed experiment separates those alternatives. Report dimension-level scores and failures; an average score must not hide fabricated evidence or a consistent trait/state error. Compare each model against deterministic controls and a transparent baseline. Repeat model calls under recorded seed/settings to measure variability rather than treating one answer as a stable capability.

Record model/weights digest, wrapper version, prompt and input hashes, context budget, seed if supported, latency/resource use, output and reviewer versions. The choice of models and number of repetitions remain an operator-reviewed benchmark configuration, not a model assignment in this draft.

### Gate C — integrated episode and continuity

Use four complete synthetic episodes: response with matching physiology, behavior change without physiological change, physiological change without behavior change, and a prediction failure with a competing explanation. Keep recommendations, acknowledgments, actions and observations separate throughout each episode.

Restart the process and substitute the specialist model version while retaining specialist identity. Verify that source lineage, failed predictions, contradictory outcomes and lessons survive; the new model must retrieve the relevant lesson without copying an unsupported conclusion as fact. Evaluate retained lessons on held-out contexts. MOTHER retains specialist experience; replacement does not erase failure history or automatically promote its content.

Completion of these gates qualifies the measured tasks and tested scope only. Real longitudinal data requires its own authorized data contract and evaluation; interventions require a separate protocol appropriate to the actual study. The present code still accepts synthetic data only.

## 6. Immediate execution order

1. Apply the minimal statistical correction in an isolated source checkout, verify package checksums and run all 46 tests plus the published single-participant CLI fixture.
2. Freeze input/output contracts and add the remaining Gate A cases before extending estimators. Choose per-person, hierarchical or state-space methods according to the declared target; do not add them simply to produce a population score.
3. Prepare the 24-case role pack with protected answers/rubrics, exact source spans and a held-out split. Reuse the scientific broker's bounded inference and receipt pattern only after compatible contracts are verified.
4. Run role comparisons on the host with pinned models and resource budgets, then review discrepancies and select provisional assignments by responsibility.
5. Execute the four integrated episodes and continuity tests. Persist all failures and revisions with the next release notes.

## Source anchors

- [FW00413 issue #144](https://github.com/ctmansfield/production-framework/issues/144) and [pinned handoff](https://github.com/ctmansfield/production-framework/issues/144#issuecomment-7010577867): original scope, 38 local tests and pending host qualification.
- [FW00413 baseline code](https://github.com/ctmansfield/production-framework/blob/8fe26e762f33315d18a167f703688ef13feb9474/packages/fw00413/behavioral.py): original pairing, pooling, trait and conflict behavior.
- [FW0043 behavior contract](https://github.com/ctmansfield/production-framework/blob/8fe26e762f33315d18a167f703688ef13feb9474/packages/fw0043/behavior.py): states/traits and independent behavioral/physiological endpoints.
- [FW0043 stack boundaries](https://github.com/ctmansfield/production-framework/blob/8fe26e762f33315d18a167f703688ef13feb9474/packages/fw0043/README.md): scientific/behavioral coordinators, scoped identity, broker and independent reviews.
- [FW0046 host-response contracts](https://github.com/ctmansfield/production-framework/blob/8fe26e762f33315d18a167f703688ef13feb9474/packages/fw0046/contracts.py) and [memory contract](https://github.com/ctmansfield/production-framework/blob/8fe26e762f33315d18a167f703688ef13feb9474/packages/fw0046/memory_contract.md): mechanistic context, receptor dynamics, feedback and durable episode/model lineage.
