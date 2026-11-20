"""Exercise actual adapter-to-ledger custody before a PF-001 mapper is available."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

from test_fixture_contract import CASES, FIXTURES


class StopBeforeMapping(RuntimeError):
    pass


class ConnectedCustody(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from integrations.healthbridge.export import normalize_capture
            from integrations.mse_ingest import BatchConflict, RecoveryError, Scope
            from integrations.mse_ingest.v02 import IngestV02
        except ModuleNotFoundError as error:
            if error.name not in {"integrations", "integrations.healthbridge",
                                  "integrations.mse_ingest", "integrations.mse_ingest.v02"}:
                raise
            raise unittest.SkipTest("assemble the pinned 0.2 adapter and ledger")
        from test_atlas_vectors import atlas_file

        cls.normalize = staticmethod(normalize_capture)
        cls.ingest_cls = IngestV02
        cls.conflict = BatchConflict
        cls.recovery_error = RecoveryError
        cls.scope = Scope("synthetic-acceptance", "healthkit", "synthetic-store", "healtharchive")
        try:
            cls.schema = json.loads(atlas_file("offline-integration.schema.json"))
        except subprocess.CalledProcessError:
            raise unittest.SkipTest("fetch the pinned ATLAS exchange schema")

    def open_ledger(self, root):
        return self.ingest_cls(
            root, archive_id="synthetic-acceptance", scope=self.scope, schema=self.schema,
            clock=lambda: datetime(2026, 11, 21, tzinfo=timezone.utc),
        )

    def exported(self, raw, subject_id="synthetic-acceptance"):
        return self.normalize(
            raw, subject_id=subject_id, source_instance="synthetic-store",
            batch_id="synthetic-baseline", capture_id="synthetic-baseline", capture_kind="full_file",
        )

    def ingest(self, ledger, raw, export):
        def stop_before_mapping(*_):
            raise StopBeforeMapping("intentional stop before PF-001 normalization")

        return ledger.ingest(
            raw, export, adapter_version=export["exporter_version"], normalize=stop_before_mapping
        )

    def test_real_export_survives_restart_at_custody_and_rejects_changed_batch(self):
        raw = (FIXTURES / CASES["baseline"]["source_compatible_file"]).read_bytes()
        export = self.exported(raw)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = self.open_ledger(root)
            with self.assertRaises(StopBeforeMapping):
                self.ingest(ledger, raw, export)
            initial = ledger.read_receipt(export["batch_id"])
            self.assertEqual(initial["status"], "durably_received")
            self.assertEqual(initial["artifact_sha256"], export["artifact"]["sha256"])
            ledger = self.open_ledger(root)
            with self.assertRaises(StopBeforeMapping):
                self.ingest(ledger, raw, export)
            self.assertEqual(ledger.read_receipt(export["batch_id"]), initial)
            changed = raw.replace(b"64.25", b"81.0")
            self.assertNotEqual(raw, changed)
            with self.assertRaises(self.conflict):
                self.ingest(ledger, changed, self.exported(changed))
            self.assertEqual(ledger.read_receipt(export["batch_id"]), initial)

    def test_real_ledger_rejects_adapter_scope_and_artifact_substitution(self):
        raw = (FIXTURES / CASES["baseline"]["source_compatible_file"]).read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            ledger = self.open_ledger(Path(directory))
            with self.assertRaisesRegex(ValueError, "scope differs"):
                self.ingest(ledger, raw, self.exported(raw, "synthetic-other"))
            with self.assertRaisesRegex(ValueError, "artifact digest or length mismatch"):
                self.ingest(ledger, raw + b" ", self.exported(raw))

    def test_reopened_real_ledger_refuses_corrupted_retained_artifact(self):
        raw = (FIXTURES / CASES["baseline"]["source_compatible_file"]).read_bytes()
        export = self.exported(raw)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = self.open_ledger(root)
            with self.assertRaises(StopBeforeMapping):
                self.ingest(ledger, raw, export)
            with sqlite3.connect(ledger.journal) as db:
                db.execute(
                    "UPDATE deliveries SET artifact = ? WHERE batch_id = ?",
                    (b"synthetic corruption", export["batch_id"]),
                )
            with self.assertRaises(self.recovery_error):
                self.open_ledger(root).read_receipt(export["batch_id"])
