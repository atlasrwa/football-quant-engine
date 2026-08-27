"""Attestation service — commit/reveal lifecycle management.

Implements the Web3-ready attestation lifecycle:
    PREDICTION CREATED → COMMITMENT CREATED → SETTLEMENT → REVEAL CREATED

Ensures:
- Commitment is server-generated (client cannot supply commitment_hash)
- Commitment must be created BEFORE settlement
- Commitment after settlement is REJECTED
- Reveal requires existing commitment + existing settlement
- Reveal before settlement is REJECTED
- Settlement fields in reveal are server-derived (never client-supplied)
- Duplicate commitment/reveal operations are safely idempotent
- Cross-user operations are blocked
- Audit events emitted transactionally

Web3 readiness:
- chain_id, contract_address, tx_hash, block_number remain nullable
- Zero blockchain dependency
- Full offline operation
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import asyncpg

from src.persistence.broadcast_hashing import compute_commitment_hash, compute_reveal_hash
from src.persistence.events import EventService, EventTypes
from src.persistence.pg_attestation_repository import PgAttestationRepository
from src.persistence.pg_prediction_repository import PgPredictionRepository
from src.persistence.pg_settlement_repository import PgSettlementRepository


class AttestationError(Exception):
    """Raised when attestation operation cannot proceed."""
    pass


class AttestationService:
    """Manages the commit→reveal attestation lifecycle."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def create_commitment(
        self,
        user_id: UUID,
        prediction_id: UUID,
    ) -> dict:
        """Create an attestation commitment for a prediction.

        Server-generates the commitment_hash from authoritative prediction data.
        Idempotent: returns existing commitment if already created.

        Args:
            user_id: Authenticated user creating the commitment.
            prediction_id: The prediction to commit.

        Returns:
            The commitment record.

        Raises:
            AttestationError: If prediction not found, not owned by user,
                or already settled.
        """
        pred_repo = PgPredictionRepository(self._conn)
        attest_repo = PgAttestationRepository(self._conn)

        # Load authoritative prediction
        prediction = await pred_repo.get_by_id(prediction_id)
        if not prediction:
            raise AttestationError(f"Prediction {prediction_id} not found")

        # Ownership check
        if prediction["user_id"] != user_id:
            raise AttestationError("Cannot create commitment for another user's prediction")

        # Critical invariant: commitment MUST be before settlement
        # If prediction is already settled, commitment is too late
        settle_repo = PgSettlementRepository(self._conn)
        existing_settlement = await settle_repo.get_by_prediction_id(prediction_id)
        if existing_settlement:
            raise AttestationError(
                f"Prediction {prediction_id} is already settled — "
                "commitment must be created before settlement"
            )

        # Idempotency: check if commitment already exists
        existing = await attest_repo.get_commitment_by_prediction(prediction_id)
        if existing:
            return existing

        # Server-compute commitment hash from authoritative fields
        prediction_timestamp = prediction["created_at"].isoformat()

        commitment_hash = compute_commitment_hash(
            prediction_id=str(prediction_id),
            strategy_id=str(prediction["strategy_id"]),
            strategy_version=prediction["strategy_version"],
            entry_odds=prediction["entry_odds"],
            proof_hash=prediction["proof_hash"],
            prediction_timestamp=prediction_timestamp,
        )

        # Create commitment
        commitment_id = uuid4()
        commitment = await attest_repo.create_commitment(
            commitment_id=commitment_id,
            prediction_id=prediction_id,
            commitment_hash=commitment_hash,
        )

        # Emit audit event
        await EventService(self._conn).emit(
            event_type=EventTypes.ATTESTATION_COMMITTED,
            aggregate_type="attestation",
            aggregate_id=str(commitment_id),
            actor_id=user_id,
            payload={
                "prediction_id": str(prediction_id),
                "commitment_hash": commitment_hash,
            },
        )

        return commitment

    async def create_reveal(
        self,
        user_id: UUID,
        prediction_id: UUID,
    ) -> dict:
        """Create an attestation reveal after settlement.

        Loads all reveal fields from authoritative settlement state.
        Client CANNOT supply outcome, closing_odds, P&L, or CLV.
        Idempotent: returns existing reveal if already created.

        Args:
            user_id: Authenticated user creating the reveal.
            prediction_id: The prediction to reveal.

        Returns:
            The reveal record.

        Raises:
            AttestationError: If commitment not found, prediction not settled,
                or cross-user operation.
        """
        pred_repo = PgPredictionRepository(self._conn)
        attest_repo = PgAttestationRepository(self._conn)
        settle_repo = PgSettlementRepository(self._conn)

        # Load authoritative prediction
        prediction = await pred_repo.get_by_id(prediction_id)
        if not prediction:
            raise AttestationError(f"Prediction {prediction_id} not found")

        # Ownership check
        if prediction["user_id"] != user_id:
            raise AttestationError("Cannot create reveal for another user's prediction")

        # Commitment must exist
        commitment = await attest_repo.get_commitment_by_prediction(prediction_id)
        if not commitment:
            raise AttestationError(
                f"No commitment exists for prediction {prediction_id} — "
                "cannot reveal without prior commitment"
            )

        # Settlement must exist
        settlement = await settle_repo.get_by_prediction_id(prediction_id)
        if not settlement:
            raise AttestationError(
                f"Prediction {prediction_id} has not been settled — "
                "cannot reveal before settlement"
            )

        # Idempotency: check if reveal already exists
        existing = await attest_repo.get_reveal_by_commitment(commitment["id"])
        if existing:
            return existing

        # Build reveal payload from authoritative settlement data
        settled_at = settlement["settled_at"].isoformat()

        reveal_payload = {
            "prediction_id": str(prediction_id),
            "settlement_id": str(settlement["id"]),
            "commitment_hash": commitment["commitment_hash"],
            "outcome": settlement["outcome"],
            "entry_odds": settlement["entry_odds"],
            "closing_odds": settlement["closing_odds"],
            "profit_loss": settlement["profit_loss"],
            "clv_pct": settlement["clv_pct"],
            "settled_at": settled_at,
        }

        reveal_hash = compute_reveal_hash(
            prediction_id=str(prediction_id),
            settlement_id=str(settlement["id"]),
            commitment_hash=commitment["commitment_hash"],
            outcome=settlement["outcome"],
            entry_odds=settlement["entry_odds"],
            closing_odds=settlement["closing_odds"],
            profit_loss=settlement["profit_loss"],
            clv_pct=settlement["clv_pct"],
            settled_at=settled_at,
        )

        # Create reveal
        reveal_id = uuid4()
        reveal = await attest_repo.create_reveal(
            reveal_id=reveal_id,
            commitment_id=commitment["id"],
            prediction_id=prediction_id,
            settlement_id=settlement["id"],
            reveal_payload=reveal_payload,
            reveal_hash=reveal_hash,
        )

        # Emit audit event
        await EventService(self._conn).emit(
            event_type=EventTypes.ATTESTATION_REVEALED,
            aggregate_type="attestation",
            aggregate_id=str(reveal_id),
            actor_id=user_id,
            payload={
                "prediction_id": str(prediction_id),
                "commitment_id": str(commitment["id"]),
                "settlement_id": str(settlement["id"]),
                "reveal_hash": reveal_hash,
            },
        )

        return reveal

    async def get_attestation(self, prediction_id: UUID) -> Optional[dict]:
        """Get full attestation provenance for a prediction."""
        attest_repo = PgAttestationRepository(self._conn)
        return await attest_repo.get_full_attestation(prediction_id)

    async def get_commitment(self, commitment_id: UUID) -> Optional[dict]:
        """Get a commitment by its ID."""
        attest_repo = PgAttestationRepository(self._conn)
        return await attest_repo.get_commitment_by_id(commitment_id)
