# E1 bibliography patch — release notes
**Version:** E1-REFS-2026-11-19-R1 · **Status:** draft for review

## Changes
- Added 248 distinct bibliographic records, 229 with DOIs and 19 keyed by PMID/URL.
- Preserved all 72 legacy E1 network sources, 70 workbook References rows, 27 Draft 0.2 citations, 17 MSE source-table entries and seven MSE seed citations as **namespaced aliases**.
- Ingested 73 DOI-linked references from the visible November 6–19 Scout digests. Included negative findings, historical works and preprints; **not just supportive studies**.
- Deduplicated overlapping primary source identifiers and linked the two explicitly identified preprint-to-journal successors without counting them as independent evidence.
- Kept the pre-existing MSE-001 snapshot, original project files, and Research Scout / weekly Meta-Research automations unchanged.

## Verification and limitations
- Source counts and exact duplicate keys checked.
- DOI-linked records resolve via DOI-form URLs; PMID-only and data archive records retain source links.
- CSV and JSON are derived from the same reconciled records; run `python3 research/e1/verify_register.py` to reproduce structural checks.
- **Not independently completed:** full-text appraisal of all 248 sources, complete bibliographic metadata enrichment, latest peer-review/correction/retraction confirmation for every record, all-time chat history reconciliation, and causal graph promotion.
- Prior Scout-generated edge grades remain unvalidated model-specific discussion notes. This import is **not evidence that E1 is independently proven**.

## Rollback
Unmerged draft changes can be withdrawn without affecting `main`. After a future merge, use an ordinary Git revert of the merge commit; do not delete prior history.
