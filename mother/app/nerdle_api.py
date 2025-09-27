from __future__ import annotations
import uuid
import random
import datetime as dt
from typing import List
from fastapi import FastAPI, HTTPException
import json
from mother.app.nerdle.models import (
    StartRequest,
    StartResponse,
    GuessRequest,
    GuessResult,
    HintRequest,
    CoachRequest,
    CoachAdvice,
)
from mother.app.nerdle.logic import (
    is_valid_equation,
    tiles_from_guess,
    try_make_target,
    constraints_from_history,
    suggest_probe,
)
from mother.app.nerdle.storage import load_game, save_game

# Default operator set used by hint logic
OPS = "+-*/="


# Tolerant JSON getter for DB fields (accept str or already-parsed dict/list)
def _j(v, default=None):
    if isinstance(v, (dict, list)):
        return v
    if v in (None, ""):
        return default
    return json.loads(v)


# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────
APP_NAME = "nerdle-trainer"

# ──────────────────────────────────────────────────────────────────────────────
# Models are now in mother.app.nerdle.models

# ──────────────────────────────────────────────────────────────────────────────
# Logic moved to mother.app.nerdle.logic

# ──────────────────────────────────────────────────────────────────────────────
# Target generator
# ──────────────────────────────────────────────────────────────────────────────
# Target generation moved to mother.app.nerdle.logic

# ──────────────────────────────────────────────────────────────────────────────
# Persistence helpers
# ──────────────────────────────────────────────────────────────────────────────
# Persistence helpers moved to mother.app.nerdle.storage


# ──────────────────────────────────────────────────────────────────────────────
# Coaching (constraints + simple next-probe heuristic)
# ──────────────────────────────────────────────────────────────────────────────
def coaching_tips(history: List[dict]) -> List[str]:
    tips = []
    if not history:
        tips.append(
            "Open with a ‘coverage’ guess: use 4 distinct digits and one operator (e.g., 12+34=46)."
        )
    else:
        g, t = history[-1]["guess"], history[-1]["tiles"]
        if "Y" not in t and "G" not in t:
            tips.append(
                "All gray: pivot operators and introduce new digits to maximize information gain."
            )
        if t.count("G") >= 4:
            tips.append(
                "Many greens: lock fixed positions and cycle unused digits for the remaining slots."
            )
        if "=" not in g:
            tips.append(
                "Always include '=' exactly once; Nerdle requires a valid full equation."
            )
    tips += [
        "Avoid numbers with leading zeros.",
        "For division, ensure the left is divisible by the right (integer division).",
        "Place '=' roughly in the middle; most targets look like a?b=c.",
    ]
    return tips


# ──────────────────────────────────────────────────────────────────────────────
# FastAPI
# ──────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="Mother Nerdle Trainer", version="0.1.0")


@app.get("/health")
def health():
    return {"ok": True, "service": APP_NAME}


@app.post("/nerdle/start", response_model=StartResponse)
def start_game(req: StartRequest):
    random.seed(req.seed)
    target = try_make_target(req.length, req.ops)
    if not target:
        raise HTTPException(500, "could not generate target of requested length/ops")
    row = {
        "game_id": str(uuid.uuid4()),
        "user_id": req.user_id,
        "status": "active",
        "target": target,
        "max_attempts": req.max_attempts,
        "attempts_used": 0,
        "history": json.dumps([]),
        "settings": json.dumps(
            {
                "length": req.length,
                "ops": req.ops,
                "allow_multi_digit": req.allow_multi_digit,
            }
        ),
        "started_at": dt.datetime.utcnow(),
        "ended_at": None,
    }
    save_game(row)
    return StartResponse(
        game_id=row["game_id"],
        user_id=row["user_id"],
        length=req.length,
        max_attempts=req.max_attempts,
        attempts_used=0,
        status="active",
    )


@app.post("/nerdle/guess", response_model=GuessResult)
def make_guess(req: GuessRequest):
    row = load_game(req.game_id, req.user_id)
    if row["status"] != "active":
        return GuessResult(
            valid=False, reason=f"game is {row['status']}", status=row["status"]
        )

    target = row["target"]
    length = _j(row["settings"], {})["length"]
    ops = _j(row["settings"], {})["ops"]

    guess = req.guess.strip()
    if len(guess) != length:
        return GuessResult(
            valid=False,
            reason=f"guess must be exactly {length} characters",
            status="active",
        )
    ok, reason = is_valid_equation(guess, ops)
    if not ok:
        return GuessResult(valid=False, reason=reason, status="active")

    tiles = tiles_from_guess(guess, target)
    hist = _j(row["history"], [])
    hist.append(
        {
            "ts": dt.datetime.utcnow().isoformat(),
            "guess": guess,
            "tiles": tiles,
            "valid": True,
            "reason": None,
        }
    )
    row["attempts_used"] += 1
    row["history"] = json.dumps(hist)

    status = "active"
    if guess == target:
        status = "won"
        row["status"] = "won"
        row["ended_at"] = dt.datetime.utcnow()
    elif row["attempts_used"] >= row["max_attempts"]:
        status = "lost"
        row["status"] = "lost"
        row["ended_at"] = dt.datetime.utcnow()

    save_game(row)

    # Small “training” hint
    hint = None
    if status == "active":
        cns = constraints_from_history(hist)
        if cns["fixed_positions"]:
            hint = f"Locked: {', '.join(cns['fixed_positions'])}"
        elif cns["must_have"]:
            hint = f"Contains: {''.join(cns['must_have'])}"

    return GuessResult(
        valid=True,
        tiles=tiles,
        attempts_used=row["attempts_used"],
        attempts_left=row["max_attempts"] - row["attempts_used"],
        status=status,
        hint=hint,
    )


@app.post("/nerdle/hint")
def get_hint(req: HintRequest):
    row = load_game(req.game_id, req.user_id)
    hist = _j(row["history"], [])
    target = row["target"]
    length = _j(row["settings"], {})["length"]

    if req.kind == "position":
        unknown = [
            i for i in range(length) if not any(h["tiles"][i] == "G" for h in hist)
        ]
        if not unknown:
            return {"hint": "All positions known; focus on exact digits."}
        i = random.choice(unknown)
        return {"hint": f"Position {i+1} is '{target[i]}'"}

    if req.kind == "operator":
        ops = [ch for ch in target if ch in OPS]
        return {"hint": f"Operator set includes: {''.join(sorted(set(ops)))}"}

    if req.kind == "result-digit":
        right = target.split("=")[1]
        return {
            "hint": f"The result (after '=') contains: {''.join(sorted(set(right)))}"
        }

    # default: symbol
    pick = random.choice(list(set(target)))
    return {"hint": f"It contains '{pick}'"}


@app.post("/nerdle/coach", response_model=CoachAdvice)
def coach(req: CoachRequest):
    row = load_game(req.game_id, req.user_id)
    hist = _j(row["history"], [])
    settings = _j(row["settings"], {})
    cns = constraints_from_history(hist)
    tips = coaching_tips(hist)
    probe = suggest_probe(hist, settings["length"], settings["ops"])
    return CoachAdvice(constraints=cns, tips=tips, suggested_probe=probe)
