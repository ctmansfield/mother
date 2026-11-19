#!/usr/bin/env python3
"""Run the 120-request behavioral comparison after a proven scientific screen.

Read-only preflight is the default. --live is required for inference. Reuses
the unchanged scientific loopback transport, GPU observer and cooperative lock.
"""
import argparse
import collections
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import time

HERE = Path(__file__).resolve().parent
SCIENTIFIC = HERE.parent / "scientific"
sys.path.insert(0, str(SCIENTIFIC))
import scientific_compare as scientific
try:
    from . import adapter
except ImportError:
    import adapter

TOTAL_SECONDS = 20000
require = scientific.require


def private_bytes(path, limit=16 * 1024 * 1024):
    path = Path(path)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and not path.is_symlink() and info.st_uid == os.geteuid()
            and not info.st_mode & 0o077 and info.st_size <= limit, "unsafe or oversized predecessor file: " + path.name)
    return path.read_bytes()


def read_json(path):
    return scientific.unique_json(private_bytes(path))


def private_directory(path):
    path = Path(path).absolute()
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and not path.is_symlink() and info.st_uid == os.geteuid()
            and not info.st_mode & 0o077, "predecessor directory must be operator-owned and private")
    return path


def check_scientific_predecessor(path):
    """Validate retained scientific proof only: no HTTP, GPU or model calls.

    Returns the ordered frozen models and source/report hashes. Native launchers
    may reuse this gate. A completed summary without its raw proof is refused.
    """
    path = private_directory(path)
    comparison_bytes = private_bytes(path / "comparison.json")
    result = scientific.unique_json(comparison_bytes)
    preflight_bytes = private_bytes(path / "preflight.json")
    before = scientific.unique_json(preflight_bytes)
    require(private_bytes(path / "exit.code").strip() == b"0", "scientific predecessor did not exit successfully")
    require(result.get("schema") == "fw00412.comparative-reasoning-screen.v1"
            and result.get("source_pin") == scientific.PIN, "scientific predecessor schema/source differs")
    require(result.get("status") == "COMPLETED_COMPARATIVE_SCREEN_NO_SCIENTIFIC_PROMOTION"
            and result.get("actual_generate_requests") == 75 and result.get("completed_model_batches") == 5
            and result.get("all_75_requests_have_gpu_residency_observed") is True
            and result.get("gpu_evidence_counts") == {"GPU_RESIDENT_OBSERVED": 75}
            and not result.get("failure"), "scientific predecessor is held, incomplete, or lacks all75 GPU observations")
    require(before.get("schema") == "fw00412.comparison-preflight.v1" and before.get("source_pin") == scientific.PIN,
            "scientific predecessor preflight differs")
    require(before.get("wrapper_sha256") == scientific.sha((SCIENTIFIC / "scientific_compare.py").read_bytes())
            and before.get("candidate_config_sha256") == scientific.sha((SCIENTIFIC / "candidates.json").read_bytes()),
            "scientific predecessor wrapper/candidates differ from this reviewed source")
    models = before.get("models")
    require(isinstance(models, list) and len(models) == 5 and [m.get("name") for m in models] == list(scientific.TAGS),
            "scientific predecessor candidate order differs")
    require(all(isinstance(m.get("digest"), str) and scientific.HEX64.fullmatch(m["digest"]) for m in models),
            "scientific predecessor requires full model digests")
    summaries = result.get("models")
    require(isinstance(summaries, list) and len(summaries) == 5, "scientific predecessor model summaries incomplete")
    common_sequence = None
    for index, (model, summary) in enumerate(zip(models, summaries), 1):
        require(summary.get("name") == model["name"] and summary.get("digest") == model["digest"]
                and summary.get("actual_generate_requests") == 15 and summary.get("broker_task_slots") == 15
                and summary.get("gpu_evidence_counts") == {"GPU_RESIDENT_OBSERVED": 15}
                and summary.get("hold") is None and summary.get("trial_directory") == f"model-{index:02d}",
                "scientific predecessor model identity/count/hold differs")
        trial = private_directory(path / f"model-{index:02d}")
        raw_bytes = private_bytes(trial / "raw-local.jsonl")
        require(scientific.sha(raw_bytes) == summary.get("raw_log_sha256"), "scientific raw ledger hash differs")
        raw = [scientific.unique_json(line) for line in raw_bytes.splitlines()]
        telemetry = [scientific.unique_json(line) for line in private_bytes(path / f"telemetry-{index:02d}.jsonl").splitlines()]
        attempts = [scientific.unique_json(line) for line in private_bytes(path / f"telemetry-{index:02d}.attempts.jsonl").splitlines()]
        require(len(raw) == len(telemetry) == len(attempts) == 15, "scientific raw/telemetry/attempt count differs")
        sequence = []
        for ordinal, (row, observed, intent) in enumerate(zip(raw, telemetry, attempts), 1):
            require(row.get("model") == model["name"] and row.get("model_digest") == model["digest"]
                    and row.get("source_pin") == scientific.PIN, "scientific raw source/model identity differs")
            request = observed.get("request", {})
            reply = observed.get("response", {})
            require(observed.get("ordinal") == intent.get("ordinal") == ordinal
                    and observed.get("model") == intent.get("model") == model["name"]
                    and observed.get("digest") == intent.get("digest") == model["digest"]
                    and observed.get("http_attempted") is True and observed.get("hold") is None
                    and observed.get("error") is None, "scientific request proof is incomplete or held")
            require(isinstance(request, dict) and request == intent.get("request")
                    and request.get("model") == model["name"] and isinstance(request.get("prompt"), str),
                    "scientific request intent differs from observed call")
            prompt_sha = scientific.sha(request["prompt"].encode())
            require(observed.get("prompt_sha256") == intent.get("prompt_sha256") == prompt_sha,
                    "scientific request prompt hash differs")
            require(row.get("prompt_sha256") in (None, prompt_sha), "scientific raw prompt differs from observed call")
            require(isinstance(reply, dict) and reply.get("model") == model["name"] and reply.get("done") is True,
                    "scientific completion acknowledgement missing")
            if row.get("error_class") is None:
                require(isinstance(reply.get("response"), str) and row.get("response") == reply["response"]
                        and row.get("response_sha256") == scientific.sha(reply["response"].encode()),
                        "scientific raw answer differs from completed telemetry response")
            require(observed.get("gpu_evidence") == "GPU_RESIDENT_OBSERVED"
                    and scientific.classify(observed.get("samples", []), model["name"], model["digest"]) == "GPU_RESIDENT_OBSERVED",
                    "scientific matching positive-VRAM observation missing")
            seed = request.get("options", {}).get("seed")
            require(type(seed) is int and observed.get("seed") == seed, "scientific request seed proof differs")
            sequence.append((row.get("case_id"), prompt_sha, seed))
        require({item[2] for item in sequence} == set(range(20261119, 20261134)), "scientific case seeds differ")
        require(len({item[0] for item in sequence}) == 15, "scientific cases repeat")
        require(common_sequence is None or sequence == common_sequence, "scientific candidates did not receive identical cases/prompts/seeds")
        common_sequence = sequence
    return {"path": str(path), "source_pin": scientific.PIN, "models": models,
            "comparison_sha256": scientific.sha(comparison_bytes), "preflight_sha256": scientific.sha(preflight_bytes),
            "validated_generate_requests": 75, "validated_gpu_residency_observations": 75,
            "status": "COMPLETED_SCIENTIFIC_PREDECESSOR_VERIFIED"}


