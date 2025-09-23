from __future__ import annotations
import re
from typing import Literal, Optional
from .personality import load_personality, Personality

KIND = Literal["routine", "accountability", "celebration"]


def _apply_voice(text: str, persona: Personality) -> str:
    if persona.voice == "we":
        text = re.sub(r"\bYou planned\b", "We planned", text)
        text = re.sub(r"\bYou scheduled\b", "We scheduled", text)
    return text


def _apply_hedging(text: str, persona: Personality, kind: KIND) -> str:
    if persona.hedging in ("minimal", "moderate", "high") and kind in (
        "routine",
        "accountability",
    ):
        text = re.sub(r"—\s+Do", "— if you’re ready. Do", text)
    return text


def _apply_exclamations(text: str, persona: Personality, kind: KIND) -> str:
    if persona.exclamations == "off":
        return text.replace("!", ".")
    if persona.exclamations == "sparse":
        if kind == "celebration":
            text = re.sub(r"!+", "!", text)
            if "!" not in text:
                text = re.sub(r"(\.)(\s|$)", r"!\2", text, count=1)
        else:
            text = text.replace("!", ".")
    return text


def _strip_emoji(text: str, persona: Personality) -> str:
    if persona.emoji == "off":
        return re.sub(r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF]", "", text)
    return text


def apply(
    message: str, kind: KIND = "routine", persona: Optional[Personality] = None
) -> str:
    persona = persona or load_personality()
    text = message
    text = _apply_voice(text, persona)
    text = _apply_hedging(text, persona, kind)
    text = _apply_exclamations(text, persona, kind)
    text = _strip_emoji(text, persona)
    return " ".join(text.split())
