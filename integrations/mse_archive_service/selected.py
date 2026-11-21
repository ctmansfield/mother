"""Offline-only adapter for the additive selected HealthKit archive."""

from contextlib import closing, contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import stat

from jsonschema import Draft202012Validator, FormatChecker

from integrations.healthbridge.capture import _check_depth, _unique_object
from integrations.mse_ingest import BatchConflict
from mother.physiology.contracts import canonical_json

SCHEMA = (
    Path(__file__).resolve().parents[2]
    / "docs/mse/integration/selected-healthkit/selected-healthkit.schema.json"
)
SCHEMA_SHA256 = "894765479170588508d1721c8b50fa20d47985910dcf427ed63e5b8fa0aceef8"
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
BATCH_PATH = re.compile(r"/v2/archive/batches/([A-Za-z0-9][A-Za-z0-9._:-]{0,127})")
DIGEST = re.compile(r"[a-f0-9]{64}")
MAX_BYTES = 128 * 1024
MAX_RECORDS = 128
MAX_COMMITS_PER_EXPORT = 8
MAX_EXPORT_BYTES = 2 * 1024 * 1024
PROCESSING = "mse.selected-healthkit-preserve/0.1"
DDL = """
CREATE TABLE identity (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);
CREATE TABLE batches (
    sequence INTEGER PRIMARY KEY, batch TEXT NOT NULL UNIQUE,
    artifact TEXT NOT NULL, original BLOB NOT NULL, receipt TEXT NOT NULL
);
CREATE TABLE sightings (
    sequence INTEGER NOT NULL REFERENCES batches(sequence),
    ordinal INTEGER NOT NULL, metric TEXT NOT NULL, native_id TEXT NOT NULL,
    operation TEXT NOT NULL CHECK(operation IN ('upsert','delete')),
    fact TEXT NOT NULL, processing TEXT NOT NULL,
    PRIMARY KEY(sequence, ordinal)
);
CREATE INDEX sightings_key ON sightings(metric, native_id, operation, sequence);
"""


def _digest(data):
    return sha256(data).hexdigest()


def _pin(value):
    return _digest(canonical_json(value).encode("utf-8"))


def _clock():
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _bounded_integer(text):
    if len(text) > 20:
        raise ValueError("selected JSON integer exceeds bound")
    return int(text)


def _reject_number(_):
    raise ValueError("selected JSON decimal values must be strings")


def _fact(scope, record):
    body = dict(record)
    if body["operation"] == "upsert":
        del body["collector_received_at"]
    return _pin(["mse.selected-fact/0.1", scope, body])


def _processing(fact, record):
    oxygen_outside_domain = (
        record["operation"] == "upsert"
        and record["metric"] == "oxygen_saturation"
        and not Decimal(0) <= Decimal(record["value"]) <= Decimal(1)
    )
    finding = "oxygen_fraction_out_of_domain" if oxygen_outside_domain else None
    return _pin([PROCESSING, fact, finding]), finding


