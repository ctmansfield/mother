# Related MOTHER / COACH repository audit

Audit date: 13 November 2026, Pacific/Guam. Read-only GitHub inspection and local source inspection. No repository, deployment, credentials, production data, or automation schedules were changed. This is a supporting audit for the MSE architecture report, not a deployment attestation.

## 1. Verified references and branch separation

GitHub branches API and commit comparisons were read during this audit. Both main branches remain older than the physiology work. Source presence on a feature branch is not evidence of merge or deployment.

| Repository / branch | Verified full SHA | Finding |
|---|---|---|
| `ctmansfield/mother`, `main` | `e4510efbb05f711f7fdc47fbab0fd6c19e8324fd` | Latest main commit dated 2025-10-30, "Fix hooks; prep full analytics + coach commit". |
| MOTHER `work/physiology-foundation-pf001` | `5a6f71a45dc64880bc06a0e1a50c7d05ff119cba` | Additive raw archive, evidence contract, export readers, replay and corrected analytics. |
| MOTHER `work/i01-capture-ui-crossrepo-acceptance` | `780e0a4e8c43662b33bb015e05fb333630f6c25d` | 28 commits ahead of main, 0 behind; includes PF001 and offline manual-event ingestion/handoff. |
| MOTHER `work/i01-offline-receipt-recovery` | `0343294346f4b8d885bd7ce032d4db6f49c54499` | Offline lost-receipt recovery, descendant of capture branch. |
| MOTHER `work/i01-delivery-state-readonly` | `81c3fcceadcf5bf7462bf813427b98e4f87721e0` | 36 commits ahead of capture branch, 0 behind: latest inspected I01 descendant. |
| MOTHER `work/r02-source-qualification-01` | `03e422075d584ff5de92578bacb4749f94412f4c` | Separate PF001-derived source-qualification preflight, not automatically present in I01 branch. |
| `ctmansfield/coach`, `main` | `1dd63725dbed112fc33d9c9a64b60b1d7263c246` | Legacy motivation/reminder client and Node-RED/Nightscout configuration. |
| COACH `work/physiology-foundation-pf001` | `1b0ba6faa89c52d2a85452b07339b846b92d1ad0` | Source-aware replay and controlled preview. |
| COACH `work/i01-capture-browser-qa` | `1900d64b4b73706bd0a06871985502b8967f2911` | 28 commits ahead of main, 0 behind; offline factual capture, original-byte envelope and browser QA. |
| COACH `work/i01-delivery-status-view` | `184606fe9d5022997f09a2e4d6ef38e5dca4a9bc` | Latest delivery-status branch shown by GitHub. Its corresponding MOTHER acceptance is source/synthetic, not authenticated live transport. |

Other verified MOTHER branches are `work/i01-durable-manual-events` (`072b157...`), `work/i01-offline-event-receiver` (`0f0ee327...`), `work/local-worker-qualification-lw001` (`83cede18...`) and `work/local-artifact-qualification-lw002` (`b39b45c...`). Their existence does not activate a worker or service.

The previous local snapshots under `/workspace/scratch/572703d71a95/repos/{mother,coach}` are clean main snapshots at those same main SHAs. Related local worktrees contain unpushed integration ancestry. Critically, local MOTHER `154852ba8a9cd6499f19bcfb0a512b8845609756` and published PF001 `5a6f71a...` were independently confirmed to have the identical Git tree `0fb8e9e16514d7a4b9a96729873a8116827465c3`. That permitted a bounded rerun of existing evaluation tests without modifying the repositories.

## 2. Current code on main

### MOTHER application interfaces

At main `e4510ef...`:

