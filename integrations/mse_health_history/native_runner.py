"""Synthetic qualification CLI for a protected native Health archive import."""

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

from mother.physiology.contracts import canonical_json

from .catalog import SyntheticHistoryCatalog
from .files import private_path
from .inventory import Limits
from .projection import consumer_snapshot, write_snapshot


def private_bytes(path, size):
    path = Path(path).absolute()
    private_path(path, directory=False)
    with path.open("rb") as stream:
        body = stream.read(size + 1)
    if len(body) > size:
        raise ValueError("protected input exceeds bound")
    return body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("init", "import", "snapshot"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--enrollment", required=True)
    parser.add_argument("--provenance-key-file", required=True)
    parser.add_argument("--bp-cutoff")
    parser.add_argument("--source-instance", default="synthetic-healthkit-store")
    parser.add_argument("--custodian-binding")
    parser.add_argument("--ciphertext")
    parser.add_argument("--identity-file")
    parser.add_argument("--age-executable")
    parser.add_argument("--scratch-root")
    parser.add_argument(
        "--purpose", choices=("mother-bp-cgm-review", "coach-bp-cgm-review")
    )
    parser.add_argument("--consumer-key-file")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-original-bytes", type=int, default=4 * 1024**3)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if not 1 <= args.max_original_bytes <= Limits().archive_bytes:
            raise ValueError("invalid protected original cap")
        key = private_bytes(args.provenance_key_file, 32)
        if len(key) != 32:
            raise ValueError("protected provenance key length mismatch")
        catalog = SyntheticHistoryCatalog(
            args.root,
            enrollment=args.enrollment,
            key=key,
            limits=Limits(archive_bytes=args.max_original_bytes),
            bp_cutoff=args.bp_cutoff,
            source_instance=args.source_instance,
        )
        if args.mode == "init":
            catalog.initialize()
            result = {"status": "synthetic_typed_root_initialized"}
        elif args.mode == "import":
            binding = json.loads(private_bytes(args.custodian_binding, 8192))
            if set(binding) != {
                "receipt",
                "recipient_fingerprint",
                "plaintext_sha256",
                "plaintext_length",
                "age_sha256",
            }:
                raise ValueError("protected export binding fields mismatch")
            receipt = catalog.ingest_sealed_export(
                ciphertext=args.ciphertext,
                identity_file=args.identity_file,
                age_executable=args.age_executable,
                scratch_root=args.scratch_root,
                **binding,
            )
            result = {
                "status": "synthetic_typed_commit_reopened",
                "receipt_id": receipt["receipt_id"],
                "members": len(catalog.members(receipt["sha256"])),
                "normalized_bp_rows": sum(
                    1 for _ in catalog.blood_pressure_lineage(receipt["sha256"])
                ),
                "unnormalized_top_level_rows": receipt["unnormalized_top_level_rows"],
            }
        else:
            output = args.output.absolute()
            private_path(output.parent, directory=True)
            snapshot = consumer_snapshot(
                catalog,
                purpose=args.purpose,
                consumer_key=private_bytes(args.consumer_key_file, 32),
                start=args.start,
                end=args.end,
            )
            write_snapshot(snapshot, output)
            result = {
                "status": "synthetic_read_only_snapshot",
                "rows": len(snapshot["rows"]),
            }
        print(canonical_json(result))
    except (OSError, TypeError, AttributeError, ValueError, sqlite3.Error):
        print("protected native runner refused", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