class SelectedArchive:
    """A single synthetic grant and an independently initialized SQLite root."""

    def __init__(self, root, *, archive_id, scope, allowed_artifact_sha256):
        self.root = Path(root).absolute()
        self.path = self.root / "selected-healthkit.sqlite3"
        if not isinstance(archive_id, str) or not TOKEN.fullmatch(archive_id):
            raise ValueError("invalid selected archive identity")
        schema_bytes = SCHEMA.read_bytes()
        if _digest(schema_bytes) != SCHEMA_SHA256:
            raise ValueError("selected schema pin mismatch")
        schema = json.loads(schema_bytes)
        self.validator = Draft202012Validator(schema, format_checker=FormatChecker())
        self._validate("scope", scope)
        if not all(
            TOKEN.fullmatch(scope[key]) for key in ("subject_id", "source_instance")
        ):
            raise ValueError("invalid selected scope tokens")
        if not scope["subject_id"].startswith("synthetic-"):
            raise ValueError("selected archive is synthetic-only")
        self.allowed = frozenset(allowed_artifact_sha256)
        if not 1 <= len(self.allowed) <= 32 or any(
            not isinstance(item, str) or not DIGEST.fullmatch(item)
            for item in self.allowed
        ):
            raise ValueError("invalid selected synthetic grant")
        self.archive_id = archive_id
        self.scope = dict(scope)
        self.identity = canonical_json(
            {
                "archive_id": archive_id,
                "scope": self.scope,
                "layout": "selected-healthkit-sqlite/1",
                "schema_sha256": SCHEMA_SHA256,
                "processing_version": PROCESSING,
            }
        )

    def _validate(self, definition, value):
        validator = self.validator.evolve(schema={"$ref": f"#/$defs/{definition}"})
        if not validator.is_valid(value):
            raise ValueError(f"invalid selected {definition}")

    def _check_root(self):
        status = self.root.stat()
        if (
            self.root.resolve(strict=True) != self.root
            or status.st_uid != os.geteuid()
            or stat.S_IMODE(status.st_mode) != 0o700
            or not stat.S_ISDIR(status.st_mode)
        ):
            raise ValueError("selected archive root must be canonical and private")

    def _check_file(self, path):
        status = path.lstat()
        if (
            not stat.S_ISREG(status.st_mode)
            or status.st_uid != os.geteuid()
            or status.st_nlink != 1
            or stat.S_IMODE(status.st_mode) != 0o600
        ):
            raise ValueError("selected archive file must be private")

    def initialize(self):
        self._check_root()
        if any(self.root.iterdir()):
            raise ValueError("selected initialization requires an empty root")
        descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executescript("BEGIN IMMEDIATE;\n" + DDL)
            db.execute("INSERT INTO identity VALUES (1,?)", (self.identity,))
        self.check_startup()

    @contextmanager
    def _connection(self, *, write=False):
        self._check_root()
        self._check_file(self.path)
        journal = self.path.with_name(self.path.name + "-journal")
        if os.path.lexists(journal):
            self._check_file(journal)
        for suffix in ("-wal", "-shm"):
            if os.path.lexists(str(self.path) + suffix):
                raise ValueError("unexpected selected archive sidecar")
        uri = self.path.as_uri() + ("?mode=rw" if write else "?mode=ro")
        with closing(sqlite3.connect(uri, uri=True, timeout=3)) as db, db:
            db.execute("PRAGMA foreign_keys=ON")
            if write:
                db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT body FROM identity WHERE id=1").fetchone()
            if row != (self.identity,):
                raise ValueError("selected archive identity mismatch")
            yield db

    def check_startup(self):
        with self._connection() as db:
            if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise ValueError("selected archive integrity failure")
            if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise ValueError("selected archive lineage failure")

    def _parse(self, batch, original):
        if not isinstance(original, bytes) or not 1 <= len(original) <= MAX_BYTES:
            raise ValueError("selected original exceeds bounds")
        text = original.decode("utf-8")
        _check_depth(text, 16)
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_int=_bounded_integer,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
        self._validate("batch", value)
        if (
            not isinstance(batch, str)
            or not TOKEN.fullmatch(batch)
            or value["scope"] != self.scope
            or value["batch_id"] != batch
        ):
            raise ValueError("selected scope or batch mismatch")
        records = value["records"]
        if len(records) > MAX_RECORDS:
            raise ValueError("selected record count exceeds bound")
        for record in records:
            if any(
                isinstance(item, str) and (not item.isascii() or not item.isprintable())
                for item in record.values()
            ):
                raise ValueError("selected record contains invalid text")
            if (
                record["operation"] == "upsert"
                and record["event_start"] > record["event_end"]
            ):
                raise ValueError("invalid selected event interval")
        return records

    def _rows(self, records):
        for ordinal, record in enumerate(records):
            fact = _fact(self.scope, record)
            processing, _ = _processing(fact, record)
            yield (
                ordinal,
                record["metric"],
                record["native_id"],
                record["operation"],
                fact,
                processing,
            )

    def _conflicts(self, db, rows):
        seen = {}
        for _, metric, native_id, operation, fact, _ in rows:
            key = (metric, native_id, operation)
            if seen.setdefault(key, fact) != fact:
                return True
            if db.execute(
                """SELECT 1 FROM sightings
                   WHERE metric=? AND native_id=? AND operation=? AND fact<>? LIMIT 1""",
                (*key, fact),
            ).fetchone():
                return True
        return False

    def _receipt(self, batch, original, sequence, received, committed, rows, status):
        artifact = _digest(original)
        receipt_id = _pin(
            ["mse.selected-receipt-id/0.1", self.archive_id, self.scope, batch]
        )
        normalized = status == "normalized"
        receipt = {
            "schema_version": "mse.selected-healthkit-receipt/0.1",
            "archive_id": self.archive_id,
            "scope": self.scope,
            "batch_id": batch,
            "artifact_sha256": artifact,
            "byte_length": len(original),
            "receipt_id": receipt_id,
            "mother_received_at": received,
            "committed_at": committed,
            "commit_sequence": sequence,
            "status": status,
            "archive_commit_id": (
                _pin([PROCESSING, receipt_id, sequence, artifact, rows])
                if normalized
                else None
            ),
            "reason_code": None if normalized else "changed_scoped_source_fact",
        }
        self._validate("receipt", receipt)
        return receipt

    def batch_request(self, method, path, *, content_type=None, original=None):
        """Exercise the versioned request seam without opening a listener."""
        route = BATCH_PATH.fullmatch(path)
        if route is None:
            raise ValueError("invalid selected batch path")
        batch = route[1]
        if method == "PUT" and content_type == "application/json":
            receipt = self.put(batch, original)
        elif method == "GET" and content_type is None and original is None:
            receipt = self.get(batch)
        else:
            raise ValueError("invalid selected batch request")
        return canonical_json(receipt).encode("utf-8")

    def put(self, batch, original):
        """Admit exact authorized synthetic bytes, then verify the committed result."""
        if not isinstance(original, bytes) or not 1 <= len(original) <= MAX_BYTES:
            raise ValueError("selected original exceeds bounds")
        if _digest(original) not in self.allowed:
            raise ValueError("selected original is not admitted")
        received = _clock()
        records = self._parse(batch, original)
        rows = list(self._rows(records))
        with self._connection(write=True) as db:
            existing = db.execute(
                "SELECT original FROM batches WHERE batch=?", (batch,)
            ).fetchone()
            if existing is not None:
                if existing[0] != original:
                    raise BatchConflict("selected batch is already bound")
            else:
                status = "quarantined" if self._conflicts(db, rows) else "normalized"
                sequence = db.execute(
                    "SELECT COALESCE(MAX(sequence),0)+1 FROM batches"
                ).fetchone()[0]
                receipt = self._receipt(
                    batch,
                    original,
                    sequence,
                    received,
                    max(received, _clock()),
                    rows,
                    status,
                )
                db.execute(
                    "INSERT INTO batches VALUES (?,?,?,?,?)",
                    (
                        sequence,
                        batch,
                        _digest(original),
                        original,
                        canonical_json(receipt),
                    ),
                )
                if status == "normalized":
                    db.executemany(
                        "INSERT INTO sightings VALUES (?,?,?,?,?,?,?)",
                        [(sequence, *row) for row in rows],
                    )
        return self.get(batch)

    def _read(self, db, batch):
        saved = db.execute(
            "SELECT sequence,artifact,original,receipt FROM batches WHERE batch=?",
            (batch,),
        ).fetchone()
        if saved is None:
            raise KeyError("unknown selected batch")
        sequence, artifact, original, receipt_json = saved
        receipt = json.loads(receipt_json)
        if _digest(original) != artifact:
            raise ValueError("selected original integrity mismatch")
        self._validate("receipt", receipt)
        records = self._parse(batch, original)
        expected = list(self._rows(records))
        saved_rows = db.execute(
            """SELECT ordinal,metric,native_id,operation,fact,processing
               FROM sightings WHERE sequence=? ORDER BY ordinal""",
            (sequence,),
        ).fetchall()
        status = receipt["status"]
        if status not in {"normalized", "quarantined"}:
            raise ValueError("invalid persisted selected batch status")
        if saved_rows != (expected if status == "normalized" else []):
            raise ValueError("selected sighting integrity mismatch")
        if receipt != self._receipt(
            batch,
            original,
            sequence,
            receipt["mother_received_at"],
            receipt["committed_at"],
            expected,
            status,
        ):
            raise ValueError("selected receipt integrity mismatch")
        return receipt, original, records, saved_rows

    def get(self, batch):
        with self._connection() as db:
            return self._read(db, batch)[0]

    def original(self, batch):
        with self._connection() as db:
            return self._read(db, batch)[1]

    def export(self, start, through, *, current=False, event_window=None):
        """Return canonical history or current rows for a bounded commit interval."""
        if (
            type(start) is not int
            or type(through) is not int
            or not 1 <= start <= through <= 2**53 - 1
            or through - start >= MAX_COMMITS_PER_EXPORT
        ):
            raise ValueError("invalid selected export range")
        if event_window is not None:
            if not isinstance(event_window, (tuple, list)) or len(event_window) != 2:
                raise ValueError("invalid selected event window")
            lower, upper = event_window
            self._validate("utc", lower)
            self._validate("utc", upper)
            if lower >= upper:
                raise ValueError("invalid selected event window")
        rows = []
        with self._connection() as db:
            db.execute("BEGIN")
            batches = db.execute(
                "SELECT batch FROM batches WHERE sequence BETWEEN ? AND ? ORDER BY sequence",
                (start, through),
            ).fetchall()
            for (batch,) in batches:
                receipt, _, records, sightings = self._read(db, batch)
                for (
                    ordinal,
                    metric,
                    native_id,
                    operation,
                    fact,
                    processing,
                ) in sightings:
                    if current and (
                        operation == "delete"
                        or db.execute(
                            """SELECT 1 FROM sightings WHERE metric=? AND native_id=?
                               AND sequence<=? AND (operation='delete' OR sequence<?)
                               LIMIT 1""",
                            (metric, native_id, through, receipt["commit_sequence"]),
                        ).fetchone()
                        or any(previous[4] == fact for previous in sightings[:ordinal])
                    ):
                        continue
                    record = records[ordinal]
                    if event_window is not None:
                        if operation == "delete":
                            continue
                        event_start = record["event_start"]
                        event_end = record["event_end"]
                        overlaps = (
                            lower <= event_start < upper
                            if event_start == event_end
                            else event_start < upper and event_end > lower
                        )
                        if not overlaps:
                            continue
                    _, finding = _processing(fact, record)
                    rows.append(
                        {
                            "receipt": receipt,
                            "ordinal": ordinal,
                            "source_fact_sha256": fact,
                            "processing_sha256": processing,
                            "processing_version": PROCESSING,
                            "processing_finding": finding,
                            "record": record,
                        }
                    )
        view = {
            "schema_version": "mse.selected-healthkit-export/0.1",
            "mode": "current" if current else "history",
            "scope": self.scope,
            "from": start,
            "through": through,
            "event_window": event_window,
            "rows": rows,
        }
        result = canonical_json({"view": view, "view_sha256": _pin(view)}).encode()
        if len(result) > MAX_EXPORT_BYTES:
            raise ValueError("selected export exceeds response bound")
        return result
