"""Event type registry and event service.

Centralizes all event types used across the platform and provides
a transactional helper for emitting audit events atomically with
the business operation they represent.

Event creation MUST occur in the same transaction as the state change.
"""

from __future__ import annotations

import json
import logging
from typing import Optional
from uuid import UUID

import asyncpg

from src.persistence.repositories import EventRecord

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# EVENT TYPE REGISTRY
# ═══════════════════════════════════════════════════════════════════

class EventTypes:
    """Centralized registry of all event types.

    Only event types corresponding to implemented operations exist here.
    Do NOT add types for future/unimplemented functionality.
    """

    # User lifecycle
    USER_REGISTERED = "USER_REGISTERED"
    USER_LOGIN = "USER_LOGIN"
    USER_DISABLED = "USER_DISABLED"

    # Wallet
    WALLET_LINKED = "WALLET_LINKED"
    WALLET_VERIFIED = "WALLET_VERIFIED"

    # Strategy lifecycle
    STRATEGY_CREATED = "STRATEGY_CREATED"
    STRATEGY_VERSION_CREATED = "STRATEGY_VERSION_CREATED"
    STRATEGY_VISIBILITY_CHANGED = "STRATEGY_VISIBILITY_CHANGED"
    STRATEGY_ARCHIVED = "STRATEGY_ARCHIVED"
    STRATEGY_DEPRECATED = "STRATEGY_DEPRECATED"
    STRATEGY_FORKED = "STRATEGY_FORKED"

    # Match data
    MATCH_IMPORTED = "MATCH_IMPORTED"
    MATCH_BATCH_IMPORTED = "MATCH_BATCH_IMPORTED"

    # Predictions & Settlement (Phase 3.3)
    PREDICTION_CREATED = "PREDICTION_CREATED"
    PREDICTION_SETTLED = "PREDICTION_SETTLED"
    PREDICTION_EXPIRED = "PREDICTION_EXPIRED"

    # Paper portfolio
    PORTFOLIO_CREATED = "PORTFOLIO_CREATED"
    LEDGER_ENTRY_CREATED = "LEDGER_ENTRY_CREATED"

    # Quarantine
    QUARANTINE_ENTERED = "QUARANTINE_ENTERED"
    QUARANTINE_PROMOTED = "QUARANTINE_PROMOTED"
    QUARANTINE_REJECTED = "QUARANTINE_REJECTED"

    # Validation
    VALIDATION_COMPLETED = "VALIDATION_COMPLETED"

    # Social
    FOLLOW_CREATED = "FOLLOW_CREATED"
    FOLLOW_DELETED = "FOLLOW_DELETED"

    # Reputation/Leaderboard
    REPUTATION_CALCULATED = "REPUTATION_CALCULATED"
    LEADERBOARD_SNAPSHOT_CREATED = "LEADERBOARD_SNAPSHOT_CREATED"

    # Broadcast (Phase 3.4)
    BROADCAST_CREATED = "BROADCAST_CREATED"
    BROADCAST_DISPATCHED = "BROADCAST_DISPATCHED"
    BROADCAST_FAILED = "BROADCAST_FAILED"

    # Attestation (Phase 3.4)
    ATTESTATION_COMMITTED = "ATTESTATION_COMMITTED"
    ATTESTATION_REVEALED = "ATTESTATION_REVEALED"
    ATTESTATION_CHAIN_SUBMITTED = "ATTESTATION_CHAIN_SUBMITTED"


# ═══════════════════════════════════════════════════════════════════
# EVENT SERVICE
# ═══════════════════════════════════════════════════════════════════

class EventService:
    """Transactional event emission service.

    Appends audit events to the event_log within the same database
    transaction as the business operation. This guarantees that:
    - If the business operation commits, the event is recorded.
    - If the business operation rolls back, the event is NOT recorded.

    Usage:
        async with transaction(user_id=str(ctx.user_id), user_role=ctx.role) as conn:
            # ... business logic ...
            await EventService(conn).emit(
                event_type=EventTypes.STRATEGY_CREATED,
                aggregate_type="strategy",
                aggregate_id=str(strategy_id),
                actor_id=ctx.user_id,
                payload={"name": strategy_name},
                correlation_id=request_id,
            )
    """

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def emit(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        actor_id: Optional[UUID] = None,
        actor_type: str = "user",
        payload: Optional[dict] = None,
        correlation_id: Optional[UUID] = None,
        causation_id: Optional[int] = None,
        event_version: int = 1,
    ) -> int:
        """Emit an audit event within the current transaction.

        Args:
            event_type: One of EventTypes constants.
            aggregate_type: Entity type ('user', 'strategy', 'match', etc.)
            aggregate_id: UUID or identifier of the affected entity.
            actor_id: UUID of the user/system that caused this event.
            actor_type: 'user', 'system', 'admin', or 'service'.
            payload: Arbitrary JSON-serializable event data.
            correlation_id: Groups related events across a request.
            causation_id: References parent event ID in a chain.
            event_version: Schema version of this event type.

        Returns:
            The auto-generated event ID (BIGSERIAL).
        """
        row = await self._conn.fetchrow(
            """
            INSERT INTO event_log (event_type, event_version, aggregate_type, aggregate_id,
                                   actor_type, actor_id, payload, correlation_id, causation_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9)
            RETURNING id
            """,
            event_type,
            event_version,
            aggregate_type,
            aggregate_id,
            actor_type,
            actor_id,
            json.dumps(payload or {}),
            correlation_id,
            causation_id,
        )
        event_id = row["id"]
        logger.debug(
            "Event emitted: type=%s aggregate=%s/%s actor=%s id=%d",
            event_type, aggregate_type, aggregate_id,
            str(actor_id)[:8] if actor_id else "system",
            event_id,
        )
        return event_id
