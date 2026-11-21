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
PRIVACY_FILES = FILES + (
    "docs/mse/privacy/contracts/analytical-view-0.1.schema.json",
    "integrations/healthbridge/numeric.py",
    "integrations/mse_privacy/custody/__init__.py",
    "integrations/mse_privacy/custody/projection.py",
    "integrations/mse_privacy/custody/storage.py",
    "integrations/mse_privacy/export/__init__.py",
    "integrations/mse_privacy/lineage/__init__.py",
)
MANIFEST = "SOURCE-MANIFEST.json"
FILE_MODE = stat.S_IFREG | 0o600
EPOCH = (1980, 1, 1, 0, 0, 0)


def git(checkout, *args):
    return subprocess.check_output(["git", "-C", str(checkout), *args])


def digest(value):
    return sha256(value).hexdigest()


def load(checkout, candidate, tree, members):
    if (
        git(checkout, "rev-parse", "HEAD").decode().strip() != candidate
        or git(checkout, "rev-parse", "HEAD^{tree}").decode().strip() != tree
        or git(checkout, "status", "--porcelain", "--untracked-files=all").strip()
    ):
        raise ValueError(f"Use the exact clean candidate {candidate}")
    files = {}
    for name in members:
        metadata = git(checkout, "ls-tree", candidate, "--", name)
        if not metadata.startswith(b"100644 blob "):
            raise ValueError(
                f"Candidate member is absent or not a regular source file: {name}"
            )
        files[name] = git(checkout, "show", f"{candidate}:{name}")
    return files


def manifest(files, candidate, tree):
    return (
        json.dumps(
            dict(
                candidate=candidate,
                tree=tree,
                members={name: digest(data) for name, data in files.items()},
            ),
            indent=2,
            sort_keys=True,
        ).encode()
        + b"\n"
    )


def package(files, candidate, tree):
    result = BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        for name, data in sorted(
            {**files, MANIFEST: manifest(files, candidate, tree)}.items()
        ):
            item = zipfile.ZipInfo(name, EPOCH)
            item.create_system = 3
            item.external_attr = FILE_MODE << 16
            archive.writestr(item, data)
    return result.getvalue()


def verify_and_install(payload, trusted_files, destination, candidate, tree):
    wanted = {**trusted_files, MANIFEST: manifest(trusted_files, candidate, tree)}
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


def dry_run(checkout, candidate=CANDIDATE, tree=TREE, *, privacy=False):
    members = PRIVACY_FILES if privacy else FILES
    files = load(checkout, candidate, tree, members)
    payload = package(files, candidate, tree)
    if payload != package(load(checkout, candidate, tree, members), candidate, tree):
        raise ValueError("Independent package builds differ")
    previous = os.umask(0o077)
    try:
        with TemporaryDirectory(prefix="mse-source-install-") as temp:
            root = Path(temp).resolve()
            wrong = dict(files)
            wrong[FILES[0]] += b" "
            try:
                verify_and_install(
                    package(wrong, candidate, tree),
                    files,
                    root / "wrong",
                    candidate,
                    tree,
                )
            except ValueError:
                if (root / "wrong").exists():
                    raise RuntimeError("Invalid source was partially installed")
            else:
                raise RuntimeError("Changed and rehashed source accepted")
            installed = root / "source"
            verify_and_install(payload, files, installed, candidate, tree)
            command = (
                f"import sys; sys.path[:0]=[{str(installed)!r}, {str(installed / REFERENCE)!r}]; "
                "from integrations.healthbridge.ingest import ingest_capture; "
                "from integrations.mse_ingest.connected import ConnectedIngest; "
                "from integrations.mse_snapshot.ledger import replay_ledger_snapshot; "
                "from mother.physiology.archive import Archive"
            )
            if privacy:
                command += (
                    "; from integrations.mse_privacy.custody import open_custody; "
                    "from integrations.mse_privacy.export import AnalyticalExporter; "
                    "from integrations.mse_privacy.lineage import LineageResolver"
                )
            subprocess.run(
                [sys.executable, "-I", "-B", "-c", command], check=True, cwd=root
            )
        if root.exists():
            raise RuntimeError("Disposable installation rollback incomplete")
    finally:
        os.umask(previous)
    return dict(
        candidate=candidate,
        tree=tree,
        source_members=len(files),
        package_sha256=digest(payload),
        manifest_sha256=digest(manifest(files, candidate, tree)),
        reproducible=True,
        changed_source_rejected=True,
        imports="passed",
        rollback="passed",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", required=True, type=Path)
    parser.add_argument("--privacy-commit")
    parser.add_argument("--privacy-tree")
    args = parser.parse_args()
    checkout = args.checkout.resolve()
    if bool(args.privacy_commit) != bool(args.privacy_tree):
        parser.error("Specify both exact privacy commit and tree")
    if args.privacy_commit:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from privacy_stores import verify_aligned_candidate

        verify_aligned_candidate(checkout, args.privacy_commit, args.privacy_tree)
        result = dry_run(checkout, args.privacy_commit, args.privacy_tree, privacy=True)
    else:
        result = dry_run(checkout)
    print(json.dumps(result, indent=2))
