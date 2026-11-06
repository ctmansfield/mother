"""Offline acceptance tests for retained history, identity and API exhaustion."""

from datetime import timedelta
import hashlib
import json
import sqlite3
import subprocess
import sys

import pandas as pd
import pytest
import requests

from analytics.preprocess.sources import nightscout_adapter as ns
from mother.physiology.archive import Archive
from mother.physiology.contracts import (
    content_hash,
    stable_id,
)
from mother.physiology.time import epoch_ms, parse_timestamp, utc_iso


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Tests must inject a fixture client; network is disabled")

    monkeypatch.setattr(requests.sessions.Session, "request", blocked)


class Response:
    def __init__(self, records=None, *, content=None, error=None):
        self.content = content if content is not None else json.dumps(records).encode()
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error


class Server:
    def __init__(self, records, treatments=(), *, fail_after=None):
        self.records = list(records)
        self.treatments = list(treatments)
        self.calls = []
        self.fail_after = fail_after

    def get(self, url, *, params, **kwargs):
        self.calls.append((url, params.copy()))
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            raise requests.ConnectionError("synthetic interruption token=do-not-log")
        if "/entries/" in url:
            left, right = params["find[date][$gte]"], params["find[date][$lt]"]
            rows = [r for r in self.records if left <= r["date"] < right]
            rows.sort(key=lambda r: r["date"], reverse=True)
        else:
            left, right = parse_timestamp(
                params["find[created_at][$gte]"]
            ), parse_timestamp(params["find[created_at][$lt]"])
            rows = [
                r
                for r in self.treatments
                if left <= parse_timestamp(r["created_at"]) < right
            ]
            rows.sort(key=lambda r: parse_timestamp(r["created_at"]), reverse=True)
        return Response(rows[: params["count"]])

    def client(self, page_size=7, **kwargs):
        return ns.NightscoutV1Client(
            "https://synthetic.invalid",
            page_size=page_size,
            verified_page_size=page_size,
            capability_evidence="synthetic-v1-fixture/1",
            request_get=self.get,
            **kwargs,
        )


def entry(identity, when, value=100, **extra):
    row = {"_id": identity, "date": epoch_ms(when), "sgv": value, "type": "sgv"}
    row.update(extra)
    return row


def file_import(
    tmp_path,
    rows,
    *,
    name="source.json",
    source="fixture",
    subject="self",
    collection="entries",
    unit="mg/dL",
    archive=None,
):
    path = tmp_path / name
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return ns.import_json_file(
        path,
        archive_path=archive or tmp_path / "archive.sqlite3",
        source_instance=source,
        subject_id=subject,
        collection=collection,
        sgv_unit=unit,
    )


def run_sync(tmp_path, server, start, end, **kwargs):
    return ns.sync_range(
        start,
        end,
        archive_path=tmp_path / "archive.sqlite3",
        analytics_dir=tmp_path / "views",
        source_instance="fixture",
        client=server.client(),
        **kwargs,
    )


def test_more_than_six_months_survive_later_incremental_sync_and_restart(tmp_path):
    start = parse_timestamp("2025-01-01T00:00:00Z")
    rows = [
        entry(str(i), start + timedelta(days=i, hours=1), 90 + i % 50)
        for i in range(212)
    ]
    first = run_sync(tmp_path, Server(rows), start, start + timedelta(days=213))
    assert first["views"]["entries"] == 212
    assert first["runs"]["entries"]["counts"]["accepted"] == 212
    rows.append(entry("later", start + timedelta(days=214, hours=1), 110))
    later_server = Server(rows)
    second = ns.incremental_sync(
        14,
        archive_path=tmp_path / "archive.sqlite3",
        analytics_dir=tmp_path / "views",
        source_instance="fixture",
        client=later_server.client(),
        end=start + timedelta(days=215),
    )
    view = pd.read_parquet(tmp_path / "views" / "cgm.parquet")
    assert second["entries"] == 213
    assert view.ts.min() == epoch_ms(start + timedelta(hours=1))
    assert all("/treatments" not in url for url, _ in later_server.calls)
    # A distinct interpreter proves the archive does not depend on process memory.
    code = "import sys; from mother.physiology.archive import Archive; a=Archive(sys.argv[1]); print(len(a.current_records())); a.close()"
    restarted = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path / "archive.sqlite3")],
        capture_output=True,
        text=True,
        check=True,
    )
    assert restarted.stdout.strip() == "213"


