"""Independent LW002 fixtures; model responses remain data and no model is used."""

from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import probe
import qualify
from test_probe import DIGEST, MODEL, FakeOllama


def fixture_manifest():
    tasks = []
    for index in range(4):
        identifier = "independent_fixture_" + str(index)
        path = "fixtures/independent_" + str(index) + ".py"
        payload_schema = {
            "type": "object",
            "properties": {
                "path": {"type": "string", "enum": [path]},
                "value": {"type": "number"},
                "source_available_at": {"type": ["string", "null"]},
                "proposed_source": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 2000,
                },
            },
            "required": ["path", "value", "source_available_at", "proposed_source"],
            "additionalProperties": False,
        }
        tasks.append(
            {
                "id": identifier,
                "title": "Independent synthetic task " + str(index),
                "owned_paths": [path],
                "prompt": "Return proposal data for " + identifier + "; zero and null.",
                "response_schema": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "enum": [identifier]},
                        "payload": payload_schema,
                    },
                    "required": ["task_id", "payload"],
                    "additionalProperties": False,
                },
            }
        )
    return {"version": "lw002-tasks/1.0.0", "tasks": tasks}


def artifact(task):
    return {
        "task_id": task["id"],
        "payload": {
            "path": task["owned_paths"][0],
            "value": 0,
            "source_available_at": None,
            "proposed_source": "def proposed_only():\n    return 0\n",
        },
    }


def response(value):
    return {
        "response": json.dumps(value),
        "done": True,
        "done_reason": "stop",
        "eval_count": 16,
        "eval_duration": 2_000_000_000,
    }


class ResponseQueue(dict):
    def __init__(self, existing, responses):
        super().__init__(existing)
        self.responses = list(responses)
        self.before_generate = None

    def get(self, route, default=None):
        if route != "/api/generate":
            return super().get(route, default)
        if self.before_generate is not None:
            self.before_generate()
        if not self.responses:
            return (500, {}, {"error": "Unexpected extra inference request"})
        return self.responses.pop(0)


class QualificationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.manifest = fixture_manifest()
        self.manifest_path = self.directory / "tasks.json"
        self.manifest_path.write_text(json.dumps(self.manifest, indent=2))
        self.manifest_hash = hashlib.sha256(self.manifest_path.read_bytes()).hexdigest()
        self.server = FakeOllama()
        self.addCleanup(self.server.close)
        self.server.responses = ResponseQueue(
            self.server.responses,
            [response(artifact(task)) for task in self.manifest["tasks"]],
        )
        self.client = probe.Client(self.server.url, timeout=10)

    def run_qualification(self, **kwargs):
        options = {"model": MODEL, "expected_digest_prefix": DIGEST}
        options.update(kwargs)
        return qualify.run_qualification(
            self.client, self.manifest, self.manifest_hash, **options
        )

    def assert_no_generation(self):
        self.assertNotIn("/api/generate", self.server.routes())
        self.assertNotIn("/api/chat", self.server.routes())
        self.assertNotIn("/api/pull", self.server.routes())

    def invoke_main(self, output, **overrides):
        arguments = {
            "--url": self.server.url,
            "--tasks": str(self.manifest_path),
            "--expected-digest-prefix": DIGEST,
            "--output": str(output),
        }
        arguments.update(overrides)
        argv = [part for pair in arguments.items() for part in pair]
        console = io.StringIO()
        with redirect_stdout(console):
            code = qualify.main(argv)
        return code, json.loads(console.getvalue())

    def test_four_schema_valid_artifacts_remain_pending_substantive_review(self):
        report = self.run_qualification()
        self.assertEqual(report["status"], "pending_substantive_review")
        self.assertEqual(report["protocol_validity"], "valid")
        self.assertEqual(report["substantive_review"], "pending")
        self.assertEqual(report["model_digest"], "sha256:" + DIGEST)
        self.assertEqual(report["manifest_sha256"], self.manifest_hash)
        source_root = Path(__file__).resolve().parent
        self.assertEqual(
            report["implementation_sha256"],
            {
                name: hashlib.sha256((source_root / name).read_bytes()).hexdigest()
                for name in ("qualify.py", "probe.py")
            },
        )
        self.assertEqual(report["artifacts_received"], 4)
        self.assertEqual(report["requests_attempted"], 4)
        for flag in (
            "repository_work_qualified",
            "autonomous_worker_qualified",
            "generated_code_executed",
            "generated_tools_executed",
            "models_pulled",
        ):
            self.assertIs(report[flag], False)
        generations = [
            entry for entry in self.server.calls if entry[1] == "/api/generate"
        ]
        self.assertEqual(len(generations), 4)
        for task, row, entry in zip(
            self.manifest["tasks"], report["task_results"], generations
        ):
            self.assertEqual(row["id"], task["id"])
            self.assertEqual(row["owned_paths"], task["owned_paths"])
            self.assertEqual(row["status"], "artifact_received")
            self.assertEqual(row["substantive_review"], "pending")
            self.assertEqual(row["parsed_artifact"], artifact(task))
            self.assertEqual(json.loads(row["raw_output"]), artifact(task))
            for name in ("context_sha256", "schema_sha256", "prompt_sha256"):
                self.assertRegex(row[name], r"^[0-9a-f]{64}$")
            self.assertEqual(entry[0], "POST")
            self.assertEqual(entry[2]["prompt"], task["prompt"])
            self.assertEqual(entry[2]["format"], task["response_schema"])
            self.assertIs(entry[2]["stream"], False)
            self.assertNotIn("tools", entry[2])
        self.assertNotIn("/api/chat", self.server.routes())
        self.assertNotIn("/api/pull", self.server.routes())

    def test_untrusted_source_text_is_retained_without_execution_or_patch_application(
        self,
    ):
        marker = self.directory / "generated-code-ran"
        candidate = artifact(self.manifest["tasks"][0])
        source = (
            "from pathlib import Path\nPath("
            + repr(str(marker))
            + ").write_text('ran')\n"
        )
        candidate["payload"]["proposed_source"] = source
        self.server.responses.responses[0] = response(candidate)
        with (
            patch.object(probe.subprocess, "run") as process,
            patch.object(probe.os, "system") as shell,
        ):
            report = self.run_qualification()
        self.assertEqual(report["status"], "pending_substantive_review")
        self.assertEqual(
            report["task_results"][0]["parsed_artifact"]["payload"]["proposed_source"],
            source,
        )
        self.assertFalse(marker.exists())
        process.assert_not_called()
        shell.assert_not_called()

    def test_wrong_answers_can_be_protocol_valid_without_becoming_quality_claims(self):
        for task, generated in zip(
            self.manifest["tasks"], self.server.responses.responses
        ):
            proposed = artifact(task)
            proposed["payload"]["value"] = 999
            generated["response"] = json.dumps(proposed)
        report = self.run_qualification()
        self.assertEqual(report["protocol_validity"], "valid")
        self.assertEqual(report["substantive_review"], "pending")
        self.assertIs(report["repository_work_qualified"], False)

    def test_protocol_and_http_failures_continue_to_later_fixed_tasks(self):
        wrong = artifact(self.manifest["tasks"][1])
        wrong["payload"]["value"] = False
        self.server.responses.responses[1] = response(wrong)
        self.server.responses.responses[2] = (503, {}, {"error": "controlled failure"})
        report = self.run_qualification()
        self.assertEqual(report["status"], "checks_failed")
        self.assertEqual(report["artifacts_received"], 2)
        self.assertEqual(
            [row["status"] for row in report["task_results"]],
            [
                "artifact_received",
                "protocol_failed",
                "request_failed",
                "artifact_received",
            ],
        )
        self.assertEqual(report["task_results"][1]["raw_output"], json.dumps(wrong))
        self.assertNotIn("parsed_artifact", report["task_results"][1])
        self.assertIn("failure", report["task_results"][2])
        self.assertEqual(self.server.routes().count("/api/generate"), 4)

    def test_progress_checkpoints_preserve_completed_results_before_next_request(self):
        snapshots = []
        report = self.run_qualification(
            persist=lambda value: snapshots.append(json.loads(json.dumps(value)))
        )
        self.assertEqual(snapshots[0]["task_results"], [])
        self.assertEqual(snapshots[-1], report)
        for index, task in enumerate(self.manifest["tasks"]):
            pending = [
                item
                for item in snapshots
                if item["active_task_id"] == task["id"]
                and item["task_results"][-1]["status"] == "incomplete"
            ]
            self.assertTrue(pending)
            self.assertEqual(len(pending[0]["task_results"]), index + 1)
            self.assertTrue(
                all(
                    row["status"] == "artifact_received"
                    for row in pending[0]["task_results"][:-1]
                )
            )

    def test_model_identity_failures_prevent_inference(self):
        for pin in ("", "a" * 11, "z" * 12, "b" * 64, None):
            with self.subTest(pin=pin):
                self.server.calls.clear()
                report = self.run_qualification(expected_digest_prefix=pin)
                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["failure"]["stage"], "model_identity")
                self.assert_no_generation()
        for rows in (
            [],
            [{"name": MODEL, "digest": DIGEST[:12]}],
            [{"name": MODEL, "digest": DIGEST}] * 2,
        ):
            with self.subTest(rows=rows):
                self.server.calls.clear()
                self.server.responses["/api/tags"] = {"models": rows}
                self.assertEqual(self.run_qualification()["status"], "failed")
                self.assert_no_generation()

    def test_unknown_schema_keywords_are_rejected_before_any_api_request(self):
        self.manifest["tasks"][2]["response_schema"]["oneOf"] = []
        report = self.run_qualification()
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["failure"]["stage"], "manifest_validation")
        self.assertEqual(self.server.calls, [])

    def test_main_preserves_existing_output_without_any_api_call(self):
        output = self.directory / "report.json"
        sentinel = b"existing report\x00\n"
        output.write_bytes(sentinel)
        code, console = self.invoke_main(output)
        self.assertEqual(code, 1)
        self.assertEqual(console["status"], "not_started")
        self.assertEqual(output.read_bytes(), sentinel)
        self.assertEqual(self.server.calls, [])

    def test_main_flushes_reports_and_does_not_read_sibling_acceptance_answers(self):
        secret = "INDEPENDENT_EXPECTED_ANSWER_MUST_NOT_ENTER_INFERENCE"
        (self.directory / "qualification_acceptance.json").write_text(
            json.dumps({"secret": secret})
        )
        output = self.directory / "report.json"
        observed = []
        self.server.responses.before_generate = lambda: observed.append(
            json.loads(output.read_text())
        )
        code, console = self.invoke_main(output)
        final = json.loads(output.read_text())
        self.assertEqual(code, 0)
        self.assertEqual(console["status"], "pending_substantive_review")
        self.assertEqual(final["status"], console["status"])
        self.assertEqual(len(observed), 4)
        for index, checkpoint in enumerate(observed):
            self.assertEqual(len(checkpoint["task_results"]), index + 1)
            self.assertEqual(checkpoint["requests_attempted"], index + 1)
            self.assertTrue(
                all(
                    row["status"] == "artifact_received"
                    for row in checkpoint["task_results"][:-1]
                )
            )
            self.assertEqual(checkpoint["task_results"][-1]["status"], "incomplete")
        self.assertNotIn(secret, json.dumps(self.server.calls))
        self.assertNotIn(secret, output.read_text())

    def test_main_reports_nonzero_for_protocol_failure_but_keeps_four_results(self):
        self.server.responses.responses[1]["response"] = "{"
        output = self.directory / "report.json"
        code, console = self.invoke_main(output)
        saved = json.loads(output.read_text())
        self.assertEqual(code, 1)
        self.assertEqual(console["status"], "checks_failed")
        self.assertEqual(len(saved["task_results"]), 4)
        self.assertEqual(saved["task_results"][1]["raw_output"], "{")
        self.assertEqual(saved["task_results"][-1]["status"], "artifact_received")

    def test_main_rejects_invalid_endpoint_and_schema_without_contact(self):
        code, unused = self.invoke_main(
            self.directory / "endpoint.json", **{"--url": "http://192.168.1.10:11434"}
        )
        self.assertEqual(code, 1)
        invalid = deepcopy(self.manifest)
        invalid["tasks"][0]["response_schema"]["$ref"] = "outside.json"
        self.manifest_path.write_text(json.dumps(invalid))
        code, unused = self.invoke_main(self.directory / "schema.json")
        self.assertEqual(code, 1)
        self.assertEqual(self.server.calls, [])

    def test_interruption_retains_prior_artifacts_and_stops_later_requests(self):
        original_call = probe.Client.call
        attempts = 0

        def interrupted_call(client, route, payload=None):
            nonlocal attempts
            if route == "/api/generate":
                attempts += 1
                if attempts == 3:
                    raise KeyboardInterrupt()
            return original_call(client, route, payload)

        output = self.directory / "report.json"
        with patch.object(probe.Client, "call", interrupted_call):
            code, console = self.invoke_main(output)
        saved = json.loads(output.read_text())
        self.assertEqual(code, 1)
        self.assertEqual(console["status"], "interrupted")
        self.assertEqual(
            [row["status"] for row in saved["task_results"]],
            ["artifact_received", "artifact_received", "interrupted"],
        )
        self.assertEqual(self.server.routes().count("/api/generate"), 2)


