"""One enrollment, one opaque object, and no decryption or ZIP handling."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import os
from pathlib import Path
import re
import shutil

from mother.physiology.contracts import canonical_json

from .files import hash_stream, private_path

TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}")
DIGEST = re.compile(r"[a-f0-9]{64}")
CHUNK = 4 * 1024**2
GIB = 1024**3


class VaultClosed(ValueError):
    pass


class VaultConflict(ValueError):
    pass


class VaultCapacity(ValueError):
    pass


def utc(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z",
        value,
    ):
        raise ValueError("history cutoff requires canonical UTC")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class Enrollment:
    vault_id: str
    import_id: str
    recipient_fingerprint: str
    expected_sha256: str
    expected_length: int
    cutoff: str
    max_allocation_bytes: int
    reserve_bytes: int
    enabled: bool = False

    def __post_init__(self):
        if not all(
            isinstance(item, str) and TOKEN.fullmatch(item)
            for item in (self.vault_id, self.import_id)
        ):
            raise ValueError("invalid history enrollment identity")
        if not all(
            isinstance(item, str) and DIGEST.fullmatch(item)
            for item in (self.recipient_fingerprint, self.expected_sha256)
        ):
            raise ValueError("invalid history enrollment digest")
        if (
            type(self.expected_length) is not int
            or not 1 <= self.expected_length <= 8 * GIB
            or type(self.max_allocation_bytes) is not int
            or not self.expected_length + 1024**2
            <= self.max_allocation_bytes
            <= 12 * GIB
            or type(self.reserve_bytes) is not int
            or not 16 * GIB <= self.reserve_bytes <= 1024 * GIB
            or type(self.enabled) is not bool
        ):
            raise ValueError("invalid history enrollment capacity")
        utc(self.cutoff)

    def identity(self):
        return canonical_json({k: v for k, v in vars(self).items() if k != "enabled"})


class CiphertextVault:
    """Store the pinned opaque ciphertext unchanged, independently of typed data."""

    def __init__(self, root, enrollment, *, clock=None, disk_usage=shutil.disk_usage):
        self.root = Path(root).absolute()
        self.enrollment = enrollment
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.disk_usage = disk_usage
        self.marker = self.root / "enrollment.json"
        self.lock = self.root / "writer.lock"
        self.partial = self.root / "partial.age"
        self.original = self.root / "original.age"
        self.committed = self.root / "receipt.json"

    def _sync_dir(self):
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    @staticmethod
    def _create(path, value=b""):
        with os.fdopen(
            os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600),
            "wb",
        ) as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())

    def initialize(self):
        private_path(self.root, directory=True)
        if any(self.root.iterdir()):
            raise ValueError("history vault initialization requires an empty root")
        self._create(self.marker, self.enrollment.identity().encode())
        self._create(self.lock)
        self._sync_dir()

    def _has(self, path):
        if os.path.lexists(path):
            private_path(path, directory=False)
            return True
        return False

    @contextmanager
    def _locked(self):
        private_path(self.root, directory=True)
        private_path(self.marker, directory=False)
        private_path(self.lock, directory=False)
        if self.marker.read_bytes() != self.enrollment.identity().encode():
            raise ValueError("history vault enrollment mismatch")
        with os.fdopen(os.open(self.lock, os.O_RDONLY | os.O_NOFOLLOW), "rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def _object(self):
        if self._has(self.original):
            if self._has(self.partial):
                raise ValueError("ambiguous history vault objects")
            return self.original
        return self.partial if self._has(self.partial) else None

    def _receipt_body(self):
        value = {
            "schema_version": "mse.historical-ciphertext-receipt/0.1",
            "vault_id": self.enrollment.vault_id,
            "import_id": self.enrollment.import_id,
            "recipient_fingerprint": self.enrollment.recipient_fingerprint,
            "ciphertext_sha256": self.enrollment.expected_sha256,
            "byte_length": self.enrollment.expected_length,
            "status": "opaque_ciphertext_durable",
        }
        return dict(
            value, receipt_id=sha256(canonical_json(value).encode()).hexdigest()
        )

    def _receipt(self):
        if not self._has(self.committed):
            return None
        body = self._receipt_body()
        if (
            self.committed.stat().st_size > 8192
            or self.committed.read_bytes() != canonical_json(body).encode()
        ):
            raise ValueError("history receipt integrity mismatch")
        if (
            self._object() != self.original
            or self.original.stat().st_size != body["byte_length"]
        ):
            raise ValueError("history ciphertext length mismatch")
        return body

    def _hash_original(self, selected):
        with selected.open("rb") as stream:
            actual = hash_stream(stream, self.enrollment.expected_length)
        if actual != (self.enrollment.expected_sha256, self.enrollment.expected_length):
            raise VaultConflict("history ciphertext has wrong digest or length")

    def check_startup(self):
        with self._locked():
            self._object()
            if self._receipt() is not None:
                self._hash_original(self.original)

    def writable(self):
        if not self.enrollment.enabled or self.clock() >= utc(self.enrollment.cutoff):
            raise VaultClosed("history intake closed")

    def progress(self):
        with self._locked():
            selected = self._object()
            return {
                "next_offset": selected.stat().st_size if selected is not None else 0,
                "complete": self._receipt() is not None,
            }

    def receipt(self):
        with self._locked():
            result = self._receipt()
            if result is None:
                raise KeyError("history receipt absent")
            return result

    def retrieve(self, offset):
        with self._locked():
            if self._receipt() is None:
                raise KeyError("history ciphertext unpublished")
            if not 0 <= offset < self.enrollment.expected_length:
                raise ValueError("history read offset outside object")
            with self.original.open("rb") as stream:
                stream.seek(offset)
                return stream.read(CHUNK)

    def put(self, offset, total, body, chunk_sha256):
        self.writable()
        if (
            type(offset) is not int
            or not 0 <= offset < self.enrollment.expected_length
            or total != self.enrollment.expected_length
            or not isinstance(body, bytes)
            or not 1 <= len(body) <= CHUNK
            or offset + len(body) > total
            or sha256(body).hexdigest() != chunk_sha256
        ):
            raise ValueError("invalid history chunk binding")
        with self._locked():
            self.writable()
            selected = self._object()
            present = selected.stat().st_size if selected is not None else 0
            if present > total:
                raise VaultConflict("history partial exceeds configured length")
            if offset < present:
                if offset + len(body) > present:
                    raise VaultConflict("history chunk overlaps incomplete range")
                with selected.open("rb") as stream:
                    stream.seek(offset)
                    if stream.read(len(body)) != body:
                        raise VaultConflict("history replay changed bytes")
                receipt = self._receipt()
                if receipt:
                    return receipt
            elif offset == present:
                if (
                    present + len(body) + 1024**2 > self.enrollment.max_allocation_bytes
                    or self.disk_usage(self.root).free
                    < self.enrollment.reserve_bytes + len(body) + 1024**2
                ):
                    raise VaultCapacity("history vault capacity gate")
                if selected is None:
                    self._create(self.partial)
                    self._sync_dir()
                self.writable()
                descriptor = os.open(
                    self.partial, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW
                )
                with os.fdopen(descriptor, "ab") as stream:
                    stream.write(body)
                    stream.flush()
                    os.fsync(stream.fileno())
                selected = self.partial
                present += len(body)
            else:
                raise VaultConflict("history chunk starts after verified prefix")
            self.writable()
            if present != total:
                return {"next_offset": present, "complete": False}
            self._hash_original(selected)
            self.writable()
            if selected == self.partial:
                os.rename(self.partial, self.original)
                self._sync_dir()
            self.writable()
            receipt = self._receipt_body()
            temporary = self.root / "receipt.pending"
            if self._has(temporary):
                # A crashed metadata write carries no authority. Full ciphertext
                # was verified again above before replacing that staging file.
                temporary.unlink()
            self._create(temporary, canonical_json(receipt).encode())
            self.writable()
            os.rename(temporary, self.committed)
            self._sync_dir()
            self.writable()
            return receipt
