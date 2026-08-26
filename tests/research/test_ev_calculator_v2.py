"""Tests for Batch 2 EV calculator extensions.

Tests cover:
- Three-way EV calculation
- Fair odds conversion
- De-vigging / margin normalization (multiple methods)
- Research prediction generation
- Missing odds handling
- EVStatus states
- Kelly criterion hardening
- Edge vs EV vs ROI distinction
- Market compatibility
- XMetric → probability → fair odds → EV pipeline
"""

import pytest

from src.research.ev_calculator import (
    DevigMethod,
    EVCalculator,
    EVResult,
    EVStatus,
    MarketProbabilityNormalizer,
    ResearchPrediction,
    ThreeWayEVResult,
    fair_odds_to_probability,
    probability_to_fair_odds,
)
from src.research.market import (
    GOALS_OVER_UNDER,
    MATCH_RESULT_1X2,
    MarketDirection,
    MarketOutcome,
)
from src.research.probability import (
    ModelIdentity,
    ProbabilityEstimate,
    ThreeWayProbabilityEstimate,
)


class TestFairOddsConversion:
    """Tests for probability ↔ fair odds conversion."""

    def test_probability_to_odds(self):
        assert abs(probability_to_fair_odds(0.5) - 2.0) < 0.001
        assert abs(probability_to_fair_odds(0.25) - 4.0) < 0.001
        assert abs(probability_to_fair_odds(1.0 / 3.0) - 3.0) < 0.001

    def test_high_probability_low_odds(self):
        odds = probability_to_fair_odds(0.9)
        assert abs(odds - 1.111) < 0.01

    def test_low_probability_high_odds(self):
        odds = probability_to_fair_odds(0.1)
        assert abs(odds - 10.0) < 0.001

    def test_invalid_probability_zero(self):
        assert probability_to_fair_odds(0.0) is None

    def test_invalid_probability_one(self):
        assert probability_to_fair_odds(1.0) is None

    def test_invalid_probability_negative(self):
        assert probability_to_fair_odds(-0.5) is None

    def test_invalid_probability_above_one(self):
        assert probability_to_fair_odds(1.5) is None

    def test_odds_to_probability(self):
        assert abs(fair_odds_to_probability(2.0) - 0.5) < 0.001
        assert abs(fair_odds_to_probability(4.0) - 0.25) < 0.001

    def test_invalid_odds(self):
        assert fair_odds_to_probability(1.0) is None
        assert fair_odds_to_probability(0.5) is None

    def test_roundtrip(self):
        """probability → odds → probability should be identity."""
        p = 0.65
        odds = probability_to_fair_odds(p)
        p_back = fair_odds_to_probability(odds)
        assert abs(p_back - p) < 0.0001


