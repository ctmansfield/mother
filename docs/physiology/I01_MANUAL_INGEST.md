# I01-D — Immutable manual event ingestion for Mother

**Status:** Isolated review increment; not deployed to NAS.
**Owner:** Mother acquisition/integration worker.
**Shared schema and migrations:** PM; unchanged.
**Base:** Mother PF-001 draft PR #1, compatible with Coach I01-P manual event drafts (Coach PR #2).

## Purpose

Persist explicitly reported Coach events in Mother's existing SQLite
archive without creating a second event store. The synchronous offline
adapter accepts only these kinds: user_marker, context, answer,
acknowledgment, reported_action, and outcome.

No automated questions, recommendations, observed actions, notifications,
device integrations, or physiological inference are generated.

## INSTALL / operation

Use an isolated Mother checkout or worktree based on PF-001. There are no
new tables, migrations or runtime dependencies beyond PF-001, including
jsonschema. The caller must select a separate test archive path. Do not
point experiments at an active NAS database before runtime reconciliation.

API example:

```python
from mother.physiology.archive import Archive
from mother.physiology.manual_ingest import ingest_manual_event

with Archive("/path/to/separate/test-archive.sqlite3") as archive:
    result = ingest_manual_event(
        archive, original_event_json_bytes,
        received_at="2026-11-07T04:03:00Z",
    )
```

The example does not operate on any existing installation. Pass original
submitted JSON bytes. A caller holding a Python dictionary must explicitly
serialize it before ingestion; those serialized bytes then constitute the
source artifact.

Mother retains original bytes and SHA-256, creates an immutable source
revision, and attaches that revision ID to the validated normalized event.
Known/occurrence/recorded timestamps remain separate; unknown source
availability stays unknown. Repeating identical event data is idempotent
across archive restart. A changed event with the same ID fails rather than
overwriting prior evidence; corrections require a separate explicit event.

Typed parent IDs must already exist in the archive, have an eligible event
kind and match the subject. A referenced session must also exist and match
the subject. These checks do not authenticate the human origin of the
submitted event; an authorized API transport remains a future requirement.

No PostgreSQL migration, credentials, service configuration, or deployment
change is performed.

## VERIFY

```bash
python -m unittest discover -s tests/physiology -p test_manual_ingest.py -v
```

A dedicated CI job runs only the isolated acceptance tests. Expected cases:
original-byte retention; stable revisions and restart; rejected same-ID
conflicting revisions; zero-valued outcomes; missing outcomes remain
absent; typed parent and subject checks; unknown session rejection;
malformed payload rejection; and replay of persisted events with lineage.

## Release notes and boundaries

- Uses the existing additive PF-001 SQLite archive and contract 1.0.0.
- Adds a bounded, offline manual event-ingest API and synthetic tests.
- Normalized events include a trusted Mother-assigned source revision.
- Does not modify the running NAS system, launch an API, send a
  notification, or make a personal-performance claim.
- Requires a separately authorized transport/identity layer before use
  with the actual Coach application.

**Next gate:** connect Coach event drafts to this adapter through an
authenticated, source-aware interface; then verify an end-to-end write,
restart, and replay on an isolated archive before deployment.
