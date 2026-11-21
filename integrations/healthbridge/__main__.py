"""Summarize a bounded, synthetic capture from stdin without retaining it."""
from __future__ import annotations

import argparse
import sys

from .capture import CaptureError, CaptureLimits
from .export import canonical_json, export_sha256, normalize_capture


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse messages can echo raw argument values.
        self.exit(2, "healthbridge: invalid arguments; see --help\n")


def main() -> int:
    defaults = CaptureLimits()
    parser = _Parser(description="Verify a synthetic HealthArchive capture from stdin.")
    parser.add_argument("--subject-id", required=True)
    parser.add_argument("--source-instance", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--capture-id", required=True)
    parser.add_argument("--capture-kind", required=True, choices=("full_file", "partial"))
    for name, ceiling in vars(defaults).items():
        parser.add_argument(
            "--max-" + name.replace("_", "-"),
            type=int,
            default=ceiling,
            help=f"positive bound, at most {ceiling}",
        )
    args = parser.parse_args()
    requested = {name: getattr(args, "max_" + name) for name in vars(defaults)}
    if any(not 1 <= value <= getattr(defaults, name) for name, value in requested.items()):
        parser.error("Limits outside permitted range")
    limits = CaptureLimits(**requested)
    try:
        original = sys.stdin.buffer.read(limits.byte_length + 1)
        export = normalize_capture(
            original,
            subject_id=args.subject_id,
            source_instance=args.source_instance,
            batch_id=args.batch_id,
            capture_id=args.capture_id,
            capture_kind=args.capture_kind,
            limits=limits,
        )
    except CaptureError:
        print("healthbridge: capture rejected", file=sys.stderr)
        return 1
    except OSError:
        print("healthbridge: capture read failed", file=sys.stderr)
        return 1

    summary = {
        "artifact_sha256": export["artifact"]["sha256"],
        "byte_length": export["artifact"]["byte_length"],
        "deletion_count": sum(row["operation"] == "delete" for row in export["revisions"]),
        "export_sha256": export_sha256(export),
        "loss_count": len(export["losses"]),
        "schema_version": export["schema_version"],
        "upsert_count": sum(row["operation"] == "upsert" for row in export["revisions"]),
    }
    sys.stdout.buffer.write(canonical_json(summary) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
