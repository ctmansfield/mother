# MSE integration addendum — 19 November 2026, Pacific/Guam

**Status:** proposed integration design, published alongside the preserved MSE-001 reference release. The contracts below are not implemented physiological adapters, new server endpoints, source qualifications or permission to operate a held system.

**Companion records:** [repository reconciliation](REPOSITORY_RECONCILIATION_2026-11-19.md), [original A–I architecture](../../research/mse/reference-v0.1.0/docs/MSE_ARCHITECTURE.md), [reference implementation](../../research/mse/reference-v0.1.0/prototype/README.md), and [publication import report](IMPORT_REPORT_2026-11-19.md).

## 1. Integration decision

Keep the Metabolic State Engine as a bounded physiological inference component of MOTHER. A specialist federation can supply evidence review, numerical forecasts, mechanistic hypotheses and experiment analysis through versioned interfaces. It must not turn a language model, molecular predictor or literature retrieval result into an authoritative physiological measurement.

The newer framework defines separate scientific, quantitative, behavioral, psychophysiological and knowledge/provenance specialties with persistent identities. Its inspected design and source are useful integration targets, but they are not a deployed MSE. The quantitative contract has a series identity, data hash, units and missingness; the host-response contract separates observations, receptor context and proposed mechanisms; the provenance contract distinguishes support, contradiction and supersession. The federation contract binds request, task, inputs, evidence and review receipts. None of these fields alone supplies the full temporal, revision and source-qualification contract required below. [F1–F6]

The original reference package remains a retrospective scalar HR/log-SDNN deviation model, with illustrative parameters, explicit unknown biochemical dimensions and uncalibrated intervals. Its native glucose envelope is a synthetic/export contract. It does not contain a qualified PF001 or N3 export adapter, fitted circadian/context model, live service, graph execution engine or intervention evaluator. This addendum does not change that code or its result semantics.

## 2. Ownership and permitted information flow

| Component | Owns | Integration boundary |
|---|---|---|
| Acquisition adapters and durable buffers | Received sensor records, source deletions, acquisition checkpoints | Continue existing acquisition independently of inference availability |
| MOTHER evidence archive | Original artifacts, source revisions, authoritative commitment and authorized current projections | Issue immutable, explicitly scoped evidence snapshots |
| MSE | Features, model-conditioned states, uncertainty, abstention and replay lineage | Read snapshots; write a separate derived namespace |
| Quantitative specialty | Candidate forecasts, baseline comparisons and calibration evaluations | Return predictions bound to the exact supplied snapshot and target definition |
| Scientific / psychophysiology specialties | Mechanism candidates and discriminating explanations | Return scoped hypotheses, evidence and missing prerequisites |
| Knowledge/provenance specialty | Source attribution, claim relationships, contradictions and review history | Publish reviewed immutable mechanism bundles; do not edit running-model assumptions |
| Behavioral COACH / interaction COACH | Observation requests, voluntary experiment coordination and factual response capture | Keep plans, acknowledgments, actual exposures and outcomes separate |
| Trusted memory steward | Access scope, append-only evidence history, checkpoint and successor continuity | Prevent a candidate model from promoting its own claims or copying personal evidence into shared memory |

MOTHER orchestrates a dependency graph, not a forced consensus. Conflicting forecasts or mechanisms remain separate candidates. An unavailable specialist must produce a typed unavailable result without blocking already supported read-only replay. A response may say that the observed trajectory changed while every proposed biochemical explanation remains unidentified.

Existing COACH/I01 factual events and receipts are reusable source interfaces. Existing read/display and foreground-message code do not automatically constitute an MSE state consumer. The proposed `/v1/mse` reads in the original architecture remain proposed routes. Authenticated message delivery, an alert submission and a physiological observation have different semantics. [R2–R4]

## 3. Proposed observation and revision contract

The following are **proposed fields and invariants**, not an assertion that existing PF001, HealthArchive, N3 or FW-004 schemas already accept them. A versioned adapter must publish explicit mappings, loss/unknown fields and qualification evidence before promotion.

