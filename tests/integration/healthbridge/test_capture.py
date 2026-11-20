"""Local synthetic tests for the captured archive boundary."""
import hashlib
import json
import unittest

from integrations.healthbridge.capture import CaptureError, parse_capture
from integrations.healthbridge.export import canonical_json, normalize_capture

HR = "a0000000-0000-4000-8000-000000000001"
SDNN = "a0000000-0000-4000-8000-000000000002"
UNKNOWN = "a0000000-0000-4000-8000-000000000003"


def reading(native=HR, **changes):
    result = {
        "id": native.upper(), "kind": "Heart rate", "value": 70, "unit": "bpm",
        "start": 0, "end": 0, "source": "Synthetic Δ", "bundleID": "test.invalid",
        "receivedAt": 1,
    }
    return dict(result, **changes)


def capture(readings=None, tombstones=None, **changes):
    envelope = {
        "readings": readings if readings is not None else [],
        "anchors": {"heartRate": "AQI="},
        "tombstones": tombstones if tombstones is not None else {},
        "backfillStart": -1,
    }
    return json.dumps(dict(envelope, **changes), ensure_ascii=False).encode()


def normalize(raw, **changes):
    scope = {"subject_id": "synthetic-a", "source_instance": "test-store",
             "batch_id": "test-batch", "capture_kind": "partial"}
    return normalize_capture(raw, **(scope | changes))


class CaptureTests(unittest.TestCase):
    def test_capture_identity_and_exchange_are_deterministic(self):
        raw = capture([reading()], extension={"ignored": True})
        output = normalize(raw)
        self.assertEqual(output, normalize(raw))
        self.assertEqual(output["capture_id"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(output["artifact"]["byte_length"], len(raw))
        self.assertEqual(output["coverage"]["backfill_start"],
                         "2000-12-31T23:59:59.000000Z")
        self.assertEqual(output["coverage"]["permissions"], "unknown")
        self.assertEqual(output["anchor_sha256"]["heartRate"],
                         hashlib.sha256(bytes([1, 2])).hexdigest())
        self.assertIn("Synthetic Δ".encode(), canonical_json(output))
        self.assertIn({"field": "source_extension", "reason": "retained_in_original_only",
                       "locator": "/extension"}, output["losses"])
        changed_whitespace = normalize(raw + b"\n")
        self.assertNotEqual(output["capture_id"], changed_whitespace["capture_id"])
        self.assertEqual(output["revisions"], changed_whitespace["revisions"])

    def test_swift_epoch_precision_and_original_numeric_lexeme(self):
        raw = capture([reading(start=11, end=12, receivedAt=13)])
        raw = raw.replace(b'"value": 70', b'"value": 7.0000e1')
        raw = raw.replace(b'"start": 11', b'"start": -0.0000015')
        raw = raw.replace(b'"end": 12', b'"end": 0.0000005')
        raw = raw.replace(b'"receivedAt": 13', b'"receivedAt": 0.0000015')
        output = normalize(raw)
        item = output["revisions"][0]["observation"]
        self.assertEqual((item["original_value"], item["value"]), ("7.0000e1", "70"))
        self.assertEqual(item["event_start"], "2000-12-31T23:59:59.999998Z")
        self.assertEqual(item["event_end"], "2001-01-01T00:00:00.000000Z")
        self.assertEqual(item["collector_received_at"], "2001-01-01T00:00:00.000002Z")
        self.assertEqual(item["epistemic_type"], "unknown")
        self.assertIsNone(item["device_id"])
        self.assertEqual({loss["locator"] for loss in output["losses"]
                          if loss["field"] == "timestamp"},
                         {"/readings/0/start", "/readings/0/end", "/readings/0/receivedAt"})

    def test_sdnn_retains_vendor_derivation(self):
        raw = capture([reading(SDNN, kind="HRV (SDNN)", unit="ms", value=22.5)])
        item = normalize(raw)["revisions"][0]["observation"]
        self.assertEqual((item["channel"], item["unit"], item["epistemic_type"]),
                         ("hrv_sdnn", "ms", "vendor_derived"))

    def test_both_delete_facts_and_unknown_uuid_survive(self):
        raw = capture([reading(deletedAt=2)], {HR.upper(): 3, UNKNOWN: 4})
        output = normalize(raw)
        facts = [row for row in output["revisions"] if row["operation"] == "delete"]
        self.assertEqual(len(facts), 3)
        self.assertEqual({row["deleted_at"] for row in facts if row["native_id"] == HR},
                         {"2001-01-01T00:00:02.000000Z", "2001-01-01T00:00:03.000000Z"})
        self.assertEqual(len([row for row in facts if row["native_id"] == UNKNOWN]), 1)
        self.assertEqual(len([row for row in output["revisions"] if row["operation"] == "upsert"]), 1)

    def test_equal_delete_facts_combine_locators(self):
        output = normalize(capture([reading(deletedAt=2.0)], {HR.upper(): 2}))
        facts = [row for row in output["revisions"] if row["operation"] == "delete"]
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["locators"],
                         ["/readings/0/deletedAt", f"/tombstones/{HR.upper()}"])

    def test_distinct_source_times_survive_equal_rounded_dates(self):
        raw = capture([reading(deletedAt=0.0000001)], {HR: 0.0000002})
        facts = [row for row in normalize(raw)["revisions"] if row["operation"] == "delete"]
        self.assertEqual(len({row["deleted_at"] for row in facts}), 1)
        self.assertEqual(len({row["revision_sha256"] for row in facts}), 2)

    def test_empty_partial_capture_infers_no_deletes_and_no_coverage(self):
        output = normalize(capture(anchors={}))
        self.assertEqual(output["revisions"], [])
        self.assertIsNone(output["coverage"]["observed_start"])
        self.assertIsNone(output["coverage"]["observed_end"])
        self.assertEqual(output["coverage"]["completeness"], "unknown")

    def test_identical_upserts_merge_but_unequal_upserts_fail(self):
        output = normalize(capture([reading(), reading()]))
        self.assertEqual(output["revisions"][0]["locators"],
                         ["/readings/0", "/readings/1"])
        with self.assertRaisesRegex(CaptureError, "Ambiguous"):
            normalize(capture([reading(), reading(value=71)]))

    def test_bad_input_fails_without_accepting_a_partial_export(self):
        invalid = [
            b'{"readings":[],"readings":[]}', b"\xff", b'{"x":NaN}',
            capture([reading(unit="ms")]), capture([reading(start=True)]),
            capture([reading(start=0.0000004, end=0.0000003)]),
            capture([reading(receivedAt=1e20)]),
            capture([reading(native="bad-uuid")]), capture(anchors={"heartRate": "!"}),
            capture([reading(value=True)]), capture(tombstones={HR: None}),
        ]
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(CaptureError):
                parse_capture(raw)

    def test_explicit_scope_changes_revision_identity(self):
        raw = capture([reading()])
        left = normalize(raw)
        right = normalize(raw, source_instance="other")
        self.assertEqual(left["artifact"], right["artifact"])
        self.assertNotEqual(left["revisions"][0]["revision_sha256"],
                            right["revisions"][0]["revision_sha256"])
        for kwargs in ({"capture_kind": "auto"}, {"subject_id": ""}, {"batch_id": "a/b"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(CaptureError):
                normalize(raw, **kwargs)
