# Proposed MSE mechanism and intervention contracts — v0.1.0

These are **new proposals**, not existing repository schemas or deployed APIs. They define data objects only. No network service, treatment, dosing, device control, scheduling or autonomous intervention is implemented. The example records are synthetic and contain no personal observations or claimed individual efficacy.

## Files and relationships

| File | Record boundary |
|---|---|
| `mechanism-claim.schema.json` | One revisioned, scoped conditional biological claim or reaction hyperedge |
| `intervention-hypothesis.schema.json` | One proposed observation/simulation/hypothesis test; eligibility, alternatives and expected outcomes |
| `causal-analysis.schema.json` | One analysis of an outcome effect with estimand, lineage, methods, uncertainty and validity status |
| `measurement-request.schema.json` | One additional observation proposed to discriminate candidate mechanisms |
| `common.schema.json` | Shared identifiers, scoped evidence, intervals, predicates and provenance |
| `examples/` | Four schema-valid synthetic records and a small immutable snapshot fixture |
| `validate_contracts.py` | Offline schema, fixture-integrity, semantic and boundary verification |

The JSON Schema dialect is Draft 2020-12. `$id` uses a reserved `.invalid` hostname as a namespace, not a downloadable API. The validator registers all schemas from disk and never retrieves remote references. `contract_version` and `contract_status` are fixed. Critical objects reject undeclared properties. `extensions` accepts inert scalar metadata; consuming services must never execute it or use it to bypass the schema's mode/authority restrictions.

Stable IDs identify concepts or records; integer revisions identify immutable versions. A foreign reference is always `{id, revision}`, not an unpinned current alias. The mechanism bundle has a snapshot ID and SHA-256. The example hashes the exact UTF-8 bytes of `examples/mechanism-snapshot.json`; that small fixture is a catalog of declared claim references, not a complete research graph. External example references deliberately illustrate future joins and do not assert that matching repository records exist. A production snapshot manifest must enumerate and hash its complete contained claim/evidence files and be validated before promotion.

Suggested relational storage: `mechanism_claim(id, revision, snapshot_id, body_json)`, `claim_participant(claim_id, claim_revision, entity_id, role, compartment, coefficient)`, `claim_evidence(claim_id, claim_revision, evidence_id, relation, scope)`, plus separate tables for hypotheses, protocols, assignments, exposures, outcomes and analyses. Reaction/claim records serve as hyperedge nodes, so multiple substrates, cofactors, partners and contextual prerequisites remain associated. A graph database is not required. Add materialized graph views or specialized graph queries only when a measured workload justifies them.

## Three-valued conditions

Every leaf declares `missing_result: "unknown"`. The interpreter treats variable names as literal keys; it never evaluates strings as code. Units must already match the declared normalized unit. Missing values, missing units or mismatched units produce `unknown`; conversion belongs in a separate validated normalization layer. Boolean `true` and numeric `1` are not interchangeable.

| Operator | Decisive case | Otherwise |
|---|---|---|
| `all_of` | Any `false` → `false` | All `true` → `true`; otherwise `unknown` |
| `any_of` | Any `true` → `true` | All `false` → `false`; otherwise `unknown` |
| `not` | `true` ↔ `false` | `unknown` remains `unknown` |

An intervention can enter human review only when its prerequisites evaluate `true` **and** exclusions evaluate `false`. Either being unknown withholds recommendation. An unknown measurement-request rule must retain unknown/deferred status rather than permit a claim. Passing review eligibility still grants no execution authority; that field is fixed to `none`.

## Scoped evidence grades A–D

Grades apply to an evidence record **for a specified claim in a specified context**. They are curated judgments with written rationale, limitations and applicability. They are not numerical probabilities and are not assigned automatically by publication type, journal, species, sample size or algorithm score.

| Grade | Proposed interpretation |
|---|---|
| A | Strong, convergent direct evidence for the stated relationship in the specified context; major competing explanations were experimentally addressed and independent support is available |
| B | Direct support in the stated context with material limits in replication, precision or discrimination among mechanisms |
| C | Indirect, observational or transported-context evidence that supports plausibility with explicit unresolved causal/transport assumptions |
| D | Exploratory or model-dependent evidence with substantial unresolved assumptions; suitable for hypothesis generation |

