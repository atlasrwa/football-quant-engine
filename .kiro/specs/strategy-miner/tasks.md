# Tasks: Automated Strategy Mining & Hypothesis Generator

## References
- #[[file:.kiro/specs/strategy-miner/requirements.md]]
- #[[file:.kiro/specs/strategy-miner/design.md]]

---

## Phase 1: Models & Multi-Market Foundation

### Task 1: Define mining data models
- [ ] Create `src/models/mining.py` with `MarketType` enum, `FormulaOperator` enum, `ComparisonOperator` enum.
- [ ] Implement `FeatureFormula` frozen dataclass with `name`, `operand_a`, `operator`, `operand_b`, optional `operand_c`/`operator_b`, `rolling_window`, `market_relevance`.
- [ ] Implement `RuleCondition` frozen dataclass with `feature_name`, `operator`, `threshold`, and `evaluate(value)` method.
- [ ] Implement `HypothesisRule` frozen dataclass with `rule_id`, `conditions` tuple, `prediction`, `market`, `line`, and `evaluate(features_dict)` method.
- [ ] Implement `EvaluationMetrics` frozen dataclass with ROI, win rate, drawdown, p-value, N bets, CLV beat rate.
- [ ] Implement `MinedStrategyResult` dataclass with rule, IS/OOS metrics, formulas, metadata.
- [ ] Implement `MiningConfig` dataclass with all configurable parameters and validation.
- [ ] Write unit tests in `tests/test_mining/test_models.py` for all model construction, validation, and methods.

### Task 2: Extend Match model with optional stats fields
- [ ] Add optional fields to `src/models/match.py`: shots, shots_on_target, shots_blocked, corners, fouls, yellow/red cards, offsides, crosses, through_balls, possession_pct, defensive_line_height, total_corners, total_cards, total_offsides, closing odds.
- [ ] Ensure all new fields default to `None` (backward-compatible).
- [ ] Update `src/ingestion/provider.py` `MockProvider._record_to_match()` to parse extended stats when present.
- [ ] Update `src/ingestion/pipeline.py` `_parse_records()` to map extended FootyStats fields.
- [ ] Write tests verifying backward compatibility (existing tests still pass) and extended field parsing.

### Task 3: Create market configuration module
- [ ] Create `src/mining/__init__.py`.
- [ ] Implement `src/mining/markets.py` with `MARKET_CONFIGS` dict mapping `MarketType` to lines, outcome field, and relevant metrics.
- [ ] Implement `resolve_outcome(match, market, line) -> str` function returning "OVER" or "UNDER".
- [ ] Implement `get_market_odds(match, market, prediction) -> Optional[float]` for odds lookup.
- [ ] Write tests for outcome resolution across all markets and lines, including edge cases (exact line hit, missing data).

---

## Phase 2: Feature Combinator

### Task 4: Implement raw metric extractor
- [ ] Create `src/mining/combinator.py` with `FeatureCombinator` class.
- [ ] Implement `extract_raw_metrics(match) -> Dict[str, float]` extracting all raw per-match metrics into a flat dict.
- [ ] Handle home/away aggregation: generate both `home_*`, `away_*`, and `total_*` variants.
- [ ] Handle missing values: return `None` for unavailable metrics, skip in downstream computations.
- [ ] Write tests with synthetic matches covering present/missing/zero metrics.

### Task 5: Implement composite formula generation
- [ ] Implement `generate_formulas(market: MarketType, max_features: int) -> List[FeatureFormula]`.
- [ ] Generate 2-operand composites: all valid `(A, operator, B)` combinations for market-relevant metrics.
- [ ] Generate 3-operand composites: `(A op B) op2 C` for high-signal combinations.
- [ ] Filter out degenerate formulas (division by zero-risk, identity operations like `A / A`).
- [ ] Assign `market_relevance` to each formula based on the metrics used.
- [ ] Enforce `max_features` cap (rank by market relevance, prefer simpler 2-operand over 3-operand).
- [ ] Write tests verifying formula count bounds, degenerate filtering, and market assignment.

### Task 6: Implement feature computation engine
- [ ] Implement `compute_features(matches: List[Match], formulas: List[FeatureFormula]) -> Dict[int, Dict[str, float]]` returning per-match feature vectors.
- [ ] Apply each formula to each match using extracted raw metrics.
- [ ] Compute rolling averages over configurable window using only prior matches (no look-ahead).
- [ ] Implement z-score normalization using training-set statistics only.
- [ ] Drop zero-variance features.
- [ ] Write tests verifying rolling computation order, normalization, look-ahead prevention, and missing data handling.

---

## Phase 3: Hypothesis Generator

### Task 7: Implement threshold sweep engine
- [ ] Create `src/mining/generator.py` with `HypothesisGenerator` class.
- [ ] Implement `compute_thresholds(feature_values: List[float], percentiles: Tuple[int,...]) -> List[float]` computing percentile-based thresholds from training data.
- [ ] Write tests verifying correct percentile computation, edge cases (all-same values, NaN handling).

### Task 8: Implement 1-condition rule generation
- [ ] Implement `generate_depth_1(features, thresholds, market, lines) -> List[HypothesisRule]`.
- [ ] For each feature × threshold × operator (>, <) × prediction (OVER, UNDER) × line, emit a rule.
- [ ] Assign deterministic `rule_id` via hashing canonical condition representation.
- [ ] Write tests verifying correct count, rule_id uniqueness, and condition content.

