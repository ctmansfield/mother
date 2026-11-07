"""Strict, offline receiver for Coach's versioned manual-event envelope.

An explicitly selected, already-open Mother Archive is the only write target.
The digest checks bytes, NOT sender authentication or authorization.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from .manual_ingest import ingest_manual_event

ENVELOPE_VERSION = "1.0.0"
CONTENT_TYPE = "application/vnd.coach.manual-event+json"
MAX_ENVELOPE_BYTES = 400 * 1024
MAX_EVENT_BYTES = 256 * 1024
EXPECTED_KEYS = {
    "envelope_version",
    "content_type",
    "encoding",
    "event_sha256",
    "event_base64",
}


class EnvelopeError(ValueError):
    """Input envelope is malformed or violates the bounded wire contract."""


def _unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise EnvelopeError("Duplicate envelope key")
        out[key] = value
    return out


def _bad_constant(value):
    raise EnvelopeError("Non-finite JSON constant")


def unpack_event(envelope_bytes: bytes) -> bytes:
    """Return the *original* submitted event bytes after integrity checking."""
    if type(envelope_bytes) is not bytes or not envelope_bytes:
        raise EnvelopeError("Envelope must be nonempty bytes")
    if len(envelope_bytes) > MAX_ENVELOPE_BYTES:
        raise EnvelopeError("Envelope exceeds bounded size")
    try:
        obj = json.loads(
            envelope_bytes.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_bad_constant,
        )
    except (ValueError, UnicodeError) as exc:
        raise EnvelopeError("Invalid envelope JSON") from exc
    if not isinstance(obj, dict) or set(obj) != EXPECTED_KEYS:
        raise EnvelopeError("Envelope keys do not match wire contract")
    if (
        obj["envelope_version"] != ENVELOPE_VERSION
        or obj["content_type"] != CONTENT_TYPE
        or obj["encoding"] != "base64"
    ):
        raise EnvelopeError("Incompatible envelope version, type or encoding")
    digest = obj["event_sha256"]
    encoded = obj["event_base64"]
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(char not in "0123456789abcdef" for char in digest)
        or not isinstance(encoded, str)
    ):
        raise EnvelopeError("Invalid digest or encoded event")
    try:
        original = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise EnvelopeError("Invalid base64 event bytes") from exc
    if not original or len(original) > MAX_EVENT_BYTES:
        raise EnvelopeError("Event exceeds bounded size or is empty")
    if hashlib.sha256(original).hexdigest() != digest:
        raise EnvelopeError("Event bytes do not match the declared digest")
    return original


def accept_envelope(archive, envelope_bytes: bytes, *, received_at=None) -> dict:
    """Verify an envelope and let Mother perform full contract/archive checks."""
    original = unpack_event(envelope_bytes)
    receipt = ingest_manual_event(archive, original, received_at=received_at)
    return {
        "wire_version": ENVELOPE_VERSION,
        "envelope_sha256": hashlib.sha256(envelope_bytes).hexdigest(),
        "event_sha256": hashlib.sha256(original).hexdigest(),
        "event_id": receipt["event_id"],
        "revision_id": receipt["revision_id"],
        "new_records": receipt["new_records"],
        "repeated_revisions": receipt["repeated_revisions"],
        "status": "new" if receipt["new_records"] else "already_archived",
        "evidence_level": "offline_synthetic_or_unqualified_input",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument(
        "--archive",
        required=True,
        type=Path,
        help="Explicit SQLite archive path, never implicitly chosen",
    )
    args = parser.parse_args(argv)
    try:
        if args.input.resolve() == args.archive.resolve():
            raise EnvelopeError("Input and archive must be separate files")
        info = args.input.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ENVELOPE_BYTES:
            raise EnvelopeError("Input is not a bounded regular file")
        fd = os.open(args.input, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            with os.fdopen(fd, "rb") as handle:
                content = handle.read(MAX_ENVELOPE_BYTES + 1)
        except BaseException:
            os.close(fd)
            raise
        original = unpack_event(content)
        # Parse and validate the transport before an Archive may create a file.
        from .archive import Archive

        with Archive(args.archive) as archive:
            receipt = accept_envelope(archive, content)
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except (ValueError, OSError) as exc:
        # Never echo raw event contents, source text or credentials to stderr.
        print(
            json.dumps(
                {"status": "rejected", "error_type": type(exc).__name__},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
