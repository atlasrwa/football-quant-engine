"""Hierarchical count model: one fit per market family, every line read off it.

Structure, from the top down:

    log mu_side = beta0 + x . beta                 global intercept and slopes
                + u_league                         league intercept, partially pooled
                + sum_k delta_[league,k] x_k       league slope deviations, strongly shrunk
                + attack_[counting team]           team attack state, nested in league
                + concede_[opposing team]          team concede state, nested in league

Each match yields **two** side observations, so the match total is the convolution
of the two fitted side distributions. Three things follow from that, and they are
the reasons the model is built this way rather than as a total-count model:

1. **Every line comes from one PMF.** ``P(over 7.5) >= P(over 8.5) >= ...`` holds
   arithmetically, not by luck. It is the survival function of a single
   distribution evaluated at increasing cutoffs.
2. **Both teams to score falls out.** ``P(home >= 1) * P(away >= 1)`` is read off
   the same two side distributions that produce the goals lines, so BTTS cannot
   contradict over 2.5 the way a separately fitted classifier can.
3. **Attack and defence are separable.** A corner happens because one side creates
   pressure and the other yields it; modelling the total directly cannot tell
   those apart, and the explanation layer needs them apart to say anything in
   football terms.

Partial pooling is what makes this usable for a team with four matches. Every
random effect is an empirical-Bayes posterior ``w * raw + (1 - w) * prior_mean``
with ``w = tau^2 / (tau^2 + s^2)``. Thin evidence means a large sampling variance
``s^2``, a small ``w``, and an estimate close to the prior — the league for a team,
the global fit for a league. Nobody abstains and nothing is a coin flip; the
estimate is informative and its uncertainty is wide, and the uncertainty is
carried into the published probability rather than reported beside it.

**Prior-season data enters here and only here.** A team's prior for the current
season is its previous-season posterior multiplied by a decay factor that falls as
current-season matches accumulate. That is a prior, and it is recorded as one. It
is *not* padding a rolling window with last season's matches — the bug that
invalidated every forecast published before the corpus fix. The rolling windows in
:mod:`src.research.prediction_engine.form_window` never cross a season boundary,
and this module never touches them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Mapping, Optional, Sequence

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import nbinom, poisson

from src.research.models.market_family import MarketFamily

POISSON = "poisson"
NEGATIVE_BINOMIAL = "negative_binomial"

#: Hard bound on log mu, so a pathological feature row cannot produce a mean of
#: 10^6 corners. Matches the convention already used by CountRegressionModel.
_LOG_MEAN_FLOOR = -4.0
_LOG_MEAN_CEILING = 3.5


# ─────────────────────────────────────────────────────────────────────────────
# Predictive distributions
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class SideCountDistribution:
    """One side's count distribution: Poisson or NB2 (``Var = mu + alpha mu^2``)."""

    mean: float
    distribution: str
    dispersion: float = 0.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.mean) or self.mean <= 0.0:
            raise ValueError(f"side mean must be finite and positive, got {self.mean!r}")
        if self.distribution not in (POISSON, NEGATIVE_BINOMIAL):
            raise ValueError(f"unsupported distribution {self.distribution!r}")
        if self.distribution == NEGATIVE_BINOMIAL and not (
            math.isfinite(self.dispersion) and self.dispersion > 0.0
        ):
            raise ValueError("negative-binomial dispersion must be finite and positive")

    def pmf(self, max_count: int) -> np.ndarray:
        """Masses for 0..max_count; the final bin absorbs the upper tail."""
        if max_count < 1:
            raise ValueError("max_count must be at least 1")
        counts = np.arange(max_count, dtype=float)
        if self.distribution == NEGATIVE_BINOMIAL:
            shape = 1.0 / self.dispersion
            success = shape / (shape + self.mean)
            masses = nbinom.pmf(counts, shape, success)
        else:
            masses = poisson.pmf(counts, self.mean)
        masses = np.asarray(masses, dtype=float)
        tail = max(0.0, 1.0 - float(masses.sum()))
        full = np.concatenate([masses, [tail]])
        total = float(full.sum())
        return full / total if total > 0 else full

    def p_zero(self) -> float:
        if self.distribution == NEGATIVE_BINOMIAL:
            shape = 1.0 / self.dispersion
            success = shape / (shape + self.mean)
            return float(nbinom.pmf(0, shape, success))
        return float(poisson.pmf(0, self.mean))

    def p_at_least_one(self) -> float:
        return min(1.0, max(0.0, 1.0 - self.p_zero()))


@dataclass(frozen=True, slots=True)
class UncertainSideDistribution:
    """A side distribution mixed over the model's uncertainty about ``log mu``.

    A team with four matches and a team with thirty can produce the same point
    estimate of ``mu``. They should not produce the same probability. The
    empirical-Bayes posterior variance of the random effects gives the model's own
    uncertainty about ``log mu``; integrating the count distribution over that
    variance pulls the resulting probabilities toward the base rate in proportion
    to how thin the evidence is.

    The mixture is a Gauss-Hermite quadrature over ``log mu``, which keeps this
    exact enough at 5 nodes and — crucially — keeps every line monotone, because a
    convex combination of non-increasing survival functions is non-increasing.
    """

    components: tuple[tuple[float, SideCountDistribution], ...]
    log_mean_variance: float

    def __post_init__(self) -> None:
        if not self.components:
            raise ValueError("at least one mixture component is required")
        total = sum(weight for weight, _ in self.components)
        if not math.isfinite(total) or abs(total - 1.0) > 1e-6:
            raise ValueError(f"mixture weights must sum to 1, got {total!r}")

    @property
    def mean(self) -> float:
        return sum(weight * component.mean for weight, component in self.components)

    def pmf(self, max_count: int) -> np.ndarray:
        stacked = np.zeros(max_count + 1, dtype=float)
        for weight, component in self.components:
            stacked += weight * component.pmf(max_count)
        total = float(stacked.sum())
        return stacked / total if total > 0 else stacked

    def p_at_least_one(self) -> float:
        return sum(
            weight * component.p_at_least_one() for weight, component in self.components
        )


