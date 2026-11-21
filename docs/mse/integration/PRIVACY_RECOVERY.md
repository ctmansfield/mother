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

## Actual-store diagnostic checkpoint

Use Python 3.12 with the existing PF-001/jsonschema dependency. Fetch repository Git objects for #35 `b7aae4f2216d27f0544eab9fe9698286fe49d716`, FORGE #40 `26895ab4cf090c75f5540dbab1f16d1f7d91db02`, ORACLE #38 `ef8dded78ffdce643db394fa3f6ef91e3fa36854` and PROVENANCE #39 `05b571ad8610d21d99bd2dacc070d063c3ff1f1c`. The diagnostic extracts the four exact source trees into one temporary directory. It does not use the simulated role/key-ref harness above.

```sh
python3 -I -B tools/mse_integration/recovery/privacy_stores.py \
  --object-store /path/to/mother-checkout-with-pins
```

Fresh synthetic HRV is ingested through actual public custody, projected by the published ORACLE preview path and persisted under a real FORGE reservation. The historical preview grant and custody reservation are explicitly connected by the harness. The actual resolver holds and checks the restricted lineage binding. Each privacy SQLite member is copied individually at a quiesced local cut with SQLite's backup API, sealed in standalone mode, and restored only inside the generated scratch tree. Neither current grants nor policy are taken from the copied databases.

**Diagnostic outcomes and release conditions.** The published projection restores as an aggregate without the raw evidence file; a reader cannot resolve protected lineage. A bootstrap with no trusted grants denies both reads. The supplied current generation fences old views after restore. Two of the passing diagnostics intentionally reproduce the published limitations: restarting with stale bootstrap grants reopens the old view, and removing the identity vault blocks aggregate reads even with published projection and current in-memory grants. These outcomes are evidence of missing durable authority and missing aggregate-only recovery, not proof of a qualified boundary.

For the connected gate, require the new current authorization API to reopen from an independent persistent generation and revocation store. Keep that store outside every copied domain. After actual revoke and restart, restore stale reservation, projection and lineage snapshots without restoring current authorization. The old view and audit path must remain denied. With live authorization retained, remove the raw evidence and identity-vault members before reopen; require the restored aggregate to pass and privileged lineage to deny. Also remove current authorization itself and require both paths to deny. Run before/after output and private-open counters through the actual connected APIs. Do not carry the preview grant shim or missing-vault limitation into final acceptance.

## Connected round 9 restore result

The connected mode uses #35 `b7aae4f2216d27f0544eab9fe9698286fe49d716`, FORGE #40 `7623616a97c0ab0213b6a9b4ebcf9affdac1e80a`, ORACLE #38 `58f78b1ed077fc0938b3540a517429500a40c663`, and PROVENANCE #39 `c509515b6ae4508d6f94e619ed557cc6789ebda7`. It calls the persistent bootstrap, actual ORACLE publisher and actual PROVENANCE resolver. There is no preview grant or substituted authority in the connected mode. Fetch those Git objects and run:

```sh
python3 -I -B tools/mse_integration/recovery/privacy_stores.py \
  --object-store /path/to/mother-checkout-with-pins --connected
```

Recovery is split five ways. Evidence and identity vault remain restricted. Projection and private lineage registry are independently recoverable. Durable authority is required for serving and is checked against a separate current fence. **Exclude the live fence from backup and restoration of the other stores.** A copied authority database cannot supply its own current epoch.

- Reopen a restored projection with current authority and fence only. The evidence, identity vault and exact PF-001 input path are unavailable. An authorized reader gets the exact prior bounded aggregate without raw markers. The reader cannot resolve restricted lineage. The auditor cannot resolve lineage when the separately protected registry is unavailable.
- Revoke through the actual custody API, restore old vault, projection and lineage databases, and reopen without bootstrap grants. Old reader and auditor credentials are denied.
- Restore the stale authority database as well, while preserving the newer fence. Reopen is denied. Missing authority or missing fence also denies reopen. No retry with old grants or privileged stores is permitted.
- Before a later authorized cutover, verify the separate live fence/revocation source before publishing anything. A coherent current authority paired with that fence is a prerequisite. Failure to reconcile must leave serving disabled while evidence is preserved for the custodians.

This connected result is scoped to the pinned source assembly and disposable SQLite backups. It does not demonstrate protection if both authority and fence are rolled back, or if one process has plaintext filesystem access to the stores. No host writes, production keys, role isolation or real-data privacy qualification were performed.
