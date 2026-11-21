"""Bounded, protected exact members and ordered source occurrences."""

from collections import Counter
from hashlib import sha256
import json
from datetime import date

from mother.physiology.contracts import canonical_json

from .blood_pressure import decimal_text, source_time
from .files import CHUNK, InvalidHistory
from .inventory import Limits, _kind

SCHEMA = "mse.native-health-universal/0.1"
DDL = """
CREATE TABLE native_source_occurrences (
    artifact TEXT NOT NULL, member INTEGER NOT NULL, ordinal INTEGER NOT NULL,
    family TEXT NOT NULL, source_type TEXT NOT NULL, tag TEXT NOT NULL,
    adapter TEXT NOT NULL, typed TEXT NOT NULL,
    PRIMARY KEY(artifact,member,ordinal),
    FOREIGN KEY(artifact,member) REFERENCES members(digest,ordinal) DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX native_occurrences_family ON native_source_occurrences(artifact,family,member,ordinal);
CREATE TABLE native_source_elements (
    artifact TEXT NOT NULL, member INTEGER NOT NULL, element INTEGER NOT NULL,
    occurrence INTEGER NOT NULL, parent INTEGER, child_position INTEGER NOT NULL,
    qualified_name TEXT NOT NULL, namespace TEXT, attributes TEXT NOT NULL,
    PRIMARY KEY(artifact,member,element),
    FOREIGN KEY(artifact,member) REFERENCES members(digest,ordinal) DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX native_source_elements_parent ON native_source_elements(artifact,member,parent,child_position);
CREATE TABLE native_source_refs (
    artifact TEXT NOT NULL, member INTEGER NOT NULL, element INTEGER NOT NULL,
    target TEXT NOT NULL, status TEXT NOT NULL, target_member INTEGER,
    PRIMARY KEY(artifact,member,element),
    FOREIGN KEY(artifact,member,element) REFERENCES native_source_elements(artifact,member,element)
);
CREATE TABLE native_source_events (
    artifact TEXT NOT NULL, member INTEGER NOT NULL, seq INTEGER NOT NULL,
    occurrence INTEGER NOT NULL, element INTEGER, depth INTEGER NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL,
    PRIMARY KEY(artifact,member,seq),
    FOREIGN KEY(artifact,member) REFERENCES members(digest,ordinal) DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX native_events_occurrence ON native_source_events(artifact,member,occurrence,seq);
CREATE TABLE native_source_chunks (
    sha256 TEXT PRIMARY KEY, payload BLOB NOT NULL
);
CREATE TABLE native_source_member_chunks (
    artifact TEXT NOT NULL, member INTEGER NOT NULL, seq INTEGER NOT NULL,
    sha256 TEXT NOT NULL REFERENCES native_source_chunks(sha256),
    PRIMARY KEY(artifact,member,seq),
    FOREIGN KEY(artifact,member) REFERENCES members(digest,ordinal) DEFERRABLE INITIALLY DEFERRED
);
"""
MAX_PAGE_ROWS = 256
MAX_PAGE_BYTES = 1024**2
MAX_EVENTS = 180_000_000
LEVEL_SQL = """CASE WHEN adapter IN ('fallback','quarantine') THEN adapter
               WHEN adapter='explicit_correlation' OR substr(adapter,-11)='_descriptor'
               THEN 'descriptor' ELSE 'typed' END"""

TAGS = {
    "Workout": "workout",
    "ActivitySummary": "activity",
    "Me": "characteristics",
    "Correlation": "correlation",
    "HeartbeatSeries": "series",
    "WorkoutRoute": "route",
    "Electrocardiogram": "ecg",
    "ClinicalRecord": "clinical",
    "MedicationRecord": "medication",
    "Medication": "medication",
    "VisionPrescription": "vision",
    "Audiogram": "audiogram",
    "ExportDate": "export_metadata",
}


