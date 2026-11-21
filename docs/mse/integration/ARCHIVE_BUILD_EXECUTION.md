# Protected evidence archive — authorized build

Instruction: [MSE-EVIDENCE-INFRA-20261121-02 r1](https://github.com/ctmansfield/mother/pull/23#issuecomment-7056096916).

Chad authorized stages 1–6 and explicitly deferred backup/restore. Prior source-only/no-provision restrictions are superseded within this bounded build. Preserve baseline, prior evidence, unrelated VMs and services. IDS and broader security tooling belong to another Codex session.

## Decisions and stage ledger

| Stage | Scope | Owner | Acceptance |
| --- | --- | --- | --- |
| 1 | Preserve source; pin baseline VM and resource/dependency requirements | All workers; PROVENANCE verifies | Exact source/checkpoint and baseline identities; dirty remainders explicit |
| 2 | Identical synthetic PostgreSQL/SQLite comparison and best-fit selection | FORGE + ATLAS; GADGET selects | Exact-value/revision/delete/retry/cutoff, concurrent query and table/view/export results; reproducible versions |
| 3 | Dedicated new VM on llm from actual baseline | PHOENIX sole runtime owner | Guarded clone, unique machine/MAC/SSH identity, private network, persistent paths; baseline unchanged |
| 4 | Selected archive engine, private ingestion API, operator inspect/query/export | FORGE + PHOENIX; SENTINEL independent | Schema/migrations/source pin, durable receipts/reopen, selected table/view export; scope/auth/TLS negative tests |
| 5 | Backup and restore | DEFERRED by Chad | Not a blocker, not claimed operationally qualified |
| 6 | Synthetic-only phone outbox and actual private delivery | ORACLE authors; NICKY sole phone owner | Signed artifact and in-place preservation; stable batch/receipt, offline/retry/conflict/reopen; exact app→server→table/export reconciliation |

GADGET selected SQLite behind the private HTTPS API after the identical synthetic PostgreSQL/SQLite comparison ([decision](https://github.com/ctmansfield/mother/pull/23#issuecomment-7056154116)). There is no remote SQL listener or shared-file access. Network database connections must use verified TLS; ingestion uses HTTPS over a private route, with no silent plaintext fallback. Local database-file access is separately scoped. The phone receives no direct database credentials.

Chad selected the QA guest's verified cold image ([source decision](https://github.com/ctmansfield/mother/pull/23#issuecomment-7056207226)). The dedicated clone uses 4 vCPU, 8 GiB RAM and a 64 GiB virtual disk. The running QA and Connect guests are not clone inputs and remain outside this build's mutation scope.

## Physical synthetic acceptance — November 21

Deployed service source is Mother draft #44 `86e362f04aac4431ecd637a2c5e0c1aee1f03ad5`, independently matched to the 24-member r2 package. The guest reports Ubuntu 24.04.5, Python 3.12.3, SQLite 3.45.1 and OpenSSL 3.0.13. HTTPS terminates in the new guest behind a private, exact-peer TCP relay. Source-package qualification, installed runtime and main-branch merge are separate states.

Installed phone source is MotherHealthBridge draft #14 `b0b9f29af09d562f92f39baf39365d730bf9bfd0`. Physical testing found a navigation lifecycle cancellation in the prior build. The fix moved the existing sender to the stable navigation ancestor; 37 host tests passed and the signed artifact was independently checked. An in-place update preserved both the opaque collector and the existing pending synthetic batch byte for byte.

With the relay stopped, the corrected phone displayed the terminal archive-unavailable result. Independent phone readback retained the same 305-byte admitted batch and no local receipt; authenticated server readback returned no receipt. After the guarded route resumed, one explicit retry of that same uncommitted batch produced the normalized-receipt success UI. Independent phone readback found no pending batch, cleared admission and a durable matching receipt at commit sequence 4. No replacement fixture or replay of a committed batch was used.

The server's retained original, normalized receipt, PF-001 source/processing row, scoped operator views and export agreed. A separate consumer database loaded the one-row export and passed integrity checking. SENTINEL independently reproduced the GET-only reconciliation. See [phone evidence](https://github.com/ctmansfield/production-framework/issues/50#issuecomment-7056681183), [runtime/storage evidence](https://github.com/ctmansfield/production-framework/issues/44#issuecomment-7056700937), and [independent acceptance](https://github.com/ctmansfield/mother/pull/44#issuecomment-7056689871).

Controlled new-guest startup qualification passed: only the dedicated guest rebooted; the host boot pin was unchanged. Its static address returned and the enabled archive service started automatically after the generic network-online wait timed out at approximately two minutes. Machine/SSH identity, source/config/schema/initialization marker, TLS leaf and network/unit pins persisted. The exact phone original, phone and diagnostic receipts, export, SQLite integrity/foreign keys and downstream load passed again. The network wait timeout is an observed startup limitation, not a clean network-ready check. See [startup evidence](https://github.com/ctmansfield/production-framework/issues/44#issuecomment-7056750133).

The [reproduction inventory](https://github.com/ctmansfield/mother/blob/1a5ab2c6684c36915d0162336ca9f61df84a2c3c/docs/mse/integration/ARCHIVE_REPRODUCTION_INVENTORY.md) maps exact dependencies, schemas, commands and private inputs. [Published runtime templates](https://github.com/ctmansfield/mother/tree/cbf202daf39df764bcdf6ae95153565b00c28e60/tools/mse_integration/recovery/archive_runtime) are normalized from executed private commands. Full clean-room replay and physical host reboot have not been tested. Restricted operator inputs remain required; no secret or raw personal-data publication is implied.

Backup/restore remains deferred. Immediate pre/post update collector copies matched; a later opaque copy differed after collection resumed, and its cause was not evaluated. The collector contents were not inspected or uploaded. The temporary phone relay closed at 13:40:49 Guam on November 21, independently verified by SENTINEL, while preserving the archive guest, stores and direct operator path. Chad confirmed trust off and removal of the exact November 21 test profile. Its configured cutoff and service-credential expiry are November 22 at 01:01:27 Guam. Closure was an operator stop, not observed timer expiry. [Independent closure](https://github.com/ctmansfield/mother/pull/44#issuecomment-7056770957) and [final cleanup/source delta](https://github.com/ctmansfield/mother/pull/23#issuecomment-7056789131). Server branch head `08514b7d20cac3bd55c4974cff1f38a9d8543193` changes only test formatting; all 24 deployed package members remain unchanged. Five focused tests and application CI passed; inherited pre-commit fixture/formatting failures remain. No merge occurred.

The archive must support authorized operator inspection and selected tables/views/exports for other APIs or special-purpose databases. Preserve exact originals and source/revision/receipt lineage. Reduced-disclosure analytical projections remain separate from authoritative evidence.

Eventual synchronization is near-real-time incremental delivery from data available to the app, backed by a durable offline outbox. First physical acceptance uses synthetic foreground uploads only. No live HealthArchive automatic transmission, background/watch/APNs expansion, public exposure or main merge is inferred.

## Reproduction bundle

- Exact baseline VM input/reference, image/source identities, guest resources, storage allocation and private network assumptions.
- OS/packages/application pins, dependency installation, schema/migration versions and compatibility rules.
- Guarded new initialization distinct from idempotent restart; refuse mismatched existing VM, disk or database identities.
- Startup/shutdown/status/verification commands and service/operator read/write boundaries.
- Configuration templates and private secret references, TLS verification/certificate lifecycle and scoped authentication bootstrap. No credentials, private keys or protected data in GitHub.
- Synthetic fixtures, actual failed/passed/skipped results and deployed-source/runtime evidence.
- Scoped stop/rollback preserving baseline and unrelated services. Backup/restore may be documented for later but is deferred for this build.

PHOENIX serializes guest mutations and hands bounded operations to FORGE/SENTINEL. NICKY serializes phone operations and any explicitly designated UI proxy. PROVENANCE binds source/artifact/schema/runtime evidence; LONESTAR maintains one board. GADGET coordinates and reviews completion. Genuine user-only unlock/login/trust steps are requested only once technically ready with exact instructions.

Successful completion establishes a reproducible private archive and synthetic phone intake/view/export. It does not establish anonymization, personal-data readiness, backups, scientific calibration, full MSE deployment or continuous background acquisition.
