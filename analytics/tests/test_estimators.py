from __future__ import annotations
import numpy as np
from analytics.phiid_core.api import InfoDecomposition


def test_mi_gaussian_dependence():
    rng = np.random.default_rng(0)
    X = rng.normal(size=500)
    Y = X + 0.1 * rng.normal(size=500)
    info = InfoDecomposition()
    mi = info.mi(X, Y, k=5)
    assert mi > 0.1


def test_cmi_independence_given():
    rng = np.random.default_rng(1)
    Z = rng.normal(size=600)
    X = Z + rng.normal(size=600) * 0.1
    Y = Z + rng.normal(size=600) * 0.1
    info = InfoDecomposition()
    cmi = info.cmi(X, Y, Z, k=5)
    assert cmi < 0.2


def test_te_directionality():
    rng = np.random.default_rng(2)
    n = 800
    X = rng.normal(size=n)
    Y = np.zeros(n)
    for t in range(1, n):
        Y[t] = 0.8 * Y[t - 1] + 0.5 * X[t - 1] + rng.normal()
    info = InfoDecomposition()
    te_xy = info.te(X, Y, lag=1, k=5)
    te_yx = info.te(Y, X, lag=1, k=5)
    assert te_xy > te_yx