- `mother_app/main.py:30–45` attempts a PostgreSQL connection at import and falls back to in-memory stores if unavailable. This is not a durable physiology-ingestion protocol.
- `mother_app/main.py:103–160` defines `/api/reminders`; `:257–277` defines `/api/behavior/events`. The behavior event body is an untyped dictionary, receives a generated UUID, and can remain only in process memory.
- `mother_app/main.py:164–188` defines `/api/models/predict`. `adherence_risk_v1` is a simple heuristic and `energy_window_v1` returns fixed clock windows; metadata explicitly says `stub-0.0.1`. Neither is a learned metabolic-state estimate.
- `mother_app/main.py:191–219` serves offline rules through `/risk/rules` and `/risk/score`. Rule `action` strings can become `suggestions`; this path does not supply intervention eligibility, uncertainty, causal identification, or a physiological treatment policy.
- `mother/api.py` is a different FastAPI app with memory/nudge endpoints, and `mother/app/api.py` is another app for memory/chat. These alternate launch families must be reconciled before adding an endpoint to a deployed runtime.
- `Dockerfile` copies only `mother_app` and starts `mother_app.main:app` on port 8080. It does not package `mother/physiology` or the analytics modules. Building this existing image does not deploy PF001 or a proposed MSE module.
- `docker-compose.stack.yml` defines Redis, Mailhog, MOTHER, COACH and health_portal configurations. These are source configurations, not evidence of the user's running instances.

`mother_app/main.py:65–71` has permissive CORS, and the inspected handler set does not implement scoped physiology authorization. The proposed MSE API should not simply expose new physiological records through this legacy handler without a proper identity/grant layer.

### COACH interfaces

At main `1dd6372...`, `coach_app/clients/mother.py:3–13` uses `MOTHER_BASE_URL` and HTTP POSTs for `/api/models/predict` and `/api/reminders`. `coach_app/cli/plan_now.py:14–32` supplies fixed example adherence features, selects motivational suggestions and creates up to three reminders. This is reusable coordination scaffolding, but it does not estimate metabolism or establish intervention effects.

Node-RED, Home Assistant, Nightscout and Mongo are present in files under `vm/coach/docker/`. Configuration presence is not a qualification of live CGM coverage, device reliability, or authenticated future physiological ingestion.

## 3. Reusable PF001 scientific evidence layer

Authoritative source files inspected at MOTHER `780e0a4...`, retained unchanged in the inspected I01 descendant unless stated:

- `mother/physiology/contracts.py`
- `mother/physiology/schemas/v1.schema.json`
- `mother/physiology/migrations/0001_archive.sql`
- `mother/physiology/archive.py`
- `mother/physiology/imports.py`
- `mother/physiology/evaluation.py`
- `docs/physiology/CONTRACT.md` and `CAPABILITIES.md`

### Existing entities and clocks

The version `1.0.0` contract already defines `source_revision`, `observation`, `stream`, `session`, `event` and `import_run`. Reuse these concepts and identifiers instead of starting a parallel observation ontology.

An observation has subject, exact channel/native type, measurement start/end, original and normalized value/unit, validity, epistemic type, source revision/lineage, method, device, recording app, specimen, body site, session/group, quality flags, processing version and clock metadata. `contracts.py:76–85` requires the source revision in observation lineage and requires a method for derivatives/inferences. UTC/offset handling is explicit; the contract distinguishes measurement, genuine source availability, first-seen and durable ingestion time.

Existing epistemic labels are `measured`, `vendor_derived`, `derived`, `imputed`, `inferred`, `clinical_interpretation`, and `reported`. Sleep classification is vendor-derived; sparse SDNN is not relabeled RMSSD. An MSE state should be a new state-estimate object linked to these records, never a rewrite of the input's epistemic type.

### Actual SQLite schema

`mother/physiology/migrations/0001_archive.sql` defines:

