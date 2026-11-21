"""Preview destination paths and rehearse installation in disposable local storage."""

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
from tempfile import TemporaryDirectory

PROTECTED = tuple(
    PurePosixPath(path)
    for path in (
        "/etc",
        "/usr",
        "/root",
        "/home",
        "/run",
        "/repos",
        "/var/lib/postgresql",
        "/mnt/nas_storage",
        "/mnt/llmstore/pgdata",
        "/mnt/llmstore/sabnzbd",
        "/proc",
        "/sys",
        "/dev",
    )
)
INSTALL_DIRS = ("state", "staging")
DB_NAMES = ("custody.sqlite3", "physiology.sqlite3")


def below(path, parent):
    return parent == path or parent in path.parents


def make_plan(allocation, backup, restore, uid, gid):
    raw_paths = (allocation, backup, restore)
    paths = tuple(PurePosixPath(path) for path in raw_paths)
    for raw, path in zip(raw_paths, paths):
        if (
            not path.is_absolute()
            or path.anchor != "/"
            or len(path.parts) < 3
            or ".." in path.parts
            or str(path) != raw
            or any(
                below(path, protected) or below(protected, path)
                for protected in PROTECTED
            )
        ):
            raise ValueError(
                "Use a normalized dedicated absolute path outside protected trees"
            )
    for index, path in enumerate(paths):
        if any(
            below(path, other) or below(other, path) for other in paths[index + 1 :]
        ):
            raise ValueError("State, backup and restore roots must not overlap")
    if uid <= 0 or gid <= 0:
        raise ValueError("Use an approved non-root writer UID and GID")
    return {
        "allocation": allocation,
        "writer_uid": uid,
        "writer_gid": gid,
        "directory_mode": "0700",
        "file_mode": "0600",
        "umask": "0077",
        "database_paths": [str(paths[0] / "state" / name) for name in DB_NAMES],
        "staging_path": str(paths[0] / "staging"),
        "backup_generation_root": backup,
        "restore_generation_root": restore,
        "host_checks": "pending verified mounts, realpaths, existing consumers and failure domains",
        "runtime": "NOT READY",
    }


def check_local(path, owner, *, directory):
    meta = path.lstat()
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    mode = 0o700 if directory else 0o600
    if (
        not expected_type(meta.st_mode)
        or stat.S_IMODE(meta.st_mode) != mode
        or (meta.st_uid, meta.st_gid) != owner
    ):
        raise ValueError("Unexpected file type, owner or mode")


def local_dry_run():
    owner = (os.getuid(), os.getgid())
    with TemporaryDirectory(prefix="mse-destination-setup-") as scratch:
        parent = Path(scratch).resolve()
        check_local(parent, owner, directory=True)
        root = parent / "mse-synthetic"
        root.mkdir(mode=0o700)
        check_local(root, owner, directory=True)
        for name in INSTALL_DIRS:
            directory = root / name
            directory.mkdir(mode=0o700)
            check_local(directory, owner, directory=True)
        for name in DB_NAMES:
            member = root / "state" / f"{name}.preflight"
            fd = os.open(member, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
            check_local(member, owner, directory=False)

        rejected = []
        link = root / "staging" / "link"
        link.symlink_to(root / "state")
        fifo = root / "staging" / "fifo"
        os.mkfifo(fifo, mode=0o600)
        for path in (link, fifo):
            try:
                check_local(path, owner, directory=False)
            except ValueError:
                rejected.append(path.name)
        if rejected != ["link", "fifo"]:
            raise RuntimeError("Nonregular path unexpectedly accepted")

        shutil.rmtree(root)
        if root.exists():
            raise RuntimeError("Disposable layout rollback incomplete")
    return {
        "synthetic_permissions": "passed",
        "nonregular_paths_rejected": rejected,
        "disposable_layout_rollback": "passed",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    for name in ("allocation", "backup", "restore"):
        plan.add_argument("--" + name, required=True)
    plan.add_argument("--uid", required=True, type=int)
    plan.add_argument("--gid", required=True, type=int)
    commands.add_parser("local-dry-run")
    args = parser.parse_args()
    try:
        if args.command == "plan":
            result = make_plan(
                args.allocation, args.backup, args.restore, args.uid, args.gid
            )
        else:
            result = local_dry_run()
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
