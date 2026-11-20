"""Opt-in tests against exact ORACLE, FORGE, PF-001 and ATLAS source heads."""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import json
import os
import shutil
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from integrations.healthbridge.export import export_sha256, normalize_capture
from integrations.healthbridge.ingest import ingest_capture
from integrations.mse_ingest import RecoveryError, Scope
from integrations.mse_ingest.connected import ConnectedIngest, NORMALIZER_VERSION
from integrations.mse_snapshot.ledger import replay_ledger_snapshot, verify_ledger_replay_manifest
from mse import MODEL_VERSION, implementation_sha256
from mse.contracts import ContractError, canonical, digest


class ConnectedReplayTests(unittest.TestCase):
    def setUp(self):
        contract_dir = Path(os.environ["MSE_ATLAS_CONTRACT_DIR"])
        self.schema = json.loads((contract_dir / "offline-integration.schema.json").read_bytes())
        self.vectors = json.loads((contract_dir / "golden-vectors.json").read_bytes())
        self.original = self.vectors["source_utf8"].encode()
        self.scope = self.vectors["snapshot"]["scope"]
        self.archive_id = self.vectors["snapshot"]["archive_id"]
        self.normalizer_version = NORMALIZER_VERSION
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        delivery = ingest_capture(
            self.ledger(), self.original, batch_id="batch-1",
            capture_kind="full_file", capture_id="capture-1",
        )
        self.export, self.receipt = delivery.export, delivery.receipt
        self.assertEqual(self.receipt["status"], "normalized")
        self.reopened = self.ledger()
        self.snapshot = self.reopened.build_snapshot(
            measurement_start=self.vectors["snapshot"]["measurement_start"],
            measurement_end=self.vectors["snapshot"]["measurement_end"],
            knowledge_cutoff_sequence=self.receipt["commit_sequence"],
            normalizer_version=self.normalizer_version,
        )

    def ledger(self, root=None):
        return ConnectedIngest(
            self.root if root is None else root, archive_id=self.archive_id,
            scope=Scope(**self.scope), schema=self.schema,
        )

    def replay(self, snapshot):
        return replay_ledger_snapshot(
            canonical(snapshot).encode(), ledger=self.reopened,
            expected_scope=self.scope, expected_archive_id=self.archive_id,
            max_bytes=64_000, max_members=128,
        )

    def test_real_capture_reopened_snapshot_and_derived_lineage(self):
        self.assertEqual(self.reopened.verify_receipt(self.receipt), self.receipt)
        self.assertEqual(self.receipt["artifact_sha256"], sha256(self.original).hexdigest())
        self.assertEqual(self.receipt["export_sha256"], export_sha256(self.export))
        self.assertTrue(self.reopened.verify_snapshot(self.snapshot))
        result = self.replay(self.snapshot)
        self.assertEqual(result, self.replay(self.snapshot))
        self.assertEqual(result["epistemic_class"], "derived")
        self.assertEqual(result["reference_result"]["active_observation_count"], 1)
        self.assertEqual(len(self.snapshot["tombstones"]), 1)
        self.assertEqual(result["lineage"]["deletion_facts"], self.snapshot["tombstones"])
        self.assertEqual(result["lineage"]["snapshot_sha256"], sha256(canonical(self.snapshot).encode()).hexdigest())
        self.assertEqual(result["lineage"]["reference_run_id"], result["reference_result"]["run_id"])
        self.assertEqual(result["lineage"]["reference_result_sha256"], digest(result["reference_result"]))
        self.assertEqual(result["result_id"], "derived:" + digest(result["lineage"]))
        member = result["lineage"]["observation_revisions"][0]
        self.assertEqual(member["receipt_id"], self.receipt["receipt_id"])
        self.assertEqual(member["artifact_sha256"], self.receipt["artifact_sha256"])
        self.assertEqual(member["revision_sha256"], self.export["revisions"][0]["revision_sha256"])
        selected = self.snapshot["observations"][0]
        for field in ("pf001_revision_id", "processing_revision_sha256", "commit_sequence", "committed_at", "mother_received_at"):
            self.assertEqual(member[field], selected[field])
        self.assertEqual(result["lineage"]["snapshot_manifest_sha256"], self.snapshot["snapshot_sha256"])
        golden_projection = deepcopy(self.vectors["native_projection"])
        observation = golden_projection["observations"][0]
        processing_fields = (
            "channel", "value", "unit", "event_start", "event_end", "epistemic_type",
            "classification_basis", "classification_evidence_sha256",
        )
        source = self.vectors["snapshot"]["observations"][0]["source_revision"]
        processing = digest([
            "mse.processing-revision/0.2", source["revision_sha256"], self.normalizer_version,
            {key: source["observation"][key] for key in processing_fields},
        ])
        self.assertEqual(member["processing_revision_sha256"], processing)
        observation["provenance"]["processing_revision_sha256"] = processing
        self.assertEqual(result["lineage"]["native_projection_sha256"],
                         digest(["mse.native-projection/0.2", golden_projection]))
        run, lineage = result["reference_result"], result["lineage"]
        self.assertEqual(lineage["reference_implementation_sha256"], implementation_sha256())
        self.assertEqual(lineage["model_version"], MODEL_VERSION)
        self.assertEqual(lineage["model_config_sha256"], digest(run["configuration"]))

    def restored_ledger(self):
        restored = self.root.parent / (self.root.name + "-restored")
        restored.mkdir(mode=0o700)
        self.addCleanup(shutil.rmtree, restored)
        for source in (self.reopened.journal, self.reopened.archive):
            destination = restored / source.name
            with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as reader:
                with closing(sqlite3.connect(destination)) as writer:
                    reader.backup(writer)
                    self.assertEqual(writer.execute("PRAGMA integrity_check").fetchone(), ("ok",))
                    self.assertIsNone(writer.execute("PRAGMA foreign_key_check").fetchone())
            destination.chmod(0o600)

        return self.ledger(restored)

    def test_public_ingest_manifest_survives_paired_sqlite_restore(self):
        original = self.replay(self.snapshot)
        reopened = self.restored_ledger()
        self.assertEqual(reopened.verify_receipt(self.receipt), self.receipt)

        def verify(output):
            return verify_ledger_replay_manifest(
                canonical(self.snapshot).encode(), canonical(output).encode(),
                ledger=reopened, expected_scope=self.scope, expected_archive_id=self.archive_id,
                max_bytes=64_000, max_members=128, max_manifest_bytes=128_000,
            )

        self.assertEqual(verify(original), original)
        altered = deepcopy(original)
        altered["lineage"]["model_config_sha256"] = "e" * 64
        altered["result_id"] = "derived:" + digest(altered["lineage"])
        with self.assertRaisesRegex(ContractError, "differs from verified replay"):
            verify(altered)

    def test_synthetic_exact_manifests_keep_join_keys_across_custody_domains(self):
        other_archive = "independent-synthetic-custody"
        other = ConnectedIngest(
            self.root / "second-custody", archive_id=other_archive,
            scope=Scope(**self.scope), schema=self.schema,
        )
        accepted = ingest_capture(
            other, self.original, batch_id="separate-batch",
            capture_kind="full_file", capture_id="separate-capture",
        ).receipt
        reopened = ConnectedIngest(
            self.root / "second-custody", archive_id=other_archive,
            scope=Scope(**self.scope), schema=self.schema,
        )
        request = {field: self.snapshot[field] for field in ("measurement_start", "measurement_end", "normalizer_version")}
        snapshot = reopened.build_snapshot(
            **request, knowledge_cutoff_sequence=accepted["commit_sequence"]
        )
        first = self.replay(self.snapshot)
        second = replay_ledger_snapshot(
            canonical(snapshot).encode(), ledger=reopened,
            expected_scope=self.scope, expected_archive_id=other_archive,
            max_bytes=64_000, max_members=128,
        )
        self.assertNotEqual(first["result_id"], second["result_id"])
        self.assertNotEqual(self.receipt["receipt_id"], accepted["receipt_id"])
        self.assertEqual(self.receipt["artifact_sha256"], accepted["artifact_sha256"])
        first_row, second_row = (result["lineage"]["observation_revisions"][0] for result in (first, second))
        for key in ("revision_sha256", "processing_revision_sha256", "native_id"):
            self.assertEqual(first_row[key], second_row[key])
        self.assertEqual(
            first["reference_result"]["states"][0]["supporting_observation_ids"],
            second["reference_result"]["states"][0]["supporting_observation_ids"],
        )
        self.assertNotIn(str(self.root), canonical(first))
        self.assertNotIn(str(self.root), canonical(second))

    def test_direct_ingest_rejects_self_consistent_invented_source_facts(self):
        original_artifact = self.export["artifact"]
        variants = {
            "revised-value": self.original.replace(b"4.20e1", b"43", 1),
            "changed-source": self.original.replace("Synthetic µ".encode(), b"Other source", 1),
            "omitted-deletion": self.original.replace(
                b'"00000000-0000-4000-8000-000000000002":3', b"", 1
            ),
        }
        for name, modified in variants.items():
            with self.subTest(name=name):
                self.assertNotEqual(modified, self.original)
                forged = normalize_capture(
                    modified, subject_id=self.scope["subject_id"],
                    source_instance=self.scope["source_instance"], batch_id=name,
                    capture_id=name, capture_kind="full_file",
                )
                forged["artifact"] = original_artifact.copy()
                self.assertNotEqual(export_sha256(forged), export_sha256(self.export))
                try:
                    receipt = self.ledger(self.root / name).ingest_export(self.original, forged)
                except (ValueError, RecoveryError):
                    continue
                self.assertNotEqual(receipt["status"], "normalized")

    def test_exact_decimal_conversion_loss_survives_verified_restore(self):
        # Use a value whose exact decimal differs even from float's shortest spelling.
        exact = "42.000000000000000001"
        original = self.original.replace(b"4.20e1", exact.encode(), 1).replace(
            b'"00000000-0000-4000-8000-000000000001"',
            b'"00000000-0000-4000-8000-000000000003"', 1,
        )
        delivery = ingest_capture(
            self.reopened, original, batch_id="precision", capture_id="precision",
            capture_kind="partial",
        )
        self.assertEqual(delivery.receipt["status"], "normalized")
        revision = next(fact for fact in delivery.export["revisions"] if fact["operation"] == "upsert")
        self.assertEqual(revision["observation"]["original_value"], exact)
        self.assertEqual(revision["observation"]["value"], exact)
        self.assertEqual(delivery.receipt["artifact_sha256"], sha256(original).hexdigest())
        snapshot = self.reopened.build_snapshot(
            measurement_start=self.snapshot["measurement_start"],
            measurement_end=self.snapshot["measurement_end"],
            knowledge_cutoff_sequence=delivery.receipt["commit_sequence"],
            normalizer_version=self.normalizer_version,
        )
        result = self.replay(snapshot)
        self.assertEqual(result["input_losses"], snapshot["losses"])
        precision_losses = [
            {"field": field, "reason": "pf001_binary64_rounding", "locator": "/readings/0/value"}
            for field in ("original_value", "value")
        ]
        self.assertTrue(all(loss in delivery.export["losses"] for loss in precision_losses))
        self.assertTrue(all(loss in snapshot["losses"] for loss in precision_losses))
        selected = next(member for member in snapshot["observations"]
                        if member["source_revision"]["revision_sha256"] == revision["revision_sha256"])
        self.assertEqual(selected["source_revision"], revision)
        reopened = self.restored_ledger()
        with closing(sqlite3.connect(reopened.archive.as_uri() + "?mode=ro", uri=True)) as archive:
            row, = archive.execute(
                "SELECT record_json FROM normalized_records WHERE revision_id=?",
                (selected["pf001_revision_id"],),
            ).fetchone()
        record = json.loads(row)
        self.assertEqual(record["original_value"], 42.0)
        self.assertEqual(record["value"], 42.0)
        self.assertEqual(record["metadata"]["exact_decimal_value"], exact)
        self.assertEqual(reopened.verify_receipt(delivery.receipt), delivery.receipt)
        options = dict(
            ledger=reopened, expected_scope=self.scope, expected_archive_id=self.archive_id,
            max_bytes=64_000, max_members=128, max_manifest_bytes=128_000,
        )
        raw = canonical(snapshot).encode()
        self.assertEqual(
            verify_ledger_replay_manifest(raw, canonical(result).encode(), **options), result
        )
        counterfeit = deepcopy(result)
        counterfeit["input_losses"] = [loss for loss in result["input_losses"] if loss not in precision_losses]
        counterfeit["result_id"] = "derived:" + digest(counterfeit["lineage"])
        with self.assertRaisesRegex(ContractError, "differs from verified replay"):
            verify_ledger_replay_manifest(raw, canonical(counterfeit).encode(), **options)

    def test_resigned_forged_or_incomplete_snapshot_fails_before_replay(self):
        def replace_with_invented_fact(snapshot):
            member = snapshot["observations"][0]
            invented = normalize_capture(
                self.original.replace(b"4.20e1", b"43", 1),
                subject_id=self.scope["subject_id"], source_instance=self.scope["source_instance"],
                batch_id="counterfeit", capture_id="counterfeit", capture_kind="full_file",
            )["revisions"][0]
            fields = ("channel", "value", "unit", "event_start", "event_end",
                      "epistemic_type", "classification_basis", "classification_evidence_sha256")
            member["source_revision"] = invented
            member["processing_revision_sha256"] = digest([
                "mse.processing-revision/0.2", invented["revision_sha256"], self.normalizer_version,
                {field: invented["observation"][field] for field in fields},
            ])

        changes = {
            "self-consistent invented fact": replace_with_invented_fact,
            "invented-receipt": lambda s: s["observations"][0].update(receipt_id="f" * 64),
            "wrong-source": lambda s: s["observations"][0]["source_revision"].update(revision_sha256="e" * 64),
            "wrong-processing": lambda s: s["observations"][0].update(processing_revision_sha256="d" * 64),
            "past-cutoff": lambda s: s.update(knowledge_cutoff_sequence=self.receipt["commit_sequence"] - 1),
            "future-cutoff": lambda s: s.update(knowledge_cutoff_sequence=self.receipt["commit_sequence"] + 1),
            "omitted-tombstone": lambda s: s.update(tombstones=[]),
        }
        for name, change in changes.items():
            with self.subTest(name=name):
                forged = deepcopy(self.snapshot)
                del forged["snapshot_sha256"]
                change(forged)
                forged["snapshot_sha256"] = digest(["mse.snapshot/0.2", forged])
                with patch("integrations.mse_snapshot.ledger._replay_validated_snapshot") as run:
                    with self.assertRaises((ContractError, RecoveryError, ValueError)):
                        self.replay(forged)
                    run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
