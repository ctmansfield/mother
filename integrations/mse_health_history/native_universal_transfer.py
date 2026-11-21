"""Deterministic protected native catalog transfer and witnessed acceptance.

This module provides the transfer/store primitives. Admission, encrypted
mount checks, and authenticated network roles are supplied by a separately
reviewed operator entry point.
"""

from base64 import b64decode, b64encode
from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3

from integrations.healthbridge.capture import _unique_object

from . import native_source
from .catalog import DDL as CATALOG_DDL
from .files import InvalidHistory, private_path
from .typed_vm import (
    Capacity,
    Conflict,
    Indeterminate,
    PIN,
    encoded,
    is_ref,
    require,
    valid_clock,
)

SCHEMA = "mse.native-health-universal-transfer/0.1"
PART_BYTES = 512 * 1024
MAX_LINE = 2 * 1024**2
MAX_WIRE = 16 * 1024**3

# Column order is fixed by the pinned storage schema. Names are never supplied
# by a query caller or interpolated from the wire.
TABLES = {
    "artifacts": (2, "digest", "digest"),
    "members": (6, "digest", "ordinal"),
    "native_source_occurrences": (8, "artifact", "member,ordinal"),
    "native_source_elements": (9, "artifact", "member,element"),
    "native_source_events": (8, "artifact", "member,seq"),
    "native_source_refs": (6, "artifact", "member,element"),
    "native_source_chunks": (2, None, "sha256"),
    "native_source_member_chunks": (4, "artifact", "member,seq"),
}


def _lines(db, artifact):
    for table, (_, key, order) in TABLES.items():
        if key is None:
            rows = db.execute(
                """SELECT sha256,payload FROM native_source_chunks WHERE sha256 IN (
                    SELECT sha256 FROM native_source_member_chunks WHERE artifact=?
                ) ORDER BY sha256""",
                (artifact,),
            )
        else:
            rows = db.execute(
                f"SELECT * FROM {table} WHERE {key}=? ORDER BY {order}", (artifact,)
            )
        for row in rows:
            data = list(row)
            if key is None:
                data[1] = b64encode(data[1]).decode("ascii")
            raw = encoded([table, data]) + b"\n"
            if len(raw) > MAX_LINE:
                raise Capacity("native universal frame exceeds bound")
            yield raw


def export_catalog(catalog, artifact, stream, *, import_ref, max_bytes=MAX_WIRE):
    """Write canonical framed records to an already-open protected spool."""
    require(
        is_ref(import_ref) and type(max_bytes) is int and 1 <= max_bytes <= MAX_WIRE,
        "invalid universal import reference or quota",
    )
    receipt = catalog.receipt(artifact)
    require(
        receipt["protection"] == "custodian_verified_ciphertext"
        and receipt["source_inventory"]["schema_version"] == native_source.SCHEMA,
        "authenticated universal catalog required",
    )
    hashing = sha256()
    length = 0
    with catalog._connection() as db:
        db.execute("BEGIN")
        for line in _lines(db, artifact):
            length += len(line)
            if length > max_bytes:
                raise Capacity("native universal spool exceeds bound")
            stream.write(line)
            hashing.update(line)
    return {
        "schema_version": SCHEMA,
        "import_ref": import_ref,
        "artifact": artifact,
        "source_receipt": receipt["receipt_id"],
        "inventory": receipt["source_inventory"],
        "wire_bytes": length,
        "wire_sha256": hashing.hexdigest(),
        "part_bytes": PART_BYTES,
        "parts": (length + PART_BYTES - 1) // PART_BYTES,
    }


