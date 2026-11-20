"""Standalone add-only installation, verification and non-deleting retirement."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
RELEASE = "mse-prototype-v0.1.0"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(root):
    entry = root / "RELEASE_MANIFEST.json"
    data = json.loads(entry.read_text())
    if data.get("release") != RELEASE or not isinstance(data.get("files"), dict):
        raise ValueError("Unrecognized release manifest")
    for name, expected in data["files"].items():
        rel = Path(name)
        if rel.is_absolute() or ".." in rel.parts or rel.as_posix() != name:
            raise ValueError("Unsafe manifest path")
        path = root / rel
        if path.is_symlink() or not path.is_file() or sha(path) != expected:
            raise ValueError("Release file hash mismatch")
    return data


def install(target):
    data = manifest(ROOT)
    if target.exists() or target.is_symlink():
        raise ValueError("Install destination already exists; choose a new isolated directory")
    if not target.parent.is_dir():
        raise ValueError("Create the destination parent explicitly before installing")
    target.mkdir(mode=0o700)
    # No package manager, service, environment, keychain or system configuration changed.
    for name in sorted(data["files"]):
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with destination.open("xb") as output:
            output.write((ROOT / name).read_bytes())
        destination.chmod(0o600)
    shutil.copyfile(ROOT / "RELEASE_MANIFEST.json", target / "RELEASE_MANIFEST.json")
    receipt = {"release": RELEASE, "installed_at": datetime.now(timezone.utc).isoformat(),
               "manifest_sha256": sha(target / "RELEASE_MANIFEST.json"),
               "operation": "copy_only_no_deployment"}
    (target / "INSTALL_RECEIPT.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    (target / "INSTALL_RECEIPT.json").chmod(0o600)
    manifest(target)
    print(json.dumps({"installed": True, "directory": str(target), "verified_files": len(data["files"]),
                      "deployed": False}, sort_keys=True))


def verify():
    data = manifest(ROOT)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    outcome = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
                             cwd=ROOT, env=env)
    if outcome.returncode:
        return outcome.returncode
    print(json.dumps({"verified": True, "release_files": len(data["files"]),
                      "claim": "software tests only; no clinical or physiological validation"}, sort_keys=True))
    return 0


def retire(target):
    if not target.is_dir() or target.is_symlink():
        raise ValueError("Retirement requires an installed directory, not a symlink")
    data = manifest(target)
    receipt = json.loads((target / "INSTALL_RECEIPT.json").read_text())
    if receipt.get("release") != RELEASE or receipt.get("manifest_sha256") != sha(target / "RELEASE_MANIFEST.json"):
        raise ValueError("Installation receipt does not match this release")
    expected = set(data["files"]) | {"RELEASE_MANIFEST.json", "INSTALL_RECEIPT.json"}
    actual = {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file() or p.is_symlink()}
    if actual != expected:
        raise ValueError("Untracked or missing files exist; preserve and review them before retirement")
    if any(p.is_symlink() for p in target.rglob("*")):
        raise ValueError("Symlink found; retirement refused")
    retired = target.with_name(target.name + ".retired-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    target.rename(retired)
    print(json.dumps({"retired": True, "retained_directory": str(retired), "deleted": False}, sort_keys=True))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["install", "verify", "retire"])
    parser.add_argument("target", nargs="?", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.operation == "verify":
            return verify()
        if args.target is None:
            raise ValueError("Explicit isolated target directory is required")
        target = args.target.expanduser().absolute()
        if args.operation == "install":
            install(target)
        else:
            retire(target)
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print("Lifecycle operation refused: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
