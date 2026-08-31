"""Unit tests for the strategy evaluator."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.engine.analysis.evaluator import Condition, Signal, Strategy, StrategyEvaluator


class TestStrategyEvaluator:
    """Tests for StrategyEvaluator."""

    def _make_strategy(self, **overrides) -> Strategy:
        """Factory for a Strategy with sensible defaults."""
        defaults = {
            "name": "Test Strategy",
            "metric": "xC",
            "market": "corners_over_under",
            "conditions": (Condition(field="home_xC", op=">", value=2.0),),
            "logic": "and",
            "direction": "OVER",
            "min_odds": 1.50,
        }
        defaults.update(overrides)
        return Strategy(**defaults)

    def _make_df(self, n: int = 10) -> pd.DataFrame:
        """Create a DataFrame with x-Metric columns and odds."""
        rng = np.random.default_rng(99)
        return pd.DataFrame({
            "date_unix": np.arange(n) * 86400,
            "home_xC": rng.uniform(1.5, 3.5, n),
            "away_xC": rng.uniform(1.5, 3.5, n),
            "home_xB": rng.uniform(5.0, 15.0, n),
            "away_xB": rng.uniform(5.0, 15.0, n),
            "home_xO": rng.uniform(1.0, 5.0, n),
            "away_xO": rng.uniform(1.0, 5.0, n),
            "over_odds": rng.uniform(1.60, 2.40, n),
            "under_odds": rng.uniform(1.60, 2.40, n),
        })

    def test_evaluate_returns_signals(self):
        """Evaluate produces signals for matching rows."""
        evaluator = StrategyEvaluator()
        df = self._make_df(20)
        # Force some rows to match
        df.loc[0, "home_xC"] = 3.0
        df.loc[0, "over_odds"] = 2.0
        strategy = self._make_strategy()

        signals = evaluator.evaluate(df, [strategy])
        assert isinstance(signals, list)
        assert all(isinstance(s, Signal) for s in signals)

    def test_evaluate_filters_by_min_odds(self):
        """Signals are not generated when odds are below min_odds."""
        evaluator = StrategyEvaluator()
        df = pd.DataFrame({
            "home_xC": [3.0, 3.0],
            "over_odds": [1.40, 2.00],
        })
        strategy = self._make_strategy(min_odds=1.50)

        signals = evaluator.evaluate(df, [strategy])
        # Only the second row meets min_odds
        matching = [s for s in signals if s.match_index == 1]
        low_odds = [s for s in signals if s.match_index == 0]
        assert len(low_odds) == 0
        assert len(matching) == 1

    def test_evaluate_and_logic(self):
        """AND logic requires all conditions to match."""
        evaluator = StrategyEvaluator()
        df = pd.DataFrame({
            "home_xC": [3.0, 3.0, 1.0],
            "away_xC": [2.5, 1.0, 2.5],
            "over_odds": [2.0, 2.0, 2.0],
        })
        strategy = self._make_strategy(
            conditions=(
                Condition(field="home_xC", op=">", value=2.0),
                Condition(field="away_xC", op=">", value=2.0),
            ),
            logic="and",
        )

        signals = evaluator.evaluate(df, [strategy])
        # Only row 0 matches both conditions
        assert len(signals) == 1
        assert signals[0].match_index == 0

    def test_evaluate_or_logic(self):
        """OR logic requires any condition to match."""
        evaluator = StrategyEvaluator()
        df = pd.DataFrame({
            "home_xC": [3.0, 1.0, 1.0],
            "away_xC": [1.0, 2.5, 1.0],
            "over_odds": [2.0, 2.0, 2.0],
        })
        strategy = self._make_strategy(
            conditions=(
                Condition(field="home_xC", op=">", value=2.0),
                Condition(field="away_xC", op=">", value=2.0),
            ),
            logic="or",
        )

        signals = evaluator.evaluate(df, [strategy])
        # Rows 0 and 1 match (at least one condition each)
        indices = {s.match_index for s in signals}
        assert 0 in indices
        assert 1 in indices
        assert 2 not in indices

    def test_all_operators(self):
        """All supported operators work correctly."""
        evaluator = StrategyEvaluator()
        df = pd.DataFrame({
            "val": [5.0],
            "over_odds": [2.0],
        })

        test_cases = [
            (">", 4.0, True),
            (">", 5.0, False),
            ("<", 6.0, True),
            ("<", 5.0, False),
            (">=", 5.0, True),
            (">=", 6.0, False),
            ("<=", 5.0, True),
            ("<=", 4.0, False),
            ("==", 5.0, True),
            ("==", 4.0, False),
            ("!=", 4.0, True),
            ("!=", 5.0, False),
        ]

        for op, value, should_match in test_cases:
            strategy = self._make_strategy(
                conditions=(Condition(field="val", op=op, value=value),),
            )
            signals = evaluator.evaluate(df, [strategy])
            assert (len(signals) > 0) == should_match, f"Failed for op={op}, value={value}"

    def test_load_strategies_from_file(self):
        """Load strategies from a JSON file."""
        evaluator = StrategyEvaluator()
        data = [
            {
                "name": "High xC Over",
                "metric": "xC",
                "market": "corners_over_under",
                "conditions": [{"field": "home_xC", "op": ">", "value": 2.5}],
                "logic": "and",
                "direction": "OVER",
                "min_odds": 1.70,
            }
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = Path(f.name)

        strategies = evaluator.load_strategies(path)
        assert len(strategies) == 1
        assert strategies[0].name == "High xC Over"
        assert strategies[0].conditions[0].field == "home_xC"
        assert strategies[0].min_odds == 1.70

        path.unlink()

    def test_load_strategies_single_object(self):
        """Load a single strategy (not wrapped in array)."""
        evaluator = StrategyEvaluator()
        data = {
            "name": "Single",
            "metric": "xB",
            "market": "cards",
            "conditions": [{"field": "home_xB", "op": ">=", "value": 10.0}],
            "logic": "and",
            "direction": "OVER",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = Path(f.name)

        strategies = evaluator.load_strategies(path)
        assert len(strategies) == 1
        assert strategies[0].name == "Single"

        path.unlink()

    def test_invalid_operator_raises(self):
        """Invalid operator in strategy raises ValueError."""
        evaluator = StrategyEvaluator()
        data = [{
            "name": "Bad",
            "metric": "xC",
            "market": "corners",
            "conditions": [{"field": "home_xC", "op": "~=", "value": 1.0}],
            "logic": "and",
            "direction": "OVER",
        }]

        with pytest.raises(ValueError, match="Invalid operator"):
            evaluator.load_strategies_from_list(data)

    def test_invalid_direction_raises(self):
        """Invalid direction raises ValueError."""
        evaluator = StrategyEvaluator()
        data = [{
            "name": "Bad",
            "metric": "xC",
            "market": "corners",
            "conditions": [{"field": "home_xC", "op": ">", "value": 1.0}],
            "logic": "and",
            "direction": "SIDEWAYS",
        }]

        with pytest.raises(ValueError, match="Invalid direction"):
            evaluator.load_strategies_from_list(data)

    def test_invalid_logic_raises(self):
        """Invalid logic combinator raises ValueError."""
        evaluator = StrategyEvaluator()
        data = [{
            "name": "Bad",
            "metric": "xC",
            "market": "corners",
            "conditions": [{"field": "home_xC", "op": ">", "value": 1.0}],
            "logic": "xor",
            "direction": "OVER",
        }]

        with pytest.raises(ValueError, match="Invalid logic"):
            evaluator.load_strategies_from_list(data)

    def test_empty_conditions_raises(self):
        """Strategy with no conditions raises ValueError."""
        evaluator = StrategyEvaluator()
        data = [{
            "name": "Empty",
            "metric": "xC",
            "market": "corners",
            "conditions": [],
            "logic": "and",
            "direction": "OVER",
        }]

        with pytest.raises(ValueError, match="at least one condition"):
            evaluator.load_strategies_from_list(data)

    def test_missing_column_skips_strategy(self):
        """Strategy with missing DataFrame column produces no signals."""
        evaluator = StrategyEvaluator()
        df = pd.DataFrame({"other_col": [1.0, 2.0, 3.0], "over_odds": [2.0, 2.0, 2.0]})
        strategy = self._make_strategy()

        signals = evaluator.evaluate(df, [strategy])
        assert len(signals) == 0

    def test_nan_values_excluded(self):
        """NaN values in condition columns don't produce false matches."""
        evaluator = StrategyEvaluator()
        df = pd.DataFrame({
            "home_xC": [np.nan, 3.0, np.nan],
            "over_odds": [2.0, 2.0, 2.0],
        })
        strategy = self._make_strategy()

        signals = evaluator.evaluate(df, [strategy])
        # Only row 1 should match (non-NaN and > 2.0)
        assert len(signals) == 1
        assert signals[0].match_index == 1

    def test_back_lay_directions_never_fabricate_odds(self):
        """R10 regression: BACK/LAY strategies must suppress (NO_SIGNAL) rather
        than fabricate odds, since no odds column is mapped for those
        directions. Locks in current correct behavior of _get_odds_column /
        _get_odds_value so a future change can't silently reintroduce a
        synthetic-odds fallback (e.g. the old hardcoded 1.90) for BACK/LAY.
        """
        evaluator = StrategyEvaluator()
        df = pd.DataFrame({
            "home_xC": [3.0, 3.0],
            "over_odds": [2.0, 2.0],
            "under_odds": [2.0, 2.0],
        })

        for direction in ("BACK", "LAY"):
            strategy = self._make_strategy(direction=direction)
            assert evaluator._get_odds_column(direction) is None

            signals = evaluator.evaluate(df, [strategy])
            assert signals == [], (
                f"{direction} produced signals with no real odds column mapped "
                "— this would mean fabricated odds are back."
            )

    def test_edge_calculation(self):
        """Edge is computed as mean distance from threshold."""
        evaluator = StrategyEvaluator()
        df = pd.DataFrame({
            "home_xC": [4.0],  # threshold is 2.0, distance = |4-2|/|2| = 1.0
            "over_odds": [2.0],
        })
        strategy = self._make_strategy(
            conditions=(Condition(field="home_xC", op=">", value=2.0),),
        )

        signals = evaluator.evaluate(df, [strategy])
        assert len(signals) == 1
        assert signals[0].condition_strength == pytest.approx(1.0, rel=1e-6)
