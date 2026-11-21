"""Verify independently recorded source fixtures without importing a product adapter."""

import hashlib
import json
import unittest
from pathlib import Path
from uuid import UUID


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "mse_integration"
EXPECTED = json.loads((FIXTURES / "expected.json").read_bytes())
CASES = EXPECTED["cases"]


def source(case):
    return json.loads((FIXTURES / CASES[case]["file"]).read_bytes())


class CapturedArchiveFixtures(unittest.TestCase):
    def test_source_artifacts_match_pinned_bytes(self):
        self.assertEqual(set(EXPECTED["case_order"]), set(CASES))
        for name, case in CASES.items():
            with self.subTest(name=name):
                raw = (FIXTURES / case["file"]).read_bytes()
                self.assertEqual(len(raw), case["bytes"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), case["sha256"])

    def test_exact_case_memberships(self):
        for name, case in CASES.items():
            if case["disposition"] != "accept":
                continue
            with self.subTest(name=name):
                archive = source(name)
                tombstones = set(archive["tombstones"])
                self.assertEqual(set(case["tombstone_ids"]), tombstones)
                live = {
                    row["id"]
                    for row in archive["readings"]
                    if row["id"] not in tombstones and "deletedAt" not in row
                }
                self.assertEqual(set(case["live_ids"]), live)
                self.assertEqual(
                    {tuple(revision) for revision in case["observed_revisions"]},
                    {(row["id"], 1) for row in archive["readings"]},
                )
                for native_id in live | tombstones:
                    self.assertEqual(str(UUID(native_id)).upper(), native_id)

    def test_partial_empty_and_late_do_not_remove_prior_evidence(self):
        baseline = CASES["baseline"]
        self.assertTrue(set(CASES["partial"]["live_ids"]) < set(baseline["live_ids"]))
        self.assertEqual(source("empty")["readings"], [])
        self.assertEqual(CASES["empty"]["coverage"], "unknown")
        (late,) = source("late")["readings"]
        originals = source("baseline")["readings"]
        self.assertLess(late["start"], min(row["start"] for row in originals))
        self.assertGreater(
            late["receivedAt"], max(row["receivedAt"] for row in originals)
        )
        combined = EXPECTED["replay"]["after_baseline_partial_empty_late"]
        self.assertEqual(set(combined["live_ids"]), {*baseline["live_ids"], late["id"]})
        self.assertEqual(combined["tombstone_ids"], baseline["tombstone_ids"])

    def test_unknown_uuid_tombstone_and_measured_tombstone_are_distinct(self):
        archive = source("baseline")
        tombstones = set(archive["tombstones"])
        ids = {row["id"] for row in archive["readings"]}
        self.assertEqual(len(tombstones - ids), 1)
        (deleted,) = (row for row in archive["readings"] if "deletedAt" in row)
        self.assertEqual(deleted["deletedAt"], archive["tombstones"][deleted["id"]])

    def test_malformed_duplicate_and_delivery_conflict_are_distinct(self):
        with self.assertRaises(json.JSONDecodeError):
            source("malformed")
        first, second = source("conflicting-uuid")["readings"]
        self.assertEqual(first["id"], second["id"])
        self.assertNotEqual(first["value"], second["value"])
        self.assertEqual(
            CASES["changed-batch"]["batch_id"], CASES["baseline"]["batch_id"]
        )
        self.assertNotEqual(
            CASES["changed-batch"]["sha256"], CASES["baseline"]["sha256"]
        )


if __name__ == "__main__":
    unittest.main()