def test_bounded_subdivision_includes_boundaries_and_does_not_count_parent_copies(
    tmp_path,
):
    start = parse_timestamp("2025-01-01T00:00:00Z")
    rows = [entry(str(i), start + timedelta(minutes=i)) for i in range(31)]
    server = Server(rows)
    result = run_sync(tmp_path, server, start, start + timedelta(minutes=30))
    run = result["runs"]["entries"]
    assert run["status"] == "complete"
    assert run["counts"]["returned_records"] == 30
    assert run["counts"]["new_revisions"] == 30
    assert len(server.calls) > 1
    assert any(item["saturated"] for item in run["counts"]["response_artifacts"])
    assert result["views"]["entries"] == 30
    assert pd.read_parquet(tmp_path / "views" / "cgm.parquet").ts.max() == epoch_ms(
        start + timedelta(minutes=29)
    )


def test_repeat_correction_and_reversion_preserve_original_revision_times(tmp_path):
    original = entry("same", "2025-02-01T12:00:00Z", 101, device="uploader")
    first = file_import(tmp_path, [original])
    second = file_import(tmp_path, [original], name="again.json")
    corrected = dict(original, sgv=105)
    third = file_import(tmp_path, [corrected], name="corrected.json")
    with Archive(tmp_path / "archive.sqlite3") as archive:
        assert len(archive.revisions()) == 2
        assert len(archive.current_records()) == 1
        assert archive.current_records()[0]["value"] == 105
        first_revision = next(
            r for r in archive.revisions() if json.loads(r["raw_json"])["sgv"] == 101
        )
        initial_times = first_revision["first_seen_at"], first_revision["ingested_at"]
    fourth = file_import(tmp_path, [original], name="reverted.json")
    with Archive(tmp_path / "archive.sqlite3") as archive:
        assert len(archive.revisions()) == 2
        assert len(archive.records(current=False)) == 2
        assert archive.current_records()[0]["value"] == 101
        same_revision = archive.revision(first_revision["revision_id"])
        assert (
            same_revision["first_seen_at"],
            same_revision["ingested_at"],
        ) == initial_times
        assert len(archive.import_runs()) == 4
    assert first["counts"]["new_revisions"] == 1
    assert second["counts"]["new_revisions"] == 0
    assert third["counts"]["new_revisions"] == 1
    assert fourth["counts"]["new_revisions"] == 0


def test_original_bytes_hash_and_canonical_record_hash_have_different_scopes(tmp_path):
    raw = entry("id", "2025-02-01T12:00:00+10:00", 102)
    result = file_import(tmp_path, [raw])
    original_bytes = (tmp_path / "source.json").read_bytes()
    with Archive(tmp_path / "archive.sqlite3") as archive:
        rev = archive.revisions()[0]
        artifact = archive.connection.execute("SELECT * FROM raw_artifacts").fetchone()
        assert bytes(artifact["content"]) == original_bytes
        assert rev["artifact_sha256"] == hashlib.sha256(original_bytes).hexdigest()
        assert rev["revision_hash"] == content_hash(raw)
        assert rev["artifact_sha256"] != rev["revision_hash"]
        assert json.loads(rev["raw_json"]) == raw
        assert (
            archive.checkpoint("fixture", "entries") is None
        )  # File is not API history coverage.
        assert result["request"]["artifact_sha256"] == rev["artifact_sha256"]


def test_modified_and_ingestion_times_are_not_original_availability(tmp_path):
    raw = entry(
        "id",
        "2025-02-01T12:00:00+10:00",
        102,
        srvCreated=epoch_ms("2025-02-02T00:00:00Z"),
        srvModified=epoch_ms("2025-02-03T00:00:00Z"),
        device="possible-uploader",
    )
    file_import(tmp_path, [raw])
    with Archive(tmp_path / "archive.sqlite3") as archive:
        revision = archive.revisions()[0]
        observed = archive.current_records()[0]
        assert revision["source_available_at"] is None
        assert observed["source_available_at"] is None
        assert revision["source_modified_at"] == "2025-02-03T00:00:00Z"
        assert observed["device_id"] is None
        assert observed["metadata"]["source_reported_device"] == "possible-uploader"
        assert observed["measurement_start"] == "2025-02-01T02:00:00Z"
        assert parse_timestamp(observed["first_seen_at"]) > parse_timestamp(
            observed["measurement_start"]
        )


