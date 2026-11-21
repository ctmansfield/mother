# Protected native import admission

This runner is an offline Mac source candidate. Independently review the
exact parser and runner package, the reviewed age executable, real
ciphertext readback, protected filesystem and operator plan before
issuing any real admission. The author qualification uses fabricated data.

The approval authority signs a private JSON policy with HMAC SHA-256 over
the ASCII domain `mse.native-custodian-admission/0.1`, a zero byte and the
UTF-8 canonical JSON policy bytes. The envelope contains only `policy`
and `hmac_sha256`. The 32-byte authority key must be delivered through a
trusted private channel independently of this policy. Use a separate
provenance key and keep both keys, the native ZIP and the age identity in
Mac custody. Treat the policy itself as sensitive.

The closed policy fields are listed in `native_custodian.py`. The policy
binds the exact archive, enrollment and source instance, a finite UTC
execution window, and the complete ciphertext receipt, recipient,
plaintext length and digest and age executable digest. The authority
must compare the receipt to independently verified ciphertext custody
and verify the plaintext pins from the original custodian. The policy
also pins filesystem UUID, mount and private catalog and scratch roots,
typed database cap, disk reserve, wall timer, expanded archive bytes and
top-level row cap. Use absolute canonical paths.

The runner checks the exact mounted APFS volume reports encryption for
that volume, verifies both private roots are on the pinned filesystem,
and budgets room for anonymous plaintext scratch, a typed DB, its
rollback journal and a disk reserve. SQLite temp files are directed
to protected scratch. Its output is the protected typed catalog on that
same volume. The operator must independently verify owner isolation,
approved scratch and volume, locking and remount controls, encrypted
swap or an approved host policy, and capacity before admission. Use a
fresh dedicated root. Keep the encrypted original and detached private
key under independent custody.

```sh
python -B -m integrations.mse_health_history.native_custodian \
  --admission "$approved_policy" --approval-key "$trusted_authority_key"
```

The runner inventories the original only after age authentication and
an exact plaintext digest and length check. Successful output is a
generic status after the receipt is reopened. If the final outcome is
uncertain, preserve the private catalog and journal, check the exact
receipt under the same authorized scope and use exact authenticated replay
during the lease as needed. Keep the sealed original and custody receipt.
No service activation or guest transfer forms part of this runner.

## Proposed private diagnostic

The optional `--diagnostic-category` changes refusal reporting only.
Use it on a separately reviewed invocation. It prints one static label
in place of the generic refusal and never renders exception text.

- `ADMISSION`, `ENVIRONMENT` and `ADMISSION_WINDOW` identify preflight
  or precommit authorization and environment phases.
- `BINDING_OR_AUTHENTICATION` covers input binding, executable pin,
  identity or ciphertext authentication, and exact plaintext checks.
- `INVENTORY` identifies rejection while parsing or inventorying the
  authenticated original. `RESOURCE_LIMIT` and `RUNTIME_LIMIT` identify
  recognized limits regardless of the phase.
- `CATALOG` identifies a catalog operation. Older Python SQLite
  bindings may expose only this coarse phase for database capacity errors.
- `COMMIT` and `READBACK` require receipt reconciliation before any
  authorized retry. A category reports the observed failure phase.
  Acceptance still depends on an exact receipt reopened read-only.

Do not share exception strings, paths, identifiers, member names, record
values, credentials, or digests through the diagnostic. A previously
completed generic refusal cannot be reclassified from the category
implementation. Preserve the original failed state and treat any real
replay as a separate authorization decision.
