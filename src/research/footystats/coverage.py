"""Data coverage analysis for FootyStats research datasets.

Produces structured coverage reports showing:
- Per-field availability
- Per-league/season match counts
- Market readiness assessment
- Temporal span analysis
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from src.research.data_source import ResearchMatch


class MarketReadiness(Enum):
    """Research readiness status for a market."""

    READY = "READY"                     # Sufficient data + odds for research
    PARTIAL = "PARTIAL"                 # Data available, odds limited/missing
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"  # Too few observations
    NOT_SUPPORTED = "NOT_SUPPORTED"     # Market not measurable with available data


@dataclass(frozen=True)
class FieldCoverage:
    """Coverage statistics for a single field."""

    field_name: str
    total_matches: int
    available_count: int
    missing_count: int
    coverage_pct: float
    earliest_date: Optional[int] = None
    latest_date: Optional[int] = None

    @property
    def usable_for_research(self) -> bool:
        """Field has >50% coverage."""
        return self.coverage_pct >= 50.0


@dataclass(frozen=True)
class LeagueCoverage:
    """Coverage for a single league/season combination."""

    league_id: int
    season: str
    match_count: int
    team_count: int
    earliest_date: int
    latest_date: int
    has_corners: bool
    has_cards: bool
    has_shots: bool
    has_possession: bool
    has_xg: bool
    has_goals_odds: bool
    has_corners_odds: bool


@dataclass
class CoverageReport:
    """Complete coverage report for a dataset."""

    total_matches: int = 0
    total_leagues: int = 0
    total_seasons: int = 0
    total_teams: int = 0
    earliest_date: Optional[int] = None
    latest_date: Optional[int] = None
    field_coverage: list[FieldCoverage] = field(default_factory=list)
    league_coverage: list[LeagueCoverage] = field(default_factory=list)
    market_readiness: dict[str, MarketReadiness] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_matches": self.total_matches,
            "total_leagues": self.total_leagues,
            "total_seasons": self.total_seasons,
            "total_teams": self.total_teams,
            "earliest_date": self.earliest_date,
            "latest_date": self.latest_date,
            "field_coverage": [
                {
                    "field": fc.field_name,
                    "available": fc.available_count,
                    "missing": fc.missing_count,
                    "coverage_pct": fc.coverage_pct,
                    "usable": fc.usable_for_research,
                }
                for fc in self.field_coverage
            ],
            "league_coverage": [
                {
                    "league_id": lc.league_id,
                    "season": lc.season,
                    "match_count": lc.match_count,
                    "team_count": lc.team_count,
                }
                for lc in self.league_coverage
            ],
            "market_readiness": {k: v.value for k, v in self.market_readiness.items()},
        }


def compute_coverage(matches: list[ResearchMatch]) -> CoverageReport:
    """Compute full coverage report from a list of matches.

    Args:
        matches: List of normalized ResearchMatch objects.

    Returns:
        CoverageReport with field-level and league-level coverage.
    """
    if not matches:
        return CoverageReport()

    total = len(matches)
    dates = [m.date_unix for m in matches]
    leagues = set(m.league_id for m in matches)
    seasons = set(m.season for m in matches)
    teams = set(t for m in matches for t in (m.home_team, m.away_team))

    # Field coverage
    field_stats = _compute_field_coverage(matches)

    # League/season coverage
    league_cov = _compute_league_coverage(matches)

    # Market readiness
    market_ready = _assess_market_readiness(matches, field_stats)

    return CoverageReport(
        total_matches=total,
        total_leagues=len(leagues),
        total_seasons=len(seasons),
        total_teams=len(teams),
        earliest_date=min(dates),
        latest_date=max(dates),
        field_coverage=field_stats,
        league_coverage=league_cov,
        market_readiness=market_ready,
    )


def _compute_field_coverage(matches: list[ResearchMatch]) -> list[FieldCoverage]:
    """Compute per-field coverage statistics."""
    total = len(matches)
    # Fields to check (post-match statistics relevant to research)
    fields_to_check = [
        "corners_home", "corners_away", "total_corners",
        "shots_home", "shots_away",
        "shots_on_target_home", "shots_on_target_away",
        "yellow_cards_home", "yellow_cards_away",
        "red_cards_home", "red_cards_away",
        "offsides_home", "offsides_away",
        "fouls_home", "fouls_away",
        "possession_home", "possession_away",
        "attacks_home", "attacks_away",
        "dangerous_attacks_home", "dangerous_attacks_away",
        "home_xg", "away_xg",
        "odds_over_goals", "odds_under_goals",
        "odds_over_corners", "odds_under_corners",
        "odds_home_win", "odds_draw", "odds_away_win",
    ]

    coverage_list: list[FieldCoverage] = []
    for field_name in fields_to_check:
        available = sum(1 for m in matches if getattr(m, field_name, None) is not None)
        missing = total - available
        pct = round(available / total * 100, 1) if total > 0 else 0.0

        # Find date range for available data
        dates_with_data = [m.date_unix for m in matches if getattr(m, field_name, None) is not None]
        earliest = min(dates_with_data) if dates_with_data else None
        latest = max(dates_with_data) if dates_with_data else None

        coverage_list.append(FieldCoverage(
            field_name=field_name,
            total_matches=total,
            available_count=available,
            missing_count=missing,
            coverage_pct=pct,
            earliest_date=earliest,
            latest_date=latest,
        ))

    return coverage_list


def _compute_league_coverage(matches: list[ResearchMatch]) -> list[LeagueCoverage]:
    """Compute per-league/season coverage."""
    # Group by (league_id, season)
    groups: dict[tuple[int, str], list[ResearchMatch]] = {}
    for m in matches:
        key = (m.league_id, m.season)
        if key not in groups:
            groups[key] = []
        groups[key].append(m)

    coverage_list: list[LeagueCoverage] = []
    for (league_id, season), group_matches in sorted(groups.items()):
        teams = set(t for m in group_matches for t in (m.home_team, m.away_team))
        dates = [m.date_unix for m in group_matches]

        has_corners = any(m.corners_home is not None for m in group_matches)
        has_cards = any(m.yellow_cards_home is not None for m in group_matches)
        has_shots = any(m.shots_home is not None for m in group_matches)
        has_possession = any(m.possession_home is not None for m in group_matches)
        has_xg = any(m.home_xg is not None for m in group_matches)
        has_goals_odds = any(m.odds_over_goals is not None for m in group_matches)
        has_corners_odds = any(m.odds_over_corners is not None for m in group_matches)

        coverage_list.append(LeagueCoverage(
            league_id=league_id,
            season=season,
            match_count=len(group_matches),
            team_count=len(teams),
            earliest_date=min(dates),
            latest_date=max(dates),
            has_corners=has_corners,
            has_cards=has_cards,
            has_shots=has_shots,
            has_possession=has_possession,
            has_xg=has_xg,
            has_goals_odds=has_goals_odds,
            has_corners_odds=has_corners_odds,
        ))

    return coverage_list


def _assess_market_readiness(
    matches: list[ResearchMatch],
    field_coverage: list[FieldCoverage],
) -> dict[str, MarketReadiness]:
    """Assess research readiness for each market."""
    total = len(matches)
    coverage_map = {fc.field_name: fc for fc in field_coverage}

    readiness: dict[str, MarketReadiness] = {}

    # GOALS_TOTAL: need goals (always available) + odds
    goals_odds = coverage_map.get("odds_over_goals")
    if total >= 100 and goals_odds and goals_odds.coverage_pct > 50:
        readiness["GOALS_TOTAL"] = MarketReadiness.READY
    elif total >= 50:
        readiness["GOALS_TOTAL"] = MarketReadiness.PARTIAL
    else:
        readiness["GOALS_TOTAL"] = MarketReadiness.INSUFFICIENT_DATA

    # CORNERS_TOTAL: need corners + odds
    corners = coverage_map.get("total_corners")
    corners_odds = coverage_map.get("odds_over_corners")
    if corners and corners.coverage_pct > 80 and total >= 100:
        if corners_odds and corners_odds.coverage_pct > 50:
            readiness["CORNERS_TOTAL"] = MarketReadiness.READY
        else:
            readiness["CORNERS_TOTAL"] = MarketReadiness.PARTIAL
    elif corners and corners.coverage_pct > 50:
        readiness["CORNERS_TOTAL"] = MarketReadiness.PARTIAL
    else:
        readiness["CORNERS_TOTAL"] = MarketReadiness.INSUFFICIENT_DATA

    # CARDS_TOTAL: need cards (no odds available from API)
    cards = coverage_map.get("yellow_cards_home")
    if cards and cards.coverage_pct > 80 and total >= 100:
        readiness["CARDS_TOTAL"] = MarketReadiness.PARTIAL  # No odds
    elif cards and cards.coverage_pct > 50:
        readiness["CARDS_TOTAL"] = MarketReadiness.PARTIAL
    else:
        readiness["CARDS_TOTAL"] = MarketReadiness.INSUFFICIENT_DATA

    # OFFSIDES_TOTAL
    offsides = coverage_map.get("offsides_home")
    if offsides and offsides.coverage_pct > 80 and total >= 100:
        readiness["OFFSIDES_TOTAL"] = MarketReadiness.PARTIAL  # No odds
    elif offsides and offsides.coverage_pct > 50:
        readiness["OFFSIDES_TOTAL"] = MarketReadiness.PARTIAL
    else:
        readiness["OFFSIDES_TOTAL"] = MarketReadiness.INSUFFICIENT_DATA

    # BTTS: need goals (always) — odds not checked in current data
    if total >= 100:
        readiness["BTTS"] = MarketReadiness.PARTIAL
    else:
        readiness["BTTS"] = MarketReadiness.INSUFFICIENT_DATA

    # MATCH_RESULT_1X2: need result + 1X2 odds
    result_odds = coverage_map.get("odds_home_win")
    if total >= 100 and result_odds and result_odds.coverage_pct > 50:
        readiness["MATCH_RESULT_1X2"] = MarketReadiness.READY
    elif total >= 50:
        readiness["MATCH_RESULT_1X2"] = MarketReadiness.PARTIAL
    else:
        readiness["MATCH_RESULT_1X2"] = MarketReadiness.INSUFFICIENT_DATA

    return readiness
