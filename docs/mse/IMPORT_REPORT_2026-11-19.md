# MSE-001 publication import report — 19 November 2026, Guam

## Instruction and scope

The current user instruction is: "The prototype needs to be saved to the mother
repository. All documentation and findings along with any new design details we
need to add at this time."

This report covers preservation in `ctmansfield/mother` of the complete original
MSE-001 release, related scientific/source findings and a current integration
addendum. The selected review branch is
`work/mse-001-reference-and-design-20261119`, based on MOTHER main
`818426fe90fab1bfd9583640363d4001b30e633f`. The GitHub publication receipt and
source-bound context record identify the resulting source commit and draft PR.
The published source commit is
[`18f7b040b576294de6570ce6e8247e8ed8590caf`](https://github.com/ctmansfield/mother/commit/18f7b040b576294de6570ce6e8247e8ed8590caf),
and the review is [MOTHER draft PR #12](https://github.com/ctmansfield/mother/pull/12).
All 84 publication file blobs and modes matched the prepared package on remote
readback; unrelated base files remained unchanged. The source-bound handoff is
`context/tasks/MSE-001-publication-r1.json` with measured evidence under
`context/evidence/` and a registered index.

This is repository publication, not a production integration or deployment.

## Preserved source

| Artifact | Verified identity |
| --- | --- |
| Original release archive | `mother-coach-mse-0.1.0.tgz`, 189,977 bytes |
| Archive SHA-256 | `e6f2a0c1d5fea4eb6fc27c93d0261dac7729e180164cac7faf863cb3acbd2fee` |
| Original manifest SHA-256 | `112ccb8df17d6afc6d8b7f932fbdeac31b1663ccd04c5538b9bd9a32e94a25f1` |
| Imported release | 63 payload files plus manifest; 64 files, 895,441 bytes; all original bytes and modes preserved |
| Imported tree digest | `1e19a152e76fe506d4366d5c2b6addd5e113498e8378ae02c244af8b61741c04`; algorithm in `research/mse/IMPORT_SOURCE.json` |

The complete A–I report, supporting audits, scientific evidence, mechanistic and
intervention contracts, proposed database schema, executable offline prototype,
tests, installation/retirement tools, original release notes/change log and
three discrete patches are retained. The original PDF's complete Markdown source
and renderer are included. Generated PDF rendering caches are not source files.
Two additional historical supporting notes and the posted coordination review
are preserved outside the immutable release with their original time/scope.

The original package's "not committed" statement describes its November 13
delivery. Current publication records describe this later change. Original
failed hypotheses, corrected review findings and test history remain intact.

## Changes and new design details

The [change log](CHANGELOG.md) accounts for every category of addition. The
[current addendum](INTEGRATION_ADDENDUM_2026-11-19.md) specifies proposed revision,
availability, unit-evidence, coverage, snapshot and state contracts; a versioned
scientific/behavioral federation boundary; conditional mechanism and receptor
semantics; separate hypotheses, exposures and outcomes; active measurement; and
successor memory preserving failures, contradictions and calibration history.
These are explicit proposals, not newly implemented live adapters or endpoints.

The [repository reconciliation](REPOSITORY_RECONCILIATION_2026-11-19.md) preserves
the current parked NAS-glucose disposition. Publication does not reopen it.

## Checks actually executed for this import

| Check | Result and scope |
| --- | --- |
| Original archive/extracted/imported comparison | All 63 manifest entries and original manifest matched; no missing or extra files |
| `python3 -B tools/verify_mse_reference.py --all` | Exit 0; original snapshot unchanged after checks |
| Prototype verification | 56 software tests passed, including four install/retirement lifecycle tests; 22 prototype payload files verified |
| Draft contracts | 25/25 fixture/schema/three-valued-logic invariants passed on a temporary copy |
| Proposed SQL | 7/7 invariants passed in an in-memory database; no migration applied |
| Original patches | Three patches rebuilt with exact original hashes; `git apply --check`, empty-directory application and exact reconstruction passed |
| New integrity-wrapper negative probes | Extra file, changed payload and changed manifest each rejected in a temporary copy |
| Existing context-reader suite | 50 tests passed; existing reader implementation was not changed |
| Prototype isolation from root collection | Pytest 8.3.5 collected no tests under `research/mse` (expected no-tests exit 5); direct prototype verification remains runnable |
| New Python formatting/lint | Black 25.9.0 and Ruff 0.13.1 passed for the verifier and scoped conftest |
| Structured configuration | New YAML parsed; imported research JSON parsed |
| Independent review | Scientific/publication review recorded separately; no scientific or publication blocker found within its stated scope |

These are distinct checks, not counts to add into one scientific sample size.
The general MOTHER CI is not used as proof because its existing commands suppress
some failures. The dedicated MSE workflow propagates failures. A remote workflow
result must be read separately at the exact published head before claiming it
passed. Local verification does not imply remote CI execution.

At source commit `18f7b040b576294de6570ce6e8247e8ed8590caf`, GitHub readback
confirmed success for the [dedicated MSE workflow](https://github.com/ctmansfield/mother/actions/runs/44358292209),
[pre-commit](https://github.com/ctmansfield/mother/actions/runs/44358292136) and
[general CI](https://github.com/ctmansfield/mother/actions/runs/44358292131)
on the PR event, with all three push-event runs also successful. These receipts
cover that source commit. The following metadata/context commit must be checked
at its own head; the final PR check page is the current result source.

## Publication contents and limits

MOTHER is public at this review. The included physiological fixtures are
synthetic; scoped review found no raw private health-record exports, credentials,
private keys or access tokens. Historical artifact/source IDs, aggregate record
counts and some historical workspace/backup-path metadata remain as technical
provenance. This is a bounded content review, not a comprehensive security audit.

No current NAS/VPS/LLM/phone runtime, real physiological data, model weights,
device authority cutover or scientific-model inference was accessed or executed.
No production service, database, credentials, signing settings, Research Scout
2.0 schedule or weekly Meta-Research schedule was changed.

The reference's fixed parameters and nominal intervals remain uncalibrated.
Software correctness does not establish human biological observability, clinical
accuracy, biochemical mechanisms or intervention efficacy. No MSE adapter was
added to the active MOTHER application package.

## Next bounded action

Review the publication PR, preserve its exact source identity, and select a
separate integration task for a read-only captured-source adapter and qualified
snapshot/replay semantics. Keep live glucose work parked until its owning
disposition changes. Installation and non-deleting retirement commands are in
[INSTALL.md](INSTALL.md).
