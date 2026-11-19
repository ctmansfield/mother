#!/usr/bin/env python3
"""Local-only native scientific screens; imports model runtimes only in a worker.

This is an operator-invoked experiment, not an agent tool or a deployed broker.
The parent owns the GPU lease, process watchdog, and contention observations.
"""
import argparse
import csv
import datetime as dt
import fcntl
import hashlib
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path
import random
import re
import signal
import stat
import subprocess
import sys
import time
import urllib.request
import uuid

HERE = Path(__file__).resolve().parent
SOURCE_PIN = "ba6fbb90c031f122b7db61d2f67f2b22ef1cf130"
TX_PIN = "bc45665ceb345eea6acfc44d82706e8d8b689209"
DEFAULT_CACHE = Path("/mnt/llmstore/caches/hf/chad/hub")
REPOS = {"query": "models--ncbi--MedCPT-Query-Encoder",
         "article": "models--ncbi--MedCPT-Article-Encoder",
         "txgemma": "models--google--txgemma-9b-chat"}
HEX40 = re.compile(r"^[a-f0-9]{40}$")
OFFLINE = {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
           "HF_HUB_DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1",
           "TOKENIZERS_PARALLELISM": "false", "PYTHONDONTWRITEBYTECODE": "1"}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def append(path, value):
    with Path(path).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def phase(state, name, seconds):
    value = {"phase": name, "started_monotonic": time.monotonic(),
             "deadline_monotonic": time.monotonic() + seconds, "pid": os.getpid()}
    temporary = state / "phase.next"
    save(temporary, value)
    temporary.replace(state / "phase.json")
    append(state / "events.jsonl", value)


def command(args, timeout=10):
    result = subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)
    require(result.returncode == 0, "command failed: " + args[0] + " (exit " + str(result.returncode) + ")")
    require(len(result.stdout) <= 200000, "command output exceeds budget")
    return result.stdout


def gpu_processes():
    raw = command(["nvidia-smi", "--query-compute-apps=pid,process_name,gpu_uuid,used_gpu_memory",
                   "--format=csv,noheader,nounits"])
    rows = []
    for row in csv.reader(io.StringIO(raw)):
        if not row:
            continue
        require(len(row) == 4 and row[0].strip().isdigit(), "unreadable GPU compute-process evidence")
        rows.append({"pid": int(row[0]), "process": row[1].strip(),
                     "gpu_uuid": row[2].strip(), "used_memory_mib": row[3].strip()})
    return rows


def gpu_snapshot():
    return {"utc": dt.datetime.now(dt.timezone.utc).isoformat(), "compute_processes": gpu_processes(),
            "gpu_csv": command(["nvidia-smi", "--query-gpu=uuid,name,driver_version,memory.total,memory.used,utilization.gpu",
                                "--format=csv,noheader,nounits"])}


class RejectRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("local Ollama idle-check redirects are refused")


def ollama_idle():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), RejectRedirect())
    with opener.open("http://127.0.0.1:11434/api/ps", timeout=5) as result:
        raw = result.read(180001)
        require(result.status == 200 and len(raw) <= 180000, "Ollama idle check failed")
    value = json.loads(raw)
    require(isinstance(value, dict) and isinstance(value.get("models"), list), "Ollama ps malformed")
    require(not value["models"], "Ollama has a loaded model; native trial held")


def resolve_snapshot(repo, pin=None):
    repo = Path(repo).resolve(strict=True)
    if pin is None:
        ref = repo / "refs/main"
        if ref.is_file():
            pin = ref.read_text().strip()
        else:
            choices = sorted(p.name for p in (repo / "snapshots").iterdir()
                             if p.is_dir() and HEX40.fullmatch(p.name))
            require(len(choices) == 1, "cached snapshot ambiguous; inspect and pin before inference")
            pin = choices[0]
    require(isinstance(pin, str) and HEX40.fullmatch(pin), "invalid cached snapshot revision")
    snapshot = (repo / "snapshots" / pin).resolve(strict=True)
    require(snapshot.is_relative_to(repo / "snapshots") and snapshot.is_dir() and snapshot.name == pin,
            "snapshot escapes local model cache or revision changed")
    return snapshot


