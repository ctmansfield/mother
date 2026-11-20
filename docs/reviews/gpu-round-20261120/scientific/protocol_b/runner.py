#!/usr/bin/env python3
"""Protocol B: explicit specialist role, unchanged scientific cases and strict judge.

Read-only preflight by default. --live: 3 installed Ollama candidates x 15
original FW00412 cases, serialized under the existing cooperative GPU lock.
No weights, deployment, scientific claims, source or baseline grades changed.
"""
import argparse
from collections import Counter
import fcntl
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import sys
import time

HERE = Path(__file__).resolve().parent
SCI = HERE.parent
BEHAVIOR = SCI.parent / "behavior"
ROOT = HERE.parents[4]
sys.path.insert(0, str(SCI))
sys.path.insert(0, str(BEHAVIOR))
import scientific_compare as sc  # noqa: E402
import behavior_compare as bc  # noqa: E402

CANDIDATES = ("deepseek-r1:14b", "medgemma:27b", "medgemma1.5:4b")
MARKER = "RESEARCH INPUT (UNTRUSTED SOURCE TEXT):\n"
BUDGET_SECONDS = 8000


def digest(data):
    return hashlib.sha256(data).hexdigest()


def revised_prompt(original, graph, sources, task):
    """Only the role identification changes; all original evidence stays visible."""
    role = task["role"]
    old = original(graph, sources, task)
    intro = "You are a RESEARCH-SCREENING candidate for " + role + "."
    if old.count(intro) != 1 or old.count(MARKER) != 1:
        raise ValueError("FW00412 original prompt template changed")
    heading, raw = old.split(MARKER, 1)
    evidence = sc.unique_json(raw)
    if not isinstance(evidence, dict) or set(evidence) != {"edge", "source", "question"}:
        raise ValueError("FW00412 source input envelope changed")
    evidence["assigned_specialist_role"] = role
    replacement = (
        "You are a scientific evidence analyst. Your assigned specialist role "
        "is exactly " + role + ". For the output JSON key role, copy exactly "
        "the assigned_specialist_role value from the RESEARCH INPUT. Do not "
        "write RESEARCH-SCREENING, the graph edge kind or any graph node ID. "
        "Only this role identity instruction is revised. Every original "
        "evidence, quotation, retraction, causality and abstention constraint remains."
    )
    result = heading.replace(intro, replacement) + MARKER + json.dumps(evidence, sort_keys=True, ensure_ascii=False)
    if any(item in result for item in ('"expected_decision"', '"expected_quote"', '"expected_polarity"')):
        raise ValueError("protected answer leaked into protocol B input")
    if len(result) > 14000:
        raise ValueError("protocol B prompt exceeds original length budget")
    return result


