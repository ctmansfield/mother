# Synthetic analytical projection

The prototype uses the actual FORGE authority and projection store.
Bootstrap configures `AnalyticalExporter(custody, open_ledger, binding)`
with an exact archive, scope, snapshot digest, recipient and generation.
Call `export(credential, load_snapshot)` with the worker credential and a
trusted deferred loader. The worker validates the current grant before
reserving the persistent handle, loading the private snapshot or opening its
ledger. The reservation itself is authorized before either private read. The reopened ledger
verifies the exact snapshot before projection. The working contract is
ATLAS PR #28 at `794591cfddbd05a2b226f917679429b104bbbac8`.

The export covers at most 24 hours. Its 60-minute buckets are relative to the
authorized origin, which is withheld. It uses exact decimal inputs for
equal-weight means and rounds once to one decimal, half to even. HR must be
qualified measured HR in bpm. SDNN must be vendor-derived in ms. The policy
suppresses fewer than three contributions and nonpositive rounded means.
Tombstones and cutoff selection are applied by the ledger. A successful
publication returns the real persisted custody view ID only. An authorized
analyst reads the aggregate from custody using its own credential. The
separate status-only path returns a fixed object without reserving a view.
A denial contains a fixed message and no capture, scope, path or backend
details. The custody service checks expiry and generation and independently
validates the payload. The source evidence and original times are unchanged.

Relative patterns and aggregates can still be linked to other knowledge.
Three readings are not three contributors. This trial assumes trusted local
bootstrap and synthetic-only inputs. Restricted lineage, stale restore,
and independent attack tests are separate combined gates.

Run the synthetic tests in an isolated assembly of PR #35, this branch and
FORGE PR #40's round 9 custody API, with PF-001's existing jsonschema dependency:

```sh
python -B -m unittest discover -s tests/integration/mse_privacy/export -v
```

### Repeated queries and utility

Each persisted release has a different random handle. Repeating the same
approved input still produces the same rows and coarse loss codes. An
observer who can compare releases may link those patterns or infer a
contribution from nearby overlapping intervals. Sparse suppression and
relative clocks do not resolve that risk. The prototype does not track
query budgets or enforce cross-request suppression. Real release policy
would need separately reviewed audience and overlapping-query controls.

The analytical output cannot recover exact event times, interval durations,
counts, missing channel support or calibration. An absent row may reflect
missing, excluded or suppressed inputs. The broad loss codes describe the
projection, with no per-bucket attribution for suppressed groups. Exact
replay stays with the restricted ledger.
