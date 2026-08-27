"""PostgreSQL implementation of MatchRepository.

ADAPTER PATTERN: The existing engine uses Match(id=int) where id is the
FootyStats external identifier. The database uses a surrogate BIGSERIAL
match_id with (external_source, external_id) as the provider-independent
identity.

This repository translates between the two representations:
- On write: Match.id → external_id column, match_id auto-generated
- On read: external_id → Match.id, match_id used only for internal FK references

The engine NEVER sees the surrogate match_id. It continues using integer IDs
exactly as before. The repository handles the mapping transparently.
"""

from __future__ import annotations

import json
from typing import List, Optional

import asyncpg

from src.models.match import Match


class PgMatchRepository:
    """PostgreSQL-backed match repository with provider-independent identity.

    Bridges the engine's Match(id=int) to the database's surrogate key scheme.
    """

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def upsert(
        self,
        match: Match,
        external_source: str = "footystats",
        raw_data: Optional[dict] = None,
    ) -> int:
        """Insert or update a match. Returns the surrogate match_id.

        On conflict (same external_source + external_id), updates mutable fields
        (goals, xG, odds, referee) but preserves the surrogate match_id.

        Args:
            match: The engine's Match object.
            external_source: Data provider identifier.
            raw_data: Optional raw provider payload for reproducibility.

        Returns:
            The database surrogate match_id (BIGINT).
        """
        row = await self._conn.fetchrow(
            """
            INSERT INTO matches (external_id, external_source, date_unix, league_id, season,
                                 home_team, away_team, home_goals, away_goals,
                                 home_xg, away_xg, referee, over_under_line,
                                 over_odds, under_odds, raw_data, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16::jsonb, 'completed')
            ON CONFLICT (external_source, external_id) DO UPDATE SET
                home_goals = EXCLUDED.home_goals,
                away_goals = EXCLUDED.away_goals,
                home_xg = EXCLUDED.home_xg,
                away_xg = EXCLUDED.away_xg,
                referee = EXCLUDED.referee,
                over_under_line = EXCLUDED.over_under_line,
                over_odds = EXCLUDED.over_odds,
                under_odds = EXCLUDED.under_odds,
                raw_data = COALESCE(EXCLUDED.raw_data, matches.raw_data),
                updated_at = NOW()
            RETURNING match_id
            """,
            match.id,               # external_id
            external_source,
            match.date_unix,
            match.league_id,
            match.season,
            match.home_team,
            match.away_team,
            match.home_goals,
            match.away_goals,
            match.home_xg,
            match.away_xg,
            match.referee,
            match.over_under_line,
            match.over_odds,
            match.under_odds,
            json.dumps(raw_data) if raw_data else None,
        )
        return row["match_id"]

    async def upsert_batch(
        self,
        matches: List[Match],
        external_source: str = "footystats",
    ) -> int:
        """Bulk upsert matches. Returns count of rows affected.

        Uses a single multi-row INSERT for efficiency.
        """
        if not matches:
            return 0

        # Build values for executemany
        count = 0
        for match in matches:
            await self.upsert(match, external_source=external_source)
            count += 1
        return count

    async def get_by_external_id(
        self,
        external_id: int,
        external_source: str = "footystats",
    ) -> Optional[Match]:
        """Retrieve a match by its external provider ID.

        Returns the engine's Match object (with id = external_id).
        """
        row = await self._conn.fetchrow(
            """
            SELECT external_id, date_unix, league_id, season,
                   home_team, away_team, home_goals, away_goals,
                   home_xg, away_xg, referee, over_under_line,
                   over_odds, under_odds
            FROM matches
            WHERE external_source = $1 AND external_id = $2
            """,
            external_source, external_id,
        )
        return self._row_to_match(row) if row else None

    async def get_by_surrogate_id(self, match_id: int) -> Optional[Match]:
        """Retrieve a match by its internal surrogate key.

        Used for FK resolution (e.g., predictions reference match_id).
        Returns the engine's Match object.
        """
        row = await self._conn.fetchrow(
            """
            SELECT external_id, date_unix, league_id, season,
                   home_team, away_team, home_goals, away_goals,
                   home_xg, away_xg, referee, over_under_line,
                   over_odds, under_odds
            FROM matches
            WHERE match_id = $1
            """,
            match_id,
        )
        return self._row_to_match(row) if row else None

    async def get_surrogate_id(
        self,
        external_id: int,
        external_source: str = "footystats",
    ) -> Optional[int]:
        """Look up the surrogate match_id for a given external ID.

        Used when creating predictions/settlements that need to FK to matches.
        """
        row = await self._conn.fetchrow(
            "SELECT match_id FROM matches WHERE external_source = $1 AND external_id = $2",
            external_source, external_id,
        )
        return row["match_id"] if row else None

    async def list_by_league_season(
        self,
        league_id: int,
        season: str,
        external_source: str = "footystats",
    ) -> List[Match]:
        """List all matches for a league/season, ordered chronologically.

        Returns the engine's Match objects.
        """
        rows = await self._conn.fetch(
            """
            SELECT external_id, date_unix, league_id, season,
                   home_team, away_team, home_goals, away_goals,
                   home_xg, away_xg, referee, over_under_line,
                   over_odds, under_odds
            FROM matches
            WHERE league_id = $1 AND season = $2 AND external_source = $3
            ORDER BY date_unix ASC
            """,
            league_id, season, external_source,
        )
        return [self._row_to_match(r) for r in rows]

    async def count_by_league_season(
        self, league_id: int, season: str
    ) -> int:
        """Count matches for a league/season."""
        row = await self._conn.fetchrow(
            "SELECT COUNT(*) as cnt FROM matches WHERE league_id = $1 AND season = $2",
            league_id, season,
        )
        return row["cnt"]

    @staticmethod
    def _row_to_match(row: asyncpg.Record) -> Match:
        """Convert a DB row to the engine's Match dataclass.

        The engine uses Match.id = external_id (integer).
        """
        home_goals = row["home_goals"]
        away_goals = row["away_goals"]
        return Match(
            id=row["external_id"],
            date_unix=row["date_unix"],
            league_id=row["league_id"],
            season=row["season"],
            home_team=row["home_team"],
            away_team=row["away_team"],
            home_goals=home_goals,
            away_goals=away_goals,
            total_goals=home_goals + away_goals,
            home_xg=row["home_xg"] or 0.0,
            away_xg=row["away_xg"] or 0.0,
            referee=row["referee"],
            over_under_line=row["over_under_line"] or 2.5,
            over_odds=row["over_odds"],
            under_odds=row["under_odds"],
        )
