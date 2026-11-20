"""Read-only adapters. HealthKit fields are grounded in b2baa2e6 HealthArchive.swift."""
from __future__ import annotations

import base64
import hashlib
from uuid import UUID

from .contracts import (ContractError, CHANNELS, identifier, read_json, swift_date,
                        timestamp, utc, validate_observation)

ADAPTER_VERSION = "healthkit-v03-json/0.1.0"


def healthkit_archive(data: bytes, *, subject_id: str, source_instance: str):
    archive = read_json(data)
    if not isinstance(archive, dict) or not {"readings", "anchors", "tombstones", "backfillStart"} <= archive.keys():
        raise ContractError("Expected v0.3 HealthArchive fields")
    if not isinstance(archive["readings"], list) or not isinstance(archive["anchors"], dict) or not isinstance(archive["tombstones"], dict):
        raise ContractError("Malformed HealthArchive collections")
    backfill = swift_date(archive["backfillStart"])
    anchor_hashes = {}
    for key, encoded in archive["anchors"].items():
        if not isinstance(encoded, str):
            raise ContractError("Anchor must be base64-encoded opaque data")
        try:
            anchor_hashes[key] = hashlib.sha256(base64.b64decode(encoded, validate=True)).hexdigest()
        except ValueError as exc:
            raise ContractError("Invalid anchor encoding") from exc
    observations, tombstones = [], []
    kinds = {"Heart rate": "heart_rate", "HRV (SDNN)": "hrv_sdnn"}
    for reading in archive["readings"]:
        required = {"id", "kind", "value", "unit", "start", "end", "source", "bundleID", "receivedAt"}
        if not isinstance(reading, dict) or not required <= reading.keys():
            raise ContractError("Malformed SavedReading")
        try:
            native = str(UUID(reading["id"]))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ContractError("Invalid HealthKit UUID") from exc
        if reading["kind"] not in kinds:
            raise ContractError("Unsupported SavedReading kind")
        channel = kinds[reading["kind"]]
        record = {
            "schema_version": "mse.observation/0.1",
            "observation_id": identifier("observation", subject_id, source_instance, native),
            "native_id": native, "subject_id": subject_id, "source_instance": source_instance,
            "channel": channel, "value": reading["value"], "unit": reading["unit"],
            "event_start": swift_date(reading["start"]), "event_end": swift_date(reading["end"]),
            "received_at": swift_date(reading["receivedAt"]),
            "epistemic_type": CHANNELS[channel][1], "context": "unknown",
            "provenance": {"adapter_version": ADAPTER_VERSION, "source_name": reading["source"],
                           "bundle_id": reading["bundleID"], "device_id": None,
                           "method": "HealthKit SDNN vendor output" if channel == "hrv_sdnn" else "HealthKit heart-rate quantity; acquisition method unavailable"},
            "quality_flags": ["acquisition_conditions_unknown", "device_identity_unavailable",
                              "measurement_error_unqualified", "source_clock_unqualified"],
        }
        observations.append(validate_observation(record))
        if reading.get("deletedAt") is not None:
            tombstones.append({"observation_id": record["observation_id"], "deleted_at": swift_date(reading["deletedAt"])})
    for raw_id, raw_date in archive["tombstones"].items():
        try:
            native = str(UUID(raw_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ContractError("Invalid tombstone UUID") from exc
        tombstones.append({"observation_id": identifier("observation", subject_id, source_instance, native),
                           "deleted_at": swift_date(raw_date)})
    metadata = {"adapter_version": ADAPTER_VERSION, "date_epoch": "2001-01-01T00:00:00Z",
                "backfill_start": backfill, "anchor_sha256": anchor_hashes,
                "sample_source_identity": "HealthKit UUID scoped by explicit archive source and subject"}
    return observations, tombstones, metadata


def native_replay(data: bytes):
    payload = read_json(data)
    if not isinstance(payload, dict) or payload.get("schema_version") != "mse.replay/0.1":
        raise ContractError("Expected explicit mse.replay/0.1 fixture/export envelope")
    if not isinstance(payload.get("observations"), list) or not isinstance(payload.get("tombstones", []), list):
        raise ContractError("Replay observations and tombstones must be arrays")
    observations = [validate_observation(x) for x in payload["observations"]]
    tombstones = []
    for item in payload.get("tombstones", []):
        if not isinstance(item, dict) or set(item) != {"observation_id", "deleted_at"} or not isinstance(item["observation_id"], str):
            raise ContractError("Invalid replay tombstone")
        tombstones.append(dict(item, deleted_at=utc(timestamp(item["deleted_at"]))))
    return observations, tombstones, {"adapter_version": "mse-native-replay/0.1.0",
                                     "synthetic": payload.get("synthetic") is True}
