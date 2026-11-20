# MSE scientific foundations and model guardrails

Research date: 2026-11-13 (Guam). Intermediate design notes for the principal architecture report. This is a proposed scientific design; it does not assert that any device, field, model, or service already exists in the repositories. No personal clinical conclusions are drawn. E1 remains the project's fixed research premise, with separate evidence records for testable downstream claims.

## 1. Recommendation constrained by observability

Start with a small, context-conditioned continuous-time state-space model of the signals actually present after repository audit. The first state should have operational semantics—e.g. a smoothed, individualized HR/SDNN deviation conditional on time of day and documented activity—not the name of an unmeasured hormone or biochemical lesion. A derived quantity becomes biologically interpretable only after its measurement model and distinguishing tests support that interpretation.

An observation in Level 1 means the output received from an instrument. It does not necessarily mean raw physical data: HealthKit HRV SDNN is already an algorithm-derived scalar. Preserve `measurement_method`, sample interval, unit, source, device, algorithm version when present, and acquisition context. Never invent raw RR intervals or compute RMSSD from SDNN or sparse average heart rate. Apple's official definition of HealthKit HRV is SDNN [S1]. Distinguish instrument-derived observations from MSE-derived features.

Suggested mathematical model for a bounded first slice:

\[
 dx(t) = [A_i x(t)+B_i u(t)+f_i(c(t))]dt + L_i dW(t),
\]

\[
 y_{j,k}=h_j(x(t_{j,k}-\tau_j),c(t_{j,k}),d_j)+b_{j,d_j}+\epsilon_{j,k}.
\]

Here `i` identifies the person, `j` the modality, `d` the device/method, `c` predeclared context, `u` recorded exposures, and `tau` a modality-specific observation delay (possibly uncertain). Use only rows of the measurement model corresponding to observations available at an event time. For linear Gaussian evolution, irregular transitions have `F(dt)=exp(A dt)` and `Q(dt)=integral_0^dt exp(A s) L L^T exp(A^T s) ds`. This handles elapsed time explicitly rather than treating five-minute and two-hour gaps alike. A scalar Ornstein–Uhlenbeck residual is a defensible prototype; promote dimensions only when data improve their identifiability. A robust Student-t observation likelihood or an explicit contamination mixture is a future extension; a simple prototype must label Gaussian assumptions.

Separate three uncertainties: instrument error; uncertainty in individual baseline and parameters; and ambiguity among mechanisms. A narrow filtered interval under one model is not evidence that other mechanisms are excluded. Record model-conditioned intervals and an identifiability/coverage status separately. Do not assign numeric mechanism probabilities unless the candidate likelihoods and priors have actually been specified and calibrated.

For personal baselines, use robust context-conditioned estimates with harmonic circadian terms, day effects and device strata. Require historical support for the context being compared; do not silently extrapolate a quiet morning baseline to exercise or fever. Use a frozen evaluation baseline plus a slowly adapting candidate baseline. A change detector can mark a regime transition; it must not immediately normalize away an emerging sustained change. Hierarchical priors can pool population information while retaining individual offsets and response kernels. Population coefficients are priors, not an individual's proven causal coefficients.

### Observability and unknown outputs

For a linear local model, inspect the rank and conditioning of an observability matrix/Gramian using the actual observation schedule. For nonlinear models, combine simulation-based state recovery, parameter sensitivity, posterior geometry, and profile likelihood [S4]. A variable is publishable only at the scope supported by its measurements. A prior-driven posterior must carry that label. Distinguish `not_measured`, `insufficient_coverage`, `artifact_suspected`, `out_of_domain`, `non_identifiable`, and `inferred_model_conditional`.

Missingness is often informative: sampling may depend on movement, user behavior, charging or sleep. Absence of an HRV observation is not zero HRV and not random by default. Track availability/coverage and inspect whether missingness predicts context/outcome. Never create implied evidence by forward filling a physiological variable across arbitrary gaps. Interpolation for a plotted line is distinct from inference and must retain its provenance.

