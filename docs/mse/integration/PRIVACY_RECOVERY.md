# Privacy recovery rehearsal and custodian decisions

This source-only synthetic addendum is assigned under [integration r8 and privacy r2](https://github.com/ctmansfield/mother/pull/23#issuecomment-7045857604). It leaves the accepted custody 0.2 and reference unchanged. The recovery contract below is provisional, for review with ATLAS, FORGE, PROVENANCE and SENTINEL. The role strings and availability references are synthetic test inputs. They do not enforce operating-system identity, provide encryption or represent actual keys.

## Separate recovery paths

| Domain | Proposed allocation under a separately approved private root | Release and restore check |
| --- | --- | --- |
| Vault | `<VAULT_ROOT>/mse-vault/{state,staging}`, backup at `<VAULT_BACKUP_ROOT>/mse-vault/<generation>` | Vault custodian approves restored mapping, using independent current revocation and policy state. Bind purpose, access generation and allowed projection identity. Withhold any mapping from a stale policy or revoked identity. Vault entries and recovery material stay outside the analytical domain. |
| Evidence | `<EVIDENCE_ROOT>/mse-evidence/state/{custody.sqlite3,physiology.sqlite3}`, backup at `<EVIDENCE_BACKUP_ROOT>/mse-evidence/<generation>` | Evidence custodian restores a coherent archived cut, verifies originals, commitments and schema, and prohibits direct analytical reads. Retain exact source bytes and timestamps according to the authoritative policy. |
| Projection | `<PROJECTION_ROOT>/mse-analytics/{state,staging}`, backup at `<PROJECTION_BACKUP_ROOT>/mse-analytics/<generation>` | Projection custodian installs an approved view into a new isolated directory. Current purpose, scoped authorization, generation and projection binding are checked before returning an allowlisted result. Missing vault, key reference, current policy or coherent binding yields denial. Evidence access is unavailable to the analytical restore path. |

Directories are proposed at mode `0700` and data files at `0600`, with distinct service and backup identities. Use disjoint storage roots, scoped staging and an independent current control source for the revocation set and policy generation. A copied backup or copied historical policy alone cannot grant access. Fail closed on a missing current policy source, uncertain recovery key reference, inconsistent generation, changed scope or forbidden output field. Keep private backup manifests and linkage records inside their respective custody boundaries.

## Local verification

```sh
python3 -I -B tools/mse_integration/recovery/privacy.py
```

The rehearsal creates three fresh permission-restricted synthetic generation files under a disposable directory. Fixed roles and distinct domain references model the recovery gates. It verifies a trusted digest, rejects nonregular generation members before reading, and restores an analytical aggregate only after checking current policy and the restored vault mapping. Revocation is injected from outside the backed-up scopes. Tests cover revoked mapping, missing vault or domain key reference, wrong purpose/role/token/generation, cross-domain substitution, resealed projection mismatch and raw field denial. The allowed analytical result is scanned for source identity, raw content, timestamp, linkage token and digest markers. The analytical result succeeds after removal of the disposable evidence fixture, which verifies that the modeled path does not open evidence.

No real encryption, independent process/host permissions, retention service, privilege broker, or secure erasure is exercised. The prototype is a recovery policy rehearsal. The eventual implementation must use distinct authenticated principals and a vault broker that returns only the minimal authorization binding, with access denial and adversarial testing at the actual boundaries.

## Owner selections

- **Boundary.** Start synthetic-only with three separate roots and simulated custodians. For a personal-data proposal that includes host-root compromise, move vault and recovery material to independently administered boundaries before qualifying that claim. Chad chooses the adversary boundary and the accountable custodian for each domain.
- **Recovery control.** Choose an independently backed-up current policy/revocation authority with monotonic recovery semantics. Specify how restoration handles a ledger gap without reviving revoked links. Require protected evidence of the current policy generation and fail closed until the independent control state is available and verified.
- **Key custody.** Select separate evidence, vault and analytical key domains, standard authenticated encryption managed by the selected platform, independent recovery references and a two-person vault recovery approval. Name primary and recovery custodians, rotation and revocation owners, and how retained generations remain recoverable with retired keys. Missing key material must never trigger use of another domain's role or keys. No keys are created in this prototype.
- **Retention.** Propose up to two independently verified generations within a 30-day maximum for synthetic trials and a shorter seven-day projection cache, with revocation records retained beyond the oldest restorable mapping. Evidence holds and approved erasure supersede ordinary expiration. Before owner selection, measure available recovery space and decide how to prove copied backups meet deletion and key-retirement requirements.
- **Rollback.** Refuse to publish stale or partial restores, preserve failed generations under restricted custody and retain the last verified active generation. Apply current revocation and erasure before activation or projection rebuild. Invalidate stale downstream exports and derived references. Prior state is never overwritten by the rehearsal.
