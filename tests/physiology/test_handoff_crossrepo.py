"""Paired Coach → Mother offline handoff, durable restart and replay tests.

The CI workflow checks out a *pinned* Coach revision as the real sender.
No network, device APIs, credentials, or notifications are invoked by tests.
"""

import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from coach_app.physiology.handoff import pack_manual_event, save_to_outbox
from coach_app.physiology.manual_events import create_manual_event
from mother.physiology.archive import Archive
from mother.physiology.handoff import (
    EnvelopeError,
    accept_envelope,
    unpack_event,
)
from mother.physiology.manual_ingest import ManualIngestError
from mother.physiology.replay import build_replay

STAMP = "2026-11-07T04:10:00Z"
RECEIVED = "2026-11-07T04:15:00Z"
SUBJECT = "synthetic-subject"
RECEIVER = (
    Path(__file__).parents[2] / "mother" / "physiology" / "handoff.py"
)


def marker(event_id="synthetic:marker"):
    return create_manual_event(
        subject_id=SUBJECT,
        event_kind="user_marker",
        payload={"description": "electrode pocket adjusted", "value": 0},
        recorded_at=STAMP,
        occurrence_start="2026-11-07T14:05:00+10:00",
        event_id=event_id,
    )


def edit_envelope(data, **changes):
    payload = json.loads(data)
    payload.update(changes)
    return json.dumps(payload, sort_keys=True).encode("utf-8")


