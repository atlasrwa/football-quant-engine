"""PostgreSQL repositories for paper_portfolios and paper_ledger_entries."""

from __future__ import annotations

import json
from typing import List, Optional
from uuid import UUID

import asyncpg


class PgPaperPortfolioRepository:
    """Repository for paper betting portfolios."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def create(
        self,
        user_id: UUID,
        name: str = "Default",
        currency: str = "USD",
        initial_balance: float = 1000.0,
    ) -> dict:
        """Create a new paper portfolio. Returns the created record."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO paper_portfolios (user_id, name, currency, initial_balance, current_balance)
            VALUES ($1, $2, $3, $4, $4)
            RETURNING *
            """,
            user_id, name, currency, initial_balance,
        )
        return dict(row)

    async def get_by_id(self, portfolio_id: UUID) -> Optional[dict]:
        row = await self._conn.fetchrow(
            "SELECT * FROM paper_portfolios WHERE id = $1", portfolio_id
        )
        return dict(row) if row else None

    async def get_by_user(self, user_id: UUID) -> List[dict]:
        rows = await self._conn.fetch(
            "SELECT * FROM paper_portfolios WHERE user_id = $1 ORDER BY created_at",
            user_id,
        )
        return [dict(r) for r in rows]

    async def update_balance(self, portfolio_id: UUID, new_balance: float) -> None:
        """Update the cached current_balance. Called after ledger entry."""
        await self._conn.execute(
            "UPDATE paper_portfolios SET current_balance = $2 WHERE id = $1",
            portfolio_id, new_balance,
        )


class PgPaperLedgerRepository:
    """INSERT-only repository for the paper betting ledger.

    The ledger is the SOURCE OF TRUTH. Append-only, never mutated.
    """

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def append(
        self,
        portfolio_id: UUID,
        entry_type: str,
        amount: float,
        balance_after: float,
        prediction_id: Optional[UUID] = None,
        settlement_id: Optional[UUID] = None,
        metadata: Optional[dict] = None,
    ) -> int:
        """Append a ledger entry. Returns the entry ID."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO paper_ledger_entries (portfolio_id, prediction_id, settlement_id,
                entry_type, amount, balance_after, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
            RETURNING id
            """,
            portfolio_id, prediction_id, settlement_id,
            entry_type, amount, balance_after,
            json.dumps(metadata) if metadata else None,
        )
        return row["id"]

    async def get_by_portfolio(self, portfolio_id: UUID, limit: int = 100) -> List[dict]:
        """Get ledger entries for a portfolio, chronological."""
        rows = await self._conn.fetch(
            "SELECT * FROM paper_ledger_entries WHERE portfolio_id = $1 ORDER BY id ASC LIMIT $2",
            portfolio_id, limit,
        )
        return [dict(r) for r in rows]

    async def get_latest_balance(self, portfolio_id: UUID) -> Optional[float]:
        """Get the most recent balance_after value."""
        row = await self._conn.fetchrow(
            "SELECT balance_after FROM paper_ledger_entries WHERE portfolio_id = $1 ORDER BY id DESC LIMIT 1",
            portfolio_id,
        )
        return row["balance_after"] if row else None

    async def has_settlement_entry(self, settlement_id: UUID) -> bool:
        """Check if a settlement already has a ledger entry (dedup)."""
        row = await self._conn.fetchrow(
            "SELECT 1 FROM paper_ledger_entries WHERE settlement_id = $1 LIMIT 1",
            settlement_id,
        )
        return row is not None
