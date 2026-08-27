"""Tests for security and trust boundaries.

These tests verify that sensitive fields are generated server-side
and cannot be forged by arbitrary caller input. When user-facing APIs
are introduced in Phase 3+, these invariants must hold.

Trust boundaries tested:
1. fdr_validated — must come from authoritative validation, not client
2. closing_odds — must come from MatchResult, not prediction creator
3. proof_hash — must be computed by factory, not caller-provided
4. settlement — must be computed by SettlementFactory, not caller
5. Backtest vs Live semantics cannot be confused
6. No synthetic data fabrication
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from src.domain.factories import PredictionEventFactory, SettlementFactory
from src.domain.prediction import PredictionEvent, PredictionSource, PredictionStatus
from src.domain.settlement import Settlement, SettlementOutcome
from src.engine.backtest import StrategyIdentityInfo
from src.engine.evaluator import Signal
from src.engine.metrics.bookie import BookieMetrics
from src.engine.settlement_service import MatchResult, PredictionSettlementService
from src.engine.signals.community_broadcaster import (
    BroadcastConfig,
    CommunityBroadcaster,
)
from src.engine.signals.crypto_exporter import CryptoSignalExporter

# Fixed clock outside the default quiet-hours window (1am-6am UTC) so these
# tests don't flake depending on the real wall-clock hour they run at.
_NOON_UTC_CLOCK = lambda: datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc)


def _make_metrics() -> BookieMetrics:
    return BookieMetrics(
        btbr_pct=55.0, vig_adjusted_edge_pct=4.5, confidence_index=85.0,
        total_signals=100, signals_beating_close=55, raw_edge_pct=6.0,
    )


class TestValidationCannotBeForged:
    """fdr_validated must come from authoritative source, never client."""

    @pytest.mark.asyncio
    async def test_broadcaster_validation_from_parameter_not_hardcoded(self):
        """Broadcaster uses validation_passed parameter, never hardcodes True."""
        config = BroadcastConfig(dry_run=True)
        broadcaster = CommunityBroadcaster(config=config, clock=_NOON_UTC_CLOCK)
        signal = Signal(match_index=0, strategy_name="s1", direction="OVER", edge=0.1, odds=2.0)
        match_data = [{"home_team": "A", "away_team": "B"}]

        # Without explicit validation_passed → defaults to False
        result = await broadcaster.run_once([signal], match_data, _make_metrics())
        assert result[0].fdr_validated is False

    @pytest.mark.asyncio
    async def test_broadcaster_validation_true_only_when_explicitly_passed(self):
        """Only validation_passed=True produces fdr_validated=True."""
        config = BroadcastConfig(dry_run=True)
        broadcaster = CommunityBroadcaster(config=config, clock=_NOON_UTC_CLOCK)
        signal = Signal(match_index=0, strategy_name="s1", direction="OVER", edge=0.1, odds=2.0)
        match_data = [{"home_team": "A", "away_team": "B"}]

        result = await broadcaster.run_once(
            [signal], match_data, _make_metrics(), validation_passed=True
        )
        assert result[0].fdr_validated is True

    @pytest.mark.asyncio
    async def test_exporter_validation_from_verdict_not_hardcoded(self):
        """CryptoSignalExporter derives fdr_validated from verdict, not client."""
        exporter = CryptoSignalExporter(dry_run=True)
        signal = Signal(match_index=0, strategy_name="s1", direction="OVER", edge=0.1, odds=2.0)

        # No verdict → not validated
        result = await exporter.dispatch(
            signal, {"home_team": "A", "away_team": "B"}, _make_metrics(), verdict=None
        )
        assert result.fdr_validated is False


class TestClosingOddsCannotBeForged:
    """Closing odds come from MatchResult at settlement time, not prediction."""

    def test_closing_odds_from_match_result_only(self):
        """CLV uses closing_odds from MatchResult, not from prediction creator."""
        service = PredictionSettlementService()
        pe = PredictionEvent(
            prediction_id="clv-test-001",
            strategy_id="s1", strategy_version=1, strategy_content_hash="a" * 64,
            model_version_id=None, match_id=100, match_date_unix=1700000000,
            home_team="A", away_team="B", league_id=4759,
            market_type="OVER_UNDER", market_line=2.5, direction="OVER",
            entry_odds=2.0, model_edge_pct=10.0, confidence=80.0,
            recommended_stake=0.05, source=PredictionSource.LIVE_SIGNAL,
            status=PredictionStatus.PENDING, proof_hash="f" * 64,
            created_at="2024-01-01T00:00:00+00:00", settled_at=None,
        )
        service.register_prediction(pe)

        # Closing odds come from MatchResult, not prediction
        result = service.settle_match(MatchResult(
            match_id=100, home_goals=2, away_goals=1, closing_odds_over=1.85
        ))

        # CLV computed from authoritative closing odds
        assert result.settlements[0].closing_odds == 1.85
        assert result.settlements[0].clv_pct is not None
        assert result.settlements[0].clv_pct == pytest.approx((2.0 / 1.85 - 1) * 100, abs=0.01)

    def test_no_closing_odds_means_no_clv(self):
        """Missing closing odds → CLV is None, not fabricated."""
        service = PredictionSettlementService()
        pe = PredictionEvent(
            prediction_id="no-clv-001",
            strategy_id="s1", strategy_version=1, strategy_content_hash="a" * 64,
            model_version_id=None, match_id=200, match_date_unix=1700000000,
            home_team="A", away_team="B", league_id=4759,
            market_type="OVER_UNDER", market_line=2.5, direction="OVER",
            entry_odds=2.0, model_edge_pct=10.0, confidence=80.0,
            recommended_stake=0.05, source=PredictionSource.LIVE_SIGNAL,
            status=PredictionStatus.PENDING, proof_hash="f" * 64,
            created_at="2024-01-01T00:00:00+00:00", settled_at=None,
        )
        service.register_prediction(pe)

        # No closing odds in MatchResult
        result = service.settle_match(MatchResult(match_id=200, home_goals=2, away_goals=1))

        assert result.settlements[0].closing_odds is None
        assert result.settlements[0].clv_pct is None


class TestProofHashCannotBeForged:
    """Proof hash is computed by factory, not caller-provided."""

    def test_factory_computes_proof_hash(self):
        """PredictionEventFactory.from_signal() computes proof_hash internally."""
        signal = Signal(match_index=0, strategy_name="s1", direction="OVER", edge=0.1, odds=2.0)
        pe = PredictionEventFactory.from_signal(
            signal=signal, strategy_id="strat-1", strategy_version=1,
            strategy_content_hash="a" * 64, match_id=100,
            match_date_unix=1700000000, home_team="A", away_team="B",
            league_id=4759,
        )

        # Proof hash is 64 char hex (SHA-256), computed internally
        assert len(pe.proof_hash) == 64
        assert all(c in "0123456789abcdef" for c in pe.proof_hash)

    def test_proof_hash_not_controllable_by_caller(self):
        """Factory does not accept proof_hash as parameter — it's always computed."""
        signal = Signal(match_index=0, strategy_name="s1", direction="OVER", edge=0.1, odds=2.0)

        # from_signal has no proof_hash parameter — it's computed internally
        import inspect
        sig = inspect.signature(PredictionEventFactory.from_signal)
        assert "proof_hash" not in sig.parameters

    def test_backtest_factory_computes_proof_hash(self):
        """from_backtest_bet() also computes proof_hash internally."""
        import inspect
        sig = inspect.signature(PredictionEventFactory.from_backtest_bet)
        assert "proof_hash" not in sig.parameters

        pe = PredictionEventFactory.from_backtest_bet(
            strategy_id="s1", strategy_version=1,
            strategy_content_hash="b" * 64, match_id=200,
            match_date_unix=1700000000, home_team="X", away_team="Y",
            league_id=4759, direction="UNDER", odds=1.9,
            model_edge_pct=12.0, outcome="WIN",
        )
        assert len(pe.proof_hash) == 64