def asset_layout(snapshot):
    """Enumerate actual loader assets without loading weights or contacting Hub."""
    snapshot = Path(snapshot)
    repo = snapshot.parent.parent.resolve()
    config_path = snapshot / "config.json"
    require(config_path.resolve().is_relative_to(repo) and config_path.is_file() and
            config_path.stat().st_size < 2000000, "model config missing, oversized, or out of cache")
    config = json.loads(config_path.read_text())
    require(not config.get("auto_map"), "custom remote model code is outside this trial")
    names = {"config.json"}
    for name in ("tokenizer.json", "tokenizer.model", "vocab.txt", "tokenizer_config.json",
                 "special_tokens_map.json", "added_tokens.json", "generation_config.json"):
        if (snapshot / name).exists():
            names.add(name)
    require(names & {"tokenizer.json", "tokenizer.model", "vocab.txt"}, "tokenizer assets missing")
    weight_format = None
    for prefix, extension in (("model", "safetensors"), ("pytorch_model", "bin")):
        index = snapshot / (prefix + "." + extension + ".index.json")
        single = snapshot / (prefix + "." + extension)
        if index.is_file():
            require(index.stat().st_size < 2000000, "weight index oversized")
            data = json.loads(index.read_text())
            mapping = data.get("weight_map")
            require(isinstance(mapping, dict) and mapping, "weight index lacks shard map")
            require(all(isinstance(n, str) and Path(n).name == n and n.endswith("." + extension)
                        for n in mapping.values()), "unsafe weight shard name")
            shards = set(mapping.values())
            names.update(shards)
            names.add(index.name)
            weight_format = extension
            break
        if single.is_file():
            names.add(single.name)
            weight_format = extension
            break
    require(weight_format is not None, "complete local model weights unavailable")
    files = []
    for name in sorted(names):
        path = (snapshot / name).resolve(strict=True)
        require(path.is_relative_to(repo) and path.is_file() and path.stat().st_size > 0,
                "missing, empty, or out-of-cache model asset: " + name)
        info = path.stat()
        files.append({"name": name, "resolved": str(path), "bytes": info.st_size,
                      "mtime_ns": info.st_mtime_ns, "inode": info.st_ino})
    return {"snapshot": str(snapshot), "revision": snapshot.name, "model_type": config.get("model_type"),
            "weight_format": weight_format, "files": files}


def freeze_assets(layout):
    for item in layout["files"]:
        item["sha256"] = digest(item["resolved"])
    layout["manifest_sha256"] = hashlib.sha256(canonical(layout)).hexdigest()
    return layout


def assets_unchanged(layout):
    for item in layout["files"]:
        require(str((Path(layout["snapshot"]) / item["name"]).resolve(strict=True)) == item["resolved"],
                "model asset symlink target changed during trial")
        info = Path(item["resolved"]).stat()
        require((info.st_size, info.st_mtime_ns, info.st_ino) ==
                (item["bytes"], item["mtime_ns"], item["inode"]), "model assets changed during trial")


def fixture_inputs(fixture):
    require(fixture.get("schema") == "mother.native-medcpt.synthetic-retrieval.v1", "retrieval fixture schema")
    articles, queries = fixture["articles"], fixture["queries"]
    require(len(articles) == 8 and len(queries) == 4, "retrieval trial bound changed")
    ids = [a["id"] for a in articles]
    require(len(set(ids)) == 8, "duplicate retrieval article")
    require(len({q["id"] for q in queries}) == 4, "duplicate retrieval query")
    for q in queries:
        require(q["relevant_article"] in ids and q["hard_negative"] in ids and
                q["relevant_article"] != q["hard_negative"], "unbound retrieval labels")
    # Explicit whitelists: query labels and IDs never enter the encoder inputs.
    return [q["text"] for q in queries], [[a["title"], a["abstract"]] for a in articles]


