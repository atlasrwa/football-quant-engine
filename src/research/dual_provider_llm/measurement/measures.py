"""Frozen statistics and null procedures. Defined here; executed only by the gated runner.

Each inferential primary has exactly one null, with N_RESAMPLES resamples and a fresh
numpy.random.default_rng(RNG_SEED):
  group_difference      two-sided group-label permutation of mean(A) - mean(B)
  interaction_coef      Freedman-Lane residual permutation for the product-term coefficient
  rank_association      two-sided outcome permutation of Spearman's rho
Two-sided permutation p = (1 + #{|T_perm| >= |T_obs|}) / (1 + N_RESAMPLES).
"""
from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np

from src.research.dual_provider_llm.measurement import support as S


def _rng():
    return np.random.default_rng(int(S.value("RNG_SEED")))


def _p(obs: float, perms: np.ndarray) -> float:
    return float((1 + np.sum(np.abs(perms) >= abs(obs) - 1e-15)) / (1 + len(perms)))


def group_difference(a: Sequence[float], b: Sequence[float]) -> Dict[str, float]:
    a, b = np.asarray(a, float), np.asarray(b, float)
    obs = float(a.mean() - b.mean())
    pool = np.concatenate([a, b])
    rng = _rng()
    perms = np.empty(int(S.value("N_RESAMPLES")))
    for i in range(len(perms)):
        x = rng.permutation(pool)
        perms[i] = x[:len(a)].mean() - x[len(a):].mean()
    return {"statistic": obs, "p_two_sided": _p(obs, perms), "n_a": int(len(a)),
            "n_b": int(len(b)), "null": "group_label_permutation"}


def _ols(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.linalg.lstsq(X, y, rcond=None)[0]


def interaction_coef(x1: Sequence[float], x2: Sequence[float], y: Sequence[float]
                     ) -> Dict[str, float]:
    """y ~ 1 + x1 + x2 + x1*x2 ; coefficient of x1*x2 with a Freedman-Lane null."""
    x1, x2, y = (np.asarray(v, float) for v in (x1, x2, y))
    X = np.column_stack([np.ones_like(x1), x1, x2, x1 * x2])
    Xr = X[:, :3]
    beta = _ols(X, y)
    fit_r = Xr @ _ols(Xr, y)
    resid_r = y - fit_r
    rng = _rng()
    perms = np.empty(int(S.value("N_RESAMPLES")))
    for i in range(len(perms)):
        perms[i] = _ols(X, fit_r + rng.permutation(resid_r))[3]
    return {"statistic": float(beta[3]), "p_two_sided": _p(float(beta[3]), perms),
            "n": int(len(y)), "n_parameters": 4, "null": "freedman_lane_residual_permutation"}


def _rank(v: np.ndarray) -> np.ndarray:
    order = np.argsort(v, kind="mergesort")
    r = np.empty(len(v))
    r[order] = np.arange(len(v))
    # average ranks for ties
    vs = v[order]
    i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and vs[j + 1] == vs[i]:
            j += 1
        r[order[i:j + 1]] = (i + j) / 2.0
        i = j + 1
    return r


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    rx, ry = _rank(np.asarray(x, float)), _rank(np.asarray(y, float))
    return float(np.corrcoef(rx, ry)[0, 1])


def rank_association(x: Sequence[float], y: Sequence[float]) -> Dict[str, float]:
    x, y = np.asarray(x, float), np.asarray(y, float)
    obs = spearman(x, y)
    rng = _rng()
    perms = np.array([spearman(x, rng.permutation(y)) for _ in range(int(S.value("N_RESAMPLES")))])
    return {"statistic": obs, "p_two_sided": _p(obs, perms), "n": int(len(x)),
            "null": "outcome_permutation"}


def residualize(y: Sequence[float], x: Sequence[float]) -> List[float]:
    y, x = np.asarray(y, float), np.asarray(x, float)
    X = np.column_stack([np.ones_like(x), x])
    return list(y - X @ _ols(X, y))


def block_percentile(recent: float, historical_blocks: Sequence[float]) -> Dict[str, float]:
    """DESCRIPTIVE ONLY (not a p-value; excluded from BH): share of disjoint historical blocks
    whose statistic is <= the recent block's."""
    h = np.asarray(historical_blocks, float)
    return {"statistic": float(recent), "percentile_among_disjoint_blocks":
            float(np.mean(h <= recent)) if len(h) else float("nan"),
            "n_blocks": int(len(h)), "inferential": False}


def bh_adjust(pvals: Sequence[float]) -> List[float]:
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    q, running = [0.0] * m, 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, pvals[i] * m / rank)
        q[i] = min(1.0, running)
    return q
