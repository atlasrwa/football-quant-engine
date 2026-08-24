"""Strategy evaluator for x-Metric hypothesis testing.

Parses community strategy JSON definitions and evaluates conditions
against computed x-Metric columns without using eval()/exec().
"""

from __future__ import annotations

import json
import logging
import operator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Condition:
    """A single comparison condition on a DataFrame column."""

    field: str
    op: str
    value: float


@dataclass(frozen=True, slots=True)
class Strategy:
    """A complete betting strategy definition."""

    name: str
    metric: str
    market: str
    conditions: tuple[Condition, ...]
    logic: str  # "and" | "or"
    direction: str  # "OVER" | "UNDER" | "BACK" | "LAY"
    min_odds: float = 1.50


@dataclass(frozen=True, slots=True)
class Signal:
    """A generated betting signal for a specific match."""

    match_index: int
    strategy_name: str
    direction: str
    edge: float
    odds: float


class StrategyEvaluator:
    """Evaluate strategy conditions against DataFrames safely.

    Operators are dispatched via a static lookup table — no dynamic
    code evaluation is ever performed.
    """

    OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
        ">": operator.gt,
        "<": operator.lt,
        ">=": operator.ge,
        "<=": operator.le,
        "==": operator.eq,
        "!=": operator.ne,
    }

    VALID_DIRECTIONS = {"OVER", "UNDER", "BACK", "LAY"}
    VALID_LOGIC = {"and", "or"}

    def load_strategies(self, path: Path) -> List[Strategy]:
        """Load and validate strategies from a JSON file.

        Expected format: a JSON array of strategy objects, or a single object.
        """
        with open(path, "r") as f:
            data = json.load(f)

        if isinstance(data, dict):
            data = [data]

        strategies: List[Strategy] = []
        for i, raw in enumerate(data):
            try:
                strategy = self._parse_strategy(raw)
                strategies.append(strategy)
            except (KeyError, ValueError, TypeError) as e:
                raise ValueError(
                    f"Invalid strategy at index {i}: {e}"
                ) from e

        logger.info("Loaded %d strategies from %s", len(strategies), path)
        return strategies

    def load_strategies_from_list(self, data: List[dict]) -> List[Strategy]:
        """Load strategies from a list of dicts (already parsed JSON)."""
        strategies: List[Strategy] = []
        for i, raw in enumerate(data):
            try:
                strategy = self._parse_strategy(raw)
                strategies.append(strategy)
            except (KeyError, ValueError, TypeError) as e:
                raise ValueError(
                    f"Invalid strategy at index {i}: {e}"
                ) from e
        return strategies

    def evaluate(
        self, df: pd.DataFrame, strategies: List[Strategy]
    ) -> List[Signal]:
        """Evaluate all strategies against every row in the DataFrame.

        Returns a list of Signals for rows that satisfy strategy conditions
        and meet minimum odds requirements.
        """
        signals: List[Signal] = []

        for strategy in strategies:
            mask = self._evaluate_strategy_mask(df, strategy)
            if mask is None:
                continue

            # Apply min_odds filter
            odds_col = self._get_odds_column(strategy.direction)
            if odds_col and odds_col in df.columns:
                odds_mask = df[odds_col] >= strategy.min_odds
                mask = mask & odds_mask

            matching_indices = df.index[mask].tolist()

            for idx in matching_indices:
                edge = self._compute_edge(df.iloc[idx] if isinstance(idx, int) else df.loc[idx], strategy)
                odds = self._get_odds_value(df, idx, strategy.direction)
                # R03: Missing odds suppress signal — no synthetic betting opportunities
                if odds is None:
                    continue
                signals.append(
                    Signal(
                        match_index=idx,
                        strategy_name=strategy.name,
                        direction=strategy.direction,
                        edge=edge,
                        odds=odds,
                    )
                )

        logger.info(
            "Evaluated %d strategies → %d signals from %d matches",
            len(strategies),
            len(signals),
            len(df),
        )
        return signals

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _parse_strategy(self, raw: dict) -> Strategy:
        """Parse and validate a single strategy dict."""
        name = raw["name"]
        metric = raw["metric"]
        market = raw["market"]
        logic = raw.get("logic", "and")
        direction = raw["direction"]
        min_odds = raw.get("min_odds", 1.50)

        if direction not in self.VALID_DIRECTIONS:
            raise ValueError(f"Invalid direction: {direction}")
        if logic not in self.VALID_LOGIC:
            raise ValueError(f"Invalid logic: {logic}")

        conditions = []
        for cond_raw in raw["conditions"]:
            op = cond_raw["op"]
            if op not in self.OPERATORS:
                raise ValueError(f"Invalid operator: {op}")
            conditions.append(
                Condition(
                    field=cond_raw["field"],
                    op=op,
                    value=float(cond_raw["value"]),
                )
            )

        if not conditions:
            raise ValueError("Strategy must have at least one condition")

        return Strategy(
            name=name,
            metric=metric,
            market=market,
            conditions=tuple(conditions),
            logic=logic,
            direction=direction,
            min_odds=min_odds,
        )

    def _evaluate_strategy_mask(
        self, df: pd.DataFrame, strategy: Strategy
    ) -> pd.Series | None:
        """Build a boolean mask for rows matching strategy conditions."""
        masks: List[pd.Series] = []

        for cond in strategy.conditions:
            if cond.field not in df.columns:
                logger.warning(
                    "Strategy '%s': field '%s' not in DataFrame, skipping",
                    strategy.name,
                    cond.field,
                )
                return None

            op_func = self.OPERATORS[cond.op]
            col_values = df[cond.field]
            mask = col_values.apply(lambda x: op_func(x, cond.value) if pd.notna(x) else False)
            masks.append(mask)

        if not masks:
            return None

        if strategy.logic == "and":
            combined = masks[0]
            for m in masks[1:]:
                combined = combined & m
        else:  # "or"
            combined = masks[0]
            for m in masks[1:]:
                combined = combined | m

        return combined

    def _compute_edge(self, row: pd.Series, strategy: Strategy) -> float:
        """Compute edge as mean normalized distance from thresholds."""
        distances: List[float] = []

        for cond in strategy.conditions:
            if cond.field not in row.index:
                continue
            val = row[cond.field]
            if pd.isna(val):
                continue
            # Normalized distance from threshold
            if cond.value != 0:
                dist = abs(val - cond.value) / abs(cond.value)
            else:
                dist = abs(val)
            distances.append(dist)

        return float(np.mean(distances)) if distances else 0.0

    def _get_odds_column(self, direction: str) -> str | None:
        """Map direction to the odds column name."""
        if direction == "OVER":
            return "over_odds"
        elif direction == "UNDER":
            return "under_odds"
        return None

    def _get_odds_value(
        self, df: pd.DataFrame, idx: int, direction: str
    ) -> float | None:
        """Get the odds value for a specific row and direction.

        Returns None if odds are missing, NaN, or unavailable.
        Missing odds must never create a synthetic betting opportunity.
        """
        col = self._get_odds_column(direction)
        if col and col in df.columns:
            val = df.loc[idx, col] if idx in df.index else df.iloc[idx][col]
            if pd.notna(val) and float(val) > 1.0:
                return float(val)
        return None  # NO_SIGNAL — missing odds suppress signal
