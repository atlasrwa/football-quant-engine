"""Distribution candidates for QFE V2 Layer 3.

These functions operate on already-produced expected counts. They answer a
separate question from team-strength estimation: given valid point-in-time
intensities, what observation distribution best describes realized counts?

Goals:
- independent Poisson anchor
- Dixon-Coles low-score dependence correction

Corners:
- independent Poisson anchor
- NB2 overdispersed count distribution

No market prices are inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import exp, isfinite, log
from typing import Callable, Iterable, Sequence

from scipy.stats import nbinom, poisson


EPS = 1e-15


def binary_log_loss(probability: float, outcome: bool) -> float:
    p = min(max(float(probability), EPS), 1.0 - EPS)
    return -log(p if outcome else 1.0 - p)


def poisson_joint_nll(
    home: int,
    away: int,
    lambda_home: float,
    lambda_away: float,
) -> float:
    return float(
        -poisson.logpmf(home, lambda_home)
        - poisson.logpmf(away, lambda_away)
    )


def dixon_coles_tau(
    home: int,
    away: int,
    lambda_home: float,
    lambda_away: float,
    rho: float,
) -> float:
    if home == 0 and away == 0:
        return 1.0 - lambda_home * lambda_away * rho
    if home == 0 and away == 1:
        return 1.0 + lambda_home * rho
    if home == 1 and away == 0:
        return 1.0 + lambda_away * rho
    if home == 1 and away == 1:
        return 1.0 - rho
    return 1.0


def dixon_coles_joint_nll(
    home: int,
    away: int,
    lambda_home: float,
    lambda_away: float,
    rho: float,
) -> float:
    tau = dixon_coles_tau(
        home,
        away,
        lambda_home,
        lambda_away,
        rho,
    )
    if tau <= 0.0 or not isfinite(tau):
        return float("inf")
    return poisson_joint_nll(
        home,
        away,
        lambda_home,
        lambda_away,
    ) - log(tau)


def _dc_cell_delta(
    home: int,
    away: int,
    lambda_home: float,
    lambda_away: float,
    rho: float,
) -> float:
    base = float(
        poisson.pmf(home, lambda_home)
        * poisson.pmf(away, lambda_away)
    )
    tau = dixon_coles_tau(
        home,
        away,
        lambda_home,
        lambda_away,
        rho,
    )
    return base * (tau - 1.0)


def dixon_coles_total_over_probability(
    lambda_home: float,
    lambda_away: float,
    line: float,
    rho: float,
) -> float:
    doubled = line * 2.0
    if abs(doubled - round(doubled)) > 1e-9 or float(line).is_integer():
        raise ValueError("development binary event scoring requires half-lines")

    threshold = int(line // 1)
    probability = float(poisson.sf(threshold, lambda_home + lambda_away))
    for home, away in ((0, 0), (0, 1), (1, 0), (1, 1)):
        if home + away > line:
            probability += _dc_cell_delta(
                home,
                away,
                lambda_home,
                lambda_away,
                rho,
            )
    return min(max(probability, 0.0), 1.0)


def dixon_coles_btts_probability(
    lambda_home: float,
    lambda_away: float,
    rho: float,
) -> float:
    probability = (
        (1.0 - exp(-lambda_home))
        * (1.0 - exp(-lambda_away))
    )
    probability += _dc_cell_delta(
        1,
        1,
        lambda_home,
        lambda_away,
        rho,
    )
    return min(max(probability, 0.0), 1.0)


def nb2_logpmf(count: int, mean: float, alpha: float) -> float:
    if count < 0 or mean <= 0 or alpha < 0:
        raise ValueError("invalid NB2 count/mean/alpha")
    if alpha == 0.0:
        return float(poisson.logpmf(count, mean))
    size = 1.0 / alpha
    probability = size / (size + mean)
    return float(nbinom.logpmf(count, size, probability))


def nb2_side_nll(
    home: int,
    away: int,
    lambda_home: float,
    lambda_away: float,
    alpha: float,
) -> float:
    return -(
        nb2_logpmf(home, lambda_home, alpha)
        + nb2_logpmf(away, lambda_away, alpha)
    )


def nb2_cdf(count: int, mean: float, alpha: float) -> float:
    if count < 0:
        return 0.0
    if alpha == 0.0:
        return float(poisson.cdf(count, mean))
    size = 1.0 / alpha
    probability = size / (size + mean)
    return float(nbinom.cdf(count, size, probability))


def nb2_side_over_probability(
    mean: float,
    line: float,
    alpha: float,
) -> float:
    doubled = line * 2.0
    if abs(doubled - round(doubled)) > 1e-9 or float(line).is_integer():
        raise ValueError("development binary event scoring requires half-lines")
    threshold = int(line // 1)
    return 1.0 - nb2_cdf(threshold, mean, alpha)


def nb2_total_over_probability(
    lambda_home: float,
    lambda_away: float,
    line: float,
    alpha: float,
) -> float:
    doubled = line * 2.0
    if abs(doubled - round(doubled)) > 1e-9 or float(line).is_integer():
        raise ValueError("development binary event scoring requires half-lines")
    threshold = int(line // 1)
    under_or_equal = 0.0
    for home in range(threshold + 1):
        if alpha == 0.0:
            p_home = float(poisson.pmf(home, lambda_home))
        else:
            size = 1.0 / alpha
            probability = size / (size + lambda_home)
            p_home = float(nbinom.pmf(home, size, probability))
        under_or_equal += p_home * nb2_cdf(
            threshold - home,
            lambda_away,
            alpha,
        )
    return min(max(1.0 - under_or_equal, 0.0), 1.0)


@dataclass(slots=True)
class OnlineGridSelector:
    """Choose the parameter with lowest cumulative prior NLL.

    Selection happens before the current outcome is observed. Ties are resolved
    by the declared grid order, which should put the conservative anchor first.
    """

    grid: tuple[float, ...]
    min_observations: int = 20
    _sum_nll: dict[float, float] = field(init=False, repr=False)
    _observations: int = field(init=False, default=0, repr=False)

    def __post_init__(self) -> None:
        if not self.grid:
            raise ValueError("grid cannot be empty")
        if len(set(self.grid)) != len(self.grid):
            raise ValueError("grid values must be unique")
        if self.min_observations < 0:
            raise ValueError("min_observations must be non-negative")
        self._sum_nll = {value: 0.0 for value in self.grid}
        self._observations = 0

    @property
    def observations(self) -> int:
        return self._observations

    @property
    def selected(self) -> float:
        if self._observations < self.min_observations:
            return self.grid[0]
        return min(
            self.grid,
            key=lambda value: (
                self._sum_nll[value],
                self.grid.index(value),
            ),
        )

    def cumulative_nll(self) -> dict[float, float]:
        return dict(self._sum_nll)

    def update(
        self,
        loss_by_parameter: Callable[[float], float],
    ) -> None:
        for value in self.grid:
            loss = float(loss_by_parameter(value))
            if not isfinite(loss):
                loss = 1e12
            self._sum_nll[value] += loss
        self._observations += 1
