# Tasks: Proprietary x-Metric Suite (xC, xB, xO)

#[[file:design.md]]

## Phase 1: Foundation & Dependencies

- [x] Task 1: Add `pandas` to `pyproject.toml` dependencies
- [x] Task 2: Create `src/engine/__init__.py` with module exports
- [x] Task 3: Create `src/engine/xmetrics.py` — `XMetricCoefficients` dataclass and `XMetricEngine` class skeleton

## Phase 2: Vectorized x-Metric Formulas

- [x] Task 4: Implement `XMetricEngine.compute_xC()` — vectorized corner pressure formula
  - Input: DataFrame with `shots_off_target_*`, `attacks_*`, `dangerous_attacks_*`, `corners_avg_against_*`
  - Output: DataFrame with `home_xC`, `away_xC` columns added
  - Guards: division-by-zero on `attacks`, NaN propagation for missing fields

- [x] Task 5: Implement `XMetricEngine.compute_xB()` — vectorized booking intensity formula
  - Input: DataFrame with `fouls_*`, `cards_per_match_*`, `referee_cards_per_match`, `possession_*`, `xg_against_*`
  - Output: DataFrame with `home_xB`, `away_xB` columns added
  - Proxy: `opponent_dribbles_faced ≈ xg_against * 3.5`

- [x] Task 6: Implement `XMetricEngine.compute_xO()` — vectorized offsides engine formula
  - Input: DataFrame with `offsides_*`, `ppda_*`
  - Output: DataFrame with `home_xO`, `away_xO` columns added
  - Proxy: `high_line_index = 1 / ppda`, league baseline = column mean

- [x] Task 7: Implement `XMetricEngine.compute_all()` — chain all three

## Phase 3: Strategy Evaluator

- [x] Task 8: Create `src/engine/evaluator.py` — `Condition`, `Strategy`, `Signal` dataclasses
- [x] Task 9: Implement `StrategyEvaluator.load_strategies()` — parse + validate JSON
- [x] Task 10: Implement `StrategyEvaluator.evaluate()` — safe condition dispatch (no eval)
  - Operator map: `{">": operator.gt, "<": operator.lt, ...}`
  - Logic combinator: "and" = all conditions True, "or" = any condition True
  - Edge calculation: mean distance from threshold across matched conditions

## Phase 4: Walk-Forward Backtest Engine

- [x] Task 11: Create `src/engine/backtest.py` — `XBacktestConfig`, `XBetRecord` dataclasses
- [x] Task 12: Implement `XMetricBacktester._generate_folds()` — sliding window indices
- [x] Task 13: Implement `XMetricBacktester._run_fold()` — evaluate signals, record bets
- [x] Task 14: Implement `XMetricBacktester.run()` — orchestrate folds, compute aggregate metrics
  - Metrics: Net ROI %, CLV %, Total P&L, Max Drawdown
  - Output: Compatible with existing `BacktestResult` pattern

## Phase 5: Statistical Validator

- [x] Task 15: Create `src/engine/validator.py` — `ValidationCriteria`, `ValidationVerdict`
- [x] Task 16: Implement `StatisticalValidator._t_test()` — 1-sample 1-tailed t-test (scipy)
- [x] Task 17: Implement `StatisticalValidator._cohens_d()` — effect size
- [x] Task 18: Implement `StatisticalValidator._confidence_interval()` — 95% CI
- [x] Task 19: Implement `StatisticalValidator.validate()` — orchestrate checks, produce verdict

## Phase 6: Tests

- [x] Task 20: Create `tests/test_xmetrics.py` — unit tests for all three x-Metric formulas
  - Test vectorized computation correctness
  - Test division-by-zero handling
  - Test NaN propagation
  - Test with empty DataFrame

- [x] Task 21: Create `tests/test_evaluator.py` — unit tests for strategy evaluation
  - Test JSON loading and validation
  - Test each operator
  - Test "and"/"or" logic
  - Test edge calculation
  - Test invalid strategy rejection

- [x] Task 22: Create `tests/test_xbacktest.py` — unit tests for walk-forward engine
  - Test fold generation
  - Test single fold execution
  - Test full backtest with synthetic data
  - Test look-ahead freedom

- [x] Task 23: Create `tests/test_validator.py` — unit tests for statistical validator
  - Test passing/failing verdicts
  - Test insufficient sample size rejection
  - Test t-test correctness against known values
  - Test Cohen's d and CI

## Phase 7: Integration

- [x] Task 24: Verify all tests pass and fix any issues
