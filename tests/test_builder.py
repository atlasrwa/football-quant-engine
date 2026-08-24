"""Unit tests for the no-code strategy builder."""

from __future__ import annotations

import json

import pytest

from src.engine.builder import StrategyBuilder
from src.engine.evaluator import Condition, Strategy


class TestStrategyBuilder:
    """Tests for StrategyBuilder fluent API."""

    def _make_builder(self) -> StrategyBuilder:
        """Create a fully configured builder."""
        return (
            StrategyBuilder()
            .set_name("High xC Over")
            .set_metric("xC")
            .set_market("corners_over_under")
            .set_direction("OVER")
            .set_min_odds(1.70)
            .add_condition("home_xC", ">", 2.5)
        )

    def test_build_produces_strategy(self):
        """Builder produces a valid Strategy object."""
        builder = self._make_builder()
        strategy = builder.build()

        assert isinstance(strategy, Strategy)
        assert strategy.name == "High xC Over"
        assert strategy.metric == "xC"
        assert strategy.market == "corners_over_under"
        assert strategy.direction == "OVER"
        assert strategy.min_odds == 1.70

    def test_build_conditions_correct(self):
        """Built strategy has correct conditions."""
        builder = self._make_builder()
        strategy = builder.build()

        assert len(strategy.conditions) == 1
        cond = strategy.conditions[0]
        assert cond.field == "home_xC"
        assert cond.op == ">"
        assert cond.value == 2.5

    def test_multiple_conditions(self):
        """Builder supports multiple conditions."""
        builder = (
            StrategyBuilder()
            .set_name("Multi")
            .set_metric("xC")
            .set_market("corners_over_under")
            .add_condition("home_xC", ">", 2.5)
            .add_condition("away_xC", ">", 2.0)
            .set_direction("OVER")
        )
        strategy = builder.build()

        assert len(strategy.conditions) == 2

    def test_or_logic(self):
        """Builder supports OR logic."""
        builder = (
            StrategyBuilder()
            .set_name("Or Logic")
            .set_metric("xB")
            .set_market("cards_over_under")
            .set_logic("or")
            .add_condition("home_xB", ">", 10.0)
            .add_condition("away_xB", ">", 10.0)
            .set_direction("OVER")
        )
        strategy = builder.build()

        assert strategy.logic == "or"

    def test_fluent_chaining(self):
        """All setters return self for chaining."""
        builder = StrategyBuilder()
        result = builder.set_name("Test")
        assert result is builder

        result = builder.set_metric("xC")
        assert result is builder

        result = builder.add_condition("x", ">", 1.0)
        assert result is builder

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def test_build_no_name_raises(self):
        """Build without name raises ValueError."""
        builder = (
            StrategyBuilder()
            .set_metric("xC")
            .set_market("corners_over_under")
            .add_condition("home_xC", ">", 2.0)
            .set_direction("OVER")
        )

        with pytest.raises(ValueError, match="name is required"):
            builder.build()

    def test_build_no_metric_raises(self):
        """Build without metric raises ValueError."""
        builder = (
            StrategyBuilder()
            .set_name("Test")
            .set_market("corners_over_under")
            .add_condition("home_xC", ">", 2.0)
            .set_direction("OVER")
        )

        with pytest.raises(ValueError, match="metric is required"):
            builder.build()

    def test_build_no_conditions_raises(self):
        """Build without conditions raises ValueError."""
        builder = (
            StrategyBuilder()
            .set_name("Test")
            .set_metric("xC")
            .set_market("corners_over_under")
            .set_direction("OVER")
        )

        with pytest.raises(ValueError, match="at least one condition"):
            builder.build()

    def test_invalid_metric_raises(self):
        """Invalid metric raises ValueError at set time."""
        builder = StrategyBuilder()

        with pytest.raises(ValueError, match="Invalid metric"):
            builder.set_metric("invalid")

    def test_invalid_market_raises(self):
        """Invalid market raises ValueError at set time."""
        builder = StrategyBuilder()

        with pytest.raises(ValueError, match="Invalid market"):
            builder.set_market("invalid_market")

    def test_invalid_direction_raises(self):
        """Invalid direction raises ValueError at set time."""
        builder = StrategyBuilder()

        with pytest.raises(ValueError, match="Invalid direction"):
            builder.set_direction("SIDEWAYS")

    def test_invalid_logic_raises(self):
        """Invalid logic raises ValueError at set time."""
        builder = StrategyBuilder()

        with pytest.raises(ValueError, match="Invalid logic"):
            builder.set_logic("xor")

    def test_invalid_operator_raises(self):
        """Invalid operator raises ValueError at add_condition time."""
        builder = StrategyBuilder()

        with pytest.raises(ValueError, match="Invalid operator"):
            builder.add_condition("home_xC", "~=", 2.0)

    def test_empty_name_raises(self):
        """Empty/blank name raises ValueError."""
        builder = StrategyBuilder()

        with pytest.raises(ValueError, match="cannot be empty"):
            builder.set_name("")
        with pytest.raises(ValueError, match="cannot be empty"):
            builder.set_name("   ")

    def test_empty_field_raises(self):
        """Empty condition field raises ValueError."""
        builder = StrategyBuilder()

        with pytest.raises(ValueError, match="field cannot be empty"):
            builder.add_condition("", ">", 2.0)

    def test_min_odds_below_1_raises(self):
        """min_odds <= 1.0 raises ValueError."""
        builder = StrategyBuilder()

        with pytest.raises(ValueError, match="min_odds must be > 1.0"):
            builder.set_min_odds(1.0)
        with pytest.raises(ValueError, match="min_odds must be > 1.0"):
            builder.set_min_odds(0.5)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def test_to_json(self):
        """to_json produces valid JSON string."""
        builder = self._make_builder()
        json_str = builder.to_json()

        data = json.loads(json_str)
        assert data["name"] == "High xC Over"
        assert data["metric"] == "xC"
        assert data["conditions"][0]["field"] == "home_xC"
        assert data["conditions"][0]["op"] == ">"
        assert data["conditions"][0]["value"] == 2.5

    def test_from_json_roundtrip(self):
        """from_json → build produces equivalent strategy."""
        builder = self._make_builder()
        json_str = builder.to_json()

        rebuilt = StrategyBuilder.from_json(json_str)
        strategy = rebuilt.build()

        assert strategy.name == "High xC Over"
        assert strategy.metric == "xC"
        assert strategy.conditions[0].value == 2.5

    def test_from_dict(self):
        """from_dict constructs builder from flat dictionary."""
        data = {
            "name": "Dict Strategy",
            "metric": "xB",
            "market": "cards_over_under",
            "direction": "OVER",
            "min_odds": 1.80,
            "conditions": [
                {"field": "home_xB", "op": ">=", "value": 8.0},
            ],
        }

        builder = StrategyBuilder.from_dict(data)
        strategy = builder.build()

        assert strategy.name == "Dict Strategy"
        assert strategy.metric == "xB"
        assert strategy.min_odds == 1.80

    def test_to_dict_structure(self):
        """to_dict matches expected schema for StrategyEvaluator."""
        builder = self._make_builder()
        data = builder.to_dict()

        assert "name" in data
        assert "metric" in data
        assert "market" in data
        assert "conditions" in data
        assert "logic" in data
        assert "direction" in data
        assert "min_odds" in data

    def test_clear_conditions(self):
        """clear_conditions removes all conditions."""
        builder = self._make_builder()
        builder.clear_conditions()

        with pytest.raises(ValueError, match="at least one condition"):
            builder.build()

    def test_compatible_with_evaluator(self):
        """Built strategy works with StrategyEvaluator.load_strategies_from_list."""
        from src.engine.evaluator import StrategyEvaluator

        builder = self._make_builder()
        data = builder.to_dict()

        evaluator = StrategyEvaluator()
        strategies = evaluator.load_strategies_from_list([data])

        assert len(strategies) == 1
        assert strategies[0].name == "High xC Over"

    def test_all_valid_metrics(self):
        """All defined valid metrics are accepted."""
        for metric in StrategyBuilder.VALID_METRICS:
            builder = StrategyBuilder()
            builder.set_metric(metric)  # Should not raise

    def test_all_valid_markets(self):
        """All defined valid markets are accepted."""
        for market in StrategyBuilder.VALID_MARKETS:
            builder = StrategyBuilder()
            builder.set_market(market)  # Should not raise

    def test_all_valid_operators(self):
        """All defined valid operators are accepted."""
        builder = StrategyBuilder()
        for op in StrategyBuilder.VALID_OPERATORS:
            builder.add_condition("field", op, 1.0)  # Should not raise