def retrieval_scores(fixture, matrix):
    queries, articles = fixture["queries"], fixture["articles"]
    require(len(matrix) == len(queries), "query score shape changed")
    ids = [a["id"] for a in articles]
    records = []
    for query, scores in zip(queries, matrix):
        require(len(scores) == len(ids) and all(isinstance(x, (int, float)) and math.isfinite(x) for x in scores),
                "nonfinite or malformed retrieval scores")
        order = sorted(range(len(ids)), key=lambda i: (-scores[i], ids[i]))
        rank = next(i + 1 for i, ix in enumerate(order) if ids[ix] == query["relevant_article"])
        pos, neg = ids.index(query["relevant_article"]), ids.index(query["hard_negative"])
        records.append({"query_id": query["id"], "ranking": [{"article": ids[i], "score": scores[i]} for i in order],
                        "relevant_rank": rank, "hit_at_1": rank == 1, "reciprocal_rank": 1 / rank,
                        "positive_over_hard_negative": scores[pos] > scores[neg],
                        "hard_negative_margin": scores[pos] - scores[neg]})
    return {"queries": records, "hit_at_1": sum(r["hit_at_1"] for r in records) / len(records),
            "mean_reciprocal_rank": sum(r["reciprocal_rank"] for r in records) / len(records),
            "positive_over_hard_negative_count": sum(r["positive_over_hard_negative"] for r in records)}


def lexical_scores(fixture):
    words = lambda text: set(re.findall(r"[a-z]+", text.lower()))
    return [[len(words(q["text"]) & words(a["title"] + " " + a["abstract"]))
             for a in fixture["articles"]] for q in fixture["queries"]]


def verify_source(source):
    source = Path(source).resolve(strict=True)
    require(command(["git", "-C", str(source), "rev-parse", "HEAD"]).strip() == SOURCE_PIN,
            "FW00412 exact source pin differs")
    require(not command(["git", "-C", str(source), "status", "--porcelain", "--untracked-files=all"]).strip(),
            "FW00412 checkout must be clean")
    expected = {"fw00410/scientific.py": "521261fe0a8f9ba09f152f95319d705283d9aba7",
                "fw00411/scout.py": "302aea4628397450257322c466ead74454d0ceb1",
                "fw0048/evidence.py": "dd850a871954ada337ccd73af6dc0b04ee16f049"}
    for relative, blob in expected.items():
        require(command(["git", "hash-object", str(source / "packages" / relative)]).strip() == blob,
                "inherited FW00412 source differs: " + relative)
    for package in ("fw00410", "fw00411", "fw00412"):
        package_path = source / "packages" / package
        for line in (package_path / "SHA256SUMS").read_text().splitlines():
            value, name = line.split(maxsplit=1)
            path = package_path / name.lstrip("*")
            require(path.resolve().is_relative_to(package_path.resolve()) and digest(path) == value,
                    "source manifest mismatch: " + name)
    return source