### Why glucose alone cannot identify insulin action

An illustrative whole-body balance is

\[
V_G \dot G = R_{a,meal} + EGP - R_d - U_{renal}.
\]

Even perfect measurements of `G(t)` constrain a net balance. Increasing `EGP` and `R_d` by the same unknown function leaves the observed derivative unchanged. Without additional measurements or restrictive assumptions, liver production, gut appearance and disposal cannot all be recovered separately. Insulin sensitivity requires more than fitting a glucose decay curve. The original minimal-model study used measured insulin as input and glucose as output [S2]; controlled experimental conditions do not transfer automatically to free-living meals.

An optional CGM observation compartment could use `dG_ISF/dt=(G_plasma-G_ISF)/tau` plus device filtering/bias, but `tau` must not be claimed individually identified from CGM alone. Basu's direct tracer estimate of approximately 5–6 minutes applied to eight healthy overnight-fasted participants [S3], not a universal postmeal shift. Device delay and physiological transport delay are distinct. Blood ketones are concentrations, not ketone-production flux; lactate is a production-minus-disposal balance; SpO2 does not measure tissue oxidative phosphorylation; energy expenditure estimates do not identify fuel mixture. Indirect calorimetry under valid assumptions can constrain substrate utilization far more directly than HR or HRV.

HRV-related states likewise need operational naming. Respiratory rate and tidal volume changed RSA magnitude independently of inferred tonic vagal control in a small beta-blockade experiment [S5]. This supports respiratory/context adjustment and uncertainty; it does not establish a universal conversion from SDNN to vagal tone. A sparse wearable SDNN trajectory cannot uniquely quantify sympathetic activation, inflammation, mitochondrial dysfunction or hormonal state.

## 2. Active measurement as model discrimination

MOTHER should emit a measurement request with: candidate hypotheses; which observations each explains; where their predictions diverge; proposed modality/condition/time window; expected discrimination; burden; prerequisites; contraindications or exclusion context; and a stop/unknown rule. The request is not an intervention or an order.

For fully specified candidate models, score a feasible measurement design `d` by

\[
U(d)=E_{y\sim p(y\mid D,d)}[KL(p(H,\theta\mid D,y,d)\Vert p(H,\theta\mid D))]-\lambda C(d).
\]

Expected information gain is a formal objective, not guaranteed biological information: it depends on the candidate-model family and predictive calibration [S14]. A first implementation should use an auditable rule table before attempting complex EIG optimization. Include an `other/unmodeled` alternative and prefer measurements with contrasting predictions instead of merely collecting more of an already redundant modality.

Examples:

| Ambiguity | Useful additional observation | What it can resolve | What remains unknown |
|---|---|---|---|
| Low SDNN with higher HR: breathing/posture, activity, illness, generalized activation | Same-device rest segment with posture and respiratory context; artifact review | Whether the pattern persists under a comparable sampling condition | Specific catecholamine concentration or cytokine pathway |
| Larger postmeal CGM excursion: meal composition/timing error, lag/artifact, appearance or disposal change | Exact meal time/quantity; repeated matched meal context; reference glucose when appropriate and available | Event alignment, reproducibility, some sensor discrepancy | Separate gut absorption, hepatic output and peripheral uptake without stronger measurement design |
| Higher fecal butyrate: more synthesis, less host uptake, altered transit, or less cross-feeder consumption | Transit context and compartment-specific metabolomics; isotope tracing in a research setting | Some mass-balance alternatives | Receptor activation or tissue flux inferred solely from stool concentration |

## 3. Mechanistic graph: preserve conjunctions, contexts and conservation

Use a typed temporal claim graph with reaction/event nodes (a relationally stored hypergraph), rather than a giant unqualified list of positive/negative edges. A reaction has a set of participant roles, stoichiometric coefficients, compartment, catalyst/enzyme, cofactors, pH/redox bounds and evidence. Gene presence is capability, expression is a stronger but still indirect activity proxy, and flux is a separate quantity. Record species/strain and assay context. A mechanism observed in an engineered cell or mouse belongs to that context until transported with explicit assumptions.

