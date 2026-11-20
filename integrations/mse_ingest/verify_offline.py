"""Run the ledger qualification suite with an isolated, commit-pinned source tree."""

from importlib.metadata import PackageNotFoundError, version
from io import BytesIO
import argparse
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory

PF001 = "b4e70b7123689ec164ba09e2974645ae36b184a2"
ATLAS = "769a0966da251da4d08633cc7663af9869da70e6"
ORACLE = "ac3fbf61389ca2a6e82683aa520c15181ac1aa80"
PROVENANCE = "5482f25c10a4ba4f2217625c8ecef45002184833"
NICKY = "bf646a8e2f77c277717dc97b24b8957e9a380579"
CONTRACTS = "docs/mse/integration/contracts"
REFERENCE = "research/mse/reference-v0.1.0/prototype"
QUALIFICATION_REQUIREMENTS = {
    "attrs": "26.1.0",
    "jsonschema": "4.25.1",
    "jsonschema-specifications": "2025.9.1",
    "referencing": "0.37.0",
    "rpds-py": "2026.9.1",
    "typing-extensions": "4.16.0",
}

WORKER = """
import sys
import unittest

root, reference = sys.argv[1:]
sys.path[:0] = [root, reference]
suite = unittest.defaultTestLoader.discover(root + "/tests/integration/mse_ingest")
result = unittest.TextTestRunner(verbosity=2).run(suite)
if not result.testsRun or result.skipped or result.expectedFailures:
    print("Offline verification requires a nonempty suite with no skipped or expected-failure tests",
          file=sys.stderr)
    raise SystemExit(1)
raise SystemExit(0 if result.wasSuccessful() else 1)
"""


def git(checkout, *args):
    return subprocess.run(
        ["git", "-C", str(checkout), *args],
        stdout=subprocess.PIPE,
        check=True,
        timeout=10,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0"},
    ).stdout


def assemble(checkout, destination, commit, paths):
    archive = git(checkout, "archive", "--format=tar", commit, "--", *paths)
    with tarfile.open(fileobj=BytesIO(archive), mode="r:") as tree:
        for entry in tree:
            relative = PurePosixPath(entry.name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unexpected path in committed source")
            target = destination.joinpath(*relative.parts)
            if entry.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif entry.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with tree.extractfile(entry) as source, target.open("xb") as output:
                    output.write(source.read())
            else:
                raise ValueError(
                    "Qualification requires regular committed source files"
                )


def verify(candidate):
    if sys.version_info < (3, 10) or sys.prefix == sys.base_prefix:
        raise ValueError("Use an isolated Python 3.10+ virtual environment")
    for package, expected in QUALIFICATION_REQUIREMENTS.items():
        if version(package) != expected:
            raise ValueError(f"{package} must match the qualification pin {expected}")

    script_directory = Path(__file__).resolve().parent
    checkout = Path(
        git(script_directory, "rev-parse", "--show-toplevel").decode().strip()
    )
    if candidate is None:
        candidate = git(checkout, "rev-parse", "HEAD^{commit}").decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", candidate):
        raise ValueError("A candidate must be an exact lowercase Git commit SHA")
    if (
        git(checkout, "rev-parse", f"{candidate}^{{commit}}").decode().strip()
        != candidate
    ):
        raise ValueError("Candidate does not identify the pinned Git commit")
    tree = git(checkout, "rev-parse", f"{candidate}^{{tree}}").decode().strip()
    print(
        f"Python {sys.version.split()[0]} · candidate {candidate} · tree {tree}",
        flush=True,
    )
    units = (
        (candidate, ("integrations/mse_ingest", "tests/integration/mse_ingest")),
        (PF001, ("mother/__init__.py", "mother/physiology", f"{REFERENCE}/mse")),
        (ATLAS, (CONTRACTS,)),
        (ORACLE, ("integrations/healthbridge",)),
        (PROVENANCE, ("integrations/mse_snapshot",)),
        (NICKY, ("tests/fixtures/mse_integration/source-compatible",)),
    )
    with TemporaryDirectory(prefix="mse-offline-verify-") as temp:
        root = Path(temp).resolve()
        scratch = root / "scratch"
        scratch.mkdir(mode=0o700)
        for commit, paths in units:
            print(f"{commit}  {', '.join(paths)}", flush=True)
            if commit != candidate:
                present = git(checkout, "ls-tree", "-r", candidate, "--", *paths)
                expected = git(checkout, "ls-tree", "-r", commit, "--", *paths)
                if present and present != expected:
                    raise ValueError(
                        f"Candidate subtree differs from pin {commit}: {', '.join(paths)}"
                    )
            assemble(checkout, root, commit, paths)
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                WORKER,
                str(root),
                str(root / REFERENCE),
            ],
            cwd=root,
            env={
                "PATH": os.defpath,
                "TMPDIR": str(scratch),
                "MSE_R3_DEPENDENCY_ROOT": str(root),
                "MSE_ATLAS_CONTRACT_DIR": str(root / CONTRACTS),
            },
            timeout=45,
        )
        return result.returncode if result.returncode >= 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", help="exact local commit SHA (default: HEAD)")
    try:
        raise SystemExit(verify(parser.parse_args().candidate))
    except (
        PackageNotFoundError,
        OSError,
        ValueError,
        subprocess.SubprocessError,
        tarfile.TarError,
    ) as error:
        print(f"Offline verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
