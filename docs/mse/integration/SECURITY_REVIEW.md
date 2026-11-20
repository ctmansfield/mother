# MSE integration security review

**MSE-INTEGRATION-20261120-01 r1 · Contract and failure-model review**

**GO for synthetic Stage A design and independent fixture preparation. HOLD for shared-interface freeze and Stage B acceptance** until the proposed contract and exact author heads satisfy the gates below. This review covers the [dispatch](https://github.com/ctmansfield/mother/pull/23#issuecomment-7041443650), [implementation plan](../IMPLEMENTATION_PLAN.md), [requirements](../HEALTH_DATA_INGESTION_REQUIREMENTS.md), and [MSE addendum](../INTEGRATION_ADDENDUM_2026-11-19.md). It examines source contracts. It records no integration execution result.

## Reviewed baseline and authority

Main was `c05f38096406965496d7d4a09edf4b3575235311`. The requirements and plan were at PR #23 head `91d67e387e91d93a7a60aec03c8164c11c7aa994`. [PF-001 #18](https://github.com/ctmansfield/mother/pull/18) was open at `b4e70b7123689ec164ba09e2974645ae36b184a2`. Its physiology contract separates observation revisions from original byte hashes and separates biological time from first-seen and durable ingest time. Its I01 receipt recovery binds an exact local envelope to the selected archive by direct reread and explicitly reports an unauthenticated sender. Reuse that archive and reconciliation pattern where compatible. Verify the captured-file receipt contract separately. The historical local receipt cannot establish remote authenticity or authorize outbox release across destinations.

## Review gates for the offline slice

| Boundary | Required behavior | Independent synthetic evidence |
| --- | --- | --- |
| Scope and receipt replay (ACQ-02, ING-02/04/08, LLM-01/02) | Obtain expected subject/source and destination namespace from the selected invocation context. Validate file declarations against it before processing. Bind stable batch ID, exact artifact SHA-256 and length, schema, destination and commitment identity to the selected reopenable ledger. Keep acquisition anchor, export progress and durable acceptance separate. | Exact retry after reopen returns the original commitment. Changed bytes under the same scoped ID conflict. Same UUID or batch ID across sources remains isolated. A copied receipt from another scope/archive or a forged receipt with altered digest or commit ID cannot acknowledge. A stale generation cannot advance progress after remap or cancellation. |
| Uncertain commit (ING-03/05/06/07) | Make durable receipt contingent on reopened artifact and committed acceptance state. If artifact, archive and ledger cannot commit together, journal transitions and reconcile only matching evidence. Normalized success requires its own durable evidence. Keep original bytes and batch identity on uncertainty. | Interrupt before artifact publish, after publish, after archive commit but before ledger/response, and after ledger commit but before receipt return. Reopen independently. Missing or corrupt referenced blob blocks verification. Orphans and archive/ledger mismatches are reported. Identical retry resolves to a single logical commitment, and changed input cannot bypass recovery. Reject malformed or unsupported input without advancing a checkpoint. |
| Path and file boundary (ACQ-06, STO-01/05/06) | Constrain input to an explicit bounded regular file and storage to a trusted private root. Treat supplied filenames and locators as data. Verify and hash the same opened bytes used for parsing/retention. Own all destination components under the trusted root, publish without clobbering and revalidate existing objects. | Reject traversal/absolute output locators, symlinked input or destination components, nonregular and oversized inputs, and an existing artifact whose bytes fail verification. Where parent or file replacement is possible, test or document how the trusted-root/open-handle contract prevents it. Verify private modes, unchanged original and unrelated sentinel files, and bounded failure on disk-pressure injection. |
| Source deletion and erasure (ACQ-04/07, STO-02/08, LLM-05) | Preserve explicit tombstones, including unknown native UUIDs, with source scope and revision provenance. A partial or empty capture carries coverage limits. Source deletion affects the applicable current view and dependent serving state under the contract. Owner erasure needs an independently selected operational policy covering originals, backups, projections, derivatives and memory references. | Delete-before-add, unknown deletion, source collision and partial omission fixtures exercise current projection without removing immutable evidence or inferring deletion from absence. Show affected current results are invalidated or mark that capability pending. Stage B demonstrates tombstone semantics only. |
| Access and logging (STO-05, ING-01/08, LLM-01) | Keep local artifact, archive and receipt stores explicitly selected and private. Model input uses a scoped snapshot. Sanitized diagnostics give stable failure codes with enough provenance for a custodian to reconcile privately. | Use distinctive synthetic canaries to check stdout, stderr, failure reports and shared artifacts for raw values, credentials and private paths. Exercise a wrong scope and a forbidden output location. Local filesystem checks establish only the local boundary. |
| Measured and derived evidence (STO-03/04, LLM-02–06) | Bind model input to exact scope, contributing revisions and artifacts, measurement interval, cutoff, schema/normalizer and coverage. Keep unknown or unavailable inputs explicit. Preserve vendor-derived SDNN and declared units. Store model estimates with code/config/model and snapshot lineage in derived results. | Late/corrected records exercise cutoff and invalidation without backdating knowledge. Replay the exact input, check loss reporting and preserve missing fields. Show derived values cannot update authoritative observations. The MSE reference’s retrospective replay retains its historical-availability limitation. Simulate unavailable inference and verify acquisition/ingestion still complete. |

## Exact-head and release disposition

| Stage | Disposition and next evidence |
| --- | --- |
| A | Contract review started. ATLAS supplies exact scope, receipt and snapshot semantics. GADGET freezes the shared interfaces after reconciliation, including recovery states and the source ordering rule for delete-before-add. |
| B | Local synthetic implementation may proceed under the dispatch. Acceptance is pending pinned adapter, ingest, MSE bridge and independent fixture heads, exact effective diffs, and normal-entry-point pass/fail/skip results plus retained failure evidence. Verify unchanged reference and fixture bytes. |
| C | Local fault design may proceed. Hold durable transport and model-serving claims pending loss/restart and invalidation tests, independent receipt/reopen verification and scope-fencing evidence. |
| D / E | Infrastructure and real-data use remain held. Require accepted D-01–D-08 decisions, separate synthetic restore evidence, an authorized pilot scope and independently verified access, privacy and recovery controls before live qualification. |

Next review uses the ATLAS contract draft and the exact author heads delivered by GADGET. This branch changes review documentation only.

## Revision 2 checkpoint

Reviewed [ATLAS draft 0.1](https://github.com/ctmansfield/mother/blob/a732adda92cc79659bf2413c7d45891cf2d13264/docs/mse/integration/contracts/README.md) under the [r2 directive](https://github.com/ctmansfield/mother/pull/23#issuecomment-7041572809). **GO for provisional local work. HOLD for freezing draft 0.1.** The next contract needs these reviewable changes:

- Define exact nested members and status-specific required/null fields. Supply versioned, noncircular digest preimages, including which fields encode source facts versus processing, receipt or clock metadata. Define canonical ordering, duplicate handling, Unicode/decimal handling and bounds. Supply golden bytes, digests and rejection cases.
- Bind receipt verification to the expected subject/source and selected ledger/archive. Declare where destination identity is encoded or verified against reopened state. Cover concurrent retries, replay of a copied receipt and changed bytes under the same identity. Test uncertainty independently for each durability boundary.
- Separate source and processing revisions. Define same-UUID changed content across captures, multiple explicit delete facts and precedence for late upserts, including previously unknown UUIDs. Keep availability, collector receipt, MOTHER receive and durable commitment distinct. Preserve raw numeric lexemes and record conversion loss. HR derivation stays unknown when source evidence cannot substantiate its class.
- Define exact snapshot membership and deterministic selection at the declared cutoff. Bind the projected replay to the exact snapshot, including scope, coverage and tombstones. Reject unrelated snapshot/projection pairs. Preserve historical availability and keep derived results separate.

Independent reproductions used Python 3.9.6 and clean, detached checkouts.

| Candidate | Invocation and observed result |
| --- | --- |
| [NICKY #25](https://github.com/ctmansfield/mother/pull/25) `3951b9d6306190fbb713cb0b3cabd13f35da2f66` | `python3 -B -m unittest discover -s tests/acceptance/mse_integration -v` ran five fixture checks. Five passed, zero failures/errors/skips. No PF-001 import. |
| [PROVENANCE #27](https://github.com/ctmansfield/mother/pull/27) `35e661c7934dce54044d4b14084120abd1f3b4e8` | Plain discovery exited 1 with one import error before test execution. The documented `PYTHONPATH=research/mse/reference-v0.1.0/prototype python3 -B -m unittest discover -s tests/integration/mse_snapshot -v` ran four tests. Four passed, zero failures/errors/skips. No PF-001 import. |
| [PHOENIX #29](https://github.com/ctmansfield/mother/pull/29) assigned head `6c2af4bf7ef42b53fd8acd123be83bf3d5180a21` | `python3 -B tools/mse_integration/recovery/rehearse.py --pf-checkout <clean PF-001 checkout>` used #18 `b4e70b7123689ec164ba09e2974645ae36b184a2`. Five passed, zero failures/errors/skips. The PR branch had advanced to `1d003625` at fetch, so this run intentionally used the assigned parent. |

These are fixture, reference seam and standalone restore results. Combined adapter, ledger, archive, and snapshot acceptance remains open. ATLAS received the blocking contract items for the next candidate. GADGET owns shared freeze and combined selection.

## Draft 0.2 exact review and destination intake

Reviewed ATLAS #28 at `928a60b704c342c091eabd25ba41c8eb84d562de`. Recomputed nine canonical preimages and SHA-256 values, the identical source-fact preimage for alternate numeric spelling and later collector receipt, and the original artifact length and digest. All matched. The nested contract addresses expected scope/archive checks, authoritative reopen verification, noncircular identities, distinct source/processing/deletion facts, separate clocks and withholding unqualified HR from the reference stream. This check did not exercise candidate implementations or schema-negative tests.

**GO to keep implementing against 0.2. HOLD freeze pending one deterministic selection rule.** A repeated source/processing fact can have multiple admitted sightings with different collector receipt, artifact, locator and commit fields. The snapshot allows one active member per UUID, while the reference projects its collector receipt and the snapshot hashes the selected provenance. Specify a stable representative among cutoff-eligible receipts, including repeated delete facts. Define processing selection at cutoff or reject ambiguity when the requested normalizer resolves to multiple processing revisions. Add a two-receipt vector proving input order does not change projection, snapshot digest or historical cutoff results. Sent to ATLAS for correction. The subsequent #28 head `c579d82e` adds destination mapping only.

**Destination readiness** is tracked separately under [MSE-DESTINATION-READINESS-20261121-01 r1](https://github.com/ctmansfield/mother/pull/23#issuecomment-7041665721). Awaiting PHOENIX's sanitized runtime inventory and FORGE's source/schema assessment. Source mapping, catalog availability, a verified intake path, and isolated restore evidence are distinct gates. No host or physiological data was accessed for this review.

## Corrected representative rule and independent retest

**GO for the corrected 0.2 contract, subject to GADGET freeze and author compatibility.** Reviewed ATLAS #28 `3fe247446f03b7ee3e8a36a0a18bd19eb5a1329c`. It selects the earliest eligible normalized receipt for each fact, copies the whole winning member and requires an explicit normalizer, rejecting ambiguous processing digests. Independently applied cutoff and representative selection to all four two-receipt cases and reproduced the full snapshots and hashes. Both input orders agreed and later receipt visibility preserved the old cutoff result. Draft 2020-12 validation accepted six positive instances and rejected all three schema-negative vectors. The three semantic negatives are outside JSON Schema and require exact author implementations. An initial review script errored after its schema checks because it treated the representative-case object as a list. The corrected run passed.

| Exact independently tested head | Result and author comparison |
| --- | --- |
| NICKY #25 `f11b2d9cd6253c887017ac8cb827d9af92e77df2` | 14 passed, up from five at the original head. Includes independent golden digest and edge fixture tests. |
| PROVENANCE #27 `977222172bd8173d794358c2a5e5f397fc734793` | 12 passed with the documented reference PYTHONPATH, matches latest author receipt. |
| PHOENIX #29 `63625c009d55da9048ee35445f0c748bb8b5f28b` | Five passed against clean PF-001 #18 `b4e70b7123689ec164ba09e2974645ae36b184a2`, matches the reported standalone restore count. Paired recovery still awaits compatible journal/archive integration. |
| FORGE #31 `b32f30d0b2e42ce16ae1b21363feaef2006e15f7` | Six passed, matches author. This head directly descends from pinned PF-001 #18. The interruption test exercises four custody/run/archive/receipt boundaries. |

All successful suites had zero failures, errors or skips. #25/#27/#29 ran under Python 3.9.6. Schema and #31 used the existing Python 3.12.14 environment.

**FORGE trust boundary.** The six tests cover uncertain commit, retry, transaction rollback and missing evidence. The harness accepts original bytes and stores them as blobs, with fixed journal and archive basenames, rather than deriving a file path from batch IDs. It checks private root mode and rejects direct symlinks at named store paths. The code and suite do not establish trusted parent containment, ownership/permissions of existing members or rejection of nonregular store files. Keep the seam scoped to a trusted disposable root. Before accepting a broader file boundary, define that root contract, cover the named cases with negative tests, and verify the captured-file adapter owns the separate safe input-opening boundary. No integrated pipeline or destination readiness disposition yet.

## Revision 3 independent checkpoint

[Revision 3](https://github.com/ctmansfield/mother/pull/23#issuecomment-7041939410). **GO for continued local synthetic implementation. HOLD for contract freeze and connected acceptance.**

- ATLAS #28 still resolved to `3fe247446f03b7ee3e8a36a0a18bd19eb5a1329c` at readback. The announced lowest numeric reading index rule is suitable if the exact contract preserves all equivalent fact locators, copies the winning member intact and distinguishes unequal source facts. Require a vector whose numeric and lexical pointer orders differ. Finite nonpositive values can be retained as source facts with original lexemes, explicit normalization/projection exclusion and a typed loss. The schema must distinguish that valid retained-source case from malformed/nonfinite input and avoid manufacturing a PF-001 observation. Exact corrected schema and vectors are pending.
- In a detached PF-001 `b4e70b7123689ec164ba09e2974645ae36b184a2` assembly, independently ran #30 `0a0489a` (14 passed), #31 `c29f442` (11 passed), #27 `6a2c1bd` (16 passed) and #25 `4ba53e1` (19 passed) under Python 3.12.14. The initial #31 discovery skipped its five contract tests because the contract directory was unset. Rerun with the pinned #28 bundle passed 11/11. Final per-suite results total 60 passes, zero failures/errors/skips. The immutable reference subtree diff was empty. These are component results in one checkout. Connected producer/verifier execution and paired restore were not present at the checked pins.
- **FORGE path boundary at #31 `c29f442`.** Four additional synthetic refusal checks passed for a public root, a direct root symlink and either named store symlink, with sentinel file contents unchanged. The inherited store entry point lacks trusted-parent containment and existing owner/mode/regular-file checks before touch/SQLite open. FIFO rejection was not executed because there is no preceding file-type guard. This evidence supports a trusted exclusive disposable root only. Sent FORGE the concrete gaps for exact-head hardening or explicit scope documentation.
- **Destination remains NOT READY.** Reviewed sanitized [PHOENIX inventory #33](https://github.com/ctmansfield/mother/pull/33) at `b05acb3` and [FORGE schema assessment #32](https://github.com/ctmansfield/mother/pull/32) at `5558ccb`. Reported local PostgreSQL availability and filesystem capacity are consistent with the sampled catalog and source assessment. A dedicated intake/identity, reserved protected allocation, compatible schema and coherent restored custody/archive are unverified. The audit supplied neither write acceptance nor a restore of the proposed destination. No direct host or physiological-data access in this independent review.

Next evidence is ATLAS’s exact final candidate, FORGE’s connected and file-boundary head, NICKY’s actual pipeline acceptance, and PHOENIX’s paired restore.

## Revision 4 connected-candidate checkpoint

[Revision 4](https://github.com/ctmansfield/mother/pull/23#issuecomment-7042142491). **GO for final contract freeze at ATLAS #28 `769a0966da251da4d08633cc7663af9869da70e6`.** The contract selects the intact lowest numeric reading-index payload, preserves all locators and records alternate-payload loss. It retains finite nonpositive metrics as signed source facts and excludes them from normalized observations/native replay. Three exact edge exports passed independently executed Draft 2020-12 checks and reproduced raw/export hashes. ORACLE #30 `c26180c` produced the exact repeat and signed-zero exports, but rejected the valid negative input with a draft-value-schema error. This is a remaining implementation mismatch against the pinned contract.

**Connected pipeline: qualified partial GO, final Stage B HOLD.** The detached PF-001 `b4e70b7` assembly kept the reference tree unchanged. Python 3.12.14 results:

| Exact head | Independently observed |
| --- | --- |
| FORGE #31 `d244105` | 16 passed, including four connected cases, zero failures/errors/skips. |
| ORACLE #30 `c26180c` | 15 passed, two mapper-dependent skips. Initial invocation had three skips before fixture path was supplied. |
| PROVENANCE #27 `089e627` | 17 standalone passed and two opt-in connected passed, including rehashed forged/incomplete snapshot rejection and exact reopened lineage. |
| NICKY #25 `13d2e19` | 23 passed, including real adapter-to-ledger custody and failure cases. This head's custody test deliberately stops before PF-001 mapping. |

The first NICKY and opt-in PROVENANCE invocations produced three and two setup errors because stock macOS temporary paths arrived through a symlinked parent. A private canonical TMPDIR resolved the test environment without weakening the path guard. The final NICKY public-entry pipeline suite and exact adapter nonpositive parity remain pending.

**FORGE file boundary: GO for the documented trusted single-UID synthetic root.** Seven independent checks passed for parent alias and write-mode rejection, existing file permissions, a direct sidecar symlink, FIFO, directory and simulated foreign-owner metadata. No file was opened after failed validation. Path checks are scoped to the reviewed caller-owned, exclusive local directory contract.

**Storage: local quiescent restore smoke GO. Destination NOT READY.** PHOENIX #29 `4d76cbb` passed four paired restore cases using its exact pinned older FORGE `c29f442` fixture-mapper dependency, zero failures/errors/skips. Separately, I used current `d244105` with the connected capture and reference: backed up both quiescent SQLite stores, checked both copy integrity results, reopened and verified the original receipt and replayed the exact snapshot to identical derived output. This is one local connected restore smoke check. The PHOENIX current connected recovery harness and interrupted paired fault qualification on current heads remain pending. No destination provisioning, intake or operational restore has been observed.

## Revision 5 exact-pin independent acceptance

[Revision 5 and PM freeze](https://github.com/ctmansfield/mother/pull/23#issuecomment-7045375231). **Contract GO, local synthetic pipeline GO, local paired fault restore GO. Destination NOT READY.** Normative 0.2 is frozen at `769a0966da251da4d08633cc7663af9869da70e6`. The contract tree matches the later `efad47c03c4f5e5183c28e274973278680e1d2f3` docs pin byte for byte.

I independently assembled the r5 functional paths over detached PF-001 `b4e70b7123689ec164ba09e2974645ae36b184a2` as tree `ad529b063ddf557ba1e4f38003082abde72d9a47`. This is the independently assembled functional tree. NICKY's separately owned immutable release candidate was pending at this checkpoint. The reference subtree had an empty diff. Under Python 3.12.14, with the exact contract/fixture roots and a canonical private TMPDIR:

| Scope | Pinned head | Result |
| --- | --- | --- |
| Adapter, public entry and finite nonpositive cases | #30 `7825b02093d280321af34af88aed96da44b33594` | 19 passed |
| Ledger, connected flow and filesystem boundaries | #31 `ceeb92157f4d7179a3ad5cd3d4af9e9aa4ff6b4f` | 19 passed |
| Standalone snapshot and opt-in connected replay | #27 `7be9ea31c6c68643573afdf37ccfa0a41901a368` | 17 plus two passed |
| Independent fixtures, custody and connected pipeline | #25 `bf646a8e2f77c277717dc97b24b8957e9a380579` | 26 passed |

All 83 suite checks passed, zero failures/errors/skips. A separate exact public-entry check called `ingest_capture`, reproduced the exact receipt on retry, reopened the ledger, rebuilt the cutoff snapshot and verified derived replay against the real reopened ledger. No membership callback or forged fixture receipt was used. The earlier negative-value rejection and missing-public-entry gap did not recur.

**File boundary.** The exact #31 suite exercised actual parent aliases, unsafe ancestor mode, replaced root, existing file mode, symlink/hardlink rejection, and FIFO/directory refusals in bounded child processes. The foreign-member ownership case used simulated UID metadata and verified SQLite was never opened. No privileged ownership change was performed. GO is bounded to the documented trusted local single-UID trial.

**Paired recovery.** #29 `1c8b56086b342ab201d80653ca01bef43de70c86` passed five standalone PF-001 checks and its four connected paired checks at the shipped older dependency pins. I reran the same four fault cases with only the dependency constants overridden in memory to r5 FORGE/ORACLE/PROVENANCE and kept the frozen ATLAS pin. All four passed, including interrupted archive-before-receipt recovery, stale archive refusal, exact retry and unrelated-original refusal. The recovery harness uses actual connected ingest, snapshot and replay after restore. No changes were made to its tracked code.

**Destination.** No change to the NOT READY result. These local tests provide no allocated destination, scoped intake or writer identity, or verified operational backup and restore. GADGET owns final combined-tree reconciliation after NICKY's immutable relay.

## Revision 6 immutable release candidate

[Revision 6](https://github.com/ctmansfield/mother/pull/23#issuecomment-7045523829). **Narrow source-integrity HOLD at combined PR #34 `877eeb66ae2c26ab8ee2144d34adeba87c988e8f`, tree `6dadd8cd94ffb4a0091f76624fdd0afd7baad507`.** The frozen contract and earlier scope-limited pipeline and paired-recovery evidence stand. The immutable #34 acceptance owner reported 84 checks and six genuine replay invocations. This checkpoint did not repeat the unchanged suite.

- **Original-to-export binding, independently confirmed in source.** Connected ingest closes over the supplied export and the PF-001 mapper builds revisions and records from those assertions. The common ledger validates schema, local scope, the original byte digest/length and self-consistency of each supplied source-fact digest. No trusted original-to-export reconstruction or equivalent semantic check occurs before custody writes. Existing receipt and reopened membership consistency therefore cannot establish that facts came from the original. Require reconstruction with configured scope, parser limits and supported exporter identity at every production-facing local intake entry, comparing the full expected exchange before mutation. This was static call-path review.
- **Precision, independently reproduced on the exact combined head.** A valid synthetic SDNN capture sent through public `ingest_capture` retained the source lexeme `42.1234567890123456789` and returned normalized. Both persisted PF-001 number fields were `42.123456789012344`. Exact decimal metadata survived. Neither the export nor the receipt-backed snapshot reported this conversion, and the only observed loss was the independent timestamp rounding from the fixture. Require deterministic per-field conversion losses or explicit exclusion when the PF-001 representation changes a value, with reopened snapshot/derived and restore lineage. Avoid retroactive claims about older commitments.

Next review uses the corrected ORACLE/FORGE APIs and immutable NICKY successor. No destination scope change.

## Round 7 corrected integrity heads

[Round 7 and database privacy directive](https://github.com/ctmansfield/mother/pull/23#issuecomment-7045683925). **GO for the two fixes as independently tested at the component pins.** FORGE `e4219cd` reconstructs the full expected export from retained input before write and again during reopened custody verification. The former callback-driven authoritative entry rejects callers. ORACLE `ac3fbf6` records deterministic per-field binary64 changes and FORGE binds the conversion/range decision through reopened snapshot projection. On a detached overlay of immutable #34, the exact corrected adapter suite passed 25, ledger suite passed 22, and PROVENANCE `5799879` connected replay passed five. Zero failures/errors/skips. The reference subtree remained unchanged. This is 52 tests on the exact fix pins, pending NICKY's immutable successor and corrected paired fault recovery qualification.

NICKY received the independent acceptance criteria for semantic rejection before custody mutation, per-field conversion loss through reopened record and manifest, exact values without spurious loss, finite range exclusion and paired restore. No unexpected blocker was reproduced. Privacy and destination readiness are separately assessed in [DATABASE_PRIVACY_ASSESSMENT.md](DATABASE_PRIVACY_ASSESSMENT.md).
