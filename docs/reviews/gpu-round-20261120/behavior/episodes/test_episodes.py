import tempfile
from pathlib import Path
import unittest
from episodes import (
    append,
    verify_records,
    episode_view,
    validate_event,
)


def event(
    kind, eid, time, data, refs=(), ep="ep-a", actor="v1", observed=None, available=None
):
    return {
        "event_id": eid,
        "episode_id": ep,
        "kind": kind,
        "observed_at": time if observed is None else observed,
        "available_at": time if available is None else available,
        "recorded_at": time,
        "actor_version": actor,
        "references": list(refs),
        "data": data,
    }


class EpisodeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name) / "episodes.jsonl"

    def add(self, *args, **kwargs):
        return append(self.file, event(*args, **kwargs))

    def rows(self):
        return verify_records(self.file.read_bytes())

    def test_acknowledgment_not_action(self):
        self.add("RECOMMENDATION", "offer", 1, {"offer": "fictional walking trial"})
        self.add("ACKNOWLEDGMENT", "ack", 2, {"acknowledged": True}, ["offer"])
        view = episode_view(self.rows(), "ep-a")
        self.assertTrue(view["acknowledged"])
        self.assertFalse(view["acted"])
        self.assertEqual(view["changes"]["PHYSIOLOGY_MEASURE"], {})

    def test_behavior_up_physiology_unchanged(self):
        self.add("RECOMMENDATION", "offer", 1, {"offer": "trial"})
        self.add("ACTION", "walk", 2, {"completed": True}, ["offer"])
        self.add(
            "BEHAVIOR_MEASURE",
            "b0",
            3,
            {"metric": "performance", "value": 8, "phase": "before"},
        )
        self.add(
            "BEHAVIOR_MEASURE",
            "b1",
            4,
            {"metric": "performance", "value": 10, "phase": "after"},
        )
        self.add(
            "PHYSIOLOGY_MEASURE",
            "p0",
            5,
            {"metric": "pulse", "value": 70, "phase": "before"},
        )
        self.add(
            "PHYSIOLOGY_MEASURE",
            "p1",
            6,
            {"metric": "pulse", "value": 70, "phase": "after"},
        )
        view = episode_view(self.rows(), "ep-a")
        self.assertEqual(view["changes"]["BEHAVIOR_MEASURE"]["performance"], 2)
        self.assertEqual(view["changes"]["PHYSIOLOGY_MEASURE"]["pulse"], 0)
        self.assertEqual(view["causality"], "NOT_ESTABLISHED")

    def test_physiology_changed_without_behavior(self):
        self.add(
            "BEHAVIOR_MEASURE",
            "b0",
            1,
            {"metric": "choice", "value": 10, "phase": "before"},
        )
        self.add(
            "BEHAVIOR_MEASURE",
            "b1",
            2,
            {"metric": "choice", "value": 10, "phase": "after"},
        )
        self.add(
            "PHYSIOLOGY_MEASURE",
            "p0",
            3,
            {"metric": "arousal", "value": 5, "phase": "before"},
        )
        self.add(
            "PHYSIOLOGY_MEASURE",
            "p1",
            4,
            {"metric": "arousal", "value": 9, "phase": "after"},
        )
        v = episode_view(self.rows(), "ep-a")
        self.assertFalse(v["acted"])
        self.assertEqual(v["changes"]["BEHAVIOR_MEASURE"]["choice"], 0)
        self.assertEqual(v["changes"]["PHYSIOLOGY_MEASURE"]["arousal"], 4)

    def test_prediction_failure_survives_replacement(self):
        self.add(
            "PREDICTION",
            "pr",
            1,
            {
                "target_kind": "BEHAVIOR_MEASURE",
                "metric": "task",
                "predicted_value": 10,
                "cutoff": 1,
            },
        )
        self.add(
            "BEHAVIOR_MEASURE",
            "obs",
            2,
            {"metric": "task", "value": 4, "phase": "after"},
        )
        self.add(
            "PREDICTION_EVALUATION",
            "ev",
            3,
            {"prediction_id": "pr", "actual_measure_id": "obs", "error": -6},
            ["pr", "obs"],
        )
        self.add(
            "LESSON",
            "lesson",
            4,
            {
                "text": "Prediction failed under this fictional context",
                "status": "UNVERIFIED_EXPERIENCE",
            },
            ["ev"],
        )
        self.add(
            "MODEL_REPLACEMENT",
            "replace",
            5,
            {"predecessor_version": "v1", "successor_version": "v2"},
            actor="v2",
        )
        v = episode_view(self.rows(), "ep-a")
        self.assertEqual(v["unverified_lessons"], ["lesson"])
        self.assertEqual(v["model_replacements"][-1]["successor_version"], "v2")
        self.assertEqual(v["causality"], "NOT_ESTABLISHED")

    def test_forecast_future_data_refused(self):
        self.add(
            "BEHAVIOR_MEASURE",
            "late",
            8,
            {"metric": "task", "value": 4, "phase": "before"},
            observed=3,
            available=8,
        )
        with self.assertRaisesRegex(ValueError, "future/late"):
            self.add(
                "PREDICTION",
                "pr",
                9,
                {
                    "target_kind": "BEHAVIOR_MEASURE",
                    "metric": "task",
                    "predicted_value": 10,
                    "cutoff": 5,
                },
                ["late"],
            )

    def test_wrong_evaluation_metric_refused(self):
        self.add(
            "PREDICTION",
            "pr",
            1,
            {
                "target_kind": "BEHAVIOR_MEASURE",
                "metric": "task",
                "predicted_value": 10,
                "cutoff": 1,
            },
        )
        self.add(
            "PHYSIOLOGY_MEASURE",
            "obs",
            2,
            {"metric": "task", "value": 4, "phase": "after"},
        )
        with self.assertRaisesRegex(ValueError, "channel mismatch"):
            self.add(
                "PREDICTION_EVALUATION",
                "ev",
                3,
                {"prediction_id": "pr", "actual_measure_id": "obs", "error": -6},
                ["pr", "obs"],
            )

    def test_lesson_without_failure_refused(self):
        self.add("RECOMMENDATION", "offer", 1, {"offer": "trial"})
        with self.assertRaisesRegex(ValueError, "prediction-evaluation"):
            self.add(
                "LESSON",
                "lesson",
                2,
                {"text": "proved effective", "status": "UNVERIFIED_EXPERIENCE"},
                ["offer"],
            )

    def test_lesson_never_verified(self):
        with self.assertRaisesRegex(ValueError, "lessons cannot"):
            validate_event(
                event(
                    "LESSON", "lesson-valid-id", 1, {"text": "true", "status": "PROVEN"}
                )
            )

    def test_short_event_identifier_still_refused(self):
        with self.assertRaisesRegex(ValueError, "invalid event_id"):
            validate_event(
                event("LESSON", "l", 1, {"text": "test", "status": "PROVEN"})
            )

    def test_duplicate_event_id_refused(self):
        self.add("RECOMMENDATION", "offer", 1, {"offer": "trial"})
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.add("RECOMMENDATION", "offer", 2, {"offer": "duplicate"})

    def test_cross_episode_reference_refused(self):
        self.add("RECOMMENDATION", "offer", 1, {"offer": "trial"})
        with self.assertRaisesRegex(ValueError, "cross-episode"):
            self.add("ACTION", "action", 2, {"completed": True}, ["offer"], ep="ep-b")

    def test_hash_chain_tamper_refused(self):
        self.add("RECOMMENDATION", "offer", 1, {"offer": "trial"})
        content = self.file.read_text().replace("trial", "tampered")
        self.file.write_text(content)
        with self.assertRaisesRegex(ValueError, "ledger entry altered"):
            self.rows()

    def test_no_model_replacement_skips_version(self):
        with self.assertRaisesRegex(ValueError, "predecessor version"):
            self.add(
                "MODEL_REPLACEMENT",
                "change",
                1,
                {"predecessor_version": "v0", "successor_version": "v2"},
                actor="v2",
            )

    def test_replacement_actor_must_be_successor(self):
        with self.assertRaisesRegex(ValueError, "successor actor"):
            self.add(
                "MODEL_REPLACEMENT",
                "change",
                1,
                {"predecessor_version": "v1", "successor_version": "v2"},
                actor="v1",
            )

    def test_reject_nonfinite_measure(self):
        with self.assertRaises(ValueError):
            self.add(
                "PHYSIOLOGY_MEASURE",
                "bad",
                1,
                {"metric": "pulse", "value": float("nan"), "phase": "after"},
            )

    def test_record_time_does_not_move_backward(self):
        self.add("RECOMMENDATION", "first", 10, {"offer": "first"})
        with self.assertRaisesRegex(ValueError, "append order"):
            self.add("RECOMMENDATION", "second", 9, {"offer": "backdated"})

    def test_retired_model_cannot_write_after_replacement(self):
        self.add(
            "MODEL_REPLACEMENT",
            "replace",
            1,
            {"predecessor_version": "v1", "successor_version": "v2"},
            actor="v2",
        )
        with self.assertRaisesRegex(ValueError, "current specialist version"):
            self.add("RECOMMENDATION", "old-model", 2, {"offer": "incorrect writer"})
        self.add(
            "RECOMMENDATION", "new-model", 3, {"offer": "successor event"}, actor="v2"
        )
        self.assertEqual(len(self.rows()), 2)

    def test_second_replay_same_hash(self):
        self.add("RECOMMENDATION", "offer", 1, {"offer": "trial"})
        original = self.file.read_bytes()
        self.assertEqual(verify_records(original), verify_records(original))


if __name__ == "__main__":
    unittest.main()
