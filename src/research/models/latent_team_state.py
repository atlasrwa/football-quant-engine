"""Low-dimensional, point-in-time latent team state for scoreline forecasts.

Raw match statistics are treated as noisy measurements of attack, defence, and
fixture tempo. They are never used from the fixture being forecast. Equal-time
fixtures must be processed together through :meth:`process_batch`, which emits
all forecasts before updating any state or running moments.

The model is deliberately narrow: it forecasts goals and 1X2 outcomes. Odds,
EV, staking, and totals-market selection are downstream concerns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import exp, factorial, isfinite, log, log1p
from typing import Literal, Sequence

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import poisson, skellam

MODEL_VERSION = "latent-team-state-v1"
MeasurementMode = Literal["raw", "goals"]


def _valid_count(value: float | int | None) -> float | None:
    if value is None:
        return None
    result = float(value)
    return result if isfinite(result) and result >= 0.0 else None


@dataclass
class RunningMoments:
    """Numerically stable online moments over log1p-transformed counts."""

    n: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def z_score(self, value: float | int | None, min_observations: int) -> float | None:
        raw = _valid_count(value)
        if raw is None or self.n < min_observations or self.n < 2:
            return None
        variance = self.m2 / (self.n - 1)
        if variance <= 1e-12:
            return None
        return (log1p(raw) - self.mean) / variance**0.5

    def update(self, value: float | int | None) -> None:
        raw = _valid_count(value)
        if raw is None:
            return
        transformed = log1p(raw)
        self.n += 1
        delta = transformed - self.mean
        self.mean += delta / self.n
        self.m2 += delta * (transformed - self.mean)


@dataclass
class TeamState:
    attack: float = 0.0
    defence: float = 0.0
    style: float = 0.0
    attack_updates: int = 0
    defence_updates: int = 0
    style_updates: int = 0
    last_update: int | None = None


@dataclass(frozen=True)
class StateOffset:
    """Point-in-time pre-kickoff adjustment for lineup/depth information.

    A future player layer can aggregate expected-minutes-weighted player states
    into this three-dimensional contract without widening the outcome model.
    Non-zero offsets require provenance and a strictly pre-kickoff ``as_of``.
    """

    attack: float = 0.0
    defence: float = 0.0
    style: float = 0.0
    as_of: int | None = None
    source: str | None = None

    def validate_for(self, kickoff: int) -> None:
        values = (self.attack, self.defence, self.style)
        if not all(isfinite(value) for value in values):
            raise ValueError("state offsets must be finite")
        if any(value != 0.0 for value in values):
            if self.as_of is None or not self.source:
                raise ValueError("non-zero state offsets require as_of and source")
            if self.as_of >= kickoff:
                raise ValueError("state offset provenance must be strictly pre-kickoff")


@dataclass(frozen=True)
class MatchObservation:
    match_id: str
    kickoff: int
    home_team_id: str
    away_team_id: str
    home_goals: int | None = None
    away_goals: int | None = None
    home_shots: float | None = None
    away_shots: float | None = None
    home_shots_on_target: float | None = None
    away_shots_on_target: float | None = None
    home_dangerous_attacks: float | None = None
    away_dangerous_attacks: float | None = None
    home_attacks: float | None = None
    away_attacks: float | None = None
    home_corners: float | None = None
    away_corners: float | None = None


@dataclass(frozen=True)
class StateFeatures:
    home_attack_edge: float
    away_attack_edge: float
    style_sum: float


@dataclass(frozen=True)
class ScorelineForecast:
    model_version: str
    generated_at: str
    kickoff: int
    home_team_id: str
    away_team_id: str
    lambda_home: float
    lambda_away: float
    home_win: float
    draw: float
    away_win: float
    outcome_entropy: float
    home_goal_interval_90: tuple[int, int]
    away_goal_interval_90: tuple[int, int]
    score_grid_max: int
    score_grid: tuple[tuple[float, ...], ...]
    home_state_updates: tuple[int, int, int]
    away_state_updates: tuple[int, int, int]
    home_state_age_days: float | None
    away_state_age_days: float | None

    @property
    def over_2_5(self) -> float:
        return float(1.0 - poisson.cdf(2, self.lambda_home + self.lambda_away))


@dataclass(frozen=True)
class _TrainingRow:
    features: StateFeatures
    home_goals: int
    away_goals: int


class DynamicStateFilter:
    """Online attack/defence/style measurement filter with frozen batch updates."""

    RAW_SIDE_FIELDS = ("shots", "shots_on_target", "dangerous_attacks")
    RAW_TOTAL_FIELDS = ("shots", "attacks", "corners")

    def __init__(
        self,
        mode: MeasurementMode = "raw",
        half_life_matches: float = 8.0,
        min_moment_observations: int = 20,
    ) -> None:
        if mode not in ("raw", "goals"):
            raise ValueError(f"unsupported measurement mode: {mode}")
        if half_life_matches <= 0:
            raise ValueError("half_life_matches must be positive")
        self.mode = mode
        self.alpha = 1.0 - 0.5 ** (1.0 / half_life_matches)
        self.min_moment_observations = min_moment_observations
        keys = {"goals"}
        keys.update(self.RAW_SIDE_FIELDS)
        keys.update(f"total_{name}" for name in self.RAW_TOTAL_FIELDS)
        self.moments = {key: RunningMoments() for key in keys}
        self.states: dict[str, TeamState] = {}
        self._last_batch_kickoff: int | None = None

    def state_for(self, team_id: str) -> TeamState:
        return self.states.setdefault(team_id, TeamState())

    @property
    def last_batch_kickoff(self) -> int | None:
        return self._last_batch_kickoff

    def validate_forecast_kickoff(self, kickoff: int) -> None:
        if self._last_batch_kickoff is not None and kickoff <= self._last_batch_kickoff:
            raise ValueError("forecast kickoff must be later than all processed batches")

    def validate_batch(self, matches: Sequence[MatchObservation]) -> None:
        if not matches:
            return
        kickoff = matches[0].kickoff
        if any(match.kickoff != kickoff for match in matches):
            raise ValueError("all matches in a batch must have the same kickoff")
        self.validate_forecast_kickoff(kickoff)

    def features(
        self,
        match: MatchObservation,
        home_offset: StateOffset = StateOffset(),
        away_offset: StateOffset = StateOffset(),
    ) -> StateFeatures:
        home = self.state_for(match.home_team_id)
        away = self.state_for(match.away_team_id)
        home_attack_edge = (home.attack + home_offset.attack) - (
            away.defence + away_offset.defence
        )
        away_attack_edge = (away.attack + away_offset.attack) - (
            home.defence + home_offset.defence
        )
        style_sum = (
            home.style
            + home_offset.style
            + away.style
            + away_offset.style
        )
        return StateFeatures(home_attack_edge, away_attack_edge, style_sum)

    def update_batch(self, matches: Sequence[MatchObservation]) -> None:
        if not matches:
            return
        self.validate_batch(matches)
        kickoff = matches[0].kickoff

        # Measurements and proposals are computed against one frozen snapshot.
        attack_evidence: dict[str, list[float]] = {}
        defence_evidence: dict[str, list[float]] = {}
        style_evidence: dict[str, list[float]] = {}

        for match in matches:
            if self.mode == "goals":
                home_attack = self.moments["goals"].z_score(
                    match.home_goals, self.min_moment_observations
                )
                away_attack = self.moments["goals"].z_score(
                    match.away_goals, self.min_moment_observations
                )
                tempo = None
            else:
                home_attack = self._raw_attack_measurement(match, "home")
                away_attack = self._raw_attack_measurement(match, "away")
                tempo = self._raw_tempo_measurement(match)

            if home_attack is not None:
                attack_evidence.setdefault(match.home_team_id, []).append(home_attack)
                defence_evidence.setdefault(match.away_team_id, []).append(-home_attack)
            if away_attack is not None:
                attack_evidence.setdefault(match.away_team_id, []).append(away_attack)
                defence_evidence.setdefault(match.home_team_id, []).append(-away_attack)
            if tempo is not None:
                style_evidence.setdefault(match.home_team_id, []).append(tempo)
                style_evidence.setdefault(match.away_team_id, []).append(tempo)

        touched = set(attack_evidence) | set(defence_evidence) | set(style_evidence)
        for team_id in touched:
            state = self.state_for(team_id)
            if team_id in attack_evidence:
                measurement = float(np.mean(attack_evidence[team_id]))
                state.attack = (1.0 - self.alpha) * state.attack + self.alpha * measurement
                state.attack_updates += 1
            if team_id in defence_evidence:
                measurement = float(np.mean(defence_evidence[team_id]))
                state.defence = (1.0 - self.alpha) * state.defence + self.alpha * measurement
                state.defence_updates += 1
            if team_id in style_evidence:
                measurement = float(np.mean(style_evidence[team_id]))
                state.style = (1.0 - self.alpha) * state.style + self.alpha * measurement
                state.style_updates += 1
            state.last_update = kickoff

        # Current-match values enter the standardizers only after all state updates.
        for match in matches:
            self._update_moments(match)
        self._last_batch_kickoff = kickoff

    def _raw_attack_measurement(
        self, match: MatchObservation, side: Literal["home", "away"]
    ) -> float | None:
        values = []
        for name in self.RAW_SIDE_FIELDS:
            value = getattr(match, f"{side}_{name}")
            z_value = self.moments[name].z_score(value, self.min_moment_observations)
            if z_value is not None:
                values.append(z_value)
        return float(np.mean(values)) if len(values) >= 2 else None

    def _raw_tempo_measurement(self, match: MatchObservation) -> float | None:
        values = []
        for name in self.RAW_TOTAL_FIELDS:
            home = _valid_count(getattr(match, f"home_{name}"))
            away = _valid_count(getattr(match, f"away_{name}"))
            total = None if home is None or away is None else home + away
            z_value = self.moments[f"total_{name}"].z_score(
                total, self.min_moment_observations
            )
            if z_value is not None:
                values.append(z_value)
        return float(np.mean(values)) if len(values) >= 2 else None

    def _update_moments(self, match: MatchObservation) -> None:
        self.moments["goals"].update(match.home_goals)
        self.moments["goals"].update(match.away_goals)
        for name in self.RAW_SIDE_FIELDS:
            self.moments[name].update(getattr(match, f"home_{name}"))
            self.moments[name].update(getattr(match, f"away_{name}"))
        for name in self.RAW_TOTAL_FIELDS:
            home = _valid_count(getattr(match, f"home_{name}"))
            away = _valid_count(getattr(match, f"away_{name}"))
            if home is not None and away is not None:
                self.moments[f"total_{name}"].update(home + away)


class PoissonStateLink:
    """Penalized Poisson link from low-dimensional state to team goals."""

    def __init__(self, include_style: bool, penalty: float = 2.0) -> None:
        self.include_style = include_style
        self.penalty = penalty
        self.coefficients: np.ndarray | None = None

    @property
    def is_fitted(self) -> bool:
        return self.coefficients is not None

    def fit(self, rows: Sequence[_TrainingRow]) -> None:
        if not rows:
            raise ValueError("cannot fit without training rows")
        design, targets = self._training_matrix(rows)
        home_goals = np.asarray([row.home_goals for row in rows], dtype=float)
        away_goals = np.asarray([row.away_goals for row in rows], dtype=float)
        away_mean = max(float(np.mean(away_goals)), 0.05)
        home_mean = max(float(np.mean(home_goals)), 0.05)
        initial = np.zeros(design.shape[1], dtype=float)
        initial[0] = log(away_mean)
        initial[1] = np.clip(log(home_mean / away_mean), -1.0, 1.0)

        def objective(theta: np.ndarray) -> tuple[float, np.ndarray]:
            eta = design @ theta
            clipped_eta = np.clip(eta, -2.3, 1.8)
            rates = np.exp(clipped_eta)
            value = float(np.sum(rates - targets * clipped_eta))
            active = ((eta > -2.3) & (eta < 1.8)).astype(float)
            gradient = design.T @ ((rates - targets) * active)
            # beta and optional gamma are the state coefficients (indices >= 2).
            value += self.penalty * float(np.dot(theta[2:], theta[2:]))
            gradient[2:] += 2.0 * self.penalty * theta[2:]
            return value, gradient

        bounds = [(-2.3, 1.8), (-1.0, 1.0)] + [(-2.0, 2.0)] * (design.shape[1] - 2)
        result = minimize(
            objective,
            initial,
            method="L-BFGS-B",
            jac=True,
            bounds=bounds,
            options={"maxiter": 500, "ftol": 1e-10},
        )
        if not result.success or not np.all(np.isfinite(result.x)):
            raise RuntimeError(f"latent-state Poisson fit failed: {result.message}")
        self.coefficients = np.asarray(result.x, dtype=float)

    def predict_rates(self, features: StateFeatures) -> tuple[float, float]:
        if self.coefficients is None:
            raise RuntimeError("Poisson state link is not fitted")
        style = [features.style_sum] if self.include_style else []
        home_row = np.asarray([1.0, 1.0, features.home_attack_edge, *style])
        away_row = np.asarray([1.0, 0.0, features.away_attack_edge, *style])
        home_rate = exp(float(np.clip(home_row @ self.coefficients, -2.3, 1.8)))
        away_rate = exp(float(np.clip(away_row @ self.coefficients, -2.3, 1.8)))
        return home_rate, away_rate

    def _training_matrix(
        self, rows: Sequence[_TrainingRow]
    ) -> tuple[np.ndarray, np.ndarray]:
        design_rows: list[list[float]] = []
        targets: list[float] = []
        for row in rows:
            style = [row.features.style_sum] if self.include_style else []
            design_rows.append([1.0, 1.0, row.features.home_attack_edge, *style])
            targets.append(float(row.home_goals))
            design_rows.append([1.0, 0.0, row.features.away_attack_edge, *style])
            targets.append(float(row.away_goals))
        return np.asarray(design_rows, dtype=float), np.asarray(targets, dtype=float)


class LatentTeamStateForecaster:
    """Walk-forward forecaster that structurally enforces equal-time batching."""

    def __init__(
        self,
        mode: MeasurementMode = "raw",
        burn_in_matches: int = 100,
        refit_every: int = 50,
        half_life_matches: float = 8.0,
        min_moment_observations: int = 20,
        penalty: float = 2.0,
        score_grid_max: int = 10,
    ) -> None:
        if burn_in_matches < 1 or refit_every < 1:
            raise ValueError("burn_in_matches and refit_every must be positive")
        self.mode = mode
        self.burn_in_matches = burn_in_matches
        self.refit_every = refit_every
        self.score_grid_max = score_grid_max
        self.state_filter = DynamicStateFilter(
            mode=mode,
            half_life_matches=half_life_matches,
            min_moment_observations=min_moment_observations,
        )
        self.link = PoissonStateLink(include_style=mode == "raw", penalty=penalty)
        self._rows: list[_TrainingRow] = []
        self._last_fit_size = 0

    @property
    def training_matches(self) -> int:
        return len(self._rows)

    def forecast(
        self,
        match: MatchObservation,
        home_offset: StateOffset = StateOffset(),
        away_offset: StateOffset = StateOffset(),
    ) -> ScorelineForecast | None:
        self.state_filter.validate_forecast_kickoff(match.kickoff)
        home_offset.validate_for(match.kickoff)
        away_offset.validate_for(match.kickoff)
        if not self.link.is_fitted:
            return None
        features = self.state_filter.features(match, home_offset, away_offset)
        lambda_home, lambda_away = self.link.predict_rates(features)
        return build_scoreline_forecast(
            match,
            lambda_home,
            lambda_away,
            self.state_filter.state_for(match.home_team_id),
            self.state_filter.state_for(match.away_team_id),
            self.score_grid_max,
            model_version=f"{MODEL_VERSION}-{self.mode}",
        )

    def process_batch(
        self, matches: Sequence[MatchObservation]
    ) -> list[ScorelineForecast | None]:
        if not matches:
            return []
        self.state_filter.validate_batch(matches)
        if any(match.home_goals is None or match.away_goals is None for match in matches):
            raise ValueError("processed training batches require completed goal outcomes")

        # Freeze states, parameters, and moments for every forecast/training row.
        feature_rows = [self.state_filter.features(match) for match in matches]
        forecasts = [self.forecast(match) for match in matches]
        for match, features in zip(matches, feature_rows, strict=True):
            self._rows.append(
                _TrainingRow(features, int(match.home_goals), int(match.away_goals))
            )

        self.state_filter.update_batch(matches)
        if len(self._rows) >= self.burn_in_matches and (
            not self.link.is_fitted
            or len(self._rows) - self._last_fit_size >= self.refit_every
        ):
            self.link.fit(self._rows)
            self._last_fit_size = len(self._rows)
        return forecasts


def build_scoreline_forecast(
    match: MatchObservation,
    lambda_home: float,
    lambda_away: float,
    home_state: TeamState | None = None,
    away_state: TeamState | None = None,
    score_grid_max: int = 10,
    model_version: str = MODEL_VERSION,
) -> ScorelineForecast:
    """Build a mass-preserving score grid with explicit overflow bins."""

    if lambda_home <= 0 or lambda_away <= 0:
        raise ValueError("Poisson rates must be positive")
    if score_grid_max < 1:
        raise ValueError("score_grid_max must be positive")
    home_vector = _poisson_vector_with_overflow(lambda_home, score_grid_max)
    away_vector = _poisson_vector_with_overflow(lambda_away, score_grid_max)
    grid = np.outer(home_vector, away_vector)

    draw = float(skellam.pmf(0, lambda_home, lambda_away))
    away_win = float(skellam.cdf(-1, lambda_home, lambda_away))
    home_win = float(np.clip(1.0 - draw - away_win, 0.0, 1.0))
    probabilities = np.asarray([home_win, draw, away_win])
    entropy = float(-np.sum(probabilities * np.log(np.clip(probabilities, 1e-15, 1.0))))

    home = home_state or TeamState()
    away = away_state or TeamState()
    return ScorelineForecast(
        model_version=model_version,
        generated_at=datetime.now(UTC).isoformat(),
        kickoff=match.kickoff,
        home_team_id=match.home_team_id,
        away_team_id=match.away_team_id,
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        home_win=home_win,
        draw=draw,
        away_win=away_win,
        outcome_entropy=entropy,
        home_goal_interval_90=(
            int(poisson.ppf(0.05, lambda_home)),
            int(poisson.ppf(0.95, lambda_home)),
        ),
        away_goal_interval_90=(
            int(poisson.ppf(0.05, lambda_away)),
            int(poisson.ppf(0.95, lambda_away)),
        ),
        score_grid_max=score_grid_max,
        score_grid=tuple(tuple(float(value) for value in row) for row in grid),
        home_state_updates=(home.attack_updates, home.defence_updates, home.style_updates),
        away_state_updates=(away.attack_updates, away.defence_updates, away.style_updates),
        home_state_age_days=_state_age_days(match.kickoff, home.last_update),
        away_state_age_days=_state_age_days(match.kickoff, away.last_update),
    )


def joint_poisson_log_loss(
    home_goals: int, away_goals: int, lambda_home: float, lambda_away: float
) -> float:
    return float(
        lambda_home
        - home_goals * log(lambda_home)
        + gammaln(home_goals + 1)
        + lambda_away
        - away_goals * log(lambda_away)
        + gammaln(away_goals + 1)
    )


def ranked_probability_score_1x2(
    forecast: ScorelineForecast, home_goals: int, away_goals: int
) -> float:
    if home_goals > away_goals:
        observed = (1.0, 0.0, 0.0)
    elif home_goals == away_goals:
        observed = (0.0, 1.0, 0.0)
    else:
        observed = (0.0, 0.0, 1.0)
    first = forecast.home_win - observed[0]
    second = forecast.home_win + forecast.draw - observed[0] - observed[1]
    return 0.5 * (first * first + second * second)


def _poisson_vector_with_overflow(rate: float, maximum: int) -> np.ndarray:
    values = np.asarray([exp(-rate) * rate**goal / factorial(goal) for goal in range(maximum + 1)])
    overflow = max(0.0, 1.0 - float(np.sum(values)))
    return np.append(values, overflow)


def _state_age_days(kickoff: int, last_update: int | None) -> float | None:
    if last_update is None:
        return None
    return max(0.0, (kickoff - last_update) / 86_400.0)
