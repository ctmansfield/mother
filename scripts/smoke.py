#!/usr/bin/env python3
from models.bishop.bandit import BishopBandit

arms = ["morning|gentle|push|hydration", "afternoon|gentle|push|hydration"]
b = BishopBandit(arms)
a = b.select()
b.update(a, 1.0)
print("smoke-ok", a)
