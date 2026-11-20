#!/usr/bin/env python3
"""Bounded, no-post comparative wrapper around the unchanged pinned FW00412 broker.

Only --live issues inference. All five installed tags and full digests must pass
before any request. Same 15 cases/seeds per candidate. No pulls, retries, unloads,
process termination, role promotion, or remote publication. GPU residency is
observed while each request is active; it is not a utilization claim.
"""
import argparse
import collections
import csv
import fcntl
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import threading
import time
import urllib.request

PIN = "ba6fbb90c031f122b7db61d2f67f2b22ef1cf130"
RECEIPT = "https://github.com/ctmansfield/production-framework/issues/139#issuecomment-7009907399"
OFFLINE_SHA = "08dbef588a51aba1640038628a832a4d646cdefec7fd964072d6fd71c26d694f"
TAGS = ("gpt-oss:20b", "medgemma1.5:4b", "medgemma:27b", "deepseek-r1:14b", "ministral-3:14b")
TOTAL_SECONDS = 12000
HEX64 = re.compile(r"^[0-9a-f]{64}$")
BLOBS = {
    "packages/fw00410/scientific.py": "521261fe0a8f9ba09f152f95319d705283d9aba7",
    "packages/fw00411/scout.py": "302aea4628397450257322c466ead74454d0ceb1",
    "packages/fw0048/evidence.py": "dd850a871954ada337ccd73af6dc0b04ee16f049",
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def unique_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


class RejectRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("local Ollama redirects are refused")


def local_api():
    """Fixed loopback transport: ignore proxy environment and refuse redirects."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), RejectRedirect())

    def api(path, payload=None, timeout=10):
        require(path in ("/api/ps", "/api/tags", "/api/generate"), "unapproved local Ollama endpoint")
        require((path == "/api/generate") == (payload is not None), "endpoint method/payload differs")
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request("http://127.0.0.1:11434" + path, data=body,
                  method="POST" if payload is not None else "GET", headers={"Content-Type": "application/json"})
        with opener.open(request, timeout=timeout) as response:
            require(response.status == 200, "local Ollama API returned non-200")
            raw = response.read(180001)
            require(len(raw) <= 180000, "local Ollama response over budget")
            return unique_json(raw)
    return api


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as dest:
        json.dump(value, dest, sort_keys=True, indent=2)
        dest.write("\n")
        dest.flush()
        os.fsync(dest.fileno())


def append_json(path, value):
    with Path(path).open("a", encoding="utf-8") as dest:
        dest.write(json.dumps(value, sort_keys=True) + "\n")
        dest.flush()
        os.fsync(dest.fileno())


def command(args, timeout=15):
    result = subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)
    require(result.returncode == 0, f"read-only command failed: {args[0]}: {result.stderr.strip()[:240]}")
    return result.stdout.strip()


def check_source(checkout):
    require(checkout.is_dir() and not checkout.is_symlink(), "checkout must be a real directory")
    require(command(["git", "-C", str(checkout), "rev-parse", "HEAD"]) == PIN, "exact FW00412 HEAD pin required")
    require(not command(["git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=all"]), "FW00412 checkout must be clean")
    for name, expected in BLOBS.items():
        require(command(["git", "-C", str(checkout), "hash-object", name]) == expected, "inherited source blob mismatch: " + name)
    for component in ("fw00410", "fw00411", "fw00412"):
        base = checkout / "packages" / component
        for line in (base / "SHA256SUMS").read_text().splitlines():
            expected, name = line.split(None, 1)
            path = base / name.lstrip(" *")
            require(path.resolve().is_relative_to(base.resolve()) and not path.is_symlink(), "unsafe manifest path")
            require(HEX64.fullmatch(expected) and sha(path.read_bytes()) == expected, "source manifest mismatch: " + str(path))


def check_offline(prior):
    require((prior / "source-pin.txt").read_text().strip() == PIN, "offline qualification source pin differs")
    require((prior / "exit.code").read_text().strip() == "0", "offline qualification did not pass")
    require((prior / "github-return-url.txt").read_text().strip() == RECEIPT, "expected offline host receipt required")
    require(sha((prior / "summary.json").read_bytes()) == OFFLINE_SHA, "offline summary differs from reviewed host receipt")
    return {"path": str(prior), "receipt": RECEIPT, "summary_sha256": OFFLINE_SHA}


def load_candidates(path):
    data = unique_json(path.read_bytes())
    require(isinstance(data, dict) and set(data) == {"schema", "source_pin", "scope", "models"}, "candidate configuration fields differ")
    require(data["schema"] == "fw00412.comparative-candidates.v1" and data["source_pin"] == PIN, "candidate configuration source/schema differs")
    require(data["models"] == list(TAGS), "reviewed five-candidate order differs; review changes before a new experiment")
    require(isinstance(data["scope"], str) and 12 <= len(data["scope"]) <= 400, "candidate scope required")
    return data


def freeze_models(api):
    inventory = api("/api/tags")
    require(isinstance(inventory, dict) and isinstance(inventory.get("models"), list), "malformed installed inventory")
    found = {}
    for row in inventory["models"]:
        require(isinstance(row, dict), "malformed inventory row")
        tag = row.get("name")
        if tag in TAGS:
            require(tag not in found, "duplicate candidate inventory tag: " + tag)
            digest = row.get("digest")
            require(isinstance(digest, str) and HEX64.fullmatch(digest), "full installed digest required: " + tag)
            found[tag] = digest
    require(set(found) == set(TAGS), "missing installed candidates: " + ", ".join(tag for tag in TAGS if tag not in found))
    return [{"name": tag, "digest": found[tag]} for tag in TAGS]


def nvidia_snapshot():
    gpu = command(["nvidia-smi", "--query-gpu=uuid,name,memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"], timeout=5)
    processes = command(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory", "--format=csv,noheader,nounits"], timeout=5)
    require(bool(gpu), "nvidia-smi reported no GPU")
    gpus = [dict(zip(("uuid", "name", "memory_total_mib", "memory_used_mib", "utilization_percent"), [cell.strip() for cell in row])) for row in csv.reader(io.StringIO(gpu))]
    rows = []
    for row in csv.reader(io.StringIO(processes)):
        require(len(row) == 4, "unparseable NVIDIA compute process row")
        rows.append(dict(zip(("gpu_uuid", "pid", "process_name", "used_gpu_memory_mib"), [cell.strip() for cell in row])))
    return {"gpus": gpus, "compute_processes": rows}


def ps_models(api):
    response = api("/api/ps", timeout=2)
    require(isinstance(response, dict) and isinstance(response.get("models"), list), "malformed Ollama residency response")
    require(all(isinstance(row, dict) for row in response["models"]), "malformed Ollama residency row")
    return response["models"]


def idle_snapshot(api, nvidia=nvidia_snapshot):
    loaded = ps_models(api)
    gpu = nvidia()
    require(not loaded, "Ollama is already occupied; no inference started")
    require(not gpu["compute_processes"], "GPU compute process already active; no inference started")
    return gpu


def trusted_ollama_gpu_process(process):
    """Permit the observed Ollama runner only; preserve one-PID GPU exclusion."""
    name = process.get("process_name")
    pid = process.get("pid")
    if not isinstance(name, str) or not name or not isinstance(pid, str) or not pid.isdecimal() or int(pid) <= 0:
        return False
    if name == "/usr/local/lib/ollama/llama-server":
        return True
    return Path(name).name in ("ollama", "ollama_llama_server")


def unattributed_processes(processes):
    return any(not trusted_ollama_gpu_process(p) for p in processes) or len({p["pid"] for p in processes}) > 1


def settle_idle(api, nvidia, previous=None, seconds=12):
    """Allow only our previous known candidate a bounded natural unload interval."""
    end = time.monotonic() + seconds
    while True:
        loaded, gpu = ps_models(api), nvidia()
        processes = gpu["compute_processes"]
        if not loaded and not processes:
            return gpu
        require(previous is not None, "GPU/Ollama already occupied")
        require(all(row.get("name", row.get("model")) == previous["name"] and row.get("digest") == previous["digest"] for row in loaded), "foreign or changed Ollama model occupied GPU")
        require(not unattributed_processes(processes), "unattributed or multiple GPU compute processes occupied GPU")
        require(time.monotonic() < end, "previous candidate did not naturally unload within bounded wait")
        time.sleep(0.2)


def native_inventory(home):
    cache = Path("/mnt/llmstore/caches/hf/chad/hub")
    tx = cache / "models--google--txgemma-9b-chat" / "snapshots" / "bc45665ceb345eea6acfc44d82706e8d8b689209"
    return {
        "status": "EXISTENCE_ONLY_NOT_RUNTIME_OR_GPU_QUALIFICATION",
        "venv_python_exists": {name: (home / "ai-envs" / name / "bin" / "python").exists() for name in ("medcpt", "txgemma", "boltz2", "timeseries")},
        "txgemma_snapshot": {"path": str(tx), "exists": tx.is_dir(), "safetensors_shards_present": len(list(tx.glob("*.safetensors"))) if tx.is_dir() else 0},
        "medcpt_cache_exists": {name: (cache / name).is_dir() for name in ("models--ncbi--MedCPT-Query-Encoder", "models--ncbi--MedCPT-Article-Encoder")},
        "native_capability_tests": "SEPARATE_ROUND_REQUIRED",
    }


def classify(samples, model, digest):
    values = [row.get("size_vram") for sample in samples for row in sample.get("models", [])
              if row.get("name", row.get("model")) == model and row.get("digest") == digest]
    numeric = [value for value in values if isinstance(value, int) and not isinstance(value, bool) and value >= 0]
    if any(value > 0 for value in numeric):
        return "GPU_RESIDENT_OBSERVED"
    if values and len(values) == len(numeric) and all(value == 0 for value in numeric):
        return "CPU_RESIDENT_OBSERVED"
    return "UNOBSERVED"


class ObservedAPI:
    """Keep original requests intact, add during-request residency observations."""
    def __init__(self, api, model, digest, path, nvidia=nvidia_snapshot, poll_seconds=0.2,
                 max_requests=15, deadline=None):
        self.api, self.model, self.digest, self.path = api, model, digest, Path(path)
        self.nvidia, self.poll_seconds = nvidia, poll_seconds
        self.max_requests = max_requests
        self.deadline = deadline if deadline is not None else time.monotonic() + TOTAL_SECONDS
        self.records = []
        self.hold = None

    def __call__(self, path, payload=None, timeout=10):
        if path != "/api/generate":
            return self.api(path, payload, timeout=timeout)
        if self.hold:
            raise ValueError("further inference held: " + self.hold)
        require(payload["model"] == self.model, "unexpected candidate request")
        if len(self.records) >= self.max_requests or time.monotonic() >= self.deadline:
            self.hold = "candidate request or total campaign wall-clock budget exhausted"
            raise ValueError(self.hold)
        # Every call gets an idle snapshot; keep_alive=0 normally unloads before
        # the next request. A busy snapshot refuses without unloading anything.
        try:
            settle_idle(self.api, self.nvidia, {"name": self.model, "digest": self.digest} if self.records else None,
                        seconds=max(0, min(12, self.deadline - time.monotonic())))
        except Exception as ex:
            self.hold = "pre_request_idle_check: " + str(ex)
            raise ValueError(self.hold) from ex
        event, box = threading.Event(), {}
        rec = {"ordinal": len(self.records) + 1, "model": self.model, "digest": self.digest,
               "prompt_sha256": sha(payload["prompt"].encode()), "seed": payload.get("options", {}).get("seed"),
               "request": payload, "samples": [], "nvidia_samples": [], "monitor_errors": [],
               "http_attempted": True, "response": None, "error": None}
        started = time.monotonic()
        # Write intent before sending. A killed/interrupted process cannot erase
        # the fact that server completion may be ambiguous.
        append_json(self.path.with_suffix(".attempts.jsonl"), {"ordinal": rec["ordinal"], "model": self.model,
                    "digest": self.digest, "prompt_sha256": rec["prompt_sha256"], "request": payload,
                    "status": "REQUEST_ABOUT_TO_BE_SENT_COMPLETION_NOT_YET_KNOWN", "time_unix": time.time()})
        self.records.append(rec)

        def generate():
            try:
                box["response"] = self.api(path, payload, timeout=timeout)
            except BaseException as ex:
                box["exception"] = ex
            finally:
                event.set()

        thread = threading.Thread(target=generate, daemon=True)
        thread.start()
        next_gpu = 0.0
        while not event.is_set():
            elapsed = time.monotonic() - started
            if elapsed > timeout + 15 or time.monotonic() >= self.deadline:
                self.hold = "HTTP completion ambiguous after wall-clock budget; inspect server before any retry"
                box["exception"] = TimeoutError(self.hold)
                break
            try:
                rows = ps_models(self.api)
                # A sample must complete while the request is still active.
                if not event.is_set():
                    rec["samples"].append({"elapsed_seconds": round(elapsed, 3), "models": rows})
                    foreign = [row for row in rows if row.get("name", row.get("model")) != self.model or row.get("digest") != self.digest]
                    if foreign:
                        self.hold = "foreign or changed Ollama model observed during request"
            except Exception as ex:
                rec["monitor_errors"].append(type(ex).__name__ + ": " + str(ex)[:180])
            if elapsed >= next_gpu and not event.is_set():
                try:
                    snap = self.nvidia()
                    snap["elapsed_seconds"] = round(time.monotonic() - started, 3)
                    # NVIDIA sampling may straddle HTTP completion. Preserve
                    # timing context without bypassing any process HOLD.
                    snap["http_completed_at_sample_end"] = event.is_set()
                    rec["nvidia_samples"].append(snap)
                    if unattributed_processes(snap["compute_processes"]):
                        self.hold = "unattributed or multiple GPU compute processes observed; future requests held"
                except Exception as ex:
                    rec["monitor_errors"].append(type(ex).__name__ + ": " + str(ex)[:180])
                    self.hold = "NVIDIA process monitoring failed; future requests held"
                next_gpu = elapsed + 1.0
            event.wait(self.poll_seconds)
        rec["elapsed_seconds"] = round(time.monotonic() - started, 3)
        rec["gpu_evidence"] = classify(rec["samples"], self.model, self.digest)
        rec["response"] = box.get("response")
        if "exception" in box:
            rec["error"] = type(box["exception"]).__name__ + ": " + str(box["exception"])[:240]
            self.hold = self.hold or "HTTP failed; server completion ambiguous; no automatic retry"
        elif not isinstance(rec["response"], dict) or rec["response"].get("done") is not True or rec["response"].get("model") != self.model:
            self.hold = "response identity or completed done=true acknowledgement missing; no automatic retry"
            rec["error"] = self.hold
        rec["hold"] = self.hold
        append_json(self.path, rec)
        if rec["error"]:
            raise ValueError(rec["error"])
        return box["response"]


def roster_for(broker, candidate):
    return broker.validate_roster({
        "schema": broker.SOURCE_SCHEME, "source_pin": PIN, "experiment_only": True,
        "source_evidence": "Five-candidate comparison: identical 15 protected cases and seeds for each model; no permanent role assignments.",
        "roles": {role: {**candidate, "rationale": "Homogeneous experimental roster so each candidate sees the same tasks in all five roles."} for role in broker.s.ROLES},
    }, PIN)


def private_state_parent(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    st = path.lstat()
    require(stat.S_ISDIR(st.st_mode) and not path.is_symlink() and st.st_uid == os.geteuid() and not st.st_mode & 0o077,
            "state parent must be an operator-owned private directory")


def main(argv=None):
    deadline = time.monotonic() + TOTAL_SECONDS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", required=True, type=Path)
    parser.add_argument("--candidates", type=Path, default=Path(__file__).with_name("candidates.json"))
    parser.add_argument("--state", type=Path, help="new private campaign directory; required with --live")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--gpu-idle-confirmed", action="store_true")
    args = parser.parse_args(argv)
    os.umask(0o077)
    sys.dont_write_bytecode = True
    check_source(args.checkout.absolute())
    config = load_candidates(args.candidates)
    store = Path.home() / ".local" / "state" / "mother-fw00412"
    offline = check_offline(store / ("offline-" + PIN[:12]))
    sys.path.insert(0, str(args.checkout.absolute() / "packages" / "fw00412"))
    broker = importlib.import_module("broker")
    api = local_api()
    models = freeze_models(api)
    initial_gpu = idle_snapshot(api)
    preflight = {"schema": "fw00412.comparison-preflight.v1", "source_pin": PIN, "scope": config["scope"],
                 "candidate_config_sha256": sha(args.candidates.read_bytes()), "wrapper_sha256": sha(Path(__file__).read_bytes()),
                 "models": models, "offline": offline, "initial_gpu": initial_gpu,
                 "native_inventory": native_inventory(Path.home()), "maximum_generate_requests": 75,
                 "request_timeout_seconds": 120, "request_wall_seconds": 135,
                 "total_wall_budget_seconds": TOTAL_SECONDS, "natural_unload_wait_seconds": 12,
                 "cases_per_model": 15, "same_case_order_and_seeds": True,
                 "model_requests_issued": 0, "scope_limit": "synthetic evidence-boundary reasoning; native scientific adapters not exercised"}
    print(json.dumps(preflight, sort_keys=True, indent=2), flush=True)
    if not args.live:
        print("PREFLIGHT ONLY: zero inference requests issued by this invocation.")
        return 0
    require(args.gpu_idle_confirmed and args.state is not None, "--live requires --state and --gpu-idle-confirmed")
    state = args.state.absolute()
    require(not state.exists() and not state.is_symlink(), "existing campaign preserved; choose a new attempt only after reviewing it")
    private_state_parent(state.parent)
    private_state_parent(store)
    lock_path = store / "scientific-gpu.lock"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        idle_snapshot(api)
        require(freeze_models(api) == models, "candidate digests changed after preflight")
        state.mkdir(mode=0o700)
        write_json(state / "preflight.json", preflight)
        write_json(state / "candidates.json", config)
        result = {"schema": "fw00412.comparative-reasoning-screen.v1", "source_pin": PIN,
                  "status": "RUNNING", "maximum_generate_requests": 75, "models": [],
                  "scientific_truth": "NOT_ESTABLISHED", "approved_for_supervisor_routing": False,
                  "publication": "NOT_PUBLISHED", "scope": config["scope"],
                  "gpu_evidence_meaning": "Positive size_vram for matching model and full digest during request; residency/offload observation, not proof of all computation on GPU",
                  "concurrency_limit": "Package advisory lock and repeated idle/process observations; no global GPU reservation"}
        failure = None
        observer = None
        active_model = None
        previous = None
        try:
            for index, model in enumerate(models, 1):
                require(time.monotonic() < deadline, "total campaign wall-clock budget exhausted")
                settle_idle(api, nvidia_snapshot, previous,
                            seconds=max(0, min(12, deadline - time.monotonic())))
                require(freeze_models(api) == models, "candidate digest changed between batches")
                trial = state / (f"model-{index:02d}")
                trial.mkdir(mode=0o700)
                (trial / "source-pin.txt").write_text(PIN + "\n")
                roster = roster_for(broker, model)
                write_json(state / (f"roster-{index:02d}.json"), roster)
                observer = ObservedAPI(api, model["name"], model["digest"], state / (f"telemetry-{index:02d}.jsonl"), nvidia=nvidia_snapshot, deadline=deadline)
                active_model = {**model, "trial_directory": trial.name}
                print(f"START {index}/5 {model['name']} — 15 identical protected cases", flush=True)
                summary = broker.run(trial, PIN, roster, api=observer)
                counts = dict(collections.Counter(rec["gpu_evidence"] for rec in observer.records))
                result["models"].append({**model, "trial_directory": trial.name, "actual_generate_requests": len(observer.records),
                                         "broker_task_slots": summary["model_requests"], "gpu_evidence_counts": counts,
                                         "hold": observer.hold, "roles": summary["roles"], "raw_log_sha256": summary["raw_log_sha256"]})
                print(json.dumps(result["models"][-1], sort_keys=True), flush=True)
                active_model = None
                previous = model
                if observer.hold:
                    raise ValueError(observer.hold)
            require(freeze_models(api) == models, "candidate digest changed at end")
            result["status"] = "COMPLETED_COMPARATIVE_SCREEN_NO_SCIENTIFIC_PROMOTION"
        except (Exception, KeyboardInterrupt) as ex:
            failure = type(ex).__name__ + ": " + str(ex)
            result["status"] = "HELD_REVIEW_LOCAL_EVIDENCE_NO_AUTOMATIC_RETRY"
            result["failure"] = failure
            if active_model is not None and observer is not None:
                result["models"].append({**active_model, "actual_generate_requests": len(observer.records),
                    "status": "INCOMPLETE_REVIEW_RAW_AND_ATTEMPT_LOGS", "hold": observer.hold,
                    "gpu_evidence_counts": dict(collections.Counter(rec.get("gpu_evidence", "INTERRUPTED_UNOBSERVED") for rec in observer.records))})
        result["actual_generate_requests"] = sum(item["actual_generate_requests"] for item in result["models"])
        result["completed_model_batches"] = sum("broker_task_slots" in item for item in result["models"])
        result["gpu_evidence_counts"] = dict(sum((collections.Counter(item["gpu_evidence_counts"]) for item in result["models"]), collections.Counter()))
        result["all_75_requests_have_gpu_residency_observed"] = result["actual_generate_requests"] == 75 and result["gpu_evidence_counts"].get("GPU_RESIDENT_OBSERVED", 0) == 75
        if not failure and not result["all_75_requests_have_gpu_residency_observed"]:
            result["status"] = "COMPLETED_SCREEN_GPU_EVIDENCE_INCOMPLETE"
        write_json(state / "comparison.json", result)
        (state / "exit.code").write_text("4\n" if failure else "0\n")
        print("LOCAL RESULTS: " + str(state), flush=True)
        print("STATUS: " + result["status"], flush=True)
        if failure:
            print("HELD: " + failure, file=sys.stderr)
        return 4 if failure else 0


if __name__ == "__main__":
    def interrupted(signum, frame):
        raise KeyboardInterrupt("signal received; preserve attempt; server completion may be ambiguous")
    signal.signal(signal.SIGTERM, interrupted)
    try:
        raise SystemExit(main())
    except (Exception, KeyboardInterrupt) as exc:
        print("REFUSED: " + type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        raise SystemExit(2)
