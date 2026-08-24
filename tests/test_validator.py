"""Unit tests for the statistical validator."""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from src.engine.backtest import XBetRecord
from src.engine.validator import (
    StatisticalValidator,
    ValidationCriteria,
    ValidationVerdict,
)


class TestStatisticalValidator:
    """Tests for StatisticalValidator."""

    def _make_bet(self, profit_loss: float, outcome: str = "WIN") -> XBetRecord:
        """Factory for a single bet record."""
        return XBetRecord(
            match_index=0,
            strategy_name="Test",
            direction="OVER",
            odds=2.0,
            stake=1.0,
            outcome=outcome,
            profit_loss=profit_loss,
            model_edge_pct=5.0,
            clv=None,
        )

    def _make_profitable_bets(self, n: int = 300) -> list[XBetRecord]:
        """Generate a profitable set of bets."""
        rng = np.random.default_rng(42)
        bets = []
        for _ in range(n):
            # ~60% win rate at odds 2.0 → clearly profitable
            if rng.random() < 0.60:
                bets.append(self._make_bet(1.0, "WIN"))
            else:
                bets.append(self._make_bet(-1.0, "LOSS"))
        return bets

    def _make_unprofitable_bets(self, n: int = 300) -> list[XBetRecord]:
        """Generate an unprofitable set of bets."""
        rng = np.random.default_rng(42)
        bets = []
        for _ in range(n):
            # ~45% win rate → unprofitable
            if rng.random() < 0.45:
                bets.append(self._make_bet(1.0, "WIN"))
            else:
                bets.append(self._make_bet(-1.0, "LOSS"))
        return bets

    def test_passing_verdict(self):
        """Profitable strategy with sufficient N passes validation."""
        validator = StatisticalValidator()
        bets = self._make_profitable_bets(300)

        verdict = validator.validate(bets)

        assert isinstance(verdict, ValidationVerdict)
        assert verdict.passed is True
        assert verdict.p_value <= 0.05
        assert verdict.roi_pct >= 3.0
        assert verdict.sample_size == 300
        assert "PROMOTED" in verdict.reason

    def test_failing_insufficient_sample(self):
        """Rejects strategy with N < min_sample_size."""
        validator = StatisticalValidator(
            criteria=ValidationCriteria(min_sample_size=250)
        )
        bets = self._make_profitable_bets(100)

        verdict = validator.validate(bets)

        assert verdict.passed is False
        assert "Insufficient sample size" in verdict.reason
        assert verdict.sample_size == 100

    def test_failing_low_roi(self):
        """Rejects strategy with ROI below threshold."""
        validator = StatisticalValidator(
            criteria=ValidationCriteria(min_roi_pct=3.0)
        )
        # Create bets with ~1% ROI (barely positive)
        bets = []
        for i in range(300):
            if i % 100 < 51:  # 51% win rate
                bets.append(self._make_bet(1.0, "WIN"))
            else:
                bets.append(self._make_bet(-1.0, "LOSS"))

        verdict = validator.validate(bets)

        # ROI = (3*51 - 3*49) / 300 * 100 = 2% — below 3%
        assert verdict.passed is False
        assert "ROI too low" in verdict.reason

    def test_failing_not_significant(self):
        """Rejects strategy that is not statistically significant."""
        validator = StatisticalValidator(
            criteria=ValidationCriteria(min_roi_pct=0.1)  # Lower ROI bar
        )
        # Barely profitable — large variance, small N → high p-value
        rng = np.random.default_rng(7)
        bets = []
        for _ in range(250):
            # ~50.5% win rate — negligible edge, won't be significant
            if rng.random() < 0.505:
                bets.append(self._make_bet(1.0, "WIN"))
            else:
                bets.append(self._make_bet(-1.0, "LOSS"))

        verdict = validator.validate(bets)
        # With such thin edge, p-value should be > 0.05
        assert verdict.passed is False
        assert "Not statistically significant" in verdict.reason or "ROI too low" in verdict.reason

    def test_void_bets_excluded(self):
        """VOID bets are excluded from validation sample."""
        validator = StatisticalValidator(
            criteria=ValidationCriteria(min_sample_size=5)
        )
        bets = [
            self._make_bet(0.0, "VOID"),
            self._make_bet(0.0, "VOID"),
            self._make_bet(1.0, "WIN"),
            self._make_bet(1.0, "WIN"),
            self._make_bet(1.0, "WIN"),
        ]

        verdict = validator.validate(bets)
        # Only 3 settled bets, below threshold of 5
        assert verdict.sample_size == 3
        assert verdict.passed is False

    def test_t_test_correctness(self):
        """t-test produces expected result for known distribution."""
        validator = StatisticalValidator()
        # All positive profits → very low p-value
        profits = np.array([0.5, 0.6, 0.4, 0.7, 0.3, 0.5, 0.6, 0.4, 0.5, 0.5])
        p_value, t_stat = validator._t_test(profits)

        assert t_stat > 0  # positive mean → positive t
        assert p_value < 0.01  # highly significant

    def test_t_test_negative_mean(self):
        """t-test with negative mean gives p > 0.5."""
        validator = StatisticalValidator()
        profits = np.array([-1.0, -1.0, -1.0, -1.0, -1.0])
        p_value, t_stat = validator._t_test(profits)

        assert t_stat < 0
        assert p_value > 0.5  # 1-tailed right: negative mean → p close to 1

    def test_t_test_single_element(self):
        """t-test with 1 element returns p=1.0."""
        validator = StatisticalValidator()
        profits = np.array([0.5])
        p_value, t_stat = validator._t_test(profits)

        assert p_value == 1.0

    def test_cohens_d_positive(self):
        """Cohen's d is positive for positive mean."""
        validator = StatisticalValidator()
        profits = np.array([1.0, 1.2, 0.8, 1.1, 0.9])
        d = validator._cohens_d(profits)

        assert d > 0
        # mean=1.0, std≈0.158 → d ≈ 6.3
        expected_d = float(np.mean(profits)) / float(np.std(profits, ddof=1))
        assert d == pytest.approx(expected_d, rel=1e-6)

    def test_cohens_d_zero_std(self):
        """Cohen's d returns 0 when std is 0."""
        validator = StatisticalValidator()
        profits = np.array([1.0, 1.0, 1.0])
        d = validator._cohens_d(profits)

        assert d == 0.0

    def test_confidence_interval(self):
        """Confidence interval contains the sample mean."""
        validator = StatisticalValidator()
        profits = np.array([0.5, 0.6, 0.4, 0.7, 0.3, 0.5, 0.6, 0.4, 0.5, 0.5])
        lower, upper = validator._confidence_interval(profits)

        mean = float(np.mean(profits))
        assert lower < mean < upper
        assert lower < upper

    def test_confidence_interval_known_values(self):
        """CI matches scipy's interval calculation."""
        validator = StatisticalValidator()
        profits = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        lower, upper = validator._confidence_interval(profits, alpha=0.05)

        # Manual: mean=3.0, std=sqrt(2.5)≈1.58, se=1.58/sqrt(5)≈0.707
        # t_crit(0.975, df=4)≈2.776
        mean = 3.0
        se = float(np.std(profits, ddof=1)) / np.sqrt(5)
        t_crit = stats.t.ppf(0.975, df=4)
        expected_lower = mean - t_crit * se
        expected_upper = mean + t_crit * se

        assert lower == pytest.approx(expected_lower, rel=1e-4)
        assert upper == pytest.approx(expected_upper, rel=1e-4)

    def test_custom_criteria(self):
        """Custom criteria thresholds are respected."""
        strict = ValidationCriteria(min_sample_size=500, max_p_value=0.01, min_roi_pct=5.0)
        validator = StatisticalValidator(criteria=strict)
        bets = self._make_profitable_bets(300)

        verdict = validator.validate(bets)
        # 300 < 500 → fail on sample size
        assert verdict.passed is False
        assert "Insufficient sample size" in verdict.reason

    def test_verdict_fields_populated(self):
        """All ValidationVerdict fields are properly populated."""
        validator = StatisticalValidator(
            criteria=ValidationCriteria(min_sample_size=10, min_roi_pct=1.0)
        )
        bets = self._make_profitable_bets(50)

        verdict = validator.validate(bets)

        assert isinstance(verdict.p_value, float)
        assert isinstance(verdict.mean_profit, float)
        assert isinstance(verdict.roi_pct, float)
        assert isinstance(verdict.sample_size, int)
        assert isinstance(verdict.confidence_interval, tuple)
        assert len(verdict.confidence_interval) == 2
        assert isinstance(verdict.effect_size, float)
        assert isinstance(verdict.reason, str)
