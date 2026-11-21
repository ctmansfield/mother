# PF-001 / 0.1.0 — Physiology evidence foundation

**7 November 2026 · review release · contract 1.0.0 · Mother package 0.2.0**

This paired increment establishes reproducible physiological evidence storage
and offline replay, corrects identified data errors, and supplies a transparent
chronological evaluation harness. Exact compatible source commits and tree
hashes are in the release bundle's `manifest.json`. It is prepared for source
review and offline installation; production deployment remains unverified.

## Changes and purpose

- Shared observations, source revisions, streams, sessions, context/action
  events and import manifests distinguish provenance, measurement/availability/
  first-seen/ingestion times, exact channels, missingness and epistemic status.
  The PM owns the canonical schema and additive archive migration.
- Mother now constructs true measured forward outcome windows, excludes
  incomplete future coverage, and keeps feature fills out of outcome labels.
  Per-cutoff availability and explicit timezone handling prevent tested forms
  of temporal leakage. ISO/seconds/milliseconds HRV rows retain method identity
  and original-file evidence. Legacy glucose labels remain glucose labels.
- Nightscout acquisition retains immutable original responses/revisions,
  stable scoped identity, repeats, corrections, reversions and explicit deletion
  markers. Atomic checkpoints, incremental overlap and historical reconciliation
  replace silent rolling-history truncation. Parquet is an archive projection.
  Completeness requires a qualified server query/count capability and excludes
  unobservable hard deletions or a transactional snapshot guarantee.
- Bounded Apple Health XML, Polar-compatible TCX HR and manual spot CSV readers
  preserve originals, counted failures and unknowns. They do not invent H10
  ECG/RR, exact device identity, exercise cessation, specimen or historical
  availability.
- Mother exports synchronized retrospective replay bundles. Coach renders
  separate source/channel/epistemic lanes, discrete measurements, coverage gaps,
  event/action categories, session context, source lineage and import accounting.
  Untimed annotations stay visible with unknown occurrence. Waveform rendering
  is not implemented; nonempty stream inputs are explicitly rejected by this
  scalar viewer.
- Coach's malformed flow files are corrected. `flows.json` is the documented
  canonical mirror; the legacy latest-entry poller is disabled and produces
  qualified observation candidates for preview rather than blanket spike
  events. It is not the durable archive or a catch-up collector.
- A channel-specific median baseline evaluator freezes earlier training groups,
  preserves shared outcomes, purges split-spanning labels, checks availability
  and rejects unresolved overlap. Missing outcomes are unscored. Empirical
  training ranges are explicitly uncalibrated; reports include native-unit
  error, held-out coverage, width, abstentions and versions. Physiological
  target recipes and representative personal evaluation remain open.
- Independent review added regressions for invalid coverage, untimed events,
  session lineage, processing-version IDs, installed resources and evaluation
  boundaries. Release scripts were strengthened against checkout-hook effects
  and untracked/ignored Python shadowing.

## Migration and compatibility

The new SQLite migration initializes a separate selected archive; existing
PostgreSQL schemas and application services are untouched. No historical file
is silently promoted to raw evidence. Existing unarchived Parquet outputs are
protected from overwrite. Recompute analytics windows/discovery outputs after
qualifying source history. Preserve original and previous processing versions.

Mother and Coach contract copies must match byte for byte. When multiple
processing versions exist for one record/channel, replay requires an explicit
version selection. For sessions, the first declared source revision anchors the
archive's current projection; all declared source references are retained and
validated for subject consistency. See `CONTRACT.md` for details.

## Scope still open

One real overlapping Nightscout/Watch/Polar interval is needed to qualify actual
exports, clocks, relayed copies and coverage. Runtime launch paths, source
capabilities and storage durability need deployment evidence. Exact device
models and live logging capability remain unverified. No personalized recovery
score, automatic therapeutic delivery, new intervention policy, routine
subjective readiness label or live prompt trigger is introduced.

The event contract and replay keep recommendations, acknowledgments, reported
actions, observed actions and outcomes separate. A user-marker constructor and
event storage foundation exist; a complete prompting/action-entry workflow is a
later backlog item. Nonresponse cannot become a negative outcome.

See `INSTALL.md`, `VERIFY.md`, `VERIFICATION.md`, `CAPABILITIES.md`,
`DESIGN_GAPS.md` and `TASK_BOARD.md` for installation, acceptance, limits and the
next dependency-aware work. Do not import these flow changes into a running
Node-RED instance until its deployed export and local modifications are
reconciled.