| Table | Actual purpose / key fields |
|---|---|
| `schema_versions` | integer version, contract version and application time |
| `import_runs` | source instance/collection, adapter/schema versions, request/count JSON and running/complete/incomplete/failed status |
| `raw_artifacts` | SHA-256 primary key, original BLOB, media type and creation time |
| `source_revisions` | immutable revision ID; source instance + collection + source key + revision hash unique; original canonical record, native ID, source timing, measurement interval, disposition, run and original-artifact hash |
| `normalized_records` | record ID, revision FK, kind, record JSON, processing version |
| `run_revisions` | repeated sightings of a revision per import run |
| `source_heads` | current revision per source namespace/collection/key, including reversion to an old revision |
| `checkpoints` | source collection checkpoint JSON and associated completed run |

`archive.py:64–65` enables foreign keys and synchronous FULL. `:154–409` performs transactional batch validation, raw-hash verification, revision insertion/idempotency, head updates and checkpoint updates. The archive preserves originals and rejects mismatched immutable IDs at the application layer; there are no SQL write-once triggers in the inspected migration, so this is a contract and controlled-writer guarantee rather than protection against arbitrary privileged SQL mutation.

`records(current=True)` joins source heads; historical revisions remain available with `current=False`. Partial response absence is not a deletion. Explicit deletion dispositions may change the current projection. Inference workers should use a read-only connection or immutable replay snapshot rather than constructing the writable Archive against a production path.

The archive is SQLite; Parquet is a derived compatibility view. Nothing in this proposal requires moving the separate genomics PostgreSQL stack or adopting an unqualified network-mounted SQLite database.

### Implemented acquisition boundaries

`imports.py:32–47` allows Apple XML HR/resting HR/exact SDNN-or-RMSSD identifiers/respiratory rate/wrist temperature/SpO₂/glucose, and manual spot BP/lactate/ketone fields. A recognized string does not prove a real device supplies it. For example, an accepted RMSSD identifier is a parser allowlist entry, not a claim Apple Watch currently provides an RMSSD channel.

Apple XML reader (`imports.py:69–79, 138–225`) uses native UUID when present, otherwise an ambiguity-marked identity; retains source app/version/device metadata and `creationDate` without treating it as historical availability. Workouts and sleep remain vendor-derived events. TCX (`:82–116, 226 onward`) preserves exported HR and recording extent; it neither identifies an H10 without evidence nor reconstructs RR/ECG from averaged HR. Spot CSV (`:119–124`) is a defined interchange format, not a working Omron/ketone/lactate Bluetooth driver.

The Nightscout reader at `analytics/preprocess/sources/nightscout_adapter.py` supports read-only v1 acquisition into the archive, captures original pages and revisions, and uses bounded interval subdivision to avoid guessed pagination. `NightscoutV1Client` requires instance-specific bounded-query/count capability evidence. No source code alone proves the installed Nightscout's count caps, correction semantics or complete lifetime history.

There is no inspected working CPAP, beat-to-beat H10/BLE ECG, microbiome or mechanistic laboratory acquisition pipeline in these branches. The stream descriptor provides an extensible place to reference original waveform/beat artifacts when adapters are actually implemented and qualified.

## 4. Existing feature/evaluation code

PF001 modifies `analytics/events/window_builder.py` and `analytics/preprocess/sources/hrv_adapter.py`. These are valuable reusable foundations:

- Features are restricted to observations available by the cutoff; explicit retrospective assumptions remain flagged.
- Glucose future labels require future measured coverage instead of converting missing targets into negatives (`window_builder.py:426–549`).
- HRV series are separated by metric and required to be homogeneous in source/device/app/method/window (`:266–328`). A historical median is computed from preceding bins, not future data.
- Individual baselines here are limited summaries, not a calibrated latent physiology model.

`mother/physiology/evaluation.py` is explicitly a **context-free scalar training-median baseline**, consuming no episode features. It groups repeated/shared outcomes, purges groups crossing the chronological split, requires labels to have been available before model fitting under strict policy, reports missing/ineligible outcomes separately, and reports MAE/RMSE. Its empirical training quantile interval is explicitly `uncalibrated_empirical_range` (`:442–451`), not a calibrated Bayesian credible interval.

