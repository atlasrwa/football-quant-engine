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
        """Compute referee volatility index for all matches.

        Two-pass algorithm:
        1. First pass: accumulate goals per referee and compute league-wide stats.
        2. Second pass: assign per-match volatility using referee index or fallback.

        Args:
            matches: List of Match objects (order doesn't matter for this calc).

        Returns:
            Dict mapping match_id to referee_volatility_index.
        """
        # Pass 1: Collect goals per referee
        referee_goals: Dict[str, List[int]] = defaultdict(list)
        all_goals: List[int] = []

        for match in matches:
            all_goals.append(match.total_goals)
            if match.referee is not None:
                referee_goals[match.referee].append(match.total_goals)

        # Compute league-wide fallback volatility
        league_volatility = self._compute_std(all_goals)
        logger.info(
            "League-wide volatility: %.4f (from %d matches)",
            league_volatility, len(all_goals),
        )

        # Compute per-referee volatility (only those with enough matches)
        referee_volatility: Dict[str, float] = {}
        for ref_name, goals in referee_goals.items():
            if len(goals) >= self._min_matches:
                referee_volatility[ref_name] = self._compute_std(goals)
            else:
                referee_volatility[ref_name] = league_volatility
                logger.debug(
                    "Referee '%s' has %d matches (< %d), using league fallback",
                    ref_name, len(goals), self._min_matches,
                )

        # Pass 2: Assign volatility per match
        result: Dict[int, float] = {}
        for match in matches:
            if match.referee is None:
                result[match.id] = league_volatility
            else:
                result[match.id] = referee_volatility.get(
                    match.referee, league_volatility
                )

        logger.info(
            "Computed referee volatility for %d matches (%d unique referees, %d above threshold)",
            len(result),
            len(referee_goals),
            sum(1 for g in referee_goals.values() if len(g) >= self._min_matches),
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