For metabolites and biomass, enforce

\[
\dot c = S v + T(c,c_{neighbor}) + inputs - consumption - washout,
\]

and, where steady-state flux-balance modeling is appropriate, `S v = 0` with explicit boundary exchange and biomass terms. Preserve element/charge/electron accounting; do not require a closed balance from a system with missing exchange reactions. Thermodynamic feasibility requires the appropriate reaction quotient and compartment chemical potentials (`DeltaG=DeltaG0'+RT ln Q`); a negative calculated reaction free energy establishes a feasibility constraint, not in-vivo flux. MICOM offers a research-scale constraint-based model with explicit objective/tradeoff assumptions [S9]; run it offline as a hypothesis/simulation module rather than making it the live sensor engine.

### Primary evidence examples for E1 edges

Belenguer et al. experimentally showed strain-level cross-feeding in anaerobic culture: some Bifidobacterium adolescentis strains supplied lactate/acetate or carbohydrate breakdown products supporting butyrate-producing partners; substrate and pH contexts were part of the experiment [S8]. Encode the strain, substrate, partners, pH and measured product. Do not flatten this to `Bifidobacterium increases butyrate` or infer net flux from abundance.

Byndloss et al. provide an especially useful conditional host–microbe feedback motif [S10]. In their mouse systems, the PPARγ/colonocyte-metabolism pathway affected electron-acceptor availability and Enterobacteriaceae fitness. Crucially, epithelial PPARγ loss alone did not suffice for the oxygenation effect: inflammatory context such as DSS exposure or virulent Salmonella was required. Store a conjunctive hyperedge and keep the nitrate/NOS2 route distinct from oxygen consumption. This is mechanistic evidence in the studied systems, not proof that a user's wearable pattern identifies this pathway.

### Receptor states are not endpoint labels

Use distinct nodes for ligand concentration in a relevant compartment, receptor surface abundance, ligand binding, pathway-specific signaling, and host function. For a single shared competitive site at equilibrium, an illustrative occupancy model is

\[
\theta_i=\frac{L_i/K_i}{1+\sum_j L_j/K_j};\qquad S_k=\mathcal G_k(R_s\sum_i\epsilon_{ik}\theta_i,context).
\]

`Ki` must be affinity under the stated assay; do not substitute EC50 without a model. `epsilon_ik` distinguishes agonism/antagonism and pathway bias; receptor reserve and transduction can make response differ substantially from occupancy [S7]. The simple formula does not cover multiple sites, cooperativity, allostery, nonequilibrium binding or compartment transport without extension. FFA2/GPR43 and FFA3/GPR41 ligand responses were experimentally characterized in heterologous systems [S6]; concentrations and receptor context must be preserved before extrapolating.

Example trafficking equations, as a hypothesis template rather than fitted physiology:

\[
\dot R_s=k_{syn}+k_{recycle}R_{int}-k_{internalize}a(t)R_s-k_{surface-loss}R_s,
\]
\[
\dot R_{int}=k_{internalize}a(t)R_s-(k_{recycle}+k_{degrade})R_{int}.
\]

GPCR internalization has receptor-dependent routes; beta-arrestin-dependent trafficking is supported experimentally, not a universal rule [S16]. A simple numerical illustration: ligand ratio `L/K` rises from 1 to 4, while available receptors fall from 1 to 0.2. Occupied surface receptors fall from `1*(1/2)=0.5` to `0.2*(4/5)=0.16`. Higher ligand therefore does not imply stronger signaling even in this deliberately simple model. These numbers are synthetic, not parameter estimates.

## 4. Intervention and N-of-1 evidence must remain separate