def adapt(family, source_type, tag, attrs):
    """Type only qualified primitives. Family dispatch alone is not normalization."""
    clocks = {}
    for name in ("startDate", "endDate", "creationDate", "date"):
        if name in attrs:
            try:
                clocks[name] = {"source": attrs[name], "utc": source_time(attrs[name])}
            except ValueError:
                clocks[name] = {"source": attrs[name], "utc": None}
    base = {"clocks": clocks}
    if family == "auxiliary_xml":
        return "fallback", base
    if any(clock["utc"] is None for clock in clocks.values()):
        return "quarantine", dict(base, reason="invalid_source_clock")
    if "startDate" in clocks and "endDate" in clocks:
        if clocks["endDate"]["utc"] < clocks["startDate"]["utc"]:
            return "quarantine", dict(base, reason="reversed_source_interval")

    if family == "quantity" and tag == "Record":
        try:
            value = decimal_text(attrs.get("value"))
        except ValueError:
            return "quarantine", dict(base, reason="invalid_quantity_decimal")
        if not attrs.get("unit"):
            return "quarantine", dict(base, reason="missing_quantity_unit")
        return "quantity", dict(
            base, value=value, source_value=attrs["value"], source_unit=attrs["unit"]
        )

    if family == "category" and tag == "Record" and attrs.get("value"):
        adapter = (
            "sleep_state"
            if source_type == "HKCategoryTypeIdentifierSleepAnalysis"
            else "category"
        )
        return adapter, dict(base, source_state=attrs["value"])

    if tag == "ActivitySummary" and "dateComponents" in attrs:
        try:
            local_date = date.fromisoformat(attrs["dateComponents"]).isoformat()
            if local_date != attrs["dateComponents"]:
                raise ValueError("invalid HealthData calendar date")
        except ValueError:
            return "quarantine", dict(base, reason="invalid_activity_date")
        return "activity_date", dict(
            base, local_date=local_date, source_date=attrs["dateComponents"]
        )

    if tag == "Workout" and attrs.get("workoutActivityType"):
        typed = dict(base, source_activity=attrs["workoutActivityType"])
        if "duration" in attrs and attrs.get("durationUnit"):
            try:
                typed["duration"] = decimal_text(attrs["duration"])
            except ValueError:
                return "quarantine", dict(base, reason="invalid_workout_duration")
            typed.update(
                source_duration=attrs["duration"],
                source_duration_unit=attrs["durationUnit"],
            )
        return "workout", typed

    if tag == "Correlation" and source_type:
        return "explicit_correlation", dict(base, source_type=source_type)

    if tag == "Me":
        known = {
            key: attrs[key]
            for key in (
                "HKCharacteristicTypeIdentifierDateOfBirth",
                "HKCharacteristicTypeIdentifierBiologicalSex",
                "HKCharacteristicTypeIdentifierBloodType",
                "HKCharacteristicTypeIdentifierFitzpatrickSkinType",
                "HKCharacteristicTypeIdentifierWheelchairUse",
                "HKCharacteristicTypeIdentifierActivityMoveMode",
            )
            if key in attrs
        }
        if known:
            return "characteristics", dict(base, source_codes=known)

    # These are descriptor adapters only. They do not decode signal arrays,
    # route geometry, documents, dose schedules, or unsupported fields.
    descriptor_fields = {
        "HeartbeatSeries": ("count",),
        "WorkoutRoute": ("sourceName",),
        "Electrocardiogram": ("classification", "symptomsStatus"),
        "ClinicalRecord": ("type",),
        "MedicationRecord": ("type",),
        "Medication": ("type",),
        "VisionPrescription": ("type",),
        "Audiogram": ("type",),
    }
    supported = descriptor_fields.get(tag, ())
    fields = {name: attrs[name] for name in supported if attrs.get(name)}
    if fields or (supported and clocks):
        return TAGS[tag] + "_descriptor", dict(base, source_fields=fields)
    # A descriptor with qualified clocks is not a decoded ECG, attachment,
    # clinical statement, dose, or characteristic value.
    if tag in TAGS or family == "clinical":
        return "fallback", dict(base, recognized_family=TAGS.get(tag, family))
    return "fallback", base


def reference_disposition(db, artifact, target):
    blocked = (
        target.startswith("/")
        or ":" in target
        or chr(92) in target
        or any(part in ("", ".", "..") for part in target.split("/"))
    )
    if blocked:
        return "blocked", None
    link = db.execute(
        "SELECT ordinal FROM members WHERE digest=? AND path=? AND kind!='directory'",
        (artifact, target),
    ).fetchone()
    return ("resolved", link[0]) if link is not None else ("unresolved", None)


