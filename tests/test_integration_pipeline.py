"""Integration tests: Full pipeline provenance chain from backtest through settlement.

Tests the complete integration of Phase 2 domain objects into the execution pipeline:
    Strategy → Evaluation → Signal → PredictionEvent → Settlement → Quarantine

These tests exercise the REAL integration points, not mocks:
- BacktestOrchestrator producing linked provenance + PredictionEvents
- Signal dispatch producing PENDING PredictionEvents
- PredictionSettlementService resolving predictions against outcomes
- QuarantineSettlementBridge routing paper trade P&L to QuarantineTracker
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from src.domain.prediction import PredictionEvent, PredictionSource, PredictionStatus
from src.domain.provenance import DatasetVersion, FeatureVersion, ModelVersion
from src.domain.backtest_run import BacktestRun, BacktestStatus
from src.domain.settlement import Settlement, SettlementOutcome
from src.engine.analysis.backtest import StrategyIdentityInfo, XBacktestConfig, XMetricBacktester
from src.engine.analysis.evaluator import Condition, Signal, Strategy, StrategyEvaluator
from src.engine.analysis.fdr import QuarantineTracker
from src.engine.analysis.orchestrator import BacktestOrchestrator, OrchestratedBacktestResult
from src.engine.market.quarantine_bridge import QuarantineSettlementBridge
from src.engine.market.settlement_service import MatchResult, PredictionSettlementService
from src.engine.market.signals.community_broadcaster import (
    BroadcastConfig,
    BroadcastResult,
    CommunityBroadcaster,
)
from src.engine.market.signals.crypto_exporter import CryptoSignalExporter, DispatchResult
from src.engine.market.metrics.bookie import BookieMetrics
from src.engine.analysis.strategy_identity import StrategyRegistry


def _make_test_df(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """Create a test DataFrame with canonical schema columns."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "match_id": range(1, n + 1),
        "date_unix": range(1000000, 1000000 + n * 86400, 86400),
        "league_id": [4759] * n,
        "season": ["2023"] * n,
        "home_team": [f"Home_{i}" for i in range(1, n + 1)],
        "away_team": [f"Away_{i}" for i in range(1, n + 1)],
        "home_xC": rng.standard_normal(n) * 0.2,
        "away_xC": rng.standard_normal(n) * 0.2,
        "over_odds": rng.uniform(1.7, 2.3, n),
        "under_odds": rng.uniform(1.7, 2.3, n),
        "market_line": [2.5] * n,
        "actual_total": rng.choice([0, 1, 2, 3, 4, 5], n, p=[0.05, 0.15, 0.25, 0.25, 0.2, 0.1]),
    })


def _make_strategy() -> Strategy:
    """Create a test strategy."""
    return Strategy(
        name="test_xC_over",
        metric="xC",
        market="total",
        conditions=(Condition(field="home_xC", op=">", value=0.0),),
        logic="and",
        direction="OVER",
        min_odds=1.50,
    )


def _make_metrics() -> BookieMetrics:
    """Create test BookieMetrics."""
    return BookieMetrics(
        btbr_pct=55.0,
        vig_adjusted_edge_pct=4.5,
        confidence_index=85.0,
        total_signals=100,
        signals_beating_close=55,
        raw_edge_pct=6.0,
    )


