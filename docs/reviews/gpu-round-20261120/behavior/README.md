# Behavioral model screen — 24 synthetic cases

This package prepares the behavioral comparison that follows the scientific
GPU comparison. It contains a frozen test pack, a deterministic structured
scorer and a bounded caller adapter. **Preparation and offline tests have made
zero model calls. No behavioral model has been qualified or assigned a role.**

The literature-download work remains deferred as open issue #145. This package
does not download articles or use real participant records.

## Run order and integration

Run the scientific campaign first. Start this pack only after that campaign
has finished, its inference completion is known, and the shared GPU is idle.
The external orchestrator must hold the same exclusive campaign lock across
the scientific and behavioral stages. Each behavioral candidate gets all
24 cases, in the same order and with the same seeds. Never run the two stages
or two candidates concurrently on that GPU.

The integrated `behavior_compare.py` launcher described in `LAUNCHER.md` owns
these checks and reuses the scientific transport, observer and shared lock.
The underlying adapter is a Python API:

```python
from behavior.adapter import run_model

summary = run_model(
    output_dir=fresh_candidate_directory,
    model=verified_model_tag,
    model_digest=verified_full_64_character_digest,
    source_pin=verified_full_40_character_source_commit,
    call=serialized_local_caller,
    seed=20261120,
)
```

`serialized_local_caller(model, prompt, options)` must return the ordinary
Ollama `/api/generate` response dictionary and raise when an external guard
fails. The adapter itself imports no HTTP client and makes no network calls.
It does not pull, unload, delete or substitute models.

The adjacent scientific observer supports this callback shape:

```python
from scientific.scientific_compare import ObservedAPI, local_api

observer = ObservedAPI(
    local_api(), verified_model_tag, verified_full_digest,
    telemetry_path, max_requests=24, deadline=campaign_deadline,
)

def serialized_local_caller(model, prompt, options):
    reply = observer('/api/generate', {
        'model': model, 'prompt': prompt, 'options': options,
        'stream': False, 'format': 'json', 'keep_alive': '0s',
    }, timeout=120)
    if observer.hold:
        raise RuntimeError('External model/GPU observer held further inference')
    return reply
```

Use the scientific wrapper's direct-loopback `local_api()` transport, which
disables ambient HTTP proxies and refuses redirects. Do not substitute a
proxy-sensitive transport.

This snippet belongs **inside the already-locked orchestrator**, after its
source, local endpoint, installed full-digest, prior completion and GPU idle
checks. The orchestrator also owns the shared absolute wall-clock deadline,
ongoing model/GPU identity observations, final idle check and telemetry
interpretation. A positive Ollama VRAM observation is evidence of residency or
offload during the request; it does not prove every calculation ran on GPU.
The adapter's output deliberately says `EXTERNAL_ORCHESTRATOR_REQUIRED` for
GPU verification. An adapter summary alone cannot establish a GPU run.

The adapter permits at most 24 serial requests per candidate. Parameters are
temperature 0, context 4096, maximum 900 output tokens, and seed `20261120 +
zero_based_case_index`. The caller supplies the per-request timeout. A caller
refusal, wrong response model, unfinished generation or unknown response
envelope stops the remaining requests and preserves the partial result. A
matched, completed response with truncation, a non-text value, oversized output,
malformed JSON or an incorrect structured answer is scored as such and the
bounded comparison continues. Raw output is bounded and hashed before checking
completed-response failures. `complete` means all 24 slots were recorded with
no fatal hold; `completed_case_slots` and `successful_requests` separately show
how many calls completed and how many had usable response envelopes.

## What is tested

The model sees only the case's role, question, fictional facts, candidate
conclusions and requested numeric quantities. IDs such as `beh-001` do not
contain the expected variant. Every role has one supported case, one context
change, one conflict and one insufficient-evidence case.

| Responsibility | Cases | Discriminations |
| --- | --- | --- |
| Measurement | 001–004 | Reported construct versus mechanism or diagnosis; incompatible scales; contradictory reports; uninterpretable bare totals |
| State and context | 005–008 | Temporary change versus stable trait; sampling-phase changes; distinct observation channels; insufficient longitudinal evidence |
| Learning and decision | 009–012 | Reward reversal; opportunity versus motivation; equivalent model fit and discriminating predictions; unidentified mechanism |
| Dynamics | 013–016 | Opposite pooled and within-person signs; observation versus availability time; context-dependent associations; per-person minimum observations |
| Strategy and experiment | 017–020 | Recommendation, acknowledgement, action and outcome; endpoint-specific benefit; unresolved tradeoffs; prediction versus observed causal benefit |
| Host feedback | 021–024 | Temporal order and reverse-causal alternatives; ligand amount versus receptor engagement; context-dependent host effects; unmeasured pathway links |

Eight cases contain either a relevance distractor or a time-ineligible fact.
Simply citing every visible fact fails those cases. Nine cases request
arithmetic, including a Simpson reversal where both within-person correlations
are −1 while the pooled correlation is approximately +0.904762.

