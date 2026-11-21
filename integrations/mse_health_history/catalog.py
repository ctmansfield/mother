"""Atomic synthetic custody catalog with independently counted BP normalization."""

from contextlib import closing, contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
from tempfile import NamedTemporaryFile
from zipfile import BadZipFile
from zlib import error as DeflateError

from mother.physiology.contracts import canonical_json

from . import bp_page
from .blood_pressure import BloodPressure, protected_ref, source_time
from .files import (
    CHUNK,
    InvalidHistory,
    LimitKind,
    NamedHistoryLimit,
    hash_stream,
    private_path,
)
from .inventory import Limits, scan
from .sealed_page import authenticate_page
from .protected_export import authenticate_export
from .vault import TOKEN

DIGEST = re.compile(r"[a-f0-9]{64}")
DDL = """
CREATE TABLE identity (owner TEXT NOT NULL);
CREATE TABLE artifacts (
    digest TEXT PRIMARY KEY, receipt TEXT NOT NULL
);
CREATE TABLE members (
    digest TEXT NOT NULL REFERENCES artifacts(digest), ordinal INTEGER NOT NULL,
    path TEXT, kind TEXT NOT NULL, member_sha256 TEXT NOT NULL, byte_length INTEGER NOT NULL,
    PRIMARY KEY(digest, ordinal)
);
CREATE TABLE coverage (
    digest TEXT NOT NULL REFERENCES artifacts(digest), family TEXT NOT NULL, source_type TEXT NOT NULL,
    observed INTEGER NOT NULL, typed INTEGER NOT NULL, unnormalized INTEGER NOT NULL,
    first_event TEXT, last_event TEXT,
    PRIMARY KEY(digest, family, source_type)
);
CREATE TABLE bp_revisions (
    revision TEXT PRIMARY KEY, identity TEXT NOT NULL, normalized TEXT NOT NULL
);
CREATE INDEX bp_identity ON bp_revisions(identity);
CREATE TABLE bp_members (
    revision TEXT NOT NULL REFERENCES bp_revisions(revision), native_ref TEXT NOT NULL,
    PRIMARY KEY(revision, native_ref)
);
CREATE TABLE bp_deletions (
    digest TEXT NOT NULL REFERENCES artifacts(digest), native_ref TEXT NOT NULL,
    PRIMARY KEY(digest,native_ref)
);
CREATE INDEX bp_deleted_key ON bp_deletions(native_ref);
CREATE TABLE bp_cursors (
    feed TEXT PRIMARY KEY, through TEXT NOT NULL, cursor_token TEXT NOT NULL,
    exhausted INTEGER NOT NULL CHECK(exhausted IN (0,1))
);
CREATE TABLE bp_cursor_tokens (
    feed TEXT NOT NULL, token TEXT NOT NULL,
    PRIMARY KEY(feed,token)
);
CREATE TABLE sightings (
    digest TEXT NOT NULL, member INTEGER NOT NULL, ordinal INTEGER NOT NULL,
    revision TEXT NOT NULL REFERENCES bp_revisions(revision),
    PRIMARY KEY(digest, member, ordinal),
    FOREIGN KEY(digest, member) REFERENCES members(digest, ordinal) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE native_bp_children (
    digest TEXT NOT NULL, member INTEGER NOT NULL, parent INTEGER NOT NULL,
    slot INTEGER NOT NULL, child INTEGER NOT NULL, role TEXT NOT NULL,
    PRIMARY KEY(digest,member,parent,slot),
    UNIQUE(digest,member,parent,child),
    FOREIGN KEY(digest,member,parent) REFERENCES sightings(digest,member,ordinal)
);
"""


def _clock_or_none(value):
    try:
        return source_time(value)
    except ValueError:
        return None


