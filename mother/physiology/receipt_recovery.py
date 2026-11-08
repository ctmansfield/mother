"""Durable local receipts for offline Coach event handoffs.

A lost receipt does not require recovering or editing a previously accepted
event. Resubmitting the *same original envelope bytes* is idempotent; Mother
verifies its selected archive and writes the same receipt after commit.

A receipt is NOT a signature or sender authentication. Verification is only
meaningful against the actual local Mother archive selected by the caller.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

from .contracts import canonical_json, content_hash
from .handoff import MAX_ENVELOPE_BYTES, accept_envelope, unpack_event

RECEIPT_VERSION = "1.0.0"
RECEIPT_SUFFIX = ".mother-receipt.json"


class ReceiptError(ValueError):
    """Cannot safely write or authenticate a local archive receipt."""


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReceiptError("Duplicate receipt key")
        result[key] = value
    return result


def _constant(value):
    raise ReceiptError("Nonfinite receipt data is unsupported")


def _archived_event(archive, original: bytes, event_id: str, revision_id: str):
    """Check the normalized event and its exact original artifact."""
    try:
        raw = json.loads(original.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise ReceiptError("Event bytes are not JSON") from exc

    revision = archive.revision(revision_id)
    if revision is None or revision["disposition"] != "accepted":
        raise ReceiptError("Selected archive lacks accepted source revision")
    digest = hashlib.sha256(original).hexdigest()
    if revision["artifact_sha256"] != digest:
        # A semantic repeat with different whitespace can be a repeated
        # revision in PF-001. Do not falsely attest a new byte identity.
        raise ReceiptError("Archived original bytes differ from this submission")
    if revision["revision_hash"] != content_hash(raw):
        raise ReceiptError("Archived source revision hash differs")
    if revision["raw_json"] != canonical_json(raw):
        raise ReceiptError("Archived source record differs")
    row = archive.connection.execute(
        "SELECT content FROM raw_artifacts WHERE sha256=?", (digest,)
    ).fetchone()
    if row is None or bytes(row[0]) != original:
        raise ReceiptError("Original source artifact is missing")
    matches = [
        record
        for record in archive.current_records(kind="event")
        if record["id"] == event_id and record["source_revision_id"] == revision_id
    ]
    if len(matches) != 1 or matches[0]["subject_id"] != raw["subject_id"]:
        raise ReceiptError("Selected archive does not project this event")
    if matches[0]["payload"] != raw["payload"]:
        raise ReceiptError("Selected archive event payload differs")


def _receipt(
    archive, envelope: bytes, original: bytes, event_id: str, revision_id: str
):
    _archived_event(archive, original, event_id, revision_id)
    return {
        "receipt_version": RECEIPT_VERSION,
        "status": "archived_in_selected_local_archive",
        "envelope_sha256": hashlib.sha256(envelope).hexdigest(),
        "original_event_sha256": hashlib.sha256(original).hexdigest(),
        "event_id": event_id,
        "source_revision_id": revision_id,
        "evidence_level": "verified_local_archive",
        "authenticated_sender": False,
    }


def verify_receipt(archive, envelope: bytes, receipt_bytes: bytes) -> dict:
    """Reconcile a receipt against the actual selected archive and envelope."""
    original = unpack_event(envelope)
    if type(receipt_bytes) is not bytes or len(receipt_bytes) > 16384:
        raise ReceiptError("Receipt is not bounded original bytes")
    try:
        data = json.loads(
            receipt_bytes.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_constant,
        )
    except (UnicodeError, ValueError) as exc:
        raise ReceiptError("Receipt is invalid JSON") from exc
    if not isinstance(data, dict):
        raise ReceiptError("Receipt must be an object")
    if not isinstance(data.get("event_id"), str) or not isinstance(
        data.get("source_revision_id"), str
    ):
        raise ReceiptError("Receipt identities are invalid")
    expected = _receipt(
        archive, envelope, original, data["event_id"], data["source_revision_id"]
    )
    if data != expected:
        raise ReceiptError("Receipt fields differ from archived evidence")
    return data


def _receipt_bytes(receipt: dict) -> bytes:
    return (canonical_json(receipt) + "\n").encode("utf-8")


def _store_receipt(folder: Path, envelope: bytes, receipt: bytes) -> Path:
    """Publish a private receipt atomically, without replacing an old file."""
    if folder.is_symlink():
        raise ReceiptError("Symlinked receipt directory is unsupported")
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = folder.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
        raise ReceiptError("Receipt directory is not private")
    if os.name == "posix" and info.st_uid != os.getuid():
        raise ReceiptError("Receipt directory has another owner")
    name = hashlib.sha256(envelope).hexdigest() + RECEIPT_SUFFIX
    target = folder / name
    descriptor, temporary = tempfile.mkstemp(prefix=".pending-receipt-", dir=folder)
    temporary_path = Path(temporary)
    try:
        if os.name == "posix":
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(receipt)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary_path, target)
        except FileExistsError:
            previous = target.lstat()
            if (
                not stat.S_ISREG(previous.st_mode)
                or previous.st_nlink != 1
                or previous.st_mode & 0o077
                or (os.name == "posix" and previous.st_uid != os.getuid())
            ):
                raise ReceiptError("An existing receipt is not a private regular file")
            if target.read_bytes() != receipt:
                raise ReceiptError("Existing receipt has incompatible contents")
        directory_fd = os.open(folder, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary_path.unlink(missing_ok=True)
    return target


def ingest_with_receipt(
    archive,
    envelope: bytes,
    *,
    receipt_directory: str | Path,
    received_at: str | None = None,
) -> dict:
    """Archive first, verify persisted bytes, then publish durable receipt.

    If receipt publication fails after commit, retry the unchanged envelope.
    Do not delete a sender's outbox file on this function's success; release
    of retained sender bytes belongs to a separately authorized policy.
    """
    original = unpack_event(envelope)  # transport validation before any write
    result = accept_envelope(archive, envelope, received_at=received_at)
    receipt = _receipt(
        archive, envelope, original, result["event_id"], result["revision_id"]
    )
    raw = _receipt_bytes(receipt)
    destination = _store_receipt(Path(receipt_directory), envelope, raw)
    reconciled = verify_receipt(archive, envelope, destination.read_bytes())
    return {
        "status": "receipt_written_and_reconciled",
        "receipt_path": str(destination),
        "event_id": reconciled["event_id"],
        "source_revision_id": reconciled["source_revision_id"],
        "envelope_sha256": reconciled["envelope_sha256"],
        "original_event_sha256": reconciled["original_event_sha256"],
        "new_records": result["new_records"],
        "authenticated_sender": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--receipt-directory", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.input.resolve() == args.archive.resolve():
            raise ReceiptError("Input and archive paths must differ")
        if args.receipt_directory.is_symlink() or args.archive.is_symlink():
            raise ReceiptError("Symlinked destinations are unsupported")
        original_stat = args.input.lstat()
        if not stat.S_ISREG(original_stat.st_mode) or not (
            0 < original_stat.st_size <= MAX_ENVELOPE_BYTES
        ):
            raise ReceiptError("Input must be a bounded regular file")
        descriptor = os.open(args.input, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as handle:
            envelope = handle.read(MAX_ENVELOPE_BYTES + 1)
        unpack_event(envelope)
        # Ensure the output directory is acceptable before any archive commit.
        folder = args.receipt_directory
        if folder.exists():
            info = folder.stat()
            if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
                raise ReceiptError("Receipt directory must be private")
        from .archive import Archive

        with Archive(args.archive) as archive:
            outcome = ingest_with_receipt(archive, envelope, receipt_directory=folder)
        print(json.dumps(outcome, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, OSError) as exc:
        # Never include event contents, source metadata or credential text.
        print(
            json.dumps(
                {
                    "status": "not_confirmed",
                    "error_type": type(exc).__name__,
                    "retry_original_envelope": True,
                }
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
