# E1 — Consolidated Mechanistic Literature Reference Register

**Version:** E1-REFS-2026-11-19-R1 · **Assembled:** 19 November 2026 (Guam)

## Canonical index

- [REFERENCE_REGISTER.json](REFERENCE_REGISTER.json) — canonical merged bibliography with provenance, stable source identifiers, scope/verification flags, links, and research-mechanism notes.
- [REFERENCE_REGISTER.csv](REFERENCE_REGISTER.csv) — filterable flat export of the same records.
- [RELEASE_NOTES.md](RELEASE_NOTES.md) — source inventory, deduplication and verification limits.

**Imported:** 72 pre-existing evidence-network references (D:S01–S72), 70 evidence-map workbook references (W:R01–R70), and 73 DOI-linked citations discussed in November 6–19 Research Scout digests. These yield **211 distinct reference records**, of which 194 have DOI keys. This is an accessible-material reconciliation, **not** an assertion that all works ever discussed in all chats have been accessed.

DOI is the authoritative bibliographic join key when present. Historic reference IDs remain namespaced aliases. Published-version links collapse duplicate preprint predecessors without treating them as independent replication. Entries without DOIs (e.g., data accessions) use source URLs.

**E1 is the project's fixed working premise**, not a claim independently established by every cited paper. Studies may support an individual reaction, compete with a proposed mechanism, provide necessary methodological controls, or report negative results. Store causal evidence grades **on particular model-specific edges**, not as a general endorsement of E1.

## Evidence handling and verification

- `primary_source_status` distinguishes original historical bibliographies, Scout-attributed references requiring primary recheck, and selected primary landing pages checked in this session.
- `peer_review_status` keeps preprints, inherited journal status, and uncertain entries distinct. Preprint versions and publication-status claims require refreshed source verification before mechanistic promotion.
- `edge_grades_as_discussed` are **unvalidated labels from prior Scout narrative**, not fresh quality appraisals. Evidence grade A applies only to causal tests in their exact experimental model.
- `scout_dates` are *discovery/discussion* dates. They are not release dates.
- `proposed_map_ids` are uncommitted candidate identifiers. Nothing in this import creates an approved graph edge, updates interventions, or confirms in vivo metabolic flux.

## Relationship to repository MSE and weekly reports

This import is additive and does not rewrite the immutable MSE-001 reference under PR #12, or change MOTHER/COACH services, Research Scout automation, or weekly Meta-Research schedules.

Future research passes should reconcile DOI, PMID, preprint version, corrections, and mapped claims against this registry. Promote a claim only after independent source verification; contradictory and negative findings should remain visible. Do not reuse an established edge ID for a different mechanism.

## Source artifacts used

The underlying pre-existing `Host_Microbial_Equilibrium_Network.json` (evidence cutoff 12 October 2026) and `microbiome_ecological_evidence_map_v1.0.xlsx` (References sheet) were accessible in the user's library. The original materials were not edited or replaced; records were imported into this repository with their S and R identifiers retained. The November 6–19 Research Scout digests supplied additional candidate references and source links.

This catalog is suitable for review and downstream deduplication, but source-level verification and scientific appraisal remain outstanding for numerous imported records.
