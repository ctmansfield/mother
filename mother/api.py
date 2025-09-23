from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from mother.core import tone, memory
from mother.core.nudges import NudgeRequest, compose_nudge, demo_nudge

app = FastAPI(title="mother-api")


@app.on_event("startup")
def _init_memory() -> None:
    memory.init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/nudge/demo")
def nudge_demo(user_id: str = "default"):
    msg = tone.apply(demo_nudge(), "routine")
    return {"message": memory.personalize_and_update(msg, user_id)}


@app.post("/nudge/preview")
def nudge_preview(nr: NudgeRequest, user_id: str = "default"):
    msg = tone.apply(compose_nudge(nr), "routine")
    return {"message": memory.personalize_and_update(msg, user_id)}


class RememberBody(BaseModel):
    user_id: str
    key: str
    value: str
    ttl_days: int | None = None


@app.post("/memory/remember")
def memory_remember(body: RememberBody):
    memory.remember_fact(
        body.user_id, body.key, body.value, ttl_days=body.ttl_days, source="api"
    )
    return {"ok": True}


@app.get("/memory/profile")
def memory_profile(user_id: str = "default"):
    prof = memory.get_profile(user_id)
    return {"user_id": user_id, "profile": prof}
