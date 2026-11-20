"""Independently recompute candidate 0.2 digests from exact ATLAS inputs."""

import base64
import hashlib
import json
import subprocess
import unittest
from decimal import Decimal
from pathlib import Path


PIN = "3fe247446f03b7ee3e8a36a0a18bd19eb5a1329c"
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

    def test_schema_negative_vectors_reject_tampering(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("reuse an environment with PF-001 jsonschema installed")
        from copy import deepcopy

        schema = json.loads(atlas_file("offline-integration.schema.json"))
        Draft202012Validator.check_schema(schema)
        validators = {
            target: Draft202012Validator({"$defs": schema["$defs"], "$ref": f"#/$defs/{target}"})
            for target in ("receipt", "snapshot", "export")
        }
        for target, validator in validators.items():
            validator.validate(self.vectors[target])
        for variant in self.vectors["valid_receipt_variants"].values():
            validators["receipt"].validate(variant)
        for case in self.vectors["negative_cases"]:
            if case["stage"] != "schema":
                continue
            with self.subTest(case=case["name"]):
                target = case["target"]
                instance = deepcopy(self.vectors[target])
                for pointer, replacement in case["replace"].items():
                    *parts, field = pointer.split("/")[1:]
                    parent = instance
                    for part in parts:
                        parent = parent[int(part)] if isinstance(parent, list) else parent[part]
                    parent[field] = replacement
                self.assertFalse(validators[target].is_valid(instance))

    def test_rehashed_snapshot_and_projection_tamper_remain_semantically_invalid(self):
        from copy import deepcopy

        v = self.vectors
        snapshot = deepcopy(v["snapshot"])
        old = snapshot.pop("snapshot_sha256")
        snapshot["knowledge_cutoff_sequence"] = 1
        self.assertNotEqual(sha(canonical(["mse.snapshot/0.2", snapshot])), old)
        self.assertTrue(any(member["commit_sequence"] > snapshot["knowledge_cutoff_sequence"]
                            for member in snapshot["observations"]))
        projection = deepcopy(v["native_projection"])
        projection["observations"][0]["value"] = "43"
        self.assertNotEqual(
            sha(canonical(["mse.native-projection/0.2", projection])),
            v["digests"]["projected_envelope"]["sha256"],
        )
        self.assertNotEqual(projection, v["native_projection"])

    def test_two_receipt_repeated_fact_orders_and_cutoffs(self):
        from itertools import permutations

        v = self.vectors
        first, = v["snapshot"]["observations"]
        repeated = {**first, "receipt_id": "f" * 64, "commit_sequence": 5,
                    "artifact_sha256": "a" * 64, "source_revision": v["fact_cases"][0]["revision"]}
        self.assertEqual(first["source_revision"]["revision_sha256"],
                         repeated["source_revision"]["revision_sha256"])
        self.assertNotEqual(first["source_revision"], repeated["source_revision"])
        for order in permutations((first, repeated)):
            for cutoff, expected in ((1, None), (2, first), (4, first), (5, first)):
                with self.subTest(order=order[0]["commit_sequence"], cutoff=cutoff):
                    eligible = [member for member in order if member["commit_sequence"] <= cutoff]
                    self.assertEqual(min(eligible, key=lambda item: item["commit_sequence"], default=None),
                                     expected)

    def test_actual_selector_matches_atlas_two_receipt_vectors(self):
        try:
            from integrations.mse_snapshot.snapshot import select_fact_sighting
        except ModuleNotFoundError as error:
            if error.name not in {"integrations", "integrations.mse_snapshot"}:
                raise
            self.skipTest("assemble the pinned snapshot selector candidate")

        representative = self.vectors["representative_cases"]
        for case in representative["cases"]:
            expected = case["expected"]
            for field, output in (("observation", "observations"), ("tombstone", "tombstones")):
                with self.subTest(case=case["name"], fact=field):
                    rows = [representative["sightings"][index] for index in case["input_order"]]
                    selected = select_fact_sighting(
                        [(row["normalizer_version"], row[field]) for row in rows],
                        case["cutoff"], normalizer_version=expected["normalizer_version"],
                    )
                    self.assertEqual([selected], expected[output])
