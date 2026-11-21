# I01-R — Recover a lost local archive receipt

**Status:** Separate draft change; no deployment or live network integration.
**Owner:** Mother archive/integration worker, exclusive files:
`mother/physiology/receipt_recovery.py`,
`tests/physiology/test_receipt_recovery.py` and this document.
**PM:** Sole owner of shared schema, migration and acceptance.
**Dependencies:** Mother I01-U [PR #7](https://github.com/ctmansfield/mother/pull/7),
Coach I01-U2 [PR #5](https://github.com/ctmansfield/coach/pull/5).
This work does not depend on the NAS restoration or personal data exports.

## Gap and chosen behavior

Mother already commits an immutable manual event and returns a result. When
the event was committed but the response was lost, the sender must not guess
whether ingestion happened or delete its pending envelope. A receipt written
before commit could make an unpersisted event appear delivered.

The offline recovery mechanism therefore:

1. Accepts a bounded original envelope from the existing Coach writer.
2. Commits or idempotently resubmits it using Mother's I01-D/T2 archive.
3. Re-examines the selected archive for the exact canonical event, current
   source revision and **original event bytes**.
4. Creates a deterministic receipt in a chosen private directory, only
   *after* that verification, without overwriting an existing receipt.
5. Re-reads the receipt and compares it with the actual archive.
6. Returns a result only when the local receipt and archive agree.

If receipt creation fails after commit, the caller must retain and retry the
*same original envelope bytes*. The retry returns an identical receipt,
without duplicating the normalized event. Replaying a semantically identical
event with different original bytes is **not** silently certified as the
same archived source artifact.

The receipt has stable `status: archived_in_selected_local_archive`,
`receipt_version: 1.0.0`, SHA-256 of the original event and envelope,
event ID, source revision ID, evidence level, and an explicit
`authenticated_sender: false`. It deliberately omits the subject ID,
event payload and transient "new/duplicate" response status.

A receipt **does not authenticate the sender or become a remote proof**.
Verification requires direct access to the actual selected Mother archive;
a copied or forged receipt without archive comparison cannot establish
acceptance. The sender's outbox remains intact; no automatic clean-up,
remote transfer, or background service is started.

## INSTALL — disposable checkout only

Use a new isolated Mother worktree based on this draft branch and an exact
reviewed Coach checkout pinned at:
`1900d64b4b73706bd0a06871985502b8967f2911`.

Run only with synthetic data until the NAS runtime and subject permissions
are explicitly reconciled. Pass an existing original envelope file from
Coach's offline outbox. Both output paths must be explicit.

```bash
python -m mother.physiology.receipt_recovery \
  --input /path/to/synthetic.coach-event.json \
  --archive /path/to/disposable/archive.sqlite3 \
  --receipt-directory /path/to/private/receipts
```

The receipt directory must have owner-only permissions. Receipt files
are mode `0600` on POSIX and are content-addressed by envelope SHA-256.
The command refuses pre-existing symlinked receipt paths, incompatible
contents, and world-readable receipts instead of replacing them.
Receipt publication uses fsynced temporary-file write, exclusive hard-link
publication and directory fsync on Linux.

A rejected packet or unavailable archive returns nonzero and emits a
minimal error type without logging event payloads. A nonzero exit may
occur **after successful archival commit**, so preserve the envelope and
retry, rather than treating the result as proof of an absent record.

Do not use this command on the running NAS archive or change credentials
without a separate installation and access review.

## VERIFY — synthetic and isolated

```bash
COACH_CHECKOUT=/path/to/pinned/coach \
PYTHONPATH=/path/to/mother:/path/to/pinned/coach \
python -m unittest discover -s tests/physiology -p test_receipt_recovery.py -v
```

Dedicated GitHub CI pins the real Coach browser event builder, executes
receipt/retry tests and repeats Mother capture/replay and prior archive
ingestion regressions, all without notification-capable tests. The new
tests simulate a crash/error **after the archive commit, before receipt
publication**, restart the archive and retry the same envelope.

Additional checks cover stable receipt bytes and inode, original byte
identity, tamper rejection, forged receipt mismatch, invalid parent
rejection, symlink/insecure receipt collision, bounded input, explicit
CLI paths and source-preserving replay.

## Remaining consequential design and runtime gates

- Which authenticated identity controls a subject and may access its
  archive? The server cannot trust user-supplied subject ID.
- Should future local receipt files be retained, encrypted, exported or
  securely removed? Encoded files are not encrypted.
- What reliable inter-host queue and transport will deliver packet and
  receipt, if the systems are not on the same authorized host? A SHA-256
  digest alone does not authenticate messages.
- How to qualify live service interruption, concurrent writers,
  power loss on the chosen filesystem, and replay after crash?

Recommendation: keep original Coach envelopes until a trusted local archive
reconciliation or future authenticated receipt confirms acceptance.
Continue with synthetic interruption testing now; defer actual service
integration until the NAS is inspected and explicitly approved.

## Release and rollback

No new table or migration. No change to contract 1.0.0 or existing
readers, endpoints or CGM logic. The module is an opt-in offline CLI and
function. Not invoking it leaves deployed systems unchanged. The standalone
test archives can be removed only by their creator after verifying they are
disposable; no destructive command is included here.

Evidence categories must stay separate: source inspection, isolated
synthetic tests, cross-repository synthetic integration, real-data
reconciliation, deployed behavior and verified live interruption.
