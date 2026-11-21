"""Normalize explicit source BP correlations without guessing component linkage."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hmac
import re
from uuid import UUID

from mother.physiology.contracts import canonical_json

from .inventory import BP_TYPE, BP_TYPES

SCHEMA = "mse.historical-blood-pressure/0.1"


def protected_ref(key, domain, *parts):
    return hmac.digest(key, canonical_json([domain, *parts]).encode(), "sha256").hex()


def source_uuid(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value
    ):
        return None
    return str(UUID(value))


def source_time(raw):
    if not isinstance(raw, str):
        raise ValueError("unusable HealthData clock")
    match = re.fullmatch(
        r"([0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9]{2}:[0-9]{2}:[0-9]{2})"
        r"(?:\.([0-9]{1,6}))? ?(Z|([+-])([0-9]{2}):?([0-9]{2}))",
        raw,
    )
    if match is None:
        raise ValueError("unusable HealthData clock")
    base, fraction, zone, sign, hours, minutes = match.groups()
    if zone == "Z":
        offset = "+00:00"
    else:
        if int(hours) > 23 or int(minutes) > 59:
            raise ValueError("unusable HealthData offset")
        offset = f"{sign}{hours}:{minutes}"
    # Python 3.9 only accepts colon-separated offsets and fixed fractional widths.
    canonical_input = (
        f"{base.replace(' ', 'T')}.{(fraction or '').ljust(6, '0')}{offset}"
    )
    try:
        return (
            datetime.fromisoformat(canonical_input)
            .astimezone(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
    except OverflowError:
        raise ValueError("unusable HealthData clock") from None


class SourceClockError(ValueError):
    """A BP source clock failed qualification."""


def clocks(attrs):
    creation = attrs.get("creationDate")
    try:
        start = source_time(attrs.get("startDate"))
        end = source_time(attrs.get("endDate"))
        created_at = source_time(creation) if creation is not None else None
    except ValueError:
        raise SourceClockError("invalid_source_clock") from None
    if end < start:
        raise SourceClockError("reversed_source_interval")
    return {
        "source_start": attrs["startDate"],
        "source_end": attrs["endDate"],
        "source_creation": creation,
        "event_start": start,
        "event_end": end,
        "created_at": created_at,
    }


def decimal_text(value):
    if (
        not isinstance(value, str)
        or len(value) > 64
        or not re.fullmatch(
            r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]{1,3})?",
            value,
        )
    ):
        raise ValueError("invalid historical decimal")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError("invalid historical decimal") from None
    if not number.is_finite() or abs(number.adjusted()) > 128:
        raise ValueError("invalid historical decimal")
    digits = format(number, "f")
    if "." in digits:
        digits = digits.rstrip("0").rstrip(".")
    return digits if number else "0"


class BloodPressure:
    def __init__(self, namespace, key):
        if not isinstance(key, bytes) or len(key) < 32:
            raise ValueError("historical provenance requires a private key")
        self.namespace = namespace
        self.key = key

    def _ref(self, domain, *parts):
        return protected_ref(self.key, domain, self.namespace, *parts)

    def _native(self, attrs, type_id):
        # A source-native ID is optional. Never synthesize one from a clock
        # or infer a live match from two similar measurements.
        value = source_uuid(attrs.get("uuid"))
        return self._ref("healthkit-native", type_id, value) if value else None

    def _source(self, attrs):
        name = attrs.get("sourceName")
        return (
            self._ref("healthkit-source", name, attrs.get("sourceVersion"))
            if name
            else None
        )

    def _component(self, attrs):
        type_id = attrs["type"]
        if attrs.get("unit") != "mmHg":
            raise ValueError("unsupported historical BP unit")
        return {
            "role": BP_TYPES[type_id],
            "value": decimal_text(attrs.get("value")),
            "original_decimal": attrs["value"],
            "unit": "mmHg",
            "native_ref": self._native(attrs, type_id),
            "source_ref": self._source(attrs),
            "clocks": clocks(attrs),
        }

    def normalize(self, tag, attrs, children, locator, child_sightings):
        type_id = attrs.get("type")
        if tag == "Correlation" and type_id == BP_TYPE:
            matching = [
                (ordinal, child)
                for ordinal, child_tag, child in children
                if child_tag == "Record" and child.get("type") in BP_TYPES
            ]
            unexpected = sum(
                child_tag == "Record" and child.get("type") not in BP_TYPES
                for _, child_tag, child in children
            )
            ordered = sorted(
                ((self._component(child), ordinal) for ordinal, child in matching),
                key=lambda located: canonical_json(located[0]),
            )
            components = [component for component, _ in ordered]
            child_sightings.extend(
                (ordinal, component["role"]) for component, ordinal in ordered
            )
            roles = [component["role"] for component in components]
            state = (
                "paired" if sorted(roles) == ["diastolic", "systolic"] else "incomplete"
            )
            if unexpected or len(roles) != len(set(roles)):
                state = "ambiguous"
            elif state == "paired":
                native_ids = [source_uuid(child.get("uuid")) for _, child in matching]
                if None not in native_ids and native_ids[0] == native_ids[1]:
                    state = "ambiguous"
        elif tag == "Record" and type_id in BP_TYPES:
            components = [self._component(attrs)]
            state, unexpected = "unpaired", 0
        else:
            return None
        native = self._native(attrs, type_id)
        identity = native or self._ref("healthkit-artifact-occurrence", *locator)
        document = {
            "schema_version": SCHEMA,
            "identity": identity,
            "native_ref": native,
            "source_ref": self._source(attrs),
            "pairing": state,
            "clocks": clocks(attrs),
            "components": sorted(components, key=canonical_json),
            "unsupported_component_count": unexpected,
        }
        revision = self._ref("healthkit-bp-revision", document)
        return identity, revision, document