def test_zero_missing_rejected_unsupported_units_and_timestamps_remain_distinct(
    tmp_path,
):
    when = "2025-02-01T12:00:00Z"
    rows = [
        entry("zero", when, 0),
        entry("missing", when, None),
        entry("bad-value", when, "not-a-number"),
        {"_id": "bad-time", "dateString": "unknown", "sgv": 100},
        entry("bad-unit", when, 10, units="widgets"),
        entry("other-type", when, 100, type="mbg"),
        entry("bool", when, True),
        entry("mmol", when, 6, units="mmol/L"),
        entry("conflict", when, 100, dateString="2025-02-02T12:00:00Z"),
    ]
    result = file_import(tmp_path, rows)
    assert result["counts"]["accepted"] == 3
    assert result["counts"]["rejected"] == 5
    assert result["counts"]["unsupported"] == 1
    with Archive(tmp_path / "archive.sqlite3") as archive:
        assert len(archive.revisions()) == len(rows)
        records = {r["metadata"]["native_id"]: r for r in archive.current_records()}
        assert (
            records["zero"]["value"] == 0 and records["zero"]["value_status"] == "valid"
        )
        assert (
            records["missing"]["value"] is None
            and records["missing"]["value_status"] == "missing"
        )
        assert records["mmol"]["value"] == pytest.approx(6 * 18.01559)
        assert records["mmol"]["original_unit"] == "mmol/L"
        assert records["zero"]["original_unit"] is None
        assert "unit_source_api_contract" in records["zero"]["quality_flags"]


def test_unknown_file_unit_is_not_guessed(tmp_path):
    result = file_import(tmp_path, [entry("id", "2025-01-01T00:00:00Z")], unit=None)
    assert result["counts"]["rejected"] == 1
    with Archive(tmp_path / "archive.sqlite3") as archive:
        assert len(archive.revisions()) == 1
        assert not archive.current_records()


def test_equivalent_date_string_offset_is_accepted(tmp_path):
    raw = entry(
        "id", "2025-02-01T02:00:00Z", 102, dateString="2025-02-01T12:00:00+10:00"
    )
    result = file_import(tmp_path, [raw])
    assert result["counts"]["accepted"] == 1
    with Archive(tmp_path / "archive.sqlite3") as archive:
        assert archive.current_records()[0]["metadata"]["original_dateString"].endswith(
            "+10:00"
        )


def test_same_payload_without_native_identity_preserves_ambiguous_occurrences(tmp_path):
    raw = {"date": epoch_ms("2025-01-01T00:00:00Z"), "sgv": 100}
    first = file_import(tmp_path, [raw, raw])
    repeated = file_import(tmp_path, [raw, raw], name="again.json")
    assert first["counts"]["ambiguous_identity_records"] == 2
    assert repeated["counts"]["new_revisions"] == 0
    with Archive(tmp_path / "archive.sqlite3") as archive:
        assert len(archive.current_records()) == 2
        assert all(
            "ambiguous_identity" in r["quality_flags"]
            for r in archive.current_records()
        )


def test_equal_record_from_two_source_namespaces_is_not_independent_deduplication(
    tmp_path,
):
    raw = entry("same-id", "2025-01-01T00:00:00Z")
    file_import(tmp_path, [raw], source="A")
    file_import(tmp_path, [raw], source="B", name="b.json")
    with Archive(tmp_path / "archive.sqlite3") as archive:
        assert len(archive.current_records()) == 2
        assert len({r["source_revision_id"] for r in archive.current_records()}) == 2


def test_source_namespace_cannot_be_silently_reassigned_to_another_subject(tmp_path):
    raw = entry("same-id", "2025-01-01T00:00:00Z")
    file_import(tmp_path, [raw], subject="one")
    with pytest.raises(ValueError, match="different subject"):
        file_import(tmp_path, [dict(raw, sgv=120)], subject="two", name="other.json")
    with Archive(tmp_path / "archive.sqlite3") as archive:
        assert len(archive.revisions()) == 1
        assert archive.current_records()[0]["subject_id"] == "one"
        assert archive.current_records()[0]["value"] == 100
        assert archive.import_runs()[-1]["status"] == "failed"


