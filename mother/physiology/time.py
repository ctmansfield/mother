"""Strict time normalization; unknown timezones never become implicit UTC.

Numeric auto detection is a documented contemporary-data convention: absolute
values below 1e11 are seconds, values from 1e11 through 1e14 are milliseconds.
Use numeric_unit for earlier millisecond epochs or other ambiguous numeric data.
Raw input values and offsets must be retained by the importing adapter.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import math
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _localize(value: datetime, name: str) -> datetime:
    try:
        zone = ZoneInfo(name)
    except (ZoneInfoNotFoundError, TypeError) as exc:
        raise ValueError(f"Unknown timezone: {name!r}") from exc
    possible = []
    for fold in (0, 1):
        candidate = value.replace(tzinfo=zone, fold=fold)
        back = candidate.astimezone(timezone.utc).astimezone(zone)
        if back.replace(tzinfo=None) == value and candidate.utcoffset() not in [
            x.utcoffset() for x in possible
        ]:
            possible.append(candidate)
    if len(possible) != 1:
        raise ValueError(
            "Ambiguous or nonexistent local time; supply source UTC offset"
        )
    return possible[0]


def parse_timestamp(
    value, numeric_unit: str | None = None, naive_timezone: str | None = None
) -> datetime:
    """Return an aware UTC datetime, or reject an unknown/invalid timestamp.

    Accept aware ISO8601, aware datetime, numeric epoch seconds/milliseconds,
    and naive datetimes only with an explicit unambiguous IANA timezone.
    Auto numeric parsing applies independently to each input record.
    """
    if numeric_unit not in (None, "s", "ms"):
        raise ValueError("numeric_unit must be 's', 'ms', or None")
    if value is None or isinstance(value, bool):
        raise ValueError("Missing or invalid timestamp")
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value).strip()
        if not raw or raw.lower() in {"nat", "nan", "none", "null", "inf", "-inf"}:
            raise ValueError("Missing or invalid timestamp")
        if _NUMBER.fullmatch(raw):
            try:
                number = Decimal(raw)
                unit = numeric_unit or ("ms" if abs(number) >= Decimal("1e11") else "s")
                if not number.is_finite() or (
                    numeric_unit is None and abs(number) >= Decimal("1e14")
                ):
                    raise ValueError(
                        "Unsupported numeric timestamp magnitude; specify units"
                    )
                seconds = number / 1000 if unit == "ms" else number
                parsed = _EPOCH + timedelta(microseconds=int(seconds * 1_000_000))
            except (InvalidOperation, OverflowError) as exc:
                raise ValueError("Invalid numeric timestamp") from exc
        else:
            if not re.search(r"[Tt ]\d{2}:\d{2}", raw):
                raise ValueError("Timestamp must include a time of day")
            try:
                parsed = datetime.fromisoformat(
                    raw.replace("Z", "+00:00").replace("z", "+00:00")
                )
            except (ValueError, TypeError) as exc:
                raise ValueError("Invalid ISO8601 timestamp") from exc
    try:
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            if not naive_timezone:
                raise ValueError(
                    "Timestamp has no timezone; explicit source timezone required"
                )
            parsed = _localize(parsed, naive_timezone)
        parsed = parsed.astimezone(timezone.utc)
        if not math.isfinite(parsed.timestamp()):
            raise ValueError("Invalid timestamp")
    except (OverflowError, OSError, TypeError) as exc:
        raise ValueError("Invalid timestamp") from exc
    return parsed


def epoch_ms(
    value, numeric_unit: str | None = None, naive_timezone: str | None = None
) -> int:
    delta = parse_timestamp(value, numeric_unit, naive_timezone) - _EPOCH
    return delta.days * 86_400_000 + delta.seconds * 1000 + delta.microseconds // 1000


def utc_iso(
    value, numeric_unit: str | None = None, naive_timezone: str | None = None
) -> str:
    return (
        parse_timestamp(value, numeric_unit, naive_timezone)
        .isoformat()
        .replace("+00:00", "Z")
    )