| Object / field group | Required representation and meaning |
|---|---|
| Logical observation identity | Subject scope, source system, source-instance namespace and native record identity; channel/type where required by that source's identity rules. Preserve original IDs in the protected archive; expose scoped references to consumers. |
| Revision identity | Immutable revision ID, canonical-content digest, predecessor/supersession links, operation (`upsert` or explicit source deletion), normalization version and authoritative commit reference. A correction creates a revision, not an overwrite. |
| Source evidence | Exact artifact digest, protected artifact handle, original record locator and parser/version. Preserve original bytes separately from canonical normalized content. A hash establishes byte identity, not sender authorization or scientific truth. |
| Measurement semantics | Channel, quantity definition, method, specimen/compartment if relevant, `instant` versus interval aggregate, start/end, acquisition-window definition, source/device/application/calibration identity, and their explicit unknowns. |
| Value and unit evidence | Original value spelling and unit; normalized value, unit system/code and conversion version; rounding/precision policy and uncertainty introduced by conversion. An absent calibration or measurement-error estimate stays unknown. |
| Epistemic class | Measured, vendor-derived, reported, computed feature, imputed, statistically inferred, simulated or clinical interpretation. Preserve the original source class and the adapter mapping. |
| Source quality | Source validity flags, parser findings, artifact suspicion, clock uncertainty, acquisition context and evidence for any excluded/downweighted value. Keep disagreement; do not silently clip unusual values into a normal range. |
| Relay lineage | Originating observation/revision and optional `same_origin_as` relationship with qualification evidence. Two archives relaying one sensor reading do not become independent corroboration. Unknown relay identity stays unresolved. |
| Access and publication scope | Owner-controlled subject/source scope, permitted purpose, view identity/generation and authorization reference. Credential contents never enter the observation or model manifest. |

Use an explicit decimal/rounding policy at the interchange boundary. Conversion from mg/dL to mmol/L changes representation, not biological meaning or compartment. SDNN cannot be converted to RMSSD, raw RR or a sympathetic/vagal fraction by changing a unit label. The current HealthArchive importer cannot recover device, calibration, metadata or source-version fields that the captured archive never stored.

### Three clocks and two forms of historical replay

Record at least:

- **Biological time:** measurement start/end and their precision or uncertainty.
- **Source availability:** when the originating source says the record became available, with definition and reliability; this can be unknown.
- **MOTHER availability:** first received and durably committed time/sequence at the authoritative archive, separately from source time and later revision time.

For a decision at time `t`, online eligibility requires the observation interval to be complete and the applicable revision to have been committed by that decision's knowledge cutoff. A later correction or deletion must not be treated as known at an earlier decision. Missing authoritative availability prevents a verified historical-online claim.

The reference implementation instead supports **retrospective snapshot replay**. Its optional global receipt cutoff selects one dataset; it does not recreate an independent historical knowledge set at every state time. Preserve its explicit historical-availability-false fields. Future sequential availability replay and retrospective smoothing must have distinct run modes and validation. A smoother may use later evidence, but cannot relabel its reconstruction as a contemporaneous forecast.

## 4. Anchors, watermarks, coverage and snapshots

These identities must remain separate:

| Progress identity | What it can establish | What it cannot establish |
|---|---|---|
| HealthKit anchor | An opaque continuation position for a specific query/store/scope and committed acquisition page | Ordered numerical time, complete permission, lifetime history or a transferable cursor for a different store |
| Source API cursor | Continuation under its documented query and snapshot contract | MOTHER durability or a general absence-of-records proof |
| Source availability watermark | A source-specific assertion about records available through a defined boundary | Completeness merely because a newest event timestamp exists |
| Archive commit watermark | Durable archive revision/receipt progress for the authorized source scope | Acquisition completeness or physiological stability |
| MSE processed watermark | Which committed snapshot/revisions a particular run processed | Coverage of missing input or qualification of an unobservable state |
| Foreground-message cursor | Message-delivery/checkpoint progress under that protocol | A HealthKit anchor, physiological measurement timestamp or verified intervention exposure |

A proposed `CoverageAssessment` should contain source/snapshot/view identity, channel, interval, expected cadence **only if justified**, observed valid support, known gaps, latest measurement age, ingestion delay, explicit correction/deletion capability, permission/scope limits, and a result such as `complete_under_contract`, `partial`, `unknown` or `unavailable`. The result must name the contract and evidence used. HealthKit's opportunistic SDNN collection is not automatically a fixed-cadence stream. An empty response is not proof that the person had no events or that all read permissions were granted.

A proposed `EvidenceSnapshot` binds an immutable manifest of observation revisions, tombstones and source artifacts to:

1. subject/source/channel scope and half-open measurement interval;
2. selected current-revision policy, knowledge cutoff and normalization version;
3. source snapshot/cursor identity and archive commit watermark;
4. access view identity/generation and a source-qualification receipt;
5. coverage assessment, canonical manifest digest and exact input-member digests.

Pagination must keep its source snapshot and view binding. Identity remapping, expiry, changed authorization generation or a cursor from another query invalidates accumulation. A separately requested coverage response can only be joined if its snapshot relation is established; otherwise retain its independent evaluation time and limitation. Repeated identical batch bytes preserve commitment identity; identical keys with different bytes are conflicts.