def test_explicit_deletion_retained_but_absence_never_deletes(tmp_path):
    raw = entry("id", "2025-01-01T00:00:00Z")
    file_import(tmp_path, [raw])
    file_import(tmp_path, [], name="empty.json")
    with Archive(tmp_path / "archive.sqlite3") as archive:
        assert len(archive.current_records()) == 1
    deleted = file_import(
        tmp_path, [{"_id": "id", "isValid": False}], name="deleted.json"
    )
    assert deleted["counts"]["deleted"] == 1
    with Archive(tmp_path / "archive.sqlite3") as archive:
        assert not archive.current_records()
        assert len(archive.records(current=False)) == 1
        assert len(archive.revisions()) == 2
        assert any(r["disposition"] == "deleted" for r in archive.revisions())


def test_unverified_capabilities_refuse_before_any_network(tmp_path):
    server = Server([])
    client = ns.NightscoutV1Client("https://synthetic.invalid", request_get=server.get)
    with pytest.raises(ns.CapabilityError):
        ns.sync_range(
            "2025-01-01T00:00:00Z",
            "2025-01-02T00:00:00Z",
            client=client,
            archive_path=tmp_path / "archive.sqlite3",
            analytics_dir=tmp_path / "views",
        )
    assert server.calls == []
    with Archive(tmp_path / "archive.sqlite3") as archive:
        assert archive.import_runs()[0]["status"] == "incomplete"
        assert archive.checkpoint(client.source_instance, "entries") is None


def test_same_timestamp_saturation_preserves_response_and_refuses_completion(tmp_path):
    when = parse_timestamp("2025-01-01T00:00:00Z")
    server = Server([entry(str(i), when) for i in range(3)])
    with pytest.raises(ns.IncompleteImportError, match="one-millisecond"):
        ns.sync_range(
            when,
            when + timedelta(milliseconds=1),
            client=server.client(2),
            source_instance="fixture",
            archive_path=tmp_path / "archive.sqlite3",
            analytics_dir=tmp_path / "views",
        )
    with Archive(tmp_path / "archive.sqlite3") as archive:
        assert archive.checkpoint("fixture", "entries") is None
        assert archive.import_runs()[0]["status"] == "incomplete"
        assert (
            archive.connection.execute("SELECT COUNT(*) FROM raw_artifacts").fetchone()[
                0
            ]
            == 1
        )


def test_interruption_retains_completed_pages_and_restart_reconciles(tmp_path):
    start = parse_timestamp("2025-01-01T00:00:00Z")
    rows = [entry(str(i), start + timedelta(hours=i)) for i in range(4)]
    interrupted = Server(rows, fail_after=2)
    with pytest.raises(ns.IncompleteImportError):
        ns.sync_range(
            start,
            start + timedelta(hours=4),
            client=interrupted.client(3),
            source_instance="fixture",
            archive_path=tmp_path / "archive.sqlite3",
            analytics_dir=tmp_path / "views",
        )
    with Archive(tmp_path / "archive.sqlite3") as archive:
        assert len(archive.current_records()) == 2
        assert archive.checkpoint("fixture", "entries") is None
        assert archive.import_runs()[0]["status"] == "incomplete"
        assert "do-not-log" not in archive.import_runs()[0]["error"]
    resumed = run_sync(tmp_path, Server(rows), start, start + timedelta(hours=4))
    assert resumed["views"]["entries"] == 4
    assert resumed["runs"]["entries"]["counts"]["new_revisions"] == 2
    with Archive(tmp_path / "archive.sqlite3") as archive:
        assert len(archive.revisions()) == 4
        assert archive.checkpoint("fixture", "entries")["through_ms"] == epoch_ms(
            start + timedelta(hours=4)
        )


def test_failed_checkpoint_write_cannot_report_completion_or_advance_cursor(tmp_path):
    start = parse_timestamp("2025-01-01T00:00:00Z")
    run_sync(tmp_path, Server([entry("old", start)]), start, start + timedelta(days=1))
    with Archive(tmp_path / "archive.sqlite3") as archive:
        before = archive.checkpoint("fixture", "entries")
        archive.connection.execute(
            """CREATE TRIGGER block_checkpoint BEFORE UPDATE ON checkpoints
            BEGIN SELECT RAISE(FAIL, 'synthetic failure'); END"""
        )
    with pytest.raises(sqlite3.IntegrityError):
        run_sync(
            tmp_path,
            Server([entry("new", start + timedelta(days=1))]),
            start + timedelta(days=1),
            start + timedelta(days=2),
        )
    with Archive(tmp_path / "archive.sqlite3") as archive:
        assert archive.checkpoint("fixture", "entries") == before
        assert archive.import_runs()[-1]["status"] == "failed"
        assert (
            len(archive.current_records()) == 2
        )  # Evidence retained, no claimed completed range.


