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

ANCHOR_KEYS = {"heartRate": "Heart rate", "hrvSDNN": "HRV (SDNN)",
               "Heart rate": "Heart rate", "HRV (SDNN)": "HRV (SDNN)"}


@dataclass(frozen=True)
class CaptureLimits:
    byte_length: int = 4 * 1024 * 1024
    records: int = 20_000
    depth: int = 32
    numeric_token_length: int = 256

    def __post_init__(self) -> None:
        for limit in (self.byte_length, self.records, self.depth, self.numeric_token_length):
            if type(limit) is not int or limit <= 0:
                raise CaptureError("Capture limits must be positive integers")
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
    finding["locator"] = locator
    losses.append(finding)


def _unknown_fields(value: dict, known: set[str], base: str, losses: list[dict]) -> None:
    for key in sorted(value.keys() - known):
        _text(key)
        _loss(losses, "source_extension", "retained_in_original_only", _pointer(base, key))


def _date(value: object, field: str, locator: str, losses: list[dict]) -> tuple[str, Decimal]:
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
        _loss(losses, field, "microsecond_rounding", locator)
    return instant.isoformat(timespec="microseconds").replace("+00:00", "Z"), seconds


def _decimal_text(value: Decimal) -> str:
    if not value:
        return "0"
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


def _check_depth(text: str, limit: int) -> None:
    depth = 0
    quoted = escaped = False
    for character in text:
        if quoted:
            if escaped:
                escaped = False
            elif character == chr(92):
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in "[{":
            depth += 1
            if depth > limit:
                raise CaptureError("Capture nesting exceeds local limit")
        elif character in "]}":
            depth -= 1


def parse_capture(original: bytes, *, limits: CaptureLimits = CaptureLimits()) -> Capture:
    """Parse caller-owned, coherent bytes. Locators refer to these exact bytes."""
    if not isinstance(original, bytes) or not 0 < len(original) <= limits.byte_length:
        raise CaptureError("Expected bounded immutable capture bytes")
    def number_token(lexeme: str) -> Number:
        if len(lexeme) > limits.numeric_token_length:
            raise CaptureError("Number exceeds caller capture limit")
        return Number(lexeme)

    try:
        text = original.decode("utf-8")
        _check_depth(text, limits.depth)
        archive = _object(json.loads(
            text, object_pairs_hook=_unique_object,
            parse_int=number_token, parse_float=number_token, parse_constant=_reject_constant,
        ))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise CaptureError("Invalid UTF-8 JSON capture") from None
    if not ARCHIVE_KEYS <= archive.keys() or not isinstance(archive["readings"], list):
        raise CaptureError("Missing or malformed HealthArchive fields")

    tombstones = _object(archive["tombstones"])
    if len(archive["readings"]) + len(tombstones) > limits.records:
        raise CaptureError("Capture record count exceeds local limit")
    losses: list[dict] = []
    _unknown_fields(archive, ARCHIVE_KEYS, "", losses)
    backfill, _ = _date(archive["backfillStart"], "backfill_start", "/backfillStart", losses)
    anchors = {}
    for metric, encoded in sorted(_object(archive["anchors"]).items()):
        try:
            opaque = base64.b64decode(_text(encoded), validate=True)
        except (ValueError, binascii.Error):
            raise CaptureError("Malformed opaque anchor encoding") from None
        label = ANCHOR_KEYS.get(metric)
        if label is None or label in anchors:
            raise CaptureError("Unsupported or ambiguous opaque anchor key")
        anchors[label] = hashlib.sha256(opaque).hexdigest()

    upserts: dict = {}
    deletions: dict = {}

    def record_delete(native: str, value: object, locator: str) -> None:
        date, exact = _date(value, "deleted_at", locator, losses)
        facts = deletions.setdefault(native, {})
        _, locators, lexemes = facts.setdefault(exact, (date, [], set()))
        locators.append(locator)
        lexemes.add(_number(value).lexeme)

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
        if value < 0:
            raise CaptureError("Negative metric is outside draft 0.2 value schema")
        start, exact_start = _date(row["start"], "event_start", path + "/start", losses)
        end, exact_end = _date(row["end"], "event_end", path + "/end", losses)
        if exact_end < exact_start:
            raise CaptureError("Reversed original measurement interval")
        received, _ = _date(row["receivedAt"], "collector_received_at", path + "/receivedAt", losses)
        observation = {
            "channel": channel, "original_value": number.lexeme, "original_unit": unit,
            "value": _decimal_text(value), "unit": unit, "event_start": start,
            "event_end": end, "collector_received_at": received,
            "original_start": _number(row["start"]).lexeme,
            "original_end": _number(row["end"]).lexeme,
            "original_received_at": _number(row["receivedAt"]).lexeme,
            "source_name": _text(row["source"]), "bundle_id": _text(row["bundleID"]),
            "epistemic_type": epistemic_type, "device_id": None,
            "calibration_id": None, "source_available_at": None,
            "classification_basis": "healthkit_sdnn" if channel == "hrv_sdnn"
                                    else "capture_derivation_unavailable",
            "classification_evidence_sha256": None,
        }
        fact = {
            "channel": channel, "unit": unit, "value": observation["value"],
            "start": _decimal_text(exact_start), "end": _decimal_text(exact_end),
            "source_name": observation["source_name"], "bundle_id": observation["bundle_id"],
        }
        previous = upserts.setdefault(native, (observation, fact, []))
        if previous[1] != fact:
            raise CaptureError("Ambiguous same-UUID upserts")
        if previous[0] != observation:
            _loss(losses, "source_sighting", "alternate_sighting_retained_in_original", path)
        previous[2].append(path)
        if not value:
            _loss(losses, "value", "outside_reference_positive_domain", path + "/value")
        if row.get("deletedAt") is not None:
            record_delete(native, row["deletedAt"], path + "/deletedAt")

    for raw_id, value in sorted(tombstones.items()):
        record_delete(_uuid(raw_id), value, _pointer("/tombstones", raw_id))

    return Capture(
        hashlib.sha256(original).hexdigest(), len(original), backfill,
        min((row[0]["event_start"] for row in upserts.values()), default=None),
        max((row[0]["event_end"] for row in upserts.values()), default=None),
        anchors, upserts, deletions, losses,
    )
