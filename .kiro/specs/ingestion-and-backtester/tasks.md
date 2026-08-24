# Tasks: Ingestion & Backtester

## References
- #[[file:.kiro/specs/ingestion-and-backtester/requirements.md]]
- #[[file:.kiro/specs/ingestion-and-backtester/design.md]]

---

## Phase 1: Project Scaffolding & Data Models

### Task 1: Initialize project structure and dependencies ✅
- [x] Create `pyproject.toml` with project metadata and dependencies (`httpx`, `numpy`, `scipy`, `pydantic`).
- [x] Create directory skeleton: `src/ingestion/`, `src/features/`, `src/backtest/`, `src/models/`, `tests/fixtures/`, `data/raw/`, `data/features/`, `data/results/`, `data/errors/`.
- [x] Add `__init__.py` files to all `src/` packages.
- [x] Add `.gitkeep` to empty `data/` subdirectories.

### Task 2: Define core data models ✅
- [x] Implement `src/models/match.py` — `Match` dataclass per design spec.
- [x] Implement `src/models/features.py` — `MatchFeatures` dataclass.
- [x] Implement `src/models/config.py` — `StrategyConfig` dataclass with defaults.
- [x] Implement `src/models/results.py` — `BetRecord`, `FoldResult`, `BacktestResult` dataclasses.

---

## Phase 2: Mock Data & Ingestion ✅

### Task 3: Create local mock fixture data ✅
- [x] Create `tests/fixtures/4759_2023.json` with 50+ synthetic match records matching the FootyStats response schema.
- [x] Include edge cases: missing referee, zero xG, high-scoring matches (6+ goals).

### Task 4: Implement MockProvider and DataProvider protocol ✅
- [x] Implement `DataProvider` protocol in `src/ingestion/__init__.py`.
- [x] Implement `MockProvider` in `src/ingestion/provider.py` loading from `tests/fixtures/`.
- [x] Implement `SyntheticMatchGenerator` in `tests/conftest.py` for parameterized test data.

### Task 5: Implement JSON cache manager ✅
- [x] Implement `src/ingestion/cache.py` — `CacheManager` with `get()`, `put()`, `exists()`, `clear()`.
- [x] File naming: `{league_id}_{season}_{match_id}.json`.
- [x] Add logging for cache hits/misses.

### Task 6: Implement schema validator ✅
- [x] Implement `src/ingestion/validator.py` — `SchemaValidator` checking required fields.
- [x] On failure, append error record to `data/errors/validation_errors.jsonl`.
- [x] Return tuple of `(valid_matches, error_count)`.

### Task 7: Implement FootyStats API client ✅
- [x] Implement `src/ingestion/client.py` — `FootyStatsClient` with `httpx.AsyncClient`.
- [x] Add rate limiting (1 req/sec default), exponential backoff (max 3 retries).
- [x] Support `key=example` default for sandbox mode.

### Task 8: Implement ingestion pipeline orchestrator ✅
- [x] Implement `src/ingestion/pipeline.py` — `IngestionPipeline` composing client → cache → validator.
- [x] Accept `--force-refresh` flag to bypass cache.
- [x] Return `List[Match]` of validated records.

---

## Phase 3: Feature Engineering ✅

### Task 9: Implement xG Efficiency Delta calculator ✅
- [x] Implement `src/features/xg_efficiency.py` — `XGEfficiencyCalculator`.
- [x] Compute per-match delta: `(actual - xg) / xg`, handling `xg == 0` → `0.0`.
- [x] Compute rolling mean over configurable window (default 5).
- [x] Ensure calculation respects chronological order (no look-ahead).

### Task 10: Implement Rolling Form calculator ✅
- [x] Implement `src/features/rolling_form.py` — `RollingFormCalculator`.
- [x] Score: W=3, D=1, L=0 over last N matches (default 6).
- [x] Normalize to 0–1: `score / (3 * N)`.
- [x] Handle teams with fewer than N historical matches (use available history).

### Task 11: Implement Referee Volatility Index calculator ✅
- [x] Implement `src/features/referee_volatility.py` — `RefereeVolatilityCalculator`.
- [x] Compute std dev of total goals per referee across all their officiated matches.
- [x] Fallback to league mean volatility when referee has < 5 matches.
- [x] Handle missing referee field gracefully (use league mean).

### Task 12: Implement Feature Assembler ✅
- [x] Implement `src/features/assembler.py` — `FeatureAssembler`.
- [x] Compose xG, form, and referee calculators into a single pipeline.
- [x] Output `List[MatchFeatures]` sorted chronologically.
- [x] Log feature completeness stats (% of matches with all features populated).

---

## Phase 4: Backtest Execution ✅

### Task 13: Implement Volatility-Adjusted Staking calculator ✅
- [x] Implement `src/backtest/staking.py` — `StakingCalculator`.
- [x] Compute match variance from rolling std dev of total goals (window=10).
- [x] Stake formula: `base_stake * (1 / (1 + match_variance))`.
- [x] Apply floor/cap constraints from `StrategyConfig`.

### Task 14: Implement Signal Generator ✅
- [x] Implement `src/backtest/signal.py` — `SignalGenerator`.
- [x] Accept feature vector, output prediction ("OVER"/"UNDER") with estimated edge.
- [x] MVP strategy: simple threshold on combined feature heuristic (to be replaced with ML model later).
- [x] Only emit signal when `edge >= min_edge_threshold`.

### Task 15: Implement Bet Logger ✅
- [x] Implement `src/backtest/bet_log.py` — `BetLogger`.
- [x] Record each bet as `BetRecord` with match_id, prediction, actual, odds, stake, P&L.
- [x] Support serialization to JSON lines format.

### Task 16: Implement Metrics Aggregator ✅
- [x] Implement `src/backtest/metrics.py` — `MetricsAggregator`.
- [x] Compute Net ROI %: `(total_profit / total_staked) * 100`.
- [x] Compute Win Rate %: `(wins / total_bets) * 100`.
- [x] Compute Max Drawdown %: peak-to-trough on cumulative P&L curve.
- [x] Compute p-value: `scipy.stats.ttest_1samp` on per-bet returns vs 0.

### Task 17: Implement Walk-Forward Engine ✅
- [x] Implement `src/backtest/engine.py` — `WalkForwardEngine`.
- [x] Accept `List[MatchFeatures]` + `StrategyConfig`.
- [x] Iterate folds: slice train/test windows, advance by step_size.
- [x] Per fold: generate signals → compute stakes → log bets → aggregate metrics.
- [x] Return complete `BacktestResult`.
- [x] Implement `src/backtest/cross_validation.py` — `TemporalCrossValidator` for fold splitting.

---

## Phase 5: Integration & Output ✅

### Task 18: Implement CLI entry point ✅
- [x] Create `src/cli.py` with CLI interface (argparse).
- [x] Subcommands: `ingest`, `features`, `backtest`, `run` (full pipeline).
- [x] Accept config overrides via CLI flags or JSON config file.

### Task 19: Implement JSON result serialization ✅
- [x] Serialize `BacktestResult` to `data/results/backtest_YYYYMMDD_HHMMSS.json`.
- [x] Include strategy config, aggregate metrics, fold breakdowns, and full bet log.
- [x] Pretty-print summary to stdout after execution.

### Task 20: End-to-end integration test with mock data ✅
- [x] Wire full pipeline: MockProvider → FeatureAssembler → WalkForwardEngine.
- [x] Run against `tests/fixtures/4759_2023.json` fixture.
- [x] Assert result structure is complete and metrics are within sane bounds.
- [x] Verify determinism: two runs with same seed produce identical output.
