# Development action log

Dates use Pacific/Guam for user-facing project records. Test logs retain UTC.

## 7 November 2026 — PF-001

1. Read handoff Version 1 and current design Draft 0.11, including the latest
   division of software and system-design responsibilities. Reconciled the
   older Draft 0.10 handoff basis before implementation.
2. Inspected both GitHub branch inventories and cloned fresh clean source
   baselines. Found no authorized deployed checkout or runtime mount here.
   Preserved the original clones and used isolated worker worktrees.
3. Inspected launch paths, tracked data paths, repository change conventions
   and notification tests. Recorded multiple Mother launch families and
   unverified tracked Parquet provenance. Avoided live notification tests.
4. Assigned bounded analytics, archive and Coach tasks with exclusive file
   ownership, dependencies and acceptance criteria. Reserved shared schemas,
   time utilities and migrations to the PM.
5. Reproduced forward-window, timestamp, cutoff-resampling, meal-age,
   default-miner and rolling-history defects with synthetic inputs. These are
   source/test findings, not assertions about deployed services.
6. Added contract 1.0.0, strict UTC normalization and additive SQLite migration.
   Twenty-one initial contract/time/migration checks passed. Added explicit
   deletion-marker support before release and prevented validation errors from
   dumping source payloads.
7. Created a dedicated verification environment with pytest, pyarrow,
   jsonschema and requests, reusing installed scientific dependencies. Exact
   verification versions are recorded in the release evidence.

8. Integrated bounded analytics and archive worker commits. Added offline
   Apple/TCX/spot readers, original artifact retention and replay production.
   Integrated Coach's validated consumer, canonical schema copy, import
   accounting and explicit notification-test gate.
9. Executed the four-source synthetic archive-to-HTML path and an installed
   package demo outside the source checkout. Kept original tracked Parquet
   history outside personal validation claims. Browser binary installation
   failed; visual layout review remains explicitly open.
10. Independent review passed 108 checks but added five failing regression
    cases. Fixed partial coverage, untimed events, session persistence/lineage,
    event processing identity and package-relative resources. Independently
    reverified the fixed implementation with 146 passing checks. Added five
    further independently passing evaluation cases to the integrated suite.
11. Integrated the generic grouped chronological baseline evaluator. Recorded
    endpoint, episode-anchor, availability and representative-evaluation gaps
    for the design session without selecting a recovery score or policy.
12. Prepared isolated patch installation and exact-tree offline verification.
    Independent packaging probes reproduced local hook and untracked Python
    shadowing failures, then passed nine cases after correction. Final exact
    bundle execution and paired revisions are recorded in its manifest and
    verification logs.

No deployment, credential change, notification, device capture or personal-data
evaluation is implied by this log. The optional old MI/bootstrap run was stopped
with exit 130 and is not a passed acceptance gate.


## 7 November 2026 — I01-T offline cross-application handoff

1. Rechecked Mother PF-001 and I01-D, Coach PF-001 and I01-P source branches
   and their open draft PR states before writing. Chose explicit file transfer
   rather than making runtime/authentication assumptions while the NAS was
   being restored.
2. Coach outbound owner created a canonical, SHA-256-pinned manual-event
   envelope and private, content-addressed outbox writer. A security review
   added refusal of pre-existing world-readable output files.
3. Mother ingest owner added a strict packet decoder and optional CLI with
   mandatory input/archive paths. It verifies exact event bytes and delegates
   contract, parent and durable revision validation to the existing Mother
   ingestion path. No schema or migration was changed.
4. Independent verification pinned the actual Coach source revision and ran
   nine paired Coach→Mother archive/restart/replay checks plus the ten existing
   Mother ingestion regressions; the Coach sender passed ten isolated tests.
   Dedicated GitHub Actions, Mother general CI and Black/Ruff passed.
5. Published review-only draft branches, explicit INSTALL/VERIFY docs, and
   updated task-board dependencies. Actual network transport, sender
   authentication, user interface, deployed NAS configuration and personal
   source data remain separate unverified gates.

Verified pinned Coach sender:
`9fbe9b1580203be78ac8e06ae12dfae9f882c24d`.
Paired Mother receiver test revision:
`daa56f12c31f6794e24da0118a0e25067782234b`
(followed by documentation-only revisions).

This increment does not claim deployment, live operation, or therapeutic
efficacy. No credentials or running services were altered.


## 7 November 2026 — I01-U offline user-facing capture

1. Reconciled Coach I01-T1 and Mother I01-T2 draft heads, retaining the
   existing single-owner shared contract 1.0.0 and archive migration.
2. Coach interaction owner added a static, offline factual-event form and
   deterministic, Unicode-safe browser envelope producer. Unknown clocks
   remain unknown, recorded time is the browser's stated clock, and typed
   parent links never infer an action or outcome. No automatic prompts or
   subjective readiness scores were introduced.
3. Independent Node acceptance verified 11 synthetic cases including exact
   event/envelope bytes, timestamps, calendar rejection, UTF-8, null values,
   parent kinds, and a no-network page policy.
4. Mother integration worker pinned the actual Coach JavaScript builder
   at `6ab02988c44e3069d5b5e6ef4bca4966330b3d8e` and verified
   four synthetic UI→Mother archive/restart/replay cases, alongside the
   existing nine receiver cases. Black/Ruff and general CI passed.
5. Updated the versioned task board and review documentation. Browser
   visual/download behavior, authenticated subject ingress, actual data,
   installed NAS revisions, and service deployment remain unverified.

No personal data or production service was used; no credential or database
migration was changed. Offline event export does not establish archival
receipt.


## 8 November 2026 — I01-R durable offline receipt recovery

1. Reconfirmed Coach I01-U2 and Mother I01-U draft bases. No live NAS
   connection, credentials, application services, or personal datasets
   were inspected or changed.
2. Built a bounded synchronous Mother receipt writer/verifier. A receipt is
   generated **only after** immutable event archival and direct verification
   of the selected source revision, normalized event and original bytes.
   It is deterministic and stored privately without overwriting an
   incompatible existing file.
3. Added an explicit crash window simulation: an exception after source
   archival but before receipt persistence. Reopening the archive and
   retrying the **same original envelope** yields exactly one normalized
   event and the expected deterministic receipt.
4. Added tests rejecting false archive attestations, modified original
   bytes and altered normalized event fields, missing event parents, receipt-content tampering, symlinked or
   world-readable existing receipts, oversize packets, and invalid CLI
   input that must not create an archive.
5. Dedicated GitHub Actions pinned the actual Coach browser sender at
   `1900d64b4b73706bd0a06871985502b8967f2911` and passed
   **12 recovery + 4 UI integration + 10 archive regression tests**.
   Black/Ruff also passed after corrective formatting.
6. Documented INSTALL, VERIFY and the outstanding authorization/queue/
   network-runtime decisions. No shared schema or migration changed.

This is **offline synthetic integration**, not authenticated live delivery.
The sender retains its original envelope; no implicit spool cleanup or
medical inference is added. Production NAS behavior remains unverified.