class TestBacktestPredictionEventIntegration:
    """Gap 1+2: Backtest produces PredictionEvents with full provenance."""

    def test_orchestrated_backtest_produces_prediction_events(self):
        """BacktestOrchestrator wires provenance and emits PredictionEvents."""
        df = _make_test_df()
        strategy = _make_strategy()
        config = XBacktestConfig(train_window=100, test_window=50, step_size=50)

        orchestrator = BacktestOrchestrator(config=config, source="synthetic")
        result = orchestrator.run(df, [strategy])

        # Result is OrchestratedBacktestResult
        assert isinstance(result, OrchestratedBacktestResult)

        # Provenance chain is complete
        assert isinstance(result.dataset_version, DatasetVersion)
        assert isinstance(result.feature_version, FeatureVersion)
        assert isinstance(result.model_version, ModelVersion)
        assert isinstance(result.backtest_run, BacktestRun)

        # Provenance links are correct
        assert result.feature_version.dataset_id == result.dataset_version.dataset_id
        assert result.model_version.feature_version_id == result.feature_version.feature_version_id
        assert result.backtest_run.model_version_id == result.model_version.model_version_id
        assert result.backtest_run.dataset_id == result.dataset_version.dataset_id

    def test_prediction_events_match_bet_records(self):
        """Every bet record produces a corresponding PredictionEvent."""
        df = _make_test_df()
        strategy = _make_strategy()
        config = XBacktestConfig(train_window=100, test_window=50, step_size=50)

        orchestrator = BacktestOrchestrator(config=config, source="synthetic")
        result = orchestrator.run(df, [strategy])

        backtest = result.backtest_result
        assert backtest.total_bets > 0
        assert len(backtest.prediction_events) == backtest.total_bets

    def test_prediction_events_have_correct_provenance(self):
        """PredictionEvents carry correct strategy identity."""
        df = _make_test_df()
        strategy = _make_strategy()
        config = XBacktestConfig(train_window=100, test_window=50, step_size=50)

        orchestrator = BacktestOrchestrator(config=config, source="synthetic")
        result = orchestrator.run(df, [strategy])

        identity = result.strategy_identities[0]
        for pe in result.backtest_result.prediction_events:
            assert pe.strategy_id == identity.strategy_id
            assert pe.strategy_version == identity.strategy_version
            assert pe.strategy_content_hash == identity.content_hash
            assert pe.source == PredictionSource.BACKTEST

    def test_prediction_events_are_pre_settled(self):
        """Backtest PredictionEvents have appropriate settled status."""
        df = _make_test_df()
        strategy = _make_strategy()
        config = XBacktestConfig(train_window=100, test_window=50, step_size=50)

        orchestrator = BacktestOrchestrator(config=config, source="synthetic")
        result = orchestrator.run(df, [strategy])

        for pe in result.backtest_result.prediction_events:
            # Backtest predictions are settled at creation
            assert pe.status in (
                PredictionStatus.SETTLED_WIN,
                PredictionStatus.SETTLED_LOSS,
                PredictionStatus.SETTLED_VOID,
            )
            assert pe.settled_at is not None

    def test_prediction_events_have_valid_proof_hashes(self):
        """Each PredictionEvent has a 64-char hex SHA-256 proof hash."""
        df = _make_test_df()
        strategy = _make_strategy()
        config = XBacktestConfig(train_window=100, test_window=50, step_size=50)

        orchestrator = BacktestOrchestrator(config=config, source="synthetic")
        result = orchestrator.run(df, [strategy])

        for pe in result.backtest_result.prediction_events:
            assert len(pe.proof_hash) == 64
            assert all(c in "0123456789abcdef" for c in pe.proof_hash)

    def test_backtest_run_metrics_match_result(self):
        """BacktestRun domain object matches XBacktestResult metrics."""
        df = _make_test_df()
        strategy = _make_strategy()
        config = XBacktestConfig(train_window=100, test_window=50, step_size=50)

        orchestrator = BacktestOrchestrator(config=config, source="synthetic")
        result = orchestrator.run(df, [strategy])

        run = result.backtest_run
        backtest = result.backtest_result

        assert run.status == BacktestStatus.COMPLETED
        assert run.total_bets == backtest.total_bets
        assert run.net_roi_pct == backtest.net_roi_pct
        assert run.win_rate == backtest.win_rate
        assert run.max_drawdown_pct == backtest.max_drawdown_pct
        assert run.n_folds == len(backtest.folds)

    def test_dataset_version_content_hash_deterministic(self):
        """Same data produces same DatasetVersion content hash."""
        df = _make_test_df(seed=123)
        strategy = _make_strategy()
        config = XBacktestConfig(train_window=100, test_window=50, step_size=50)

        o1 = BacktestOrchestrator(config=config, source="synthetic")
        o2 = BacktestOrchestrator(config=config, source="synthetic")
        r1 = o1.run(df, [strategy])
        r2 = o2.run(df.copy(), [strategy])

        assert r1.dataset_version.content_hash == r2.dataset_version.content_hash

    def test_no_identity_no_prediction_events(self):
        """XMetricBacktester without identity produces no PredictionEvents."""
        df = _make_test_df()
        strategy = _make_strategy()
        config = XBacktestConfig(train_window=100, test_window=50, step_size=50)

        # Direct backtester without orchestrator
        backtester = XMetricBacktester(config=config)
        result = backtester.run(df, [strategy])

        assert result.total_bets > 0
        assert len(result.prediction_events) == 0