class OfflineHandoffTests(unittest.TestCase):
    def test_paired_sender_receiver_preserves_event_bytes(self):
        event = marker()
        envelope = pack_manual_event(event)
        original = unpack_event(envelope)
        self.assertEqual(json.loads(original), event)
        with Archive(":memory:") as archive:
            result = accept_envelope(
                archive, envelope, received_at=RECEIVED
            )
            self.assertEqual(result["status"], "new")
            source = archive.revision(result["revision_id"])
            self.assertEqual(source["source_available_at"], None)
            self.assertEqual(source["first_seen_at"], RECEIVED)
            retained = archive.connection.execute(
                "SELECT content FROM raw_artifacts WHERE sha256=?",
                (result["event_sha256"],),
            ).fetchone()[0]
            self.assertEqual(bytes(retained), original)
            stored = archive.current_records(kind="event")[0]
            self.assertEqual(stored["source_revision_id"], result["revision_id"])
            self.assertIsNone(stored["known_at"])
            self.assertEqual(stored["payload"]["value"], 0)

    def test_restart_idempotency_and_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outbox = root / "outbox"
            db = root / "archive.sqlite3"
            path = save_to_outbox(outbox, pack_manual_event(marker()))
            with Archive(db) as archive:
                first = accept_envelope(
                    archive, path.read_bytes(), received_at=RECEIVED
                )
                self.assertEqual(first["new_records"], 1)
            with Archive(db) as archive:
                second = accept_envelope(
                    archive,
                    path.read_bytes(),
                    received_at="2026-11-08T01:00:00Z",
                )
                self.assertEqual(second["status"], "already_archived")
                self.assertEqual(second["new_records"], 0)
                self.assertEqual(first["revision_id"], second["revision_id"])
                self.assertEqual(len(archive.current_records("event")), 1)
                self.assertEqual(len(archive.revisions()), 1)
                bundle = build_replay(
                    archive,
                    subject_id=SUBJECT,
                    start="2026-11-07T04:00:00Z",
                    end="2026-11-07T05:00:00Z",
                )
                self.assertEqual(len(bundle["events"]), 1)
                self.assertEqual(len(bundle["source_revisions"]), 1)
                self.assertEqual(
                    bundle["events"][0]["source_revision_id"],
                    bundle["source_revisions"][0]["id"],
                )
                self.assertEqual(
                    bundle["metadata"]["timing_policy"],
                    "retrospective_current_revision_projection",
                )

    def test_action_outcome_linked_but_not_inferred(self):
        action = create_manual_event(
            subject_id=SUBJECT,
            event_kind="reported_action",
            event_id="action:1",
            payload={"activity": "adjusted fabric"},
            recorded_at=STAMP,
        )
        outcome = create_manual_event(
            subject_id=SUBJECT,
            event_kind="outcome",
            event_id="outcome:1",
            reference_event=action,
            payload={"value": 0, "unit": "reported"},
            recorded_at=STAMP,
        )
        with Archive(":memory:") as archive:
            with self.assertRaises(ManualIngestError):
                accept_envelope(
                    archive, pack_manual_event(outcome), received_at=RECEIVED
                )
            accept_envelope(
                archive, pack_manual_event(action), received_at=RECEIVED
            )
            self.assertEqual(
                [x["event_kind"] for x in archive.current_records("event")],
                ["reported_action"],
            )
            accept_envelope(
                archive, pack_manual_event(outcome), received_at=RECEIVED
            )
            self.assertEqual(
                len(archive.current_records(kind="event")), 2
            )
            self.assertEqual(
                next(
                    x
                    for x in archive.current_records("event")
                    if x["event_kind"] == "outcome"
                )["related_ids"],
                [action["id"]],
            )

    def test_tampering_rejected_before_opening_archive(self):
        envelope = pack_manual_event(marker())
        raw = json.loads(envelope)
        content = base64.b64decode(raw["event_base64"])
        tampered = bytearray(content)
        tampered[-1] = ord("!")
        changed = edit_envelope(
            envelope,
            event_base64=base64.b64encode(tampered).decode("ascii"),
        )
        with self.assertRaises(EnvelopeError):
            unpack_event(changed)

    def test_incompatible_or_untrusted_wire_rejected(self):
        good = pack_manual_event(marker())
        for changes in (
            {"envelope_version": "2.0.0"},
            {"encoding": "plain"},
            {"content_type": "text/plain"},
            {"event_sha256": "0" * 64},
            {"event_base64": "@@broken@@"},
            {"extra_field": 123},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(EnvelopeError):
                    unpack_event(edit_envelope(good, **changes))
        with self.assertRaises(EnvelopeError):
            unpack_event(b'{"encoding":"base64","encoding":"base64"}')
        with self.assertRaises(EnvelopeError):
            unpack_event(b'{"event_base64":NaN}')

    def test_valid_checksum_does_not_override_mother_validation(self):
        event = marker()
        event["source"] = "untrusted:manual"
        wire = pack_manual_event(marker())
        payload = json.loads(wire)
        original = json.dumps(event, sort_keys=True).encode("utf-8")
        payload["event_base64"] = base64.b64encode(original).decode("ascii")
        payload["event_sha256"] = hashlib.sha256(original).hexdigest()
        forged = json.dumps(payload).encode("utf-8")
        with Archive(":memory:") as archive:
            with self.assertRaises(ManualIngestError):
                accept_envelope(archive, forged, received_at=RECEIVED)
            self.assertEqual(archive.revisions(), [])

    def test_changed_event_id_content_is_not_silently_overwritten(self):
        event = marker()
        changed = marker()
        changed["payload"] = {"description": "changed"}
        with Archive(":memory:") as archive:
            accept_envelope(
                archive, pack_manual_event(event), received_at=RECEIVED
            )
            with self.assertRaises(ValueError):
                accept_envelope(
                    archive, pack_manual_event(changed), received_at=RECEIVED
                )
            self.assertEqual(len(archive.current_records("event")), 1)
            self.assertEqual(len(archive.revisions()), 1)

    def test_cli_explicit_archive_and_symlink_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = save_to_outbox(root / "outbox", pack_manual_event(marker()))
            db = root / "archive.sqlite3"
            command = [
                sys.executable,
                "-m",
                "mother.physiology.handoff",
                "--input",
                str(file),
                "--archive",
                str(db),
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "new")
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(result.stdout)["status"], "already_archived"
            )
            alias = root / "symlink.json"
            alias.symlink_to(file)
            bad = command.copy()
            bad[bad.index(str(file))] = str(alias)
            self.assertEqual(
                subprocess.run(bad, capture_output=True).returncode, 2
            )
            self.assertTrue(db.exists())

    def test_cli_bad_input_does_not_create_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / "bad.json"
            file.write_bytes(b'{"envelope_version":"invalid"}')
            db = root / "new-archive.sqlite3"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mother.physiology.handoff",
                    "--input",
                    str(file),
                    "--archive",
                    str(db),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertFalse(db.exists())
            self.assertNotIn("synthetic-subject", result.stderr)


if __name__ == "__main__":
    unittest.main()
