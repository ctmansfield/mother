"""Prepare an exact r4 callback after custodian-only age authentication."""

import base64
from pathlib import Path

from mother.physiology.contracts import canonical_json

from .sealed_page import MAX_CIPHERTEXT, authenticate_page

BINDINGS = {
    "archive_id",
    "enrollment",
    "source_instance",
    "through",
    "stream_id",
    "feed",
    "page_seq",
    "sha256",
    "byte_length",
}


def verify_and_prepare(envelope, *, expected, ciphertext_path, **custodian_inputs):
    """Return callback bytes only after an independent binding and exact decrypt."""
    if (
        set(envelope) != {"witness", "ciphertext_receipt", "ciphertext_base64"}
        or set(expected) != BINDINGS
        or set(envelope["witness"])
        != BINDINGS
        | {
            "schema_version",
            "ciphertext_receipt_id",
            "ciphertext_sha256",
            "recipient_fingerprint",
        }
    ):
        raise ValueError("BP custody envelope shape mismatch")
    witness = envelope["witness"]
    receipt = envelope["ciphertext_receipt"]
    if (
        witness["schema_version"] != "mse.historical-bp-custody-witness/0.1"
        or any(
            witness[k] != v or type(witness[k]) is not type(v)
            for k, v in expected.items()
        )
        or witness["ciphertext_receipt_id"] != receipt["receipt_id"]
        or witness["ciphertext_sha256"] != receipt["ciphertext_sha256"]
        or witness["recipient_fingerprint"] != receipt["recipient_fingerprint"]
    ):
        raise ValueError("BP custody binding mismatch")
    encoded = envelope["ciphertext_base64"]
    if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_CIPHERTEXT + 2) // 3):
        raise ValueError("BP custody ciphertext exceeds bound")
    pinned_ciphertext = base64.b64decode(encoded, validate=True)
    with Path(ciphertext_path).open("rb") as stream:
        if stream.read(MAX_CIPHERTEXT + 1) != pinned_ciphertext:
            raise ValueError("BP custody ciphertext differs from response")
    plaintext, _ = authenticate_page(
        ciphertext=ciphertext_path,
        vault_receipt=receipt,
        plaintext_sha256=expected["sha256"],
        plaintext_length=expected["byte_length"],
        **custodian_inputs,
    )
    plaintext.close()
    return canonical_json(witness).encode("utf-8")
