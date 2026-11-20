from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from integrations.mse_ingest import BatchConflict, LocalIngest, RecoveryError, Scope
from mother.physiology.archive import Archive
from mother.physiology.contracts import canonical_json, content_hash, make_observation

SCOPE = Scope("synthetic:forge", "healthkit", "synthetic:store", "healtharchive")
CLOCK = datetime(2026, 11, 21, 1, 2, 3, tzinfo=timezone.utc)
NATIVE = "00000000-0000-4000-8000-000000000112"
ORIGINAL = b'{"synthetic_hr": 79.5}\n'
EXPORT = hashlib.sha256(b"synthetic export").hexdigest()


class Interrupted(Exception):
    pass


def normalize(original, context):
    if original != ORIGINAL:
        raise AssertionError("adapter received different original bytes")
    raw = {"native_id": NATIVE, "value": 79.5}
    observed = context.mother_received_at
    event = "2026-11-21T00:00:00Z"
    revision = {
        "revision_id": "revision:forge-synthetic",
        "source_instance": context.scope.archive_source,
        "collection": context.scope.collection,
        "source_key": NATIVE,
        "native_id": NATIVE,
        "revision_hash": content_hash(raw),
        "raw_json": canonical_json(raw),
        "first_seen_at": observed,
        "ingested_at": observed,
        "measurement_start": event,
        "measurement_end": event,
        "import_run_id": context.run_id,
        "disposition": "accepted",
        "artifact_sha256": context.artifact_sha256,
    }
    observation = make_observation(
        id="observation:forge-synthetic",
        subject_id=context.scope.subject_id,
        source_revision_id=revision["revision_id"],
        channel="heart_rate",
        measurement_start=event,
        measurement_end=event,
        first_seen_at=observed,
        ingested_at=observed,
        original_value=79.5,
        original_unit="beats/min",
        value=79.5,
        unit="beats/min",
    )
    return [revision], [observation]


class LocalIngestTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def apply(self, service=None, **options):
        arguments = dict(
            scope=SCOPE,
            batch_id="forge-local-batch",
            original=ORIGINAL,
            export_sha256=EXPORT,
            source_schema="healtharchive-codable-json/0.1",
            adapter_version="forge-test/1",
            normalize=normalize,
        )
        return (service or LocalIngest(self.root, clock=lambda: CLOCK)).ingest(
            **dict(arguments, **options)
        )

    def archive_state(self, root):
        if not (root / "physiology.sqlite3").exists():
            return [], [], 0
        with Archive(root / "physiology.sqlite3") as archive:
            return (
                archive.import_runs(),
                archive.records(current=False),
                archive.connection.execute(
                    "SELECT count(*) FROM raw_artifacts"
                ).fetchone()[0],
            )

    def test_identical_retry_after_reopen_and_conflict(self):
        first = self.apply()
        forbidden = Mock(side_effect=AssertionError("renormalized an accepted retry"))
        retry = self.apply(normalize=forbidden)
        self.assertEqual(first, retry)
        self.assertEqual(first["status"], "normalized")
        self.assertEqual(first["artifact_sha256"], hashlib.sha256(ORIGINAL).hexdigest())
        self.assertEqual(first["byte_length"], len(ORIGINAL))
        self.assertEqual(first["commit_sequence"], 1)
        for change in (
            {"original": ORIGINAL + b" "},
            {"export_sha256": "0" * 64},
            {"adapter_version": "changed"},
            {"source_schema": "changed"},
        ):
            with self.subTest(change=tuple(change)), self.assertRaises(BatchConflict):
                self.apply(**change)
        self.assertEqual(self.apply(normalize=forbidden), first)
        runs, observations, artifacts = self.archive_state(self.root)
        self.assertEqual([run["run_id"] for run in runs], [first["pf001_run_id"]])
        self.assertEqual([row["value"] for row in observations], [79.5])
        self.assertEqual(artifacts, 1)
        forbidden.assert_not_called()

    def test_interrupted_custody_run_archive_and_receipt(self):
        for phase in ("custody", "run", "archive", "receipt"):
            with self.subTest(phase=phase):
                root = self.root / phase
                service = LocalIngest(root, clock=lambda: CLOCK)

                def interrupt(current):
                    if current == phase:
                        raise Interrupted()

                service._checkpoint = interrupt
                with self.assertRaises(Interrupted):
                    self.apply(service)
                with sqlite3.connect(service.journal) as db:
                    before = db.execute(
                        "SELECT receipt_id, received_at, artifact, commit_sequence FROM deliveries"
                    ).fetchone()
                self.assertEqual(before[2], ORIGINAL)
                self.assertEqual(before[3], 1 if phase == "receipt" else None)
                runs, records, artifacts = self.archive_state(root)
                completed = phase in ("archive", "receipt")
                self.assertEqual(len(records), int(completed))
                self.assertEqual(artifacts, int(completed))
                self.assertEqual(len(runs), 0 if phase == "custody" else 1)
                forbidden = Mock(
                    side_effect=AssertionError("renormalized completed run")
                )
                reopened = LocalIngest(root)
                receipt = self.apply(
                    reopened, normalize=forbidden if completed else normalize
                )
                self.assertEqual(receipt["receipt_id"], before[0])
                self.assertEqual(before[1], "2026-11-21T01:02:03Z")
                self.assertEqual(
                    receipt["mother_received_at"], "2026-11-21T01:02:03.000000Z"
                )
                self.assertEqual(receipt["commit_sequence"], 1)
                if runs:
                    self.assertEqual(receipt["pf001_run_id"], runs[0]["run_id"])
                self.assertEqual(self.apply(reopened, normalize=forbidden), receipt)
                self.assertEqual(len(self.archive_state(root)[0]), 1)

    def test_invalid_json_schema_record_rolls_back_and_custody_survives(self):
        def invalid(original, context):
            revisions, records = normalize(original, context)
            records[0]["record_type"] = "invalid"
            return revisions, records

        with self.assertRaisesRegex(ValueError, "record_type"):
            self.apply(normalize=invalid)
        runs, observations, artifacts = self.archive_state(self.root)
        self.assertEqual([run["status"] for run in runs], ["running"])
        self.assertEqual((observations, artifacts), ([], 0))
        recovered = self.apply()
        self.assertEqual(recovered["pf001_run_id"], runs[0]["run_id"])

    def test_missing_normalized_record_fails_closed(self):
        self.apply()
        with sqlite3.connect(self.root / "physiology.sqlite3") as db:
            db.execute("DELETE FROM normalized_records")
        with self.assertRaisesRegex(RecoveryError, "normalized record digest mismatch"):
            self.apply()

    def test_missing_journal_fails_closed(self):
        self.apply()
        (self.root / "custody.sqlite3").unlink()
        with self.assertRaisesRegex(RecoveryError, "missing its custody journal"):
            self.apply()

    def test_concurrent_identical_retry_uses_one_run_and_receipt(self):
        with ThreadPoolExecutor(max_workers=2) as workers:
            receipts = list(workers.map(lambda _: self.apply(), range(2)))
        self.assertEqual(*receipts)
        self.assertEqual(len(self.archive_state(self.root)[0]), 1)
