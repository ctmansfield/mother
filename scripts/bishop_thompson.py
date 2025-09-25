#!/usr/bin/env python3
# Thompson sampling for linear reward model with ridge prior.
import json
import os
import random

try:
    import numpy as np
except Exception:
    np = None

STATE = os.path.join("out", "bishop_thompson.json")


def load_yaml(path):
    try:
        import yaml

        with open(path, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _cfg():
    return (
        (load_yaml("content/bishop.yaml") or {}).get("bishop", {}).get("thompson", {})
    )


def _feat_vec(arm):
    try:
        from scripts.bishop_ctx import feat_vec_from_arm

        return feat_vec_from_arm(arm)
    except Exception:
        return [1.0]


def _D():
    try:
        from scripts.bishop_ctx import D

        return D
    except Exception:
        return 1


def _zeros_D():
    D = _D()
    if np is not None:
        return np.zeros(D, dtype=float), np.eye(D, dtype=float)
    return [0.0] * D, [[float(i == j) for j in range(D)] for i in range(D)]


def _to_json(A, b):
    if np is not None:
        return {"A": A.tolist(), "b": b.tolist()}
    return {"A": A, "b": b}


def _from_json(obj):
    A = obj.get("A")
    b = obj.get("b")
    if np is not None:
        return np.array(A, dtype=float), np.array(b, dtype=float)
    return A, b


class ThompsonBandit:
    def __init__(self, path=STATE, v=None, l2=None):
        self.path = path
        c = _cfg()
        self.v = float(v if v is not None else c.get("v", 0.1))
        self.l2 = float(l2 if l2 is not None else c.get("l2", 1.0))
        self.state = self._load()

    def _load(self):
        if not os.path.exists(self.path):
            return {}
        try:
            return json.load(open(self.path))
        except Exception:
            return {}

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        json.dump(self.state, open(self.path, "w"))

    def _ensure(self, arm):
        if arm in self.state:
            return
        b, A = _zeros_D()
        if np is not None:
            A *= 0.0
            A += self.l2 * np.eye(_D(), dtype=float)
        else:
            for i in range(_D()):
                for j in range(_D()):
                    A[i][j] = self.l2 if i == j else 0.0
        self.state[arm] = _to_json(A, b)

    def _sample_theta(self, A, b):
        if np is None:
            # scalar fallback
            mean = (b[0] / A[0][0]) if A[0][0] != 0 else 0.0
            std = self.v * (1.0 / (A[0][0] ** 0.5 if A[0][0] > 0 else 1.0))
            return [random.gauss(mean, std)]
        Ainv = np.linalg.inv(A)
        mu = Ainv.dot(b)
        # sample from N(mu, v^2 * A^-1)
        L = np.linalg.cholesky(Ainv + 1e-9 * np.eye(len(Ainv)))
        z = np.random.normal(size=len(mu))
        theta = mu + (self.v * L.dot(z))
        return theta

    def select(self, candidates):
        if not candidates:
            return None, {}
        scores = {}
        for arm in candidates:
            self._ensure(arm)
            A, b = _from_json(self.state[arm])
            x = _feat_vec(arm)
            theta = self._sample_theta(A, b)
            if np is not None:
                x = np.array(x, dtype=float)
                theta = np.array(theta, dtype=float)
                s = float(x.dot(theta))
            else:
                s = float(theta[0])
            scores[arm] = s
        best = max(candidates, key=lambda a: scores.get(a, -1e18))
        return best, scores

    def update(self, arm, reward):
        self._ensure(arm)
        A, b = _from_json(self.state[arm])
        x = _feat_vec(arm)
        if np is not None:
            x = np.array(x, dtype=float)
            A += np.outer(x, x)
            b += reward * x
        else:
            A[0][0] += 1.0
            b[0] += reward
        self.state[arm] = _to_json(A, b)
        self._save()


# Back-compat for older motherctl imports
class ThompsonBLR(ThompsonBandit):
    pass
