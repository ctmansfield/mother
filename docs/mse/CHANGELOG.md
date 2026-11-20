# MSE repository change log

## Repository import 1 — 19 November 2026, Guam

| Change | Reason and resulting behavior |
| --- | --- |
| Add `research/mse/reference-v0.1.0/` | Preserve all original A–I design, executable code, evidence, contracts, proposed SQL and patch artifacts byte-for-byte. No existing application code is replaced. |
| Add `research/mse/IMPORT_SOURCE.json` | Record original archive/manifest identity, import selection and file hashes. |
| Add `research/mse/conftest.py` | Keep isolated prototype tests out of unrelated root pytest discovery; the dedicated verifier explicitly runs them. |
| Add `docs/mse/README.md` and root README link | Make the design and executable reference discoverable in MOTHER. |
| Add current reconciliation and integration addendum | Distinguish current source facts and holds from historical host reports; reconcile new scientific/behavioral federation and memory requirements. |
| Preserve historical coordination review | Retain the earlier decisions, blind spots and evidence locators without presenting them as current runtime evidence. |
| Preserve historical scientific and Coach source notes | Retain supporting reasoning, primary-source references and detailed findings not otherwise stored as standalone files; record source/published hashes and formatting-only normalization. |
| Add repository installation, release notes, import report and independent review | Provide exact operator commands, validation scope, findings and rollback/retention behavior. |
| Add `tools/verify_mse_reference.py` | Fail on changed/missing/extra release files; run existing tests and builders on a temporary copy; preserve original reports. |
| Add pinned design-verification requirement and dedicated workflow | Provide an explicit gate independent of the general workflow's failure suppression. |
| Exclude the immutable reference path from rewriting pre-commit hooks | Preserve original release fingerprints; dedicated integrity and execution checks cover this exact path. New surrounding code and documentation retain normal hooks. |
| Add source-bound context handoff | Make instruction, report, test, merge and runtime states recoverable by later workers. |

No model parameters, original source files, production services, live data,
credentials, device signing or automation schedules are changed. The original
release's detailed change log remains inside the preserved reference.
