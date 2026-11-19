"""Behavioral orchestration checks using synthetic proof and fake APIs only."""
import contextlib
import fcntl
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import behavior_compare as b
from test_scientific_compare import FakeAPI, idle_gpu


def write(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + "\n")
    path.chmod(0o600)


def scientific_proof(path):
    """Fictional retained evidence for gate tests, never host/GPU evidence."""
    path.mkdir(mode=0o700)
    models = b.scientific.freeze_models(FakeAPI())
    summaries = []
    for index, model in enumerate(models, 1):
        trial = path / f"model-{index:02d}"
        trial.mkdir(mode=0o700)
        raw, telemetry, attempts = [], [], []
        for ordinal in range(1, 16):
            prompt = f"fictional gate test case {ordinal}"
            prompt_sha = b.scientific.sha(prompt.encode())
            request = {"model": model["name"], "prompt": prompt, "options": {"seed": 20261118 + ordinal}}
            raw.append({"model": model["name"], "model_digest": model["digest"], "source_pin": b.scientific.PIN,
                        "case_id": f"synthetic-{ordinal}", "prompt_sha256": prompt_sha, "error_class": None,
                        "response": "{}", "response_sha256": b.scientific.sha(b"{}")})
            intent = {"ordinal": ordinal, "model": model["name"], "digest": model["digest"],
                      "request": request, "prompt_sha256": prompt_sha}
            attempts.append(intent)
            telemetry.append({**intent, "seed": request["options"]["seed"], "http_attempted": True,
                              "hold": None, "error": None, "response": {"model": model["name"], "done": True, "response": "{}"},
                              "gpu_evidence": "GPU_RESIDENT_OBSERVED", "samples": [{"models": [
                                  {"name": model["name"], "digest": model["digest"], "size": 4096, "size_vram": 2048}]}]})
        for target, values in ((trial / "raw-local.jsonl", raw),
                               (path / f"telemetry-{index:02d}.jsonl", telemetry),
                               (path / f"telemetry-{index:02d}.attempts.jsonl", attempts)):
            target.write_text("".join(json.dumps(value, sort_keys=True) + "\n" for value in values))
            target.chmod(0o600)
        summaries.append({**model, "actual_generate_requests": 15, "broker_task_slots": 15,
                          "gpu_evidence_counts": {"GPU_RESIDENT_OBSERVED": 15}, "hold": None,
                          "trial_directory": trial.name, "raw_log_sha256": b.scientific.sha((trial / "raw-local.jsonl").read_bytes())})
    write(path / "comparison.json", {"schema": "fw00412.comparative-reasoning-screen.v1", "source_pin": b.scientific.PIN,
        "status": "COMPLETED_COMPARATIVE_SCREEN_NO_SCIENTIFIC_PROMOTION", "actual_generate_requests": 75,
        "completed_model_batches": 5, "all_75_requests_have_gpu_residency_observed": True,
        "gpu_evidence_counts": {"GPU_RESIDENT_OBSERVED": 75}, "models": summaries})
    write(path / "preflight.json", {"schema": "fw00412.comparison-preflight.v1", "source_pin": b.scientific.PIN,
        "wrapper_sha256": b.scientific.sha((b.SCIENTIFIC / "scientific_compare.py").read_bytes()),
        "candidate_config_sha256": b.scientific.sha((b.SCIENTIFIC / "candidates.json").read_bytes()), "models": models})
    (path / "exit.code").write_text("0\n")
    (path / "exit.code").chmod(0o600)
    return b.check_scientific_predecessor(path)


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.mask = os.umask(0o077)

    def tearDown(self):
        os.umask(self.mask)

    def test_predecessor_requires_complete_status_and_underlying_gpu_proof(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "scientific"
            proof = scientific_proof(path)
            self.assertEqual(proof["validated_gpu_residency_observations"], 75)
            original = json.loads((path / "comparison.json").read_text())
            for changed in ({"status": "HELD_REVIEW_LOCAL_EVIDENCE_NO_AUTOMATIC_RETRY"},
                            {"actual_generate_requests": 74}, {"source_pin": "0" * 40},
                            {"all_75_requests_have_gpu_residency_observed": False}):
                write(path / "comparison.json", {**original, **changed})
                with self.assertRaises(ValueError):
                    b.check_scientific_predecessor(path)
            write(path / "comparison.json", original)
            telemetry_path = path / "telemetry-01.jsonl"
            rows = [json.loads(line) for line in telemetry_path.read_text().splitlines()]
            rows[0]["response"]["response"] = '{"changed":true}'
            telemetry_path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            with self.assertRaisesRegex(ValueError, "raw answer"):
                b.check_scientific_predecessor(path)
            rows[0]["response"]["response"] = "{}"
            rows[0]["samples"][0]["models"][0]["size_vram"] = 0
            telemetry_path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            with self.assertRaisesRegex(ValueError, "positive-VRAM"):
                b.check_scientific_predecessor(path)

    def test_dirty_source_or_changed_installed_digest_refuses_without_inference(self):
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(b.scientific, "command", side_effect=[temp, "a" * 40, " M benchmark.py"]):
                with self.assertRaisesRegex(ValueError, "clean"):
                    b.check_source()
            fake = FakeAPI()
            models = b.scientific.freeze_models(fake)
            models[0]["digest"] = "f" * 64
            with self.assertRaisesRegex(ValueError, "digests differ"):
                b.run_campaign(Path(temp) / "behavior", {"source_pin": "a" * 40}, {"models": models}, fake,
                               nvidia=idle_gpu, lock_path=Path(temp) / "scientific-gpu.lock")
            self.assertEqual(fake.calls, [])
            self.assertFalse((Path(temp) / "behavior").exists())

    def test_120_calls_same_prompts_seeds_and_completed_format_failure_continues(self):
        cases, key, pack_sha = b.adapter.benchmark.load_pack()
        def answer(payload):
            case = cases[payload["options"]["seed"] - 20261120]
            return b.adapter.benchmark.oracle_response(case, key[case["id"]])
        fake = FakeAPI(responder=answer)
        def api(path, payload=None, timeout=10):
            value = fake(path, payload, timeout)
            if path == "/api/generate" and payload["options"]["seed"] == 20261120:
                value["done_reason"] = "length"
            return value
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            state = Path(temp) / "behavior"
            code = b.run_campaign(state, {"source_pin": "a" * 40, "pack_sha256": pack_sha},
                                  {"models": b.scientific.freeze_models(fake)}, api, nvidia=idle_gpu,
                                  poll_seconds=0.001, lock_path=Path(temp) / "scientific-gpu.lock")
            self.assertEqual(code, 0)
            result = json.loads((state / "comparison.json").read_text())
            self.assertEqual(result["actual_generate_requests"], 120)
            self.assertEqual(result["completed_model_batches"], 5)
            self.assertTrue(result["all_120_requests_have_gpu_residency_observed"])
            sequences = []
            for index, model in enumerate(result["models"], 1):
                summary = model["adapter_summary"]
                self.assertEqual(summary["completed_case_slots"], 24)
                self.assertEqual(summary["successful_requests"], 23)
                self.assertEqual(sum(role["structured_correct"] for role in summary["roles"].values()), 23)
                rows = [json.loads(line) for line in (state / f"telemetry-{index:02d}.jsonl").read_text().splitlines()]
                sequences.append([(row["prompt_sha256"], row["seed"]) for row in rows])
            self.assertTrue(all(sequence == sequences[0] for sequence in sequences))
        self.assertEqual(len(fake.calls), 120)

    def test_ambiguous_request_preserves_partial_counts_and_stops(self):
        fake = FakeAPI(failure=TimeoutError("fictional timeout"))
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            state = Path(temp) / "behavior"
            code = b.run_campaign(state, {"source_pin": "a" * 40}, {"models": b.scientific.freeze_models(fake)},
                                  fake, nvidia=idle_gpu, poll_seconds=0.001,
                                  lock_path=Path(temp) / "scientific-gpu.lock")
            result = json.loads((state / "comparison.json").read_text())
            self.assertEqual(code, 4)
            self.assertEqual(result["actual_generate_requests"], 1)
            self.assertEqual(result["completed_model_batches"], 0)
            self.assertEqual(result["models"][0]["adapter_summary"]["cases_recorded"], 1)
            self.assertTrue((state / "telemetry-01.attempts.jsonl").is_file())
        self.assertEqual(len(fake.calls), 1)

    def test_help_and_shared_lease_conflict_issue_no_api_requests(self):
        with mock.patch.object(b.scientific, "local_api", side_effect=AssertionError("no API from help")):
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as exited:
                b.main(["--help"])
            self.assertEqual(exited.exception.code, 0)
        with tempfile.TemporaryDirectory() as temp:
            lock = Path(temp) / "scientific-gpu.lock"
            with lock.open("w") as held:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                api = mock.Mock(side_effect=AssertionError("no API while another campaign owns lock"))
                with self.assertRaises(BlockingIOError):
                    b.run_campaign(Path(temp) / "behavior", {"source_pin": "a" * 40}, {"models": []}, api,
                                   nvidia=idle_gpu, lock_path=lock)
                api.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
