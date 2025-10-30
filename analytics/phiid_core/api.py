from __future__ import annotations
from typing import Dict, Any
import numpy as np
from scipy.special import digamma
from sklearn.neighbors import NearestNeighbors


def _to_2d(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a)
    if a.ndim == 1:
        return a.reshape(-1, 1)
    return a


def _ksg_mi(X: np.ndarray, Y: np.ndarray, k: int = 5) -> float:
    X = _to_2d(X)
    Y = _to_2d(Y)
    n = X.shape[0]
    if n < k + 2:
        return 0.0
    XY = np.concatenate([X, Y], axis=1)
    # kNN in joint space (Chebyshev metric)
    nn_xy = NearestNeighbors(metric="chebyshev", n_neighbors=k + 1).fit(XY)
    dists, _ = nn_xy.kneighbors(XY)
    eps = dists[:, k] - 1e-10
    # Count neighbors in marginal spaces within eps
    nn_x = NearestNeighbors(metric="chebyshev").fit(X)
    nn_y = NearestNeighbors(metric="chebyshev").fit(Y)
    n_x = np.array(
        [
            len(nn_x.radius_neighbors([X[i]], eps[i], return_distance=False)[0]) - 1
            for i in range(n)
        ]
    )
    n_y = np.array(
        [
            len(nn_y.radius_neighbors([Y[i]], eps[i], return_distance=False)[0]) - 1
            for i in range(n)
        ]
    )
    mi = digamma(k) + digamma(n) - np.mean(digamma(n_x + 1) + digamma(n_y + 1))
    return float(max(0.0, mi))


def _ksg_cmi(X: np.ndarray, Y: np.ndarray, Z: np.ndarray, k: int = 5) -> float:
    X = _to_2d(X)
    Y = _to_2d(Y)
    Z = _to_2d(Z)
    n = X.shape[0]
    if n < k + 2:
        return 0.0
    XYZ = np.concatenate([X, Y, Z], axis=1)
    XZ = np.concatenate([X, Z], axis=1)
    YZ = np.concatenate([Y, Z], axis=1)

    nn_xyz = NearestNeighbors(metric="chebyshev", n_neighbors=k + 1).fit(XYZ)
    dists, _ = nn_xyz.kneighbors(XYZ)
    eps = dists[:, k] - 1e-10

    nn_xz = NearestNeighbors(metric="chebyshev").fit(XZ)
    nn_yz = NearestNeighbors(metric="chebyshev").fit(YZ)
    nn_z = NearestNeighbors(metric="chebyshev").fit(Z)

    n_xz = np.array(
        [
            len(nn_xz.radius_neighbors([XZ[i]], eps[i], return_distance=False)[0]) - 1
            for i in range(n)
        ]
    )
    n_yz = np.array(
        [
            len(nn_yz.radius_neighbors([YZ[i]], eps[i], return_distance=False)[0]) - 1
            for i in range(n)
        ]
    )
    n_z = np.array(
        [
            len(nn_z.radius_neighbors([Z[i]], eps[i], return_distance=False)[0]) - 1
            for i in range(n)
        ]
    )

    cmi = digamma(k) - np.mean(digamma(n_xz + 1) + digamma(n_yz + 1) - digamma(n_z + 1))
    return float(max(0.0, cmi))


class InfoDecomposition:
    """
    First-pass info estimators: Kraskov KSG MI/CMI and TE as CMI(X_{t-lag}; Y_t | Y_{t-lag}).
    PID/ΦID placeholders remain minimal until upgraded.
    """

    def mi(self, X: np.ndarray, Y: np.ndarray, k: int = 5) -> float:
        return _ksg_mi(X, Y, k=k)

    def cmi(self, X: np.ndarray, Y: np.ndarray, Z: np.ndarray, k: int = 5) -> float:
        return _ksg_cmi(X, Y, Z, k=k)

    def te(self, X: np.ndarray, Y: np.ndarray, lag: int = 1, k: int = 5) -> float:
        """
        Transfer entropy TE_{X→Y} with embedding 1 and lag: I(X_{t-lag}; Y_t | Y_{t-lag}) via KSG CMI.
        """
        X = np.asarray(X).reshape(-1)
        Y = np.asarray(Y).reshape(-1)
        if lag < 1:
            lag = 1
        if len(X) != len(Y) or len(X) <= lag:
            return 0.0
        Y_now = Y[lag:]
        Y_past = Y[:-lag]
        X_past = X[:-lag]
        return _ksg_cmi(X_past, Y_now, Y_past, k=k)

    def pid(self, sources: Dict[str, np.ndarray], target: np.ndarray) -> Dict[str, Any]:
        # Simple unique proxy via MI drop on removal; proper PID to be implemented later
        feats = list(sources.keys())
        total = {f: self.mi(sources[f], target) for f in feats}
        unique = {
            f: max(
                0.0,
                total[f] - np.mean([v for k2, v in total.items() if k2 != f] or [0]),
            )
            for f in feats
        }
        return {"unique": unique, "redundant": {}, "synergy": {}}

    def phiid(
        self,
        sources: Dict[str, np.ndarray],
        target: np.ndarray,
        lags: Dict[str, int] | None = None,
    ) -> Dict[str, Any]:
        # Minimal transfer components via TE per source; proper ΦID pending
        comp = {}
        lags = lags or {}
        for name, X in sources.items():
            lag = int(lags.get(name, 1))
            comp[name] = {"transfer": self.te(X, target, lag=lag)}
        return {"components": comp}