def _gauss_hermite_mixture(
    log_mean: float,
    log_mean_variance: float,
    distribution: str,
    dispersion: float,
    *,
    nodes: int = 5,
) -> UncertainSideDistribution:
    """Mix a side distribution over a normal uncertainty on ``log mu``.

    **Mean-preserving.** Mixing over ``log mu`` without correction inflates the
    mean by ``exp(variance / 2)`` — Jensen's inequality, since ``exp`` is convex.
    At the variance cap that is a 13% inflation of every expected count, which
    biases every ``P(over)`` upward, and it biases them *most* for the thin teams
    the widening exists to serve. The audit in ``scripts/audit_calibration.py``
    caught this as a systematic over-bias whose size tracked posterior variance
    across families (cards +0.036, corners −0.001, in the same order as their
    shrinkage variances). Subtracting ``variance / 2`` from the location makes the
    mixture widen the distribution while leaving its mean where the fit put it.
    """
    variance = max(0.0, float(log_mean_variance))
    # Mean-preserving location shift, applied before clipping.
    centred = min(_LOG_MEAN_CEILING, max(_LOG_MEAN_FLOOR, log_mean - variance / 2.0))
    if variance <= 1e-12:
        return UncertainSideDistribution(
            components=(
                (1.0, SideCountDistribution(math.exp(centred), distribution, dispersion)),
            ),
            log_mean_variance=0.0,
        )
    raw_nodes, raw_weights = np.polynomial.hermite_e.hermegauss(nodes)
    weights = raw_weights / raw_weights.sum()
    sigma = math.sqrt(variance)
    components: list[tuple[float, SideCountDistribution]] = []
    for node, weight in zip(raw_nodes, weights):
        shifted = min(
            _LOG_MEAN_CEILING, max(_LOG_MEAN_FLOOR, centred + sigma * float(node))
        )
        components.append(
            (
                float(weight),
                SideCountDistribution(math.exp(shifted), distribution, dispersion),
            )
        )
    total = sum(weight for weight, _ in components)
    components = [(weight / total, dist) for weight, dist in components]
    return UncertainSideDistribution(
        components=tuple(components), log_mean_variance=variance
    )


@dataclass(frozen=True, slots=True)
class MatchCountDistribution:
    """Two side distributions and the coherent match total they imply.

    ``p_over`` is the survival function of one cached total PMF, so the full line
    ladder is monotone by construction. That property is the reason this class
    exists and is asserted by
    ``tests/research/test_hierarchical_market_model.py::test_line_ladder_is_monotone``.
    """

    home: UncertainSideDistribution
    away: UncertainSideDistribution
    max_side_count: int = 30
    _total: np.ndarray = field(default=None, repr=False, compare=False)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        home_pmf = self.home.pmf(self.max_side_count)
        away_pmf = self.away.pmf(self.max_side_count)
        total = np.convolve(home_pmf, away_pmf)
        mass = float(total.sum())
        if mass > 0:
            total = total / mass
        object.__setattr__(self, "_total", total)

    @property
    def total_pmf(self) -> tuple[float, ...]:
        return tuple(float(value) for value in self._total)

    @property
    def expected_total(self) -> float:
        return self.home.mean + self.away.mean

    def p_over(self, line: float) -> float:
        """``P(total > line)``, read off the single convolved total PMF."""
        cutoff = math.floor(line)
        if cutoff < 0:
            return 1.0
        if cutoff >= len(self._total) - 1:
            return 0.0
        value = 1.0 - float(self._total[: cutoff + 1].sum())
        return min(1.0, max(0.0, value))

    def p_under(self, line: float) -> float:
        return 1.0 - self.p_over(line)

    def p_both_score(self) -> float:
        """``P(home >= 1 and away >= 1)`` from the same two side distributions.

        Conditional independence given the fitted means is the assumption; the
        dependence that matters for football totals — both sides being high in an
        open game — is already carried by the shared league, opponent and form
        terms in ``log mu``, which is what makes this stronger than multiplying
        two unconditional rates. Whether it beats a directly fitted classifier is
        an empirical question, answered out of sample in
        :mod:`src.research.evaluation.hierarchical_lines`.
        """
        return min(
            1.0, max(0.0, self.home.p_at_least_one() * self.away.p_at_least_one())
        )

    def total_interval(self, mass: float = 0.80) -> tuple[int, int]:
        """Central interval on the total, so wide uncertainty is visible."""
        if not 0.0 < mass < 1.0:
            raise ValueError("mass must be in (0, 1)")
        cumulative = np.cumsum(self._total)
        lower_tail = (1.0 - mass) / 2.0
        low = int(np.searchsorted(cumulative, lower_tail))
        high = int(np.searchsorted(cumulative, 1.0 - lower_tail))
        return low, min(high, len(self._total) - 1)


# ─────────────────────────────────────────────────────────────────────────────
# Rows
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class SideRow:
    """One side of one fixture: the count it produced and the features behind it.

    Every match contributes two of these. ``counting_team`` produced the count;
    ``opposing_team`` allowed it. The ``*_name`` fields are display labels only —
    all model state is keyed on the ids, so a provider renaming a club cannot
    silently split its history in two.
    """

    fixture_id: str
    league: str
    season: str
    kickoff_unix: int
    counting_team: str
    opposing_team: str
    is_home: bool
    features: Mapping[str, float]
    count: Optional[float] = None
    counting_team_name: Optional[str] = None
    opposing_team_name: Optional[str] = None

    @property
    def counting_label(self) -> str:
        return self.counting_team_name or self.counting_team

    @property
    def opposing_label(self) -> str:
        return self.opposing_team_name or self.opposing_team

    def feature_vector(self, names: Sequence[str]) -> np.ndarray:
        return np.array([float(self.features.get(name, 0.0)) for name in names], dtype=float)


# ─────────────────────────────────────────────────────────────────────────────
# Shrinkage bookkeeping
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class ShrunkEffect:
    """An empirical-Bayes posterior with every input to it kept visible.

    Provenance needs to distinguish a forecast built on 4 matches from one built
    on 30, and this is the record that does it: the raw estimate, how far it was
    pulled toward the prior, where the prior came from, and how much of the
    posterior is prior-season carry-over rather than current-season evidence.
    """

    key: str
    raw: float
    posterior: float
    n_observations: int
    sampling_variance: float
    prior_variance: float
    shrinkage_weight: float
    prior_mean: float = 0.0
    prior_season_decay: float = 0.0
    prior_season_contribution: float = 0.0

    @property
    def posterior_variance(self) -> float:
        """Residual uncertainty about this effect after shrinking."""
        return max(0.0, (1.0 - self.shrinkage_weight) * self.prior_variance)

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "raw": round(self.raw, 6),
            "posterior": round(self.posterior, 6),
            "n_observations": self.n_observations,
            "shrinkage_weight": round(self.shrinkage_weight, 6),
            "sampling_variance": round(self.sampling_variance, 6),
            "prior_variance": round(self.prior_variance, 6),
            "posterior_variance": round(self.posterior_variance, 6),
            "prior_season_decay": round(self.prior_season_decay, 6),
            "prior_season_contribution": round(self.prior_season_contribution, 6),
        }


_ZERO_EFFECT = ShrunkEffect(
    key="",
    raw=0.0,
    posterior=0.0,
    n_observations=0,
    sampling_variance=float("inf"),
    prior_variance=0.0,
    shrinkage_weight=0.0,
)