### Task 9: Implement multi-condition rule generation (depth 2-3)
- [ ] Implement `generate_depth_2(...)` and `generate_depth_3(...)` building compound rules.
- [ ] Use canonical ordering (sorted by feature_name) for deduplication.
- [ ] Implement deduplication via set of rule_id hashes.
- [ ] Enforce `max_hypotheses_per_market` cap — stop generation once reached.
- [ ] Write tests for deduplication correctness, cap enforcement, and depth-3 structure.

### Task 10: Implement full hypothesis generation pipeline
- [ ] Implement `generate_all(features_matrix, market, config) -> List[HypothesisRule]` orchestrating depth 1 → 2 → 3.
- [ ] Log progress (hypotheses generated count) at INFO level.
- [ ] Write integration test running full generation with small feature set, verifying bounds.

---

## Phase 4: Strategy Evaluator

### Task 11: Implement single-hypothesis evaluator
- [ ] Create `src/mining/evaluator.py` with `StrategyEvaluator` class.
- [ ] Implement `evaluate_hypothesis(rule: HypothesisRule, feature_matrix: Dict, matches: List[Match]) -> EvaluationMetrics`.
- [ ] For each match: evaluate rule conditions against features, if triggered record bet via BetLogger.
- [ ] Use `MetricsAggregator.compute()` on collected bet records.
- [ ] Compute CLV beat rate by comparing signal odds vs closing odds where available.
- [ ] Write tests with known outcomes verifying correct bet placement, metric computation, and CLV.

### Task 12: Implement batch evaluator with IS/OOS protocol
- [ ] Implement `evaluate_batch(rules: List[HypothesisRule], matches_is: List[Match], matches_oos: List[Match], features_is: Dict, features_oos: Dict) -> List[Tuple[HypothesisRule, EvaluationMetrics, EvaluationMetrics]]`.
- [ ] Precompute feature matrices for both seasons before evaluation loop.
- [ ] Evaluate each hypothesis against IS then OOS sequentially.
- [ ] Log progress (% evaluated) at INFO level.
- [ ] Write tests verifying IS/OOS separation, no cross-contamination.

### Task 13: Implement parallel evaluation support
- [ ] Add `n_workers` parameter to `evaluate_batch`.
- [ ] When `n_workers > 1`, use `multiprocessing.Pool` with configurable chunk_size.
- [ ] Ensure all data passed to workers is pickle-serializable (frozen dataclasses, numpy arrays).
- [ ] Write test confirming parallel results match single-threaded results.

---

## Phase 5: Statistical Filter

### Task 14: Implement cascading statistical filter
- [ ] Create `src/mining/filter.py` with `StatisticalFilter` class.
- [ ] Implement `apply(results: List[Tuple[rule, is_metrics, oos_metrics]], config: MiningConfig) -> List[MinedStrategyResult]`.
- [ ] Stage 1: Discard rules with OOS `total_bets < min_bets`.
- [ ] Stage 2: Discard rules with OOS `net_roi_pct <= min_roi_pct`.
- [ ] Stage 3: Discard rules with OOS `p_value >= max_p_value`.
- [ ] Stage 4: Discard rules with OOS `clv_beat_rate <= min_clv_beat_rate` (skip if CLV unavailable).
- [ ] Log elimination count at each stage.
- [ ] Write tests with synthetic results covering pass/fail at each stage boundary.

### Task 15: Implement result serialization
- [ ] Implement `serialize_result(result: MinedStrategyResult) -> Dict` for JSON output.
- [ ] Implement `save_results(results: List[MinedStrategyResult], output_dir: Path)` appending to `mined_strategies.jsonl`.
- [ ] Implement `format_mining_summary(results, filter_stats) -> str` for terminal output.
- [ ] Write tests verifying JSON round-trip, JSONL append behavior, and summary formatting.

---

## Phase 6: CLI Integration & End-to-End Testing

### Task 16: Implement CLI `mine` subcommand
- [ ] Add `mine` subcommand to `src/cli.py` with all arguments per FR-5.1.
- [ ] Wire subcommand to orchestrate: ingest → combine features → generate hypotheses → evaluate → filter → output.
- [ ] Report progress per FR-5.2 (feature count, hypotheses count, evaluation %, filter results).
- [ ] Write CLI tests verifying argument parsing, help output, and error handling.

### Task 17: Create extended test fixtures
- [ ] Create `tests/fixtures/4759_2023_extended.json` with 64+ matches including full stats (shots, corners, cards, offsides, crosses, through_balls, possession, line height).
- [ ] Create `tests/fixtures/4759_2024_extended.json` as OOS season data (64+ matches).
- [ ] Ensure fixtures include closing odds for CLV calculation testing.
- [ ] Verify fixtures load correctly through existing ingestion pipeline.

### Task 18: End-to-end integration test
- [ ] Write `tests/test_mining/test_integration.py` running full mining pipeline with fixture data.
- [ ] Assert: pipeline completes without error.
- [ ] Assert: feature generation produces expected formula count.
- [ ] Assert: hypothesis count respects max_hypotheses cap.
- [ ] Assert: filter eliminates rules that don't meet criteria.
- [ ] Assert: surviving rules have correct MinedStrategyResult structure.
- [ ] Assert: determinism — same inputs produce same outputs.

### Task 19: Run full test suite and verify
- [ ] Run `pytest tests/` and confirm all existing + new tests pass.
- [ ] Verify no regressions in ingestion, features, or backtest modules.
- [ ] Verify mining module tests cover all data structures, combinators, generators, evaluators, and filters.
- [ ] Mark all tasks complete.