The data and mechanisms are deliberately fictional. The E1 host-foundation
premise remains intact; the final cases test whether a model invents missing
measurement links, not whether that foundational premise should be rejected.

## Response and grading contract

The model must return one duplicate-free JSON object with exactly these fields:

```json
{
  "schema": "fw00413.behavioral-model-response.v1",
  "case_id": "beh-001",
  "role": "MEASUREMENT",
  "decision": "SELECT",
  "conclusion_id": "c-b",
  "evidence_ids": ["f-1", "f-2"],
  "excluded_evidence_ids": [],
  "numeric": {"score-change": 4},
  "rationale": "A short explanation for later human review."
}
```

This example illustrates the contract and is not injected into any model
prompt. `SELECT` chooses a supported descriptive conclusion, including a
supported limitation. `HOLD` chooses
the listed conclusion preserving an unresolved conflict or incompatibility.
`ABSTAIN` uses a null conclusion when none of the supplied conclusions is
warranted for the requested claim.
Requested arithmetic must still be supplied when the substantive conclusion
requires abstention.

The scorer reports distinct dimensions:

| Dimension | Test |
| --- | --- |
| Protocol | Exact fields, types, enums, duplicate-free JSON and finite numeric values |
| Case binding | Returned role and case ID match the actual request |
| Evidence ID validity | IDs exist in the case and are not simultaneously cited and excluded |
| Evidence relevance | Cited IDs belong to the protected acceptable evidence set |
| Evidence completeness | At least one protected sufficient evidence set is included |
| Temporal exclusions | Excluded IDs exactly match the predeclared time-ineligible facts |
| Structured decision | Decision category and conclusion choice match the controlled rubric |
| Arithmetic | Exact requested keys and predeclared absolute tolerances |
| Critical errors | Changed identity, fabricated/conflicting IDs, future/unavailable evidence, invented conclusion or predeclared critical inference |

`structured_correct` requires all applicable dimensions and no critical error.
Schema compliance alone does not count as correctness. An all-abstain strategy
can answer only the six insufficient cases correctly, even if supplied all
other oracle fields; it fails the other eighteen.

The rationale is bounded and retained, **not scored by keywords or treated as
automatically verified reasoning**. A response can have correct structured
fields and a defective prose explanation; the separate rationale-review status
remains `NOT_PERFORMED`. Human review must inspect prose contradictions and
the full response before drawing any suitability conclusion.

## Frozen inputs and protected key

`fixtures/cases.json` is the model-visible case data. The caller receives only
the prompt constructed from one of those records. `protected/answer_key.json`
contains expected decisions, accepted evidence, numeric tolerances and critical
inferences. `PACK_MANIFEST.json` binds the exact bytes of both files; every run
records its pack SHA-256:

`803d7c62e0574974ceb729b238f92e02c27d90af787ddc522b92078685e8319b`

“Protected” means withheld from the model request by this adapter. The key is
ordinary source under host control; it is not a security sandbox, independent
test-set custodian or guarantee against prior exposure. Do not put it into
model retrieval, chat history or the callback. A changed case or rubric requires
an explicitly versioned new pack and fresh results, not silent mutation of this
campaign's input files.

## Offline validation commands

From the parent `gpu-round-20261120` directory:

```bash
python3 -B behavior/benchmark.py validate
python3 -B -m unittest discover -s behavior/tests -v
```

To inspect one model-visible prompt without making an inference request:

```bash
python3 -B behavior/benchmark.py prompt --case-id beh-014
```

To check release file hashes, run this from the `behavior` directory:

```bash
sha256sum -c SHA256SUMS
```

These commands perform no downloads, installation, model access or network
calls. They do not set strict shell flags or close the calling terminal.

## Evidence retained by a live adapter run

Each candidate requires a fresh directory. It is created with mode 0700; files
are created with mode 0600. Existing output is never overwritten. The files are:

- `run_manifest.json`: source pin, candidate tag and full digest, frozen pack,
  ordered cases, seeds and request limits.
- `records.jsonl`: one fsynced record per completed or refused callback,
  including prompt hash, bounded raw response, response hash, structured grade,
  request status, elapsed time and available Ollama timings.
- `summary.json`: separate per-role metrics, interruption/completion status,
  unattempted case count and result-ledger hash.

External observer telemetry supplies GPU residency evidence and any attempted
request whose completion remains ambiguous after interruption. Keep it beside
these files. Do not retry an ambiguous request until the host has been checked.

## Interpretation limits

This is a small, finite-choice synthetic reasoning screen with four cases per
role. It is not a clinical evaluation, independent held-out benchmark,
validation of psychological constructs, causal study of people, or evidence
that a model should make health decisions. No automatic passing threshold or
permanent role assignment is defined. Compare each candidate's structured
answers, arithmetic, critical errors, abstentions, prose and runtime evidence.

The four multistep episodes in `FW00413/NEXT_ROUND_DESIGN.md` remain a subsequent
test design. This pack does not claim to test persistent episode memory,
real longitudinal forecasting, native specialist runtimes or intervention
effectiveness. Offline oracle and mocked-caller tests validate the harness;
their scores are not model-performance results.
