from pathlib import Path
import json

import pytest

from mother.physiology.archive import Archive
from mother.physiology.contracts import validate_record
from mother.physiology.demo import create_demo
from mother.physiology.imports import import_file
from mother.physiology.replay import build_replay
from mother.physiology.units import normalize_scalar

FIXTURES = Path(__file__).parents[2] / "mother" / "physiology" / "fixtures"
NOW = "2026-11-06T10:00:00Z"


def load(archive, name="watch.xml", format="apple_xml", source="test-watch", now=NOW):
    return import_file(
        archive,
        FIXTURES / name,
        format=format,
        source_instance=source,
        subject_id="synthetic",
        now=now,
    )


def test_apple_iso_methods_rejections_original_retention_and_idempotent_restart(
    tmp_path,
):
    path = tmp_path / "archive.sqlite3"
    with Archive(path) as archive:
        result = load(archive)
        assert result["counts"] == {
            "received": 7,
            "accepted": 5,
            "rejected": 1,
            "unsupported": 1,
            "ambiguous_identity": 7,
            "normalized": 5,
        }
        records = archive.current_records()
        sdnn = next(r for r in records if r.get("channel") == "hrv_sdnn")
        assert sdnn["native_type"] == "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"
        assert sdnn["value"] == 40 and sdnn["unit"] == "ms"
        assert sdnn["measurement_start"] == "2026-01-10T13:00:00Z"
        assert sdnn["source_available_at"] is None
        assert not any(r.get("channel") == "hrv_rmssd" for r in records)
        original = archive.connection.execute(
            "SELECT content FROM raw_artifacts WHERE sha256=?",
            (result["artifact_sha256"],),
        ).fetchone()[0]
        assert bytes(original) == (FIXTURES / "watch.xml").read_bytes()
        original_ids = {r["id"] for r in records}
    with Archive(path) as archive:
        load(archive, now="2026-11-07T10:00:00Z")
        assert {r["id"] for r in archive.current_records()} == original_ids
        assert len(archive.revisions()) == 7
        assert all(r["first_seen_at"] == NOW for r in archive.revisions())


def test_tcx_keeps_hr_separate_from_rr_ecg_and_exercise_cessation(tmp_path):
    with Archive(tmp_path / "archive.sqlite3") as archive:
        result = load(archive, "polar.tcx", "polar_tcx", "test-polar")
        records = archive.current_records()
        assert result["counts"]["accepted"] == 5
        assert len([r for r in records if r.get("channel") == "heart_rate"]) == 4
        assert not any(r.get("channel") in {"rr", "ecg", "hrv_rmssd"} for r in records)
        context = next(r for r in records if r["record_type"] == "event")
        assert context["event_kind"] == "context"
        assert context["payload"]["exercise_end"] is None
        assert all(r.get("device_id") is None for r in records)


def test_spot_group_and_unknown_analyte_specimen_are_preserved(tmp_path):
    with Archive(tmp_path / "archive.sqlite3") as archive:
        load(archive, "spots.csv", "spot_csv", "test-spots")
        records = archive.current_records()
        bp = [r for r in records if r["channel"].startswith("blood_pressure")]
        assert len(bp) == 2
        assert {r["measurement_group_id"] for r in bp} == {"fixture-bp-1"}
        ketone = next(r for r in records if r["channel"] == "ketone")
        assert ketone["specimen"] is None and ketone["metadata"]["analyte"] is None
        assert ketone["epistemic_type"] == "reported"


def test_unrelated_equal_measurements_are_not_merged(tmp_path):
    with Archive(tmp_path / "archive.sqlite3") as archive:
        load(archive, source="source-a")
        load(archive, source="source-b")
        assert len(archive.current_records()) == 10


def test_invalid_xml_preserves_original_without_advancing_checkpoint(tmp_path):
    source = tmp_path / "broken.xml"
    source.write_text("<HealthData><Record>")
    with Archive(tmp_path / "archive.sqlite3") as archive:
        with pytest.raises(Exception):
            import_file(
                archive,
                source,
                format="apple_xml",
                source_instance="broken",
                subject_id="synthetic",
                now=NOW,
            )
        assert archive.checkpoint("broken", "apple_xml") is None
        assert len(archive.current_records()) == 0
        assert (
            archive.connection.execute("SELECT count(*) FROM raw_artifacts").fetchone()[
                0
            ]
            == 1
        )
        assert (
            archive.connection.execute("SELECT status FROM import_runs").fetchone()[0]
            == "failed"
        )


