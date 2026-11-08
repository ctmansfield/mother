# Coach and Mother physiology delivery board

Release increment: **PF-001 / 0.1.0**. Design basis: *Coach and Mother App
Development Handoff*, Version 1, and *Personal Physiology and Delivery
Prototype*, **Draft 0.11**, read 7 November 2026 (Pacific/Guam).

The PM/integration owner owns this board, shared schemas, time utilities,
migrations, compatibility manifest and release gates. Each task has one writer.
Worker results are integrated in dependency order; branch existence is not a
passed gate. See VERIFICATION.md for the final evidence level.

## Baseline and authority

| Item | Inspected state | Authority/limitation |
| --- | --- | --- |
| Coach main | `1dd63725dbed112fc33d9c9a64b60b1d7263c246`, fresh clean clone | Source baseline; deployed revision unknown |
| Mother main | `e4510efbb05f711f7fdc47fbab0fd6c19e8324fd`, fresh clean clone | Source baseline; deployed revision unknown |
| Design reconciliation | Draft 0.11 adds the software/design division to Draft 0.10 requirements | No later conflicting decision found in the current outline |
| Local deployed checkout | No NAS/LLM deployment mounted in this workspace | Remote uncommitted work remains unknown and must be preserved at installation |
| Existing analysis files | `storage/analytics/{cgm,treatments,windows}.parquet` are tracked | Provenance unverified; not representative personal validation data |
| Durable acquisition authority | New explicit archive path under the selected repository/storage root | Immutable records/revisions; Parquet is a derived compatibility view |
| API deployment | `mother_app.main:app` and `mother.api:app` launch paths both exist | Actual active family must be inspected before service integration |
| Devices/history | User reports Nightscout, Watch, H10 and spot meters | Exact source models, formats, overlap and supported live capabilities unverified |

## Dependency-aware backlog

