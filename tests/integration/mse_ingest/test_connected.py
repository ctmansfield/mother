"""Use pinned ORACLE capture code and NICKY capture files, never fabricated receipts."""

from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from integrations.mse_ingest import BatchConflict, Scope
from integrations.mse_ingest.connected import ConnectedIngest, NORMALIZER_VERSION
from integrations.mse_ingest.v02 import digest
from mother.physiology.archive import Archive


@unittest.skipUnless(
    os.environ.get("MSE_R3_DEPENDENCY_ROOT"), "requires pinned R3 sibling sources"
)
class ConnectedTests(unittest.TestCase):
    def setUp(self):
        dependencies = Path(os.environ["MSE_R3_DEPENDENCY_ROOT"])
        self.schema = json.loads(
            (
                dependencies
                / "docs/mse/integration/contracts/offline-integration.schema.json"
            ).read_bytes()
        )
        self.fixtures = (
            dependencies / "tests/fixtures/mse_integration/source-compatible"
        )
        self.scope = Scope("forge-r3-test", "healthkit", "nicky-trial", "healtharchive")
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

    def open(self):
        return ConnectedIngest(
            self.root, archive_id="forge-r3-test", scope=self.scope, schema=self.schema
        )

    def capture(self, fixture, batch, *, original=None):
        from integrations.healthbridge.export import normalize_capture

        if original is None:
            original = (self.fixtures / f"{fixture}.json").read_bytes()
        exported = normalize_capture(
            original,
            subject_id=self.scope.subject_id,
            source_instance=self.scope.source_instance,
            batch_id=batch,
            capture_id=f"capture-{batch}",
            capture_kind="full_file" if fixture == "baseline" else "partial",
        )
        return original, exported

    def ingest(
        self,
        fixture,
        batch,
        *,
        original=None,
        normalizer=NORMALIZER_VERSION,
        service=None,
    ):
        return (service or self.open()).ingest_export(
            *self.capture(fixture, batch, original=original),
            normalizer_version=normalizer,
        )

    def snapshot(self, sequence, version=NORMALIZER_VERSION):
        return self.open().build_snapshot(
            measurement_start="2025-01-01T00:00:00Z",
            measurement_end="2027-01-01T00:00:00Z",
            knowledge_cutoff_sequence=sequence,
            normalizer_version=version,
        )

    def test_real_adapter_archive_and_reference_replay(self):
        from integrations.mse_snapshot.ledger import replay_ledger_snapshot

        receipt = self.ingest("baseline", "first")
        reopened = self.open()
        self.assertEqual(reopened.verify_receipt(receipt), receipt)
        snapshot = self.snapshot(receipt["commit_sequence"])
        self.assertTrue(reopened.verify_snapshot(snapshot))
        self.assertEqual(len(snapshot["observations"]), 2)
        self.assertEqual(len(snapshot["tombstones"]), 2)
        self.assertTrue(
            any(
                member["source_revision"]["native_id"].endswith("0004")
                for member in snapshot["tombstones"]
            )
        )
        with Archive(self.root / "physiology.sqlite3") as archive:
            records = archive.records(current=False)
            self.assertEqual(
                [(item["channel"], item["value"]) for item in records],
                [("hrv_sdnn", 41.5)],
            )
            self.assertEqual(records[0]["processing_version"], NORMALIZER_VERSION)
            self.assertEqual(
                sum(row["disposition"] == "deleted" for row in archive.revisions()), 2
            )
        derived = replay_ledger_snapshot(
            json.dumps(snapshot).encode(),
            ledger=reopened,
            expected_scope=self.scope.fields(),
            expected_archive_id="forge-r3-test",
            max_members=100,
            max_bytes=100_000,
        )
        self.assertEqual(derived["epistemic_class"], "derived")
        self.assertEqual(
            derived["lineage"]["snapshot_manifest_sha256"], snapshot["snapshot_sha256"]
        )

    def test_retries_conflict_receipt_order_and_exact_processing_version(self):
        first = self.ingest("baseline", "first")
        self.assertEqual(self.ingest("baseline", "first"), first)
        initial = self.snapshot(first["commit_sequence"])
        with self.assertRaises(BatchConflict):
            self.ingest("late", "first")
        cross_capture = json.loads((self.fixtures / "baseline.json").read_bytes())
        cross_capture["readings"][1]["value"] += 1
        changed = self.ingest(
            "baseline", "conflict", original=json.dumps(cross_capture).encode()
        )
        self.assertEqual(changed["status"], "quarantined")

        repeated = json.loads((self.fixtures / "baseline.json").read_bytes())
        for row in repeated["readings"]:
            row["receivedAt"] += 10
        second = self.ingest(
            "baseline", "second", original=json.dumps(repeated).encode()
        )
        self.assertEqual(self.snapshot(first["commit_sequence"]), initial)
        self.assertEqual(
            self.snapshot(second["commit_sequence"])["observations"],
            initial["observations"],
        )
        next_version = "forge-pf001-trial-version-2"
        remodel = self.ingest("baseline", "remodel", normalizer=next_version)
        self.assertEqual(
            self.snapshot(second["commit_sequence"], next_version)["observations"], []
        )
        replayed = self.snapshot(remodel["commit_sequence"], next_version)
        self.assertEqual(len(replayed["observations"]), 2)
        self.assertEqual(
            replayed["observations"][0]["receipt_id"], remodel["receipt_id"]
        )
        self.assertNotEqual(
            replayed["observations"][0]["processing_revision_sha256"],
            initial["observations"][0]["processing_revision_sha256"],
        )
        self.assertEqual(replayed["tombstones"], initial["tombstones"])
        late = self.ingest("late", "late")
        self.assertEqual(len(self.snapshot(late["commit_sequence"])["observations"]), 3)
        self.assertEqual(self.snapshot(first["commit_sequence"]), initial)

    def test_interrupted_archive_and_member_verification_after_restart(self):
        opened = self.open()

        def interrupt(phase):
            if phase == "archive":
                raise InterruptedError()

        opened._checkpoint = interrupt
        with self.assertRaises(InterruptedError):
            self.ingest("baseline", "interrupted", service=opened)
        custody = self.open().read_receipt("interrupted")
        self.assertEqual(custody["status"], "durably_received")
        self.assertEqual(self.snapshot(custody["commit_sequence"])["observations"], [])
        receipt = self.ingest("baseline", "interrupted")
        snapshot = self.snapshot(receipt["commit_sequence"])
        reopened = self.open()
        member = snapshot["observations"][0]
        self.assertTrue(
            reopened.verify_membership(reopened.archive_id, self.scope.fields(), member)
        )

        omitted = deepcopy(snapshot)
        omitted.pop("snapshot_sha256")
        omitted["observations"].pop()
        omitted["snapshot_sha256"] = digest("mse.snapshot/0.2", omitted)
        self.assertFalse(reopened.verify_snapshot(omitted))
        mismatched = deepcopy(member)
        mismatched["source_revision"]["locators"].append("/readings/999")
        self.assertFalse(
            reopened.verify_membership(
                reopened.archive_id, self.scope.fields(), mismatched
            )
        )

        with sqlite3.connect(self.root / "physiology.sqlite3") as db:
            db.execute(
                "UPDATE raw_artifacts SET content=CAST('corrupted synthetic input' AS BLOB)"
            )
        self.assertFalse(reopened.verify_snapshot(snapshot))
        self.assertFalse(
            reopened.verify_membership(reopened.archive_id, self.scope.fields(), member)
        )

    def test_source_only_zero_and_first_equal_sighting(self):
        capture = json.loads((self.fixtures / "baseline.json").read_bytes())
        sdnn = capture["readings"][1]
        sdnn["value"] = 0
        duplicate = dict(sdnn, receivedAt=sdnn["receivedAt"] - 10)
        capture["readings"].append(duplicate)
        original, export = self.capture(
            "baseline", "zero", original=json.dumps(capture).encode()
        )
        fact = next(
            item
            for item in export["revisions"]
            if item["native_id"] == sdnn["id"].lower() and item["operation"] == "upsert"
        )
        self.assertEqual(
            fact["observation"]["original_received_at"], str(sdnn["receivedAt"])
        )
        self.assertEqual(fact["locators"], ["/readings/1", "/readings/3"])
        receipt = self.open().ingest_export(original, export)
        snapshot = self.snapshot(receipt["commit_sequence"])
        self.assertTrue(self.open().verify_snapshot(snapshot))
        self.assertEqual(len(snapshot["observations"]), 1)
        self.assertTrue(
            any(
                loss["reason"] == "outside_reference_positive_domain"
                for loss in snapshot["losses"]
            )
        )
        with Archive(self.root / "physiology.sqlite3") as archive:
            self.assertEqual(archive.records(current=False), [])
            self.assertIn(
                fact["native_id"], {row["native_id"] for row in archive.revisions()}
            )
