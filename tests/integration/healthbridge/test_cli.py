"""Verify the offline CLI's deterministic, bounded summary and error behavior."""
import hashlib
import json
import subprocess
import sys
import unittest


class CaptureCLITests(unittest.TestCase):
    def invoke(self, raw, *options):
        return subprocess.run(
            [sys.executable, "-B", "-m", "integrations.healthbridge",
             "--subject-id", "synthetic-subject", "--source-instance", "test-store",
             "--batch-id", "batch-1", "--capture-id", "capture-1",
             "--capture-kind", "partial", *options],
            input=raw, capture_output=True, check=False,
        )

    def test_summary_is_deterministic_and_contains_no_source_fields(self):
        raw = b'{"readings":[],"anchors":{},"tombstones":{},"backfillStart":0}'
        result = self.invoke(raw)
        self.assertEqual((result.returncode, result.stderr), (0, b""))
        self.assertEqual(self.invoke(raw).stdout, result.stdout)
        value = json.loads(result.stdout)
        self.assertEqual(value["artifact_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(value["byte_length"], len(raw))
        self.assertEqual((value["upsert_count"], value["deletion_count"]), (0, 0))
        self.assertNotIn(b"synthetic-subject", result.stdout)
        self.assertNotIn(b"backfillStart", result.stdout)

    def test_status_only_omits_linkable_metadata_on_success(self):
        raw = (b'{"readings":[{"id":"a0000000-0000-4000-8000-000000000001",'
               b'"kind":"Heart rate","value":64.125,"unit":"bpm","start":785000000,'
               b'"end":785000001,"source":"synthetic-source-marker",'
               b'"bundleID":"test.synthetic.marker","receivedAt":785000010,'
               b'"synthetic/path-marker":"extension-value-marker"}],'
               b'"anchors":{},"tombstones":{},"backfillStart":0}')
        summary = self.invoke(raw)
        self.assertEqual(summary.returncode, 0)
        for marker in (b"a0000000", b"64.125", b"785000000", b"synthetic-source-marker",
                       b"test.synthetic.marker", b"path-marker", b"extension-value-marker"):
            self.assertNotIn(marker, summary.stdout + summary.stderr)
        status = self.invoke(raw, "--status-only")
        self.assertEqual((status.returncode, status.stdout, status.stderr),
                         (0, b'{"status":"valid"}\n', b""))

    def test_invalid_or_oversize_input_has_no_output_and_no_value_echo(self):
        for options in ((), ("--max-byte-length", "1")):
            with self.subTest(options=options):
                result = self.invoke(b"synthetic-value-marker", *options)
                self.assertEqual((result.returncode, result.stdout), (1, b""))
                self.assertEqual(result.stderr, b"healthbridge: capture rejected\n")

    def test_out_of_policy_cli_limits_return_usage_without_echo(self):
        for invalid in ("synthetic-argument-marker", "0", "1000000000"):
            with self.subTest(invalid=invalid):
                result = self.invoke(b"", "--max-depth", invalid)
                self.assertEqual((result.returncode, result.stdout), (2, b""))
                self.assertEqual(result.stderr, b"healthbridge: invalid arguments; see --help\n")
