from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from jsonschema import ValidationError

from integrations.mse_ingest import BatchConflict, RecoveryError, Scope
from integrations.mse_ingest.v02 import IngestV02, digest, source_digest
from mother.physiology.contracts import canonical_json, content_hash, make_observation


@unittest.skipUnless(
    os.environ.get("MSE_ATLAS_CONTRACT_DIR"),
    "requires exact ATLAS 0.2 schema and vectors",
)
class Atlas02Tests(unittest.TestCase):
    def setUp(self):
        directory = Path(os.environ["MSE_ATLAS_CONTRACT_DIR"])
        self.schema = json.loads(
            (directory / "offline-integration.schema.json").read_bytes()
        )
        self.golden = json.loads((directory / "golden-vectors.json").read_bytes())
        self.export = self.golden["export"]
        self.original = self.golden["source_utf8"].encode("utf-8")
        self.scope = Scope(**self.export["scope"])
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

    def service(self, archive_id=None):
        return IngestV02(
            self.root,
            archive_id=archive_id or self.golden["receipt"]["archive_id"],
            scope=self.scope,
            schema=self.schema,
        )

    def ingest(self, export=None, original=None, service=None, normalizer=None):
        export = export or self.export
        return (service or self.service()).ingest(
            original or self.original,
            export,
            adapter_version="forge-golden-test",
            normalize=normalizer or (lambda raw, context: self.map(export, context)),
        )

    @staticmethod
    def map(export, context):
        revisions, records = [], []
        for fact in export["revisions"]:
            fingerprint = fact["revision_sha256"]
            raw = {"mse_source_revision_sha256": fingerprint}
            deleted = fact["operation"] == "delete"
            observation = fact.get("observation", {})
            revision = {
                "revision_id": "revision:" + fingerprint,
                "source_instance": context.scope.archive_source,
                "collection": context.scope.collection,
                "source_key": fact["native_id"],
                "native_id": fact["native_id"],
                "raw_json": canonical_json(raw),
                "revision_hash": content_hash(raw),
                "import_run_id": context.run_id,
                "disposition": "deleted" if deleted else "accepted",
                "first_seen_at": context.mother_received_at,
                "ingested_at": context.mother_received_at,
                "measurement_start": observation.get("event_start"),
                "measurement_end": observation.get("event_end"),
                "artifact_sha256": context.artifact_sha256,
            }
            revisions.append(revision)
            if not deleted and observation["epistemic_type"] != "unknown":
                records.append(
                    make_observation(
                        id="observation:" + fingerprint,
                        subject_id=context.scope.subject_id,
                        source_revision_id=revision["revision_id"],
                        channel=observation["channel"],
                        measurement_start=observation["event_start"],
                        measurement_end=observation["event_end"],
                        first_seen_at=context.mother_received_at,
                        ingested_at=context.mother_received_at,
                        epistemic_type=observation["epistemic_type"],
                        original_value=float(observation["original_value"]),
                        original_unit=observation["original_unit"],
                        value=float(observation["value"]),
                        unit=observation["unit"],
                    )
                )
        return revisions, records

    def batch(self, name, revisions):
        export = deepcopy(self.export)
        export["batch_id"] = name
        export["revisions"] = sorted(
            revisions,
            key=lambda fact: (
                fact["native_id"],
                fact["operation"],
                fact["revision_sha256"],
            ),
        )
        return export

    def test_golden_digest_and_reopened_receipt(self):
        service = self.service()
        golden = self.golden["receipt"]
        service.validators["receipt"].validate(golden)
        for receipt in self.golden["valid_receipt_variants"].values():
            service.validators["receipt"].validate(receipt)
        self.assertEqual(digest("mse.export/0.2", self.export), golden["export_sha256"])
        result = self.ingest(service=service)
        for key in (
            "schema_version",
            "archive_id",
            "scope",
            "batch_id",
            "artifact_sha256",
            "byte_length",
            "export_sha256",
            "receipt_id",
            "commit_sequence",
        ):
            self.assertEqual(result[key], golden[key])
        self.assertEqual(self.service().verify_receipt(result), result)
        self.assertEqual(self.ingest(), result)
        with self.assertRaisesRegex(RecoveryError, "differs from reopened"):
            self.service().verify_receipt(
                dict(result, committed_at="2099-01-01T00:00:00.000000Z")
            )
        with self.assertRaisesRegex(ValueError, "archive identity"):
            self.service().verify_receipt(dict(result, archive_id="foreign-archive"))
        with self.assertRaisesRegex(RecoveryError, "Configured archive identity"):
            self.ingest(service=self.service("foreign-archive"))

    def test_export_and_schema_negatives(self):
        for export, error in (
            (dict(self.export, extra=True), ValidationError),
            (
                dict(
                    self.export, artifact=dict(self.export["artifact"], sha256="0" * 64)
                ),
                ValueError,
            ),
            (
                dict(self.export, scope=dict(self.export["scope"], subject_id="wrong")),
                ValueError,
            ),
        ):
            with self.subTest(error=error), self.assertRaises(error):
                self.ingest(export)
        altered = deepcopy(self.export)
        altered["revisions"][0]["observation"]["original_value"] = "43"
        with self.assertRaisesRegex(ValueError, "source revision digest"):
            self.ingest(altered)
        receipt = self.ingest()
        with self.assertRaises(ValidationError):
            self.service().verify_receipt(dict(receipt, pf001_run_id=None))
        with self.assertRaises(BatchConflict):
            self.ingest(dict(self.export, capture_id="changed"))

    def test_custody_and_archive_interruptions_recover(self):
        service = self.service()
        for phase in ("custody", "archive"):

            def interrupt(current):
                if current == phase:
                    raise InterruptedError()

            service._checkpoint = interrupt
            with self.assertRaises(InterruptedError):
                self.ingest(service=service)

        def forbidden(*args):
            self.fail("completed PF-001 run was replayed")

        receipt = self.ingest(normalizer=forbidden)
        self.assertEqual(receipt["commit_sequence"], 2)
        custody = dict(
            receipt, status="durably_received", commit_sequence=1, pf001_run_id=None
        )
        with service._v02_write() as db:
            stored = db.execute(
                "SELECT body FROM stage_receipts WHERE sequence=1"
            ).fetchone()
        custody["committed_at"] = json.loads(stored["body"])["committed_at"]
        self.assertEqual(self.service().verify_receipt(custody), custody)

    def test_cross_capture_conflict_and_delete_cutoff(self):
        first = self.ingest()
        upsert, unrelated_delete = self.export["revisions"]
        conflict = deepcopy(upsert)
        conflict["observation"]["original_value"] = "43"
        conflict["observation"]["value"] = "43"
        conflict["revision_sha256"] = source_digest(self.export["scope"], conflict)
        quarantined = self.ingest(self.batch("conflict", [conflict]))
        self.assertEqual(quarantined["status"], "quarantined")
        self.assertIsNone(quarantined["pf001_run_id"])
        self.assertEqual(self.service().verify_receipt(quarantined), quarantined)
        first_delete = dict(unrelated_delete, native_id=upsert["native_id"])
        first_delete["revision_sha256"] = source_digest(
            self.export["scope"], first_delete
        )
        next_delete = dict(
            first_delete,
            original_deleted_at=["4"],
            deleted_at="2001-01-01T00:00:04.000000Z",
        )
        next_delete["revision_sha256"] = source_digest(
            self.export["scope"], next_delete
        )
        removed = self.ingest(self.batch("delete", [first_delete, next_delete]))
        late = self.ingest(self.batch("late", [upsert]))
        before = self.service().facts_at(first["commit_sequence"])
        self.assertEqual(len(before["observations"]), 1)
        self.assertEqual(len(before["tombstones"]), 1)
        self.assertEqual(
            self.service().facts_at(removed["commit_sequence"])["observations"], []
        )
        after = self.service().facts_at(late["commit_sequence"])
        self.assertEqual(after["observations"], [])
        self.assertEqual(len(after["tombstones"]), 3)

    def test_mapping_cannot_claim_normalization_without_source_members(self):
        with self.assertRaisesRegex(ValueError, "exactly the exported source facts"):
            self.ingest(normalizer=lambda raw, context: ([], []))
        self.assertEqual(self.ingest()["status"], "normalized")
