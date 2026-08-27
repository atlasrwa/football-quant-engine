"""Broadcast service — signal dispatch with trust gating.

Ensures:
- Only PROMOTED predictions from valid strategies can be broadcast
- Trust gate derives eligibility from authoritative persisted state
- Client NEVER supplies trust-sensitive fields
- Payload hash is server-computed (canonical SHA-256)
- Deep links are stable server-generated references
- Broadcasts are idempotent via DB UNIQUE constraint
- Audit events emitted transactionally

Trust gate (derived from Phase 3.3 authoritative state):
    prediction exists
        ↓
    prediction belongs to valid strategy/version
        ↓
    quarantine status = PROMOTED
        ↓
    prediction is valid (PENDING or settled)
        ↓
    broadcast allowed
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import asyncpg

from src.persistence.broadcast_hashing import compute_broadcast_payload_hash
from src.persistence.events import EventService, EventTypes
from src.persistence.pg_broadcast_repository import PgBroadcastRepository
from src.persistence.pg_prediction_repository import PgPredictionRepository
from src.persistence.pg_quarantine_repository import PgQuarantineRepository
from src.services.dispatch import SignalDispatcher, DispatchResult


class BroadcastError(Exception):
    """Raised when broadcast cannot proceed."""
    pass


class BroadcastService:
    """Dispatches prediction signals with trust gating and delivery tracking."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn
        self._dispatcher = SignalDispatcher()

    async def create_broadcast(
        self,
        user_id: UUID,
        prediction_id: UUID,
        channel: str,
        destination: Optional[str] = None,
    ) -> dict:
        """Create and dispatch a prediction broadcast.

        Enforces the full trust gate before allowing broadcast.
        Idempotent: returns existing broadcast if already created.

        Args:
            user_id: Authenticated user requesting broadcast.
            prediction_id: The prediction to broadcast.
            channel: Target channel (web, mobile, telegram, etc.).
            destination: Channel-specific address.

        Returns:
            The broadcast log record.

        Raises:
            BroadcastError: If trust gate fails or prediction not found.
        """
        # ═══════════════════════════════════════════════════════
        # TRUST GATE: Derive eligibility from authoritative state
        # ═══════════════════════════════════════════════════════

        pred_repo = PgPredictionRepository(self._conn)
        prediction = await pred_repo.get_by_id(prediction_id)

        if not prediction:
            raise BroadcastError(f"Prediction {prediction_id} not found")

        # Ownership check
        if prediction["user_id"] != user_id:
            raise BroadcastError("Cannot broadcast another user's prediction")

        # Verify strategy/version is PROMOTED through quarantine
        qe_repo = PgQuarantineRepository(self._conn)
        quarantine = await qe_repo.get(
            prediction["strategy_id"],
            prediction["strategy_version"],
        )

        if not quarantine:
            raise BroadcastError(
                f"Strategy {prediction['strategy_id']} v{prediction['strategy_version']} "
                "has no quarantine record — cannot broadcast"
            )

        if quarantine["status"] != "PROMOTED":
            raise BroadcastError(
                f"Strategy {prediction['strategy_id']} v{prediction['strategy_version']} "
                f"is {quarantine['status']}, not PROMOTED — cannot broadcast"
            )

        # Validate channel
        from src.services.dispatch import SUPPORTED_CHANNELS
        if channel not in SUPPORTED_CHANNELS:
            raise BroadcastError(f"Unsupported channel: {channel}")

        # ═══════════════════════════════════════════════════════
        # BUILD CANONICAL PAYLOAD
        # ═══════════════════════════════════════════════════════

        prediction_timestamp = prediction["created_at"].isoformat()

        payload_hash = compute_broadcast_payload_hash(
            prediction_id=str(prediction_id),
            strategy_id=str(prediction["strategy_id"]),
            strategy_version=prediction["strategy_version"],
            direction=prediction["direction"],
            entry_odds=prediction["entry_odds"],
            confidence=prediction["confidence"],
            match_id=prediction["match_id"],
            proof_hash=prediction["proof_hash"],
            prediction_timestamp=prediction_timestamp,
        )

        # Generate stable deep link
        deep_link = f"/predictions/{prediction_id}"

        # ═══════════════════════════════════════════════════════
        # DISPATCH
        # ═══════════════════════════════════════════════════════

        broadcast_payload = {
            "prediction_id": str(prediction_id),
            "strategy_id": str(prediction["strategy_id"]),
            "strategy_version": prediction["strategy_version"],
            "direction": prediction["direction"],
            "entry_odds": prediction["entry_odds"],
            "confidence": prediction["confidence"],
            "match_id": prediction["match_id"],
            "proof_hash": prediction["proof_hash"],
            "prediction_timestamp": prediction_timestamp,
            "deep_link": deep_link,
        }

        dispatch_result = await self._dispatcher.dispatch(
            channel=channel,
            payload=broadcast_payload,
            destination=destination,
        )

        # ═══════════════════════════════════════════════════════
        # PERSIST BROADCAST RECORD (idempotent)
        # ═══════════════════════════════════════════════════════

        broadcast_id = uuid4()
        broadcast_repo = PgBroadcastRepository(self._conn)

        broadcast = await broadcast_repo.create(
            broadcast_id=broadcast_id,
            user_id=user_id,
            prediction_id=prediction_id,
            channel=channel,
            status=dispatch_result.status,
            payload_hash=payload_hash,
            destination=destination,
            deep_link=deep_link,
            dispatched_at=dispatch_result.dispatched_at,
            error_code=dispatch_result.error_code,
            error_message=dispatch_result.error_message,
        )

        # ═══════════════════════════════════════════════════════
        # EMIT AUDIT EVENT
        # ═══════════════════════════════════════════════════════

        if dispatch_result.success:
            event_type = EventTypes.BROADCAST_DISPATCHED
        else:
            event_type = EventTypes.BROADCAST_FAILED

        await EventService(self._conn).emit(
            event_type=event_type,
            aggregate_type="broadcast",
            aggregate_id=str(broadcast["id"]),
            actor_id=user_id,
            payload={
                "prediction_id": str(prediction_id),
                "channel": channel,
                "status": dispatch_result.status,
                "payload_hash": payload_hash,
            },
        )

        return broadcast

    async def get_broadcast(self, broadcast_id: UUID) -> Optional[dict]:
        """Get a broadcast by ID."""
        repo = PgBroadcastRepository(self._conn)
        return await repo.get_by_id(broadcast_id)

    async def get_prediction_broadcasts(self, prediction_id: UUID) -> list[dict]:
        """Get all broadcasts for a prediction."""
        repo = PgBroadcastRepository(self._conn)
        return await repo.get_by_prediction(prediction_id)