An experiment in mice can support a high-grade claim explicitly scoped to those mice, while remaining indirect evidence for the corresponding human claim. A human trial can support an outcome effect without identifying the biochemical mechanism. `supports`, `contradicts` and `qualifies` remain separate relations. A source DOI/PMID/URL is required for any evidence entry; examples use empty evidence arrays because no study is being asserted as support for their synthetic individual records.

E1 is represented with `assertion_status: "project_premise"` and `claim_type: "premise"`. Its premise status is separate from evidence grading and is not repeatedly regraded. Downstream testable claims each receive their own scoped evidence. An `established_in_scope` claim requires a supporting evidence record structurally, but passing that validation does not prove the assertion true: scientific review is still necessary.

## Receptors, fluxes and unknown parameters

Ligand concentrations, surface receptor amounts, occupancy and signaling use different IDs. A receptor record explicitly names its binding and transduction model; a null transduction model is an unknown rather than an implied one-to-one response. Affinity parameters may be unknown (`value: null`, `status: "unknown"`); EC50 must not be silently substituted for Kd. Thermodynamic feasibility, element/charge/electron balances and measured flux remain distinct properties.

The receptor illustration is dimensionally transparent: with no competitors, occupied surface receptor amount is `Rs*(L/K)/(1+L/K)`. Changing `L/K` from 1 to 4 and `Rs` from 1 to 0.2 changes occupancy fraction from 0.5 to 0.8 but occupied receptor amount from 0.5 to 0.16. Those are synthetic arbitrary receptor units. Signaling still requires an efficacy/transduction model. No tissue-specific or clinical claim follows from this arithmetic.

## Intervention hypotheses, exposures and causal analyses

An intervention hypothesis links target states and mechanism versions to prerequisites, exclusions, expected direction/delay, measurable/adverse outcomes, confounders, literature and individual analysis history. Its allowed modes are exactly `observation`, `simulation`, and `hypothesis_test`. It contains no executable dosing fields. Exposures are recorded separately from planned assignments, outcome observations and analysis conclusions. Recording an outcome does not establish efficacy.

The causal-analysis contract fixes the estimand, comparator, individual/context and time horizon. It distinguishes assignment-based, exposure-based, adherence-restricted and observational analysis; preserves raw-to-feature-to-outcome lineage; and records missingness, carryover, autocorrelation, multiplicity and protocol deviations. `individual_effect_replicated` requires references to earlier analyses; supported individual effects require a numeric estimate, interval and pinned input/code hashes. Scientific sufficiency is not guaranteed by those fields. A simulation must carry `simulation_only` validity and a simulated or unknown estimate; it cannot claim an observed association or individual effect. A null or failed analysis can retain unknown effect estimates and absent hashes honestly. `mechanism_established` is fixed false in this outcome-analysis object: any directly tested biochemical mechanism requires a separate scoped claim and evidence record.

Negative, adverse, null and failed results persist. Corrections supersede old revisions; they do not delete them. A model retirement must retain the code, assumptions, accepted and failed validation results and individual-response histories needed for replay and successor evaluation.

## Measurement requests

Each request links to its input state and pinned mechanism snapshot, at least two candidate explanations and their contrasting observation patterns, and an unmodeled alternative. The acquisition method, timing, context, feasibility and burden are explicit. A qualitative priority is not an information-gain calculation. Numeric expected information gain is a different tagged object requiring a model version, calibration record, method, interval and assumptions. The synthetic example deliberately uses a qualitative score with unknown quantitative predictions.

## Verification

The reference verifier needs Python with `jsonschema` and `referencing` available. It installs nothing and has no network calls. From this directory run:

```bash
python3 validate_contracts.py
```

The verifier checks the five schema definitions, four examples, snapshot digests, reversed time windows, forbidden modes/fields, unsupported established claims, missing-as-false errors, unjustified individual-effect status, incomplete numeric information-gain claims, and three-valued logic. It writes `validation-report.json`. These are software/data-contract checks; biological validity, causal validity, model calibration, actual device behavior, and complete external-reference integrity remain separate research and integration tasks.

No production files are changed. Rollback for this proposal consists of leaving this isolated directory uninstalled; no service or database migration exists. Future integration should vendor the schemas under a versioned namespace and preserve old versions for historical replay.
