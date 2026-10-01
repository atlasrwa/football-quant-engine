"""Research data source abstraction.

Defines the odds-blind interface for normalized football evidence consumed
by the QFE V2 probability engine. Bookmaker prices are deliberately excluded
from this object and live in the separate timestamped market layer.
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

    Historical post-match fields may be used only to construct features for
    later fixtures. A match's own realized statistics can never predict itself.
    Bookmaker odds are intentionally absent from this representation.
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

    # --- Rich per-side fields (POST-MATCH ONLY; TheStatsAPI Rich_Corpus) --------
    # Optional, default None: backward-compatible additive extension used by the
    # asymmetric-matchup-engine Team_Profiler to derive the previously
    # unpopulated / partially-populated profile dimensions from cached rich
    # stats. NULL != ZERO is preserved: a field absent from the source (or absent
    # on either side of the match) stays None; a genuine 0 is kept as 0.

    # Shots detail (shots group)
    shots_inside_box_home: Optional[int] = None
    shots_inside_box_away: Optional[int] = None
    shots_outside_box_home: Optional[int] = None
    shots_outside_box_away: Optional[int] = None
    blocked_shots_home: Optional[int] = None
    blocked_shots_away: Optional[int] = None
    # Chance quality (overview / npxg)
    big_chances_home: Optional[int] = None
    big_chances_away: Optional[int] = None
    npxg_home: Optional[float] = None
    npxg_away: Optional[float] = None
    # Attack / entries (attack + passes groups)
    touches_in_box_home: Optional[int] = None
    touches_in_box_away: Optional[int] = None
    final_third_entries_home: Optional[int] = None
    final_third_entries_away: Optional[int] = None
    fouled_in_final_third_home: Optional[int] = None
    fouled_in_final_third_away: Optional[int] = None
    accurate_crosses_home: Optional[int] = None
    accurate_crosses_away: Optional[int] = None
    accurate_long_balls_home: Optional[int] = None
    accurate_long_balls_away: Optional[int] = None
    # Duels (duels group, percentages)
    aerial_duel_pct_home: Optional[float] = None
    aerial_duel_pct_away: Optional[float] = None
    ground_duel_pct_home: Optional[float] = None
    ground_duel_pct_away: Optional[float] = None
    # Defending (defending group)
    tackles_home: Optional[int] = None
    tackles_away: Optional[int] = None
    tackles_won_pct_home: Optional[float] = None
    tackles_won_pct_away: Optional[float] = None
    interceptions_home: Optional[int] = None
    interceptions_away: Optional[int] = None
    clearances_home: Optional[int] = None
    clearances_away: Optional[int] = None
    # Goalkeeping (goalkeeping group; goals_prevented is 0%-populated per audit)
    saves_home: Optional[int] = None
    saves_away: Optional[int] = None
    high_claims_home: Optional[int] = None
    high_claims_away: Optional[int] = None
    goals_prevented_home: Optional[float] = None
    goals_prevented_away: Optional[float] = None

    # Referee
    referee: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict (None values included for schema completeness)."""
        from dataclasses import asdict
        return asdict(self)

    @property
    def available_fields(self) -> list[str]:
        """Return list of field names that have non-None values."""
        return [k for k, v in self.to_dict().items() if v is not None]


class ResearchDataSource(ABC):
    """Abstract interface for research data provision.

    Implementations provide normalized football evidence only. Market prices
    use the separate prospective odds-capture/reconciliation layer.
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

    def compute_content_hash(self) -> str:
        """Compute a content hash representing this dataset snapshot."""
        matches = self.get_matches()
        canonical = json.dumps(
            [m.to_dict() for m in matches],
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
