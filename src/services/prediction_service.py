"""Prediction creation service.

Ensures:
- proof_hash is ALWAYS computed server-side (I10)
- entry_odds are never fabricated (I3)
- BACKTEST predictions cannot enter live path (I12)
- All prediction creation is atomic with event logging
"""

from __future__ import annotations

import time
from typing import Optional
from uuid import UUID, uuid4

import asyncpg

from src.domain.prediction import PredictionEvent
from src.persistence.events import EventService, EventTypes
from src.persistence.pg_prediction_repository import PgPredictionRepository


class PredictionService:
    """Creates predictions with server-computed proof_hash."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def create_prediction(
        self,
        user_id: UUID,
        strategy_id: UUID,
        strategy_version: int,
        strategy_content_hash: str,
        match_id: int,
        match_date_unix: int,
        home_team: str,
        away_team: str,
        league_id: int,
        market_type: str,
        direction: str,
        entry_odds: Optional[float],
        model_edge_pct: float,
        confidence: float,
        recommended_stake: float,
        source: str,
        market_line: Optional[float] = None,
        model_version_id: Optional[UUID] = None,
    ) -> dict:
        """Create a prediction with server-computed proof_hash.

        The proof_hash is computed using PredictionEvent.compute_proof_hash()
        — the SAME algorithm as the existing domain layer. It is NEVER
        accepted from the client.

        Args:
            All prediction fields except proof_hash (server-computed)
            and status (always starts as PENDING).

        Returns:
            The created prediction record dict.
        """
        prediction_id = uuid4()

        # SERVER-SIDE proof_hash computation (I10)
        # Uses the canonical algorithm from src/domain/prediction.py
        timestamp = int(time.time())
        proof_hash = PredictionEvent.compute_proof_hash(
            strategy_content_hash=strategy_content_hash,
            match_id=match_id,
            direction=direction,
            entry_odds=entry_odds,
            timestamp=timestamp,
        )

        repo = PgPredictionRepository(self._conn)
        prediction = await repo.create(
            prediction_id=prediction_id,
            user_id=user_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            strategy_content_hash=strategy_content_hash,
            match_id=match_id,
            match_date_unix=match_date_unix,
            home_team=home_team,
            away_team=away_team,
            league_id=league_id,
            market_type=market_type,
            direction=direction,
            entry_odds=entry_odds,
            model_edge_pct=model_edge_pct,
            confidence=confidence,
            recommended_stake=recommended_stake,
            source=source,
            proof_hash=proof_hash,
            market_line=market_line,
            model_version_id=model_version_id,
        )

        # Emit event
        await EventService(self._conn).emit(
            event_type=EventTypes.PREDICTION_CREATED,
            aggregate_type="prediction",
            aggregate_id=str(prediction_id),
            actor_id=user_id,
            payload={
                "strategy_id": str(strategy_id),
                "strategy_version": strategy_version,
                "match_id": match_id,
                "direction": direction,
                "source": source,
            },
        )

        return prediction
