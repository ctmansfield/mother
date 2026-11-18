"""Offline commands, explicit input paths, isolated outputs, and terse errors."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

from .adapters import healthkit_archive, native_replay
from .contracts import ContractError, canonical
from .model import replay
from .storage import Store


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline MSE reference replay; no services or treatment authority")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("import-healthkit", help="Read a copied v0.3 archive; preserve original bytes in a separate replay database")
    ingest.add_argument("input", type=Path)
    ingest.add_argument("--subject", required=True)
    ingest.add_argument("--source-instance", required=True)
    ingest.add_argument("--db", type=Path, required=True)
    native = sub.add_parser("import-replay", help="Read new mse.replay/0.1 synthetic fixture or explicit export")
    native.add_argument("input", type=Path)
    native.add_argument("--db", type=Path, required=True)
    run = sub.add_parser("replay")
    run.add_argument("--db", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--source-receipt-cutoff", help="One global retrospective snapshot receipt/end filter; NOT online or per-state as-available replay")
    run.add_argument("--mode", choices=["retrospective_snapshot"], default="retrospective_snapshot")
    args = parser.parse_args(argv)
    try:
        if args.command.startswith("import"):
            # Read once: hashes and parser consume the same exact bytes.
            if args.input.stat().st_size > 64 * 1024 * 1024:
                raise ContractError("Prototype import limited to 64 MiB")
            data = args.input.read_bytes()
            if len(data) > 64 * 1024 * 1024:
                raise ContractError("Prototype import limited to 64 MiB")
            if args.command == "import-healthkit":
                records, deleted, metadata = healthkit_archive(data, subject_id=args.subject, source_instance=args.source_instance)
            else:
                records, deleted, metadata = native_replay(data)
            with Store(args.db) as store:
                result = store.import_batch(data, records, deleted, metadata)
            print(canonical(result))
        else:
            if not args.db.exists():
                raise ContractError("Replay requires an existing MSE database")
            if args.output.exists() or args.output.is_symlink():
                raise ContractError("Output exists; choose a new output filename")
            with Store(args.db) as store:
                result = replay(store, source_receipt_cutoff=args.source_receipt_cutoff, replay_mode=args.mode)
            args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
                stream.write("\n")
            print(canonical({"run_id": result["run_id"], "active_observations": result["active_observation_count"],
                             "state_estimates": len(result["states"]), "output_written": True,
                             "uncertainty_status": "uncalibrated_reference_model"}))
        return 0
    except (ContractError, OSError, sqlite3.Error) as exc:
        if isinstance(exc, ContractError):
            print("MSE rejected operation: " + str(exc), file=sys.stderr)
        else:
            print("MSE I/O failure (details suppressed to avoid exposing record paths)", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
