# Coach/Mother implementation handoff to the design session

**Design-session decision brief · 7 November 2026 · source/design evidence**

The working objective remains the exercise-end forecast of subsequent measured
cardiovascular/overnight response, with synchronized replay and separate channel
outcomes. Draft 0.11 already supplies that direction; the earlier interview's
general endpoint question should not restart the objective discussion. The
remaining decisions concern operational definitions and evidence qualification.

M1 corrects legacy glucose analytics; E01 supplies a generic scalar evaluation
harness. Neither chooses a physiological recovery endpoint. This review read
the supplied design/handoff snapshots and those implementations. It did not read
personal Parquet data, change implementation, or verify deployment.

## Priority and ownership

| ID | Priority | Consequential choice | Authority / next evidence |
| --- | --- | --- | --- |
| DG-01 | P0 before real response evaluation | Exact target recipe and channel-specific eligibility | Design session, informed by PM export/coverage inspection |
| DG-02 | P0 before episode construction | Shared-outcome grouping and benchmark prediction anchor | Design session; PM implements the selected episode rules |
| DG-03 | P1 before forecast claims | Evidence allowed when historical availability is unknown | Existing design principle already constrains claims; design selects the first validation scope |
| DG-04 | P1 before local-night analysis | Historical timezone and sleep association | Primarily PM source qualification; escalate only an unresolved analysis fallback |
| DG-05 | P1 before reporting personal accuracy | Representative benchmark, baseline comparison, and uncertainty qualification | Design session sets the evaluation question; PM freezes and executes the protocol |

## DG-01 — Specify the first outcome recipe without redefining recovery

**Gap and importance.** The design lists eligible channel families, but a scalar
training label still needs a reproducible summary, interval, source/method, and
coverage rule. These choices determine what the model predicts. The 30-minute
replay view is an engineering display default, not an adopted recovery deadline.

**Evidence and uncertainty.** D1, “First response model and evaluation,” separates
early HR, next-sleep HR, metric-specific HRV, other overnight channels, glucose
context, and spot anchors. M1's `label_events` still constructs glucose-event
labels and requires measured future bins. E01 accepts a caller-defined channel,
value, unit, outcome end, and eligibility. Actual Watch sampling, Polar retained
samples, and shared source intervals remain unqualified in the supplied design
record; H10 ECG/RR availability cannot be presumed.

**Options and tradeoffs.** A well-supported next-sleep scalar uses existing
overnight coverage but depends on a reliable sleep interval and distributed
observations. An early post-exercise trajectory can resolve short-time response
when continuous recording and exercise cessation are supported. Multiple channel
targets retain physiological detail but need separate eligibility and evaluation.

**Recommendation.** Inspect the first overlapping source bundle, then adopt one
versioned scalar recipe per supported channel while retaining its original
trajectory. Keep HRV source/method/window distinctions. Return concrete proposed
summary and coverage rules to design; do not transfer the legacy five-minute
glucose completeness gate to sparse Watch measurements.

**Affected interfaces.** Observation method/native type and quality; episode
target recipe/version, `channel`, `unit`, `value`, `outcome_end`, `eligibility`;
Coach coverage and insufficient-data displays.

**Continuing work.** Source imports, archive/revision retention, replay, coverage
profiling, and synthetic evaluator checks.

## DG-02 — Define the independent episode and its prediction anchor

**Gap and importance.** Several workouts may share one sleep outcome; subsequent
exercise can also interrupt an early response. A group identifier prevents
duplicate evidence, but it does not by itself choose the scientifically useful
prediction cutoff or exposure summary.

**Evidence and uncertainty.** D1 requires linked/cumulative multi-session
episodes and grouped evaluation. E01 collapses consistent shared group/channel
outcomes, uses the group's earliest cutoff in its generic baseline report,
purges groups spanning the split, and rejects unresolved overlaps. That earliest
cutoff is a harness convention, not a design decision about exercise physiology.
Actual workout frequency, cooldown logging, workload fields, and sleep linkage
remain unknown.

**Options and tradeoffs.** One prespecified benchmark prediction per shared
outcome group gives straightforward independent accounting. Forecasting after
every workout preserves more interactions but requires group-aware weighting
and reporting of correlated predictions. Treating a cluster as cumulative
exposure requires an explicit cluster/cessation rule and retains workload
components in their own units.

**Recommendation.** Preserve every workout and its time. Construct shared-outcome
links from source evidence, then have design select one benchmark anchor rule
for the first evaluation. Do not silently adopt E01's earliest-cutoff convention
as the physiological rule. Unresolved groups remain visible and unscored until
reconciled; no outcome is duplicated across train/test partitions.

**Affected interfaces.** Session/exercise and sleep links, `episode_id`,
`outcome_group_id`, cutoff, outcome interval, cumulative workload representation,
split manifest, and interruption/censoring status.

**Continuing work.** Event/session linking, source timelines, overlap detection,
group validators, and replay of both simple and multi-workout episodes.

## DG-03 — Qualify historical availability before claiming forecast behavior

**Gap and importance.** Measurement timestamps alone do not establish that an
input or completed outcome was available at a historical prediction/fit cutoff.
Six months of retrospective measurements may support useful mapping while their
original availability remains unknown.

**Evidence and uncertainty.** D1's observation contract explicitly preserves
unknown availability and requires stated replay assumptions. M1 defaults to
strict availability in its callable API; the legacy pipeline explicitly selects
`assume_at_measurement`. E01's strict mode excludes training outcomes without
supported `outcome_available_at`; its explicit `assume_outcome_end` alternative
records affected groups. Actual uploader latency, vendor synchronization, and
annotation availability have not been established by this review.

