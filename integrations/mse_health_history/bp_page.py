"""Synthetic BP API page seam for review with the mobile writer."""

import json

from integrations.healthbridge.capture import _unique_object
from mother.physiology.contracts import canonical_json

from .blood_pressure import SCHEMA, clocks, decimal_text, source_time, source_uuid
from .inventory import BP_TYPE, BP_TYPES

VERSION = "mse.historical-bp-page/0.1"
FEEDS = {role: type_id for type_id, role in BP_TYPES.items()} | {"correlation": BP_TYPE}
MAX_BYTES = 1024 * 1024
MAX_ROWS = 128


def _check(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys.split()):
        raise ValueError("invalid historical BP API fields")


def _identity(value):
    canonical = source_uuid(value)
    if canonical is None or canonical != value:
        raise ValueError("historical BP API requires canonical native UUID")
    return canonical


def _reject_number(_):
    raise ValueError("historical BP API decimals must be strings")


def read_page(stream, enrollment, digest_pattern):
    stream.seek(0)
    raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("historical BP page exceeds byte limit")
    page = json.loads(
        raw,
        object_pairs_hook=_unique_object,
        parse_float=_reject_number,
        parse_constant=_reject_number,
    )
    _check(
        page,
        "schema_version enrollment through feed prior_cursor_sha256 next_cursor_sha256 upserts deleted_ids exhausted",
    )
    if (
        page["schema_version"] != VERSION
        or page["enrollment"] != enrollment
        or not isinstance(page["feed"], str)
        or page["feed"] not in FEEDS
        or source_time(page["through"]) != page["through"]
    ):
        raise ValueError("historical BP page enrollment or feed mismatch")
    for field in ("prior_cursor_sha256", "next_cursor_sha256"):
        value = page[field]
        if field == "prior_cursor_sha256" and value is None:
            continue
        if not isinstance(value, str) or not digest_pattern.fullmatch(value):
            raise ValueError("invalid historical BP cursor digest")
    if (
        not isinstance(page["upserts"], list)
        or not isinstance(page["deleted_ids"], list)
        or len(page["upserts"]) + len(page["deleted_ids"]) > MAX_ROWS
        or type(page["exhausted"]) is not bool
        or page["exhausted"] != (not page["upserts"] and not page["deleted_ids"])
    ):
        raise ValueError("historical BP page row limit exceeded")
    for deleted in page["deleted_ids"]:
        _identity(deleted)
    return page


def _lineage(row, adapter, type_id, through):
    _check(row, "uuid start end source_bundle source_version sync_id sync_version")
    for field in ("source_bundle", "source_version", "sync_id"):
        value = row[field]
        if field != "source_bundle" and value is None:
            continue
        if (
            not isinstance(value, str)
            or not 1 <= len(value) <= 256
            or not value.isprintable()
        ):
            raise ValueError("invalid historical BP API provenance")
    version = row["sync_version"]
    if version is not None and (
        type(version) is not int or not 0 <= version <= 2**53 - 1
    ):
        raise ValueError("invalid historical BP API sync version")
    source_clocks = clocks({"startDate": row["start"], "endDate": row["end"]})
    if (
        source_clocks["event_start"] != row["start"]
        or source_clocks["event_end"] != row["end"]
        or row["end"] > through
    ):
        raise ValueError("historical BP API record outside enrollment")
    native = adapter._native({"uuid": _identity(row["uuid"])}, type_id)
    return {
        "native_ref": native,
        "source_ref": adapter._ref(
            "healthkit-bundle", row["source_bundle"], row["source_version"]
        ),
        "sync_ref": (
            adapter._ref("healthkit-sync", row["source_bundle"], row["sync_id"])
            if row["sync_id"] is not None
            else None
        ),
        "sync_version": version,
        "clocks": source_clocks,
    }


def _part(component, adapter, through):
    _check(component, "feed lineage mmhg")
    feed = component["feed"]
    if not isinstance(feed, str) or feed not in {"systolic", "diastolic"}:
        raise ValueError("invalid historical BP component feed")
    raw = component["mmhg"]
    normalized = decimal_text(raw) if raw is not None else None
    if raw != normalized:
        raise ValueError("historical BP API requires canonical decimal text")
    return dict(
        _lineage(component["lineage"], adapter, FEEDS[feed], through),
        role=feed,
        value=normalized,
        original_decimal=raw,
        unit="mmHg",
    )


def normalize(row, feed, through, adapter):
    if feed == "correlation":
        _check(row, "lineage components unexpected_component_ids")
        inputs = row["components"]
        unexpected = row["unexpected_component_ids"]
        if (
            not isinstance(inputs, list)
            or not isinstance(unexpected, list)
            or len(inputs) + len(unexpected) > 16
        ):
            raise ValueError("invalid historical BP correlation membership")
        for native in unexpected:
            _identity(native)
        parts = [_part(item, adapter, through) for item in inputs]
        roles = sorted(item["role"] for item in parts)
        ids = {item["lineage"]["uuid"] for item in inputs}
        if unexpected or len(roles) != len(set(roles)):
            pairing = "ambiguous"
        elif (
            roles == ["diastolic", "systolic"]
            and len(ids) == 2
            and all(item["value"] is not None for item in parts)
        ):
            pairing = "paired"
        else:
            pairing = "incomplete"
        root = _lineage(row["lineage"], adapter, BP_TYPE, through)
        unknown_count = len(unexpected)
    else:
        root = _part(row, adapter, through)
        if root["role"] != feed:
            raise ValueError("historical BP page contains wrong feed")
        parts, pairing, unknown_count = [root], "unpaired", 0
        root = {
            key: root[key]
            for key in (
                "native_ref",
                "source_ref",
                "sync_ref",
                "sync_version",
                "clocks",
            )
        }
    document = dict(
        root,
        schema_version=SCHEMA,
        identity=root["native_ref"],
        pairing=pairing,
        components=sorted(parts, key=canonical_json),
        unsupported_component_count=unknown_count,
    )
    revision = adapter._ref("healthkit-bp-revision", document)
    return document["identity"], revision, document
