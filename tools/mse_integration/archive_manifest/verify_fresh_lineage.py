"""Independently reconcile an exact synthetic capture, receipt, export and closed consumer."""
from __future__ import annotations

import argparse
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from integrations.healthbridge.export import export_sha256, normalize_capture
from integrations.mse_archive_service.store import CAPTURE_LIMITS, PrivateArchive, schema
from integrations.mse_ingest import Scope
from integrations.mse_ingest.connected import NORMALIZER_VERSION, _processing, _source_row
from integrations.mse_ingest.v02 import digest
from jsonschema import Draft202012Validator
from mother.physiology.contracts import canonical_json
from verify import VerificationError, _json, _read_regular

MAX_EVIDENCE_BYTES = 2 * 1024 * 1024
ACCEPTED_PHONE_ARTIFACT = "818d9d015eb8facbbd5c82461a0bf0a5f0deced9a98042dd58fa736d23a75904"


def _require(ok, reason):
    if not ok:
        raise VerificationError(reason)


def verify_lineage(original, receipt_bytes, export_bytes, consumer, *, approved_hashes):
    hashes = tuple(sha256(item).hexdigest() for item in (original, receipt_bytes, export_bytes))
    _require(hashes == approved_hashes, "Custodian digest mismatch")
    _require(hashes[0] != ACCEPTED_PHONE_ARTIFACT, "Historical phone artifact excluded")
    receipt, envelope = _json(receipt_bytes), _json(export_bytes)
    rules = schema()
    Draft202012Validator({"$defs": rules["$defs"], "$ref": "#/$defs/receipt"}).validate(receipt)
    _require(receipt["status"] == "normalized" and receipt["artifact_sha256"] == hashes[0]
             and receipt["byte_length"] == len(original), "Normalized receipt does not bind original")
    scope = Scope(**receipt["scope"])
    _require(scope.subject_id.startswith("synthetic-"), "Expected agreed synthetic scope")
    batch = receipt["batch_id"]
    reconstructed = normalize_capture(
        original, subject_id=scope.subject_id, source_instance=scope.source_instance,
        batch_id=batch, capture_id=batch, capture_kind="partial", limits=CAPTURE_LIMITS,
    )
    expected_id = digest("mse.receipt-id/0.2", receipt["archive_id"], receipt["scope"], batch)
    _require(receipt["receipt_id"] == expected_id
             and receipt["export_sha256"] == export_sha256(reconstructed)
             and receipt["source_schema"] == reconstructed["artifact"]["source_schema"],
             "Receipt identity or authoritative export mismatch")

    members = []
    for fact in reconstructed["revisions"]:
        revision_id, _ = _source_row(scope, fact)
        member = {key: receipt[key] for key in (
            "artifact_sha256", "receipt_id", "mother_received_at", "committed_at", "commit_sequence"
        )}
        member.update(source_revision=fact, pf001_revision_id=revision_id)
        if fact["operation"] == "upsert":
            member["processing_revision_sha256"] = _processing(fact, NORMALIZER_VERSION)
        members.append(member)
    rows = [
        PrivateArchive._relation(SimpleNamespace(scope=scope), reconstructed, NORMALIZER_VERSION, member)
        for member in members
    ]
    view = envelope["view"]
    _require(
        envelope["schema_version"] == "archive_export_v1"
        and envelope["purpose"] == "authorized_synthetic_transfer"
        and canonical_json(envelope).encode() == export_bytes
        and envelope["view_sha256"] == sha256(canonical_json(view).encode()).hexdigest()
        and view["archive_id"] == receipt["archive_id"] and view["scope"] == receipt["scope"]
        and view["view"] == "archive_receipt_revisions_v1"
        and view["query"]["mode"] == "history"
        and view["query"]["from"] == view["query"]["through"] == receipt["commit_sequence"]
        and view["coverage"] == "unknown"
        and all(view["query"].get(key) is None for key in (
            "metric", "measurement_start", "measurement_end", "batch_id", "receipt_id"
        ))
        and envelope["row_count"] == len(rows) > 0
        and sorted(map(canonical_json, rows)) == sorted(map(canonical_json, view["rows"])),
        "Export view membership, cutoff or fields mismatch",
    )

    expected = []
    for row in rows:
        revision = row["source_revision"]
        observation = revision.get("observation", {})
        expected.append((
            row["receipt_id"], row["source_revision_id"], row["processing_revision_id"] or "",
            row["commit_sequence"], revision["operation"], observation.get("channel"),
            observation.get("value"), observation.get("unit"), canonical_json(row),
        ))
    # Require an ordinary, closed transfer database. Never reopen active archive state.
    _require(consumer.is_file() and not consumer.is_symlink()
             and not any(Path(str(consumer) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")),
             "Expected a closed regular consumer database")
    with closing(sqlite3.connect(consumer.absolute().as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        db.execute("PRAGMA trusted_schema=OFF")
        loaded = db.execute("""
            SELECT receipt_id,source_revision_id,processing_key,commit_sequence,operation,
                   channel,decimal_value,unit,row_json FROM receipt_revisions LIMIT 1025
        """).fetchall()
        stored_manifest, = db.execute("SELECT json FROM export_manifest WHERE id=1").fetchone()
        expected_manifest = dict(envelope, view={key: value for key, value in view.items() if key != "rows"})
        _require(sorted(loaded) == sorted(expected) and _json(stored_manifest) == expected_manifest,
                 "Consumer relational keys, values or full rows mismatch")
        _require(db.execute("PRAGMA integrity_check").fetchall() == [("ok",)],
                 "Consumer integrity failure")
    return {
        "status": "passed", "artifact_sha256": hashes[0], "receipt_sha256": hashes[1],
        "export_sha256": hashes[2], "view_sha256": envelope["view_sha256"],
        "source_member_count": len(rows), "commit_sequence": receipt["commit_sequence"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("original", "receipt", "export", "consumer"):
        parser.add_argument("--" + field, type=Path, required=True)
    for field in ("original", "receipt", "export"):
        parser.add_argument("--" + field + "-sha256", required=True)
    args = parser.parse_args()
    try:
        data = [_read_regular(path, MAX_EVIDENCE_BYTES) for path in (args.original, args.receipt, args.export)]
        result = verify_lineage(
            *data, args.consumer,
            approved_hashes=(args.original_sha256, args.receipt_sha256, args.export_sha256),
        )
    except VerificationError as exc:
        parser.exit(1, f"Fresh lineage verification failed: {exc}\n")
    except Exception:
        parser.exit(1, "Fresh lineage verification failed: invalid or unreadable evidence\n")
    print(canonical_json(result))


if __name__ == "__main__":
    main()
