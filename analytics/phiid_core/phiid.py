from __future__ import annotations
import numpy as np

from analytics.phiid_core.api import InfoDecomposition


def synthetic_var(n: int = 2000, lag: int = 1, seed: int = 42):
    rng = np.random.default_rng(seed)
    e1 = rng.normal(size=n)
    e2 = rng.normal(size=n)
    e3 = rng.normal(size=n)
    X = np.zeros(n)
    Z = np.zeros(n)
    Y = np.zeros(n)
    for t in range(1, n):
        X[t] = 0.8 * X[t - 1] + e1[t]
        Z[t] = 0.6 * Z[t - 1] + e2[t]
        # Y depends on past of X and Z
        Y[t] = 0.5 * X[t - lag] + 0.5 * Z[t - lag] + 0.1 * Y[t - 1] + e3[t]
    return X, Z, Y


def phiid_transfer_demo():
    X, Z, Y = synthetic_var()
    info = InfoDecomposition()
    res = info.phiid({"X": X, "Z": Z}, Y, lags={"X": 1, "Z": 1})
    return res
