"""Validate an immutable synthetic HealthArchive capture without writing files."""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from uuid import UUID

MAX_CAPTURE_BYTES = 4 * 1024 * 1024
SWIFT_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)
METRICS = {"Heart rate": ("heart_rate", "bpm", "unknown"),
           "HRV (SDNN)": ("hrv_sdnn", "ms", "vendor_derived")}
ARCHIVE_KEYS = {"readings", "anchors", "tombstones", "backfillStart"}
READING_KEYS = {"id", "kind", "value", "unit", "start", "end", "source",
                "bundleID", "receivedAt"}


class CaptureError(ValueError):
    """A capture is invalid. Messages contain field names, never input values."""


@dataclass(frozen=True)
class Number:
    lexeme: str

    def decimal(self) -> Decimal:
        if len(self.lexeme) > 256:
            raise CaptureError("Number exceeds local normalization limit")
        try:
            value = Decimal(self.lexeme)
        except InvalidOperation as exc:
            raise CaptureError("Number exponent exceeds local normalization limit") from exc
        if not value.is_finite() or abs(value.as_tuple().exponent) > 256:
            raise CaptureError("Number exponent exceeds local normalization limit")
        return value


def _unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise CaptureError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise CaptureError("JSON requires finite numbers")


def _object(value: object) -> dict:
    if not isinstance(value, dict):
        raise CaptureError("Expected a JSON object")
    return value


def _number(value: object) -> Number:
    if not isinstance(value, Number):
        raise CaptureError("Expected a numeric JSON token")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise CaptureError("Expected a nonempty source string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise CaptureError("Invalid Unicode string") from exc
    return value


def _uuid(value: object) -> str:
    raw = _text(value)
    try:
        canonical = str(UUID(raw))
    except ValueError as exc:
        raise CaptureError("Invalid native UUID") from exc
    if raw.lower() != canonical:
        raise CaptureError("Invalid native UUID representation")
    return canonical


def _pointer(base: str, field: str) -> str:
    return base + "/" + field.replace("~", "~0").replace("/", "~1")


def _loss(losses: list[dict], field: str, reason: str, locator: str | None = None) -> None:
    finding = {"field": field, "reason": reason}
    if locator is not None:
        finding["locator"] = locator
    losses.append(finding)


def _unknown_fields(value: dict, known: set[str], base: str, losses: list[dict]) -> None:
    for key in sorted(value.keys() - known):
        _text(key)
        _loss(losses, "source_extension", "retained_in_original_only", _pointer(base, key))


def _date(value: object, locator: str, losses: list[dict]) -> tuple[str, Decimal]:
    seconds = _number(value).decimal()
    with localcontext() as context:
        context.prec = 270
        micros = seconds.scaleb(6)
        rounded = micros.to_integral_value(rounding=ROUND_HALF_EVEN)
    try:
        if abs(rounded) > 10**18:
            raise OverflowError
        instant = SWIFT_EPOCH + timedelta(microseconds=int(rounded))
    except OverflowError as exc:
        raise CaptureError("Date outside supported UTC range") from exc
    if micros != rounded:
        _loss(losses, "timestamp", "rounded_to_microseconds_ties_even", locator)
    return instant.isoformat(timespec="microseconds").replace("+00:00", "Z"), seconds


def _decimal_text(value: Decimal) -> str:
    digits = format(value, "f")
    return digits.rstrip("0").rstrip(".") if "." in digits else digits


@dataclass(frozen=True)
class Capture:
    sha256: str
    byte_length: int
    backfill_start: str
    observed_start: str | None
    observed_end: str | None
    anchor_sha256: dict
    upserts: dict
    deletions: dict
    losses: list[dict]


def parse_capture(original: bytes) -> Capture:
    """Parse caller-owned, coherent bytes. Locators refer to these exact bytes."""
    if not isinstance(original, bytes) or not 0 < len(original) <= MAX_CAPTURE_BYTES:
        raise CaptureError("Expected bounded immutable capture bytes")
    try:
        archive = _object(json.loads(
            original.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_int=Number, parse_float=Number, parse_constant=_reject_constant,
        ))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise CaptureError("Invalid UTF-8 JSON capture") from None
    if not ARCHIVE_KEYS <= archive.keys() or not isinstance(archive["readings"], list):
        raise CaptureError("Missing or malformed HealthArchive fields")

    losses: list[dict] = []
    _unknown_fields(archive, ARCHIVE_KEYS, "", losses)
    backfill, _ = _date(archive["backfillStart"], "/backfillStart", losses)
    anchors = {}
    for metric, encoded in sorted(_object(archive["anchors"]).items()):
        try:
            opaque = base64.b64decode(_text(encoded), validate=True)
        except (ValueError, binascii.Error):
            raise CaptureError("Malformed opaque anchor encoding") from None
        anchors[_text(metric)] = hashlib.sha256(opaque).hexdigest()

    upserts: dict = {}
    deletions: dict = {}

    def record_delete(native: str, value: object, locator: str) -> None:
        date, exact = _date(value, locator, losses)
        facts = deletions.setdefault(native, {})
        facts.setdefault(exact, (date, []))[1].append(locator)

    for index, item in enumerate(archive["readings"]):
        row = _object(item)
        if not READING_KEYS <= row.keys():
            raise CaptureError("Missing SavedReading fields")
        path = f"/readings/{index}"
        _unknown_fields(row, READING_KEYS | {"deletedAt"}, path, losses)
        native = _uuid(row["id"])
        metric = METRICS.get(_text(row["kind"]))
        if metric is None or row["unit"] != metric[1]:
            raise CaptureError("Unsupported metric or unit")
        channel, unit, epistemic_type = metric
        number = _number(row["value"])
        value = number.decimal()
        start, exact_start = _date(row["start"], path + "/start", losses)
        end, exact_end = _date(row["end"], path + "/end", losses)
        if exact_end < exact_start:
            raise CaptureError("Reversed original measurement interval")
        received, exact_received = _date(row["receivedAt"], path + "/receivedAt", losses)
        observation = {
            "channel": channel, "original_value": number.lexeme, "original_unit": unit,
            "value": _decimal_text(value), "unit": unit, "event_start": start,
            "event_end": end, "collector_received_at": received,
            "source_name": _text(row["source"]), "bundle_id": _text(row["bundleID"]),
            "epistemic_type": epistemic_type, "device_id": None,
            "calibration_id": None, "source_available_at": None,
        }
        exact_times = tuple(map(_decimal_text, (exact_start, exact_end, exact_received)))
        previous = upserts.setdefault(native, (observation, exact_times, []))
        if previous[:2] != (observation, exact_times):
            raise CaptureError("Ambiguous same-UUID upserts")
        previous[2].append(path)
        for field in ("device_id", "calibration_id", "source_available_at", "source_revision"):
            _loss(losses, field, "not_recorded_by_source", path)
        if epistemic_type == "unknown":
            _loss(losses, "epistemic_type", "acquisition_method_unavailable", path)
        if row.get("deletedAt") is not None:
            record_delete(native, row["deletedAt"], path + "/deletedAt")

    for raw_id, value in sorted(_object(archive["tombstones"]).items()):
        record_delete(_uuid(raw_id), value, _pointer("/tombstones", raw_id))

    return Capture(
        hashlib.sha256(original).hexdigest(), len(original), backfill,
        min((row[0]["event_start"] for row in upserts.values()), default=None),
        max((row[0]["event_end"] for row in upserts.values()), default=None),
        anchors, upserts, deletions, losses,
    )
