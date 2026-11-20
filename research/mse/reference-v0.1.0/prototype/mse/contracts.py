"""Small explicit contract for instrument outputs, distinct from inferred states."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math

UTC = timezone.utc
SWIFT_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)
CHANNELS = {
    "heart_rate": ("bpm", "measured"),
    "hrv_sdnn": ("ms", "vendor_derived"),
    "glucose": ("mmol/L", "measured"),
}


class ContractError(ValueError):
    """Deliberately terse: exception messages never embed source records."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def identifier(kind, *parts):
    return kind + ":" + digest(list(parts))


def read_json(data):
    def reject_constant(_):
        raise ContractError("Nonfinite JSON number")

    def unique_keys(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ContractError("Duplicate JSON key")
            out[key] = value
        return out
    try:
        return json.loads(data, parse_constant=reject_constant,
                          object_pairs_hook=unique_keys)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError("Invalid JSON input") from exc


def timestamp(value):
    if not isinstance(value, str):
        raise ContractError("Timestamp must be timezone-aware ISO 8601")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("Invalid timestamp") from exc
    if result.tzinfo is None:
        raise ContractError("Timestamp lacks timezone")
    return result.astimezone(UTC)


def utc(value):
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def swift_date(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ContractError("Swift Date must be finite numeric seconds since 2001-01-01 UTC")
    try:
        return utc(SWIFT_EPOCH + timedelta(seconds=value))
    except (OverflowError, ValueError) as exc:
        raise ContractError("Swift Date outside supported range") from exc


def decimal_string(value):
    if isinstance(value, bool):
        raise ContractError("Boolean is not a physiological scalar")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ContractError("Invalid scalar") from exc
    if not number.is_finite() or not math.isfinite(float(number)):
        raise ContractError("Nonfinite scalar")
    return format(number, "f")


def validate_observation(record):
    required = {"schema_version", "observation_id", "native_id", "subject_id", "source_instance",
                "channel", "value", "unit", "event_start", "event_end", "received_at",
                "epistemic_type", "context", "provenance", "quality_flags"}
    if not isinstance(record, dict) or set(record) != required:
        raise ContractError("Observation fields differ from mse.observation/0.1")
    if record["schema_version"] != "mse.observation/0.1":
        raise ContractError("Unsupported observation schema")
    for key in ("observation_id", "native_id", "subject_id", "source_instance", "context"):
        if not isinstance(record[key], str) or not record[key]:
            raise ContractError("Missing observation identity or context")
    if record["channel"] not in CHANNELS:
        raise ContractError("Unsupported channel")
    expected_unit, expected_epistemic = CHANNELS[record["channel"]]
    if record["unit"] != expected_unit:
        raise ContractError("Channel/unit mismatch")
    if record["epistemic_type"] not in {"measured", "vendor_derived"}:
        raise ContractError("Inference/imputation cannot enter instrument-observation stream")
    if record["channel"] == "hrv_sdnn" and record["epistemic_type"] != expected_epistemic:
        raise ContractError("SDNN must retain vendor-derived semantics")
    value = decimal_string(record["value"])
    if Decimal(value) <= 0:
        raise ContractError("Supported channels require a positive scalar")
    start, end, receipt = (timestamp(record[k]) for k in ("event_start", "event_end", "received_at"))
    if end < start:
        raise ContractError("Observation end precedes start")
    if not isinstance(record["provenance"], dict) or not isinstance(record["quality_flags"], list):
        raise ContractError("Invalid provenance or quality flags")
    for key in ("bundle_id", "device_id", "method", "calibration_id"):
        item = record["provenance"].get(key)
        if item is not None and not isinstance(item, str):
            raise ContractError("Measurement-stratum provenance must be string or null")
    window = record["provenance"].get("acquisition_window_seconds")
    if window is not None and (isinstance(window, bool) or not isinstance(window, (int, float))
                               or not math.isfinite(window) or window < 0):
        raise ContractError("Declared acquisition window must be nonnegative finite seconds or null")
    if any(not isinstance(x, str) for x in record["quality_flags"]):
        raise ContractError("Invalid quality flag")
    expected_id = identifier("observation", record["subject_id"], record["source_instance"], record["native_id"])
    if record["observation_id"] != expected_id:
        raise ContractError("Observation ID does not match subject/source/native identity")
    result = dict(record, value=value, event_start=utc(start), event_end=utc(end), received_at=utc(receipt))
    canonical(result)
    return result


def measurement_identity(record):
    """Receipt time is transport provenance, not immutable sample identity."""
    return {k: v for k, v in record.items() if k != "received_at"}
