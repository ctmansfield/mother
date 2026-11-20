"""An entirely synthetic, offline acquisition-to-replay demonstration."""

from pathlib import Path
import json

from .archive import Archive
from .imports import import_file
from .replay import build_replay


def create_demo(output_dir):
    # The existing Nightscout reader stays the ingestion boundary.
    from analytics.preprocess.sources.nightscout_adapter import import_json_file

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    archive_path = output / "synthetic.sqlite3"
    fixtures = Path(__file__).parent / "fixtures"
    runs = [
        import_json_file(
            fixtures / "nightscout.json",
            archive_path=archive_path,
            source_instance="synthetic-nightscout",
            subject_id="synthetic-demo",
        )
    ]
    with Archive(archive_path) as archive:
        for format, name, source in [
            ("apple_xml", "watch.xml", "synthetic-apple"),
            ("polar_tcx", "polar.tcx", "synthetic-polar"),
            ("spot_csv", "spots.csv", "synthetic-spots"),
        ]:
            runs.append(
                import_file(
                    archive,
                    fixtures / name,
                    format=format,
                    source_instance=source,
                    subject_id="synthetic-demo",
                )
            )
        bundle = build_replay(
            archive,
            subject_id="synthetic-demo",
            start="2026-01-09T07:00:00Z",
            end="2026-01-10T22:00:00Z",
            cadence_seconds={"glucose": 300},
            evidence_level="synthetic_integration",
        )
    replay_path = output / "synthetic_replay.json"
    replay_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "evidence_level": "synthetic_integration",
        "personal_performance_claim": False,
        "archive": str(archive_path),
        "replay": str(replay_path),
        "imports": runs,
    }
    (output / "import_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest
