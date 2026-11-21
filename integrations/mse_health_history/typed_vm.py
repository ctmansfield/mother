"""ATLAS r2 synthetic native BP batch projection and protected guest store."""

from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3

from integrations.healthbridge.capture import _unique_object
from mother.physiology.contracts import canonical_json

from .blood_pressure import decimal_text, protected_ref, source_time
from .files import private_path
from .projection import _bucket

BATCH = "mse.native-bp-typed-batch/0.1"
MANIFEST = "mse.native-bp-typed-manifest/0.1"
RECEIPT = "mse.native-bp-typed-receipt/0.1"
NORMALIZER = "native-bp-0_1"
PROJECTION_REVISION = "native-bp-purpose-0_1"
PURPOSES = {"mother-bp-review", "coach-bp-review"}
MAX_BYTES = 1024**2
MAX_OPS = 128
MAX_ROWS = 10_000
PIN = re.compile(r"[0-9a-f]{64}")
REF = re.compile(r"[A-Za-z0-9_-]{1,96}")
SYNTHETIC = re.compile(r"synthetic-[a-z0-9-]{1,80}")
SCOPE = (
    "store_id",
    "enrollment_id",
    "source_namespace_ref",
    "import_ref",
    "normalization_version",
)
ENVELOPE = {
    "schema_version",
    *SCOPE,
    "batch_seq",
    "prev_batch_sha256",
    "final",
    "ops",
    "manifest",
}
MANIFEST_FIELDS = {
    "schema_version",
    "artifact_receipt_ref",
    "member_inventory_ref",
    "event_start_inclusive",
    "event_end_exclusive",
    "nonterminal_batches",
    "nonterminal_bytes",
    "last_nonterminal_sha256",
    "upsert_count",
    "delete_count",
    "source_occurrence_count",
    "quarantined_count",
    "normalizer_version",
}
UPSERT = {
    "op",
    "occurrence_ref",
    "logical_ref",
    "revision_ref",
    "kind",
    "pairing",
    "event_start",
    "event_end",
    "components",
}
COMPONENT = {
    "component_occurrence_ref",
    "component_ref",
    "role",
    "value_mmhg",
    "event_start",
    "event_end",
}


class Conflict(ValueError):
    pass


class Capacity(ValueError):
    pass


class ScopeDenied(ValueError):
    pass


class Indeterminate(OSError):
    pass


def encoded(value):
    # Wire fields admit ASCII strings, booleans, null and bounded integers.
    # Canonical JSON and RFC 8785 are identical for this subset.
    return canonical_json(value).encode("utf-8")


def digest(raw):
    return sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def is_ref(value):
    return isinstance(value, str) and REF.fullmatch(value) is not None


def is_count(value):
    return type(value) is int and 0 <= value <= 2**32


def valid_clock(value):
    return source_time(value) == value


def valid_interval(start, end, lower, upper):
    return valid_clock(start) and valid_clock(end) and lower <= start <= end < upper


def validate_op(op, bounds):
    require(
        isinstance(op, dict) and is_ref(op.get("occurrence_ref")), "invalid op identity"
    )
    if op.get("op") == "delete":
        require(
            set(op) == {"op", "occurrence_ref", "target_kind", "target_ref"}
            and op["target_kind"] in ("correlation", "component")
            and is_ref(op["target_ref"]),
            "invalid tombstone",
        )
        return
    require(
        set(op) == UPSERT
        and op["op"] == "upsert"
        and is_ref(op["logical_ref"])
        and is_ref(op["revision_ref"])
        and valid_interval(op["event_start"], op["event_end"], *bounds)
        and isinstance(op["components"], list)
        and len(op["components"]) <= 16,
        "invalid BP upsert",
    )
    for component in op["components"]:
        require(
            isinstance(component, dict)
            and set(component) == COMPONENT
            and is_ref(component["component_occurrence_ref"])
            and is_ref(component["component_ref"])
            and component["role"] in ("systolic", "diastolic")
            and valid_interval(
                component["event_start"], component["event_end"], *bounds
            )
            and (
                component["value_mmhg"] is None
                or decimal_text(component["value_mmhg"]) == component["value_mmhg"]
            ),
            "invalid BP component",
        )
    components = op["components"]
    require(
        len({c["component_occurrence_ref"] for c in components}) == len(components),
        "duplicate child occurrence",
    )
    if op["kind"] == "standalone":
        require(
            op["pairing"] == "unpaired" and len(components) == 1,
            "invalid standalone BP",
        )
    else:
        require(
            op["kind"] == "correlation"
            and op["pairing"] in ("paired", "incomplete", "ambiguous"),
            "invalid correlation",
        )
        roles = {c["role"] for c in components}
        if op["pairing"] == "paired":
            require(
                len(components) == 2
                and len(roles) == 2
                and len({c["component_ref"] for c in components}) == 2
                and all(c["value_mmhg"] is not None for c in components),
                "contradictory pairing",
            )
        if op["pairing"] == "incomplete":
            require(len(components) < 2, "contradictory incomplete correlation")


