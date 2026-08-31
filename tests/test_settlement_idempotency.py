"""Tests for settlement idempotency and economic integrity.

These tests verify the P0 invariant:
    One prediction → one settlement → one economic effect.

Failure modes tested:
- Repeated identical settlement (must be no-op)
- Conflicting settlement (must raise SettlementConflictError)
- Callback double-execution prevention
- Duplicate P&L prevention
- Quarantine bridge deduplication
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from src.domain.prediction import PredictionEvent, PredictionSource, PredictionStatus
from src.domain.settlement import Settlement, SettlementOutcome
from src.engine.analysis.fdr import QuarantineTracker
from src.engine.market.quarantine_bridge import QuarantineSettlementBridge
from src.engine.market.settlement_service import (
    MatchResult,
    PredictionSettlementService,
    SettlementConflictError,
    SettlementResult,
)


def _make_pending(
    prediction_id: str = "pred-001",
    match_id: int = 100,
    direction: str = "OVER",
    odds: float = 2.0,
    market_line: float = 2.5,
    source: PredictionSource = PredictionSource.LIVE_SIGNAL,
    strategy_id: str = "strat-001",
) -> PredictionEvent:
    """Create a PENDING prediction for testing."""
    return PredictionEvent(
        prediction_id=prediction_id,
        strategy_id=strategy_id,
        strategy_version=1,
        strategy_content_hash="a" * 64,
        model_version_id=None,
        match_id=match_id,
        match_date_unix=1700000000,
        home_team="Home",
        away_team="Away",
        league_id=4759,
        market_type="OVER_UNDER",
        market_line=market_line,
        direction=direction,
        entry_odds=odds,
        model_edge_pct=10.0,
        confidence=80.0,
        recommended_stake=0.05,
        source=source,
        status=PredictionStatus.PENDING,
        proof_hash="f" * 64,
        created_at="2024-01-01T00:00:00+00:00",
        settled_at=None,
    )


class TestSettlementIdempotency:
    """Settlement is idempotent: repeated calls produce same result."""

    def test_first_settlement_succeeds(self):
        """First settlement creates a new Settlement record."""
        service = PredictionSettlementService()
        pe = _make_pending(match_id=100, direction="OVER")
        service.register_prediction(pe)

        result = service.settle_match(MatchResult(match_id=100, home_goals=2, away_goals=1))

        assert len(result.settlements) == 1
        assert result.settlements[0].outcome == SettlementOutcome.WIN
        assert service.settled_count == 1

    def test_repeated_identical_settlement_is_noop(self):
        """Second settlement of same prediction with same outcome returns existing."""
        service = PredictionSettlementService()
        pe = _make_pending(prediction_id="idempotent-001", match_id=100, direction="OVER")
        service.register_prediction(pe)

        # First settlement
        result1 = service.settle_match(MatchResult(match_id=100, home_goals=2, away_goals=1))
        settlement1 = result1.settlements[0]

        # Re-add to pending (simulates retry/restart)
        service._pending.setdefault(100, []).append(pe)

        # Second settlement — same match result
        result2 = service.settle_match(MatchResult(match_id=100, home_goals=2, away_goals=1))

        # Returns existing settlement (idempotent)
        assert len(result2.settlements) == 1
        assert result2.settlements[0].settlement_id == settlement1.settlement_id

        # Only ONE settlement exists in the store
        assert service.settled_count == 1

    def test_repeated_settlement_does_not_fire_callbacks(self):
        """Callbacks do not fire on idempotent retry."""
        service = PredictionSettlementService()
        callback_count = [0]

        def counting_callback(pred, settlement):
            callback_count[0] += 1

        service.on_settlement(counting_callback)

        pe = _make_pending(prediction_id="callback-001", match_id=100, direction="OVER")
        service.register_prediction(pe)

        # First settlement — callback fires
        service.settle_match(MatchResult(match_id=100, home_goals=2, away_goals=1))
        assert callback_count[0] == 1

        # Re-add to pending and settle again
        service._pending.setdefault(100, []).append(pe)
        service.settle_match(MatchResult(match_id=100, home_goals=2, away_goals=1))

        # Callback did NOT fire again
        assert callback_count[0] == 1

    def test_conflicting_settlement_raises_error(self):
        """Settling with different outcome raises SettlementConflictError."""
        service = PredictionSettlementService()
        pe = _make_pending(prediction_id="conflict-001", match_id=100, direction="OVER", market_line=2.5)
        service.register_prediction(pe)

        # First: OVER 2.5, 3 goals → WIN
        service.settle_match(MatchResult(match_id=100, home_goals=2, away_goals=1))

        # Re-add to pending
        service._pending.setdefault(100, []).append(pe)

        # Second: same prediction but different result (1 goal → LOSS)
        with pytest.raises(SettlementConflictError) as exc_info:
            service.settle_match(MatchResult(match_id=100, home_goals=0, away_goals=1))

        assert exc_info.value.existing_outcome == SettlementOutcome.WIN
        assert exc_info.value.new_outcome == SettlementOutcome.LOSS
        assert "conflict" in str(exc_info.value)

    def test_is_already_settled_check(self):
        """is_already_settled() returns True after settlement."""
        service = PredictionSettlementService()
        pe = _make_pending(prediction_id="check-001", match_id=100)
        service.register_prediction(pe)

        assert not service.is_already_settled("check-001")

        service.settle_match(MatchResult(match_id=100, home_goals=2, away_goals=1))

        assert service.is_already_settled("check-001")

    def test_settlement_count_not_incremented_on_retry(self):
        """settled_count stays at 1 even after idempotent retry."""
        service = PredictionSettlementService()
        pe = _make_pending(prediction_id="count-001", match_id=100)
        service.register_prediction(pe)

        service.settle_match(MatchResult(match_id=100, home_goals=3, away_goals=0))
        assert service.settled_count == 1

        # Retry
        service._pending.setdefault(100, []).append(pe)
        service.settle_match(MatchResult(match_id=100, home_goals=3, away_goals=0))
        assert service.settled_count == 1  # Still 1


class TestEconomicIntegrity:
    """One prediction produces exactly one economic effect."""

    def test_one_prediction_one_pnl(self):
        """Settlement P&L is computed exactly once."""
        service = PredictionSettlementService()
        pe = _make_pending(prediction_id="econ-001", match_id=100, odds=2.0, direction="OVER")
        service.register_prediction(pe)

        result = service.settle_match(MatchResult(match_id=100, home_goals=2, away_goals=1))
        assert result.total_profit_loss == 1.0  # (2.0 - 1) * 1.0

    def test_retry_does_not_double_pnl(self):
        """Repeated settlement does not double the P&L."""
        service = PredictionSettlementService()
        pe = _make_pending(prediction_id="double-001", match_id=100, odds=2.0, direction="OVER")
        service.register_prediction(pe)

        # First settlement
        result1 = service.settle_match(MatchResult(match_id=100, home_goals=2, away_goals=1))
        first_pnl = result1.total_profit_loss

        # Re-add and retry
        service._pending.setdefault(100, []).append(pe)
        result2 = service.settle_match(MatchResult(match_id=100, home_goals=2, away_goals=1))

        # P&L from result2 is same settlement (not new money)
        assert result2.total_profit_loss == first_pnl

        # Total settlements in service is still 1
        all_settlements = service.get_all_settlements()
        assert len(all_settlements) == 1
        total_realized = sum(s.profit_loss for s in all_settlements)
        assert total_realized == 1.0

    def test_multiple_predictions_independent_settlement(self):
        """Multiple predictions for same match settle independently."""
        service = PredictionSettlementService()
        pe1 = _make_pending(prediction_id="multi-001", match_id=100, direction="OVER", odds=2.0)
        pe2 = _make_pending(prediction_id="multi-002", match_id=100, direction="UNDER", odds=1.85)
        service.register_prediction(pe1)
        service.register_prediction(pe2)

        # 3 goals: OVER wins, UNDER loses
        result = service.settle_match(MatchResult(match_id=100, home_goals=2, away_goals=1))

        assert len(result.settlements) == 2
        outcomes = {s.prediction_id: s for s in result.settlements}
        assert outcomes["multi-001"].outcome == SettlementOutcome.WIN
        assert outcomes["multi-001"].profit_loss == 1.0
        assert outcomes["multi-002"].outcome == SettlementOutcome.LOSS
        assert outcomes["multi-002"].profit_loss == -1.0


class TestCallbackSafety:
    """Callbacks fire exactly once per settlement and cannot double-apply."""

    def test_callback_fires_once_per_prediction(self):
        """Each new settlement fires callback exactly once."""
        service = PredictionSettlementService()
        fired = []

        def track_callback(pred, settlement):
            fired.append((pred.prediction_id, settlement.outcome.value))

        service.on_settlement(track_callback)

        pe1 = _make_pending(prediction_id="cb-001", match_id=100, direction="OVER")
        pe2 = _make_pending(prediction_id="cb-002", match_id=100, direction="UNDER")
        service.register_prediction(pe1)
        service.register_prediction(pe2)

        service.settle_match(MatchResult(match_id=100, home_goals=2, away_goals=1))

        assert len(fired) == 2
        assert ("cb-001", "WIN") in fired
        assert ("cb-002", "LOSS") in fired

    def test_callback_not_refired_on_retry(self):
        """Retried settlement does NOT re-invoke callbacks."""
        service = PredictionSettlementService()
        pnl_deltas = []

        def pnl_callback(pred, settlement):
            pnl_deltas.append(settlement.profit_loss)

        service.on_settlement(pnl_callback)

        pe = _make_pending(prediction_id="retry-cb-001", match_id=100, odds=2.0, direction="OVER")
        service.register_prediction(pe)

        # First settlement → callback fires with +1.0
        service.settle_match(MatchResult(match_id=100, home_goals=2, away_goals=1))
        assert pnl_deltas == [1.0]

        # Retry → callback does NOT fire again
        service._pending.setdefault(100, []).append(pe)
        service.settle_match(MatchResult(match_id=100, home_goals=2, away_goals=1))
        assert pnl_deltas == [1.0]  # Still only one entry

    def test_callback_error_does_not_prevent_other_callbacks(self):
        """A failing callback doesn't block other callbacks."""
        service = PredictionSettlementService()
        results = []

        def failing_callback(pred, settlement):
            raise RuntimeError("Intentional failure")

        def working_callback(pred, settlement):
            results.append(settlement.outcome.value)

        service.on_settlement(failing_callback)
        service.on_settlement(working_callback)

        pe = _make_pending(prediction_id="err-cb-001", match_id=100, direction="OVER")
        service.register_prediction(pe)

        # Should not raise — error is logged
        result = service.settle_match(MatchResult(match_id=100, home_goals=2, away_goals=1))

        assert len(result.settlements) == 1
        assert results == ["WIN"]  # Second callback still fired