def verify_structure(db, artifact):
    """Derive reachability and source denominators from the ordered parser events."""
    rows = db.execute(
        """SELECT e.member,e.seq,e.occurrence,e.element,e.depth,e.kind,e.data,m.kind
           FROM native_source_events e JOIN members m ON m.digest=e.artifact AND m.ordinal=e.member
           WHERE e.artifact=? ORDER BY e.member,e.seq""",
        (artifact,),
    )
    elements = iter(
        db.execute(
            """SELECT member,element,occurrence,parent,child_position,qualified_name,namespace,attributes
           FROM native_source_elements WHERE artifact=? ORDER BY member,element""",
            (artifact,),
        )
    )
    refs = iter(
        db.execute(
            """SELECT member,element,target,status,target_member FROM native_source_refs
           WHERE artifact=? ORDER BY member,element""",
            (artifact,),
        )
    )
    top = iter(
        db.execute(
            """SELECT member,ordinal,family,source_type,tag FROM native_source_occurrences
           WHERE artifact=? ORDER BY member,ordinal""",
            (artifact,),
        )
    )
    stack = []
    nested = Counter()
    seen_member = ordinal = sequence = elem = event_count = element_count = 0
    hashing = sha256()
    for member, seq, occurrence, owner, depth, kind, data, member_kind in rows:
        if member != seen_member:
            if stack:
                raise InvalidHistory("unclosed source element stack")
            seen_member, ordinal, sequence, elem = member, 0, 0, 0
        sequence += 1
        event_count += 1
        parent = stack[-1][0] if stack else None
        if (
            seq != sequence
            or owner != parent
            or member_kind not in ("healthdata_xml", "source_xml")
        ):
            raise InvalidHistory("native source event ownership mismatch")
        hashing.update(
            canonical_json((member, seq, occurrence, owner, depth, kind, data)).encode()
            + b"\n"
        )
        if kind == "start":
            if depth != len(stack) + 1:
                raise InvalidHistory("native source event depth mismatch")
            elem += 1
            element_count += 1
            event_element, tag, attrs = json.loads(data)
            if event_element != elem:
                raise InvalidHistory("native source element ordering mismatch")
            attr_map = dict(attrs)
            source_type = attr_map.get("type", "")
            family = (
                "auxiliary_xml"
                if member_kind == "source_xml"
                else _kind(tag, source_type)
            )
            namespaces = (
                dict(stack[-1][2])
                if stack
                else {"xml": "http://www.w3.org/XML/1998/namespace"}
            )
            for key, value in attrs:
                if key == "xmlns":
                    namespaces[""] = value
                elif key.startswith("xmlns:"):
                    namespaces[key[6:]] = value
            prefix = tag.split(":", 1)[0] if ":" in tag else ""
            position = 1
            if stack:
                stack[-1][1] += 1
                position = stack[-1][1]
            if depth == 2:
                ordinal += 1
                if next(top, None) != (
                    member,
                    ordinal,
                    family,
                    source_type or tag,
                    tag,
                ):
                    raise InvalidHistory(
                        "native parsed top-level occurrence missing or rebound"
                    )
            elif depth > 2:
                nested[(family, source_type or tag)] += 1
                if len(nested) > Limits().type_buckets:
                    raise InvalidHistory("native nested source type quota exceeded")
            owned = ordinal if depth >= 2 else 0
            if occurrence != owned or next(elements, None) != (
                member,
                elem,
                owned,
                parent,
                position,
                tag,
                namespaces.get(prefix) or None,
                canonical_json(attrs),
            ):
                raise InvalidHistory("native parsed element missing or rebound")
            if tag.rsplit(":", 1)[-1] == "FileReference" and "path" in attr_map:
                target = attr_map["path"]
                if next(refs, None) != (
                    member,
                    elem,
                    target,
                    *reference_disposition(db, artifact, target),
                ):
                    raise InvalidHistory("native parsed reference missing or rebound")
            stack.append([elem, 0, namespaces, tag])
        else:
            if depth != len(stack) or occurrence != (ordinal if depth >= 2 else 0):
                raise InvalidHistory("native source content ownership mismatch")
            if kind == "end":
                if not stack or json.loads(data) != stack[-1][3]:
                    raise InvalidHistory("native source element close mismatch")
                stack.pop()
    if stack or any(next(rows, None) is not None for rows in (top, elements, refs)):
        raise InvalidHistory("native source contains unowned indexed content")
    return {
        "ordered_events": event_count,
        "event_sha256": hashing.hexdigest(),
        "xml_element_count": element_count,
        "nested_source_classes": [
            {"family": family, "source_type": kind, "observed": count}
            for (family, kind), count in sorted(nested.items())
        ],
    }


