"""Tests for the provider comparison harness (evaluation hooks)."""

from __future__ import annotations

import pytest

from src.research.evaluation import (
    ArmPredictions,
    ProviderComparisonHarness,
    ranked_probability_score,
)


class TestRPS:
    def test_perfect_prediction_zero(self):
        # All mass on the actual outcome -> RPS 0.
        assert ranked_probability_score([0.0, 1.0, 0.0], outcome_index=1) == 0.0

    def test_worse_than_confident_correct(self):
        confident = ranked_probability_score([1.0, 0.0, 0.0], 0)
        spread = ranked_probability_score([0.34, 0.33, 0.33], 0)
        assert confident < spread

    def test_requires_two_categories(self):
        with pytest.raises(ValueError):
            ranked_probability_score([1.0], 0)

    def test_outcome_index_bounds(self):
        with pytest.raises(ValueError):
            ranked_probability_score([0.5, 0.5], 2)


class TestHarnessAlignmentAndVerdict:
    def _arms(self):
        # fs predicts fixtures A,B,C; tsa predicts B,C,D; market predicts B,C.
        fs = ArmPredictions(
            name="footystats_only",
            binary={"A": 0.6, "B": 0.7, "C": 0.4},
            outcomes={"A": True, "B": True, "C": False},
        )
        tsa = ArmPredictions(
            name="thestatsapi_only",
            binary={"B": 0.65, "C": 0.45, "D": 0.5},
            outcomes={"B": True, "C": False, "D": True},
        )
        market = ArmPredictions(
            name="market",
            binary={"B": 0.6, "C": 0.5},
            outcomes={"B": True, "C": False},
        )
        return [fs, tsa, market]

    def test_alignment_to_common_fixtures(self):
        harness = ProviderComparisonHarness(min_samples=1)
        report = harness.compare(self._arms(), reference_arm="market")
        # Common to all three arms: B and C.
        assert report.aligned_fixture_count == 2
        for arm in report.arms:
            assert arm.n_evaluated == 2

    def test_verdict_is_never_a_winner(self):
        harness = ProviderComparisonHarness(min_samples=1)
        report = harness.compare(self._arms(), reference_arm="market")
        assert report.verdict == "NO_CLAIM"
        assert "out-of-sample" in report.note

    def test_coverage_reported(self):
        harness = ProviderComparisonHarness(min_samples=1)
        report = harness.compare(self._arms(), reference_arm="market")
        cov = {a.name: a.coverage for a in report.arms}
        # Union is {A,B,C,D} = 4. fs covers 3 -> 0.75; market covers 2 -> 0.5.
        assert abs(cov["footystats_only"] - 0.75) < 1e-9
        assert abs(cov["market"] - 0.5) < 1e-9

    def test_brier_skill_score_vs_reference(self):
        harness = ProviderComparisonHarness(min_samples=1)
        report = harness.compare(self._arms(), reference_arm="market")
        market = next(a for a in report.arms if a.name == "market")
        # Reference arm's skill score vs itself is 0 (brier/brier=1 -> 1-1=0).
        assert market.brier_skill_score is not None
        assert abs(market.brier_skill_score) < 1e-9

    def test_empty_arms(self):
        harness = ProviderComparisonHarness(min_samples=1)
        report = harness.compare([])
        assert report.aligned_fixture_count == 0 and report.verdict == "NO_CLAIM"
