"""Provisional snapshot wire mapping for the offline reference replay."""
from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import re
from uuid import UUID

from mse.contracts import ContractError, canonical, digest, identifier, read_json, timestamp, utc

from .reference import _replay_projection

SNAPSHOT_VERSION = "mse.evidence-snapshot/0.1"
MAPPING_VERSION = "mse-snapshot-provisional/0.1"
TOP_FIELDS = set("""
    schema_version scope purpose measurement_start measurement_end
    knowledge_cutoff_sequence normalizer_version coverage observations tombstones
    losses snapshot_sha256
""".split())
SCOPE_FIELDS = {"subject_id", "source_system", "source_instance", "collection"}
MEMBER_FIELDS = {"native_id", "pf001_revision_id", "artifact_sha256", "receipt"}
RECEIPT_FIELDS = {
    "scope", "receipt_id", "status", "artifact_sha256", "mother_received_at",
    "committed_at", "commit_sequence",
}
OBSERVATION_FIELDS = set("""
    channel original_value original_unit value unit event_start event_end
    collector_received_at source_name bundle_id epistemic_type device_id
    calibration_id source_available_at
""".split())


def _fields(value, expected):
    if not isinstance(value, dict) or set(value) != expected:
        raise ContractError("Unexpected snapshot fields")


def _string(value):
    if not isinstance(value, str) or not value:
        raise ContractError("Expected a nonempty snapshot string")


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ContractError("Expected a lowercase SHA-256 digest")


def _clock(value):
    try:
        parsed = timestamp(value)
        if value == utc(parsed):
            return parsed
    except (OverflowError, ValueError):
        pass
    raise ContractError("Expected canonical UTC timestamp")


def _sequence(value):
    if type(value) is not int or value < 0:
        raise ContractError("Expected a nonnegative commitment sequence")
    return value


def _check_json(value):
    if isinstance(value, float):
        raise ContractError("Shared snapshot JSON does not accept floating-point values")
    if isinstance(value, dict):
        for item in value.values():
            _check_json(item)
    if isinstance(value, list):
        for item in value:
            _check_json(item)


def _read_snapshot(snapshot_bytes):
    try:
        snapshot = read_json(snapshot_bytes.decode("utf-8"))
        _check_json(snapshot)
        _fields(snapshot, TOP_FIELDS)
        _sha(snapshot["snapshot_sha256"])
        preimage = {k: v for k, v in snapshot.items() if k != "snapshot_sha256"}
        if digest(preimage) != snapshot["snapshot_sha256"]:
            raise ContractError("Snapshot digest mismatch")
    except (UnicodeError, RecursionError) as exc:
        raise ContractError("Invalid snapshot encoding") from exc
    if (snapshot["schema_version"] != SNAPSHOT_VERSION
            or snapshot["purpose"] != "offline_synthetic_replay"):
        raise ContractError("Unsupported snapshot version or purpose")
    scope = snapshot["scope"]
    _fields(scope, SCOPE_FIELDS)
    for value in scope.values():
        _string(value)
    if (scope["source_system"], scope["collection"]) != ("healthkit", "healtharchive"):
        raise ContractError("Unsupported snapshot source scope")
    _string(snapshot["normalizer_version"])
    if not isinstance(snapshot["coverage"], dict) or any(
        not isinstance(snapshot[k], list) for k in ("observations", "tombstones", "losses")
    ) or any(not isinstance(loss, dict) for loss in snapshot["losses"]):
        raise ContractError("Invalid coverage, losses or member lists")
    return snapshot


def _member(member, payload, snapshot):
    _fields(member, MEMBER_FIELDS | {payload})
    native = member["native_id"]
    _string(native)
    try:
        canonical_uuid = str(UUID(native))
    except ValueError as exc:
        raise ContractError("Invalid native UUID") from exc
    if native != canonical_uuid:
        raise ContractError("Noncanonical native UUID")
    _string(member["pf001_revision_id"])
    _sha(member["artifact_sha256"])

    receipt = member["receipt"]
    _fields(receipt, RECEIPT_FIELDS)
    _string(receipt["receipt_id"])
    if (receipt["scope"] != snapshot["scope"] or receipt["status"] != "normalized"
            or receipt["artifact_sha256"] != member["artifact_sha256"]):
        raise ContractError("Snapshot member scope or receipt binding mismatch")
    sequence = _sequence(receipt["commit_sequence"])
    if sequence == 0 or sequence > snapshot["knowledge_cutoff_sequence"]:
        raise ContractError("Snapshot member outside commitment cutoff")
    if _clock(receipt["committed_at"]) < _clock(receipt["mother_received_at"]):
        raise ContractError("Commitment precedes MOTHER receipt")
    scope = snapshot["scope"]
    return identifier("observation", scope["subject_id"], scope["source_instance"], native)


