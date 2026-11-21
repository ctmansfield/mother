import json
import subprocess
import sys
import unittest

from test_receipt_bound_handoff_cli import ReceiptHandoffCLITests


class CandidateCLITests(unittest.TestCase):
    def setUp(self):
        base = ReceiptHandoffCLITests()
        base.setUp()
        self.addCleanup(base.doCleanups)
        self.base = base
        self.candidate_path = base.root / "candidate.json"
        self.handoff = {
            "status": "HOLD",
            "next_owner": "FORGE",
            "next_action_code": "READ_DURABLE_LEDGER",
            "evidence_ids": ["receipt-FORGE", "receipt-SENTINEL"],
            "verified_state": "STAGED",
        }
        self.candidate_path.write_text(json.dumps(self.handoff), encoding="utf-8")

    def invoke(self, receipt_paths=None):
        selected = self.base.paths if receipt_paths is None else receipt_paths
        completed = subprocess.run(
            [
                sys.executable, "-B", "-m", "tools.receipt_bound_handoff_cli",
                "--directive", str(self.base.directive), "--as-of", "30",
                "--candidate", str(self.candidate_path), *(str(p) for p in selected),
            ],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(completed.stderr, "")
        return completed.returncode, json.loads(completed.stdout)

    def test_exact_handoff_routes_to_human_review(self):
        self.assertEqual(self.invoke(), (0, {
            "disposition": "ELIGIBLE_FOR_REVIEW", "reason": None,
            "handoff": self.handoff, "defects": [],
        }))

    def test_model_cannot_change_authoritative_owner_or_claim_execution(self):
        self.candidate_path.write_text(
            json.dumps({**self.handoff, "next_owner": "NICKY", "executed": True}),
            encoding="utf-8",
        )
        self.assertEqual(self.invoke(), (2, {
            "disposition": "HOLD", "reason": "candidate_mismatch",
            "handoff": self.handoff, "defects": ["next_owner", "unexpected_candidate_fields"],
        }))

    def test_no_candidate_file_access_before_receipt_qualification(self):
        self.candidate_path = self.base.root / "not-present.json"
        self.assertEqual(self.invoke(receipt_paths=[]), (2, {
            "disposition": "HOLD", "reason": "missing_receipt",
            "handoff": None, "defects": ["unverified_receipts"],
        }))

    def test_unreadable_and_malformed_candidates(self):
        for raw in (b"[]", b"\xff", b'{"status":"HOLD","status":"PROCEED"}',
                    b'{"extra":{"nested":1,"nested":2}}'):
            with self.subTest(raw=raw):
                self.candidate_path.write_bytes(raw)
                self.assertEqual(self.invoke(), (2, {
                    "disposition": "HOLD", "reason": "invalid_candidate_document",
                    "handoff": self.handoff, "defects": ["malformed_candidate"],
                }))
        self.candidate_path = self.base.root / "not-present.json"
        self.assertEqual(self.invoke(), (2, {
            "disposition": "HOLD", "reason": "unreadable_candidate",
            "handoff": self.handoff, "defects": ["unreadable_candidate"],
        }))
