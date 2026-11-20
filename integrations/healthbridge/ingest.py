"""Connect synthetic HealthArchive exports to the local FORGE ingest service."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib

from .capture import CaptureLimits
from .export import EXPORT_VERSION, export_sha256, normalize_capture


class IngestBindingError(RuntimeError):
    """The authoritative service result does not bind the adapter inputs."""


@dataclass(frozen=True)
class CaptureDelivery:
    export: dict
    receipt: dict


def ingest_capture(
    service,
    original: bytes,
    *,
    batch_id: str,
    capture_id: str,
    capture_kind: str,
    map_export,
    limits: CaptureLimits = CaptureLimits(),
) -> CaptureDelivery:
    """Ingest via the configured service and return the reopened receipt.

    The service supplies the expected scope. FORGE's mapper owns PF-001
    source and processing identities and receives only validated adapter
    output plus the ledger-issued normalization context.
    """
    scope = service.scope.fields()
    export = normalize_capture(
        original,
        subject_id=scope["subject_id"],
        source_instance=scope["source_instance"],
        batch_id=batch_id,
        capture_id=capture_id,
        capture_kind=capture_kind,
        limits=limits,
    )
    if export["scope"] != scope:
        raise IngestBindingError("Configured ingest scope differs from captured scope")

    artifact = export["artifact"]
    expected = {
        "archive_id": service.archive_id,
        "scope": scope,
        "batch_id": batch_id,
        "artifact_sha256": artifact["sha256"],
        "byte_length": artifact["byte_length"],
        "source_schema": artifact["source_schema"],
        "export_sha256": export_sha256(export),
    }

    def normalize(retained, context):
        if (
            retained != original
            or context.artifact_sha256 != artifact["sha256"]
            or hashlib.sha256(retained).hexdigest() != context.artifact_sha256
            or context.scope.fields() != scope
        ):
            raise IngestBindingError("Ledger normalization context differs from capture")
        return map_export(deepcopy(export), context)

    receipt = service.ingest(
        original, export, adapter_version=EXPORT_VERSION, normalize=normalize,
    )
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise IngestBindingError("Returned receipt differs from capture and export")
    verified = service.verify_receipt(receipt)
    if verified != receipt:
        raise IngestBindingError("Reopened receipt differs from returned receipt")
    return CaptureDelivery(export, verified)
