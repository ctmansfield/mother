# MSE and HealthBridge integration implementation plan

Plan ID: MSE-INTEGRATION-20261120-01 · Revision 1

Status: active team focus; first increment is offline source implementation and review.
Authority: Chad requested that MSE and this integration become the team's focus and that GADGET break down implementation and assign work. [Requirements PR #23](https://github.com/ctmansfield/mother/pull/23) remains the requirements baseline; requirements are proposed until reconciled. This plan permits bounded local synthetic implementation and draft PRs, not deployment or personal-data ingestion.

## First result to deliver

A deterministic, offline path from a synthetic captured HealthArchive through preserved artifact custody and versioned normalization to a MOTHER physiological evidence snapshot, then into the existing MSE reference interface. It must retain source identity, tombstones, explicit unknowns and failure evidence. No live phone, model server, GPU, real health data or service is needed.

Do not recreate the MSE or PF-001 archive. Reuse their qualified seams when they fit; document missing interfaces. MOTHER PR #18 is open at `b4e70b7123689ec164ba09e2974645ae36b184a2` and is a source dependency, not mainline. Main observed `c05f38096406965496d7d4a09edf4b3575235311`; requirements head before this plan `9a0984ec7d128c5bf77c3ff3dbe1b72581fe46e3`. Recheck before branching.

## Sequence and gates

| Stage | Result | Exit evidence and next action |
| --- | --- | --- |
| A — contract and source reconciliation | Map all 30 requirements to existing code/evidence/gaps; identify PF-001/MSE schemas and select offline interface versions | ATLAS contract matrix and exact source pins; GADGET reviews a shared contract before downstream authors freeze interface code |
| B — synthetic vertical slice | Captured JSON adapter, artifact/acceptance ledger harness, snapshot-to-MSE bridge and independent fixture pack | Exact-head offline end-to-end tests; no invented metadata, skipped tombstones, duplicate authority or writes to original source |
| C — recovery and model boundary | Durable transport/outbox design and isolated prototype, recovery faults, authorized snapshot query/derived-result boundaries | Lost-response/retry/conflict/restart/invalidation evidence; independent security review; model-offline acquisition remains functional |
| D — storage/operations decision | Resolve host/volume/database/artifact storage, retention, backup/RPO/RTO, service and credential ownership | Chad accepts concrete ADR choices; isolated synthetic restore passes before proposing live service |
| E — bounded live pilot | Specifically authorized source interval, destination, retained artifacts and complete reconciliation | New explicit authorization; actual custody/normalization/model-visible evidence and independent cleanup/rollback |

Only A and local synthetic B implementation are dispatched now. C design and local fault harness preparation may proceed; C production transport, D infrastructure operations and E are not activated. No main merge is implied. No private-host inventory, GPU activity, downloads or benchmark changes are part of these assignments.

## Worker assignments and file ownership

Each worker uses an isolated checkout/topic branch in `ctmansfield/mother`, reads current root instructions and requirements, checks its owning receipts, ACKs exact instruction/scope, and returns source SHA, tests passed/failed/skipped, evidence and next dependency. Draft PRs must target a coherent base and disclose dependency PRs. Do not merge PR #18 or another worker's code, force-push, edit immutable reference content, or modify shared runtime state. GADGET serializes integration and shared context/index edits.

