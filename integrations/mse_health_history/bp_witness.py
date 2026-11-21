"""Detached Ed25519 witness. Only the custodian runs decryption and signing."""

import argparse
import base64
import json
import binascii
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from mother.physiology.contracts import canonical_json

from .files import hash_stream, private_path
from .sealed_page import authenticate_page


def _execute(openssl, mode, key, message, sig=None):
    # Temporary inputs contain only signed custody metadata and a signature.
    # Decrypted bytes and normalized facts never enter these files.
    with TemporaryDirectory(prefix="bp-witness-") as directory:
        root = Path(directory)
        payload = root / "metadata"
        payload.write_bytes(message)
        command = [
            str(openssl),
            "pkeyutl",
            mode,
            "-rawin",
            "-inkey",
            str(key),
            "-in",
            str(payload),
        ]
        if sig is not None:
            signature = root / "signature"
            signature.write_bytes(sig)
            command.extend(["-pubin", "-sigfile", str(signature)])
        return subprocess.run(
            command, capture_output=True, timeout=5, check=True
        ).stdout


class CustodianVerifier:
    def __init__(self, key, pin, openssl="/usr/bin/openssl"):
        self.key = Path(key).absolute()
        self.pin = pin
        self.openssl = Path(openssl).resolve(strict=True)
        self.check()

    def check(self):
        private_path(self.key, directory=False)
        with self.key.open("rb") as stream:
            if hash_stream(stream, 8192)[0] != self.pin:
                raise ValueError("custodian public key pin mismatch")

    def __call__(self, message, signature):
        try:
            self.check()
            if not isinstance(signature, str) or len(signature) != 86:
                return False
            raw = base64.b64decode(signature + "==", altchars=b"-_", validate=True)
            if (
                len(raw) != 64
                or base64.urlsafe_b64encode(raw).decode().rstrip("=") != signature
            ):
                return False
            _execute(self.openssl, "-verify", self.key, message, raw)
            return True
        except (OSError, ValueError, binascii.Error, subprocess.SubprocessError):
            return False


def authenticate_and_sign(
    statement, *, expected_binding, signing_key, openssl="/usr/bin/openssl", **inputs
):
    """Run with independently trusted binding and keys inside custodian custody."""
    fields = {
        "archive_id",
        "enrollment_id",
        "source_instance",
        "feed",
        "page_seq",
        "plaintext_sha256",
        "plaintext_length",
        "ciphertext_receipt",
        "typed_receipt_id",
    }
    if (
        not isinstance(statement, dict)
        or set(statement) != fields | {"schema"}
        or statement["schema"] != "bp-history-custodian-witness-v1"
        or not isinstance(expected_binding, dict)
        or set(expected_binding) != fields - {"ciphertext_receipt", "typed_receipt_id"}
        or any(statement[field] != value for field, value in expected_binding.items())
    ):
        raise ValueError("custodian statement does not match independent page binding")
    plaintext, _ = authenticate_page(
        **inputs,
        vault_receipt=statement["ciphertext_receipt"],
        plaintext_sha256=statement["plaintext_sha256"],
        plaintext_length=statement["plaintext_length"],
    )
    plaintext.close()
    key = Path(signing_key).absolute()
    private_path(key, directory=False)
    signature = _execute(openssl, "-sign", key, canonical_json(statement).encode())
    if len(signature) != 64:
        raise ValueError("expected Ed25519 witness signature")
    return {
        "statement": statement,
        "signature": base64.urlsafe_b64encode(signature).decode().rstrip("="),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in (
        "statement",
        "binding",
        "ciphertext",
        "signing_key",
        "identity_file",
        "age_executable",
        "age_sha256",
        "recipient_fingerprint",
        "openssl",
    ):
        parser.add_argument("--" + field.replace("_", "-"), required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = vars(parser.parse_args())
    output = args.pop("output")
    try:
        for flag in ("statement", "binding"):
            path = Path(args[flag]).absolute()
            private_path(path, directory=False)
            with path.open("rb") as stream:
                raw = stream.read(8193)
            if len(raw) > 8192:
                raise ValueError("custodian metadata exceeds bound")
            args[flag] = json.loads(raw)
        proof = authenticate_and_sign(
            args.pop("statement"), expected_binding=args.pop("binding"), **args
        )
        import os

        with os.fdopen(
            os.open(
                output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            ),
            "wb",
        ) as result:
            result.write(canonical_json(proof).encode())
            result.flush()
            os.fsync(result.fileno())
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        print("BP witness refused", file=__import__("sys").stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
