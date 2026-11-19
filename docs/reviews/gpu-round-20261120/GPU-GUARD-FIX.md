# GPU monitor false-positive correction — 2026-11-20

## Observed failure
The first FW00412 scientific GPU comparison attempt `/home/chad/fw-scientific-gpu.ZiXnPdgO` issued **one** of 75 planned requests and correctly preserved a HOLD; it is not a 0/15 model performance result. Matching GPU residency was observed for `gpt-oss:20b`, and NVIDIA telemetry consistently showed exactly one compute process, PID `3766817`, executable name `/usr/local/lib/ollama/llama-server`. No monitor errors were recorded; the GPU and Ollama were idle after the run.

The original guard permitted only executable basenames starting with `ollama`; it falsely rejected the legitimate `llama-server` helper. The failure was an attribution rule defect, not evidence of an unrelated workload.

## Changes
- Accept that **exact** observed Ollama helper path as an allowed process, without accepting arbitrary processes named `llama-server`.
- Preserve the previous individually accepted Ollama process basenames `ollama` and `ollama_llama_server`.
- Preserve the **single distinct GPU PID** limit and refusal of malformed PID data and unrelated process names.
- Add six offline regression cases for the real recorded sample, historical names, unknown names, multiple PIDs, malformed records, and idle GPU.
- Update scientific and root SHA256SUMS. Preserve the prior attempt and all historical negative evidence.

## Qualification
Six isolated Python guard regression tests ran locally against the exact new predicate semantics: PASS. Run the full `test_scientific_compare.py` and `test_gpu_guard_regression.py` suites plus manifests in a fresh pinned checkout on `llm` before launching a **new** GPU attempt. No GPU inference was started by this patch.

## Boundaries
One process path from the user's recorded telemetry is allowed; other new server paths need an explicit separately reviewed amendment. This rule checks process names reported by NVIDIA, not cryptographic parentage or a host-wide GPU lease. No supervisor routing, credentials, weights, deployments or scientific claims changed.
