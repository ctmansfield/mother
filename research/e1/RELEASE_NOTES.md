# E1 reference consolidation — release notes
Date: 2026-11-19. Release: E1-REFS-2026-11-19-R1.

## Changes
- Added 250 deduplicated reference entries (228 DOI-keyed; 22 PMID/URL-keyed), cross-linked to legacy namespaced source identifiers.
- Preserved 72 dossier source entries and 70 evidence-map workbook rows, then reconciled 73 DOI-linked items from visible Research Scout discussions.
- Linked superseded preprints to published successors without counting them as replications.
- Retained unreviewed attributions, negative/contrary findings, preprint status, and unresolved causal/clinical dependencies instead of treating E1 as proven.
- Kept MSE-001 snapshot and existing automations untouched.

## Verification
- Reference input counts verified before export: dossier 72, workbook 70, Scout 73.
- All canonical record keys unique and all DOI-bearing records linked to a DOI resolver.
- CSV and JSON were generated from the same in-memory records.
- Original artifacts and main branch not overwritten; draft PR proposed for review.
- **Not done:** manual primary-source full-text appraisal, retraction check for every article, exhaustive historical-chat reconciliation, programmatic updating of older Excel/Word library copies, scientific validation of conditional graph edges.

## Review workflow
Compare `REFERENCE_REGISTER.json` and `REFERENCE_REGISTER.csv`, verify source DOI/PMID and preprint-successor correspondence, fill missing publication dates, and annotate specific reaction/host/organism/model edges with necessity/rescue evidence. Merge only after review.

## Additional reconciliation pass
- Imported 27 manuscript references from Draft 0.2, 17 MSE scientific-source entries (including papers, guidance and official HealthKit documentation), and seven MSE seed-map references, without rewriting immutable MSE-001 payloads.
- Newly generated register totals: 250 distinct records; 228 DOI-keyed.
- All new DOI/PMID citation metadata is inherited from accessible original documents, not freshly appraised for causality or corrections.
