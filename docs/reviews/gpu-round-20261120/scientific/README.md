# Scientific GPU comparison — Ollama reasoning screen

Prepared source only. No host inference has been run by this preparation.

This first pass compares `gpt-oss:20b`, `medgemma1.5:4b`, `medgemma:27b`,
`deepseek-r1:14b`, and `ministral-3:14b` against the same 15 protected FW00412
scientific evidence-boundary cases. Each model sees all five roles with identical
prompts, case order and seeds: at most **75 serial inference requests**. The
MedGemma variants are scientific candidates; the other models are reasoning
controls. These are experimental candidates, with no permanent role assignment.

This does not exercise the native MedCPT retrieval, TxGemma, Boltz2 structural
or TimesFM forecasting runtimes. Their expected environments/cache paths are
reported by a cheap existence check only; their capability tests are separate.

## Start the run

Use Python 3.10+ and a clean checkout of `ctmansfield/production-framework`
detached at `ba6fbb90c031f122b7db61d2f67f2b22ef1cf130`. No Python packages
need installing for this wrapper. The host must already have all five candidate
tags, a working local Ollama at `127.0.0.1:11434`, and `nvidia-smi`.

The exact prior offline host receipt is required in
`~/.local/state/mother-fw00412/offline-ba6fbb90c031`, including `source-pin.txt`,
`exit.code`, `github-return-url.txt`, and the matching `summary.json`.

From this directory, after the completed coding run has released the GPU:

```bash
python3 -B scientific_compare.py \
  --checkout /absolute/path/to/fw00412-checkout \
  --candidates candidates.json \
  --state "$HOME/.local/state/mother-fw00412/comparison-20261120-01" \
  --live --gpu-idle-confirmed
```

The companion `RUN-SCIENTIFIC.sh` in the published source package prepares the
exact checkout and invokes this command. For a read-only preflight, omit
`--state`, `--live` and `--gpu-idle-confirmed`. Preflight checks the exact source,
inherited manifests, prior offline receipt, **all five installed full digests**,
idle Ollama and NVIDIA compute processes. A missing model stops the launch;
there is no automatic model pull or substitution.
The injected transport fixes the address to `127.0.0.1:11434`, ignores ambient
proxy settings, refuses redirects, and permits only tags, residency and generate
endpoints. It preserves the original broker's response-size budget.

Each request keeps the original broker parameters: temperature 0, context 4096,
maximum 520 output tokens, and `keep_alive=0s`. The original HTTP timeout is
120 seconds; the observer allows at most 135 seconds of wall time for an active
request, plus any bounded in-progress monitor operation. The campaign budget
is **12,000 seconds (3 hours 20 minutes)**, including model load, telemetry and
idle checks. There is a maximum 12-second natural unload wait between requests;
no unload/kill command is sent. Calls are serialized. This is a worst-case
budget, not an expected completion time.

## What gets recorded

The private, single-use campaign directory contains:

- `preflight.json`: full candidate digests, source/config/wrapper hashes,
  offline receipt, NVIDIA inventory, and native runtime/cache existence.
- `model-01` through `model-05`: unchanged broker raw responses, per-role
  correctness/protocol/abstention/error metrics, and candidate role matrices.
- `telemetry-XX.attempts.jsonl`: request intent written before HTTP dispatch,
  so interruption cannot silently erase an ambiguous attempted call.
- `telemetry-XX.jsonl`: full request/response, matching `/api/ps` residency
  samples, NVIDIA memory/utilization/process observations, and monitor errors.
- `comparison.json`: actual attempted calls, task-slot counts, per-model role
  scores, separate GPU evidence counts, and any hold reason.
- `exit.code`: 0 means the screen completed; 4 means it was held after claiming
  a campaign. Neither value grants scientific validation or deployment.

`GPU_RESIDENT_OBSERVED` requires a matching model name and full digest with a
positive integer `size_vram` sampled while that request is active. It proves
observed GPU residency/offload, **not that every computation ran on the GPU**.
The raw `size` and `size_vram` values are retained.
`CPU_RESIDENT_OBSERVED` requires matching residency with a valid zero value.
Missing, invalid or missed samples are `UNOBSERVED`. These categories stay
separate from correctness and protocol validity, and do not skip later cases.

The package advisory lock coordinates other FW00412 invocations only. It is
not a global GPU reservation. Idle/process checks are repeated. Foreign loaded
models, changed digests, unattributed compute processes, ambiguous HTTP
completion or exhausted time budgets hold further inference; they do not
terminate somebody else's work. Inspect preserved evidence before any new
attempt. Never automatically repeat a request whose completion is uncertain.

The wrapper does not call the original `qualify.sh`, because that script
publishes a GitHub comment. This wrapper makes **no GitHub posts**, pulls,
installs, credential changes, deployments or routing promotions.

## Focused verification

```bash
FW00412_TEST_CHECKOUT=/absolute/path/to/reviewed/source \
  python3 -B -m unittest -v test_scientific_compare.py
```

Tests use fake APIs only. They check full candidate/digest refusal, meaningful
GPU classification, process contention, ambiguous completion, request budgets,
and the same 15 prompts/seeds for all five candidates through the unchanged
broker. The prior protected CPU suites are not rerun by this launcher.

## Source dependencies

- [Pinned broker](https://github.com/ctmansfield/production-framework/blob/ba6fbb90c031f122b7db61d2f67f2b22ef1cf130/packages/fw00412/broker.py)
- [Verified offline host receipt](https://github.com/ctmansfield/production-framework/issues/139#issuecomment-7009907399)
- [Ollama `/api/ps` residency schema](https://docs.ollama.com/api/ps)

See `source-dependencies.json` for the exact source and receipt hashes, and
`SHA256SUMS` for this wrapper package. Fifteen synthetic cases per candidate
are a first evidence-boundary screen; they do not estimate general scientific
reliability or verify the full native scientific stack.
