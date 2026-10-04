"""Conway-Maxwell-Poisson distribution utilities for QFE V2.1.

CMP generalizes Poisson with dispersion parameter nu:
- nu = 1: Poisson,
- nu < 1: over-dispersion,
- nu > 1: under-dispersion.

QFE parameterizes CMP by predictive mean rather than the native lambda
parameter. For each requested mean/nu pair, lambda is solved deterministically
so model-location comparisons remain like-for-like.

The implementation is finite-support with explicit tail checks and fails
closed if adequate normalization cannot be established.
"""
from __future__ import annotations

from functools import lru_cache
from math import ceil, isfinite, log, sqrt

import numpy as np
from scipy.optimize import brentq
from scipy.special import gammaln
from scipy.stats import poisson

CMP_VERSION = "qfe-cmp-mean-parameterized-v1"
_DEFAULT_MAX_COUNT = 120
_MAX_SUPPORT = 480
_TAIL_TOLERANCE = 1e-11


def _validate(mean: float, nu: float) -> tuple[float, float]:
    mean = float(mean)
    nu = float(nu)
    if not isfinite(mean) or mean <= 0:
        raise ValueError("CMP mean must be positive and finite")
    if not isfinite(nu) or nu <= 0:
        raise ValueError("CMP nu must be positive and finite")
    return mean, nu


def _minimum_support(mean: float) -> int:
    # Count targets in QFE are low-count, but over-dispersed CMP tails can be
    # materially wider than Poisson. This conservative starting support keeps
    # truncation error far below the scoring precision used by the engine.
    return min(
        _MAX_SUPPORT,
        max(
            _DEFAULT_MAX_COUNT,
            int(ceil(mean + 18.0 * sqrt(mean + mean * mean) + 20.0)),
        ),
    )


def _normalized_weights(
    log_lambda: float,
    nu: float,
    support: int,
) -> np.ndarray:
    k = np.arange(support + 1, dtype=float)
    log_weights = k * float(log_lambda) - float(nu) * gammaln(k + 1.0)
    max_log = float(np.max(log_weights))
    weights = np.exp(log_weights - max_log)
    total = float(weights.sum())
    if not isfinite(total) or total <= 0:
        raise FloatingPointError("invalid CMP normalizer")
    return weights / total


def _truncated_mean(log_lambda: float, nu: float, support: int) -> float:
    probabilities = _normalized_weights(log_lambda, nu, support)
    k = np.arange(len(probabilities), dtype=float)
    return float(np.dot(k, probabilities))


def _solve_log_lambda(mean: float, nu: float, support: int) -> float:
    if abs(nu - 1.0) <= 1e-14:
        return log(mean)

    def objective(log_lambda: float) -> float:
        return _truncated_mean(log_lambda, nu, support) - mean

    lower = -25.0
    upper = max(5.0, nu * log(mean + 1.0) + 4.0)
    lower_value = objective(lower)
    upper_value = objective(upper)
    while upper_value <= 0.0 and upper < 30.0:
        upper += 2.0
        upper_value = objective(upper)
    if lower_value >= 0.0 or upper_value <= 0.0:
        raise RuntimeError(
            "unable to bracket CMP mean parameterization "
            f"(mean={mean}, nu={nu}, support={support})"
        )
    return float(
        brentq(
            objective,
            lower,
            upper,
            xtol=1e-10,
            rtol=1e-10,
            maxiter=100,
        )
    )


