"""Explicitly admitted native archive import on a protected macOS volume."""

import argparse
import errno
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import plistlib
import resource
import shutil
import signal
import sqlite3
import subprocess
import sys

from integrations.healthbridge.capture import _unique_object
from mother.physiology.contracts import canonical_json

from .blood_pressure import source_time
from .catalog import _HistoryCatalog
from .files import HistoryLimit, LimitKind, NamedHistoryLimit, private_path
from .inventory import Limits
from .native_runner import private_bytes
from .native_status import CATEGORIES, DIAGNOSTIC_PREFIX, SUCCESS
from .protected_export import ExportAuthenticationError
from .vault import DIGEST, TOKEN

DOMAIN = b"mse.native-custodian-admission/0.1\x00"
GIB = 1024**3
FIELDS = {
    "mode",
    "archive_id",
    "enrollment",
    "source_instance",
    "allowed_at",
    "expires_at",
    "volume_uuid",
    "mount",
    "catalog",
    "scratch",
    "ciphertext",
    "identity_file",
    "provenance_key_file",
    "age_executable",
    "binding",
    "catalog_bytes",
    "reserve_bytes",
    "runtime_seconds",
    "max_expanded_bytes",
    "max_top_level_rows",
}
BINDING = {
    "receipt",
    "recipient_fingerprint",
    "plaintext_sha256",
    "plaintext_length",
    "age_sha256",
}


def load_admission(path, approval_key):
    envelope = json.loads(
        private_bytes(path, 24 * 1024), object_pairs_hook=_unique_object
    )
    if set(envelope) != {"policy", "hmac_sha256"} or len(approval_key) != 32:
        raise ValueError("custodian admission shape")
    policy = envelope["policy"]
    expected = hmac.new(approval_key, DOMAIN + canonical_json(policy).encode(), sha256)
    if not hmac.compare_digest(envelope["hmac_sha256"], expected.hexdigest()):
        raise ValueError("custodian admission authentication")
    if set(policy) != FIELDS or policy["mode"] != "protected-native-import":
        raise ValueError("custodian admission scope")
    if not all(
        TOKEN.fullmatch(policy[k])
        for k in ("archive_id", "enrollment", "source_instance")
    ):
        raise ValueError("custodian admission labels")
    for field, low, high in (
        ("catalog_bytes", 64 * 1024**2, 16 * GIB),
        ("reserve_bytes", 256 * 1024**2, 16 * GIB),
        ("runtime_seconds", 1, 1800),
        ("max_expanded_bytes", 1, Limits().expanded_bytes),
        ("max_top_level_rows", 1, Limits().top_level_rows),
    ):
        if type(policy[field]) is not int or not low <= policy[field] <= high:
            raise ValueError("custodian resource bounds")
    binding = policy["binding"]
    if (
        set(binding) != BINDING
        or not all(
            DIGEST.fullmatch(binding[k])
            for k in (
                "recipient_fingerprint",
                "plaintext_sha256",
                "age_sha256",
            )
        )
        or type(binding["plaintext_length"]) is not int
        or not 1 <= binding["plaintext_length"] <= Limits().archive_bytes
        or type(binding["receipt"]["byte_length"]) is not int
        or not 1
        <= binding["receipt"]["byte_length"]
        <= Limits().archive_bytes + 16 * 1024**2
    ):
        raise ValueError("custodian binding fields")
    return policy


def lease(policy):
    start, end = policy["allowed_at"], policy["expires_at"]
    now = (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )
    if not source_time(start) == start <= now < end == source_time(end):
        raise ValueError("custodian admission outside authorized time")


def paths_on_encrypted_volume(policy):
    mount = Path(policy["mount"])
    if not mount.is_absolute() or mount.resolve(strict=True) != mount:
        raise ValueError("exact protected macOS mount required")
    data = plistlib.loads(
        subprocess.check_output(
            ["/usr/sbin/diskutil", "info", "-plist", str(mount)],
            timeout=10,
            stderr=subprocess.DEVNULL,
        )
    )
    if (
        data.get("MountPoint") != str(mount)
        or data.get("FilesystemType") != "apfs"
        or data.get("EncryptionThisVolumeProper") is not True
        or data.get("VolumeUUID") != policy["volume_uuid"]
    ):
        raise ValueError("approved encrypted APFS volume not mounted")
    catalog, scratch = (Path(policy[k]) for k in ("catalog", "scratch"))
    for root in (catalog, scratch):
        private_path(root, directory=True)
        if mount not in root.parents or root.stat().st_dev != mount.stat().st_dev:
            raise ValueError("protected root outside pinned volume")
    if catalog == scratch or catalog in scratch.parents or scratch in catalog.parents:
        raise ValueError("independent catalog and scratch roots required")
    return catalog, scratch


