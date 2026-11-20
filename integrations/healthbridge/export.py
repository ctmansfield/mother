"""Provisional ATLAS 0.1 exchange encoding, separate from capture validation."""
from __future__ import annotations

import hashlib
import json

from .capture import CaptureError, _decimal_text, parse_capture

EXPORT_VERSION = "healtharchive-capture/0.1"


def canonical_json(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _token(value: str) -> str:
    if (not isinstance(value, str) or not value or len(value) > 128
            or not all(c.isascii() and (c.isalnum() or c in "._-") for c in value)):
        raise CaptureError("Expected explicit bounded scope or batch token")
    return value


def normalize_capture(
    original: bytes, *, subject_id: str, source_instance: str,
    batch_id: str, capture_kind: str,
) -> dict:
    """Return a deterministic exchange object. The caller retains original bytes."""
    scope = {
        "subject_id": _token(subject_id), "source_system": "healthkit",
        "source_instance": _token(source_instance), "collection": "healtharchive",
    }
    batch_id = _token(batch_id)
    if capture_kind not in ("full_file", "partial"):
        raise CaptureError("Capture kind must be explicitly full_file or partial")
    capture = parse_capture(original)
    revisions: list[dict] = []

    def revision(native: str, operation: str, payload: dict, exact: dict, locators: list) -> None:
        # Provisional preimage binds exact source time independently of UTC rounding.
        preimage = {"scope": scope, "native_id": native, "operation": operation,
                    **payload, **exact}
        revisions.append({
            "native_id": native, "operation": operation, **payload,
            "revision_sha256": hashlib.sha256(canonical_json(preimage)).hexdigest(),
            "locators": sorted(locators),
        })

    for native, (observation, times, locators) in sorted(capture.upserts.items()):
        revision(native, "upsert", {"observation": observation},
                 {"swift_date_seconds": list(times)}, locators)
    for native, facts in sorted(capture.deletions.items()):
        for seconds, (date, locators) in sorted(facts.items()):
            revision(native, "delete", {"deleted_at": date},
                     {"swift_deleted_at_seconds": _decimal_text(seconds)}, locators)
    revisions.sort(key=lambda row: (row["native_id"], row["operation"], row["revision_sha256"]))
    return {
        "schema_version": "mse.healtharchive-export/0.1",
        "scope": scope, "batch_id": batch_id, "capture_id": capture.sha256,
        "exporter_version": EXPORT_VERSION,
        "artifact": {
            "sha256": capture.sha256, "byte_length": capture.byte_length,
            "media_type": "application/json", "source_schema": "healtharchive-codable-json/0.1",
        },
        "coverage": {
            "capture_kind": capture_kind, "backfill_start": capture.backfill_start,
            "observed_start": capture.observed_start, "observed_end": capture.observed_end,
            "permissions": "unknown", "completeness": "unknown",
        },
        "anchor_sha256": capture.anchor_sha256, "revisions": revisions,
        "losses": sorted(capture.losses, key=canonical_json),
    }