Maintain distinct identifiers for a literature mechanism, intervention hypothesis, planned experiment, randomized assignment, actual exposure, adherence, outcome measurement, causal analysis and conclusion. `hypothesis-supported`, `exposure-recorded`, `association-observed`, and `individual-effect-replicated` are different statuses. An outcome claim should specify the individual, intervention version, comparator, context, time horizon, effect distribution and analysis version. It must not imply a biochemical mechanism was established merely because an outcome changed.

For a reversible, suitable behavioral comparison, specify randomized order, matched blocks, carryover/washout assumptions, primary endpoint, smallest effect of interest, stopping criteria, adverse-response endpoints and analysis before data collection. Within-person comparisons remove stable person-level differences, not time-varying confounding. Analyze the randomized assignment as primary; actual exposure/adherence analyses are secondary and need additional assumptions. Preserve all periods, missingness and early stopping [S15]. Use autocorrelated residual models or block resampling at the day/meal/period level; 288 CGM observations in a day are not 288 independent treatment replications. Do not adjust away a post-treatment mediator (e.g. measured postmeal steps when estimating the total effect of assigned walking).

An illustrative outcome model is

\[
Y_b=\alpha_{person}+\alpha_{matched-block}+\beta A_b+\gamma^T C_{pre,b}+\delta Carryover_b+e_b,
\]

with randomization-based checks or appropriately calibrated Bayesian intervals. Predeclare which contexts must be stable and which are effect modifiers. Precision requirements, effect size of interest and observed variance should determine the number of periods; there is no universal sufficient cycle count.

Walking is an example of a candidate research hypothesis with context-specific literature, not a universal prescription. DiPietro's small older-adult trial found improved glucose outcomes under the studied protocol [S12]. Van Dijk's trial in men with type 2 diabetes found reduced meal iAUC with brief ADL but no significant reduction in daily time above its hyperglycemia threshold for that ADL condition [S13]. These are different endpoints/populations, not a reason to erase one result. They show why the registry needs context and outcome-specific support/contradiction relations. A lower excursion in a personal trial would support that protocol's glycemic outcome under observed conditions; it would not on its own prove improved mitochondrial function or identify an insulin-mediated mechanism.

## 5. Scientific validation gates

1. Software validity: event deduplication, unit conversion, interval semantics, deterministic replay, correct equations, numerical stability, version pinning and deletion propagation. Passing these does not validate biology.
2. Measurement validity: compare with appropriate references under the acquisition conditions, quantify bias, agreement, artifacts and error structure; correlated device outputs are not independent validation.
3. Predictive validity: rolling-origin evaluation with leakage-free baselines and whole-day/episode holdouts; compare against last-value, individual circadian baseline and simple regression. Assess interval coverage/sharpness and residual context dependence in addition to prediction error. Report performance after device or regime changes separately.
4. Latent-state validity: show observability under actual sensor schedules, parameter recovery in synthetic systems, robustness to plausible alternative mechanisms, and agreement with independent measurements that were not used to fit the state. Synthetic truth recovery is necessary but not proof of the human mechanism.
5. Causal validity: prospective randomized within-person replication where appropriate, predefined effect/uncertainty criteria, carryover assessment and retained null/adverse results. External mechanistic studies can strengthen plausibility but cannot establish the individual's mechanism without relevant measurements.

Preserve contradicted hypotheses, failure contexts, negative results, outgoing model artifacts and evaluation histories across model retirement. Candidate models should be compared in replay/shadow mode against a frozen accepted model; a change in explanation should never silently rewrite historical outputs. The dynamic research graph should export reviewed versioned mechanism bundles with stable identifiers and hashes; inference consumes a pinned bundle and is reproducible even while the research graph evolves.

## 6. Primary-source register

All source descriptions below are scoped claims, not universal causal assertions. No source is quoted verbatim. Browser access sometimes returned PubMed/PMC anti-bot pages; full abstracts or targeted methods passages were retrievable with search. Root must open or search the primary URLs directly before using their citation refs.

