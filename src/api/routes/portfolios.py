"""Paper portfolio and ledger API endpoints."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.api.dependencies import get_current_user
from src.api.errors import APIError, ErrorCodes
from src.auth.context import AuthContext
from src.persistence.database import get_pool
from src.persistence.pg_paper_repository import PgPaperPortfolioRepository, PgPaperLedgerRepository
from src.persistence.events import EventService, EventTypes

router = APIRouter(prefix="/api/v1/portfolios", tags=["portfolios"])


class CreatePortfolioRequest(BaseModel):
    name: str = Field(default="Default", min_length=1, max_length=100)
    currency: str = Field(default="USD", max_length=10)
    initial_balance: float = Field(default=1000.0, gt=0)


@router.post("", status_code=201)
async def create_portfolio(
    body: CreatePortfolioRequest,
    ctx: AuthContext = Depends(get_current_user),
) -> dict:
    """Create a paper portfolio."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")

            repo = PgPaperPortfolioRepository(conn)
            ledger = PgPaperLedgerRepository(conn)

            portfolio = await repo.create(
                user_id=ctx.user_id,
                name=body.name,
                currency=body.currency,
                initial_balance=body.initial_balance,
            )

            # Create opening balance ledger entry
            await ledger.append(
                portfolio_id=portfolio["id"],
                entry_type="OPENING_BALANCE",
                amount=body.initial_balance,
                balance_after=body.initial_balance,
                metadata={"currency": body.currency},
            )

            await EventService(conn).emit(
                event_type=EventTypes.PORTFOLIO_CREATED,
                aggregate_type="portfolio",
                aggregate_id=str(portfolio["id"]),
                actor_id=ctx.user_id,
                payload={"name": body.name, "initial_balance": body.initial_balance},
            )

    return {"portfolio": _serialize(portfolio)}


@router.get("")
async def list_portfolios(ctx: AuthContext = Depends(get_current_user)) -> dict:
    """List current user's portfolios."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")
            repo = PgPaperPortfolioRepository(conn)
            portfolios = await repo.get_by_user(ctx.user_id)
    return {"portfolios": [_serialize(p) for p in portfolios]}


@router.get("/{portfolio_id}")
async def get_portfolio(portfolio_id: UUID, ctx: AuthContext = Depends(get_current_user)) -> dict:
    """Get a specific portfolio."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")
            repo = PgPaperPortfolioRepository(conn)
            portfolio = await repo.get_by_id(portfolio_id)
    if not portfolio:
        raise APIError(404, ErrorCodes.NOT_FOUND, "Portfolio not found")
    return {"portfolio": _serialize(portfolio)}


@router.get("/{portfolio_id}/ledger")
async def get_ledger(
    portfolio_id: UUID,
    limit: int = 100,
    ctx: AuthContext = Depends(get_current_user),
) -> dict:
    """Get ledger entries for a portfolio."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")
            repo = PgPaperLedgerRepository(conn)
            entries = await repo.get_by_portfolio(portfolio_id, limit=limit)
    return {"entries": [_serialize(e) for e in entries]}


def _serialize(record: dict) -> dict:
    result = {}
    for k, v in record.items():
        if hasattr(v, "hex"):
            result[k] = str(v)
        elif hasattr(v, "isoformat"):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result
