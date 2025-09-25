#!/usr/bin/env python3
import numpy as np
import re
import hashlib

WORD = re.compile(r"[A-Za-z0-9_]+")


def _cfg():
    try:
        import yaml

        with open("content/weyland.yaml", "r") as f:
            return (yaml.safe_load(f) or {}).get("weyland", {})
    except Exception:
        return {}


def _h(s):  # deterministic 64-bit
    return int(hashlib.blake2b(s.encode("utf-8"), digest_size=8).hexdigest(), 16)


def _ngrams(s, n=3):
    s = re.sub(r"\s+", " ", s.lower()).strip()
    s = f"^{s}$"
    return [s[i : i + n] for i in range(max(0, len(s) - n + 1))]


def embed(text: str):
    c = _cfg()
    n = int(c.get("ngram", 3))
    d = int(c.get("dim", 512))
    norm = bool(c.get("normalize", True))
    v = np.zeros(d, dtype=float)
    if not text:
        return v
    for g in _ngrams(text, n=n):
        v[_h(g) % d] += 1.0
    if norm:
        s = np.linalg.norm(v)
        if s > 0:
            v /= s
    return v


def cosine(a, b):
    if a is None or b is None:
        return 0.0
    da = float(np.linalg.norm(a))
    db = float(np.linalg.norm(b))
    if da == 0 or db == 0:
        return 0.0
    return float(a.dot(b) / (da * db))
