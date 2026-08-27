"""Prediction and Settlement API endpoints."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from src.api.dependencies import get_current_user
from src.api.errors import APIError, ErrorCodes
from src.auth.context import AuthContext
from src.persistence.database import get_pool
from src.persistence.pg_prediction_repository import PgPredictionRepository
from src.persistence.pg_settlement_repository import PgSettlementRepository
from src.services.prediction_service import PredictionService
from src.services.settlement_service import SettlementService, SettlementError

router = APIRouter(prefix="/api/v1", tags=["predictions"])


# ═══════════════════ Schemas ═══════════════════

class CreatePredictionRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    strategy_id: UUID
    strategy_version: int
    strategy_content_hash: str = Field(..., min_length=64, max_length=64)
    match_id: int
    match_date_unix: int
    home_team: str
    away_team: str
    league_id: int
    market_type: str
    direction: str = Field(..., pattern=r"^(OVER|UNDER|BACK|LAY)$")
    entry_odds: Optional[float] = Field(None, gt=1.0)
    model_edge_pct: float
    confidence: float = Field(..., ge=0, le=100)
    recommended_stake: float = Field(..., ge=0)
    source: str = Field(..., pattern=r"^(LIVE_SIGNAL|PAPER_TRADE)$")
    market_line: Optional[float] = None
    model_version_id: Optional[UUID] = None
    # proof_hash NOT accepted from client (I10)
    # closing_odds NOT accepted (I9)
    # outcome NOT accepted (I11)
    # fdr_validated NOT accepted (I8)


class SettleRequest(BaseModel):
    prediction_id: UUID
    actual_home_goals: int = Field(..., ge=0)
    actual_away_goals: int = Field(..., ge=0)
    stake: float = Field(default=1.0, gt=0)
    portfolio_id: Optional[UUID] = None
    # outcome NOT accepted (I11)
    # closing_odds NOT accepted (I9)


# ═══════════════════ Endpoints ═══════════════════

@router.post("/predictions", status_code=201)
async def create_prediction(
    body: CreatePredictionRequest,
    ctx: AuthContext = Depends(get_current_user),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> dict:
    """Create a prediction. proof_hash computed server-side."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")

            svc = PredictionService(conn)
            prediction = await svc.create_prediction(
                user_id=ctx.user_id,
                strategy_id=body.strategy_id,
                strategy_version=body.strategy_version,
                strategy_content_hash=body.strategy_content_hash,
                match_id=body.match_id,
                match_date_unix=body.match_date_unix,
                home_team=body.home_team,
                away_team=body.away_team,
                league_id=body.league_id,
                market_type=body.market_type,
                direction=body.direction,
                entry_odds=body.entry_odds,
                model_edge_pct=body.model_edge_pct,
                confidence=body.confidence,
                recommended_stake=body.recommended_stake,
                source=body.source,
                market_line=body.market_line,
                model_version_id=body.model_version_id,
            )

    return {"prediction": _serialize(prediction)}


@router.get("/predictions")
async def list_predictions(
    status: Optional[str] = None,
    limit: int = 50,
    ctx: AuthContext = Depends(get_current_user),
) -> dict:
    """List current user's predictions."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")
            repo = PgPredictionRepository(conn)
            predictions = await repo.get_by_user(ctx.user_id, status=status, limit=limit)
    return {"predictions": [_serialize(p) for p in predictions]}


@router.get("/predictions/{prediction_id}")
async def get_prediction(
    prediction_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
) -> dict:
    """Get a specific prediction."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")
            repo = PgPredictionRepository(conn)
            prediction = await repo.get_by_id(prediction_id)
    if not prediction:
        raise APIError(404, ErrorCodes.NOT_FOUND, "Prediction not found")
    return {"prediction": _serialize(prediction)}


@router.post("/settlements/settle")
async def settle_prediction(
    body: SettleRequest,
    ctx: AuthContext = Depends(get_current_user),
) -> dict:
    """Settle a prediction. Outcome + closing_odds are server-derived."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")

            svc = SettlementService(conn)
            try:
                settlement = await svc.settle_prediction(
                    prediction_id=body.prediction_id,
                    actual_home_goals=body.actual_home_goals,
                    actual_away_goals=body.actual_away_goals,
                    stake=body.stake,
                    portfolio_id=body.portfolio_id,
                )
            except SettlementError as e:
                raise APIError(422, ErrorCodes.BUSINESS_RULE_VIOLATION, str(e))

    return {"settlement": _serialize(settlement)}


def _serialize(record: dict) -> dict:
    """Convert UUID/datetime values to JSON-safe strings."""
    result = {}
    for k, v in record.items():
        if hasattr(v, "hex"):  # UUID
            result[k] = str(v)
        elif hasattr(v, "isoformat"):  # datetime
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result