class TestMarketProbabilityNormalizer:
    """Tests for de-vigging / margin removal."""

    def test_multiplicative_two_way(self):
        norm = MarketProbabilityNormalizer(DevigMethod.MULTIPLICATIVE)
        result = norm.normalize_two_way(1.90, 2.00)
        assert result is not None
        fair_over, fair_under = result
        assert abs(fair_over + fair_under - 1.0) < 0.001
        # 1/1.9 > 1/2.0, so fair_over > fair_under
        assert fair_over > fair_under

    def test_additive_two_way(self):
        norm = MarketProbabilityNormalizer(DevigMethod.ADDITIVE)
        result = norm.normalize_two_way(1.90, 2.00)
        assert result is not None
        fair_over, fair_under = result
        assert abs(fair_over + fair_under - 1.0) < 0.001

    def test_power_two_way(self):
        norm = MarketProbabilityNormalizer(DevigMethod.POWER)
        result = norm.normalize_two_way(1.90, 2.00)
        assert result is not None
        fair_over, fair_under = result
        assert abs(fair_over + fair_under - 1.0) < 0.001

    def test_no_margin_odds(self):
        """Fair odds (no margin) should pass through."""
        norm = MarketProbabilityNormalizer(DevigMethod.MULTIPLICATIVE)
        result = norm.normalize_two_way(2.0, 2.0)
        assert result is not None
        fair_over, fair_under = result
        assert abs(fair_over - 0.5) < 0.001
        assert abs(fair_under - 0.5) < 0.001

    def test_invalid_odds_returns_none(self):
        norm = MarketProbabilityNormalizer()
        assert norm.normalize_two_way(1.0, 2.0) is None
        assert norm.normalize_two_way(2.0, 0.5) is None

    def test_three_way_multiplicative(self):
        norm = MarketProbabilityNormalizer(DevigMethod.MULTIPLICATIVE)
        result = norm.normalize_three_way(2.0, 3.5, 4.0)
        assert result is not None
        h, d, a = result
        assert abs(h + d + a - 1.0) < 0.001
        assert h > d > a  # Lower odds = higher probability

    def test_three_way_additive(self):
        norm = MarketProbabilityNormalizer(DevigMethod.ADDITIVE)
        result = norm.normalize_three_way(2.0, 3.5, 4.0)
        assert result is not None
        h, d, a = result
        assert abs(h + d + a - 1.0) < 0.001

    def test_three_way_power(self):
        norm = MarketProbabilityNormalizer(DevigMethod.POWER)
        result = norm.normalize_three_way(2.0, 3.5, 4.0)
        assert result is not None
        h, d, a = result
        assert abs(h + d + a - 1.0) < 0.001

    def test_three_way_invalid_odds(self):
        norm = MarketProbabilityNormalizer()
        assert norm.normalize_three_way(0.5, 3.0, 4.0) is None
        assert norm.normalize_three_way(2.0, 1.0, 4.0) is None

    def test_overround_calculation(self):
        norm = MarketProbabilityNormalizer()
        # 1/1.9 + 1/2.0 = 0.5263 + 0.5 = 1.0263 → overround = 2.63%
        overround = norm.compute_overround(1.90, 2.00)
        assert overround is not None
        assert abs(overround - 0.0263) < 0.001

    def test_overround_three_way(self):
        norm = MarketProbabilityNormalizer()
        overround = norm.compute_overround(2.0, 3.5, 4.0)
        assert overround is not None
        # 1/2 + 1/3.5 + 1/4 = 0.5 + 0.286 + 0.25 = 1.036 → 3.6%
        assert overround > 0

    def test_overround_invalid_odds(self):
        norm = MarketProbabilityNormalizer()
        assert norm.compute_overround(1.0, 2.0) is None

    def test_methods_differ_slightly(self):
        """Different methods should give slightly different results."""
        mult = MarketProbabilityNormalizer(DevigMethod.MULTIPLICATIVE)
        add = MarketProbabilityNormalizer(DevigMethod.ADDITIVE)
        power = MarketProbabilityNormalizer(DevigMethod.POWER)

        r1 = mult.normalize_two_way(1.50, 2.80)
        r2 = add.normalize_two_way(1.50, 2.80)
        r3 = power.normalize_two_way(1.50, 2.80)

        # All sum to 1
        assert abs(sum(r1) - 1.0) < 0.001
        assert abs(sum(r2) - 1.0) < 0.001
        assert abs(sum(r3) - 1.0) < 0.001

        # But not all identical (skewed odds show difference)
        # At minimum mult and add should differ for skewed markets
        assert abs(r1[0] - r2[0]) > 0.001 or abs(r1[0] - r3[0]) > 0.001


