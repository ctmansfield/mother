# Local worker qualification

## Runtime evidence requirements

Qualification records the serving daemon version, full installed model digest,
model metadata, requested and observed context, residency, resource use and
timing. Installed artifacts and resident models are distinct observations.
Each OS installation must be checked independently; installation count does not
establish the number of available physical compute resources.

Runtime reports contain installation-specific technical inventory. Return them
through the private project handoff; keep them out of repository commits and
public review descriptions. The repository retains generic probe code,
synthetic fixtures and reproducible acceptance criteria.

The example model is `qwen2.5-coder:7b`. Its published artifact listing identifies
7.62B parameters and Q4_K_M quantization. The probe captures the complete local
digest and metadata before inference. Source inspection supports the probe's
API shapes on Ollama v0.12.0; actual tool behavior, placement, throughput and
coding accuracy require installation-specific qualification.

## Immediate assignment: LW-001

**Owner:** PM for implementation and protocol boundaries; a separate verifier
owns the new tests and review report. **Owned paths:** `tools/local_workers/`,
this operating record, and the corresponding task-board/change-log entries.
The shared physiological schema and archive migration remain unchanged.

The standalone probe gathers model identity, runtime/context/residency and
bounded synthetic structured-output/native-tool evidence. The model generates
one structured record and, when advertised, one native tool-call request. No
generated tool is executed. Existing reports are preserved; model downloads and
server reconfiguration are outside this task.

**Acceptance:** installed model identity matches the requested snapshot; server
metadata is retained; known zero and unknown availability survive structured
output; a declared native tool capability is checked against an actual parsed
call shape; failures and missing capabilities remain distinct. GPU residency is
observed rather than inferred from the model file size.

**Required return:** report JSON, exact model/server/context identifiers, passed
and failed checks, API and client timing, residency metadata, and unresolved
capabilities. All reports keep `repository_work_qualified=false`.

## Subsequent gate: four bounded repository tasks

Use one pinned model/configuration and isolated disposable worktrees. Keep one
schema/migration owner and independent acceptance tests. Qualify:

1. Mapping a synthetic source fixture into the frozen observation contract.
2. Repairing a seeded timestamp or future-window defect within assigned files.
3. Adding archive repeat/correction/interruption tests that detect seeded faults.
4. Reviewing a defective patch and producing accurate INSTALL/VERIFY notes.

Record accepted work, missed defects, scope violations, reviewer effort,
elapsed time and measured resource use. Expand local responsibility by the
task categories supported by those results. No percentage of project completion
or equivalence with a larger model is asserted before qualification.

Start with one resident coding model and queued inference requests. Logical
worker roles may share it while keeping separate contexts and worktrees.
Deterministic import/archive/replay/evaluation/test jobs execute as ordinary
local software. A bounded artifact runner is provided by LW-002. It supplies
four fixed task contexts and retains proposed artifacts for independent review.
A remote coordinator connection and autonomous repository operation remain
separate work. A successful runtime or response-schema check does not qualify
the proposed code.

### Separate protocol and task correctness

Native-tool parsing and schema-constrained generation are distinct interfaces.
A failed native-tool response does not prevent a fixed runner from submitting
curated coding tasks through structured generation. Retain the failure and its
exact prompt condition; do not reinterpret ordinary content as an executed call.

LW-002 acceptance criteria are frozen before real task responses are read. The
model receives only the task manifest, not independent expected answers.
Responses remain data until reviewed. Installation reports and task responses
belong in the private handoff. See `tools/local_workers/QUALIFY.md` for task
ownership, limits and interpretation.

Physiological outcome definitions, device/garment choices and intervention
principles remain with the design session. Local worker qualification can
proceed before the first representative personal source bundle is supplied.

## Evidence references

- [Ollama v0.12.0 API](https://github.com/ollama/ollama/blob/v0.12.0/docs/api.md),
  request/response types, handlers and capability detection at tag commit
  `9f3a37fd36bf1c46cc86a47bc5372535f8ee3547`.
- [Published Qwen2.5-Coder 7B artifact](https://ollama.com/library/qwen2.5-coder:7b).
- `tools/local_workers/README.md` and the independently authored offline tests.