class TestSettlementCannotBeForged:
    """Settlement outcome is computed from match data, not caller-provided."""

    def test_outcome_computed_from_actual_goals(self):
        """SettlementFactory resolves outcome from actual data, not caller input."""
        pe = PredictionEvent(
            prediction_id="forge-test-001",
            strategy_id="s1", strategy_version=1, strategy_content_hash="a" * 64,
            model_version_id=None, match_id=100, match_date_unix=1700000000,
            home_team="A", away_team="B", league_id=4759,
            market_type="OVER_UNDER", market_line=2.5, direction="OVER",
            entry_odds=2.0, model_edge_pct=10.0, confidence=80.0,
            recommended_stake=0.05, source=PredictionSource.LIVE_SIGNAL,
            status=PredictionStatus.PENDING, proof_hash="f" * 64,
            created_at="2024-01-01T00:00:00+00:00", settled_at=None,
        )

        # OVER 2.5, 1 goal → LOSS (cannot be forged as WIN)
        settlement = SettlementFactory.settle_prediction(
            prediction=pe, actual_total_goals=1,
            actual_home_goals=0, actual_away_goals=1,
        )
        assert settlement.outcome == SettlementOutcome.LOSS

    def test_settle_prediction_has_no_outcome_parameter(self):
        """SettlementFactory.settle_prediction() does not accept outcome as input."""
        import inspect
        sig = inspect.signature(SettlementFactory.settle_prediction)
        # Outcome is NOT a parameter — it's computed from actual_total_goals + direction
        assert "outcome" not in sig.parameters

    def test_pnl_computed_not_provided(self):
        """P&L is computed from outcome + odds + stake, not caller-provided."""
        import inspect
        sig = inspect.signature(SettlementFactory.settle_prediction)
        assert "profit_loss" not in sig.parameters