def _empirical_bayes(
    key: str,
    observed: float,
    exposure: float,
    n_observations: int,
    prior_variance: float,
    *,
    prior_mean: float = 0.0,
    prior_season_decay: float = 0.0,
) -> ShrunkEffect:
    """Shrink a log observed/expected ratio toward ``prior_mean``.

    The half-count continuity correction keeps a team that has conceded no corners
    all season finite instead of producing ``log 0``. Sampling variance of a log
    rate is approximately ``1 / observed``, which is what makes thin evidence
    shrink hard without any explicit match-count rule.
    """
    raw = math.log((observed + 0.5) / (exposure + 0.5))
    sampling_variance = 1.0 / (observed + 0.5)
    denominator = prior_variance + sampling_variance
    weight = prior_variance / denominator if denominator > 0.0 else 0.0
    decayed_prior = prior_season_decay * prior_mean
    posterior = weight * raw + (1.0 - weight) * decayed_prior
    return ShrunkEffect(
        key=key,
        raw=raw,
        posterior=posterior,
        n_observations=n_observations,
        sampling_variance=sampling_variance,
        prior_variance=prior_variance,
        shrinkage_weight=weight,
        prior_mean=prior_mean,
        prior_season_decay=prior_season_decay,
        prior_season_contribution=(1.0 - weight) * decayed_prior,
    )


def _method_of_moments_variance(
    effects: Sequence[tuple[float, float]], *, floor: float = 0.0
) -> float:
    """Between-group variance net of mean sampling variance.

    ``effects`` is ``(raw_estimate, sampling_variance)`` per group. If the observed
    spread between groups is no larger than what sampling noise alone would
    produce, the prior variance is zero and every group shrinks all the way to the
    prior — which is the correct answer, not a degenerate one.
    """
    if len(effects) < 2:
        return floor
    raws = [raw for raw, _ in effects]
    mean = sum(raws) / len(raws)
    between = sum((raw - mean) ** 2 for raw in raws) / (len(raws) - 1)
    mean_sampling = sum(variance for _, variance in effects) / len(effects)
    return max(floor, between - mean_sampling)


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class HierarchicalConfig:
    """Every knob, with the reasoning for its default in the comment beside it."""

    #: Current-season matches at which the prior-season contribution halves. Six
    #: is roughly the point where a season-to-date mean stops being dominated by
    #: one result, so it is where prior-season information should stop dominating.
    prior_season_half_life_matches: float = 6.0
    #: Hard ceiling on how much a league slope may deviate from the global slope.
    #: League-varying slopes are 25 parameters per feature estimated on a few
    #: hundred rows each; the independent per-league fits failed on exactly that
    #: variance, so deviations are permitted but strongly restrained.
    slope_shrinkage_cap: float = 0.25
    #: Backfitting passes over (global slopes -> league -> team -> slopes).
    backfit_iterations: int = 2
    #: Residual variance/mean above which the negative binomial is selected.
    overdispersion_threshold: float = 1.10
    #: Ridge penalty on standardised global slopes.
    ridge: float = 0.02
    #: Minimum side observations before a team gets its own raw estimate at all.
    min_team_observations: int = 1
    #: Pooling constant for the between-team variance component. A league's own
    #: estimate gets weight ``n / (n + k)``; the global estimate takes the rest.
    #: Twenty team-seasons is roughly one league-season, so a league with a full
    #: season of its own mostly trusts itself and a thinner one borrows.
    variance_pooling_constant: float = 20.0
    min_global_observations: int = 40
    #: Fit a scalar shrinkage on the fitted log-mean deviation, estimated on a
    #: held-out tail of the training fold. This is the direct remedy for a
    #: reliability slope below 1: the audit measured an in-sample slope of 1.008
    #: against 0.754 out of sample, meaning the fitted spread in ``log mu`` is
    #: about a quarter too wide for the relationship that actually holds on unseen
    #: fixtures. Because it is one scalar applied to the mean *before* the
    #: distribution is built, every line stays coherent.
    calibrate_signal_scale: bool = True
    #: Chronological tail of the training fold reserved for estimating that scalar.
    signal_scale_holdout: float = 0.25
    #: Bounds on the scalar. Above 1 is permitted so the estimate can say the
    #: signal was under-extended rather than being forced to shrink.
    signal_scale_bounds: tuple[float, float] = (0.2, 1.3)
    min_signal_scale_rows: int = 400
    uncertainty_nodes: int = 5
    #: Cap on the modelled uncertainty in log mu, so a brand-new team widens
    #: toward the league rate rather than toward a uniform distribution.
    max_log_mean_variance: float = 0.25
    max_side_count: int = 30

    def __post_init__(self) -> None:
        if self.prior_season_half_life_matches <= 0:
            raise ValueError("prior_season_half_life_matches must be positive")
        if not 0.0 <= self.slope_shrinkage_cap <= 1.0:
            raise ValueError("slope_shrinkage_cap must be in [0, 1]")
        if self.backfit_iterations < 1:
            raise ValueError("backfit_iterations must be at least 1")

    def prior_season_decay(self, current_season_matches: int) -> float:
        """Weight on prior-season information after ``n`` current-season matches.

        Halves every ``prior_season_half_life_matches`` matches. Explicit, bounded,
        and reported per team in provenance, so a reader can see how much of a
        forecast is last season rather than this one.
        """
        n = max(0, int(current_season_matches))
        return float(0.5 ** (n / self.prior_season_half_life_matches))


@dataclass(frozen=True, slots=True)
class FittedGlobal:
    """The global layer: intercept, standardised slopes, and the count law."""

    intercept: float
    weights: dict[str, float]
    feature_means: dict[str, float]
    feature_scales: dict[str, float]
    distribution: str
    dispersion: float
    n_observations: int
    marginal_variance_mean_ratio: float
    residual_variance_mean_ratio: float
    #: Covariance of ``(intercept, standardised slopes)`` from the inverse observed
    #: information. Used to propagate estimation uncertainty into the predictive
    #: distribution, so an unusual feature row widens rather than being asserted
    #: with the same certainty as a typical one.
    coefficient_covariance: tuple[tuple[float, ...], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "intercept": round(self.intercept, 6),
            "weights": {k: round(v, 6) for k, v in self.weights.items()},
            "distribution": self.distribution,
            "dispersion": round(self.dispersion, 6),
            "n_observations": self.n_observations,
            "marginal_variance_mean_ratio": round(self.marginal_variance_mean_ratio, 4),
            "residual_variance_mean_ratio": round(self.residual_variance_mean_ratio, 4),
            "coefficient_uncertainty_propagated": bool(self.coefficient_covariance),
        }


class NotFittedError(RuntimeError):
    """Raised when a prediction is requested before a successful fit."""