class _HistoryCatalog:
    """Shared exact custody and typed catalog internals."""

    def __init__(
        self,
        root,
        *,
        enrollment,
        key,
        limits=Limits(),
        archive_id="synthetic-bp-custody",
        bp_cutoff=None,
        source_instance="synthetic-healthkit-store",
    ):
        if any(
            not isinstance(value, str) or not TOKEN.fullmatch(value)
            for value in (enrollment, archive_id, source_instance)
        ):
            raise ValueError("invalid history scope")
        self.root = Path(root).absolute()
        self.objects = self.root / "originals"
        self.db = self.root / "history.sqlite3"
        self.archive_id = archive_id
        self.enrollment = enrollment
        self.source_instance = source_instance
        if bp_cutoff is not None and source_time(bp_cutoff) != bp_cutoff:
            raise ValueError("historical BP cutoff requires canonical UTC")
        self.bp_cutoff = bp_cutoff
        self.bp = BloodPressure(canonical_json([enrollment, source_instance]), key)
        self.owner = protected_ref(
            key,
            "historical-catalog/0.1",
            archive_id,
            enrollment,
            source_instance,
            bp_cutoff,
        )
        self.limits = limits

    def initialize(self):
        private_path(self.root, directory=True)
        if any(self.root.iterdir()):
            raise InvalidHistory("history initialization requires an empty root")
        self.objects.mkdir(mode=0o700)
        descriptor = os.open(self.db, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        with closing(sqlite3.connect(self.db)) as db, db:
            db.executescript("BEGIN IMMEDIATE;\n" + DDL)
            db.execute("INSERT INTO identity VALUES (?)", (self.owner,))

    @contextmanager
    def _connection(self, *, write=False):
        private_path(self.root, directory=True)
        private_path(self.objects, directory=True)
        private_path(self.db, directory=False)
        for suffix in ("-journal", "-wal", "-shm"):
            sidecar = Path(str(self.db) + suffix)
            if os.path.lexists(sidecar):
                private_path(sidecar, directory=False)
        uri = self.db.as_uri() + ("?mode=rw" if write else "?mode=ro")
        with closing(sqlite3.connect(uri, uri=True, timeout=5)) as db, db:
            db.execute("PRAGMA foreign_keys=ON")
            if write:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT owner FROM identity").fetchall() != [(self.owner,)]:
                raise InvalidHistory("history enrollment identity mismatch")
            yield db

    def _stage(self, source, staging):
        hashing = sha256()
        size = 0
        with Path(source).open("rb") as stream:
            while chunk := stream.read(CHUNK):
                size += len(chunk)
                if size > self.limits.archive_bytes:
                    raise InvalidHistory("history byte limit exceeded")
                hashing.update(chunk)
                staging.write(chunk)
        staging.flush()
        os.fsync(staging.fileno())
        return hashing.hexdigest(), size

    def _verify_original(self, body, size):
        if not isinstance(body, str) or not DIGEST.fullmatch(body):
            raise InvalidHistory("invalid history original identity")
        path = self.objects / body
        private_path(path, directory=False)
        with path.open("rb") as stream:
            if hash_stream(stream, self.limits.archive_bytes) != (body, size):
                raise InvalidHistory("history original integrity mismatch")

    def _publish(self, staging, body, size):
        # An object without a committed receipt is an orphan, not accepted
        # custody. An exact retry can use it after verifying its full digest.
        destination = self.objects / body
        if os.path.lexists(destination):
            self._verify_original(body, size)
            return
        # The SQLite write transaction serializes publication within this private directory.
        os.rename(staging, destination)
        descriptor = os.open(self.objects, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def ingest(self, source):
        """Inventory a fabricated exact XML/ZIP original."""
        return self._ingest(source, self._inventory)

    def ingest_bp_page(self, source):
        """Commit a fabricated API page and its cursor digest atomically."""
        return self._ingest(source, self._bp_page)

    def ingest_sealed_bp_page(self, **custodian_inputs):
        """Authenticate exact ciphertext locally, then commit typed page/cursor only."""
        body = custodian_inputs["plaintext_sha256"]
        size = custodian_inputs["plaintext_length"]
        stream, raw = authenticate_page(**custodian_inputs)
        with stream, self._connection(write=True) as db:
            existing = db.execute(
                "SELECT receipt FROM artifacts WHERE digest=?", (body,)
            ).fetchone()
            if existing is not None:
                receipt = json.loads(existing[0])
                if receipt.get("ciphertext_receipt") != raw:
                    raise InvalidHistory(
                        "historical plaintext already bound to different custody"
                    )
                return receipt
            return self._bp_page(db, stream, body, size, raw=raw)

    def ingest_sealed_export(
        self,
        *,
        precommit=None,
        database_bytes=None,
        report_phase=None,
        **custodian_inputs,
    ):
        """Import after authenticated custody, without a local plaintext original copy."""
        body = custodian_inputs["plaintext_sha256"]
        size = custodian_inputs["plaintext_length"]
        sealed_receipt = custodian_inputs["receipt"]
        with self._connection() as db:
            self._require_child_ledger(db)
        if report_phase is not None:
            report_phase("BINDING")
        with authenticate_export(
            limit=self.limits.archive_bytes, **custodian_inputs
        ) as stage:
            if report_phase is not None:
                report_phase("CATALOG")
            with self._connection(write=True) as db:
                if database_bytes is not None:
                    page_size = db.execute("PRAGMA page_size").fetchone()[0]
                    limit_pages = database_bytes // page_size
                    if (
                        db.execute(f"PRAGMA max_page_count={limit_pages}").fetchone()[0]
                        != limit_pages
                    ):
                        raise NamedHistoryLimit(
                            LimitKind.CATALOG_PAGES,
                            "protected catalog page limit unavailable",
                        )
                existing = db.execute(
                    "SELECT receipt FROM artifacts WHERE digest=?", (body,)
                ).fetchone()
                if existing is not None:
                    receipt = json.loads(existing[0])
                    if receipt.get("ciphertext_receipt") != sealed_receipt:
                        raise InvalidHistory(
                            "historical original bound to different custody"
                        )
                    if precommit is not None:
                        precommit()
                    return receipt
                if report_phase is not None:
                    report_phase("ARCHIVE_OR_XML")
                receipt = self._inventory(
                    db, stage, body, size, ciphertext_receipt=sealed_receipt
                )
                if precommit is not None:
                    precommit()
                return receipt

    def _ingest(self, source, operation):
        private_path(self.root, directory=True)
        private_path(self.objects, directory=True)
        with NamedTemporaryFile(
            dir=self.objects, prefix=".pending-", delete=False
        ) as stage:
            try:
                body, size = self._stage(source, stage)
                with self._connection(write=True) as db:
                    existing = db.execute(
                        "SELECT receipt FROM artifacts WHERE digest=?", (body,)
                    ).fetchone()
                    if existing is not None:
                        self._verify_original(body, size)
                        return json.loads(existing[0])
                    receipt = operation(db, stage, body, size)
                    self._publish(stage.name, body, size)
                    return receipt
            finally:
                Path(stage.name).unlink(missing_ok=True)

    def _record_bp(self, db, original, member, ordinal, normalized):
        identity, revision, document = normalized
        db.execute(
            "INSERT OR IGNORE INTO bp_revisions VALUES (?,?,?)",
            (revision, identity, canonical_json(document)),
        )
        db.executemany(
            "INSERT OR IGNORE INTO bp_members VALUES (?,?)",
            [
                (revision, item["native_ref"])
                for item in document["components"]
                if item["native_ref"] is not None
            ],
        )
        db.execute(
            "INSERT INTO sightings VALUES (?,?,?,?)",
            (original, member, ordinal, revision),
        )

    def _bp_page(self, db, stage, body, size, *, raw=None):
        page = bp_page.read_page(stage, self.enrollment, self.source_instance)
        if page["through"] != self.bp_cutoff:
            raise InvalidHistory(
                "historical BP cutoff differs from configured enrollment"
            )
        feed = page["feed"]
        previous = db.execute(
            "SELECT through,cursor_token,exhausted FROM bp_cursors WHERE feed=?",
            (feed,),
        ).fetchone()
        enrolled = db.execute("SELECT through FROM bp_cursors LIMIT 1").fetchone()
        if enrolled is not None and enrolled[0] != page["through"]:
            raise InvalidHistory("historical BP enrollment cutoff changed")
        if previous and previous[2]:
            raise InvalidHistory("historical BP feed already completed")
        if page["cursor_in"] != (previous[1] if previous else None):
            raise InvalidHistory("historical BP checkpoint token mismatch")
        if (page["upserts"] or page["deleted_ids"]) and (
            page["cursor_out"] == page["cursor_in"]
        ):
            raise InvalidHistory("nonempty historical BP page did not advance")
        if page["cursor_out"] != page["cursor_in"]:
            if db.execute(
                "SELECT 1 FROM bp_cursor_tokens WHERE feed=? AND token=?",
                (feed, page["cursor_out"]),
            ).fetchone():
                raise InvalidHistory("historical BP checkpoint token reused")
            db.execute(
                "INSERT INTO bp_cursor_tokens VALUES (?,?)", (feed, page["cursor_out"])
            )
        db.execute("INSERT INTO artifacts VALUES (?,?)", (body, "{}"))
        db.execute(
            "INSERT INTO members VALUES (?,1,NULL,'bp_api_page',?,?)",
            (body, body, size),
        )
        seen = set()
        for ordinal, row in enumerate(page["upserts"], 1):
            normalized = bp_page.normalize(row, feed, page["through"], self.bp)
            if normalized[0] in seen:
                raise InvalidHistory("ambiguous historical BP page key")
            seen.add(normalized[0])
            self._record_bp(db, body, 1, ordinal, normalized)
        deleted = {
            self.bp._native({"uuid": native}, bp_page.FEEDS[feed])
            for native in page["deleted_ids"]
        }
        db.executemany(
            "INSERT INTO bp_deletions VALUES (?,?)",
            [(body, native) for native in sorted(deleted)],
        )
        db.execute(
            """INSERT INTO bp_cursors VALUES (?,?,?,?)
               ON CONFLICT(feed) DO UPDATE SET cursor_token=excluded.cursor_token,
                   exhausted=excluded.exhausted""",
            (feed, page["through"], page["cursor_out"], page["exhausted"]),
        )
        receipt = {
            "schema_version": "mse.historical-bp-page-receipt/0.1",
            "status": "typed_and_cursor_durable",
            "archive_id": self.archive_id,
            "enrollment": self.enrollment,
            "source_instance": self.source_instance,
            "exhausted": page["exhausted"],
            "receipt_id": protected_ref(
                self.bp.key, "history-bp-page", self.owner, body
            ),
            "sha256": body,
            "byte_length": size,
            "protection": (
                "synthetic_unencrypted"
                if raw is None
                else "custodian_verified_ciphertext"
            ),
            "feed": feed,
            "through": page["through"],
            "cursor_in": page["cursor_in"],
            "cursor_out": page["cursor_out"],
            "typed_upserts": len(seen),
            "typed_tombstones": len(deleted),
        }
        if raw is not None:
            receipt["ciphertext_receipt"] = raw
        db.execute(
            "UPDATE artifacts SET receipt=? WHERE digest=?",
            (canonical_json(receipt), body),
        )
        return receipt

    def _inventory(self, db, stage, body, size, *, ciphertext_receipt=None):
        db.execute("INSERT INTO artifacts VALUES (?,?)", (body, "{}"))
        counts = {}
        normalizations = {"paired": 0, "unpaired": 0, "incomplete": 0, "ambiguous": 0}
        nested_unmapped = 0
        nested_counts = {}
        invalid_bp = 0
        files = 0
        attachments = 0
        source_xml = 0

        def member(ordinal, path, kind, digest, size):
            nonlocal files, attachments, source_xml
            files += 1
            attachments += kind == "attachment"
            source_xml += kind == "healthdata_xml"
            db.execute(
                "INSERT INTO members VALUES (?,?,?,?,?,?)",
                (body, ordinal, path, kind, digest, size),
            )

        def nested(family, source_type):
            lookup = (family, source_type)
            if (
                lookup not in nested_counts
                and len(nested_counts) >= self.limits.type_buckets
            ):
                raise NamedHistoryLimit(
                    LimitKind.XML_TYPE_BUCKETS,
                    "HealthData nested type bucket limit exceeded",
                )
            nested_counts[lookup] = nested_counts.get(lookup, 0) + 1

        def row(member_index, ordinal, family, source_type, tag, attrs, children):
            nonlocal nested_unmapped, invalid_bp
            key = (family, source_type or tag)
            if key not in counts and len(counts) >= self.limits.type_buckets:
                raise NamedHistoryLimit(
                    LimitKind.XML_TYPE_BUCKETS, "HealthData type bucket limit exceeded"
                )
            values = counts.setdefault(key, [0, 0, 0, None, None])
            values[0] += 1
            first = _clock_or_none(attrs.get("startDate"))
            last = _clock_or_none(attrs.get("endDate"))
            if first is not None and (values[3] is None or first < values[3]):
                values[3] = first
            if last is not None and (values[4] is None or last > values[4]):
                values[4] = last
            child_sightings = []
            try:
                normalized = self.bp.normalize(
                    tag, attrs, children, (body, member_index, ordinal), child_sightings
                )
            except (ValueError, OverflowError):
                invalid_bp += 1
                normalized = None
            if normalized is None:
                values[2] += 1
                return
            identity, revision, document = normalized
            values[1] += 1
            normalizations[document["pairing"]] += 1
            nested_unmapped += document["unsupported_component_count"]
            self._record_bp(db, body, member_index, ordinal, normalized)
            db.executemany(
                "INSERT INTO native_bp_children VALUES (?,?,?,?,?,?)",
                (
                    (body, member_index, ordinal, slot, child, role)
                    for slot, (child, role) in enumerate(child_sightings, 1)
                ),
            )

        try:
            identity = scan(stage, self.limits, row, member, nested)
        except (BadZipFile, DeflateError, EOFError):
            raise InvalidHistory("invalid HealthData ZIP structure") from None
        if identity != (body, size):
            raise InvalidHistory("history exact original verification failed")
        db.executemany(
            "INSERT INTO coverage VALUES (?,?,?,?,?,?,?,?)",
            [(body, *kind, *values) for kind, values in counts.items()],
        )
        receipt = {
            "schema_version": "mse.historical-original-receipt/0.1",
            "receipt_id": protected_ref(
                self.bp.key, "history-custody", self.owner, body
            ),
            "sha256": body,
            "byte_length": size,
            "protection": "synthetic_unencrypted",
            "members": files,
            "attachment_members_retained_unnormalized": attachments,
            "healthdata_xml_members": source_xml,
            "observed_top_level_rows": sum(values[0] for values in counts.values()),
            "normalized_bp_top_level_rows": sum(normalizations.values()),
            "unnormalized_top_level_rows": sum(values[2] for values in counts.values()),
            "unmapped_bp_children": nested_unmapped,
            "bp_invalid_top_level_rows": invalid_bp,
            "nested_occurrences": [
                {"family": family, "source_type": source_type, "observed": count}
                for (family, source_type), count in sorted(nested_counts.items())
            ],
            "bp_pairing_counts": normalizations,
        }
        if ciphertext_receipt is not None:
            receipt["protection"] = "custodian_verified_ciphertext"
            receipt["ciphertext_receipt"] = ciphertext_receipt
        db.execute(
            "UPDATE artifacts SET receipt=? WHERE digest=?",
            (canonical_json(receipt), body),
        )
        return receipt

    def receipt(self, body):
        with self._connection() as db:
            row = db.execute(
                "SELECT receipt FROM artifacts WHERE digest=?", (body,)
            ).fetchone()
        if row is None:
            raise KeyError("unknown historical original")
        receipt = json.loads(row[0])
        if receipt["protection"] == "synthetic_unencrypted":
            self._verify_original(body, receipt["byte_length"])
        return receipt

    def coverage(self, body):
        self.receipt(body)
        with self._connection() as db:
            keys = (
                "family",
                "source_type",
                "observed",
                "typed",
                "unnormalized",
                "first_event",
                "last_event",
            )
            rows = db.execute(
                """SELECT family,source_type,observed,typed,unnormalized,first_event,last_event
                   FROM coverage WHERE digest=? ORDER BY family,source_type""",
                (body,),
            )
            return [dict(zip(keys, row)) for row in rows]

    def members(self, body):
        self.receipt(body)
        with self._connection() as db:
            keys = ("ordinal", "path", "kind", "sha256", "byte_length")
            rows = db.execute(
                """SELECT ordinal,path,kind,member_sha256,byte_length
                   FROM members WHERE digest=? ORDER BY ordinal""",
                (body,),
            )
            return [dict(zip(keys, row)) for row in rows]

    def blood_pressure_lineage(self, body):
        """Stream original/member/ordinal lineage from the typed destination."""
        self.receipt(body)
        with self._connection() as db:
            for member, ordinal, revision, fact in db.execute(
                """SELECT s.member,s.ordinal,s.revision,r.normalized FROM sightings s
                   JOIN bp_revisions r ON s.revision=r.revision WHERE s.digest=?
                   ORDER BY s.member,s.ordinal""",
                (body,),
            ):
                yield {
                    "original_sha256": body,
                    "member": member,
                    "ordinal": ordinal,
                    "revision": revision,
                    "fact": json.loads(fact),
                }

    @staticmethod
    def _require_child_ledger(db):
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='native_bp_children'"
        ).fetchone():
            raise InvalidHistory(
                "native physical child lineage requires a fresh catalog"
            )

    def blood_pressure_component_lineage(self, body, member, ordinal):
        with self._connection() as db:
            self._require_child_ledger(db)
            return db.execute(
                """SELECT child,role FROM native_bp_children
                   WHERE digest=? AND member=? AND parent=? ORDER BY slot""",
                (body, member, ordinal),
            ).fetchall()

    def blood_pressure(self, *, current=False):
        with self._connection() as db:
            query = "SELECT normalized FROM bp_revisions ORDER BY identity,revision"
            if current:
                # Multiple source revisions without authoritative ordering
                # remain conflicted and do not enter the default view.
                query = """SELECT normalized FROM bp_revisions
                           WHERE identity IN (
                               SELECT identity FROM bp_revisions GROUP BY identity HAVING COUNT(*)=1
                           )
                           AND NOT EXISTS (
                               SELECT 1 FROM bp_deletions d
                               WHERE d.native_ref=bp_revisions.identity
                                  OR d.native_ref IN (
                                      SELECT native_ref FROM bp_members m
                                      WHERE m.revision=bp_revisions.revision
                                  )
                           ) ORDER BY identity,revision"""
            for (body,) in db.execute(query):
                yield json.loads(body)


class SyntheticHistoryCatalog(_HistoryCatalog):
    """Local synthetic source candidate with an independent identity namespace."""

    def __init__(
        self,
        root,
        *,
        enrollment,
        key,
        limits=Limits(),
        archive_id="synthetic-bp-custody",
        bp_cutoff=None,
        source_instance="synthetic-healthkit-store",
    ):
        if any(
            not isinstance(value, str)
            or not re.fullmatch(r"synthetic-[A-Za-z0-9-]{1,100}", value)
            for value in (enrollment, archive_id, source_instance)
        ):
            raise ValueError("synthetic history scope required")
        super().__init__(
            root,
            enrollment=enrollment,
            key=key,
            limits=limits,
            archive_id=archive_id,
            bp_cutoff=bp_cutoff,
            source_instance=source_instance,
        )
