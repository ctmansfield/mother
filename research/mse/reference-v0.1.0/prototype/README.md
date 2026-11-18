# MSE reference prototype 0.1.0

This is a new, isolated, offline physiological inference prototype. It is not a
deployed MOTHER service, a replacement HealthKit collector, or a validated
metabolic/medical model. It reads a **copied** v0.3 `HealthArchive` JSON file without
changing the original. It supports the actual bridge's HR and vendor-derived SDNN
fields and a separate, explicitly new `mse.replay/0.1` fixture/export contract.

## Source grounding

The adapter was designed after inspecting `ctmansfield/mother-health-bridge` at
`b2baa2e6bd2d018b6e34a07c783b7c3523366374`:

- `MotherHealthBridge/HealthArchive.swift`: `SavedReading` and `HealthArchive`.
- `MotherHealthBridge/ContentView.swift`: active JSON acquisition, default Swift
  `JSONEncoder`, HR and SDNN, UUIDs, source name/bundle and tombstones.
- `MotherHealthBridge/SQLiteHealthKitAdapter.swift`: separate experimental
  transactional acquisition boundary, not called by this prototype.
- `AGENTS.md`: preserve active JSON, source data, signing and production services.

MOTHER's PF001 `schemas/v1.schema.json`, `contracts.py`, `imports.py`, and
`migrations/0001_archive.sql` were also inspected. An adapter from an authoritative
PF001 current-record snapshot remains a future integration; this package does not
invent a current-record export endpoint or infer deletion semantics from a loose
list of historical revisions. The glucose channel is accepted only in the new
explicit replay contract. No CGM connection is implemented here.

## Included behavior

1. Validate and hash the exact input bytes. Interpret Swift numeric dates as
   seconds since **2001-01-01 UTC**, not Unix seconds. Preserve opaque anchor
   digests and source provenance; do not parse or advance HealthKit anchors.
2. Keep raw artifacts and normalized observations in a **separate** SQLite file.
   Identity is scoped by subject, archive source and native UUID. Duplicate samples
   are idempotent; conflicting immutable samples reject the entire import while
   retaining its raw artifact in quarantine. Receipt-time changes alone do not
   redefine a sample.
3. Preserve tombstones, including delete-before-add. Old states remain auditable,
   but changes invalidate earlier runs and require replay. A tombstone hides a
   sample from inference; it is not deletion of retained raw physiological data.
4. Compute retrospective baselines from completed, nonoverlapping prior intervals
   and scalar Ornstein–Uhlenbeck (OU) reference estimates. Reference times are
   aggregate **interval ends**. Abstain when evidence is insufficient, after long
   gaps, for overlapping/extra same-time samples, or for known invalid quality.
   Subject, archive source, channel, bundle, device, explicit context, method,
   exact observed interval duration, declared acquisition window and calibration
   identity are separate strata. Unknown methods/windows do not merge with
   explicit declarations. The bridge lacks posture/activity/respiration context,
   so its baseline is **unadjusted**.
5. Return supporting observation IDs, full recursive baseline ancestry, code hash,
   configuration hash, immutable run ID, unknown biochemical dimensions, and a
   heuristic request for additional observations. Quality flags from every actual
   baseline/filter ancestor propagate; excluded observations and reasons remain
   visible. Every interval is marked `uncalibrated_reference_model`. There is no
   intervention execution authority.

All included data are synthetic. SQLite files and JSON replay results may contain
sensitive information when a user chooses a real input. Output files are created
with mode 0600 and newly created output directories with mode 0700. This package
does not implement database encryption or authenticate a network service.

## Reference model

For each channel/source/context, let `v` be HR in bpm or `log(SDNN in ms)`. The
baseline `b_t` is the arithmetic mean of qualified intervals in the preceding
seven days whose ends precede the current interval's end and do not extend past
its start. At least eight are required by default. This is event-time ordering in
a **retrospective snapshot**, not a historical availability guarantee. Low support
emits `status="unknown"`, `reason="insufficient_prior_baseline"`. There is no
physiological claim attached to that engineering threshold.

The residual observation is `y_t = v_t - b_t`. At elapsed time `dt`, the latent
scalar uses `a = exp(-dt/tau)`, predicted mean `m- = a*m`, and predicted variance
`P- = a*a*P + q_inf*(1-a*a)`. The observation variance is a fixed channel floor
plus the baseline sample variance (at least the same floor) divided by its sample
count. The Kalman gain is `K=P-/(P-+R)`, followed by `m=m-+K*(y_t-m-)` and
`P=(1-K)*P-`. The displayed reference interval is `m ± 1.96*sqrt(P)`.

| Channel | Measurement variance floor | OU equilibrium variance | OU time constant |
|---|---:|---:|---:|
| HR | 4 bpm² | 100 bpm² | 2 h |
| log SDNN | 0.09 | 0.16 | 6 h |
| Glucose, explicit replay only | 0.25 (mmol/L)² | 4 (mmol/L)² | 1 h |

These are **illustrative fixed parameters**, not learned instrument errors,
physiological time constants, or validated individual priors. Baseline uncertainty
uses an independence approximation; autocorrelation and errors in contextual
labels are not estimated. The moving baseline and OU residual are an empirical
reference construction. Persistent changes can enter the baseline; the prototype
does not establish whether that is adaptation, drift, illness or a new normal.
The default maximum latent continuity gap is six hours. No values are generated
between samples; sparse SDNN is never converted into beat intervals or RMSSD.