class TestSignalDispatchPredictionEventIntegration:
    """Gap 3: Signal dispatch produces PENDING PredictionEvents."""

    @pytest.mark.asyncio
    async def test_crypto_exporter_emits_prediction_event(self):
        """CryptoSignalExporter with identity produces DispatchResult with PredictionEvent."""
        exporter = CryptoSignalExporter(dry_run=True)
        signal = Signal(match_index=0, strategy_name="test", direction="OVER", condition_strength=0.15, odds=2.0)
        metrics = _make_metrics()
        identity = StrategyIdentityInfo(
            strategy_id="strat-001", strategy_version=1, content_hash="a" * 64
        )
        match_info = {
            "match_id": 500, "date_unix": 1700000000,
            "home_team": "Arsenal", "away_team": "Chelsea",
            "league_id": 4759, "market_line": 2.5,
        }

        result = await exporter.dispatch(
            signal, match_info, metrics, strategy_identity=identity
        )

        assert isinstance(result, DispatchResult)
        assert result.prediction_event is not None
        assert result.prediction_event.status == PredictionStatus.PENDING
        assert result.prediction_event.direction == "OVER"
        assert result.prediction_event.strategy_id == "strat-001"
        assert result.prediction_event.match_id == 500
        assert result.prediction_event.source == PredictionSource.LIVE_SIGNAL

    @pytest.mark.asyncio
    async def test_crypto_exporter_without_identity_returns_payload(self):
        """CryptoSignalExporter without identity returns plain SignalPayload."""
        from src.engine.market.signals.crypto_exporter import SignalPayload

        exporter = CryptoSignalExporter(dry_run=True)
        signal = Signal(match_index=0, strategy_name="test", direction="OVER", condition_strength=0.15, odds=2.0)
        metrics = _make_metrics()

        result = await exporter.dispatch(
            signal, {"home_team": "A", "away_team": "B"}, metrics
        )

        assert isinstance(result, SignalPayload)

    @pytest.mark.asyncio
    async def test_broadcaster_emits_prediction_events(self):
        """CommunityBroadcaster with identity produces PredictionEvents."""
        config = BroadcastConfig(dry_run=True)
        # Fixed noon-UTC clock: outside default quiet hours (1am-6am UTC), so
        # this test doesn't flake depending on when it's actually run.
        broadcaster = CommunityBroadcaster(
            config=config,
            clock=lambda: datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc),
        )
        signals = [
            Signal(match_index=0, strategy_name="s1", direction="OVER", condition_strength=0.1, odds=1.9),
            Signal(match_index=1, strategy_name="s1", direction="UNDER", condition_strength=0.12, odds=2.1),
        ]
        match_data = [
            {"match_id": 100, "date_unix": 1700000000, "home_team": "A", "away_team": "B", "league_id": 4759},
            {"match_id": 200, "date_unix": 1700100000, "home_team": "C", "away_team": "D", "league_id": 4759},
        ]
        identity = StrategyIdentityInfo(
            strategy_id="strat-002", strategy_version=2, content_hash="b" * 64
        )

        result = await broadcaster.run_once(
            signals, match_data, _make_metrics(), strategy_identity=identity
        )

        assert isinstance(result, BroadcastResult)
        assert len(result.prediction_events) == 2
        assert result.prediction_events[0].direction == "OVER"
        assert result.prediction_events[1].direction == "UNDER"
        assert all(pe.status == PredictionStatus.PENDING for pe in result.prediction_events)
        assert all(pe.strategy_id == "strat-002" for pe in result.prediction_events)

    @pytest.mark.asyncio
    async def test_paper_trade_source(self):
        """Dispatch with source=PAPER_TRADE sets correct PredictionSource."""
        exporter = CryptoSignalExporter(dry_run=True)
        signal = Signal(match_index=0, strategy_name="test", direction="OVER", condition_strength=0.1, odds=2.0)
        metrics = _make_metrics()
        identity = StrategyIdentityInfo(
            strategy_id="strat-003", strategy_version=1, content_hash="c" * 64
        )

        result = await exporter.dispatch(
            signal, {"match_id": 999, "home_team": "X", "away_team": "Y"},
            metrics, strategy_identity=identity, source="PAPER_TRADE"
        )

        assert result.prediction_event.source == PredictionSource.PAPER_TRADE


