"""Tests for EV calculator."""

import pytest

from src.research.ev_calculator import EVCalculator, EVResult
from src.research.market import (
    CORNERS_OVER_UNDER,
    GOALS_OVER_UNDER,
    MarketDirection,
)
from src.research.probability import ProbabilityEstimate


class TestEVCalculator:
    """Tests for EVCalculator."""

    def test_positive_ev_over(self):
        """Model thinks 60% OVER, odds are 2.0 → EV = 0.6*2.0 - 1 = 0.2."""
        est = ProbabilityEstimate(p_over=0.6, p_under=0.4, model_name="test")
        result = EVCalculator.compute(
            est, GOALS_OVER_UNDER, over_odds=2.0, under_odds=2.0,
            direction=MarketDirection.OVER,
        )
        assert result is not None
        assert abs(result.expected_value - 0.2) < 0.001
        assert result.direction == MarketDirection.OVER

    def test_negative_ev(self):
        """Model thinks 40% OVER, odds are 2.0 → EV = 0.4*2.0 - 1 = -0.2."""
        est = ProbabilityEstimate(p_over=0.4, p_under=0.6, model_name="test")
        result = EVCalculator.compute(
            est, GOALS_OVER_UNDER, over_odds=2.0, under_odds=2.0,
            direction=MarketDirection.OVER,
        )
        assert result is not None
        assert abs(result.expected_value - (-0.2)) < 0.001

    def test_zero_ev(self):
        """Model agrees with market → EV = 0."""
        est = ProbabilityEstimate(p_over=0.5, p_under=0.5, model_name="test")
        result = EVCalculator.compute(
            est, GOALS_OVER_UNDER, over_odds=2.0, under_odds=2.0,
            direction=MarketDirection.OVER,
        )
        assert result is not None
        assert abs(result.expected_value) < 0.001

    def test_picks_best_side_when_no_direction(self):
        """Without direction, should pick the side with higher EV."""
        est = ProbabilityEstimate(p_over=0.7, p_under=0.3, model_name="test")
        result = EVCalculator.compute(
            est, GOALS_OVER_UNDER, over_odds=1.80, under_odds=2.20,
        )
        assert result is not None
        assert result.direction == MarketDirection.OVER  # Higher EV

    def test_under_direction(self):
        est = ProbabilityEstimate(p_over=0.3, p_under=0.7, model_name="test")
        result = EVCalculator.compute(
            est, GOALS_OVER_UNDER, over_odds=2.0, under_odds=1.80,
            direction=MarketDirection.UNDER,
        )
        assert result is not None
        assert result.direction == MarketDirection.UNDER
        # EV = 0.7 * 1.80 - 1 = 0.26
        assert abs(result.expected_value - 0.26) < 0.001

    def test_invalid_odds_returns_none(self):
        est = ProbabilityEstimate(p_over=0.6, p_under=0.4, model_name="test")
        result = EVCalculator.compute(
            est, GOALS_OVER_UNDER, over_odds=1.0, under_odds=2.0,
        )
        assert result is None

    def test_kelly_fraction_positive_edge(self):
        """Kelly = edge / (odds - 1)."""
        est = ProbabilityEstimate(p_over=0.6, p_under=0.4, model_name="test")
        result = EVCalculator.compute(
            est, GOALS_OVER_UNDER, over_odds=2.0, under_odds=2.0,
            direction=MarketDirection.OVER,
        )
        assert result is not None
        assert result.kelly_fraction > 0

    def test_kelly_fraction_zero_when_no_edge(self):
        """Negative edge → kelly capped at 0."""
        est = ProbabilityEstimate(p_over=0.4, p_under=0.6, model_name="test")
        result = EVCalculator.compute(
            est, GOALS_OVER_UNDER, over_odds=2.0, under_odds=2.0,
            direction=MarketDirection.OVER,
        )
        assert result is not None
        assert result.kelly_fraction == 0.0

    def test_implied_probability(self):
        est = ProbabilityEstimate(p_over=0.6, p_under=0.4, model_name="test")
        result = EVCalculator.compute(
            est, GOALS_OVER_UNDER, over_odds=1.80, under_odds=2.20,
            direction=MarketDirection.OVER,
        )
        assert result is not None
        assert abs(result.implied_probability - 1.0 / 1.80) < 0.001

    def test_compute_both_sides(self):
        est = ProbabilityEstimate(p_over=0.55, p_under=0.45, model_name="test")
        over_result, under_result = EVCalculator.compute_both_sides(
            est, GOALS_OVER_UNDER, over_odds=1.90, under_odds=2.00,
        )
        assert over_result is not None
        assert under_result is not None
        assert over_result.direction == MarketDirection.OVER
        assert under_result.direction == MarketDirection.UNDER

    def test_ev_formula_consistency(self):
        """EV = P * odds - 1 must hold exactly."""
        est = ProbabilityEstimate(p_over=0.65, p_under=0.35, model_name="test")
        result = EVCalculator.compute(
            est, CORNERS_OVER_UNDER, over_odds=1.75, under_odds=2.30,
            direction=MarketDirection.OVER,
        )
        assert result is not None
        expected_ev = 0.65 * 1.75 - 1.0
        assert abs(result.expected_value - expected_ev) < 0.0001

    def test_edge_calculation(self):
        """Edge = model_probability - fair_probability."""
        est = ProbabilityEstimate(p_over=0.6, p_under=0.4, model_name="test")
        result = EVCalculator.compute(
            est, GOALS_OVER_UNDER, over_odds=2.0, under_odds=2.0,
            direction=MarketDirection.OVER,
        )
        assert result is not None
        # Fair prob at equal odds = 0.5, model = 0.6, edge = 0.1
        assert abs(result.edge - 0.1) < 0.001
