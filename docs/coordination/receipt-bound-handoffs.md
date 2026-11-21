# Receipt-bound handoffs

The controller renders the verified state, evidence IDs, first owner, disposition and allowed next action from an exact task directive and its pinned current receipts. Model reports and reconciliations are advisory. They can raise a human review objection. They cannot modify the verified fields, authorize execution, advance a checkpoint, or clear a hold. A passing binding makes a handoff eligible for human review.

## Offline qualification branch

Treat every receipt as synthetic in this trial. The caller provides the independently trusted directive and a complete set of issuer-specific receipt pins. The prototype must verify the exact bytes, task, revision, artifact, issuer, and observation/expiry times. Missing, duplicate, corrupted, stale, unexpected, or disagreeing receipts yield HOLD and no handoff. A state requires an explicit rule in the directive. The clock is supplied to make boundary cases replayable. Receipt validity is half-open. A receipt is current at its observation time and expires at its expiry time. Each required issuer attests the same bounded state.

A digest proves byte identity relative to a trusted pin. The prototype assumes the caller already established the authority of the directive and the pins. It does not read the network, publish records, release data, or execute a next action.

## Evidence for the decision

In the synthetic Gadget trial, the model alone gave 6/12 correct verdicts and falsely approved three defective handoffs. Supplying typed verification removed false approvals from the model output, but it still objected to four clean handoffs. The scripted router held all six planted handoffs and sent all six clean handoffs to human review. Preserve those distinctions in any broader trial. Keep prompts, model pins, and receipts separate from operational routing.

## Prototype entry point and acceptance

`tools/receipt_bound_handoff.py` provides `derive_handoff` and `check_candidate`. Use a caller-verified directive with a half-open authority window and exact pins for each required issuer. A successful receipt check derives a frozen handoff from a state rule. The candidate check treats the evidence ID list in directive order as canonical and holds missing, modified, or extra fields. A worker cannot add an execution claim. The result remains eligible for human review even when the bound operational status is HOLD.

Run the focused cases with `python3 -B -m unittest discover -s tests -p test_receipt_bound_handoff.py`. The eight tests cover clean binding, missing and repeated evidence, wrong byte and artifact pins, ambiguous JSON, stale receipt and authority windows, conflicting validly pinned receipts, missing state rules, and candidate overrides.

Eight independent Qwen3 14B role requests reviewed the initial branch contract on llm. Five returned the requested JSON shape. Duplicate JSON keys and missing receipts were useful regression cases. The model suggestions that reversed the time comparison, equated a receipt digest with an artifact digest, or implied automatic execution were rejected. The tests and implementation were independently checked. This branch is an offline prototype. It does not establish the authenticity of a pin source or enroll any live routing.

## Offline command

Run the CLI from the repository root with a caller-verified JSON directive and the
explicit receipt paths:

```sh
python3 -m tools.receipt_bound_handoff_cli --directive directive.json --as-of 30 receipt-a.json receipt-b.json
```

The directive has exactly the fields of the `Directive` dataclass. Write `pins`
as an array of `ReceiptPin` records and `state_rules` as an object keyed by
verified state. The caller supplies the evaluation time in Unix seconds. The
adapter reads exact receipt bytes and does no network access or file writes.

Exit 0 makes the emitted handoff eligible for human review, including when its
bound operational status is HOLD. Exit 2 reports a rejected qualification or
input error. The JSON result contains `disposition`, `reason` and `handoff`.

The CLI was assigned to eight workers from branch revision `7b8332a`. Two
workers drafted code and six reviewed acceptance cases. One coder revised after
feedback. Independent review rejected all three code drafts, including a
validator stub, path-revealing errors, and a revision with no success receipt.
The independently implemented adapter passed seven CLI tests and eight existing
receipt tests.
