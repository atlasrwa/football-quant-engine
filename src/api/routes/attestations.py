"""Attestation API endpoints — Commit/Reveal lifecycle.

Provides endpoints for creating attestation commitments and reveals,
and querying attestation provenance.

Trust boundaries:
- commitment_hash is server-generated (NEVER client-supplied)
- reveal outcome/closing_odds/P&L/CLV are server-derived from settlement
- cross-user operations blocked by ownership checks + RLS
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.api.dependencies import get_current_user
from src.api.errors import APIError, ErrorCodes
from src.auth.context import AuthContext
from src.persistence.database import get_pool
from src.services.attestation_service import AttestationService, AttestationError

router = APIRouter(prefix="/api/v1", tags=["attestations"])


# ═══════════════════ Schemas ═══════════════════

class CreateCommitmentRequest(BaseModel):
    prediction_id: UUID
    # Client does NOT supply:
    # - commitment_hash (server-computed)
    # - chain_id, contract_address, tx_hash, block_number (future Web3)


class CreateRevealRequest(BaseModel):
    prediction_id: UUID
    # Client does NOT supply:
    # - outcome (server-derived from settlement)
    # - closing_odds (server-derived from settlement)
    # - profit_loss (server-derived from settlement)
    # - clv_pct (server-derived from settlement)
    # - reveal_hash (server-computed)


# ═══════════════════ Endpoints ═══════════════════

@router.post("/attestations/commit", status_code=201)
async def create_commitment(
    body: CreateCommitmentRequest,
    ctx: AuthContext = Depends(get_current_user),
) -> dict:
    """Create a server-generated attestation commitment.

    Must be called BEFORE the prediction is settled.
    Idempotent: returns existing commitment if already created.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")

            svc = AttestationService(conn)
            try:
                commitment = await svc.create_commitment(
                    user_id=ctx.user_id,
                    prediction_id=body.prediction_id,
                )
            except AttestationError as e:
                raise APIError(422, ErrorCodes.BUSINESS_RULE_VIOLATION, str(e))

    return {"commitment": _serialize(commitment)}


@router.post("/attestations/{commitment_id}/reveal", status_code=201)
async def create_reveal(
    commitment_id: UUID,
    body: CreateRevealRequest,
    ctx: AuthContext = Depends(get_current_user),
) -> dict:
    """Create an attestation reveal after settlement.

    All settlement fields (outcome, closing_odds, P&L, CLV) are
    server-derived from authoritative state. Client supplies only
    the prediction_id for identification.

    Must be called AFTER the prediction is settled.
    Idempotent: returns existing reveal if already created.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")

            svc = AttestationService(conn)
            try:
                reveal = await svc.create_reveal(
                    user_id=ctx.user_id,
                    prediction_id=body.prediction_id,
                )
            except AttestationError as e:
                raise APIError(422, ErrorCodes.BUSINESS_RULE_VIOLATION, str(e))

    return {"reveal": _serialize(reveal)}


@router.get("/attestations/{commitment_id}")
async def get_attestation_by_commitment(
    commitment_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
) -> dict:
    """Get attestation status/provenance by commitment ID."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")

            svc = AttestationService(conn)
            commitment = await svc.get_commitment(commitment_id)

    if not commitment:
        raise APIError(404, ErrorCodes.NOT_FOUND, "Attestation commitment not found")
    return {"attestation": _serialize(commitment)}


@router.get("/predictions/{prediction_id}/attestation")
async def get_prediction_attestation(
    prediction_id: UUID,
    ctx: AuthContext = Depends(get_current_user),
) -> dict:
    """Get full attestation provenance for a prediction.

    Returns commitment + reveal (if exists) in a single response.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.user_id = '{ctx.user_id}'")
            await conn.execute(f"SET LOCAL app.user_role = '{ctx.role}'")

            svc = AttestationService(conn)
            attestation = await svc.get_attestation(prediction_id)

    if not attestation:
        raise APIError(404, ErrorCodes.NOT_FOUND, "No attestation found for this prediction")
    return {"attestation": _serialize(attestation)}


def _serialize(record: dict) -> dict:
    """Convert UUID/datetime/dict values to JSON-safe strings."""
    result = {}
    for k, v in record.items():
        if hasattr(v, "hex"):  # UUID
            result[k] = str(v)
        elif hasattr(v, "isoformat"):  # datetime
            result[k] = v.isoformat()
        elif isinstance(v, dict):
            result[k] = v  # JSONB already decoded
        else:
            result[k] = v
    return result
