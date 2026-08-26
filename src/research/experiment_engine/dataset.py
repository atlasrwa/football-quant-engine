"""Research dataset abstraction.

The experiment runner does not care where data came from.
The same experiment code works with synthetic, FootyStats,
or any other historical provider.

ResearchDataSource (Batch 1) → ResearchDataset → ExperimentRunner
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional

from src.research.data_source import MarketOdds, ResearchDataSource, ResearchMatch
from src.research.experiment_engine.temporal import SplitType, TemporalSplit
from src.research.market import MarketType, ResearchMarket


@dataclass
class DatasetStatistics:
    """Statistics about a research dataset.

    Tracks data quality and availability.
    """

    total_matches: int = 0
    eligible_matches: int = 0
    missing_target: int = 0
    missing_odds: int = 0
    excluded_invalid: int = 0
    matches_with_odds: int = 0
    date_range_start: Optional[int] = None
    date_range_end: Optional[int] = None
    leagues: int = 0
    seasons: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_matches": self.total_matches,
            "eligible_matches": self.eligible_matches,
            "missing_target": self.missing_target,
            "missing_odds": self.missing_odds,
            "excluded_invalid": self.excluded_invalid,
            "matches_with_odds": self.matches_with_odds,
            "date_range_start": self.date_range_start,
            "date_range_end": self.date_range_end,
            "leagues": self.leagues,
            "seasons": self.seasons,
        }


class ResearchDataset:
    """A prepared dataset for experiment execution.

    Wraps a ResearchDataSource and provides:
    - Match data as dictionaries
    - Market-specific odds lookup
    - Content hashing for reproducibility
    - Dataset statistics
    - Temporal split application

    The experiment runner consumes this, not the raw data source.
    """

    def __init__(
        self,
        source: ResearchDataSource,
        market: ResearchMarket,
        league_id: Optional[int] = None,
        season: Optional[str] = None,
        min_date: Optional[int] = None,
        max_date: Optional[int] = None,
    ) -> None:
        """Initialize dataset from a data source.

        Args:
            source: The underlying data source.
            market: Target market for odds lookup.
            league_id: Optional league filter.
            season: Optional season filter.
            min_date: Optional min timestamp filter.
            max_date: Optional max timestamp filter.
        """
        self._source = source
        self._market = market
        self._league_id = league_id
        self._season = season

        # Load matches
        self._matches = source.get_matches(
            league_id=league_id,
            season=season,
            min_date=min_date,
            max_date=max_date,
        )

        # Load odds for this market
        match_ids = [m.match_id for m in self._matches]
        self._odds_records = source.get_market_odds(
            match_ids=match_ids,
            market=market.market_type.value,
        )
        self._odds_by_match: dict[int, MarketOdds] = {
            o.match_id: o for o in self._odds_records
        }

        # Build match dicts with odds merged
        self._match_dicts: list[dict[str, Any]] = []
        for match in self._matches:
            d = match.to_dict()
            # Merge odds from MarketOdds records if available
            odds = self._odds_by_match.get(match.match_id)
            if odds is not None:
                # Map to the market's expected odds field names
                d[market.odds_over_field] = odds.over_odds
                d[market.odds_under_field] = odds.under_odds
            self._match_dicts.append(d)

        self._statistics: Optional[DatasetStatistics] = None

    @property
    def matches(self) -> list[ResearchMatch]:
        """Raw match objects."""
        return self._matches

    @property
    def match_dicts(self) -> list[dict[str, Any]]:
        """Match data as dictionaries with odds merged."""
        return self._match_dicts

    @property
    def market(self) -> ResearchMarket:
        """Target market."""
        return self._market

    @property
    def size(self) -> int:
        """Number of matches in dataset."""
        return len(self._matches)

    @property
    def content_hash(self) -> str:
        """Deterministic content hash of the dataset.

        Based on match data content, not runtime state.
        """
        canonical = json.dumps(
            [
                {
                    "match_id": m.match_id,
                    "date_unix": m.date_unix,
                }
                for m in self._matches
            ],
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def compute_statistics(self) -> DatasetStatistics:
        """Compute dataset statistics for reporting."""
        if self._statistics is not None:
            return self._statistics

        stats = DatasetStatistics()
        stats.total_matches = len(self._matches)

        leagues = set()
        seasons = set()

        for match, d in zip(self._matches, self._match_dicts):
            leagues.add(match.league_id)
            seasons.add(match.season)

            # Check target availability
            target_val = d.get(self._market.target_field)
            if target_val is None:
                stats.missing_target += 1
            else:
                stats.eligible_matches += 1

            # Check odds availability
            over_odds = d.get(self._market.odds_over_field)
            under_odds = d.get(self._market.odds_under_field)
            if over_odds is not None and under_odds is not None:
                stats.matches_with_odds += 1
            else:
                stats.missing_odds += 1

        if self._matches:
            stats.date_range_start = self._matches[0].date_unix
            stats.date_range_end = self._matches[-1].date_unix
        stats.leagues = len(leagues)
        stats.seasons = len(seasons)

        self._statistics = stats
        return stats

    def apply_split(
        self, split: TemporalSplit
    ) -> dict[SplitType, list[dict[str, Any]]]:
        """Apply a temporal split to the dataset.

        Returns match dicts organized by split segment.
        """
        result: dict[SplitType, list[dict[str, Any]]] = {
            SplitType.TRAIN: [],
            SplitType.TEST: [],
        }
        if split.validation is not None:
            result[SplitType.VALIDATION] = []

        for match, d in zip(self._matches, self._match_dicts):
            segment = split.assign_match(match)
            if segment is not None:
                result[segment].append(d)

        return result

    def get_odds_for_match(self, match_id: int) -> Optional[MarketOdds]:
        """Get odds record for a specific match."""
        return self._odds_by_match.get(match_id)

    def has_odds(self, match_dict: dict[str, Any]) -> bool:
        """Check if a match dict has odds available."""
        return (
            match_dict.get(self._market.odds_over_field) is not None
            and match_dict.get(self._market.odds_under_field) is not None
        )