def runtime(torch):
    require(torch.cuda.is_available(), "CUDA unavailable; CPU fallback refused")
    torch.cuda.set_device(0)
    torch.cuda.reset_peak_memory_stats(0)
    versions = {}
    for package in ("torch", "transformers", "accelerate", "safetensors"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return {"python": sys.version, "executable": sys.executable, "packages": versions,
            "torch_cuda": torch.version.cuda, "device": "cuda:0", "device_name": torch.cuda.get_device_name(0),
            "free_total_bytes_before_load": list(torch.cuda.mem_get_info(0)), "pid": os.getpid()}


def cuda_evidence(torch, model, encoded, output):
    parameter_devices = sorted({str(p.device) for p in model.parameters()})
    buffer_devices = sorted({str(p.device) for p in model.buffers()})
    input_devices = sorted({str(v.device) for v in encoded.values()})
    require(parameter_devices == ["cuda:0"] and set(buffer_devices) <= {"cuda:0"} and
            input_devices == ["cuda:0"] and str(output.device) == "cuda:0", "CUDA tensor placement not established")
    torch.cuda.synchronize(0)
    return {"parameter_devices": parameter_devices, "buffer_devices": buffer_devices,
            "input_devices": input_devices, "output_device": str(output.device),
            "peak_allocated_bytes": torch.cuda.max_memory_allocated(0),
            "peak_reserved_bytes": torch.cuda.max_memory_reserved(0),
            "evidence": "CUDA_PARAMETERS_INPUTS_OUTPUTS_OBSERVED"}


def load_kwargs(layout):
    values = {"local_files_only": True, "trust_remote_code": False,
              "use_safetensors": layout["weight_format"] == "safetensors"}
    if layout["weight_format"] == "bin":
        version = importlib.metadata.version("torch").split("+")[0]
        parts = tuple(int(x) for x in version.split(".")[:2])
        require(parts >= (2, 6), "cached PyTorch bin needs torch >= 2.6 for weights-only loading; no automatic update")
        values["weights_only"] = True
    return values


def run_medcpt(args, state):
    import torch
    from transformers import AutoModel, AutoTokenizer
    evidence = runtime(torch)
    save(state / "runtime.json", evidence)
    fixture = json.loads((HERE / "retrieval_fixture.json").read_text())
    query_text, article_text = fixture_inputs(fixture)
    embeddings, manifests, device_records = {}, {}, {}
    for key, texts, limit in (("query", query_text, 64), ("article", article_text, 512)):
        phase(state, "hash_" + key, 600)
        layout = freeze_assets(asset_layout(resolve_snapshot(args.hf_cache / REPOS[key])))
        require(layout["model_type"] == "bert", "MedCPT expected Bert architecture")
        save(state / (key + "_assets.json"), layout)
        manifests[key] = layout
        phase(state, "load_" + key, 180)
        assets_unchanged(layout)
        tokenizer = AutoTokenizer.from_pretrained(layout["snapshot"], local_files_only=True, trust_remote_code=False)
        model = AutoModel.from_pretrained(layout["snapshot"], **load_kwargs(layout)).to("cuda:0").eval()
        encoded = tokenizer(texts, padding=True, truncation=False, return_tensors="pt")
        require(encoded["input_ids"].shape[1] <= limit, "fixture input token budget exceeded")
        encoded = {k: v.to("cuda:0") for k, v in encoded.items()}
        phase(state, "forward_" + key, 120)
        with torch.inference_mode():
            output = model(**encoded).last_hidden_state[:, 0, :]
        require(tuple(output.shape) == (len(texts), 768) and torch.isfinite(output).all().item(),
                "MedCPT output shape or finite-value check failed")
        device_records[key] = cuda_evidence(torch, model, encoded, output)
        embeddings[key] = output
        del model, encoded
        torch.cuda.empty_cache()
    phase(state, "score_retrieval", 30)
    with torch.inference_mode():
        scores = embeddings["query"] @ embeddings["article"].T
    require(str(scores.device) == "cuda:0", "retrieval scores not computed on CUDA")
    torch.cuda.synchronize(0)
    result = retrieval_scores(fixture, scores.cpu().tolist())
    baseline = retrieval_scores(fixture, lexical_scores(fixture))
    for layout in manifests.values():
        assets_unchanged(layout)
    save(state / "summary.json", {"schema": "mother.native-medcpt-screen.v1", "status": "COMPLETED_SYNTHETIC_SCREEN",
         "scientific_truth": "NOT_ESTABLISHED", "model_forward_calls": 2, "query_count": 4, "article_count": 8,
         "representation": "RAW_CLS_LAST_HIDDEN_STATE", "ranking": "INNER_PRODUCT", "normalization": "NONE",
         "fixture_sha256": digest(HERE / "retrieval_fixture.json"), "model_results": result,
         "lexical_overlap_baseline": baseline, "cuda_evidence": device_records,
         "model_manifest_sha256": {k: v["manifest_sha256"] for k, v in manifests.items()},
         "post_run_asset_check": "SIZE_MTIME_INODE_UNCHANGED", "role_activation": "NOT_ASSIGNED"})


def run_txgemma(args, state):
    source = verify_source(args.source)
    sys.path.insert(0, str(source / "packages/fw00412"))
    import broker
    import fixtures
    import specialists
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    graph, sources, _, _ = broker.checked_environment()
    tasks = fixtures.cases()
    require(len(tasks) == 15, "scientific benchmark case count changed")
    save(state / "runtime.json", runtime(torch))
    phase(state, "hash_txgemma", 900)
    layout = freeze_assets(asset_layout(resolve_snapshot(args.hf_cache / REPOS["txgemma"], TX_PIN)))
    require(layout["model_type"] == "gemma2" and layout["weight_format"] == "safetensors", "TxGemma architecture or safe weights differ")
    save(state / "txgemma_assets.json", layout)
    phase(state, "load_txgemma", 240)
    assets_unchanged(layout)
    require(torch.cuda.is_bf16_supported(), "native TxGemma bfloat16 unsupported; no precision substitution")
    tokenizer = AutoTokenizer.from_pretrained(layout["snapshot"], local_files_only=True, trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(layout["snapshot"], torch_dtype=torch.bfloat16,
            device_map={"": "cuda:0"}, attn_implementation="sdpa", **load_kwargs(layout)).eval()
    order = list(range(len(tasks)))
    random.Random(20261119).shuffle(order)
    records = []
    for ix in order:
        task = tasks[ix]
        scoped = broker.with_retraction(sources, task)
        question = specialists.prompt(graph, scoped, task)
        # No protected answer fields, previous answers, grades, or repair prompts enter this message.
        chat = tokenizer.apply_chat_template([{"role": "user", "content": question}], tokenize=False,
                                             add_generation_prompt=True)
        encoded = tokenizer(chat, add_special_tokens=False, return_tensors="pt")
        require(encoded["input_ids"].shape[1] <= 4096 - 520, "TxGemma prompt exceeds fixed context budget")
        encoded = {k: v.to("cuda:0") for k, v in encoded.items()}
        torch.manual_seed(20261119 + ix)
        phase(state, "generate_" + task["id"], 125)
        append(state / "attempts.jsonl", {"case_id": task["id"], "seed": 20261119 + ix,
                                         "prompt_sha256": specialists.sha(question.encode())})
        started = time.monotonic()
        with torch.inference_mode():
            outputs = model.generate(**encoded, max_new_tokens=520, do_sample=False, num_beams=1,
                                     max_time=120, use_cache=True)
        device = cuda_evidence(torch, model, encoded, outputs)
        token_ids = outputs[0, encoded["input_ids"].shape[1]:]
        answer = tokenizer.decode(token_ids, skip_special_tokens=True)
        eos = model.generation_config.eos_token_id
        endings = set(eos if isinstance(eos, (list, tuple)) else [eos])
        complete = len(token_ids) > 0 and int(token_ids[-1]) in endings
        bounded = len(answer.encode()) <= specialists.MAX_RESPONSE
        grade = specialists.judge(answer, graph, scoped, task) if complete and bounded else {
            "task_correct": False, "schema_valid": False, "source_anchor_valid": False,
            "false_candidate": False, "correct_abstain": False, "candidate_only": False,
            "reason": "native_generation_incomplete_or_over_budget"}
        record = {"case_id": task["id"], "role": task["role"], "model": "google/txgemma-9b-chat",
                  "revision": TX_PIN, "source_pin": SOURCE_PIN, "model_manifest_sha256": layout["manifest_sha256"],
                  "prompt_sha256": specialists.sha(question.encode()), "chat_sha256": specialists.sha(chat.encode()),
                  "response": answer if bounded else "", "response_sha256": specialists.sha(answer.encode()),
                  "generated_tokens": len(token_ids), "complete_eos": complete, "grade": grade,
                  "elapsed_seconds": time.monotonic() - started, "cuda_evidence": device,
                  "scientific_truth": "NOT_ESTABLISHED", "role_assignment": "EXPERIMENT_ONLY_NOT_ROUTED"}
        append(state / "raw-local.jsonl", record)
        records.append(record)
    assets_unchanged(layout)
    save(state / "summary.json", {"schema": "mother.native-txgemma-screen.v1", "status": "COMPLETED_SYNTHETIC_SCREEN",
         "model_generate_calls": len(records), "source_pin": SOURCE_PIN, "revision": TX_PIN,
         "graph_sha256": graph["graph_sha256"], "source_record_sha256": sources["records"][0]["record_sha256"],
         "raw_log_sha256": digest(state / "raw-local.jsonl"), "roles": {
             role: {"samples": sum(r["role"] == role for r in records),
                    "correct": sum(r["role"] == role and r["grade"]["task_correct"] for r in records),
                    "schema_valid": sum(r["role"] == role and r["grade"]["schema_valid"] for r in records)}
             for role in specialists.ROLES},
         "harness_difference": "Native chat template; no Ollama format=json constraint; bfloat16 SDPA; greedy decoding",
         "comparison_scope": "SAME_CASES_AND_GRADER_DIFFERENT_RUNTIME_PROTOCOL",
         "post_run_asset_check": "SIZE_MTIME_INODE_UNCHANGED", "scientific_truth": "NOT_ESTABLISHED",
         "shared_memory_promotion": "NOT_APPROVED", "role_activation": "NOT_ASSIGNED"})


def inspect_local(args):
    report = {"status": "READINESS_ONLY_NO_MODEL_LOAD_NO_CUDA_INFERENCE", "models": {}, "environments": {},
              "coverage": {"medcpt": "RETRIEVAL_ADAPTER_PREPARED", "txgemma": "TEXT_ADAPTER_PREPARED",
                           "boltz2": "CHECKPOINT_INSPECTION_ONLY", "timesfm": "ENVIRONMENT_INSPECTION_ONLY"}}
    for key, directory in REPOS.items():
        try:
            snapshot = resolve_snapshot(args.hf_cache / directory, TX_PIN if key == "txgemma" else None)
            report["models"][key] = asset_layout(snapshot)
        except (OSError, ValueError, KeyError) as ex:
            report["models"][key] = {"readiness": "HELD", "reason": str(ex)}
    for name in ("medcpt", "txgemma", "boltz2", "timeseries"):
        binary = Path.home() / "ai-envs" / name / "bin/python"
        report["environments"][name] = {"python": str(binary), "exists": binary.is_file()}
    cache = args.boltz_cache.expanduser()
    candidates = []
    if cache.is_dir():
        for root, directories, files in os.walk(cache):
            if len(Path(root).relative_to(cache).parts) >= 3:
                directories[:] = []
            for name in files:
                if name.endswith((".ckpt", ".pt", ".safetensors")):
                    candidates.append({"path": str(Path(root) / name), "bytes": (Path(root) / name).stat().st_size})
                    require(len(candidates) <= 100, "Boltz checkpoint inspection bound exceeded")
    report["boltz2"] = {"inspected_cache": str(cache), "cache_exists": cache.is_dir(), "candidate_files": candidates,
                        "readiness": "NOT_VALIDATED", "limitation": "Only this local path inspected; model identity and inference not established"}
    print(json.dumps(report, sort_keys=True, indent=2))


def private_directory(path, create=False):
    path = Path(path).absolute()
    if create:
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and not path.is_symlink() and info.st_uid == os.geteuid() and
            not info.st_mode & 0o077, "state/lease directory must be operator-owned and private")
    return path


def stop_owned(process):
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            process.wait(timeout=10)
            return
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=10)


