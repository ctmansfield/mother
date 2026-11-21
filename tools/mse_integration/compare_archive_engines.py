"""Compare a matched archive transaction on disposable SQLite and PostgreSQL."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import UUID

DDL = (
    "CREATE TABLE archive_sequence (value BIGINT NOT NULL)",
    "INSERT INTO archive_sequence VALUES (0)",
    "CREATE TABLE archive_batches (scope TEXT NOT NULL, batch TEXT NOT NULL, "
    "digest TEXT NOT NULL, raw BYTEA NOT NULL, seq BIGINT NOT NULL UNIQUE, "
    "PRIMARY KEY(scope,batch))",
    "CREATE TABLE archive_facts (scope TEXT NOT NULL, native TEXT NOT NULL, "
    "seq BIGINT NOT NULL REFERENCES archive_batches(seq), value TEXT, "
    "channel TEXT NOT NULL, unit TEXT NOT NULL, deleted INTEGER NOT NULL "
    "CHECK (deleted IN (0,1)), PRIMARY KEY(scope,native,seq))",
    "CREATE INDEX archive_cutoff ON archive_facts(scope, seq)",
    "CREATE VIEW archive_export AS SELECT f.scope,f.native,f.seq,f.value,"
    "f.channel,f.unit,b.digest FROM archive_facts f JOIN archive_batches b ON "
    "(b.scope=f.scope AND b.seq=f.seq) WHERE f.deleted=0",
)


class Engine:
    def __init__(self, kind, location):
        self.kind = kind
        self.location = location

    @contextmanager
    def connect(self):
        if self.kind == "SQLite":
            connection = sqlite3.connect(self.location, timeout=5)
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA synchronous=FULL")
        else:
            import psycopg

            connection = psycopg.connect(self.location, connect_timeout=5)
            connection.execute("SET statement_timeout='5s'")
            connection.execute("SET lock_timeout='4s'")
        with closing(connection):
            yield connection

    def execute(self, db, sql, values=()):
        return db.execute(
            sql if self.kind == "SQLite" else sql.replace("?", "%s"), values
        )

    def install(self):
        with self.connect() as db:
            for statement in DDL:
                db.execute(statement)
            db.commit()

    def commit(self, batch, rows, *, interrupt=False):
        raw = json.dumps(rows, separators=(",", ":")).encode()
        digest = sha256(raw).hexdigest()
        with self.connect() as db:
            if self.kind == "SQLite":
                db.execute("BEGIN IMMEDIATE")
            else:
                db.execute("SELECT value FROM archive_sequence FOR UPDATE")
            existing = self.execute(
                db,
                "SELECT digest,raw,seq FROM archive_batches WHERE scope=? AND batch=?",
                ("synthetic", batch),
            ).fetchone()
            if existing:
                if existing[0] != digest or bytes(existing[1]) != raw:
                    raise ValueError("batch conflict")
                return existing[2], digest
            sequence = db.execute(
                "UPDATE archive_sequence SET value=value+1 RETURNING value"
            ).fetchone()[0]
            self.execute(
                db,
                "INSERT INTO archive_batches VALUES (?,?,?,?,?)",
                ("synthetic", batch, digest, raw, sequence),
            )
            if interrupt:
                raise InterruptedError("synthetic precommit interruption")
            with closing(db.cursor()) as cursor:
                sql = "INSERT INTO archive_facts VALUES (?,?,?,?,?,?,?)"
                cursor.executemany(
                    sql if self.kind == "SQLite" else sql.replace("?", "%s"),
                    [
                        ("synthetic", native, sequence, value, channel, unit, deleted)
                        for native, value, channel, unit, deleted in rows
                    ],
                )
            db.commit()
            return sequence, digest

    def page(self, cutoff):
        with self.connect() as db:
            return self.execute(
                db,
                """
                SELECT e.native,e.channel,e.unit,e.value,e.digest FROM archive_export e
                WHERE e.scope=? AND e.seq<=? AND NOT EXISTS (
                    SELECT 1 FROM archive_facts d
                    WHERE d.scope=e.scope AND d.native=e.native AND d.deleted=1 AND d.seq<=?
                ) ORDER BY e.native,e.seq
                """,
                ("synthetic", cutoff, cutoff),
            ).fetchall()


def samples(start, count):
    return [
        (
            str(UUID(int=index, version=4)),
            "40.1234567890123456789" if index % 2 else "65.25",
            "hrv_sdnn" if index % 2 else "heart_rate",
            "ms" if index % 2 else "bpm",
            0,
        )
        for index in range(start, start + count)
    ]


def exercise(engine):
    engine.install()
    first = samples(1, 2)
    receipt = engine.commit("first", first)
    assert engine.commit("first", first) == receipt
    try:
        engine.commit("first", samples(99, 1))
    except ValueError:
        pass
    else:
        raise AssertionError("accepted conflict")
    try:
        engine.commit("interrupted", samples(200, 1), interrupt=True)
    except InterruptedError:
        pass
    else:
        raise AssertionError("accepted interruption")
    assert len(engine.page(1)) == 2
    deleted = tuple((*first[0][0:1], None, *first[0][2:4], 1))
    assert engine.commit("deleted", [deleted])[0] == 2
    assert len(engine.page(1)) == 2 and len(engine.page(2)) == 1
    assert engine.page(1)[0][3] == "40.1234567890123456789"

    def write(worker):
        for batch in range(8):
            engine.commit(
                f"{worker}-{batch}", samples(1000 + worker * 1024 + batch * 64, 64)
            )

    start = perf_counter()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(write, range(2)))
    writes = perf_counter() - start
    start = perf_counter()
    page = engine.page(18)
    reads = perf_counter() - start
    assert len(page) == 1025
    return page, {
        "kind": engine.kind,
        "rows": len(page),
        "writer_seconds": round(writes, 4),
        "read_seconds": round(reads, 4),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-socket", type=Path, required=True)
    args = parser.parse_args()
    socket = args.postgres_socket.resolve(strict=True)
    if not socket.is_dir():
        raise ValueError("Use the disposable cluster's private Unix socket directory")
    # The qualification command supplies a fresh cluster and dedicated database.
    import psycopg.conninfo

    location = psycopg.conninfo.make_conninfo(
        host=str(socket), dbname="archive_comparison"
    )
    with TemporaryDirectory(prefix="archive-engine-comparison-") as root:
        sqlite, sqlite_metrics = exercise(Engine("SQLite", Path(root) / "sqlite.db"))
        postgres, postgres_metrics = exercise(Engine("PostgreSQL", location))
        assert sqlite == postgres
        print(
            json.dumps(
                {
                    "same_export_rows": True,
                    "sqlite_version": sqlite3.sqlite_version,
                    "checks": [
                        "retry",
                        "conflict",
                        "rollback",
                        "cutoff",
                        "deletion",
                        "exact_decimal",
                        "view_join",
                        "two_writers",
                    ],
                    "engines": [sqlite_metrics, postgres_metrics],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