def ensure_space(policy, catalog, *, extra=0):
    if shutil.disk_usage(catalog).free < policy["reserve_bytes"] + extra:
        raise NamedHistoryLimit(
            LimitKind.FILESYSTEM_RESERVE, "protected filesystem reserve insufficient"
        )
    database = catalog / "history.sqlite3"
    for path in (database, catalog / "history.sqlite3-journal"):
        if os.path.lexists(path):
            private_path(path, directory=False)
            if path.stat().st_size > policy["catalog_bytes"]:
                kind = (
                    LimitKind.CATALOG_BYTES
                    if path == database
                    else LimitKind.JOURNAL_BYTES
                )
                raise NamedHistoryLimit(kind, "protected catalog bound exceeded")
    if any(os.path.lexists(str(database) + suffix) for suffix in ("-wal", "-shm")):
        raise ValueError("protected catalog requires rollback journal mode")


def timeout(_signal, _frame):
    raise TimeoutError("protected native import wall deadline")


def file_limit(_signal, _frame):
    raise NamedHistoryLimit(LimitKind.FILE_SIZE, "protected file-size deadline")


def diagnostic_category(error, phase):
    if isinstance(error, TimeoutError):
        return "RUNTIME_LIMIT"
    if isinstance(error, ExportAuthenticationError):
        return "AUTHENTICATION"
    if isinstance(error, NamedHistoryLimit):
        return error.kind.value
    if isinstance(error, HistoryLimit):
        return "INVENTORY_LIMIT" if phase == "ARCHIVE_OR_XML" else "RESOURCE_LIMIT"
    if isinstance(error, OSError):
        category = {
            errno.ENOSPC: "FILESYSTEM_FULL",
            errno.EDQUOT: "FILESYSTEM_QUOTA",
            errno.EFBIG: LimitKind.FILE_SIZE.value,
        }.get(error.errno)
        if category is not None:
            return category
    if isinstance(error, sqlite3.Error):
        if getattr(error, "sqlite_errorcode", None) == getattr(
            sqlite3, "SQLITE_FULL", 13
        ):
            return "SQLITE_FULL"
        if phase == "ARCHIVE_OR_XML":
            return "CATALOG"
    return phase


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admission", required=True)
    parser.add_argument("--approval-key", required=True)
    parser.add_argument("--diagnostic-category", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    phase = "ADMISSION"

    def report_phase(value):
        nonlocal phase
        phase = value

    try:
        if sys.platform != "darwin":
            raise ValueError("protected runner requires macOS")
        approval = private_bytes(args.approval_key, 32)
        policy = load_admission(args.admission, approval)
        lease(policy)
        report_phase("ENVIRONMENT")
        catalog_root, scratch = paths_on_encrypted_volume(policy)
        binding = policy["binding"]
        ensure_space(
            policy,
            catalog_root,
            extra=binding["plaintext_length"] + 2 * policy["catalog_bytes"],
        )
        key = private_bytes(policy["provenance_key_file"], 32)
        if len(key) != 32 or hmac.compare_digest(key, approval):
            raise ValueError("independent provenance key required")
        os.environ["SQLITE_TMPDIR"] = str(scratch)
        os.environ["TMPDIR"] = str(scratch)

        def precommit():
            report_phase("PRECOMMIT_WINDOW")
            lease(policy)
            ensure_space(policy, catalog_root)
            report_phase("COMMIT")

        cap = max(binding["plaintext_length"], policy["catalog_bytes"])
        _, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
        if hard != resource.RLIM_INFINITY and cap > hard:
            raise NamedHistoryLimit(
                LimitKind.FILE_SIZE_CONFIGURATION, "protected file limit unavailable"
            )
        resource.setrlimit(resource.RLIMIT_FSIZE, (cap, hard))
        signal.signal(signal.SIGXFSZ, file_limit)
        signal.signal(signal.SIGALRM, timeout)
        signal.alarm(policy["runtime_seconds"])
        report_phase("CATALOG")
        catalog = _HistoryCatalog(
            catalog_root,
            key=key,
            archive_id=policy["archive_id"],
            enrollment=policy["enrollment"],
            source_instance=policy["source_instance"],
            limits=Limits(
                archive_bytes=binding["plaintext_length"],
                expanded_bytes=policy["max_expanded_bytes"],
                top_level_rows=policy["max_top_level_rows"],
            ),
        )
        if not any(catalog_root.iterdir()):
            catalog.initialize()
        if any(catalog.objects.iterdir()):
            raise ValueError(
                "native protected catalog cannot contain plaintext originals"
            )
        receipt = catalog.ingest_sealed_export(
            ciphertext=policy["ciphertext"],
            identity_file=policy["identity_file"],
            age_executable=policy["age_executable"],
            scratch_root=scratch,
            precommit=precommit,
            report_phase=report_phase,
            database_bytes=policy["catalog_bytes"],
            **binding,
        )
        report_phase("READBACK")
        if catalog.receipt(binding["plaintext_sha256"]) != receipt:
            raise ValueError("reopened catalog receipt mismatch")
        print(SUCCESS.decode("ascii"), end="")
    except (
        AttributeError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
        sqlite3.Error,
        subprocess.SubprocessError,
    ) as error:
        if args.diagnostic_category:
            category = diagnostic_category(error, phase)
            if category not in CATEGORIES:
                category = "CATALOG"
            print(DIAGNOSTIC_PREFIX.decode("ascii") + category, file=sys.stderr)
        else:
            print(
                "Protected native import refused or requires receipt reconciliation",
                file=sys.stderr,
            )
        return 1
    finally:
        signal.alarm(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
