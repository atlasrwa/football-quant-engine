"""Ingestion pipeline orchestrating client, cache, and validator."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.ingestion.cache import CacheManager
from src.ingestion.client import FootyStatsClient
from src.ingestion.provider import MockProvider
from src.ingestion.validator import SchemaValidator
from src.models.match import Match

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """Orchestrates the full ingestion flow: fetch → cache → validate → parse.

    Supports both live API fetching and local fixture loading. Uses a
    cache-first strategy unless force_refresh is enabled.
    """

    def __init__(
        self,
        client: Optional[FootyStatsClient] = None,
        cache: Optional[CacheManager] = None,
        validator: Optional[SchemaValidator] = None,
        force_refresh: bool = False,
    ) -> None:
        """Initialize IngestionPipeline.

        Args:
            client: FootyStats API client. If None, uses default sandbox client.
            cache: Cache manager. If None, uses default data/raw/ directory.
            validator: Schema validator. If None, uses default data/errors/ directory.
            force_refresh: If True, bypasses cache and re-fetches from API.
        """
        self._client = client or FootyStatsClient()
        self._cache = cache or CacheManager()
        self._validator = validator or SchemaValidator()
        self._force_refresh = force_refresh

    @property
    def cache(self) -> CacheManager:
        """Access the cache manager."""
        return self._cache

    @property
    def validator(self) -> SchemaValidator:
        """Access the schema validator."""
        return self._validator

    async def ingest_league(
        self, league_id: int, season: str
    ) -> List[Match]:
        """Ingest all matches for a league/season from the API.

        Flow: API fetch → per-match caching → batch validation → Match parsing.

        Args:
            league_id: The FootyStats league identifier.
            season: The season string.

        Returns:
            List of validated Match objects.
        """
        # Step 1: Check cache or fetch from API
        if not self._force_refresh:
            cached = self._cache.get_bulk(league_id, season)
            if cached:
                logger.info(
                    "Using %d cached records for league=%d season=%s",
                    len(cached), league_id, season,
                )
                raw_records = cached
            else:
                raw_records = await self._fetch_and_cache(league_id, season)
        else:
            logger.info("Force refresh enabled, bypassing cache")
            raw_records = await self._fetch_and_cache(league_id, season)

        # Step 2: Validate
        valid_records, error_count = self._validator.validate_batch(raw_records)
        if error_count > 0:
            logger.warning(
                "%d records failed validation (logged to %s)",
                error_count,
                self._validator.error_log_path,
            )

        # Step 3: Parse to Match objects
        matches = self._parse_records(valid_records)
        logger.info(
            "Ingestion complete: %d matches ready (from %d raw records)",
            len(matches), len(raw_records),
        )
        return matches

    def ingest_from_fixtures(
        self, league_id: int, season: str, fixtures_dir: Optional[Path] = None
    ) -> List[Match]:
        """Ingest matches from local fixture files (synchronous).

        Useful for testing and offline development.

        Args:
            league_id: The FootyStats league identifier.
            season: The season string.
            fixtures_dir: Optional path to fixtures directory.

        Returns:
            List of validated Match objects.
        """
        provider = MockProvider(fixtures_dir=fixtures_dir)
        return provider.fetch_matches(league_id, season)

    def ingest_from_raw_records(
        self, records: List[Dict[str, Any]]
    ) -> List[Match]:
        """Validate and parse a list of raw record dicts.

        Useful for processing already-loaded data (e.g., from cache or test).

        Args:
            records: List of raw JSON dicts.

        Returns:
            List of validated Match objects.
        """
        valid_records, _ = self._validator.validate_batch(records)
        return self._parse_records(valid_records)

    async def _fetch_and_cache(
        self, league_id: int, season: str
    ) -> List[Dict[str, Any]]:
        """Fetch from API and cache each match individually.

        Args:
            league_id: League identifier.
            season: Season string.

        Returns:
            List of raw match dicts.
        """
        raw_matches = await self._client.fetch_league_matches(league_id, season)

        # Cache each match individually
        for record in raw_matches:
            match_id = record.get("id")
            if match_id is not None:
                self._cache.put(league_id, season, int(match_id), record)

        logger.info("Fetched and cached %d records", len(raw_matches))
        return raw_matches

    @staticmethod
    def _parse_records(records: List[Dict[str, Any]]) -> List[Match]:
        """Parse validated records into Match objects.

        Args:
            records: List of validated raw dicts.

        Returns:
            List of Match objects. Skips records that fail parsing.
        """
        matches: List[Match] = []

        for record in records:
            try:
                home_goals = int(record["homeGoalCount"])
                away_goals = int(record["awayGoalCount"])

                match = Match(
                    id=int(record["id"]),
                    date_unix=int(record["date_unix"]),
                    league_id=int(record["league_id"]),
                    season=str(record["season"]),
                    home_team=str(record["home_name"]),
                    away_team=str(record["away_name"]),
                    home_goals=home_goals,
                    away_goals=away_goals,
                    total_goals=home_goals + away_goals,
                    home_xg=float(record.get("team_a_xg") or 0.0),
                    away_xg=float(record.get("team_b_xg") or 0.0),
                    referee=record.get("referee_name") or None,
                    over_under_line=2.5,
                    over_odds=float(record["o25_potential"]) if record.get("o25_potential") else None,
                    under_odds=float(record["u25_potential"]) if record.get("u25_potential") else None,
                )
                matches.append(match)
            except (KeyError, ValueError, TypeError) as e:
                logger.warning("Failed to parse record id=%s: %s", record.get("id"), e)

        return matches
