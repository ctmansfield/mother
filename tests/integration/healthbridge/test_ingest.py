"""Exercise the adapter against exact external FORGE and fixture checkouts."""
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from integrations.healthbridge.capture import CaptureError
from integrations.healthbridge.ingest import ingest_capture

FIXTURES = os.environ.get("MSE_HEALTHBRIDGE_FIXTURES")
CONTRACT = os.environ.get("MSE_ATLAS_CONTRACT_DIR")


@unittest.skipUnless(FIXTURES and CONTRACT, "requires pinned fixtures and ATLAS schema")
class IngestTests(unittest.TestCase):
    def setUp(self):
        from integrations.mse_ingest import Scope
        from integrations.mse_ingest.connected import ConnectedIngest

        self.service_class = ConnectedIngest
        self.fixtures = Path(FIXTURES)
        self.expected = json.loads((self.fixtures / "expected.json").read_bytes())
        self.schema = json.loads(
            (Path(CONTRACT) / "offline-integration.schema.json").read_bytes()
        )
        self.scope = Scope("synthetic-mse-acceptance", "healthkit", "fixture-store",
                           "healtharchive")
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

    def service(self):
        return self.service_class(
            self.root, archive_id="oracle-fixture-trial", scope=self.scope,
            schema=self.schema,
        )

    def delivery(self, name, batch=None):
        case = self.expected["cases"].get(name) or self.expected["provisional_edges"][name]
        original = (self.fixtures / case["file"]).read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(), case["sha256"])
        return ingest_capture(
            self.service(), original, batch_id=batch or case.get("batch_id", name),
            capture_id="fixture-" + name,
            capture_kind="partial" if case.get("coverage") == "partial" else "full_file",
        )

    def test_invalid_fixtures_fail_before_custody(self):
        for name in ("malformed", "conflicting-uuid", "reversed-interval", "duplicate-json-key"):
            with self.subTest(name=name), self.assertRaises(CaptureError):
                self.delivery(name)
        self.assertFalse((self.root / "custody.sqlite3").exists())
        self.assertFalse((self.root / "physiology.sqlite3").exists())

    def test_actual_fixtures_bind_receipts_and_pf001_members(self):
        from integrations.mse_ingest import BatchConflict
        from mother.physiology.archive import Archive


        for name in ("baseline", "partial", "empty", "late"):
            with self.subTest(name=name):
                result = self.delivery(name)
                self.assertEqual(result.receipt["status"], "normalized")
                self.assertEqual(self.delivery(name), result)
                with Archive(self.service().archive) as archive:
                    run = archive.import_run(result.receipt["pf001_run_id"])
                    self.assertEqual(run["status"], "complete")
                    self.assertEqual(run["request"]["artifact_sha256"],
                                     result.export["artifact"]["sha256"])
                    self.assertEqual(run["request"]["export_sha256"],
                                     result.receipt["export_sha256"])
                    stored = {
                        row["revision_id"]: row for row in archive.revisions()
                    }
                    manifest = run["counts"]
                    self.assertEqual(
                        {json.loads(stored[member]["raw_json"])["mse_source_revision_sha256"]
                         for member in manifest["revisions"]},
                        {fact["revision_sha256"] for fact in result.export["revisions"]},
                    )
                    self.assertEqual(len(manifest["records"]), 1 if name in ("baseline", "partial") else 0)

        original = self.delivery("baseline")
        with self.assertRaises(BatchConflict):
            self.delivery("changed-batch")
        self.assertEqual(self.service().read_receipt(original.receipt["batch_id"]),
                         original.receipt)
        altered = self.delivery("changed-batch", batch="new-conflicting-batch")
        self.assertEqual(altered.receipt["status"], "quarantined")
        self.assertIsNone(altered.receipt["pf001_run_id"])

    def test_actual_numeric_and_delete_edges(self):
        numeric = self.delivery("numeric-time")
        self.assertEqual(numeric.receipt["status"], "normalized")
        self.assertEqual(
            {loss["field"] for loss in numeric.export["losses"]
             if loss["reason"] == "microsecond_rounding"},
            {"event_start", "event_end"},
        )
        deletions = self.delivery("repeated-delete")
        self.assertEqual(deletions.receipt["status"], "normalized")
        self.assertEqual(
            len([row for row in deletions.export["revisions"] if row["operation"] == "delete"]),
            3,
        )


    def test_actual_nonpositive_sdnn_remains_source_only(self):
        from integrations.mse_ingest.connected import NORMALIZER_VERSION
        from mother.physiology.archive import Archive

        goldens = json.loads((Path(CONTRACT) / "golden-vectors.json").read_bytes())
        for case in goldens["capture_edge_cases"]["nonpositive"]:
            with self.subTest(name=case["name"]), TemporaryDirectory() as directory:
                expected = case["expected_export"]
                scope = type(self.scope)(**expected["scope"])
                service = self.service_class(
                    Path(directory).resolve(), archive_id="oracle-source-only",
                    scope=scope, schema=self.schema,
                )
                result = ingest_capture(
                    service, case["source_utf8"].encode(),
                    batch_id=expected["batch_id"], capture_id=expected["capture_id"],
                    capture_kind=expected["coverage"]["capture_kind"],
                )
                self.assertEqual(result.receipt["status"], "normalized")
                actual = result.export.copy()
                actual["exporter_version"] = expected["exporter_version"]
                self.assertEqual(actual, expected)
                with Archive(service.archive) as archive:
                    run = archive.import_run(result.receipt["pf001_run_id"])
                    self.assertEqual(len(run["counts"]["revisions"]), 2)
                    self.assertEqual(run["counts"]["records"], {})
                snapshot = service.build_snapshot(
                    measurement_start="2001-01-01T00:00:00.000000Z",
                    measurement_end="2001-01-01T00:00:02.000000Z",
                    knowledge_cutoff_sequence=result.receipt["commit_sequence"],
                    normalizer_version=NORMALIZER_VERSION,
                )
                self.assertEqual(snapshot["observations"], [])
                self.assertEqual(len(snapshot["tombstones"]), 1)
                self.assertIn(
                    {"field": "value", "reason": "outside_reference_positive_domain",
                     "locator": "/readings/0/value"}, snapshot["losses"],
                )

    def test_pf001_float_rounding_is_visible_in_verified_snapshot(self):
        from integrations.mse_ingest.connected import NORMALIZER_VERSION
        from mother.physiology.archive import Archive

        goldens = json.loads((Path(CONTRACT) / "golden-vectors.json").read_bytes())
        raw = goldens["source_utf8"].replace("4.20e1", "9007199254740993").encode()
        self.scope = type(self.scope)(**goldens["export"]["scope"])
        service = self.service()
        delivery = ingest_capture(
            service, raw, batch_id="rounded", capture_id="rounded",
            capture_kind="full_file",
        )
        self.assertEqual(delivery.receipt["status"], "normalized")
        with Archive(service.archive) as archive:
            record, = archive.records(current=False)
            self.assertEqual(record["value"], 9007199254740992.0)
            self.assertEqual(record["metadata"]["exact_decimal_value"], "9007199254740993")
        snapshot = service.build_snapshot(
            measurement_start="2001-01-01T00:00:00.000000Z",
            measurement_end="2001-01-01T00:00:02.000000Z",
            knowledge_cutoff_sequence=delivery.receipt["commit_sequence"],
            normalizer_version=NORMALIZER_VERSION,
        )
        service.verify_snapshot(snapshot)
        member, = snapshot["observations"]
        self.assertEqual(member["source_revision"]["observation"]["value"], "9007199254740993")
        findings = {(row["field"], row["locator"]) for row in snapshot["losses"]
                    if row["reason"] == "pf001_binary64_rounding"}
        self.assertEqual(findings, {(field, "/readings/0/value")
                                   for field in ("original_value", "value")})

    def test_delivery_repr_does_not_disclose_export_or_receipt_fields(self):
        result = self.delivery("baseline")
        self.assertEqual(result.receipt["status"], "normalized")
        logged = repr(result)
        for value in (result.receipt["batch_id"], result.receipt["artifact_sha256"],
                      result.receipt["scope"]["subject_id"], result.receipt["receipt_id"]):
            self.assertNotIn(value, logged)
