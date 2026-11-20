# Independent MSE prototype review

## Post-fix independent acceptance — 13 November 2026

The author implemented corrections for R1–R3 after the initial review below. The reviewer re-read the modified model/storage logic, repeated the original probes and independently ran the 52 core tests. **R1–R3 are resolved for the declared retrospective reference scope.** Original findings below are preserved as the review history, not outstanding claims about the corrected package.

- **R1:** reference time is now acquisition interval end; baseline supports must be completed, nonoverlapping earlier intervals. Overlapping/equal-time supports abstain rather than multiplying information. The original long interval is no longer in the earlier target baseline. Outputs explicitly declare `retrospective_snapshot`, historical source/MOTHER availability false, and maximum support receipt time. The global source-receipt cutoff also requires completed intervals and explicitly does not represent a separate historical knowledge set at every state. Unsupported `source_as_available` mode rejects.
- **R2:** grouping now includes method, exact observed interval duration, optional declared window and calibration identity. Original method-change probe yields baseline count zero and unknown state. Exact-duration stratification is intentionally conservative and may fragment real HealthKit windows; real-data qualification should assess whether a declared equivalence class is justified instead of silently pooling them.
- **R3:** known-invalid flags exclude records from baseline/filter updates. The original known-motion ancestor is absent from supporting IDs, present in excluded IDs and explicitly reflected in output quality. Separate current, baseline, recursive-ancestor, support and excluded quality summaries now retain dependency context.

Independent command: `PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests -p test_mse.py -q`.

**Observed: 52 tests passed in 0.055 seconds.** Executable implementation SHA-256 at recheck: `998ad8654a801945bd0fa10b93de75755bee929317b49b3701584372e0e7dbf1`. The reviewer separately repeated the three original probes plus rejection of the unsupported historical mode. No real data, network endpoint, physiological intervention or production service was used. No executable package file was edited by this reviewer.

The original caveat about first-persisted receipt times, unqualified relay relationships, approximate baseline/OU uncertainty and absent online availability remains relevant, and is consistent with the corrected explicit retrospective scope. Architecture C4/F should use interval-end reference, the expanded strata, exact unknown/status fields and external/future factual-response capture semantics. The package author is refreshing release manifest/examples/documentation separately.

## Initial review and findings — retained history

Reviewed `/workspace/scratch/d8b6cef2becf/mse-prototype-v0.1.0` and architecture report sections C4/F on 13 November 2026. Read contracts, adapters, SQLite storage, filter/replay, feature utility, CLI, installer/retirement implementation, README and relevant tests. No package file was edited. This is a bounded correctness review, not a security certification or physiological validation.

## Disposition

The isolated design is coherent for an **offline retrospective, uncalibrated reference prototype**. It preserves raw artifacts, scopes native identity, separates source stores, retains tombstones and failed conflicting imports, stores reproducible code/configuration/data identities, and labels unknown biochemical mechanisms. The copy-only installer and rename-only retirement avoid modifying production repositories/services. The main remaining issues concern the meaning of time, method and quality in an estimate; they should be resolved or explicitly machine-labeled before calling outputs online/as-available physiological inference.

## Findings confirmed with targeted synthetic probes

### R1 — Interval and availability boundaries are weaker than “as-of” can imply

**Location:** `mse/model.py`, `estimate`, series ordering and prior-baseline selection; `mse/storage.py`, `active_observations`.

The filter sorts and timestamps estimates by `event_start`. Prior baseline eligibility checks only an earlier `event_start`; it does not require the previous interval's `event_end` to precede the target, or its `received_at` to be known by that target time. A source-receipt cutoff restricts the whole selected dataset once, not the knowledge set independently at every estimate time.

**Executed probe:** ten otherwise valid synthetic observations at minute intervals; first observation starts at 00:00 but ends and is received at 00:39. The state labeled `as_of_event_time=00:09` includes that first observation in its baseline, `baseline_count=9`, `status=estimated`.

This is acceptable only as explicitly defined retrospective start-indexed processing, not evidence that the baseline was available at 00:09. The existing test that appends a later-event observation does not test a late-arriving earlier event or overlapping acquisition interval.

**Recommendation:** choose a declared observation reference time (conservatively interval end), disallow overlapping/incomplete supports from a target's baseline, and distinguish event-time retrospective from sequential availability-time replay. A minimally scoped release can instead emit explicit machine fields such as `availability_policy=retrospective_snapshot` and state that “prior” means prior sample starts, with no online-validity claim. Do not present the existing global source-receipt-cutoff view as per-state historical availability.

### R2 — Native method/window changes can silently share a baseline

**Location:** `mse/model.py`, grouping tuple.

Grouping separates subject, archive source, channel, context, bundle and device. It omits `provenance.method` and acquisition-window definitions. A native replay can therefore supply same-source SDNN or HR records with different declared methods/windows and still combine them.

**Executed probe:** changing only the final record's method to a different measurement-window description yields `baseline_count=9`, `status=estimated`.

