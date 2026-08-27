"""Quarantine lifecycle service.

Manages the state machine for strategy version quarantine:
  PENDING_QUARANTINE → PROMOTED (after 90 days + validation)
  PENDING_QUARANTINE → REJECTED

Does NOT modify the existing QuarantineTracker logic.
Uses the DB as the state store; the application enforces transition rules.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import asyncpg

from src.persistence.events import EventService, EventTypes
from src.persistence.pg_quarantine_repository import PgQuarantineRepository
from src.persistence.pg_validation_repository import PgValidationRepository


class QuarantineError(Exception):
    """Raised when quarantine operation fails."""
    pass


class QuarantineService:
    """Manages version-specific quarantine lifecycle."""

    # Minimum paper trades required before paper P&L is considered a
    # meaningful signal for promotion. Paired with the paper_pnl > 0 check
    # in PgQuarantineRepository.promote() — without both, promotion was
    # gated only on elapsed time + one historical validation run, so a
    # strategy that lost money for 90 days of paper trading could still
    # go live (see AUDIT_REPORT.md / RISK_REGISTER.md R09).
    MIN_PAPER_BETS_FOR_PROMOTION: int = 30

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def enter_quarantine(
        self,
        strategy_id: UUID,
        strategy_version: int,
        user_id: UUID,
    ) -> dict:
        """Enter a strategy version into quarantine.

        Idempotent: if already quarantined, returns existing entry.
        """
        repo = PgQuarantineRepository(self._conn)
        entry = await repo.enter(strategy_id, strategy_version, user_id)

        # Emit event (only if newly created)
        if entry.get("status") == "PENDING_QUARANTINE" and entry.get("paper_bets", 0) == 0:
            await EventService(self._conn).emit(
                event_type=EventTypes.QUARANTINE_ENTERED,
                aggregate_type="quarantine",
                aggregate_id=f"{strategy_id}:{strategy_version}",
                actor_id=user_id,
                payload={
                    "strategy_id": str(strategy_id),
                    "strategy_version": strategy_version,
                },
            )

        return entry

    async def promote(
        self,
        strategy_id: UUID,
        strategy_version: int,
        user_id: UUID,
    ) -> dict:
        """Promote a strategy version from quarantine.

        Requirements:
        - Must be PENDING_QUARANTINE
        - 90-day quarantine period must have elapsed
        - Must have a PASSED validation run
        - Must have at least MIN_PAPER_BETS_FOR_PROMOTION paper trades
        - Cumulative paper P&L must be positive

        Raises QuarantineError if requirements not met.
        """
        repo = PgQuarantineRepository(self._conn)
        val_repo = PgValidationRepository(self._conn)

        # Check validation exists
        validation = await val_repo.get_latest_passed(strategy_id, strategy_version)
        if not validation:
            raise QuarantineError(
                f"Strategy {strategy_id} v{strategy_version} has no PASSED validation. "
                "Cannot promote without statistical validation."
            )

        # Attempt promotion (DB enforces quarantine_until <= NOW(), paper_bets,
        # and paper_pnl atomically in the WHERE clause).
        result = await repo.promote(
            strategy_id, strategy_version,
            min_paper_bets=self.MIN_PAPER_BETS_FOR_PROMOTION,
        )
        if not result:
            # Check why it failed, most specific reason first
            entry = await repo.get(strategy_id, strategy_version)
            if not entry:
                raise QuarantineError("Strategy version not in quarantine")
            if entry["status"] != "PENDING_QUARANTINE":
                raise QuarantineError(f"Strategy is already {entry['status']}")
            if entry["quarantine_until"] > datetime.now(timezone.utc):
                raise QuarantineError(
                    "90-day quarantine period has not elapsed"
                )
            if entry["paper_bets"] < self.MIN_PAPER_BETS_FOR_PROMOTION:
                raise QuarantineError(
                    f"Insufficient paper trading volume: {entry['paper_bets']}/"
                    f"{self.MIN_PAPER_BETS_FOR_PROMOTION} bets required"
                )
            raise QuarantineError(
                f"Paper trading P&L is not positive: {entry['paper_pnl']:+.2f}"
            )

        # Emit event
        await EventService(self._conn).emit(
            event_type=EventTypes.QUARANTINE_PROMOTED,
            aggregate_type="quarantine",
            aggregate_id=f"{strategy_id}:{strategy_version}",
            actor_id=user_id,
            payload={
                "strategy_id": str(strategy_id),
                "strategy_version": strategy_version,
                "validation_id": str(validation["id"]),
            },
        )

        return result

    async def reject(
        self,
        strategy_id: UUID,
        strategy_version: int,
        user_id: UUID,
        reason: str = "",
    ) -> dict:
        """Reject a quarantined strategy version.

        Raises QuarantineError if not in PENDING_QUARANTINE state.
        """
        repo = PgQuarantineRepository(self._conn)
        result = await repo.reject(strategy_id, strategy_version)
        if not result:
            entry = await repo.get(strategy_id, strategy_version)
            if not entry:
                raise QuarantineError("Strategy version not in quarantine")
            raise QuarantineError(f"Strategy is already {entry['status']}")

        await EventService(self._conn).emit(
            event_type=EventTypes.QUARANTINE_REJECTED,
            aggregate_type="quarantine",
            aggregate_id=f"{strategy_id}:{strategy_version}",
            actor_id=user_id,
            payload={
                "strategy_id": str(strategy_id),
                "strategy_version": strategy_version,
                "reason": reason,
            },
        )

        return result
