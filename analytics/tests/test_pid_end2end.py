from __future__ import annotations
import numpy as np
import pytest

from analytics.phiid_core.pid import pid_broja


@pytest.mark.skip(reason="requires dit; enable when dit is installed")
def test_pid_broja_two_sources():
    # simple discrete example
    # Y = X1 XOR X2 -> pure synergy
    X1 = np.array([0, 0, 1, 1] * 50)
    X2 = np.array([0, 1, 0, 1] * 50)
    Y = (X1 ^ X2).astype(int)
    res = pid_broja({"X1": X1, "X2": X2}, Y)
    assert res["synergy"]["pair"] > 0.1
    assert res["redundant"]["both"] < 0.05
