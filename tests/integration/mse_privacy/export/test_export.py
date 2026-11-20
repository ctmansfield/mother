"""Exercise the projection using actual reopened synthetic ledger snapshots."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from integrations.healthbridge.ingest import ingest_capture
from integrations.mse_ingest import Scope
from integrations.mse_ingest.connected import ConnectedIngest, NORMALIZER_VERSION
from integrations.mse_privacy.export import AnalyticalExporter, ExportDenied, ProjectionGrant


class AnalyticalExportTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory(dir=Path.cwd().parent)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
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
        deleted = "a0000000-0000-4000-8000-000000000003"
        raw = json.dumps({"readings": [hr, sdnn, sdnn2, sdnn3, sparse], "anchors": {}, "tombstones": {deleted: 10},
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
        self.policy = ProjectionGrant(
            tuple(self.scope.fields().items()), "archive-marker", self.snapshot["snapshot_sha256"],
        )
        self.exporter = AnalyticalExporter(self.ledger(), self.policy)

    def ledger(self):
        return ConnectedIngest(
            self.root, archive_id="archive-marker", scope=self.scope, schema=self.schema,
        )

    def export(self, **overrides):
        return self.exporter.export(self.snapshot, **overrides)

    def test_reopened_snapshot_projects_only_coarse_aggregates_and_losses(self):
        original = deepcopy(self.snapshot)
        output = self.export()
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
        other = self.export()
        self.assertNotEqual(output.pop("view_id"), other.pop("view_id"))
        self.assertEqual(output, other)
        self.assertEqual(self.snapshot, original)
        self.assertTrue(self.ledger().verify_snapshot(original))

    def test_role_purpose_fields_and_scope_fail_closed(self):
        from dataclasses import replace

        for fields in (frozenset({"native_id", "event_start", "device_id"}),
                       frozenset({"bundle_id"})):
            with self.assertRaisesRegex(ExportDenied, "^Analytical export denied$"):
                self.export(requested_fields=fields)
        scope = dict(self.policy.scope)
        scope["subject_id"] = "other-subject-marker"
        for policy in (
            replace(self.policy, scope=tuple(scope.items())),
            replace(self.policy, role="analytical_reader"),
            replace(self.policy, purpose="other-purpose-marker"),
            replace(self.policy, snapshot_sha256="wrong-digest"),
        ):
            with self.assertRaisesRegex(ExportDenied, "^Analytical export denied$"):
                AnalyticalExporter(self.ledger(), policy).export(self.snapshot)

    def test_status_and_tampered_snapshot_do_not_disclose_members(self):
        self.assertEqual(self.export(status_only=True), {"status": "available"})
        self.snapshot["observations"][0]["source_revision"]["observation"]["value"] = "99.5"
        with self.assertRaisesRegex(ExportDenied, "^Analytical export denied$"):
            self.export(status_only=True)
