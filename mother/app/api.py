# mother/app/api.py
from __future__ import annotations
from typing import List, Optional, Iterable, Dict, Any, Tuple
import os
import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# --- Your storage adapter ----------------------------------------------------
# Assumes you've already fixed/installed this in your repo
from mother.memory.adapter import MemoryAdapter

# ---- Memory service thin wrapper -------------------------------------------


class MemoryService:
    """Small convenience wrapper over MemoryAdapter."""

    def __init__(self, dsn: Optional[str] = None):
        # Prefer DSN env, otherwise default to pg_service (PGSERVICE=mother_local)
        dsn = dsn or os.getenv("MOTHER_DB_DSN") or "service=mother_local"
        self._mem = MemoryAdapter(dsn=dsn)

    def recall(
        self,
        *,
        user_id: str,
        query_text: str,
        k: int = 5,
        types: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]:
        return self._mem.retrieve(
            user_id=user_id,
            query=query_text,
            limit=k,
            types=list(types) if types else None,
        )

    def remember(
        self,
        *,
        user_id: str,
        text: str,
        type: str = "semantic",  # autobio | episodic | semantic | procedural
        tags: Optional[Iterable[str]] = None,
        pin: bool = False,
        payload: Optional[Dict[str, Any]] = None,
        confidence: float = 0.9,
    ) -> str:
        return self._mem.upsert(
            user_id=user_id,
            text=text,
            type=type,
            tags=list(tags) if tags else [],
            pin=pin,
            payload=payload or {},
            confidence=confidence,
        )


# ---- Simple heuristics for “what to remember” ------------------------------

_PATTERNS: List[Tuple[re.Pattern, str, List[str], bool]] = [
    (
        re.compile(r"(?:^|\b)(/+(?:home|root|mnt|srv|var|repos)[^\s]+)", re.I),
        "autobio",
        ["path"],
        True,
    ),
    (
        re.compile(r"\b(repo(?:sitory)? (?:root|path) is [^\n]+)", re.I),
        "autobio",
        ["repo", "path"],
        True,
    ),
    (
        re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d{2,5})?\b"),
        "semantic",
        ["ip"],
        False,
    ),
    (
        re.compile(r"\b([a-z0-9][-a-z0-9.]*\.[a-z]{2,})(?::\d{2,5})?\b", re.I),
        "semantic",
        ["host"],
        False,
    ),
    (
        re.compile(r"\bpostgres\b.*\b(10\.10\.10\.\d+:\d+)\b", re.I),
        "semantic",
        ["db", "infra"],
        False,
    ),
]


def extract_candidate_facts(*texts: str) -> List[Tuple[str, str, List[str], bool]]:
    out, seen = [], set()
    for t in texts:
        if not t:
            continue
        for pat, typ, tags, pin in _PATTERNS:
            for m in pat.finditer(t):
                fact = m.group(1) if m.groups() else m.group(0)
                key = fact.strip().lower()
                if len(key) >= 4 and key not in seen:
                    seen.add(key)
                    out.append((fact.strip(), typ, tags, pin))
    return out


# ---- Chat middleware --------------------------------------------------------

BASE_SYSTEM = (
    "You are a helpful assistant. Prefer concrete, verified facts. "
    "If a user fact conflicts with new evidence, ask a short follow-up before assuming."
)


def build_prompt(
    history: List[Dict[str, str]], user_msg: str, facts: List[Dict[str, Any]]
) -> str:
    mem_block = "\n".join(f"- {r['text']}" for r in facts) if facts else ""
    hist = "\n".join(f"{m['role'].title()}: {m['content']}" for m in history[-10:])
    memory_section = f"\nKnown facts:\n{mem_block}\n" if mem_block else ""
    return f"{BASE_SYSTEM}\n{memory_section}\n{hist}\nUser: {user_msg}\nAssistant:"


class ChatMemory:
    def __init__(
        self,
        mem: Optional[MemoryService] = None,
        *,
        k: int = 5,
        recall_types: Iterable[str] = ("autobio", "semantic"),
        auto_remember: bool = True,
    ):
        self.mem = mem or MemoryService()
        self.k = k
        self.recall_types = list(recall_types)
        self.auto_remember = auto_remember

    def call_llm(self, prompt: str) -> str:
        # TODO: replace with your real LLM call
        return "Acknowledged. Using /root/genomics-stack and DB at 10.10.10.1:5434."

    def handle(
        self, *, user_id: str, history: List[Dict[str, str]], user_msg: str
    ) -> Dict[str, Any]:
        facts = self.mem.recall(
            user_id=user_id, query_text=user_msg, k=self.k, types=self.recall_types
        )
        prompt = build_prompt(history, user_msg, facts)
        reply = self.call_llm(prompt)

        saved: List[str] = []
        if self.auto_remember:
            for text, typ, tags, pin in extract_candidate_facts(user_msg, reply):
                try:
                    self.mem.remember(
                        user_id=user_id, text=text, type=typ, tags=tags, pin=pin
                    )
                    saved.append(text)
                except Exception:
                    pass

        return {
            "reply": reply,
            "facts_used": [r["text"] for r in facts],
            "facts_saved": saved,
        }


# ---- FastAPI ----------------------------------------------------------------

app = FastAPI(title="Mother Memory API", version="0.1.0")

# CORS for quick testing in browser tools
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mem_service = MemoryService()
chat_mm = ChatMemory(mem_service)

# ---- Schemas ----------------------------------------------------------------


class Message(BaseModel):
    role: str = Field(pattern=r"^(user|assistant|system)$")
    content: str


class ChatRequest(BaseModel):
    user_id: str
    message: str
    history: List[Message] = []


class ChatResponse(BaseModel):
    reply: str
    facts_used: List[str] = []
    facts_saved: List[str] = []


class UpsertRequest(BaseModel):
    user_id: str
    text: str
    type: str = Field("semantic", pattern=r"^(autobio|episodic|semantic|procedural)$")
    tags: List[str] = []
    pin: bool = False
    payload: Dict[str, Any] = {}
    confidence: float = 0.9


class SearchRequest(BaseModel):
    user_id: str
    query: str
    limit: int = 5
    types: Optional[List[str]] = None


# ---- Endpoints --------------------------------------------------------------


@app.get("/health")
async def health() -> Dict[str, Any]:
    try:
        # a lightweight query exercises DB connection
        _ = mem_service.recall(user_id="healthcheck", query_text="ping", k=1)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    result = chat_mm.handle(
        user_id=req.user_id,
        history=[m.model_dump() for m in req.history],
        user_msg=req.message,
    )
    return ChatResponse(**result)


@app.post("/mem/upsert")
async def mem_upsert(req: UpsertRequest) -> Dict[str, Any]:
    try:
        vid = mem_service.remember(
            user_id=req.user_id,
            text=req.text,
            type=req.type,
            tags=req.tags,
            pin=req.pin,
            payload=req.payload,
            confidence=req.confidence,
        )
        return {"ok": True, "id": vid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mem/search")
async def mem_search(req: SearchRequest) -> Dict[str, Any]:
    try:
        res = mem_service.recall(
            user_id=req.user_id, query_text=req.query, k=req.limit, types=req.types
        )
        return {"ok": True, "results": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
