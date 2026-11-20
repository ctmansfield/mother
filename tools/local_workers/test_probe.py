"""Independent synthetic LW001 checks; no installed runtime or model is contacted.

Run with: python -m unittest discover -s tools/local_workers -p test_probe.py -v
"""

from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import probe


MODEL = probe.DEFAULT_MODEL
DIGEST = "a" * 64


def complete_generation():
    return {
        "response": json.dumps(probe.EXPECTED),
        "done": True,
        "done_reason": "stop",
        "eval_count": 12,
        "eval_duration": 2_000_000_000,
        "total_duration": 3_000_000_000,
    }


def complete_tool_call():
    return {
        "done": True,
        "done_reason": "stop",
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "probe_echo",
                        "arguments": {"probe_id": "lw001", "value": 0},
                    }
                }
            ],
        },
    }


class FakeOllama:
    """A controlled HTTP endpoint whose only listener is IPv4 loopback."""

    def __init__(self):
        self.calls = []
        self.responses = {
            "/api/version": {"version": "synthetic-ollama-version"},
            "/api/tags": {"models": [{"name": MODEL, "digest": "sha256:" + DIGEST}]},
            "/api/show": {
                "capabilities": ["completion", "tools"],
                "details": {"family": "synthetic", "quantization_level": "Q4_K_M"},
                "model_info": {
                    "general.architecture": "synthetic",
                    "synthetic.context_length": 8192,
                },
                "template": "synthetic fixture template",
            },
            "/api/ps": {
                "models": [
                    {
                        "name": MODEL,
                        "digest": "sha256:" + DIGEST,
                        "size": 100,
                        "size_vram": 80,
                        "context_length": 4096,
                    }
                ]
            },
            "/api/generate": complete_generation(),
            "/api/chat": complete_tool_call(),
        }
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.respond()

            def do_POST(self):
                self.respond()

            def respond(self):
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length)) if length else None
                fixture.calls.append((self.command, self.path, payload))
                response = fixture.responses.get(
                    self.path, (404, {}, {"error": "Unexpected fixture route"})
                )
                status, headers, body = (
                    response if isinstance(response, tuple) else (200, {}, response)
                )
                encoded = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                for name, value in headers.items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *unused):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.server.server_port)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def routes(self):
        return [route for unused_method, route, unused_payload in self.calls]


class ProbeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.server = FakeOllama()
        self.addCleanup(self.server.close)
        self.client = probe.Client(self.server.url, timeout=10)
        self.gpu = self.enter_patch(
            patch.object(
                probe,
                "gpu_snapshot",
                return_value={"status": "unavailable", "reason": "synthetic fixture"},
            )
        )
        self.child_process = self.enter_patch(
            patch.object(
                probe.subprocess,
                "run",
                side_effect=AssertionError("No subprocess belongs in synthetic probe"),
            )
        )

    def enter_patch(self, patcher):
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def run_probe(self, expected_digest=DIGEST):
        return probe.run_probe(self.client, MODEL, expected_digest)

    def assert_no_inference(self):
        self.assertNotIn("/api/generate", self.server.routes())
        self.assertNotIn("/api/chat", self.server.routes())
        self.assertNotIn("/api/pull", self.server.routes())

    def test_successful_pinned_inventory_generation_and_native_tool_flow(self):
        report = self.run_probe()
        self.assertEqual(report["status"], "smoke_checks_passed")
        self.assertEqual(report["server_version"], "synthetic-ollama-version")
        self.assertEqual(report["model_digest"], "sha256:" + DIGEST)
        self.assertEqual(report["requested_digest_prefix"], DIGEST)
        self.assertEqual(report["model_metadata"]["trained_context_length"], 8192)
        self.assertTrue(report["structured_output"]["passed"])
        self.assertEqual(report["native_tools"]["status"], "call_shape_passed")
        self.assertEqual(
            report["structured_output"]["metrics"]["generated_tokens_per_second"], 6
        )
        self.assertEqual(
            self.server.routes(),
            [
                "/api/version",
                "/api/tags",
                "/api/show",
                "/api/ps",
                "/api/generate",
                "/api/ps",
                "/api/chat",
            ],
        )
        for method, route, payload in self.server.calls:
            if route in ("/api/show", "/api/generate", "/api/chat"):
                self.assertEqual(method, "POST")
                self.assertEqual(payload["model"], MODEL)
            else:
                self.assertEqual(method, "GET")
            if route in ("/api/generate", "/api/chat"):
                self.assertIs(payload["stream"], False)
                self.assertEqual(payload["options"], probe.OPTIONS)
                self.assertEqual(payload["keep_alive"], "2m")
        self.assertEqual(self.server.calls[4][2]["format"], probe.FORMAT)
        self.assertEqual(self.server.calls[-1][2]["tools"], [probe.TOOL])
        self.assertIs(report["repository_work_qualified"], False)
        self.assertIs(report["generated_tools_executed"], False)
        self.assertIs(report["models_pulled"], False)
        self.assertIs(report["personal_data_used"], False)
        self.assertIs(report["native_tools"]["tools_executed"], False)
        self.assertEqual(self.gpu.call_count, 2)
        self.child_process.assert_not_called()

    def test_digest_prefix_accepts_a_matching_installed_digest(self):
        for expected in (DIGEST[:12], DIGEST[:16].upper(), DIGEST.upper()):
            with self.subTest(expected=expected):
                self.assertEqual(
                    self.run_probe(expected)["status"], "smoke_checks_passed"
                )

    def test_model_digest_without_algorithm_prefix_is_accepted(self):
        self.server.responses["/api/tags"]["models"][0]["digest"] = DIGEST
        self.assertEqual(self.run_probe()["status"], "smoke_checks_passed")

    def test_an_omitted_digest_pin_remains_optional(self):
        self.assertEqual(self.run_probe(None)["status"], "smoke_checks_passed")

    def test_digest_mismatch_rejects_before_inference(self):
        report = self.run_probe("b" * 64)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["failure"]["stage"], "model_identity")
        self.assert_no_inference()

    def test_invalid_supplied_digest_pins_reject_before_inventory_or_inference(self):
        for expected in ("", "a" * 11, "a" * 65, "g" * 12, " " + "a" * 12):
            with self.subTest(expected=expected):
                self.server.calls.clear()
                report = self.run_probe(expected)
                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["failure"]["stage"], "model_identity")
                self.assertEqual(self.server.calls, [])
                self.assert_no_inference()

    def test_missing_or_ambiguous_model_rejects_without_pull(self):
        for rows in ([], [{"name": "another-model"}], [{"name": MODEL}] * 2):
            with self.subTest(rows=rows):
                self.server.responses["/api/tags"] = {"models": rows}
                self.server.calls.clear()
                report = self.run_probe()
                self.assertEqual(report["status"], "failed")
                self.assert_no_inference()

    def test_unavailable_model_digest_rejects_a_requested_pin(self):
        for digest in (None, DIGEST[:12], "g" * 64, DIGEST + "extra"):
            with self.subTest(digest=digest):
                self.server.responses["/api/tags"]["models"][0]["digest"] = digest
                self.server.calls.clear()
                report = self.run_probe()
                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["failure"]["stage"], "model_identity")
                self.assert_no_inference()

    def test_unadvertised_and_unknown_tool_capabilities_skip_chat(self):
        for capability, expected in (
            (["completion"], "not_advertised"),
            (None, "unknown"),
        ):
            with self.subTest(capability=capability):
                self.server.responses["/api/show"]["capabilities"] = capability
                self.server.calls.clear()
                report = self.run_probe()
                self.assertEqual(report["status"], "smoke_checks_passed")
                self.assertEqual(report["native_tools"]["status"], expected)
                self.assertNotIn("/api/chat", self.server.routes())

    def test_textual_tool_call_is_a_failed_declared_capability(self):
        self.server.responses["/api/chat"]["message"] = {
            "role": "assistant",
            "content": json.dumps(complete_tool_call()["message"]),
        }
        report = self.run_probe()
        self.assertEqual(report["status"], "checks_failed")
        self.assertIs(report["native_tools"]["advertised"], True)
        self.assertEqual(report["native_tools"]["status"], "call_shape_failed")
        self.child_process.assert_not_called()

    def test_unexpected_generated_function_is_not_executed(self):
        self.server.responses["/api/chat"]["message"]["tool_calls"] = [
            {"function": {"name": "os.system", "arguments": {"command": "fixture"}}}
        ]
        with patch.object(probe.os, "system") as execute:
            report = self.run_probe()
        self.assertEqual(report["status"], "checks_failed")
        execute.assert_not_called()
        self.child_process.assert_not_called()
        self.assertEqual(self.server.routes().count("/api/chat"), 1)
        self.assertNotIn("/api/pull", self.server.routes())

    def test_declared_tool_http_failure_is_reported_as_failure(self):
        self.server.responses["/api/chat"] = (400, {}, {"error": "fixture rejection"})
        report = self.run_probe()
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["failure"]["stage"], "native_tool_call")
        self.assertIs(report["native_tools"]["advertised"], True)
        self.assertEqual(report["placement_after_generation"]["status"], "observed")

    def test_unavailable_residency_is_explicit_and_does_not_invent_gpu_placement(self):
        self.server.responses["/api/ps"] = (503, {}, {"error": "fixture unavailable"})
        report = self.run_probe()
        self.assertEqual(report["status"], "smoke_checks_passed")
        self.assertEqual(report["placement_before"]["status"], "unavailable")
        self.assertEqual(report["placement_after_generation"]["status"], "unavailable")
        self.assertEqual(report["gpu_before"]["status"], "unavailable")
        self.assertEqual(report["gpu_after"]["status"], "unavailable")

    def test_redirects_are_refused_without_contacting_the_target(self):
        target = FakeOllama()
        self.addCleanup(target.close)
        for status in (301, 302, 303, 307, 308):
            with self.subTest(status=status):
                self.server.responses["/api/version"] = (
                    status,
                    {"Location": target.url + "/api/version"},
                    b"",
                )
                with self.assertRaisesRegex(RuntimeError, "HTTP " + str(status)):
                    self.client.call("/api/version")
        self.assertEqual(target.calls, [])

    def test_client_rejects_non_strict_and_truncated_api_json(self):
        for body in (
            b'{"version":"one","version":"two"}',
            b'{"value":NaN}',
            b'{"value":Infinity}',
            b'{"value":1e9999}',
            b'{"version":',
            b"[]",
        ):
            with self.subTest(body=body):
                self.server.responses["/api/version"] = body
                with self.assertRaises(ValueError):
                    self.client.call("/api/version")

    def test_client_rejects_an_oversize_api_response(self):
        self.server.responses["/api/version"] = b" " * (probe.MAX_RESPONSE_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "size bound"):
            self.client.call("/api/version")

    def invoke_main(self, output, *extra):
        console = io.StringIO()
        with redirect_stdout(console):
            code = probe.main(
                [
                    "--url",
                    self.server.url,
                    "--expected-digest-prefix",
                    DIGEST,
                    "--output",
                    str(output),
                    *extra,
                ]
            )
        return code, json.loads(console.getvalue())

    def test_main_writes_a_successful_report_without_overstating_qualification(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            code, console = self.invoke_main(output)
            report = json.loads(output.read_text())
        self.assertEqual(code, 0)
        self.assertEqual(console["status"], "smoke_checks_passed")
        self.assertIs(console["repository_work_qualified"], False)
        self.assertEqual(report["status"], console["status"])

    def test_main_preserves_existing_report_and_performs_no_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            original = b"existing report bytes\x00\n"
            output.write_bytes(original)
            code, console = self.invoke_main(output)
            self.assertEqual(output.read_bytes(), original)
        self.assertEqual(code, 1)
        self.assertEqual(console["status"], "not_started")
        self.assertIs(console["probe_attempted"], False)
        self.assertEqual(self.server.calls, [])
        self.gpu.assert_not_called()

    def test_main_persists_failures_and_returns_nonzero(self):
        for failure in ("model", "structured_output", "declared_tools", "api"):
            with self.subTest(failure=failure):
                self.server.responses["/api/version"] = {"version": "synthetic"}
                self.server.responses["/api/tags"]["models"] = [
                    {"name": MODEL, "digest": "sha256:" + DIGEST}
                ]
                self.server.responses["/api/generate"] = complete_generation()
                self.server.responses["/api/chat"] = complete_tool_call()
                if failure == "model":
                    self.server.responses["/api/tags"]["models"] = []
                elif failure == "structured_output":
                    self.server.responses["/api/generate"]["response"] = "{}"
                elif failure == "declared_tools":
                    self.server.responses["/api/chat"]["message"] = {"content": "text"}
                else:
                    self.server.responses["/api/version"] = (
                        503,
                        {},
                        {"error": "synthetic unavailable API"},
                    )
                with tempfile.TemporaryDirectory() as directory:
                    output = Path(directory) / "report.json"
                    code, console = self.invoke_main(output)
                    report = json.loads(output.read_text())
                self.assertEqual(code, 1)
                self.assertIn(console["status"], ("failed", "checks_failed"))
                self.assertEqual(console["status"], report["status"])
                self.assertIs(report["generated_tools_executed"], False)


class ProtocolValueTests(unittest.TestCase):
    def test_exact_zero_and_unknown_availability_are_preserved(self):
        self.assertEqual(probe.check_structured(complete_generation()), (True, None))
        for value in (False, True, None, "0", 1):
            with self.subTest(value=value):
                altered = dict(probe.EXPECTED, value=value)
                response = complete_generation()
                response["response"] = json.dumps(altered)
                self.assertFalse(probe.check_structured(response)[0])
        for availability in (False, 0, "null", "2026-01-01T00:00:00Z"):
            with self.subTest(availability=availability):
                altered = dict(probe.EXPECTED, source_available_at=availability)
                response = complete_generation()
                response["response"] = json.dumps(altered)
                self.assertFalse(probe.check_structured(response)[0])

    def test_structured_json_rejects_duplicates_nonfinite_and_truncated_output(self):
        exact = json.dumps(probe.EXPECTED)
        for output in (
            exact.replace('"value": 0', '"value": 1, "value": 0'),
            exact.replace('"value": 0', '"value": NaN'),
            exact.replace('"value": 0', '"value": Infinity'),
            exact.replace('"value": 0', '"value": -Infinity'),
            exact.replace('"value": 0', '"value": 1e9999'),
            exact[:-1],
        ):
            with self.subTest(output=output):
                response = complete_generation()
                response["response"] = output
                self.assertFalse(probe.check_structured(response)[0])

    def test_structured_json_requires_exact_identity_units_and_fields(self):
        for altered in (
            dict(probe.EXPECTED, measurement_id="another-record"),
            dict(probe.EXPECTED, unit="mmol/L"),
            dict(probe.EXPECTED, extra="unexpected"),
            {key: value for key, value in probe.EXPECTED.items() if key != "unit"},
        ):
            with self.subTest(altered=altered):
                response = complete_generation()
                response["response"] = json.dumps(altered)
                self.assertFalse(probe.check_structured(response)[0])

    def test_complete_flag_and_length_termination_apply_to_both_protocols(self):
        for done, reason in (
            (False, "stop"),
            (1, "stop"),
            (None, None),
            (True, "length"),
        ):
            with self.subTest(done=done, reason=reason):
                generated = dict(complete_generation(), done=done, done_reason=reason)
                called = dict(complete_tool_call(), done=done, done_reason=reason)
                self.assertFalse(probe.check_structured(generated)[0])
                self.assertFalse(probe.check_tool(called))

    def test_native_tool_arguments_are_structured_exact_and_integer_typed(self):
        self.assertTrue(probe.check_tool(complete_tool_call()))
        for arguments in (
            '{"probe_id":"lw001","value":0}',
            {"probe_id": "lw001", "value": False},
            {"probe_id": "lw001", "value": 0.0},
            {"probe_id": "lw001", "value": None},
            {"probe_id": "lw001", "value": 0, "command": "unexpected"},
            {"probe_id": "another-probe", "value": 0},
        ):
            with self.subTest(arguments=arguments):
                response = complete_tool_call()
                response["message"]["tool_calls"][0]["function"][
                    "arguments"
                ] = arguments
                self.assertFalse(probe.check_tool(response))
        response = complete_tool_call()
        response["message"]["tool_calls"] *= 2
        self.assertFalse(probe.check_tool(response))

    def test_loopback_roots_only_and_credentials_are_rejected(self):
        for url in (
            "http://127.0.0.1:11434",
            "http://localhost:11434/",
            "http://[::1]:11434",
        ):
            with self.subTest(url=url):
                self.assertEqual(probe.Client(url).url, url.rstrip("/"))
        for url in (
            "http://192.168.1.10:11434",
            "http://0.0.0.0:11434",
            "http://203.0.113.1:11434",
            "http://[2001:db8::1]:11434",
            "http://example.invalid:11434",
            "http://localhost.example.invalid:11434",
            "http://user:secret@127.0.0.1:11434",
            "http://user@localhost:11434",
            "https://localhost:11434",
            "http://127.0.0.1:11434/api",
            "http://127.0.0.1:11434?secret=fixture",
            "http://127.0.0.1:11434#fragment",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    probe.Client(url)

    def test_metrics_do_not_invent_throughput_from_missing_or_boolean_counts(self):
        for count, duration in ((None, None), (True, 1), (1, False), (1, 0), (-1, 1)):
            with self.subTest(count=count, duration=duration):
                result = probe.metrics(
                    {"eval_count": count, "eval_duration": duration}, 0.25
                )
                self.assertIsNone(result["generated_tokens_per_second"])
                self.assertEqual(result["wall_seconds"], 0.25)


if __name__ == "__main__":
    unittest.main()