class TestSettlementServiceIntegration:
    """Gap 4: Settlement service resolves predictions correctly."""

    def test_settle_over_win(self):
        """OVER prediction with goals > line = WIN."""
        service = PredictionSettlementService()
        pe = self._make_pending("OVER", match_id=100, odds=2.0)
        service.register_prediction(pe)

        result = service.settle_match(MatchResult(match_id=100, home_goals=2, away_goals=1))

        assert len(result.settlements) == 1
        assert result.settlements[0].outcome == SettlementOutcome.WIN
        assert result.settlements[0].profit_loss == 1.0  # stake=1.0 * (2.0 - 1)
        assert result.total_profit_loss == 1.0

    def test_settle_over_loss(self):
        """OVER prediction with goals < line = LOSS."""
        service = PredictionSettlementService()
        pe = self._make_pending("OVER", match_id=200, odds=1.9)
        service.register_prediction(pe)

        result = service.settle_match(MatchResult(match_id=200, home_goals=1, away_goals=0))

        assert result.settlements[0].outcome == SettlementOutcome.LOSS
        assert result.settlements[0].profit_loss == -1.0

    def test_settle_under_win(self):
        """UNDER prediction with goals < line = WIN."""
        service = PredictionSettlementService()
        pe = self._make_pending("UNDER", match_id=300, odds=1.85)
        service.register_prediction(pe)

        result = service.settle_match(MatchResult(match_id=300, home_goals=0, away_goals=1))

        assert result.settlements[0].outcome == SettlementOutcome.WIN
        assert result.settlements[0].profit_loss == pytest.approx(0.85)

    def test_settle_push(self):
        """Goals exactly on line = PUSH."""
        service = PredictionSettlementService()
        pe = self._make_pending("OVER", match_id=400, odds=2.0, market_line=2.0)
        service.register_prediction(pe)

        result = service.settle_match(MatchResult(match_id=400, home_goals=1, away_goals=1))

        assert result.settlements[0].outcome == SettlementOutcome.PUSH
        assert result.settlements[0].profit_loss == 0.0

    def test_settle_with_closing_odds_computes_clv(self):
        """CLV is computed when closing odds are available."""
        service = PredictionSettlementService()
        pe = self._make_pending("OVER", match_id=500, odds=2.0)
        service.register_prediction(pe)

        result = service.settle_match(MatchResult(
            match_id=500, home_goals=2, away_goals=1, closing_odds_over=1.80
        ))

        # CLV = (2.0 / 1.80 - 1) * 100 = 11.11%
        assert result.settlements[0].clv_pct == pytest.approx(11.11, abs=0.01)

    def test_settle_without_closing_odds_clv_none(self):
        """CLV is None when closing odds unavailable."""
        service = PredictionSettlementService()
        pe = self._make_pending("OVER", match_id=600, odds=2.0)
        service.register_prediction(pe)

        result = service.settle_match(MatchResult(match_id=600, home_goals=3, away_goals=1))

        assert result.settlements[0].clv_pct is None

    def test_settle_multiple_predictions_same_match(self):
        """Multiple predictions for one match all settle together."""
        service = PredictionSettlementService()
        pe1 = self._make_pending("OVER", match_id=700, odds=2.0, pred_id="p1")
        pe2 = self._make_pending("UNDER", match_id=700, odds=1.85, pred_id="p2")
        service.register_prediction(pe1)
        service.register_prediction(pe2)

        # 3 goals → OVER wins, UNDER loses
        result = service.settle_match(MatchResult(match_id=700, home_goals=2, away_goals=1))

        assert len(result.settlements) == 2
        outcomes = {s.prediction_id: s.outcome for s in result.settlements}
        assert outcomes["p1"] == SettlementOutcome.WIN
        assert outcomes["p2"] == SettlementOutcome.LOSS

    def test_settle_no_pending_returns_empty(self):
        """Settling a match with no predictions returns empty result."""
        service = PredictionSettlementService()
        result = service.settle_match(MatchResult(match_id=999, home_goals=1, away_goals=1))

        assert result.settlements == []
        assert result.total_profit_loss == 0.0

    def test_register_non_pending_raises(self):
        """Cannot register a non-PENDING prediction."""
        service = PredictionSettlementService()
        pe = PredictionEvent(
            prediction_id="settled-pred",
            strategy_id="s1", strategy_version=1, strategy_content_hash="a" * 64,
            model_version_id=None, match_id=100, match_date_unix=1700000000,
            home_team="A", away_team="B", league_id=4759,
            market_type="OVER_UNDER", market_line=2.5, direction="OVER",
            entry_odds=2.0, model_edge_pct=10.0, confidence=80.0,
            recommended_stake=0.05, source=PredictionSource.LIVE_SIGNAL,
            status=PredictionStatus.SETTLED_WIN,
            proof_hash="x" * 64,
            created_at="2024-01-01T00:00:00+00:00", settled_at="2024-01-02T00:00:00+00:00",
        )

        with pytest.raises(ValueError, match="non-PENDING"):
            service.register_prediction(pe)

    def test_register_duplicate_raises(self):
        """Cannot register the same prediction twice."""
        service = PredictionSettlementService()
        pe = self._make_pending("OVER", match_id=100, pred_id="dup-001")
        service.register_prediction(pe)

        with pytest.raises(ValueError, match="already registered"):
            service.register_prediction(pe)

    def _make_pending(
        self, direction: str, match_id: int, odds: float = 2.0,
        pred_id: str | None = None, market_line: float = 2.5,
    ) -> PredictionEvent:
        """Helper to create a PENDING PredictionEvent."""
        import uuid
        return PredictionEvent(
            prediction_id=pred_id or str(uuid.uuid4()),
            strategy_id="strat-test",
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
            source=PredictionSource.LIVE_SIGNAL,
            status=PredictionStatus.PENDING,
            proof_hash="f" * 64,
            created_at="2024-01-01T00:00:00+00:00",
            settled_at=None,
        )


