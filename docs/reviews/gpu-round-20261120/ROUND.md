# Scientific GPU first; behavioral comparison next

20 November 2026 (Pacific/Guam)

## Current instruction

The user deferred literature downloads and requested scientific GPU evaluation first, with behavioral preparation continuing while the scientific experiment runs. [Literature issue #145](https://github.com/ctmansfield/production-framework/issues/145) remains open. The earlier E1 acquisition handoff is not the next action.

This directory is an operator-invoked experiment package. No host inference has been observed from this ChatGPT session. The attempted SSH connection failed in the local SSH client before a connection was established. Source publication is separate from running this experiment on `llm`. The initial scientific launcher was released at `8711a81b15880bdca7a7e050839073138556d442`; its scientific code is unchanged in this extension.

## First launch: Ollama scientific comparison

Run `bash docs/reviews/gpu-round-20261120/RUN-SCIENTIFIC.sh` from a clean, pinned MOTHER checkout on `llm`. The script creates a new private attempt directory, clones the exact framework dependency, and starts the comparative wrapper. It leaves previous attempts available.

Framework source: `ba6fbb90c031f122b7db61d2f67f2b22ef1cf130`.
Required prior host qualification: [FW00412 offline receipt](https://github.com/ctmansfield/production-framework/issues/139#issuecomment-7009907399).

The reviewed comparison has 75 task opportunities: five candidates, each receiving all 15 unchanged FW00412 synthetic scientific cases in the same order and with the same seeds. The candidates are `gpt-oss:20b`, `medgemma1.5:4b`, `medgemma:27b`, `deepseek-r1:14b`, and `ministral-3:14b`. Their historical tags are a proposed comparison roster; current installation and full digests must be observed on the host before inference. A missing or changed candidate is a hold requiring inspection, not a silent substitution.

This is a scientific evidence-boundary reasoning screen. The five tested responsibilities are source interpretation, ecology, metabolism, receptor interpretation, and host interpretation. The framework's protected cases and grader remain unchanged. The screen does not measure retrieval quality, molecular structure accuracy, clinical performance, or scientific validity of E1.

## Required evidence and sequencing

Each request retains the exact model identity, prompt/seed, raw response, protected grade, and observations of the matching model's GPU residency while the request is active. Positive `size_vram` establishes observed GPU residency or offload; it does not establish that every layer or computation ran on the GPU. Task correctness, protocol failures, CPU observations, unobserved residency, and incomplete attempts remain separate.

The wrapper uses the FW00412 advisory GPU lock and repeated Ollama/NVIDIA idle and process observations. This does not reserve the entire host against unrelated schedulers. A contender or ambiguous completion holds later requests. Run only one GPU experiment at a time; the behavioral run follows the scientific run. Neither script takes over another workload.

The existing scientific per-call HTTP limit is 120 seconds. The comparative wrapper has an additional whole-run bound; the launch script's last-resort client watchdog is 12,500 seconds. Actual duration is unknown until measured. If a client timeout or watchdog leaves server completion uncertain, inspect the retained attempt and current GPU state before any new inference.

Results stay in the printed `LOCAL EVIDENCE` directory. The handoff sends no issue comments. A completed harness run is an experiment receipt; it does not assign permanent specialist roles or promote a scientific claim.

## Second stage: native scientific engines

The [scientific capability registry](https://github.com/ctmansfield/production-framework/blob/7cc2035a7077523f33d9f47b6bb44de17adecc84/docs/mother-coach/FW004_MODEL_CAPABILITY_REGISTRY.md) also names native MedCPT, TxGemma, Boltz-2, and TimesFM assets. Historical downloads or imports are not GPU inference evidence.

Separate native adapters are prepared for paired MedCPT retrieval and TxGemma generation. They use cached assets, freeze local provenance, and verify CUDA parameter, buffer, input and output placement. MedCPT ranks eight fictional article snippets for four synthetic queries, with close negatives and a lexical baseline. TxGemma receives the same 15 protected scientific cases at cached revision `bc45665ceb345eea6acfc44d82706e8d8b689209`.

TxGemma's native chat template, bfloat16 precision and unconstrained JSON output differ from the Ollama runtime. Its result is a comparison under different runtime conditions, not a model-only ranking. Boltz-2 and TimesFM require their own task-specific fixtures and runtime qualification; an existence/readiness observation does not count as an inference result.

After the first scientific attempt finishes, run the following from this directory, substituting the actual printed attempt path:

```bash
bash RUN-NATIVE-SCIENTIFIC.sh /home/chad/fw-scientific-gpu.ACTUAL_ATTEMPT
```

The helper verifies the first screen's retained 75 request records and GPU observations, checks its clean framework source, saves readiness evidence, and runs MedCPT then TxGemma using their existing virtual environments. Each engine has its own retained outcome and fresh evidence directory. It does not download weights or install packages. See `native/README.md` for load/forward watchdog limits, memory evidence and interpretation.

## Behavioral work during the scientific run

The prepared pack implements 24 fictional cases across six responsibilities: measurement/construct interpretation, state/context, learning/decision, individual dynamics, strategy/experiment interpretation, and host feedback. Each responsibility includes a supported, changed-context, conflicting, and insufficient-evidence case.

Model-visible observations and choices are separate from the protected answer key. The evaluator checks structured decisions, acceptable evidence sets, temporal exclusions, numerical tolerances, and predeclared critical inferences. Free-text rationales are retained for independent review; formatting or keyword matches cannot establish a scientific or psychological conclusion.

The behavioral comparison repeats the same candidate set and exact full digests, giving each model all 24 cases: at most 120 requests. It uses the same serial GPU observation contract after the scientific attempt has ended and its evidence is reviewed. An all-abstain answer pattern reaches only six of the 24 cases even with otherwise correct oracle fields; citing every fact fails the eight distractor or temporal-exclusion cases. These are harness diagnostics, not model scores.

After the scientific stages have finished and their results are inspected:

```bash
bash RUN-BEHAVIORAL.sh /home/chad/fw-scientific-gpu.ACTUAL_ATTEMPT
```

The predecessor gate rechecks the original scientific raw ledgers, request intents, telemetry, full digests and matching positive VRAM observations. A held, incomplete or insufficiently observed predecessor is refused. The behavioral runner also refuses changed model digests or a busy GPU, retains partial attempts, and never repeats an ambiguous request automatically. An invalid or truncated but completed output is scored as a failure without silently dropping the remaining cases.

The behavioral per-call HTTP limit is 120 seconds, with a 20,000-second whole-campaign bound. This is an upper budget, not a predicted duration. `behavior/LAUNCHER.md` describes the evidence and commands; `behavior/README.md` describes the six responsibilities and protected grading. The frozen fixture/key pack is `803d7c62e0574974ceb729b238f92e02c27d90af787ddc522b92078685e8319b`.

These finite-choice cases precede the four multistep episodes in the earlier design. Persistent episode memory, real longitudinal forecasts and intervention effectiveness are not tested by this pack. Free-text rationale review remains pending after structured scoring.

## Source and runtime state

- Literature: deferred; existing issue remains open.
- Scientific source dependency: previously qualified offline; that receipt contains zero model/GPU calls.
- New scientific and behavioral GPU wrappers: prepared and offline-tested; host evidence still required.
- Native MedCPT/TxGemma adapters: prepared and offline-tested; actual CUDA loading and inference remain unobserved.
- Behavioral model benchmark: 24 cases implemented; no real model calls recorded here.
- Runtime deployment and permanent model-role assignment: none.