def test_failure_writing_normalized_record_rolls_back_revision_and_checkpoint(tmp_path):
    with Archive(tmp_path / "archive.sqlite3") as archive:
        run = archive.begin_run("fixture", "entries", ns.ADAPTER_VERSION, {})
        raw = entry("id", "2025-01-01T00:00:00Z")
        revision, record = ns._prepare_record(
            archive,
            run,
            raw,
            source_instance="fixture",
            collection="entries",
            subject_id="self",
            artifact_sha256=None,
            observed_at="2026-01-01T00:00:00Z",
            occurrence=0,
            sgv_unit="mg/dL",
        )
        record["measurement_end"] = "2024-01-01T00:00:00Z"
        with pytest.raises(ValueError):
            archive.commit_batch(
                run,
                [revision],
                [record],
                complete=True,
                checkpoint={"cursor": "unsafe"},
            )
        assert archive.revisions() == []
        assert archive.current_records() == []
        assert archive.checkpoint("fixture", "entries") is None
        assert archive.import_run(run)["status"] == "running"


def test_partial_batch_cannot_advance_checkpoint(tmp_path):
    with Archive(tmp_path / "archive.sqlite3") as archive:
        run = archive.begin_run("fixture", "entries", ns.ADAPTER_VERSION, {})
        with pytest.raises(ValueError, match="completed"):
            archive.commit_batch(run, checkpoint={"cursor": "unsafe"})
        assert archive.checkpoint("fixture", "entries") is None


def test_reconciliation_finds_older_late_arrivals_outside_incremental_overlap(tmp_path):
    start = parse_timestamp("2025-01-01T00:00:00Z")
    initial = [
        entry("first", start + timedelta(days=1)),
        entry("last", start + timedelta(days=8)),
    ]
    run_sync(tmp_path, Server(initial), start, start + timedelta(days=10))
    changed = initial + [
        entry("late-old", start + timedelta(days=2)),
        entry("late-overlap", start + timedelta(days=9)),
    ]
    args = dict(
        archive_path=tmp_path / "archive.sqlite3",
        analytics_dir=tmp_path / "views",
        source_instance="fixture",
        end=start + timedelta(days=12),
    )
    incremental = ns.incremental_sync(client=Server(changed).client(), **args)
    assert incremental["entries"] == 3
    reconciled = ns.incremental_sync(
        client=Server(changed).client(), reconcile=True, **args
    )
    assert reconciled["entries"] == 4
    assert reconciled["runs"]["entries"]["request"]["start"] == utc_iso(start)


def test_disjoint_read_does_not_silently_claim_contiguous_coverage(tmp_path):
    run_sync(tmp_path, Server([]), "2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z")
    run_sync(tmp_path, Server([]), "2025-02-01T00:00:00Z", "2025-02-02T00:00:00Z")
    with Archive(tmp_path / "archive.sqlite3") as archive:
        assert (
            archive.checkpoint("fixture", "entries")["through"]
            == "2025-01-02T00:00:00Z"
        )
        assert len(archive.import_runs()) == 2


def test_optional_treatments_preserve_context_without_fabricating_action_or_availability(
    tmp_path,
):
    when = "2025-01-01T01:00:00Z"
    server = Server(
        [entry("cgm", when)],
        [
            {
                "_id": "meal",
                "created_at": when,
                "eventType": "Meal Bolus",
                "carbs": 25,
                "insulin": 0,
            }
        ],
    )
    client = server.client(treatment_dates_normalized=True)
    result = ns.sync_range(
        "2025-01-01T00:00:00Z",
        "2025-01-02T00:00:00Z",
        client=client,
        source_instance="fixture",
        archive_path=tmp_path / "archive.sqlite3",
        analytics_dir=tmp_path / "views",
        include_treatments=True,
    )
    with Archive(tmp_path / "archive.sqlite3") as archive:
        context = archive.current_records("event")[0]
        assert context["event_kind"] == "context"
        assert context["known_at"] is None
        assert context["payload"]["source_record"]["insulin"] == 0
    assert result["views"]["treatments"] == 1
    assert (
        pd.read_parquet(tmp_path / "views" / "treatments.parquet").insulin.iloc[0] == 0
    )


