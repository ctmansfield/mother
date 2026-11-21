# Protected evidence archive reproduction manifest

**Status:** source manifest and design inputs for review. The protected
archive remains **NOT READY** for live imports. No engine, topology, host,
path, account, credential, key or backup target is selected.
[Focus directive](https://github.com/ctmansfield/mother/pull/23#issuecomment-7055804570)

## Source and dependency lock

| Component | Exact source and purpose |
| --- | --- |
| Accepted offline assembly | [Review PR #35](https://github.com/ctmansfield/mother/pull/35), commit `b7aae4f2216d27f0544eab9fe9698286fe49d716`, tree `7abdfe4ce80b2a31223bcbdd36b2c2d3eacde264`. Preserve it as evidence. |
| Author archive candidate | [FORGE #31](https://github.com/ctmansfield/mother/pull/31) `e4219cdf3dba73f586e3820990f3ab34f1a7c1d9`, tree `7925bc2756c9471137b3ab05836d3557750db69e`. `integrations/mse_ingest` owns artifact custody, receipt journal and PF-001 binding. |
| Archive schema | [PF-001 #18](https://github.com/ctmansfield/mother/pull/18) `b4e70b7123689ec164ba09e2974645ae36b184a2` is unmerged. SQLite schema version **1**, physiological contract **1.0.0**. `mother/physiology/migrations/0001_archive.sql` SHA-256 `5994014c2b5a9ad0b2730b75a463eedfc0608adf0f599b6e3f0918044620e00b`; `mother/physiology/schemas/v1.schema.json` SHA-256 `ddcc1255efda566def86c0011cf9321cdcdb226fdd1f9f6ab1feadee30e15ba1`. |
| Exchange schema | [Frozen ATLAS 0.2](https://github.com/ctmansfield/mother/blob/769a0966da251da4d08633cc7663af9869da70e6/docs/mse/integration/contracts/README.md), commit `769a0966da251da4d08633cc7663af9869da70e6`. `docs/mse/integration/contracts/offline-integration.schema.json` SHA-256 `12b93fbebf37a15d91c4ad56288dac7a62b91910fc98baaf8d2184b5c602688a`. |
| Capture adapter | [ORACLE #30](https://github.com/ctmansfield/mother/pull/30) `ac3fbf61389ca2a6e82683aa520c15181ac1aa80`. Trusted raw reconstruction uses exporter `healtharchive-capture:0.2.1` for new custody and `healtharchive-capture:0.2` for historical verification. Current PF-001 mapper is `forge-pf001-binary64-0.2`. |
| Qualification-only dependencies | The #31 verifier pins PROVENANCE `5482f25c10a4ba4f2217625c8ecef45002184833`, NICKY fixtures `bf646a8e2f77c277717dc97b24b8957e9a380579` and the immutable reference supplied by #18. These exercise connected replay. The protected writer itself has no model executor, GPU, listener, projection or identity-vault dependency. |

The local code supports Python 3.10+. Reference runs used Python **3.12.14**.
The measured disposable archive fit run used SQLite **3.53.1**. Record the
actual Python executable identity, SQLite runtime and compile options,
OS/architecture, filesystem and locking behavior, and exact package builds
for a reviewed target. The #31 verifier requires an isolated environment with
`jsonschema==4.25.1`, `attrs==26.1.0`,
`jsonschema-specifications==2025.9.1`, `referencing==0.37.0`,
`rpds-py==2026.9.1`, `typing-extensions==4.16.0`.
Git and those Python packages must be staged before offline verification.
Platform-specific package hashes, a verified platform image and an
independent reproducible installation receipt remain release inputs.
[Finite verifier](https://github.com/ctmansfield/mother/blob/e4219cdf3dba73f586e3820990f3ab34f1a7c1d9/integrations/mse_ingest/verify_offline.py) · [Measured fit](https://github.com/ctmansfield/mother/pull/36)

## Schema and write authority

| Object | Ownership and consistency boundary |
| --- | --- |
| Original bytes | `custody.sqlite3:deliveries.artifact` holds exact admitted bytes per scoped batch. `physiology.sqlite3:raw_artifacts.content` retains accepted original bytes keyed by SHA-256. PF-001 deduplicates there, while distinct journal deliveries can duplicate identical bytes. Both stores and their existing receipts are preserved. A future single-copy policy requires a separately reviewed migration and recovery proof. |
| Custody journal | `deliveries`, `commits`, `trial_identity`, `trial_exports`, `stage_receipts` manage reservation, exact export, stage identity and monotonic local commit sequence. Current tables are inline create-if-absent DDL pinned to the FORGE commit. There is no general durable journal migration/version ledger or upgrade mechanism. A new version must explicitly recognize old layouts before writes. |
| PF-001 archive | `schema_versions`, `import_runs`, `raw_artifacts`, `source_revisions`, `normalized_records`, `run_revisions`, `source_heads`, `checkpoints` are owned by migration 0001. See the pinned migration for primary/foreign keys, uniqueness and indexes. A completed archive run couples artifact, immutable revision/membership proof and eligible normalized observations. No collector checkpoint advances from a captured anchor. |
| Operator evidence | Receipt, original and exact membership may contain sensitive source scope, paths, hashes and clocks. Provide scoped status, receipt verification and explicitly authorized original/exact-data export through separately designed operator paths. Preserve who accessed what and under which purpose without copying raw evidence into logs. No operator service or access policy exists in this source bundle. |

The connected entry rederives the export from retained input bytes under the
trusted scope/parser. Custody commits before archive writes. The journal
serializes the archive step with `BEGIN IMMEDIATE`; PF-001 uses its own
`BEGIN IMMEDIATE`, foreign keys and `synchronous=FULL`. The journal also uses
`synchronous=FULL`. SQLite connection wait settings are 30 seconds in the
pinned implementation; they are not service deadlines. Archive completion
and journal publication are two durable commits. The terminal receipt is
released after exact run/artifact/member verification. An interruption
before receipt can leave a pending custody record or a completed run awaiting
reconciliation. An identical retry reuses the bound original and run.
Conflicting scope, content or export binding, missing bytes and ambiguous
matches fail closed. Reopen reconstructs the export and verifies exact
membership. The contract retains tombstones and separate source/processing
IDs and per-field numeric loss.

## Startup and controlled stop

The qualified entry is a **local synthetic Python** call:
`ConnectedIngest(root, archive_id=..., scope=Scope(...), schema=...)` and
`ingest_capture(...)`. The path is one canonical, caller-owned private root
with a trusted parent, directory mode 0700, and regular owned database files
and sidecars at mode 0600. Keep it on storage whose local locking and
durability are qualified. Configure only explicit, nonsecret synthetic
values during reproduction:

| Input template field | Meaning |
| --- | --- |
| `<source_commit>`, `<contract_path>`, `<private_root>` | Exact reviewed code and schema plus caller-selected synthetic workspace |
| `<archive_id>`, `<subject_id>`, `<source_instance>` | Fixed synthetic archive/subject/store identity. Source system is `healthkit`, collection `healtharchive`. |
| `<batch_id>`, `<capture_id>`, `<capture_kind>` | Versioned delivery and capture declarations. Replay an uncertain batch with identical bytes and metadata. |
| `<writer_identity>`, `<operator_roles>`, `<backup_target>`, `<quota>`, `<RPO/RTO>` | Unselected operating inputs, including Chad's scoped read/export access, backup custody and stop criteria. These are not accepted module settings or secrets. |

Fresh synthetic initialization means a newly allocated empty private root,
then first accepted ingestion through the archive API. PF-001 applies its
baseline only to a new recognized store. Reopen a known pair with the same
identity and confirm schema, artifact hashes and receipt linkage before
reporting readiness. Stop intake and drain or record pending operations
before shutdown or an intended backup cut. Retain both store files and
reconciliation evidence. Do not replace a missing partner with a fresh
store to make reopen succeed. There is no service startup unit, ingress
endpoint, OS identity configuration or operational stop command in this
manifest. They require a separately reviewed implementation.

For resource sizing, the source-backed 1,024-reading disposable sample used
5,087,232 bytes across two closed SQLite files, before transient writes,
outputs, backups and restore headroom. Size from workload/batch retention
and observed write/read duration under a chosen candidate. These figures
do not establish host capacity, locking on networked mounts or recovery time.
[Database fit measurements](https://github.com/ctmansfield/mother/pull/36)

## Proposed connection and phone-sync requirements

Remote database connections should default to encrypted transport with
certificate-chain and server-hostname verification. A missing trust root,
name mismatch, or TLS negotiation failure must stop the connection. No
silent plaintext fallback. Any engine or client choice must preserve a
supported path to that mode before remote access is approved. A same-host
Unix-domain socket may be considered separately with explicit filesystem
permissions, service identity and peer authorization. Socket access does
not provide encrypted transport. Transport security and encryption of
database files and backups are separate decisions. No engine, certificate,
trust root or socket path is selected here.

The phone connects to a private **HTTPS ingestion API over Tailscale**.
Keep database credentials and database access behind the API. The phone
validates the HTTPS server certificate and hostname even on the tailnet,
and presents a scoped API identity. Tailnet reachability, HTTPS identity
and API authorization are separate checks. The ingress URL, audience,
certificate and operating policy remain unselected.

The proposed sync sequence is:

1. Persist original bytes, digest, scope and stable batch identity in a
   durable phone outbox before sending. Keep the outbox through timeout,
   restart and uncertain response.
2. Send the same batch over the private HTTPS route. The archive validates
   scope and content, commits the original and its acceptance stage, and
   returns a durable receipt. An identical retry returns the existing
   commitment. Changed content under the same identity is a conflict.
3. Verify the receipt against the expected scope, batch, digest and required
   commitment stage before durably acknowledging the outbox item or advancing
   the delivery checkpoint. A transport response alone is insufficient.
   A delivery checkpoint supplies no authority to advance a HealthKit
   acquisition anchor.

Earlier synthetic upload and network checks provide reusable transport
evidence. The offline candidate provides reusable custody, retry and recovery
evidence. Continuous real-data sync, background execution, physical-device
restart and offline catch-up through the proposed API remain unqualified.
[Health-data ingestion requirements](https://github.com/ctmansfield/mother/blob/91d67e387e91d93a7a60aec03c8164c11c7aa994/docs/mse/HEALTH_DATA_INGESTION_REQUIREMENTS.md)
· [Offline custody acceptance](https://github.com/ctmansfield/mother/pull/35)

## Verification, backup and rollback

From a clean detached checkout of exact #31, with the verifier's pinned Git
objects and Python venv already present, run:

```sh
python -B integrations/mse_ingest/verify_offline.py
```

It assembles committed inputs in a temporary tree, uses local Git, and exits
nonzero on missing dependencies, skips, failures or timeout. The #31 receipt
records **22 passed**. Do not select #35 as the verifier target by substituting
its newer bridge for the fixed #31 verifier pin. Use the #35 accepted recipe
for that assembly. Its receipt reports **100 checks** and **4 separate paired
restore checks**. The #35 recovery driver has an older hardcoded combined
pin. The accepted test invoked `run_rehearsal` with the #35 SHA selected only
inside that test process; a plain CLI run using the old constant is not an
exact reproduction. [#31 receipt](https://github.com/ctmansfield/mother/pull/31#issuecomment-7045642645) · [#35 recipe and evidence](https://github.com/ctmansfield/mother/pull/35)

For a proposed backup, quiesce writes across both stores or establish a
reviewed equivalent shared cut. SQLite online backup of each database
separately can produce individually valid files from different acceptance
points. Copy exact protected originals and custody manifest as required by
the selected architecture. Record source/config/schema pins, artifact
lengths/digests, both backup digests, trusted archive identity, receipt
cutoff, pending stages and backup generation. Preserve required recovery
state and protect sidecars. Do not copy active DB files alone as proof of
durability.

Restore to a separate private root with trusted identity and current approved
configuration. Check schema versions and original/member digest equality.
On isolated restored files check `PRAGMA integrity_check` on both stores and
`PRAGMA foreign_key_check` on PF-001, then validate exact completed and pending
receipts, deliberate stale-pair rejection and identical retry. SQLite
integrity checks alone cannot prove cross-store consistency. Verify an
independent authorized operator can perform the approved status/read/export
path without relying on a service identity's unrestricted access.

A rollback review must distinguish pointing a verifier at a sealed historical
copy from reverting an operational archive. Preserve current evidence and
capture the newer receipt boundaries before any contemplated rollback.
Use a separately restored pair and verified manifest; never silently
reverse valid receipts or overwrite intact originals. The existing evidence
qualifies synthetic recovery only. Operational mount, isolation, admission,
backup/restore custody and operator access require separate decisions.
