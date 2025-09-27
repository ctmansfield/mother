from __future__ import annotations
import os
from typing import Any
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

PG_DSN = os.getenv("PG_DSN")


def pg_conn():
    if PG_DSN:
        return psycopg.connect(PG_DSN, row_factory=dict_row)
    return psycopg.connect(row_factory=dict_row)


def as_json(v: Any):
    if isinstance(v, (dict, list)):
        return v
    if v is None or v == "":
        return {}
    import json as _json

    return _json.loads(v)


def load_game(game_id: str, user_id: str) -> dict:
    with pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM nerdle_game WHERE game_id=%s AND user_id=%s",
            (game_id, user_id),
        )
        row = cur.fetchone()
        if not row:
            from fastapi import HTTPException

            raise HTTPException(404, "game not found")
        return row


def save_game(row: dict):
    cols = list(row.keys())
    for c in ("history", "settings"):
        if c in row and isinstance(row[c], (dict, list)):
            row[c] = Json(row[c])
    vals = [row[c] for c in cols]
    placeholders = ",".join(["%s"] * len(cols))
    pkcols = ["game_id"]
    updates = ",".join([f"{c}=EXCLUDED.{c}" for c in cols if c not in pkcols])
    sql = (
        f"INSERT INTO nerdle_game ({','.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT (game_id) DO UPDATE SET {updates}"
    )
    with pg_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, vals)
        conn.commit()
