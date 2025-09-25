#!/usr/bin/env python3
import os
import sqlite3


def load_yaml(path):
    try:
        import yaml

        with open(path, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def cfg():
    return (load_yaml("content/storage.yaml") or {}).get("storage", {}) or {}


def ensure_out():
    os.makedirs("out", exist_ok=True)


def _csv_append(path, header, row):
    ensure_out()
    exists = os.path.exists(path)
    with open(path, "a") as f:
        if not exists:
            f.write(header + "\n")
        f.write(row + "\n")


def _ensure_sqlite(dbpath):
    ensure_out()
    os.makedirs(os.path.dirname(dbpath), exist_ok=True)
    con = sqlite3.connect(dbpath)
    cur = con.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS text_log(
        ts INTEGER, arm TEXT, category TEXT,
        text_id TEXT, text_hash TEXT, tone TEXT, segment TEXT, text TEXT
    )"""
    )
    con.commit()
    con.close()


def log_text_choice(
    ts: int,
    arm: str,
    category: str,
    text_id: str,
    text_hash: str,
    tone: str,
    segment: str,
    text: str,
):
    # Always CSV
    safe_text = (text or "").replace('"', "'")
    _csv_append(
        "out/text_log.csv",
        "ts,arm,category,text_id,text_hash,tone,segment,text",
        f'{ts},{arm},{category},{text_id},{text_hash},{tone},{segment},"{safe_text}"',
    )
    # Optional SQLite mirror
    c = cfg()
    if (c.get("backend", "csv") or "csv").lower() == "sqlite":
        db = c.get("sqlite_path", "out/mother.db")
        _ensure_sqlite(db)
        con = sqlite3.connect(db)
        con.execute(
            "INSERT INTO text_log(ts,arm,category,text_id,text_hash,tone,segment,text) VALUES (?,?,?,?,?,?,?,?)",
            (int(ts), arm, category, text_id, text_hash, tone, segment, text),
        )
        con.commit()
        con.close()
