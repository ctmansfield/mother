"""Pinned Coach browser module → Mother immutable archive and replay tests.

No personal records, network requests, deployed services, or notifications.
The input is generated from Coach's production capture_ui.js, not a Python
reimplementation of the wire protocol.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from mother.physiology.archive import Archive
from mother.physiology.handoff import accept_envelope, unpack_event
from mother.physiology.replay import build_replay

HELPER = Path(__file__).with_name("generate_ui_fixture.cjs")
SUBJECT = "synthetic-subject"
RECEIPT = "2026-11-07T04:15:00Z"
BEGIN = "2026-11-07T04:00:00Z"
END = "2026-11-07T04:40:00Z"


def from_actual_coach(kind: str) -> bytes:
    env = dict(os.environ)
    process = subprocess.run(
        ["node", str(HELPER), kind],
        env=env,
        capture_output=True,
        check=True,
        text=True,
        timeout=15,
    )
    return base64.b64decode(process.stdout.strip(), validate=True)


@unittest.skipUnless(
    os.environ.get("COACH_CHECKOUT"),
    "Explicit pinned Coach source checkout is needed for paired acceptance",
)
class CoachUICrossRepoAcceptance(unittest.TestCase):
    def test_browser_builder_packet_is_importable_and_replayable(self):
        wire = from_actual_coach("marker")
        submitted = unpack_event(wire)
        event = json.loads(submitted)
        self.assertEqual(event["processing_version"], "coach-manual-events/0.1.0")
        self.assertEqual(event["subject_id"], SUBJECT)
        self.assertIsNone(event["known_at"])
        self.assertEqual(event["occurrence_start"], "2026-11-07T14:05:00+10:00")
        self.assertEqual(event["recorded_at"], "2026-11-07T04:12:00.000Z")
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "archive.sqlite3"
            with Archive(path) as archive:
                receipt = accept_envelope(archive, wire, received_at=RECEIPT)
                self.assertEqual(receipt["status"], "new")
                blob = archive.connection.execute(
                    "SELECT content FROM raw_artifacts WHERE sha256=?",
                    (hashlib.sha256(submitted).hexdigest(),),
                ).fetchone()[0]
                self.assertEqual(bytes(blob), submitted)
            with Archive(path) as archive:
                replay = build_replay(
                    archive,
                    subject_id=SUBJECT,
                    start=BEGIN,
                    end=END,
                )
                self.assertEqual(len(replay["events"]), 1)
                self.assertEqual(
                    replay["events"][0]["source_revision_id"],
                    replay["source_revisions"][0]["id"],
                )
                self.assertEqual(replay["events"][0]["payload"]["text"],
                    event["payload"]["text"])

    def test_repeated_transfer_after_restart_is_idempotent(self):
        wire = from_actual_coach("marker")
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "archive.sqlite3"
            with Archive(path) as archive:
                first = accept_envelope(archive, wire, received_at=RECEIPT)
                self.assertEqual(first["new_records"], 1)
            with Archive(path) as archive:
                second = accept_envelope(
                    archive, wire, received_at="2026-11-08T10:00:00Z"
                )
                self.assertEqual(second["status"], "already_archived")
                self.assertEqual(second["revision_id"], first["revision_id"])
                self.assertEqual(len(archive.revisions()), 1)
                self.assertEqual(len(archive.current_records("event")), 1)

    def test_action_and_outcome_have_separate_ids_and_linkage(self):
        action = from_actual_coach("action")
        outcome = from_actual_coach("outcome")
        with Archive(":memory:") as archive:
            result = accept_envelope(archive, action, received_at=RECEIPT)
            self.assertEqual(result["status"], "new")
            self.assertEqual(
                [e["event_kind"] for e in archive.current_records("event")],
                ["reported_action"],
            )
            accept_envelope(archive, outcome, received_at=RECEIPT)
            records = {e["event_kind"]: e for e in archive.current_records("event")}
            self.assertEqual(records["outcome"]["related_ids"],
                [records["reported_action"]["id"]])
            self.assertNotEqual(records["reported_action"]["id"], records["outcome"]["id"])
            self.assertEqual(records["outcome"]["epistemic_type"], "reported")

    def test_relayed_or_modified_event_does_not_fake_independent_measurements(self):
        original = json.loads(unpack_event(from_actual_coach("marker")))
        self.assertNotEqual(original["epistemic_type"], "measured")
        self.assertNotIn("value", original["payload"])
        self.assertEqual(original["quality_flags"], [])
        self.assertEqual(original["source_revision_id"], None)


if __name__ == "__main__":
    unittest.main()
