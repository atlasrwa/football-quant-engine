"""In-memory repository implementations for testing.

These implementations allow existing unit tests to continue running
without a PostgreSQL connection. They mirror the interface of the
PostgreSQL repositories but store data in plain Python dicts.

Used by:
- Existing unit tests (no change required)
- CLI in offline/file mode (no --persist flag)
- Integration tests that don't need real DB
"""

from __future__ import annotations

from typing import Dict, List, Optional
from uuid import UUID

from src.models.match import Match


class InMemoryMatchRepository:
    """In-memory match repository for tests and offline CLI usage.

    Stores matches keyed by (external_source, external_id).
    Assigns monotonically increasing surrogate IDs.
    """

    def __init__(self) -> None:
        self._matches: Dict[tuple, Match] = {}  # (source, ext_id) → Match
        self._surrogate_map: Dict[tuple, int] = {}  # (source, ext_id) → surrogate
        self._next_id: int = 1

    async def upsert(
        self, match: Match, external_source: str = "footystats", raw_data: Optional[dict] = None
    ) -> int:
        """Store/update a match. Returns a surrogate ID."""
        key = (external_source, match.id)
        self._matches[key] = match
        if key not in self._surrogate_map:
            self._surrogate_map[key] = self._next_id
            self._next_id += 1
        return self._surrogate_map[key]

    async def get_by_external_id(
        self, external_id: int, external_source: str = "footystats"
    ) -> Optional[Match]:
        """Retrieve by external ID."""
        return self._matches.get((external_source, external_id))

    async def get_surrogate_id(
        self, external_id: int, external_source: str = "footystats"
    ) -> Optional[int]:
        """Get surrogate ID mapping."""
        return self._surrogate_map.get((external_source, external_id))

    async def list_by_league_season(
        self, league_id: int, season: str, external_source: str = "footystats"
    ) -> List[Match]:
        """List matches for a league/season, chronologically."""
        results = [
            m for (src, _), m in self._matches.items()
            if src == external_source and m.league_id == league_id and m.season == season
        ]
        return sorted(results, key=lambda m: m.date_unix)

    async def count_by_league_season(self, league_id: int, season: str) -> int:
        """Count matches for a league/season."""
        return len(await self.list_by_league_season(league_id, season))

    def clear(self) -> None:
        """Reset all stored data."""
        self._matches.clear()
        self._surrogate_map.clear()
        self._next_id = 1
