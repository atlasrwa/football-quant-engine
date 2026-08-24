"""xG Efficiency Delta calculator.

Computes per-team xG efficiency delta and rolling mean over a configurable window.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Dict, List, Tuple

from src.models.match import Match

logger = logging.getLogger(__name__)


class XGEfficiencyCalculator:
    """Computes xG efficiency delta per team with rolling averages.

    The xG efficiency delta measures how a team over/under-performs
    relative to their expected goals:
        delta = (actual_goals - xg) / xg

    When xg == 0, delta is set to 0.0 to avoid division by zero.

    The calculator maintains a rolling window of deltas per team and
    returns the rolling mean at each match point.
    """

    def __init__(self, window: int = 5) -> None:
        """Initialize the calculator.

        Args:
            window: Number of recent matches for rolling mean (default 5).
        """
        if window < 1:
            raise ValueError(f"window must be >= 1, got {window}")
        self._window = window

    @property
    def window(self) -> int:
        """The rolling window size."""
        return self._window

    @staticmethod
    def compute_delta(actual_goals: int, xg: float) -> float:
        """Compute single-match xG efficiency delta.

        Args:
            actual_goals: Goals actually scored.
            xg: Expected goals.

        Returns:
            The efficiency delta, or 0.0 if xg is zero.
        """
        if xg == 0.0:
            return 0.0
        return (actual_goals - xg) / xg

    def compute_rolling(
        self, matches: List[Match]
    ) -> List[Tuple[int, float, float]]:
        """Compute rolling xG efficiency delta for all matches.

        Processes matches in chronological order (assumes input is sorted
        by date_unix). For each match, returns the rolling mean delta for
        both the home and away team *before* incorporating the current match
        (look-ahead free).

        Args:
            matches: List of Match objects sorted chronologically.

        Returns:
            List of tuples: (match_id, home_rolling_delta, away_rolling_delta).
            Each delta is the rolling mean of the team's prior deltas.
        """
        # Per-team rolling window of recent deltas
        team_deltas: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=self._window)
        )

        results: List[Tuple[int, float, float]] = []

        for match in matches:
            # Get current rolling means BEFORE updating (no look-ahead)
            home_history = team_deltas[match.home_team]
            away_history = team_deltas[match.away_team]

            home_rolling = (
                sum(home_history) / len(home_history) if home_history else 0.0
            )
            away_rolling = (
                sum(away_history) / len(away_history) if away_history else 0.0
            )

            results.append((match.id, home_rolling, away_rolling))

            # Now update histories with this match's deltas
            home_delta = self.compute_delta(match.home_goals, match.home_xg)
            away_delta = self.compute_delta(match.away_goals, match.away_xg)

            team_deltas[match.home_team].append(home_delta)
            team_deltas[match.away_team].append(away_delta)

        logger.info(
            "Computed xG efficiency deltas for %d matches (window=%d)",
            len(results), self._window,
        )
        return results

    def compute_rolling_map(
        self, matches: List[Match]
    ) -> Dict[int, Tuple[float, float]]:
        """Compute rolling deltas and return as a match_id → (home, away) map.

        Args:
            matches: List of Match objects sorted chronologically.

        Returns:
            Dict mapping match_id to (home_rolling_delta, away_rolling_delta).
        """
        results = self.compute_rolling(matches)
        return {match_id: (home, away) for match_id, home, away in results}