def test_unverified_treatment_storage_does_not_invalidate_completed_entry_archive(
    tmp_path,
):
    server = Server([])
    with pytest.raises(ns.CapabilityError, match="treatment"):
        run_sync(
            tmp_path,
            server,
            "2025-01-01T00:00:00Z",
            "2025-01-02T00:00:00Z",
            include_treatments=True,
        )
    with Archive(tmp_path / "archive.sqlite3") as archive:
        assert archive.checkpoint("fixture", "entries") is not None
        assert archive.checkpoint("fixture", "treatments") is None
        assert [r["status"] for r in archive.import_runs()] == [
            "complete",
            "incomplete",
        ]


def test_legacy_parquet_is_never_silently_overwritten(tmp_path):
    directory = tmp_path / "views"
    directory.mkdir()
    path = directory / "cgm.parquet"
    pd.DataFrame([{"ts": epoch_ms("2024-01-01T00:00:00Z"), "sgv": 99}]).to_parquet(path)
    original = path.read_bytes()
    with pytest.raises(ValueError, match="Legacy Parquet"):
        run_sync(
            tmp_path,
            Server([entry("new", "2025-01-01T01:00:00Z")]),
            "2025-01-01T00:00:00Z",
            "2025-01-02T00:00:00Z",
        )
    assert path.read_bytes() == original
    with Archive(tmp_path / "archive.sqlite3") as archive:
        assert archive.import_runs()[0]["status"] == "complete"
        assert len(archive.current_records()) == 1
        assert (
            ns.export_analysis_views(archive, tmp_path / "new-views", "fixture")[
                "entries"
            ]
            == 1
        )


def test_view_failure_preserves_previous_file_and_archive(tmp_path, monkeypatch):
    run_sync(
        tmp_path,
        Server([entry("id", "2025-01-01T01:00:00Z")]),
        "2025-01-01T00:00:00Z",
        "2025-01-02T00:00:00Z",
    )
    path = tmp_path / "views" / "cgm.parquet"
    before = path.read_bytes()

    def broken(*args, **kwargs):
        raise OSError("synthetic disk-full view failure")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", broken)
    with Archive(tmp_path / "archive.sqlite3") as archive:
        with pytest.raises(OSError):
            ns.export_analysis_views(archive, tmp_path / "views", "fixture")
        assert len(archive.current_records()) == 1
    assert path.read_bytes() == before
    assert not list((tmp_path / "views").glob("*.tmp"))


def test_other_processing_versions_are_preserved_but_excluded_from_compatibility_view(
    tmp_path,
):
    file_import(tmp_path, [entry("id", "2025-01-01T00:00:00Z")])
    with Archive(tmp_path / "archive.sqlite3") as archive:
        original = archive.current_records()[0]
        other = dict(
            original,
            id=stable_id("observation", "different-processing"),
            processing_version="experimental/2",
            value=999,
        )
        run = archive.begin_run("fixture", "entries", "experimental/2", {})
        archive.commit_batch(run, normalized_records=[other], complete=True)
        assert len(archive.current_records()) == 2
        ns.export_analysis_views(archive, tmp_path / "views", "fixture")
        assert pd.read_parquet(tmp_path / "views" / "cgm.parquet").sgv.tolist() == [100]
        duplicate = dict(original, id=stable_id("observation", "bad-duplicate"))
        run = archive.begin_run("fixture", "entries", ns.ADAPTER_VERSION, {})
        archive.commit_batch(run, normalized_records=[duplicate], complete=True)
        with pytest.raises(ValueError, match="Ambiguous duplicate"):
            ns.export_analysis_views(archive, tmp_path / "views", "fixture")


