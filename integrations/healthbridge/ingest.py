"""Connect synthetic HealthArchive exports to the local FORGE ingest service."""
from __future__ import annotations

from dataclasses import dataclass

from .capture import CaptureLimits
from .export import export_sha256, normalize_capture


class IngestBindingError(RuntimeError):
    """The authoritative service result does not bind the adapter inputs."""


@dataclass(frozen=True, repr=False)
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
    limits: CaptureLimits = CaptureLimits(),
) -> CaptureDelivery:
    """Ingest via the configured service and return the reopened receipt.

    The configured ConnectedIngest service supplies the expected scope and
    maps the export to its own PF-001 source and processing revisions.
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

    receipt = service.ingest_export(original, export)
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise IngestBindingError("Returned receipt differs from capture and export")
    verified = service.verify_receipt(receipt)
    if verified != receipt:
        raise IngestBindingError("Reopened receipt differs from returned receipt")
    return CaptureDelivery(export, verified)
