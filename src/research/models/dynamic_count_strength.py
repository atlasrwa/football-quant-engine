"""Dynamic hierarchical count strengths and conservative QFE V2 baseline.

This is the first *benchmark* forecasting layer above Foundation V1. It is not a promoted production model and its default hyperparameters are not claimed optimal.

Architecture for each side-specific count process:

    global environment
      -> competition environment
        -> team global venue-role
          -> team-in-competition venue-role
            -> opponent-adjusted forecast

Examples for home goals:
- home team's HOME_ATTACK state measures home goals scored;
- away team's AWAY_DEFENCE state measures home goals conceded;
- both are shrunk toward competition/global priors;
- the final expected count is a conservative log-space blend of those states
  and the competition baseline.

Research walk-forward state updates are point-in-time and availability-gated.
For a target fixture, the default prediction cutoff is six hours before kickoff;
an earlier result becomes admissible only six hours after its own kickoff.
Same-kickoff forecasts are emitted from one frozen state. Market prices are
never inputs. `process_batch` remains a low-level immediate-update primitive for
unit tests/manual state construction; scientific walk-forward code must use
`walk_forward`.
"""

from __future__ import annotations

import hashlib
import heapq
import json
from dataclasses import asdict, dataclass
from math import exp, isfinite, log
from typing import Iterable, Literal, Sequence

from scipy.stats import poisson

from src.research.data_source import ResearchMatch


MODEL_VERSION = "qfe-conservative-dynamic-count-v2-pit-horizon"
DEFAULT_DECISION_HORIZON_SECONDS = 6 * 3600
DEFAULT_AVAILABILITY_EMBARGO_SECONDS = 6 * 3600
Role = Literal[
    "HOME_ATTACK",
    "HOME_DEFENCE",
    "AWAY_ATTACK",
    "AWAY_DEFENCE",
]


@dataclass(frozen=True, slots=True)
class CountTargetSpec:
    name: str
    home_field: str
    away_field: str
    initial_home_rate: float
    initial_away_rate: float
    exclude_extra_time: bool = True

    def __post_init__(self) -> None:
        if self.initial_home_rate <= 0 or self.initial_away_rate <= 0:
            raise ValueError("initial count rates must be positive")

    def observed_counts(
        self,
        match: ResearchMatch,
    ) -> tuple[int, int] | None:
        if self.exclude_extra_time and match.has_extra_time_or_shootout_metadata:
            return None
        home = getattr(match, self.home_field)
        away = getattr(match, self.away_field)
        if home is None or away is None:
            return None
        if isinstance(home, bool) or isinstance(away, bool):
            return None
        if int(home) != home or int(away) != away or home < 0 or away < 0:
            return None
        return int(home), int(away)


GOALS_TARGET = CountTargetSpec(
    name="goals",
    home_field="home_goals",
    away_field="away_goals",
    initial_home_rate=1.35,
    initial_away_rate=1.10,
)
CORNERS_TARGET = CountTargetSpec(
    name="corners",
    home_field="corners_home",
    away_field="corners_away",
    initial_home_rate=5.20,
    initial_away_rate=4.50,
)


