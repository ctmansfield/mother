from __future__ import annotations
from typing import Dict, Any, List

OPERATORS = {
    "<=": lambda a, b: a <= b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    ">": lambda a, b: a > b,
    "==": lambda a, b: a == b,
}


def evaluate_rules(rules: List[Dict[str, Any]], features: Dict[str, Any]):
    triggered = []
    for r in rules:
        conds = r.get("if_all", [])
        ok = True
        for c in conds:
            f = c.get("feature")
            op = c.get("op", "<=")
            val = c.get("value")
            fv = features.get(f)
            if fv is None:
                ok = False
                break
            cmp = OPERATORS.get(op)
            if not cmp:
                ok = False
                break
            if not cmp(fv, val):
                ok = False
                break
        if ok:
            triggered.append(r)
    return triggered
