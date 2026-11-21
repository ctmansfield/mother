# Receipt-bound handoffs

The controller renders the verified state, evidence IDs, first owner, disposition and allowed next action from an exact task directive and its pinned current receipts. Model reports and reconciliations are advisory. They can raise a human review objection. They cannot modify the verified fields, authorize execution, advance a checkpoint, or clear a hold. A passing binding makes a handoff eligible for human review.

## Offline qualification branch

Treat every receipt as synthetic in this trial. The caller provides the independently trusted directive and a complete set of issuer-specific receipt pins. The prototype must verify the exact bytes, task, revision, artifact, issuer, and observation/expiry times. Missing, duplicate, corrupted, stale, unexpected, or disagreeing receipts yield HOLD and no handoff. A state requires an explicit rule in the directive. The clock is supplied to make boundary cases replayable. Receipt validity is half-open. A receipt is current at its observation time and expires at its expiry time. Each required issuer attests the same bounded state.

A digest proves byte identity relative to a trusted pin. The prototype assumes the caller already established the authority of the directive and the pins. It does not read the network, publish records, release data, or execute a next action.

## Evidence for the decision

In the synthetic Gadget trial, the model alone gave 6/12 correct verdicts and falsely approved three defective handoffs. Supplying typed verification removed false approvals from the model output, but it still objected to four clean handoffs. The scripted router held all six planted handoffs and sent all six clean handoffs to human review. Preserve those distinctions in any broader trial. Keep prompts, model pins, and receipts separate from operational routing.
