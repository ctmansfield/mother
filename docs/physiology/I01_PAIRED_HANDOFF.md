# I01-T2 — Offline Coach → Mother manual-event handoff

**Status:** Isolated, reviewable implementation. No NAS deployment.
**Dependencies:** Coach I01-P manual drafts → Coach I01-T1 outbound envelope →
Mother I01-D archive ingest (PR #5) → this receiver.
**Owners:** Coach owns outbound bytes and outbox; Mother owns acceptance,
source revisions and the durable archive; PM owns shared contract/migrations.
Neither application changes its running service configuration.

## Purpose and wire contract

The receiver consumes an explicitly selected local file containing the
five-field version 1.0.0 envelope described by Coach
`docs/physiology/I01_HANDOFF.md`.

It requires the exact envelope version, MIME type, base64 encoding and SHA-256
of the *original event bytes*. A changed or unrecognized field, duplicate JSON
key, invalid UTF-8/base64, nonfinite number, over-limit input or mismatched
hash is rejected before opening an archive.

Hash matching proves **byte integrity, not sender authentication**. The event
inside the envelope must still satisfy Mother's existing schema, version,
source, epistemic classification and subject/parent/session checks.

The original event bytes, immutable source revisions, source-specific first
observation times and processing versions are retained in the existing
archive. Replays remain retrospective; null known/availability times stay
unknown. Acknowledgment is not action; absence of an outcome is not negative
outcome data.

## INSTALL (isolated, no service modifications)

Review the Mother branch based on I01-D PR #5 in an isolated worktree and the
pinned Coach sender at `9fbe9b1580203be78ac8e06ae12dfae9f882c24d`.

To submit a **synthetic** envelope already produced by the Coach sender to a
new, explicitly chosen test archive:

```bash
python -m mother.physiology.handoff \
  --input /path/to/synthetic.coach-event.json \
  --archive /path/to/disposable/i01-archive.sqlite3
```

The input must be a regular file, not a symlink, and is never overwritten or
removed by the receiver. The archive path is mandatory and is the only data
location that may be changed. It is created by the archive's existing additive
migration when absent. Do not point this script at any deployed NAS archive
until current revisions and permissions have been reconciled.

The command emits a structured acknowledgment (new/already_archived, source
revision and hashes) to stdout. A rejected transport writes a minimal
error-type record to stderr and returns nonzero; raw event payloads are never
printed in failure text. **Receipt delivery is not transactional with the
archive commit.** Replaying the exact envelope after a lost receipt is safe and
returns already_archived; preserving the outbox is the caller's responsibility.

## VERIFY

This is a **two-repository** acceptance gate. The CI job checks out the
actual pinned Coach sender and runs nine synthetic receiver tests plus the
ten existing Mother manual-ingest tests. It does not infer correctness from
duplicated test-only serialization code.

```bash
PYTHONPATH="/path/to/mother:/path/to/pinned-coach" \
python -m unittest discover -s tests/physiology -p test_handoff_crossrepo.py -v

python -m unittest discover -s tests/physiology -p test_manual_ingest.py -v
```

Run from the isolated Mother worktree. No live network connector,
notification routing, credentials or personal data is used in the tests.

Acceptance includes: original event bytes and hash, exact version,
unknown timestamps and zero values, source revision linkage, idempotent
replay after restart, explicit action/outcome linkage, rejected cross-source
modifications and same-ID overwrite attempts, malformed packets, and
defensive CLI behavior. It does not establish authenticated remote access.

## Release notes / rollback

- Adds `mother/physiology/handoff.py`, synthetic integration tests, and
  a pinned no-network GitHub acceptance workflow.
- Changes **no shared schema, migration, existing normalized record, service
  endpoint, credential or production container**.
- Source event original bytes remain authoritative; the envelope is a
  handoff wrapper, not an independently authenticated observation.
- Does not automatically poll a directory or accept a network request.
- Rollback: do not deploy this optional code or simply stop invoking the
  standalone command; no installed archive schema is replaced.

## Next acceptance gate

After the NAS restoration is fully reconciled and approved, select an
authenticated Coach-to-Mother transport and subject authorization policy,
then add an explicitly limited API, controlled local queue and restart
tests. Do not publish personal event/spool reports in a public repository.

Source qualification, real exercise-to-sleep episodes, device connectors,
live runtime validation and physiological interventions remain separate
milestones.
