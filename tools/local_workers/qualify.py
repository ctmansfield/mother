#!/usr/bin/env python3
"""LW-002: collect four bounded artifact proposals without executing them."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import time

import probe


VERSION = "local-artifact-qualification/1.0.0"
MANIFEST_VERSION = "lw002-tasks/1.0.0"
MAX_MANIFEST_BYTES = 128 * 1024
MAX_DEPTH = 32
MAX_JSON_NODES = 50_000
OPTIONS = {"temperature": 0, "seed": 0, "num_ctx": 4096, "num_predict": 1536}
KEEP_ALIVE = "2m"
SCHEMA_KEYS = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "minItems",
    "maxItems",
    "minLength",
    "maxLength",
    "enum",
}
TYPES = {"object", "array", "string", "integer", "number", "boolean", "null"}
EXPECTED_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    KeyError,
    OSError,
    RecursionError,
)


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_hash(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def bounded_json(value):
    """Bound nesting and work even for a synthetic client bypassing HTTP bounds."""
    stack = [(value, 0)]
    count = 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if depth > MAX_DEPTH or count > MAX_JSON_NODES:
            raise ValueError("JSON exceeds the nesting or node bound")
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise ValueError("JSON object keys must be strings")
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
        elif type(item) is float:
            if not math.isfinite(item):
                raise ValueError("JSON numbers must be finite")
        elif item is not None and type(item) not in (str, bool, int):
            raise ValueError("Value is not a supported JSON type")


def same_json(left, right):
    """JSON numeric equality without Python's False == 0 shortcut."""
    if type(left) in (int, float) and type(right) in (int, float):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            same_json(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            same_json(a, b) for a, b in zip(left, right)
        )
    return left == right


def schema_types(schema):
    value = schema.get("type")
    return [value] if isinstance(value, str) else value


def validate_schema(schema):
    """Accept only the explicit, closed subset used by the fixed task bundle."""
    bounded_json(schema)

    def visit(node, depth=0):
        if depth > MAX_DEPTH or not isinstance(node, dict):
            raise ValueError("Schema must be a bounded object")
        if set(node) - SCHEMA_KEYS:
            raise ValueError("Unsupported schema keyword")
        types = schema_types(node)
        if (
            not isinstance(types, list)
            or not types
            or any(not isinstance(kind, str) or kind not in TYPES for kind in types)
            or len(types) != len(set(types))
        ):
            raise ValueError("Schema needs supported, unique types")
        if "object" in types:
            properties = node.get("properties")
            required = node.get("required", [])
            if (
                not isinstance(properties, dict)
                or node.get("additionalProperties") is not False
                or not isinstance(required, list)
                or any(not isinstance(key, str) for key in required)
                or len(required) != len(set(required))
                or not set(required).issubset(properties)
            ):
                raise ValueError(
                    "Object schemas must be closed with valid required keys"
                )
            for key, child in properties.items():
                if not key or len(key) > 128:
                    raise ValueError("Schema property names must have 1–128 characters")
                visit(child, depth + 1)
        elif any(
            key in node for key in ("properties", "required", "additionalProperties")
        ):
            raise ValueError("Object keywords require an object type")
        if "array" in types:
            visit(node.get("items"), depth + 1)
        elif any(key in node for key in ("items", "minItems", "maxItems")):
            raise ValueError("Array keywords require an array type")
        if "string" not in types and any(
            key in node for key in ("minLength", "maxLength")
        ):
            raise ValueError("String keywords require a string type")
        for low, high in (("minItems", "maxItems"), ("minLength", "maxLength")):
            for key in (low, high):
                if key in node and (type(node[key]) is not int or node[key] < 0):
                    raise ValueError("Schema bounds must be nonnegative integers")
            if low in node and high in node and node[low] > node[high]:
                raise ValueError("Schema minimum exceeds its maximum")
        if "enum" in node:
            choices = node["enum"]
            if not isinstance(choices, list) or not choices or len(choices) > 128:
                raise ValueError("Schema enum must contain 1–128 values")
            without_enum = {key: value for key, value in node.items() if key != "enum"}
            for index, choice in enumerate(choices):
                if any(same_json(choice, earlier) for earlier in choices[:index]):
                    raise ValueError("Schema enum has duplicate values")
                _validate_value(choice, without_enum, "$enum")

    visit(schema)
    return schema


def matches_type(value, kind):
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": type(value) is str,
        "integer": type(value) is int
        or (type(value) is float and math.isfinite(value) and value.is_integer()),
        "number": type(value) in (int, float),
        "boolean": type(value) is bool,
        "null": value is None,
    }[kind]


