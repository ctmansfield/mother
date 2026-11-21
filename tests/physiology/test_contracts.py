import copy
from pathlib import Path
import sqlite3

import pytest

from mother.physiology import contracts
from mother.physiology.time import epoch_ms, parse_timestamp, utc_iso


def observation():
    return contracts.make_observation(
        id="obs:fixture",
        subject_id="synthetic",
        source_revision_id="rev:fixture",
        channel="heart_rate",
        measurement_start="2026-01-01T10:00:00+10:00",
        source_available_at=None,
        first_seen_at="2026-02-01T00:00:00Z",
        ingested_at="2026-02-01T00:00:01Z",
        original_value=0,
        original_unit="beats/min",
        value=0,
        unit="beats/min",
    )


@pytest.mark.parametrize(
    "raw",
    [
        1767225600,
        "1767225600",
        1767225600000,
        "1767225600000",
        "2026-01-01T00:00:00Z",
        "2026-01-01T10:00:00+10:00",
    ],
)
def test_mixed_timestamp_units_represent_the_same_instant(raw):
    assert epoch_ms(raw) == 1767225600000


@pytest.mark.parametrize(
    "raw", [None, True, "NaT", float("nan"), "", "2026-01-01", "2026-01-01T12:00:00"]
)
def test_unknown_or_naive_timestamps_are_rejected(raw):
    with pytest.raises(ValueError):
        parse_timestamp(raw)


def test_naive_localization_rejects_dst_ambiguity_and_nonexistent_time():
    for raw in ["2026-11-01T01:30:00", "2026-03-08T02:30:00"]:
        with pytest.raises(ValueError):
            parse_timestamp(raw, naive_timezone="America/New_York")
    assert (
        utc_iso("2026-01-01T10:00:00", naive_timezone="Pacific/Guam")
        == "2026-01-01T00:00:00Z"
    )


def test_explicit_numeric_unit_handles_early_millisecond_epochs():
    assert epoch_ms(1000, numeric_unit="ms") == 1000
    assert epoch_ms(1000, numeric_unit="s") == 1_000_000


def test_zero_is_valid_and_missing_is_distinct_and_unknown_availability_survives():
    record = observation()
    assert record["value"] == 0
    assert record["source_available_at"] is None
    record["value_status"] = "missing"
    with pytest.raises(ValueError):
        contracts.validate_record(record)
    record["value"] = None
    contracts.validate_record(record)


def test_contract_rejects_unversioned_untraceable_or_reversed_records():
    for change in [
        {"schema_version": "0.0.0"},
        {"lineage": []},
        {"measurement_end": "2025-12-01T00:00:00Z"},
        {"first_seen_at": "2026-03-01T00:00:00Z"},
        {"measurement_start": "2026-01-01T00:00:00"},
        {"value": float("inf")},
    ]:
        record = observation()
        record.update(change)
        with pytest.raises(ValueError):
            contracts.validate_record(record)


def test_derivative_requires_method_and_keeps_observation_separate():
    raw = observation()
    derivative = copy.deepcopy(raw)
    derivative.update(id="obs:derived", epistemic_type="imputed")
    with pytest.raises(ValueError):
        contracts.validate_record(derivative)
    derivative["method"] = "synthetic-test-interpolation-v1"
    contracts.validate_record(derivative)
    assert raw["epistemic_type"] == "measured"


def test_recommendation_acknowledgment_actual_action_and_outcome_remain_distinct():
    kinds = [
        "recommendation",
        "acknowledgment",
        "reported_action",
        "observed_action",
        "outcome",
    ]
    records = [
        contracts.make_event(
            id=f"event:{kind}",
            subject_id="synthetic",
            event_kind=kind,
            recorded_at="2026-01-01T00:00:00Z",
            source="fixture",
            related_ids=["event:recommendation"] if kind != "recommendation" else [],
        )
        for kind in kinds
    ]
    assert [r["event_kind"] for r in records] == kinds
    assert all(r["occurrence_start"] is None for r in records)
    assert all(r["known_at"] is None for r in records)


def test_canonical_hash_is_order_independent_and_not_source_bytes():
    assert contracts.content_hash({"a": 1, "b": 2}) == contracts.content_hash(
        {"b": 2, "a": 1}
    )
    assert contracts.stable_id("revision", "device-a", "1") != contracts.stable_id(
        "revision", "device-b", "1"
    )


def test_sqlite_migration_is_additive_and_idempotent():
    migration = Path(contracts.__file__).parent / "migrations" / "0001_archive.sql"
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE unrelated(data TEXT)")
    db.execute("INSERT INTO unrelated VALUES ('preserve')")
    db.executescript(migration.read_text())
    db.executescript(migration.read_text())
    assert db.execute("SELECT data FROM unrelated").fetchone()[0] == "preserve"
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    tables = {
        r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {
        "raw_artifacts",
        "source_revisions",
        "source_heads",
        "checkpoints",
        "import_runs",
    } <= tables
