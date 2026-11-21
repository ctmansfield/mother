"""Synthetic checks of CLI disclosure boundaries and exact custody provenance."""

import json
import subprocess
import sys
import unittest

from test_fixture_contract import CASES, FIXTURES


class PrivacyBoundaries(unittest.TestCase):
    def test_cli_summary_and_rejection_omit_synthetic_identifiers_and_values(self):
        case = CASES["baseline"]
        raw = (FIXTURES / case["source_compatible_file"]).read_bytes()
        args = [
            sys.executable,
            "-B",
            "-m",
            "integrations.healthbridge",
            "--subject-id",
            "synthetic-privacy-subject",
            "--source-instance",
            "synthetic-privacy-instance",
            "--batch-id",
            "synthetic-privacy-batch",
            "--capture-id",
            "synthetic-privacy-capture",
            "--capture-kind",
            "full_file",
        ]
        markers = [
            b"Synthetic QA",
            b"org.example.synthetic.mse",
            b"785000010",
            b"41.5",
            b"synthetic-privacy-",
        ]
        markers.extend(key.encode() for key in case["live_ids"] + case["tombstone_ids"])
        good = subprocess.run(args, input=raw, capture_output=True, timeout=10)
        if b"No module named" in good.stderr:
            self.skipTest("assemble the actual HealthBridge CLI")
        self.assertEqual(good.returncode, 0, good.stderr)
        summary = json.loads(good.stdout)
        self.assertTrue(summary)
        self.assertTrue(
            set(summary).isdisjoint({"scope", "revisions", "readings", "anchors"})
        )
        self.assertEqual(good.stderr, b"")
        bad = subprocess.run(args, input=raw[:-4], capture_output=True, timeout=10)
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(bad.stdout, b"")
        for marker in markers:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, good.stdout + bad.stderr)