# ─────────────────────────────────────────────────────────────────────────────
# The model
# ─────────────────────────────────────────────────────────────────────────────
class HierarchicalCountModel:
    """One hierarchical count fit per market family.

    Fit once, then read every line, both first-half and full-match variants of the
    family it was built for, and — for goals — both teams to score, from the same
    parameters.
    """

    def __init__(
        self,
        family: MarketFamily,
        config: HierarchicalConfig | None = None,
    ) -> None:
        self.family = family
        self.config = config or HierarchicalConfig()
        self.feature_names: tuple[str, ...] = family.feature_names
        self.global_layer: Optional[FittedGlobal] = None
        self.league_effects: dict[str, ShrunkEffect] = {}
        self.attack_effects: dict[tuple[str, str], ShrunkEffect] = {}
        self.concede_effects: dict[tuple[str, str], ShrunkEffect] = {}
        self.league_slopes: dict[tuple[str, str], ShrunkEffect] = {}
        self.league_dispersion: dict[str, float] = {}
        #: Scalar shrinkage on the fitted log-mean deviation, estimated out of
        #: sample. 1.0 means no shrinkage was needed.
        self.signal_scale = 1.0
        self.signal_scale_diagnostics: dict[str, object] = {}
        #: Prior-season posteriors, keyed (league, team) -> effect value, keyed by
        #: the season they were estimated in.
        self._season_order: dict[str, list[str]] = {}
        self._team_season_state: dict[tuple[str, str, str], float] = {}
        self._team_season_counts: dict[tuple[str, str, str], int] = {}
        self._latest_season: dict[str, str] = {}

    # ── properties ────────────────────────────────────────────────────────
    @property
    def is_fitted(self) -> bool:
        return self.global_layer is not None

    @property
    def distribution(self) -> str:
        if self.global_layer is None:
            raise NotFittedError("model is not fitted")
        return self.global_layer.distribution

    # ── fitting ───────────────────────────────────────────────────────────
    def fit(self, rows: Sequence[SideRow]) -> None:
        """Fit the global, league, team and league-slope layers by backfitting."""
        labelled = [row for row in rows if _valid_count(row.count)]
        if len(labelled) < self.config.min_global_observations:
            raise ValueError(
                f"{self.family.name}: {len(labelled)} labelled side rows is below the "
                f"minimum of {self.config.min_global_observations}"
            )

        y = np.array([float(row.count) for row in labelled], dtype=float)
        raw_x = np.vstack([row.feature_vector(self.feature_names) for row in labelled])
        means = raw_x.mean(axis=0)
        scales = raw_x.std(axis=0, ddof=0)
        scales = np.where(scales < 1e-9, 1.0, scales)
        x = (raw_x - means) / scales

        self._index_seasons(labelled)

        offset = np.zeros(len(labelled), dtype=float)
        intercept = math.log(max(0.05, float(y.mean())))
        weights = np.zeros(x.shape[1], dtype=float)
        distribution = POISSON
        dispersion = 0.0

        for iteration in range(self.config.backfit_iterations):
            intercept, weights = self._fit_global_slopes(
                y, x, offset, distribution, dispersion, intercept, weights
            )
            base_log_mu = intercept + x @ weights
            distribution, dispersion, residual_ratio = self._select_distribution(
                y, np.exp(np.clip(base_log_mu + offset, _LOG_MEAN_FLOOR, _LOG_MEAN_CEILING))
            )
            self._fit_league_effects(labelled, y, base_log_mu)
            self._fit_team_effects(labelled, y, base_log_mu)
            self._fit_league_slopes(labelled, y, x, base_log_mu)
            offset = np.array(
                [
                    self._random_offset(row, row.feature_vector(self.feature_names), means, scales)
                    for row in labelled
                ],
                dtype=float,
            )

        final_log_mu = np.clip(
            intercept + x @ weights + offset, _LOG_MEAN_FLOOR, _LOG_MEAN_CEILING
        )
        distribution, dispersion, residual_ratio = self._select_distribution(
            y, np.exp(final_log_mu)
        )
        marginal_ratio = float(np.var(y, ddof=1) / np.mean(y)) if np.mean(y) > 0 else 0.0
        covariance = self._coefficient_covariance(
            x, np.exp(final_log_mu), distribution, dispersion
        )

        self.global_layer = FittedGlobal(
            intercept=float(intercept),
            weights={
                name: float(value) for name, value in zip(self.feature_names, weights)
            },
            feature_means={
                name: float(value) for name, value in zip(self.feature_names, means)
            },
            feature_scales={
                name: float(value) for name, value in zip(self.feature_names, scales)
            },
            distribution=distribution,
            dispersion=dispersion,
            n_observations=len(labelled),
            marginal_variance_mean_ratio=marginal_ratio,
            residual_variance_mean_ratio=residual_ratio,
            coefficient_covariance=covariance,
        )
        self._fit_league_dispersion(labelled, y, np.exp(final_log_mu))
        if self.config.calibrate_signal_scale:
            self._fit_signal_scale(labelled)

    def _fit_signal_scale(self, labelled: Sequence[SideRow]) -> None:
        """Estimate how far the fitted signal over-extends, out of sample.

        A probe model is fitted on the earlier part of the training fold and scored
        on the later part, so the scale is estimated on rows the probe never saw.
        The scale that maximises the held-out count likelihood is then applied to
        the full model. This is deliberately *not* estimated on the rows the full
        model was fitted on: in sample the slope is 1.008 by construction, which is
        exactly why the defect was invisible until it was measured out of sample.
        """
        ordered = sorted(labelled, key=lambda row: (row.kickoff_unix, row.fixture_id))
        split = int(len(ordered) * (1.0 - self.config.signal_scale_holdout))
        train, holdout = ordered[:split], ordered[split:]
        if (
            len(train) < self.config.min_signal_scale_rows
            or len(holdout) < self.config.min_signal_scale_rows // 2
        ):
            self.signal_scale_diagnostics = {
                "status": "skipped",
                "reason": "insufficient rows to estimate a held-out scale",
            }
            return

        probe_config = replace(self.config, calibrate_signal_scale=False)
        probe = HierarchicalCountModel(self.family, probe_config)
        try:
            probe.fit(train)
        except (ValueError, RuntimeError) as exc:
            self.signal_scale_diagnostics = {
                "status": "skipped",
                "reason": f"probe fit failed: {type(exc).__name__}",
            }
            return

        baselines: list[float] = []
        deviations: list[float] = []
        counts: list[float] = []
        for row in holdout:
            try:
                terms = probe._side_terms(row)
            except (NotFittedError, KeyError):
                continue
            league = terms["league_effect"]
            baseline = probe.global_layer.intercept + (
                league.posterior if league else 0.0
            )
            baselines.append(baseline)
            deviations.append(float(terms["log_mu"]) - baseline)
            counts.append(float(row.count))
        if len(counts) < self.config.min_signal_scale_rows // 2:
            self.signal_scale_diagnostics = {
                "status": "skipped",
                "reason": "too few scorable holdout rows",
            }
            return

        base = np.asarray(baselines, dtype=float)
        deviation = np.asarray(deviations, dtype=float)
        observed = np.asarray(counts, dtype=float)
        distribution = probe.global_layer.distribution
        dispersion = probe.global_layer.dispersion

        def negative_log_likelihood(scale: float) -> float:
            log_mu = np.clip(
                base + scale * deviation, _LOG_MEAN_FLOOR, _LOG_MEAN_CEILING
            )
            mu = np.exp(log_mu)
            if distribution == NEGATIVE_BINOMIAL and dispersion > 0:
                shape = 1.0 / dispersion
                return -float(
                    np.sum(
                        gammaln(observed + shape)
                        - gammaln(shape)
                        - gammaln(observed + 1.0)
                        + shape * np.log(shape / (shape + mu))
                        + observed * np.log(np.clip(mu / (shape + mu), 1e-12, 1.0))
                    )
                )
            return -float(np.sum(observed * log_mu - mu - gammaln(observed + 1.0)))

        low, high = self.config.signal_scale_bounds
        grid = np.linspace(low, high, 45)
        losses = [negative_log_likelihood(float(value)) for value in grid]
        best = float(grid[int(np.argmin(losses))])
        self.signal_scale = best
        self.signal_scale_diagnostics = {
            "status": "fitted",
            "scale": round(best, 4),
            "n_holdout_rows": len(counts),
            "log_likelihood_gain_vs_unshrunk": round(
                negative_log_likelihood(1.0) - min(losses), 4
            ),
            "note": (
                "scalar shrinkage of the fitted log-mean deviation, estimated on a "
                "held-out tail of the training fold; applied before any line is "
                "read so cross-line monotonicity is preserved"
            ),
        }

    def _coefficient_covariance(
        self,
        x: np.ndarray,
        mu: np.ndarray,
        distribution: str,
        dispersion: float,
    ) -> tuple[tuple[float, ...], ...]:
        """Inverse observed information for ``(intercept, standardised slopes)``.

        Without this the predictive distribution treats the fitted coefficients as
        exact, which makes the model overconfident: it spreads probabilities
        further from the base rate than the evidence for its slopes supports. The
        audit measured that directly as a reliability slope well below 1 across six
        of seven families. The GLM weight is ``mu`` for Poisson and
        ``mu / (1 + alpha mu)`` for NB2; the ridge penalty is added to the
        information because it was part of the objective that produced these
        estimates.
        """
        weight = mu / (1.0 + dispersion * mu) if (
            distribution == NEGATIVE_BINOMIAL and dispersion > 0
        ) else mu
        design = np.column_stack([np.ones(len(x)), x])
        information = design.T @ (design * weight[:, None])
        # The ridge penalised the slopes but not the intercept.
        penalty = np.eye(information.shape[0]) * (2.0 * self.config.ridge)
        penalty[0, 0] = 0.0
        information = information + penalty
        try:
            covariance = np.linalg.inv(information)
        except np.linalg.LinAlgError:
            covariance = np.linalg.pinv(information)
        if not np.all(np.isfinite(covariance)):
            return ()
        return tuple(tuple(float(value) for value in row) for row in covariance)

    # ── global layer ──────────────────────────────────────────────────────
    def _fit_global_slopes(
        self,
        y: np.ndarray,
        x: np.ndarray,
        offset: np.ndarray,
        distribution: str,
        dispersion: float,
        intercept0: float,
        weights0: np.ndarray,
    ) -> tuple[float, np.ndarray]:
        """Maximum likelihood on the global intercept and slopes, offsets held."""
        n, k = x.shape
        ridge = self.config.ridge

        def negative_log_likelihood(params: np.ndarray) -> float:
            log_mu = np.clip(
                params[0] + x @ params[1:] + offset, _LOG_MEAN_FLOOR, _LOG_MEAN_CEILING
            )
            mu = np.exp(log_mu)
            if distribution == NEGATIVE_BINOMIAL and dispersion > 0:
                shape = 1.0 / dispersion
                log_likelihood = float(
                    np.sum(
                        gammaln(y + shape)
                        - gammaln(shape)
                        - gammaln(y + 1.0)
                        + shape * np.log(shape / (shape + mu))
                        + y * np.log(np.clip(mu / (shape + mu), 1e-12, 1.0))
                    )
                )
            else:
                log_likelihood = float(
                    np.sum(y * log_mu - mu - gammaln(y + 1.0))
                )
            return -(log_likelihood - ridge * float(np.sum(params[1:] ** 2)))

        start = np.concatenate([[intercept0], weights0])
        result = minimize(
            negative_log_likelihood,
            start,
            method="L-BFGS-B",
            options={"maxiter": 400, "ftol": 1e-8},
        )
        estimate = result.x if result.x is not None else start
        if not np.all(np.isfinite(estimate)):
            estimate = start
        return float(estimate[0]), np.asarray(estimate[1:], dtype=float)

    def _select_distribution(
        self, y: np.ndarray, mu: np.ndarray
    ) -> tuple[str, float, float]:
        """Choose Poisson or NB2 from **residual** dispersion, not marginal.

        Marginal variance/mean is the wrong test once there are covariates: a
        family whose mean genuinely varies across fixtures looks overdispersed
        even when the conditional law is exactly Poisson. The Pearson statistic
        over its degrees of freedom is the conditional test, and it is what
        decides here. The moment estimator for ``alpha`` follows from the same
        residuals.
        """
        n = len(y)
        degrees_of_freedom = max(1, n - len(self.feature_names) - 1)
        safe_mu = np.clip(mu, 1e-9, None)
        pearson = float(np.sum((y - safe_mu) ** 2 / safe_mu))
        ratio = pearson / degrees_of_freedom
        if ratio <= self.config.overdispersion_threshold:
            return POISSON, 0.0, ratio
        numerator = float(np.sum((y - safe_mu) ** 2 - safe_mu))
        denominator = float(np.sum(safe_mu**2))
        alpha = numerator / denominator if denominator > 0 else 0.0
        alpha = float(min(5.0, max(1e-4, alpha)))
        return NEGATIVE_BINOMIAL, alpha, ratio

    # ── league intercepts ─────────────────────────────────────────────────
    def _fit_league_effects(
        self, rows: Sequence[SideRow], y: np.ndarray, base_log_mu: np.ndarray
    ) -> None:
        observed: dict[str, float] = {}
        exposure: dict[str, float] = {}
        counts: dict[str, int] = {}
        for index, row in enumerate(rows):
            league = row.league
            observed[league] = observed.get(league, 0.0) + float(y[index])
            exposure[league] = exposure.get(league, 0.0) + math.exp(
                min(_LOG_MEAN_CEILING, max(_LOG_MEAN_FLOOR, float(base_log_mu[index])))
            )
            counts[league] = counts.get(league, 0) + 1

        provisional = [
            (
                math.log((observed[league] + 0.5) / (exposure[league] + 0.5)),
                1.0 / (observed[league] + 0.5),
            )
            for league in sorted(observed)
        ]
        prior_variance = _method_of_moments_variance(provisional)
        self.league_effects = {
            league: _empirical_bayes(
                key=league,
                observed=observed[league],
                exposure=exposure[league],
                n_observations=counts[league],
                prior_variance=prior_variance,
            )
            for league in sorted(observed)
        }

    # ── team attack / concede states, nested in league ────────────────────
    def _fit_team_effects(
        self, rows: Sequence[SideRow], y: np.ndarray, base_log_mu: np.ndarray
    ) -> None:
        """Attack and concede states per team, per season, nested inside league.

        Two accumulations per team: what it produced when it was the counting side
        (attack) and what its opponents produced against it (concede). Both are
        measured against exposure that already carries the league intercept, which
        is what makes the pooling nested rather than crossed — a team is shrunk
        toward its own league, and its league toward the global fit.

        Per-season accumulation is what lets the prior-season posterior seed the
        current season's prior. The recursion runs forward through seasons in
        kickoff order, so a season is only ever informed by earlier ones.
        """
        attack_observed: dict[tuple[str, str, str], float] = {}
        attack_exposure: dict[tuple[str, str, str], float] = {}
        attack_counts: dict[tuple[str, str, str], int] = {}
        concede_observed: dict[tuple[str, str, str], float] = {}
        concede_exposure: dict[tuple[str, str, str], float] = {}
        concede_counts: dict[tuple[str, str, str], int] = {}

        for index, row in enumerate(rows):
            league_offset = self._league_offset(row.league)
            exposure = math.exp(
                min(
                    _LOG_MEAN_CEILING,
                    max(_LOG_MEAN_FLOOR, float(base_log_mu[index]) + league_offset),
                )
            )
            value = float(y[index])
            attack_key = (row.league, row.counting_team, row.season)
            concede_key = (row.league, row.opposing_team, row.season)
            attack_observed[attack_key] = attack_observed.get(attack_key, 0.0) + value
            attack_exposure[attack_key] = attack_exposure.get(attack_key, 0.0) + exposure
            attack_counts[attack_key] = attack_counts.get(attack_key, 0) + 1
            concede_observed[concede_key] = concede_observed.get(concede_key, 0.0) + value
            concede_exposure[concede_key] = (
                concede_exposure.get(concede_key, 0.0) + exposure
            )
            concede_counts[concede_key] = concede_counts.get(concede_key, 0) + 1

        self.attack_effects = self._shrink_team_layer(
            attack_observed, attack_exposure, attack_counts
        )
        self.concede_effects = self._shrink_team_layer(
            concede_observed, concede_exposure, concede_counts
        )
        self._team_season_counts = {
            key: attack_counts.get(key, 0) for key in attack_counts
        }

    def _shrink_team_layer(
        self,
        observed: Mapping[tuple[str, str, str], float],
        exposure: Mapping[tuple[str, str, str], float],
        counts: Mapping[tuple[str, str, str], int],
    ) -> dict[tuple[str, str], ShrunkEffect]:
        """Shrink one team layer, walking seasons forward so priors carry over.

        The result is keyed ``(league, team)`` and holds the effect for that
        team's **most recent** season, because that is what a forecast for an
        upcoming fixture needs. Earlier seasons survive only as the prior that
        produced it.
        """
        # Within-league between-team prior variance, measured on the raw estimates.
        by_league: dict[str, list[tuple[float, float]]] = {}
        for key in observed:
            league = key[0]
            raw = math.log((observed[key] + 0.5) / (exposure[key] + 0.5))
            by_league.setdefault(league, []).append((raw, 1.0 / (observed[key] + 0.5)))
        global_prior = _method_of_moments_variance(
            [pair for pairs in by_league.values() for pair in pairs]
        )
        # The variance component is itself partially pooled. A league with a handful
        # of teams produces a between-team variance estimate that is mostly noise
        # and frequently collapses to zero, which would assert that every team in
        # that league is identical -- an absurdly confident claim from a dozen rows,
        # and one that would make a thin league look *more* certain than a rich one.
        # Shrinking the estimate toward the global between-team variance keeps thin
        # leagues wide, which is the behaviour the hierarchy is supposed to deliver.
        league_prior: dict[str, float] = {}
        for league, pairs in by_league.items():
            moment = _method_of_moments_variance(pairs)
            weight = len(pairs) / (len(pairs) + self.config.variance_pooling_constant)
            league_prior[league] = weight * moment + (1.0 - weight) * global_prior

        result: dict[tuple[str, str], ShrunkEffect] = {}
        carried: dict[tuple[str, str], float] = {}
        seasons_by_team: dict[tuple[str, str], list[str]] = {}
        for league, team, season in observed:
            seasons_by_team.setdefault((league, team), []).append(season)

        for (league, team), seasons in seasons_by_team.items():
            ordered = sorted(
                set(seasons), key=lambda s: self._season_rank(league, s)
            )
            for season in ordered:
                key = (league, team, season)
                if counts.get(key, 0) < self.config.min_team_observations:
                    continue
                prior_mean = carried.get((league, team), 0.0)
                decay = self.config.prior_season_decay(counts.get(key, 0))
                effect = _empirical_bayes(
                    key=f"{team}@{league}:{season}",
                    observed=observed[key],
                    exposure=exposure[key],
                    n_observations=counts.get(key, 0),
                    prior_variance=league_prior.get(league, global_prior),
                    prior_mean=prior_mean,
                    prior_season_decay=decay,
                )
                carried[(league, team)] = effect.posterior
                result[(league, team)] = effect
        return result

    # ── league slope deviations ───────────────────────────────────────────
    def _fit_league_slopes(
        self,
        rows: Sequence[SideRow],
        y: np.ndarray,
        x: np.ndarray,
        base_log_mu: np.ndarray,
    ) -> None:
        """One strongly-shrunk slope deviation per league, per declared feature.

        A single Fisher-scoring step on the league's own rows gives both the
        deviation and its sampling variance, which is what the empirical-Bayes
        step needs. The resulting weight is then capped, so even a league with a
        long history cannot take a large deviation on a handful of features. That
        cap is a deliberate restraint, not an estimate.
        """
        varying = self.family.features.league_varying
        self.league_slopes = {}
        if not varying:
            return
        indexes = {name: i for i, name in enumerate(self.feature_names)}
        rows_by_league: dict[str, list[int]] = {}
        for index, row in enumerate(rows):
            rows_by_league.setdefault(row.league, []).append(index)

        for feature in varying:
            column = indexes[feature]
            provisional: dict[str, tuple[float, float, int]] = {}
            for league, row_indexes in rows_by_league.items():
                selected = np.asarray(row_indexes, dtype=int)
                mu = np.exp(
                    np.clip(
                        base_log_mu[selected] + self._league_offset(league),
                        _LOG_MEAN_FLOOR,
                        _LOG_MEAN_CEILING,
                    )
                )
                feature_values = x[selected, column]
                score = float(np.sum((y[selected] - mu) * feature_values))
                information = float(np.sum(mu * feature_values**2))
                if information <= 1e-9:
                    continue
                provisional[league] = (
                    score / information,
                    1.0 / information,
                    len(row_indexes),
                )
            if len(provisional) < 2:
                continue
            prior_variance = _method_of_moments_variance(
                [(value[0], value[1]) for value in provisional.values()]
            )
            for league, (deviation, sampling_variance, n) in provisional.items():
                denominator = prior_variance + sampling_variance
                weight = prior_variance / denominator if denominator > 0 else 0.0
                weight = min(self.config.slope_shrinkage_cap, weight)
                self.league_slopes[(league, feature)] = ShrunkEffect(
                    key=f"{league}:{feature}",
                    raw=deviation,
                    posterior=weight * deviation,
                    n_observations=n,
                    sampling_variance=sampling_variance,
                    prior_variance=prior_variance,
                    shrinkage_weight=weight,
                )

    def _fit_league_dispersion(
        self, rows: Sequence[SideRow], y: np.ndarray, mu: np.ndarray
    ) -> None:
        """Residual dispersion per league, reported rather than acted on.

        Per-league dispersion is measured so the report can state where the
        negative binomial is doing work and where it is not. It is not used to
        give each league its own alpha: on a few hundred rows that estimate is
        noisier than the pooled one, which is the same variance argument that
        rules out independent per-league slopes.
        """
        by_league: dict[str, list[tuple[float, float]]] = {}
        for index, row in enumerate(rows):
            by_league.setdefault(row.league, []).append((float(y[index]), float(mu[index])))
        self.league_dispersion = {}
        for league, pairs in by_league.items():
            if len(pairs) < 30:
                continue
            degrees = max(1, len(pairs) - 1)
            pearson = sum(
                (value - max(1e-9, fitted)) ** 2 / max(1e-9, fitted)
                for value, fitted in pairs
            )
            self.league_dispersion[league] = pearson / degrees

    # ── seasons ───────────────────────────────────────────────────────────
    def _index_seasons(self, rows: Sequence[SideRow]) -> None:
        """Order each league's seasons by kickoff, derived from the data.

        No hard-coded season list: the ordering comes from when the matches
        actually happened, so it cannot silently age out.
        """
        latest: dict[tuple[str, str], int] = {}
        for row in rows:
            key = (row.league, row.season)
            latest[key] = max(latest.get(key, 0), int(row.kickoff_unix))
        by_league: dict[str, list[tuple[int, str]]] = {}
        for (league, season), kickoff in latest.items():
            by_league.setdefault(league, []).append((kickoff, season))
        self._season_order = {
            league: [season for _, season in sorted(pairs)]
            for league, pairs in by_league.items()
        }
        self._latest_season = {
            league: seasons[-1] for league, seasons in self._season_order.items() if seasons
        }

    def _season_rank(self, league: str, season: str) -> int:
        order = self._season_order.get(league, [])
        return order.index(season) if season in order else len(order)

    # ── prediction ────────────────────────────────────────────────────────
    def _league_offset(self, league: str) -> float:
        effect = self.league_effects.get(league)
        return effect.posterior if effect else 0.0

    def _random_offset(
        self,
        row: SideRow,
        raw_features: np.ndarray,
        means: np.ndarray,
        scales: np.ndarray,
    ) -> float:
        """League intercept, league slope deviations, and both team states."""
        offset = self._league_offset(row.league)
        attack = self.attack_effects.get((row.league, row.counting_team))
        concede = self.concede_effects.get((row.league, row.opposing_team))
        offset += attack.posterior if attack else 0.0
        offset += concede.posterior if concede else 0.0
        if self.league_slopes:
            standardised = (raw_features - means) / scales
            indexes = {name: i for i, name in enumerate(self.feature_names)}
            for feature in self.family.features.league_varying:
                slope = self.league_slopes.get((row.league, feature))
                if slope is not None:
                    offset += slope.posterior * float(standardised[indexes[feature]])
        return offset

    def _side_terms(self, row: SideRow) -> dict[str, object]:
        """Everything behind one side's ``log mu``, itemised for attribution."""
        layer = self.global_layer
        if layer is None:
            raise NotFittedError(f"{self.family.name} model is not fitted")
        contributions: dict[str, float] = {}
        log_mu = layer.intercept
        for name in self.feature_names:
            raw_value = float(row.features.get(name, layer.feature_means[name]))
            standardised = (raw_value - layer.feature_means[name]) / layer.feature_scales[
                name
            ]
            weight = layer.weights[name]
            slope = self.league_slopes.get((row.league, name))
            if slope is not None:
                weight += slope.posterior
            contribution = weight * standardised
            contributions[name] = contribution
            log_mu += contribution

        league = self.league_effects.get(row.league)
        attack = self.attack_effects.get((row.league, row.counting_team)) or _ZERO_EFFECT
        concede = self.concede_effects.get((row.league, row.opposing_team)) or _ZERO_EFFECT
        log_mu += (league.posterior if league else 0.0) + attack.posterior + concede.posterior

        # Predictive uncertainty in log mu has two sources, and both belong here:
        # the empirical-Bayes posterior variance of the random effects (how little
        # we know about this league and these teams) and the estimation variance of
        # the global coefficients (how little we know about the slopes, which is
        # larger for an unusual feature row than a typical one).
        random_effect_variance = (
            (league.posterior_variance if league else 0.0)
            + attack.posterior_variance
            + concede.posterior_variance
        )
        coefficient_variance = self._coefficient_variance(row, layer)
        variance = min(
            self.config.max_log_mean_variance,
            random_effect_variance + coefficient_variance,
        )
        # Apply the out-of-sample signal scale to the deviation from the
        # league-typical mean, never to the baseline itself. Shrinking the baseline
        # would drag every league toward a global average that no league occupies.
        baseline = layer.intercept + (league.posterior if league else 0.0)
        scaled = baseline + self.signal_scale * (log_mu - baseline)
        return {
            "log_mu": min(_LOG_MEAN_CEILING, max(_LOG_MEAN_FLOOR, scaled)),
            "log_mu_unscaled": min(_LOG_MEAN_CEILING, max(_LOG_MEAN_FLOOR, log_mu)),
            "log_mean_variance": variance,
            "random_effect_variance": random_effect_variance,
            "coefficient_variance": coefficient_variance,
            "signal_scale": self.signal_scale,
            "feature_contributions": {
                name: self.signal_scale * value
                for name, value in contributions.items()
            },
            "league_effect": league,
            "attack_effect": attack if attack is not _ZERO_EFFECT else None,
            "concede_effect": concede if concede is not _ZERO_EFFECT else None,
        }

    def _coefficient_variance(self, row: SideRow, layer: FittedGlobal) -> float:
        """``x' Sigma x`` for the standardised design row, intercept included."""
        if not layer.coefficient_covariance:
            return 0.0
        design = [1.0]
        for name in self.feature_names:
            raw_value = float(row.features.get(name, layer.feature_means[name]))
            design.append(
                (raw_value - layer.feature_means[name]) / layer.feature_scales[name]
            )
        vector = np.asarray(design, dtype=float)
        covariance = np.asarray(layer.coefficient_covariance, dtype=float)
        if covariance.shape[0] != vector.shape[0]:
            return 0.0
        value = float(vector @ covariance @ vector)
        return max(0.0, value) if math.isfinite(value) else 0.0

    def predict_side(self, row: SideRow) -> UncertainSideDistribution:
        terms = self._side_terms(row)
        layer = self.global_layer
        assert layer is not None
        return _gauss_hermite_mixture(
            float(terms["log_mu"]),
            float(terms["log_mean_variance"]),
            layer.distribution,
            layer.dispersion,
            nodes=self.config.uncertainty_nodes,
        )

    def predict_match(
        self, home_row: SideRow, away_row: SideRow
    ) -> MatchCountDistribution:
        """The coherent match distribution: every line and BTTS come from this."""
        return MatchCountDistribution(
            home=self.predict_side(home_row),
            away=self.predict_side(away_row),
            max_side_count=self.config.max_side_count,
        )

    def line_probabilities(
        self, home_row: SideRow, away_row: SideRow
    ) -> dict[float, float]:
        """``P(over line)`` for every declared line, guaranteed non-increasing."""
        distribution = self.predict_match(home_row, away_row)
        return {line: distribution.p_over(line) for line in self.family.lines}

    # ── provenance ────────────────────────────────────────────────────────
    def side_provenance(self, row: SideRow) -> dict[str, object]:
        """Shrinkage and prior-season carry-over for one side of one fixture."""
        terms = self._side_terms(row)
        league = terms["league_effect"]
        attack = terms["attack_effect"]
        concede = terms["concede_effect"]
        return {
            "team": row.counting_team,
            "opponent": row.opposing_team,
            "league": row.league,
            "is_home": row.is_home,
            "log_mean": round(float(terms["log_mu"]), 6),
            "log_mean_variance": round(float(terms["log_mean_variance"]), 6),
            "league_effect": league.to_dict() if league else None,
            "attack_effect": attack.to_dict() if attack else None,
            "concede_effect": concede.to_dict() if concede else None,
            "team_state_known": attack is not None,
            "opponent_state_known": concede is not None,
        }

    def match_provenance(
        self, home_row: SideRow, away_row: SideRow
    ) -> dict[str, object]:
        layer = self.global_layer
        if layer is None:
            raise NotFittedError(f"{self.family.name} model is not fitted")
        distribution = self.predict_match(home_row, away_row)
        low, high = distribution.total_interval(0.80)
        home_provenance = self.side_provenance(home_row)
        away_provenance = self.side_provenance(away_row)
        return {
            "family": self.family.name,
            "distribution": layer.distribution,
            "dispersion": round(layer.dispersion, 6),
            "residual_variance_mean_ratio": round(
                layer.residual_variance_mean_ratio, 4
            ),
            "expected_total": round(distribution.expected_total, 4),
            "central_80_interval": [low, high],
            "home_side": home_provenance,
            "away_side": away_provenance,
            "shrinkage_weights": {
                "league": _weight_of(home_provenance.get("league_effect")),
                "home_attack": _weight_of(home_provenance.get("attack_effect")),
                "home_concede": _weight_of(away_provenance.get("concede_effect")),
                "away_attack": _weight_of(away_provenance.get("attack_effect")),
                "away_concede": _weight_of(home_provenance.get("concede_effect")),
            },
            "prior_season_contribution": {
                "home_attack": _prior_of(home_provenance.get("attack_effect")),
                "away_attack": _prior_of(away_provenance.get("attack_effect")),
            },
        }

    def fit_report(self) -> dict[str, object]:
        """Fitted structure, for the run report and for auditing shrinkage."""
        layer = self.global_layer
        if layer is None:
            raise NotFittedError(f"{self.family.name} model is not fitted")
        league_weights = [
            effect.shrinkage_weight for effect in self.league_effects.values()
        ]
        attack_weights = [
            effect.shrinkage_weight for effect in self.attack_effects.values()
        ]
        return {
            "family": self.family.name,
            "lines": list(self.family.lines),
            "feature_names": list(self.feature_names),
            "unavailable_mechanisms": list(
                self.family.features.unavailable_mechanisms
            ),
            "league_varying_slopes": list(self.family.features.league_varying),
            "global": layer.to_dict(),
            "n_leagues": len(self.league_effects),
            "n_team_attack_states": len(self.attack_effects),
            "n_team_concede_states": len(self.concede_effects),
            "median_league_shrinkage_weight": (
                round(float(np.median(league_weights)), 4) if league_weights else None
            ),
            "median_team_shrinkage_weight": (
                round(float(np.median(attack_weights)), 4) if attack_weights else None
            ),
            "league_slope_shrinkage_cap": self.config.slope_shrinkage_cap,
            "signal_scale": round(self.signal_scale, 4),
            "signal_scale_diagnostics": self.signal_scale_diagnostics,
            "prior_season_half_life_matches": self.config.prior_season_half_life_matches,
            "league_residual_dispersion": {
                league: round(value, 4)
                for league, value in sorted(self.league_dispersion.items())
            },
        }


def _weight_of(effect: object) -> Optional[float]:
    if isinstance(effect, Mapping):
        return effect.get("shrinkage_weight")
    return None


def _prior_of(effect: object) -> Optional[float]:
    if isinstance(effect, Mapping):
        return effect.get("prior_season_contribution")
    return None


def _valid_count(value: object) -> bool:
    if value is None:
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number >= 0.0
