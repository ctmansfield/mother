#!/usr/bin/env python3
"""Focused launcher checks. Fake APIs only: no network, GPU, pulls or posts."""
import importlib
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import scientific_compare as c


class FakeAPI:
    def __init__(self, vram=2048, failure=None, responder=None):
        self.vram, self.failure, self.responder = vram, failure, responder
        self.active = None
        self.calls = []
        self.lock = threading.Lock()

    def __call__(self, path, payload=None, timeout=10):
        if path == "/api/tags":
            return {"models": [{"name": tag, "digest": str(index + 1) * 64} for index, tag in enumerate(c.TAGS)]}
        if path == "/api/ps":
            with self.lock:
                model = self.active
            if model is None:
                return {"models": []}
            row = {"name": model, "digest": str(c.TAGS.index(model) + 1) * 64, "size": 4096}
            if self.vram is not None:
                row["size_vram"] = self.vram
            return {"models": [row]}
        if path != "/api/generate":
            raise AssertionError("unexpected endpoint")
        with self.lock:
            self.active = payload["model"]
        self.calls.append(payload)
        time.sleep(0.012)
        with self.lock:
            self.active = None
        if self.failure:
            raise self.failure
        return {"model": payload["model"], "response": self.responder(payload) if self.responder else "{}", "done": True, "done_reason": "stop"}


def idle_gpu():
    return {"gpus": [{"uuid": "test-gpu"}], "compute_processes": []}


def request(model=c.TAGS[0], prompt="synthetic prompt", seed=20261119):
    return {"model": model, "prompt": prompt, "stream": False, "format": "json",
            "options": {"temperature": 0, "seed": seed, "num_ctx": 4096, "num_predict": 520}, "keep_alive": "0s"}