class TestThreeWayEV:
    """Tests for three-way market EV calculation."""

    def test_compute_three_way_basic(self):
        """Model predicts home win, market has value."""
        calc = EVCalculator()
        est = ThreeWayProbabilityEstimate(
            p_home=0.6, p_draw=0.25, p_away=0.15, model_name="test"
        )
        result = calc.compute_three_way(est, home_odds=2.0, draw_odds=3.5, away_odds=5.0)
        assert result is not None
        # EV_home = 0.6 * 2.0 - 1 = 0.2
        assert abs(result.ev_home - 0.2) < 0.001
        assert result.best_outcome == MarketOutcome.HOME

    def test_three_way_ev_formula(self):
        """EV = P * odds - 1 for each outcome."""
        calc = EVCalculator()
        est = ThreeWayProbabilityEstimate(
            p_home=0.4, p_draw=0.3, p_away=0.3, model_name="test"
        )
        result = calc.compute_three_way(est, home_odds=2.5, draw_odds=3.0, away_odds=4.0)
        assert result is not None
        assert abs(result.ev_home - (0.4 * 2.5 - 1.0)) < 0.001
        assert abs(result.ev_draw - (0.3 * 3.0 - 1.0)) < 0.001
        assert abs(result.ev_away - (0.3 * 4.0 - 1.0)) < 0.001

    def test_three_way_fair_probs_sum_to_one(self):
        calc = EVCalculator()
        est = ThreeWayProbabilityEstimate(
            p_home=0.5, p_draw=0.3, p_away=0.2, model_name="test"
        )
        result = calc.compute_three_way(est, home_odds=2.0, draw_odds=3.5, away_odds=5.0)
        assert result is not None
        assert abs(sum(result.fair_probs) - 1.0) < 0.001

    def test_three_way_kelly_capped_at_zero(self):
        """Negative edge → kelly = 0."""
        calc = EVCalculator()
        est = ThreeWayProbabilityEstimate(
            p_home=0.2, p_draw=0.3, p_away=0.5, model_name="test"
        )
        result = calc.compute_three_way(est, home_odds=2.0, draw_odds=3.5, away_odds=5.0)
        assert result is not None
        # Home is undervalued by model → kelly_home should be 0
        assert result.kelly_fractions[0] == 0.0

    def test_three_way_invalid_odds(self):
        calc = EVCalculator()
        est = ThreeWayProbabilityEstimate(
            p_home=0.5, p_draw=0.3, p_away=0.2, model_name="test"
        )
        result = calc.compute_three_way(est, home_odds=1.0, draw_odds=3.5, away_odds=5.0)
        assert result is None

    def test_three_way_best_outcome_draw(self):
        """Test that draw can be the best EV outcome."""
        calc = EVCalculator()
        est = ThreeWayProbabilityEstimate(
            p_home=0.2, p_draw=0.6, p_away=0.2, model_name="test"
        )
        result = calc.compute_three_way(est, home_odds=2.5, draw_odds=3.0, away_odds=4.0)
        assert result is not None
        # EV_draw = 0.6 * 3.0 - 1 = 0.8, EV_home = 0.2*2.5-1 = -0.5
        assert result.best_outcome == MarketOutcome.DRAW