### Correction and invalidation

The proposed chain is: source correction/deletion → immutable revision and commitment → explicit snapshot change → dependency invalidation event → new feature/state run. Serving a current state must check validity, not simply select the newest stored numeric estimate. Preserve the previous state and its exact inputs for historical explanation. Source absence in a partial export never creates a deletion. No adapter may advance an acquisition checkpoint after failed or uncertain commitment.

## 5. State, specialist result and measurement-request contracts

A proposed `StateEstimate` carries target definition/version, subject scope, valid interval/reference time, epistemic class, snapshot and run identities, source support and exclusions, model/configuration/implementation hashes, optional mechanism-bundle hash, context, freshness and observability status. A numeric distribution may be absent. A numeric interval must identify its level, method, conditioning assumptions and calibration status.

Keep these distinct: measurement uncertainty; uncertainty in baseline/parameters; forecast or latent-state uncertainty conditional on a model; uncertainty over competing mechanisms; source coverage; and out-of-domain status. An uncalibrated Gaussian reference interval cannot resolve competing biochemical explanations. Supported unknown reasons include insufficient coverage/history, unknown context, invalid quality, unqualified source, out of domain, nonidentifiable mechanism, unavailable dependency and prior domination.

Map the MSE result into a **versioned federation adapter**; do not import experimental FW-004 code directly into production inference. Inspect the actual differences: FW-004.6 uses underscore evidence-status tokens, while FW-004.8 uses hyphenated tokens; their scope vocabularies also differ. A Python `Literal` annotation is not runtime input validation. The adapter needs explicit enum mappings, structural/semantic validation, unknown preservation and round-trip rejection tests. `observed` from a model-output record must not become a measured physiological observation. [F3–F6]

A proposed `MeasurementRequest` contains request/parent IDs, state and snapshot references, unresolved hypotheses including an unmodeled alternative, predicted distinctions, measurement or controlled-observation specification, timing/window, required capability, burden, prerequisites/exclusions, uncertainty, stop rule and returned-result linkage. Initially use inspectable rules. An information-gain score remains null unless a specified, calibrated model family supports its calculation.

For example, higher HR and lower vendor SDNN with unknown posture/activity can justify asking for that missing context and a comparable same-source observation. It cannot justify a quantified endocrine or inflammatory diagnosis. A request is not an order, a completed measurement or evidence that COACH can access a particular instrument.

## 6. Conditional E1 mechanism map and receptor state

E1 remains a fixed **working research premise**: industrialization-associated microbial ecological changes may create a mismatch in host biochemical support. Store its premise status, scope and rationale separately from the evidence grade of an individual causal claim.

Use a versioned claim graph with reified mechanisms/hyperedges for joint requirements. Stable local IDs and external identifiers identify concepts; immutable revisions identify assertions. Each mechanism binds typed participants, stoichiometry/compartments, substrate/cofactor and environmental conditions, temporal delay, parameter distributions or unknowns, evidence support/contradiction, and model applicability. Dietary versus host-derived substrates, microbial organisms/strains/genes, capability versus expressed activity, cross-feeding/competition/predation/phage events, metabolite pools, transport and host responses remain separate entities.

Evaluate required conditions with three-valued logic. Missing pH, receptor expression, strain function or compartment concentration is `unknown`, not a satisfied prerequisite. Conservation and thermodynamic feasibility constrain a hypothesis; they do not establish actual flux. A metabolite concentration cannot alone determine production, transport and consumption separately. See original architecture D for the proposed balances, evidence scheme and primary-source rationale.

Receptor binding, abundance, efficacy and trafficking require separate variables. For the **illustrative, single-site competitive-equilibrium template**:

\[
\theta_j=\frac{L_j/K_j}{1+\sum_k L_k/K_k},\qquad
S_p=\mathcal{G}_p\!\left(aR_s\sum_j\epsilon_{jp}\theta_j,c\right).
\]

Here `L` is local free ligand concentration, `K` is the appropriate assay-conditioned affinity, `R_s` is available surface receptor amount, `a` is a responsive fraction, and `epsilon` is pathway-specific efficacy. A separate trafficking template may use:

\[
\dot R_s=k_{syn}+k_{rec}R_i-k_{int}(\theta,c)R_s-k_{deg,s}R_s,
\quad
\dot R_i=k_{int}(\theta,c)R_s-(k_{rec}+k_{deg,i})R_i.
\]