def parse_batch(raw, scope, bounds, seq):
    if not 0 < len(raw) <= MAX_BYTES:
        raise Capacity("native batch byte cap")
    try:
        batch = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except RecursionError:
        raise ValueError("native batch nesting") from None
    require(
        isinstance(batch, dict)
        and set(batch) == ENVELOPE
        and batch["schema_version"] == BATCH
        and all(batch[k] == scope[k] for k in SCOPE)
        and type(batch["batch_seq"]) is int
        and batch["batch_seq"] == seq
        and type(batch["final"]) is bool
        and isinstance(batch["ops"], list),
        "native batch identity mismatch",
    )
    previous = batch["prev_batch_sha256"]
    require(
        (
            previous is None
            if seq == 1
            else isinstance(previous, str) and PIN.fullmatch(previous)
        ),
        "invalid native predecessor",
    )
    if len(batch["ops"]) > MAX_OPS:
        raise Capacity("native batch op cap")
    manifest = batch["manifest"]
    if batch["final"]:
        require(
            not batch["ops"]
            and isinstance(manifest, dict)
            and set(manifest) == MANIFEST_FIELDS,
            "invalid terminal batch",
        )
        require(
            manifest["schema_version"] == MANIFEST
            and manifest["normalizer_version"] == scope["normalization_version"]
            and is_ref(manifest["artifact_receipt_ref"])
            and is_ref(manifest["member_inventory_ref"])
            and (manifest["event_start_inclusive"], manifest["event_end_exclusive"])
            == bounds
            and manifest["last_nonterminal_sha256"] == previous
            and all(
                is_count(manifest[k])
                for k in (
                    "nonterminal_batches",
                    "nonterminal_bytes",
                    "upsert_count",
                    "delete_count",
                    "source_occurrence_count",
                    "quarantined_count",
                )
            ),
            "terminal manifest scope or count format",
        )
    else:
        require(batch["ops"] and manifest is None, "invalid nonterminal batch")
        for op in batch["ops"]:
            validate_op(op, bounds)
    require(encoded(batch) == raw, "native batch must use canonical bytes")
    return batch


def build_batches(
    scope, bounds, ops, *, artifact_ref, inventory_ref, observed, quarantined
):
    """Yield immutable canonical batch bytes and an explicit terminal manifest."""
    previous = None
    sent = upserts = deletes = seq = 0
    pending = []

    def make(items, manifest=None):
        return encoded(
            {
                "schema_version": BATCH,
                **scope,
                "batch_seq": seq,
                "prev_batch_sha256": previous,
                "final": manifest is not None,
                "ops": items,
                "manifest": manifest,
            }
        )

    def groups():
        for op in ops:
            pending.append(op)
            if len(pending) == MAX_OPS:
                yield list(pending)
                pending.clear()
        if pending:
            yield pending

    for items in groups():
        seq += 1
        raw = make(items)
        parse_batch(raw, scope, bounds, seq)
        yield raw
        previous = digest(raw)
        sent += len(raw)
        upserts += sum(op["op"] == "upsert" for op in items)
        deletes += sum(op["op"] == "delete" for op in items)
    seq += 1
    terminal = make(
        [],
        {
            "schema_version": MANIFEST,
            "artifact_receipt_ref": artifact_ref,
            "member_inventory_ref": inventory_ref,
            "event_start_inclusive": bounds[0],
            "event_end_exclusive": bounds[1],
            "nonterminal_batches": seq - 1,
            "nonterminal_bytes": sent,
            "last_nonterminal_sha256": previous,
            "upsert_count": upserts,
            "delete_count": deletes,
            "source_occurrence_count": observed,
            "quarantined_count": quarantined,
            "normalizer_version": scope["normalization_version"],
        },
    )
    parse_batch(terminal, scope, bounds, seq)
    yield terminal


