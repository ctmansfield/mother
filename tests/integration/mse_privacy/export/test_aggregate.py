"""Independent edge checks for the projection transform."""
from datetime import datetime, timedelta, timezone
import unittest

from integrations.mse_privacy.export import _aggregate


def observation(channel, unit, epistemic_type, value):
    return {"source_revision": {"observation": {
        "event_start": "2001-01-01T00:15:00Z",
        "event_end": "2001-01-01T00:20:00Z",
        "channel": channel,
        "unit": unit,
        "epistemic_type": epistemic_type,
        "value": value,
    }}}


class AggregateTests(unittest.TestCase):
    def test_measured_hr_and_sdnn_are_distinct_and_missing_is_unknown(self):
        start = datetime(2001, 1, 1, tzinfo=timezone.utc)
        end = start + timedelta(hours=24)
        hr = [observation("heart_rate", "bpm", "measured", "62.25")] * 3
        sdnn = [observation("hrv_sdnn", "ms", "vendor_derived", "41.05")] * 3
        rows, losses = _aggregate({"observations": hr + sdnn, "losses": []}, start, end)
        self.assertEqual(rows, [
            {"bucket_index": 0, "channel": "heart_rate", "unit": "bpm", "mean_value": "62.2"},
            {"bucket_index": 0, "channel": "hrv_sdnn", "unit": "ms", "mean_value": "41.0"},
        ])
        self.assertIn("coverage_unknown", losses)
        rows, losses = _aggregate({"observations": [], "losses": []}, start, end)
        self.assertEqual((rows, losses), ([], ["coverage_unknown"]))

    def test_sparse_nonpositive_and_tiny_rounded_groups_are_withheld(self):
        start = datetime(2001, 1, 1, tzinfo=timezone.utc)
        hr = [observation("heart_rate", "bpm", "measured", "60")] * 2
        sdnn = [observation("hrv_sdnn", "ms", "vendor_derived", "0.04")] * 3
        excluded = [observation("hrv_sdnn", "ms", "vendor_derived", "-0.5"),
                    observation("hrv_sdnn", "ms", "vendor_derived", "0")]
        result = _aggregate({"observations": hr + sdnn + excluded, "losses": []},
                            start, start + timedelta(hours=24))
        self.assertEqual(result, ([], ["coverage_unknown", "some_inputs_excluded",
                                      "some_outputs_suppressed"]))
