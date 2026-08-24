"""Shared test fixtures and the SyntheticMatchGenerator."""

from __future__ import annotations

import random
from typing import List, Optional

import pytest

from src.models.match import Match


class SyntheticMatchGenerator:
    """Generates synthetic match data with controllable distributions.

    Useful for stress testing, edge case coverage, and parameterized tests
    where specific statistical properties are needed.
    """

    # Default team and referee pools
    TEAMS = [
        "Arsenal", "Chelsea", "Liverpool", "Man City", "Man Utd",
        "Tottenham", "Newcastle", "Aston Villa", "Brighton", "Wolves",
    ]
    REFEREES = [
        "Michael Oliver", "Anthony Taylor", "Craig Pawson",
        "Simon Hooper", "Robert Jones",
    ]

    def __init__(self, seed: int = 42) -> None:
        """Initialize with a fixed random seed for reproducibility.

        Args:
            seed: Random seed for deterministic generation.
        """
        self._rng = random.Random(seed)

    def generate(
        self,
        n_matches: int = 500,
        mean_goals: float = 2.7,
        goal_std: float = 1.4,
        xg_noise: float = 0.3,
        referee_null_pct: float = 0.03,
        seed: Optional[int] = None,
    ) -> List[Match]:
        """Generate a list of synthetic Match objects.

        Args:
            n_matches: Number of matches to generate.
            mean_goals: Mean total goals per match (Poisson-like via normal approx).
            goal_std: Standard deviation of total goals.
            xg_noise: Std dev of noise added to xG relative to actual goals.
            referee_null_pct: Fraction of matches with null referee.
            seed: Optional override seed (re-seeds the generator).

        Returns:
            List of Match objects sorted chronologically by date_unix.
        """
        if seed is not None:
            self._rng = random.Random(seed)

        matches: List[Match] = []
        base_timestamp = 1693526400  # Sept 1, 2023

        for i in range(n_matches):
            home_team, away_team = self._rng.sample(self.TEAMS, 2)

            # Generate goals using clamped normal distribution
            total = max(0, round(self._rng.gauss(mean_goals, goal_std)))
            home_goals = self._rng.randint(0, total)
            away_goals = total - home_goals

            # xG with noise relative to actual goals
            home_xg = max(0.0, home_goals + self._rng.gauss(0, xg_noise))
            away_xg = max(0.0, away_goals + self._rng.gauss(0, xg_noise))

            # Referee assignment
            if self._rng.random() < referee_null_pct:
                referee = None
            else:
                referee = self._rng.choice(self.REFEREES)

            # Odds generation (realistic range for over/under 2.5)
            over_odds = round(self._rng.uniform(1.45, 2.20), 2)
            under_odds = round(self._rng.uniform(1.70, 2.60), 2)

            match = Match(
                id=10000 + i,
                date_unix=base_timestamp + (i * 86400),  # 1 match per day
                league_id=4759,
                season="2023",
                home_team=home_team,
                away_team=away_team,
                home_goals=home_goals,
                away_goals=away_goals,
                total_goals=home_goals + away_goals,
                home_xg=round(home_xg, 2),
                away_xg=round(away_xg, 2),
                referee=referee,
                over_under_line=2.5,
                over_odds=over_odds,
                under_odds=under_odds,
            )
            matches.append(match)

        return matches


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def synthetic_generator() -> SyntheticMatchGenerator:
    """Provide a SyntheticMatchGenerator with default seed."""
    return SyntheticMatchGenerator(seed=42)


@pytest.fixture
def synthetic_matches(synthetic_generator: SyntheticMatchGenerator) -> List[Match]:
    """Provide 100 synthetic matches for testing."""
    return synthetic_generator.generate(n_matches=100)


@pytest.fixture
def tmp_cache_dir(tmp_path):
    """Provide a temporary cache directory for CacheManager tests."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return cache_dir


@pytest.fixture
def tmp_errors_dir(tmp_path):
    """Provide a temporary errors directory for validator tests."""
    errors_dir = tmp_path / "errors"
    errors_dir.mkdir()
    return errors_dir
