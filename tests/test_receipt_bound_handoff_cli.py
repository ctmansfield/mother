import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ReceiptHandoffCLITests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.directive = self.root / "directive.json"
        self.paths = [self.root / "forge.json", self.root / "sentinel.json"]
        self.records = [
            {
                "issuer": owner,
                "receipt_id": f"receipt-{owner}",
                "task_id": "case-1",
                "revision": "r4",
                "artifact_sha256": "a" * 64,
                "observed_at": 20,
                "expires_at": 80,
                "verified_state": "STAGED",
            }
            for owner in ("FORGE", "SENTINEL")
        ]
        for path, value in zip(self.paths, self.records):
            path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        self.manifest = {
            "task_id": "case-1",
            "revision": "r4",
            "artifact_sha256": "a" * 64,
            "valid_from": 10,
            "expires_at": 90,
            "pins": [
                {
                    "issuer": value["issuer"],
                    "receipt_id": value["receipt_id"],
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
                for path, value in zip(self.paths, self.records)
            ],
            "state_rules": {
                "STAGED": {
                    "status": "HOLD",
                    "next_owner": "FORGE",
                    "next_action_code": "READ_DURABLE_LEDGER",
                },
            },
        }
        self.write_directive()

    def write_directive(self):
        self.directive.write_text(json.dumps(self.manifest), encoding="utf-8")

    def run_cli(self, paths=None, as_of=30):
        args = [
            sys.executable,
            "-B",
            "-m",
            "tools.receipt_bound_handoff_cli",
            "--directive",
            str(self.directive),
            "--as-of",
            str(as_of),
            *(str(path) for path in (self.paths if paths is None else paths)),
        ]
        completed = subprocess.run(args, capture_output=True, text=True, check=False)
        self.assertEqual(completed.stderr, "")
        return completed.returncode, json.loads(completed.stdout)

    def assert_hold(self, code, **kwargs):
        self.assertEqual(
            self.run_cli(**kwargs),
            (
                2,
                {
                    "disposition": "HOLD",
                    "reason": code,
                    "handoff": None,
                },
            ),
        )

    def test_verified_operational_hold_is_eligible_for_review(self):
        code, value = self.run_cli(paths=self.paths[::-1], as_of=20)
        self.assertEqual(code, 0)
        self.assertEqual(
            value,
            {
                "disposition": "ELIGIBLE_FOR_REVIEW",
                "reason": None,
                "handoff": {
                    "status": "HOLD",
                    "next_owner": "FORGE",
                    "next_action_code": "READ_DURABLE_LEDGER",
                    "evidence_ids": ["receipt-FORGE", "receipt-SENTINEL"],
                    "verified_state": "STAGED",
                },
            },
        )

    def test_empty_receipts_and_clock_boundaries(self):
        self.assert_hold("missing_receipt", paths=[])
        self.assert_hold("receipt_not_current", as_of=19)
        self.assert_hold("receipt_not_current", as_of=80)
        self.assert_hold("directive_not_current", as_of=90)
        self.assert_hold("invalid_as_of", as_of=-1)

    def test_exact_receipt_bytes_are_pinned(self):
        value = self.paths[0].read_bytes()
        self.paths[0].write_bytes(value + b" ")
        self.assert_hold("receipt_digest_mismatch")

    def test_receipt_bindings_and_conflicts_are_checked_in_core(self):
        for changes, reason in (
            ({"revision": "r3"}, "receipt_binding_mismatch"),
            ({"verified_state": "DURABLE"}, "conflicting_states"),
        ):
            with self.subTest(reason=reason):
                body = json.dumps({**self.records[0], **changes}).encode()
                self.paths[0].write_bytes(body)
                self.manifest["pins"][0]["sha256"] = hashlib.sha256(body).hexdigest()
                self.write_directive()
                self.assert_hold(reason)

    def test_nested_duplicate_keys_and_nonobject_directives(self):
        raw = self.directive.read_bytes()
        for value in (
            b"[]",
            b"\xff",
            raw.replace(b'"status": "HOLD"', b'"status": "PROCEED", "status": "HOLD"'),
        ):
            with self.subTest(value=value[:20]):
                self.directive.write_bytes(value)
                self.assert_hold("invalid_directive_document")

    def test_strict_field_types_and_unexpected_fields(self):
        original = json.loads(self.directive.read_bytes())
        for update in (
            {"valid_from": True},
            {"task_id": "\t "},
            {"extension": True},
            {"pins": [{"issuer": "X", "receipt_id": 3, "sha256": "a" * 64}]},
            {
                "state_rules": {
                    " ": {
                        "status": "HOLD",
                        "next_owner": "FORGE",
                        "next_action_code": "READ",
                    }
                }
            },
        ):
            with self.subTest(update=update):
                self.directive.write_text(
                    json.dumps({**original, **update}), encoding="utf-8"
                )
                self.assert_hold("invalid_directive_document")

    def test_read_errors_do_not_include_path_or_record(self):
        self.assert_hold("unreadable_input", paths=[self.root / "private-name.json"])
        self.directive = self.root / "secret-directive.json"
        self.assert_hold("unreadable_input")
