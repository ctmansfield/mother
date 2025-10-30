from __future__ import annotations
from typing import Dict, Any
import numpy as np

try:
    import dit
    from dit.pid import pid as dit_pid
    from dit.pid.measures.broja import PID_BROJA
except Exception:  # pragma: no cover - optional during scaffold
    dit = None
    PID_BROJA = None


def pid_broja(sources: Dict[str, np.ndarray], target: np.ndarray) -> Dict[str, Any]:
    """
    Compute PID using BROJA for exactly two sources.
    Returns dict with keys: unique, redundant, synergy each mapping feature->value where applicable.
    """
    if dit is None or PID_BROJA is None:
        raise RuntimeError("dit[PID_BROJA] not available. Install 'dit'.")

    if len(sources) != 2:
        raise NotImplementedError("BROJA PID implemented for exactly two sources.")

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
    d = dit.Distribution(list(map(tuple, outcomes)), p)
    d.set_rv_names([names[0], names[1], "Y"])

    pid = dit_pid(d, [[names[0]], [names[1]]], "Y", measure=PID_BROJA)
    # Extract components
    uniq0 = float(pid.get_partial({names[0]}))
    uniq1 = float(pid.get_partial({names[1]}))
    red = float(pid.get_partial({names[0], names[1]}))  # redundancy
    syn = float(pid.get_partial(set()))  # synergy term in BROJA lattice

    return {
        "unique": {names[0]: uniq0, names[1]: uniq1},
        "redundant": {"both": red},
        "synergy": {"pair": syn},
    }
