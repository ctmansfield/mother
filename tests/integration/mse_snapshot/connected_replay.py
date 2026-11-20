"""Opt-in tests against exact ORACLE, FORGE, PF-001 and ATLAS source heads."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from integrations.healthbridge.export import normalize_capture
from integrations.mse_ingest import RecoveryError, Scope
from integrations.mse_ingest.connected import ConnectedIngest
from integrations.mse_snapshot.ledger import replay_ledger_snapshot
from mse.contracts import ContractError, canonical, digest


class ConnectedReplayTests(unittest.TestCase):
    def setUp(self):
        contract_dir = Path(os.environ["MSE_ATLAS_CONTRACT_DIR"])
        self.schema = json.loads((contract_dir / "offline-integration.schema.json").read_bytes())
        self.vectors = json.loads((contract_dir / "golden-vectors.json").read_bytes())
        self.original = self.vectors["source_utf8"].encode()
        self.scope = self.vectors["snapshot"]["scope"]
        self.archive_id = self.vectors["snapshot"]["archive_id"]
        self.normalizer_version = self.vectors["snapshot"]["normalizer_version"]
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.export = normalize_capture(
            self.original, subject_id=self.scope["subject_id"],
            source_instance=self.scope["source_instance"],
            batch_id="batch-1", capture_kind="full_file", capture_id="capture-1",
            exporter_version=self.vectors["export"]["exporter_version"],
        )
        self.receipt = self.ledger().ingest_export(
            self.original, self.export, normalizer_version=self.normalizer_version
        )
        self.assertEqual(self.receipt["status"], "normalized")
        self.reopened = self.ledger()
        self.snapshot = self.reopened.build_snapshot(
            measurement_start=self.vectors["snapshot"]["measurement_start"],
            measurement_end=self.vectors["snapshot"]["measurement_end"],
            knowledge_cutoff_sequence=self.receipt["commit_sequence"],
            normalizer_version=self.normalizer_version,
        )

    def ledger(self):
        return ConnectedIngest(
            self.root, archive_id=self.archive_id,
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
        result = self.replay(self.snapshot)
        self.assertEqual(result["epistemic_class"], "derived")
        self.assertEqual(result["reference_result"]["active_observation_count"], 1)
        self.assertEqual(len(result["lineage"]["deletion_facts"]), 1)
        member = result["lineage"]["observation_revisions"][0]
        self.assertEqual(member["receipt_id"], self.receipt["receipt_id"])
        self.assertEqual(member["artifact_sha256"], self.receipt["artifact_sha256"])
        self.assertEqual(member["revision_sha256"], self.export["revisions"][0]["revision_sha256"])
        self.assertEqual(result["lineage"]["snapshot_manifest_sha256"], self.snapshot["snapshot_sha256"])
        self.assertEqual(
            result["lineage"]["native_projection_sha256"], self.vectors["digests"]["projected_envelope"]["sha256"]
        )

    def test_resigned_forged_or_incomplete_snapshot_fails_before_replay(self):
        changes = {
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