class LauncherTests(unittest.TestCase):
    def test_loopback_transport_disables_proxy_and_rejects_redirects(self):
        response = mock.MagicMock()
        response.status = 200
        response.read.return_value = b'{"models":[]}'
        response.__enter__.return_value = response
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(c.urllib.request, "build_opener", return_value=opener) as factory:
            api = c.local_api()
            self.assertEqual(api("/api/ps"), {"models": []})
            handlers = factory.call_args.args
            self.assertEqual(handlers[0].proxies, {})
            self.assertIsInstance(handlers[1], c.RejectRedirect)
            request_sent = opener.open.call_args.args[0]
            self.assertEqual(request_sent.full_url, "http://127.0.0.1:11434/api/ps")
            with self.assertRaisesRegex(ValueError, "redirects"):
                handlers[1].redirect_request(None, None, 302, "Found", {}, "https://example.invalid/")
            before = opener.open.call_count
            with self.assertRaises(ValueError):
                api("http://example.invalid/api/ps")
            with self.assertRaises(ValueError):
                api("/api/pull", {"model": "unrequested"})
            self.assertEqual(opener.open.call_count, before)

    def test_loopback_response_budget_and_duplicate_keys_rejected(self):
        response = mock.MagicMock()
        response.status = 200
        response.__enter__.return_value = response
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(c.urllib.request, "build_opener", return_value=opener):
            api = c.local_api()
            for data in (b" " * 180001, b'{"models":[],"models":[1]}'):
                response.read.return_value = data
                with self.assertRaises(ValueError):
                    api("/api/ps")

    def test_config_exact_order_and_all_candidates(self):
        path = Path(__file__).with_name("candidates.json")
        self.assertEqual(c.load_candidates(path)["models"], list(c.TAGS))
        with tempfile.TemporaryDirectory() as temp:
            changed = json.loads(path.read_text())
            changed["models"].pop()
            out = Path(temp) / "changed.json"
            out.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, "five-candidate"):
                c.load_candidates(out)

    def test_missing_candidate_refused_without_generate(self):
        fake = FakeAPI()
        def api(path, *args, **kwargs):
            value = fake(path, *args, **kwargs)
            if path == "/api/tags":
                value["models"].pop()
            return value
        with self.assertRaisesRegex(ValueError, "missing installed"):
            c.freeze_models(api)
        self.assertEqual(fake.calls, [])

    def test_invalid_or_duplicate_full_digest_refused(self):
        for rows in ([{"name": c.TAGS[0], "digest": "abc"}],
                     [{"name": c.TAGS[0], "digest": "1" * 64}] * 2):
            with self.assertRaises(ValueError):
                c.freeze_models(lambda *args, **kwargs: {"models": rows})

    def test_gpu_evidence_requires_identity_and_valid_numeric_value(self):
        def sample(**extra):
            return [{"models": [{"name": c.TAGS[0], "digest": "1" * 64, **extra}]}]
        self.assertEqual(c.classify(sample(size_vram=1), c.TAGS[0], "1" * 64), "GPU_RESIDENT_OBSERVED")
        self.assertEqual(c.classify(sample(size_vram=0), c.TAGS[0], "1" * 64), "CPU_RESIDENT_OBSERVED")
        for value in (None, True, "0", -1):
            self.assertEqual(c.classify(sample(size_vram=value), c.TAGS[0], "1" * 64), "UNOBSERVED")
        self.assertEqual(c.classify(sample(size_vram=1), c.TAGS[0], "2" * 64), "UNOBSERVED")

    def test_gpu_observation_and_raw_response_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "telemetry.jsonl"
            fake = FakeAPI()
            observer = c.ObservedAPI(fake, c.TAGS[0], "1" * 64, path, idle_gpu, 0.001)
            response = observer("/api/generate", request(), timeout=1)
            self.assertEqual(response["model"], c.TAGS[0])
            evidence = json.loads(path.read_text())
            self.assertEqual(evidence["gpu_evidence"], "GPU_RESIDENT_OBSERVED")
            self.assertEqual(evidence["response"], response)
            self.assertEqual(evidence["samples"][0]["models"][0]["size_vram"], 2048)
            self.assertTrue(path.with_suffix(".attempts.jsonl").exists())
            self.assertEqual(observer.hold, None)

    def test_cpu_and_missing_samples_classified_without_skipping_following_cases(self):
        for value, expected in ((0, "CPU_RESIDENT_OBSERVED"), (None, "UNOBSERVED")):
            with tempfile.TemporaryDirectory() as temp:
                observer = c.ObservedAPI(FakeAPI(value), c.TAGS[0], "1" * 64, Path(temp) / "telemetry.jsonl", idle_gpu, 0.001)
                observer("/api/generate", request(), timeout=1)
                observer("/api/generate", request(seed=20261120), timeout=1)
                self.assertEqual(len(observer.records), 2)
                self.assertEqual(observer.records[0]["gpu_evidence"], expected)
                self.assertIsNone(observer.hold)

    def test_ambiguous_http_failure_blocks_further_network_attempts(self):
        with tempfile.TemporaryDirectory() as temp:
            fake = FakeAPI(failure=TimeoutError("timeout"))
            observer = c.ObservedAPI(fake, c.TAGS[0], "1" * 64, Path(temp) / "telemetry.jsonl", idle_gpu, 0.001)
            for unused in range(2):
                with self.assertRaises(ValueError):
                    observer("/api/generate", request(), timeout=1)
            self.assertEqual(len(fake.calls), 1)
            self.assertEqual(len(observer.records), 1)
            self.assertIn("ambiguous", observer.hold)

    def test_gpu_runner_identity_and_unattributed_fail_closed(self):
        def proc(name, pid="3791544", uuid="test-gpu"):
            return {"process_name": name, "pid": pid, "gpu_uuid": uuid}
        known = proc("/usr/local/lib/ollama/llama-server")
        self.assertFalse(c.unattributed_processes([known]))
        self.assertFalse(c.unattributed_processes([proc("/usr/bin/ollama")]))
        self.assertTrue(c.unattributed_processes([proc("[No data]")]))
        self.assertTrue(c.unattributed_processes([proc("python")]))
        self.assertTrue(c.unattributed_processes([proc("/tmp/ollama-malicious")]))
        self.assertTrue(c.unattributed_processes([known, proc("python", "999")]))
        self.assertTrue(c.unattributed_processes([known, proc("[No data]", "999")]))

    def test_nvidia_record_marks_http_boundary(self):
        # Deterministic seam: snapshot completes after the generator's HTTP
        # event is set; raw sample must record the boundary explicitly.
        with tempfile.TemporaryDirectory() as temp:
            fake = FakeAPI()
            sampled = threading.Event()
            def gpu():
                if fake.active:
                    time.sleep(0.025)
                    sampled.set()
                    return {"gpus": [], "compute_processes": []}
                return idle_gpu()
            observer = c.ObservedAPI(fake, c.TAGS[0], "1" * 64,
                                    Path(temp) / "telemetry.jsonl", gpu, 0.001)
            observer("/api/generate", request(), timeout=1)
            self.assertTrue(sampled.is_set())
            self.assertTrue(any(s["http_completed_at_sample_end"]
                                for s in observer.records[0]["nvidia_samples"]))

    def test_foreign_gpu_process_refuses_before_generate(self):
        with tempfile.TemporaryDirectory() as temp:
            fake = FakeAPI()
            def busy():
                return {"gpus": [], "compute_processes": [{"process_name": "python", "pid": "23"}]}
            observer = c.ObservedAPI(fake, c.TAGS[0], "1" * 64, Path(temp) / "telemetry.jsonl", busy)
            with self.assertRaises(ValueError):
                observer("/api/generate", request(), timeout=1)
            self.assertEqual(fake.calls, [])

    def test_foreign_gpu_process_during_request_holds_future_requests(self):
        with tempfile.TemporaryDirectory() as temp:
            fake = FakeAPI()
            def gpu():
                return {"gpus": [], "compute_processes": [{"process_name": "python", "pid": "23"}] if fake.active else []}
            observer = c.ObservedAPI(fake, c.TAGS[0], "1" * 64, Path(temp) / "telemetry.jsonl", gpu, 0.001)
            observer("/api/generate", request(), timeout=1)
            with self.assertRaisesRegex(ValueError, "held"):
                observer("/api/generate", request(), timeout=1)
            self.assertEqual(len(fake.calls), 1)

    def test_expired_campaign_refuses_without_generate(self):
        with tempfile.TemporaryDirectory() as temp:
            fake = FakeAPI()
            observer = c.ObservedAPI(fake, c.TAGS[0], "1" * 64, Path(temp) / "telemetry.jsonl", idle_gpu,
                                     deadline=time.monotonic() - 1)
            with self.assertRaisesRegex(ValueError, "budget"):
                observer("/api/generate", request(), timeout=1)
            self.assertEqual(fake.calls, [])

    def test_incomplete_response_is_preserved_and_holds_following_requests(self):
        with tempfile.TemporaryDirectory() as temp:
            fake = FakeAPI()
            def incomplete(path, *args, **kwargs):
                value = fake(path, *args, **kwargs)
                if path == "/api/generate":
                    value["done"] = False
                return value
            path = Path(temp) / "telemetry.jsonl"
            observer = c.ObservedAPI(incomplete, c.TAGS[0], "1" * 64, path, idle_gpu, 0.001)
            for unused in range(2):
                with self.assertRaises(ValueError):
                    observer("/api/generate", request(), timeout=1)
            self.assertEqual(len(fake.calls), 1)
            self.assertFalse(json.loads(path.read_text())["response"]["done"])

    def test_two_ollama_gpu_processes_are_not_assumed_to_be_ours(self):
        processes = [{"pid": "1", "process_name": "/bin/ollama"},
                     {"pid": "2", "process_name": "/bin/ollama_llama_server"}]
        self.assertTrue(c.unattributed_processes(processes))
        self.assertFalse(c.unattributed_processes(processes[:1]))

    def test_partial_batch_accounted_when_broker_raises_after_request(self):
        checkout = os.environ.get("FW00412_TEST_CHECKOUT")
        if not checkout:
            self.skipTest("requires reviewed broker source for integration check")
        sys.path.insert(0, str(Path(checkout) / "packages" / "fw00412"))
        broker = importlib.import_module("broker")
        fake = FakeAPI()
        def interrupted_run(state, source_pin, roster, api):
            api("/api/generate", request(), timeout=1)
            raise ValueError("injected post-request interruption")
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "campaign"
            with mock.patch.object(c, "check_source"), mock.patch.object(c, "check_offline", return_value={}), \
                 mock.patch.object(c, "nvidia_snapshot", side_effect=idle_gpu), \
                 mock.patch.object(c.Path, "home", return_value=Path(temp)), \
                 mock.patch.object(c, "local_api", return_value=fake), \
                 mock.patch.object(broker, "run", side_effect=interrupted_run), \
                 mock.patch.object(c, "idle_snapshot", return_value=idle_gpu()), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = c.main(["--checkout", checkout, "--state", str(state), "--live", "--gpu-idle-confirmed"])
            self.assertEqual(result, 4)
            summary = json.loads((state / "comparison.json").read_text())
            self.assertEqual(summary["actual_generate_requests"], 1)
            self.assertEqual(summary["completed_model_batches"], 0)
            self.assertEqual(summary["models"][0]["status"], "INCOMPLETE_REVIEW_RAW_AND_ATTEMPT_LOGS")
            self.assertEqual(len(fake.calls), 1)

    def test_unchanged_broker_same_fifteen_cases_and_seeds_for_all_five_candidates(self):
        checkout = os.environ.get("FW00412_TEST_CHECKOUT")
        if not checkout:
            self.skipTest("set FW00412_TEST_CHECKOUT to reviewed source snapshot for integration check")
        sys.path.insert(0, str(Path(checkout) / "packages" / "fw00412"))
        broker = importlib.import_module("broker")
        tasks = broker.fixtures.cases()
        fake = FakeAPI(responder=lambda payload: broker.s.proposal_for_task(tasks[payload["options"]["seed"] - 20261119]))
        sequences = []
        with tempfile.TemporaryDirectory() as temp:
            for index, model in enumerate(c.freeze_models(fake)):
                state = Path(temp) / str(index)
                state.mkdir(mode=0o700)
                (state / "source-pin.txt").write_text(c.PIN + "\n")
                observer = c.ObservedAPI(fake, model["name"], model["digest"], Path(temp) / f"telemetry-{index}.jsonl", idle_gpu, 0.001)
                summary = broker.run(state, c.PIN, c.roster_for(broker, model), api=observer)
                self.assertEqual(summary["model_requests"], 15)
                self.assertEqual(sum(role["correct"] for role in summary["roles"].values()), 15)
                self.assertEqual(len(observer.records), 15)
                self.assertTrue(all(row["gpu_evidence"] == "GPU_RESIDENT_OBSERVED" for row in observer.records))
                sequences.append([(row["prompt_sha256"], row["seed"]) for row in observer.records])
        self.assertEqual(len(fake.calls), 75)
        self.assertTrue(all(sequence == sequences[0] for sequence in sequences))


if __name__ == "__main__":
    unittest.main(verbosity=2)
