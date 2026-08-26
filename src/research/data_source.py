"""Research data source abstraction.

Defines the interface for providing normalized football match data
to the research laboratory. Data-source-agnostic: the lab does not
know whether data came from FootyStats, CSV, database, or synthetic
generator.

Every data source must provide:
- Match records with all available raw fields
- Market data (odds/lines)
- Team history
- League context
- Available field metadata
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass(frozen=True, slots=True)
class ResearchMatch:
    """Normalized research match record with all available fields.

    This is the universal match representation consumed by the research
    laboratory. It supports ALL potential football data fields.
    Fields not available from a particular source are None.

    Temporal contract:
    - date_unix: match kickoff timestamp
    - Fields available BEFORE kickoff: team context, odds, league position
    - Fields available AFTER kickoff: goals, shots, corners, cards, etc.
    - The research engine must NEVER use post-kickoff fields as pre-match features
    """

    # Identity
    match_id: int
    date_unix: int
    league_id: int
    season: str
    home_team: str
    away_team: str

    # Results (POST-MATCH ONLY)
    home_goals: Optional[int] = None
    away_goals: Optional[int] = None
    total_goals: Optional[int] = None
    ht_home_goals: Optional[int] = None
    ht_away_goals: Optional[int] = None

    # Shots (POST-MATCH ONLY)
    shots_home: Optional[int] = None
    shots_away: Optional[int] = None
    shots_on_target_home: Optional[int] = None
    shots_on_target_away: Optional[int] = None
    shots_off_target_home: Optional[int] = None
    shots_off_target_away: Optional[int] = None

    # Corners (POST-MATCH ONLY)
    corners_home: Optional[int] = None
    corners_away: Optional[int] = None
    total_corners: Optional[int] = None

    # Cards (POST-MATCH ONLY)
    yellow_cards_home: Optional[int] = None
    yellow_cards_away: Optional[int] = None
    red_cards_home: Optional[int] = None
    red_cards_away: Optional[int] = None
    total_cards: Optional[int] = None

    # Offsides (POST-MATCH ONLY)
    offsides_home: Optional[int] = None
    offsides_away: Optional[int] = None
    total_offsides: Optional[int] = None

    # Fouls (POST-MATCH ONLY)
    fouls_home: Optional[int] = None
    fouls_away: Optional[int] = None

    # Attacks (POST-MATCH ONLY)
    attacks_home: Optional[int] = None
    attacks_away: Optional[int] = None
    dangerous_attacks_home: Optional[int] = None
    dangerous_attacks_away: Optional[int] = None

    # Possession (POST-MATCH ONLY)
    possession_home: Optional[float] = None
    possession_away: Optional[float] = None

    # xG (POST-MATCH ONLY)
    home_xg: Optional[float] = None
    away_xg: Optional[float] = None

    # PPDA (POST-MATCH ONLY)
    ppda_home: Optional[float] = None
    ppda_away: Optional[float] = None

    # Referee
    referee: Optional[str] = None

    # Odds (PRE-MATCH — available before kickoff)
    odds_over_goals: Optional[float] = None
    odds_under_goals: Optional[float] = None
    line_goals: Optional[float] = None
    odds_over_corners: Optional[float] = None
    odds_under_corners: Optional[float] = None
    line_corners: Optional[float] = None
    odds_over_cards: Optional[float] = None
    odds_under_cards: Optional[float] = None
    line_cards: Optional[float] = None
    odds_over_offsides: Optional[float] = None
    odds_under_offsides: Optional[float] = None
    line_offsides: Optional[float] = None
    odds_home_win: Optional[float] = None
    odds_draw: Optional[float] = None
    odds_away_win: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict (None values included for schema completeness)."""
        from dataclasses import asdict
        return asdict(self)

    @property
    def available_fields(self) -> list[str]:
        """Return list of field names that have non-None values."""
        return [k for k, v in self.to_dict().items() if v is not None]


@dataclass(frozen=True, slots=True)
class MarketOdds:
    """Market odds snapshot for a specific match and market."""

    match_id: int
    market: str  # e.g. "GOALS_TOTAL", "CORNERS_TOTAL"
    line: float
    over_odds: Optional[float] = None
    under_odds: Optional[float] = None
    timestamp: Optional[int] = None  # When odds were captured


class ResearchDataSource(ABC):
    """Abstract interface for research data provision.

    Implementations must provide normalized match data regardless of
    the underlying data provider (FootyStats, CSV, synthetic, etc.).
    """

    @abstractmethod
    def get_matches(
        self,
        league_id: Optional[int] = None,
        season: Optional[str] = None,
        min_date: Optional[int] = None,
        max_date: Optional[int] = None,
    ) -> list[ResearchMatch]:
        """Get matches matching filter criteria.

        Args:
            league_id: Filter by league (None = all).
            season: Filter by season (None = all).
            min_date: Minimum date_unix (inclusive).
            max_date: Maximum date_unix (exclusive).

        Returns:
            List of ResearchMatch sorted by date_unix ascending.
        """
        ...

    @abstractmethod
    def get_available_fields(self) -> list[str]:
        """Return list of field names this source can provide.

        Used by FeatureRegistry to determine what features can be computed.
        """
        ...

    @abstractmethod
    def get_market_odds(
        self,
        match_ids: Optional[list[int]] = None,
        market: Optional[str] = None,
    ) -> list[MarketOdds]:
        """Get market odds data.

        Args:
            match_ids: Filter by match IDs (None = all).
            market: Filter by market type (None = all).

        Returns:
            List of MarketOdds records.
        """
        ...

    def compute_content_hash(self) -> str:
        """Compute a content hash representing this dataset snapshot."""
        matches = self.get_matches()
        canonical = json.dumps(
            [m.to_dict() for m in matches],
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
