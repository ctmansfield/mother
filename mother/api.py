from fastapi import FastAPI
from mother.core.nudges import NudgeRequest, compose_nudge, demo_nudge

app = FastAPI(title="mother-api")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/nudge/preview")
def nudge_preview(nr: NudgeRequest):
    return {"message": compose_nudge(nr)}


@app.get("/nudge/demo")
def nudge_demo():
    return {"message": demo_nudge()}
