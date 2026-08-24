"""Unit tests for FDR control and quarantine tracking."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pytest

from src.engine.fdr import (
    FDRController,
    FDRResult,
    QuarantineEntry,
    QuarantineStatus,
    QuarantineTracker,
)


class TestFDRController:
    """Tests for Benjamini-Hochberg FDR correction."""

    def test_single_significant_p_value(self):
        """Single p-value below alpha is rejected."""
        fdr = FDRController(alpha=0.05)
        results = fdr.correct([0.01])

        assert len(results) == 1
        assert results[0].rejected is True
        assert results[0].rank == 1

    def test_single_non_significant_p_value(self):
        """Single p-value above alpha is not rejected."""
        fdr = FDRController(alpha=0.05)
        results = fdr.correct([0.10])

        assert len(results) == 1
        assert results[0].rejected is False

    def test_multiple_all_significant(self):
        """All p-values below their BH thresholds are rejected."""
        fdr = FDRController(alpha=0.05)
        # 3 p-values, thresholds: 0.0167, 0.0333, 0.05
        results = fdr.correct([0.01, 0.02, 0.03])

        assert all(r.rejected for r in results)

    def test_bh_step_up_procedure(self):
        """BH step-up correctly identifies the cutoff."""
        fdr = FDRController(alpha=0.05)
        # p-values: sorted would be [0.01, 0.03, 0.04, 0.20, 0.50]
        # Thresholds: [0.01, 0.02, 0.03, 0.04, 0.05]
        # 0.01 <= 0.01 ✓ (rank 1)
        # 0.03 <= 0.02 ✗ (rank 2)
        # 0.04 <= 0.03 ✗ (rank 3)
        # 0.20 <= 0.04 ✗ (rank 4)
        # 0.50 <= 0.05 ✗ (rank 5)
        # Cutoff at rank 1 → only first rejected
        results = fdr.correct([0.01, 0.03, 0.04, 0.20, 0.50])

        # Only the p=0.01 (original index 0) should be rejected
        rejected = [r for r in results if r.rejected]
        assert len(rejected) == 1
        assert rejected[0].original_p == 0.01

    def test_bh_with_clear_signals(self):
        """Multiple clearly significant results are all rejected."""
        fdr = FDRController(alpha=0.05)
        # All very small p-values
        p_values = [0.001, 0.002, 0.003, 0.004, 0.005]
        # Thresholds: [0.01, 0.02, 0.03, 0.04, 0.05]
        # All pass easily
        results = fdr.correct(p_values)

        assert all(r.rejected for r in results)

    def test_empty_input(self):
        """Empty p-value list returns empty results."""
        fdr = FDRController(alpha=0.05)
        results = fdr.correct([])

        assert results == []

    def test_preserves_original_order(self):
        """Results are returned in the same order as input p-values."""
        fdr = FDRController(alpha=0.05)
        p_values = [0.50, 0.01, 0.30]
        results = fdr.correct(p_values)

        assert results[0].original_p == 0.50
        assert results[1].original_p == 0.01
        assert results[2].original_p == 0.30

    def test_adjusted_threshold(self):
        """adjusted_threshold computes correct BH threshold."""
        fdr = FDRController(alpha=0.05)

        assert fdr.adjusted_threshold(1, 10) == pytest.approx(0.005)
        assert fdr.adjusted_threshold(5, 10) == pytest.approx(0.025)
        assert fdr.adjusted_threshold(10, 10) == pytest.approx(0.05)

    def test_adjusted_threshold_invalid_inputs(self):
        """Invalid rank/total raises ValueError."""
        fdr = FDRController(alpha=0.05)

        with pytest.raises(ValueError):
            fdr.adjusted_threshold(0, 10)
        with pytest.raises(ValueError):
            fdr.adjusted_threshold(1, 0)

    def test_is_significant_single_submission(self):
        """Single submission uses raw alpha."""
        fdr = FDRController(alpha=0.05)

        assert fdr.is_significant(0.03, submission_count=1) is True
        assert fdr.is_significant(0.06, submission_count=1) is False

    def test_is_significant_multiple_submissions(self):
        """Multiple submissions tighten the threshold."""
        fdr = FDRController(alpha=0.05)

        # With 10 submissions, threshold = 1/10 * 0.05 = 0.005
        assert fdr.is_significant(0.003, submission_count=10) is True
        assert fdr.is_significant(0.01, submission_count=10) is False

    def test_invalid_alpha_raises(self):
        """Alpha outside (0,1) raises ValueError."""
        with pytest.raises(ValueError):
            FDRController(alpha=0.0)
        with pytest.raises(ValueError):
            FDRController(alpha=1.0)
        with pytest.raises(ValueError):
            FDRController(alpha=-0.1)

    def test_fdr_result_fields(self):
        """FDRResult has all expected fields."""
        fdr = FDRController(alpha=0.05)
        results = fdr.correct([0.01, 0.10])

        r = results[0]
        assert isinstance(r.original_p, float)
        assert isinstance(r.adjusted_threshold, float)
        assert isinstance(r.rank, int)
        assert isinstance(r.total_hypotheses, int)
        assert isinstance(r.rejected, bool)
        assert r.total_hypotheses == 2


class TestQuarantineTracker:
    """Tests for QuarantineTracker lifecycle."""

    def _now(self) -> datetime:
        return datetime(2024, 6, 1, 12, 0, 0)

    def test_enter_quarantine(self):
        """Strategy enters quarantine with PENDING status."""
        tracker = QuarantineTracker()
        entry = tracker.enter_quarantine("strat_1", self._now())

        assert entry.status == QuarantineStatus.PENDING_QUARANTINE
        assert entry.strategy_name == "strat_1"
        assert entry.entry_date == self._now()

    def test_check_status(self):
        """Status is retrievable after entry."""
        tracker = QuarantineTracker()
        tracker.enter_quarantine("strat_1", self._now())

        status = tracker.check_status("strat_1", self._now())
        assert status == QuarantineStatus.PENDING_QUARANTINE

    def test_check_unknown_strategy_raises(self):
        """Checking unknown strategy raises KeyError."""
        tracker = QuarantineTracker()

        with pytest.raises(KeyError):
            tracker.check_status("unknown", self._now())

    def test_not_eligible_before_90_days(self):
        """Strategy is not eligible before 90 days."""
        tracker = QuarantineTracker()
        tracker.enter_quarantine("strat_1", self._now())

        day_89 = self._now() + timedelta(days=89)
        assert tracker.is_eligible_for_promotion("strat_1", day_89) is False

    def test_eligible_after_90_days(self):
        """Strategy is eligible after exactly 90 days."""
        tracker = QuarantineTracker()
        tracker.enter_quarantine("strat_1", self._now())

        day_90 = self._now() + timedelta(days=90)
        assert tracker.is_eligible_for_promotion("strat_1", day_90) is True

    def test_promote_after_90_days(self):
        """Promotion succeeds after quarantine period."""
        tracker = QuarantineTracker()
        tracker.enter_quarantine("strat_1", self._now())

        day_91 = self._now() + timedelta(days=91)
        success = tracker.promote("strat_1", day_91)

        assert success is True
        assert tracker.check_status("strat_1", day_91) == QuarantineStatus.PROMOTED

    def test_promote_before_90_days_fails(self):
        """Promotion fails before quarantine period."""
        tracker = QuarantineTracker()
        tracker.enter_quarantine("strat_1", self._now())

        day_30 = self._now() + timedelta(days=30)
        success = tracker.promote("strat_1", day_30)

        assert success is False
        assert tracker.check_status("strat_1", day_30) == QuarantineStatus.PENDING_QUARANTINE

    def test_reject_strategy(self):
        """Rejection sets status to REJECTED."""
        tracker = QuarantineTracker()
        tracker.enter_quarantine("strat_1", self._now())

        success = tracker.reject("strat_1")

        assert success is True
        assert tracker.check_status("strat_1", self._now()) == QuarantineStatus.REJECTED

    def test_reject_unknown_returns_false(self):
        """Rejecting unknown strategy returns False."""
        tracker = QuarantineTracker()
        assert tracker.reject("unknown") is False

    def test_re_enter_quarantine_resets(self):
        """Re-entering quarantine resets the entry date."""
        tracker = QuarantineTracker()
        tracker.enter_quarantine("strat_1", self._now())
        tracker.reject("strat_1")

        new_date = self._now() + timedelta(days=10)
        entry = tracker.enter_quarantine("strat_1", new_date)

        assert entry.entry_date == new_date
        assert entry.status == QuarantineStatus.PENDING_QUARANTINE

    def test_cannot_re_enter_promoted(self):
        """Cannot re-enter quarantine for promoted strategy."""
        tracker = QuarantineTracker()
        tracker.enter_quarantine("strat_1", self._now())
        tracker.promote("strat_1", self._now() + timedelta(days=90))

        with pytest.raises(ValueError, match="already promoted"):
            tracker.enter_quarantine("strat_1", self._now() + timedelta(days=100))

    def test_update_paper_pnl(self):
        """Paper P&L is tracked during quarantine."""
        tracker = QuarantineTracker()
        tracker.enter_quarantine("strat_1", self._now())

        tracker.update_paper_pnl("strat_1", 5.0, bets=3)
        tracker.update_paper_pnl("strat_1", -2.0, bets=2)

        entry = tracker.entries["strat_1"]
        assert entry.paper_pnl == pytest.approx(3.0)
        assert entry.paper_bets == 5

    def test_update_pnl_unknown_raises(self):
        """Updating P&L for unknown strategy raises KeyError."""
        tracker = QuarantineTracker()

        with pytest.raises(KeyError):
            tracker.update_paper_pnl("unknown", 1.0)

    def test_update_pnl_non_pending_raises(self):
        """Updating P&L for non-pending strategy raises ValueError."""
        tracker = QuarantineTracker()
        tracker.enter_quarantine("strat_1", self._now())
        tracker.reject("strat_1")

        with pytest.raises(ValueError, match="Cannot update P&L"):
            tracker.update_paper_pnl("strat_1", 1.0)
