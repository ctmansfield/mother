"""Offline acceptance for immutable Coach manual event ingestion.

All inputs are synthetic; this suite does not use device APIs or notifications.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from mother.physiology.archive import Archive
from mother.physiology.contracts import (
    canonical_json,
    content_hash,
    make_event,
    stable_id,
)
from mother.physiology.manual_ingest import (
    ManualIngestError,
    ingest_manual_event,
)
from mother.physiology.replay import build_replay


SUBJECT = "synthetic-subject"
WHEN = "2026-11-07T04:00:00Z"
RECEIVED = "2026-11-07T04:03:00Z"


def draft(event_id="marker:1", kind="user_marker", **changes):
    raw = {
        "schema_version": "1.0.0",
        "record_type": "event",
        "id": event_id,
        "subject_id": SUBJECT,
        "processing_version": "coach-manual-events/0.1.0",
        "event_kind": kind,
        "occurrence_start": WHEN,
        "occurrence_end": None,
        "known_at": None,
        "recorded_at": WHEN,
        "source": "coach:manual",
        "source_revision_id": None,
        "session_id": None,
        "related_ids": [],
        "payload": {"description": "Synthetic marker only"},
        "epistemic_type": "reported",
        "quality_flags": [],
    }
    raw.update(changes)
    return raw


def wire(raw):
    return (json.dumps(raw, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def seed_parent(archive, kind, parent_id):
    """Create a typed non-Coach parent fixture using existing Archive APIs."""
    source = "fixture:annotation-system"
    collection = "fixture_annotations"
    raw = {"synthetic_kind": kind, "synthetic_id": parent_id}
    source_key = "native:" + parent_id
    revision_hash = content_hash(raw)
    revision_id = stable_id(
        "revision", source, collection, source_key, revision_hash
    )
    run = archive.begin_run(
        source,
        collection,
        "fixture/1",
        {"subject_id": SUBJECT},
        started_at=RECEIVED,
    )
    revision = {
        "revision_id": revision_id,
        "source_instance": source,
        "collection": collection,
        "source_key": source_key,
        "native_id": parent_id,
        "revision_hash": revision_hash,
        "raw_json": canonical_json(raw),
        "first_seen_at": RECEIVED,
        "ingested_at": RECEIVED,
        "source_available_at": None,
        "source_modified_at": None,
        "measurement_start": WHEN,
        "measurement_end": None,
        "import_run_id": run,
        "disposition": "accepted",
        "rejection_reason": None,
        "artifact_sha256": None,
        "observed_at": RECEIVED,
    }
    parent = make_event(
        id=parent_id,
        subject_id=SUBJECT,
        processing_version="fixture/1",
        event_kind=kind,
        occurrence_start=WHEN,
        recorded_at=WHEN,
        source=source,
        source_revision_id=revision_id,
        epistemic_type="reported",
    )
    archive.commit_batch(run, [revision], [parent], complete=True)
    return parent


class ManualArchiveAcceptance(unittest.TestCase):
    def test_marker_retains_original_bytes_and_stable_revision(self):
        with Archive(":memory:") as archive:
            raw = draft()
            data = wire(raw)
            result = ingest_manual_event(
                archive, data, received_at=RECEIVED
            )
            self.assertEqual(result["new_records"], 1)
            self.assertEqual(result["artifact_sha256"], hashlib.sha256(data).hexdigest())
            original = archive.connection.execute(
                "SELECT content FROM raw_artifacts WHERE sha256=?",
                (result["artifact_sha256"],),
            ).fetchone()[0]
            self.assertEqual(bytes(original), data)
            stored = archive.current_records(kind="event")[0]
            self.assertEqual(stored["id"], raw["id"])
            self.assertEqual(stored["source_revision_id"], result["revision_id"])
            self.assertEqual(stored["known_at"], None)
            self.assertEqual(stored["payload"], raw["payload"])
            revision = archive.revision(result["revision_id"])
            self.assertIsNone(revision["source_available_at"])
            self.assertEqual(revision["first_seen_at"], RECEIVED)

    def test_idempotency_and_restart(self):
        with TemporaryDirectory() as directory:
            database = Path(directory) / "archive.sqlite3"
            data = wire(draft())
            with Archive(database) as archive:
                first = ingest_manual_event(
                    archive, data, received_at=RECEIVED
                )
                self.assertEqual(first["new_records"], 1)
            with Archive(database) as archive:
                later = ingest_manual_event(
                    archive, data, received_at="2026-11-08T04:00:00Z"
                )
                self.assertEqual(later["new_records"], 0)
                self.assertEqual(later["repeated_revisions"], 1)
                self.assertEqual(len(archive.current_records(kind="event")), 1)
                self.assertEqual(len(archive.revisions()), 1)
                self.assertEqual(
                    archive.revision(first["revision_id"])["first_seen_at"],
                    RECEIVED,
                )

    def test_conflicting_event_identity_rejected_without_overwrite(self):
        with Archive(":memory:") as archive:
            ingest_manual_event(archive, wire(draft()), received_at=RECEIVED)
            bad = draft(payload={"description": "Changed in place"})
            with self.assertRaises(ValueError):
                ingest_manual_event(
                    archive, wire(bad), received_at="2026-11-07T04:05:00Z"
                )
            original = archive.current_records(kind="event")
            self.assertEqual(len(original), 1)
            self.assertEqual(
                original[0]["payload"], {"description": "Synthetic marker only"}
            )
            self.assertEqual(len(archive.revisions()), 1)
            self.assertEqual(
                len([run for run in archive.import_runs() if run["status"] == "failed"]),
                1,
            )

    def test_reported_action_and_missing_outcome_remain_distinct(self):
        with Archive(":memory:") as archive:
            action = draft("action:1", "reported_action")
            ingest_manual_event(archive, wire(action), received_at=RECEIVED)
            self.assertEqual(
                [r["event_kind"] for r in archive.current_records(kind="event")],
                ["reported_action"],
            )
            outcome = draft(
                "outcome:1",
                "outcome",
                related_ids=["action:1"],
                payload={"value": 0, "unit": "reported"},
            )
            ingest_manual_event(archive, wire(outcome), received_at=RECEIVED)
            stored = archive.current_records(kind="event")
            self.assertEqual({r["event_kind"] for r in stored}, {
                "reported_action", "outcome"
            })
            self.assertEqual(
                next(r for r in stored if r["event_kind"] == "outcome")["payload"]["value"], 0
            )

    def test_unknown_or_incompatible_parents_rejected(self):
        with Archive(":memory:") as archive:
            with self.assertRaises(ManualIngestError):
                ingest_manual_event(
                    archive,
                    wire(draft("answer:1", "answer", related_ids=["missing"])),
                    received_at=RECEIVED,
                )
            ingest_manual_event(
                archive, wire(draft("action:1", "reported_action")),
                received_at=RECEIVED,
            )
            with self.assertRaises(ManualIngestError):
                ingest_manual_event(
                    archive,
                    wire(draft("answer:2", "answer", related_ids=["action:1"])),
                    received_at=RECEIVED,
                )

    def test_question_recommendation_parent_types(self):
        with Archive(":memory:") as archive:
            seed_parent(archive, "question", "question:1")
            seed_parent(archive, "recommendation", "recommendation:1")
            answer = draft("answer:1", "answer", related_ids=["question:1"])
            ack = draft(
                "ack:1", "acknowledgment", related_ids=["recommendation:1"]
            )
            action = draft(
                "action:1", "reported_action", related_ids=["ack:1"]
            )
            for record in (answer, ack, action):
                ingest_manual_event(
                    archive, wire(record), received_at=RECEIVED
                )
            kinds = {r["id"]: r["event_kind"] for r in archive.current_records("event")}
            self.assertEqual(kinds["answer:1"], "answer")
            self.assertEqual(kinds["ack:1"], "acknowledgment")
            self.assertEqual(kinds["action:1"], "reported_action")

    def test_different_subject_parent_and_session_are_rejected(self):
        with Archive(":memory:") as archive:
            ingest_manual_event(
                archive, wire(draft("action:1", "reported_action")),
                received_at=RECEIVED,
            )
            with self.assertRaises(ManualIngestError):
                ingest_manual_event(
                    archive,
                    wire(draft(
                        "cross:1",
                        "outcome",
                        subject_id="other-subject",
                        related_ids=["action:1"],
                    )),
                    received_at=RECEIVED,
                )
            with self.assertRaises(ManualIngestError):
                ingest_manual_event(
                    archive,
                    wire(draft("marker:2", session_id="missing-session")),
                    received_at=RECEIVED,
                )

    def test_malformed_or_forged_fields_rejected(self):
        with Archive(":memory:") as archive:
            for invalid in [
                wire(draft(source_revision_id="forged-revision")),
                wire(draft(epistemic_type="measured")),
                wire(draft(source="coach:automated")),
                wire(draft(recorded_at="2026-11-07T04:00:00")),
                b'{"record_type":"event","record_type":"event"}',
                b'{"payload":NaN}',
                b'{"id":',
            ]:
                with self.subTest(invalid=invalid[:40]):
                    with self.assertRaises(ValueError):
                        ingest_manual_event(
                            archive, invalid, received_at=RECEIVED
                        )
            self.assertEqual(archive.revisions(), [])

    def test_bounded_input_and_no_unknown_revisions(self):
        with Archive(":memory:") as archive:
            with self.assertRaises(ManualIngestError):
                ingest_manual_event(
                    archive, b"x" * (256 * 1024 + 1),
                    received_at=RECEIVED
                )
            with self.assertRaises(ManualIngestError):
                ingest_manual_event(
                    archive, wire(draft(related_ids=["action:missing"])),
                    received_at=RECEIVED,
                )
            self.assertEqual(len(archive.revisions()), 0)

    def test_replay_keeps_actions_and_original_lineage(self):
        with TemporaryDirectory() as directory:
            database = Path(directory) / "archive.sqlite3"
            with Archive(database) as archive:
                for row in (
                    draft("marker:1"),
                    draft("action:1", "reported_action"),
                    draft("outcome:1", "outcome", related_ids=["action:1"]),
                ):
                    ingest_manual_event(
                        archive, wire(row), received_at=RECEIVED
                    )
            with Archive(database) as archive:
                bundle = build_replay(
                    archive,
                    subject_id=SUBJECT,
                    start="2026-11-07T03:00:00Z",
                    end="2026-11-07T05:00:00Z",
                )
                self.assertEqual(len(bundle["events"]), 3)
                self.assertEqual(len(bundle["source_revisions"]), 3)
                self.assertTrue(all(
                    r["source_revision_id"] in {
                        s["id"] for s in bundle["source_revisions"]
                    }
                    for r in bundle["events"]
                ))
                self.assertEqual(
                    next(r for r in bundle["events"] if r["id"] == "outcome:1")["related_ids"],
                    ["action:1"],
                )


if __name__ == "__main__":
    unittest.main()
