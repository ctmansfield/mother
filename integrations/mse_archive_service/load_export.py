"""Load one authorized logical export into a new purpose-specific SQLite file."""

import argparse
from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import sys

from mother.physiology.contracts import canonical_json

LIMIT = 2 * 1024 * 1024
KEYS = {"schema_version", "purpose", "row_count", "view_sha256", "view"}
VIEW = "archive_receipt_revisions_v1"


def load(data, destination, *, expected_sha256):
    if len(data) > LIMIT or sha256(data).hexdigest() != expected_sha256:
        raise ValueError("export size or trusted digest mismatch")
    envelope = json.loads(data)
    if (
        not isinstance(envelope, dict)
        or set(envelope) != KEYS
        or envelope["schema_version"] != "archive_export_v1"
        or envelope["purpose"] != "authorized_synthetic_transfer"
        or canonical_json(envelope).encode() != data
    ):
        raise ValueError("invalid export envelope")
    view = envelope["view"]
    if (
        view["view"] != VIEW
        or sha256(canonical_json(view).encode()).hexdigest() != envelope["view_sha256"]
    ):
        raise ValueError("invalid logical view pin")
    rows = view["rows"]
    if len(rows) != envelope["row_count"] or len(rows) > 1024:
        raise ValueError("invalid row count")

    with closing(sqlite3.connect(":memory:")) as staging:
        staging.execute(
            "CREATE TABLE export_manifest (id INTEGER PRIMARY KEY CHECK(id=1), json TEXT NOT NULL)"
        )
        staging.execute(
            """
            CREATE TABLE receipt_revisions (
                receipt_id TEXT NOT NULL, source_revision_id TEXT NOT NULL,
                processing_key TEXT NOT NULL, commit_sequence INTEGER NOT NULL,
                operation TEXT NOT NULL CHECK(operation IN ('upsert','delete')),
                channel TEXT, decimal_value TEXT, unit TEXT, row_json TEXT NOT NULL,
                PRIMARY KEY(receipt_id, source_revision_id, processing_key)
            )
        """
        )
        metadata = dict(
            envelope,
            view={name: value for name, value in view.items() if name != "rows"},
        )
        staging.execute(
            "INSERT INTO export_manifest VALUES (1,?)", (canonical_json(metadata),)
        )
        for row in rows:
            revision = row["source_revision"]
            observation = revision.get("observation", {})
            decimal = observation.get("value")
            if decimal is not None and type(decimal) is not str:
                raise ValueError("exact decimals must be text")
            staging.execute(
                "INSERT INTO receipt_revisions VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    row["receipt_id"],
                    row["source_revision_id"],
                    row["processing_revision_id"] or "",
                    row["commit_sequence"],
                    revision["operation"],
                    observation.get("channel"),
                    decimal,
                    observation.get("unit"),
                    canonical_json(row),
                ),
            )
        staging.commit()
        descriptor = os.open(
            destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        os.close(descriptor)
        with closing(sqlite3.connect(destination)) as db:
            staging.backup(db)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    try:
        with options.input.open("rb") as stream:
            data = stream.read(LIMIT + 1)
        load(data, options.output, expected_sha256=options.sha256)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        print("logical archive export import failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
