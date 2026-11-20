"""Isolate the provisional ATLAS 0.1 receipt encoding from local storage."""

from mother.physiology.time import parse_timestamp


def _timestamp(value):
    return (
        parse_timestamp(value).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def encode_receipt(scope, row):
    return {
        "schema_version": "mse.ingest-receipt/0.1",
        "scope": scope.fields(),
        "batch_id": row["batch_id"],
        "artifact_sha256": row["artifact_sha256"],
        "byte_length": len(row["artifact"]),
        "source_schema": row["source_schema"],
        "export_sha256": row["export_sha256"],
        "receipt_id": row["receipt_id"],
        "status": "normalized",
        "mother_received_at": _timestamp(row["received_at"]),
        "committed_at": _timestamp(row["committed_at"]),
        "commit_sequence": row["commit_sequence"],
        "pf001_run_id": row["run_id"],
        "reason_code": None,
    }
