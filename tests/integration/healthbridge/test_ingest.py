"""Exercise the adapter against exact external FORGE and fixture checkouts."""
import hashlib
import importlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from integrations.healthbridge.capture import CaptureError
from integrations.healthbridge.ingest import ingest_capture

FIXTURES = os.environ.get("MSE_HEALTHBRIDGE_FIXTURES")
CONTRACT = os.environ.get("MSE_ATLAS_CONTRACT_DIR")
MAPPER = os.environ.get("MSE_FORGE_MAPPER")


@unittest.skipUnless(FIXTURES and CONTRACT, "requires pinned fixtures and ATLAS schema")
class IngestTests(unittest.TestCase):
    def setUp(self):
        from integrations.mse_ingest import Scope
        from integrations.mse_ingest.v02 import IngestV02

        self.service_class = IngestV02
        self.fixtures = Path(FIXTURES)
        self.expected = json.loads((self.fixtures / "expected.json").read_bytes())
        self.schema = json.loads(
            (Path(CONTRACT) / "offline-integration.schema.json").read_bytes()
        )
        self.scope = Scope("synthetic-mse-acceptance", "healthkit", "fixture-store",
                           "healtharchive")
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def service(self):
        return self.service_class(
            self.root, archive_id="oracle-fixture-trial", scope=self.scope,
            schema=self.schema,
        )

    def delivery(self, name, mapper, batch=None):
        case = self.expected["cases"].get(name) or self.expected["provisional_edges"][name]
        original = (self.fixtures / case["file"]).read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(), case["sha256"])
        return ingest_capture(
            self.service(), original, batch_id=batch or case.get("batch_id", name),
            capture_id="fixture-" + name,
            capture_kind="partial" if case.get("coverage") == "partial" else "full_file",
            map_export=mapper,
        )

    def test_invalid_fixtures_fail_before_ledger_or_mapper(self):
        for name in ("malformed", "conflicting-uuid", "reversed-interval", "duplicate-json-key"):
            with self.subTest(name=name), self.assertRaises(CaptureError):
                self.delivery(name, None)
        self.assertFalse((self.root / "custody.sqlite3").exists())
        self.assertFalse((self.root / "physiology.sqlite3").exists())

    @unittest.skipUnless(MAPPER, "requires FORGE production-path mapper")
    def test_actual_fixtures_bind_receipts_and_pf001_members(self):
        from integrations.mse_ingest import BatchConflict
        from mother.physiology.archive import Archive

        module, function = MAPPER.split(":", 1)
        mapper = getattr(importlib.import_module(module), function)

        for name in ("baseline", "partial", "empty", "late"):
            with self.subTest(name=name):
                result = self.delivery(name, mapper)
                self.assertEqual(result.receipt["status"], "normalized")
                self.assertEqual(self.delivery(name, mapper), result)
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

        original = self.delivery("baseline", mapper)
        with self.assertRaises(BatchConflict):
            self.delivery("changed-batch", mapper)
        self.assertEqual(self.service().read_receipt(original.receipt["batch_id"]),
                         original.receipt)
        altered = self.delivery("changed-batch", mapper, batch="new-conflicting-batch")
        self.assertEqual(altered.receipt["status"], "quarantined")
        self.assertIsNone(altered.receipt["pf001_run_id"])

    @unittest.skipUnless(MAPPER, "requires FORGE production-path mapper")
    def test_actual_numeric_and_delete_edges(self):
        module, function = MAPPER.split(":", 1)
        mapper = getattr(importlib.import_module(module), function)
        numeric = self.delivery("numeric-time", mapper)
        self.assertEqual(numeric.receipt["status"], "normalized")
        self.assertEqual(
            {loss["field"] for loss in numeric.export["losses"]
             if loss["reason"] == "microsecond_rounding"},
            {"event_start", "event_end"},
        )
        deletions = self.delivery("repeated-delete", mapper)
        self.assertEqual(deletions.receipt["status"], "normalized")
        self.assertEqual(
            len([row for row in deletions.export["revisions"] if row["operation"] == "delete"]),
            3,
        )