These are proposed simulation templates, not fitted human receptor models or universally valid equations. Record units, assay/tissue/species, receptor variant, competition, signaling bias and the limits of equilibrium assumptions. RNA abundance is not automatically surface receptor amount. A model needs an explicit desensitization/recovery law if `a` varies.

In the original synthetic example, increasing `L/K` from 1 to 4 raises occupancy fraction from 0.5 to 0.8, while reducing `R_s` from 1 to 0.2 lowers occupied receptor amount from 0.5 to 0.16. The physiological signal therefore cannot be inferred from metabolite production alone. Neither receptor state nor microbial flux is identified by the reference HR/SDNN replay.

### Evidence and immutable bundles

Keep the original project A–D evidence grade, scope/applicability, evidence relation and workflow-review status as **different axes**. A schema check or two reviewer receipts can establish process compliance; they cannot manufacture a Grade A mechanism or a verified individual effect. Deduplicate underlying experiments/studies before counting support across retrieved summaries or model outputs.

The mutable research graph publishes a reviewed `MechanismBundle` containing exact claim/node/parameter revisions, included contradictions, eligibility predicates, evidence links, unit/identifier mappings, compiler/version and digest. MSE pins the bundle and permitted uses in a run. New graph findings create a new candidate bundle and, where appropriate, explicit validity events; they never rewrite historical runs. No natural-language claim becomes executable code or a treatment rule automatically.

## 7. Intervention hypotheses, exposures and outcomes

Keep separate IDs and contracts for:

- **InterventionHypothesis:** target-state definition, proposed mechanism, prerequisites/dependencies, expected direction and delay, measurable and adverse outcomes, confounders, supporting/contradictory evidence, individual history and exclusions.
- **EligibilityAssessment:** state/snapshot/bundle references, true/false/unknown predicates and missing evidence. Unknown required conditions block a positive recommendation.
- **ExperimentPlan and Assignment:** estimand, comparator, randomization/blocking, carryover, pre-exposure covariates, endpoints, analysis/stopping rules and assigned condition.
- **Exposure:** actual reported or observed action, time/amount uncertainty, source revision and adherence linkage. Acknowledgment remains acknowledgment.
- **ResponseObservation:** independently sourced outcome measurements or reports; missing outcomes remain missing.
- **CausalAnalysis and IndividualEffectClaim:** pinned data/plan/analysis versions, effect uncertainty, sensitivity, replication and contradictions, with a scoped validity claim.

Initial modes remain observation, hypothesis testing and simulation. Simulated exposure/response records occupy a distinct namespace and cannot enter the measured-outcome archive as actual events. No autonomous medication change, physiological dosing or medical-treatment actuator is introduced.

Within-person comparisons require comparable context and explicit time-varying confounders. Appropriate randomized repeated periods can strengthen an individual causal estimate; samples within one CGM episode are not independent experimental replicates. A reproducible endpoint effect still does not prove the proposed mediator. Preserve failed hypotheses and adverse responses in later selection and successor memory. The original architecture E/F/G supplies the N-of-1 example and scientific validation ladder.

## 8. Persistent identity and successor memory

The new federation's persistent specialist identity is compatible with MSE reproducibility if memory is treated as **versioned evidence and selection policy**, not as mutable hidden context. Stable `specialist_id` is separate from engine/model weights, adapter, retrieval index and inference process. Retain per-engine provenance and task-domain calibration; never treat changed retrieval context as neural-weight training. [F1–F2]

A proposed successor manifest contains predecessor/successor identities, authorized scope, exact model/adapter/configuration and graph bundles, evidence snapshot references, committed episode boundary, selector/index revisions, calibration/model cards, accepted and failed experiments, contradictions/retractions, invalidated states, unresolved observability gaps, outstanding holds and the last verified checkpoint. Raw personal evidence remains in its protected store; the shared scientific memory receives only authorized scoped claims and artifact references.

Separate memory namespaces for personal longitudinal observations, model-development experiments, curated public biological evidence and organizational workflow lessons. Retrieving a person's state must not automatically expose their source records to a general scientific-language engine. A successor cannot self-promote a candidate because its predecessor remembered it confidently.

Proposed continuity acceptance:

1. Same code/configuration/snapshot replay reproduces the declared output; a new engine is evaluated separately rather than forced to impersonate identical performance.
2. Restart and uncertain-commit recovery retain one experiment identity and all failure evidence.
3. Engine replacement preserves specialist identity, constraints, unknowns, calibration status and negative outcomes.
4. Relevant-context versus memory-disabled held-out comparisons test useful retrieval; unrelated or unauthorized context is withheld.
5. Retractions and source corrections propagate into current serving validity without erasing earlier explanations.
6. A successor with missing capability, missing input or unsupported calibration abstains explicitly.