def source_gate():
    head = sc.command(["git", "-C", str(ROOT), "rev-parse", "HEAD"])
    if not re.fullmatch("[a-f0-9]{40}", head):
        raise ValueError("immutable MOTHER source pin required")
    if sc.command(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=all"]):
        raise ValueError("MOTHER source checkout dirty")
    for line in (HERE / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split(None, 1)
        file = HERE / name.lstrip(" *")
        if file.is_symlink() or not file.resolve().is_relative_to(HERE.resolve()) or digest(file.read_bytes()) != expected:
            raise ValueError("Protocol B manifest mismatch: " + name)
    return head


def source_and_baseline(baseline, framework):
    sc.check_source(framework)
    sc.check_offline(Path.home() / ".local/state/mother-fw00412" / ("offline-" + sc.PIN[:12]))
    proof = bc.check_scientific_predecessor(baseline / "results")
    if proof["validated_generate_requests"] != 75 or proof["validated_gpu_residency_observations"] != 75:
        raise ValueError("Baseline A must have 75 matched GPU observations")
    sys.path.insert(0, str(framework / "packages/fw00412"))
    broker = importlib.import_module("broker")
    all_models = sc.freeze_models(sc.local_api())
    selected = [next((m for m in all_models if m["name"] == name), None) for name in CANDIDATES]
    if any(m is None for m in selected):
        raise ValueError("a frozen Protocol B candidate is not installed")
    previous = {m["name"]: m for m in proof["models"]}
    if any(previous[m["name"]]["digest"] != m["digest"] for m in selected):
        raise ValueError("model digest changed since Baseline A")
    return broker, selected, proof


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--framework", type=Path, required=True)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--gpu-idle-confirmed", action="store_true")
    args = parser.parse_args(argv)
    os.umask(0o077)
    sys.dont_write_bytecode = True
    commit = source_gate()
    broker, models, prior = source_and_baseline(
        args.baseline.expanduser().absolute(), args.framework.expanduser().absolute())
    graph, sources, _, _ = broker.checked_environment()
    tasks = broker.fixtures.cases()
    if len(tasks) != 15:
        raise ValueError("protected task count changed")
    original = broker.s.prompt
    for task in tasks:
        revised_prompt(original, graph, broker.with_retraction(sources, task), task)
    api = sc.local_api()
    first_gpu = sc.idle_snapshot(api)
    preliminary = {
        "schema":"fw00412.protocol-b-preflight.v1",
        "prompt":"B_EXPLICIT_ASSIGNED_SPECIALIST_ROLE",
        "grader":"UNCHANGED_FW00412",
        "original_tasks":"UNCHANGED_15",
        "mother_source":commit,
        "framework_source":sc.PIN,
        "baseline_proof":prior,
        "models":models,
        "planned_requests":45,
        "initial_gpu":first_gpu,
        "protocol_b_code_sha256":digest(Path(__file__).read_bytes()),
        "inference_calls_preflight":0,
        "approval":"EXPERIMENT_ONLY_NO_ROLE_ASSIGNMENT"
    }
    print(json.dumps(preliminary, sort_keys=True, indent=2), flush=True)
    if not args.live:
        print("PREFLIGHT_ONLY_ZERO_MODEL_GENERATION_CALLS")
        return 0
    if args.state is None or not args.gpu_idle_confirmed:
        raise ValueError("--live requires --state and confirmed GPU idleness")
    state = args.state.expanduser().absolute()
    if state.exists() or state.is_symlink():
        raise ValueError("new private attempt directory required")
    sc.private_state_parent(state.parent)
    locker = Path.home() / ".local/state/mother-fw00412"
    sc.private_state_parent(locker)
    fd = os.open(locker / "scientific-gpu.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    deadline = time.monotonic() + 8000
    with os.fdopen(fd, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        sc.idle_snapshot(api)
        inventory = sc.freeze_models(api)
        if any(m not in inventory for m in models):
            raise ValueError("candidate digest changed between preflight and launch")
        state.mkdir(mode=0o700)
        sc.write_json(state / "preflight.json", preliminary)
        outcome = {
            "schema":"fw00412.protocol-b-comparison.v1",
            "status":"RUNNING",
            "prompt":"B_EXPLICIT_ASSIGNED_SPECIALIST_ROLE",
            "grader":"UNCHANGED_FW00412",
            "mother_source":commit,
            "framework_source":sc.PIN,
            "baseline_comparison_sha256":prior["comparison_sha256"],
            "planned_requests":45,
            "models":[],
            "scientific_truth":"NOT_ESTABLISHED",
            "role_assignment":"NOT_ASSIGNED",
            "publication":"NOT_PUBLISHED"
        }
        active = None
        observer = None
        preceding = None
        failure = None
        try:
            for index, model in enumerate(models, 1):
                if time.monotonic() >= deadline:
                    raise ValueError("Protocol B campaign budget exhausted")
                sc.settle_idle(api, sc.nvidia_snapshot, preceding, seconds=12)
                if model not in sc.freeze_models(api):
                    raise ValueError("candidate model digest changed during experiment")
                folder = state / ("model-%02d" % index)
                folder.mkdir(mode=0o700)
                (folder / "source-pin.txt").write_text(sc.PIN + "\n")
                observer = sc.ObservedAPI(api, model["name"], model["digest"],
                    state / ("telemetry-%02d.jsonl" % index),
                    max_requests=15, deadline=deadline)
                active = model
                roster = sc.roster_for(broker, model)
                print("START PROTOCOL B %d/3 %s" % (index, model["name"]), flush=True)
                broker.s.prompt = lambda g, s, t: revised_prompt(original, g, s, t)
                try:
                    report = broker.run(folder, sc.PIN, roster, api=observer)
                finally:
                    broker.s.prompt = original
                entry = {
                    **model,
                    "actual_requests":len(observer.records),
                    "task_slots":report["model_requests"],
                    "roles":report["roles"],
                    "gpu_evidence_counts":dict(Counter(r["gpu_evidence"] for r in observer.records)),
                    "raw_log_sha256":report["raw_log_sha256"],
                    "hold":observer.hold
                }
                outcome["models"].append(entry)
                print(json.dumps(entry, sort_keys=True), flush=True)
                active = None
                preceding = model
                if observer.hold:
                    raise ValueError("GPU/HTTP observer held campaign: " + observer.hold)
            sc.settle_idle(api, sc.nvidia_snapshot, preceding, seconds=12)
            outcome["status"] = "COMPLETED_STRICT_SCORED_NO_PROMOTION"
        except (Exception, KeyboardInterrupt) as error:
            failure = type(error).__name__ + ": " + str(error)
            outcome["status"] = "HELD_KEEP_ALL_EVIDENCE"
            outcome["failure"] = failure[:400]
            if active is not None:
                outcome["models"].append({
                    **active, "status":"INCOMPLETE",
                    "actual_requests":len(observer.records) if observer else 0,
                    "gpu_evidence_counts":dict(Counter(
                        r.get("gpu_evidence","UNOBSERVED") for r in observer.records)) if observer else {}
                })
        finally:
            broker.s.prompt = original
        outcome["actual_requests"] = sum(m["actual_requests"] for m in outcome["models"])
        outcome["gpu_evidence_counts"] = dict(sum((
            Counter(m["gpu_evidence_counts"]) for m in outcome["models"]
        ), Counter()))
        outcome["all_gpu_observed"] = (
            outcome["actual_requests"] == 45 and
            outcome["gpu_evidence_counts"].get("GPU_RESIDENT_OBSERVED") == 45)
        if failure is None and not outcome["all_gpu_observed"]:
            outcome["status"] = "COMPLETED_GPU_EVIDENCE_INCOMPLETE"
        sc.write_json(state / "comparison.json", outcome)
        exit_code = 4 if failure or not outcome["all_gpu_observed"] else 0
        (state / "exit.code").write_text(str(exit_code) + "\n")
        print("STATUS:", outcome["status"], "\nLOCAL EVIDENCE:", state, flush=True)
        return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
        print("REFUSED:", type(error).__name__, str(error)[:250], file=sys.stderr)
        raise SystemExit(2)
