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

Database engine is not yet selected. Existing prototype SQLite or an available PostgreSQL instance is not a decision. Network database connections must use verified TLS; ingestion uses HTTPS over a private route, with no silent plaintext fallback. Local Unix socket access is separately scoped. The phone receives no direct database credentials.

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
