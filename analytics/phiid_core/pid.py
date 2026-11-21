from __future__ import annotations

from typing import Any, Dict

import numpy as np


def pid_broja(sources: Dict[str, np.ndarray], target: np.ndarray) -> Dict[str, Any]:
    """
    Compute PID using BROJA for exactly two sources.
    Returns dict with keys: unique, redundant, synergy each mapping feature->value where applicable.
    """
    if len(sources) != 2:
        raise NotImplementedError("BROJA PID implemented for exactly two sources.")

    try:
        from dit import Distribution
        from dit.pid import PID_BROJA
    except ModuleNotFoundError as error:
        if error.name != "dit":
            raise
        raise RuntimeError(
            "BROJA PID requires dit. Install requirements-broja.txt."
        ) from error

    names = list(sources.keys())
    X1 = np.asarray(sources[names[0]]).astype(int)
    X2 = np.asarray(sources[names[1]]).astype(int)
    Y = np.asarray(target).astype(int)

    # Build joint distribution from samples: discretize if needed
    # Here assume already discrete integers 0/1 etc.
    # Construct outcomes and frequencies
    data = list(zip(X1, X2, Y))
    outcomes, counts = np.unique(data, axis=0, return_counts=True)
    p = counts / counts.sum()
    distribution = Distribution([tuple(outcome) for outcome in outcomes.tolist()], p)
    pid = PID_BROJA(distribution, ((0,), (1,)), (2,), method="scipy")

    uniq0 = float(pid[((0,),)])
    uniq1 = float(pid[((1,),)])
    red = float(pid[((0,), (1,))])
    syn = float(pid[((0, 1),)])

    return {
        "unique": {names[0]: uniq0, names[1]: uniq1},
        "redundant": {"both": red},
        "synergy": {"pair": syn},
    }