This is a suitable comparator and leakage-control foundation for a new model. Passing it does not validate a biochemical mechanism, clinical state, prediction model on real data, or an intervention effect.

The R02 branch's `mother/physiology/qualification.py` adds offline replay quality/lineage summaries and flags same-value/time cross-source samples as review candidates rather than automatic duplicates. It does not qualify original sensors or claim completeness; its documentation says actual original exports are still needed for R02 acceptance. Do not assume the separate R02 branch is already merged into I01.

## 5. Existing intervention-adjacent event structure

COACH `coach_app/physiology/manual_events.py:16–30, 51–125` separates facts:

- `answer` requires a `question` parent.
- `acknowledgment` requires a `recommendation` parent.
- `reported_action` optionally refers to a recommendation/acknowledgment.
- `outcome` requires a reported or observed action parent.

An acknowledgment never becomes proof an action occurred. Absence never becomes an adverse or negative outcome. All user-entered events remain `reported`.

MOTHER `mother/physiology/manual_ingest.py` checks these parent types and same-subject relationships before adding original bytes, source revision and normalized event transactionally. Repeating identical bytes is idempotent; changing content under an existing event ID is rejected. These are useful exposure/response provenance primitives, but not a scientific intervention registry or causal-effect estimator. Add explicit hypothesis, experiment, eligibility, exposure and analysis-result contracts alongside them rather than flattening these distinctions.

## 6. Existing delivery and durability semantics

COACH `coach_app/physiology/handoff.py` creates a versioned bounded original-byte envelope and publishes a private content-addressed local outbox file using exclusive publication and fsync. It explicitly says it is not authenticated network transport. MOTHER `mother/physiology/handoff.py` checks envelope format/digest and archives the original event. A digest provides integrity, not sender authentication.

At MOTHER `81c3fcce...`, `receipt_recovery.py` handles a lost receipt after a committed event by retrying unchanged original bytes, verifying exact archived revision/projection/original bytes, and creating a deterministic local receipt. `delivery_state.py` uses SQLite read-only/query-only snapshot inspection and distinguishes prepared, delivery unknown, archive verified with missing/valid/invalid receipt, and conflict. A copied report remains unauthenticated; it never authorizes deleting originals. This is directly reusable reasoning for at-least-once physiological batch transport, although no such network batch protocol is implemented here.

## 7. N3 glucose server: documentary evidence and inspection limit

