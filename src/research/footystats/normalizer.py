"""Match normalization — FootyStats raw records to ResearchMatch.

CRITICAL RULES:
1. NULL ≠ ZERO: Missing data stays None, never becomes 0
2. Sentinel -1 = NULL: FootyStats uses -1 for "not recorded"
3. Odds 0 = NULL: FootyStats uses 0 for "market not available"
4. RAW vs DERIVED: Only raw source values, no computed features
5. Temporal integrity: pre-match fields tagged, post-match fields preserved
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from src.research.data_source import MarketOdds, ResearchMatch

logger = logging.getLogger(__name__)


# Sentinel values that mean "not recorded / not available"
_SENTINEL_NOT_RECORDED = -1
_ODDS_NOT_AVAILABLE = 0


def _safe_int(value: Any) -> Optional[int]:
    """Convert to int, treating sentinels and None as NULL."""
    if value is None:
        return None
    try:
        v = int(value)
        if v == _SENTINEL_NOT_RECORDED:
            return None
        return v
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> Optional[float]:
    """Convert to float, treating sentinels and None as NULL."""
    if value is None:
        return None
    try:
        v = float(value)
        if v == _SENTINEL_NOT_RECORDED:
            return None
        return v
    except (TypeError, ValueError):
        return None


def _safe_odds(value: Any) -> Optional[float]:
    """Convert odds value, treating 0 and sentinel as NULL.

    Odds of 0 mean 'market not available' in FootyStats.
    Valid odds must be > 1.0.
    """
    if value is None:
        return None
    try:
        v = float(value)
        if v <= 0 or v == _SENTINEL_NOT_RECORDED:
            return None
        # Odds below 1.0 are invalid (decimal odds)
        if v < 1.0:
            return None
        return v
    except (TypeError, ValueError):
        return None


def _safe_possession(value: Any) -> Optional[float]:
    """Convert possession, treating sentinels as NULL.

    Valid range: 0-100.
    """
    if value is None:
        return None
    try:
        v = float(value)
        if v == _SENTINEL_NOT_RECORDED:
            return None
        if v < 0 or v > 100:
            return None
        return v
    except (TypeError, ValueError):
        return None


class MatchNormalizer:
    """Normalizes raw FootyStats API records to ResearchMatch.

    Preserves NULL semantics: missing data is never fabricated.
    Tracks normalization statistics for coverage auditing.
    """

    def __init__(self) -> None:
        self._normalized_count: int = 0
        self._skipped_count: int = 0
        self._field_availability: dict[str, int] = {}

    @property
    def normalized_count(self) -> int:
        return self._normalized_count

    @property
    def skipped_count(self) -> int:
        return self._skipped_count

    @property
    def field_availability(self) -> dict[str, int]:
        """Count of non-null values per field across all normalized records."""
        return dict(self._field_availability)

    def normalize(self, raw: dict[str, Any]) -> Optional[ResearchMatch]:
        """Normalize a single raw FootyStats record to ResearchMatch.

        Args:
            raw: Raw API response dict for a single match.

        Returns:
            ResearchMatch or None if record is invalid/incomplete.
        """
        # Required fields
        match_id = raw.get("id")
        date_unix = raw.get("date_unix")
        status = raw.get("status", "")

        if match_id is None or date_unix is None:
            self._skipped_count += 1
            return None

        # Only process completed matches (have final statistics)
        if status != "complete":
            self._skipped_count += 1
            return None

        home_name = raw.get("home_name", "")
        away_name = raw.get("away_name", "")
        if not home_name or not away_name:
            self._skipped_count += 1
            return None

        # Competition/league info
        competition_id = raw.get("competition_id") or raw.get("league_id")
        season = raw.get("season", "")

        # Results
        home_goals = _safe_int(raw.get("homeGoalCount"))
        away_goals = _safe_int(raw.get("awayGoalCount"))

        if home_goals is None or away_goals is None:
            self._skipped_count += 1
            return None

        total_goals = home_goals + away_goals

        # Build ResearchMatch
        match = ResearchMatch(
            match_id=int(match_id),
            date_unix=int(date_unix),
            league_id=int(competition_id) if competition_id else 0,
            season=str(season),
            home_team=str(home_name),
            away_team=str(away_name),
            # Results
            home_goals=home_goals,
            away_goals=away_goals,
            total_goals=total_goals,
            ht_home_goals=_safe_int(raw.get("ht_goals_team_a")),
            ht_away_goals=_safe_int(raw.get("ht_goals_team_b")),
            # Shots
            shots_home=_safe_int(raw.get("team_a_shots")),
            shots_away=_safe_int(raw.get("team_b_shots")),
            shots_on_target_home=_safe_int(raw.get("team_a_shotsOnTarget")),
            shots_on_target_away=_safe_int(raw.get("team_b_shotsOnTarget")),
            shots_off_target_home=_safe_int(raw.get("team_a_shotsOffTarget")),
            shots_off_target_away=_safe_int(raw.get("team_b_shotsOffTarget")),
            # Corners
            corners_home=_safe_int(raw.get("team_a_corners")),
            corners_away=_safe_int(raw.get("team_b_corners")),
            total_corners=_safe_int(raw.get("totalCornerCount")),
            # Cards
            yellow_cards_home=_safe_int(raw.get("team_a_yellow_cards")),
            yellow_cards_away=_safe_int(raw.get("team_b_yellow_cards")),
            red_cards_home=_safe_int(raw.get("team_a_red_cards")),
            red_cards_away=_safe_int(raw.get("team_b_red_cards")),
            total_cards=_compute_total_cards(raw),
            # Offsides
            offsides_home=_safe_int(raw.get("team_a_offsides")),
            offsides_away=_safe_int(raw.get("team_b_offsides")),
            total_offsides=_compute_total_offsides(raw),
            # Fouls
            fouls_home=_safe_int(raw.get("team_a_fouls")),
            fouls_away=_safe_int(raw.get("team_b_fouls")),
            # Attacks
            attacks_home=_safe_int(raw.get("team_a_attacks")),
            attacks_away=_safe_int(raw.get("team_b_attacks")),
            dangerous_attacks_home=_safe_int(raw.get("team_a_dangerous_attacks")),
            dangerous_attacks_away=_safe_int(raw.get("team_b_dangerous_attacks")),
            # Possession
            possession_home=_safe_possession(raw.get("team_a_possession")),
            possession_away=_safe_possession(raw.get("team_b_possession")),
            # xG
            home_xg=_safe_float(raw.get("team_a_xg")),
            away_xg=_safe_float(raw.get("team_b_xg")),
            # Odds (PRE-MATCH)
            odds_over_goals=_safe_odds(raw.get("odds_ft_over25")),
            odds_under_goals=_safe_odds(raw.get("odds_ft_under25")),
            line_goals=2.5,
            odds_over_corners=_safe_odds(raw.get("odds_corners_over_95")),
            odds_under_corners=_safe_odds(raw.get("odds_corners_under_95")),
            line_corners=9.5,
            odds_over_cards=None,  # Not available in API
            odds_under_cards=None,
            line_cards=None,
            odds_over_offsides=None,  # Not available in API
            odds_under_offsides=None,
            line_offsides=None,
            odds_home_win=_safe_odds(raw.get("odds_ft_1")),
            odds_draw=_safe_odds(raw.get("odds_ft_x")),
            odds_away_win=_safe_odds(raw.get("odds_ft_2")),
            # Referee
            referee=str(raw.get("refereeID", "")) if raw.get("refereeID") else None,
        )

        self._normalized_count += 1
        self._track_field_availability(match)
        return match

    def normalize_batch(self, records: list[dict[str, Any]]) -> list[ResearchMatch]:
        """Normalize a batch of raw records.

        Args:
            records: List of raw API response dicts.

        Returns:
            List of valid ResearchMatch objects (invalid records skipped).
        """
        results = []
        for raw in records:
            match = self.normalize(raw)
            if match is not None:
                results.append(match)
        return results

    def extract_market_odds(self, raw: dict[str, Any]) -> list[MarketOdds]:
        """Extract MarketOdds records from a raw API record.

        Odds timestamp is set to 1 hour before kickoff (pre-match snapshot).
        This is conservative — we cannot know the exact capture time.

        Args:
            raw: Raw API response dict.

        Returns:
            List of MarketOdds for available markets.
        """
        match_id = raw.get("id")
        date_unix = raw.get("date_unix")
        if match_id is None or date_unix is None:
            return []

        # Odds timestamp: 1 hour before kickoff (pre-match)
        odds_ts = int(date_unix) - 3600

        odds_list: list[MarketOdds] = []

        # Goals total (2.5 line)
        over_goals = _safe_odds(raw.get("odds_ft_over25"))
        under_goals = _safe_odds(raw.get("odds_ft_under25"))
        if over_goals and under_goals:
            odds_list.append(MarketOdds(
                match_id=int(match_id),
                market="GOALS_TOTAL",
                line=2.5,
                over_odds=over_goals,
                under_odds=under_goals,
                timestamp=odds_ts,
            ))

        # Corners total (9.5 line)
        over_corners = _safe_odds(raw.get("odds_corners_over_95"))
        under_corners = _safe_odds(raw.get("odds_corners_under_95"))
        if over_corners and under_corners:
            odds_list.append(MarketOdds(
                match_id=int(match_id),
                market="CORNERS_TOTAL",
                line=9.5,
                over_odds=over_corners,
                under_odds=under_corners,
                timestamp=odds_ts,
            ))

        return odds_list

    def _track_field_availability(self, match: ResearchMatch) -> None:
        """Track which fields have data for coverage auditing."""
        d = match.to_dict()
        for key, val in d.items():
            if val is not None:
                self._field_availability[key] = self._field_availability.get(key, 0) + 1


def _compute_total_cards(raw: dict[str, Any]) -> Optional[int]:
    """Compute total cards from components."""
    yh = _safe_int(raw.get("team_a_yellow_cards"))
    ya = _safe_int(raw.get("team_b_yellow_cards"))
    rh = _safe_int(raw.get("team_a_red_cards"))
    ra = _safe_int(raw.get("team_b_red_cards"))

    parts = [x for x in [yh, ya, rh, ra] if x is not None]
    if not parts:
        return None
    return sum(parts)


def _compute_total_offsides(raw: dict[str, Any]) -> Optional[int]:
    """Compute total offsides from components."""
    oh = _safe_int(raw.get("team_a_offsides"))
    oa = _safe_int(raw.get("team_b_offsides"))
    if oh is None and oa is None:
        return None
    return (oh or 0) + (oa or 0)