class TestBacktestLiveSeparation:
    """Backtest and live predictions have distinct semantics that cannot be confused."""

    def test_backtest_predictions_cannot_be_registered_for_settlement(self):
        """Backtest predictions are born SETTLED — cannot enter settlement service."""
        service = PredictionSettlementService()
        pe = PredictionEventFactory.from_backtest_bet(
            strategy_id="s1", strategy_version=1,
            strategy_content_hash="a" * 64, match_id=100,
            match_date_unix=1700000000, home_team="A", away_team="B",
            league_id=4759, direction="OVER", odds=2.0,
            model_edge_pct=15.0, outcome="WIN",
        )

        # Cannot register — already settled
        with pytest.raises(ValueError, match="non-PENDING"):
            service.register_prediction(pe)

    def test_live_prediction_source_is_live_signal(self):
        """Live predictions have LIVE_SIGNAL source."""
        signal = Signal(match_index=0, strategy_name="s1", direction="OVER", edge=0.1, odds=2.0)
        pe = PredictionEventFactory.from_signal(
            signal=signal, strategy_id="s1", strategy_version=1,
            strategy_content_hash="a" * 64, match_id=100,
            match_date_unix=1700000000, home_team="A", away_team="B",
            league_id=4759,
        )
        assert pe.source == PredictionSource.LIVE_SIGNAL

    def test_backtest_prediction_source_is_backtest(self):
        """Backtest predictions have BACKTEST source."""
        pe = PredictionEventFactory.from_backtest_bet(
            strategy_id="s1", strategy_version=1,
            strategy_content_hash="a" * 64, match_id=100,
            match_date_unix=1700000000, home_team="A", away_team="B",
            league_id=4759, direction="OVER", odds=2.0,
            model_edge_pct=15.0, outcome="LOSS",
        )
        assert pe.source == PredictionSource.BACKTEST

    def test_sources_are_distinct_enum_values(self):
        """All three sources are distinct enum members."""
        assert PredictionSource.BACKTEST != PredictionSource.LIVE_SIGNAL
        assert PredictionSource.LIVE_SIGNAL != PredictionSource.PAPER_TRADE
        assert PredictionSource.BACKTEST != PredictionSource.PAPER_TRADE


class TestNoSyntheticDataFabrication:
    """System never fabricates data — missing info is None/unavailable."""

    def test_missing_odds_produces_none_not_synthetic(self):
        """None entry_odds are preserved, not replaced with synthetic value."""
        pe = PredictionEventFactory.from_backtest_bet(
            strategy_id="s1", strategy_version=1,
            strategy_content_hash="a" * 64, match_id=100,
            match_date_unix=1700000000, home_team="A", away_team="B",
            league_id=4759, direction="OVER", odds=None,  # Missing!
            model_edge_pct=15.0, outcome="WIN",
        )
        assert pe.entry_odds is None

    def test_missing_closing_odds_produces_none_clv(self):
        """Missing closing odds → CLV is None, not fabricated."""
        clv = Settlement.compute_clv(entry_odds=2.0, closing_odds=None)
        assert clv is None

    def test_invalid_closing_odds_produces_none_clv(self):
        """Invalid closing odds (<=1.0) → CLV is None."""
        clv = Settlement.compute_clv(entry_odds=2.0, closing_odds=1.0)
        assert clv is None

    def test_settlement_pnl_zero_when_odds_missing(self):
        """WIN with None odds → P&L is 0 (cannot compute), not fabricated."""
        pnl = Settlement.compute_profit_loss(
            outcome=SettlementOutcome.WIN, odds=None, stake=1.0
        )
        assert pnl == 0.0