| ID | Primary source / official documentation | Exact design use and limitation | Retrieved source refs |
|---|---|---|---|
| S1 | Apple, [heartRateVariabilitySDNN](https://developer.apple.com/documentation/healthkit/hkquantitytypeidentifier/heartratevariabilitysdnn.md); [WWDC19 heartbeat series](https://developer.apple.com/videos/play/wwdc2019/218/) | HealthKit HRV scalar is SDNN; a heartbeat-series request is a separate capability. Does not establish repository integration or algorithm quality for this individual. | `turn5view5`, `turn0search20` |
| S2 | Bergman et al., 1979, [DOI 10.1152/ajpendo.1979.236.6.E667](https://doi.org/10.1152/ajpendo.1979.236.6.E667); [PMID 443421](https://pubmed.ncbi.nlm.nih.gov/443421/) | Original minimal-model work used measured insulin input and glucose output after controlled glucose injection in dogs. Supports careful measurement requirements, not CGM-only insulin-sensitivity claims. | `turn7search5`, `turn7search6` |
| S3 | Basu et al., 2013, [DOI 10.2337/db13-1132](https://doi.org/10.2337/db13-1132); [PMCID PMC3837059](https://pmc.ncbi.nlm.nih.gov/articles/PMC3837059/) | Eight healthy overnight-fasted subjects; tracer-measured interstitial lag approximately 5–6 min. Do not generalize to dynamic exercise/meals or whole device delay. | `turn6search0`, `turn6search1` |
| S4 | Raue et al., 2009, [DOI 10.1093/bioinformatics/btp358](https://doi.org/10.1093/bioinformatics/btp358); [PMID 19505944](https://pubmed.ncbi.nlm.nih.gov/19505944/) | Profile likelihood distinguishes structural/practical nonidentifiability and supports experiment planning. It is a method, not validation of a particular MSE. | `turn1search1` |
| S5 | Grossman et al., 1991, [DOI 10.1111/j.1469-8986.1991.tb00412.x](https://doi.org/10.1111/j.1469-8986.1991.tb00412.x); [PMID 1946886](https://pubmed.ncbi.nlm.nih.gov/1946886/) | Six men studied after beta blockade; respiratory effects on RSA complicate vagal interpretation. Specific RSA experimental finding, not direct calibration of HealthKit SDNN. | `turn6search3`, `turn1search5` |
| S6 | Brown et al., 2003, [DOI 10.1074/jbc.M211609200](https://doi.org/10.1074/jbc.M211609200); [PMID 12496283](https://pubmed.ncbi.nlm.nih.gov/12496283/) | GPR41/GPR43 activation by SCFA ligands in engineered assay systems, with differing ligand specificity. Preserve tissue/assay limitations. | `turn1search2` |
| S7 | Black & Leff, 1983, [DOI 10.1098/rspb.1983.0093](https://doi.org/10.1098/rspb.1983.0093); [PMID 6141562](https://pubmed.ncbi.nlm.nih.gov/6141562/) | Operational agonism separates binding and transduction, supporting separation of affinity, efficacy and system response. A general model, not fitted receptor parameters here. | `turn2search1` |
| S8 | Belenguer et al., 2006, [DOI 10.1128/AEM.72.5.3593-3599.2006](https://doi.org/10.1128/AEM.72.5.3593-3599.2006); [PMCID PMC1472403](https://pmc.ncbi.nlm.nih.gov/articles/PMC1472403/) | In-vitro strain-, substrate- and pH-dependent cross-feeding; isotope work distinguishes routes. Not net human community flux inferred from taxa abundance. | `turn3search2`, `turn3search3`, `turn3search13` |
| S9 | Diener et al., 2020, [DOI 10.1128/mSystems.00606-19](https://doi.org/10.1128/mSystems.00606-19); [PMCID PMC6977071](https://pmc.ncbi.nlm.nih.gov/articles/PMC6977071/) | MICOM constraint-based community modeling; objectives/tradeoffs materially change predictions. Gene/abundance inputs and modeled growth do not measure human metabolite flux. | `turn7search7`, `turn3search12` |
| S10 | Byndloss et al., 2017, [DOI 10.1126/science.aam9949](https://doi.org/10.1126/science.aam9949); [PMCID PMC5642957](https://pmc.ncbi.nlm.nih.gov/articles/PMC5642957/) | Experimental mouse host–microbe feedback, including inflammation-dependent oxygen effects of reduced epithelial PPARγ. This is a conditional mechanistic exemplar, not a universal human inference. | `turn6search2` |
| S11 | Berry et al., 2020, [DOI 10.1038/s41591-020-0934-0](https://doi.org/10.1038/s41591-020-0934-0); [PMCID PMC8265154](https://pmc.ncbi.nlm.nih.gov/articles/PMC8265154/) | Repeated standardized meals and person/context variation justify individualized context models. Prediction and microbiome associations are not causal mechanism proof. Check linked publisher correction. | `turn2search4`, `turn2search14`, `turn2search19` |
| S12 | DiPietro et al., 2013, [DOI 10.2337/dc13-0084](https://doi.org/10.2337/dc13-0084); [PMCID PMC3781561](https://pmc.ncbi.nlm.nih.gov/articles/PMC3781561/) | N=10 inactive older adults, controlled randomized protocol order; postmeal walking improved specified glycemic endpoints. Evidence is population, protocol and endpoint specific. | `turn7search3`, `turn7search4` |
| S13 | van Dijk et al., 2013, [DOI 10.2337/dc12-2620](https://doi.org/10.2337/dc12-2620); [PMCID PMC3816888](https://pmc.ncbi.nlm.nih.gov/articles/PMC3816888/) | N=20 men with T2D; brief ADL reduced cumulative meal iAUC but did not significantly reduce daily duration above specified hyperglycemia threshold. Keep endpoint-specific results. | `turn7search1`, `turn7search2` |
| S14 | Foster et al., 2020, [A Unified Stochastic Gradient Approach to Designing Bayesian-Optimal Experiments](https://proceedings.mlr.press/v108/foster20a.html) | Primary computational method for expected-information-gain design. EIG is conditional on supplied probabilistic model; no physiological validation implied. | `turn2search26`, `turn2search50` |
| S15 | Vohra et al., 2015, [CENT statement DOI 10.1136/bmj.h1738](https://doi.org/10.1136/bmj.h1738); Shamseer et al., [explanation DOI 10.1136/bmj.h1793](https://www.bmj.com/content/350/bmj.h1793) | Primary reporting guidance for prospective multiple-crossover N-of-1 trials: prespecification, periods, missingness, outcomes and uncertainty. It does not make an observational series causal. | `turn1search3`, `turn1search4` |

Optional mechanistic sources if the final report includes these claims:

- **S16** Ferguson et al. 1996, [DOI 10.1126/science.271.5247.363](https://doi.org/10.1126/science.271.5247.363), [PMID 8553074](https://pubmed.ncbi.nlm.nih.gov/8553074/), `turn3search1`; Zhang et al. 1996, [DOI 10.1074/jbc.271.31.18302](https://doi.org/10.1074/jbc.271.31.18302), [PMID 8702465](https://pubmed.ncbi.nlm.nih.gov/8702465/), `turn3search8`: experimental beta-arrestin/GPCR internalization and distinct endocytic routes. Do not universalize one receptor's route.
- **S17** Broussard et al. 2012, [DOI 10.7326/0003-4819-157-8-201210160-00005](https://doi.org/10.7326/0003-4819-157-8-201210160-00005), [PMCID PMC4435718](https://pmc.ncbi.nlm.nih.gov/articles/PMC4435718/), `turn6search4`: seven-person randomized sleep-restriction crossover measured adipocyte insulin-stimulated Akt signaling and systemic insulin sensitivity. Shows what direct tissue-mechanism evidence looks like; wearable sleep/glucose correlations cannot substitute for those assays.
