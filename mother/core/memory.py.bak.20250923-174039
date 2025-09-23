from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

_DB_DEFAULT = os.path.join(
    os.environ.get(
        "MOTHER_DB_DIR",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data")),
    ),
    "mother.db",
)
DB_PATH = os.environ.get("MOTHER_DB_PATH", _DB_DEFAULT)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


_CONN: sqlite3.Connection = _connect()


def init_db() -> None:
    _CONN.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            last_seen_at TEXT
        );
        """
    )
    _CONN.execute(
        """
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            k TEXT NOT NULL,
            v TEXT NOT NULL,
            source TEXT,
            confidence REAL DEFAULT 0.9,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            expires_at TEXT,
            UNIQUE(user_id, k),
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );
        """
    )
    _CONN.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            payload TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );
        """
    )
    _CONN.commit()


def _ensure_user(user_id: str) -> None:
    cur = _CONN.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,))
    if cur.fetchone() is None:
        _CONN.execute(
            "INSERT INTO users(user_id, created_at) VALUES(?, ?)",
            (user_id, _utc_now().isoformat()),
        )
        _CONN.commit()


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    return datetime.fromisoformat(s)


def humanize_delta(d: timedelta) -> str:
    seconds = int(d.total_seconds())
    if seconds <= 30:
        return "just now"
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24
    if days >= 1:
        rem_h = hours % 24
        return f"{days}d" if rem_h == 0 else f"{days}d {rem_h}h"
    if hours >= 1:
        rem_m = minutes % 60
        return f"{hours}h" if rem_m == 0 else f"{hours}h {rem_m}m"
    return f"{minutes}m"


def touch_and_delta(
    user_id: str,
    kind: str = "interaction",
    payload: Optional[Dict[str, Any]] = None,
) -> Optional[timedelta]:
    """Return delta since last_seen BEFORE updating last_seen; then update."""
    _ensure_user(user_id)
    cur = _CONN.execute("SELECT last_seen_at FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    last_seen = _parse_dt(row[0]) if row and row[0] else None
    now = _utc_now()
    _CONN.execute(
        "UPDATE users SET last_seen_at=? WHERE user_id=?",
        (now.isoformat(), user_id),
    )
    _CONN.execute(
        "INSERT INTO events(user_id, kind, payload, created_at) VALUES(?, ?, ?, ?)",
        (user_id, kind, json.dumps(payload or {}), now.isoformat()),
    )
    _CONN.commit()
    return (now - last_seen) if last_seen else None


def remember_fact(
    user_id: str,
    key: str,
    value: str,
    *,
    ttl_days: Optional[int] = None,
    source: str = "api",
    confidence: float = 0.9,
) -> None:
    _ensure_user(user_id)
    now = _utc_now().isoformat()
    expires = (_utc_now() + timedelta(days=ttl_days)).isoformat() if ttl_days else None
    _CONN.execute(
        """
        INSERT INTO facts(user_id, k, v, source, confidence, created_at, updated_at, expires_at)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, k) DO UPDATE SET
          v=excluded.v,
          source=excluded.source,
          confidence=excluded.confidence,
          updated_at=excluded.updated_at,
          expires_at=excluded.expires_at
        """,
        (user_id, key, value, source, confidence, now, now, expires),
    )
    _CONN.commit()


def get_profile(user_id: str) -> Dict[str, str]:
    _ensure_user(user_id)
    _CONN.execute(
        "DELETE FROM facts WHERE expires_at IS NOT NULL AND expires_at < ?",
        (_utc_now().isoformat(),),
    )
    _CONN.commit()
    cur = _CONN.execute(
        "SELECT k, v FROM facts WHERE user_id=? ORDER BY k",
        (user_id,),
    )
    return {k: v for (k, v) in cur.fetchall()}


def personalize_and_update(text: str, user_id: str = "default") -> str:
    delta = touch_and_delta(user_id, kind="render", payload={"preview": text[:120]})
    pre = ""
    if delta:
        pre = f"We last checked in {humanize_delta(delta)}. "
    return pre + text
