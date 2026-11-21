"""Custodian-side authentication of one bounded BP page, without plaintext files."""

from hashlib import sha256
import io
from pathlib import Path
import subprocess

from mother.physiology.contracts import canonical_json

from .bp_page import MAX_BYTES
from .files import hash_stream, private_path
from .vault import DIGEST, TOKEN

MAX_CIPHERTEXT = 2 * MAX_BYTES


def _valid_digest(value):
    return isinstance(value, str) and DIGEST.fullmatch(value) is not None


def authenticate_page(
    *,
    ciphertext,
    vault_receipt,
    recipient_fingerprint,
    plaintext_sha256,
    plaintext_length,
    age_executable,
    age_sha256,
    identity_file,
):
    """Return verified plaintext and a safe receipt binding inside custodian memory."""
    expected_keys = {
        "schema_version",
        "vault_id",
        "import_id",
        "recipient_fingerprint",
        "ciphertext_sha256",
        "byte_length",
        "status",
        "receipt_id",
    }
    if (
        not isinstance(vault_receipt, dict)
        or set(vault_receipt) != expected_keys
        or vault_receipt["schema_version"] != "mse.historical-ciphertext-receipt/0.1"
        or vault_receipt["status"] != "opaque_ciphertext_durable"
        or vault_receipt["recipient_fingerprint"] != recipient_fingerprint
        or not all(
            _valid_digest(value)
            for value in (
                recipient_fingerprint,
                plaintext_sha256,
                age_sha256,
                vault_receipt["ciphertext_sha256"],
                vault_receipt["receipt_id"],
            )
        )
        or not all(
            isinstance(vault_receipt[field], str)
            and TOKEN.fullmatch(vault_receipt[field])
            for field in ("vault_id", "import_id")
        )
        or type(vault_receipt["byte_length"]) is not int
        or not 1 <= vault_receipt["byte_length"] <= MAX_CIPHERTEXT
        or type(plaintext_length) is not int
        or not 1 <= plaintext_length <= MAX_BYTES
    ):
        raise ValueError("invalid historical ciphertext custody binding")
    receipt_body = {
        key: value for key, value in vault_receipt.items() if key != "receipt_id"
    }
    if (
        sha256(canonical_json(receipt_body).encode()).hexdigest()
        != vault_receipt["receipt_id"]
    ):
        raise ValueError("historical ciphertext receipt identity mismatch")

    age = Path(age_executable).resolve(strict=True)
    with age.open("rb") as stream:
        if hash_stream(stream, 64 * 1024**2)[0] != age_sha256:
            raise ValueError("historical age executable pin mismatch")
    identity = Path(identity_file).absolute()
    private_path(identity, directory=False)
    cipher = Path(ciphertext).absolute()
    private_path(cipher, directory=False)
    expected = (vault_receipt["ciphertext_sha256"], vault_receipt["byte_length"])
    with cipher.open("rb") as stream:
        if hash_stream(stream, MAX_CIPHERTEXT) != expected:
            raise ValueError("historical ciphertext differs from durable receipt")
        stream.seek(0)
        try:
            decrypted = subprocess.run(
                [str(age), "--decrypt", "--identity", str(identity)],
                stdin=stream,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=True,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            raise ValueError("historical ciphertext authentication failed") from None
        stream.seek(0)
        if hash_stream(stream, MAX_CIPHERTEXT) != expected:
            raise ValueError("historical ciphertext changed during authentication")
    if (
        len(decrypted) != plaintext_length
        or sha256(decrypted).hexdigest() != plaintext_sha256
    ):
        raise ValueError("historical exact plaintext pin mismatch")
    return io.BytesIO(decrypted), dict(vault_receipt)
