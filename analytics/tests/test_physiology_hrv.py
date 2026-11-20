import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from analytics.preprocess.sources.hrv_adapter import ingest_hrv_csv


def import_csv(tmp_path, contents, **kwargs):
    source = tmp_path / "input.csv"
    source.write_text(contents)
    output = tmp_path / "hrv.parquet"
    report = ingest_hrv_csv(str(source), str(output), **kwargs)
    return pd.read_parquet(output), report, source


def test_mixed_seconds_milliseconds_iso_offsets_are_parsed_per_row(tmp_path):
    data, report, source = import_csv(
        tmp_path,
        "ts,rmssd,source_note\n"
        "1735689600,40,seconds\n"
        "1735689900000,41,milliseconds\n"
        "2025-01-01T10:10:00+10:00,42,offset\n"
        "invalid,43,rejected\n"
        "2025-01-01T00:20:00,44,naive_rejected\n",
    )
    assert data["ts"].tolist() == [1735689600000, 1735689900000, 1735690200000]
    assert data["source_note"].tolist() == ["seconds", "milliseconds", "offset"]
    assert report["input_rows"] == 5
    assert report["rows"] == 3
    assert report["rejected_records"] == report["rejected_input_rows"] == 2
    assert report["assumed_ms_records"] == 3
    assert Path(report["source_artifact"]).read_bytes() == source.read_bytes()
    assert report["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert {r["reason"] for r in report["rejections"]} == {"invalid_timestamp"}


def test_sdnn_is_not_renamed_rmssd_and_seconds_are_explicitly_converted(tmp_path):
    data, report, _ = import_csv(
        tmp_path,
        "ts,metric,value,unit,native_type,source_available_at\n"
        "2025-01-01T00:00:00Z,SDNN,0.04,s,HKQuantityTypeIdentifierHeartRateVariabilitySDNN,\n"
        "2025-01-01T00:05:00Z,RMSSD,25,ms,rmssd,2025-01-01T00:06:00Z\n",
    )
    assert data["metric"].tolist() == ["sdnn", "rmssd"]
    assert data["sdnn"].iloc[0] == 40
    assert pd.isna(data["rmssd"].iloc[0])
    assert data["rmssd"].iloc[1] == 25
    assert data["original_value"].iloc[0] == "0.04"
    assert data["original_unit"].iloc[0] == "s"
    assert data["source_available_at"].iloc[0] == ""
    assert report["metric_counts"] == {"sdnn": 1, "rmssd": 1}
    assert report["assumed_ms_records"] == 0


def test_unsupported_metric_invalid_value_and_unknown_units_are_accounted(tmp_path):
    data, report, _ = import_csv(
        tmp_path,
        "ts,metric,value,unit\n"
        "2025-01-01T00:00:00Z,hrv,40,ms\n"
        "2025-01-01T00:05:00Z,rmssd,not_numeric,ms\n"
        "2025-01-01T00:10:00Z,rmssd,40,unknown\n"
        "2025-01-01T00:15:00Z,rmssd,40,\n"
        "2025-01-01T00:20:00Z,rmssd,0,ms\n",
    )
    assert len(data) == 1
    assert data["value"].iloc[0] == 0
    assert report["rejected_records"] == 4
    assert {r["reason"] for r in report["rejections"]} == {
        "unsupported_metric",
        "invalid_metric_value",
        "missing_or_unsupported_unit",
    }


def test_both_metrics_in_one_source_row_remain_distinct(tmp_path):
    data, report, _ = import_csv(
        tmp_path, "ts,rmssd,sdnn,device\n2025-01-01T00:00:00Z,40,80,test_device\n"
    )
    assert len(data) == 2
    assert set(data["metric"]) == {"rmssd", "sdnn"}
    assert data["source_row"].tolist() == [2, 2]
    assert report["accepted_input_rows"] == 1
    assert data["source_record_json"].nunique() == 1
    assert json.loads(data["source_record_json"].iloc[0])["sdnn"] == "80"


def test_partial_row_rejection_is_distinguishable(tmp_path):
    data, report, _ = import_csv(
        tmp_path, "ts,rmssd,sdnn\n2025-01-01T00:00:00Z,40,invalid\n"
    )
    assert data["metric"].tolist() == ["rmssd"]
    assert report["rejected_input_rows"] == 0
    assert report["partially_rejected_input_rows"] == 1
    assert report["rejected_records"] == 1


def test_conflicting_native_metric_is_rejected(tmp_path):
    data, report, _ = import_csv(
        tmp_path,
        "ts,metric,value,unit,native_type\n"
        "2025-01-01T00:00:00Z,rmssd,40,ms,HKQuantityTypeIdentifierHeartRateVariabilitySDNN\n",
    )
    assert data.empty
    assert report["rejections"][0]["reason"] == "conflicting_metric_identifiers"


def test_repeat_import_retains_one_original_and_separate_run_manifests(tmp_path):
    data, first, source = import_csv(tmp_path, "ts,rmssd\n1735689600,40\n")
    second = ingest_hrv_csv(str(source), str(tmp_path / "hrv.parquet"))
    assert first["source_artifact"] == second["source_artifact"]
    assert first["manifest"] != second["manifest"]
    assert len(list((tmp_path / "source_artifacts").glob("*.csv"))) == 1
    assert len(list((tmp_path / "import_manifests").glob("*.json"))) == 2
    assert second["rows"] == 1


def test_explicit_numeric_unit_handles_early_epoch_milliseconds(tmp_path):
    data, report, _ = import_csv(tmp_path, "ts,rmssd\n1000,40\n", timestamp_unit="ms")
    assert data["ts"].iloc[0] == 1000
    assert report["timestamp_policy"] == "explicit ms"


def test_explicit_source_timezone_preserves_naive_interpretation_assumption(tmp_path):
    data, report, _ = import_csv(
        tmp_path, "ts,rmssd\n2025-01-01T10:00:00,40\n", naive_timezone="Pacific/Guam"
    )
    assert data["ts"].iloc[0] == 1735689600000
    assert report["naive_timezone"] == "Pacific/Guam"


def test_ambiguous_local_time_is_rejected_not_guessed(tmp_path):
    data, report, _ = import_csv(
        tmp_path,
        "ts,rmssd\n2025-11-02T01:30:00,40\n",
        naive_timezone="America/New_York",
    )
    assert data.empty
    assert report["rejections"][0]["reason"] == "invalid_timestamp"


def test_source_artifact_collision_never_overwrites_original(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("ts,rmssd\n1735689600,40\n")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    artifacts = tmp_path / "source_artifacts"
    artifacts.mkdir()
    original = artifacts / f"{digest}.csv"
    original.write_bytes(b"unrelated data")
    with pytest.raises(ValueError, match="content hash"):
        ingest_hrv_csv(str(source), str(tmp_path / "hrv.parquet"))
    assert original.read_bytes() == b"unrelated data"
