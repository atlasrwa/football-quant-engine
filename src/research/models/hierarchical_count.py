"""Coherent count models for pooled, league-only, and hierarchical forecasts.

The three arms deliberately share :class:`CountRegressionModel` for all count
regression fitting.  The hierarchical arm adds only an empirical-Bayes league
intercept to the pooled fitted intensity; it does not duplicate the underlying
Poisson/negative-binomial fit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from scipy.stats import nbinom, poisson

from src.research.models.count_regression import (
    CountRegressionModel,
    DistributionType,
)

POOLED_ARM = "pooled"
INDEPENDENT_ARM = "independent"
HIERARCHICAL_ARM = "hierarchical"
COUNT_ARMS = (POOLED_ARM, INDEPENDENT_ARM, HIERARCHICAL_ARM)


@dataclass(frozen=True, slots=True)
class CountMarketSpec:
    """One count process, evaluated at any number of O/U lines."""

    name: str
    target_field: str
    lines: tuple[float, ...]
    feature_fields: tuple[str, ...]
    distribution: str = DistributionType.AUTO
    use_team_effects: bool = True

    def __post_init__(self) -> None:
        if not self.name or not self.target_field:
            raise ValueError("market name and target_field are required")
        if not self.lines:
            raise ValueError("at least one evaluation line is required")
        if len(set(self.lines)) != len(self.lines):
            raise ValueError("market lines must be unique")


@dataclass(frozen=True, slots=True)
class PredictiveCountDistribution:
    """A fitted Poisson or NB2 distribution with arbitrary-line tails."""

    mean: float
    distribution: str
    dispersion: float = 0.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.mean) or self.mean <= 0.0:
            raise ValueError("mean must be finite and positive")
        if self.distribution not in (
            DistributionType.POISSON,
            DistributionType.NEGATIVE_BINOMIAL,
        ):
            raise ValueError(f"unsupported count distribution: {self.distribution}")
        if self.distribution == DistributionType.NEGATIVE_BINOMIAL:
            if not math.isfinite(self.dispersion) or self.dispersion <= 0.0:
                raise ValueError("negative-binomial dispersion must be positive")

    def p_over(self, line: float) -> float:
        """Return ``P(count > line)`` from this one coherent distribution."""
        cutoff = math.floor(line)
        if self.distribution == DistributionType.NEGATIVE_BINOMIAL:
            shape = 1.0 / self.dispersion
            success = shape / (shape + self.mean)
            value = 1.0 - float(nbinom.cdf(cutoff, shape, success))
        else:
            value = 1.0 - float(poisson.cdf(cutoff, self.mean))
        return min(1.0, max(0.0, value))

    def pmf(self, max_count: int) -> tuple[float, ...]:
        """Return masses 0..max_count, with the final bin including the tail."""
        if max_count < 1:
            raise ValueError("max_count must be at least 1")
        values: list[float] = []
        if self.distribution == DistributionType.NEGATIVE_BINOMIAL:
            shape = 1.0 / self.dispersion
            success = shape / (shape + self.mean)
            values = [float(nbinom.pmf(k, shape, success)) for k in range(max_count)]
        else:
            values = [float(poisson.pmf(k, self.mean)) for k in range(max_count)]
        values.append(max(0.0, 1.0 - sum(values)))
        total = sum(values)
        return tuple(value / total for value in values)


@dataclass(frozen=True, slots=True)
class EmpiricalBayesLeagueEffect:
    """Posterior league offset and its explicit shrinkage diagnostics."""

    raw_log_offset: float
    posterior_log_offset: float
    sampling_variance: float
    prior_variance: float
    shrinkage_weight: float
    n_observations: int


class LeagueCountModel:
    """Fit pooled, league-only, and empirical-Bayes partial-pooling arms.

    Rows must carry the market target and a league label under ``league_field``.
    The pooled and independent arms are ordinary ``CountRegressionModel`` fits.
    For the hierarchical arm, pooled expected counts are treated as exposures.
    A league's log observed/exposure ratio has approximate sampling variance
    ``1 / observed_count`` and a zero-centred normal prior whose variance is
    estimated across leagues by method of moments.  The posterior offset is
    therefore ``tau² / (tau² + s²) * raw_offset``: an explicit empirical-Bayes
    partial-pooling estimate.  Applying that offset to the pooled intensity
    preserves one coherent Poisson/NB2 distribution at every requested line.
    """

    def __init__(self, spec: CountMarketSpec, *, league_field: str = "_league") -> None:
        self.spec = spec
        self.league_field = league_field
        self.pooled_model: CountRegressionModel | None = None
        self.independent_models: dict[str, CountRegressionModel] = {}
        self.league_effects: dict[str, EmpiricalBayesLeagueEffect] = {}
        self.prior_variance = 0.0

    @property
    def is_fitted(self) -> bool:
        return self.pooled_model is not None and self.pooled_model.params is not None

    def _new_model(self) -> CountRegressionModel:
        return CountRegressionModel(
            target_field=self.spec.target_field,
            line=self.spec.lines[0],
            distribution=self.spec.distribution,
            feature_fields=self.spec.feature_fields,
            use_team_effects=self.spec.use_team_effects,
        )

    def fit(self, rows: Sequence[Mapping[str, object]]) -> None:
        valid = [dict(row) for row in rows if self._valid_target(row)]
        if not valid:
            raise ValueError(f"no valid training rows for {self.spec.name}")

        pooled = self._new_model()
        pooled.fit(valid, [False] * len(valid))
        if pooled.params is None:
            raise ValueError(f"pooled model did not fit for {self.spec.name}")
        self.pooled_model = pooled

        by_league: dict[str, list[dict[str, object]]] = {}
        for row in valid:
            league = self._league(row)
            by_league.setdefault(league, []).append(row)

        self.independent_models = {}
        raw_effects: dict[str, tuple[float, float, int]] = {}
        for league, league_rows in sorted(by_league.items()):
            model = self._new_model()
            model.fit(league_rows, [False] * len(league_rows))
            if model.params is not None:
                self.independent_models[league] = model

            observed = sum(float(row[self.spec.target_field]) for row in league_rows)
            exposure = sum(pooled.predict_expected_count(row) for row in league_rows)
            # Half-count continuity correction keeps sparse/zero leagues finite.
            raw_offset = math.log((observed + 0.5) / (exposure + 0.5))
            sampling_variance = 1.0 / (observed + 0.5)
            raw_effects[league] = (raw_offset, sampling_variance, len(league_rows))

        if len(raw_effects) > 1:
            offsets = [value[0] for value in raw_effects.values()]
            mean_offset = sum(offsets) / len(offsets)
            between_variance = sum((x - mean_offset) ** 2 for x in offsets) / (
                len(offsets) - 1
            )
            mean_sampling_variance = sum(value[1] for value in raw_effects.values()) / len(
                raw_effects
            )
            self.prior_variance = max(0.0, between_variance - mean_sampling_variance)
        else:
            self.prior_variance = 0.0

        self.league_effects = {}
        for league, (raw_offset, sampling_variance, n_obs) in raw_effects.items():
            denominator = self.prior_variance + sampling_variance
            weight = self.prior_variance / denominator if denominator > 0.0 else 0.0
            self.league_effects[league] = EmpiricalBayesLeagueEffect(
                raw_log_offset=raw_offset,
                posterior_log_offset=weight * raw_offset,
                sampling_variance=sampling_variance,
                prior_variance=self.prior_variance,
                shrinkage_weight=weight,
                n_observations=n_obs,
            )

    def predict_distribution(
        self,
        row: Mapping[str, object],
        *,
        arm: str,
    ) -> PredictiveCountDistribution:
        """Return an arm's distribution; all lines must be derived from it."""
        if arm not in COUNT_ARMS:
            raise ValueError(f"unknown arm {arm!r}; expected one of {COUNT_ARMS}")
        if self.pooled_model is None or self.pooled_model.params is None:
            raise RuntimeError("model must be fitted before prediction")

        league = self._league(row)
        if arm == INDEPENDENT_ARM:
            model = self.independent_models.get(league)
            if model is None or model.params is None:
                raise KeyError(f"no independent model for league {league!r}")
            return self._distribution_from_model(model, row)

        pooled_distribution = self._distribution_from_model(self.pooled_model, row)
        if arm == POOLED_ARM:
            return pooled_distribution

        effect = self.league_effects.get(league)
        if effect is None:
            raise KeyError(f"no empirical-Bayes effect for league {league!r}")
        mean = pooled_distribution.mean * math.exp(effect.posterior_log_offset)
        mean = min(math.exp(4.0), max(math.exp(-3.0), mean))
        return PredictiveCountDistribution(
            mean=mean,
            distribution=pooled_distribution.distribution,
            dispersion=pooled_distribution.dispersion,
        )

    def predict_over(
        self,
        row: Mapping[str, object],
        *,
        arm: str,
        line: float,
    ) -> float:
        return self.predict_distribution(row, arm=arm).p_over(line)

    def _distribution_from_model(
        self, model: CountRegressionModel, row: Mapping[str, object]
    ) -> PredictiveCountDistribution:
        params = model.params
        if params is None:
            raise RuntimeError("underlying CountRegressionModel is not fitted")
        dispersion = params.dispersion
        distribution = params.distribution
        if distribution == DistributionType.NEGATIVE_BINOMIAL and dispersion <= 0.0:
            distribution = DistributionType.POISSON
            dispersion = 0.0
        return PredictiveCountDistribution(
            mean=model.predict_expected_count(row),
            distribution=distribution,
            dispersion=dispersion,
        )

    def _valid_target(self, row: Mapping[str, object]) -> bool:
        value = row.get(self.spec.target_field)
        try:
            return value is not None and math.isfinite(float(value)) and float(value) >= 0.0
        except (TypeError, ValueError):
            return False

    def _league(self, row: Mapping[str, object]) -> str:
        value = row.get(self.league_field)
        if value is None or str(value) == "":
            raise ValueError(f"row is missing league field {self.league_field!r}")
        return str(value)