def test_replay_has_explicit_absence_source_clocks_and_no_interpolation(tmp_path):
    with Archive(tmp_path / "archive.sqlite3") as archive:
        load(archive)
        load(archive, "spots.csv", "spot_csv", "test-spots")
        bundle = build_replay(
            archive,
            subject_id="synthetic",
            start="2026-01-10T06:00:00Z",
            end="2026-01-11T00:00:00Z",
            cadence_seconds={"heart_rate": 300},
        )
        for record in (
            bundle["observations"] + bundle["events"] + bundle["source_revisions"]
        ):
            validate_record(record)
        assert (
            len([r for r in bundle["observations"] if r["channel"] == "lactate"]) == 1
        )
        assert all(r["source_available_at"] is None for r in bundle["observations"])
        assert (
            next(c for c in bundle["coverage"] if c["channel"] == "hrv_rmssd")["status"]
            == "absent"
        )
        assert next(c for c in bundle["coverage"] if c["channel"] == "heart_rate")[
            "gaps"
        ]
        assert (
            bundle["metadata"]["timing_policy"]
            == "retrospective_current_revision_projection"
        )


def test_synthetic_cross_source_demo_retains_older_history(tmp_path):
    manifest = create_demo(tmp_path / "demo")
    assert manifest["personal_performance_claim"] is False
    bundle = json.loads(Path(manifest["replay"]).read_text())
    assert bundle["metadata"]["evidence_level"] == "synthetic_integration"
    channels = {r["channel"] for r in bundle["observations"]}
    assert {"heart_rate", "glucose", "hrv_sdnn", "lactate", "ketone"} <= channels
    with Archive(manifest["archive"]) as archive:
        assert any(
            r.get("measurement_start", "").startswith("2025-06-01")
            for r in archive.current_records()
        )


def test_scalar_units_reject_guesses_and_preserve_zero():
    assert normalize_scalar("glucose", 5, "mmol/L") == (90.07795, "mg/dL")
    assert normalize_scalar("heart_rate", 0, "bpm") == (0, "beats/min")
    for value, unit in [(True, "bpm"), ("nan", "bpm"), (10, None), (10, "unknown")]:
        with pytest.raises(ValueError):
            normalize_scalar("heart_rate", value, unit)


def _session(references):
    return {
        "schema_version": "1.0.0",
        "record_type": "session",
        "id": "session:context-fixture",
        "subject_id": "synthetic",
        "processing_version": "context-fixture/1",
        "start": "2026-01-09T00:00:00Z",
        "end": "2026-01-09T01:00:00Z",
        "device_ids": [],
        "recording_app": "synthetic fixture",
        "firmware": None,
        "configuration": {},
        "body_site": None,
        "clock": {},
        "garment": {},
        "source_revision_ids": references,
    }


def test_replay_retains_referenced_session_outside_view_and_all_its_sources(tmp_path):
    with Archive(tmp_path / "archive.sqlite3") as archive:
        load(archive)
        observations = [
            r for r in archive.current_records() if r["record_type"] == "observation"
        ]
        references = [r["source_revision_id"] for r in observations[:2]]
        session = _session(references)
        point = dict(
            observations[0],
            id="observation:session-fixture",
            session_id=session["id"],
            processing_version="context-fixture/1",
        )
        run = archive.begin_run(
            "test-watch", "apple_xml", "context-fixture/1", {"subject_id": "synthetic"}
        )
        archive.commit_batch(run, normalized_records=[session, point], complete=True)
        bundle = build_replay(
            archive,
            subject_id="synthetic",
            start="2026-01-10T00:00:00Z",
            end="2026-01-11T00:00:00Z",
            processing_versions=["context-fixture/1"],
        )
        assert bundle["sessions"] == [session]
        assert bundle["observations"] == [point]
        assert {r["id"] for r in bundle["source_revisions"]} == set(references)


def test_session_unknown_lineage_fails_transactionally(tmp_path):
    with Archive(tmp_path / "archive.sqlite3") as archive:
        load(archive)
        source = archive.current_records()[0]["source_revision_id"]
        run = archive.begin_run(
            "test-watch", "apple_xml", "context-fixture/1", {"subject_id": "synthetic"}
        )
        with pytest.raises(ValueError, match="unresolved source lineage"):
            archive.commit_batch(
                run,
                normalized_records=[_session([source, "missing-revision"])],
                complete=True,
            )
        assert archive.current_records("session") == []
        assert archive.import_run(run)["status"] == "running"


def test_session_cannot_attach_another_subjects_source(tmp_path):
    with Archive(tmp_path / "archive.sqlite3") as archive:
        load(archive)
        import_file(
            archive,
            FIXTURES / "watch.xml",
            format="apple_xml",
            source_instance="other-watch",
            subject_id="another-synthetic-subject",
            now=NOW,
        )
        anchor = archive.current_records(source_instance="test-watch")[0][
            "source_revision_id"
        ]
        other = archive.current_records(source_instance="other-watch")[0][
            "source_revision_id"
        ]
        run = archive.begin_run(
            "test-watch", "apple_xml", "context-fixture/1", {"subject_id": "synthetic"}
        )
        with pytest.raises(ValueError, match="different subject"):
            archive.commit_batch(
                run, normalized_records=[_session([anchor, other])], complete=True
            )
        assert archive.current_records("session") == []
