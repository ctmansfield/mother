# Synthetic privacy custody

This isolated prototype adds three separate roots. It does not connect to the
accepted PF-001 ledger or change existing HR/SDNN, reference, receipt or source
bytes. It follows ATLAS's provisional analytical 0.1 contract at
`794591cfddbd05a2b226f917679429b104bbbac8`. [Round 8](https://github.com/ctmansfield/mother/pull/23#issuecomment-7045857604)

| Root | Content | Application access |
| --- | --- | --- |
| Evidence | Exact synthetic original bytes, private scope and random evidence handle | Evidence writer for its configured evidence-ingest scope. No analytics, projection-worker, exact-MSE or vault credential reads raw originals through this interface. |
| Linkage vault | Private scope/recipient/purpose/version/generation and separately random purpose tokens; issued view reservations with expiry | Linkage custodian can issue or resolve a pseudonym in its own context. Projection worker can allocate a view and bind lineage. A separately authorized lineage auditor can resolve an existing view binding. |
| Projection | Random `av_` view handle and strict analytical 0.1 payload | Projection writer can publish the same approved payload idempotently. Analyst reads only a published view with a matching live reservation. No raw archive fallback or scope, raw-source, linkage or expiry columns in the projection store. |

Trusted, local bootstrap calls `open_custody` with existing, disjoint canonical
private roots and configured `Grant` values. Set `initialize=True` only for a
fresh trial. Each grant binds role, the four-field source scope, purpose,
policy version, generation, recipient and an aware expiration. Bootstrap
returns the boundary object and a name-to-credential map. Pass each consumer
only its own opaque random credential. View and pseudonym handles are not
credentials. Projection and analyst grants use `aggregate_hr_sdnn` with policy
`synthetic-aggregate-hr-sdnn/0.1`; writer and reader roles are distinct. The
projection worker's input admission and aggregation stay with ORACLE; the
custody layer independently enforces the outward allowlist.

The evidence APIs are `put_evidence` and `read_evidence`. Vault pseudonyms are
internal, purpose/recipient/generation-scoped and persist across reopen.
`issue_view`, `put_projection` and `read_projection` bind the opaque view to an
active reservation on every call. `authorize_lineage(..., operation="bind")`
allows the projection writer, and `operation="resolve"` allows the lineage
auditor. Its private decision contains a copy of the exact scope, purpose,
policy version, generation, recipient and reservation expiry. Never serialize
this decision into the analytical response. A reader grant’s expiry is still
checked separately from the stored reservation clock.

`revoke` fences the context in the live object using the independent
retention-recovery role. After restart or restore, trusted bootstrap must
provide the current generation and approved policy from a source outside
restorable data. This prototype does not maintain that operational authority
or deliver production revocation. Older generation rows remain protected
history and cannot be served to the current generation. A missing vault
or reservation denies access. Separate stores are not a security boundary
against a process sharing the local filesystem UID, host/root control or
configuration access. All files are plaintext in this prototype. The caller
owns authentication, trusted process separation and any future encryption,
keys, backups and retention. An allowlisted aggregate can still be linkable.

The boundary assumes caller-owned private paths and a trusted exclusive PID/UID
environment. It pins root and parent identity, checks store SQLite kind and
version, rejects symlinks and nonregular files or sidecars before SQLite, and
sanitizes expected access and storage errors. It does not use ambient raw
fallback. Retain historical evidence and protect backups of the three domains
under separate roles. Do not let a projection restore supply its own grants.

## Original-byte minimization plan

The existing synthetic pipeline retains exact bytes both in FORGE
`deliveries.artifact` and PF-001 `raw_artifacts.content`. PF-001 deduplicates by
artifact SHA-256. Different batch identities can duplicate exact bytes in the
journal. This prototype's evidence-store bytes are only isolated synthetic
inputs. No automatic import creates a third copy of the accepted stores.

For a future reviewed transition, select one protected canonical original
location and use immutable scoped digest/length references for new deliveries.
Durably stage original custody before issuing a receipt. Reconcile missing,
orphaned and ambiguous references under injected restart/restore failures.
Verify historical receipts and digests, preserve existing retained bytes by
default, and compare backup, tail-replay, recovery and erasure behavior before
any custody-policy decision. No removal or in-place migration is implemented.

```sh
python -B -m unittest discover -s tests/integration/mse_privacy/custody -v
```
