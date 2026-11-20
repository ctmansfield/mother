#!/usr/bin/env python3
"""Offline Protocol B GPU guard qualification; post compact result to PR #15.

Does not start Ollama, request inference, change credentials, or modify
the preserved campaign. Uses the operator's existing gh authentication.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

PR = "15"
REPO = "ctmansfield/mother"
TARGET = "docs/reviews/gpu-round-20261120/scientific"
ROOT = Path(__file__).resolve().parents[4]

def run(args, cwd=None, env=None):
    try:
        return subprocess.run(args, cwd=cwd, env=env, capture_output=True,
                              text=True, timeout=180, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        class Result:
            returncode = 125
            stdout = ""
            stderr = str(exc)
        return Result()

def main():
    repo = ROOT
    sha = run(["git", "rev-parse", "HEAD"], cwd=repo)
    branch = run(["git", "branch", "--show-current"], cwd=repo)
    dirty = run(["git", "status", "--porcelain"], cwd=repo)
    target = repo / TARGET
    tests = target / "test_scientific_compare.py"
    if sha.returncode != 0 or branch.returncode != 0 or dirty.returncode != 0:
        print("REFUSED: repository revision/status unavailable")
        return 2
    if branch.stdout.strip() != "review/gpu-guard-protocol-b-20261120" or dirty.stdout.strip():
        print("REFUSED: expected review branch with clean working tree")
        return 2
    if not tests.is_file():
        print("REFUSED: test suite not found")
        return 2
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = run([sys.executable, "-B", "-m", "unittest", "-v",
                     "test_scientific_compare"], cwd=target, env=env)
    log = completed.stdout + completed.stderr
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    receipt = {
        "schema": "mother.protocol-b-gpu-guard-offline-receipt.v1",
        "time_utc": stamp,
        "repository": REPO,
        "revision": sha.stdout.strip(),
        "branch": branch.stdout.strip(),
        "suite": str(tests.relative_to(repo)),
        "test_exit_code": completed.returncode,
        "test_log_sha256": hashlib.sha256(log.encode()).hexdigest(),
        "run_mode": "OFFLINE_ONLY_NO_GPU_INFERENCE",
        "historical_protocol_b_hold": "UNCHANGED",
    }
    # Durable local record, independent of the GitHub comment outcome.
    state = Path.home() / ".local" / "state" / "mother-fw00412" / "qualifications"
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = state / ("protocol-b-guard-" + sha.stdout.strip()[:12] + ".json")
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    path.chmod(0o600)
    print("LOCAL RECEIPT:", path)
    print("TEST STATUS:", completed.returncode, "LOG SHA:", receipt["test_log_sha256"])
    print(log[-2500:])
    message = "### Automated host offline qualification\n\n```json\n" + json.dumps(receipt, indent=2, sort_keys=True) + "\n```"
    posted = run(["gh", "pr", "comment", PR, "--repo", REPO, "--body", message], cwd=repo)
    if posted.returncode != 0:
        print("GITHUB RECEIPT NOT POSTED:", posted.stderr.strip()[:500])
        print("Host tests were executed; local receipt preserved.")
        return 3 if completed.returncode == 0 else 4
    print("GITHUB RECEIPT POSTED:", "https://github.com/ctmansfield/mother/pull/15")
    return 0 if completed.returncode == 0 else 4

if __name__ == "__main__":
    sys.exit(main())
