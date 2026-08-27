"""Broadcast API endpoints — Signal Dispatch.

Provides endpoints for creating/dispatching prediction signals
and querying broadcast delivery status.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from src.api.dependencies import get_current_user
from src.api.errors import APIError, ErrorCodes
from src.auth.context import AuthContext
from src.persistence.database import get_pool
from src.services.broadcast_service import BroadcastService, BroadcastError

router = APIRouter(prefix="/api/v1", tags=["broadcasts"])


# ═══════════════════ Schemas ═══════════════════

class CreateBroadcastRequest(BaseModel):
    prediction_id: UUID
    channel: str = Field(..., pattern=r"^(web|mobile|telegram|discord|email|webhook)$")
    destination: Optional[str] = Field(None, max_length=500)
    # Client does NOT supply:
    # - payload_hash (server-computed)
    # - deep_link (server-generated)
    # - proof_hash (server-derived)
    # - fdr_validated (server-derived)
    # - closing_odds (server-derived)
    # - settlement outcome (server-derived)


# ═══════════════════ Endpoints ═══════════════════

@router.post("/broadcasts", status_code=201)
async def create_broadcast(
    body: CreateBroadcastRequest,
    ctx: AuthContext = Depends(get_current_user),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> dict:
    """Create and dispatch a prediction broadcast.

    Enforces trust gate: prediction must belong to a PROMOTED strategy version.
    Payload hash and deep link are server-generated.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")

            svc = BroadcastService(conn)
            try:
                broadcast = await svc.create_broadcast(
                    user_id=ctx.user_id,
                    prediction_id=body.prediction_id,
                    channel=body.channel,
                    destination=body.destination,
                )
            except BroadcastError as e:
                raise APIError(422, ErrorCodes.BUSINESS_RULE_VIOLATION, str(e))

    return {"broadcast": _serialize(broadcast)}


@router.get("/broadcasts/{broadcast_id}")
async def get_broadcast(
    broadcast_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
) -> dict:
    """Get broadcast status by ID."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")

            svc = BroadcastService(conn)
            broadcast = await svc.get_broadcast(broadcast_id)

    if not broadcast:
        raise APIError(404, ErrorCodes.NOT_FOUND, "Broadcast not found")
    return {"broadcast": _serialize(broadcast)}


@router.get("/predictions/{prediction_id}/broadcasts")
async def get_prediction_broadcasts(
    prediction_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
) -> dict:
    """Get broadcast history for a prediction."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")

            svc = BroadcastService(conn)
            broadcasts = await svc.get_prediction_broadcasts(prediction_id)

    return {"broadcasts": [_serialize(b) for b in broadcasts]}


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
