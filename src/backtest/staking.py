"""Volatility-Adjusted Staking calculator.

Scales position size inversely to match goal variance, with floor/cap constraints.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Dict, List, Optional

from src.models.config import StrategyConfig
from src.models.features import MatchFeatures
from src.models.match import Match

logger = logging.getLogger(__name__)


class StakingCalculator:
    """Computes stake size inversely proportional to match goal variance.

    Formula: stake = base_stake * (1 / (1 + match_variance))

    Where match_variance is the average of the rolling std dev of total goals
    for both participating teams over the last N matches.

    Stakes are bounded by:
        - Floor: base_stake * min_stake_multiplier
        - Cap:   base_stake * max_stake_multiplier
    """

    def __init__(self, config: Optional[StrategyConfig] = None) -> None:
        """Initialize StakingCalculator.

        Args:
            config: Strategy configuration with staking parameters.
        """
        self._config = config or StrategyConfig()
        self._base_stake = self._config.base_stake
        self._min_stake = self._base_stake * self._config.min_stake_multiplier
        self._max_stake = self._base_stake * self._config.max_stake_multiplier
        self._variance_window = self._config.variance_rolling_window

    @property
    def base_stake(self) -> float:
        """The base stake size."""
        return self._base_stake

    @property
    def min_stake(self) -> float:
        """The minimum allowed stake."""
        return self._min_stake

    @property
    def max_stake(self) -> float:
        """The maximum allowed stake."""
        return self._max_stake

    def compute_stake(self, match_variance: float) -> float:
        """Compute stake for a given match variance.

        Args:
            match_variance: The combined match goal variance.

        Returns:
            Stake size, bounded by floor and cap.
        """
        raw_stake = self._base_stake * (1.0 / (1.0 + match_variance))
        clamped = max(self._min_stake, min(self._max_stake, raw_stake))
        return round(clamped, 6)

    def compute_match_variance(
        self,
        home_team: str,
        away_team: str,
        team_goal_history: Dict[str, deque],
    ) -> float:
        """Compute combined match variance from team histories.

        Args:
            home_team: Home team name.
            away_team: Away team name.
            team_goal_history: Dict mapping team name to deque of recent total goals.

        Returns:
            Combined match variance: (home_std + away_std) / 2.
            Returns 0.0 if insufficient history for both teams.
        """
        home_std = self._compute_std(team_goal_history.get(home_team, deque()))
        away_std = self._compute_std(team_goal_history.get(away_team, deque()))
        return (home_std + away_std) / 2.0

    def compute_stakes_for_matches(
        self, matches: List[Match]
    ) -> Dict[int, float]:
        """Compute stake sizes for a list of matches using rolling variance.

        Processes matches chronologically. For each match, computes variance
        from prior history (no look-ahead).

        Args:
            matches: List of Match objects sorted chronologically.

        Returns:
            Dict mapping match_id to computed stake size.
        """
        team_goals: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=self._variance_window)
        )

        stakes: Dict[int, float] = {}

        for match in matches:
            # Compute variance BEFORE updating history (no look-ahead)
            variance = self.compute_match_variance(
                match.home_team, match.away_team, team_goals
            )
            stakes[match.id] = self.compute_stake(variance)

            # Update history
            team_goals[match.home_team].append(match.total_goals)
            team_goals[match.away_team].append(match.total_goals)

        logger.info(
            "Computed stakes for %d matches (base=%.2f, min=%.2f, max=%.2f)",
            len(stakes), self._base_stake, self._min_stake, self._max_stake,
        )
        return stakes

    @staticmethod
    def _compute_std(values: deque) -> float:
        """Compute population standard deviation of values.

        Args:
            values: Deque of numeric values.

        Returns:
            Population std dev. Returns 0.0 for empty or single-element inputs.
        """
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5
