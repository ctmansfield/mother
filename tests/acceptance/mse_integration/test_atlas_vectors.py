"""Independently recompute candidate 0.2 digests from exact ATLAS inputs."""

import base64
import hashlib
import json
import subprocess
import unittest
from decimal import Decimal
from pathlib import Path


PIN = "928a60b704c342c091eabd25ba41c8eb84d562de"
ROOT = Path(__file__).resolve().parents[3]
CONTRACT = "docs/mse/integration/contracts/"


def atlas_file(name):
    return subprocess.check_output(
        ["git", "show", f"{PIN}:{CONTRACT}{name}"], cwd=ROOT, stderr=subprocess.DEVNULL
    )


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def decimal(lexeme):
    return format(Decimal(lexeme).normalize(), "f")


def revision_preimage(scope, revision):
    operation = revision["operation"]
    if operation == "delete":
        values = {decimal(value) for value in revision["original_deleted_at"]}
        payload, = values
    else:
        row = revision["observation"]
        payload = {
            "channel": row["channel"],
            "value": decimal(row["original_value"]),
            "unit": row["original_unit"],
            "start": decimal(row["original_start"]),
            "end": decimal(row["original_end"]),
            "source_name": row["source_name"],
            "bundle_id": row["bundle_id"],
        }
    return ["mse.source-revision/0.2", scope, revision["native_id"], operation, payload]


class AtlasCandidateVectors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.vectors = json.loads(atlas_file("golden-vectors.json"))
        except subprocess.CalledProcessError:
            raise unittest.SkipTest(f"fetch exact ATLAS PR #28 object {PIN} for candidate checks")

    def check_vector(self, name, value):
        vector = self.vectors["digests"][name]
        actual = canonical(value)
        self.assertEqual(actual, vector["canonical_utf8"].encode("utf-8"))
        self.assertEqual(sha(actual), vector["sha256"])
        return vector["sha256"]

    def test_raw_artifact_anchor_and_export(self):
        v = self.vectors
        export = v["export"]
        raw = v["source_utf8"].encode("utf-8")
        self.assertEqual(sha(raw), export["artifact"]["sha256"])
        self.assertEqual(len(raw), export["artifact"]["byte_length"])
        anchors = json.loads(raw)["anchors"]
        self.assertEqual({key: sha(base64.b64decode(value)) for key, value in anchors.items()},
                         export["anchor_sha256"])
        digest = self.check_vector("export", ["mse.export/0.2", export])
        self.assertEqual(digest, v["receipt"]["export_sha256"])

    def test_source_fact_digests_and_equivalence(self):
        v = self.vectors
        export = v["export"]
        for revision in export["revisions"]:
            name = revision["operation"]
            digest = self.check_vector(name, revision_preimage(export["scope"], revision))
            self.assertEqual(digest, revision["revision_sha256"])
        for case, name in zip(v["fact_cases"], ("upsert", "changed_upsert", "second_delete")):
            revision = case["revision"]
            digest = self.check_vector(name, revision_preimage(export["scope"], revision))
            self.assertEqual(digest, revision["revision_sha256"])

    def test_receipt_snapshot_processing_and_projection(self):
        v = self.vectors
        receipt = v["receipt"]
        digest = self.check_vector("receipt_id", [
            "mse.receipt-id/0.2", receipt["archive_id"], receipt["scope"], receipt["batch_id"]
        ])
        self.assertEqual(digest, receipt["receipt_id"])
        snapshot = dict(v["snapshot"])
        expected = snapshot.pop("snapshot_sha256")
        self.assertEqual(expected, self.check_vector("snapshot", ["mse.snapshot/0.2", snapshot]))
        member, = snapshot["observations"]
        revision = member["source_revision"]
        keys = ("channel", "value", "unit", "event_start", "event_end", "epistemic_type",
                "classification_basis", "classification_evidence_sha256")
        fields = {key: revision["observation"][key] for key in keys}
        digest = self.check_vector("processing_revision", [
            "mse.processing-revision/0.2", revision["revision_sha256"],
            snapshot["normalizer_version"], fields
        ])
        self.assertEqual(digest, member["processing_revision_sha256"])
        self.check_vector("projected_envelope", ["mse.native-projection/0.2", v["native_projection"]])

    def test_receipt_binding_mutations_change_lookup_or_bound_body(self):
        receipt = self.vectors["receipt"]
        original_scope = receipt["scope"]
        original_digest = receipt["receipt_id"]
        for key in ("subject_id", "source_instance"):
            with self.subTest(field=key):
                scope = {**original_scope, key: "synthetic-other"}
                self.assertNotEqual(original_digest, sha(canonical([
                    "mse.receipt-id/0.2", receipt["archive_id"], scope, receipt["batch_id"]
                ])))
        for field in ("archive_id", "batch_id"):
            with self.subTest(field=field):
                changed = {**receipt, field: "synthetic-other"}
                self.assertNotEqual(original_digest, sha(canonical([
                    "mse.receipt-id/0.2", changed["archive_id"], original_scope, changed["batch_id"]
                ])))
        for field in ("artifact_sha256", "export_sha256"):
            with self.subTest(field=field):
                changed = {**receipt, field: "0" * 64}
                self.assertEqual(original_digest, changed["receipt_id"])
                self.assertNotEqual(canonical(receipt), canonical(changed))