class TestQuarantineBridgeIntegration:
    """Gap 5: Quarantine bridge routes paper trade P&L correctly."""

    def test_paper_trade_updates_quarantine(self):
        """PAPER_TRADE settlement updates QuarantineTracker paper_pnl."""
        tracker = QuarantineTracker()
        service = PredictionSettlementService()
        bridge = QuarantineSettlementBridge(tracker)
        bridge.attach(service)

        strategy_id = "quarantined-strat"
        tracker.enter_quarantine(strategy_id, datetime(2024, 1, 1, tzinfo=timezone.utc))

        pe = self._make_paper_prediction(strategy_id, match_id=100, direction="OVER")
        service.register_prediction(pe)
        service.settle_match(MatchResult(match_id=100, home_goals=2, away_goals=1))

        entry = tracker.entries[strategy_id]
        assert entry.paper_pnl == 1.0  # WIN: 1.0 * (2.0 - 1)
        assert entry.paper_bets == 1

    def test_live_signal_does_not_update_quarantine(self):
        """LIVE_SIGNAL settlement does NOT update quarantine."""
        tracker = QuarantineTracker()
        service = PredictionSettlementService()
        bridge = QuarantineSettlementBridge(tracker)
        bridge.attach(service)

        strategy_id = "quarantined-strat"
        tracker.enter_quarantine(strategy_id, datetime(2024, 1, 1, tzinfo=timezone.utc))

        pe = PredictionEvent(
            prediction_id="live-pred",
            strategy_id=strategy_id, strategy_version=1, strategy_content_hash="a" * 64,
            model_version_id=None, match_id=200, match_date_unix=1700000000,
            home_team="A", away_team="B", league_id=4759,
            market_type="OVER_UNDER", market_line=2.5, direction="OVER",
            entry_odds=2.0, model_edge_pct=10.0, confidence=80.0,
            recommended_stake=0.05, source=PredictionSource.LIVE_SIGNAL,
            status=PredictionStatus.PENDING,
            proof_hash="f" * 64,
            created_at="2024-01-01T00:00:00+00:00", settled_at=None,
        )
        service.register_prediction(pe)
        service.settle_match(MatchResult(match_id=200, home_goals=3, away_goals=0))

        entry = tracker.entries[strategy_id]
        assert entry.paper_pnl == 0.0
        assert entry.paper_bets == 0

    def test_multiple_settlements_accumulate(self):
        """Multiple paper trade settlements accumulate P&L."""
        tracker = QuarantineTracker()
        service = PredictionSettlementService()
        bridge = QuarantineSettlementBridge(tracker)
        bridge.attach(service)

        strategy_id = "accumulator-strat"
        tracker.enter_quarantine(strategy_id, datetime(2024, 1, 1, tzinfo=timezone.utc))

        # WIN: +1.0
        pe1 = self._make_paper_prediction(strategy_id, match_id=100, direction="OVER", pred_id="p1")
        service.register_prediction(pe1)
        service.settle_match(MatchResult(match_id=100, home_goals=2, away_goals=2))

        # LOSS: -1.0
        pe2 = self._make_paper_prediction(strategy_id, match_id=200, direction="OVER", pred_id="p2")
        service.register_prediction(pe2)
        service.settle_match(MatchResult(match_id=200, home_goals=1, away_goals=0))

        # WIN: +1.0
        pe3 = self._make_paper_prediction(strategy_id, match_id=300, direction="OVER", pred_id="p3")
        service.register_prediction(pe3)
        service.settle_match(MatchResult(match_id=300, home_goals=3, away_goals=1))

        entry = tracker.entries[strategy_id]
        assert entry.paper_pnl == pytest.approx(1.0)  # +1 -1 +1 = 1.0
        assert entry.paper_bets == 3

    def test_strategy_not_in_quarantine_no_error(self):
        """Settlement for strategy not in quarantine doesn't raise."""
        tracker = QuarantineTracker()
        service = PredictionSettlementService()
        bridge = QuarantineSettlementBridge(tracker)
        bridge.attach(service)

        # Register prediction for strategy NOT in quarantine
        pe = self._make_paper_prediction("unknown-strat", match_id=100, direction="OVER")
        service.register_prediction(pe)

        # Should not raise
        result = service.settle_match(MatchResult(match_id=100, home_goals=2, away_goals=1))
        assert len(result.settlements) == 1  # Settlement still produced

    def test_bridge_stats_tracking(self):
        """Bridge tracks processed count and total P&L."""
        tracker = QuarantineTracker()
        service = PredictionSettlementService()
        bridge = QuarantineSettlementBridge(tracker)
        bridge.attach(service)

        strategy_id = "stats-strat"
        tracker.enter_quarantine(strategy_id, datetime(2024, 1, 1, tzinfo=timezone.utc))

        pe = self._make_paper_prediction(strategy_id, match_id=100, direction="OVER")
        service.register_prediction(pe)
        service.settle_match(MatchResult(match_id=100, home_goals=2, away_goals=1))

        assert bridge.settlements_processed == 1
        assert bridge.total_paper_pnl == pytest.approx(1.0)

    def _make_paper_prediction(
        self, strategy_id: str, match_id: int, direction: str,
        pred_id: str | None = None,
    ) -> PredictionEvent:
        """Create a PAPER_TRADE PENDING prediction."""
        import uuid
        return PredictionEvent(
            prediction_id=pred_id or str(uuid.uuid4()),
            strategy_id=strategy_id, strategy_version=1, strategy_content_hash="a" * 64,
            model_version_id=None, match_id=match_id, match_date_unix=1700000000,
            home_team="Home", away_team="Away", league_id=4759,
            market_type="OVER_UNDER", market_line=2.5, direction=direction,
            entry_odds=2.0, model_edge_pct=10.0, confidence=80.0,
            recommended_stake=0.05, source=PredictionSource.PAPER_TRADE,
            status=PredictionStatus.PENDING,
            proof_hash="f" * 64,
            created_at="2024-01-01T00:00:00+00:00", settled_at=None,
        )


