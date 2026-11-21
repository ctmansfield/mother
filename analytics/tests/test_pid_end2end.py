from __future__ import annotations

import os
from importlib.util import find_spec

import numpy as np
import pytest

from analytics.phiid_core.pid import pid_broja


@pytest.fixture
def require_broja():
    if find_spec("dit") is None:
        if os.environ.get("MOTHER_REQUIRE_BROJA") == "1":
            pytest.fail("BROJA is required but dit is not installed")
        pytest.skip("Install requirements-broja.txt to qualify BROJA PID")


def test_pid_broja_two_sources(require_broja):
    # simple discrete example
    # Y = X1 XOR X2 -> pure synergy
    X1 = np.array([0, 0, 1, 1] * 50)
    X2 = np.array([0, 1, 0, 1] * 50)
    Y = (X1 ^ X2).astype(int)
    res = pid_broja({"X1": X1, "X2": X2}, Y)
    assert res["synergy"]["pair"] == pytest.approx(1, abs=1e-5)
    assert res["redundant"]["both"] == pytest.approx(0, abs=1e-5)
    assert list(res["unique"].values()) == pytest.approx([0, 0], abs=1e-5)


def test_pid_broja_redundant_sources(require_broja):
    source = np.array([0, 1] * 50)
    result = pid_broja({"X1": source, "X2": source}, source)
    assert result["redundant"]["both"] == pytest.approx(1, abs=1e-5)
    assert result["synergy"]["pair"] == pytest.approx(0, abs=1e-5)
    assert list(result["unique"].values()) == pytest.approx([0, 0], abs=1e-5)
