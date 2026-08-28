"""No-code strategy builder and schema exporter.

Provides a fluent API for constructing Strategy objects from simple
dictionary inputs (e.g., UI dropdown selections) with full validation
and bi-directional JSON serialization.
"""

from __future__ import annotations

import json
import logging
from typing import List

from src.engine.evaluator import Condition, Strategy, StrategyEvaluator

logger = logging.getLogger(__name__)


class StrategyBuilder:
    """No-code strategy construction from simple parameters.

    Provides a fluent builder pattern with input validation, producing
    Strategy objects compatible with StrategyEvaluator.
    """

    VALID_METRICS = {"xC", "xB", "xO"}
    VALID_MARKETS = {
        "corners_over_under",
        "cards_over_under",
        "offsides_over_under",
        "match_odds",
        "asian_handicap",
    }
    VALID_OPERATORS = {">", "<", ">=", "<=", "==", "!="}
    VALID_DIRECTIONS = {"OVER", "UNDER", "BACK", "LAY"}
    VALID_LOGIC = {"and", "or"}

    def __init__(self) -> None:
        self._name: str = ""
        self._metric: str = ""
        self._market: str = ""
        self._conditions: List[dict] = []
        self._logic: str = "and"
        self._direction: str = "OVER"
        self._min_odds: float = 1.50

    # ------------------------------------------------------------------
    # Fluent setter API
    # ------------------------------------------------------------------

    def set_name(self, name: str) -> "StrategyBuilder":
        """Set the strategy name.

        Args:
            name: Human-readable strategy name.

        Returns:
            Self for chaining.
        """
        if not name or not name.strip():
            raise ValueError("Strategy name cannot be empty")
        self._name = name.strip()
        return self

    def set_metric(self, metric: str) -> "StrategyBuilder":
        """Set the target metric (xC, xB, xO).

        Args:
            metric: One of VALID_METRICS.

        Returns:
            Self for chaining.
        """
        if metric not in self.VALID_METRICS:
            raise ValueError(
                f"Invalid metric '{metric}'. Must be one of: {sorted(self.VALID_METRICS)}"
            )
        self._metric = metric
        return self

    def set_market(self, market: str) -> "StrategyBuilder":
        """Set the target market.

        Args:
            market: One of VALID_MARKETS.

        Returns:
            Self for chaining.
        """
        if market not in self.VALID_MARKETS:
            raise ValueError(
                f"Invalid market '{market}'. Must be one of: {sorted(self.VALID_MARKETS)}"
            )
        self._market = market
        return self

    def set_direction(self, direction: str) -> "StrategyBuilder":
        """Set the betting direction.

        Args:
            direction: One of VALID_DIRECTIONS.

        Returns:
            Self for chaining.
        """
        if direction not in self.VALID_DIRECTIONS:
            raise ValueError(
                f"Invalid direction '{direction}'. Must be one of: {sorted(self.VALID_DIRECTIONS)}"
            )
        self._direction = direction
        return self

    def set_logic(self, logic: str) -> "StrategyBuilder":
        """Set the condition combinator logic.

        Args:
            logic: "and" or "or".

        Returns:
            Self for chaining.
        """
        if logic not in self.VALID_LOGIC:
            raise ValueError(
                f"Invalid logic '{logic}'. Must be one of: {sorted(self.VALID_LOGIC)}"
            )
        self._logic = logic
        return self

    def set_min_odds(self, min_odds: float) -> "StrategyBuilder":
        """Set minimum odds filter.

        Args:
            min_odds: Minimum acceptable odds (must be > 1.0).

        Returns:
            Self for chaining.
        """
        if min_odds <= 1.0:
            raise ValueError(f"min_odds must be > 1.0, got {min_odds}")
        self._min_odds = min_odds
        return self

    def add_condition(self, field: str, op: str, value: float) -> "StrategyBuilder":
        """Add a condition to the strategy.

        Args:
            field: DataFrame column name to evaluate.
            op: Comparison operator (>, <, >=, <=, ==, !=).
            value: Threshold value.

        Returns:
            Self for chaining.
        """
        if op not in self.VALID_OPERATORS:
            raise ValueError(
                f"Invalid operator '{op}'. Must be one of: {sorted(self.VALID_OPERATORS)}"
            )
        if not field or not field.strip():
            raise ValueError("Condition field cannot be empty")

        self._conditions.append({
            "field": field.strip(),
            "op": op,
            "value": float(value),
        })
        return self

    def clear_conditions(self) -> "StrategyBuilder":
        """Remove all conditions."""
        self._conditions = []
        return self

    # ------------------------------------------------------------------
    # Build & Validation
    # ------------------------------------------------------------------

    def build(self) -> Strategy:
        """Validate inputs and produce a Strategy object.

        Returns:
            Validated Strategy instance.

        Raises:
            ValueError: If required fields are missing or invalid.
        """
        errors: List[str] = []

        if not self._name:
            errors.append("name is required")
        if not self._metric:
            errors.append("metric is required")
        if not self._market:
            errors.append("market is required")
        if not self._conditions:
            errors.append("at least one condition is required")

        if errors:
            raise ValueError(f"Cannot build strategy: {'; '.join(errors)}")

        conditions = tuple(
            Condition(field=c["field"], op=c["op"], value=c["value"])
            for c in self._conditions
        )

        strategy = Strategy(
            name=self._name,
            metric=self._metric,
            market=self._market,
            conditions=conditions,
            logic=self._logic,
            direction=self._direction,
            min_odds=self._min_odds,
        )

        logger.info("Built strategy: '%s' (%s, %s)", self._name, self._metric, self._direction)
        return strategy

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize builder state to a dictionary.

        Returns:
            Dict representation compatible with strategy JSON schema.
        """
        return {
            "name": self._name,
            "metric": self._metric,
            "market": self._market,
            "conditions": [
                {"field": c["field"], "op": c["op"], "value": c["value"]}
                for c in self._conditions
            ],
            "logic": self._logic,
            "direction": self._direction,
            "min_odds": self._min_odds,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string.

        Args:
            indent: JSON indentation level.

        Returns:
            JSON string representation.
        """
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> "StrategyBuilder":
        """Reconstruct builder from JSON string.

        Args:
            json_str: JSON string (single strategy object).

        Returns:
            Populated StrategyBuilder instance.
        """
        data = json.loads(json_str)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyBuilder":
        """Build from a dictionary (e.g., UI form submission).

        Args:
            data: Dict with strategy parameters.

        Returns:
            Populated StrategyBuilder instance.
        """
        builder = cls()

        if "name" in data:
            builder.set_name(data["name"])
        if "metric" in data:
            builder.set_metric(data["metric"])
        if "market" in data:
            builder.set_market(data["market"])
        if "direction" in data:
            builder.set_direction(data["direction"])
        if "logic" in data:
            builder.set_logic(data["logic"])
        if "min_odds" in data:
            builder.set_min_odds(float(data["min_odds"]))

        for cond in data.get("conditions", []):
            builder.add_condition(
                field=cond["field"],
                op=cond["op"],
                value=float(cond["value"]),
            )

        return builder
