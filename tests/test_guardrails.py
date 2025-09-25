from models.newt.guardrails import NewtGuard


def test_quiet_hours():
    g = NewtGuard({"quiet_hours": ["22:00-07:00"], "budget_per_day": 6})
    assert isinstance(g, NewtGuard)