Current source records at [production-framework issue 42](https://github.com/ctmansfield/production-framework/issues/42) and [issue 50](https://github.com/ctmansfield/production-framework/issues/50), including their November 12 comments, describe an N3 glucose-read `1.0.0-draft.2` server pin `59a6ce9c0a4fb303e13302ed38deaaacdded277d` and a Swift client draft PR. The contract manifest is `059f57df93331bd29608edfbe43c3df3eddce1de0ef4d2633258c5a92f679960`. They report a 36,767-record archived NAS projection and fixed historical acceptance windows 288/318/318 rows. These are project-reported acceptance targets, not independently queried source data in this audit.

The exact N3 server commit was requested from both `ctmansfield/mother` and `ctmansfield/production-framework`; both returned `422 No commit found`. Accessible repository search for `mother` returned MOTHER and the health bridge only. No N3/glucose server file was found in the current local scratch tree. The coordination comments themselves state a FORGE launcher commit was not resolvable in checked repositories and request exact source/ref. Thus **the N3 server's implementation, database and deployment cannot be independently audited from these accessible references**. Do not invent its schema or claim it is absent from the user's systems.

The hub distinguishes reported synthetic loopback HTTPS acceptance from real NAS historical acceptance, which remains separately skipped/pending in the cited comments. The signed-in Simulator rehearsal authorization in those comments belongs to another session and is not an action undertaken by this audit. Read-only Swift glucose display is not proof of a health acquisition upload path.

## 8. Verification actually performed here

1. GitHub branch lists and current commit comparisons; exact SHA/tree evidence retained.
2. Read actual relevant source/schema/SQL/docs from pinned feature commits and matching local main snapshots.
3. Verified the local PF001 integration tree equals published PF001 tree `0fb8e9e...`.
4. Reran existing scalar-baseline and independent leakage tests using the existing isolated environment:

```bash
cd /workspace/scratch/572703d71a95/worktrees/mother-integration
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /workspace/scratch/572703d71a95/.venv-release/bin/python -m pytest -q tests/physiology/test_evaluation.py tests/physiology/test_evaluation_independent.py
```

**Observed result: 35 passed in 0.05 s.** No device, real data, production service or network request is involved in those tests.

An earlier invocation with the default Python failed to import pytest; it was an environment/dependency failure, then resolved by using the existing isolated release environment. The initial `unittest` discovery was not a suitable runner for those pytest modules. These failures are retained here rather than silently claiming the first attempt succeeded.

The legacy `.github/workflows/ci.yml` on MOTHER main uses `|| true` for installation, verification and pytest, so its green status alone would not establish tests passed. Use dedicated newer gates or exact locally executed tests and inspect counts/failures.

## 9. Consequences for MSE integration

1. **Preserve acquisition and authority.** Consume PF001 normalized records/current revision references and the bridge's real read/export boundaries; do not replace JSON authority or declare N3 upload functionality.
2. **Add a separate inference layer.** Proposed `mother/mse/` should read versioned evidence snapshots and write derived features, state estimates, unknown/observability reasons, model/run manifests, hypothesis sets and measurement requests to a separate selected store.
3. **Reuse evidence and replay.** Existing raw artifacts, source revisions, precise clocks, quality flags, event parent semantics and baseline evaluation prevent a second incompatible foundation.
4. **Version contracts explicitly.** MSE state/measurement-request/intervention objects should have their own namespace and version; PF001 1.0.0 consumers must not unexpectedly receive a new record type.
5. **Resolve branch/deployment integration before service wiring.** PF001/I01/R02 remain distinct source increments; production packaging and existing endpoint ownership are not settled by this audit.
6. **Require actual source qualification for stronger states.** CGM + sparse HR/SDNN permit context-sensitive physiological response descriptions; they do not identify insulin sensitivity, substrate oxidation, inflammation, mitochondrial function or microbial flux without additional identifying measurements.

## Pinned source links

- [MOTHER PF001 archive schema](https://github.com/ctmansfield/mother/blob/5a6f71a45dc64880bc06a0e1a50c7d05ff119cba/mother/physiology/migrations/0001_archive.sql)
- [MOTHER evidence contract](https://github.com/ctmansfield/mother/blob/780e0a4e8c43662b33bb015e05fb333630f6c25d/docs/physiology/CONTRACT.md)
- [MOTHER import readers](https://github.com/ctmansfield/mother/blob/780e0a4e8c43662b33bb015e05fb333630f6c25d/mother/physiology/imports.py)
- [MOTHER scalar baseline evaluator](https://github.com/ctmansfield/mother/blob/780e0a4e8c43662b33bb015e05fb333630f6c25d/mother/physiology/evaluation.py)
- [MOTHER delivery-state source](https://github.com/ctmansfield/mother/blob/81c3fcceadcf5bf7462bf813427b98e4f87721e0/mother/physiology/delivery_state.py)
- [COACH manual event constructors](https://github.com/ctmansfield/coach/blob/1900d64b4b73706bd0a06871985502b8967f2911/coach_app/physiology/manual_events.py)
- [COACH offline handoff](https://github.com/ctmansfield/coach/blob/1900d64b4b73706bd0a06871985502b8967f2911/coach_app/physiology/handoff.py)
- [MOTHER R02 qualification](https://github.com/ctmansfield/mother/blob/03e422075d584ff5de92578bacb4749f94412f4c/docs/physiology/R02_QUALIFICATION.md)
