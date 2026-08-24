"""Referee Volatility Index calculator.

Computes the standard deviation of total goals per referee across officiated matches.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List, Optional

import numpy as np

from src.models.match import Match

logger = logging.getLogger(__name__)


class RefereeVolatilityCalculator:
    """Computes referee volatility index as std dev of total goals.

    If a referee has fewer than min_matches officiated games in the dataset,
    the index falls back to the league-wide mean volatility.

    Matches with missing referee data also use the league-wide fallback.
    """

    def __init__(self, min_matches: int = 5) -> None:
        """Initialize the calculator.

        Args:
            min_matches: Minimum officiated matches before a referee gets
                         their own volatility index (default 5).
        """
        if min_matches < 1:
            raise ValueError(f"min_matches must be >= 1, got {min_matches}")
        self._min_matches = min_matches

    @property
    def min_matches(self) -> int:
        """Minimum match threshold for individual referee stats."""
        return self._min_matches

    def compute_index(
        self, matches: List[Match]
    ) -> Dict[int, float]:
        """Compute referee volatility index for all matches (temporal/expanding).

        For each match at time T, the referee volatility is computed using
        only matches that occurred BEFORE T (look-ahead free). This ensures
        no future information leaks into historical feature values.

        Algorithm:
        1. Sort matches chronologically by date_unix.
        2. For each match, compute referee volatility from prior matches only.
        3. If the referee has fewer than min_matches prior observations,
           fall back to the league-wide expanding volatility.

        Args:
            matches: List of Match objects.

        Returns:
            Dict mapping match_id to referee_volatility_index.
        """
        if not matches:
            return {}

        # Sort chronologically
        sorted_matches = sorted(matches, key=lambda m: m.date_unix)

        # Expanding accumulators
        referee_goals_history: Dict[str, List[int]] = defaultdict(list)
        all_goals_history: List[int] = []

        result: Dict[int, float] = {}

        for match in sorted_matches:
            # Compute volatility BEFORE incorporating this match's data
            league_volatility = self._compute_std(all_goals_history)

            if match.referee is not None:
                ref_history = referee_goals_history[match.referee]
                if len(ref_history) >= self._min_matches:
                    ref_vol = self._compute_std(ref_history)
                else:
                    ref_vol = league_volatility
            else:
                ref_vol = league_volatility

            result[match.id] = ref_vol

            # NOW update histories with this match's data (for next match)
            all_goals_history.append(match.total_goals)
            if match.referee is not None:
                referee_goals_history[match.referee].append(match.total_goals)

        logger.info(
            "Computed referee volatility for %d matches (expanding, look-ahead free)",
            len(result),
        )
        return result

    def compute_referee_stats(
        self, matches: List[Match]
    ) -> Dict[Optional[str], Dict[str, float]]:
        """Compute detailed stats per referee for debugging/inspection.

        Args:
            matches: List of Match objects.

        Returns:
            Dict mapping referee name to stats dict with keys:
            'count', 'mean_goals', 'std_goals', 'uses_fallback'.
        """
        referee_goals: Dict[Optional[str], List[int]] = defaultdict(list)
        all_goals: List[int] = []

        for match in matches:
            all_goals.append(match.total_goals)
            referee_goals[match.referee].append(match.total_goals)

        league_std = self._compute_std(all_goals)
        league_mean = float(np.mean(all_goals)) if all_goals else 0.0

        stats: Dict[Optional[str], Dict[str, float]] = {}
        for ref_name, goals in referee_goals.items():
            count = len(goals)
            stats[ref_name] = {
                "count": count,
                "mean_goals": float(np.mean(goals)),
                "std_goals": self._compute_std(goals),
                "uses_fallback": float(count < self._min_matches),
            }

        return stats

    @staticmethod
    def _compute_std(values: List[int]) -> float:
        """Compute population standard deviation.

        Args:
            values: List of integer values.

        Returns:
            Population std dev. Returns 0.0 for empty or single-element lists.
        """
        if len(values) < 2:
            return 0.0
        return float(np.std(values, ddof=0))
