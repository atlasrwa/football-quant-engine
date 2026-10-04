"""Competition-local QFE V2.1 dynamic count-strength challenger.

This is a deliberately minimal structural variant of the frozen QFE V2
DynamicHierarchicalCountBaseline. It preserves the proven decayed
Gamma-Poisson hierarchy and all target-specific hyperparameters, but removes
the cross-competition team-global transfer path.

The team-in-competition posterior therefore shrinks directly toward the
current competition environment. When a team enters a different competition,
its local support starts at zero rather than importing an absolute team rate
estimated relative to the universal global environment.

This module is research-only until chronological evidence promotes it.
"""
from __future__ import annotations

from src.research.data_source import ResearchMatch
from src.research.models.dynamic_count_strength import (
    DynamicHierarchicalCountBaseline,
    RateEstimate,
    Role,
)

COMPETITION_LOCAL_MODEL_VERSION = "qfe-v21-competition-local-gamma-poisson-v1"


class CompetitionLocalDynamicCountBaseline(DynamicHierarchicalCountBaseline):
    """Frozen V2 hierarchy with the team-global transfer path removed."""

    @property
    def model_version(self) -> str:
        return f"{COMPETITION_LOCAL_MODEL_VERSION}:{self.target.name}"

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
        # global_rate remains in the inherited method contract so the
        # challenger is interface-compatible with the reference model. It is
        # intentionally unused: local team strength is defined only relative
        # to the current competition environment.
        del global_rate
        return self._posterior(
            self._state(
                self._team_comp,
                (team_ref, competition_ref, role),
            ),
            timestamp=timestamp,
            prior_mean=competition_rate.rate,
            prior_weight=self.config.team_comp_prior_weight,
        )

    def _update_match(self, match: ResearchMatch) -> None:
        """Update only hierarchy nodes that can influence this challenger."""
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
                self._team_comp,
                (team_ref, competition_ref, role),
            ).update(value, kickoff, half_life)
