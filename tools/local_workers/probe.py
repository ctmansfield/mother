#!/usr/bin/env python3
"""LW-001: bounded Ollama runtime checks with synthetic inputs and no tool execution."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import time
from urllib import error, parse, request

VERSION = "local-worker-probe/1.0.0"
DEFAULT_MODEL = "qwen2.5-coder:7b"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
OPTIONS = {"temperature": 0, "seed": 0, "num_ctx": 4096, "num_predict": 192}
EXPECTED = {
    "probe_id": "lw001",
    "measurement_id": "synthetic-001",
    "value": 0,
    "unit": "mg/dL",
    "source_available_at": None,
}
FORMAT = {
    "type": "object",
    "properties": {
        "probe_id": {"type": "string", "enum": ["lw001"]},
        "measurement_id": {"type": "string"},
        "value": {"type": "number"},
        "unit": {"type": "string"},
        "source_available_at": {"type": ["string", "null"]},
    },
    "required": list(EXPECTED),
    "additionalProperties": False,
}
TOOL = {
    "type": "function",
    "function": {
        "name": "probe_echo",
        "description": "Return the specified synthetic probe identifier and value.",
        "parameters": {
            "type": "object",
            "properties": {
                "probe_id": {"type": "string"},
                "value": {"type": "integer"},
            },
            "required": ["probe_id", "value"],
            "additionalProperties": False,
        },
    },
}


def strict_json(value):
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError("Duplicate JSON member")
            result[key] = item
        return result

    def constant(unused):
        raise ValueError("Non-finite JSON number")

    def floating(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Non-finite JSON number")
        return number

    return json.loads(
        value, object_pairs_hook=pairs, parse_constant=constant, parse_float=floating
    )


def loopback_url(value):
    parsed = parse.urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError("Use a loopback HTTP root URL without credentials or a path")
    host = parsed.hostname
    if host != "localhost":
        try:
            permitted = ipaddress.ip_address(host).is_loopback
        except (ValueError, TypeError):
            permitted = False
        if not permitted:
            raise ValueError("This local probe accepts loopback addresses only")
    if parsed.port is not None and not 0 < parsed.port < 65536:
        raise ValueError("Invalid local port")
    return value.rstrip("/")


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Client:
    def __init__(self, url, timeout=60):
        self.url = loopback_url(url)
        if not 0 < timeout <= 60:
            raise ValueError("Request timeout must be between 0 and 60 seconds")
        self.timeout = timeout
        self.opener = request.build_opener(request.ProxyHandler({}), NoRedirect())

    def call(self, route, payload=None):
        data = (
            json.dumps(payload, allow_nan=False).encode()
            if payload is not None
            else None
        )
        req = request.Request(
            self.url + route,
            data=data,
            method="POST" if payload is not None else "GET",
            headers={"Content-Type": "application/json"},
        )
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
        except error.HTTPError as exc:
            raise RuntimeError(f"{route} returned HTTP {exc.code}") from None
        except (error.URLError, TimeoutError, OSError):
            raise RuntimeError(f"{route} was unavailable or timed out") from None
        if len(body) > MAX_RESPONSE_BYTES:
            raise ValueError("Local API response exceeded the probe size bound")
        result = strict_json(body)
        if not isinstance(result, dict):
            raise ValueError("Local API response must be an object")
        return result


def gpu_snapshot():
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return {"status": "unavailable", "reason": "nvidia-smi not found"}
    command = [
        executable,
        "--query-gpu=index,name,memory.total,memory.used,driver_version",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "unavailable", "reason": "GPU inventory did not complete"}
    return {
        "status": "observed" if result.returncode == 0 else "unavailable",
        "exit_code": result.returncode,
        "fields": ["index", "name", "memory_total_MiB", "memory_used_MiB", "driver"],
        "csv": result.stdout.strip() if result.returncode == 0 else None,
    }


def placement(client, model):
    try:
        rows = client.call("/api/ps").get("models", [])
        if not isinstance(rows, list):
            raise ValueError("Invalid model residency response")
        return {
            "status": "observed",
            "models": [
                {
                    key: row.get(key)
                    for key in (
                        "name",
                        "model",
                        "digest",
                        "size",
                        "size_vram",
                        "context_length",
                        "expires_at",
                    )
                }
                for row in rows
                if row.get("name", row.get("model")) == model
            ],
        }
    except (RuntimeError, ValueError, TypeError, AttributeError) as exc:
        return {"status": "unavailable", "reason": str(exc)}


def metrics(response, elapsed):
    result = {"wall_seconds": elapsed}
    for field in (
        "total_duration",
        "load_duration",
        "prompt_eval_count",
        "prompt_eval_duration",
        "eval_count",
        "eval_duration",
        "done_reason",
    ):
        result[field] = response.get(field)
    count, duration = result["eval_count"], result["eval_duration"]
    result["generated_tokens_per_second"] = (
        count * 1e9 / duration
        if type(count) is int and type(duration) is int and count >= 0 and duration > 0
        else None
    )
    result["duration_unit"] = "nanoseconds_for_api_duration_fields"
    return result


def check_structured(response):
    if response.get("done") is not True or response.get("done_reason") == "length":
        return False, "Generation was not complete"
    try:
        value = strict_json(response.get("response", ""))
    except (ValueError, TypeError, UnicodeDecodeError):
        return False, "Output was not strict JSON"
    if (
        not isinstance(value, dict)
        or value != EXPECTED
        or type(value.get("value")) not in (int, float)
    ):
        return (
            False,
            "Synthetic identity, zero value, unit or unknown availability changed",
        )
    return True, None


def check_tool(response):
    if response.get("done") is not True or response.get("done_reason") == "length":
        return False
    calls = response.get("message", {}).get("tool_calls", [])
    if not isinstance(calls, list) or len(calls) != 1:
        return False
    function = calls[0].get("function", {})
    arguments = function.get("arguments")
    return (
        function.get("name") == "probe_echo"
        and isinstance(arguments, dict)
        and arguments == {"probe_id": "lw001", "value": 0}
        and type(arguments.get("value")) is int
    )


def run_probe(client, model=DEFAULT_MODEL, expected_digest=None):
    now = datetime.now(timezone.utc)
    report = {
        "probe_version": VERSION,
        "recorded_at_utc": now.isoformat(),
        "host_local_time": now.astimezone().isoformat(),
        "runtime": {
            "system": platform.system(),
            "release": platform.release(),
            "python": platform.python_version(),
            "logical_cpus": os.cpu_count(),
            "wsl_kernel_indicator": "microsoft" in platform.release().lower(),
        },
        "model": model,
        "requested_digest_prefix": expected_digest,
        "options": dict(OPTIONS),
        "keep_alive": "2m",
        "evidence_level": "local_runtime_smoke",
        "repository_work_qualified": False,
        "generated_tools_executed": False,
        "models_pulled": False,
        "personal_data_used": False,
        "status": "incomplete",
        "gpu_before": gpu_snapshot(),
    }
    stage = "model_identity"
    try:
        if expected_digest is not None and (
            not isinstance(expected_digest, str)
            or re.fullmatch(r"[0-9a-fA-F]{12,64}", expected_digest) is None
        ):
            raise ValueError(
                "Expected digest prefix must contain 12 to 64 hexadecimal characters"
            )
        stage = "server_inventory"
        report["server_version"] = client.call("/api/version").get("version")
        rows = client.call("/api/tags").get("models", [])
        selected = [r for r in rows if r.get("name", r.get("model")) == model]
        if len(selected) != 1:
            raise ValueError(
                "Requested model is not uniquely present locally; no pull attempted"
            )
        digest = selected[0].get("digest")
        report["model_digest"] = digest
        stage = "model_identity"
        if (
            not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", digest.removeprefix("sha256:")) is None
        ):
            raise ValueError("Server did not provide a complete SHA-256 model digest")
        if expected_digest is not None and (
            not digest.removeprefix("sha256:")
            .lower()
            .startswith(expected_digest.lower())
        ):
            raise ValueError(
                "Installed model digest differs from the requested snapshot"
            )
        stage = "model_metadata"
        shown = client.call("/api/show", {"model": model, "verbose": False})
        info = shown.get("model_info", {})
        architecture = info.get("general.architecture")
        report["model_metadata"] = {
            "details": shown.get("details"),
            "capabilities": shown.get("capabilities"),
            "architecture": architecture,
            "trained_context_length": info.get(f"{architecture}.context_length"),
            "template_sha256": hashlib.sha256(
                shown.get("template", "").encode()
            ).hexdigest(),
        }
        report["placement_before"] = placement(client, model)
        stage = "structured_output"
        prompt = (
            "Normalize this synthetic record into the supplied JSON schema. "
            "Use probe_id lw001. measurement_id is synthetic-001; measured value is "
            "numeric zero; unit is mg/dL; source availability is unknown and must "
            "be JSON null. Return only the JSON object."
        )
        start = time.perf_counter()
        response = client.call(
            "/api/generate",
            {
                "model": model,
                "prompt": prompt,
                "format": FORMAT,
                "stream": False,
                "options": dict(OPTIONS),
                "keep_alive": "2m",
            },
        )
        passed, reason = check_structured(response)
        report["structured_output"] = {
            "passed": passed,
            "reason": reason,
            "output": response.get("response"),
            "metrics": metrics(response, time.perf_counter() - start),
        }
        # Capture actual resident-model metadata even when the optional native
        # tool test subsequently fails. There is no handler that executes tools.
        report["placement_after_generation"] = placement(client, model)
        capabilities = shown.get("capabilities")
        advertised = "tools" in capabilities if isinstance(capabilities, list) else None
        report["native_tools"] = {
            "advertised": advertised,
            "status": "not_advertised" if advertised is False else "unknown",
            "tools_executed": False,
        }
        tool_ok = True
        if advertised:
            stage = "native_tool_call"
            start = time.perf_counter()
            response = client.call(
                "/api/chat",
                {
                    "model": model,
                    "stream": False,
                    "tools": [TOOL],
                    "messages": [
                        {
                            "role": "user",
                            "content": "Call probe_echo exactly once with probe_id lw001 and integer value 0. "
                            "This is a synthetic protocol check.",
                        }
                    ],
                    "options": dict(OPTIONS),
                    "keep_alive": "2m",
                },
            )
            tool_ok = check_tool(response)
            report["native_tools"].update(
                status="call_shape_passed" if tool_ok else "call_shape_failed",
                response=response.get("message"),
                metrics=metrics(response, time.perf_counter() - start),
            )
        report["status"] = (
            "smoke_checks_passed" if passed and tool_ok else "checks_failed"
        )
    except (RuntimeError, ValueError, TypeError, AttributeError, KeyError) as exc:
        report["status"] = "failed"
        report["failure"] = {
            "stage": stage,
            "type": type(exc).__name__,
            "message": str(exc),
        }
    finally:
        report["gpu_after"] = gpu_snapshot()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--expected-digest-prefix")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    inference_attempted = False
    try:
        client = Client(args.url)
        # Reserve before inference: an existing report is never overwritten.
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            inference_attempted = True
            report = run_probe(client, args.model, args.expected_digest_prefix)
            serialized = json.dumps(
                report, indent=2, ensure_ascii=False, allow_nan=False
            )
            handle.write(serialized + "\n")
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "report": str(args.output),
                    "repository_work_qualified": False,
                    "tools_executed": False,
                }
            )
        )
        return 0 if report["status"] == "smoke_checks_passed" else 1
    except (OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "report_failed" if inference_attempted else "not_started",
                    "probe_attempted": inference_attempted,
                    "error": str(exc),
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