class UniversalStore:
    def __init__(
        self,
        path,
        manifest,
        *,
        trusted_manifest_sha256,
        starts,
        ends,
        clock,
        database_bytes,
        policy_sha256=None,
        admission_check=None,
    ):
        require(
            set(manifest)
            == {
                "schema_version",
                "import_ref",
                "artifact",
                "source_receipt",
                "inventory",
                "wire_bytes",
                "wire_sha256",
                "part_bytes",
                "parts",
            }
            and manifest["schema_version"] == SCHEMA
            and is_ref(manifest["import_ref"])
            and PIN.fullmatch(manifest["artifact"])
            and PIN.fullmatch(manifest["source_receipt"])
            and PIN.fullmatch(manifest["wire_sha256"])
            and type(manifest["wire_bytes"]) is int
            and 0 < manifest["wire_bytes"] <= MAX_WIRE
            and manifest["part_bytes"] == PART_BYTES
            and manifest["parts"]
            == (manifest["wire_bytes"] + PART_BYTES - 1) // PART_BYTES
            and sha256(encoded(manifest)).hexdigest() == trusted_manifest_sha256
            and valid_clock(starts)
            and valid_clock(ends)
            and starts < ends
            and type(database_bytes) is int
            and manifest["wire_bytes"] <= database_bytes <= 32 * 1024**3,
            "universal store admission mismatch",
        )
        self.path = Path(path).absolute()
        private_path(self.path.parent, directory=True)
        self.manifest = json.loads(encoded(manifest))
        self.pin = trusted_manifest_sha256
        self.identity = encoded([self.pin, starts, ends, database_bytes, policy_sha256])
        self.starts, self.ends, self.clock, self.database_bytes = (
            starts,
            ends,
            clock,
            database_bytes,
        )
        self.admission_check = admission_check

    def writable(self):
        if self.admission_check is not None:
            self.admission_check()
        observed = self.clock()
        if not valid_clock(observed) or not self.starts <= observed < self.ends:
            raise PermissionError("native universal lease closed")
        return observed

    def _cap(self, db):
        size = db.execute("PRAGMA page_size").fetchone()[0]
        cap = self.database_bytes // size
        if db.execute(f"PRAGMA max_page_count={cap}").fetchone()[0] != cap:
            raise Capacity("native universal database cap unavailable")

    def initialize(self):
        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        try:
            with closing(sqlite3.connect(self.path)) as db, db:
                self._cap(db)
                db.executescript(
                    "BEGIN IMMEDIATE;\n"
                    + CATALOG_DDL
                    + native_source.DDL
                    + """
                    CREATE TABLE universal_parts (
                        seq INTEGER PRIMARY KEY, digest TEXT NOT NULL, payload BLOB NOT NULL
                    );
                    CREATE TABLE universal_publication (
                        slot INTEGER PRIMARY KEY CHECK(slot=1), receipt BLOB NOT NULL, witness TEXT
                    );
                """
                )
                db.execute("INSERT INTO identity VALUES (?)", (self.identity,))
        except BaseException:
            self.path.unlink(missing_ok=True)
            raise

    def connect(self, *, write=False):
        private_path(self.path, directory=False)
        for suffix in ("-journal", "-wal", "-shm"):
            sidecar = Path(str(self.path) + suffix)
            if os.path.lexists(sidecar):
                private_path(sidecar, directory=False)
        db = sqlite3.connect(
            self.path.as_uri() + ("?mode=rw" if write else "?mode=ro"), uri=True
        )
        try:
            require(
                db.execute("SELECT owner FROM identity").fetchall()
                == [(self.identity,)],
                "universal store scope mismatch",
            )
            db.execute("PRAGMA foreign_keys=ON")
            if write:
                db.execute("PRAGMA synchronous=FULL")
                self._cap(db)
        except BaseException:
            db.close()
            raise
        return db

    def put(self, seq, raw, *, predecessor, digest):
        self.writable()
        if type(seq) is not int or not 1 <= seq <= self.manifest["parts"]:
            raise ValueError("invalid universal part sequence")
        expected = min(PART_BYTES, self.manifest["wire_bytes"] - (seq - 1) * PART_BYTES)
        require(
            type(raw) is bytes
            and len(raw) == expected
            and sha256(raw).hexdigest() == digest,
            "universal part byte binding",
        )
        with closing(self.connect(write=True)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self.writable()
            prior = db.execute(
                "SELECT digest FROM universal_parts WHERE seq=?", (seq - 1,)
            ).fetchone()
            if predecessor != (prior[0] if prior else None) or (
                seq > 1 and prior is None
            ):
                raise Conflict("universal predecessor mismatch")
            old = db.execute(
                "SELECT digest FROM universal_parts WHERE seq=?", (seq,)
            ).fetchone()
            if old is not None:
                if old[0] != digest:
                    raise Conflict("universal part conflict")
                return 200
            if db.execute("SELECT 1 FROM universal_publication").fetchone():
                raise Conflict("universal import is closed")
            db.execute("INSERT INTO universal_parts VALUES (?,?,?)", (seq, digest, raw))
            self.writable()
        return 201

    def _ingest_frames(self, db):
        pending = b""
        hashing = sha256()
        length = 0
        count = 0
        for seq, pin, part in db.execute(
            "SELECT seq,digest,payload FROM universal_parts ORDER BY seq"
        ):
            count += 1
            if seq != count or sha256(part).hexdigest() != pin:
                raise InvalidHistory("universal staged part mismatch")
            hashing.update(part)
            length += len(part)
            frames = (pending + part).split(b"\n")
            pending = frames.pop()
            if len(pending) > MAX_LINE:
                raise Capacity("native universal frame exceeds bound")
            for raw in frames:
                self._ingest_frame(db, raw)
        if (
            pending
            or count != self.manifest["parts"]
            or length != self.manifest["wire_bytes"]
            or hashing.hexdigest() != self.manifest["wire_sha256"]
        ):
            raise Conflict("universal wire manifest mismatch")

    def _ingest_frame(self, db, raw):
        if not raw or len(raw) > MAX_LINE:
            raise Capacity("native universal frame exceeds bound")
        try:
            value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        except RecursionError:
            raise InvalidHistory("native universal frame depth") from None
        require(
            isinstance(value, list) and len(value) == 2 and encoded(value) == raw,
            "invalid universal frame",
        )
        table, row = value
        require(
            isinstance(table, str) and table in TABLES and isinstance(row, list),
            "invalid universal frame table",
        )
        columns, key, _ = TABLES[table]
        require(len(row) == columns, "invalid universal frame column count")
        if key is None:
            require(
                isinstance(row[1], str) and isinstance(row[0], str),
                "invalid universal chunk fields",
            )
            row[1] = b64decode(row[1], validate=True)
            require(
                0 < len(row[1]) <= native_source.CHUNK
                and sha256(row[1]).hexdigest() == row[0],
                "invalid universal chunk bytes",
            )
        else:
            require(
                row[0] == self.manifest["artifact"],
                "invalid universal artifact binding",
            )
        db.execute(f"INSERT INTO {table} VALUES ({','.join('?' for _ in row)})", row)

    def _reconcile(self, db):
        artifact = self.manifest["artifact"]
        stored = db.execute(
            "SELECT receipt FROM artifacts WHERE digest=?", (artifact,)
        ).fetchone()
        require(stored is not None, "universal source receipt absent")
        receipt = json.loads(stored[0])
        inventory = self.manifest["inventory"]
        require(
            receipt["protection"] == "custodian_verified_ciphertext"
            and receipt["receipt_id"] == self.manifest["source_receipt"]
            and receipt["source_inventory"] == inventory,
            "universal source receipt mismatch",
        )
        observed, typed, fallback, quarantine = db.execute(
            """SELECT count(*),coalesce(sum(adapter NOT IN ('fallback','quarantine')),0),
                      coalesce(sum(adapter='fallback'),0),coalesce(sum(adapter='quarantine'),0)
               FROM native_source_occurrences WHERE artifact=?""",
            (artifact,),
        ).fetchone()
        require(
            (observed, typed, fallback, quarantine)
            == (
                inventory["source_occurrences"],
                inventory["typed_occurrences"],
                inventory["fallback_occurrences"],
                inventory["quarantined_occurrences"],
            ),
            "universal occurrence reconciliation mismatch",
        )
        member_count, member_bytes = db.execute(
            "SELECT count(*),coalesce(sum(byte_length),0) FROM members WHERE digest=?",
            (artifact,),
        ).fetchone()
        chunk_count = db.execute(
            "SELECT count(*) FROM native_source_member_chunks WHERE artifact=?",
            (artifact,),
        ).fetchone()[0]
        elements = db.execute(
            "SELECT count(*) FROM native_source_elements WHERE artifact=?",
            (artifact,),
        ).fetchone()[0]
        require(
            member_count == receipt["members"]
            and member_bytes == inventory["member_payload_bytes"]
            and chunk_count == inventory["member_chunk_count"]
            and elements == inventory["xml_element_count"],
            "universal member or element totals mismatch",
        )
        require(
            db.execute(
                """SELECT 1 FROM native_source_chunks c WHERE NOT EXISTS (
                       SELECT 1 FROM native_source_member_chunks m WHERE m.sha256=c.sha256
                   ) LIMIT 1"""
            ).fetchone()
            is None,
            "universal chunk is missing its member link",
        )
        writer = native_source.SourceWriter(db, artifact)
        writer.verify_members()
        events = sha256()
        count = 0
        for event in db.execute(
            """SELECT member,seq,occurrence,element,depth,kind,data FROM native_source_events
               WHERE artifact=? ORDER BY member,seq""",
            (artifact,),
        ):
            events.update(encoded(event) + b"\n")
            count += 1
        require(
            count == inventory["ordered_events"]
            and events.hexdigest() == inventory["event_sha256"],
            "universal event reconciliation mismatch",
        )
        require(
            db.execute("PRAGMA foreign_key_check").fetchone() is None,
            "universal source linkage mismatch",
        )

    def finish(self):
        self.writable()
        with closing(self.connect(write=True)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self.writable()
            previous = db.execute(
                "SELECT receipt,witness FROM universal_publication"
            ).fetchone()
            if previous is not None:
                if previous[1] is None:
                    raise Indeterminate("native universal terminal lacks witness")
                return 200, previous[0]
            if (
                db.execute("SELECT count(*) FROM universal_parts").fetchone()[0]
                != self.manifest["parts"]
            ):
                raise Conflict("native universal terminal missing parts")
            self._ingest_frames(db)
            self._reconcile(db)
            record = {
                "schema_version": SCHEMA,
                "status": "witnessed",
                "manifest_sha256": self.pin,
                "import_ref": self.manifest["import_ref"],
            }
            receipt = encoded(
                dict(record, receipt_id=sha256(encoded(record)).hexdigest())
            )
            db.execute(
                "INSERT INTO universal_publication VALUES (1,?,NULL)", (receipt,)
            )
            self.writable()
        try:
            observed = self.writable()
        except PermissionError as error:
            raise Indeterminate(
                "native universal terminal lacks in-window observation"
            ) from error
        with closing(self.connect(write=True)) as db, db:
            db.execute(
                "UPDATE universal_publication SET witness=? WHERE slot=1 AND witness IS NULL",
                (observed,),
            )
        return 201, self.receipt()

    def receipt(self):
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT receipt,witness FROM universal_publication"
            ).fetchone()
        if row is None:
            raise KeyError("native universal receipt absent")
        if row[1] is None:
            raise Indeterminate("native universal terminal lacks witness")
        return row[0]

    def restricted_occurrences(self, **page):
        self.receipt()
        with closing(self.connect()) as db:
            return native_source.occurrences(db, self.manifest["artifact"], **page)

    def restricted_member_range(self, member, expected, offset, length):
        self.receipt()
        with closing(self.connect()) as db:
            return native_source.member_range(
                db, self.manifest["artifact"], member, expected, offset, length
            )

    def restricted_events(self, member, occurrence, **page):
        self.receipt()
        with closing(self.connect()) as db:
            return native_source.events(
                db, self.manifest["artifact"], member, occurrence, **page
            )

    def restricted_elements(self, member, **page):
        self.receipt()
        with closing(self.connect()) as db:
            return native_source.elements(db, self.manifest["artifact"], member, **page)

    def accepted_manifest(self):
        self.receipt()
        return json.loads(encoded(self.manifest))

    def restricted_members(self, *, after=0, limit=64):
        self.receipt()
        with closing(self.connect()) as db:
            return native_source.members(
                db, self.manifest["artifact"], after=after, limit=limit
            )
