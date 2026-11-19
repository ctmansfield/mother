# Run the behavioral GPU comparison

Prepared source; no behavioral host inference has been performed during preparation.

Use this launcher **after** the scientific Ollama screen has completed with all
75 requests and matching positive-VRAM observations. Supply its retained
`results` directory. The launcher validates the source pin, completion/exit
status, all five full digests, raw-ledger hashes, and underlying request,
completion and residency records. Held, incomplete, CPU-only or unobserved
scientific results require review; there is no override or silent bypass.

From the published clean MOTHER checkout:

```bash
python3 -u -B behavior/behavior_compare.py \
  --after-scientific /absolute/path/to/scientific-attempt/results \
  --state "$HOME/.local/state/mother-fw00412/behavior-comparison-20261120-01" \
  --live --gpu-idle-confirmed
```

The companion `RUN-BEHAVIORAL.sh` prepares a fresh attempt and invokes the
launcher. Omitting `--state`, `--live` and `--gpu-idle-confirmed` performs source,
predecessor, installed-inventory and idle checks without inference. `--help`
makes no API or GPU calls.

Each of the **same five candidates and full digests** from the scientific run
receives all 24 behavioral cases in identical order with the same seeds:
**120 maximum serial requests**. The adapter retains completed-response
format/truncation failures as test results and continues the remaining cases.
An ambiguous completion, identity/resource guard failure or exhausted budget
holds further requests. Existing attempts remain untouched.

The published scientific loopback transport and observer are reused unchanged:
no ambient proxy, no redirects, no pulls or installs, no posts, and no process
termination. The same `scientific-gpu.lock` serializes cooperating scientific,
native and behavioral invocations. This is a cooperative lock with repeated
contention checks, not a global GPU reservation. A final idle check is required
before successful completion.

Request parameters are temperature 0, context 4096, at most 900 output tokens,
and seed `20261120 + case_index`. Each HTTP request has a 120-second timeout,
with the scientific observer's 135-second active-request budget plus bounded
in-progress monitor operations. The total campaign budget is **20,000 seconds
(5 hours 33 minutes 20 seconds)** including load, monitoring and idle checks;
this is a worst-case bound, not an expected completion time.

Private output contains `preflight.json`, `comparison.json`, `exit.code`, five
candidate directories with adapter records/summaries, and matching telemetry
plus request-intent logs. Actual attempted requests, recorded case slots,
completed response slots, usable responses, structured correctness and GPU
evidence have separate counts. The prose rationales remain for human review.
Positive `size_vram` proves observed residency/offload, not that every operation
ran on GPU. All 120 observations must be present before that GPU-evidence flag
is true; CPU/missed observations remain explicitly classified.

`check_scientific_predecessor(path)` is also a reusable read-only gate for the
native launcher. It does not contact Ollama, load a model or query a GPU.

Focused launcher checks:

```bash
python3 -B -m unittest discover -s behavior/tests -p test_comparison.py -v
```

These use synthetic predecessor files and fake APIs, including a complete
120-call comparison. Their successful result validates orchestration only.
