"""Structured count-distribution candidates for QFE V2 Layer 3.

These adapters sit above target-specific expected counts. They do not alter the
independent football-information path; they only ask whether a better outcome
distribution improves proper scoring once a pre-match mean is already known.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite, log
from typing import Iterable

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import gammaln
from scipy.stats import nbinom, poisson


@dataclass(frozen=True, slots=True)
class NB2Fit:
    alpha: float
    n_observations: int
    objective: float


@dataclass(frozen=True, slots=True)
class DixonColesRhoFit:
    rho: float
    n_observations: int
    objective: float


def poisson_count_logpmf(count: int, mean: float) -> float:
    if count < 0 or mean <= 0 or not isfinite(mean):
        raise ValueError("invalid count/mean")
    return float(poisson.logpmf(count, mean))


def nb2_logpmf(count: int, mean: float, alpha: float) -> float:
    """NB2 log-PMF where Var[Y]=mu+alpha*mu^2."""
    if count < 0 or mean <= 0 or alpha <= 0:
        raise ValueError("invalid NB2 parameters")
    r = 1.0 / alpha
    p = r / (r + mean)
    return float(
        gammaln(count + r)
        - gammaln(r)
        - gammaln(count + 1)
        + r * log(p)
        + count * log(1.0 - p)
    )


def nb2_pmf(count: int, mean: float, alpha: float) -> float:
    if count < 0:
        return 0.0
    if mean <= 0 or alpha <= 0:
        raise ValueError("invalid NB2 parameters")
    r = 1.0 / alpha
    p = r / (r + mean)
    return float(nbinom.pmf(count, r, p))


def nb2_cdf(count: int, mean: float, alpha: float) -> float:
    if mean <= 0 or alpha <= 0:
        raise ValueError("invalid NB2 parameters")
    if count < 0:
        return 0.0
    r = 1.0 / alpha
    p = r / (r + mean)
    return float(nbinom.cdf(count, r, p))


def nb2_total_pmf_from_sides(
    total: int,
    lambda_home: float,
    lambda_away: float,
    alpha: float,
) -> float:
    """Total-count PMF from two independent NB2 side counts with common alpha."""
    if total < 0:
        return 0.0
    return float(sum(
        nb2_pmf(home, lambda_home, alpha)
        * nb2_pmf(total - home, lambda_away, alpha)
        for home in range(total + 1)
    ))


def nb2_total_under_probability_from_sides(
    line: float,
    lambda_home: float,
    lambda_away: float,
    alpha: float,
) -> float:
    doubled = line * 2
    if abs(doubled - round(doubled)) > 1e-9:
        raise ValueError("only integer/half lines supported")
    max_total = int(line) - 1 if float(line).is_integer() else int(line // 1)
    if max_total < 0:
        return 0.0
    return float(sum(
        nb2_total_pmf_from_sides(total, lambda_home, lambda_away, alpha)
        for total in range(max_total + 1)
    ))


def fit_nb2_dispersion(
    observations: Iterable[tuple[float, int]],
    *,
    alpha_bounds: tuple[float, float] = (1e-4, 3.0),
) -> NB2Fit:
    rows = [(float(mu), int(y)) for mu, y in observations if mu > 0 and y >= 0]
    if len(rows) < 20:
        raise ValueError("at least 20 observations required to fit NB2 dispersion")
    lo, hi = alpha_bounds
    if not 0 < lo < hi:
        raise ValueError("invalid alpha bounds")

    def objective(log_alpha: float) -> float:
        alpha = exp(log_alpha)
        return -sum(nb2_logpmf(y, mu, alpha) for mu, y in rows)

    result = minimize_scalar(
        objective,
        bounds=(log(lo), log(hi)),
        method="bounded",
        options={"xatol": 1e-8, "maxiter": 500},
    )
    if not result.success:
        raise RuntimeError(f"NB2 dispersion fit failed: {result.message}")
    alpha = exp(float(result.x))
    return NB2Fit(
        alpha=alpha,
        n_observations=len(rows),
        objective=float(result.fun),
    )


def _dc_tau(
    home_goals: int,
    away_goals: int,
    lambda_home: float,
    lambda_away: float,
    rho: float,
) -> float:
    if home_goals == 0 and away_goals == 0:
        return 1.0 - lambda_home * lambda_away * rho
    if home_goals == 0 and away_goals == 1:
        return 1.0 + lambda_home * rho
    if home_goals == 1 and away_goals == 0:
        return 1.0 + lambda_away * rho
    if home_goals == 1 and away_goals == 1:
        return 1.0 - rho
    return 1.0


def dixon_coles_joint_logpmf(
    home_goals: int,
    away_goals: int,
    lambda_home: float,
    lambda_away: float,
    rho: float,
) -> float:
    if min(home_goals, away_goals) < 0:
        raise ValueError("goal counts must be non-negative")
    if lambda_home <= 0 or lambda_away <= 0:
        raise ValueError("goal rates must be positive")
    tau = _dc_tau(
        home_goals,
        away_goals,
        lambda_home,
        lambda_away,
        rho,
    )
    if tau <= 0 or not isfinite(tau):
        return float("-inf")
    return float(
        poisson.logpmf(home_goals, lambda_home)
        + poisson.logpmf(away_goals, lambda_away)
        + log(tau)
    )


def fit_dixon_coles_rho(
    observations: Iterable[tuple[float, float, int, int]],
    *,
    rho_bounds: tuple[float, float] = (-0.20, 0.20),
) -> DixonColesRhoFit:
    rows = [
        (float(lh), float(la), int(hg), int(ag))
        for lh, la, hg, ag in observations
        if lh > 0 and la > 0 and hg >= 0 and ag >= 0
    ]
    if len(rows) < 50:
        raise ValueError("at least 50 observations required to fit Dixon-Coles rho")
    lo, hi = rho_bounds
    if not lo < hi:
        raise ValueError("invalid rho bounds")

    def objective(rho: float) -> float:
        total = 0.0
        for lh, la, hg, ag in rows:
            ll = dixon_coles_joint_logpmf(hg, ag, lh, la, rho)
            if not isfinite(ll):
                return 1e100
            total -= ll
        return total

    result = minimize_scalar(
        objective,
        bounds=(lo, hi),
        method="bounded",
        options={"xatol": 1e-8, "maxiter": 500},
    )
    if not result.success:
        raise RuntimeError(f"Dixon-Coles rho fit failed: {result.message}")
    return DixonColesRhoFit(
        rho=float(result.x),
        n_observations=len(rows),
        objective=float(result.fun),
    )


def dixon_coles_total_pmf(
    total_goals: int,
    lambda_home: float,
    lambda_away: float,
    rho: float,
) -> float:
    if total_goals < 0:
        return 0.0
    return float(sum(
        exp(dixon_coles_joint_logpmf(
            home,
            total_goals - home,
            lambda_home,
            lambda_away,
            rho,
        ))
        for home in range(total_goals + 1)
    ))


def dixon_coles_under_probability(
    line: float,
    lambda_home: float,
    lambda_away: float,
    rho: float,
) -> float:
    """Win probability for under at integer/half total-goal lines."""
    doubled = line * 2
    if abs(doubled - round(doubled)) > 1e-9:
        raise ValueError("only integer/half lines supported")
    max_total = int(line) - 1 if float(line).is_integer() else int(line // 1)
    if max_total < 0:
        return 0.0
    return float(sum(
        dixon_coles_total_pmf(total, lambda_home, lambda_away, rho)
        for total in range(max_total + 1)
    ))



def independent_btts_probability(lambda_home: float, lambda_away: float) -> float:
    if lambda_home <= 0 or lambda_away <= 0:
        raise ValueError("goal rates must be positive")
    return float((1.0 - exp(-lambda_home)) * (1.0 - exp(-lambda_away)))


def dixon_coles_btts_probability(
    lambda_home: float,
    lambda_away: float,
    rho: float,
) -> float:
    """BTTS probability under the Dixon-Coles low-score correction."""
    base = independent_btts_probability(lambda_home, lambda_away)
    p11 = float(poisson.pmf(1, lambda_home) * poisson.pmf(1, lambda_away))
    corrected = base - rho * p11  # tau(1,1)=1-rho; all other BTTS cells unchanged.
    return min(max(corrected, 0.0), 1.0)

def binary_log_loss(probability: float, outcome: bool, eps: float = 1e-12) -> float:
    p = min(max(float(probability), eps), 1.0 - eps)
    return float(-log(p if outcome else 1.0 - p))


def brier_score(probability: float, outcome: bool) -> float:
    return float((float(probability) - float(outcome)) ** 2)
