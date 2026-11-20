# Metabolic State Engine — repository design and reference

MSE-001 is now preserved as a versioned research reference in the MOTHER source
tree. The original release is dated 13 November 2026. The repository import and
current integration notes are dated 19 November 2026, Guam time.

The executable prototype estimates retrospective heart-rate and HealthKit SDNN
signal deviations from synthetic or explicitly supplied archive files. Its
fixed model parameters and uncertainty intervals are uncalibrated. It is not
wired into MOTHER's server, acquisition adapters, COACH or a live data store.
Glucose adapters, dynamic mechanism execution and intervention efficacy remain
future work. No biological or clinical validation is claimed.

## Read in this order

| Purpose | Document |
| --- | --- |
| Current repository facts and execution holds | [Repository reconciliation](REPOSITORY_RECONCILIATION_2026-11-19.md) |
| Current integration and data-contract decisions | [Integration addendum](INTEGRATION_ADDENDUM_2026-11-19.md) |
| Complete original deliverables A–I | [Architecture and model specification](../../research/mse/reference-v0.1.0/docs/MSE_ARCHITECTURE.md) |
| Original code inspection | [Health Bridge audit](../../research/mse/reference-v0.1.0/docs/HEALTH_BRIDGE_AUDIT.md), [MOTHER/COACH audit](../../research/mse/reference-v0.1.0/docs/RELATED_REPOSITORY_AUDIT.md) |
| Executable behavior and limitations | [Prototype README](../../research/mse/reference-v0.1.0/prototype/README.md) |
| E1 mechanism and intervention objects | [Draft contracts](../../research/mse/reference-v0.1.0/design/contracts/README.md), [mechanism seed map](../../research/mse/reference-v0.1.0/design/MECHANISM_SEED_MAP.md) |
| Proposed future database | [Separate MSE schema](../../research/mse/reference-v0.1.0/design/001_mse_proposed.sql) |
| Earlier GADGET/PM coordination findings | [Historical coordination review](COORDINATION_REVIEW_2026-11-14.md) |
| Supporting research and source findings | [Historical notes index](historical/README.md) |
| Repository installation and rollback | [Installation and verification](INSTALL.md) |
| Import evidence and remaining work | [Import report](IMPORT_REPORT_2026-11-19.md), [independent publication review](INDEPENDENT_PUBLICATION_REVIEW_2026-11-19.md) |
| Every repository addition and its reason | [Change log](CHANGELOG.md), [release notes](RELEASE_NOTES.md) |

## What is preserved

`research/mse/reference-v0.1.0/` contains the original 63 manifest-covered files
and their manifest: the full report, two repository audits, prototype source and
tests, JSON Schemas and synthetic examples, proposed SQL, three add-only patches,
source evidence, verification receipts, release notes, install/rollback tools
and report/patch builders. The Markdown report is the complete source of the
previously delivered PDF. Unlisted PDF-rendering caches are not source artifacts.

This snapshot is byte-preserved. Statements such as "not committed" inside its
original release notes describe the original delivery on 13 November. This
repository index and the import report describe the subsequent publication.
Do not rewrite old tests, failed hypotheses, review findings or provenance to
make them appear current. New results belong in new records and release versions.

## Verify from the repository root

Integrity verification uses Python 3.11+ and the standard library:

```bash
python3 -B tools/verify_mse_reference.py
```

The complete existing software verification also requires the pinned
`jsonschema` dependency and Git. See [INSTALL.md](INSTALL.md) for an isolated
verification environment. Then run:

```bash
python3 -B tools/verify_mse_reference.py --all
```

The wrapper propagates failures. It checks the original manifest and every
payload file, runs the prototype's 56 tests, 25 contract checks, seven in-memory
SQL checks, and reconstructs the three original patches in temporary directories.
The schema/patch builders run on a temporary copy because they write their
verification reports. The preserved snapshot is checked again afterward.

The dedicated **MSE reference** GitHub workflow runs these checks. The older
general MOTHER workflow contains failure-suppressing commands and is not evidence
for this reference's correctness. Prototype tests are excluded from root pytest
discovery and remain explicitly runnable through their own verifier.

## Next implementation boundary

Select an accepted, immutable source export contract before adding a MOTHER
adapter. Separate event time, source revision, authoritative availability and
replay cutoff; retain unknown units and coverage. Preserve the current glucose
execution hold until its owner changes the disposition. The first integration
should be read-only replay into a separate derived state store, with measured
signals, inferred states, mechanism hypotheses and individual causal outcomes
kept distinct. Publication of this reference does not change that hold.
