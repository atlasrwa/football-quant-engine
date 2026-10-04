"""QFE V2.1 uncertainty-aware hierarchical log-rate state-space challenger.

This module is additive research code. It does not replace the frozen QFE V2
probability path.

Architecture for each side-specific count process:

    global absolute log-rate
      + competition residual
        + team-global residual (measured relative to competition environment)
          + team-in-competition local residual

Every latent state follows a mean-reverting Gaussian process in log space and
is updated online with a Poisson likelihood using a Laplace/assumed-density
posterior approximation. Crucially, cross-competition team strength is an
environment-relative residual; it is never formed by dividing an absolute team
rate by a universal global count rate.

All forecasts for the same kickoff are emitted from one frozen pre-kickoff
state. Likelihood contributions are then aggregated by latent node before any
state update, making same-kickoff processing deterministic and order-invariant.

Market prices are not accepted by this module.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import exp, isfinite, log, sqrt
import hashlib
import json
from typing import Iterable, Literal, Sequence

from scipy.stats import poisson

from src.research.data_source import ResearchMatch
from src.research.models.dynamic_count_strength import CountTargetSpec, Role

STATE_SPACE_VERSION = "qfe-v21-hierarchical-log-state-space-v2-capable"
Side = Literal["home", "away"]


def _safe_exp(value: float) -> float:
    return exp(min(max(float(value), -20.0), 20.0))


@dataclass(frozen=True, slots=True)
class StateDynamics:
    half_life_days: float
    stationary_sd: float

    def __post_init__(self) -> None:
        if self.half_life_days <= 0:
            raise ValueError("half_life_days must be positive")
        if self.stationary_sd <= 0:
            raise ValueError("stationary_sd must be positive")

    @property
    def stationary_variance(self) -> float:
        return self.stationary_sd * self.stationary_sd


@dataclass(frozen=True, slots=True)
class HierarchicalStateSpaceConfig:
    global_state: StateDynamics
    competition_state: StateDynamics
    team_global_state: StateDynamics
    team_comp_state: StateDynamics
    team_influence: float = 1.0
    min_effective_team_support: float = 3.0
    interval_z: float = 1.6448536269514722
    use_team_global_transfer: bool = True
    intensity_point: Literal["posterior_mean", "posterior_median"] = "posterior_mean"

    def __post_init__(self) -> None:
        if not 0.0 <= self.team_influence <= 1.0:
            raise ValueError("team_influence must be in [0, 1]")
        if self.min_effective_team_support < 0:
            raise ValueError("min_effective_team_support must be non-negative")
        if self.interval_z <= 0:
            raise ValueError("interval_z must be positive")
        if self.intensity_point not in ("posterior_mean", "posterior_median"):
            raise ValueError("unsupported intensity_point")

    @property
    def identity_hash(self) -> str:
        payload = json.dumps(
            asdict(self),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class GaussianStateView:
    mean: float
    variance: float
    effective_observations: float
    raw_updates: int

    @property
    def sd(self) -> float:
        return sqrt(max(self.variance, 0.0))


@dataclass(slots=True)
class GaussianLogState:
    mean: float | None = None
    variance: float | None = None
    effective_observations: float = 0.0
    raw_updates: int = 0
    last_update_ts: int | None = None

    def _rho(self, timestamp: int, dynamics: StateDynamics) -> float:
        if self.last_update_ts is None or timestamp <= self.last_update_ts:
            return 1.0
        delta_days = (timestamp - self.last_update_ts) / 86400.0
        return 0.5 ** (delta_days / dynamics.half_life_days)

    def view(
        self,
        *,
        timestamp: int,
        dynamics: StateDynamics,
        center: float,
    ) -> GaussianStateView:
        if self.last_update_ts is not None and timestamp < self.last_update_ts:
            raise ValueError("state view cannot travel backwards in time")
        if self.mean is None or self.variance is None:
            return GaussianStateView(
                mean=float(center),
                variance=dynamics.stationary_variance,
                effective_observations=0.0,
                raw_updates=self.raw_updates,
            )
        rho = self._rho(timestamp, dynamics)
        mean = float(center) + rho * (self.mean - float(center))
        variance = (
            rho * rho * self.variance
            + (1.0 - rho * rho) * dynamics.stationary_variance
        )
        support = self.effective_observations * rho
        return GaussianStateView(
            mean=mean,
            variance=max(float(variance), 1e-12),
            effective_observations=max(float(support), 0.0),
            raw_updates=self.raw_updates,
        )

    def update_batch(
        self,
        observations: Sequence[tuple[int, float]],
        *,
        timestamp: int,
        dynamics: StateDynamics,
        center: float,
    ) -> None:
        """Apply one order-invariant Poisson/Laplace update.

        Each observation is (count, log_offset) and has likelihood

            count ~ Poisson(exp(log_offset + latent_state)).

        Multiple same-kickoff observations for a shared node are aggregated
        analytically before the one-dimensional posterior mode is solved.
        """
        if not observations:
            return
        if self.last_update_ts is not None and timestamp < self.last_update_ts:
            raise ValueError("state updates must be chronological")
        for count, offset in observations:
            if isinstance(count, bool) or count < 0 or int(count) != count:
                raise ValueError("Poisson counts must be non-negative integers")
            if not isfinite(offset):
                raise ValueError("log offsets must be finite")

        prior = self.view(timestamp=timestamp, dynamics=dynamics, center=center)
        y_sum = float(sum(int(count) for count, _ in observations))
        exposure = sum(_safe_exp(offset) for _, offset in observations)
        if not isfinite(exposure) or exposure <= 0:
            raise ValueError("Poisson exposure must be positive and finite")

        prior_precision = 1.0 / max(prior.variance, 1e-12)
        mode = prior.mean
        for _ in range(50):
            expected = exposure * _safe_exp(mode)
            gradient = -(mode - prior.mean) * prior_precision + y_sum - expected
            precision = prior_precision + expected
            step = gradient / max(precision, 1e-12)
            step = min(max(step, -2.0), 2.0)
            updated = min(max(mode + step, -8.0), 8.0)
            if abs(updated - mode) < 1e-10:
                mode = updated
                break
            mode = updated

        posterior_expected = exposure * _safe_exp(mode)
        posterior_precision = prior_precision + posterior_expected
        posterior_variance = 1.0 / max(posterior_precision, 1e-12)

        self.mean = float(mode)
        self.variance = float(posterior_variance)
        self.effective_observations = (
            prior.effective_observations + float(len(observations))
        )
        self.raw_updates += len(observations)
        self.last_update_ts = int(timestamp)


@dataclass(frozen=True, slots=True)
class RoleStateTrace:
    team_global_effect_mean: float
    team_global_effect_variance: float
    team_comp_effect_mean: float
    team_comp_effect_variance: float
    team_global_support: float
    team_comp_support: float

    @property
    def total_effect_mean(self) -> float:
        return self.team_global_effect_mean + self.team_comp_effect_mean

    @property
    def total_effect_variance(self) -> float:
        return (
            self.team_global_effect_variance
            + self.team_comp_effect_variance
        )


@dataclass(frozen=True, slots=True)
class StateSpaceTrace:
    global_home_log_rate: float
    global_away_log_rate: float
    competition_home_effect: float
    competition_away_effect: float
    competition_home_log_rate: float
    competition_away_log_rate: float
    competition_home_variance: float
    competition_away_variance: float
    home_attack: RoleStateTrace
    away_defence: RoleStateTrace
    away_attack: RoleStateTrace
    home_defence: RoleStateTrace
    latent_log_variance_home: float
    latent_log_variance_away: float


@dataclass(frozen=True, slots=True)
class StateSpaceCountForecast:
    model_version: str
    config_hash: str
    target: str
    fixture_key: str
    kickoff_ts: int
    competition_ref: str
    home_team_ref: str
    away_team_ref: str
    lambda_home: float
    lambda_away: float
    lambda_total: float
    median_lambda_home: float
    median_lambda_away: float
    latent_log_sd_home: float
    latent_log_sd_away: float
    home_expected_rate_interval_90: tuple[float, float]
    away_expected_rate_interval_90: tuple[float, float]
    effective_support: float
    supported: bool
    trace: StateSpaceTrace

    def probability_over(self, line: float) -> float:
        if line < 0:
            raise ValueError("line must be non-negative")
        doubled = line * 2
        if abs(doubled - round(doubled)) > 1e-9:
            raise ValueError("probability_over supports integer/half lines only")
        threshold = int(line) if float(line).is_integer() else int(line // 1)
        return float(1.0 - poisson.cdf(threshold, self.lambda_total))


@dataclass(frozen=True, slots=True)
class _Context:
    forecast: StateSpaceCountForecast
    global_home: GaussianStateView
    global_away: GaussianStateView
    competition_home: GaussianStateView
    competition_away: GaussianStateView
    competition_home_log_rate: float
    competition_away_log_rate: float


class HierarchicalLogStateSpaceModel:
    """Online hierarchical Poisson state-space model with explicit uncertainty."""

    def __init__(
        self,
        target: CountTargetSpec,
        config: HierarchicalStateSpaceConfig,
    ) -> None:
        self.target = target
        self.config = config
        self._global: dict[Side, GaussianLogState] = {
            "home": GaussianLogState(),
            "away": GaussianLogState(),
        }
        self._competition: dict[tuple[str, Side], GaussianLogState] = {}
        self._team_global: dict[tuple[str, Role], GaussianLogState] = {}
        self._team_comp: dict[tuple[str, str, Role], GaussianLogState] = {}
        self._last_processed_kickoff: int | None = None

    @property
    def model_version(self) -> str:
        return f"{STATE_SPACE_VERSION}:{self.target.name}"

    @property
    def last_processed_kickoff(self) -> int | None:
        return self._last_processed_kickoff

    def _state(self, mapping: dict, key: object) -> GaussianLogState:
        state = mapping.get(key)
        if state is None:
            state = GaussianLogState()
            mapping[key] = state
        return state

    def _initial_log_rate(self, side: Side) -> float:
        rate = (
            self.target.initial_home_rate
            if side == "home"
            else self.target.initial_away_rate
        )
        return log(rate)

    @staticmethod
    def _role_side(role: Role) -> Side:
        if role in ("HOME_ATTACK", "AWAY_DEFENCE"):
            return "home"
        return "away"

    def _fixture_identity(
        self,
        match: ResearchMatch,
    ) -> tuple[str, str, str, str]:
        if (
            not match.stable_fixture_key
            or not match.competition_ref
            or not match.home_team_ref
            or not match.away_team_ref
        ):
            raise ValueError("stable fixture/competition/team identity is required")
        return (
            match.stable_fixture_key,
            match.competition_ref,
            match.home_team_ref,
            match.away_team_ref,
        )

    def _global_view(self, side: Side, timestamp: int) -> GaussianStateView:
        return self._global[side].view(
            timestamp=timestamp,
            dynamics=self.config.global_state,
            center=self._initial_log_rate(side),
        )

    def _competition_view(
        self,
        competition_ref: str,
        side: Side,
        timestamp: int,
    ) -> GaussianStateView:
        return self._state(
            self._competition,
            (competition_ref, side),
        ).view(
            timestamp=timestamp,
            dynamics=self.config.competition_state,
            center=0.0,
        )

    def _role_trace(
        self,
        *,
        team_ref: str,
        competition_ref: str,
        role: Role,
        timestamp: int,
    ) -> RoleStateTrace:
        if self.config.use_team_global_transfer:
            global_team = self._state(
                self._team_global,
                (team_ref, role),
            ).view(
                timestamp=timestamp,
                dynamics=self.config.team_global_state,
                center=0.0,
            )
        else:
            global_team = GaussianStateView(
                mean=0.0,
                variance=0.0,
                effective_observations=0.0,
                raw_updates=0,
            )
        local_team = self._state(
            self._team_comp,
            (team_ref, competition_ref, role),
        ).view(
            timestamp=timestamp,
            dynamics=self.config.team_comp_state,
            center=0.0,
        )
        return RoleStateTrace(
            team_global_effect_mean=global_team.mean,
            team_global_effect_variance=global_team.variance,
            team_comp_effect_mean=local_team.mean,
            team_comp_effect_variance=local_team.variance,
            team_global_support=global_team.effective_observations,
            team_comp_support=local_team.effective_observations,
        )

    def _context(self, match: ResearchMatch) -> _Context:
        (
            fixture_key,
            competition_ref,
            home_team,
            away_team,
        ) = self._fixture_identity(match)
        kickoff = int(match.date_unix)
        if (
            self._last_processed_kickoff is not None
            and kickoff <= self._last_processed_kickoff
        ):
            raise ValueError(
                "forecast kickoff must be later than all processed kickoffs"
            )

        global_home = self._global_view("home", kickoff)
        global_away = self._global_view("away", kickoff)
        competition_home = self._competition_view(
            competition_ref,
            "home",
            kickoff,
        )
        competition_away = self._competition_view(
            competition_ref,
            "away",
            kickoff,
        )

        comp_home_log = global_home.mean + competition_home.mean
        comp_away_log = global_away.mean + competition_away.mean
        comp_home_var = global_home.variance + competition_home.variance
        comp_away_var = global_away.variance + competition_away.variance

        home_attack = self._role_trace(
            team_ref=home_team,
            competition_ref=competition_ref,
            role="HOME_ATTACK",
            timestamp=kickoff,
        )
        away_defence = self._role_trace(
            team_ref=away_team,
            competition_ref=competition_ref,
            role="AWAY_DEFENCE",
            timestamp=kickoff,
        )
        away_attack = self._role_trace(
            team_ref=away_team,
            competition_ref=competition_ref,
            role="AWAY_ATTACK",
            timestamp=kickoff,
        )
        home_defence = self._role_trace(
            team_ref=home_team,
            competition_ref=competition_ref,
            role="HOME_DEFENCE",
            timestamp=kickoff,
        )

        w = self.config.team_influence
        home_effect = 0.5 * (
            home_attack.total_effect_mean
            + away_defence.total_effect_mean
        )
        away_effect = 0.5 * (
            away_attack.total_effect_mean
            + home_defence.total_effect_mean
        )
        log_median_home = comp_home_log + w * home_effect
        log_median_away = comp_away_log + w * away_effect

        home_effect_variance = 0.25 * (
            home_attack.total_effect_variance
            + away_defence.total_effect_variance
        )
        away_effect_variance = 0.25 * (
            away_attack.total_effect_variance
            + home_defence.total_effect_variance
        )
        log_var_home = comp_home_var + w * w * home_effect_variance
        log_var_away = comp_away_var + w * w * away_effect_variance

        median_home = _safe_exp(log_median_home)
        median_away = _safe_exp(log_median_away)
        if self.config.intensity_point == "posterior_mean":
            lambda_home = _safe_exp(log_median_home + 0.5 * log_var_home)
            lambda_away = _safe_exp(log_median_away + 0.5 * log_var_away)
        else:
            lambda_home = median_home
            lambda_away = median_away
        sd_home = sqrt(max(log_var_home, 0.0))
        sd_away = sqrt(max(log_var_away, 0.0))
        z = self.config.interval_z
        interval_home = (
            _safe_exp(log_median_home - z * sd_home),
            _safe_exp(log_median_home + z * sd_home),
        )
        interval_away = (
            _safe_exp(log_median_away - z * sd_away),
            _safe_exp(log_median_away + z * sd_away),
        )

        if self.config.use_team_global_transfer:
            support_values = (
                home_attack.team_global_support,
                away_defence.team_global_support,
                away_attack.team_global_support,
                home_defence.team_global_support,
            )
        else:
            support_values = (
                home_attack.team_comp_support,
                away_defence.team_comp_support,
                away_attack.team_comp_support,
                home_defence.team_comp_support,
            )
        effective_support = min(support_values)
        supported = (
            effective_support >= self.config.min_effective_team_support
        )

        forecast = StateSpaceCountForecast(
            model_version=self.model_version,
            config_hash=self.config.identity_hash,
            target=self.target.name,
            fixture_key=fixture_key,
            kickoff_ts=kickoff,
            competition_ref=competition_ref,
            home_team_ref=home_team,
            away_team_ref=away_team,
            lambda_home=lambda_home,
            lambda_away=lambda_away,
            lambda_total=lambda_home + lambda_away,
            median_lambda_home=median_home,
            median_lambda_away=median_away,
            latent_log_sd_home=sd_home,
            latent_log_sd_away=sd_away,
            home_expected_rate_interval_90=interval_home,
            away_expected_rate_interval_90=interval_away,
            effective_support=effective_support,
            supported=supported,
            trace=StateSpaceTrace(
                global_home_log_rate=global_home.mean,
                global_away_log_rate=global_away.mean,
                competition_home_effect=competition_home.mean,
                competition_away_effect=competition_away.mean,
                competition_home_log_rate=comp_home_log,
                competition_away_log_rate=comp_away_log,
                competition_home_variance=comp_home_var,
                competition_away_variance=comp_away_var,
                home_attack=home_attack,
                away_defence=away_defence,
                away_attack=away_attack,
                home_defence=home_defence,
                latent_log_variance_home=log_var_home,
                latent_log_variance_away=log_var_away,
            ),
        )
        return _Context(
            forecast=forecast,
            global_home=global_home,
            global_away=global_away,
            competition_home=competition_home,
            competition_away=competition_away,
            competition_home_log_rate=comp_home_log,
            competition_away_log_rate=comp_away_log,
        )

    def forecast(self, match: ResearchMatch) -> StateSpaceCountForecast:
        return self._context(match).forecast

    def _apply_batch_updates(
        self,
        matches: Sequence[ResearchMatch],
        contexts: Sequence[_Context],
    ) -> None:
        if len(matches) != len(contexts):
            raise ValueError("matches/contexts length mismatch")
        if not matches:
            return
        kickoff = int(matches[0].date_unix)

        global_obs: dict[Side, list[tuple[int, float]]] = {
            "home": [],
            "away": [],
        }
        comp_obs: dict[tuple[str, Side], list[tuple[int, float]]] = {}
        team_global_obs: dict[
            tuple[str, Role],
            list[tuple[int, float]],
        ] = {}
        team_comp_obs: dict[
            tuple[str, str, Role],
            list[tuple[int, float]],
        ] = {}

        for match, context in zip(matches, contexts, strict=True):
            counts = self.target.observed_counts(match)
            if counts is None:
                continue
            (
                _,
                competition_ref,
                home_team,
                away_team,
            ) = self._fixture_identity(match)
            home_count, away_count = counts

            global_obs["home"].append((home_count, 0.0))
            global_obs["away"].append((away_count, 0.0))
            comp_obs.setdefault((competition_ref, "home"), []).append(
                (home_count, context.global_home.mean)
            )
            comp_obs.setdefault((competition_ref, "away"), []).append(
                (away_count, context.global_away.mean)
            )

            role_rows: tuple[
                tuple[str, Role, int, float],
                ...,
            ] = (
                (
                    home_team,
                    "HOME_ATTACK",
                    home_count,
                    context.competition_home_log_rate,
                ),
                (
                    away_team,
                    "AWAY_DEFENCE",
                    home_count,
                    context.competition_home_log_rate,
                ),
                (
                    away_team,
                    "AWAY_ATTACK",
                    away_count,
                    context.competition_away_log_rate,
                ),
                (
                    home_team,
                    "HOME_DEFENCE",
                    away_count,
                    context.competition_away_log_rate,
                ),
            )
            trace_by_role = {
                (home_team, "HOME_ATTACK"): context.forecast.trace.home_attack,
                (away_team, "AWAY_DEFENCE"): context.forecast.trace.away_defence,
                (away_team, "AWAY_ATTACK"): context.forecast.trace.away_attack,
                (home_team, "HOME_DEFENCE"): context.forecast.trace.home_defence,
            }
            for team_ref, role, count, comp_log_rate in role_rows:
                if self.config.use_team_global_transfer:
                    team_global_obs.setdefault((team_ref, role), []).append(
                        (count, comp_log_rate)
                    )
                    team_global_effect = trace_by_role[
                        (team_ref, role)
                    ].team_global_effect_mean
                else:
                    team_global_effect = 0.0
                team_comp_obs.setdefault(
                    (team_ref, competition_ref, role),
                    [],
                ).append(
                    (
                        count,
                        comp_log_rate + team_global_effect,
                    )
                )

        for side in ("home", "away"):
            self._global[side].update_batch(
                global_obs[side],
                timestamp=kickoff,
                dynamics=self.config.global_state,
                center=self._initial_log_rate(side),
            )
        for key, observations in comp_obs.items():
            self._state(self._competition, key).update_batch(
                observations,
                timestamp=kickoff,
                dynamics=self.config.competition_state,
                center=0.0,
            )
        for key, observations in team_global_obs.items():
            self._state(self._team_global, key).update_batch(
                observations,
                timestamp=kickoff,
                dynamics=self.config.team_global_state,
                center=0.0,
            )
        for key, observations in team_comp_obs.items():
            self._state(self._team_comp, key).update_batch(
                observations,
                timestamp=kickoff,
                dynamics=self.config.team_comp_state,
                center=0.0,
            )

    def process_batch(
        self,
        matches: Sequence[ResearchMatch],
    ) -> tuple[StateSpaceCountForecast, ...]:
        if not matches:
            return ()
        kickoff = int(matches[0].date_unix)
        if any(int(match.date_unix) != kickoff for match in matches):
            raise ValueError("all matches in a batch must have the same kickoff")
        if (
            self._last_processed_kickoff is not None
            and kickoff <= self._last_processed_kickoff
        ):
            raise ValueError("batches must be strictly chronological")

        contexts = tuple(self._context(match) for match in matches)
        forecasts = tuple(context.forecast for context in contexts)
        self._apply_batch_updates(matches, contexts)
        self._last_processed_kickoff = kickoff
        return forecasts

    def walk_forward(
        self,
        matches: Iterable[ResearchMatch],
    ) -> tuple[StateSpaceCountForecast, ...]:
        ordered = sorted(
            matches,
            key=lambda match: (
                match.date_unix,
                match.stable_fixture_key or "",
            ),
        )
        forecasts: list[StateSpaceCountForecast] = []
        batch: list[ResearchMatch] = []
        current_kickoff: int | None = None
        for match in ordered:
            kickoff = int(match.date_unix)
            if current_kickoff is None:
                current_kickoff = kickoff
            if kickoff != current_kickoff:
                forecasts.extend(self.process_batch(batch))
                batch = []
                current_kickoff = kickoff
            batch.append(match)
        if batch:
            forecasts.extend(self.process_batch(batch))
        return tuple(forecasts)
