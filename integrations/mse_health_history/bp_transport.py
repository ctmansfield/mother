"""ATLAS r3 BP page transport. Plaintext originals stay in bounded memory."""

from contextlib import closing, contextmanager
from hashlib import sha256
import json
from io import BytesIO
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess

from mother.physiology.contracts import canonical_json

from . import bp_page
from .blood_pressure import BloodPressure, source_uuid
from .files import hash_stream, private_path
from .vault import TOKEN, VaultCapacity, VaultClosed, VaultConflict

MAX_BYTES = 1024**2
MAX_ROWS = 512
MAX_PAGES = 100_000
FOREVER = "9999-12-31T23:59:59.999999Z"
FEEDS = {
    "correlation": "correlation",
    "systolic": "systolic",
    "diastolic": "diastolic",
}
CURSOR = re.compile(r"[A-Za-z0-9_-]{43}")
DDL = """
CREATE TABLE identity (body TEXT NOT NULL);
CREATE TABLE pages (
 stream TEXT NOT NULL, seq INTEGER NOT NULL, digest TEXT NOT NULL,
 raw_size INTEGER NOT NULL, ciphertext BLOB NOT NULL, cipher_digest TEXT NOT NULL,
 receipt TEXT NOT NULL, custody_at TEXT, witness TEXT, custodian_proof TEXT,
 PRIMARY KEY(stream,seq)
);
CREATE TABLE checkpoints (
 stream TEXT PRIMARY KEY, seq INTEGER NOT NULL, cursor TEXT NOT NULL UNIQUE
);
CREATE TABLE cursors (token TEXT PRIMARY KEY);
CREATE TABLE results (
 stream TEXT NOT NULL, seq INTEGER NOT NULL, ordinal INTEGER NOT NULL, fact TEXT NOT NULL,
 PRIMARY KEY (stream,seq,ordinal),
 FOREIGN KEY (stream,seq) REFERENCES pages(stream,seq)
);
"""


class BPUnavailable(OSError):
    pass


def digest(body):
    return sha256(body).hexdigest()


def _key(value):
    return isinstance(value, str) and TOKEN.fullmatch(value) is not None


