"""Synthetic native BP projection and a separate transactional guest store."""

from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3

from integrations.healthbridge.capture import _unique_object
from mother.physiology.contracts import canonical_json

from .blood_pressure import decimal_text, source_time
from .files import private_path

SCHEMA = "mse.native-bp-projection/0.1"
PURPOSE = "mother-bp-review"
MAX_ROWS = 10_000
MAX_BYTES = 4 * 1024 * 1024
PIN = re.compile(r"[0-9a-f]{64}")
IDENTITY = re.compile(r"synthetic-[a-z0-9-]{1,80}")
ROW_FIELDS = {"member", "ordinal", "revision", "event_end", "systolic", "diastolic"}


class Conflict(ValueError):
    pass


def encoded(value):
    return canonical_json(value).encode("utf-8")


def project(catalog, original_sha256):
    """Run on the custodian Mac after successful authenticated local import."""
    receipt = catalog.receipt(original_sha256)
    if receipt["schema_version"] != "mse.historical-original-receipt/0.1" or (
        receipt["protection"] != "custodian_verified_ciphertext"
    ):
        raise ValueError("authenticated native original required")
    rows = []
    for lineage in catalog.blood_pressure_lineage(original_sha256):
        fact = lineage["fact"]
        if fact["pairing"] != "paired":
            continue
        if len(rows) == MAX_ROWS:
            raise ValueError("native projection row limit")
        values = {part["role"]: part["value"] for part in fact["components"]}
        rows.append(
            {
                "member": lineage["member"],
                "ordinal": lineage["ordinal"],
                "revision": lineage["revision"],
                "event_end": fact["clocks"]["event_end"],
                "systolic": values["systolic"],
                "diastolic": values["diastolic"],
            }
        )
    raw = encoded(
        {
            "schema": SCHEMA,
            "purpose": PURPOSE,
            "enrollment": catalog.enrollment,
            "source_instance": catalog.source_instance,
            "artifact_receipt": receipt["receipt_id"],
            "rows": rows,
        }
    )
    validate(raw, catalog.enrollment, catalog.source_instance, receipt["receipt_id"])
    return raw


def validate(raw, enrollment, source_instance, artifact_receipt):
    if not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("native projection byte limit")
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object)
    except RecursionError:
        raise ValueError("native projection nesting limit") from None
    expected = {
        "schema": SCHEMA,
        "purpose": PURPOSE,
        "enrollment": enrollment,
        "source_instance": source_instance,
        "artifact_receipt": artifact_receipt,
    }
    if (
        not isinstance(value, dict)
        or set(value) != {*expected, "rows"}
        or any(value[k] != v for k, v in expected.items())
        or not isinstance(value["rows"], list)
        or len(value["rows"]) > MAX_ROWS
    ):
        raise ValueError("native projection contract mismatch")
    previous = (0, 0)
    for row in value["rows"]:
        if not isinstance(row, dict) or set(row) != ROW_FIELDS:
            raise ValueError("native BP fields mismatch")
        member, ordinal = row["member"], row["ordinal"]
        if (
            type(member) is not int
            or type(ordinal) is not int
            or not 1 <= member <= 1_000_000
            or not 1 <= ordinal <= 100_000_000
            or (member, ordinal) <= previous
            or not isinstance(row["revision"], str)
            or not PIN.fullmatch(row["revision"])
            or source_time(row["event_end"]) != row["event_end"]
            or any(
                decimal_text(row[key]) != row[key] for key in ("systolic", "diastolic")
            )
        ):
            raise ValueError("native BP row mismatch")
        previous = (member, ordinal)
    if encoded(value) != raw:
        raise ValueError("native projection must be canonical")
    return value["rows"]


