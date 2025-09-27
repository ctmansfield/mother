from __future__ import annotations
from typing import List, Optional, Dict
from pydantic import BaseModel, Field


class StartRequest(BaseModel):
    user_id: str
    length: int = 8
    ops: str = "+-*/"
    max_attempts: int = 6
    allow_multi_digit: bool = True
    seed: Optional[int] = None


class StartResponse(BaseModel):
    game_id: str
    user_id: str
    length: int
    max_attempts: int
    attempts_used: int
    status: str


class GuessRequest(BaseModel):
    user_id: str
    game_id: str
    guess: str


class GuessResult(BaseModel):
    valid: bool
    reason: Optional[str] = None
    tiles: Optional[List[str]] = None
    attempts_used: int = 0
    attempts_left: int = 0
    status: str = "active"
    hint: Optional[str] = None


class HintRequest(BaseModel):
    user_id: str
    game_id: str
    kind: str = Field("symbol", description="symbol|position|operator|result-digit")


class CoachRequest(BaseModel):
    user_id: str
    game_id: str


class CoachAdvice(BaseModel):
    constraints: Dict[str, List[str]]
    tips: List[str]
    suggested_probe: Optional[str] = None
