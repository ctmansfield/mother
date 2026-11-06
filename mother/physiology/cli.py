"""Offline source imports and replay; no notification or treatment actions."""

import argparse
import json
from pathlib import Path

from .archive import Archive
from .demo import create_demo
from .imports import import_file
from .replay import build_replay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("import")
    ingest.add_argument("--archive", required=True)
    ingest.add_argument("--source", required=True)
    ingest.add_argument(
        "--format", required=True, choices=["apple_xml", "polar_tcx", "spot_csv"]
    )
    ingest.add_argument("--source-instance", required=True)
    ingest.add_argument("--subject", required=True)
    replay = commands.add_parser("replay")
    replay.add_argument("--archive", required=True)
    replay.add_argument("--subject", required=True)
    replay.add_argument("--start", required=True)
    replay.add_argument("--end", required=True)
    replay.add_argument("--out", required=True)
    replay.add_argument(
        "--cadence", action="append", default=[], metavar="CHANNEL=SECONDS"
    )
    replay.add_argument("--processing-version", action="append")
    demo = commands.add_parser("demo")
    demo.add_argument(
        "--output-dir", required=True, help="New directory for synthetic outputs"
    )
    args = parser.parse_args()
    if args.command == "demo":
        result = create_demo(args.output_dir)
    elif args.command == "import":
        with Archive(args.archive) as archive:
            result = import_file(
                archive,
                args.source,
                format=args.format,
                source_instance=args.source_instance,
                subject_id=args.subject,
            )
    else:
        cadences = {}
        for value in args.cadence:
            key, seconds = value.split("=", 1)
            cadences[key] = float(seconds)
        with Archive(args.archive) as archive:
            result = build_replay(
                archive,
                subject_id=args.subject,
                start=args.start,
                end=args.end,
                cadence_seconds=cadences,
                processing_versions=args.processing_version,
            )
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        result = {
            "out": str(target),
            "observations": len(result["observations"]),
            "events": len(result["events"]),
            "evidence_level": "imported_unvalidated",
        }
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
