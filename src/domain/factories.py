"""Domain object factories.

These factories bridge the existing engine objects (Signal, XBetRecord, etc.)
to the new Phase 2 domain model. They create PredictionEvents and Settlements
from the existing pipeline outputs without modifying the existing code.

Design principle: the existing engine produces its outputs as before.
Factories consume those outputs and produce canonical domain objects.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List

from src.domain.prediction import PredictionEvent, PredictionSource, PredictionStatus
from src.domain.settlement import Settlement, SettlementOutcome
from src.engine.evaluator import Signal


class PredictionEventFactory:
    """Creates PredictionEvent instances from existing engine outputs.

    This factory bridges the gap between the existing Signal/XBetRecord
    types and the new canonical PredictionEvent domain object.
    """

    @staticmethod
    def from_signal(
        signal: Signal,
        strategy_id: str,
        strategy_version: int,
        strategy_content_hash: str,
        match_id: int,
        match_date_unix: int,
        home_team: str,
        away_team: str,
        league_id: int,
        market_type: str = "OVER_UNDER",
        market_line: float | None = 2.5,
        model_version_id: str | None = None,
        confidence: float = 50.0,
        recommended_stake: float = 0.01,
        source: PredictionSource = PredictionSource.LIVE_SIGNAL,
    ) -> PredictionEvent:
        """Create a PredictionEvent from a Signal.

        Args:
            signal: The generated Signal from StrategyEvaluator.
            strategy_id: Strategy identifier.
            strategy_version: Strategy version number.
            strategy_content_hash: Hash of strategy definition.
            match_id: Match being predicted.
            match_date_unix: Match timestamp.
            home_team: Home team name.
            away_team: Away team name.
            league_id: League identifier.
            market_type: Market type string.
            market_line: Market line (e.g., 2.5).
            model_version_id: Optional model version reference.
            confidence: Confidence score (0-100).
            recommended_stake: Fraction of bankroll.
            source: How the prediction was generated.

        Returns:
            A new PredictionEvent in PENDING status.
        """
        prediction_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        timestamp = int(datetime.now(timezone.utc).timestamp())

        proof_hash = PredictionEvent.compute_proof_hash(
            strategy_content_hash=strategy_content_hash,
            match_id=match_id,
            direction=signal.direction,
            entry_odds=signal.odds,
            timestamp=timestamp,
        )

        return PredictionEvent(
            prediction_id=prediction_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            strategy_content_hash=strategy_content_hash,
            model_version_id=model_version_id,
            match_id=match_id,
            match_date_unix=match_date_unix,
            home_team=home_team,
            away_team=away_team,
            league_id=league_id,
            market_type=market_type,
            market_line=market_line,
            direction=signal.direction,
            entry_odds=signal.odds,
            model_edge_pct=signal.edge * 100.0,
            confidence=confidence,
            recommended_stake=recommended_stake,
            source=source,
            status=PredictionStatus.PENDING,
            proof_hash=proof_hash,
            created_at=now,
            settled_at=None,
        )

    @staticmethod
    def from_backtest_bet(
        strategy_id: str,
        strategy_version: int,
        strategy_content_hash: str,
        match_id: int,
        match_date_unix: int,
        home_team: str,
        away_team: str,
        league_id: int,
        direction: str,
        odds: float | None,
        model_edge_pct: float,
        outcome: str,
        market_type: str = "OVER_UNDER",
        market_line: float | None = 2.5,
        model_version_id: str | None = None,
    ) -> PredictionEvent:
        """Create a PredictionEvent from a backtest bet record.

        In backtest mode, predictions are created already-settled because
        we know the outcome. The status is set based on the outcome.

        Args:
            strategy_id: Strategy identifier.
            strategy_version: Strategy version number.
            strategy_content_hash: Hash of strategy definition.
            match_id: Match identifier.
            match_date_unix: Match timestamp.
            home_team: Home team.
            away_team: Away team.
            league_id: League identifier.
            direction: Prediction direction.
            odds: Entry odds (None if unavailable).
            model_edge_pct: Model edge percentage.
            outcome: "WIN"/"LOSS"/"VOID".
            market_type: Market type string.
            market_line: Market line.
            model_version_id: Optional model version reference.

        Returns:
            A PredictionEvent with appropriate settled status.
        """
        prediction_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        timestamp = int(datetime.now(timezone.utc).timestamp())

        # Map outcome to status
        status_map = {
            "WIN": PredictionStatus.SETTLED_WIN,
            "LOSS": PredictionStatus.SETTLED_LOSS,
            "VOID": PredictionStatus.SETTLED_VOID,
        }
        status = status_map.get(outcome, PredictionStatus.SETTLED_VOID)

        proof_hash = PredictionEvent.compute_proof_hash(
            strategy_content_hash=strategy_content_hash,
            match_id=match_id,
            direction=direction,
            entry_odds=odds,
            timestamp=timestamp,
        )

        return PredictionEvent(
            prediction_id=prediction_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            strategy_content_hash=strategy_content_hash,
            model_version_id=model_version_id,
            match_id=match_id,
            match_date_unix=match_date_unix,
            home_team=home_team,
            away_team=away_team,
            league_id=league_id,
            market_type=market_type,
            market_line=market_line,
            direction=direction,
            entry_odds=odds,
            model_edge_pct=model_edge_pct,
            confidence=50.0,  # Default for backtest predictions
            recommended_stake=0.01,
            source=PredictionSource.BACKTEST,
            status=status,
            proof_hash=proof_hash,
            created_at=now,
            settled_at=now if status != PredictionStatus.PENDING else None,
        )


class SettlementFactory:
    """Creates Settlement instances from match outcomes."""

    @staticmethod
    def settle_prediction(
        prediction: PredictionEvent,
        actual_total_goals: int,
        actual_home_goals: int,
        actual_away_goals: int,
        closing_odds: float | None = None,
        stake: float = 1.0,
    ) -> Settlement:
        """Settle a PredictionEvent against actual match outcome.

        Args:
            prediction: The prediction to settle.
            actual_total_goals: Actual total goals scored.
            actual_home_goals: Home team goals.
            actual_away_goals: Away team goals.
            closing_odds: Closing odds for CLV (None if unavailable).
            stake: Stake amount.

        Returns:
            A Settlement record.
        """
        # Determine outcome based on direction and actual results
        outcome = SettlementFactory._resolve_outcome(
            direction=prediction.direction,
            market_line=prediction.market_line,
            actual_total_goals=actual_total_goals,
        )

        # Compute CLV if closing odds available
        clv_pct = Settlement.compute_clv(prediction.entry_odds, closing_odds)

        # Compute P&L
        profit_loss = Settlement.compute_profit_loss(
            outcome=outcome,
            odds=prediction.entry_odds,
            stake=stake,
        )

        now = datetime.now(timezone.utc).isoformat()
        actual_result = f"{actual_home_goals}-{actual_away_goals}"

        return Settlement(
            settlement_id=str(uuid.uuid4()),
            prediction_id=prediction.prediction_id,
            match_id=prediction.match_id,
            outcome=outcome,
            actual_total_goals=actual_total_goals,
            actual_result=actual_result,
            entry_odds=prediction.entry_odds,
            closing_odds=closing_odds,
            clv_pct=clv_pct,
            stake=stake,
            profit_loss=profit_loss,
            settled_at=now,
        )

    @staticmethod
    def _resolve_outcome(
        direction: str,
        market_line: float | None,
        actual_total_goals: int,
    ) -> SettlementOutcome:
        """Resolve the settlement outcome.

        Args:
            direction: Prediction direction ("OVER"/"UNDER").
            market_line: The market line (e.g., 2.5).
            actual_total_goals: Actual total goals.

        Returns:
            SettlementOutcome.
        """
        if market_line is None:
            return SettlementOutcome.VOID

        if direction == "OVER":
            if actual_total_goals > market_line:
                return SettlementOutcome.WIN
            elif actual_total_goals == market_line:
                return SettlementOutcome.PUSH
            else:
                return SettlementOutcome.LOSS
        elif direction == "UNDER":
            if actual_total_goals < market_line:
                return SettlementOutcome.WIN
            elif actual_total_goals == market_line:
                return SettlementOutcome.PUSH
            else:
                return SettlementOutcome.LOSS
        else:
            # BACK/LAY require different resolution logic (Phase 3+)
            return SettlementOutcome.VOID