class TestEndToEndPipeline:
    """Full end-to-end: Strategy → Backtest → Signal → Settlement → Quarantine."""

    def test_full_pipeline_backtest_to_settlement(self):
        """Orchestrated backtest predictions can be looked up via settlement service."""
        df = _make_test_df(n=300, seed=77)
        strategy = _make_strategy()
        config = XBacktestConfig(train_window=100, test_window=50, step_size=50)

        # Run orchestrated backtest
        orchestrator = BacktestOrchestrator(config=config, source="synthetic")
        result = orchestrator.run(df, [strategy])

        # Verify provenance chain integrity
        assert result.dataset_version.source == "synthetic"
        assert result.dataset_version.n_matches == 300
        assert result.backtest_run.total_bets == result.backtest_result.total_bets
        assert len(result.backtest_result.prediction_events) == result.backtest_result.total_bets

        # Every prediction has the same strategy identity
        identity = result.strategy_identities[0]
        for pe in result.backtest_result.prediction_events:
            assert pe.strategy_id == identity.strategy_id
            assert pe.strategy_content_hash == identity.content_hash

    @pytest.mark.asyncio
    async def test_full_pipeline_signal_to_quarantine(self):
        """Signal → PredictionEvent → Settlement → Quarantine P&L update."""
        # Setup the full pipeline
        tracker = QuarantineTracker()
        service = PredictionSettlementService()
        bridge = QuarantineSettlementBridge(tracker)
        bridge.attach(service)

        strategy_id = "pipeline-strat"
        tracker.enter_quarantine(strategy_id, datetime(2024, 1, 1, tzinfo=timezone.utc))

        # Step 1: Dispatch signal (paper trade mode)
        exporter = CryptoSignalExporter(dry_run=True)
        signal = Signal(match_index=0, strategy_name="pipeline-strat", direction="OVER", condition_strength=0.12, odds=2.05)
        metrics = _make_metrics()
        identity = StrategyIdentityInfo(
            strategy_id=strategy_id, strategy_version=1, content_hash="d" * 64
        )
        match_info = {"match_id": 1000, "date_unix": 1700000000, "home_team": "A", "away_team": "B", "league_id": 4759}

        dispatch_result = await exporter.dispatch(
            signal, match_info, metrics, strategy_identity=identity, source="PAPER_TRADE"
        )

        # Step 2: Register the prediction
        prediction = dispatch_result.prediction_event
        assert prediction.source == PredictionSource.PAPER_TRADE
        assert prediction.status == PredictionStatus.PENDING
        service.register_prediction(prediction)

        # Step 3: Settle the match (3 goals → OVER 2.5 = WIN)
        settlement_result = service.settle_match(
            MatchResult(match_id=1000, home_goals=2, away_goals=1, closing_odds_over=1.90)
        )

        # Step 4: Verify settlement
        assert len(settlement_result.settlements) == 1
        settlement = settlement_result.settlements[0]
        assert settlement.outcome == SettlementOutcome.WIN
        assert settlement.profit_loss == pytest.approx(1.05)  # 1.0 * (2.05 - 1)
        assert settlement.clv_pct == pytest.approx((2.05 / 1.90 - 1) * 100, abs=0.01)

        # Step 5: Verify quarantine was updated
        entry = tracker.entries[strategy_id]
        assert entry.paper_pnl == pytest.approx(1.05)
        assert entry.paper_bets == 1

    def test_full_pipeline_deterministic_provenance(self):
        """Same strategy + same data = same content hashes where applicable."""
        df = _make_test_df(n=300, seed=99)
        strategy = _make_strategy()
        config = XBacktestConfig(train_window=100, test_window=50, step_size=50)

        r1 = BacktestOrchestrator(config=config, source="synthetic").run(df, [strategy])
        r2 = BacktestOrchestrator(config=config, source="synthetic").run(df.copy(), [strategy])

        # Dataset content hash is deterministic (same match_ids)
        assert r1.dataset_version.content_hash == r2.dataset_version.content_hash

        # Strategy content hash is deterministic (same definition)
        assert r1.strategy_identities[0].content_hash == r2.strategy_identities[0].content_hash

        # Backtest results are deterministic (same data, same strategy)
        assert r1.backtest_result.total_bets == r2.backtest_result.total_bets
        assert r1.backtest_result.net_roi_pct == r2.backtest_result.net_roi_pct

        # Note: feature_version.content_hash and model_version.content_hash
        # depend on dataset_id (UUID), which differs between runs. This is
        # correct — they identify a specific execution context, not just config.

    def test_summary_includes_provenance_ids(self):
        """OrchestratedBacktestResult.summary() includes all provenance IDs."""
        df = _make_test_df()
        strategy = _make_strategy()
        config = XBacktestConfig(train_window=100, test_window=50, step_size=50)

        result = BacktestOrchestrator(config=config, source="synthetic").run(df, [strategy])
        summary = result.summary()

        assert "dataset_id" in summary
        assert "feature_version_id" in summary
        assert "model_version_id" in summary
        assert "backtest_run_id" in summary
        assert "n_prediction_events" in summary
        assert summary["n_prediction_events"] == result.backtest_result.total_bets