| Worker | Immediate assignment | Owned paths / deliverable | Dependency and acceptance |
| --- | --- | --- | --- |
| ATLAS | Inventory current PF-001, HealthArchive and MSE contracts; map ACQ/ING/STO/LLM requirements and D-01–D-08; propose shared adapter/receipt/snapshot interfaces | `docs/mse/integration/CONTRACT_RECONCILIATION.md`, `docs/mse/integration/contracts/` | First contract draft unblocks ORACLE/FORGE. Preserve measured/derived/unknown, time and deletion semantics; exact pins and explicit incompatible fields |
| ORACLE | Implement read-only synthetic captured-HealthArchive adapter and versioned normalized export, without changing iOS acquisition | `integrations/healthbridge/`, `tests/integration/healthbridge/` | Inspect/design immediately; freeze interface after ATLAS draft. Original bytes unchanged, coherent snapshot, UUID/source namespace, tombstones, loss report and deterministic mapping |
| FORGE | Implement isolated received-artifact/receipt-ledger harness and PF-001 archive seam reuse; no HTTP listener yet | `integrations/mse_ingest/`, `tests/integration/mse_ingest/` | Pin PF-001 dependency; no parallel incompatible archive. Identical retry stable, conflict rejected, reopen integrity, interrupted artifact/ledger commit recovery |
| NICKY | Build independent synthetic source fixtures and acceptance matrix; test adapter/receipt/MSE boundary as heads arrive | `tests/fixtures/mse_integration/`, `tests/acceptance/mse_integration/`, `docs/mse/integration/ACCEPTANCE.md` | Unique synthetic identities, expected UUID/revision/tombstone sets; partial/empty/malformed/late/conflicting cases; no phone or protected collector access |
| PROVENANCE | Map evidence snapshot to existing MSE reference input and implement an external bridge if feasible; maintain lineage/loss manifest | `integrations/mse_snapshot/`, `tests/integration/mse_snapshot/`, `docs/mse/integration/LINEAGE.md` | Preserve original reference tree; bind snapshot/adapter/code/model identities; outputs stay derived, missing fields unknown; replay exact synthetic inputs |
| PHOENIX | Prepare storage/operations ADR options and local synthetic backup/restore rehearsal design/harness | `docs/mse/integration/STORAGE_OPTIONS.md`, `tools/mse_integration/recovery/` | D-01–D-08 recommendations with tradeoffs and unknowns, estimated synthetic scale, RPO/RTO choices, restore checks. No host/VM/service/credential actions |
| SENTINEL | Independently review contracts and threat/failure boundaries, then exact author heads and end-to-end recovery evidence | `docs/mse/integration/SECURITY_REVIEW.md` | Scope confusion, receipt forgery/replay, source deletion vs erasure, private data/logging, path/file abuse, uncertain commits; give bounded GO/HOLD per increment |
| LONESTAR | Maintain one dependency/status/evidence board and reconcile requirement coverage from actual receipts | `docs/mse/integration/STATUS.md` on a separate documentation branch | Track posted/visible/acknowledged/implemented/tested/reviewed/merged/deployed separately; dependency blockers and next owners; no invented ACKs |
| GADGET / PM | Own canonical instruction, shared-interface freeze, integration candidate and final review | This plan and PR #23; shared context registration serialized here | Verify current sources and workers' exact heads, coordinate offline combined tests, keep deployment and real-data gates explicit |

File prefixes reserve ownership, not permission to duplicate existing functionality. If an existing path is more appropriate, propose it to GADGET before crossing ownership. Workers may develop compatibility shims locally against pinned dependencies; publish the limitation rather than silently copying an entire stale branch.

## First combined acceptance

- Captured synthetic HR/SDNN additions and unknown-UUID tombstones preserve original artifact bytes and declared source semantics.
- Full and partial exports never invent missing records, provenance or deletions.
- Identical batch retries preserve receipt identity; changed content under the same identity fails.
- Reopened artifact/ledger/archive reconstruct the exact accepted observations and tombstones; interrupted commits reconcile explicitly.
- Snapshot scope, revisions, cutoff and coverage are bound to the MSE run; missing support yields unknown/unavailable rather than a fabricated state.
- Derived results retain input lineage and never overwrite measured evidence. Model execution can be unavailable without losing acquisition or ingestion work.
- Independent tests include negative cases and retain failures; no existing uploader fixtures are resent, no live traffic occurs, and immutable MSE reference bytes remain unchanged.

## Reporting and next decision

Canonical dispatch is recorded on PR #23. Workers ACK there or on their existing owning record with a link back, and put implementation evidence on their draft PR. GADGET's next checkpoint is contract reconciliation and author branch readiness, followed by an exact-head synthetic integration run. MOTHER's existing benchmark/model integration work is separate and must not be interrupted or treated as the data-ingestion owner automatically.

## 21 November checkpoint and next increment (revision 2)

Canonical [r2 dispatch](https://github.com/ctmansfield/mother/pull/23#issuecomment-7041572809) supplements the initial assignment. Completed author milestones: ATLAS #28 contract/matrix draft, NICKY #25 fixture checks (5), PROVENANCE #27 reference seam (4), PHOENIX #29 restore checks (5 after preserved WAL-related failure), SENTINEL #24 Stage A review and LONESTAR #26 board. ORACLE inventory and FORGE four archive-seam probes are complete; neither is an implemented end-to-end adapter. These counts are author evidence pending independent reproduction, and the PRs are unmerged.

Next assignments remove the shared-interface bottleneck: ATLAS produces precise nested schemas, status nullability and golden digest vectors with review from SENTINEL. ORACLE starts the actual capture/parser and validation implementation; FORGE builds custody/journal/recovery and exercises normalized-record validation in an isolated dependency environment. PROVENANCE implements validated snapshot projection rather than accepting unrelated supplied projection bytes. NICKY adds independent contract vectors and combined acceptance. PHOENIX supplies a reproducible restore invocation and prepares paired artifact/ledger/archive recovery tests. LONESTAR updates the single board using owning receipts.

The existing 0.1 contract is a working candidate, not frozen. Authors continue disjoint work with provisional shared serialization kept behind a small interface. Freeze requires exact corrected contract, independent boundary review and author compatibility responses. Explicitly resolve source versus processing revision identity, changed-content UUID behavior, multiple/unknown deletion facts, three clocks and unsupported epistemic-class assumptions. GADGET then assembles a local combined candidate, without merging to main or changing runtime authority.