def _validate_value(value, schema, path="$", depth=0):
    if depth > MAX_DEPTH:
        raise ValueError("Value exceeds the nesting bound")
    if not any(matches_type(value, kind) for kind in schema_types(schema)):
        raise ValueError(f"{path}: wrong JSON type")
    if "enum" in schema and not any(same_json(value, item) for item in schema["enum"]):
        raise ValueError(f"{path}: value is outside the permitted enum")
    if isinstance(value, dict):
        properties = schema["properties"]
        if not set(schema.get("required", [])).issubset(value):
            raise ValueError(f"{path}: required property is missing")
        if set(value) - set(properties):
            raise ValueError(f"{path}: unexpected object property")
        for key, item in value.items():
            _validate_value(item, properties[key], f"{path}.{key}"[-768:], depth + 1)
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get(
            "maxItems", MAX_JSON_NODES
        ):
            raise ValueError(f"{path}: array length is outside bounds")
        for index, item in enumerate(value):
            _validate_value(item, schema["items"], f"{path}[{index}]"[-768:], depth + 1)
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get(
            "maxLength", probe.MAX_RESPONSE_BYTES
        ):
            raise ValueError(f"{path}: string length is outside bounds")


def validate_value(value, schema):
    validate_schema(schema)
    bounded_json(value)
    _validate_value(value, schema)
    return value