@lru_cache(maxsize=200_000)
def _cached_pmf(
    mean_key: float,
    nu_key: float,
) -> tuple[float, ...]:
    mean, nu = _validate(mean_key, nu_key)
    if abs(nu - 1.0) <= 1e-14:
        support = _minimum_support(mean)
        probabilities = poisson.pmf(np.arange(support + 1), mean).astype(float)
        tail = max(0.0, 1.0 - float(probabilities.sum()))
        if tail > _TAIL_TOLERANCE:
            while tail > _TAIL_TOLERANCE and support < _MAX_SUPPORT:
                support = min(_MAX_SUPPORT, support * 2)
                probabilities = poisson.pmf(
                    np.arange(support + 1),
                    mean,
                ).astype(float)
                tail = max(0.0, 1.0 - float(probabilities.sum()))
        if tail > _TAIL_TOLERANCE:
            raise RuntimeError("Poisson reference tail exceeds support contract")
        probabilities /= probabilities.sum()
        return tuple(float(x) for x in probabilities)

    support = _minimum_support(mean)
    while True:
        log_lambda = _solve_log_lambda(mean, nu, support)
        probabilities = _normalized_weights(log_lambda, nu, support)
        tail_edge = float(probabilities[-6:].sum())
        if tail_edge <= _TAIL_TOLERANCE:
            implied_mean = float(
                np.dot(
                    np.arange(len(probabilities), dtype=float),
                    probabilities,
                )
            )
            if abs(implied_mean - mean) > 2e-7 * max(1.0, mean):
                raise RuntimeError("CMP mean parameterization tolerance failed")
            return tuple(float(x) for x in probabilities)
        if support >= _MAX_SUPPORT:
            raise RuntimeError(
                "CMP tail remains material at maximum support "
                f"(mean={mean}, nu={nu})"
            )
        support = min(_MAX_SUPPORT, support * 2)


def cmp_pmf_vector(mean: float, nu: float) -> np.ndarray:
    """Return normalized CMP probabilities on an audited finite support."""
    mean, nu = _validate(mean, nu)
    # Rounding is far below model scoring precision and allows repeated fold
    # calculations for identical frozen forecasts to share deterministic cache.
    key_mean = round(mean, 10)
    key_nu = round(nu, 10)
    return np.asarray(_cached_pmf(key_mean, key_nu), dtype=float)


def cmp_logpmf(observed: int, mean: float, nu: float) -> float:
    if isinstance(observed, bool) or observed < 0 or int(observed) != observed:
        raise ValueError("observed count must be a non-negative integer")
    probabilities = cmp_pmf_vector(mean, nu)
    observed = int(observed)
    if observed >= len(probabilities):
        raise RuntimeError("observed count lies outside audited CMP support")
    probability = max(float(probabilities[observed]), 1e-300)
    return float(log(probability))


def convolve_count_pmfs(
    home: np.ndarray,
    away: np.ndarray,
) -> np.ndarray:
    home = np.asarray(home, dtype=float)
    away = np.asarray(away, dtype=float)
    if home.ndim != 1 or away.ndim != 1:
        raise ValueError("count PMFs must be one-dimensional")
    if np.any(home < 0) or np.any(away < 0):
        raise ValueError("count PMFs cannot contain negative mass")
    hs = float(home.sum())
    as_ = float(away.sum())
    if abs(hs - 1.0) > 1e-8 or abs(as_ - 1.0) > 1e-8:
        raise ValueError("count PMFs must be normalized")
    total = np.convolve(home, away)
    total /= total.sum()
    return total


def discrete_rps(probabilities: np.ndarray, observed: int) -> float:
    """Ranked probability score for a discrete count forecast."""
    probabilities = np.asarray(probabilities, dtype=float)
    if probabilities.ndim != 1 or len(probabilities) == 0:
        raise ValueError("probabilities must be a non-empty vector")
    if isinstance(observed, bool) or observed < 0 or int(observed) != observed:
        raise ValueError("observed count must be a non-negative integer")
    if observed >= len(probabilities):
        raise RuntimeError("observed count lies outside probability support")
    cdf = np.cumsum(probabilities)
    k = np.arange(len(probabilities))
    empirical = (k >= int(observed)).astype(float)
    return float(np.sum((cdf - empirical) ** 2))


def probability_over(probabilities: np.ndarray, line: float) -> float:
    if line < 0 or abs(line * 2 - round(line * 2)) > 1e-9:
        raise ValueError("line must be a non-negative integer/half line")
    threshold = int(line)
    probabilities = np.asarray(probabilities, dtype=float)
    if threshold >= len(probabilities):
        return 0.0
    return float(probabilities[threshold + 1 :].sum())