class TestQuarantineBridgeIdempotency:
    """QuarantineSettlementBridge does not double-apply P&L."""

    def test_bridge_applies_pnl_once(self):
        """Paper trade P&L is applied exactly once to quarantine."""
        tracker = QuarantineTracker()
        service = PredictionSettlementService()
        bridge = QuarantineSettlementBridge(tracker)
        bridge.attach(service)

        strategy_id = "bridge-strat"
        tracker.enter_quarantine(strategy_id, datetime(2024, 1, 1, tzinfo=timezone.utc))

        pe = _make_pending(
            prediction_id="bridge-001", match_id=100, direction="OVER",
            source=PredictionSource.PAPER_TRADE, strategy_id=strategy_id,
        )
        service.register_prediction(pe)

        # First settlement
        service.settle_match(MatchResult(match_id=100, home_goals=2, away_goals=1))
        assert tracker.entries[strategy_id].paper_pnl == 1.0
        assert tracker.entries[strategy_id].paper_bets == 1

        # Retry — bridge callback NOT refired (idempotency from service)
        service._pending.setdefault(100, []).append(pe)
        service.settle_match(MatchResult(match_id=100, home_goals=2, away_goals=1))

        # P&L is still 1.0, not 2.0
        assert tracker.entries[strategy_id].paper_pnl == 1.0
        assert tracker.entries[strategy_id].paper_bets == 1

    def test_bridge_pnl_matches_settlement(self):
        """Paper P&L routed to quarantine matches the settlement amount."""
        tracker = QuarantineTracker()
        service = PredictionSettlementService()
        bridge = QuarantineSettlementBridge(tracker)
        bridge.attach(service)

        strategy_id = "exact-pnl-strat"
        tracker.enter_quarantine(strategy_id, datetime(2024, 1, 1, tzinfo=timezone.utc))

        pe = _make_pending(
            prediction_id="exact-001", match_id=100, direction="OVER", odds=2.5,
            source=PredictionSource.PAPER_TRADE, strategy_id=strategy_id,
        )
        service.register_prediction(pe)

        service.settle_match(MatchResult(match_id=100, home_goals=2, away_goals=1))

        # P&L = stake * (odds - 1) = 1.0 * (2.5 - 1) = 1.5
        settlement = service.get_settlement("exact-001")
        assert settlement.profit_loss == 1.5
        assert tracker.entries[strategy_id].paper_pnl == 1.5

    def test_reconstructable_from_settlements(self):
        """Paper P&L can be reconstructed by summing settlements."""
        tracker = QuarantineTracker()
        service = PredictionSettlementService()
        bridge = QuarantineSettlementBridge(tracker)
        bridge.attach(service)

        strategy_id = "reconstruct-strat"
        tracker.enter_quarantine(strategy_id, datetime(2024, 1, 1, tzinfo=timezone.utc))

        # Settle multiple predictions
        for i, (goals, direction) in enumerate([(3, "OVER"), (1, "OVER"), (4, "OVER")]):
            pe = _make_pending(
                prediction_id=f"recon-{i}", match_id=100 + i, direction=direction,
                source=PredictionSource.PAPER_TRADE, strategy_id=strategy_id, odds=2.0,
            )
            service.register_prediction(pe)
            h_goals = goals - 1 if goals > 0 else 0
            a_goals = 1 if goals > 0 else 0
            service.settle_match(MatchResult(match_id=100 + i, home_goals=h_goals, away_goals=a_goals))

        # Reconstruct P&L from settlements
        strategy_settlements = service.get_settlements_by_strategy(strategy_id)
        reconstructed_pnl = sum(s.profit_loss for s in strategy_settlements)

        # Matches quarantine tracker
        assert tracker.entries[strategy_id].paper_pnl == pytest.approx(reconstructed_pnl)
        assert tracker.entries[strategy_id].paper_bets == len(strategy_settlements)