class SourceWriter:
    def __init__(self, db, artifact):
        self.db, self.artifact = db, artifact
        self.event_member = self.chunk_member = 0
        self.event_seq = self.chunk_seq = 0
        self.events = self.bytes = self.typed = self.partial = self.fallback = (
            self.quarantine
        ) = 0
        self.event_hash = sha256()
        self.element_seq = 0
        self.stack = []

    def event(self, member, occurrence, depth, kind, data):
        self.events += 1
        if self.events > MAX_EVENTS:
            raise InvalidHistory("native source event cap exceeded")
        if member != self.event_member:
            self.event_member, self.event_seq, self.element_seq = member, 0, 0
        owner = self.stack[-1][0] if self.stack else None
        if kind == "start":
            self.element_seq += 1
            tag, attrs = data
            namespaces = (
                dict(self.stack[-1][2])
                if self.stack
                else {"xml": "http://www.w3.org/XML/1998/namespace"}
            )
            for key, value in attrs:
                if key == "xmlns":
                    namespaces[""] = value
                elif key.startswith("xmlns:"):
                    namespaces[key[6:]] = value
            prefix = tag.split(":", 1)[0] if ":" in tag else ""
            position = 1
            if self.stack:
                self.stack[-1][1] += 1
                position = self.stack[-1][1]
            self.db.execute(
                "INSERT INTO native_source_elements VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    self.artifact,
                    member,
                    self.element_seq,
                    occurrence,
                    owner,
                    position,
                    tag,
                    namespaces.get(prefix) or None,
                    canonical_json(attrs),
                ),
            )
            if tag.rsplit(":", 1)[-1] == "FileReference":
                target = dict(attrs).get("path")
                if target is not None:
                    forbidden = (
                        target.startswith("/")
                        or ":" in target
                        or "\\" in target
                        or any(part in ("", ".", "..") for part in target.split("/"))
                    )
                    self.db.execute(
                        "INSERT INTO native_source_refs VALUES (?,?,?,?,?,NULL)",
                        (
                            self.artifact,
                            member,
                            self.element_seq,
                            target,
                            "blocked" if forbidden else "unresolved",
                        ),
                    )
            data = [self.element_seq, tag, attrs]
            self.stack.append([self.element_seq, 0, namespaces])
        self.event_seq += 1
        value = canonical_json(data)
        row = (
            self.artifact,
            member,
            self.event_seq,
            occurrence,
            owner,
            depth,
            kind,
            value,
        )
        self.db.execute(
            "INSERT INTO native_source_events VALUES (?,?,?,?,?,?,?,?)", row
        )
        self.event_hash.update(canonical_json(row[1:]).encode() + b"\n")
        if kind == "end":
            self.stack.pop()

    def chunk(self, member, raw):
        if member != self.chunk_member:
            self.chunk_member, self.chunk_seq = member, -1
        self.chunk_seq += 1
        pin = sha256(raw).hexdigest()
        self.db.execute(
            "INSERT OR IGNORE INTO native_source_chunks VALUES (?,?)", (pin, raw)
        )
        if self.db.execute(
            "SELECT payload FROM native_source_chunks WHERE sha256=?", (pin,)
        ).fetchone() != (raw,):
            raise InvalidHistory("native source content digest mismatch")
        self.db.execute(
            "INSERT INTO native_source_member_chunks VALUES (?,?,?,?)",
            (self.artifact, member, self.chunk_seq, pin),
        )
        self.bytes += len(raw)

    def occurrence(
        self,
        member,
        ordinal,
        family,
        source_type,
        tag,
        attrs,
        bp=None,
        bp_reason=None,
    ):
        if bp_reason is not None:
            adapter, value = "quarantine", {"reason": bp_reason}
        elif bp is None:
            adapter, value = adapt(family, source_type, tag, attrs)
        else:
            adapter, value = "blood_pressure", bp
        if adapter == "quarantine":
            self.quarantine += 1
        elif adapter == "fallback":
            self.fallback += 1
        elif adapter.endswith("_descriptor") or adapter == "explicit_correlation":
            self.partial += 1
        else:
            self.typed += 1
        self.db.execute(
            "INSERT INTO native_source_occurrences VALUES (?,?,?,?,?,?,?,?)",
            (
                self.artifact,
                member,
                ordinal,
                family,
                source_type or tag,
                tag,
                adapter,
                canonical_json(value),
            ),
        )

    def resolve_references(self):
        self.db.execute(
            """UPDATE native_source_refs AS r
               SET status='resolved', target_member=(
                   SELECT ordinal FROM members WHERE digest=r.artifact AND path=r.target AND kind!='directory'
               )
               WHERE r.artifact=? AND r.status='unresolved' AND EXISTS (
                   SELECT 1 FROM members WHERE digest=r.artifact AND path=r.target AND kind!='directory'
               )""",
            (self.artifact,),
        )

    def verify_members(self):
        for member, kind, expected, size in self.db.execute(
            "SELECT ordinal,kind,member_sha256,byte_length FROM members WHERE digest=?",
            (self.artifact,),
        ):
            total = count = 0
            hashing = sha256()
            for seq, pin, raw in self.db.execute(
                """SELECT m.seq,m.sha256,c.payload FROM native_source_member_chunks m
                   JOIN native_source_chunks c ON c.sha256=m.sha256
                   WHERE m.artifact=? AND m.member=? ORDER BY m.seq""",
                (self.artifact, member),
            ):
                if (
                    seq != count
                    or len(raw) != min(CHUNK, size - total)
                    or sha256(raw).hexdigest() != pin
                ):
                    raise InvalidHistory("native member chunk reconciliation mismatch")
                total += len(raw)
                count += 1
                hashing.update(raw)
            if (
                (kind == "directory" and count)
                or total != size
                or hashing.hexdigest() != expected
            ):
                raise InvalidHistory(
                    "native exact member payload reconciliation mismatch"
                )

    def reconciliation(self, observed, member_bytes):
        if (
            self.typed + self.partial + self.fallback + self.quarantine != observed
            or self.bytes != member_bytes
        ):
            raise InvalidHistory("native source inventory reconciliation failed")
        self.resolve_references()
        self.verify_members()
        structure = verify_structure(self.db, self.artifact)
        if (
            structure["event_sha256"] != self.event_hash.hexdigest()
            or structure["ordered_events"] != self.events
        ):
            raise InvalidHistory("native source events do not reconcile with parser")
        return {
            "schema_version": SCHEMA,
            "source_occurrences": observed,
            "typed_occurrences": self.typed,
            "descriptor_occurrences": self.partial,
            "fallback_occurrences": self.fallback,
            "quarantined_occurrences": self.quarantine,
            **structure,
            "member_payload_bytes": self.bytes,
            "member_chunk_bytes_max": CHUNK,
            "member_chunk_count": self.db.execute(
                "SELECT count(*) FROM native_source_member_chunks WHERE artifact=?",
                (self.artifact,),
            ).fetchone()[0],
        }


