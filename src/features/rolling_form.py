"""Rolling Form calculator.

Computes per-team rolling form score (W=3, D=1, L=0) normalized to [0, 1].
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Dict, List, Tuple

from src.models.match import Match

logger = logging.getLogger(__name__)


class RollingFormCalculator:
    """Computes rolling form per team over a configurable window.

    Form is calculated as points earned (W=3, D=1, L=0) over the last
    N matches, normalized to [0, 1] by dividing by (3 * N).

    For teams with fewer than N historical matches, the available
    history is used (normalized by 3 * actual_count).
    """

    def __init__(self, window: int = 6) -> None:
        """Initialize the calculator.

        Args:
            window: Number of recent matches for rolling form (default 6).
        """
        if window < 1:
            raise ValueError(f"window must be >= 1, got {window}")
        self._window = window

    @property
    def window(self) -> int:
        """The rolling window size."""
        return self._window

    @staticmethod
    def match_points(team: str, match: Match) -> int:
        """Determine points earned by a team in a match.

        Args:
            team: The team name.
            match: The match object.

        Returns:
            3 for win, 1 for draw, 0 for loss.

        Raises:
            ValueError: If team is not in the match.
        """
        if team == match.home_team:
            if match.home_goals > match.away_goals:
                return 3
            elif match.home_goals == match.away_goals:
                return 1
            else:
                return 0
        elif team == match.away_team:
            if match.away_goals > match.home_goals:
                return 3
            elif match.away_goals == match.home_goals:
                return 1
            else:
                return 0
        else:
            raise ValueError(f"Team '{team}' not found in match {match.id}")

    def compute_rolling(
        self, matches: List[Match]
    ) -> List[Tuple[int, float, float]]:
        """Compute rolling form for all matches.

        Processes matches chronologically. For each match, returns the
        normalized rolling form for both teams *before* incorporating
        the current match (look-ahead free).

        Args:
            matches: List of Match objects sorted chronologically.

        Returns:
            List of tuples: (match_id, home_form, away_form).
            Each form value is in [0, 1].
        """
        # Per-team rolling window of recent points
        team_points: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=self._window)
        )

        results: List[Tuple[int, float, float]] = []

        for match in matches:
            # Get current rolling form BEFORE updating
            home_history = team_points[match.home_team]
            away_history = team_points[match.away_team]

            home_form = self._normalize(home_history)
            away_form = self._normalize(away_history)

            results.append((match.id, home_form, away_form))

            # Update histories with this match's points
            home_pts = self.match_points(match.home_team, match)
            away_pts = self.match_points(match.away_team, match)

            team_points[match.home_team].append(home_pts)
            team_points[match.away_team].append(away_pts)

        logger.info(
            "Computed rolling form for %d matches (window=%d)",
            len(results), self._window,
        )
        return results

    def compute_rolling_map(
        self, matches: List[Match]
    ) -> Dict[int, Tuple[float, float]]:
        """Compute rolling form and return as a match_id → (home, away) map.

        Args:
            matches: List of Match objects sorted chronologically.

        Returns:
            Dict mapping match_id to (home_form, away_form).
        """
        results = self.compute_rolling(matches)
        return {match_id: (home, away) for match_id, home, away in results}

    def _normalize(self, history: deque) -> float:
        """Normalize points history to [0, 1].

        Args:
            history: Deque of recent match points.

        Returns:
            Normalized form in [0, 1]. Returns 0.0 if no history.
        """
        if not history:
            return 0.0
        total_points = sum(history)
        max_possible = 3 * len(history)
        return total_points / max_possible
