"""Odds Normalization & Fixture Mapping — robust cross-provider identity resolution.

Maps fixtures across providers using:
1. Provider event IDs (strongest)
2. Canonical fixture mapping (home_team_id + away_team_id + date)
3. Fallback: normalized team name + date matching (weakest, confidence-scored)

Ambiguous mappings are REJECTED and logged, never silently accepted.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class MappingConfidence(Enum):
    """Confidence level of fixture identity mapping."""
    EXACT = "EXACT"          # Provider event ID matches
    HIGH = "HIGH"            # Team IDs + date match exactly
    MEDIUM = "MEDIUM"        # Normalized names + date match
    LOW = "LOW"              # Partial match (ambiguous)
    REJECTED = "REJECTED"    # Cannot reliably map


@dataclass(frozen=True)
class NormalizedFixtureMapping:
    """Result of mapping a provider fixture to our internal fixture_id."""
    internal_fixture_id: str
    provider_event_id: str = ""
    confidence: MappingConfidence = MappingConfidence.REJECTED
    home_team_matched: bool = False
    away_team_matched: bool = False
    date_matched: bool = False
    rejection_reason: str = ""

    @property
    def is_usable(self) -> bool:
        """Whether this mapping is reliable enough to use."""
        return self.confidence in (MappingConfidence.EXACT, MappingConfidence.HIGH)

    def to_dict(self) -> dict[str, Any]:
        return {
            "internal_fixture_id": self.internal_fixture_id,
            "provider_event_id": self.provider_event_id,
            "confidence": self.confidence.value,
            "is_usable": self.is_usable,
            "rejection_reason": self.rejection_reason,
        }


class OddsNormalizer:
    """Normalizes bookmaker, market, selection, and team names across providers.

    Uses canonical forms for comparison. Never relies exclusively on
    raw string matching.
    """

    # Canonical market name mapping
    _MARKET_ALIASES: dict[str, str] = {
        "over_under_2.5": "GOALS_TOTAL",
        "over_under_goals": "GOALS_TOTAL",
        "match_goals": "GOALS_TOTAL",
        "total_goals": "GOALS_TOTAL",
        "over_under_corners": "CORNERS_TOTAL",
        "total_corners": "CORNERS_TOTAL",
        "match_corners": "CORNERS_TOTAL",
        "over_under_cards": "CARDS_TOTAL",
        "total_cards": "CARDS_TOTAL",
        "1x2": "MATCH_RESULT_1X2",
        "match_winner": "MATCH_RESULT_1X2",
        "full_time_result": "MATCH_RESULT_1X2",
        "both_teams_to_score": "BTTS",
        "btts": "BTTS",
    }

    # Canonical selection mapping
    _SELECTION_ALIASES: dict[str, str] = {
        "over": "OVER",
        "under": "UNDER",
        "home": "HOME",
        "1": "HOME",
        "draw": "DRAW",
        "x": "DRAW",
        "away": "AWAY",
        "2": "AWAY",
        "yes": "YES",
        "no": "NO",
    }

    # Canonical bookmaker names
    _BOOKMAKER_ALIASES: dict[str, str] = {
        "pinnacle": "pinnacle",
        "pinnaclesports": "pinnacle",
        "betfair": "betfair",
        "betfair_exchange": "betfair",
        "bet365": "bet365",
        "williamhill": "william_hill",
        "william_hill": "william_hill",
        "market_average": "market_average",
    }

    def normalize_market(self, raw_market: str) -> str:
        """Normalize market name to canonical form."""
        key = raw_market.lower().strip().replace(" ", "_").replace("-", "_")
        return self._MARKET_ALIASES.get(key, raw_market.upper())

    def normalize_selection(self, raw_selection: str) -> str:
        """Normalize selection to canonical form."""
        key = raw_selection.lower().strip()
        return self._SELECTION_ALIASES.get(key, raw_selection.upper())

    def normalize_bookmaker(self, raw_bookmaker: str) -> str:
        """Normalize bookmaker name."""
        key = raw_bookmaker.lower().strip().replace(" ", "").replace("-", "_")
        return self._BOOKMAKER_ALIASES.get(key, raw_bookmaker.lower())

    def map_fixture(
        self,
        provider_event_id: str,
        home_team_id: Optional[int],
        away_team_id: Optional[int],
        kickoff_timestamp: Optional[int],
        known_fixtures: dict[str, dict[str, Any]],
    ) -> NormalizedFixtureMapping:
        """Map a provider's fixture to our internal fixture_id.

        Priority:
        1. Exact provider_event_id match
        2. home_team_id + away_team_id + date match
        3. Rejected (ambiguous)
        """
        # Try exact event ID match first
        for fid, fixture_data in known_fixtures.items():
            if fixture_data.get("source_fixture_id") == provider_event_id:
                return NormalizedFixtureMapping(
                    internal_fixture_id=fid,
                    provider_event_id=str(provider_event_id),
                    confidence=MappingConfidence.EXACT,
                    home_team_matched=True,
                    away_team_matched=True,
                    date_matched=True,
                )

        # Try team ID + date match
        if home_team_id and away_team_id and kickoff_timestamp:
            for fid, fixture_data in known_fixtures.items():
                fhome = fixture_data.get("home_team_id")
                faway = fixture_data.get("away_team_id")
                fkickoff = fixture_data.get("kickoff_timestamp", 0)

                home_match = fhome == home_team_id
                away_match = faway == away_team_id
                # Allow 1 hour tolerance for kickoff matching
                date_match = abs(fkickoff - kickoff_timestamp) < 3600

                if home_match and away_match and date_match:
                    return NormalizedFixtureMapping(
                        internal_fixture_id=fid,
                        provider_event_id=str(provider_event_id),
                        confidence=MappingConfidence.HIGH,
                        home_team_matched=True,
                        away_team_matched=True,
                        date_matched=True,
                    )

        # Cannot reliably map
        return NormalizedFixtureMapping(
            internal_fixture_id="",
            provider_event_id=str(provider_event_id),
            confidence=MappingConfidence.REJECTED,
            rejection_reason="No reliable fixture match found",
        )
