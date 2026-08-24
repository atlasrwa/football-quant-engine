"""Synthetic data loader for stress-testing.

Generates randomized match data with configurable rates of edge cases:
missing stats, extreme values, postponed fixtures, and boundary conditions.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from src.engine.data.base import BaseDataLoader, MATCH_RECORD_SCHEMA

logger = logging.getLogger(__name__)


class SyntheticDataLoader(BaseDataLoader):
    """Generates randomized match data for stress testing.

    Configurable parameters control the rate of NaN values, extreme
    outliers, and edge-case scenarios.
    """

    def __init__(
        self,
        n: int = 1000,
        seed: int = 42,
        nan_rate: float = 0.05,
        extreme_rate: float = 0.02,
        void_rate: float = 0.01,
    ) -> None:
        """Initialize synthetic data generator.

        Args:
            n: Number of matches to generate.
            seed: Random seed for reproducibility.
            nan_rate: Fraction of values to set as NaN (0.0–1.0).
            extreme_rate: Fraction of values to replace with extremes.
            void_rate: Fraction of matches to mark as postponed/void.
        """
        self.n = n
        self.seed = seed
        self.nan_rate = nan_rate
        self.extreme_rate = extreme_rate
        self.void_rate = void_rate

    def load(self, **kwargs: Any) -> pd.DataFrame:
        """Generate synthetic match data conforming to MatchRecord schema.

        Returns:
            DataFrame with all MATCH_RECORD_SCHEMA columns, including
            injected edge cases.
        """
        rng = np.random.default_rng(self.seed)
        n = kwargs.get("n", self.n)

        teams = [f"Team_{chr(65 + i)}" for i in range(20)]

        df = pd.DataFrame({
            # Identity
            "match_id": np.arange(1, n + 1),
            "date_unix": np.sort(rng.integers(1672531200, 1704067200, n)),
            "league_id": rng.choice([4759, 1625, 2012, 3001, 87], n),
            "season": rng.choice(["2022/2023", "2023/2024"], n),
            "home_team": rng.choice(teams, n),
            "away_team": rng.choice(teams, n),
            # xC inputs
            "attacks_home": rng.integers(40, 160, n).astype(float),
            "attacks_away": rng.integers(40, 160, n).astype(float),
            "dangerous_attacks_home": rng.integers(15, 90, n).astype(float),
            "dangerous_attacks_away": rng.integers(15, 90, n).astype(float),
            "shots_off_target_home": rng.integers(0, 12, n).astype(float),
            "shots_off_target_away": rng.integers(0, 12, n).astype(float),
            "corners_avg_against_home": rng.uniform(2.0, 8.0, n),
            "corners_avg_against_away": rng.uniform(2.0, 8.0, n),
            # xB inputs
            "fouls_home": rng.integers(6, 22, n).astype(float),
            "fouls_away": rng.integers(6, 22, n).astype(float),
            "possession_home": rng.uniform(30.0, 70.0, n),
            "possession_away": rng.uniform(30.0, 70.0, n),
            "referee_cards_per_match": rng.uniform(2.0, 8.0, n),
            "xg_against_home": rng.uniform(0.3, 3.0, n),
            "xg_against_away": rng.uniform(0.3, 3.0, n),
            # xO inputs
            "offsides_home": rng.integers(0, 8, n).astype(float),
            "offsides_away": rng.integers(0, 8, n).astype(float),
            "ppda_home": rng.uniform(4.0, 18.0, n),
            "ppda_away": rng.uniform(4.0, 18.0, n),
            # Market data
            "over_odds": rng.uniform(1.50, 2.80, n),
            "under_odds": rng.uniform(1.50, 2.80, n),
            "market_line": rng.choice([1.5, 2.5, 3.5], n).astype(float),
            # Outcome
            "actual_total": rng.poisson(2.7, n).astype(float),
        })

        # Inject edge cases
        df = self._inject_nan(df, rng)
        df = self._inject_extremes(df, rng)
        df = self._inject_voids(df, rng)

        df = self.validate_schema(df)
        logger.info(
            "SyntheticDataLoader: generated %d rows (nan=%.1f%%, extreme=%.1f%%, void=%.1f%%)",
            n, self.nan_rate * 100, self.extreme_rate * 100, self.void_rate * 100,
        )
        return df

    def _inject_nan(self, df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
        """Randomly set values to NaN to simulate missing data."""
        if self.nan_rate <= 0:
            return df

        float_cols = [
            col for col, dtype in MATCH_RECORD_SCHEMA.items()
            if dtype == "float" and col in df.columns
        ]

        for col in float_cols:
            mask = rng.random(len(df)) < self.nan_rate
            df.loc[mask, col] = np.nan

        return df

    def _inject_extremes(self, df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
        """Replace some values with extreme outliers."""
        if self.extreme_rate <= 0:
            return df

        # Extreme referee cards (>10 per match)
        mask = rng.random(len(df)) < self.extreme_rate
        df.loc[mask, "referee_cards_per_match"] = rng.uniform(10.0, 18.0, mask.sum())

        # Extreme possession (>80% or <20%)
        mask = rng.random(len(df)) < self.extreme_rate
        df.loc[mask, "possession_home"] = rng.choice([15.0, 85.0], mask.sum())

        # Zero attacks (edge case for division)
        mask = rng.random(len(df)) < self.extreme_rate
        df.loc[mask, "attacks_home"] = 0.0

        # Very high offsides
        mask = rng.random(len(df)) < self.extreme_rate
        df.loc[mask, "offsides_home"] = rng.integers(12, 20, mask.sum()).astype(float)

        # Zero PPDA (division by zero edge case)
        mask = rng.random(len(df)) < self.extreme_rate
        df.loc[mask, "ppda_home"] = 0.0

        return df

    def _inject_voids(self, df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
        """Mark some matches as postponed/void (NaN outcomes)."""
        if self.void_rate <= 0:
            return df

        mask = rng.random(len(df)) < self.void_rate
        df.loc[mask, "actual_total"] = np.nan

        return df