The actual HealthKit adapter currently emits a constant method per channel, so this is chiefly an extension-contract risk rather than proof of a mixed-method real input. Include method/window/calibration identity in future strata or reject within-series changes until a bridge calibration is declared. Unknown device identity is correctly flagged and cannot be repaired by this grouping rule.

### R3 — Ancestor quality flags do not propagate into the state summary

**Location:** `mse/model.py`, construction of `measurement_quality_flags` and filter lineage.

The state copies only the current record's quality flags, while prior baseline/filter observations remain dependencies. Quality flags do not exclude/downweight records in this reference model.

**Executed probe:** mark a baseline ancestor `known_motion_artifact`. Its ID remains in `supporting_observation_ids`, but the flag is absent from the final state's `measurement_quality_flags`; output remains estimated.

The full lineage permits downstream investigation, but a consumer looking only at state flags may miss known bad support. Aggregate dependency quality or provide separate current/baseline/filter quality summaries, and define which verified invalid flags require abstention. Unqualified error models are already disclosed; those disclosures do not identify a particular flagged ancestor.

## Additional limitations from source inspection

- `measurement_identity` excludes `received_at`, and duplicate imports preserve the first persisted normalized receipt. Raw alternate artifacts remain linked. If otherwise identical replay inputs declare different receipt times and are imported in different orders, the source-receipt-cutoff view can differ. The actual bridge normally preserves its first receivedAt; avoid using arbitrary native receipt revisions as a historical-availability authority without a defined merge/revision policy.
- State groups do not pool distinct archive sources, so no direct duplicate cross-source fusion occurs in this prototype. Relayed-copy identity is not resolved: two separately labeled feeds may still represent the same originating sensor. Do not count two emitted series as independent corroboration.
- Any observation-set addition/deletion invalidates all prior runs conservatively. That is safe but broader than necessary. Run invalidations and retained source artifacts are useful; there is no implemented public “current valid state” API, and consumers must not ignore invalidation records when that API is added.
- Malformed input is rejected before a Store is opened. Only conflicts accepted far enough to reach `import_batch` are retained as rejected raw artifacts. Do not describe all malformed input as durably quarantined by this prototype.
- The moving sample-mean baseline plus OU residual is a transparent reference calculation. It does not estimate baseline autocorrelation, robust outliers, circadian structure or context regression. Its dependence/uncertainty limitations are clearly disclosed; the displayed interval is not a calibrated biological credible interval.

## Architecture C4/F claim alignment

**Aligned:** C4 correctly says independent scalar OU reference filters, positive-SDNN log transform, simple historical baseline, fixed assumed noise/OU parameters, uncalibrated uncertainty, no fitted harmonic/context regression, and no biochemical mechanism identification. F correctly says standalone package, read-only source input, new replay envelope, no existing PF001/N3 exporter and no production integration.

**Small corrections recommended:**

1. C4 says low support yields `insufficient_data`; actual output is `status="unknown"`, `reason="insufficient_prior_baseline"`. Use exact field values if presenting them as implementation behavior.
2. C4 says filters separate subject/source/channel/context; implementation also separates bundle/device. State that explicitly.
3. “Prior-only” needs the temporal qualification in R1. The proposed online/replay design is stronger than the executable start-time-only baseline.
4. F1's slice sequence includes optional factual response capture. The executable package has no event/answer capture adapter or intervention/exposure evaluator; its replay envelope contains observations and tombstones. Label response capture as existing external COACH capability or a subsequent integration step.
5. A future contextual baseline path in F is correctly labeled proposed. Do not summarize the current scalar stratification as a fitted context-dependent model.

## Installer/replay strengths verified by inspection

- New installation destination required; manifest-listed files copied exclusively; no package installation, service, credential or production DB change.
- Retirement verifies payload checksums and a matching installation receipt, rejects untracked/modified files and symlinks, and renames rather than deletes.
- Replay refuses an unrecognized SQLite application ID/schema and creates new output files exclusively; physiological data stays separate from installed code.
- Input artifact bytes are stored independently of normalized hashes. Conflicting UUID sample contents reject the whole import while retaining the conflict artifact. Same UUID across explicit subject/source scopes remains distinct.
- Tombstones can precede observations and suppress later inference without destroying originals. Unknown deleted IDs remain evidence. Tests cover these properties.
- Same-timestamp observations do not multiply baseline support or sequential filter updates, and ancestry includes prior baselines after they leave the sliding window.
- The area primitive distinguishes signed versus positive incremental area, clips bracketing segments, and withholds whole-window area when support is incomplete.

## Verification performed in this review

Executed three short synthetic Python probes in the package directory using `python3 -B` and `PYTHONDONTWRITEBYTECODE=1`; no package modifications and no real data or external services. Their results are recorded under R1–R3. Existing test source was inspected to establish coverage boundaries; the entire suite was not redundantly rerun by this reviewer.

The review identified **no demonstrated production-write or destructive-installer defect** in the inspected path. This statement does not replace an exhaustive adversarial security review. The substantive blockers to stronger scientific use are temporal semantics, input qualification/method consistency and quality-aware uncertainty, not installation mechanics.