def _bounded(rows, limit, keys):
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE_ROWS:
        raise ValueError("native source page outside bound")
    page, size = [], 0
    for row in rows:
        item = dict(zip(keys, row))
        encoded_size = len(canonical_json(item).encode()) + 1
        if len(page) == limit or size + encoded_size > MAX_PAGE_BYTES:
            if not page:
                raise ValueError("native source row exceeds read bound")
            break
        page.append(item)
        size += encoded_size
    return page


def occurrences(db, artifact, *, after=(0, 0), family=None, limit=64):
    rows = db.execute(
        f"""SELECT member,ordinal,family,source_type,tag,adapter,{LEVEL_SQL},typed
           FROM native_source_occurrences
           WHERE artifact=? AND (member,ordinal)>(?,?) AND (? IS NULL OR family=?)
           ORDER BY member,ordinal LIMIT ?""",
        (artifact, *after, family, family, MAX_PAGE_ROWS + 1),
    )
    return _bounded(
        rows,
        limit,
        (
            "member",
            "ordinal",
            "family",
            "source_type",
            "tag",
            "adapter",
            "level",
            "typed_json",
        ),
    )


def events(db, artifact, member, occurrence, *, after=0, limit=64):
    rows = db.execute(
        """SELECT seq,element,depth,kind,data FROM native_source_events
           WHERE artifact=? AND member=? AND occurrence=? AND seq>?
           ORDER BY seq LIMIT ?""",
        (artifact, member, occurrence, after, MAX_PAGE_ROWS + 1),
    )
    return _bounded(rows, limit, ("seq", "element", "depth", "kind", "data_json"))