def project(
    catalog, original_sha256, scope, bounds, *, mapping_key, record_accounting=None
):
    """Project only authenticated native sightings, keeping locator mappings off-guest."""
    require(
        isinstance(mapping_key, bytes) and len(mapping_key) == 32,
        "private mapping key required",
    )
    require(
        len(bounds) == 2 and all(map(valid_clock, bounds)) and bounds[0] < bounds[1],
        "invalid native projection interval",
    )
    receipt = catalog.receipt(original_sha256)
    require(
        receipt["schema_version"] == "mse.historical-original-receipt/0.1"
        and receipt["protection"] == "custodian_verified_ciphertext"
        and scope["enrollment_id"] == catalog.enrollment
        and scope["source_namespace_ref"]
        == protected_ref(
            mapping_key, "native-namespace", catalog.enrollment, catalog.source_instance
        ),
        "authenticated native origin scope required",
    )

    quarantined = receipt["bp_invalid_top_level_rows"]

    def ref(domain, *parts):
        return protected_ref(
            mapping_key, domain, scope["source_namespace_ref"], original_sha256, *parts
        )

    def ops():
        snapshot_excluded = 0
        emitted = 0
        for lineage in catalog.blood_pressure_lineage(original_sha256):
            fact = lineage["fact"]
            if any(
                not valid_interval(
                    sample["clocks"]["event_start"],
                    sample["clocks"]["event_end"],
                    *bounds,
                )
                for sample in (fact, *fact["components"])
            ):
                snapshot_excluded += 1
                continue
            emitted += 1
            occurrence = ref(
                "native-occurrence",
                original_sha256,
                lineage["member"],
                lineage["ordinal"],
            )
            components = []
            physical = catalog.blood_pressure_component_lineage(
                original_sha256, lineage["member"], lineage["ordinal"]
            )
            if fact["pairing"] == "unpaired":
                physical = [(None, fact["components"][0]["role"])]
            require(
                len(physical) == len(fact["components"]),
                "native child lineage unavailable",
            )
            for part, (child, role) in zip(fact["components"], physical):
                require(part["role"] == role, "native child lineage role mismatch")
                occurrence_child = ref("native-component-occurrence", occurrence, child)
                components.append(
                    {
                        "component_occurrence_ref": occurrence_child,
                        "component_ref": ref(
                            "native-component", part["native_ref"] or occurrence_child
                        ),
                        "role": part["role"],
                        "value_mmhg": part["value"],
                        "event_start": part["clocks"]["event_start"],
                        "event_end": part["clocks"]["event_end"],
                    }
                )
            yield {
                "op": "upsert",
                "occurrence_ref": occurrence,
                "logical_ref": ref("native-logical", fact["identity"]),
                "revision_ref": ref("native-revision", lineage["revision"]),
                "kind": (
                    "standalone" if fact["pairing"] == "unpaired" else "correlation"
                ),
                "pairing": fact["pairing"],
                "event_start": fact["clocks"]["event_start"],
                "event_end": fact["clocks"]["event_end"],
                "components": components,
            }

        normalized = receipt["normalized_bp_top_level_rows"]
        unnormalized = receipt["unnormalized_top_level_rows"]
        observed = receipt["observed_top_level_rows"]
        require(
            emitted + snapshot_excluded == normalized
            and normalized + unnormalized == observed
            and 0 <= quarantined <= unnormalized,
            "native projection does not reconcile to source inventory",
        )
        if record_accounting is not None:
            record_accounting(
                {
                    "source_occurrence_count": observed,
                    "normalized_bp_count": normalized,
                    "unnormalized_count": unnormalized,
                    "parser_quarantined_bp_count": quarantined,
                    "snapshot_excluded_count": snapshot_excluded,
                    "emitted_upsert_count": emitted,
                }
            )

    return build_batches(
        scope,
        bounds,
        ops(),
        artifact_ref=ref("native-artifact", receipt["receipt_id"]),
        inventory_ref=ref(
            "native-inventory", receipt["receipt_id"], catalog.members(original_sha256)
        ),
        observed=receipt["observed_top_level_rows"],
        quarantined=quarantined,
    )


