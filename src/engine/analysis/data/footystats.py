"""FootyStats data adapter.

Maps raw FootyStats CSV/JSON columns to the canonical MatchRecord schema
using a declarative column mapping dictionary.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src.engine.analysis.data.base import BaseDataLoader

logger = logging.getLogger(__name__)


class FootyStatsAdapter(BaseDataLoader):
    """Maps FootyStats CSV/JSON data to canonical MatchRecord schema.

    The column mapping is purely declarative — adding support for new
    FootyStats field variations requires only updating COLUMN_MAP.
    """

    # Declarative mapping: FootyStats raw column → canonical column
    COLUMN_MAP: dict[str, str] = {
        # Identity
        "id": "match_id",
        "date_unix": "date_unix",
        "competition_id": "league_id",
        "season": "season",
        "home_name": "home_team",
        "away_name": "away_team",
        # Alternative identity fields
        "homeID": "home_team",
        "awayID": "away_team",
        "League": "league_id",
        # xC inputs
        "attacks_home": "attacks_home",
        "attacks_away": "attacks_away",
        "dangerous_attacks_home": "dangerous_attacks_home",
        "dangerous_attacks_away": "dangerous_attacks_away",
        "shots_off_target_home": "shots_off_target_home",
        "shots_off_target_away": "shots_off_target_away",
        "corners_avg_against_home": "corners_avg_against_home",
        "corners_avg_against_away": "corners_avg_against_away",
        # FootyStats alternative names
        "team_a_corners_avg_against": "corners_avg_against_home",
        "team_b_corners_avg_against": "corners_avg_against_away",
        # xB inputs
        "fouls_home": "fouls_home",
        "fouls_away": "fouls_away",
        "team_a_possession": "possession_home",
        "team_b_possession": "possession_away",
        "possession_home": "possession_home",
        "possession_away": "possession_away",
        "referee_cards_per_match": "referee_cards_per_match",
        "referee_cpm": "referee_cards_per_match",
        "team_a_xg_against": "xg_against_home",
        "team_b_xg_against": "xg_against_away",
        "xg_against_home": "xg_against_home",
        "xg_against_away": "xg_against_away",
        # xO inputs
        "offsides_home": "offsides_home",
        "offsides_away": "offsides_away",
        "team_a_offsides": "offsides_home",
        "team_b_offsides": "offsides_away",
        # Market data
        "o25_potential": "over_odds",
        "u25_potential": "under_odds",
        "over_odds": "over_odds",
        "under_odds": "under_odds",
        "over_under_line": "market_line",
        "market_line": "market_line",
        # Outcome
        "totalGoalCount": "actual_total",
        "total_goals": "actual_total",
        "actual_total": "actual_total",
        "homeGoalCount": "_home_goals",
        "awayGoalCount": "_away_goals",
    }

    def __init__(self, column_overrides: dict[str, str] | None = None) -> None:
        """Initialize with optional column mapping overrides.

        Args:
            column_overrides: Additional or replacement column mappings.
        """
        self._column_map = dict(self.COLUMN_MAP)
        if column_overrides:
            self._column_map.update(column_overrides)

    def load(
        self,
        path: Path | None = None,
        data: pd.DataFrame | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Load from file path or pre-loaded DataFrame.

        Args:
            path: Path to CSV or JSON file.
            data: Pre-loaded DataFrame with FootyStats columns.

        Returns:
            Canonical MatchRecord DataFrame.
        """
        if data is not None:
            df = data.copy()
        elif path is not None:
            df = self._read_file(path)
        else:
            raise ValueError("Either 'path' or 'data' must be provided")

        df = self._apply_mapping(df)
        df = self._compute_derived(df)
        df = self.validate_schema(df)

        logger.info("FootyStatsAdapter: loaded %d rows", len(df))
        return df

    def _read_file(self, path: Path) -> pd.DataFrame:
        """Read CSV or JSON file."""
        path = Path(path)
        if path.suffix == ".csv":
            return pd.read_csv(path)
        elif path.suffix == ".json":
            return pd.read_json(path)
        else:
            raise ValueError(f"Unsupported file format: {path.suffix}")

    def _apply_mapping(self, df: pd.DataFrame) -> pd.DataFrame:
        """Rename columns according to the declarative mapping."""
        rename_map: dict[str, str] = {}
        for raw_col, canonical_col in self._column_map.items():
            if raw_col in df.columns and canonical_col not in df.columns:
                rename_map[raw_col] = canonical_col
            elif raw_col in df.columns and canonical_col in rename_map.values():
                # Already mapped, skip duplicates
                continue

        df = df.rename(columns=rename_map)
        return df

    def _compute_derived(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute derived columns from raw fields."""
        # actual_total from home + away goals if not directly available
        if "actual_total" not in df.columns or df["actual_total"].isna().all():
            if "_home_goals" in df.columns and "_away_goals" in df.columns:
                df["actual_total"] = (
                    pd.to_numeric(df["_home_goals"], errors="coerce")
                    + pd.to_numeric(df["_away_goals"], errors="coerce")
                )

        # Default market_line to 2.5 if missing
        if "market_line" not in df.columns or df["market_line"].isna().all():
            df["market_line"] = 2.5

        return df
