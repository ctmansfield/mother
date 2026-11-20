"""Local synthetic tests for the captured archive boundary."""
import hashlib
import json
import unittest

from integrations.healthbridge.capture import CaptureError, CaptureLimits, parse_capture
from integrations.healthbridge.export import canonical_json, export_sha256, normalize_capture

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
             "batch_id": "test-batch", "capture_kind": "partial", "capture_id": "capture-1"}
    return normalize_capture(raw, **(scope | changes))


class CaptureTests(unittest.TestCase):
    def test_capture_identity_and_exchange_are_deterministic(self):
        raw = capture([reading()], extension={"ignored": True})
        output = normalize(raw)
        self.assertEqual(output, normalize(raw))
        self.assertEqual(output["artifact"]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(output["artifact"]["byte_length"], len(raw))
        self.assertEqual(output["coverage"]["backfill_start"],
                         "2000-12-31T23:59:59.000000Z")
        self.assertEqual(output["coverage"]["permissions"], "unknown")
        self.assertEqual(output["anchor_sha256"]["Heart rate"],
                         hashlib.sha256(bytes([1, 2])).hexdigest())
        self.assertIn("Synthetic Δ".encode(), canonical_json(output))
        self.assertIn({"field": "source_extension", "reason": "retained_in_original_only",
                       "locator": "/extension"}, output["losses"])
        changed_whitespace = normalize(raw + b"\n")
        self.assertNotEqual(output["artifact"]["sha256"], changed_whitespace["artifact"]["sha256"])
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
                          if loss["reason"] == "microsecond_rounding"},
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
        self.assertEqual(facts[0]["original_deleted_at"], ["2", "2.0"])
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

    def test_repeated_sighting_uses_numeric_index_and_whole_payload(self):
        rows = [
            reading(f"a0000000-0000-4000-8000-{index + 10:012d}")
            for index in range(11)
        ]
        rows[2] = reading(value=70, receivedAt=8)
        rows[10] = reading(value=70.0, receivedAt=2)
        output = normalize(capture(rows))
        fact = next(row for row in output["revisions"] if row["native_id"] == HR)
        self.assertEqual(fact["locators"], ["/readings/10", "/readings/2"])
        self.assertEqual(fact["observation"]["original_value"], "70")
        self.assertEqual(fact["observation"]["original_received_at"], "8")
        self.assertIn(
            {"field": "source_sighting", "locator": "/readings/10",
             "reason": "alternate_sighting_retained_in_original"}, output["losses"],
        )
        rows[2], rows[10] = rows[10], rows[2]
        swapped = next(row for row in normalize(capture(rows))["revisions"]
                       if row["native_id"] == HR)
        self.assertEqual(swapped["revision_sha256"], fact["revision_sha256"])
        self.assertEqual(swapped["observation"]["original_value"], "70.0")
        self.assertEqual(swapped["observation"]["original_received_at"], "2")

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

    def test_atlas_02_golden_export_and_source_revisions(self):
        # Source vector and expected digests from #28 at 928a60b.
        raw = (
            '{"readings":[{"id":"00000000-0000-4000-8000-000000000001",'
            '"kind":"HRV (SDNN)","value":4.20e1,"unit":"ms","start":0.0000005,'
            '"end":1,"source":"Synthetic µ","bundleID":"test.synthetic",'
            '"receivedAt":2}],"anchors":{"HRV (SDNN)":"AQI="},'
            '"tombstones":{"00000000-0000-4000-8000-000000000002":3},'
            '"backfillStart":0}'
        ).encode()
        options = dict(subject_id="synthetic-atlas", source_instance="fixture-store",
                       batch_id="batch-1", capture_kind="full_file",
                       capture_id="capture-1", exporter_version="fixture-1")
        output = normalize_capture(raw, **options)
        self.assertEqual(export_sha256(output),
                         "54bc62e4c8e16e47a7ba114dfd27ada7fa8bfddb165500a6a663626b3daab6a4")
        upsert, delete = output["revisions"]
        self.assertEqual(upsert["revision_sha256"],
                         "422024522216229dfd02903cc548d549759829c4b4b3f328006c908b214fef6f")
        self.assertEqual(delete["revision_sha256"],
                         "1a0e130c30b61c22ddf510bc2aac9d87e15b17440b9ca2c8df41d4ff5e53cb82")
        drifted = raw.replace(b"4.20e1", b"42.0").replace(b'"receivedAt":2', b'"receivedAt":9')
        drifted_output = normalize_capture(drifted, **options)
        self.assertEqual(drifted_output["revisions"][0]["revision_sha256"],
                         upsert["revision_sha256"])
        self.assertNotEqual(export_sha256(drifted_output), export_sha256(output))

    def test_unknown_anchor_is_reported_and_left_in_original(self):
        raw = capture(anchors={"synthetic/custom": "AQI="})
        output = normalize(raw)
        self.assertEqual(output["anchor_sha256"], {})
        self.assertIn(
            {"field": "anchor_sha256", "reason": "unmapped_anchor_retained_in_original",
             "locator": "/anchors/synthetic~1custom"}, output["losses"],
        )
        self.assertEqual(output["artifact"]["sha256"], hashlib.sha256(raw).hexdigest())
        with self.assertRaises(CaptureError):
            normalize(capture(anchors={"heartRate": "AQI=", "Heart rate": "AQI="}))

    def test_limits_reject_entire_capture(self):
        raw = capture([reading()], {UNKNOWN: 4}, extension={"string": "[{]"})
        for limits in (
            CaptureLimits(byte_length=len(raw) - 1),
            CaptureLimits(records=1),
            CaptureLimits(depth=2),
            CaptureLimits(numeric_token_length=1),
        ):
            with self.subTest(limits=limits), self.assertRaises(CaptureError):
                parse_capture(raw, limits=limits)
        parse_capture(raw, limits=CaptureLimits(byte_length=len(raw), records=2, depth=3))

    def test_zero_stays_canonical_but_outside_reference_domain(self):
        raw = capture([reading()]).replace(b'"value": 70', b'"value": -0.00')
        output = normalize(raw)
        observation = output["revisions"][0]["observation"]
        self.assertEqual((observation["original_value"], observation["value"]), ("-0.00", "0"))
        self.assertIn({"field": "value", "reason": "outside_reference_positive_domain",
                       "locator": "/readings/0/value"}, output["losses"])

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
