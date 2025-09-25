from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import List, Optional

import psycopg
from psycopg.rows import dict_row

from .embedders import load_embedder
from .sql import search_memory_sql, upsert_memory_sql


def _dsn_from_env() -> str:
    host = os.getenv("PGHOST", "192.168.1.225")
    port = int(os.getenv("PGPORT", "55432"))
    db = os.getenv("PGDATABASE", "mother")
    user = os.getenv("PGUSER", "mother")
    pwd = os.getenv("PGPASSWORD", "")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


def _pad_or_trunc(vec: List[float], dim: int) -> List[float]:
    if len(vec) == dim:
        return vec
    if len(vec) > dim:
        return vec[:dim]
    return vec + [0.0] * (dim - len(vec))


@dataclass
class MemoryAdapter:
    dsn: str | None = None
    metric: str = os.getenv("MEMORY_DISTANCE", "cosine")
    topk: int = int(os.getenv("MEMORY_TOPK", "50"))

    def __post_init__(self) -> None:
        self.dsn = self.dsn or _dsn_from_env()
        self.embedder = load_embedder()
        self.dim = int(os.getenv("EMBEDDING_DIM", str(self.embedder.dim)))

    def _connect(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def _stable_id(self, user_id: str, text: str) -> str:
        h = hashlib.sha256(f"{user_id}\x1f{text}".encode("utf-8")).hexdigest()
        return h[:32]

    def upsert(
        self,
        user_id: str,
        text: str,
        mtype: str = "autobio",
        tags: Optional[list[str]] = None,
        pin: bool = False,
        payload: Optional[dict] = None,
        id_override: Optional[str] = None,
        confidence: float = 0.9,
    ) -> str:
        vid = id_override or self._stable_id(user_id, text)
        vec = _pad_or_trunc(self.embedder.embed(text), self.dim)
        params = {
            "id": vid,
            "user_id": user_id,
            "type": mtype,
            "text": text,
            "tags": tags or [],
            "confidence": float(confidence),
            "ttl_days": 0 if pin else int(os.getenv("MEMORY_TTL_DAYS", "0")),
            "retention_policy": os.getenv("MEMORY_RETENTION", "LRFU(21d)"),
            "embedding_model": self.embedder.name,
            "embedding_dim": self.dim,
            "embedding": vec,
            "payload": json.dumps(payload or {}),
        }
        sql = upsert_memory_sql()
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()
        return vid

    def retrieve(
        self,
        user_id: str,
        query: str,
        limit: Optional[int] = None,
        types: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
    ) -> list[dict]:
        limit = int(limit or self.topk)
        qvec = _pad_or_trunc(self.embedder.embed(query), self.dim)
        sql = search_memory_sql(metric=self.metric)
        params = {
            "user_id": user_id,
            "query_vec": qvec,
            "limit": limit,
            "types": types,
            "tags": tags,
        }
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        out = []
        for r in rows:
            d = float(r.pop("distance", 0.0))
            score = 1.0 - d if self.metric == "cosine" else -d
            r["score"] = score
            out.append(r)
        return out