def _observation(member, key, scope, start, end):
    observation = member["observation"]
    _fields(observation, OBSERVATION_FIELDS)
    first, last = (_clock(observation[k]) for k in ("event_start", "event_end"))
    if not start <= first < end or not first <= last <= end:
        raise ContractError("Observation outside snapshot interval")
    _clock(observation["collector_received_at"])
    if observation["source_available_at"] is not None:
        _clock(observation["source_available_at"])
    for name in ("source_name", "bundle_id", "device_id", "calibration_id"):
        if observation[name] is not None:
            _string(observation[name])
    _string(observation["original_value"])

    channel, unit = observation["channel"], observation["unit"]
    if (channel, unit) not in (("heart_rate", "bpm"), ("hrv_sdnn", "ms")):
        raise ContractError("Unsupported snapshot channel/unit pair")
    if observation["original_unit"] != unit:
        raise ContractError("Unsupported measurement unit conversion")
    value = observation["value"]
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value) or Decimal(value) <= 0:
        raise ContractError("Invalid positive decimal measurement")
    epistemic = observation["epistemic_type"]
    if epistemic == "unknown" and channel == "heart_rate":
        return None
    if (channel, epistemic) not in (("heart_rate", "measured"), ("hrv_sdnn", "vendor_derived")):
        raise ContractError("Unsupported observation epistemic class")

    return {
        "schema_version": "mse.observation/0.1",
        "observation_id": key,
        "native_id": member["native_id"],
        "subject_id": scope["subject_id"],
        "source_instance": scope["source_instance"],
        "channel": channel,
        "value": value,
        "unit": unit,
        "event_start": observation["event_start"],
        "event_end": observation["event_end"],
        "received_at": observation["collector_received_at"],
        "epistemic_type": epistemic,
        "context": "unknown",
        "provenance": {name: observation[name] for name in ("bundle_id", "device_id", "calibration_id")},
        "quality_flags": ["acquisition_conditions_unknown", "measurement_error_unqualified", "source_clock_unqualified"],
    }


def _project(snapshot):
    start, end = (_clock(snapshot[k]) for k in ("measurement_start", "measurement_end"))
    if start >= end:
        raise ContractError("Invalid snapshot interval")
    _sequence(snapshot["knowledge_cutoff_sequence"])

    receipts = {}
    revisions = set()
    for member in snapshot["observations"] + snapshot["tombstones"]:
        if not isinstance(member, dict):
            raise ContractError("Invalid snapshot member")
        revision = member.get("pf001_revision_id")
        _string(revision)
        if revision in revisions:
            raise ContractError("Repeated PF-001 revision identity")
        revisions.add(revision)
        receipt = member.get("receipt")
        _fields(receipt, RECEIPT_FIELDS)
        receipt_id = receipt["receipt_id"]
        _string(receipt_id)
        if receipts.setdefault(receipt_id, receipt) != receipt:
            raise ContractError("Conflicting snapshot receipt identity")

    tombstones = {}
    for member in snapshot["tombstones"]:
        key = _member(member, "deleted_at", snapshot)
        deleted_at = member["deleted_at"]
        _clock(deleted_at)
        tombstones[key, deleted_at] = {"observation_id": key, "deleted_at": deleted_at}

    active, seen, projection_losses = [], set(), []
    deleted_ids = {key for key, _ in tombstones}
    for member in snapshot["observations"]:
        key = _member(member, "observation", snapshot)
        if key in seen or key in deleted_ids:
            raise ContractError("Snapshot active revision conflicts with another member")
        seen.add(key)
        observation = _observation(member, key, snapshot["scope"], start, end)
        if observation is None:
            projection_losses.append({
                "pf001_revision_id": member["pf001_revision_id"],
                "reason": "heart_rate_derivation_unknown",
            })
        else:
            active.append(observation)
    envelope = {
        "schema_version": "mse.replay/0.1",
        "synthetic": True,
        "observations": sorted(active, key=lambda row: row["observation_id"]),
        "tombstones": [tombstones[k] for k in sorted(tombstones)],
    }
    return canonical(envelope).encode("utf-8"), sorted(
        projection_losses, key=lambda loss: loss["pf001_revision_id"]
    )


def replay_snapshot(snapshot_bytes: bytes) -> dict:
    """Validate a synthetic snapshot and replay only its own derived projection."""
    snapshot = _read_snapshot(snapshot_bytes)
    projection, losses = _project(snapshot)
    result = _replay_projection(snapshot_bytes, projection)
    lineage = result["lineage"]
    lineage.update(
        snapshot_manifest_sha256=snapshot["snapshot_sha256"],
        snapshot_scope=snapshot["scope"],
        knowledge_cutoff_sequence=snapshot["knowledge_cutoff_sequence"],
        normalizer_version=snapshot["normalizer_version"],
        mapping_version=MAPPING_VERSION,
        mapping_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        measurement_interval=[snapshot["measurement_start"], snapshot["measurement_end"]],
        observation_revisions=sorted(
            ({
                "native_id": member["native_id"],
                "pf001_revision_id": member["pf001_revision_id"],
                "collector_received_at": member["observation"]["collector_received_at"],
                "source_available_at": member["observation"]["source_available_at"],
                "receipt": member["receipt"],
            } for member in snapshot["observations"]),
            key=lambda member: member["native_id"],
        ),
        deletion_facts=sorted(
            snapshot["tombstones"],
            key=canonical,
        ),
    )
    result.update(
        result_id="derived:" + digest(lineage),
        coverage=snapshot["coverage"],
        input_losses=snapshot["losses"],
        projection_losses=losses,
    )
    return result
