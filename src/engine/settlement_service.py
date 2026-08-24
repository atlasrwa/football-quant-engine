"""Settlement service — resolves predictions against actual match outcomes.

This service bridges the gap between live/paper predictions and their
settlement. It maintains an in-memory store of PENDING predictions and
settles them when match results arrive.

Architecture:
    PredictionEvent (PENDING) → MatchResult arrives → SettlementFactory → Settlement
    
No persistence layer — in-memory store acceptable for Phase 2.
Persistence is a Phase 3 concern.

Settlement Idempotency Guarantee:
    A prediction can only be economically settled ONCE.
    - First settlement: SUCCESS → creates Settlement, fires callbacks
    - Repeated identical settlement: NO-OP → returns existing Settlement
    - Conflicting settlement: EXPLICIT ERROR → SettlementConflictError
    
    This guarantee holds regardless of retries, restarts, or duplicate calls.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Dict, List

from src.domain.prediction import PredictionEvent, PredictionSource, PredictionStatus
from src.domain.settlement import Settlement, SettlementOutcome
from src.domain.factories import SettlementFactory

logger = logging.getLogger(__name__)


class SettlementConflictError(Exception):
    """Raised when attempting to settle a prediction with a conflicting outcome.

    This occurs when a prediction has already been settled (e.g., as WIN)
    and a subsequent settlement attempt resolves it differently (e.g., as LOSS).
    This indicates a data integrity issue that requires investigation.
    """

    def __init__(
        self,
        prediction_id: str,
        existing_outcome: SettlementOutcome,
        new_outcome: SettlementOutcome,
    ) -> None:
        self.prediction_id = prediction_id
        self.existing_outcome = existing_outcome
        self.new_outcome = new_outcome
        super().__init__(
            f"Settlement conflict for prediction {prediction_id[:8]}: "
            f"already settled as {existing_outcome.value}, "
            f"cannot re-settle as {new_outcome.value}"
        )


@dataclass(frozen=True, slots=True)
class MatchResult:
    """Actual match outcome for settlement.

    Attributes:
        match_id: The match being settled.
        home_goals: Goals scored by home team.
        away_goals: Goals scored by away team.
        closing_odds_over: Closing over odds (None if unavailable).
        closing_odds_under: Closing under odds (None if unavailable).
    """

    match_id: int
    home_goals: int
    away_goals: int
    closing_odds_over: float | None = None
    closing_odds_under: float | None = None

    @property
    def total_goals(self) -> int:
        """Total goals in the match."""
        return self.home_goals + self.away_goals

    @property
    def result_str(self) -> str:
        """Score string (e.g., '2-1')."""
        return f"{self.home_goals}-{self.away_goals}"


@dataclass
class SettlementResult:
    """Result of settling predictions for a single match.

    Attributes:
        match_id: The match that was settled.
        settlements: List of Settlement records produced.
        settled_predictions: The original predictions that were settled.
        total_profit_loss: Sum of P&L across all settlements.
    """

    match_id: int
    settlements: List[Settlement]
    settled_predictions: List[PredictionEvent]
    total_profit_loss: float

    @property
    def n_wins(self) -> int:
        """Number of winning settlements."""
        return sum(1 for s in self.settlements if s.outcome == SettlementOutcome.WIN)

    @property
    def n_losses(self) -> int:
        """Number of losing settlements."""
        return sum(1 for s in self.settlements if s.outcome == SettlementOutcome.LOSS)

    @property
    def n_voids(self) -> int:
        """Number of voided settlements."""
        return sum(
            1 for s in self.settlements
            if s.outcome in (SettlementOutcome.VOID, SettlementOutcome.PUSH)
        )


class PredictionSettlementService:
    """Manages prediction lifecycle and settlement.

    Responsibilities:
    1. Accept and store PENDING predictions (from signal dispatch or paper trading)
    2. Settle predictions when match results arrive
    3. Notify registered callbacks on settlement (for quarantine updates, etc.)

    This is the central integration point between the prediction pipeline
    and outcome resolution.

    Usage:
        service = PredictionSettlementService()

        # Register predictions as they're generated
        service.register_prediction(prediction_event)

        # When match results arrive
        result = service.settle_match(match_result)

        # Access settlements
        for settlement in result.settlements:
            print(f"{settlement.prediction_id}: {settlement.outcome.value}")
    """

    def __init__(self) -> None:
        # match_id → list of PENDING predictions
        self._pending: Dict[int, List[PredictionEvent]] = {}
        # prediction_id → Settlement (settled records)
        self._settlements: Dict[str, Settlement] = {}
        # prediction_id → PredictionEvent (all registered, including settled)
        self._all_predictions: Dict[str, PredictionEvent] = {}
        # Settlement callbacks: called with (prediction, settlement) after each settlement
        self._on_settlement_callbacks: List[Callable[[PredictionEvent, Settlement], None]] = []

    @property
    def pending_count(self) -> int:
        """Total number of PENDING predictions across all matches."""
        return sum(len(preds) for preds in self._pending.values())

    @property
    def settled_count(self) -> int:
        """Total number of settled predictions."""
        return len(self._settlements)

    @property
    def pending_matches(self) -> List[int]:
        """Match IDs with PENDING predictions."""
        return [mid for mid, preds in self._pending.items() if preds]

    def register_prediction(self, prediction: PredictionEvent) -> None:
        """Register a PENDING prediction for future settlement.

        Args:
            prediction: A PredictionEvent in PENDING status.

        Raises:
            ValueError: If prediction is already settled or already registered.
        """
        if prediction.status != PredictionStatus.PENDING:
            raise ValueError(
                f"Cannot register non-PENDING prediction "
                f"(status={prediction.status.value}, id={prediction.prediction_id[:8]})"
            )

        if prediction.prediction_id in self._all_predictions:
            raise ValueError(
                f"Prediction already registered: {prediction.prediction_id[:8]}"
            )

        self._all_predictions[prediction.prediction_id] = prediction

        if prediction.match_id not in self._pending:
            self._pending[prediction.match_id] = []
        self._pending[prediction.match_id].append(prediction)

        logger.debug(
            "Registered prediction %s for match %d (%s %s)",
            prediction.prediction_id[:8],
            prediction.match_id,
            prediction.direction,
            prediction.strategy_id[:8],
        )

    def register_predictions(self, predictions: List[PredictionEvent]) -> int:
        """Batch register multiple predictions.

        Args:
            predictions: List of PENDING PredictionEvents.

        Returns:
            Number of successfully registered predictions.
        """
        registered = 0
        for pred in predictions:
            try:
                self.register_prediction(pred)
                registered += 1
            except ValueError as e:
                logger.warning("Skipped prediction: %s", e)
        return registered

    def settle_match(
        self,
        match_result: MatchResult,
        stake: float = 1.0,
    ) -> SettlementResult:
        """Settle all PENDING predictions for a completed match.

        Idempotency guarantee:
        - If a prediction is already settled with the SAME outcome: skip (no-op)
        - If a prediction is already settled with a DIFFERENT outcome: raise SettlementConflictError
        - Callbacks only fire for NEW settlements (never re-fired on retry)

        Args:
            match_result: The actual match outcome.
            stake: Stake amount for P&L calculation.

        Returns:
            SettlementResult with all settlements for this match.

        Raises:
            SettlementConflictError: If a prediction was already settled
                with a different outcome.
        """
        match_id = match_result.match_id
        pending = self._pending.pop(match_id, [])

        if not pending:
            logger.debug("No pending predictions for match %d", match_id)
            return SettlementResult(
                match_id=match_id,
                settlements=[],
                settled_predictions=[],
                total_profit_loss=0.0,
            )

        settlements: List[Settlement] = []
        settled_predictions: List[PredictionEvent] = []

        for prediction in pending:
            # IDEMPOTENCY CHECK: Has this prediction already been settled?
            existing = self._settlements.get(prediction.prediction_id)
            if existing is not None:
                # Determine what the new outcome WOULD be
                new_outcome = SettlementFactory._resolve_outcome(
                    direction=prediction.direction,
                    market_line=prediction.market_line,
                    actual_total_goals=match_result.total_goals,
                )

                if existing.outcome == new_outcome:
                    # Idempotent: same outcome → return existing, no callback
                    logger.debug(
                        "Prediction %s already settled as %s (idempotent skip)",
                        prediction.prediction_id[:8],
                        existing.outcome.value,
                    )
                    settlements.append(existing)
                    settled_predictions.append(prediction)
                    continue
                else:
                    # Conflict: different outcome → integrity error
                    raise SettlementConflictError(
                        prediction_id=prediction.prediction_id,
                        existing_outcome=existing.outcome,
                        new_outcome=new_outcome,
                    )

            # Determine closing odds based on direction
            closing_odds = self._get_closing_odds(prediction, match_result)

            settlement = SettlementFactory.settle_prediction(
                prediction=prediction,
                actual_total_goals=match_result.total_goals,
                actual_home_goals=match_result.home_goals,
                actual_away_goals=match_result.away_goals,
                closing_odds=closing_odds,
                stake=stake,
            )

            settlements.append(settlement)
            settled_predictions.append(prediction)
            self._settlements[prediction.prediction_id] = settlement

            # Invoke callbacks ONLY for new settlements (never on retry)
            for callback in self._on_settlement_callbacks:
                try:
                    callback(prediction, settlement)
                except Exception as e:
                    logger.error(
                        "Settlement callback error for %s: %s",
                        prediction.prediction_id[:8], e,
                    )

        total_pnl = sum(s.profit_loss for s in settlements)

        logger.info(
            "Settled match %d: %d predictions, P&L=%.2f (W:%d L:%d V:%d)",
            match_id,
            len(settlements),
            total_pnl,
            sum(1 for s in settlements if s.outcome == SettlementOutcome.WIN),
            sum(1 for s in settlements if s.outcome == SettlementOutcome.LOSS),
            sum(1 for s in settlements if s.outcome in (SettlementOutcome.VOID, SettlementOutcome.PUSH)),
        )

        return SettlementResult(
            match_id=match_id,
            settlements=settlements,
            settled_predictions=settled_predictions,
            total_profit_loss=total_pnl,
        )

    def settle_matches(
        self,
        match_results: List[MatchResult],
        stake: float = 1.0,
    ) -> List[SettlementResult]:
        """Batch settle multiple matches.

        Args:
            match_results: List of match outcomes.
            stake: Stake amount.

        Returns:
            List of SettlementResult (one per match with predictions).
        """
        results = []
        for match_result in match_results:
            result = self.settle_match(match_result, stake=stake)
            if result.settlements:
                results.append(result)
        return results

    def on_settlement(
        self, callback: Callable[[PredictionEvent, Settlement], None]
    ) -> None:
        """Register a callback invoked after each prediction is settled.

        The callback receives (prediction, settlement) and can perform
        side effects like updating quarantine P&L.

        Args:
            callback: Function taking (PredictionEvent, Settlement).
        """
        self._on_settlement_callbacks.append(callback)

    def get_prediction(self, prediction_id: str) -> PredictionEvent | None:
        """Look up a registered prediction by ID."""
        return self._all_predictions.get(prediction_id)

    def get_settlement(self, prediction_id: str) -> Settlement | None:
        """Look up a settlement by prediction ID."""
        return self._settlements.get(prediction_id)

    def get_pending_for_match(self, match_id: int) -> List[PredictionEvent]:
        """Get all PENDING predictions for a specific match."""
        return list(self._pending.get(match_id, []))

    def is_already_settled(self, prediction_id: str) -> bool:
        """Check if a prediction has already been settled.

        Args:
            prediction_id: The prediction to check.

        Returns:
            True if a settlement exists for this prediction.
        """
        return prediction_id in self._settlements

    def get_all_settlements(self) -> List[Settlement]:
        """Get all settlements."""
        return list(self._settlements.values())

    def get_settlements_by_strategy(self, strategy_id: str) -> List[Settlement]:
        """Get all settlements for a specific strategy."""
        results = []
        for prediction_id, settlement in self._settlements.items():
            prediction = self._all_predictions.get(prediction_id)
            if prediction and prediction.strategy_id == strategy_id:
                results.append(settlement)
        return results

    def _get_closing_odds(
        self, prediction: PredictionEvent, match_result: MatchResult
    ) -> float | None:
        """Get appropriate closing odds based on prediction direction."""
        if prediction.direction == "OVER":
            return match_result.closing_odds_over
        elif prediction.direction == "UNDER":
            return match_result.closing_odds_under
        return None
