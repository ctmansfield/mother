"""Verify an inert archive deployment package against an independent Git allowlist."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tarfile
import zipfile

MAX_PACKAGE_BYTES = 128 * 1024 * 1024
MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_MEMBERS = 4096
HEX = re.compile(r"[0-9a-f]{40}")
MEMBER_NAME = re.compile(r"[A-Za-z0-9._/-]{1,256}")
CREDENTIAL_CONTENT = re.compile(
    rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|"
    rb"gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|"
    rb"AKIA[0-9A-Z]{16}|"
    rb"(?:postgres(?:ql)?|https?)://[^@:/\s]+:[^@/\s]+@",
    re.IGNORECASE,
)
SECRET_NAMES = {"id_rsa", "id_ed25519", "authorized_keys", ".pgpass", ".netrc", ".secrets",
                ".env", "credentials", "shadow", "machine-id"}
SECRET_SUFFIXES = {".key", ".p12", ".pfx", ".mobileprovision", ".sqlite", ".sqlite3", ".db"}


class VerificationError(ValueError):
    """Safe error without protected paths or inputs."""


def _path(name):
    if not isinstance(name, str) or not MEMBER_NAME.fullmatch(name):
        raise VerificationError("Invalid package member path")
    path = PurePosixPath(name)
    if path.is_absolute() or path.as_posix() != name or not path.parts or ".." in path.parts:
        raise VerificationError("Noncanonical package member path")
    if any(part.lower() in SECRET_NAMES or part.lower().startswith(("ssh_host_", ".env.")) for part in path.parts):
        raise VerificationError("Disallowed secret or runtime identity filename")
    if path.suffix.lower() in SECRET_SUFFIXES:
        raise VerificationError("Disallowed credential or runtime database member")
    return name


def _git(checkout, *args):
    try:
        return subprocess.run(
            ["git", "--no-replace-objects", "-C", str(checkout), *args],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        raise VerificationError("Pinned source is unavailable") from None


def _json(data):
    def unique(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise VerificationError("Duplicate allowlist keys")
        return result
    return json.loads(data, object_pairs_hook=unique)


def _allowlist(raw):
    entries = _json(raw)
    if not isinstance(entries, list) or not 0 < len(entries) <= MAX_MEMBERS:
        raise VerificationError("Invalid allowlist length")
    result = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"member", "commit", "source"}:
            raise VerificationError("Invalid allowlist row")
        member, source = _path(entry["member"]), _path(entry["source"])
        commit = entry["commit"]
        if (not isinstance(commit, str) or not HEX.fullmatch(commit)
                or member in result):
            raise VerificationError("Invalid commit pin or duplicate allowlist member")
        result[member] = commit, source
    return result


@contextmanager
def _members(package):
    if zipfile.is_zipfile(package):
        with zipfile.ZipFile(package) as archive:
            package.seek(0)
            if package.read(4) != b"PK\x03\x04" or archive.comment:
                raise VerificationError("Unexpected ZIP prefix or comment")
            def entries():
                for entry in archive.infolist():
                    if entry.comment or entry.extra or entry.flag_bits & 1:
                        raise VerificationError("Unexpected ZIP member metadata or encryption")
                    mode = stat.S_IFMT(entry.external_attr >> 16)
                    if mode not in (0, stat.S_IFDIR if entry.is_dir() else stat.S_IFREG):
                        raise VerificationError("Nonregular ZIP member")
                    yield entry.filename, entry.is_dir(), entry.file_size, lambda: archive.open(entry)
            yield entries()
    else:
        package.seek(0)
        with tarfile.open(fileobj=package, mode="r:*") as archive:
            def entries():
                for entry in archive:
                    if (not entry.isdir() and not entry.isfile()) or entry.pax_headers:
                        raise VerificationError("Unexpected TAR member type or metadata")
                    if entry.uname not in ("", "root") or entry.gname not in ("", "root", "wheel"):
                        raise VerificationError("Unexpected TAR owner metadata")
                    yield entry.name, entry.isdir(), entry.size, lambda: archive.extractfile(entry)
            yield entries()


def _sha(data):
    return sha256(data).hexdigest()


def _read_regular(path, limit):
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise VerificationError("Input must be a regular local file")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise VerificationError("Input exceeds byte limit")
    return data


def verify_package(checkout, package, allowlist_bytes):
    """Return a source-only receipt. Nothing is extracted or executed."""
    expected = _allowlist(allowlist_bytes)
    package_bytes = _read_regular(package, MAX_PACKAGE_BYTES)

    seen, rows, total = set(), [], 0
    parents = {p.as_posix() for name in expected for p in PurePosixPath(name).parents} - {"."}
    # Use one immutable byte buffer for digest and content checks.
    archive_bytes = BytesIO(package_bytes)
    if package_bytes.startswith(b"PK") and (
        not package_bytes.startswith(b"PK\x03\x04")
        or not package_bytes[-22:].startswith(b"PK\x05\x06")
        or package_bytes[-2:] != b"\0\0"
    ):
        raise VerificationError("Unexpected ZIP envelope metadata")
    with _members(archive_bytes) as entries:
        for index, (raw_name, directory, size, opener) in enumerate(entries):
            if index >= 2 * MAX_MEMBERS:
                raise VerificationError("Package exceeds member-count bound")
            name = _path(raw_name.removesuffix("/") if directory else raw_name)
            if name in seen:
                raise VerificationError("Duplicate package member")
            seen.add(name)
            if directory:
                if name not in parents or size:
                    raise VerificationError("Unexpected package directory")
                continue
            if name not in expected:
                raise VerificationError("Package member not on trusted allowlist")
            total += size
            if not 0 <= size <= MAX_MEMBER_BYTES or total > MAX_PACKAGE_BYTES:
                raise VerificationError("Package exceeds decompressed bound")
            commit, source = expected[name]
            commit_type = _git(checkout, "cat-file", "-t", commit).strip()
            if commit_type != b"commit":
                raise VerificationError("Allowlist pin is not a Git commit")
            spec = f"{commit}:{source}"
            if _git(checkout, "cat-file", "-t", spec).strip() != b"blob":
                raise VerificationError("Allowlist source is not a Git blob")
            tree_entry = _git(checkout, "ls-tree", commit, "--", source)
            if not tree_entry.startswith((b"100644 blob ", b"100755 blob ")):
                raise VerificationError("Allowlist source is not a regular Git file")
            if int(_git(checkout, "cat-file", "-s", spec)) != size:
                raise VerificationError("Member size differs from pinned source")
            with opener() as file:
                data = file.read(size + 1)
            if len(data) != size or data != _git(checkout, "cat-file", "blob", spec):
                raise VerificationError("Member bytes differ from pinned source")
            if CREDENTIAL_CONTENT.search(data):
                raise VerificationError("Credential-shaped content in packaged source")
            rows.append({"member": name, "commit": commit, "source": source, "sha256": _sha(data), "byte_length": size})
    if {row["member"] for row in rows} != expected.keys():
        raise VerificationError("Package is missing allowed source members")
    return {
        "schema_version": "mse.archive-package-source-verification/0.1",
        "status": "passed", "package_sha256": _sha(package_bytes),
        "package_byte_length": len(package_bytes), "allowlist_sha256": _sha(allowlist_bytes),
        "members": sorted(rows, key=lambda row: row["member"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--allowlist", type=Path, required=True)
    parser.add_argument("--repeat-package", type=Path)
    args = parser.parse_args()
    try:
        allowlist = _read_regular(args.allowlist, MAX_MEMBER_BYTES)
        receipt = verify_package(args.checkout, args.package, allowlist)
        if args.repeat_package is not None:
            repeat = verify_package(args.checkout, args.repeat_package, allowlist)
            if receipt != repeat:
                raise VerificationError("Independently supplied package bytes differ")
            receipt["matching_package_input_count"] = 2
        else:
            receipt["matching_package_input_count"] = 1
    except VerificationError as exc:
        parser.exit(1, f"Archive package verification failed: {exc}\n")
    except (OSError, ValueError, RuntimeError, tarfile.TarError, zipfile.BadZipFile):
        parser.exit(1, "Archive package verification failed: Invalid input or unreadable archive\n")
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