class _TypedStore:
    def __init__(
        self,
        path,
        scope,
        bounds,
        artifact,
        inventory,
        *,
        max_batches,
        max_bytes,
        admitted_deletions=(),
        admission_pin=None,
        database_bytes=None,
    ):
        require(
            set(scope) == set(SCOPE)
            and all(is_ref(scope[k]) for k in SCOPE)
            and scope["normalization_version"] == NORMALIZER
            and is_ref(artifact)
            and is_ref(inventory)
            and len(bounds) == 2
            and all(map(valid_clock, bounds))
            and bounds[0] < bounds[1]
            and is_count(max_batches)
            and 1 <= max_batches <= 1024
            and is_count(max_bytes)
            and 1 <= max_bytes <= 512 * MAX_BYTES,
            "invalid guest scope or quota",
        )
        require(
            all(
                kind in ("correlation", "component") and is_ref(ref)
                for kind, ref in admitted_deletions
            ),
            "invalid tombstone admission",
        )
        self.path = Path(path).absolute()
        private_path(self.path.parent, directory=True)
        self.scope, self.bounds = dict(scope), tuple(bounds)
        self.artifact, self.inventory = artifact, inventory
        self.max_batches, self.max_bytes = max_batches, max_bytes
        self.database_bytes = database_bytes
        self.admitted_deletions = frozenset(map(tuple, admitted_deletions))
        self.identity = encoded(
            [
                "native-bp-store-witness/0.1",
                BATCH,
                scope,
                bounds,
                artifact,
                inventory,
                max_batches,
                max_bytes,
                sorted(self.admitted_deletions),
                *([admission_pin, database_bytes] if admission_pin is not None else []),
            ]
        )

    def _bound_pages(self, db):
        if self.database_bytes is not None:
            size = db.execute("PRAGMA page_size").fetchone()[0]
            pages = self.database_bytes // size
            if db.execute(f"PRAGMA max_page_count={pages}").fetchone()[0] != pages:
                raise Capacity("admitted guest catalog page cap unavailable")

    def initialize(self):
        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        try:
            with closing(sqlite3.connect(self.path)) as db, db:
                self._bound_pages(db)
                db.executescript(
                    """
                    BEGIN IMMEDIATE;
                    CREATE TABLE identity (body BLOB NOT NULL);
                    CREATE TABLE batches (
                        seq INTEGER PRIMARY KEY, digest TEXT, size INTEGER, receipt BLOB,
                        final INTEGER, upserts INTEGER, deletes INTEGER, observed_at TEXT
                    );
                    CREATE TABLE ops (
                        occurrence TEXT PRIMARY KEY, op TEXT, logical TEXT, revision TEXT, body BLOB
                    );
                    CREATE TABLE revisions (id TEXT PRIMARY KEY, content BLOB);
                """
                )
                db.execute("INSERT INTO identity VALUES (?)", (self.identity,))
        except BaseException:
            self.path.unlink(missing_ok=True)
            raise

    def connect(self, *, write=False):
        private_path(self.path, directory=False)
        for suffix in ("-journal", "-wal", "-shm"):
            path = Path(str(self.path) + suffix)
            if os.path.lexists(path):
                private_path(path, directory=False)
        mode = "rw" if write else "ro"
        db = sqlite3.connect(f"{self.path.as_uri()}?mode={mode}", uri=True)
        try:
            if db.execute("SELECT body FROM identity").fetchall() != [(self.identity,)]:
                raise ValueError("guest scope unavailable")
            if write:
                db.execute("PRAGMA synchronous=FULL")
                self._bound_pages(db)
        except BaseException:
            db.close()
            raise
        return db

    def record_op(self, db, op):
        raw = encoded(op)
        known = db.execute(
            "SELECT body FROM ops WHERE occurrence=?", (op["occurrence_ref"],)
        ).fetchone()
        if known is not None:
            if known[0] != raw:
                raise Conflict("occurrence content conflict")
            return
        if op["op"] == "delete":
            if (op["target_kind"], op["target_ref"]) not in self.admitted_deletions:
                raise ScopeDenied("tombstone outside admission")
        else:
            revision = {
                k: v for k, v in op.items() if k not in {"occurrence_ref", "components"}
            }
            revision["components"] = [
                {k: v for k, v in c.items() if k != "component_occurrence_ref"}
                for c in op["components"]
            ]
            content = encoded(revision)
            db.execute(
                "INSERT OR IGNORE INTO revisions VALUES (?,?)",
                (op["revision_ref"], content),
            )
            if (
                db.execute(
                    "SELECT content FROM revisions WHERE id=?", (op["revision_ref"],)
                ).fetchone()[0]
                != content
            ):
                raise Conflict("revision content conflict")
        db.execute(
            "INSERT INTO ops VALUES (?,?,?,?,?)",
            (
                op["occurrence_ref"],
                op["op"],
                op.get("logical_ref"),
                op.get("revision_ref"),
                raw,
            ),
        )

    def ingest(self, seq, raw, writable):
        require(type(seq) is int and seq > 0, "invalid batch sequence")
        if seq > self.max_batches or len(raw) > MAX_BYTES:
            raise Capacity("guest batch quota")
        pin = digest(raw)
        with closing(self.connect(write=True)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            writable()
            accepted = db.execute(
                "SELECT digest,receipt,observed_at FROM batches WHERE seq=?", (seq,)
            ).fetchone()
            if accepted is not None:
                if accepted[0] != pin:
                    raise Conflict("batch identity conflict")
                if accepted[2] is None:
                    raise Indeterminate("guest batch has no durability witness")
                return 200, accepted[1]
            if db.execute("SELECT 1 FROM batches WHERE observed_at IS NULL").fetchone():
                raise Indeterminate("guest store has an unwitnessed batch")
            batch = parse_batch(raw, self.scope, self.bounds, seq)
            last = db.execute(
                "SELECT seq,digest,final FROM batches ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            if (
                seq != (last[0] + 1 if last else 1)
                or batch["prev_batch_sha256"] != (last[1] if last else None)
                or (last and last[2])
            ):
                raise Conflict("batch sequence or predecessor conflict")
            size, upserts, deletes = db.execute(
                "SELECT coalesce(sum(size),0),coalesce(sum(upserts),0),coalesce(sum(deletes),0) FROM batches"
            ).fetchone()
            if size + len(raw) > self.max_bytes:
                raise Capacity("guest aggregate byte quota")
            manifest = batch["manifest"]
            if manifest is not None:
                expected = {
                    "artifact_receipt_ref": self.artifact,
                    "member_inventory_ref": self.inventory,
                    "nonterminal_batches": seq - 1,
                    "nonterminal_bytes": size,
                    "upsert_count": upserts,
                    "delete_count": deletes,
                }
                if any(manifest[k] != v for k, v in expected.items()):
                    raise Conflict("terminal manifest disagrees with accepted batches")
            for op in batch["ops"]:
                self.record_op(db, op)
            total_upserts = sum(op["op"] == "upsert" for op in batch["ops"])
            total_deletes = len(batch["ops"]) - total_upserts
            body = batch_receipt(batch, raw, total_upserts, total_deletes)
            db.execute(
                "INSERT INTO batches VALUES (?,?,?,?,?,?,?,NULL)",
                (
                    seq,
                    pin,
                    len(raw),
                    body,
                    batch["final"],
                    total_upserts,
                    total_deletes,
                ),
            )
            writable()
        try:
            # This observation comes after the FULL-synchronous staging commit.
            observed = writable()
            if not valid_clock(observed):
                raise ValueError("invalid durability observation")
        except ValueError as error:
            raise Indeterminate(
                "guest commit lacks an in-lease durability observation"
            ) from error
        with closing(self.connect(write=True)) as db, db:
            updated = db.execute(
                """UPDATE batches SET observed_at=?
                   WHERE seq=? AND digest=? AND observed_at IS NULL""",
                (observed, seq, pin),
            )
            if updated.rowcount != 1:
                raise Indeterminate("guest durability witness cannot be recorded")
        if self.receipt(seq) != body:
            raise Indeterminate("committed batch receipt readback mismatch")
        return 201, body

    def receipt(self, seq):
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT receipt,observed_at FROM batches WHERE seq=?", (seq,)
            ).fetchone()
        if row is None:
            raise KeyError("guest batch absent")
        if row[1] is None:
            raise Indeterminate("guest batch has no durability witness")
        return row[0]

    def snapshot(self, descriptor):
        with closing(self.connect()) as db:
            db.execute("BEGIN")
            terminal = db.execute(
                "SELECT receipt,observed_at FROM batches WHERE final=1"
            ).fetchone()
            if (
                terminal is None
                or json.loads(terminal[0])["receipt_id"]
                != descriptor["terminal_receipt"]
            ):
                raise KeyError("snapshot terminal unavailable")
            if terminal[1] is None:
                raise Indeterminate("guest terminal has no durability witness")
            deletions = {
                (value["target_kind"], value["target_ref"])
                for (raw,) in db.execute("SELECT body FROM ops WHERE op='delete'")
                for value in (json.loads(raw),)
            }
            rows = []
            facts = db.execute(
                """
                SELECT r.content FROM revisions r JOIN (
                    SELECT logical, min(revision) revision FROM ops WHERE op='upsert'
                    GROUP BY logical HAVING count(DISTINCT revision)=1
                ) f ON r.id=f.revision
            """
            )
            for (raw,) in facts:
                fact = json.loads(raw)
                when = fact["event_end"]
                if (
                    fact["pairing"] != "paired"
                    or not descriptor["start"] <= when < descriptor["end"]
                    or ("correlation", fact["logical_ref"]) in deletions
                    or any(
                        ("component", c["component_ref"]) in deletions
                        for c in fact["components"]
                    )
                ):
                    continue
                values = {c["role"]: c["value_mmhg"] for c in fact["components"]}
                rows.append({"bucket": _bucket(when), **values})
                if len(rows) > descriptor["max_rows"]:
                    raise Capacity("snapshot row cap")
        body = encoded(
            {
                "schema_version": "mse.native-bp-purpose-snapshot/0.1",
                "snapshot_id": descriptor["snapshot_id"],
                "purpose": descriptor["purpose"],
                "projection_revision": PROJECTION_REVISION,
                "subject": descriptor["subject"],
                "count": len(rows),
                "rows": sorted(rows, key=lambda row: (row["bucket"], encoded(row))),
            }
        )
        if len(body) > descriptor["max_bytes"]:
            raise Capacity("snapshot byte cap")
        return body


