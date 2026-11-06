"""Independent V01 regressions: synthetic data and local package builds only."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

from analytics.events import window_builder
from analytics.preprocess.sources.nightscout_adapter import import_json_file
from mother.physiology.archive import Archive
from mother.physiology.contracts import (
    canonical_json,
    content_hash,
    make_event,
    validate_record,
)
from mother.physiology import imports
from mother.physiology.replay import build_replay
from mother.physiology.time import epoch_ms


START = "2026-01-10T00:00:00Z"
END = "2026-01-10T01:00:00Z"
SUBJECT = "v01-synthetic"


def _revision(run_id, revision_id="v01-revision"):
    raw = {"native_id": "v01-native", "fixture": "independent acceptance"}
    return {
        "revision_id": revision_id,
        "source_instance": "v01-source",
        "collection": "fixture",
        "source_key": "native:v01-native",
        "native_id": "v01-native",
        "revision_hash": content_hash(raw),
        "raw_json": canonical_json(raw),
        "first_seen_at": START,
        "ingested_at": START,
        "source_available_at": None,
        "source_modified_at": None,
        "measurement_start": START,
        "measurement_end": END,
        "import_run_id": run_id,
        "disposition": "accepted",
        "rejection_reason": None,
        "artifact_sha256": None,
        "observed_at": START,
    }


def test_v01_missing_measurements_remain_present_partial_coverage(tmp_path):
    """Missing records must not become an absent-with-records bundle contradiction."""
    source = tmp_path / "missing.json"
    source.write_text(
        json.dumps(
            [
                {
                    "_id": "missing-sgv",
                    "date": epoch_ms(START),
                    "sgv": None,
                    "units": "mg/dL",
                }
            ]
        )
    )
    archive_path = tmp_path / "archive.sqlite3"
    import_json_file(
        source,
        archive_path=archive_path,
        source_instance="v01-nightscout",
        subject_id=SUBJECT,
    )
    with Archive(archive_path) as archive:
        bundle = build_replay(
            archive,
            subject_id=SUBJECT,
            start=START,
            end=END,
            cadence_seconds={"glucose": 300},
        )
    coverage = next(row for row in bundle["coverage"] if row["channel"] == "glucose")
    assert coverage["count"] == 1 and coverage["valid_count"] == 0
    assert bundle["observations"][0]["value_status"] == "missing"
    assert (
        coverage["status"] == "partial"
    ), "A supplied missing record is not an absent channel"
    assert coverage["gaps"][0]["reason"] == "no_valid_observations"


def test_v01_unknown_occurrence_event_is_retained_by_recorded_time(tmp_path):
    """Select an untimed annotation by its known recording time without inventing occurrence."""
    with Archive(tmp_path / "archive.sqlite3") as archive:
        run_id = archive.begin_run(
            "v01-source", "fixture", "v01/1", {"subject_id": SUBJECT}, started_at=START
        )
        marker = make_event(
            id="v01-untimed-marker",
            subject_id=SUBJECT,
            event_kind="user_marker",
            occurrence_start=None,
            occurrence_end=None,
            known_at=None,
            recorded_at="2026-01-10T00:10:00Z",
            source="v01-source",
            source_revision_id="v01-revision",
            payload={"text": "Contact was adjusted; occurrence time unknown"},
        )
        archive.commit_batch(run_id, [_revision(run_id)], [marker], complete=True)
        bundle = build_replay(archive, subject_id=SUBJECT, start=START, end=END)
    assert [row["id"] for row in bundle["events"]] == [marker["id"]]
    assert bundle["events"][0]["occurrence_start"] is None
    assert bundle["events"][0]["known_at"] is None
    assert bundle["events"][0]["recorded_at"] == "2026-01-10T00:10:00Z"


def test_v01_canonical_session_can_persist_and_replay_its_source_references(tmp_path):
    """A valid session has plural source_revision_ids, not a singular observation field."""
    session = {
        "schema_version": "1.0.0",
        "record_type": "session",
        "id": "v01-session",
        "subject_id": SUBJECT,
        "processing_version": "v01/1",
        "start": START,
        "end": END,
        "device_ids": ["v01-device"],
        "recording_app": "v01-fixture",
        "firmware": None,
        "configuration": {},
        "body_site": None,
        "clock": {},
        "garment": {},
        "source_revision_ids": ["v01-revision"],
    }
    validate_record(session)
    with Archive(tmp_path / "archive.sqlite3") as archive:
        run_id = archive.begin_run(
            "v01-source", "fixture", "v01/1", {"subject_id": SUBJECT}, started_at=START
        )
        archive.commit_batch(run_id, [_revision(run_id)], [session], complete=True)
        assert archive.current_records("session") == [session]
        bundle = build_replay(archive, subject_id=SUBJECT, start=START, end=END)
    assert [row["id"] for row in bundle["sessions"]] == [session["id"]]
    assert {row["id"] for row in bundle["source_revisions"]} == set(
        session["source_revision_ids"]
    )


def test_v01_file_event_reprocessing_preserves_both_versions(tmp_path, monkeypatch):
    """Processing-version changes need new event identities as well as observation identities."""
    source = tmp_path / "watch.xml"
    source.write_text(
        """<HealthData>
