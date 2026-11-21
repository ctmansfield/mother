"""Authenticate a native export into bounded scratch on the custodian volume."""

from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryFile
from threading import Timer

from mother.physiology.contracts import canonical_json

from .files import CHUNK, HistoryLimit, hash_stream, private_path
from .vault import DIGEST, TOKEN


class ExportAuthenticationError(ValueError):
    """The bound ciphertext could not authenticate under age."""


@contextmanager
def authenticate_export(
    *,
    ciphertext,
    receipt,
    recipient_fingerprint,
    plaintext_sha256,
    plaintext_length,
    age_executable,
    age_sha256,
    identity_file,
    scratch_root,
    limit,
    timeout=900,
):
    """Yield an anonymous seekable file only after successful age authentication."""
    required = {
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
        not isinstance(receipt, dict)
        or set(receipt) != required
        or receipt["schema_version"] != "mse.historical-ciphertext-receipt/0.1"
        or receipt["status"] != "opaque_ciphertext_durable"
        or receipt["recipient_fingerprint"] != recipient_fingerprint
        or not all(
            isinstance(pin, str) and DIGEST.fullmatch(pin)
            for pin in (
                recipient_fingerprint,
                plaintext_sha256,
                age_sha256,
                receipt["ciphertext_sha256"],
                receipt["receipt_id"],
            )
        )
        or not all(
            isinstance(receipt[k], str) and TOKEN.fullmatch(receipt[k])
            for k in ("vault_id", "import_id")
        )
        or type(plaintext_length) is not int
        or not 1 <= plaintext_length <= limit
        or type(receipt["byte_length"]) is not int
        or not 1 <= receipt["byte_length"] <= limit + 16 * 1024**2
    ):
        raise ValueError("invalid protected export binding")
    payload = {key: value for key, value in receipt.items() if key != "receipt_id"}
    if sha256(canonical_json(payload).encode()).hexdigest() != receipt["receipt_id"]:
        raise ValueError("protected export receipt identity mismatch")
    age = Path(age_executable).resolve(strict=True)
    with age.open("rb") as file:
        if hash_stream(file, 64 * 1024**2)[0] != age_sha256:
            raise ValueError("protected export age pin mismatch")
    identity, cipher, scratch = (
        Path(path).absolute() for path in (identity_file, ciphertext, scratch_root)
    )
    private_path(identity, directory=False)
    private_path(cipher, directory=False)
    private_path(scratch, directory=True)
    if shutil.disk_usage(scratch).free < plaintext_length + 64 * 1024**2:
        raise HistoryLimit("protected export scratch capacity insufficient")
    expected = (receipt["ciphertext_sha256"], receipt["byte_length"])
    with cipher.open("rb") as source, TemporaryFile(dir=scratch) as stage:
        if hash_stream(source, limit + 16 * 1024**2) != expected:
            raise ValueError("protected export ciphertext digest mismatch")
        source.seek(0)
        with subprocess.Popen(
            [str(age), "--decrypt", "--identity", str(identity)],
            stdin=source,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        ) as operation:
            timer = Timer(timeout, operation.kill)
            timer.start()
            try:
                count = 0
                digest = sha256()
                while block := operation.stdout.read(CHUNK):
                    count += len(block)
                    if count > plaintext_length:
                        raise ValueError("protected export plaintext exceeds pin")
                    digest.update(block)
                    stage.write(block)
                if operation.wait() != 0:
                    raise ExportAuthenticationError(
                        "protected export age authentication failed"
                    )
            except BaseException:
                if operation.poll() is None:
                    operation.kill()
                raise
            finally:
                timer.cancel()
        source.seek(0)
        if hash_stream(source, limit + 16 * 1024**2) != expected:
            raise ValueError("protected export ciphertext changed")
        if (digest.hexdigest(), count) != (plaintext_sha256, plaintext_length):
            raise ValueError("protected export exact plaintext pin mismatch")
        stage.seek(0)
        yield stage
