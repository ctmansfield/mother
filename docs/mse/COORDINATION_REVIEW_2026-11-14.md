# Historical coordination review — 14 November 2026, Guam

This is a content-preserving Markdown copy of the review posted to [Production Framework #42](https://github.com/ctmansfield/production-framework/issues/42#issuecomment-6857111350). It describes evidence available at that time, not current runtime state. Only trailing whitespace has been normalized for repository formatting. The current repository reconciliation and integration addendum are adjacent to this file. The original comment was published at 2026-11-13T15:15:15Z (14 November in Guam).

---

# GADGET / PM coordination review — MOTHER / COACH / Bridge

**REPORT-ID: MSE-GADGET-HANDOFF-20261114-01**
**Status: review completed; coordination handoff requested by Chad.**
Chad authorized sending this completed review to GADGET, including a GitHub fallback. This records findings and proposed next actions. It does not authorize additional execution, deployment, merging, credential changes or schedule changes.

## Recommendation

Keep the sequence **isolated Linux rehearsal → authorized read-only Swift-to-NAS acceptance → Desktop/Xcode integration and iPhone validation**. The next shared milestone is qualification of the existing glucose read path. Offline MSE development can proceed independently against qualified historical data; a live metabolic-inference claim would require additional ingestion and scientific validation.

The immediate dependency is a **named, approved disposable Ubuntu x86_64 environment** and an exact candidate manifest. Source reconciliation, acceptance design, Coach patch preservation, and ORACLE's isolated Swift work can proceed in parallel. Do not require completion of the entire Framework release or every PF-001/I01 merge before a separately scoped rehearsal.

### Evidence vocabulary and delivery-time updates

- **Execution evidence supplied by Chad:** accepted within its stated scope; this review did not independently inspect the production hosts or rehash the private NAS artifacts.
- **Repository-checked:** inspected GitHub source, PRs and CI during the completed review. The exact pins below identify that evidence; recheck moving heads before execution or merging.
- **[HOST], [ARTIFACT], [BOARD], [GITHUB]:** a fresh check is still needed for the named claim.
- Posting this handoff establishes a GitHub record, not receipt or acknowledgment by the separate GADGET chat.

New GitHub receipts were read before sending this handoff. They supersede the earlier statement that the coordination issues had no ACKs:

- [FORGE #46 ACK](https://github.com/ctmansfield/production-framework/issues/46#issuecomment-6856907369): accepted; that release-reconciliation assignment has not been executed; qualification tests SKIP.
- [PROVENANCE #47 ACK](https://github.com/ctmansfield/production-framework/issues/47#issuecomment-6856903446): accepted; lineage-contract implementation is deferred pending owning branches/contracts.
- [GADGET #49 ACK](https://github.com/ctmansfield/production-framework/issues/49#issuecomment-6856920393): accepted; repository inventory verified; offline runtime tests SKIP.
- [ORACLE detailed Swift completion receipt](https://github.com/ctmansfield/mother-health-bridge/pull/1#issuecomment-6856973861) and [hub receipt](https://github.com/ctmansfield/production-framework/issues/42#issuecomment-6856990257): local source reconciliation and lifecycle-model test work completed. Publication/integration, real NAS, physical-device and remaining UI acceptance remain pending.

These are distinct assignments. The #46 release ACK is not evidence that the separate glucose Linux rehearsal ran, and the #47 contract ACK is not the bounded Nightscout pilot receipt.

## Top three next actions

### 1. Close the disposable Linux rehearsal gate

**Owner:** FORGE for the rehearsal; PM/GADGET for coordination; PHOENIX/LONESTAR for the existing environment inventory and owner handoff; SENTINEL or the designated independent reviewer for confinement and recovery evidence.

**Dependencies:** a specifically approved disposable Ubuntu x86_64 target, scoped access and input-transfer route, and the exact one-entry rehearsal package. Existing access to NAS, LLM or another shared host does not establish suitability or authorization for this run.

**Evidence needed to close:**

- Candidate digest, source manifest, entry point, OS/architecture, runtime requirements, effective UID/GID, allowed mounts and write paths.
- Read-only input mounts, bounded output, effective privilege drop, and checks that the runtime cannot regain prohibited privileges or access host credentials/control sockets.
- A successful normal run, controlled interruption, restart/recovery and cleanup, with before/after inventories covering unexpected processes, listeners, mounts and retained sensitive material.
- Separate evidence for catchable termination and uncatchable termination. A shell trap alone does not establish cleanup after SIGKILL; an outer owner or subsequent recovery procedure must handle that case.

The [new PHOENIX inventory receipt](https://github.com/ctmansfield/production-framework/issues/42#issuecomment-6856930660) identifies a retained KAL Ubuntu VM mentioned in [#24](https://github.com/ctmansfield/production-framework/issues/24) as an unverified lead. Its availability, isolation, requirements, ownership and authorization still need checking. Reuse this inventory instead of repeating broad discovery. FORGE's stated requirements include Python 3.12, PostgreSQL 16/libpq and scoped mount-namespace/privilege-drop operations. PR #35's Canonical-keyring qualification is a separate job; sharing a host does not share acceptance evidence.

**Specific Chad decision:** identify or approve the named disposable target and exact rehearsal scope if existing authorization does not already cover it. PM should first reconcile existing approvals and the builder owner's decision. **[HOST/ARTIFACT]**

### 2. Complete the source, artifact and runtime evidence chain

**Owner:** GADGET/PM maintains the acceptance ledger; FORGE owns the package; ORACLE owns Swift with Desktop/Xcode; PM identifies the durable Coach patch owner.

**Dependencies:** no Linux execution is required for the read-only reconciliation and packaging work. This proceeds alongside action 1.

**Already completed in ORACLE's new receipt:** comparison of the runner pin with the combined Swift source; corrected Guam gap evidence; review of the new suspension/foreground model tests. The runner remains at `e84a848796689b9bcb247a57024bc9f8d6e576c1`; the combined implementation is `9f4256a4285dacf641b01ed6d8a710872c115c68`, with prior documentation `cf99c00e8286033105ea53855679ed7b986c2489`. New local tests are `50746d0b21f82737de21f3f15c91c8059ea39f75`, documentation head `98c1dd1751479314f89318bab16dc8ace87574ed`. Xcode reports 205 executed functions / 406 cases, one staging skip; focused suite 11 / 32. ORACLE reviewed rather than reran those executions.

**Remaining evidence needed to close:**

- Bind the selected executable package to its exact source, fixture, launcher, transport overlays, endpoint implementation, commands and result receipts. A changed one-entry package gets its own digest and appropriate checks.
- Resolve the exact repository or retained source artifact for N3 `59a6ce9c0a4fb303e13302ed38deaaacdded277d`; that SHA was not resolvable in the Mother and Framework repositories checked in the review.
- Review and retain the local ORACLE bundle/manifest where the receiving worker can verify it. The new full-history bundle is reported as `c856b76cb8bf5a39c9ce9e25839a47ad4f59a037b238893c9a5ec24b89fa0f76`; the previously reviewed rehearsal archive remains `d4f763a80328d9de38c6aa75d9445f4780768d4496a108b1b5c6901fc47286f7`. These are different artifacts.
- Preserve the distinction between identical glucose-client source and nonidentical applications/packages. ORACLE reports `MotherGlucose.swift` and original glucose tests byte-identical across the compared pins, while dashboard labels, Package.swift, SQLite work and staging overlays differ. Passing at one pin is not whole-application runtime acceptance at another.
- Reconcile Bridge PR #1's target conflicts through ORACLE's reviewed combined work; preserve both glucose registration and `SyntheticIncrementalHandoff.swift`, plus both changelog histories. Do not redo completed work merely because the remote PR still contains the old head. Rerun affected checks when the chosen integrated source actually changes.
- Give the deployed Coach handler fix a durable source/release path: upstream baseline, original/patched handler hashes, regression test, image digest, read-only bind location, Compose override, and recoverable rollback configuration.

**Specific Chad decision:** resolve the canonical patch owner/location if PM cannot settle it from current responsibilities; separately authorize publication/integration when that is the next requested step. This handoff does not itself approve a push, merge or image upgrade. Exact artifact identity gates execution; merging all stacked drafts does not automatically gate an isolated, reviewed candidate. **[GITHUB/HOST/ARTIFACT]**

### 3. Run frozen historical Swift-to-NAS acceptance, then complete device integration

**Owner:** ORACLE for Swift; FORGE for the endpoint/runner; PROVENANCE and independent QA for record reconciliation; PM for cross-system acceptance.

**Dependencies:** action 1 passes, the exact artifacts in action 2 are selected and verified, and the real-data read-only scope is authorized. Reuse applicable existing authorization rather than asking for it again.

**Evidence needed to close:**

- Named endpoint/runtime, trusted TLS, approved read scope, selected client revision and the exact normalized projection. Projection SHA-256: `a5dc20e6d4fce67e93f96b5b45fa49de654249fb193e5ebe968cad535403bff6`.
- Explicit historical anchor and half-open query bounds. Chad's reported 288 / 318 / 318 readings over 3 / 4 / 4 pages apply only to the same frozen historical snapshot and anchor. Reconcile the receipt and manifest; do not substitute a synthetic run with identical counts.
- Exact record identities/revisions, decimal values, verified units, provenance, stable ordering including equal timestamps, continuation and terminal pages, retry behavior and deduplication.
- Raw-only substitutions rejected; stale latest, unknown synchronization and unknown source coverage remain visible.
- NAS source data stays read-only; no production checkpoint advances; local outputs are bounded and cleaned or retained according to the reviewed plan.
- Remaining UI/session/lifecycle checks are tied to the selected integrated Swift revision. Host model tests do not establish actual scene-transition or physical-device behavior.

**Specific Chad decision, only where not already covered:** the named endpoint, dataset, client, credential-delivery route and bounded real-data scope. This does not imply continuous ingestion, production writes or credential changes. Then ORACLE coordinates Desktop integration and iPhone acceptance; isolated preparation, build work and review can continue now. **[HOST/ARTIFACT]**

## Reconciled execution evidence and its limits

| Area | Verified result supplied for this review | What it does not establish |
|---|---|---|
| Frozen Nightscout archive | All 55,861 archived SGV records matched the frozen snapshot. | Ongoing acquisition after the snapshot. |
| Separate normalized projection | 36,767 readings have record-level Clarity mg/dL evidence; 19,094 remain raw-only; pause/resume and exact verification passed. | Units for raw-only rows or future records; raw-only status is not proof of an ingestion gap. |
| N3 historical staging | 288 / 318 / 318 readings; 3 / 4 / 4 pages; anchor is latest normalized reading plus 1 ms. Latest is stale; sync and source coverage unknown. | Rolling-now coverage or equality with the raw archive cutoff. |
| Coach status repair | Read-only handler bind deployed on pinned image; verified TLS status returned exactly `{"entries":"r"}` for the Keychain Subject and HTTP 401 anonymously. | Durable repository packaging, next-upgrade compatibility or current host bytes without a fresh check. |
| Bounded live pilot | Receipt `cf7e4fa6-8cbc-4050-9d67-f6fa6c9c518f`: four live rows matched four sealed rows; zero missing, changed or ambiguous pairs. | Full-window completeness, revision history or continuous ingestion. All four units were unverified and remained unnormalized. |
| Swift | Signed-in Simulator/synthetic HTTPS and independent ordering, raw-only rejection and retry review passed; ORACLE's later local lifecycle-model receipt adds scoped evidence. | Real NAS HTTPS or physical iPhone acceptance. |

The pilot's temporary checkpoint was removed and no temporary grant was installed. PROVENANCE reported the account already had `NOPASSWD: ALL`. That is evidence about audited execution, not an enforced least-privilege boundary or proof that sudo would otherwise be denied.

ORACLE's separate gapped synthetic endpoint totals, 276 / 306 / 306 over 3 / 4 / 4 pages, are not dashboard request counts or the complete historical-window acceptance counts. The corrected synthetic Guam gap is November 15, 2023, 5:13 AM–6:13 AM. Keep dataset, query, client and receipt identities attached to every count.

## Repository findings from the completed review

| Component | Exact inspected head | Review finding |
|---|---|---|
| [Bridge PR #1](https://github.com/ctmansfield/mother-health-bridge/pull/1) | `e84a848796689b9bcb247a57024bc9f8d6e576c1` | Open draft, unmerged, conflict/dirty state; no exact-head Checks/Actions/review submissions at the audit. ORACLE's newer comment is a local-work receipt, not a code push. |
| [Mother PF-001 PR #1](https://github.com/ctmansfield/mother/pull/1) | `5a6f71a45dc64880bc06a0e1a50c7d05ff119cba` | Open draft; clean against main. General CI is green, but wrappers can mask failures; bounded physiology evidence remains separate. |
| [Mother I01 PR #9](https://github.com/ctmansfield/mother/pull/9) | `81c3fcceadcf5bf7462bf813427b98e4f87721e0` | Open draft, clean against its stacked base; [dedicated read-only CI passed](https://github.com/ctmansfield/mother/actions/runs/42511852127). Offline reconciliation evidence. |
| [Coach PF-001 PR #1](https://github.com/ctmansfield/coach/pull/1) | `1b0ba6faa89c52d2a85452b07339b846b92d1ad0` | Open draft, clean; no exact-head Checks/Actions at the audit. Local 54-pass/7-skip evidence is a separate result. |
| [Coach I01 PR #6](https://github.com/ctmansfield/coach/pull/6) | `184606fe9d5022997f09a2e4d6ef38e5dca4a9bc` | Open draft, clean against its stacked base; [dedicated Node/Chromium CI passed](https://github.com/ctmansfield/coach/actions/runs/42511517020). This is not the Nightscout repair regression. |
| [Framework RC2 PR #35](https://github.com/ctmansfield/production-framework/pull/35) | `739a772f00595484e0aab691de369e9feae56523` | Open draft; inspected exact-head CI covers repository policy. Broader runtime/recovery release gates remain separate. |

Bridge's target is `b2baa2e6bd2d018b6e34a07c783b7c3523366374`. The audit's three-way comparison found conflicts in `Package.swift` and `docs/CHANGELOG.md`; the PR payload's older base `9c89bea056c95c7a7db1bcf8fb6460d08e356aa0` was not the current target tip. [Exact comparison](https://github.com/ctmansfield/mother-health-bridge/compare/b2baa2e6bd2d018b6e34a07c783b7c3523366374...e84a848796689b9bcb247a57024bc9f8d6e576c1). An API combined status of pending with zero statuses is absent status evidence, not necessarily a running or failed CI job. ORACLE now confirms remote PR and Desktop target remain unchanged while the combined work is local.

### Coach deployment drift

The [older MOTHER #10 comment](https://github.com/ctmansfield/mother/issues/10#issuecomment-6856217695) said the fix was not deployed. Chad's later deployment evidence supersedes that earlier chronology; the old comment is not evidence that the repair failed to deploy.

The [tracked Coach Compose file at main](https://github.com/ctmansfield/coach/blob/1dd63725dbed112fc33d9c9a64b60b1d7263c246/vm/coach/docker/compose/docker-compose.yml), also checked in the latest I01 state, still used `nightscout/cgm-remote-monitor:latest` without the deployed handler bind, digest pin or `AUTH_DEFAULT_ROLES` override. The checked Coach branches/PRs/releases did not establish a durable repair path. Another repository or retained host artifact may hold it; that remains to be identified.

Record both the image digest and the externally mounted handler bytes. An image pin alone does not identify bind-mounted code. The next image upgrade must preserve a compatible patch or demonstrate a tested upstream fix. The supplied backup location is `/var/backups/nightscout-status-v3-20261113T145507Z`; verify its identity and recoverability before relying on it. **[HOST/ARTIFACT/GITHUB]**

### Board and reporting

The issue-based coordination record is now materially newer than the original review. The live [project board](https://github.com/users/ctmansfield/projects/2) columns were not directly inspected in this review; do not report them as reconciled merely because issue comments are accessible. **[BOARD]**

Retain separate statuses for source prepared, tests executed, independently reviewed, published, merged, deployed and runtime verified. The new ACKs and ORACLE receipts improve reporting, but an ACK does not qualify unexecuted work.

## Blind spots that affect the next milestone or decision

1. **Post-snapshot ingestion.** Matching four existing sealed records does not demonstrate durable capture of new readings after the freeze. This is not a blocker to a bounded historical viewer; it becomes a gate for ongoing monitoring.
2. **Completeness and revision semantics.** Full-window pagination, late arrivals, corrections, deletions, repeated timestamps and restart behavior need an explicit source contract. Maximum measurement time is not automatically a safe ingestion cursor.
3. **Distinct clocks and anchors.** Preserve raw cutoff, latest normalized time, historical query anchor, ingestion watermark and current time as different fields. Equality between the historical anchor and raw archive cutoff is unverified.
4. **Unit evidence.** TLS, plausible numeric ranges and display settings do not qualify units. Keep the 19,094 raw-only rows and four unqualified pilot rows out of normalized metabolic inference until record-level evidence supports conversion.
5. **Recovery scope.** Projection resume against frozen input does not prove crash recovery during changing network ingestion. Linux interruption cleanup, endpoint recovery and ingestion checkpoint semantics are different tests.
6. **Privilege enforcement.** Audit logs and absence of a newly installed grant do not demonstrate confinement when existing broad sudo remains available. Verify the effective execution boundary in the disposable rehearsal.
7. **Artifact portability.** Local commits and hashes are useful receipts but do not establish that another worker can retrieve, verify and execute the intended candidate. Transfer and verify the exact handoff without silently changing its pin.
8. **Scientific scope.** A qualified glucose read path supports descriptive glucose dynamics. It does not by itself identify autonomic, mitochondrial, inflammatory or host–microbial mechanisms. MSE should preserve observations, inference, hypotheses and unknowns separately.

## Parallel work and what changes the milestone

**Proceed independently now:** FORGE package preparation; scoped builder qualification; ORACLE local handoff/publication planning and remaining test design; Coach patch source/release preservation; acceptance assertions and replay fixtures; lineage contract work once its owners/baselines are pinned; offline MSE work on qualified normalized evidence.

**Not automatic prerequisites for the historical read milestone:** normalizing all 19,094 raw-only records, establishing a continuous feed, merging every PF-001/I01 draft, completing general worker automation, or promoting Framework RC2.

If the objective becomes **current glucose continuously and completely available to MOTHER**, the milestone changes. Post-snapshot acquisition, revision/deletion semantics, unit qualification, bounded loss/recovery behavior, freshness and source-coverage reporting must then pass before that claim is accepted. The existing evidence supports the bounded historical acceptance sequence, with the gaps above kept explicit.

**Requested GADGET/PM response:** acknowledge this review, reconcile the three actions against active assignments and existing approvals, name the exact rehearsal candidate and environment decision, and return links to the owning evidence records. Preserve the separate Research Scout 2.0 and weekly Meta-Research schedules.
