"""Abstract base class and canonical schema for data providers.

All data loaders must produce DataFrames conforming to MATCH_RECORD_SCHEMA,
ensuring the x-Metric engine operates identically regardless of data source.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Canonical column schema — every loader must produce these columns.
# Values are the expected dtype category: "int", "float", "str".
MATCH_RECORD_SCHEMA: dict[str, str] = {
    # Identity
    "match_id": "int",
    "date_unix": "int",
    "league_id": "int",
    "season": "str",
    "home_team": "str",
    "away_team": "str",
    # xC inputs
    "attacks_home": "float",
    "attacks_away": "float",
    "dangerous_attacks_home": "float",
    "dangerous_attacks_away": "float",
    "shots_off_target_home": "float",
    "shots_off_target_away": "float",
    "corners_avg_against_home": "float",
    "corners_avg_against_away": "float",
    # xB inputs
    "fouls_home": "float",
    "fouls_away": "float",
    "possession_home": "float",
    "possession_away": "float",
    "referee_cards_per_match": "float",
    "xg_against_home": "float",
    "xg_against_away": "float",
    # xO inputs
    "offsides_home": "float",
    "offsides_away": "float",
    "ppda_home": "float",
    "ppda_away": "float",
    # Market data
    "over_odds": "float",
    "under_odds": "float",
    "market_line": "float",
    # Outcome (for backtesting)
    "actual_total": "float",
}


class BaseDataLoader(ABC):
    """Abstract base for all data providers.

    Subclasses implement `load()` to produce a DataFrame with the
    canonical MATCH_RECORD_SCHEMA columns.
    """

    @abstractmethod
    def load(self, **kwargs: Any) -> pd.DataFrame:
        """Load data and return canonical MatchRecord DataFrame.

        Returns:
            DataFrame with columns matching MATCH_RECORD_SCHEMA.
        """
        ...

    def validate_schema(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ensure DataFrame conforms to MatchRecord schema.

        Adds missing columns as NaN/empty, coerces types, and logs warnings
        for missing required columns.

        Returns:
            DataFrame with all schema columns present.
        """
        for col, dtype_str in MATCH_RECORD_SCHEMA.items():
            if col not in df.columns:
                if dtype_str == "str":
                    df[col] = ""
                else:
                    df[col] = np.nan
                logger.warning("Schema validation: column '%s' missing, filled with default", col)
            else:
                # Coerce types
                if dtype_str == "float":
                    df[col] = pd.to_numeric(df[col], errors="coerce").astype(np.float64)
                elif dtype_str == "int":
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                elif dtype_str == "str":
                    df[col] = df[col].astype(str)

        # Ensure column order matches schema
        schema_cols = list(MATCH_RECORD_SCHEMA.keys())
        extra_cols = [c for c in df.columns if c not in schema_cols]
        df = df[schema_cols + extra_cols]

        n_rows = len(df)
        n_complete = df[schema_cols].notna().all(axis=1).sum()
        logger.info(
            "Schema validation: %d rows, %d fully complete (%.1f%%)",
            n_rows, n_complete, (n_complete / n_rows * 100) if n_rows > 0 else 0,
        )
        return df