| ID / milestone | Owner and owned paths | Dependencies | Acceptance / exit evidence | State |
| --- | --- | --- | --- | --- |
| B00 / M0 source reconciliation | Baseline worker; preflight report only | Handoff + design | Clean pinned clones, instructions, launch/data path inventory, hazards | Source inspected |
| C01 / M0 shared contract | PM; `mother/physiology/{__init__,contracts,time}.py`, `schemas/`, `migrations/`; Coach schema copy | B00 | Versioned observation/revision/stream/session/event/import metadata; strict time and missingness validation | Implemented; isolated checks passed |
| A01 / M1 analytics correctness | Analytics worker; `analytics/events/window_builder.py`, HRV adapter, rule miner, pipeline config, `analytics/tests/test_physiology_*` | C01 | Correct forward boundaries; unknown missing horizons; no feature leakage; timestamp parsing; method-specific HRV; default miner works | Integrated; isolated and synthetic checks passed |
| D01 / M1–M2 Nightscout archive | Archive worker; Nightscout adapter, `mother/physiology/archive.py`, `analytics/tests/test_archive_*` | C01 | Immutable originals/revisions; bounded complete acquisition or explicit failure; reimport/restart/history retention; atomic checkpoints | Integrated; synthetic archive/API fixtures passed; actual server gate open |
| U01 / M1 Coach flow hygiene | Coach worker; three malformed flows, flow README, explicit live-test gate | B00 | Strict JSON; canonical mirror preserved; no blanket CGM_SPIKE; offline fixtures; no notification during ordinary checks | Integrated; controlled fixtures passed; deployed flow reconciliation open |
| W01 / M3 import capability mapping | PM; bounded export readers, unit utilities, fixtures and capability documentation | C01, D01 | Explicit supported source mappings; raw files preserved; gaps, failures, unknowns and true lineage visible | Bounded readers integrated; synthetic checks passed; device/export qualification open |
| R01 / M3 synchronized replay | PM Mother replay producer; Coach worker replay consumer/tests | C01, D01, W01 | Synthetic end-to-end bundle; lineage, separate clocks, discrete anchors, epistemic states and gaps visible | Synthetic cross-app integration verified; browser visual review open |
| R02 / M3 real-data acceptance | PM + independent verification | R01 + overlapping exports | Small Nightscout/Watch/Polar episode reconciles with original sources | Blocked: representative source bundle unavailable |
| E01 / M4 evaluation harness | Analytics worker; evaluator module and tests | C01, explicit caller-defined endpoints | Chronological split, shared outcome grouping, label embargo, baseline comparison and uncertainty | Integrated; author and independent synthetic checks passed; no personal model claim |
| E02 / M4 personal performance | Independent evaluation | E01 + representative independent episodes | Later held-out episodes; per-channel error/coverage/calibration; no synthetic wearer claims | Blocked: data and endpoint eligibility |
| L01 / M5 live acquisition | Device workstream after replay | R02 + verified device/server capabilities | Freshness, interruption/restart, buffered reconciliation, archive agreement | Blocked: actual integration capability and runtime evidence |
| I01-P / manual event draft | Coach interaction owner; Coach [PR #2](https://github.com/ctmansfield/coach/pull/2) | C01 | Factual event, typed links, nulls and separate actions/outcomes | Synthetic acceptance passed; draft only |
| I01-D / durable manual ingestion | Mother acquisition owner; Mother [PR #5](https://github.com/ctmansfield/mother/pull/5) | C01, I01-P | Immutable source revisions and original bytes, idempotent restart and replay | 10 synthetic tests passed; no live service |
| I01-T / offline cross-app handoff | Coach sender [PR #3](https://github.com/ctmansfield/coach/pull/3) and Mother receiver [PR #6](https://github.com/ctmansfield/mother/pull/6) on separate branches and exclusive files | I01-D, I01-P | Versioned packet, SHA-256 integrity, explicit private file, pinned paired test, restart/replay; no network | Coach 10 offline and Mother 9 paired + 10 archive tests passed in dedicated CI; reviewed drafts |
| I01-U / offline capture interface | Coach UI owner; Coach [PR #4](https://github.com/ctmansfield/coach/pull/4); Mother verification [PR #7](https://github.com/ctmansfield/mother/pull/7) | I01-T, contract 1.0.0 | Offline accessible form and typed event relationships, exact event bytes, pinned crossrepo restart/replay, no network | Implemented in draft; Coach 11 offline + Mother 4 pinned UI→archive and 9 receiver tests passed; Coach [PR #5](https://github.com/ctmansfield/coach/pull/5) added 7 passing real Chromium browser checks and reviewed synthetic desktop/mobile screenshots; other assistive-technology and deployment QA open |
| I01-R / lost-receipt recovery | Mother archive worker; [PR #8](https://github.com/ctmansfield/mother/pull/8) `receipt_recovery.py`, focused synthetic tests, separate CI and docs | I01-D, I01-T, I01-U | Source-verified receipt after archive commit; deterministic protected file; idempotent retry after receipt-write failure and SQLite restart; no early deletion | **Implemented; 12 recovery + 4 pinned Coach UI + 10 ingestion tests passed in dedicated CI**, Black/Ruff passed, full event/source attestation; no live transport or NAS check, no live transport or NAS check |
| I01 / interaction completion | Future authorized live transport and QA owners; no existing service edits | I01-U2, deployed runtime reconciliation, identity/subject policy, assistive-technology QA; factual trigger policy for later automatic questions | Authenticated ingress and permission checks, user-facing saved/acknowledged confirmation, pending outcomes unknown; controlled deployment | **Open:** no authenticated API, browser visual acceptance, automatic questions, or deployed workflow |
| V01 / release | Independent worker (no authoring of reviewed Mother fixes); PM integration | C01/A01/D01/U01/R01 | Compatible revisions, adversarial fixtures, clean apply/install, repeatable VERIFY, documented limitations | Independent source/synthetic gate passed; final bundle evidence recorded separately |

The I01-T offline handoff has completed its synthetic gate without access to
the restored NAS installation. User has deferred host checks, original exports
and local-LLM worker qualification. No deployed system has been modified.
The next I01 task is **authentication/subject authorization design and a
controlled capture UI** after deployment reconciliation; it is not a reason
to enable live endpoints during routine development.

## Next bounded assignments

The immediate critical path is R02 → source backfill/episode qualification →
E02, with L01 depending additionally on real runtime and capability evidence.
No blocked design choice prevents retaining and replaying qualified originals.

| Next assignment | Owner / exclusive files | Input and acceptance | Return |
| --- | --- | --- | --- |
| Qualify one real interval (R02) | Acquisition worker; new source qualification manifest and tests/fixtures approved for repository use; no raw personal files committed | Original Nightscout/Watch/Polar overlap; reconcile counts, clocks, units, native IDs, relays, sampling and gaps | Source hashes, field map, accepted/rejected counts, uncertainties, exact replay revision |
| Freeze target/group proposal (E02 prerequisite) | Analytics worker; new versioned episode recipe after design disposition; no schema edits | Qualified R02 profile; explicit exercise cessation, actual sleep linkage and independent group rules | Concrete target/eligibility options with coverage consequences; frozen split proposal |
| Runtime reconciliation (L01 prerequisite) | Baseline/runtime worker; read-only report | Actual repo HEAD/status, running launch family, mounts, archive filesystem, existing flow export and API capability evidence | Difference from release manifest; preservation plan; bounded deployment/rollback verification |
| Complete context interaction (I01) | Coach worker; new annotation workflow only | Existing contract plus selected factual trigger policy; synthetic tests can proceed before a live trigger is enabled | Durable event/answer path, no-response unknowns, no notifications in ordinary tests |

These are assignments ready for the next inputs, not claims that workers are
running indefinitely after this delivery.

## Ownership and worker return contract

Analytics and acquisition use separate Mother worktrees. Coach has its own
worktree. Only the PM changes shared contracts, migration files or release
manifests; workers request changes with a concrete failing case. The final
reviewer must identify which components they authored, and independently review
the other components. PM tests the Coach changes independently.

Every return contains task ID; owned paths; base/head commits; purpose; exact
commands and exit results; fixture assumptions; unresolved failures; interface
and migration implications; and a reviewable commit/patch. Worker claims are
rechecked in the integrated branch before release.

## Design boundaries

Passive observations are primary. Factual questions are selective annotations,
not routine readiness labels. Measurements, vendor derivations, imputation,
inference and clinical interpretation remain distinct. Recommendations,
acknowledgments, actual actions and outcomes remain separate. Baseline departure
does not imply dysfunction. No compound, route, dose, therapeutic control,
garment material, sensor choice or new collection burden is selected here.

The exact first physiological endpoints and sample/coverage eligibility are
design decisions. Current glucose-event labels remain legacy glucose targets;
they are not renamed as post-exercise recovery. UTC in old historical
configuration is an explicit engineering fallback, not assumed wearer history.

## Evidence states

Use **source inspected**, **implemented**, **isolated-test verified**,
**synthetic integration verified**, **real-data integration verified**,
**deployed** and **live verified** separately. Mocked APIs do not establish
installed Nightscout behavior. Repository tests do not establish device
capability, personal model performance or production persistence.
