"""Read-only Coach delivery-state reconciliation against a selected Mother archive.

A copied receipt is not sufficient to establish archive acceptance. This tool
does not create an archive, retry delivery, remove an outbox item, authenticate
a sender, or modify any existing service.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
from urllib.parse import quote

from .contracts import content_hash, stable_id, validate_record
from .handoff import MAX_ENVELOPE_BYTES, unpack_event
from .manual_ingest import (
    COLLECTION,
    COACH_PROCESSING_VERSION,
    MANUAL_KINDS,
    _parse_input,
)
from .receipt_recovery import ReceiptError, _archived_event, verify_receipt

REPORT_VERSION = "1.0.0"
MAX_RECEIPT_BYTES = 16384
STATES = {
    "prepared_pending",
    "delivery_unknown",
    "archive_verified_receipt_missing",
    "archive_verified_receipt_valid",
    "archive_verified_receipt_invalid",
    "archive_conflict",
}
NEXT_ACTION = {
    "prepared_pending": "Retain original packet until an authorized transfer is attempted.",
    "delivery_unknown": "Retain and retry the exact packet; do not infer that no write occurred.",
    "archive_verified_receipt_missing": "Retain packet and regenerate its receipt from the same archive.",
    "archive_verified_receipt_valid": "Locally verified; retain packet until an approved retention policy applies.",
    "archive_verified_receipt_invalid": "Retain packet and investigate receipt mismatch before trusting it.",
    "archive_conflict": "Retain packet; review conflicting immutable source history manually.",
}


class DeliveryStateError(ValueError):
    """The input or selected archive cannot be safely reconciled."""


class ReadOnlyArchive:
    """Minimal view used by the existing receipt verifier within one SQL snapshot."""

    def __init__(self, connection, event_id):
        self.connection = connection
        self.event_id = event_id

    def revision(self, revision_id):
        row = self.connection.execute(
            "SELECT * FROM source_revisions WHERE revision_id=?", (revision_id,)
        ).fetchone()
        return dict(row) if row else None

    def current_records(self, kind=None):
        if kind != "event":
            raise DeliveryStateError("Only event projection is supported")
        rows = self.connection.execute(
            """SELECT n.record_json FROM normalized_records n
            JOIN source_revisions r ON r.revision_id=n.revision_id
            JOIN source_heads h ON h.revision_id=r.revision_id
            WHERE n.record_id=? AND n.kind='event' AND r.disposition='accepted'""",
            (self.event_id,),
        ).fetchall()
        return [json.loads(row[0]) for row in rows]


@contextmanager
def open_readonly(path: Path, event_id: str):
    """Open an existing local archive read-only without running migrations."""
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.is_symlink():
        raise DeliveryStateError("Archive must be an existing regular file")
    # mode=ro and query_only prevent migration, data insertion, and checkpoint
    # writes. A read transaction keeps the source/record/artifact view stable.
    uri = "file:" + quote(str(path.absolute()), safe="/") + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        try:
            versions = connection.execute(
                "SELECT version,contract_version FROM schema_versions"
            ).fetchall()
        except sqlite3.Error as exc:
            raise DeliveryStateError("Not a recognized physiology archive") from exc
        if [tuple(row) for row in versions] != [(1, "1.0.0")]:
            raise DeliveryStateError("Unsupported archive version")
        yield ReadOnlyArchive(connection, event_id)
    finally:
        connection.rollback()
        connection.close()


def _validated_original(envelope):
    original = unpack_event(envelope)
    raw = _parse_input(original)
    validate_record(raw)
    if (
        raw.get("record_type") != "event"
        or raw.get("source") != "coach:manual"
        or raw.get("processing_version") != COACH_PROCESSING_VERSION
        or raw.get("source_revision_id") is not None
        or raw.get("epistemic_type") != "reported"
        or raw.get("event_kind") not in MANUAL_KINDS
        or len(raw["id"]) > 256
        or len(raw["subject_id"]) > 256
    ):
        raise DeliveryStateError("Incompatible Coach event source or version")
    return original, raw


def reconcile_delivery(
    envelope: bytes,
    *,
    attempted: bool = False,
    archive_path: str | Path | None = None,
    receipt_bytes: bytes | None = None,
) -> dict:
    """Resolve a local status without writing to the selected archive.

    The caller's attempted flag is an unauthenticated assertion. A receipt
    alone never yields a confirmed status. Only direct archive inspection
    may produce archive_verified_* states.
    """
    if type(attempted) is not bool:
        raise DeliveryStateError("attempted must be boolean")
    original, raw = _validated_original(envelope)
    if receipt_bytes is not None and (
        type(receipt_bytes) is not bytes or len(receipt_bytes) > MAX_RECEIPT_BYTES
    ):
        raise DeliveryStateError("Receipt exceeds bounded size")
    has_receipt = receipt_bytes is not None
    source = "coach:manual:" + raw["subject_id"]
    source_key = "native:" + raw["id"]
    revision_id = stable_id(
        "revision",
        source,
        COLLECTION,
        source_key,
        content_hash(raw),
    )
    state = "delivery_unknown" if (attempted or has_receipt) else "prepared_pending"
    archive_checked = False
    receipt_checked = False
    evidence = "sender_assertion_only"
    if archive_path is not None:
        with open_readonly(Path(archive_path), raw["id"]) as archive:
            archive_checked = True
            rows = archive.connection.execute(
                """SELECT revision_id FROM source_revisions
                   WHERE source_instance=? AND collection=? AND source_key=?""",
                (source, COLLECTION, source_key),
            ).fetchall()
            if rows:
                if not any(row[0] == revision_id for row in rows):
                    state = "archive_conflict"
                    evidence = "local_archive_conflict"
                else:
                    try:
                        _archived_event(archive, original, raw["id"], revision_id)
                    except (ReceiptError, ValueError):
                        state = "archive_conflict"
                        evidence = "local_archive_conflict"
                    else:
                        evidence = "local_archive_snapshot"
                        if has_receipt:
                            receipt_checked = True
                            try:
                                verify_receipt(archive, envelope, receipt_bytes)
                            except (ReceiptError, ValueError):
                                state = "archive_verified_receipt_invalid"
                            else:
                                state = "archive_verified_receipt_valid"
                        else:
                            state = "archive_verified_receipt_missing"
            # No matching revision: cannot infer that a previous transfer
            # did not commit elsewhere. Keep the conservative pending state.
    result = {
        "report_version": REPORT_VERSION,
        "state": state,
        "evidence_level": evidence,
        "archive_checked": archive_checked,
        "receipt_present": has_receipt,
        "receipt_checked": receipt_checked,
        "event_id": raw["id"],
        "envelope_sha256": hashlib.sha256(envelope).hexdigest(),
        "expected_source_revision_id": revision_id,
        "authenticated_sender": False,
        "safe_to_delete_original": False,
        "next_action": NEXT_ACTION[state],
    }
    if state not in STATES:
        raise DeliveryStateError("Internal unsupported state")
    return result


def _bounded_regular_file(path: Path, maximum: int) -> bytes:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum:
        raise DeliveryStateError("Input must be a bounded regular file")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        value = stream.read(maximum + 1)
    if not 0 < len(value) <= maximum:
        raise DeliveryStateError("Input file changed while reading")
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--attempted", action="store_true")
    parser.add_argument("--output", type=Path, help="New private report JSON")
    args = parser.parse_args(argv)
    try:
        envelope = _bounded_regular_file(args.input, MAX_ENVELOPE_BYTES)
        receipt = (
            _bounded_regular_file(args.receipt, MAX_RECEIPT_BYTES)
            if args.receipt is not None
            else None
        )
        report = reconcile_delivery(
            envelope,
            attempted=args.attempted,
            archive_path=args.archive,
            receipt_bytes=receipt,
        )
        body = json.dumps(report, sort_keys=True, ensure_ascii=False) + "\n"
        if args.output is not None:
            if args.output.resolve() in {
                args.input.resolve(),
                args.archive.resolve() if args.archive else None,
                args.receipt.resolve() if args.receipt else None,
            }:
                raise DeliveryStateError("Report must not overwrite source files")
            if args.output.parent.is_symlink():
                raise DeliveryStateError("Symlinked report directory unsupported")
            fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
        else:
            sys.stdout.write(body)
        return 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        # A failed read is not evidence of absent archives or lost data.
        print(
            json.dumps(
                {
                    "status": "not_reconciled",
                    "error_type": type(exc).__name__,
                    "retain_original": True,
                }
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
