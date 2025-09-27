# mother/app/game_api.py
from __future__ import annotations
import os
import time
import random
import json
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from uuid import uuid4

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


# --------------------------------------------------------------------------------------
# DB helpers
# --------------------------------------------------------------------------------------
def _conninfo() -> str:
    dsn = os.getenv("MOTHER_DB_DSN")
    svc = os.getenv("PGSERVICE", "mother_local")
    return dsn if dsn else f"service={svc}"


def _exec(sql: str, args: tuple = ()):
    # autocommit per call; fine for our simple inserts/selects
    with psycopg.connect(_conninfo()) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            if cur.description:
                return cur.fetchall()
            return None


# --------------------------------------------------------------------------------------
# Game state (kept in-process; fine for testing / dev)
# --------------------------------------------------------------------------------------
WORDS = "apple river rocket neon summit cloud coral copper vector llama kernel genome memory stack phoenix".split()
EMOJI = "😀 🐶 🍕 🚀 🌟 🎲 🎧 🧬 🧠 🐙 🪐 🧩 🔑 🛰️ 🐍".split()
DIGITS = list("0123456789")


def _next_token(mode: str) -> str:
    if mode == "emoji":
        return random.choice(EMOJI)
    if mode == "digits":
        return random.choice(DIGITS)
    return random.choice(WORDS)


@dataclass
class GameState:
    user_id: str
    mode: str = "words"  # one of: words|emoji|digits
    seq: List[str] = field(default_factory=list)
    level: int = 0
    score: int = 0
    started_at: float = field(default_factory=time.time)
    finished: bool = False


GAMES: Dict[str, GameState] = {}

# --------------------------------------------------------------------------------------
# FastAPI app
# --------------------------------------------------------------------------------------
app = FastAPI(title="Mother Memory Game API", version="0.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


class NewGameIn(BaseModel):
    user_id: str = Field(..., description="Your user id (e.g. u_chad)")
    mode: str = Field("words", description="words|emoji|digits")


class NewGameOut(BaseModel):
    session_id: str
    level: int
    sequence: List[str]
    tip: str


class AnswerIn(BaseModel):
    session_id: str
    answer: str = Field(
        ..., description="Space-separated tokens, e.g. 'apple river' or '😀 🚀'"
    )
    # Optional: echo user_id for high-score attribution safety
    user_id: Optional[str] = None


class AnswerOut(BaseModel):
    correct: bool
    level: int
    score: int
    next_sequence: Optional[List[str]] = None
    expected: Optional[List[str]] = None
    finished: bool


class HighScore(BaseModel):
    mode: str
    score: int
    when: float


@app.get("/health")
def health():
    return {"ok": True, "service": "memory-game"}


def _save_high_score(user_id: str, mode: str, score: int):
    # only persist if this beats the previous best for that mode
    row = _exec(
        """
        SELECT COALESCE(MAX( (payload->>'score')::int ), 0)
        FROM memory_item
        WHERE user_id = %s
          AND type = 'episodic'
          AND payload ? 'kind'
          AND payload->>'kind' = 'memory_game'
          AND payload->>'mode' = %s
        """,
        (user_id, mode),
    )
    best = row[0][0] if row else 0
    if score <= best:
        return

    mid = hashlib.md5(f"{user_id}:{mode}:{time.time()}".encode()).hexdigest()
    text = f"MemoryGame best score {score} (mode={mode})"
    payload = json.dumps({"kind": "memory_game", "mode": mode, "score": score})
    _exec(
        """
        INSERT INTO memory_item
          (id, user_id, type, text, tags, confidence, ttl_days, retention_policy,
           embedding_model, embedding_dim, embedding, payload)
        VALUES
          (%s, %s, 'episodic', %s, ARRAY['game','score'], 0.9, 0, 'LRFU(21d)',
           'hash-fallback-v1', 1024, NULL, %s::jsonb)
        """,
        (mid, user_id, text, payload),
    )


@app.post("/game/memory/new", response_model=NewGameOut)
def new_game(inp: NewGameIn):
    sid = str(uuid4())
    mode = inp.mode.lower()
    if mode not in ("words", "emoji", "digits"):
        raise HTTPException(400, "mode must be one of: words|emoji|digits")

    st = GameState(user_id=inp.user_id, mode=mode)
    st.seq.append(_next_token(mode))
    st.level = 1
    GAMES[sid] = st

    tip = "Repeat the sequence back exactly as space-separated tokens."
    return NewGameOut(session_id=sid, level=st.level, sequence=st.seq[:], tip=tip)


@app.get("/game/memory/state/{session_id}")
def state(session_id: str):
    st = GAMES.get(session_id)
    if not st:
        raise HTTPException(404, "unknown session")
    return {
        "user_id": st.user_id,
        "mode": st.mode,
        "level": st.level,
        "score": st.score,
        "sequence": st.seq,
        "finished": st.finished,
        "age_s": round(time.time() - st.started_at, 3),
    }


@app.post("/game/memory/answer", response_model=AnswerOut)
def answer(inp: AnswerIn):
    st = GAMES.get(inp.session_id)
    if not st:
        raise HTTPException(404, "unknown session")
    if st.finished:
        return AnswerOut(
            correct=False,
            level=st.level,
            score=st.score,
            expected=st.seq,
            finished=True,
        )

    tokens = [t for t in inp.answer.strip().split() if t]
    if tokens == st.seq:
        st.score += 1
        st.level += 1
        st.seq.append(_next_token(st.mode))
        return AnswerOut(
            correct=True,
            level=st.level,
            score=st.score,
            next_sequence=st.seq[:],
            finished=False,
        )
    else:
        st.finished = True
        _save_high_score(st.user_id, st.mode, st.score)
        return AnswerOut(
            correct=False,
            level=st.level,
            score=st.score,
            expected=st.seq[:],
            finished=True,
        )


@app.get("/game/memory/highscores")
def highscores(user_id: str):
    rows = (
        _exec(
            """
        SELECT (payload->>'mode') AS mode,
               (payload->>'score')::int AS score,
               EXTRACT(EPOCH FROM ts_created) AS when_epoch
        FROM memory_item
        WHERE user_id = %s
          AND type = 'episodic'
          AND payload->>'kind' = 'memory_game'
        ORDER BY (payload->>'score')::int DESC, ts_created DESC
        LIMIT 10;
        """,
            (user_id,),
        )
        or []
    )
    return [
        HighScore(mode=r[0], score=r[1], when=float(r[2])).model_dump() for r in rows
    ]
