"""Exercise the projection using actual reopened synthetic ledger snapshots."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from integrations.healthbridge.ingest import ingest_capture
from integrations.mse_ingest import Scope
from integrations.mse_ingest.connected import ConnectedIngest, NORMALIZER_VERSION
from integrations.mse_privacy.custody import Grant, open_custody
from integrations.mse_privacy.export import (
    POLICY_VERSION, AnalyticalExporter, ExportDenied, ProjectionBinding,
)


class AnalyticalExportTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory(dir=Path.cwd().parent)
        self.addCleanup(temp.cleanup)
        sandbox = Path(temp.name).resolve()
        self.root = sandbox / "ledger"
        self.root.mkdir(mode=0o700)
        self.roots = {}
        for name in ("authority", "fence", "projection", "evidence", "vault"):
            root = sandbox / name
            root.mkdir(mode=0o700)
            self.roots[name + "_root"] = root
        self.now = datetime(2026, 11, 21, tzinfo=timezone.utc)
        self.scope = Scope("subject-marker", "healthkit", "source-marker", "healtharchive")
        self.schema = json.loads(Path(
            "docs/mse/integration/contracts/offline-integration.schema.json"
        ).read_bytes())
        row = {
            "id": "a0000000-0000-4000-8000-000000000001",
            "kind": "Heart rate", "value": 64.25, "unit": "bpm",
            "start": 1, "end": 2, "receivedAt": 9,
            "source": "source-name-marker", "bundleID": "bundle.marker",
        }
        hr = dict(row, kind="Heart rate")
        sdnn = dict(row, id="a0000000-0000-4000-8000-000000000002",
                    kind="HRV (SDNN)", value=42.25, unit="ms", start=3601, end=3602)
        sdnn2 = dict(sdnn, id="a0000000-0000-4000-8000-000000000004", end=7201)
        sdnn3 = dict(sdnn, id="a0000000-0000-4000-8000-000000000005")
        sparse = dict(sdnn, id="a0000000-0000-4000-8000-000000000006",
                      start=7201, end=7203)
        zero = dict(sdnn, id="a0000000-0000-4000-8000-000000000007", value=0)
        negative = dict(sdnn, id="a0000000-0000-4000-8000-000000000008", value=-1)
        deleted = "a0000000-0000-4000-8000-000000000003"
        raw = json.dumps({"readings": [hr, sdnn, sdnn2, sdnn3, sparse, zero, negative], "anchors": {}, "tombstones": {deleted: 10},
                          "backfillStart": 0}).encode()
        self.delivery = ingest_capture(
            self.ledger(), raw, batch_id="batch-marker", capture_id="capture-marker",
            capture_kind="full_file",
        )
        self.snapshot = self.ledger().build_snapshot(
            measurement_start="2001-01-01T00:00:00.000000Z",
            measurement_end="2001-01-02T00:00:00.000000Z",
            knowledge_cutoff_sequence=self.delivery.receipt["commit_sequence"],
            normalizer_version=NORMALIZER_VERSION,
        )
        self.binding = ProjectionBinding(
            tuple(self.scope.fields().items()), "archive-marker",
            self.snapshot["snapshot_sha256"], "recipient-marker", 1,
        )
        writer = Grant(
            role="projection_writer", scope=self.scope.fields(), purpose="aggregate_hr_sdnn",
            policy_version=POLICY_VERSION, generation=1, recipient="recipient-marker",
            expires_at=self.now + timedelta(minutes=15),
        )
        self.custody, self.credentials = open_custody(
            **self.roots, grants={
                "writer": writer, "analyst": replace(writer, role="analyst"),
                "other_recipient": replace(writer, recipient="another-recipient"),
            }, initialize=True, clock=lambda: self.now,
        )
        self.opens = []
        self.exporter = AnalyticalExporter(self.custody, self.open_ledger, self.binding)

    def open_ledger(self):
        self.opens.append("ledger")
        return self.ledger()

    def load_snapshot(self):
        self.opens.append("snapshot")
        return self.snapshot

    def ledger(self):
        return ConnectedIngest(
            self.root, archive_id="archive-marker", scope=self.scope, schema=self.schema,
        )

    def export(self, **overrides):
        return self.exporter.export(
            self.credentials["writer"], self.load_snapshot, **overrides,
        )

    def read(self, handle):
        return self.custody.read_projection(self.credentials["analyst"], handle)

    def test_reopened_snapshot_projects_only_coarse_aggregates_and_losses(self):
        original = deepcopy(self.snapshot)
        output = self.read(self.export()["view_id"])
        self.assertEqual(output["rows"], [
            {"bucket_index": 1, "channel": "hrv_sdnn", "unit": "ms", "mean_value": "42.2"},
        ])
        self.assertEqual(output["projection_loss"], [
            "coverage_unknown", "cross_bucket_interval_assigned_by_start",
            "relative_time_binning", "some_inputs_excluded", "some_outputs_suppressed",
            "value_aggregation_and_rounding",
        ])
        text = json.dumps(output)
        for forbidden in (
            "subject-marker", "source-marker", "source-name-marker", "bundle.marker",
            "archive-marker", "a0000000", "2001-01", "batch-marker", "capture-marker",
            self.snapshot["snapshot_sha256"], self.delivery.receipt["artifact_sha256"],
            str(self.root),
        ):
            self.assertNotIn(forbidden, text)
        other = self.read(self.export()["view_id"])
        reopened, _ = open_custody(**self.roots, clock=lambda: self.now)
        self.assertEqual(reopened.read_projection(self.credentials["analyst"],
                                                  output["view_id"]), output)
        self.assertNotEqual(output.pop("view_id"), other.pop("view_id"))
        self.assertEqual(output, other)
        self.assertEqual(self.snapshot, original)
        self.assertTrue(self.ledger().verify_snapshot(original))

    def test_role_recipient_and_fields_deny_before_private_reads(self):
        for role in ("analyst", "other_recipient"):
            with self.assertRaisesRegex(ExportDenied, "^Analytical export denied$"):
                self.exporter.export(self.credentials[role], self.load_snapshot)
        for fields in (frozenset({"native_id", "event_start", "device_id"}),
                       frozenset({"bundle_id"})):
            with self.assertRaisesRegex(ExportDenied, "^Analytical export denied$"):
                self.export(requested_fields=fields)
        scope = dict(self.binding.scope)
        scope["subject_id"] = "other-subject-marker"
        for binding in (
            replace(self.binding, scope=tuple(scope.items())),
            replace(self.binding, generation=2),
        ):
            worker = AnalyticalExporter(self.custody, self.open_ledger, binding)
            with self.assertRaisesRegex(ExportDenied, "^Analytical export denied$"):
                worker.export(self.credentials["writer"], self.load_snapshot)
        self.assertEqual(self.opens, [])

    def test_expired_writer_denies_before_private_reads(self):
        self.now += timedelta(minutes=16)
        with self.assertRaisesRegex(ExportDenied, "^Analytical export denied$"):
            self.export()
        self.assertEqual(self.opens, [])

    def test_status_and_tampered_snapshot_do_not_disclose_members(self):
        self.assertEqual(self.export(status_only=True), {"status": "available"})
        self.snapshot["observations"][0]["source_revision"]["observation"]["value"] = "99.5"
        with self.assertRaisesRegex(ExportDenied, "^Analytical export denied$"):
            self.export(status_only=True)

    def test_empty_interval_emits_no_channel_or_absence_claim(self):
        self.snapshot = self.ledger().build_snapshot(
            measurement_start="2001-02-01T00:00:00.000000Z",
            measurement_end="2001-02-02T00:00:00.000000Z",
            knowledge_cutoff_sequence=self.delivery.receipt["commit_sequence"],
            normalizer_version=NORMALIZER_VERSION,
        )
        worker = AnalyticalExporter(
            self.custody, self.open_ledger,
            replace(self.binding, snapshot_sha256=self.snapshot["snapshot_sha256"]),
        )
        handle = worker.export(self.credentials["writer"], self.load_snapshot)["view_id"]
        output = self.read(handle)
        self.assertEqual(output["rows"], [])
        self.assertEqual(output["projection_loss"], ["coverage_unknown"])

    def test_loader_failure_is_redacted_after_valid_authorization(self):
        def fail():
            raise RuntimeError("private/path/and-source-marker")

        with self.assertRaisesRegex(ExportDenied, "^Analytical export denied$") as caught:
            self.exporter.export(self.credentials["writer"], fail)
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertEqual(self.opens, [])
