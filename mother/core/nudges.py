from pydantic import BaseModel


class NudgeRequest(BaseModel):
    routine: str
    why: str | None = None
    micro_step: str = "2-minute start"
    choices: list[str] = ["Do", "Snooze 15m", "Edit"]


def compose_nudge(nr: NudgeRequest) -> str:
    recap = f"We scheduled {nr.routine}" + (f" because {nr.why}." if nr.why else ".")
    ask = f"Let’s take the first {nr.micro_step} now — {', '.join(nr.choices)}?"
    return f"{recap} {ask}"


def health_summary_stub() -> str:
    return "Vitals steady enough for a short focus block."


def demo_nudge() -> str:
    return compose_nudge(
        NudgeRequest(
            routine="hydrate", why="you think clearer when hydrated", micro_step="sip"
        )
    )
