"""Independent acceptance of the real synthetic capture-to-MSE pipeline."""

from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from test_fixture_contract import CASES, FIXTURES


class ConnectedPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from integrations.healthbridge.ingest import ingest_capture
            from integrations.mse_ingest import BatchConflict, RecoveryError, Scope
            from integrations.mse_ingest.connected import (
                ConnectedIngest,
                NORMALIZER_VERSION,
            )
            from integrations.mse_ingest.v02 import digest
            from integrations.mse_snapshot.ledger import replay_ledger_snapshot
            from mse.contracts import ContractError
        except ModuleNotFoundError as error:
            if not error.name.startswith("integrations"):
                raise
            raise unittest.SkipTest(
                "assemble the pinned connected integration candidate"
            )
        cls.ingest_capture = staticmethod(ingest_capture)
        cls.replay = staticmethod(replay_ledger_snapshot)
        cls.digest = staticmethod(digest)
        cls.ingest_class = ConnectedIngest
        cls.version = NORMALIZER_VERSION
        cls.errors = (BatchConflict, RecoveryError, ContractError)
        cls.scope = Scope(
            "independent-r4", "healthkit", "synthetic-nicky", "healtharchive"
        )
        schema = Path("docs/mse/integration/contracts/offline-integration.schema.json")
        cls.schema = json.loads(schema.read_bytes())

    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()

    def ledger(self):
        return self.ingest_class(
            self.root,
            scope=self.scope,
            archive_id="independent-r4",
            schema=self.schema,
        )

    def deliver(self, case, batch, replacement=None):
        fixture = CASES[case]
        path = FIXTURES / fixture.get("source_compatible_file", fixture["file"])
        raw = path.read_bytes() if replacement is None else replacement
        delivery = self.ingest_capture(
            self.ledger(),
            raw,
            batch_id=batch,
            capture_id=f"capture-{batch}",
            capture_kind="full_file" if case == "baseline" else "partial",
        )
        return delivery.receipt

    def snapshot(self, cutoff):
        return self.ledger().build_snapshot(
            measurement_start="2025-01-01T00:00:00Z",
            measurement_end="2027-01-01T00:00:00Z",
            knowledge_cutoff_sequence=cutoff,
            normalizer_version=self.version,
        )

    def verified_replay(self, snapshot):
        return self.replay(
            json.dumps(snapshot).encode(),
            ledger=self.ledger(),
            expected_scope=self.scope.fields(),
            expected_archive_id="independent-r4",
            max_members=100,
            max_bytes=100_000,
        )

    def member_ids(self, snapshot, field):
        return {member["source_revision"]["native_id"] for member in snapshot[field]}

    def test_real_ledger_reopen_and_replay_bind_exact_members(self):
        receipt = self.deliver("baseline", "baseline")
        self.assertEqual(receipt["status"], "normalized")
        self.assertEqual(self.ledger().verify_receipt(receipt), receipt)
        self.assertEqual(self.deliver("baseline", "baseline"), receipt)
        snapshot = self.snapshot(receipt["commit_sequence"])
        for actual, expected in (
            ("observations", "live_ids"),
            ("tombstones", "tombstone_ids"),
        ):
            self.assertEqual(
                self.member_ids(snapshot, actual),
                {value.lower() for value in CASES["baseline"][expected]},
            )
        output = self.verified_replay(snapshot)
        self.assertEqual(output["epistemic_class"], "derived")
        self.assertEqual(
            output["lineage"]["snapshot_manifest_sha256"], snapshot["snapshot_sha256"]
        )

    def test_repeated_fact_late_cutoff_and_conflict_keep_old_replay(self):
        receipt = self.deliver("baseline", "baseline")
        cutoff = receipt["commit_sequence"]
        first = self.snapshot(cutoff)
        changed = (
            (FIXTURES / CASES["baseline"]["source_compatible_file"])
            .read_bytes()
            .replace(b"64.25", b"81.0", 1)
        )
        with self.assertRaises(self.errors[0]):
            self.deliver("baseline", "baseline", changed)
        conflict = self.deliver("baseline", "conflict", changed)
        self.assertEqual(conflict["status"], "quarantined")
        self.deliver("partial", "repeated")
        self.deliver("empty", "empty")
        last = self.deliver("late", "late")
        newer = self.snapshot(last["commit_sequence"])
        self.assertEqual(self.snapshot(cutoff), first)
        late = {value.lower() for value in CASES["late"]["live_ids"]}
        self.assertEqual(
            self.member_ids(newer, "observations"),
            self.member_ids(first, "observations") | late,
        )
        self.assertEqual(newer["tombstones"], first["tombstones"])
        for member in first["observations"]:
            self.assertIn(member, newer["observations"])
        for snapshot in (first, newer):
            self.assertEqual(
                self.verified_replay(snapshot)["epistemic_class"], "derived"
            )

    def test_verified_replay_refuses_omission_and_corrupted_custody(self):
        receipt = self.deliver("baseline", "baseline")
        snapshot = self.snapshot(receipt["commit_sequence"])
        omitted = deepcopy(snapshot)
        omitted["observations"].pop()
        del omitted["snapshot_sha256"]
        omitted["snapshot_sha256"] = self.digest("mse.snapshot/0.2", omitted)
        with self.assertRaises(self.errors[2]):
            self.verified_replay(omitted)
        with sqlite3.connect(self.ledger().journal) as db:
            db.execute(
                "UPDATE deliveries SET artifact = ? WHERE batch_id = ?",
                (b"synthetic corruption", receipt["batch_id"]),
            )
        with self.assertRaises(self.errors[1:]):
            self.verified_replay(snapshot)

    def test_frozen_numeric_index_and_nonpositive_source_only_edges(self):
        from mother.physiology.archive import Archive

        vectors = json.loads(
            Path("docs/mse/integration/contracts/golden-vectors.json").read_bytes()
        )["capture_edge_cases"]
        cases = [("reading-index-2-vs-10", vectors["repeated_upsert"])]
        cases.extend((case["name"], case) for case in vectors["nonpositive"])
        for name, case in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                store = self.ingest_class(
                    Path(directory).resolve(),
                    scope=self.scope,
                    archive_id="independent-r4",
                    schema=self.schema,
                )
                expected = case["expected_export"]
                delivery = self.ingest_capture(
                    store,
                    case["source_utf8"].encode(),
                    batch_id=expected["batch_id"],
                    capture_id=expected["capture_id"],
                    capture_kind=expected["coverage"]["capture_kind"],
                )
                self.assertEqual(
                    store.verify_receipt(delivery.receipt), delivery.receipt
                )
                self.assertEqual(delivery.receipt["status"], "normalized")
                actual_upserts = [
                    row
                    for row in delivery.export["revisions"]
                    if row["operation"] == "upsert"
                ]
                expected_upserts = [
                    row for row in expected["revisions"] if row["operation"] == "upsert"
                ]
                self.assertEqual(len(actual_upserts), len(expected_upserts))
                for actual, target in zip(actual_upserts, expected_upserts):
                    self.assertEqual(actual["locators"], target["locators"])
                    self.assertEqual(actual["observation"], target["observation"])
                with Archive(store.archive) as archive:
                    run = archive.import_run(delivery.receipt["pf001_run_id"])
                    self.assertTrue(run["counts"]["revisions"])
                    if name != "reading-index-2-vs-10":
                        self.assertEqual(run["counts"]["records"], {})
                snapshot = store.build_snapshot(
                    measurement_start="2000-01-01T00:00:00Z",
                    measurement_end="2002-01-01T00:00:00Z",
                    knowledge_cutoff_sequence=delivery.receipt["commit_sequence"],
                    normalizer_version=self.version,
                )
                if name != "reading-index-2-vs-10":
                    self.assertEqual(snapshot["observations"], [])
                    self.assertTrue(
                        any(
                            loss["reason"] == "outside_reference_positive_domain"
                            for loss in snapshot["losses"]
                        )
                    )
                reopened = self.ingest_class(
                    Path(directory).resolve(),
                    scope=self.scope,
                    archive_id="independent-r4",
                    schema=self.schema,
                )
                result = self.replay(
                    json.dumps(snapshot).encode(),
                    ledger=reopened,
                    expected_scope=self.scope.fields(),
                    expected_archive_id="independent-r4",
                    max_members=100,
                    max_bytes=100_000,
                )
                self.assertEqual(
                    result["lineage"]["snapshot_manifest_sha256"],
                    snapshot["snapshot_sha256"],
                )

    def test_direct_ingest_rejects_export_that_disagrees_with_retained_source(self):
        from integrations.healthbridge.export import normalize_capture

        fixture = CASES["baseline"]["source_compatible_file"]
        original = (FIXTURES / fixture).read_bytes()
        alternatives = {
            "different-value": original.replace(b"41.5", b"42.5"),
            "different-source": original.replace(b"Synthetic QA", b"Synthetic other"),
            # Change metric and unit together so the submitted export remains
            # schema-valid for the asserted metric.
            "different-source-unit": original.replace(
                b"HRV (SDNN)", b"Heart rate"
            ).replace(b'"unit": "ms"', b'"unit": "bpm"'),
            "different-source-clock": original.replace(b"785000010", b"785000011"),
        }
        # Derive valid facts using the real adapter, then pass the wrong raw
        # capture with its correct artifact identity. No hand-built facts.
        for name, raw in alternatives.items():
            with self.subTest(name=name):
                self.assertNotEqual(original, raw)
                options = dict(
                    subject_id=self.scope.subject_id,
                    source_instance=self.scope.source_instance,
                    batch_id=name,
                    capture_id=name,
                    capture_kind="full_file",
                )
                export = normalize_capture(original, **options)
                revised = normalize_capture(raw, **options)
                revised["artifact"] = export["artifact"]
                with self.assertRaises((ValueError, self.errors[1])):
                    self.ledger().ingest_export(original, revised)

    def test_direct_ingest_rejects_omitted_source_tombstone(self):
        from integrations.healthbridge.export import normalize_capture

        original = (FIXTURES / CASES["baseline"]["source_compatible_file"]).read_bytes()
        export = normalize_capture(
            original,
            subject_id=self.scope.subject_id,
            source_instance=self.scope.source_instance,
            batch_id="omission",
            capture_id="omission",
            capture_kind="full_file",
        )
        unknown_id = CASES["baseline"]["tombstone_ids"][-1].lower()
        export["revisions"] = [
            row for row in export["revisions"] if row["native_id"] != unknown_id
        ]
        with self.assertRaises((ValueError, self.errors[1])):
            self.ledger().ingest_export(original, export)

    def test_decimal_precision_retains_source_and_records_conversion_loss(self):
        from decimal import Decimal
        from mother.physiology.archive import Archive

        original = (FIXTURES / CASES["baseline"]["source_compatible_file"]).read_bytes()
        lexeme = "41.500000000000000001"
        precise = original.replace(b"41.5", lexeme.encode(), 1)
        delivery = self.ingest_capture(
            self.ledger(),
            precise,
            batch_id="decimal-edge",
            capture_id="decimal-edge",
            capture_kind="full_file",
        )
        sdnn = next(
            row["observation"]
            for row in delivery.export["revisions"]
            if row.get("observation", {}).get("channel") == "hrv_sdnn"
        )
        self.assertEqual(sdnn["original_value"], lexeme)
        with Archive(self.ledger().archive) as archive:
            records = archive.records(current=False)
        snapshot = self.snapshot(delivery.receipt["commit_sequence"])
        self.assertEqual(
            self.verified_replay(snapshot)["lineage"]["snapshot_manifest_sha256"],
            snapshot["snapshot_sha256"],
        )
        if records:
            self.assertNotEqual(
                Decimal(lexeme), Decimal.from_float(records[0]["value"])
            )
        self.assertTrue(
            any(
                "precision" in loss["reason"] or "rounding" in loss["reason"]
                for loss in snapshot["losses"]
                if loss["field"] in {"value", "original_value"}
            ),
            "PF-001 projection or exclusion requires an explicit value precision loss",
        )
