"""File-based local JSON caching layer for raw API responses."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Default cache directory
_DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw"


class CacheManager:
    """Manages local JSON file cache for raw FootyStats API responses.

    Files are stored as: {cache_dir}/{league_id}_{season}_{match_id}.json

    Provides cache-first retrieval with optional force-refresh bypass.
    Season strings are sanitized (slashes replaced with underscores) to
    ensure safe filesystem paths (e.g., "2018/2019" → "2018_2019").
    """

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        """Initialize CacheManager.

        Args:
            cache_dir: Directory for cached JSON files. Defaults to data/raw/.
        """
        self._cache_dir = cache_dir or _DEFAULT_CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _sanitize_season(season: str) -> str:
        """Sanitize season string for use in file paths.

        Replaces slashes with underscores to prevent path traversal.

        Args:
            season: Raw season string (e.g., "2018/2019").

        Returns:
            Sanitized string safe for filenames (e.g., "2018_2019").
        """
        return season.replace("/", "_")

    @property
    def cache_dir(self) -> Path:
        """Return the cache directory path."""
        return self._cache_dir

    @property
    def hits(self) -> int:
        """Total cache hits since initialization."""
        return self._hits

    @property
    def misses(self) -> int:
        """Total cache misses since initialization."""
        return self._misses

    def _build_key(self, league_id: int, season: str, match_id: int) -> str:
        """Build the cache filename key.

        Args:
            league_id: League identifier.
            season: Season string (will be sanitized).
            match_id: Match identifier.

        Returns:
            Filename string without directory.
        """
        safe_season = self._sanitize_season(season)
        return f"{league_id}_{safe_season}_{match_id}.json"

    def _build_path(self, league_id: int, season: str, match_id: int) -> Path:
        """Build the full file path for a cache entry.

        Args:
            league_id: League identifier.
            season: Season string (will be sanitized).
            match_id: Match identifier.

        Returns:
            Full Path to the cache file.
        """
        return self._cache_dir / self._build_key(league_id, season, match_id)

    def exists(self, league_id: int, season: str, match_id: int) -> bool:
        """Check if a match is cached.

        Args:
            league_id: League identifier.
            season: Season string.
            match_id: Match identifier.

        Returns:
            True if cache file exists.
        """
        return self._build_path(league_id, season, match_id).is_file()

    def get(
        self, league_id: int, season: str, match_id: int
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a cached match record.

        Args:
            league_id: League identifier.
            season: Season string.
            match_id: Match identifier.

        Returns:
            The cached JSON dict, or None if not cached.
        """
        path = self._build_path(league_id, season, match_id)
        if not path.is_file():
            self._misses += 1
            logger.debug(
                "Cache MISS: %s (ts=%d)", path.name, int(time.time())
            )
            return None

        self._hits += 1
        logger.debug("Cache HIT: %s (ts=%d)", path.name, int(time.time()))
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def put(
        self, league_id: int, season: str, match_id: int, data: Dict[str, Any]
    ) -> Path:
        """Store a match record in the cache.

        Args:
            league_id: League identifier.
            season: Season string.
            match_id: Match identifier.
            data: The raw JSON dict to cache.

        Returns:
            Path to the written cache file.
        """
        path = self._build_path(league_id, season, match_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.debug("Cache WRITE: %s (ts=%d)", path.name, int(time.time()))
        return path

    def get_bulk(
        self, league_id: int, season: str
    ) -> list[Dict[str, Any]]:
        """Retrieve all cached records for a league/season.

        Args:
            league_id: League identifier.
            season: Season string (will be sanitized).

        Returns:
            List of cached JSON dicts matching the league/season prefix.
        """
        safe_season = self._sanitize_season(season)
        prefix = f"{league_id}_{safe_season}_"
        results = []
        for path in sorted(self._cache_dir.glob(f"{prefix}*.json")):
            with open(path, "r", encoding="utf-8") as f:
                results.append(json.load(f))
        logger.info(
            "Bulk cache read: %d files for %s%s",
            len(results), prefix, "*.json",
        )
        return results

    def clear(self, league_id: Optional[int] = None, season: Optional[str] = None) -> int:
        """Remove cached files.

        Args:
            league_id: If provided, only clear this league's cache.
            season: If provided (with league_id), only clear this season.

        Returns:
            Number of files removed.
        """
        if league_id is not None and season is not None:
            safe_season = self._sanitize_season(season)
            pattern = f"{league_id}_{safe_season}_*.json"
        elif league_id is not None:
            pattern = f"{league_id}_*.json"
        else:
            pattern = "*.json"

        removed = 0
        for path in self._cache_dir.glob(pattern):
            path.unlink()
            removed += 1

        logger.info("Cache clear: removed %d files (pattern=%s)", removed, pattern)
        self._hits = 0
        self._misses = 0
        return removed
