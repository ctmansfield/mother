from __future__ import annotations
import re
import random
from typing import Dict, List, Optional, Tuple

DIGITS = set("0123456789")
OPS = set("+-*/")
TOKENS = DIGITS | OPS | {"="}
LEADING_ZERO_RE = re.compile(r"\b0\d")


def _int_eval(expr: str) -> Optional[int]:
    if not expr or any(ch not in (DIGITS | OPS) for ch in expr):
        return None
    if LEADING_ZERO_RE.search(expr):
        return None
    parts = re.split(r"([+\-*/])", expr)
    if not parts or not parts[0] or parts[0] == "-":
        return None
    try:
        val = int(parts[0])
        i = 1
        while i < len(parts):
            op = parts[i]
            rhs = int(parts[i + 1])
            if op == "+":
                val = val + rhs
            elif op == "-":
                val = val - rhs
            elif op == "*":
                val = val * rhs
            elif op == "/":
                if rhs == 0 or (val % rhs) != 0:
                    return None
                val = val // rhs
            else:
                return None
            i += 2
        return val
    except Exception:
        return None


def is_valid_equation(s: str, allowed_ops: str) -> Tuple[bool, str]:
    if any(ch not in (DIGITS | set(allowed_ops) | {"="}) for ch in s):
        return False, "contains disallowed characters"
    if s.count("=") != 1:
        return False, "must contain exactly one '='"
    left, right = s.split("=", 1)
    if not left or not right:
        return False, "missing left or right side"
    lv = _int_eval(left)
    rv = _int_eval(right)
    if lv is None or rv is None:
        return (
            False,
            "invalid arithmetic (leading zeros, bad ops, or non-integer division)",
        )
    if lv != rv:
        return False, "equation not true"
    return True, "ok"


def tiles_from_guess(guess: str, target: str) -> List[str]:
    G, Y, B = "G", "Y", "B"
    res = [B] * len(guess)
    t_counts: Dict[str, int] = {}
    for i, (g, t) in enumerate(zip(guess, target)):
        if g == t:
            res[i] = G
        else:
            t_counts[t] = t_counts.get(t, 0) + 1
    for i, (g, t) in enumerate(zip(guess, target)):
        if res[i] == G:
            continue
        if t_counts.get(g, 0) > 0:
            res[i] = Y
            t_counts[g] -= 1
    return res


def rand_int(n_digits: int, no_leading_zero=True) -> int:
    lo = 10 ** (n_digits - 1) if n_digits > 1 else 0
    hi = 10**n_digits - 1
    x = random.randint(lo, hi)
    if n_digits > 1 and no_leading_zero and str(x)[0] == "0":
        return rand_int(n_digits, no_leading_zero)
    return x


def format_eq(a: int, op: str, b: int, c: int) -> str:
    return f"{a}{op}{b}={c}"


def try_make_target(length: int, allowed_ops: str) -> Optional[str]:
    for _ in range(5000):
        op = random.choice(list(allowed_ops))
        if op in "+-":
            a = random.randint(0, 99)
            b = random.randint(0, 99)
            c = a + b if op == "+" else a - b
        elif op == "*":
            a = random.randint(2, 15)
            b = random.randint(2, 15)
            c = a * b
        else:  # '/'
            b = random.randint(2, 15)
            c = random.randint(2, 50)
            a = b * c
        s = format_eq(a, op, b, c)
        ok, _ = is_valid_equation(s, allowed_ops)
        if len(s) == length and ok:
            return s
    return None


def constraints_from_history(history: List[dict]) -> Dict[str, List[str]]:
    must_have, cannot_have = set(), set()
    fixed = {}
    not_here: Dict[int, set] = {}
    for h in history:
        g = h["guess"]
        t = h["tiles"]
        for i, (ch, flag) in enumerate(zip(g, t)):
            if flag == "G":
                fixed[i] = ch
                must_have.add(ch)
            elif flag == "Y":
                must_have.add(ch)
                not_here.setdefault(i, set()).add(ch)
            else:
                cannot_have.add(ch)
    cannot = [c for c in cannot_have if c not in must_have]
    not_here_fmt = [f"pos {i} ≠ {''.join(sorted(s))}" for i, s in not_here.items()]
    fixed_fmt = [f"{i}:{ch}" for i, ch in sorted(fixed.items())]
    return {
        "must_have": sorted(must_have),
        "cannot_have": sorted(cannot),
        "fixed_positions": fixed_fmt,
        "not_in_positions": not_here_fmt,
    }


def suggest_probe(history: List[dict], length: int, allowed_ops: str) -> Optional[str]:
    seen = set(ch for h in history for ch in h["guess"])
    fresh_digits = [d for d in "9876543210" if d not in seen]
    fresh_ops = [o for o in allowed_ops if o not in seen] or list(allowed_ops)

    def pick(n):
        take = (
            fresh_digits[:n]
            if len(fresh_digits) >= n
            else (fresh_digits + list("0123456789"))[:n]
        )
        return [int(x) for x in take]

    op = fresh_ops[0]
    a, b, c = 12, 34, 46
    try:
        a, b = pick(2)
        if op == "+":
            c = a + b
        elif op == "-":
            c = a - b
        elif op == "*":
            c = a * b
        else:
            b = max(2, b or 2)
            c = max(1, a or 1)
            a = b * c
        s = f"{a}{op}{b}={c}"
        for _ in range(30):
            if len(s) == length:
                break
            if len(s) < length:
                s = s.replace("=", "0=", 1)
            else:
                s = s.replace("0", "", 1)
        return s if len(s) == length else None
    except Exception:
        return None