<Workout uuid="v01-workout" workoutActivityType="HKWorkoutActivityTypeWalking" startDate="2026-01-10 00:00:00 +0000" endDate="2026-01-10 00:30:00 +0000"/>
<Record uuid="v01-hr" type="HKQuantityTypeIdentifierHeartRate" unit="count/min" value="100" startDate="2026-01-10 00:10:00 +0000" endDate="2026-01-10 00:10:00 +0000" sourceName="Synthetic fixture"/>
</HealthData>"""
    )
    old_version = imports.ADAPTER_VERSION
    new_version = "v01-export-reader/2"
    with Archive(tmp_path / "archive.sqlite3") as archive:
        imports.import_file(
            archive,
            source,
            format="apple_xml",
            source_instance="v01-watch",
            subject_id=SUBJECT,
            now="2026-01-11T00:00:00Z",
        )
        monkeypatch.setattr(imports, "ADAPTER_VERSION", new_version)
        imports.import_file(
            archive,
            source,
            format="apple_xml",
            source_instance="v01-watch",
            subject_id=SUBJECT,
            now="2026-01-12T00:00:00Z",
        )
        records = archive.current_records()
        assert len(records) == 4
        assert {row["processing_version"] for row in records} == {
            old_version,
            new_version,
        }
        assert len(archive.revisions()) == 2
        with pytest.raises(ValueError, match="processing version"):
            build_replay(archive, subject_id=SUBJECT, start=START, end=END)
        bundle = build_replay(
            archive,
            subject_id=SUBJECT,
            start=START,
            end=END,
            processing_versions=[new_version],
        )
        assert len(bundle["events"]) == 1 and len(bundle["observations"]) == 1
        assert all(
            row["processing_version"] == new_version
            for row in bundle["events"] + bundle["observations"]
        )


def test_v01_installed_resources_and_default_config_do_not_depend_on_cwd(
    tmp_path, monkeypatch
):
    """Build locally without network, then inspect the actual wheel resource inventory."""
    source_root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(tmp_path)
    cfg = window_builder.load_cfg(window_builder.CFG_PATH)
    assert cfg.get("horizon_minutes") == [
        30,
        60,
    ], "Default config disappeared outside the repository cwd"
    assert cfg.get("availability_policy") == "assume_at_measurement"
    staging = tmp_path / "package-source"
    staging.mkdir()
    shutil.copy2(source_root / "pyproject.toml", staging / "pyproject.toml")
    for directory in ("mother", "analytics"):
        shutil.copytree(
            source_root / directory,
            staging / directory,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    wheels = tmp_path / "wheels"
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-index",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheels),
            str(staging),
        ],
        text=True,
        capture_output=True,
        timeout=45,
        check=False,
        env={**os.environ, "PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1"},
    )
    assert process.returncode == 0, process.stdout + process.stderr
    wheel = next(wheels.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    assert {
        "mother/physiology/schemas/v1.schema.json",
        "mother/physiology/migrations/0001_archive.sql",
        "mother/physiology/fixtures/watch.xml",
        "analytics/config/pipeline.yaml",
    } <= names
