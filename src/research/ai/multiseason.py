"""Multi-Season Research Support — extends FootyStats for multi-season loading.

Provides:
- Multi-season dataset construction with provenance
- Season-level coverage reporting
- Chronological ordering guarantees
- Deduplication across seasons
- Content hashing for deterministic identity

Does NOT:
- Replace the existing FootyStatsDataSource
- Modify the ResearchDataSource interface
- Assume season IDs are sequential
- Auto-discover unlimited seasons
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.research.data_source import MarketOdds, ResearchMatch

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SeasonCoverage:
    """Coverage information for a single season."""

    season_id: int
    season_label: str
    league_id: int
    match_count: int
    earliest_date_unix: int
    latest_date_unix: int
    teams: int
    feature_coverage_pct: float
    odds_coverage_pct: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "season_id": self.season_id,
            "season": self.season_label,
            "league_id": self.league_id,
            "matches": self.match_count,
            "date_range": f"{self.earliest_date_unix}-{self.latest_date_unix}",
            "teams": self.teams,
            "feature_coverage_pct": self.feature_coverage_pct,
            "odds_coverage_pct": self.odds_coverage_pct,
        }


@dataclass
class MultiSeasonDataset:
    """Dataset spanning multiple seasons with provenance tracking.

    Preserves:
    - Season identity per match
    - League identity per match
    - Chronological ordering across all seasons
    - Deduplication (same match_id never appears twice)
    - Per-season coverage statistics

    Never:
    - Shuffles or randomly orders data
    - Collapses seasons in ways preventing regime analysis
    - Allows future seasons to contaminate past analysis
    """

    matches: list[ResearchMatch] = field(default_factory=list)
    market_odds: list[MarketOdds] = field(default_factory=list)
    season_coverage: list[SeasonCoverage] = field(default_factory=list)
    content_hash_value: str = ""
    season_ids: list[int] = field(default_factory=list)

    @property
    def total_matches(self) -> int:
        return len(self.matches)

    @property
    def seasons(self) -> list[str]:
        """Unique season labels in chronological order."""
        seen: dict[str, int] = {}
        for m in self.matches:
            if m.season not in seen:
                seen[m.season] = m.date_unix
        return sorted(seen.keys(), key=lambda s: seen[s])

    @property
    def leagues(self) -> list[int]:
        """Unique league IDs."""
        return sorted(set(m.league_id for m in self.matches))

    @property
    def teams(self) -> set[str]:
        """All teams across all seasons."""
        return set(t for m in self.matches for t in (m.home_team, m.away_team))

    @property
    def date_range(self) -> tuple[int, int]:
        """(earliest, latest) date_unix."""
        if not self.matches:
            return (0, 0)
        dates = [m.date_unix for m in self.matches]
        return (min(dates), max(dates))

    def get_matches_for_season(self, season_id: int) -> list[ResearchMatch]:
        """Get matches belonging to a specific season_id.

        Maintains chronological order within the season.
        """
        # season_id maps to league_id in FootyStats
        return [m for m in self.matches if m.league_id == season_id]

    def compute_content_hash(self) -> str:
        """Deterministic content hash across all seasons.

        Based on match IDs and timestamps — not retrieval time.
        Same data always produces same hash.
        """
        if self.content_hash_value:
            return self.content_hash_value
        canonical = json.dumps(
            [(m.match_id, m.date_unix) for m in self.matches],
            sort_keys=True,
            separators=(",", ":"),
        )
        self.content_hash_value = hashlib.sha256(canonical.encode()).hexdigest()
        return self.content_hash_value

    def get_coverage_summary(self) -> dict[str, Any]:
        """Get aggregate coverage summary across all seasons."""
        if not self.matches:
            return {"total_matches": 0, "seasons": 0, "leagues": 0}

        earliest, latest = self.date_range
        return {
            "total_matches": self.total_matches,
            "seasons": len(self.seasons),
            "season_list": self.seasons,
            "leagues": self.leagues,
            "teams": len(self.teams),
            "earliest_date_unix": earliest,
            "latest_date_unix": latest,
            "season_ids": self.season_ids,
            "per_season": [sc.to_dict() for sc in self.season_coverage],
        }

    def validate_chronological_order(self) -> bool:
        """Verify matches are in strict chronological order."""
        for i in range(1, len(self.matches)):
            if self.matches[i].date_unix < self.matches[i - 1].date_unix:
                return False
        return True


def build_multi_season_dataset(
    season_ids: list[int],
    api_key: Optional[str] = None,
    cache_dir: Optional[Path] = None,
    client: Optional[Any] = None,
) -> MultiSeasonDataset:
    """Build a multi-season dataset from FootyStats.

    Args:
        season_ids: Explicit list of season/competition IDs to load.
        api_key: API key (uses env if None).
        cache_dir: Cache directory for API responses.
        client: Pre-configured FootyStatsResearchClient (for testing).

    Returns:
        MultiSeasonDataset with all seasons loaded, deduplicated, sorted.

    Does not auto-discover seasons — uses only the explicit list.
    """
    from src.research.footystats.adapter import FootyStatsDataSource

    # Create source with all seasons
    source = FootyStatsDataSource(
        season_ids=season_ids,
        api_key=api_key,
        cache_dir=cache_dir,
        client=client,
    )

    # Load all matches (triggers lazy-load)
    all_matches = source.get_matches()
    all_odds = source.get_market_odds()
    coverage_summary = source.get_coverage_summary()

    # Build per-season coverage
    season_coverage_list: list[SeasonCoverage] = []
    for sid in season_ids:
        season_matches = [m for m in all_matches if m.league_id == sid]
        if not season_matches:
            logger.warning("Season %d: no matches loaded", sid)
            continue

        dates = [m.date_unix for m in season_matches]
        teams_in_season = set(
            t for m in season_matches for t in (m.home_team, m.away_team)
        )

        # Compute feature coverage for season
        fields_with_data = 0
        total_fields = 0
        for m in season_matches[:10]:  # Sample
            avail = m.available_fields
            total_fields = max(total_fields, len(avail))
            fields_with_data = max(fields_with_data, len(avail))

        # Odds coverage
        season_match_ids = {m.match_id for m in season_matches}
        odds_for_season = [o for o in all_odds if o.match_id in season_match_ids]
        odds_coverage = len(odds_for_season) / max(1, len(season_matches))

        season_labels = set(m.season for m in season_matches)
        season_label = sorted(season_labels)[0] if season_labels else str(sid)

        season_coverage_list.append(SeasonCoverage(
            season_id=sid,
            season_label=season_label,
            league_id=sid,
            match_count=len(season_matches),
            earliest_date_unix=min(dates),
            latest_date_unix=max(dates),
            teams=len(teams_in_season),
            feature_coverage_pct=round(fields_with_data / max(1, total_fields) * 100, 1),
            odds_coverage_pct=round(odds_coverage * 100, 1),
        ))

    # Sort coverage chronologically
    season_coverage_list.sort(key=lambda sc: sc.earliest_date_unix)

    # Deduplicate matches by match_id (in case same match appears in overlapping seasons)
    seen_ids: set[int] = set()
    deduplicated: list[ResearchMatch] = []
    for m in all_matches:
        if m.match_id not in seen_ids:
            seen_ids.add(m.match_id)
            deduplicated.append(m)

    # Ensure chronological order
    deduplicated.sort(key=lambda m: m.date_unix)

    dataset = MultiSeasonDataset(
        matches=deduplicated,
        market_odds=all_odds,
        season_coverage=season_coverage_list,
        season_ids=season_ids,
    )

    logger.info(
        "Multi-season dataset: %d matches, %d seasons, %d leagues, date range %d-%d",
        dataset.total_matches,
        len(dataset.seasons),
        len(dataset.leagues),
        *dataset.date_range,
    )

    return dataset
