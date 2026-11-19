# FW00412 role-echo shadow replay (GitHub-only handoff)

Read-only diagnostic for the complete, original scientific GPU attempt at `/home/chad/fw-scientific-gpu.uU1dgb0h`. Preserve its raw records and original strict grades. Requires a clean exact FW00412 framework checkout at `ba6fbb90c031f122b7db61d2f67f2b22ef1cf130`.

The reviewer observed 75 GPU requests: 48 invalid-enum responses, of which 34 reflect only the generic introductory role label. This utility *only* shadow-tests the returned `role` field when it is exactly `RESEARCH-SCREENING` or `RESEARCH-SCREENING candidate for {trusted task role}`. Graph/source/edge binding, authority flags, quotes, polarity, and causal gates remain unchanged. Other roles, graph node names and edge kinds remain held.

## From a fresh pinned GitHub checkout on llm

```bash
repo="$HOME/YOUR_FRESH_PINNED_MOTHER_CHECKOUT"
pack="$repo/docs/reviews/gpu-round-20261120/scientific/role_replay"

if ( cd "$pack" && sha256sum -c SHA256SUMS && python3 -B -m unittest -v test_replay ); then
  python3 -B "$pack/replay.py" \
    --attempt "$HOME/fw-scientific-gpu.uU1dgb0h" \
    --source "$HOME/fw-scientific-gpu.uU1dgb0h/framework"
else
  printf 'HOLD: package validation failed; original attempt unchanged.\n'
fi
```

The `repo` above is an illustrative variable. Use the immutable source commit supplied in the handoff, not a moving branch. No dependencies are installed and no network, Ollama, GPU, or GitHub posting occurs during tests or replay. The repo checkout itself may require GitHub network access.

## Release notes

- v0.1: immutable read-only role echo replay, eight synthetic regression tests, original ledger and source verification.
- Output: per-model counts, shadow-grader reasons and metadata-only examples; original grades remain authoritative.
- This does **not** repair 16 historical request errors, change the model-visible prompt, qualify models scientifically, or approve a knowledge claim.
