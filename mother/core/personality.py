from __future__ import annotations
import os
import functools
import pathlib
from typing import Literal, List
from pydantic import BaseModel
import yaml

_PERSONALITY_PATH_ENV = "MOTHER_PERSONALITY"
_DEFAULT_PATH = pathlib.Path(__file__).resolve().parent.parent / "personality.yaml"


class Personality(BaseModel):
    warmth: float = 0.5
    directness: float = 0.5
    playfulness: float = 0.0
    authority: Literal["peer", "coach", "expert"] = "peer"
    energy: float = 0.5
    emoji: Literal["off", "sparse", "occasional"] = "off"
    reading_level: Literal["basic", "concise-pro"] = "concise-pro"
    motivation: List[Literal["nudger", "accountability", "celebratory"]] = ["nudger"]
    voice: Literal["you", "we", "mixed"] = "you"
    hedging: Literal["none", "minimal", "moderate", "high"] = "minimal"
    exclamations: Literal["off", "sparse", "occasional"] = "sparse"


@functools.lru_cache(maxsize=1)
def load_personality() -> Personality:
    p = os.environ.get(_PERSONALITY_PATH_ENV)
    path = pathlib.Path(p) if p else _DEFAULT_PATH
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return Personality.model_validate(data)
    return Personality()
