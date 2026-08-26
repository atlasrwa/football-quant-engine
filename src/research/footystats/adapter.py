"""FootyStats Data Source Adapter — implements ResearchDataSource.

This is the primary integration point between FootyStats and the
research engine. It implements the existing ResearchDataSource interface
without modifying it.

Architecture:
    FootyStats API
        ↓
    FootyStatsResearchClient (handles auth, rate limit, pagination, cache)
        ↓
    MatchNormalizer (raw → ResearchMatch, null preservation)
        ↓
    RecordValidator (quality checks, deduplication)
        ↓
    FootyStatsDataSource (implements ResearchDataSource)
        ↓
    ResearchDataset (existing research engine)

Does NOT:
- Modify ResearchDataSource interface
- Embed FootyStats-specific logic in the research engine
- Fabricate missing values
- Store credentials in research objects
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional

from src.research.data_source import MarketOdds, ResearchDataSource, ResearchMatch
from src.research.footystats.client import FootyStatsResearchClient
from src.research.footystats.normalizer import MatchNormalizer
from src.research.footystats.provenance import DataProvenance, compute_match_hash, create_provenance
from src.research.footystats.quality import DataQualityStatus, QualityReport, RecordValidator

logger = logging.getLogger(__name__)


class FootyStatsDataSource(ResearchDataSource):
    """ResearchDataSource backed by the FootyStats API.

    Implements the exact interface consumed by the research engine.
    Data is fetched, normalized, validated, and deduplicated before
    being returned.

    Usage:
        source = FootyStatsDataSource(season_ids=[4759])
        dataset = ResearchDataset(source=source, market=corners_market)
        # ... proceed with existing research pipeline
    """

    def __init__(
        self,
        season_ids: list[int],
        api_key: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        client: Optional[FootyStatsResearchClient] = None,
    ) -> None:
        """Initialize FootyStats data source.

        Args:
            season_ids: List of FootyStats season/competition IDs to load.
            api_key: API key (reads from env if None).
            cache_dir: Cache directory for API responses.
            client: Pre-configured client (for testing/injection).
        """
        self._season_ids = season_ids
        self._client = client or FootyStatsResearchClient(
            api_key=api_key, cache_dir=cache_dir,
        )
        self._normalizer = MatchNormalizer()
        self._validator = RecordValidator()

        # Lazy-loaded data
        self._matches: Optional[list[ResearchMatch]] = None
        self._raw_records: Optional[list[dict[str, Any]]] = None
        self._market_odds: Optional[list[MarketOdds]] = None
        self._provenance: list[DataProvenance] = []
        self._quality_report: Optional[QualityReport] = None
        self._content_hash_value: Optional[str] = None

    @property
    def quality_report(self) -> Optional[QualityReport]:
        """Quality report from last data load."""
        return self._quality_report

    @property
    def provenance_records(self) -> list[DataProvenance]:
        """Provenance records for loaded data."""
        return list(self._provenance)

    @property
    def normalizer(self) -> MatchNormalizer:
        return self._normalizer

    def _ensure_loaded(self) -> None:
        """Lazy-load and process all data."""
        if self._matches is not None:
            return

        all_raw: list[dict[str, Any]] = []
        for season_id in self._season_ids:
            logger.info("Fetching season %d...", season_id)
            raw_matches = self._client.fetch_season_matches(season_id)
            all_raw.extend(raw_matches)
            logger.info("Season %d: %d raw records", season_id, len(raw_matches))

        self._raw_records = all_raw

        # Normalize
        normalized = self._normalizer.normalize_batch(all_raw)
        logger.info(
            "Normalized: %d matches from %d raw records (skipped %d)",
            len(normalized), len(all_raw), self._normalizer.skipped_count,
        )

        # Validate and deduplicate
        valid, rejected = self._validator.validate_batch(normalized)
        self._quality_report = self._validator.report
        logger.info(
            "Validation: %d valid, %d rejected (rate: %.1f%%)",
            len(valid), len(rejected), self._validator.report.valid_rate * 100,
        )

        # Sort chronologically
        self._matches = sorted(valid, key=lambda m: m.date_unix)

        # Extract odds
        self._market_odds = []
        for raw in all_raw:
            odds = self._normalizer.extract_market_odds(raw)
            self._market_odds.extend(odds)

        # Create provenance
        self._provenance = []
        for raw in all_raw:
            if raw.get("id") and raw.get("status") == "complete":
                prov = create_provenance(raw)
                self._provenance.append(prov)

        # Compute content hash
        self._content_hash_value = None

    def get_matches(
        self,
        league_id: Optional[int] = None,
        season: Optional[str] = None,
        min_date: Optional[int] = None,
        max_date: Optional[int] = None,
    ) -> list[ResearchMatch]:
        """Get matches matching filter criteria.

        Args:
            league_id: Filter by league/competition ID.
            season: Filter by season string (e.g., "2020/2021").
            min_date: Minimum date_unix (inclusive).
            max_date: Maximum date_unix (exclusive).

        Returns:
            List of ResearchMatch sorted by date_unix ascending.
        """
        self._ensure_loaded()
        assert self._matches is not None

        result = self._matches
        if league_id is not None:
            result = [m for m in result if m.league_id == league_id]
        if season is not None:
            result = [m for m in result if m.season == season]
        if min_date is not None:
            result = [m for m in result if m.date_unix >= min_date]
        if max_date is not None:
            result = [m for m in result if m.date_unix < max_date]

        return result

    def get_available_fields(self) -> list[str]:
        """Return fields that this source can provide.

        Based on actual API data, not assumptions.
        """
        self._ensure_loaded()

        # Return fields that have at least some non-null values
        if not self._normalizer.field_availability:
            return []

        return sorted(self._normalizer.field_availability.keys())

    def get_market_odds(
        self,
        match_ids: Optional[list[int]] = None,
        market: Optional[str] = None,
    ) -> list[MarketOdds]:
        """Get market odds data.

        Args:
            match_ids: Filter by match IDs.
            market: Filter by market type (e.g., "GOALS_TOTAL", "CORNERS_TOTAL").

        Returns:
            List of MarketOdds records.
        """
        self._ensure_loaded()
        assert self._market_odds is not None

        result = self._market_odds
        if match_ids is not None:
            id_set = set(match_ids)
            result = [o for o in result if o.match_id in id_set]
        if market is not None:
            result = [o for o in result if o.market == market]

        return result

    def compute_content_hash(self) -> str:
        """Compute deterministic content hash for the dataset.

        Based on match IDs and date_unix pairs — not retrieval time.
        Same data always produces same hash.
        """
        self._ensure_loaded()
        assert self._matches is not None

        if self._content_hash_value is not None:
            return self._content_hash_value

        canonical = json.dumps(
            [(m.match_id, m.date_unix) for m in self._matches],
            sort_keys=True,
            separators=(",", ":"),
        )
        self._content_hash_value = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return self._content_hash_value

    def get_coverage_summary(self) -> dict[str, Any]:
        """Get data coverage summary for auditing.

        Returns:
            Dict with coverage metrics per field.
        """
        self._ensure_loaded()
        assert self._matches is not None

        total = len(self._matches)
        if total == 0:
            return {"total_matches": 0}

        field_avail = self._normalizer.field_availability
        coverage = {}
        for field_name, count in sorted(field_avail.items()):
            coverage[field_name] = {
                "available": count,
                "missing": total - count,
                "coverage_pct": round(count / total * 100, 1),
            }

        # Date range
        dates = [m.date_unix for m in self._matches]

        return {
            "total_matches": total,
            "earliest_date_unix": min(dates),
            "latest_date_unix": max(dates),
            "seasons": list(set(m.season for m in self._matches)),
            "leagues": list(set(m.league_id for m in self._matches)),
            "teams": len(set(
                t for m in self._matches for t in (m.home_team, m.away_team)
            )),
            "field_coverage": coverage,
            "quality_report": self._quality_report.to_dict() if self._quality_report else None,
        }
