# Synthetic analytical projection

The prototype accepts an exact, reopened ConnectedIngest snapshot under a
trusted, local `ProjectionGrant` bound to its archive, source scope and
snapshot digest. The grant is constructed by the trusted bootstrap. Reader
requests cannot supply a role or ask for arbitrary fields. The ledger
reconstructs the snapshot before projection. The working contract is ATLAS
PR #28 at `794591cfddbd05a2b226f917679429b104bbbac8`.

The export covers at most 24 hours. Its 60-minute buckets are relative to the
authorized origin, which is withheld. It uses exact decimal inputs for
equal-weight means and rounds once to one decimal, half to even. HR must be
qualified measured HR in bpm. SDNN must be vendor-derived in ms. The policy
suppresses fewer than three contributions and nonpositive rounded means.
Tombstones and cutoff selection are applied by the ledger. Opaque random
preview handles, coarse loss codes and eligible aggregate rows form the
external view. Status-only returns a fixed object. A denial contains a fixed
message and no capture, scope, path or backend details.

Original evidence is unchanged. Relative patterns and aggregates can still
be linked to other knowledge. Three readings are not three contributors.
Local trusted Python bootstrap, process isolation, and synthetic-only inputs
are prerequisites. This draft allocates a new random preview handle for each
projection. Persistence, recipient authorization, generation, expiry,
revocation and restricted manifest/handle resolution are separate FORGE and
PROVENANCE integration work. The preview handle is not an access credential.

Run the synthetic tests in the PR #35 dependency checkout with PF-001's
existing jsonschema dependency:

```sh
python -B -m unittest discover -s tests/integration/mse_privacy/export -v
```