class TypedStore:
    def __init__(self, path, enrollment, source_instance, artifact_receipt):
        if (
            not IDENTITY.fullmatch(enrollment)
            or not IDENTITY.fullmatch(source_instance)
            or not PIN.fullmatch(artifact_receipt)
        ):
            raise ValueError("invalid synthetic guest scope")
        self.path = Path(path).absolute()
        private_path(self.path.parent, directory=True)
        self.scope = (enrollment, source_instance, artifact_receipt)
        self.identity = encoded([SCHEMA, PURPOSE, *self.scope])

    def initialize(self):
        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        try:
            with closing(sqlite3.connect(self.path)) as db, db:
                db.executescript(
                    """
                    BEGIN IMMEDIATE;
                    CREATE TABLE identity (body BLOB NOT NULL);
                    CREATE TABLE receipt (
                        slot INTEGER PRIMARY KEY CHECK(slot=1), digest TEXT, body BLOB
                    );
                    CREATE TABLE bp (
                        member INTEGER, ordinal INTEGER, revision TEXT, event_end TEXT,
                        systolic TEXT, diastolic TEXT, PRIMARY KEY(member,ordinal)
                    );
                    CREATE INDEX bp_event ON bp(event_end,member,ordinal);
                    """
                )
                db.execute("INSERT INTO identity VALUES (?)", (self.identity,))
        except BaseException:
            self.path.unlink(missing_ok=True)
            raise

    def connect(self, *, write=False):
        private_path(self.path, directory=False)
        mode = "rw" if write else "ro"
        db = sqlite3.connect(f"{self.path.as_uri()}?mode={mode}", uri=True)
        try:
            if db.execute("SELECT body FROM identity").fetchall() != [(self.identity,)]:
                raise ValueError("guest store scope mismatch")
            if write:
                db.execute("PRAGMA synchronous=FULL")
        except BaseException:
            db.close()
            raise
        return db

    def ingest(self, raw, writable):
        rows = validate(raw, *self.scope)
        digest = sha256(raw).hexdigest()
        with closing(self.connect(write=True)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            writable()
            existing = db.execute("SELECT digest,body FROM receipt").fetchone()
            if existing:
                if existing[0] != digest:
                    raise Conflict(
                        "native projection conflicts with committed artifact"
                    )
                return 200, existing[1]
            db.executemany(
                "INSERT INTO bp VALUES (:member,:ordinal,:revision,:event_end,:systolic,:diastolic)",
                rows,
            )
            record = {
                "schema": SCHEMA,
                "purpose": PURPOSE,
                "enrollment": self.scope[0],
                "source_instance": self.scope[1],
                "artifact_receipt": self.scope[2],
                "projection_sha256": digest,
                "bytes": len(raw),
                "bp_pairs": len(rows),
            }
            body = encoded(dict(record, receipt_id=sha256(encoded(record)).hexdigest()))
            db.execute("INSERT INTO receipt VALUES (1,?,?)", (digest, body))
            writable()
        return 201, body

    def receipt(self):
        with closing(self.connect()) as db:
            row = db.execute("SELECT body FROM receipt").fetchone()
        if row is None:
            raise KeyError("projection absent")
        return row[0]

    def read(self, start, end):
        if source_time(start) != start or source_time(end) != end or start >= end:
            raise ValueError("invalid snapshot bounds")
        with closing(self.connect()) as db:
            db.execute("BEGIN")
            receipt = db.execute("SELECT body FROM receipt").fetchone()
            if receipt is None:
                raise KeyError("projection absent")
            rows = db.execute(
                """SELECT event_end,systolic,diastolic FROM bp
                   WHERE event_end>=? AND event_end<? ORDER BY event_end,member,ordinal""",
                (start, end),
            )
            return encoded(
                {
                    "purpose": PURPOSE,
                    "receipt_id": json.loads(receipt[0])["receipt_id"],
                    "start": start,
                    "end": end,
                    "rows": [
                        dict(event_end=at, systolic=sys, diastolic=dia, unit="mmHg")
                        for at, sys, dia in rows
                    ],
                }
            )
