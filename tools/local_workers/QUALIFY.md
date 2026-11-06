# LW-002 — Bounded local artifact qualification

Version: `local-artifact-qualification/1.0.0`.

This trial measures proposed artifacts from four fixed synthetic software tasks.
The runner supplies curated context to Ollama's schema-constrained generation
endpoint and retains responses as data for independent review. Native tool
calling is a separate capability; an LW-001 native-tool failure remains a
failed native-tool result.

## Fixed task scope

| Task | Proposed artifact | Independent acceptance |
| --- | --- | --- |
| Contract mapping | Two synthetic observations as constructor arguments | UTC instants, four clock meanings, zero, missingness, original timestamp, identities and lineage |
| Timestamp repair | A replacement module as text for one fixture path | Preserve the instant, reject unknown timezone and invalid input, limit scope; inspect before behavioral testing |
| Archive tests | Input/output vectors | Idempotent repeats, retained corrections, interruption/replay, and checkpoint advancement after a completed page |
| Review and release | Anchored findings and release action IDs | Availability cutoffs, missing values, action versus acknowledgment, missing outcomes, and truthful verification claims |

Fixture paths are scope labels. The runner does not create them or apply a
proposed patch. `qualification_tasks.json` is the sole task-context manifest.
`qualification_acceptance.json` is frozen independent review material and is
never included in inference requests.

## Run

Python 3.9 or newer and an already installed Ollama model are required. The
standard library is sufficient. From this directory, choose an output filename
outside the repository and pin the intended installed artifact:

```bash
python3 qualify.py \
  --model qwen2.5-coder:7b \
  --expected-digest-prefix dae161e27b0e \
  --output /incoming/lw002-report.json
```

The example pin identifies the published example artifact. Use the intended
installation's full digest for a strict recorded trial. Existing reports are
preserved; choose a new output name for a subsequent attempt.

Each of four requests uses temperature 0, seed 0, a 4,096-token context, a
1,536-token output budget, and a two-minute model-retention request. Requests
are sequential and independently bounded by the loopback-only client. The
runner verifies installed identity before inference and records task-manifest,
prompt and schema hashes, raw output, completion state and timing. Completed
results are saved before advancing to the next task.

Return the complete report through the private project handoff. It includes
installation-specific model metadata and proposed source text. Keep reports
out of public commits and review descriptions.

## Interpret results

`artifact_received` means a task returned complete, strict JSON matching its
response schema. Semantic correctness is still pending. A zero process status
means all four artifacts were received for review; it does not mean four
correct solutions. Failure on one task is preserved while the other independent
tasks are attempted.

The report always keeps repository and autonomous-worker qualification false.
Generated code and tools are not executed. Malformed output, wrong task
identity, unknown fields, duplicate members, nonfinite numbers and truncated
generation must not silently become accepted artifacts.

The independent reviewer uses the frozen acceptance file, reviews proposed
source before subsequent execution, and records substantive correctness
separately from protocol validity. Unsupported repair forms receive review,
not an automatic incorrectness judgment. This small fixture trial supports
decisions about the next bounded assignment; it does not establish a general
coding-success percentage or personal physiological model performance.

## Verification

From this directory:

```bash
python3 -m unittest discover -s . -p 'test_*.py' -v
```

Controlled tests use synthetic HTTP responses and do not contact an installed
model. Portable release evidence records the command, Python version, exact
source identities and results. Actual model-task results are separate evidence.

## Native-tool diagnosis

For template-driven Ollama v0.12.0 chat, the tool parser derives its opening
marker from the template's `.ToolCalls` branch. The published example template
uses `<tool_call>`. JSON emitted without that marker can remain ordinary
message content even when its function name and arguments are correct.
Native qualification still requires structured `message.tool_calls`; this
runner uses `/api/generate` and does not reinterpret content as a native call.

Protocol sources:

- [Pinned tool parser](https://github.com/ollama/ollama/blob/v0.12.0/tools/tools.go)
- [Pinned marker extraction](https://github.com/ollama/ollama/blob/v0.12.0/tools/template.go)
- [Published example template](https://ollama.com/library/qwen2.5-coder:7b/blobs/1e65450c3067)

Reinforcing the marker in a separate native-tool prompt is a possible later
diagnostic. Retain that distinct prompt condition and the previous failure.
