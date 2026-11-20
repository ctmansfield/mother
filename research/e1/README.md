# E1 — Consolidated Mechanistic Literature Reference Register

**Release:** E1-REFS-2026-11-19-R1 · **Assembled:** 19 November 2026 (Guam)

## Canonical E1 bibliography in MOTHER

- [REFERENCE_REGISTER.json](REFERENCE_REGISTER.json) — master reference list with DOI, PMID, source provenance, original identifiers and mechanism notes.
- [REFERENCE_REGISTER.csv](REFERENCE_REGISTER.csv) — flat, filterable reference table.
- [verify_register.py](verify_register.py) — validates source counts, keys, cross-references and CSV/JSON parity.
- [RELEASE_NOTES.md](RELEASE_NOTES.md) — patch notes, verification status and limitations.

**Consolidated result:** **248 distinct source records** (229 DOI-keyed, 19 PMID/URL-keyed). These were reconciled from **72 original evidence-network citations**, **70 workbook citations**, **73 DOI-linked Scout-digest entries**, **27 Draft 0.2 references**, **17 MSE scientific-foundations entries**, and **7 MSE mechanism-seed references**. All numbers refer to source *entries* before deduplication except the distinct count.

Legacy IDs are preserved as namespaced aliases: `D:S01–S72`, `W:R01–R70`, `DRAFT02:1–27`, `MSE:S1–S17`, `MSE-SEED:1–7`. DOI and PMID are preferred join keys; source URLs are retained for unkeyed datasets or official documentation. Two published-version/preprint links are recorded explicitly, without counting predecessors as independent replication.

## Scientific interpretation and verification boundary

**E1 is the fixed research premise, not an independently proven conclusion of this bibliography.** The included records encompass positive experimental evidence, contrary and negative outcomes, observational associations, historical foundational work, methodological controls, preprints and datasets. Each paper supports only specific edges in its tested organism, model, cell or assay. Grade A–D refers to an edge/model claim, not blanket proof of E1 or clinical efficacy.

`primary_source_status` identifies which original DOI pages were checked during this consolidation and which records were inherited from prior summaries or library source documents. Many entries still need manual original-source full-text verification, corrections/retraction checks, model-specific perturbation/rescue appraisal and publication-version reconciliation. Scout summary text is a **candidate lead**, not an independently verified biological fact. `scout_dates` are discussion dates, **not publication dates**.

Do not use this bibliography to infer individual clinical mechanisms or recommend treatments. Keep measured metabolites, flux, enzyme capacity, receptor engagement, signaling, host outcomes and ecological feedback as distinct claims. Promote hypotheses to causal map edges only after independent source verification.

## Provenance and relationship to MSE

Inputs were the accessible library `Host_Microbial_Equilibrium_Network.json` (research cutoff 12 Oct 2026), `microbiome_ecological_evidence_map_v1.0.xlsx` References sheet, `Host_Microbial_Equilibrium_Draft_0_2.md`, and the November 6–19 Scout digests in this conversation. The two MSE reference documents were read from the unmerged MOTHER draft [PR #12](https://github.com/ctmansfield/mother/pull/12). None of these originals was overwritten; the MSE reference stays immutable.

This versioned import is additive and changes **neither** MOTHER/COACH runtime, Research Scout automation, **nor** the weekly Meta-Research report/schedule.

## Check

From repository root:

```bash
python3 research/e1/verify_register.py
```

This verifies structural integrity, **not** scientific validity. Future Scouts should query the canonical DOI/PMID and candidate map IDs before proposing new bibliography entries.