def check_source():
    root = Path(scientific.command(["git", "-C", str(HERE), "rev-parse", "--show-toplevel"]))
    pin = scientific.command(["git", "-C", str(root), "rev-parse", "HEAD"])
    require(re.fullmatch(r"[0-9a-f]{40}", pin), "full MOTHER source commit required")
    require(not scientific.command(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"]),
            "MOTHER source checkout must be clean")
    for base in (HERE, SCIENTIFIC):
        for line in (base / "SHA256SUMS").read_text().splitlines():
            expected, name = line.split(None, 1)
            path = base / name.lstrip(" *")
            require(path.resolve().is_relative_to(base) and not path.is_symlink()
                    and scientific.HEX64.fullmatch(expected) and scientific.sha(path.read_bytes()) == expected,
                    "source manifest mismatch: " + name)
    _, _, pack_sha = adapter.benchmark.load_pack()
    return {"source_pin": pin, "root": str(root), "pack_sha256": pack_sha,
            "wrapper_sha256": scientific.sha(Path(__file__).read_bytes())}


def run_campaign(state, source, predecessor, api, *, nvidia=scientific.nvidia_snapshot,
                 deadline=None, poll_seconds=0.2, lock_path=None):
    deadline = deadline if deadline is not None else time.monotonic() + TOTAL_SECONDS
    state = Path(state).absolute()
    require(not state.exists() and not state.is_symlink(), "previous behavioral campaign preserved")
    scientific.private_state_parent(state.parent)
    lock_path = Path(lock_path) if lock_path is not None else Path.home() / ".local/state/mother-fw00412/scientific-gpu.lock"
    scientific.private_state_parent(lock_path.parent)
    models = predecessor["models"]
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        initial_gpu = scientific.idle_snapshot(api, nvidia)
        require(scientific.freeze_models(api) == models, "installed candidate digests differ from scientific predecessor")
        state.mkdir(mode=0o700)
        scientific.write_json(state / "preflight.json", {"schema": "fw00413.behavior-comparison-preflight.v1",
            **source, "scientific_predecessor": predecessor, "initial_gpu": initial_gpu,
            "maximum_generate_requests": 120, "cases_per_model": 24, "request_timeout_seconds": 120,
            "request_wall_seconds": 135, "total_wall_budget_seconds": TOTAL_SECONDS,
            "candidate_order": [m["name"] for m in models], "same_prompts_order_seeds": True})
        result = {"schema": "fw00413.behavior-comparison.v1", **source, "scientific_predecessor": predecessor,
            "status": "RUNNING", "maximum_generate_requests": 120, "models": [],
            "scientific_truth": "NOT_ESTABLISHED", "role_assignment": "NOT_ASSIGNED",
            "publication": "NOT_PUBLISHED", "rationale_review": "NOT_PERFORMED",
            "gpu_evidence_meaning": "Matching positive size_vram during request; residency/offload, not all computation on GPU",
            "concurrency_limit": "Shared cooperative package lock and contention checks; no global GPU reservation"}
        failure = None
        observer = None
        active = None
        previous = None
        try:
            for index, model in enumerate(models, 1):
                require(time.monotonic() < deadline, "behavioral total wall-clock budget exhausted")
                scientific.settle_idle(api, nvidia, previous, seconds=max(0, min(12, deadline - time.monotonic())))
                require(scientific.freeze_models(api) == models, "candidate digest changed between behavioral batches")
                trial = state / f"model-{index:02d}"
                observer = scientific.ObservedAPI(api, model["name"], model["digest"], state / f"telemetry-{index:02d}.jsonl",
                            nvidia=nvidia, poll_seconds=poll_seconds, max_requests=24, deadline=deadline)
                active = {**model, "trial_directory": trial.name}

                def call(name, prompt, options):
                    reply = observer("/api/generate", {"model": name, "prompt": prompt, "options": options,
                                     "stream": False, "format": "json", "keep_alive": "0s"}, timeout=120)
                    require(not observer.hold, "external observer held further inference")
                    return reply

                print(f"START {index}/5 {model['name']} — 24 identical behavioral cases", flush=True)
                summary = adapter.run_model(trial, model["name"], model["digest"], source["source_pin"], call, seed=20261120)
                result["models"].append({**active, "actual_generate_requests": len(observer.records),
                    "gpu_evidence_counts": dict(collections.Counter(row.get("gpu_evidence", "INTERRUPTED_UNOBSERVED") for row in observer.records)),
                    "hold": observer.hold, "adapter_summary": summary})
                active = None
                previous = model
                print(json.dumps({"model": model["name"], "complete": summary["complete"],
                                  "actual_generate_requests": len(observer.records), "gpu_evidence_counts": result["models"][-1]["gpu_evidence_counts"]}), flush=True)
                require(not observer.hold and summary["complete"] and not summary["fatal_hold"],
                        "behavioral candidate held; review raw and telemetry before another run")
            require(scientific.freeze_models(api) == models, "candidate digest changed at campaign end")
            scientific.settle_idle(api, nvidia, previous, seconds=max(0, min(12, deadline - time.monotonic())))
            result["status"] = "COMPLETED_BEHAVIORAL_SCREEN_NO_ROLE_ASSIGNMENT"
        except (Exception, KeyboardInterrupt) as error:
            failure = type(error).__name__ + ": " + str(error)
            result["status"] = "HELD_REVIEW_LOCAL_EVIDENCE_NO_AUTOMATIC_RETRY"
            result["failure"] = failure
            if active is not None and observer is not None:
                result["models"].append({**active, "actual_generate_requests": len(observer.records),
                    "status": "INCOMPLETE_REVIEW_RAW_AND_ATTEMPT_LOGS", "hold": observer.hold,
                    "gpu_evidence_counts": dict(collections.Counter(row.get("gpu_evidence", "INTERRUPTED_UNOBSERVED") for row in observer.records))})
        result["actual_generate_requests"] = sum(model["actual_generate_requests"] for model in result["models"])
        result["completed_model_batches"] = sum(model.get("adapter_summary", {}).get("complete") is True for model in result["models"])
        result["gpu_evidence_counts"] = dict(sum((collections.Counter(model["gpu_evidence_counts"]) for model in result["models"]), collections.Counter()))
        result["all_120_requests_have_gpu_residency_observed"] = result["actual_generate_requests"] == 120 and result["gpu_evidence_counts"].get("GPU_RESIDENT_OBSERVED") == 120
        if not failure and not result["all_120_requests_have_gpu_residency_observed"]:
            result["status"] = "COMPLETED_BEHAVIORAL_SCREEN_GPU_EVIDENCE_INCOMPLETE"
        scientific.write_json(state / "comparison.json", result)
        (state / "exit.code").write_text("4\n" if failure else "0\n")
        print("LOCAL RESULTS: " + str(state) + "\nSTATUS: " + result["status"], flush=True)
        return 4 if failure else 0


def main(argv=None):
    deadline = time.monotonic() + TOTAL_SECONDS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--after-scientific", required=True, type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--gpu-idle-confirmed", action="store_true")
    args = parser.parse_args(argv)
    os.umask(0o077)
    sys.dont_write_bytecode = True
    source = check_source()
    predecessor = check_scientific_predecessor(args.after_scientific)
    api = scientific.local_api()
    require(scientific.freeze_models(api) == predecessor["models"], "installed candidate digests differ from scientific predecessor")
    gpu = scientific.idle_snapshot(api)
    if not args.live:
        print(json.dumps({"status": "PREFLIGHT_ONLY_ZERO_INFERENCE_REQUESTS", "source": source,
                         "scientific_predecessor": predecessor, "gpu": gpu}, sort_keys=True, indent=2))
        return 0
    require(args.gpu_idle_confirmed and args.state is not None, "--live requires --state and --gpu-idle-confirmed")
    return run_campaign(args.state, source, predecessor, api, deadline=deadline)


if __name__ == "__main__":
    def interrupted(signum, frame):
        raise KeyboardInterrupt("signal received; server completion may be ambiguous; preserve evidence")
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGHUP, interrupted)
    try:
        raise SystemExit(main())
    except (Exception, KeyboardInterrupt) as error:
        print("REFUSED: " + type(error).__name__ + ": " + str(error), file=sys.stderr)
        raise SystemExit(2)