def validate_manifest(manifest):
    bounded_json(manifest)
    if (
        not isinstance(manifest, dict)
        or set(manifest) != {"version", "tasks"}
        or manifest.get("version") != MANIFEST_VERSION
        or not isinstance(manifest.get("tasks"), list)
        or len(manifest["tasks"]) != 4
    ):
        raise ValueError("Use the supported manifest version with exactly four tasks")
    seen = set()
    for task in manifest["tasks"]:
        if not isinstance(task, dict) or set(task) != {
            "id",
            "title",
            "owned_paths",
            "prompt",
            "response_schema",
        }:
            raise ValueError("Task manifest fields do not match the fixed contract")
        identifier = task["id"]
        if (
            not isinstance(identifier, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", identifier) is None
            or identifier in seen
        ):
            raise ValueError("Task IDs must be unique bounded identifiers")
        seen.add(identifier)
        if not isinstance(task["title"], str) or not 1 <= len(task["title"]) <= 256:
            raise ValueError("Task titles must have 1–256 characters")
        if (
            not isinstance(task["prompt"], str)
            or not 1 <= len(task["prompt"]) <= 12_000
        ):
            raise ValueError("Task prompts must have 1–12000 characters")
        paths = task["owned_paths"]
        if not isinstance(paths, list) or not 1 <= len(paths) <= 16:
            raise ValueError("Each task requires 1–16 owned fixture paths")
        for path in paths:
            if (
                not isinstance(path, str)
                or not 1 <= len(path) <= 256
                or "\\" in path
                or PurePosixPath(path).is_absolute()
                or PureWindowsPath(path).drive
                or ".." in PurePosixPath(path).parts
                or path in (".", "")
            ):
                raise ValueError("Owned fixture paths must be bounded relative paths")
        if len(paths) != len(set(paths)):
            raise ValueError("Owned fixture paths must be unique within a task")
        schema = validate_schema(task["response_schema"])
        if (
            schema.get("type") != "object"
            or set(schema.get("properties", {})) != {"task_id", "payload"}
            or set(schema.get("required", [])) != {"task_id", "payload"}
            or schema["properties"]["task_id"].get("type") != "string"
            or schema["properties"]["task_id"].get("enum") != [identifier]
        ):
            raise ValueError("Response envelope must bind task_id and require payload")
    return manifest


def read_source(path):
    with Path(path).open("rb") as handle:
        raw = handle.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("Source file exceeds 128 KiB")
    return raw


def load_manifest(path):
    raw = read_source(path)
    manifest = probe.strict_json(raw.decode("utf-8"))
    return validate_manifest(manifest), hashlib.sha256(raw).hexdigest()


def check_response(response, task):
    result = {
        "status": "protocol_failed",
        "protocol_validity": "invalid",
        "substantive_review": "pending",
        "raw_output": response.get("response"),
        "completion": {
            "done": response.get("done"),
            "done_reason": response.get("done_reason"),
        },
        "findings": [],
    }
    if response.get("done") is not True or response.get("done_reason") == "length":
        result["findings"].append("Generation did not finish normally")
    raw = result["raw_output"]
    if not isinstance(raw, str):
        result["findings"].append("Response is not a JSON text string")
        return result
    try:
        if len(raw.encode("utf-8")) > probe.MAX_RESPONSE_BYTES:
            raise ValueError("Generated JSON exceeds the response bound")
        value = probe.strict_json(raw)
        validate_value(value, task["response_schema"])
        if value.get("task_id") != task["id"]:
            raise ValueError("Response task identity does not match its request")
    except EXPECTED_ERRORS as exc:
        result["findings"].append(f"{type(exc).__name__}: {str(exc)[:800]}")
        return result
    if result["findings"]:
        return result
    result.update(
        status="artifact_received", protocol_validity="valid", parsed_artifact=value
    )
    return result


def new_report(model, expected_digest_prefix, manifest_sha256):
    return {
        "runner_version": VERSION,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_level": "local_artifact_proposals",
        "status": "incomplete",
        "protocol_validity": "pending",
        "substantive_review": "pending",
        "repository_work_qualified": False,
        "autonomous_worker_qualified": False,
        "generated_code_executed": False,
        "generated_tools_executed": False,
        "models_pulled": False,
        "model": model,
        "requested_digest_prefix": expected_digest_prefix,
        "manifest_sha256": manifest_sha256,
        "options": dict(OPTIONS),
        "keep_alive": KEEP_ALIVE,
        "active_task_id": None,
        "requests_attempted": 0,
        "task_results": [],
    }


def failure(exc, stage=None):
    result = {"type": type(exc).__name__, "message": str(exc)[:800]}
    if stage is not None:
        result["stage"] = stage
    return result


def task_record(task):
    return {
        "id": task["id"],
        "title": task["title"],
        "owned_paths": list(task["owned_paths"]),
        "prompt_sha256": hashlib.sha256(task["prompt"].encode("utf-8")).hexdigest(),
        "schema_sha256": content_hash(task["response_schema"]),
        "context_sha256": content_hash(
            {"prompt": task["prompt"], "response_schema": task["response_schema"]}
        ),
        "status": "incomplete",
        "protocol_validity": "pending",
        "substantive_review": "pending",
    }


def run_qualification(
    client,
    manifest,
    manifest_sha256,
    model=probe.DEFAULT_MODEL,
    expected_digest_prefix=None,
    persist=None,
):
    report = new_report(model, expected_digest_prefix, manifest_sha256)

    def save():
        if persist is not None:
            persist(report)

    def interrupted():
        report.update(status="interrupted", protocol_validity="incomplete")
        if report["active_task_id"] is not None:
            report["task_results"][-1].update(
                status="interrupted", protocol_validity="not_observed"
            )
        save()
        return report

    save()
    stage = "manifest_validation"
    try:
        validate_manifest(manifest)
        if (
            not isinstance(manifest_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", manifest_sha256) is None
        ):
            raise ValueError("Manifest identity must be a full lowercase SHA-256")
        report["manifest_version"] = manifest["version"]
        report["task_contexts"] = [
            {
                key: value
                for key, value in task_record(task).items()
                if key not in ("status", "protocol_validity", "substantive_review")
            }
            for task in manifest["tasks"]
        ]
        stage = "implementation_identity"
        report["implementation_sha256"] = {
            "qualify.py": hashlib.sha256(read_source(__file__)).hexdigest(),
            "probe.py": hashlib.sha256(read_source(probe.__file__)).hexdigest(),
        }
        stage = "model_identity"
        if (
            not isinstance(expected_digest_prefix, str)
            or re.fullmatch(r"[0-9a-fA-F]{12,64}", expected_digest_prefix) is None
        ):
            raise ValueError(
                "Expected model pin must have 12–64 hexadecimal characters"
            )
        if not isinstance(model, str) or not 1 <= len(model) <= 256:
            raise ValueError("Choose one bounded installed model name")
        stage = "server_inventory"
        report["server_version"] = client.call("/api/version").get("version")
        rows = client.call("/api/tags").get("models")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("Server model inventory must be an object array")
        selected = [row for row in rows if row.get("name", row.get("model")) == model]
        if len(selected) != 1:
            raise ValueError(
                "Requested model is not uniquely installed; no pull attempted"
            )
        stage = "model_identity"
        digest = selected[0].get("digest")
        report["model_digest"] = digest
        if not isinstance(digest, str):
            raise ValueError("Server did not provide a complete model digest")
        normalized = digest.removeprefix("sha256:")
        if re.fullmatch(r"[0-9a-fA-F]{64}", normalized) is None:
            raise ValueError("Server did not provide a complete model digest")
        if not normalized.lower().startswith(expected_digest_prefix.lower()):
            raise ValueError(
                "Installed model digest differs from the requested snapshot"
            )
        stage = "model_metadata"
        shown = client.call("/api/show", {"model": model, "verbose": False})
        info, template = shown.get("model_info", {}), shown.get("template")
        if not isinstance(info, dict) or not isinstance(template, str):
            raise ValueError("Model metadata or template is unavailable")
        architecture = info.get("general.architecture")
        report["model_metadata"] = {
            "details": shown.get("details"),
            "capabilities": shown.get("capabilities"),
            "architecture": architecture,
            "trained_context_length": info.get(f"{architecture}.context_length"),
            "template_sha256": hashlib.sha256(template.encode("utf-8")).hexdigest(),
        }
        report["placement_before"] = probe.placement(client, model)
    except KeyboardInterrupt:
        return interrupted()
    except EXPECTED_ERRORS as exc:
        report.update(status="failed", protocol_validity="not_observed")
        report["failure"] = failure(exc, stage)
        save()
        return report
    save()
    for task in manifest["tasks"]:
        result = task_record(task)
        report["task_results"].append(result)
        report["active_task_id"] = task["id"]
        report["requests_attempted"] += 1
        save()
        start = time.perf_counter()
        try:
            response = client.call(
                "/api/generate",
                {
                    "model": model,
                    "prompt": task["prompt"],
                    "format": task["response_schema"],
                    "stream": False,
                    "options": dict(OPTIONS),
                    "keep_alive": KEEP_ALIVE,
                },
            )
            result.update(check_response(response, task))
            result["metrics"] = probe.metrics(response, time.perf_counter() - start)
        except KeyboardInterrupt:
            return interrupted()
        except EXPECTED_ERRORS as exc:
            result.update(
                status="request_failed",
                protocol_validity="not_observed",
                failure=failure(exc),
                metrics={"wall_seconds": time.perf_counter() - start},
            )
        report["active_task_id"] = None
        save()
    try:
        report["placement_after"] = probe.placement(client, model)
    except KeyboardInterrupt:
        return interrupted()
    received = sum(
        row["status"] == "artifact_received" for row in report["task_results"]
    )
    report["artifacts_received"] = received
    report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    report.update(
        status="pending_substantive_review" if received == 4 else "checks_failed",
        protocol_validity="valid" if received == 4 else "invalid",
    )
    save()
    return report


def write_report(handle, report):
    """Flush each completed task before asking the model for the next one."""
    serialized = json.dumps(report, indent=2, allow_nan=False) + "\n"
    handle.seek(0)
    handle.write(serialized)
    handle.truncate()
    handle.flush()
    os.fsync(handle.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default=probe.DEFAULT_MODEL)
    parser.add_argument("--expected-digest-prefix", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--tasks",
        type=Path,
        default=Path(__file__).with_name("qualification_tasks.json"),
    )
    args = parser.parse_args(argv)
    reserved = False
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            reserved = True
            report = new_report(args.model, args.expected_digest_prefix, None)
            write_report(handle, report)
            stage = "manifest_validation"
            try:
                manifest, digest = load_manifest(args.tasks)
                stage = "endpoint_validation"
                client = probe.Client(args.url)
            except KeyboardInterrupt:
                report.update(status="interrupted", protocol_validity="incomplete")
                write_report(handle, report)
            except EXPECTED_ERRORS as exc:
                report.update(status="failed", protocol_validity="not_observed")
                report["failure"] = failure(exc, stage)
                write_report(handle, report)
            else:
                report = run_qualification(
                    client,
                    manifest,
                    digest,
                    args.model,
                    args.expected_digest_prefix,
                    persist=lambda value: write_report(handle, value),
                )
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "report": str(args.output),
                    "artifacts_received": report.get("artifacts_received", 0),
                    "substantive_review": "pending",
                    "repository_work_qualified": False,
                    "generated_code_executed": False,
                }
            )
        )
        return 0 if report["status"] == "pending_substantive_review" else 1
    except KeyboardInterrupt:
        # A signal between handlers may bypass the inference-level handler.
        # Preserve the current file. Checkpoint writes are flushed and synced,
        # but are not an atomic power-loss/kill recovery mechanism.
        print(json.dumps({"status": "interrupted", "report": str(args.output)}))
        return 1
    except (OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "report_failed" if reserved else "not_started",
                    "report": str(args.output),
                    "error": str(exc)[:800],
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
