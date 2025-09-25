#!/usr/bin/env python3
# Contextual bandit: logistic epsilon-greedy + Adagrad with NumPy fast path.
import json
import os
import math
import random

try:
    import numpy as np
except Exception:
    np = None

STATE = os.path.join("out", "bishop_ctx.json")

FEATS = [
    "bias",
    "daypart_morning",
    "daypart_midday",
    "daypart_afternoon",
    "daypart_evening",
    "tone_gentle",
    "tone_humor",
    "tone_strict",
    "channel_push",
    "channel_in_app",
    "category_hydration",
    "category_posture",
    "category_movement",
    "category_focus",
    "category_sleep",
]
D = len(FEATS)


def feat_vec_from_arm(arm: str):
    parts = (arm or "").split("|")
    dp = parts[0] if len(parts) > 0 else ""
    tn = parts[1] if len(parts) > 1 else ""
    ch = parts[2] if len(parts) > 2 else ""
    ct = parts[3] if len(parts) > 3 else ""
    x = [0.0] * D
    x[0] = 1.0

    def set1(name):
        if name in FEATS:
            x[FEATS.index(name)] = 1.0

    set1(f"daypart_{dp}")
    set1(f"tone_{tn}")
    set1(f"channel_{ch}")
    set1(f"category_{ct}")
    return np.array(x, dtype=float) if np is not None else x


def sigmoid(z):
    try:
        return 1.0 / (1.0 + math.exp(-z))
    except Exception:
        return 0.5


class CtxBandit:
    def __init__(self, path=STATE):
        self.path = path
        self.lr = 0.10
        self.eps = 0.10
        # weights/accumulators as vectors when NumPy is available
        if np is not None:
            self.w = np.zeros(D)
            self.g2 = np.zeros(D)
        else:
            self.w = [0.0] * D
            self.g2 = [0.0] * D
        self.load()

    def load(self):
        if not os.path.exists(self.path):
            return
        try:
            d = json.load(open(self.path))
            self.lr = float(d.get("lr", 0.10))
            self.eps = float(d.get("eps", 0.10))
            w = d.get("w", [0.0] * D)
            g2 = d.get("g2", [0.0] * D)
            if np is not None:
                self.w = np.array(w, dtype=float)
                self.g2 = np.array(g2, dtype=float)
            else:
                self.w = list(map(float, w))
                self.g2 = list(map(float, g2))
        except Exception:
            pass

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if np is not None:
            w = self.w.tolist()
            g2 = self.g2.tolist()
        else:
            w = self.w
            g2 = self.g2
        json.dump(
            {"w": w, "g2": g2, "lr": self.lr, "eps": self.eps}, open(self.path, "w")
        )

    # score one x
    def _score(self, x):
        if np is not None:
            return sigmoid(float(self.w @ x))
        else:
            return sigmoid(sum(wi * xi for wi, xi in zip(self.w, x)))

    # pick from a list of arm strings (epsilon-greedy on predicted p)
    def choose(self, candidates):
        if not candidates:
            return None
        if random.random() < self.eps:
            return random.choice(candidates)
        if np is not None:
            X = np.vstack([feat_vec_from_arm(a) for a in candidates])  # (n,D)
            ps = 1.0 / (1.0 + np.exp(-(X @ self.w)))  # vectorized
            idx = int(np.argmax(ps))
            return candidates[idx]
        else:
            best = None
            bestp = -1.0
            for a in candidates:
                p = self._score(feat_vec_from_arm(a))
                if p > bestp:
                    bestp = p
                    best = a
            return best

    # Adagrad update with logistic loss
    def update(self, x, y):
        if np is not None:
            p = 1.0 / (1.0 + np.exp(-float(self.w @ x)))
            g = (p - float(y)) * x  # gradient
            self.g2 = self.g2 + g * g
            step = self.lr / (1e-8 + np.sqrt(self.g2))
            self.w = self.w - step * g
            self.w = np.clip(self.w, -8.0, 8.0)
        else:
            # pure Python
            z = sum(wi * xi for wi, xi in zip(self.w, x))
            p = sigmoid(z)
            gscale = p - float(y)
            for i in range(D):
                gi = gscale * x[i]
                self.g2[i] += gi * gi
                step = self.lr / (1e-8 + math.sqrt(self.g2[i]))
                self.w[i] -= step * gi
                if self.w[i] > 8.0:
                    self.w[i] = 8.0
                if self.w[i] < -8.0:
                    self.w[i] = -8.0
