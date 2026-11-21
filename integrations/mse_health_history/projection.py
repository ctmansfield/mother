"""Bounded read-only consumer snapshot and an offline Nightscout JSON adapter."""

from contextlib import closing
from datetime import timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3

from integrations.healthbridge.capture import _unique_object
from mother.physiology.contracts import canonical_json
from mother.physiology.time import parse_timestamp
from mother.physiology.units import GLUCOSE_MMOL_L_TO_MG_DL

from .blood_pressure import decimal_text, protected_ref, source_time

MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_ROWS = 10_000
BUCKET_MINUTES = 15
PURPOSES = {"mother-bp-cgm-review", "coach-bp-cgm-review"}


def _finite(_):
    raise ValueError("non-finite glucose token")


def _bucket(clock):
    dt = parse_timestamp(clock).astimezone(timezone.utc)
    return (
        dt.replace(
            minute=dt.minute // BUCKET_MINUTES * BUCKET_MINUTES, second=0, microsecond=0
        )
        .isoformat(timespec="minutes")
        .replace("+00:00", "Z")
    )


def _entry(row, unit_contract):
    if not isinstance(row, dict) or row.get("type", "sgv") != "sgv":
        raise ValueError("unsupported Nightscout entry")
    unit = row.get("units", row.get("unit", unit_contract))
    value = row.get("sgv")
    if not isinstance(value, (str, int, Decimal)) or isinstance(value, bool):
        raise ValueError("unusable Nightscout measurement")
    number = Decimal(decimal_text(str(value)))
    if unit in ("mmol/L", "mmol/l", "mmol"):
        number *= Decimal(str(GLUCOSE_MMOL_L_TO_MG_DL))
    elif unit not in ("mg/dL", "mg/dl", "mgdl"):
        raise ValueError("unqualified Nightscout unit")
    date = row.get("date")
    stamped = row.get("dateString")
    if date is None:
        event = parse_timestamp(stamped)
    else:
        event = parse_timestamp(date, numeric_unit="ms")
        if stamped is not None and parse_timestamp(stamped) != event:
            raise ValueError("inconsistent Nightscout clocks")
    return {
        "time": event.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z"),
        "value": decimal_text(format(number, "f")),
        "unit": "mg/dL",
    }


def synthetic_nightscout_entries(path, *, unit_contract=None):
    """Parse a fabricated local JSON array. No endpoint, credentials or API cursor."""
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("Nightscout source fixture exceeds byte limit")
    value = json.loads(
        raw,
        parse_float=Decimal,
        parse_constant=_finite,
        object_pairs_hook=_unique_object,
    )
    if not isinstance(value, list) or len(value) > MAX_ROWS:
        raise ValueError("Nightscout fixture must be a bounded entry array")
    records = []
    unsupported = 0
    aliases = {}
    conflicted = set()
    for row in value:
        try:
            fact = _entry(row, unit_contract)
        except (TypeError, ValueError, OverflowError):
            unsupported += 1
            continue
        identity = row.get("_id", row.get("identifier"))
        if not isinstance(identity, str) or not identity:
            records.append(fact)
            continue
        original = aliases.setdefault(identity, fact)
        if original != fact:
            conflicted.add(identity)
    records.extend(
        fact for identity, fact in aliases.items() if identity not in conflicted
    )
    return {
        "artifact_sha256": sha256(raw).hexdigest(),
        "observed": len(value),
        "unnormalized": unsupported,
        "conflicted_identities": len(conflicted),
        "rows": records,
    }


def consumer_snapshot(
    catalog, *, purpose, consumer_key, start, end, synthetic_glucose=None
):
    if (
        purpose not in PURPOSES
        or not isinstance(consumer_key, bytes)
        or len(consumer_key) < 32
    ):
        raise ValueError(
            "consumer projection requires an approved purpose and private key"
        )
    from_clock, through_clock = source_time(start), source_time(end)
    if from_clock >= through_clock:
        raise ValueError("consumer projection requires a bounded UTC range")
    subject = protected_ref(
        consumer_key, "historical-consumer/0.1", purpose, catalog.owner
    )
    rows = []

    def append(row):
        if len(rows) >= MAX_ROWS:
            raise ValueError("consumer projection row limit exceeded")
        rows.append(row)

    for bp in catalog.blood_pressure(current=True):
        event = bp["clocks"]["event_end"]
        if bp["pairing"] == "paired" and from_clock <= event < through_clock:
            values = {part["role"]: part["value"] for part in bp["components"]}
            append(
                {
                    "kind": "blood_pressure_pair",
                    "bucket": _bucket(event),
                    "unit": "mmHg",
                    "systolic": values["systolic"],
                    "diastolic": values["diastolic"],
                }
            )
    for fact in (synthetic_glucose or {}).get("rows", []):
        if from_clock <= fact["time"] < through_clock:
            append(
                {
                    "kind": "glucose_cgm",
                    "bucket": _bucket(fact["time"]),
                    "unit": "mg/dL",
                    "value": decimal_text(fact["value"]),
                }
            )
    return {
        "schema_version": "mse.synthetic-bp-cgm-projection/0.1",
        "purpose": purpose,
        "synthetic": True,
        "subject": subject,
        "utc_bucket_minutes": BUCKET_MINUTES,
        "rows": sorted(
            rows, key=lambda row: (row["bucket"], row["kind"], canonical_json(row))
        ),
    }


def write_snapshot(snapshot, path):
    """Publish a new purpose-only SQLite file for readers using SQLite mode=ro."""
    path = Path(path)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    try:
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE manifest (body TEXT NOT NULL)")
            db.execute(
                "CREATE TABLE facts (ordinal INTEGER PRIMARY KEY, bucket TEXT, kind TEXT, body TEXT NOT NULL)"
            )
            db.execute(
                "INSERT INTO manifest VALUES (?)",
                (canonical_json({k: v for k, v in snapshot.items() if k != "rows"}),),
            )
            db.executemany(
                "INSERT INTO facts VALUES (?,?,?,?)",
                [
                    (i, row["bucket"], row["kind"], canonical_json(row))
                    for i, row in enumerate(snapshot["rows"], 1)
                ],
            )
        path.chmod(0o400)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