**Options and tradeoffs.** Strict historical evaluation supports a stronger
timing claim but may leave few eligible episodes. Assumption-labeled replay uses
more history and can test sensitivity to declared delays, with a conditional
interpretation. Prospective logging can supply measured timing evidence while
historical mapping continues.

**Recommendation.** Keep strict gates for live-equivalent forecast claims and
retain clearly labeled retrospective exploration. The design session should
choose the first real-data validation claim after the PM reports availability
coverage. No new permission is needed to preserve unknown times or implement
both paths; those requirements are already settled.

**Affected interfaces.** `source_available_at`, annotation known time,
`outcome_available_at`, feature cutoff metadata, replay policy, latency evidence,
and report evidence labels.

**Continuing work.** Original/revision capture, durable checkpoints, UTC replay,
source-supported timestamp extraction, and future collector timing logs.

## DG-04 — Establish historical timezone facts and actual sleep intervals

**Gap and importance.** A global UTC night mask is not verified local-night
history, and a clock window does not establish the next principal sleep episode.
Timezone and sleep mistakes change which measurements enter an overnight target.

**Evidence and uncertainty.** D1 requires actual sleep episodes and historical
local-time context. M1 accepts an explicit IANA timezone and labels its checked-in
UTC configuration an unverified engineering fallback. E01 uses absolute aware
cutoffs and does not select sleep episodes. Source offsets, timezone changes,
travel intervals, and actual sleep annotations remain to be inspected.

**Options and tradeoffs.** A verified single-zone run is simple when the entire
interval supports it. A versioned interval-to-timezone map handles changes with
more metadata. Unknown segments can retain UTC alignment while abstaining from
local-clock classification. Clock-based windows could be a separately declared
secondary analysis if design chooses one when sleep data are unavailable.

**Recommendation.** PM should recover original offsets and source timezone
evidence, use actual sleep records, and maintain explicit unknown segments.
Do not infer historical zones from the user's current residence or the host.
Escalate only if missing sleep evidence forces a choice of a different analysis
endpoint; ordinary timezone reconciliation is PM-owned work.

**Affected interfaces.** Original timestamp/offset, clock context, historical
zone provenance, session/sleep association, `timezone` configuration, and target
eligibility.

**Continuing work.** UTC synchronization, raw interval display, timezone/DST
validation, and channel coverage inspection.

## DG-05 — Freeze a representative evaluation protocol after data qualification

**Gap and importance.** One reconciled replay verifies a data path. Personal
accuracy and useful uncertainty require later independent episodes representing
the intended workload and sleep conditions. Software defaults do not establish
that qualification.

**Evidence and uncertainty.** D1/H1 specify an initial overlapping
Nightscout–Watch–Polar bundle, then repeated comparable episodes, rest comparisons,
chronological evaluation, baseline comparison, and coverage/abstention reporting.
E01 implements a context-free training median and an explicitly uncalibrated
empirical range. Its latest-quarter split and minimum two training groups are
engineering defaults, not a selected personal study protocol or sample adequacy
claim. Available independent counts, workload diversity, wear gaps, and target
eligibility remain unknown.

**Options and tradeoffs.** A fixed later holdout is easy to freeze and audit but
uses one temporal comparison. Rolling-origin evaluation can expose temporal
variation and use more episodes, with additional split/availability checks.
A context-free median supplies a transparent first comparator; a contextual
baseline requires verified workload/context fields and enough comparable groups.

**Recommendation.** PM first reports usable independent groups and missingness
by channel/context. Design then selects and versions the benchmark question,
reference conditions, target eligibility, and evidence needed for an accuracy
claim. Begin with an explicitly frozen later holdout and the transparent baseline;
report empirical interval coverage/width without calling it calibrated merely
because the evaluator returned numbers. Preserve ordinary rest and non-exercise
sleep records for the selected comparison.

**Affected interfaces.** Dataset qualification manifest, target/processing
version, split cutoff/group manifest, baseline version, coverage and abstention
counts, interval method, and evaluation scope.

**Continuing work.** Generic evaluation arithmetic, split/purge validation,
reproducible reports, archive coverage summaries, and source lineage.

## Evidence references

- **D1:** [Personal Physiology and Delivery Prototype](https://chatgpt.com/space/page_de885284f8bc8191b47d127ee38a02b2), Draft 0.11; local source snapshot `/workspace/scratch/572703d71a95/inputs/design_page.md`. Relevant headings: “First response model and evaluation,” “Minimal observation contract,” and “Ordered implementation plan.”
- **H1:** [Coach and Mother App Development Handoff](https://chatgpt.com/space/page_f04c83ebd5ac81918eb219c56111d1de), Version 1; local snapshot `/workspace/scratch/572703d71a95/inputs/handoff_page.md`. Relevant headings: “First model and replay requirements,” “Acceptance and delivery,” and “Decisions and reporting back to design.”
- **M1:** Mother worker commit `ab67c8ddfd2b76ea6402d21fdac6a35ca26bec00`; `analytics/events/window_builder.py` (`compute_features`, `label_events`), `analytics/config/pipeline.yaml`, and `analytics/preprocess/sources/hrv_adapter.py`.
- **E01:** Mother worker commit `d880b7be50e1b1cf76b588c77b9b7c3a1bc80bb4`; `mother/physiology/evaluation.py` (`_groups`, `_validate_retained_overlap`, `evaluate_baseline`).

These are implementation/design boundaries, not requests to pause independent
development. Device-model verification, export mapping, database/runtime
reconciliation, code-level deduplication, and test mechanics remain PM-owned.
Delivery substances, route, dose, garment hardware, and physical experiments
remain with the design session and do not need decisions for these software
increments.
