# Scientific GPU first; behavioral comparison next

20 November 2026 (Pacific/Guam)

## Current instruction

The user deferred literature downloads and requested scientific GPU evaluation first, with behavioral preparation continuing while the scientific experiment runs. [Literature issue #145](https://github.com/ctmansfield/production-framework/issues/145) remains open. The earlier E1 acquisition handoff is not the next action.

This directory is an operator-invoked, source-only experiment package. No host inference has been observed from this ChatGPT session. The attempted SSH connection failed in the local SSH client before a connection was established. Source publication is separate from running this experiment on `llm`.

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

## Native scientific engines

The [scientific capability registry](https://github.com/ctmansfield/production-framework/blob/7cc2035a7077523f33d9f47b6bb44de17adecc84/docs/mother-coach/FW004_MODEL_CAPABILITY_REGISTRY.md) also names native MedCPT, TxGemma, Boltz-2, and TimesFM assets. Historical downloads or imports are not GPU inference evidence.

Separate native adapters are being prepared for paired MedCPT retrieval and TxGemma generation. They must use cached assets, freeze local provenance, and verify CUDA parameter/tensor placement. Boltz-2 and TimesFM require their own task-specific fixtures and runtime qualification; an existence/readiness observation does not count as an inference result.

## Behavioral work during the scientific run

The next pack implements 24 fictional cases across six responsibilities: measurement/construct interpretation, state/context, learning/decision, individual dynamics, strategy/experiment interpretation, and host feedback. Each responsibility includes a supported, changed-context, conflicting, and insufficient-evidence case.

Model-visible observations and choices are separate from the protected answer key. The evaluator checks structured decisions, acceptable evidence sets, temporal exclusions, numerical tolerances, and predeclared critical inferences. Free-text rationales are retained for independent review; formatting or keyword matches cannot establish a scientific or psychological conclusion.

The intended behavioral comparison repeats the same candidate set and uses the same serial GPU observation contract after the scientific attempt has ended and its evidence is reviewed. Behavioral preparation does not start another GPU job while science is running.

## Source and runtime state

- Literature: deferred; existing issue remains open.
- Scientific source dependency: previously qualified offline; that receipt contains zero model/GPU calls.
- New GPU wrappers: source preparation and offline verification only until host evidence is returned.
- Behavioral model benchmark: preparation in progress; no real model calls recorded here.
- Runtime deployment and permanent model-role assignment: none.
