#!/usr/bin/env python3
"""Read-only FW00412 role-field shadow adjudication; preserves strict results.

Never edits source/receipts or raw model outputs. No network, model, GPU, or retries.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

MODEL_SLOTS = 15
SOURCE_PIN = "ba6fbb90c031f122b7db61d2f67f2b22ef1cf130"
GENERIC = "RESEARCH-SCREENING"
ROLES = frozenset(("SOURCE", "ECOLOGY", "METABOLIC", "RECEPTOR", "HOST"))


def role_normalization(returned, assigned):
    """Only two known introductory-text echoes; never map an edge kind or node ID."""
    if assigned not in ROLES or not isinstance(returned, str):
        return None
    if returned == assigned:
        return "UNCHANGED"
    if returned == GENERIC:
        return "GENERIC_ROLE_LABEL_ECHO"
    if returned == "RESEARCH-SCREENING candidate for " + assigned:
        return "FULL_INTRODUCTORY_PHRASE_ECHO"
    return None


def load_unique(raw):
    def hook(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=hook)


def summarize_file(path, tasks, graph, sources, broker, specialists):
    rows = [
        load_unique(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) != MODEL_SLOTS:
        raise ValueError("expected exactly 15 original records, no partial results")
    task_by_id = {task["id"]: task for task in tasks}
    if (
        set(task_by_id) != {row.get("case_id") for row in rows}
        or len({row.get("case_id") for row in rows}) != MODEL_SLOTS
    ):
        raise ValueError("original task IDs incomplete or repeated")
    model_names = {row.get("model") for row in rows}
    if len(model_names) != 1:
        raise ValueError("multiple model identities in one record batch")
    model = next(iter(model_names))
    measures = Counter()
    examples = []
    for row in rows:
        if (
            row.get("source_pin") != SOURCE_PIN
            or row.get("graph_sha256") != graph["graph_sha256"]
            or row.get("source_record_sha256") != sources["records"][0]["record_sha256"]
        ):
            raise ValueError("underlying graph/source pin differs")
        task = task_by_id[row["case_id"]]
        if row.get("role") != task["role"]:
            raise ValueError("trusted task role differs")
        if (
            row.get("response_sha256")
            != hashlib.sha256(row.get("response", "").encode()).hexdigest()
        ):
            raise ValueError("response bytes differ from saved fingerprint")
        if row.get("error_class"):
            measures["original_request_error"] += 1
            continue
        raw = row["response"]
        scoped = broker.with_retraction(sources, task)
        old = specialists.judge(raw, graph, scoped, task)
        saved = row.get("grade", {})
        if (old["task_correct"], old["schema_valid"], old["reason"]) != (
            saved.get("task_correct"),
            saved.get("schema_valid"),
            saved.get("reason"),
        ):
            raise ValueError("original grade does not reproduce")
        measures["original_schema_valid"] += bool(old["schema_valid"])
        measures["original_correct"] += bool(old["task_correct"])
        try:
            value = load_unique(raw)
        except (TypeError, ValueError, UnicodeError):
            measures["not_parseable_json"] += 1
            continue
        if not isinstance(value, dict):
            measures["not_object"] += 1
            continue
        category = role_normalization(value.get("role"), task["role"])
        if category is None:
            measures["unsafe_or_unrecognized_role_held"] += 1
            continue
        if category != "UNCHANGED":
            measures["role_echo_repair_eligible"] += 1
            measures["role_" + category.lower()] += 1
        normalized = deepcopy(value)
        normalized["role"] = task["role"]
        repaired = specialists.judge(
            json.dumps(normalized, sort_keys=True), graph, scoped, task
        )
        measures["shadow_schema_valid"] += bool(repaired["schema_valid"])
        measures["shadow_correct"] += bool(repaired["task_correct"])
        measures["shadow_false_candidates"] += bool(repaired["false_candidate"])
        if category != "UNCHANGED" and len(examples) < 5:
            examples.append(
                {
                    "case_id": row["case_id"],
                    "category": category,
                    "original_reason": old["reason"],
                    "shadow_reason": repaired["reason"],
                    "shadow_correct": repaired["task_correct"],
                }
            )
    return {
        "model": model,
        "total_rows": len(rows),
        "counts": dict(sorted(measures.items())),
        "examples_metadata_only": examples,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    source, attempt = args.source.resolve(strict=True), args.attempt.resolve(
        strict=True
    )
    if not (attempt / "results/comparison.json").is_file():
        raise ValueError("missing completed comparison")
    cmp = load_unique((attempt / "results/comparison.json").read_text())
    if (
        cmp.get("status")
        not in (
            "COMPLETED_COMPARATIVE_SCREEN_NO_SCIENTIFIC_PROMOTION",
            "COMPLETED_SCREEN_GPU_EVIDENCE_INCOMPLETE",
        )
        or cmp.get("actual_generate_requests") != 75
    ):
        raise ValueError("comparison incomplete; original attempt preserved")
    if (attempt / "results/exit.code").read_text().strip() != "0":
        raise ValueError("comparison exit not zero")
    head = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if head != SOURCE_PIN:
        raise ValueError("source checkout is not at the exact FW00412 pinned commit")
    dirty = subprocess.run(
        ["git", "-C", str(source), "status", "--porcelain", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    if dirty:
        raise ValueError(
            "source checkout changed; replay requires original pinned files"
        )
    sys.path.insert(0, str(source / "packages/fw00412"))
    broker = importlib.import_module("broker")
    specialists = importlib.import_module("specialists")
    graph, sources, _, _ = broker.checked_environment()
    tasks = broker.fixtures.cases()
    output = []
    for index, model_info in enumerate(cmp["models"], 1):
        path = attempt / f"results/model-{index:02d}/raw-local.jsonl"
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != model_info["raw_log_sha256"]:
            raise ValueError("raw ledger changed: model " + str(index))
        report = summarize_file(path, tasks, graph, sources, broker, specialists)
        if report["model"] != model_info["name"]:
            raise ValueError("model identity mismatch")
        output.append(report)
    print(
        json.dumps(
            {
                "schema": "fw00412.role-shadow-replay.v1",
                "scope": "OFFLINE_DIAGNOSTIC_NOT_NEW_SCIENTIFIC_GRADE",
                "original_attempt": str(attempt),
                "original_source_pin": SOURCE_PIN,
                "does_not_modify_original_scores": True,
                "models": output,
            },
            sort_keys=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
