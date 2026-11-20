#!/usr/bin/env python3
"""Build a mother-only local integration candidate; no main/bridge changes.

Creates one isolated Git worktree. Sequentially merges existing source refs
without force, stops on first conflict, and posts a compact result to PR #17.
No tests, live services, deployments, or Coach/HealthBridge mutations.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

REPO = "ctmansfield/mother"
REPORT_PR = "17"
BRANCH = "integration/mother-only-candidate-20261120"
LOCAL_BRANCH = "integration/mother-only-staging-20261120"
SOURCES = (
    ("PF-001", "work/physiology-foundation-pf001"),
    ("LW-001", "work/local-worker-qualification-lw001"),
    ("LW-002", "work/local-artifact-qualification-lw002"),
    ("R02", "work/r02-source-qualification-01"),
    ("I01-D", "work/i01-durable-manual-events"),
    ("I01-T2", "work/i01-offline-event-receiver"),
    ("I01-U", "work/i01-capture-ui-crossrepo-acceptance"),
    ("I01-R", "work/i01-offline-receipt-recovery"),
    ("I01-S1", "work/i01-delivery-state-readonly"),
)
ROOT = Path(__file__).resolve().parents[2]
WORKTREE = Path.home() / "mother-only-candidate-20261120"
BRIDGE_MARKERS = ("motherhealthbridge", "mother-health-bridge", "health_bridge",
                  "health-bridge", "/bridge/")

def command(args, cwd=ROOT, timeout=90):
    try:
        return subprocess.run(args, cwd=cwd, text=True, capture_output=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as ex:
        class Failure:
            returncode, stdout, stderr = 125, "", str(ex)
        return Failure()

def git(*args, cwd=ROOT):
    return command(["git", *args], cwd=cwd)

def bridge_touched(files):
    return [f for f in files if any(token in "/" + f.lower() for token in BRIDGE_MARKERS)]

def main():
    receipt = {
        "schema": "mother.mother-only-integration-candidate.v1",
        "time_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scope": "MOTHER_REPOSITORY_ONLY_NO_HEALTH_BRIDGE_NO_COACH_WRITES",
        "candidate_ref": BRANCH,
        "source_order": [name for name, _ in SOURCES],
        "integrated": [],
        "status": "PREFLIGHT",
        "tests": "NOT_RUN",
        "live_gpu": "NOT_RUN",
    }
    def stamp(status, error=""):
        receipt["status"] = status
        if error:
            receipt["error"] = error[:350]
        state = Path.home() / ".local" / "state" / "mother-integration"
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = state / "candidate-20261120.json"
        path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
        path.chmod(0o600)
        print("RECEIPT", path, json.dumps(receipt, sort_keys=True))
        body = "### Mother-only candidate staging\n\n```json\n" + json.dumps(receipt, sort_keys=True, indent=2) + "\n```"
        posted = command(["gh", "pr", "comment", REPORT_PR, "--repo", REPO, "--body", body])
        if posted.returncode != 0:
            print("GITHUB_POST_FAILED:", posted.stderr.strip()[:300])
        else:
            print("GITHUB_RECEIPT_POSTED: https://github.com/ctmansfield/mother/pull/17")
        return 0 if status == "LOCAL_CANDIDATE_READY_UNTESTED" and posted.returncode == 0 else 4
    if WORKTREE.exists() or WORKTREE.is_symlink():
        return stamp("REFUSED", "dedicated worktree path already exists; no overwrite")
    current = git("branch", "--show-current")
    dirty = git("status", "--porcelain")
    if current.returncode or current.stdout.strip() != BRANCH or dirty.returncode or dirty.stdout.strip():
        return stamp("REFUSED", "invoke from clean published candidate branch")
    # git supports ordinary positional refspecs; do not mutate source repositories.
    fetched = command(["git", "fetch", "origin", "main", *[ref for _, ref in SOURCES]], timeout=180)
    if fetched.returncode:
        return stamp("REFUSED", "fetch failed: " + fetched.stderr)
    before = git("rev-parse", "origin/main")
    if before.returncode:
        return stamp("REFUSED", "cannot resolve origin/main")
    receipt["main_base_sha"] = before.stdout.strip()
    created = git("worktree", "add", "-b", LOCAL_BRANCH, str(WORKTREE), "origin/main")
    if created.returncode:
        return stamp("REFUSED", "worktree creation failed: " + created.stderr)
    for name, ref in SOURCES:
        target = "origin/" + ref
        seen = git("rev-parse", "--verify", target)
        if seen.returncode:
            return stamp("HELD_SOURCE_MISSING", name + ": " + target)
        source_diff = git("diff", "--name-only", "origin/main..." + target, cwd=WORKTREE)
        if source_diff.returncode:
            receipt["blocked_at"] = name
            return stamp("HELD_SOURCE_DIFF_FAILED", "cannot inspect source path scope")
        forbidden_source = bridge_touched(source_diff.stdout.splitlines())
        if forbidden_source:
            receipt["blocked_at"] = name
            receipt["forbidden_paths"] = forbidden_source
            return stamp("HELD_BRIDGE_PATH_DETECTED", "source branch excluded before merge")
        merge = git("merge", "--no-ff", "--no-edit", "-m", "Integrate " + name + " for offline candidate", target, cwd=WORKTREE)
        if merge.returncode:
            git("merge", "--abort", cwd=WORKTREE)
            receipt["blocked_at"] = name
            return stamp("HELD_MERGE_CONFLICT", name + ": " + merge.stderr.strip()[-300:])
        changed = git("diff", "--name-only", "origin/main..HEAD", cwd=WORKTREE)
        if changed.returncode:
            return stamp("HELD_INSPECTION_FAILED", "cannot inspect merged files")
        forbidden = bridge_touched(changed.stdout.splitlines())
        if forbidden:
            receipt["forbidden_paths"] = forbidden
            return stamp("HELD_BRIDGE_PATH_DETECTED", "review candidate without advancing")
        receipt["integrated"].append({"name": name, "source_sha": seen.stdout.strip()})
    sha = git("rev-parse", "HEAD", cwd=WORKTREE)
    receipt["local_candidate_sha"] = sha.stdout.strip() if sha.returncode == 0 else "UNKNOWN"
    return stamp("LOCAL_CANDIDATE_READY_UNTESTED")

if __name__ == "__main__":
    sys.exit(main())
