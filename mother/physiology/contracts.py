"""Single-owner constructors and validation for the shared JSON contract."""

from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path

from . import CONTRACT_VERSION, PROCESSING_VERSION
from .time import parse_timestamp


def canonical_json(value) -> str:
    """Canonical payload serialization, deliberately not an original-byte hash."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def content_hash(value) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def stable_id(kind: str, *parts) -> str:
    return f"{kind}:{content_hash(list(parts))}"


@lru_cache(maxsize=1)
def _validator():
    from jsonschema import Draft202012Validator, FormatChecker

    path = Path(__file__).parent / "schemas" / "v1.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_record(record: dict) -> dict:
    """Validate structure and cross-field meaning; return the unchanged record."""
    canonical_json(record)  # Reject NaN/Infinity and non-JSON values first.
    errors = sorted(_validator().iter_errors(record), key=lambda e: str(e.path))
    if errors:
        details = errors[0].context or [errors[0]]
        # Keep error output small and avoid copying whole source records.
        raise ValueError(
            "Invalid physiology record: "
            + "; ".join(
                f"/{'/'.join(str(p) for p in e.absolute_path)} ({e.validator})"
                for e in details[:3]
            )
        )
    kind = record["record_type"]
    pairs = {
        "observation": ("measurement_start", "measurement_end"),
        "event": ("occurrence_start", "occurrence_end"),
        "session": ("start", "end"),
        "stream": ("start", "end"),
        "import_run": ("started_at", "completed_at"),
    }
    if kind in pairs:
        start, end = (record[k] for k in pairs[kind])
        if end is not None and start is None:
            raise ValueError("An interval end requires a known start")
        if (
            start is not None
            and end is not None
            and parse_timestamp(end) < parse_timestamp(start)
        ):
            raise ValueError("Interval end precedes start")
    if "first_seen_at" in record and parse_timestamp(
        record["ingested_at"]
    ) < parse_timestamp(record["first_seen_at"]):
        raise ValueError("Ingestion cannot precede this system's first observation")
    if kind == "observation":
        if record["source_revision_id"] not in record["lineage"]:
            raise ValueError("Observation lineage must include its source revision")
        if (
            record["epistemic_type"]
            in {"derived", "imputed", "inferred", "clinical_interpretation"}
            and not record["method"]
        ):
            raise ValueError("A derivative or interpretation must name its method")
    if kind == "stream":
        if record["timing"] == "regular" and record["sample_rate_hz"] is None:
            raise ValueError("Regular streams require an explicit sample rate")
        for gap in record["gaps"]:
            if parse_timestamp(gap["end"]) < parse_timestamp(gap["start"]):
                raise ValueError("Gap end precedes start")
    return record


def make_observation(**values) -> dict:
    record = {
        "schema_version": CONTRACT_VERSION,
        "record_type": "observation",
        "processing_version": PROCESSING_VERSION,
        "native_type": None,
        "measurement_end": None,
        "source_available_at": None,
        "original_unit": None,
        "unit": None,
        "method": None,
        "device_id": None,
        "recording_app": None,
        "body_site": None,
        "specimen": None,
        "session_id": None,
        "measurement_group_id": None,
        "value_status": "valid",
        "epistemic_type": "measured",
        "quality_flags": [],
        "metadata": {},
        "clock": {},
    }
    record.update(values)
    record.setdefault("lineage", [record.get("source_revision_id")])
    return validate_record(record)


def make_event(**values) -> dict:
    record = {
        "schema_version": CONTRACT_VERSION,
        "record_type": "event",
        "processing_version": PROCESSING_VERSION,
        "occurrence_start": None,
        "occurrence_end": None,
        "known_at": None,
        "source_revision_id": None,
        "session_id": None,
        "related_ids": [],
        "payload": {},
        "epistemic_type": "reported",
        "quality_flags": [],
    }
    record.update(values)
    return validate_record(record)
