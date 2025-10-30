from fastapi import FastAPI, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import uuid
import datetime as dt
from dateutil import parser
import json

# Lightweight rule evaluator from analytics package
try:
    from analytics.rules.apply import evaluate_rules
except Exception:
    # Attempt to add repo root to path if running from mother_app/
    import sys
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from analytics.rules.apply import evaluate_rules
    except Exception:

        def evaluate_rules(rules, features):
            return []


# Optional Postgres connection (best effort)
PG_DSN = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "dbname": os.getenv("POSTGRES_DB", "health"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
}
USE_DB = True
try:
    import psycopg

    conn = psycopg.connect(**PG_DSN, autocommit=True)
except Exception:
    conn = None
    USE_DB = False

app = FastAPI(title="mother")

# Load rules produced by offline analytics (analytics/rules/rules.json)
RULES_PATH = os.getenv("AN_RULES_PATH", "analytics/rules/rules.json")
RULES: List[Dict[str, Any]] | Dict[str, Any] = []


def load_rules():
    global RULES
    try:
        with open(RULES_PATH, "r") as f:
            RULES = json.load(f)
    except Exception:
        RULES = []


load_rules()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# simple memory stores for dev
REMINDERS: Dict[str, Dict[str, Any]] = {}
EVENTS: List[Dict[str, Any]] = []


class ReminderIn(BaseModel):
    user_id: str
    title: str
    note: Optional[str] = None
    due_at: str
    recur_rule: Optional[str] = None
    channel: str = "email"


class PredictIn(BaseModel):
    model: str
    features: Dict[str, Any]


class RiskScoreIn(BaseModel):
    user_id: str
    t0: Optional[str] = None
    current_features: Dict[str, Any]


@app.get("/healthz")
def healthz():
    return {"ok": True, "db": bool(USE_DB)}


@app.post("/api/reminders")
def create_reminder(body: ReminderIn):
    rid = str(uuid.uuid4())
    rec = body.model_dump()
    rec["id"] = rid
    rec["status"] = "scheduled"
    try:
        due = parser.isoparse(rec["due_at"])
    except Exception:
        due = dt.datetime.utcnow()
        rec["due_at"] = due.isoformat() + "Z"

    REMINDERS[rid] = rec

    if USE_DB:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO reminders (id, user_id, title, note, due_at, recur_rule, channel, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    rid,
                    rec["user_id"],
                    rec["title"],
                    rec.get("note"),
                    rec["due_at"],
                    rec.get("recur_rule"),
                    rec["channel"],
                    rec["status"],
                ),
            )
    return {"id": rid, **rec}


@app.get("/api/reminders")
def list_reminders(
    frm: Optional[str] = Query(default=None, alias="from"),
    to: Optional[str] = Query(default=None),
):
    def to_dt(s):
        try:
            return parser.isoparse(s) if s else None
        except Exception:
            return None

    frm_dt = to_dt(frm)
    to_dt_ = to_dt(to)

    def within(r):
        d = to_dt(r.get("due_at"))
        if frm_dt and d and d < frm_dt:
            return False
        if to_dt_ and d and d > to_dt_:
            return False
        return True

    items = [v for v in REMINDERS.values() if within(v)]
    return {"items": items, "count": len(items)}


@app.post("/api/models/predict")
def predict(body: PredictIn):
    model = body.model
    features = body.features or {}
    # Very simple heuristic stub; replace with your real model dispatch
    if model == "adherence_risk_v1":
        base = 0.6
        penalty = 0.1 * int(features.get("recent_skips", 0))
        expectancy = max(
            0.1, min(0.95, base - penalty + 0.05 * int(features.get("last_streak", 0)))
        )
        return {
            "prediction": {
                "expectancy": round(expectancy, 2),
                "risk": round(1 - expectancy, 2),
            },
            "meta": {"model_ver": "stub-0.0.1"},
        }
    elif model == "energy_window_v1":
        return {
            "prediction": {"windows": [["09:30", "11:30"], ["14:00", "16:00"]]},
            "meta": {"model_ver": "stub-0.0.1"},
        }
    else:
        return {"prediction": {}, "meta": {"model_ver": "stub-unknown"}}


@app.get("/risk/rules")
def get_rules():
    rules = RULES.get("rules") if isinstance(RULES, dict) else RULES
    return {"rules": rules or []}


@app.post("/risk/score")
def risk_score(body: RiskScoreIn):
    rules = RULES.get("rules") if isinstance(RULES, dict) else RULES
    rules = rules or []
    feats = body.current_features or {}
    trig = evaluate_rules(rules, feats)
    # aggregate simple risk per event
    risk = {}
    for r in rules:
        ev = r.get("event")
        if ev and ev not in risk:
            risk[ev] = "low"
    for r in trig:
        ev = r.get("event")
        if ev:
            risk[ev] = "high"
    suggestions = [r.get("action") for r in trig if r.get("action")]
    return {
        "risk_scores": risk,
        "triggered_rules": trig,
        "suggestions": suggestions,
        "meta": {"rules_path": RULES_PATH, "rules_count": len(rules)},
    }


@app.get("/explain/feature-importance")
def explain_feature_importance(event: Optional[str] = Query(default=None)):
    # Try to load offline outputs; otherwise derive simple placeholders
    payload = {"unique_rank": [], "synergy_sets": []}
    try:
        with open("analytics/eval/feature_importance.json", "r") as f:
            data = json.load(f)
            if event and event in data:
                payload = data[event]
            elif not event and isinstance(data, dict):
                # return union view
                payload = next(iter(data.values()))
    except Exception:
        pass
    # If still empty, infer synergy sets from rules
    if not payload.get("synergy_sets"):
        rules = RULES.get("rules") if isinstance(RULES, dict) else RULES
        rules = rules or []
        sets = []
        for r in rules:
            if event and r.get("event") != event:
                continue
            feats = [c.get("feature") for c in r.get("if_all", []) if c.get("feature")]
            if len(feats) >= 2:
                sets.append(feats[:3])
        payload["synergy_sets"] = sets
        # naive unique rank based on frequency
        freq: Dict[str, int] = {}
        for s in sets:
            for f in s:
                freq[f] = freq.get(f, 0) + 1
        payload["unique_rank"] = sorted(freq.keys(), key=lambda k: -freq[k])
    return payload


@app.post("/api/behavior/events")
def behavior_events(event: Dict[str, Any] = Body(...)):
    event["id"] = str(uuid.uuid4())
    EVENTS.append(event)
    if USE_DB:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO behavior_events (id, user_id, action_id, event, latency_s, context)
                VALUES (%s,%s,%s,%s,%s,%s)
                """,
                (
                    event.get("id"),
                    event.get("user_id"),
                    event.get("action_id"),
                    event.get("event"),
                    event.get("latency_s"),
                    json.dumps(event.get("context", {})),
                ),
            )
    return {"ok": True, "id": event["id"]}
