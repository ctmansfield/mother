"""ATLAS draft 0.2 exchange encoding, separate from capture validation."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal

from .capture import CaptureError, CaptureLimits, _decimal_text, parse_capture
from .numeric import project_binary64

LEGACY_EXPORT_VERSION = "healtharchive-capture:0.2"
EXPORT_VERSION = "healtharchive-capture:0.2.1"
SOURCE_REVISION = "mse.source-revision/0.2"


def canonical_json(value: object) -> bytes:
    """Encode an adapter-generated exchange value in canonical UTF-8."""
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def export_sha256(export: dict) -> str:
    return _digest(["mse.export/0.2", export])


def _token(value: str) -> str:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value) is None
    ):
        raise CaptureError("Expected explicit bounded exchange token")
    return value


def normalize_capture(
    original: bytes,
    *,
    subject_id: str,
    source_instance: str,
    batch_id: str,
    capture_kind: str,
    capture_id: str,
    exporter_version: str = EXPORT_VERSION,
    limits: CaptureLimits = CaptureLimits(),
) -> dict:
    """Return a deterministic exchange object. The caller retains original bytes."""
    scope = {
        "subject_id": _token(subject_id),
        "source_system": "healthkit",
        "source_instance": _token(source_instance),
        "collection": "healtharchive",
    }
    batch_id = _token(batch_id)
    capture_id = _token(capture_id)
    exporter_version = _token(exporter_version)
    if capture_kind not in ("full_file", "partial"):
        raise CaptureError("Capture kind must be explicitly full_file or partial")
    capture = parse_capture(original, limits=limits)
    revisions: list[dict] = []

    def revision(
        native: str, operation: str, payload: dict, fact: object, locators: list
    ) -> None:
        revisions.append(
            {
                "native_id": native,
                "operation": operation,
                **payload,
                "revision_sha256": _digest(
                    [SOURCE_REVISION, scope, native, operation, fact]
                ),
                "locators": sorted(set(locators)),
            }
        )

    findings = list(capture.losses)
    for native, (observation, fact, locators) in capture.upserts.items():
        if (
            exporter_version != LEGACY_EXPORT_VERSION
            and observation["epistemic_type"] != "unknown"
            and Decimal(observation["value"]) > 0
        ):
            for field in ("original_value", "value"):
                _, reason = project_binary64(observation[field])
                if reason is not None:
                    findings.extend(
                        {
                            "field": field,
                            "reason": reason,
                            "locator": pointer + "/value",
                        }
                        for pointer in locators
                    )
        revision(native, "upsert", {"observation": observation}, fact, locators)
    for native, facts in capture.deletions.items():
        for seconds, (date, locators, lexemes) in facts.items():
            payload = {"deleted_at": date, "original_deleted_at": sorted(lexemes)}
            revision(native, "delete", payload, _decimal_text(seconds), locators)
    revisions.sort(
        key=lambda row: (row["native_id"], row["operation"], row["revision_sha256"])
    )
    losses = {canonical_json(loss): loss for loss in findings}
    return {
        "schema_version": "mse.healtharchive-export/0.2",
        "scope": scope,
        "batch_id": batch_id,
        "capture_id": capture_id,
        "exporter_version": exporter_version,
        "artifact": {
            "sha256": capture.sha256,
            "byte_length": capture.byte_length,
            "media_type": "application/json",
            "source_schema": "healtharchive-codable-json/0.1",
        },
        "coverage": {
            "capture_kind": capture_kind,
            "backfill_start": capture.backfill_start,
            "observed_start": capture.observed_start,
            "observed_end": capture.observed_end,
            "permissions": "unknown",
            "completeness": "unknown",
        },
        "anchor_sha256": capture.anchor_sha256,
        "revisions": revisions,
        "losses": [losses[key] for key in sorted(losses)],
    }
