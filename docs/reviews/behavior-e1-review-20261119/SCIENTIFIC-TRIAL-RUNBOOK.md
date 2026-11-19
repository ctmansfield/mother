# Scientific specialist trial — next host run

Reviewed 19 November 2026. Scope: preserve the completed coding campaign and the scientific offline qualification; prepare a separate bounded scientific trial. This document is a runbook, not a report that host inference ran.

## Verified baseline

- FW00412 source: `ba6fbb90c031f122b7db61d2f67f2b22ef1cf130`.
- [Actual host offline receipt](https://github.com/ctmansfield/production-framework/issues/139#issuecomment-7009907399): FW00410, FW00411 and FW00412 protected suites PASS; five scientific roles; 15 protected candidate/abstain cases; zero model/GPU calls.
- Host evidence directory reported by the operator: `/home/chad/.local/state/mother-fw00412/offline-ba6fbb90c031`.
- Published source counts: FW00410 59 tests, original FW00411 50, FW00412 70. A source snapshot can re-run those suites, but cannot substitute for the real host's model/GPU qualification.
- E1 is the project's fixed working premise. The evidence machinery evaluates downstream claims and provenance without converting that premise or a text quotation into an independently established causal fact.

## Correct the separate Scout preflight

The original FW00411 run stopped before tests because the qualifier expected the wrong Git blob for `packages/fw00410/scientific.py`. The fix retains the source guard, corrects the expected Git blob to `521261fe0a8f9ba09f152f95319d705283d9aba7`, and adds two regression tests. The prior failed attempt remains part of the history.

From a fresh checkout detached at `8f9907e7f6b5c4f639123ff1e8b8fe629b8d0308`:

```bash
FW00411_EXPECTED_SHA=8f9907e7f6b5c4f639123ff1e8b8fe629b8d0308 \
  bash packages/fw00411/scripts/qualify.sh
```

The source script writes local qualification evidence and then posts/read-backs a sanitized GitHub receipt. It does not invoke Ollama. This command is included as the published host workflow; it was not executed by this review.

## Scientific model roles

| Role | Trial question | Required separation |
|---|---|---|
| SOURCE | Does the proposal bind the supplied source and exact quotation? | Text provenance versus independent verification of the study |
| ECOLOGY | Does organism/substrate/product evidence fit the context? | Compatible observation versus unresolved opposing observation |
| METABOLIC | Is the reaction assertion supported at the right evidence level? | Chemical balance versus measured physiological flux |
| RECEPTOR | Does evidence establish the claimed receptor relationship? | Occupancy estimate versus measured engagement, signaling and host function |
| HOST | Does the study support the contextual host claim? | Association versus intervention-based causality |

The role configuration is an experimental choice, not a permanent model assignment. The current runner requires a supplied mapping. No model choices are filled in here because the current installed inventory and operator selection have not been observed.

## Prepare a roster without inference

Use a checkout detached at the FW00412 source pin above. First inspect the installed local tags and confirm the five intended choices. The current source helper queries only local Ollama `/api/tags`; it does not install models or run inference.

The repository's exact choice template is:

```json
{
  "roles": {
    "SOURCE": "CHOOSE_INSTALLED_MODEL",
    "ECOLOGY": "CHOOSE_INSTALLED_MODEL",
    "METABOLIC": "CHOOSE_INSTALLED_MODEL",
    "RECEPTOR": "CHOOSE_INSTALLED_MODEL",
    "HOST": "CHOOSE_INSTALLED_MODEL"
  },
  "source_evidence": "Operator-chosen synthetic specialist role comparison; no model role certified"
}
```

The documented source workflow uses these files:

```bash
fw00412_pin=ba6fbb90c031f122b7db61d2f67f2b22ef1cf130
mkdir -p "$HOME/.local/state/mother-fw00412/operator"
chmod 700 "$HOME/.local/state/mother-fw00412/operator"
```

Create `choices.json` there only if it does not already exist, using the template and replacing every placeholder with an explicitly chosen installed tag. Preserve an existing choice/roster file. Make `choices.json` mode 0600. Then run the source helper:

```bash
python3 -B packages/fw00412/scripts/make_roster.py \
  --source-pin "$fw00412_pin" \
  --choices "$HOME/.local/state/mother-fw00412/operator/choices.json" \
  --output "$HOME/.local/state/mother-fw00412/operator/roster.json"
```

The helper verifies all five roles, requires each named installed model to have a full 64-hex digest, binds the source pin, creates a mode-0600 file, and refuses to overwrite a previous roster.

## Bounded live launch

After matching offline qualification and an observed idle GPU/Ollama, the exact published launch is:

```bash
FW00412_EXPECTED_SHA="$fw00412_pin" \
FW00412_ENABLE_LIVE=YES \
FW00412_GPU_IDLE_CONFIRMED=YES \
FW00412_ROSTER="$HOME/.local/state/mother-fw00412/operator/roster.json" \
  bash packages/fw00412/scripts/qualify.sh live
```

The flags assert facts the operator has verified. The wrapper checks installed model digests and idle Ollama, requires the exact-source offline receipt, refuses to overwrite an existing attempt, serializes the trial under its package-local advisory lock, and applies a 2,400-second outer timeout. A package-local lock does not provide exclusivity against an unrelated coding process; check the completed coding run and other GPU users before launching.

Preserve the new host directory `~/.local/state/mother-fw00412/live-ba6fbb90c031`, including raw responses, role matrix, summary and exit code. Raw responses stay local. The script publishes only sanitized status/hashes and checks the exact GitHub comment body. If completion or publication is ambiguous, inspect the retained evidence before considering another attempt.

## What the next result can establish

Read the role-by-model matrix using at least these denominators: valid protocol outputs, accepted candidate assertions, correct abstentions, false evidence approvals, held contradictory/retracted claims, and latency. Report all failures and preserve the source/model digests. Fifteen synthetic cases are a first boundary test; they do not estimate general scientific reliability.

The next expansion should use held-out source excerpts from the E1 library, with exact document/version hashes and separately specified expected evidence-level decisions. Keep full-text acquisition status, source interpretation, physiological flux, receptor engagement and causal host effects as distinct measurements. Account-only papers become eligible for source-based evaluation only after the user has imported the actual document and provenance has been validated.

## Source links

- [FW00412 README](https://github.com/ctmansfield/production-framework/blob/ba6fbb90c031f122b7db61d2f67f2b22ef1cf130/packages/fw00412/README.md)
- [FW00412 qualifier](https://github.com/ctmansfield/production-framework/blob/ba6fbb90c031f122b7db61d2f67f2b22ef1cf130/packages/fw00412/scripts/qualify.sh)
- [Roster helper](https://github.com/ctmansfield/production-framework/blob/ba6fbb90c031f122b7db61d2f67f2b22ef1cf130/packages/fw00412/scripts/make_roster.py)
- [FW00411 correction](https://github.com/ctmansfield/production-framework/commit/8f9907e7f6b5c4f639123ff1e8b8fe629b8d0308)
