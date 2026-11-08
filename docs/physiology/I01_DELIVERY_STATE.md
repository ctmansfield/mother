# I01-S1 — Read-only delivery-state reconciliation in Mother

**Status:** Source-level / synthetic acceptance only; no NAS deployment.
**Base:** Mother I01-R receipt-recovery PR #8; actual Coach delivery viewer
pinned to `34554b07e0edb531074daa1bd77a28ac301409e9`, containing the
unchanged original event sender code.
**Owner:** Mother archive/integration worker. No shared schema, migration, live
API, credentials, notification, or data-source configuration changes.

## Purpose

A user who downloaded a Coach event file needs to distinguish:

| State | Meaning | Allowed conclusion |
| --- | --- | --- |
| `prepared_pending` | Caller has not marked a transfer attempt; no archive match established | Keep the original file |
| `delivery_unknown` | Attempt reported, receipt copied without archive verification, or archive has no matching event | Do **not** claim write success or absence; keep and retry the exact original |
| `archive_verified_receipt_missing` | Direct read-only snapshot verified exact current event revision and original bytes in selected Mother archive | Locally archived; regenerate receipt, retain original pending policy |
| `archive_verified_receipt_valid` | Same direct archive check and matching receipt | Locally archived and receipt reconciled; **not** sender-authenticated |
| `archive_verified_receipt_invalid` | Direct archive check succeeds but supplied receipt fails verification | Investigate receipt; don't treat it as authoritative |
| `archive_conflict` | Same subject/source event ID has different revision, projection or original byte identity | Preserve evidence; investigate the conflict, never overwrite |

The result is **never** `safe_to_delete_original: true`. No unverified
receipt, copied report, or a caller's `--attempted` flag can produce a
successful archive confirmation without reading the explicit archive.

The snapshot uses an existing SQLite file in `mode=ro` with query-only SQL
and a consistent read transaction. It does not call Archive's constructor or
install migrations, and will refuse missing, symlinked or incompatible
databases instead of silently creating one. Source values and subject IDs
are not included in the generated report, but event IDs and digests may
remain sensitive; protect reports accordingly.

## INSTALL / VERIFY

Install in a separate Mother review worktree based on I01-R. Use only
synthetic envelopes and a disposable SQLite archive during qualification.

Prepared but not submitted:

```bash
python -m mother.physiology.delivery_state \
  --input /path/to/synthetic.coach-event.json
```

Attempt made, outcome uncertain:

```bash
python -m mother.physiology.delivery_state \
  --input /path/to/synthetic.coach-event.json \
  --attempted
```

Direct local archive verification and optional receipt:

```bash
python -m mother.physiology.delivery_state \
  --input /path/to/synthetic.coach-event.json \
  --archive /path/to/disposable/archive.sqlite3 \
  --receipt /path/to/private/receipt.mother-receipt.json \
  --output /path/to/new-private-status.json
```

The last command verifies the selected archive in read-only mode, then
writes an exclusive, owner-private report file. Existing report files are
not overwritten. Do not use any of these commands against the running NAS
installation until its current revisions and approved paths are reconciled.

Focused CI acceptance (requires a pinned checkout of the actual Coach UI):

```bash
COACH_CHECKOUT=/path/to/pinned/coach \
PYTHONPATH=/path/to/mother:/path/to/pinned/coach \
python -m unittest discover -s tests/physiology -p test_delivery_state.py -v
```

## Verification criteria

- Explicit pending versus attempted-but-unknown remains distinct.
- Receipt alone, even authentic-looking, cannot establish archive success.
- Direct original-byte/revision/projection checks are required.
- A missing receipt after committed event is recoverable without rewriting
  the archive, and a later matching receipt can be verified.
- Conflicting same-ID contents, forged receipt contents, unknown archive,
  symlinked archive, illegal output overwrite and SQLite writes fail closed.
- Unknown receipt or delivery does not mean a negative physiological outcome
  or failed medical intervention; those domains remain separate.

## Release notes / rollback / next worker

Adds `mother/physiology/delivery_state.py` and a dedicated synthetic CI
suite. No migration, endpoint, auto-dispatch, outbox deletion, personal
data ingestion, model inference, or therapeutic action is implemented.
Rollback is to leave this optional read-only module uninstalled.

The Coach delivery-state interface may display this minimal JSON as a local
report, but a **copied JSON report is not authenticated**. A browser or
independent machine cannot safely claim live Mother confirmation from a
bare file or SHA-256 digest. Account/subject grants, authenticated status
transport, retained outbox deletion policy, and real power-loss/live restart
remain explicit later design and deployment acceptance gates.

## Executed integration evidence (8–9 November 2026 Guam)

GitHub's dedicated I01-S1 workflow checked out the exact Coach source revision
above and completed **15 read-only state tests**, **5 actual
Mother-report→Coach-viewer tests**, and **12 existing receipt-recovery
regressions**. The paired acceptance proves compatibility with the real Coach
JavaScript interpreter and the Mother-produced minimal JSON report, not a
test-only copy of the UI state machine.

The paired cases include prepared/attempted, committed without receipt,
committed with verified receipt, forged digest rejection, and a copied receipt
without archive access remaining unknown. No actual NAS database, live login,
personal event record, or network endpoint was used.

**Important:** Tests prove that the browser displays the archived states as
unauthenticated claims with a keep-original warning. This does not establish
sender authentication or a safe policy for deleting event envelopes.