def member_payload(db, artifact, member, *, after=-1, limit=4):
    if type(limit) is not int or not 1 <= limit <= 17:
        raise ValueError("native member chunk page outside bound")
    rows = db.execute(
        """SELECT m.seq,m.sha256,c.payload FROM native_source_member_chunks m
           JOIN native_source_chunks c ON c.sha256=m.sha256
           WHERE m.artifact=? AND m.member=? AND m.seq>? ORDER BY m.seq LIMIT ?""",
        (artifact, member, after, limit),
    )
    for seq, pin, raw in rows:
        if sha256(raw).hexdigest() != pin:
            raise InvalidHistory("native member chunk integrity mismatch")
        yield seq, pin, raw


def elements(db, artifact, member, *, after=0, limit=64):
    rows = db.execute(
        """SELECT element,occurrence,parent,child_position,qualified_name,namespace,attributes
           FROM native_source_elements WHERE artifact=? AND member=? AND element>?
           ORDER BY element LIMIT ?""",
        (artifact, member, after, MAX_PAGE_ROWS + 1),
    )
    return _bounded(
        rows,
        limit,
        (
            "element",
            "occurrence",
            "parent",
            "child_position",
            "qualified_name",
            "namespace",
            "attributes_json",
        ),
    )


def member_range(db, artifact, member, expected, offset, length):
    if (
        type(offset) is not int
        or type(length) is not int
        or offset < 0
        or not 0 <= length <= MAX_PAGE_BYTES
    ):
        raise ValueError("native member range outside bound")
    row = db.execute(
        "SELECT kind,member_sha256,byte_length FROM members WHERE digest=? AND ordinal=?",
        (artifact, member),
    ).fetchone()
    if row is None or row[0] == "directory" or row[1] != expected:
        raise KeyError("native member unavailable")
    if offset + length > row[2]:
        raise ValueError("native member range exceeds payload")
    if length == 0:
        return b""
    first, relative = divmod(offset, CHUNK)
    last = (offset + length - 1) // CHUNK
    parts = list(
        member_payload(db, artifact, member, after=first - 1, limit=last - first + 1)
    )
    if [seq for seq, _, _ in parts] != list(range(first, last + 1)):
        raise InvalidHistory("native member range missing chunks")
    result = b"".join(payload for _, _, payload in parts)[relative : relative + length]
    if len(result) != length or (
        length == row[2] and sha256(result).hexdigest() != expected
    ):
        raise InvalidHistory("native member range integrity mismatch")
    return result


def members(db, artifact, *, after=0, limit=64):
    rows = db.execute(
        """SELECT ordinal,path,kind,member_sha256,byte_length,
                  CASE kind WHEN 'attachment' THEN 'byte_only'
                            WHEN 'directory' THEN 'directory' ELSE 'structured' END,
                  CASE WHEN kind='attachment' AND lower(path) LIKE '%.gpx'
                            THEN 'gpx_not_recognized_as_supported_xml'
                       WHEN kind='attachment' THEN 'no_structured_decoder' END
           FROM members WHERE digest=? AND ordinal>? ORDER BY ordinal LIMIT ?""",
        (artifact, after, MAX_PAGE_ROWS + 1),
    )
    return _bounded(
        rows,
        limit,
        ("ordinal", "path", "kind", "sha256", "byte_length", "disposition", "reason"),
    )


def references(db, artifact, member, *, after=0, limit=64):
    rows = db.execute(
        """SELECT element,target,status,target_member FROM native_source_refs
           WHERE artifact=? AND member=? AND element>? ORDER BY element LIMIT ?""",
        (artifact, member, after, MAX_PAGE_ROWS + 1),
    )
    return _bounded(rows, limit, ("element", "target", "status", "target_member"))
