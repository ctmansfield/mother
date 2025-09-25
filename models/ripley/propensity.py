import math


class RipleyLogit:
    def __init__(self, weights=None):
        self.w = weights or {}

    def predict(self, x):
        z = 0.0
        for k, v in x.items():
            z += self.w.get(k, 0.0) * float(v)
        return 1.0 / (1.0 + math.exp(-z))
