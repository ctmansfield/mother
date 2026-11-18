#!/usr/bin/env python3
"""Verify the preserved MSE release; execute its existing checks on a temporary copy."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "research" / "mse" / "reference-v0.1.0"
MANIFEST_SHA256 = "112ccb8df17d6afc6d8b7f932fbdeac31b1663ccd04c5538b9bd9a32e94a25f1"
PAYLOAD_COUNT = 63


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_integrity(root):
    manifest = root / "MANIFEST.sha256"
    if manifest.is_symlink() or sha256(manifest) != MANIFEST_SHA256:
        raise ValueError("The original release manifest has changed.")
    expected = {"MANIFEST.sha256"}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        path = Path(relative)
        if (
            separator != "  "
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or not relative
            or path.is_absolute()
            or ".." in path.parts
            or relative in expected
        ):
            raise ValueError("Invalid or duplicate release manifest entry.")
        current = root
        for part in path.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Symlinks are not part of this release.")
        if not current.is_file() or sha256(current) != digest:
            raise ValueError("Missing or changed release file: " + relative)
        expected.add(relative)
    actual = {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()}
    if len(expected) != PAYLOAD_COUNT + 1 or actual != expected:
        raise ValueError("Release contains missing, extra, or unexpected files.")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Release contains an unexpected symlink.")
    return {"payload_files": PAYLOAD_COUNT, "manifest_sha256": MANIFEST_SHA256}


def run_all_checks():
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    with tempfile.TemporaryDirectory(prefix="mother-mse-verify-") as directory:
        copied = Path(directory) / "reference-v0.1.0"
        shutil.copytree(REFERENCE, copied)
        commands = [
            ["bash", str(copied / "prototype" / "verify.sh")],
            [
                sys.executable,
                "-B",
                str(copied / "design/contracts/validate_contracts.py"),
            ],
            [sys.executable, "-B", str(copied / "verification/verify_design_sql.py")],
            [sys.executable, "-B", str(copied / "tools/build_patch_deliverables.py")],
        ]
        for command in commands:
            result = subprocess.run(command, cwd=copied, env=environment, check=False)
            if result.returncode:
                raise RuntimeError(
                    "Verification command failed with status " + str(result.returncode)
                )
        for original in (REFERENCE / "patches").glob("*.patch"):
            rebuilt = copied / "patches" / original.name
            if sha256(rebuilt) != sha256(original):
                raise ValueError("Patch reconstruction changed: " + original.name)
    verify_integrity(REFERENCE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all",
        action="store_true",
        help="Also run prototype, JSON Schema, SQL, and patch checks; needs jsonschema.",
    )
    arguments = parser.parse_args()
    try:
        integrity = verify_integrity(REFERENCE)
        if arguments.all:
            run_all_checks()
    except (OSError, ValueError, RuntimeError) as error:
        print("MSE reference verification failed: " + str(error), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "passed",
                **integrity,
                "existing_checks_executed": arguments.all,
                "scope": "Offline software and release integrity; no biological validation.",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
