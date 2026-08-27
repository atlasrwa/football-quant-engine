"""PostgreSQL repository for market_prices (time-series observations)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

import asyncpg


class PgMarketPriceRepository:
    """INSERT-only market price time-series repository."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def insert(
        self,
        match_id: int,
        market_type: str,
        selection: str,
        price_type: str,
        odds: float,
        observed_at: datetime,
        source: str,
        line: Optional[float] = None,
        raw_payload: Optional[dict] = None,
    ) -> int:
        """Insert a market price observation. Returns the row ID."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO market_prices (match_id, market_type, line, selection, price_type,
                                       odds, observed_at, source, raw_payload)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
            RETURNING id
            """,
            match_id, market_type, line, selection, price_type,
            odds, observed_at, source,
            json.dumps(raw_payload) if raw_payload else None,
        )
        return row["id"]

    async def insert_batch(
        self, records: List[dict]
    ) -> int:
        """Batch insert price observations. Returns count inserted."""
        count = 0
        for r in records:
            await self.insert(
                match_id=r["match_id"],
                market_type=r["market_type"],
                selection=r["selection"],
                price_type=r["price_type"],
                odds=r["odds"],
                observed_at=r["observed_at"],
                source=r["source"],
                line=r.get("line"),
                raw_payload=r.get("raw_payload"),
            )
            count += 1
        return count

    async def get_price_history(
        self,
        match_id: int,
        market_type: str,
        selection: str,
    ) -> List[dict]:
        """Get all price observations for a match/market/selection, chronological."""
        rows = await self._conn.fetch(
            """
            SELECT id, match_id, market_type, line, selection, price_type,
                   odds, observed_at, source
            FROM market_prices
            WHERE match_id = $1 AND market_type = $2 AND selection = $3
            ORDER BY observed_at ASC
            """,
            match_id, market_type, selection,
        )
        return [dict(r) for r in rows]

    async def get_closing_price(
        self,
        match_id: int,
        market_type: str,
        selection: str,
        source: Optional[str] = None,
    ) -> Optional[float]:
        """Get the closing price for a market. Returns odds or None."""
        query = """
            SELECT odds FROM market_prices
            WHERE match_id = $1 AND market_type = $2 AND selection = $3
              AND price_type = 'CLOSING'
        """
        params: list = [match_id, market_type, selection]
        if source:
            query += " AND source = $4"
            params.append(source)
        query += " ORDER BY observed_at DESC LIMIT 1"

        row = await self._conn.fetchrow(query, *params)
        return row["odds"] if row else None
