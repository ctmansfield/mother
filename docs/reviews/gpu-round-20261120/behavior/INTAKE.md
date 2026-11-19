# Behavioral pack intake receipt

Prepared under the root task's current authorization to run the scientific GPU
round first and prepare the behavioral round while waiting. This child task is
limited to local source, offline tests and the caller adapter. Root owns all
remote writes and host execution.

Read before implementation through the repository connector:

- `ctmansfield/production-framework/AGENTS.md`, blob
  `482de5adaed6b14e4634814119de4eeb440e825a`.
- `docs/coordination/SESSION_WORKFLOW.md`, blob
  `7523de09471307b625b484eb1a52b792b313420a`.
- `docs/REPOSITORY-POLICY.md`.
- `context/project.json` and `context/index.json`. No existing capsule in that
  index matched the current behavioral GPU pack task.
- Issue #144 and corrected FW00413 `NEXT_ROUND_DESIGN.md`.
- FW00412 broker/specialist caller and prompt boundary at the pinned source.

Rules applied: source and documentation only; no data/model caches or secrets
in repository artifacts; no deployment implied by a Git change; preserve
failures and provenance; no silent role promotion. The E1 literature feature
remains deferred. Root will attach the canonical campaign/session receipt when
integrating the sibling scientific, behavioral and native packages.
