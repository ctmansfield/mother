# Protocol B — explicit scientific role binding

**GitHub-only, source-pinned experiment.** Baseline A remains immutable at `/home/chad/fw-scientific-gpu.uU1dgb0h`. Its 75 GPU requests and strict/synthetic scores are historical evidence, not model qualification.

Protocol B selects **DeepSeek R1 14B**, **MedGemma 27B**, and **MedGemma 1.5 4B** (15 identical FW00412 cases each, 45 serial requests). It changes only the *model-visible role instruction*, preserving the original strict FW00412 judge, source/edge tasks, citations, retraction and scientific authority gates. The prompt explicitly supplies `assigned_specialist_role` and forbids generic `RESEARCH-SCREENING` and edge-kind labels in the output's `role` field.

The launcher checks the exact qualified FW00412 checkout, the completed Baseline A raw evidence and 75 positive GPU observations, model digests, idle NVIDIA/Ollama, and shared scientific lock. It does not pull models, publish results, alter model roles, or change original data. Raw output stays in the newly created private state directory. Any ambiguous inference or GPU-contention hold stops later requests.

## Local source tests (no GPU)

From this directory:
```bash
sha256sum -c SHA256SUMS
python3 -B -m unittest -v test_runner
```

## Host preflight (no inference)
```bash
python3 -B runner.py \
  --baseline "$HOME/fw-scientific-gpu.uU1dgb0h" \
  --framework "$HOME/fw-scientific-gpu.uU1dgb0h/framework"
```

## Host GPU run (after idle verification)
```bash
attempt="$(mktemp -d "$HOME/fw-protocol-b.XXXXXXXX")"
python3 -u -B runner.py \
  --baseline "$HOME/fw-scientific-gpu.uU1dgb0h" \
  --framework "$HOME/fw-scientific-gpu.uU1dgb0h/framework" \
  --state "$attempt/results" --live --gpu-idle-confirmed
```

Keep the original Baseline A and this Protocol B attempt separate. A zero exit means all requested calls had observed GPU residency; scientific correctness and false claims are reported independently. No permanent role assignment follows.
