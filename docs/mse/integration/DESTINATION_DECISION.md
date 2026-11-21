# Synthetic MSE destination decision

**Decision requested:** approve or revise the following values for a future bounded synthetic trial on the established LLM host. The package is reviewable offline. Operational readiness and the two r6 source-integrity fixes are separate gates. [Destination audit](https://github.com/ctmansfield/mother/pull/33) · [r6 directive](https://github.com/ctmansfield/mother/pull/23#issuecomment-7045523829)

| Item | Proposed selection for owner review | Required confirmation |
| --- | --- | --- |
| Placement | Dedicated subtree `mother/mse-synthetic` below the audited local ext4 data mount. Host and mount identity stay in the private decision record. | PHOENIX verifies exact mount source, canonical parents, usable quota and existing consumers. Reject a missing mount, NFS fallback, overlapping path, PostgreSQL directory or benchmark dependency. |
| Writer | Dedicated non-login identity `mother-mse-synth`, one SQLite writer, numeric UID/GID selected by the host owner. State directories `0700`, database and artifact files `0600`, umask `0077`. No inference service access to state. | Chad approves the service boundary. PHOENIX verifies the actual UID/GID, ownership and writer/reader access. Source installation uses a separate custodian-owned release tree with read-only access for the writer. |
| State layout | Under the allocation use `state/custody.sqlite3`, `state/physiology.sqlite3` and private `staging/`. Preserve originals in the journal and PF-001 BLOBs for the trial. | FORGE confirms current schema and working-set bounds. No third canonical artifact store. |
| Capacity | 2 GiB hard state cap initially, stop new admits at 1.5 GiB, and keep 2 GiB free for one isolated restore. Count staged input, both copies of accepted originals, auxiliary SQLite files and in-flight work against state. | Confirm a real quota and verify the threshold under representative synthetic data before relying on it. A free-space reading alone does not reserve capacity. |
| Backup volume | A separately approved failure domain with 6 GiB reserved for two nominal 2 GiB sealed generations plus one 2 GiB publication workspace. Publish by immutable generation ID only after all member and cross-store checks pass. | Chad names the backup custodian and destination. PHOENIX verifies mount, capacity, at-rest controls, recovery access and failure-domain separation. If measured sizes exceed reserve, increase it or narrow scope before admission. |
| Retention | Keep both complete generations and accepted originals through independent review, then propose a 30-day cap for synthetic qualification artifacts. Never prune unacknowledged evidence or the last verified rollback generation silently. | Chad approves maximum duration and any longer evidence hold. Custodian records named deletion and audit rules. |
| RPO/RTO | Propose at most 24-hour RPO and four-hour RTO, with pretrial baseline and posttrial seal. A trial may declare zero accepted-batch loss only if every accepted commit has a recoverable sealed copy or the sender retains replayable bytes through reconciliation. | Measure transfer, verification, logical restore and reconciliation elapsed time. No recovery objective is qualified by the local tests. |
| Intake and compute | Local finite synthetic input using public `ingest_capture`. Preserve the archive/backup when inference is unavailable. | No listener, network grant, external sender or personal data in this decision. Authorize a later intake separately. |

## Candidate-bound offline installation and verification

Run from the PHOENIX recovery topic with a clean detached [candidate #34](https://github.com/ctmansfield/mother/pull/34) checkout at `877eeb66ae2c26ab8ee2144d34adeba87c988e8f`, tree `6dadd8cd94ffb4a0091f76624fdd0afd7baad507`, and the previously qualified local Python environment. The first command uses a fixed source allowlist and bytes from Git objects. It builds and verifies the deterministic package in memory, installs verified bytes only into temporary storage, checks public imports and removes the temporary installation. The second command uses only generated local layout markers. The third supplies synthetic input, verifies authoritative receipts, and compares full restored cutoff snapshots and replay lineage. The destination-path preview and approval placeholders are in [the setup runbook](DESTINATION_SETUP.md).

```sh
python3 -I -B tools/mse_integration/recovery/source_package.py --checkout "$candidate"
python3 -I -B tools/mse_integration/recovery/destination.py local-dry-run
python3 -I -B tools/mse_integration/recovery/paired.py --combined-checkout "$candidate"
```

The source bundle excludes credentials, prior fixtures, databases, profiles and binaries. It is evidence of the tested #34 packaging and restore behavior. It must be regenerated with explicit updated source pins and reviewed again for a corrected release candidate. Under r6, require original-byte-to-export binding and explicit numeric loss to survive backup, restored receipt, cutoff snapshot and derived replay before release consideration.

## Guarded backup and rollback decision

1. Quiesce the one writer at an acceptance boundary. Record archive/scope, latest authoritative stages, schema and source pins, and exact generation binding. Back up the journal and PF-001 using the SQLite backup API, keep their common cut, and seal both as standalone copies.
2. Verify member hashes, integrity and foreign keys, exact original bindings, and authoritative restored receipts. Independently compare the fixed-cutoff snapshot, derived manifest and expected conversion loss. Preserve failed copies and their diagnostics privately.
3. Reject partial or mixed generations. Leave active state untouched. A future approved cutover must restore to a new private directory, reverify retained identities and reconcile any later commitments before selecting it. If checks fail, keep the last verified generation and return HOLD. No automatic cleanup of other generations or active resources.
4. The setup and rollback commands here run only on disposable scratch. PHOENIX and SENTINEL must qualify actual allocation, ownership, backup durability and isolation before a separate owner instruction can authorize any host change.