Context-reader hashes and ACKs establish source binding or receipt, not scientific validity, deployment or fresh source availability. The current publication does not change worker schedules, model weights or runtime identities.

## 9. Bounded implementation sequence

| Order | Proposed increment | Acceptance required before claiming the increment exists |
|---|---|---|
| 0 | Preserve/reference the original offline package and publish this design | Exact artifact integrity, reviewable source/limits and reproducible synthetic checks |
| 1 | Read-only captured HealthArchive → selected PF001 evidence adapter | Epoch/unit/revision mapping, loss report, artifact preservation, tombstones, deduplication and no source writes |
| 2 | Snapshot/coverage/availability contracts and sequential replay | Correction/deletion and late-arrival cases; per-decision knowledge set; explicit source qualification and unknowns |
| 3 | Context events and fitted individual baseline | Qualified meal/activity/sleep context, source/window compatibility, held-out comparison and interval calibration |
| 4 | MSE ↔ federation candidate-result and measurement-request adapter | Scope/schema mapping, exact snapshot binding, unavailable/disagreement handling and no invented measured claims |
| 5 | Small immutable mechanism bundle and observation-only COACH workflow | Conditional predicates, contradiction retention, request/exposure/outcome separation and preserved successor memory |
| 6 | A prospectively specified individual experiment | Appropriate consent/context/design, independent endpoint measurements and separate causal/mechanistic validation |

The existing reference package can support synthetic/offline work immediately. **NAS glucose remains parked under the current owning disposition; publication does not reopen that work or authorize a live source qualification.** Qualified CGM becomes a future increment only after the owning source and runtime gates are explicitly resolved. Keep the original JSON collector and source authority until their separate owner accepts any cutover. No new always-on service, GPU dependency or graph database is required for these increments.

## Source locators

These are pinned source/design locators, not assertions about current host state. Some framework records require authorized access. No private physiological data or host access instructions are reproduced here.

- F1. [Federated specialty design](https://github.com/ctmansfield/production-framework/blob/4798adfb24d9babbd1e862f28480d3d4157392a4/docs/mother-coach/FW004_FEDERATED_SPECIALTY_STACKS.md).
- F2. [Scientific specialist memory/interface design](https://github.com/ctmansfield/production-framework/blob/4798adfb24d9babbd1e862f28480d3d4157392a4/docs/mother-coach/FW004_SPECIALIST_MEMORY_AND_INTERFACES.md).
- F3. [Quantitative contracts](https://github.com/ctmansfield/production-framework/blob/588ea8ca2068013967aa5997dca8102604ddba94/packages/fw0045/contracts.py).
- F4. [Host-response contracts](https://github.com/ctmansfield/production-framework/blob/588ea8ca2068013967aa5997dca8102604ddba94/packages/fw0046/contracts.py).
- F5. [Evidence/provenance contracts](https://github.com/ctmansfield/production-framework/blob/588ea8ca2068013967aa5997dca8102604ddba94/packages/fw0047/contracts.py).
- F6. [Federation request/result contracts](https://github.com/ctmansfield/production-framework/blob/588ea8ca2068013967aa5997dca8102604ddba94/packages/fw0048/contracts.py).
- R1. [PF001 physiological contract](https://github.com/ctmansfield/mother/blob/5a6f71a45dc64880bc06a0e1a50c7d05ff119cba/mother/physiology/schemas/v1.schema.json).
- R2. [MOTHER I01 physiology source](https://github.com/ctmansfield/mother/tree/81c3fcceadcf5bf7462bf813427b98e4f87721e0/mother/physiology).
- R3. [COACH I01 physiology source](https://github.com/ctmansfield/coach/tree/184606fe9d5022997f09a2e4d6ef38e5dca4a9bc/coach_app/physiology).
- R4. [Preserved foreground inbox source](https://github.com/ctmansfield/mother-health-bridge/blob/65e67f5d73ad1bc7011579947972c394d68e09da/MotherHealthBridge/ForegroundInboxCore.swift).
- R5. [Current documentary phase reconciliation and parked work](https://github.com/ctmansfield/production-framework/issues/42#issuecomment-6908655745); [successor closeout preserving historical receipts](https://github.com/ctmansfield/production-framework/issues/42#issuecomment-6907820371).

## Acquisition and storage requirements companion

[HealthBridge → MOTHER ingestion and storage requirements](HEALTH_DATA_INGESTION_REQUIREMENTS.md) extends this design with acquisition-side acceptance criteria and explicit deployment/storage decisions for joint review. It is proposed requirements, not implemented adapters, a production database choice or authorization to transfer personal data.