class TestResearchPrediction:
    """Tests for ResearchPrediction generation."""

    def test_valid_prediction(self):
        calc = EVCalculator()
        est = ProbabilityEstimate(p_over=0.6, p_under=0.4, model_name="test")
        pred = calc.create_research_prediction(
            est, GOALS_OVER_UNDER,
            over_odds=2.0, under_odds=2.0,
            direction=MarketDirection.OVER,
        )
        assert pred.ev_status == EVStatus.VALID
        assert pred.is_ev_positive
        assert abs(pred.expected_value - 0.2) < 0.001
        assert pred.market_type == "GOALS_TOTAL"
        assert pred.line == 2.5
        assert pred.direction == "OVER"

    def test_missing_odds(self):
        calc = EVCalculator()
        est = ProbabilityEstimate(p_over=0.6, p_under=0.4, model_name="test")
        pred = calc.create_research_prediction(
            est, GOALS_OVER_UNDER,
            over_odds=None, under_odds=None,
            direction=MarketDirection.OVER,
        )
        assert pred.ev_status == EVStatus.MISSING_ODDS
        assert not pred.is_ev_positive
        assert pred.expected_value is None
        # Fair odds still computed from model probability
        assert pred.fair_odds is not None
        assert abs(pred.fair_odds - 1.0 / 0.6) < 0.001

    def test_invalid_odds(self):
        calc = EVCalculator()
        est = ProbabilityEstimate(p_over=0.6, p_under=0.4, model_name="test")
        pred = calc.create_research_prediction(
            est, GOALS_OVER_UNDER,
            over_odds=0.5, under_odds=2.0,
            direction=MarketDirection.OVER,
        )
        assert pred.ev_status == EVStatus.INVALID_ODDS

    def test_with_model_identity(self):
        calc = EVCalculator()
        est = ProbabilityEstimate(p_over=0.55, p_under=0.45, model_name="test")
        identity = ModelIdentity.create("logistic", 1, {"lr": 0.01})
        pred = calc.create_research_prediction(
            est, GOALS_OVER_UNDER,
            over_odds=1.90, under_odds=2.00,
            direction=MarketDirection.OVER,
            model_identity=identity,
        )
        assert pred.model_id == identity.content_hash
        assert pred.model_version == 1

    def test_with_timestamps(self):
        calc = EVCalculator()
        est = ProbabilityEstimate(p_over=0.55, p_under=0.45, model_name="test")
        pred = calc.create_research_prediction(
            est, GOALS_OVER_UNDER,
            over_odds=1.90, under_odds=2.00,
            direction=MarketDirection.OVER,
            prediction_timestamp=10000,
            information_timestamp=9000,
        )
        assert pred.prediction_timestamp == 10000
        assert pred.information_timestamp == 9000

    def test_kelly_positive(self):
        calc = EVCalculator()
        est = ProbabilityEstimate(p_over=0.7, p_under=0.3, model_name="test")
        pred = calc.create_research_prediction(
            est, GOALS_OVER_UNDER,
            over_odds=2.0, under_odds=2.0,
            direction=MarketDirection.OVER,
        )
        assert pred.is_kelly_positive
        assert pred.kelly_fraction > 0

    def test_kelly_zero_no_edge(self):
        calc = EVCalculator()
        est = ProbabilityEstimate(p_over=0.4, p_under=0.6, model_name="test")
        pred = calc.create_research_prediction(
            est, GOALS_OVER_UNDER,
            over_odds=2.0, under_odds=2.0,
            direction=MarketDirection.OVER,
        )
        assert not pred.is_kelly_positive
        assert pred.kelly_fraction == 0.0


class TestEdgeVsEVDistinction:
    """Tests proving edge ≠ EV ≠ ROI.

    These are fundamentally different concepts:
    - Edge: P(model) - P(fair) — probability advantage
    - EV: P(model) × odds - 1 — expected economic profit per unit
    - ROI: actual profit / actual staked — realized return (post-hoc)
    """

    def test_edge_and_ev_different_values(self):
        """Edge and EV have different magnitudes."""
        est = ProbabilityEstimate(p_over=0.6, p_under=0.4, model_name="test")
        result = EVCalculator.compute(
            est, GOALS_OVER_UNDER, over_odds=2.0, under_odds=2.0,
            direction=MarketDirection.OVER,
        )
        assert result is not None
        # Edge = 0.6 - 0.5 = 0.1
        assert abs(result.edge - 0.1) < 0.001
        # EV = 0.6 * 2.0 - 1 = 0.2
        assert abs(result.expected_value - 0.2) < 0.001
        # They are different!
        assert result.edge != result.expected_value

    def test_positive_edge_implies_positive_ev(self):
        """If edge > 0 (vs fair probability), EV should be positive."""
        est = ProbabilityEstimate(p_over=0.6, p_under=0.4, model_name="test")
        result = EVCalculator.compute(
            est, GOALS_OVER_UNDER, over_odds=1.90, under_odds=2.00,
            direction=MarketDirection.OVER,
        )
        assert result is not None
        # Fair over prob ≈ 0.513 (from de-vigging 1.90/2.00)
        # Model = 0.6 > 0.513 → positive edge
        assert result.edge > 0
        # EV = 0.6 * 1.90 - 1 = 0.14 → positive
        assert result.expected_value > 0

    def test_negative_edge_negative_ev(self):
        """Negative edge means the model thinks market is efficient."""
        est = ProbabilityEstimate(p_over=0.4, p_under=0.6, model_name="test")
        result = EVCalculator.compute(
            est, GOALS_OVER_UNDER, over_odds=2.0, under_odds=2.0,
            direction=MarketDirection.OVER,
        )
        assert result is not None
        assert result.edge < 0
        assert result.expected_value < 0

    def test_ev_depends_on_odds_not_just_edge(self):
        """Same edge at different odds gives different EV."""
        est = ProbabilityEstimate(p_over=0.6, p_under=0.4, model_name="test")

        # At odds 2.0: EV = 0.6*2.0 - 1 = 0.20
        r1 = EVCalculator.compute(
            est, GOALS_OVER_UNDER, over_odds=2.0, under_odds=2.0,
            direction=MarketDirection.OVER,
        )
        # At odds 1.5: EV = 0.6*1.5 - 1 = -0.10
        r2 = EVCalculator.compute(
            est, GOALS_OVER_UNDER, over_odds=1.5, under_odds=3.0,
            direction=MarketDirection.OVER,
        )
        assert r1 is not None and r2 is not None
        assert r1.expected_value > 0
        assert r2.expected_value < 0
        # Same model probability, different EV!


