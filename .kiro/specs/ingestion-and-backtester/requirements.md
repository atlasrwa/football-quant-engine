# Requirements: Ingestion & Backtester

## Overview

This spec defines the functional requirements for the Football Quant Engine's core pipeline: ingesting raw match data from FootyStats, computing proprietary mixed features, and executing a walk-forward backtest with Volatility-Adjusted Staking for Over/Under markets.

---

## FR-1: FootyStats API Data Ingestion & Local JSON Caching

### FR-1.1: API Client
- The system SHALL provide a client module that fetches match data from the FootyStats API (`https://api.football-data-api.com/`).
- The client SHALL accept a configurable API key, defaulting to `example` for the public sandbox endpoint.
- The client SHALL support fetching league season match lists and individual match detail endpoints.
- The client SHALL handle HTTP errors (4xx, 5xx) with exponential backoff retries (max 3 attempts).
- The client SHALL enforce a configurable rate limit (default: 1 request/second) to respect API quotas.

### FR-1.2: Local JSON Cache
- The system SHALL persist all raw API responses as JSON files in a local cache directory (`data/raw/`).
- Each cached file SHALL be named using the pattern `{league_id}_{season}_{match_id}.json`.
- The system SHALL skip API calls for matches that already exist in the local cache (cache-first strategy).
- The cache SHALL support a `--force-refresh` flag to bypass the cache and re-fetch from the API.
- The system SHALL log cache hits and misses with timestamps.

### FR-1.3: Data Validation
- The system SHALL validate ingested JSON against a minimum schema (required fields: `id`, `homeGoals`, `awayGoals`, `date_unix`, `xg`, `team_a_xg`, `team_b_xg`).
- Invalid or incomplete records SHALL be logged to `data/errors/validation_errors.jsonl` and excluded from downstream processing.

---

## FR-2: Raw Feature Calculation

### FR-2.1: xG Efficiency Delta
- The system SHALL compute `xG_efficiency_delta` per team per match as: `(actual_goals - expected_goals) / expected_goals`.
- When `expected_goals == 0`, the delta SHALL be set to `0.0`.
- The system SHALL compute a rolling mean of `xG_efficiency_delta` over a configurable window (default: 5 matches).

### FR-2.2: Rolling Form
- The system SHALL compute a `rolling_form` score per team as the points earned (W=3, D=1, L=0) over the last N matches (configurable, default N=6).
- The system SHALL normalize rolling form to a 0–1 scale by dividing by `3 * N`.

### FR-2.3: Referee Volatility Index
- The system SHALL compute a `referee_volatility_index` per referee as the standard deviation of total match goals across all officiated matches in the dataset.
- If a referee has fewer than 5 officiated matches in the dataset, the index SHALL fall back to the league-wide mean volatility.

### FR-2.4: Combined Feature Vector
- For each match, the system SHALL output a feature vector containing:
  - `home_xg_eff_delta_rolling` (float)
  - `away_xg_eff_delta_rolling` (float)
  - `home_rolling_form` (float, 0–1)
  - `away_rolling_form` (float, 0–1)
  - `referee_volatility_index` (float)
  - `total_goals` (int, target variable)
  - `over_under_line` (float, e.g., 2.5)

---

## FR-3: Volatility-Adjusted Staking

### FR-3.1: Match Variance Estimation
- The system SHALL estimate per-match goal variance using the rolling standard deviation of total goals for both participating teams over the last N matches (configurable, default N=10).
- Combined match variance SHALL be computed as: `(home_team_goal_std + away_team_goal_std) / 2`.

### FR-3.2: Stake Sizing
- The system SHALL compute stake size inversely proportional to combined match variance: `stake = base_stake * (1 / (1 + match_variance))`.
- `base_stake` SHALL be configurable (default: 1.0 unit).
- The system SHALL cap maximum stake at `base_stake * max_stake_multiplier` (default multiplier: 3.0).
- The system SHALL floor minimum stake at `base_stake * min_stake_multiplier` (default multiplier: 0.25).

### FR-3.3: Signal Threshold
- A bet SHALL only be placed when the model's predicted edge exceeds a configurable `min_edge_threshold` (default: 0.05, i.e., 5%).

---

## FR-4: Backtest Execution

### FR-4.1: Walk-Forward Structure
- The system SHALL execute a walk-forward backtest with configurable `train_window` and `test_window` sizes (default: 100 train / 20 test matches).
- The walk-forward SHALL advance by `step_size` matches per fold (default: 20).
- At each fold, the model SHALL be re-fitted on the training window before predicting on the test window.

### FR-4.2: Performance Metrics
- The system SHALL track and report the following metrics across all folds:
  - **Net ROI %**: `(total_profit / total_staked) * 100`
  - **Win Rate %**: `(winning_bets / total_bets) * 100`
  - **Max Drawdown %**: Maximum peak-to-trough decline in cumulative P&L as a percentage of peak.
  - **p-value**: One-sample t-test of per-bet returns against a null hypothesis of zero mean return.

### FR-4.3: Backtest Output
- The system SHALL output a structured `BacktestResult` object containing all metrics, per-fold breakdowns, and the full bet log.
- The bet log SHALL include: `match_id`, `date`, `prediction`, `actual_outcome`, `odds`, `stake`, `profit_loss`.
- Results SHALL be serializable to JSON for downstream consumption.

### FR-4.4: Reproducibility
- The backtest SHALL accept a `random_seed` parameter for any stochastic components.
- Given identical inputs and configuration, the backtest SHALL produce deterministic, reproducible results.

---

## Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-1 | The pipeline SHALL process 1,000 matches in under 30 seconds on a single-core machine. |
| NFR-2 | All monetary/probability calculations SHALL use 64-bit floating point precision. |
| NFR-3 | The system SHALL be implemented in Python 3.11+ with no paid dependencies. |
| NFR-4 | The system SHALL provide structured logging (JSON format) at DEBUG, INFO, WARN, ERROR levels. |
| NFR-5 | All modules SHALL be independently testable with mock data. |