class QualificationContractTests(unittest.TestCase):
    def setUp(self):
        self.manifest = fixture_manifest()
        self.task = self.manifest["tasks"][0]

    def assert_invalid(self, generated):
        checked = qualify.check_response(generated, self.task)
        self.assertEqual(checked["status"], "protocol_failed")
        self.assertEqual(checked["protocol_validity"], "invalid")
        self.assertEqual(checked["substantive_review"], "pending")
        self.assertNotIn("parsed_artifact", checked)
        self.assertTrue(checked["findings"])
        self.assertEqual(checked["raw_output"], generated.get("response"))

    def test_wrong_identity_unknown_fields_bool_number_and_out_of_scope_path(self):
        wrong_id = artifact(self.task)
        wrong_id["task_id"] = "another_task"
        unknown = artifact(self.task)
        unknown["repository_work_qualified"] = True
        nested = artifact(self.task)
        nested["payload"]["shell_command"] = "do not execute"
        boolean = artifact(self.task)
        boolean["payload"]["value"] = False
        outside = artifact(self.task)
        outside["payload"]["path"] = "../outside.py"
        for value in (wrong_id, unknown, nested, boolean, outside):
            with self.subTest(value=value):
                self.assert_invalid(response(value))

    def test_duplicate_nonfinite_overflow_and_invalid_json_remain_rejected_data(self):
        valid = json.dumps(artifact(self.task))
        for raw in (
            valid.replace('"value": 0', '"value": 3, "value": 0'),
            valid.replace('"value": 0', '"value": NaN'),
            valid.replace('"value": 0', '"value": Infinity'),
            valid.replace('"value": 0', '"value": 1e9999'),
            valid[:-1],
            "```json\n" + valid + "\n```",
            "[]",
        ):
            with self.subTest(raw=raw):
                generated = response(artifact(self.task))
                generated["response"] = raw
                self.assert_invalid(generated)

    def test_incomplete_generation_and_nontext_outputs_fail_closed(self):
        for done, reason in (
            (False, "stop"),
            (1, "stop"),
            (True, "length"),
            (None, None),
        ):
            with self.subTest(done=done, reason=reason):
                generated = response(artifact(self.task))
                generated.update(done=done, done_reason=reason)
                self.assert_invalid(generated)
        for raw in (None, artifact(self.task), 0):
            with self.subTest(raw=raw):
                generated = response(artifact(self.task))
                generated["response"] = raw
                self.assert_invalid(generated)

    def test_supported_schema_bounds_and_numeric_enum_do_not_accept_bool(self):
        schema = {
            "type": "array",
            "items": {"type": "string", "minLength": 2, "maxLength": 3},
            "minItems": 1,
            "maxItems": 2,
        }
        qualify.validate_value(["ab", "abc"], schema)
        for invalid in ([], ["a"], ["abcd"], ["ab"] * 3):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    qualify.validate_value(invalid, schema)
        with self.assertRaises(ValueError):
            qualify.validate_value(False, {"type": ["number", "boolean"], "enum": [0]})

    def test_integer_schema_accepts_integral_numbers_but_not_booleans(self):
        qualify.validate_value(2.0, {"type": "integer"})
        for invalid in (False, 2.5):
            with self.subTest(integer=invalid):
                with self.assertRaises(ValueError):
                    qualify.validate_value(invalid, {"type": "integer"})

    def test_unsupported_and_open_schemas_are_rejected(self):
        for schema in (
            {"type": "string", "pattern": ".*"},
            {"type": "object", "properties": {}, "additionalProperties": True},
            {
                "type": "object",
                "properties": {},
                "required": ["missing"],
                "additionalProperties": False,
            },
            {"type": "array"},
            {"type": "string", "minLength": 5, "maxLength": 1},
        ):
            with self.subTest(schema=schema):
                with self.assertRaises(ValueError):
                    qualify.validate_schema(schema)

    def test_manifest_exact_task_count_unique_ids_and_safe_relative_scope(self):
        variants = []
        short = deepcopy(self.manifest)
        short["tasks"].pop()
        variants.append(short)
        duplicate = deepcopy(self.manifest)
        duplicate["tasks"][1] = deepcopy(duplicate["tasks"][0])
        variants.append(duplicate)
        for path in (
            "../outside.py",
            "/outside.py",
            "C:/outside.py",
            "C:outside.py",
            "C:\\outside.py",
        ):
            invalid = deepcopy(self.manifest)
            invalid["tasks"][0]["owned_paths"] = [path]
            variants.append(invalid)
        for manifest in variants:
            with self.subTest(manifest=manifest):
                with self.assertRaises(ValueError):
                    qualify.validate_manifest(manifest)

    def test_manifest_identity_hashes_exact_bytes_and_refuses_duplicate_members(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.json"
            raw = json.dumps(self.manifest, indent=2).encode() + b"\n"
            path.write_bytes(raw)
            loaded, digest = qualify.load_manifest(path)
            self.assertEqual(loaded, self.manifest)
            self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
            invalid = raw.replace(
                b'"version":', b'"version":"duplicate", "version":', 1
            )
            path.write_bytes(invalid)
            with self.assertRaises(ValueError):
                qualify.load_manifest(path)

    def test_real_manifest_and_frozen_acceptance_agree_without_evaluating_model_output(
        self,
    ):
        root = Path(__file__).resolve().parent
        manifest, digest = qualify.load_manifest(root / "qualification_tasks.json")
        acceptance = json.loads((root / "qualification_acceptance.json").read_text())
        self.assertEqual(acceptance["manifest_sha256"], digest)
        self.assertEqual(
            [task["id"] for task in acceptance["tasks"]],
            [task["id"] for task in manifest["tasks"]],
        )
        self.assertIs(acceptance["model_input"], False)
        self.assertIs(acceptance["actual_model_outputs_inspected_before_freeze"], False)


if __name__ == "__main__":
    unittest.main()