The following exact flags exclude a sample from the baseline and filter:
`known_motion_artifact`, `invalid_measurement`, `sensor_error`,
`invalid_calibration`, `clock_error`, and `corrupt_record`. A current sample with
any such flag produces `unknown` with reason `known_invalid_measurement_quality`.
Other flags propagate without a pretended numeric noise calibration. State
objects separate current, baseline, recursive-filter-ancestor, actual-support and
excluded-quality flags. `measurement_quality_flags` is their aggregate alert
summary; consult `excluded_observation_ids` to see what did not contribute.

Observation grouping uses **exact** recorded interval duration. This conservative
choice may fragment irregular HealthKit records and leave insufficient support.
It is preferable to silently mixing SDNN windows; clinically qualified window
compatibility and method bridging remain future work. Recorded sample interval
duration is not asserted to equal a vendor's internal calculation window.

The `features.meal_area` utility computes signed and positive incremental area
using supported bracketing segments only. It withholds whole-window results when
coverage is incomplete. It is a tested calculation primitive; no meal detector,
CGM ingest pipeline or intervention evaluator is implemented.

## Install and verify

Python 3.11+ is sufficient; no packages need downloading. Commands assume this
release directory is the current directory. `bash` runs the wrappers as child
processes and never closes an existing terminal.

```bash
bash install.sh "$HOME/mse-reference-0.1.0"
bash "$HOME/mse-reference-0.1.0/verify.sh"
```

The destination must not exist. Installation copies only manifest-verified files
to that new directory. It changes no repository branch, service, package manager,
database, environment configuration, credentials or automation schedule. Tests
write only to newly created temporary directories.

## Synthetic replay

Keep runtime data outside the installed code directory so retirement can verify
ownership. Pick a fresh run directory, then run:

```bash
mkdir -m 700 "$HOME/mse-demo-0.1.0"
cd "$HOME/mse-reference-0.1.0"
python3 -B -m mse import-healthkit examples/synthetic_healthkit_v03.json \
  --subject synthetic-person --source-instance synthetic-healthkit \
  --db "$HOME/mse-demo-0.1.0/evidence.sqlite"
python3 -B -m mse replay --db "$HOME/mse-demo-0.1.0/evidence.sqlite" \
  --output "$HOME/mse-demo-0.1.0/states.json"
```

The import is safe to repeat against this MSE database. Repeating the replay must
use a new output filename because existing JSON files are not overwritten.
`examples/synthetic_healthkit_v03.json` has 26 synthetic readings: 13 HR and 13
SDNN, every 15 minutes between 06:00 and 09:00 UTC on 1 January 2026. Its synthetic
anchors are opaque test bytes; they are not real HealthKit query anchors.

To inspect a **copy** of a real v0.3 archive, use `import-healthkit` with an explicit
pseudonymous subject, a stable archive-instance identifier and a new output DB.
The importer supports exactly the observed Swift numeric date representation.
It does not select a real archive automatically or access an iPhone.

`replay` supports only `--mode retrospective_snapshot`. The optional
`--source-receipt-cutoff` applies **one global final-snapshot filter** to recorded
`receivedAt`, completed interval ends and tombstones. It does not reconstruct a
separate knowledge set at each output's reference time. A late-received old
measurement can revise a retrospective estimate. Every run/state marks historical
source and MOTHER availability as unestablished; each state discloses the latest
supporting source receipt. `source_as_available` and online modes are unsupported
and refused, not approximated. No `as_of_event_time` field is emitted; the field is
`observation_reference_time` with policy `aggregate_interval_end`.

Native duplicate receipt changes retain the first persisted receipt while keeping
all raw artifacts. That order-dependent fact is another reason this prototype
does not claim historical availability authority. A future sequential replay
needs explicit source-receipt revision rules plus authoritative MOTHER ingestion
clocks, watermark/late-event behavior, and per-target knowledge cutoffs.

## Rollback

```bash
bash "$HOME/mse-reference-0.1.0/rollback.sh" "$HOME/mse-reference-0.1.0"
```

Rollback verifies the receipt, source hashes and absence of untracked files,
then renames the entire installation to a sibling `*.retired-<timestamp>-<id>`
directory. It deletes nothing. Modified or untracked code/data causes refusal;
retain and review those files before choosing another action. Restore by renaming
the returned retired directory to the original path only when that original path
is absent. Runtime data outside the installation are retained.

## Limits and promotion gates

Passing tests proves contract/software behavior for the included cases. It does
not prove biological identifiability, sensor accuracy, calibration of intervals,
causal effects, individual clinical utility or real-device reliability. This
prototype deliberately lacks a PF001/N3 adapter, a transport, real-time service,
fitted Bayesian hierarchy, circadian/activity/sleep model, mechanistic graph
runtime, N-of-1 experiment manager, dosing logic and production deployment.

Before a real use, qualify exported data and clock semantics, compare against
simple baselines on held-out longitudinal periods, calibrate predictive intervals,
add source-specific error models and explicit context, test retrospective versus
as-available replay, and establish an authoritative current-revision snapshot
contract. Individual scientific validation requires prospective measurements and,
for causal claims, appropriately controlled repeated interventions.