@pytest.mark.parametrize(
    "content",
    [b'{"wrong":"shape"}', b"not-json", b'[{"date":1,"date":2}]', b'[{"sgv":NaN}]'],
)
def test_malformed_response_bytes_are_retained_without_claiming_completion(
    tmp_path, content
):
    client = ns.NightscoutV1Client(
        "https://synthetic.invalid",
        page_size=3,
        verified_page_size=3,
        capability_evidence="synthetic",
        request_get=lambda *args, **kwargs: Response(content=content),
    )
    with pytest.raises(ns.IncompleteImportError):
        ns.sync_range(
            "2025-01-01T00:00:00Z",
            "2025-01-02T00:00:00Z",
            client=client,
            source_instance="fixture",
            archive_path=tmp_path / "archive.sqlite3",
            analytics_dir=tmp_path / "views",
        )
    with Archive(tmp_path / "archive.sqlite3") as archive:
        assert (
            bytes(
                archive.connection.execute(
                    "SELECT content FROM raw_artifacts"
                ).fetchone()[0]
            )
            == content
        )
        assert archive.import_runs()[0]["status"] == "incomplete"
        assert archive.checkpoint("fixture", "entries") is None


def test_malformed_file_retains_original_bytes_and_failure_record(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b"not-json")
    with pytest.raises(ValueError):
        ns.import_json_file(
            path, archive_path=tmp_path / "archive.sqlite3", source_instance="fixture"
        )
    with Archive(tmp_path / "archive.sqlite3") as archive:
        assert archive.import_runs()[0]["status"] == "failed"
        assert (
            bytes(
                archive.connection.execute(
                    "SELECT content FROM raw_artifacts"
                ).fetchone()[0]
            )
            == b"not-json"
        )


def test_out_of_range_response_fails_instead_of_silently_filtering(tmp_path):
    raw = entry("wrong", "2024-01-01T00:00:00Z")
    client = ns.NightscoutV1Client(
        "https://synthetic.invalid",
        page_size=3,
        verified_page_size=3,
        capability_evidence="synthetic",
        request_get=lambda *args, **kwargs: Response([raw]),
    )
    with pytest.raises(ns.IncompleteImportError, match="time-range"):
        ns.sync_range(
            "2025-01-01T00:00:00Z",
            "2025-01-02T00:00:00Z",
            client=client,
            source_instance="fixture",
            archive_path=tmp_path / "archive.sqlite3",
            analytics_dir=tmp_path / "views",
        )


def test_http_error_does_not_persist_token(tmp_path):
    client = ns.NightscoutV1Client(
        "https://synthetic.invalid",
        page_size=3,
        verified_page_size=3,
        capability_evidence="synthetic",
        token="secret-value",
        request_get=lambda *args, **kwargs: Response(
            error=requests.HTTPError("URL?token=secret-value")
        ),
    )
    with pytest.raises(ns.IncompleteImportError) as error:
        ns.sync_range(
            "2025-01-01T00:00:00Z",
            "2025-01-02T00:00:00Z",
            client=client,
            source_instance="fixture",
            archive_path=tmp_path / "archive.sqlite3",
            analytics_dir=tmp_path / "views",
        )
    assert "secret-value" not in str(error.value)
    with Archive(tmp_path / "archive.sqlite3") as archive:
        assert "secret-value" not in json.dumps(archive.import_runs())


def test_unrecognized_database_and_future_schema_are_not_modified(tmp_path):
    path = tmp_path / "unrelated.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE unrelated(value TEXT)")
    with pytest.raises(ValueError, match="unrecognized"):
        Archive(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall() == [("unrelated",)]
    future = tmp_path / "future.sqlite3"
    with Archive(future) as archive:
        archive.connection.execute("UPDATE schema_versions SET version=2")
    with pytest.raises(ValueError, match="Unsupported"):
        Archive(future)


def test_archive_rejects_artifact_hash_mismatch_and_immutable_record_replacement(
    tmp_path,
):
    file_import(tmp_path, [entry("id", "2025-01-01T00:00:00Z")])
    with Archive(tmp_path / "archive.sqlite3") as archive:
        run = archive.begin_run("fixture", "entries", ns.ADAPTER_VERSION, {})
        with pytest.raises(ValueError, match="hash mismatch"):
            archive.commit_batch(
                run, artifacts=[{"sha256": "0" * 64, "content": b"original"}]
            )
        old = archive.current_records()[0]
        with pytest.raises(ValueError, match="immutable normalized"):
            archive.commit_batch(run, normalized_records=[dict(old, value=200)])
        assert archive.current_records()[0]["value"] == 100