class TypedStore(_TypedStore):
    """The existing synthetic-only entry point."""

    def __init__(
        self,
        path,
        scope,
        bounds,
        artifact,
        inventory,
        *,
        max_batches,
        max_bytes,
        admitted_deletions=(),
    ):
        require(
            isinstance(scope.get("enrollment_id"), str)
            and SYNTHETIC.fullmatch(scope["enrollment_id"]),
            "synthetic guest enrollment required",
        )
        super().__init__(
            path,
            scope,
            bounds,
            artifact,
            inventory,
            max_batches=max_batches,
            max_bytes=max_bytes,
            admitted_deletions=admitted_deletions,
        )


def batch_receipt(batch, raw, upserts, deletes):
    manifest = batch["manifest"]
    record = {
        "schema_version": RECEIPT,
        "status": "typed_batch_durable",
        **{k: batch[k] for k in SCOPE},
        "batch_seq": batch["batch_seq"],
        "batch_sha256": digest(raw),
        "byte_length": len(raw),
        "prev_batch_sha256": batch["prev_batch_sha256"],
        "final": batch["final"],
        "upsert_count": upserts,
        "delete_count": deletes,
        "manifest_sha256": digest(encoded(manifest)) if manifest is not None else None,
    }
    return encoded(dict(record, receipt_id=digest(encoded(record))))