@dataclass(frozen=True, slots=True)
class DynamicCountConfig:
    half_life_days: float = 180.0
    global_prior_weight: float = 20.0
    competition_prior_weight: float = 40.0
    team_global_prior_weight: float = 16.0
    team_comp_prior_weight: float = 8.0
    team_influence: float = 0.75
    transfer_factor_floor: float = 0.60
    transfer_factor_ceiling: float = 1.67
    min_effective_team_support: float = 3.0

    def __post_init__(self) -> None:
        positive = (
            self.half_life_days,
            self.global_prior_weight,
            self.competition_prior_weight,
            self.team_global_prior_weight,
            self.team_comp_prior_weight,
        )
        if any(value <= 0 for value in positive):
            raise ValueError("decay/prior weights must be positive")
        if not 0.0 <= self.team_influence <= 1.0:
            raise ValueError("team_influence must be in [0, 1]")
        if not 0 < self.transfer_factor_floor <= 1.0:
            raise ValueError("transfer_factor_floor must be in (0, 1]")
        if self.transfer_factor_ceiling < 1.0:
            raise ValueError("transfer_factor_ceiling must be >= 1")
        if self.transfer_factor_floor > self.transfer_factor_ceiling:
            raise ValueError("transfer factor bounds are incoherent")
        if self.min_effective_team_support < 0:
            raise ValueError("min_effective_team_support must be non-negative")

    @property
    def identity_hash(self) -> str:
        payload = json.dumps(
            asdict(self),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class DecayedCountState:
    weighted_count: float = 0.0
    effective_exposure: float = 0.0
    raw_updates: int = 0
    last_update_ts: int | None = None

    def _factor(self, timestamp: int, half_life_days: float) -> float:
        if self.last_update_ts is None or timestamp <= self.last_update_ts:
            return 1.0
        delta_days = (timestamp - self.last_update_ts) / 86400.0
        return 0.5 ** (delta_days / half_life_days)

    def view(
        self,
        timestamp: int,
        half_life_days: float,
    ) -> tuple[float, float]:
        factor = self._factor(timestamp, half_life_days)
        return self.weighted_count * factor, self.effective_exposure * factor

    def update(
        self,
        value: int,
        timestamp: int,
        half_life_days: float,
    ) -> None:
        if value < 0:
            raise ValueError("count observation must be non-negative")
        if self.last_update_ts is not None and timestamp < self.last_update_ts:
            raise ValueError("state updates must be chronological")
        count, exposure = self.view(timestamp, half_life_days)
        self.weighted_count = count + float(value)
        self.effective_exposure = exposure + 1.0
        self.raw_updates += 1
        self.last_update_ts = timestamp


@dataclass(frozen=True, slots=True)
class RateEstimate:
    rate: float
    effective_observations: float
    raw_updates: int
    prior_mean: float
    prior_weight: float

    @property
    def posterior_weight_from_data(self) -> float:
        denom = self.effective_observations + self.prior_weight
        return self.effective_observations / denom if denom else 0.0


@dataclass(frozen=True, slots=True)
class HierarchyTrace:
    global_home_rate: float
    global_away_rate: float
    competition_home_rate: float
    competition_away_rate: float
    home_attack_rate: float
    away_defence_rate: float
    away_attack_rate: float
    home_defence_rate: float
    home_attack_support: float
    away_defence_support: float
    away_attack_support: float
    home_defence_support: float


@dataclass(frozen=True, slots=True)
class HierarchicalCountForecast:
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
    effective_support: float
    supported: bool
    trace: HierarchyTrace

    def probability_over(self, line: float) -> float:
        """Poisson P(total > line) for integer/half lines.

        Quarter-line settlement is deliberately not collapsed to a Bernoulli
        probability here; downstream settlement contracts own split stakes.
        """
        if line < 0:
            raise ValueError("line must be non-negative")
        doubled = line * 2
        if abs(doubled - round(doubled)) > 1e-9:
            raise ValueError("probability_over supports integer/half lines only")
        threshold = int(line) if float(line).is_integer() else int(line // 1)
        return float(1.0 - poisson.cdf(threshold, self.lambda_total))

    def probability_under(self, line: float) -> float:
        if line < 0:
            raise ValueError("line must be non-negative")
        doubled = line * 2
        if abs(doubled - round(doubled)) > 1e-9:
            raise ValueError("probability_under supports integer/half lines only")
        if float(line).is_integer():
            # Integer line has push mass, so WIN probability excludes the push.
            return float(poisson.cdf(int(line) - 1, self.lambda_total))
        return float(poisson.cdf(int(line // 1), self.lambda_total))

    def push_probability(self, line: float) -> float:
        if not float(line).is_integer():
            return 0.0
        return float(poisson.pmf(int(line), self.lambda_total))


class DynamicHierarchicalCountBaseline:
    """Online target-specific count baseline with hierarchical shrinkage."""

    def __init__(
        self,
        target: CountTargetSpec,
        config: DynamicCountConfig = DynamicCountConfig(),
    ) -> None:
        self.target = target
        self.config = config

        self._global: dict[str, DecayedCountState] = {
            "home": DecayedCountState(),
            "away": DecayedCountState(),
        }
        self._competition: dict[tuple[str, str], DecayedCountState] = {}
        self._team_global: dict[tuple[str, Role], DecayedCountState] = {}
        self._team_comp: dict[tuple[str, str, Role], DecayedCountState] = {}
        self._last_processed_kickoff: int | None = None

    @property
    def model_version(self) -> str:
        return f"{MODEL_VERSION}:{self.target.name}"

    @property
    def last_processed_kickoff(self) -> int | None:
        return self._last_processed_kickoff

    def _initial_rate(self, side: str) -> float:
        return (
            self.target.initial_home_rate
            if side == "home"
            else self.target.initial_away_rate
        )

    def _state(
        self,
        mapping: dict,
        key: object,
    ) -> DecayedCountState:
        state = mapping.get(key)
        if state is None:
            state = DecayedCountState()
            mapping[key] = state
        return state

    def _posterior(
        self,
        state: DecayedCountState,
        *,
        timestamp: int,
        prior_mean: float,
        prior_weight: float,
    ) -> RateEstimate:
        count, exposure = state.view(
            timestamp,
            self.config.half_life_days,
        )
        rate = (count + prior_weight * prior_mean) / (
            exposure + prior_weight
        )
        return RateEstimate(
            rate=max(rate, 1e-6),
            effective_observations=exposure,
            raw_updates=state.raw_updates,
            prior_mean=prior_mean,
            prior_weight=prior_weight,
        )

    def _global_rate(self, side: str, timestamp: int) -> RateEstimate:
        return self._posterior(
            self._global[side],
            timestamp=timestamp,
            prior_mean=self._initial_rate(side),
            prior_weight=self.config.global_prior_weight,
        )

    def _competition_rate(
        self,
        competition_ref: str,
        side: str,
        timestamp: int,
        global_rate: RateEstimate,
    ) -> RateEstimate:
        return self._posterior(
            self._state(self._competition, (competition_ref, side)),
            timestamp=timestamp,
            prior_mean=global_rate.rate,
            prior_weight=self.config.competition_prior_weight,
        )

    @staticmethod
    def _role_side(role: Role) -> str:
        if role in ("HOME_ATTACK", "AWAY_DEFENCE"):
            return "home"
        return "away"

    def _team_rate(
        self,
        *,
        team_ref: str,
        competition_ref: str,
        role: Role,
        timestamp: int,
        global_rate: RateEstimate,
        competition_rate: RateEstimate,
    ) -> RateEstimate:
        global_team = self._posterior(
            self._state(self._team_global, (team_ref, role)),
            timestamp=timestamp,
            prior_mean=global_rate.rate,
            prior_weight=self.config.team_global_prior_weight,
        )
        factor = global_team.rate / max(global_rate.rate, 1e-9)
        factor = min(
            max(factor, self.config.transfer_factor_floor),
            self.config.transfer_factor_ceiling,
        )
        comp_prior_mean = competition_rate.rate * factor
        return self._posterior(
            self._state(
                self._team_comp,
                (team_ref, competition_ref, role),
            ),
            timestamp=timestamp,
            prior_mean=comp_prior_mean,
            prior_weight=self.config.team_comp_prior_weight,
        )

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

    def forecast(self, match: ResearchMatch) -> HierarchicalCountForecast:
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

        global_home = self._global_rate("home", kickoff)
        global_away = self._global_rate("away", kickoff)
        comp_home = self._competition_rate(
            competition_ref,
            "home",
            kickoff,
            global_home,
        )
        comp_away = self._competition_rate(
            competition_ref,
            "away",
            kickoff,
            global_away,
        )

        home_attack = self._team_rate(
            team_ref=home_team,
            competition_ref=competition_ref,
            role="HOME_ATTACK",
            timestamp=kickoff,
            global_rate=global_home,
            competition_rate=comp_home,
        )
        away_defence = self._team_rate(
            team_ref=away_team,
            competition_ref=competition_ref,
            role="AWAY_DEFENCE",
            timestamp=kickoff,
            global_rate=global_home,
            competition_rate=comp_home,
        )
        away_attack = self._team_rate(
            team_ref=away_team,
            competition_ref=competition_ref,
            role="AWAY_ATTACK",
            timestamp=kickoff,
            global_rate=global_away,
            competition_rate=comp_away,
        )
        home_defence = self._team_rate(
            team_ref=home_team,
            competition_ref=competition_ref,
            role="HOME_DEFENCE",
            timestamp=kickoff,
            global_rate=global_away,
            competition_rate=comp_away,
        )

        team_home = (home_attack.rate * away_defence.rate) ** 0.5
        team_away = (away_attack.rate * home_defence.rate) ** 0.5
        w = self.config.team_influence
        lambda_home = exp(
            (1.0 - w) * log(comp_home.rate)
            + w * log(max(team_home, 1e-9))
        )
        lambda_away = exp(
            (1.0 - w) * log(comp_away.rate)
            + w * log(max(team_away, 1e-9))
        )

        supports = (
            home_attack.effective_observations,
            away_defence.effective_observations,
            away_attack.effective_observations,
            home_defence.effective_observations,
        )
        effective_support = min(supports)
        supported = (
            effective_support >= self.config.min_effective_team_support
        )

        return HierarchicalCountForecast(
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
            effective_support=effective_support,
            supported=supported,
            trace=HierarchyTrace(
                global_home_rate=global_home.rate,
                global_away_rate=global_away.rate,
                competition_home_rate=comp_home.rate,
                competition_away_rate=comp_away.rate,
                home_attack_rate=home_attack.rate,
                away_defence_rate=away_defence.rate,
                away_attack_rate=away_attack.rate,
                home_defence_rate=home_defence.rate,
                home_attack_support=home_attack.effective_observations,
                away_defence_support=away_defence.effective_observations,
                away_attack_support=away_attack.effective_observations,
                home_defence_support=home_defence.effective_observations,
            ),
        )

    def _update_match(self, match: ResearchMatch) -> None:
        counts = self.target.observed_counts(match)
        if counts is None:
            return
        (
            _,
            competition_ref,
            home_team,
            away_team,
        ) = self._fixture_identity(match)
        kickoff = int(match.date_unix)
        home_count, away_count = counts
        half_life = self.config.half_life_days

        self._global["home"].update(home_count, kickoff, half_life)
        self._global["away"].update(away_count, kickoff, half_life)
        self._state(
            self._competition,
            (competition_ref, "home"),
        ).update(home_count, kickoff, half_life)
        self._state(
            self._competition,
            (competition_ref, "away"),
        ).update(away_count, kickoff, half_life)

        updates: tuple[tuple[str, Role, int], ...] = (
            (home_team, "HOME_ATTACK", home_count),
            (home_team, "HOME_DEFENCE", away_count),
            (away_team, "AWAY_ATTACK", away_count),
            (away_team, "AWAY_DEFENCE", home_count),
        )
        for team_ref, role, value in updates:
            self._state(
                self._team_global,
                (team_ref, role),
            ).update(value, kickoff, half_life)
            self._state(
                self._team_comp,
                (team_ref, competition_ref, role),
            ).update(value, kickoff, half_life)

    def process_batch(
        self,
        matches: Sequence[ResearchMatch],
    ) -> tuple[HierarchicalCountForecast, ...]:
        """Forecast a same-kickoff batch, then update states from its outcomes."""
        if not matches:
            return ()
        kickoff = matches[0].date_unix
        if any(match.date_unix != kickoff for match in matches):
            raise ValueError("all matches in a batch must have the same kickoff")
        if (
            self._last_processed_kickoff is not None
            and kickoff <= self._last_processed_kickoff
        ):
            raise ValueError("batches must be strictly chronological")

        forecasts = tuple(self.forecast(match) for match in matches)
        for match in matches:
            self._update_match(match)
        self._last_processed_kickoff = int(kickoff)
        return forecasts

    def walk_forward(
        self,
        matches: Iterable[ResearchMatch],
        *,
        decision_horizon_seconds: int = DEFAULT_DECISION_HORIZON_SECONDS,
        availability_embargo_seconds: int = DEFAULT_AVAILABILITY_EMBARGO_SECONDS,
    ) -> tuple[HierarchicalCountForecast, ...]:
        """Generate PIT-safe forecasts under an explicit information horizon.

        A source match is allowed to update state for target fixture F only when::

            source_kickoff + availability_embargo_seconds
                <= F.kickoff - decision_horizon_seconds

        This mirrors the Foundation PIT dataset contract. Outcomes from target
        fixtures are queued after forecasting and become state evidence only
        when their declared availability timestamp is reached by a later target.
        """
        if decision_horizon_seconds <= 0:
            raise ValueError("decision_horizon_seconds must be positive")
        if availability_embargo_seconds < 0:
            raise ValueError("availability_embargo_seconds must be non-negative")

        ordered = sorted(
            matches,
            key=lambda match: (
                match.date_unix,
                match.stable_fixture_key or "",
            ),
        )
        forecasts: list[HierarchicalCountForecast] = []
        # (available_at, stable_key, match) gives deterministic heap ordering.
        pending: list[tuple[int, str, ResearchMatch]] = []

        index = 0
        while index < len(ordered):
            kickoff = int(ordered[index].date_unix)
            cutoff = kickoff - decision_horizon_seconds

            while pending and pending[0][0] <= cutoff:
                _, _, source_match = heapq.heappop(pending)
                self._update_match(source_match)

            batch: list[ResearchMatch] = []
            while index < len(ordered) and int(ordered[index].date_unix) == kickoff:
                batch.append(ordered[index])
                index += 1

            # Freeze state across every fixture at the same kickoff.
            forecasts.extend(self.forecast(match) for match in batch)

            for match in batch:
                fixture_key = match.stable_fixture_key
                if not fixture_key:
                    raise ValueError("stable fixture identity required")
                available_at = int(match.date_unix) + availability_embargo_seconds
                heapq.heappush(pending, (available_at, fixture_key, match))

        return tuple(forecasts)


def poisson_count_nll(observed: int, expected_rate: float) -> float:
    """Per-side Poisson negative log likelihood diagnostic."""
    if observed < 0 or expected_rate <= 0 or not isfinite(expected_rate):
        raise ValueError("invalid count/rate")
    return float(-poisson.logpmf(observed, expected_rate))
