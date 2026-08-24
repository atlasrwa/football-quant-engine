# Requirements: Automated Strategy Mining & Hypothesis Generator

## Overview

This spec defines the functional requirements for the Strategy Mining module — an automated system that programmatically discovers profitable betting strategies across four markets (Over/Under Goals, Total Corners, Total Cards, Total Offsides) by combining FootyStats raw metrics into composite features, generating multi-condition rule trees, evaluating them with walk-forward backtests, and filtering for statistical robustness.

---

## FR-1: Feature Combinator

### FR-1.1: Raw Metric Ingestion

- The system SHALL consume the following raw per-match metrics from FootyStats API responses:
  - `shots_total` (home/away total shots)
  - `shots_on_target` (home/away shots on target)
  - `shots_blocked` (home/away blocked shots)
  - `crosses_total` (home/away total crosses)
  - `fouls_committed` (home/away fouls)
  - `cards_yellow` / `cards_red` (home/away cards)
  - `corners_total` (home/away corners)
  - `offsides_total` (home/away offsides)
  - `through_balls` (home/away through balls attempted)
  - `defensive_line_height` (home/away average line height)
  - `possession_pct` (home/away possession percentage)
- All metrics SHALL be rate-normalized per 90 minutes when the source provides minutes played.
- Missing metrics SHALL default to `None` and be excluded from composite calculations involving them.

### FR-1.2: Composite Ratio Generation

- The system SHALL programmatically generate composite feature ratios by combining 2–3 raw metrics using the following operators:
  - Division: `A / B` (rate ratio)
  - Multiplication: `A * B` (interaction term)
  - Difference: `A - B` (differential)
  - Sum: `A + B` (aggregation)
- Each composite SHALL be identified by a unique `FeatureFormula` object encoding the operands and operator.
- The system SHALL generate composites relevant to each market:
  - **GOALS**: shots, shots_on_target, xG, crosses, through_balls
  - **CORNERS**: crosses, shots_blocked, possession_pct, defensive_line_height
  - **CARDS**: fouls_committed, cards_yellow, cards_red, referee history
  - **OFFSIDES**: through_balls, defensive_line_height, offsides_total
- The system SHALL produce rolling averages (configurable window, default 5 matches) for all composite features.
- The total number of generated composites SHALL be bounded by a configurable `max_features` parameter (default: 200) to prevent combinatorial explosion.

### FR-1.3: Feature Normalization

- All composite features SHALL be z-score normalized within their rolling window context.
- The system SHALL track feature statistics (mean, std) computed only on training data to prevent look-ahead bias.
- Features with zero variance across the training window SHALL be dropped automatically.

---

## FR-2: Hypothesis Generator

### FR-2.1: Market Type Support

- The system SHALL support four market types:
  - `GOALS` — Over/Under total match goals (lines: 0.5, 1.5, 2.5, 3.5, 4.5)
  - `CORNERS` — Over/Under total match corners (lines: 7.5, 8.5, 9.5, 10.5, 11.5)
  - `CARDS` — Over/Under total match cards (lines: 2.5, 3.5, 4.5, 5.5)
  - `OFFSIDES` — Over/Under total match offsides (lines: 1.5, 2.5, 3.5)
- Each hypothesis SHALL target exactly one market and one line.

### FR-2.2: Rule Tree Structure

- Each hypothesis SHALL be expressed as a rule tree with maximum depth 3.
- A rule tree node SHALL be one of:
  - **Condition node**: `feature_name <operator> threshold` where operator is in `{<, >, <=, >=}`.
  - **Leaf node**: prediction (`OVER` or `UNDER`) with the target market/line.
- Condition nodes combine via `AND` logic (all conditions in a path must be satisfied).
- A complete rule tree path from root to leaf forms a single strategy: "IF condition_1 AND condition_2 AND condition_3 THEN predict OVER 2.5 goals".
- Maximum conditions per strategy: 3 (depth limit).
- Minimum conditions per strategy: 1.

### FR-2.3: Parameter Ranges

- For each feature used in conditions, the system SHALL sweep threshold values across:
  - Percentiles: [10, 20, 30, 40, 50, 60, 70, 80, 90] of the feature distribution in the training set.
- Operators SHALL be restricted to `>` and `<` for simplicity (9 thresholds x 2 operators = 18 variants per feature per condition level).
- The generator SHALL produce hypotheses by combinatorially expanding:
  - 1-condition rules: `N_features * 18`
  - 2-condition rules: `C(N_features, 2) * 18^2`
  - 3-condition rules: `C(N_features, 3) * 18^3`
- A configurable `max_hypotheses` parameter (default: 50,000) SHALL cap the total rules generated per market to bound computation time.

### FR-2.4: Hypothesis Deduplication

- The system SHALL deduplicate logically equivalent rules (e.g., `A > 0.5 AND B > 0.3` is equivalent to `B > 0.3 AND A > 0.5`).
- Conditions SHALL be canonically ordered by feature name to enable deduplication.

---

## FR-3: Strategy Evaluator

### FR-3.1: Two-Season Walk-Forward Protocol

- The system SHALL evaluate each hypothesis using a 2-season walk-forward protocol:
  - **In-Sample (IS)**: Discovery on Season 1 data — the hypothesis is generated and initially validated here.
  - **Out-of-Sample (OOS)**: Verification on Season 2 data — the hypothesis is tested without modification.
- Seasons SHALL be configurable as `(league_id, season_1, season_2)` tuples.
- The system SHALL NOT modify rule parameters between IS and OOS evaluation.

### FR-3.2: Per-Hypothesis Backtest Execution

