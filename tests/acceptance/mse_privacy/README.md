# Independent local privacy acceptance

Assigned under [MSE integration r8 / privacy r2](https://github.com/ctmansfield/mother/pull/23#issuecomment-7045857604). The authoritative offline baseline remains PR #35 at `b7aae4f2216d27f0544eab9fe9698286fe49d716`. This directory reserves acceptance tests for the separately versioned synthetic prototype.

Use two fabricated subjects, two approved purposes, distinct analyst and evidence roles, a revoked grant, and separate local roots for evidence, linkage and analytical projection. Send the fabricated source through the patient-data-shaped synthetic path. Do not use an always-allow callback, rewrite the qualified evidence, or use real input.

| Gate | Required observation against the real prototype |
| --- | --- |
| Role, subject and purpose | A permitted analyst gets only the approved projection. Change one of role, subject, purpose or generation at a time. Verify denial even when the caller presents a handle from a prior permitted request. |
| Lower-level entry points | Exercise direct public APIs for protected custody, raw evidence and identity mapping using an analyst context. Verify denial and confirm no fallback to a broader identity or directory. A process with direct filesystem privileges is a separate threat. |
| Disclosure | Scan successful analytical output and captured failures, stdout/stderr and logs for source/native/subject identifiers, original timestamps, artifact/revision hashes, paths and raw bytes. Check keys and values. Verify authorized exact MSE can still resolve the approved evidence. CLI tests do not cover operating-system process inspection or external telemetry. |
| Revocation, restart and restore | Reopen from an isolated backup made before revocation. Keep current policy authoritative. A revoked mapping/handle must stay denied; missing linkage state fails closed. Confirm a separately authorized subject remains usable. |
| HR/SDNN fidelity | In restricted evidence, compare HR bpm and vendor SDNN ms, exact decimal lexemes and documented projection loss, interval boundaries, collector/commit distinction, exact tombstone facts and missing/unknown fields. In the analytical output check actual transformations and versioned loss. No projection may convert absence into zero or resurrect a deleted reading. |
| Residual linkability | Use separately created synthetic auxiliary timing patterns. Report retained ordering, gaps and rare values as possible linkages. A field scan cannot establish anonymity. |

Run the independent inputs and disclosure assertion checks from the repository root with
`python -B -m unittest discover -s tests/acceptance/mse_privacy -v`.
These checks qualify the test inputs and scanner only. Real API tests require the exact
custody, export, lineage and recovery heads and the policy revision they target.

## Round 10 connected check

From the exact combined checkout, set `PYTHON` to an existing Python 3.12
environment with jsonschema and run
`sh tests/acceptance/mse_privacy/run_connected.sh`.
The independent suite uses the actual public HealthArchive ingest, ledger,
custody credentials, publisher, projection reader and restricted resolver.
The paired restore suite extracts the pinned product inputs from local Git
objects. No listener or network access is needed.

The stale authority case keeps the current independent fence. The checked
denial applies to that split rollback. A rollback of both authority and its
trusted fence remains outside this local check. Older R9 preview/authority
findings apply only to the recorded R9 candidate.
