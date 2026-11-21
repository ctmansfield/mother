from dataclasses import replace
import hashlib
import json
import unittest

from tools.receipt_bound_handoff import (
    Directive,
    HandoffRule,
    ReceiptPin,
    check_candidate,
    derive_handoff,
)

ARTIFACT = "a" * 64


def receipt(issuer, **changes):
    return {
        "issuer": issuer,
        "receipt_id": "receipt-" + issuer,
        "task_id": "task",
        "revision": "r1",
        "artifact_sha256": ARTIFACT,
        "observed_at": 20,
        "expires_at": 80,
        "verified_state": "PENDING",
        **changes,
    }


def encode(obj):
    return json.dumps(obj).encode()


class ReceiptBoundHandoffTests(unittest.TestCase):
    def setUp(self):
        self.records = [receipt("FORGE"), receipt("SENTINEL")]
        self.raw = [encode(obj) for obj in self.records]
        self.directive = Directive(
            "task",
            "r1",
            ARTIFACT,
            10,
            90,
            self.pins(self.records, self.raw),
            {"PENDING": HandoffRule("HOLD", "FORGE", "READ_LEDGER")},
        )

    @staticmethod
    def pins(records, raw):
        return tuple(
            ReceiptPin(
                obj["issuer"], obj["receipt_id"], hashlib.sha256(data).hexdigest()
            )
            for obj, data in zip(records, raw)
        )

    def assert_hold(self, reason, *, directive=None, raw=None, as_of=30):
        result = derive_handoff(
            self.directive if directive is None else directive,
            self.raw if raw is None else raw,
            as_of=as_of,
        )
        self.assertEqual(
            (result.disposition, result.reason, result.handoff), ("HOLD", reason, None)
        )

    def test_matching_receipts_produce_advisory_handoff_in_directive_order(self):
        result = derive_handoff(self.directive, reversed(self.raw), as_of=20)
        self.assertEqual(result.disposition, "ELIGIBLE_FOR_REVIEW")
        self.assertEqual(result.handoff.status, "HOLD")
        self.assertEqual(result.handoff.next_owner, "FORGE")
        self.assertEqual(result.handoff.next_action_code, "READ_LEDGER")
        self.assertEqual(
            result.handoff.evidence_ids, ("receipt-FORGE", "receipt-SENTINEL")
        )

    def test_receipt_set_must_be_complete_and_unique(self):
        self.assert_hold("missing_receipt", raw=self.raw[:1])
        self.assert_hold("duplicate_issuer", raw=[*self.raw, self.raw[0]])
        self.assert_hold("unexpected_issuer", raw=[*self.raw, encode(receipt("ATLAS"))])

    def test_pins_bind_exact_bytes_and_no_duplicate_json_keys(self):
        self.assert_hold(
            "receipt_digest_mismatch", raw=[self.raw[0] + b" ", self.raw[1]]
        )
        broken = b'{"issuer":"ATLAS","issuer":"FORGE",' + self.raw[0][1:]
        raw = [broken, self.raw[1]]
        self.assert_hold(
            "malformed_receipt",
            raw=raw,
            directive=replace(self.directive, pins=self.pins(self.records, raw)),
        )

    def test_fully_pinned_wrong_artifact_or_revision_is_held(self):
        for changes in (
            {"artifact_sha256": "b" * 64},
            {"revision": "r0"},
            {"task_id": "old-task"},
        ):
            with self.subTest(changes=changes):
                records = [self.records[0], receipt("SENTINEL", **changes)]
                raw = [encode(row) for row in records]
                self.assert_hold(
                    "receipt_binding_mismatch",
                    raw=raw,
                    directive=replace(self.directive, pins=self.pins(records, raw)),
                )

    def test_pinned_receipts_disagree_on_state(self):
        records = [self.records[0], receipt("SENTINEL", verified_state="COMMITTED")]
        raw = [encode(obj) for obj in records]
        self.assert_hold(
            "conflicting_states",
            raw=raw,
            directive=replace(self.directive, pins=self.pins(records, raw)),
        )

    def test_receipt_and_directive_windows_are_half_open(self):
        for moment in (19, 80):
            self.assert_hold("receipt_not_current", as_of=moment)
        for moment in (9, 90):
            self.assert_hold("directive_not_current", as_of=moment)
        self.assert_hold("invalid_as_of", as_of=True)

    def test_no_implicit_rule_or_duplicate_pin(self):
        self.assert_hold(
            "missing_or_invalid_state_rule",
            directive=replace(self.directive, state_rules={}),
        )
        self.assert_hold(
            "invalid_directive",
            directive=replace(self.directive, pins=(self.directive.pins[0],) * 2),
        )

    def test_candidate_cannot_override_routing_or_claim_execution(self):
        derived = derive_handoff(self.directive, self.raw, as_of=30)
        candidate = {
            "status": "HOLD",
            "next_owner": "FORGE",
            "evidence_ids": ["receipt-FORGE", "receipt-SENTINEL"],
            "verified_state": "PENDING",
            "next_action_code": "READ_LEDGER",
        }
        self.assertEqual(
            check_candidate(derived, candidate).disposition, "ELIGIBLE_FOR_REVIEW"
        )
        wrong = check_candidate(
            derived, {**candidate, "next_owner": "NICKY", "executed": True}
        )
        self.assertEqual(wrong.disposition, "HOLD")
        self.assertEqual(wrong.defects, ("next_owner", "unexpected_candidate_fields"))
        self.assertEqual(wrong.verified_handoff, derived.handoff)

        missing = derive_handoff(self.directive, self.raw[:1], as_of=30)
        self.assertEqual(
            check_candidate(missing, candidate).defects, ("unverified_receipts",)
        )