- For each hypothesis, the evaluator SHALL:
  1. Iterate over all matches in the evaluation season chronologically.
  2. For each match, compute the composite features using only prior match history (no look-ahead).
  3. Evaluate the rule tree conditions against the feature values.
  4. If all conditions are met, record a bet on the predicted direction at the available market odds.
  5. Determine the outcome based on the actual match result for the target market/line.
- Stake sizing SHALL use the existing `StakingCalculator` from the backtest module with a flat 1.0 unit base stake (volatility adjustment optional via config).

### FR-3.3: Integration with Existing Engine

- The evaluator SHALL reuse `src/backtest/metrics.py` (`MetricsAggregator`) for computing ROI, win rate, max drawdown, and p-value.
- The evaluator SHALL reuse `src/backtest/bet_log.py` (`BetLogger`) for recording bets.
- The evaluator SHALL accept matches from the existing `IngestionPipeline` (supporting both fixture and API modes).

### FR-3.4: Parallel Evaluation

- The evaluator SHALL support batch evaluation of multiple hypotheses against the same match dataset.
- The system SHALL precompute all features once per season and reuse them across all hypothesis evaluations.
- The evaluator SHALL support optional multiprocessing for hypothesis evaluation (configurable `n_workers`, default: 1).

---

## FR-4: Statistical Filter

### FR-4.1: Minimum Sample Size

- A hypothesis SHALL be discarded if it produces fewer than 250 qualifying bets across the evaluation period.
- This threshold SHALL be configurable via `min_bets` parameter (default: 250).

### FR-4.2: Profitability Filter

- A hypothesis SHALL be discarded if its Net ROI is not strictly greater than +5.0% on the OOS period.
- This threshold SHALL be configurable via `min_roi_pct` parameter (default: 5.0).

### FR-4.3: Statistical Significance Filter

- A hypothesis SHALL be discarded if its p-value (one-sample t-test of per-bet returns vs zero) is not strictly less than 0.05 on the OOS period.
- This threshold SHALL be configurable via `max_p_value` parameter (default: 0.05).

### FR-4.4: Closing Line Value (CLV) Beat Rate

- For each bet, the system SHALL compare the odds at time of signal generation against the closing odds (if available from FootyStats `closing_odds` field).
- CLV beat rate = `(bets_where_signal_odds > closing_odds) / total_bets_with_closing_data`.
- A hypothesis SHALL be discarded if its CLV beat rate is not strictly greater than 65% on the OOS period.
- This threshold SHALL be configurable via `min_clv_beat_rate` parameter (default: 0.65).
- When closing odds data is unavailable for a match, that match SHALL be excluded from CLV calculation (not counted as pass or fail).

### FR-4.5: Filter Application Order

- Filters SHALL be applied in the following order (cheapest-to-compute first):
  1. Minimum sample size (N >= 250)
  2. Net ROI > +5%
  3. p-value < 0.05
  4. CLV beat rate > 65%
- Each filter stage SHALL log the number of hypotheses eliminated.

### FR-4.6: Output

- Surviving hypotheses SHALL be output as `MinedStrategyResult` objects containing:
  - The `HypothesisRule` (full rule tree definition)
  - IS metrics (ROI, win rate, drawdown, p-value, N bets)
  - OOS metrics (ROI, win rate, drawdown, p-value, N bets, CLV beat rate)
  - Feature importance ranking (which features appeared in the rule)
  - Market type and line
- Results SHALL be serializable to JSON and appended to `data/results/mined_strategies.jsonl`.

---

## FR-5: CLI Integration

### FR-5.1: Mine Subcommand

- The system SHALL expose a `python -m src.cli mine` subcommand.
- Required arguments:
  - `--league-id` / `--league`: Target league.
  - `--season-is`: In-sample season string.
  - `--season-oos`: Out-of-sample season string.
- Optional arguments:
  - `--market`: One of `[goals, corners, cards, offsides, all]` (default: `all`).
  - `--max-hypotheses`: Cap on rules generated per market (default: 50000).
  - `--max-features`: Cap on composite features generated (default: 200).
  - `--min-bets`: Minimum qualifying bets (default: 250).
  - `--min-roi`: Minimum OOS ROI % (default: 5.0).
  - `--max-p-value`: Maximum OOS p-value (default: 0.05).
  - `--min-clv-beat-rate`: Minimum CLV beat rate (default: 0.65).
  - `--n-workers`: Parallel workers for evaluation (default: 1).
  - `--output`: Output directory (default: `data/results/`).
  - `-v` / `-vv`: Verbosity.

### FR-5.2: Progress Reporting

- The CLI SHALL report progress during mining:
  - Feature combination count generated.
  - Hypotheses generated per market.
  - Evaluation progress (% of hypotheses evaluated).
  - Filter pass counts at each stage.
  - Final surviving strategy count.

---

## Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-1 | The mining pipeline SHALL evaluate 10,000 hypotheses against 400 matches in under 5 minutes (single-core). |
| NFR-2 | All statistical calculations SHALL use 64-bit floating point precision. |
| NFR-3 | The system SHALL be implemented in Python 3.11+ using only `numpy`, `scipy`, and standard library (no ML frameworks required). |
| NFR-4 | Feature combination generation SHALL be deterministic given the same input metrics and configuration. |
| NFR-5 | All modules SHALL be independently testable with synthetic data. |
| NFR-6 | The system SHALL provide structured logging at DEBUG, INFO, WARN, ERROR levels with progress counters. |
| NFR-7 | Memory usage SHALL remain under 2 GB when evaluating 50,000 hypotheses against 800 matches. |