class Sealer:
    def __init__(self, executable, executable_sha256, recipient_file, recipient_sha256):
        self.executable = Path(executable).resolve(strict=True)
        self.recipient = Path(recipient_file).absolute()
        self.executable_sha256 = executable_sha256
        self.recipient_sha256 = recipient_sha256
        self.check()

    def check(self):
        with self.executable.open("rb") as stream:
            if hash_stream(stream, 64 * 1024**2)[0] != self.executable_sha256:
                raise ValueError("age executable pin mismatch")
        private_path(self.recipient, directory=False)
        with self.recipient.open("rb") as stream:
            raw = stream.read(4097)
        if not 1 <= len(raw) <= 4096 or digest(raw) != self.recipient_sha256:
            raise ValueError("age public recipient pin mismatch")
        if not re.fullmatch(rb"(?:age1|age1pq1)[a-z0-9]+\n?", raw):
            raise ValueError("expected one native age public recipient")

    def __call__(self, raw):
        self.check()
        try:
            sealed = subprocess.run(
                [
                    str(self.executable),
                    "--encrypt",
                    "--recipients-file",
                    str(self.recipient),
                ],
                input=raw,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=15,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            raise BPUnavailable("age sealing failed") from None
        if (
            not sealed.startswith(b"age-encryption.org/v1\n")
            or len(sealed) > 2 * MAX_BYTES
        ):
            raise BPUnavailable("age sealing failed")
        return sealed


class BPStore:
    def __init__(self, root, config, sealer, key, *, clock, verify_custodian):
        self.root = Path(root).absolute()
        self.db = self.root / "bp-history.sqlite3"
        self.config = config
        self.clock = clock
        self.sealer = sealer
        self.verify_custodian = verify_custodian
        self.normalizer = BloodPressure(config["source_instance"], key)
        self.identity = canonical_json(
            {
                k: config[k]
                for k in (
                    "archive_id",
                    "enrollment_id",
                    "source_instance",
                    "streams",
                    "snapshot",
                    "transport_starts_at",
                    "transport_ends_at",
                    "recipient_sha256",
                    "age_sha256",
                    "max_pages",
                    "custodian_public_sha256",
                    "max_bytes",
                    "reserve_bytes",
                )
            }
            | {"key_pin": digest(key), "layout": "bp-history-sqlite/2"}
        )

    def writable(self, now=None):
        now = self.clock() if now is None else now
        if (
            not self.config["enabled"]
            or not self.config["transport_starts_at"]
            <= now
            < self.config["transport_ends_at"]
        ):
            raise VaultClosed("BP transport closed")

    def initialize(self):
        private_path(self.root, directory=True)
        if any(self.root.iterdir()):
            raise ValueError("BP initialization requires empty root")
        os.close(
            os.open(
                self.db, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600
            )
        )
        with closing(sqlite3.connect(self.db)) as db, db:
            db.executescript("BEGIN IMMEDIATE;\n" + DDL)
            db.execute("INSERT INTO identity VALUES (?)", (self.identity,))
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    @contextmanager
    def connect(self, *, write=False):
        private_path(self.root, directory=True)
        private_path(self.db, directory=False)
        for suffix in ("-journal", "-wal", "-shm"):
            sidecar = Path(str(self.db) + suffix)
            if os.path.lexists(sidecar):
                private_path(sidecar, directory=False)
        with (
            closing(
                sqlite3.connect(
                    self.db.as_uri() + ("?mode=rw" if write else "?mode=ro"),
                    uri=True,
                    timeout=3,
                )
            ) as db,
            db,
        ):
            db.execute("PRAGMA foreign_keys=ON")
            if write:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT body FROM identity").fetchall() != [(self.identity,)]:
                raise ValueError("BP enrollment identity mismatch")
            yield db

    def _parse(self, stream, seq, raw):
        if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
            raise VaultCapacity("BP page byte cap")
        page = bp_page.read_page(
            BytesIO(raw), self.config["enrollment_id"], self.config["source_instance"]
        )
        if (
            page["feed"] != stream
            or page["through"] != self.config["snapshot"]["sample_end_before"]
        ):
            raise ValueError("BP page binding mismatch")
        return page

    def _facts(self, stream, page):
        feed = next(
            FEEDS[key]
            for key, binding in self.config["streams"].items()
            if binding == stream
        )
        snapshot = self.config["snapshot"]
        lower, upper = snapshot["sample_start_at"], snapshot["sample_end_before"]
        facts = []
        seen = set()
        for row in page["upserts"]:
            identity, revision, fact = bp_page.normalize(
                row, feed, FOREVER, self.normalizer
            )
            start = fact["clocks"]["event_start"]
            if (lower is not None and start < lower) or start >= upper:
                raise ValueError("BP sample outside frozen predicate")
            if identity in seen:
                raise ValueError("duplicate BP upsert identity")
            seen.add(identity)
            facts.append({"operation": "upsert", "revision": revision, "fact": fact})
        deleted = set()
        for value in page["deleted_ids"]:
            native = source_uuid(value)
            if native is None or native != value or native in deleted:
                raise ValueError("invalid BP deletion identity")
            deleted.add(native)
            identity = self.normalizer._native({"uuid": native}, bp_page.FEEDS[feed])
            facts.append({"operation": "delete", "identity": identity})
        return facts

    def receipt(self, stream, seq):
        with self.connect() as db:
            row = db.execute(
                "SELECT digest,receipt,witness FROM pages WHERE stream=? AND seq=?",
                (stream, seq),
            ).fetchone()
        if row is None or row[2] is None:
            raise KeyError("BP receipt absent")
        body = json.loads(row[1])
        if (
            not self.config["transport_starts_at"]
            <= row[2]
            < self.config["transport_ends_at"]
            or body["sha256"] != row[0]
        ):
            raise BPUnavailable("BP receipt witness mismatch")
        return body

    def put(self, stream, seq, raw):
        self.writable()
        page = self._parse(stream, seq, raw)
        pin = digest(raw)
        body = {
            "schema_version": "mse.historical-bp-page-receipt/0.1",
            "status": "typed_and_cursor_durable",
            "archive_id": self.config["archive_id"],
            "enrollment": page["enrollment"],
            "source_instance": page["source_instance"],
            "feed": stream,
            "through": page["through"],
            "sha256": pin,
            "byte_length": len(raw),
            "cursor_in": page["cursor_in"],
            "cursor_out": page["cursor_out"],
            "typed_upserts": len(page["upserts"]),
            "typed_tombstones": len(page["deleted_ids"]),
            "exhausted": page["exhausted"],
            "protection": "custodian_verified_ciphertext",
        }
        with self.connect(write=True) as db:
            self.writable()
            previous = db.execute(
                "SELECT digest,receipt,witness,custody_at FROM pages WHERE stream=? AND seq=?",
                (stream, seq),
            ).fetchone()
            if previous is not None:
                if previous[0] != pin:
                    raise VaultConflict("BP page identity conflict")
                if previous[2] is None:
                    if previous[3] is None:
                        raise BPUnavailable("BP page requires sealed reconciliation")
                    return 202, {"status": "pending_custodian_verification"}
                return 200, json.loads(previous[1])
            if db.execute(
                "SELECT 1 FROM pages WHERE witness IS NULL LIMIT 1"
            ).fetchone():
                raise BPUnavailable("BP intake requires sealed reconciliation")
            head = db.execute(
                """SELECT c.seq,c.cursor,p.receipt FROM checkpoints c JOIN pages p
                   ON p.stream=c.stream AND p.seq=c.seq WHERE c.stream=?""",
                (stream,),
            ).fetchone()
            same_terminal_cursor = (
                page["exhausted"] and page["cursor_out"] == page["cursor_in"]
            )
            if (
                seq != (head[0] + 1 if head else 1)
                or page["cursor_in"] != (head[1] if head else None)
                or (head and json.loads(head[2])["exhausted"])
                or (
                    not same_terminal_cursor
                    and db.execute(
                        "SELECT 1 FROM cursors WHERE token=?", (page["cursor_out"],)
                    ).fetchone()
                )
            ):
                raise VaultConflict("BP checkpoint conflict")
            if (
                db.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
                >= self.config["max_pages"]
            ):
                raise VaultCapacity("BP archive quota")
            facts = self._facts(stream, page)
            cipher = self.sealer(raw)
            used = db.execute(
                "SELECT COALESCE(SUM(length(ciphertext)),0) FROM pages"
            ).fetchone()[0]
            if (
                used + len(cipher) > self.config["max_bytes"]
                or shutil.disk_usage(self.root).free
                < self.config["reserve_bytes"] + 8 * MAX_BYTES
            ):
                raise VaultCapacity("BP archive byte quota")
            raw_receipt = self._raw_receipt(stream, seq, cipher)
            body["ciphertext_receipt"] = raw_receipt
            body["receipt_id"] = digest(
                canonical_json({"seq": seq, "receipt": body}).encode()
            )
            self.writable()
            db.execute(
                "INSERT INTO pages VALUES (?,?,?,?,?,?,?,NULL,NULL,NULL)",
                (
                    stream,
                    seq,
                    pin,
                    len(raw),
                    cipher,
                    digest(cipher),
                    canonical_json(body),
                ),
            )
            db.executemany(
                "INSERT INTO results VALUES (?,?,?,?)",
                [
                    (stream, seq, i, canonical_json(fact))
                    for i, fact in enumerate(facts)
                ],
            )
            if not same_terminal_cursor:
                db.execute("INSERT INTO cursors VALUES (?)", (page["cursor_out"],))
            self.writable()

        verified_at = self.clock()
        self.writable(verified_at)
        with self.connect(write=True) as db:
            self.writable()
            db.execute(
                "UPDATE pages SET custody_at=? WHERE stream=? AND seq=?",
                (verified_at, stream, seq),
            )
        return 202, {"status": "pending_custodian_verification"}

    def _raw_receipt(self, stream, seq, cipher):
        record = {
            "schema_version": "mse.historical-ciphertext-receipt/0.1",
            "vault_id": self.config["archive_id"],
            "import_id": digest(
                canonical_json([self.config["enrollment_id"], stream, seq]).encode()
            ),
            "recipient_fingerprint": self.config["recipient_sha256"],
            "ciphertext_sha256": digest(cipher),
            "byte_length": len(cipher),
            "status": "opaque_ciphertext_durable",
        }
        return dict(record, receipt_id=digest(canonical_json(record).encode()))

    def _custody(self, db, stream, seq):
        row = db.execute(
            "SELECT digest,raw_size,ciphertext,cipher_digest,receipt,custody_at FROM pages WHERE stream=? AND seq=?",
            (stream, seq),
        ).fetchone()
        if (
            not row
            or not row[5]
            or not self.config["transport_starts_at"]
            <= row[5]
            < self.config["transport_ends_at"]
        ):
            raise KeyError("BP custody absent")
        if digest(row[2]) != row[3]:
            raise BPUnavailable("BP custody digest mismatch")
        body = json.loads(row[4])
        if body["ciphertext_receipt"] != self._raw_receipt(stream, seq, row[2]):
            raise BPUnavailable("BP custody receipt mismatch")
        return {
            "schema": "bp-history-custodian-witness-v1",
            "archive_id": self.config["archive_id"],
            "enrollment_id": self.config["enrollment_id"],
            "source_instance": self.config["source_instance"],
            "feed": stream,
            "page_seq": seq,
            "plaintext_sha256": row[0],
            "plaintext_length": row[1],
            "ciphertext_receipt": body["ciphertext_receipt"],
            "typed_receipt_id": body["receipt_id"],
        }, row[2]

    def custody(self, stream, seq, *, ciphertext=False):
        with self.connect() as db:
            return self._custody(db, stream, seq)[int(ciphertext)]

    def commit(self, stream, seq, statement, signature):
        self.writable()
        if not self.verify_custodian(canonical_json(statement).encode(), signature):
            raise ValueError("invalid BP custodian signature")
        with self.connect(write=True) as db:
            self.writable()
            expected, _ = self._custody(db, stream, seq)
            if expected != statement:
                raise VaultConflict("BP custodian witness mismatch")
            row = db.execute(
                "SELECT custodian_proof,witness FROM pages WHERE stream=? AND seq=?",
                (stream, seq),
            ).fetchone()
            if row[1] is not None:
                return 200, self.receipt(stream, seq)
            if row[0] is not None:
                raise BPUnavailable("BP typed decision is sealed")
            db.execute(
                "UPDATE pages SET custodian_proof=? WHERE stream=? AND seq=?",
                (
                    canonical_json({"statement": statement, "signature": signature}),
                    stream,
                    seq,
                ),
            )
            receipt = json.loads(
                db.execute(
                    "SELECT receipt FROM pages WHERE stream=? AND seq=?", (stream, seq)
                ).fetchone()[0]
            )
            db.execute(
                """INSERT INTO checkpoints VALUES (?,?,?)
                   ON CONFLICT(stream) DO UPDATE SET seq=excluded.seq,cursor=excluded.cursor""",
                (stream, seq, receipt["cursor_out"]),
            )
            self.writable()
        observed = self.clock()
        self.writable(observed)
        with self.connect(write=True) as db:
            self.writable()
            db.execute(
                "UPDATE pages SET witness=? WHERE stream=? AND seq=?",
                (observed, stream, seq),
            )
        return 200, self.receipt(stream, seq)

    def export(self, stream, start, through):
        if not 1 <= start <= through or through - start >= 4:
            raise ValueError("BP export span out of bounds")
        with self.connect() as db:
            rows = db.execute(
                """SELECT r.seq,r.fact FROM results r JOIN pages p
                   ON p.stream=r.stream AND p.seq=r.seq
                   WHERE r.stream=? AND r.seq BETWEEN ? AND ?
                     AND p.witness>=? AND p.witness<?
                   ORDER BY r.seq,r.ordinal""",
                (
                    stream,
                    start,
                    through,
                    self.config["transport_starts_at"],
                    self.config["transport_ends_at"],
                ),
            )
            data = [{"page_seq": seq, **json.loads(fact)} for seq, fact in rows]
        result = {"schema": "bp-history-export-v1", "stream_id": stream, "rows": data}
        if len(canonical_json(result).encode()) > 2 * MAX_BYTES:
            raise VaultCapacity("BP export byte cap")
        return result
