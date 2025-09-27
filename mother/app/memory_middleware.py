# mother/app/memory_middleware.py
from __future__ import annotations
from typing import Callable, Iterable, Optional, List, Dict, Any, Tuple
import re

from mother.memory.adapter import MemoryAdapter

# ---- Memory service thin wrapper ------------------------------------------


class MemoryService:
    """Small convenience wrapper over MemoryAdapter."""

    def __init__(self, dsn: Optional[str] = "service=mother_local"):
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
        type: str = "semantic",  # one of: autobio | episodic | semantic | procedural
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

# Lightweight patterns that capture the kinds of facts you’ve been saving.
_PATTERNS: List[Tuple[re.Pattern, str, List[str], bool]] = [
    # paths / repos
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
    # infra hosts / IP:port
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
    """Return list of (text, type, tags, pin). Duplicates removed."""
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


# ---- Prompt stitching ------------------------------------------------------

BASE_SYSTEM = (
    "You are a helpful assistant. Prefer concrete, verified facts. "
    "If a user fact conflicts with new evidence, ask a short follow-up before assuming."
)


def build_prompt(
    history: List[Dict[str, str]], user_msg: str, facts: List[Dict[str, Any]]
) -> str:
    mem_block = "\n".join(f"- {r['text']}" for r in facts) if facts else ""
    hist = "\n".join(
        f"{m['role'].title()}: {m['content']}" for m in history[-10:]
    )  # last 10 turns
    memory_section = f"\nKnown facts:\n{mem_block}\n" if mem_block else ""
    return f"{BASE_SYSTEM}\n{memory_section}\n{hist}\nUser: {user_msg}\nAssistant:"


# ---- Middleware wrapper ----------------------------------------------------


class ChatMemoryMiddleware:
    """
    Wraps an LLM callable with:
      1) pre-query recall
      2) post-reply auto-remember (very conservative)
    """

    def __init__(
        self,
        llm_call: Callable[[str], str],
        mem: Optional[MemoryService] = None,
        *,
        k: int = 5,
        recall_types: Iterable[str] = ("autobio", "semantic"),
        auto_remember: bool = True,
    ):
        self.llm_call = llm_call
        self.mem = mem or MemoryService()
        self.k = k
        self.recall_types = list(recall_types)
        self.auto_remember = auto_remember

    def handle(
        self, *, user_id: str, history: List[Dict[str, str]], user_msg: str
    ) -> Dict[str, Any]:
        # 1) Recall (query-aware)
        facts = self.mem.recall(
            user_id=user_id, query_text=user_msg, k=self.k, types=self.recall_types
        )

        # 2) Build prompt and get model reply
        prompt = build_prompt(history, user_msg, facts)
        reply = self.llm_call(prompt)

        # 3) Auto-remember small, high-value facts from user + reply
        saved: List[str] = []
        if self.auto_remember:
            for text, typ, tags, pin in extract_candidate_facts(user_msg, reply):
                try:
                    self.mem.remember(
                        user_id=user_id, text=text, type=typ, tags=tags, pin=pin
                    )
                    saved.append(text)
                except Exception:
                    # Don’t break the chat on storage hiccups
                    pass

        return {
            "reply": reply,
            "facts_used": [r["text"] for r in facts],
            "facts_saved": saved,
        }
