# Synthetic privacy custody

This prototype adds independent SQLite roots for originals, pseudonyms,
analytical projections, authorization and a revocation fence. No accepted
HR/SDNN, PF-001, reference or receipt bytes are modified. [Round 9](https://github.com/ctmansfield/mother/pull/23#issuecomment-7055350520)

| Root | Content and authority |
| --- | --- |
| Evidence | Exact synthetic originals and private scoped handles. Only the scoped evidence writer can open originals through the API. |
| Identity vault | Private random purpose-specific pseudonym mappings. Linkage credentials are distinct from analytical credentials. |
| Projection | Opaque view handle and allowlisted analytical 0.1 payload. No source scope or identity mapping is stored here. |
| Authority | Trusted grant policy, scope, recipient, operation role, generation and expiry. Stores credential digests and scoped view reservations. No original bytes or pseudonym lookup table. |
| Fence | Independent pair binding and monotonic revocation epoch. Keep outside all restorable roots and independently protected. |

Trusted local bootstrap calls `open_custody(authority_root=..., fence_root=...,
projection_root=..., evidence_root=..., vault_root=..., grants=...,
initialize=True)` on fresh disjoint canonical private roots. Each `Grant` binds
an operation role, the four HealthArchive scope fields, purpose, policy,
generation, recipient and an aware expiration. The returned name-to-credential
map is private. Reopen with `initialize=False` and omit `grants`. Previously
issued random credentials remain subject to the durable generation and expiry.
For aggregate-only reopen omit both `evidence_root` and `vault_root`.
Authority, fence and projection remain required.

`authorize_projection(credential, view_id=None)` provides the private
trusted binding for pre-read admission. `issue_view(credential)` reserves an
opaque random view handle. `put_projection(credential, view_id, payload)` and
`read_projection(credential, view_id)` check live authority and the same
reservation before projection access. `authorize_lineage(credential, view_id,
operation="bind"|"resolve")` returns the private scope, purpose, policy,
generation, recipient and immutable reservation expiry for the distinct
writer and auditor operations. The caller receives no raw role override.
Outward projection storage and reads enforce the analytical 0.1 allowlist.
Unsafe values or unavailable private stores produce fixed error text.

`revoke(credential)` advances the scope/purpose/recipient generation and
persistent global epoch. An authority SQLite transaction serializes the
authorization decision and the projection read. A read admitted before
revocation may finish. A read after revocation commits is denied. The fence
commits first. An interruption between commits leaves unequal epochs and
blocks service until trusted reconciliation. Missing authority or fence,
a different pair, or a stale authority backup with the current fence denies.
This prototype provides no renewal, fence recovery, or rollback protection
if both authority and independently protected fence are replaced together.
The restore operator must exclude the live fence from restoration.

The stores are plaintext and assume trusted bootstrap, caller-owned canonical
paths and exclusive local filesystem control. These application checks
provide no protection against another process with the same UID, raw-readable
backups, or a compromised host. Production authentication, independent
storage identities, encryption and key custody remain unqualified.

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

## Bootstrap ownership and verification

The trusted local test operator selects the private roots and provisions grants
once, before handing an opaque credential to each consumer. Keep bootstrap
and the authority/fence paths outside the consumer interface. The API does
not authenticate the operating-system caller or authorize arbitrary local
configuration. A claimed role string is not a credential. Changing the
initial grant list is a trusted initialization operation for fresh stores.
Initialization against existing stores fails, and reopening with a supplied
grant list fails. A caller who can write the authority or fence databases or
run a different bootstrap against consumer data is outside the application
boundary.

The trusted fence custodian retains the current fence independently of
authority and all data restores. A stale authority copy paired with the
current fence fails closed. Missing, malformed or mismatched fence state also
fails closed before a projection file opens. If the authority and fence are
both replaced by their mutually consistent historical versions, local
state alone provides no current epoch for comparison. An independently
protected current fence or external trust anchor is required for that
threat. Files remain plaintext, with no protection claim for readable data
or a compromised host.

Run the bounded verifier from the candidate checkout with Python 3.10+.
It uses the standard library, starts no listener and installs nothing.
The test process has a 30-second deadline. Missing tests, skips, expected
failures, ordinary failures and timeouts return a nonzero status.

```sh
python -B integrations/mse_privacy/custody/verify_offline.py
```

The private `published_projection_digest(credential, view_id)` returns SHA-256
of the validated, canonical compact sorted-key JSON payload actually published
under a live reservation. Only scoped projection writers and lineage auditors
can request it. A reservation without a publication is denied. Lineage can
use this digest to compare exact canonical output bytes before binding.
