"""Build, verify and install a candidate source bundle in disposable local scratch."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
import zipfile

CANDIDATE = "877eeb66ae2c26ab8ee2144d34adeba87c988e8f"
TREE = "6dadd8cd94ffb4a0091f76624fdd0afd7baad507"
REFERENCE = "research/mse/reference-v0.1.0/prototype"
FILES = (
    "docs/mse/integration/contracts/offline-integration.schema.json",
    "integrations/healthbridge/capture.py",
    "integrations/healthbridge/export.py",
    "integrations/healthbridge/ingest.py",
    "integrations/mse_ingest/__init__.py",
    "integrations/mse_ingest/connected.py",
    "integrations/mse_ingest/receipt.py",
    "integrations/mse_ingest/v02.py",
    "integrations/mse_snapshot/ledger.py",
    "integrations/mse_snapshot/reference.py",
    "integrations/mse_snapshot/snapshot.py",
    "mother/__init__.py",
    "mother/physiology/__init__.py",
    "mother/physiology/archive.py",
    "mother/physiology/contracts.py",
    "mother/physiology/migrations/0001_archive.sql",
    "mother/physiology/schemas/v1.schema.json",
    "mother/physiology/time.py",
    "mother/physiology/units.py",
) + tuple(
    f"{REFERENCE}/mse/{name}.py"
    for name in (
        "__init__",
        "__main__",
        "adapters",
        "contracts",
        "features",
        "model",
        "storage",
    )
)
MANIFEST = "SOURCE-MANIFEST.json"
FILE_MODE = stat.S_IFREG | 0o600
EPOCH = (1980, 1, 1, 0, 0, 0)


def git(checkout, *args):
    return subprocess.check_output(["git", "-C", str(checkout), *args])


def digest(value):
    return sha256(value).hexdigest()


def load(checkout):
    if (
        git(checkout, "rev-parse", "HEAD").decode().strip() != CANDIDATE
        or git(checkout, "rev-parse", "HEAD^{tree}").decode().strip() != TREE
        or git(checkout, "status", "--porcelain", "--untracked-files=all").strip()
    ):
        raise ValueError(f"Use the exact clean candidate {CANDIDATE}")
    files = {}
    for name in FILES:
        metadata = git(checkout, "ls-tree", CANDIDATE, "--", name)
        if not metadata.startswith(b"100644 blob "):
            raise ValueError(
                f"Candidate member is absent or not a regular source file: {name}"
            )
        files[name] = git(checkout, "show", f"{CANDIDATE}:{name}")
    return files


def manifest(files):
    return (
        json.dumps(
            dict(
                candidate=CANDIDATE,
                tree=TREE,
                members={name: digest(data) for name, data in files.items()},
            ),
            indent=2,
            sort_keys=True,
        ).encode()
        + b"\n"
    )


def package(files):
    result = BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        for name, data in sorted({**files, MANIFEST: manifest(files)}.items()):
            item = zipfile.ZipInfo(name, EPOCH)
            item.create_system = 3
            item.external_attr = FILE_MODE << 16
            archive.writestr(item, data)
    return result.getvalue()


def verify_and_install(payload, trusted_files, destination):
    wanted = {**trusted_files, MANIFEST: manifest(trusted_files)}
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        if archive.namelist() != sorted(wanted):
            raise ValueError("Unexpected package inventory")
        for item in archive.infolist():
            if (
                item.external_attr >> 16 != FILE_MODE
                or item.date_time != EPOCH
                or item.compress_type != zipfile.ZIP_STORED
                or archive.read(item) != wanted[item.filename]
            ):
                raise ValueError("Package differs from pinned source or metadata")
        destination.mkdir(mode=0o700)
        for name in sorted(wanted):
            target = destination / name
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with target.open("xb") as file:
                file.write(archive.read(name))
            target.chmod(0o600)
    for name, expected in wanted.items():
        target = destination / name
        if (
            target.read_bytes() != expected
            or stat.S_IMODE(target.stat().st_mode) != 0o600
        ):
            raise ValueError("Installed member differs from verified source")


def dry_run(checkout):
    files = load(checkout)
    payload = package(files)
    if payload != package(load(checkout)):
        raise ValueError("Independent package builds differ")
    previous = os.umask(0o077)
    try:
        with TemporaryDirectory(prefix="mse-source-install-") as temp:
            root = Path(temp).resolve()
            wrong = dict(files)
            wrong[FILES[0]] += b" "
            try:
                verify_and_install(package(wrong), files, root / "wrong")
            except ValueError:
                if (root / "wrong").exists():
                    raise RuntimeError("Invalid source was partially installed")
            else:
                raise RuntimeError("Changed and rehashed source accepted")
            installed = root / "source"
            verify_and_install(payload, files, installed)
            command = (
                f"import sys; sys.path[:0]=[{str(installed)!r}, {str(installed / REFERENCE)!r}]; "
                "from integrations.healthbridge.ingest import ingest_capture; "
                "from integrations.mse_ingest.connected import ConnectedIngest; "
                "from integrations.mse_snapshot.ledger import replay_ledger_snapshot; "
                "from mother.physiology.archive import Archive"
            )
            subprocess.run(
                [sys.executable, "-I", "-B", "-c", command], check=True, cwd=root
            )
        if root.exists():
            raise RuntimeError("Disposable installation rollback incomplete")
    finally:
        os.umask(previous)
    return dict(
        candidate=CANDIDATE,
        tree=TREE,
        source_members=len(files),
        package_sha256=digest(payload),
        manifest_sha256=digest(manifest(files)),
        reproducible=True,
        changed_source_rejected=True,
        imports="passed",
        rollback="passed",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(dry_run(args.checkout.resolve()), indent=2))
