# MOTHER / COACH — MSE-001 v0.1.0

Repository-grounded architecture review and an isolated, offline reference
implementation. Prepared 13 November 2026. No upstream code or production
service was changed.

## Start here

Read `docs/MSE_ARCHITECTURE.md` for the complete A–I deliverables. It distinguishes
inspected source, reported device/deployment results, software executed in this
workspace, and new proposals. The separately supplied PDF contains the same
architecture report with rendered diagrams and equations.

| Directory or file | Contents and authority |
|---|---|
| `docs/` | Full A–I report and two detailed repository audits |
| `prototype/` | Executable offline HR/SDNN reference package; its README defines its implemented CLI and behavior |
| `design/contracts/` | Proposed versioned JSON Schemas, synthetic examples and logic verification; no deployed API is implied |
| `design/001_mse_proposed.sql` | Proposed separate future MSE database; not the prototype runtime schema and not a production migration |
| `design/MECHANISM_SEED_MAP.md` | Two bounded biochemical motifs with concrete participants, scoped primary evidence and missing measurements |
| `patches/` | Three standalone, add-only patch deliverables for empty review directories; no upstream integration base is assumed |
| `evidence/` | Inspected repository pins and Health Bridge source-manifest fingerprints |
| `verification/` | Executed checks, independent review, exact final prototype evidence and known limits |
| `tools/render_report.py` | Offline PDF renderer; authoring dependencies are separate from the stdlib-only prototype |
| `INSTALL.md` | Installation, synthetic replay, verification and non-deleting retirement |
| `RELEASE_NOTES.md`, `CHANGELOG.md` | Release scope, each modification and its reason |
| `MANIFEST.sha256` | Fingerprints for the review-bundle contents, excluding this manifest itself |

## Architecture decision

Keep acquisition, evidence and interpretation separate. Reuse the HealthKit
archive and MOTHER PF001/I01 provenance contracts. Put MSE output in its own
derived store. Consume reviewed, immutable mechanism bundles from the E1 research
map. Give COACH explicit uncertainty and measurement requests.

The executable first slice supports the two channels actually acquired by the
inspected bridge: heart rate and HealthKit SDNN. It imports captured archive
bytes, retains exact provenance and deletions, computes prior-only reference
features and performs deterministic retrospective replay. It declares unknown
biochemical mechanisms. Its numerical intervals are explicitly uncalibrated.

## Verification result

The exact final installed prototype passed 56 software tests. The independent
reviewer reran 52 core tests, a subset of those 56. The complete installation,
idempotent import, exact replay and non-deleting retirement lifecycle passed.
Separate checks cover 25 draft contract/schema invariants, seven proposed SQL
invariants and 35 existing MOTHER evaluation/leakage tests. These counts do not
establish scientific, clinical or production validation.

All physiological examples shipped in this bundle are synthetic. There are no
personal health-record exports, credentials, deployed services or automated
treatment controls in this release.

## First integration decision

Select and pin the MOTHER PF001/I01 integration base and its authoritative
current-record export contract. Add a read-only adapter and qualify replay
before changing any iOS storage or transport behavior. The next scientific
increment is qualified CGM plus meal/activity/sleep context, followed by
prospective within-person comparisons. See sections F–H of the full report.