class TestKellyHardening:
    """Tests for Kelly criterion edge cases."""

    def test_kelly_zero_edge(self):
        """No edge → Kelly = 0."""
        est = ProbabilityEstimate(p_over=0.5, p_under=0.5, model_name="test")
        result = EVCalculator.compute(
            est, GOALS_OVER_UNDER, over_odds=2.0, under_odds=2.0,
            direction=MarketDirection.OVER,
        )
        assert result is not None
        assert result.kelly_fraction == 0.0

    def test_kelly_negative_edge(self):
        """Negative edge → Kelly capped at 0 (don't bet)."""
        est = ProbabilityEstimate(p_over=0.3, p_under=0.7, model_name="test")
        result = EVCalculator.compute(
            est, GOALS_OVER_UNDER, over_odds=2.0, under_odds=2.0,
            direction=MarketDirection.OVER,
        )
        assert result is not None
        assert result.kelly_fraction == 0.0

    def test_kelly_positive_reasonable_fraction(self):
        """Positive edge → small Kelly fraction."""
        est = ProbabilityEstimate(p_over=0.6, p_under=0.4, model_name="test")
        result = EVCalculator.compute(
            est, GOALS_OVER_UNDER, over_odds=2.0, under_odds=2.0,
            direction=MarketDirection.OVER,
        )
        assert result is not None
        # kelly = edge / (odds - 1) = 0.1 / 1.0 = 0.1
        assert abs(result.kelly_fraction - 0.1) < 0.01

    def test_kelly_formula_decimal_odds(self):
        """Kelly = (b*p - q) / b where b = odds - 1.

        Equivalent to edge / (odds - 1) when edge = p - fair_p.
        """
        est = ProbabilityEstimate(p_over=0.65, p_under=0.35, model_name="test")
        result = EVCalculator.compute(
            est, GOALS_OVER_UNDER, over_odds=1.80, under_odds=2.20,
            direction=MarketDirection.OVER,
        )
        assert result is not None
        # Kelly should be edge / (odds - 1)
        expected_kelly = result.edge / (1.80 - 1.0)
        if expected_kelly < 0:
            expected_kelly = 0
        assert abs(result.kelly_fraction - expected_kelly) < 0.001


class TestMarketCompatibility:
    """Tests verifying XMetric → probability → EV pipeline concept."""

    def test_xmetric_feature_to_probability_to_ev(self):
        """Demonstrate: features → model → probability → fair odds → EV."""
        from src.research.probability import LogisticRegressionModel

        # Simulate XMetric features
        model = LogisticRegressionModel(learning_rate=0.1, max_iter=500)
        features = [{"home_xC": float(i * 0.1)} for i in range(100)]
        outcomes = [i > 50 for i in range(100)]
        model.fit(features, outcomes)

        # Predict
        est = model.predict({"home_xC": 7.0})
        assert 0 < est.p_over < 1

        # Convert to EV
        result = EVCalculator.compute(
            est, GOALS_OVER_UNDER, over_odds=1.90, under_odds=2.00,
            direction=MarketDirection.OVER,
        )
        assert result is not None
        # The pipeline works: xMetric → probability → EV
        assert isinstance(result.expected_value, float)
