"""Quarantine and Validation API endpoints."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.dependencies import get_current_user
from src.api.errors import APIError, ErrorCodes
from src.auth.context import AuthContext
from src.persistence.database import get_pool
from src.persistence.pg_quarantine_repository import PgQuarantineRepository
from src.persistence.pg_validation_repository import PgValidationRepository
from src.services.quarantine_service import QuarantineService, QuarantineError

router = APIRouter(prefix="/api/v1", tags=["quarantine"])


class EnterQuarantineRequest(BaseModel):
    strategy_id: UUID
    strategy_version: int


@router.post("/quarantine/enter", status_code=201)
async def enter_quarantine(
    body: EnterQuarantineRequest,
    ctx: AuthContext = Depends(get_current_user),
) -> dict:
    """Enter a strategy version into quarantine."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")

            svc = QuarantineService(conn)
            entry = await svc.enter_quarantine(
                body.strategy_id, body.strategy_version, ctx.user_id
            )

    return {"quarantine": _serialize(entry)}


@router.post("/quarantine/{strategy_id}/{version}/promote")
async def promote_quarantine(
    strategy_id: UUID,
    version: int,
    ctx: AuthContext = Depends(get_current_user),
) -> dict:
    """Promote a strategy version from quarantine.

    Requires 90-day period elapsed + PASSED validation.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")

            svc = QuarantineService(conn)
            try:
                entry = await svc.promote(strategy_id, version, ctx.user_id)
            except QuarantineError as e:
                raise APIError(422, ErrorCodes.BUSINESS_RULE_VIOLATION, str(e))

    return {"quarantine": _serialize(entry)}


@router.get("/quarantine/{strategy_id}/{version}")
async def get_quarantine(
    strategy_id: UUID,
    version: int,
    ctx: AuthContext = Depends(get_current_user),
) -> dict:
    """Get quarantine status for a strategy version."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")

            repo = PgQuarantineRepository(conn)
            entry = await repo.get(strategy_id, version)

    if not entry:
        raise APIError(404, ErrorCodes.NOT_FOUND, "Quarantine entry not found")
    return {"quarantine": _serialize(entry)}


# ═══════════════════ Validation ═══════════════════

@router.get("/validation/{validation_id}")
async def get_validation(
    validation_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
) -> dict:
    """Get a validation run result."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")
            repo = PgValidationRepository(conn)
            result = await repo.get_by_id(validation_id)

    if not result:
        raise APIError(404, ErrorCodes.NOT_FOUND, "Validation run not found")
    return {"validation": _serialize(result)}


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