def supervise(args):
    os.umask(0o077)
    store = private_directory(Path.home() / ".local/state/mother-native-science", create=True)
    name = args.mode + "-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    state = store / name
    state.mkdir(mode=0o700)
    save(state / "request.json", {"mode": args.mode, "source": str(args.source), "source_pin": SOURCE_PIN,
         "adapter_sha256": digest(__file__), "fixture_sha256": digest(HERE / "retrieval_fixture.json"),
         "utc": dt.datetime.now(dt.timezone.utc).isoformat(), "state": str(state)})
    process = None
    rc, reason = 2, "PREFLIGHT_HELD"
    try:
        lock_dir = private_directory(Path.home() / ".local/state/mother-fw00412", create=True)
        lock_path = lock_dir / "scientific-gpu.lock"
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as lease:
            fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            before = gpu_snapshot()
            save(state / "gpu-before.json", before)
            require(not before["compute_processes"], "GPU already has compute processes")
            ollama_idle()
            if args.mode == "txgemma":
                verify_source(args.source)
            phase(state, "worker_start", 120)
            child_args = [sys.executable, "-B", str(Path(__file__).resolve()), args.mode, "--worker-state", str(state),
                          "--hf-cache", str(args.hf_cache), "--source", str(args.source)]
            with (state / "worker.log").open("x") as log:
                process = subprocess.Popen(child_args, stdout=log, stderr=subprocess.STDOUT,
                                           start_new_session=True, env={**os.environ, **OFFLINE})
                deadline = time.monotonic() + (1500 if args.mode == "medcpt" else 3300)
                sampled = 0.0
                while process.poll() is None:
                    now = time.monotonic()
                    current = json.loads((state / "phase.json").read_text())
                    if now > min(deadline, current["deadline_monotonic"]):
                        reason = "OWNED_WORKER_TIMEOUT_" + current["phase"]
                        stop_owned(process)
                        rc = 124
                        break
                    if now - sampled >= 2:
                        observed = gpu_snapshot()
                        append(state / "gpu-samples.jsonl", observed)
                        require(all(p["pid"] == process.pid for p in observed["compute_processes"]),
                                "foreign GPU compute process appeared; owned trial stopped")
                        sampled = now
                    time.sleep(0.25)
                else:
                    rc = process.returncode
                    reason = "COMPLETED" if rc == 0 else "WORKER_FAILED"
            save(state / "gpu-after.json", gpu_snapshot())
    except (OSError, ValueError, subprocess.SubprocessError, KeyboardInterrupt) as ex:
        rc = 130 if isinstance(ex, KeyboardInterrupt) else 4
        reason = type(ex).__name__ + ": " + str(ex)
        if process is not None:
            stop_owned(process)
    finally:
        save(state / "supervisor.json", {"exit_code": rc, "status": reason,
             "scope": "OWNED_PROCESS_ONLY", "gpu_lease": "COOPERATIVE_PACKAGE_LOCK_PLUS_OBSERVED_CONTENTION_CHECKS",
             "global_scheduler_lock": "NOT_ESTABLISHED", "model_results": "SEE_RAW_LOCAL_EVIDENCE"})
        print("NATIVE SCIENCE EXIT:", rc, "\nLOCAL EVIDENCE:", state, "\nSTATUS:", reason)
    return rc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inspect", "medcpt", "txgemma"))
    parser.add_argument("--hf-cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--source", type=Path, default=Path("/tmp/FW00412_SOURCE_REQUIRED"))
    parser.add_argument("--boltz-cache", type=Path, default=Path.home() / ".boltz")
    parser.add_argument("--worker-state", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.mode == "inspect":
        inspect_local(args)
        return 0
    if args.worker_state is None:
        return supervise(args)
    os.umask(0o077)
    os.environ.update(OFFLINE)
    state = private_directory(args.worker_state)
    try:
        (run_medcpt if args.mode == "medcpt" else run_txgemma)(args, state)
        return 0
    except Exception as ex:
        save(state / "failure.json", {"class": type(ex).__name__, "reason": str(ex)[:2000],
                                      "status": "FAILED_NOT_SCIENTIFIC_SUCCESS"})
        raise


if __name__ == "__main__":
    def interrupted(signum, frame):
        raise KeyboardInterrupt("signal received; stop the owned native worker and preserve evidence")
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGHUP, interrupted)
    sys.exit(main())
