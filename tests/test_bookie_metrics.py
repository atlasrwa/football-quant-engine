"""Unit tests for Beat the Bookie metric calculations."""

from __future__ import annotations

import pytest

from src.engine.analysis.backtest import XBetRecord
from src.engine.analysis.friction import MarketFrictionConfig
from src.engine.market.metrics.bookie import BookieMetrics, BookieMetricsCalculator


class TestBookieMetricsCalculator:
    """Tests for BookieMetricsCalculator."""

    def _make_bet(
        self, odds: float = 2.0, profit_loss: float = 1.0, outcome: str = "WIN"
    ) -> XBetRecord:
        """Factory for a bet record."""
        return XBetRecord(
            match_index=0,
            strategy_name="Test",
            direction="OVER",
            odds=odds,
            stake=1.0,
            outcome=outcome,
            profit_loss=profit_loss,
            model_edge_pct=5.0,
            clv=None,
        )

    # ------------------------------------------------------------------
    # BTBR
    # ------------------------------------------------------------------

    def test_btbr_all_beating(self):
        """100% BTBR when all entry odds > closing odds."""
        calc = BookieMetricsCalculator()
        entry = [2.10, 1.95, 2.30]
        closing = [1.90, 1.85, 2.10]

        btbr = calc.compute_btbr(entry, closing)
        assert btbr == pytest.approx(100.0)

    def test_btbr_none_beating(self):
        """0% BTBR when no entry odds > closing odds."""
        calc = BookieMetricsCalculator()
        entry = [1.80, 1.85, 1.90]
        closing = [1.90, 1.95, 2.00]

        btbr = calc.compute_btbr(entry, closing)
        assert btbr == pytest.approx(0.0)

    def test_btbr_partial(self):
        """Partial BTBR calculation."""
        calc = BookieMetricsCalculator()
        entry = [2.10, 1.80, 2.30, 1.70]
        closing = [1.90, 1.85, 2.10, 1.75]

        # 2.10>1.90 ✓, 1.80<1.85 ✗, 2.30>2.10 ✓, 1.70<1.75 ✗ → 50%
        btbr = calc.compute_btbr(entry, closing)
        assert btbr == pytest.approx(50.0)

    def test_btbr_empty(self):
        """Empty lists return 0%."""
        calc = BookieMetricsCalculator()
        assert calc.compute_btbr([], []) == 0.0

    def test_btbr_equal_odds(self):
        """Equal odds do not count as beating."""
        calc = BookieMetricsCalculator()
        entry = [2.00, 2.00]
        closing = [2.00, 2.00]

        btbr = calc.compute_btbr(entry, closing)
        assert btbr == pytest.approx(0.0)

    # ------------------------------------------------------------------
    # Vig-Adjusted Edge
    # ------------------------------------------------------------------

    def test_vig_adjusted_edge_match_odds(self):
        """Match odds: edge = ROI - 3%."""
        calc = BookieMetricsCalculator()
        edge = calc.compute_vig_adjusted_edge(10.0, "match_odds")
        assert edge == pytest.approx(7.0)  # 10% - 3%

    def test_vig_adjusted_edge_corners(self):
        """Corners market: edge = ROI - 6%."""
        calc = BookieMetricsCalculator()
        edge = calc.compute_vig_adjusted_edge(10.0, "corners_over_under")
        assert edge == pytest.approx(4.0)  # 10% - 6%

    def test_vig_adjusted_edge_negative(self):
        """Negative edge when ROI < margin."""
        calc = BookieMetricsCalculator()
        edge = calc.compute_vig_adjusted_edge(2.0, "corners_over_under")
        assert edge == pytest.approx(-4.0)  # 2% - 6%

    def test_vig_adjusted_edge_custom_friction(self):
        """Custom friction config affects edge calculation."""
        friction = MarketFrictionConfig(margin_corners=0.10)
        calc = BookieMetricsCalculator(friction_config=friction)

        edge = calc.compute_vig_adjusted_edge(15.0, "corners")
        assert edge == pytest.approx(5.0)  # 15% - 10%

    # ------------------------------------------------------------------
    # Confidence Index
    # ------------------------------------------------------------------

    def test_confidence_index_perfect(self):
        """p=0 gives confidence=100."""
        calc = BookieMetricsCalculator()
        assert calc.compute_confidence_index(0.0) == pytest.approx(100.0)

    def test_confidence_index_zero(self):
        """p=1 gives confidence=0."""
        calc = BookieMetricsCalculator()
        assert calc.compute_confidence_index(1.0) == pytest.approx(0.0)

    def test_confidence_index_standard(self):
        """p=0.05 gives confidence=95."""
        calc = BookieMetricsCalculator()
        assert calc.compute_confidence_index(0.05) == pytest.approx(95.0)

    def test_confidence_index_clamped(self):
        """Confidence clamped to [0, 100]."""
        calc = BookieMetricsCalculator()
        assert calc.compute_confidence_index(-0.1) == 100.0  # clamped
        assert calc.compute_confidence_index(1.5) == 0.0  # clamped

    # ------------------------------------------------------------------
    # Full compute()
    # ------------------------------------------------------------------

    def test_compute_empty_records(self):
        """Empty records return zero metrics."""
        calc = BookieMetricsCalculator()
        metrics = calc.compute([], closing_odds=[])
        assert metrics.btbr_pct == 0.0
        assert metrics.total_signals == 0

    def test_compute_with_closing_odds(self):
        """Full computation with closing odds."""
        calc = BookieMetricsCalculator()
        bets = [
            self._make_bet(odds=2.10, profit_loss=1.10, outcome="WIN"),
            self._make_bet(odds=1.90, profit_loss=-1.0, outcome="LOSS"),
            self._make_bet(odds=2.20, profit_loss=1.20, outcome="WIN"),
        ]
        closing = [1.95, 1.95, 2.00]

        metrics = calc.compute(bets, closing_odds=closing, fdr_p_value=0.02)

        # BTBR: 2.10>1.95 ✓, 1.90<1.95 ✗, 2.20>2.00 ✓ → 66.67%
        assert metrics.btbr_pct == pytest.approx(66.67, rel=0.01)
        assert metrics.signals_beating_close == 2
        assert metrics.total_signals == 3
        # Confidence: 100*(1-0.02) = 98
        assert metrics.confidence_index == pytest.approx(98.0)

    def test_compute_without_closing_odds(self):
        """Without closing odds, BTBR is 0%."""
        calc = BookieMetricsCalculator()
        bets = [self._make_bet(odds=2.0, profit_loss=1.0)]

        metrics = calc.compute(bets, closing_odds=None, fdr_p_value=0.03)

        assert metrics.btbr_pct == 0.0
        assert metrics.signals_beating_close == 0
        assert metrics.confidence_index == pytest.approx(97.0)

    def test_compute_void_bets_excluded_from_roi(self):
        """VOID bets don't affect ROI calculation."""
        calc = BookieMetricsCalculator()
        bets = [
            self._make_bet(odds=2.0, profit_loss=1.0, outcome="WIN"),
            self._make_bet(odds=2.0, profit_loss=0.0, outcome="VOID"),
        ]

        metrics = calc.compute(bets, fdr_p_value=0.01, market="match_odds")

        # ROI from settled: 1.0/1.0 * 100 = 100%
        # Vig-adjusted: 100 - 3 = 97%
        assert metrics.raw_edge_pct == pytest.approx(100.0)
        assert metrics.vig_adjusted_edge_pct == pytest.approx(97.0)

    def test_metrics_summary(self):
        """BookieMetrics.summary() returns serializable dict."""
        metrics = BookieMetrics(
            btbr_pct=65.5,
            vig_adjusted_edge_pct=4.2,
            confidence_index=95.0,
            total_signals=100,
            signals_beating_close=65,
            raw_edge_pct=10.2,
        )

        summary = metrics.summary()
        assert isinstance(summary, dict)
        assert summary["btbr_pct"] == 65.5
        assert summary["confidence_index"] == 95.0
