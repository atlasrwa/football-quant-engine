# Requirements: Proprietary x-Metric Suite (xC, xB, xO)

## Overview

Build a vectorized Python execution and backtesting framework that calculates three novel, proprietary x-Metrics (xC, xB, xO) directly from FootyStats raw match/team CSV variables and evaluates their predictive edge against betting market lines.

## Functional Requirements

### FR-1: xC — Expected Corner Pressure Engine
- **FR-1.1:** Compute xC from FootyStats raw fields: `shots_off_target`, `attacks`, `dangerous_attacks`, `possession`, and `corners_against_avg`.
- **FR-1.2:** Formula: `xC = α·(dangerous_attacks / attacks) + β·(shots_off_target) + γ·(opponent_corners_conceded_avg)`.
- **FR-1.3:** Default coefficients: α=0.45, β=0.30, γ=0.25 (configurable).
- **FR-1.4:** Produce per-match home_xC and away_xC columns suitable for Corners Over/Under and Asian Handicap markets.

### FR-2: xB — Expected Booking Intensity Index
- **FR-2.1:** Compute xB from FootyStats raw fields: `fouls`, `cards_per_match`, `referee_cpm`, `possession_pct`, and `xg_against`.
- **FR-2.2:** Formula: `xB = (team_fouls_per_90 × referee_cards_per_foul) + δ·(100 - possession_pct) × opponent_dribbles_faced`.
- **FR-2.3:** Default coefficients: δ=0.02 (configurable). Use proxy `xg_against * 3.5` for `opponent_dribbles_faced` when not directly available.
- **FR-2.4:** Produce per-match home_xB and away_xB columns suitable for Total Card Points / Team Bookings Over/Under markets.

### FR-3: xO — Expected Offsides Trap & Attack Line Engine
- **FR-3.1:** Compute xO from FootyStats raw fields: `offsides`, `ppda` (passes allowed per defensive action), `long_passes_per_90`, and `offside_given_per_90`.
- **FR-3.2:** Formula: `xO = η·(attacker_offsides_avg × (opponent_high_line_index / league_baseline))`.
- **FR-3.3:** Use `1 / ppda` as proxy for `opponent_high_line_index` (lower PPDA = higher defensive line). League baseline is the season-wide mean.
- **FR-3.4:** Default coefficient: η=1.0 (configurable).
- **FR-3.5:** Produce per-match home_xO and away_xO columns suitable for Total Match Offsides / Player Offside Props markets.

### FR-4: Hypothesis Evaluator (Strategy Loader)
- **FR-4.1:** Parse community strategy definitions from JSON configuration files.
- **FR-4.2:** Dynamically evaluate conditions against xC, xB, xO columns without `eval()` or `exec()`.
- **FR-4.3:** Support comparison operators: `>`, `<`, `>=`, `<=`, `==`, `!=` and logical combinators (`and`, `or`).
- **FR-4.4:** Return signal direction (OVER/UNDER/BACK/LAY) and confidence edge for each qualifying match.

### FR-5: Walk-Forward Out-of-Sample Backtest Engine
- **FR-5.1:** Perform chronological time-series backtests across historical FootyStats seasons.
- **FR-5.2:** Split data into sliding train/test windows (configurable sizes).
- **FR-5.3:** Compute Net ROI %, Closing Line Value (CLV %), Total Profit/Loss, and Max Drawdown.
- **FR-5.4:** Report per-fold metrics and aggregate results as `BacktestResult`-compatible output.
- **FR-5.5:** Ensure look-ahead-free operation — no future data leaks into train windows.

### FR-6: Statistical Validator & Promotion Gate
- **FR-6.1:** Run 1-sample 1-tailed t-test (H₁: mean_profit > 0) with p ≤ 0.05.
- **FR-6.2:** Validate minimum sample size N ≥ 250 bets for promotion eligibility.
- **FR-6.3:** Require Net ROI ≥ 3% for promotion.
- **FR-6.4:** Output a `ValidationVerdict` with pass/fail, p-value, confidence interval, effect size, and reason.

## Non-Functional Requirements

### NFR-1: Performance
- All x-Metric computations must be vectorized (numpy/pandas) — no Python-level row loops.
- Backtest 10,000 matches in under 5 seconds on standard hardware.

### NFR-2: Extensibility
- New x-Metrics must be addable by implementing a single function with a consistent signature.
- Strategy JSON schema must support arbitrary metric combinations.

### NFR-3: Compatibility
- Integrate with existing `StrategyConfig`, `Match`, and `MatchFeatures` models.
- Extend (not replace) the existing `src/backtest/` engine.
- Python ≥ 3.11, numpy, scipy, pandas (add to deps).

### NFR-4: Data Safety
- All temporal computations must be look-ahead-free.
- Coefficients must be frozen during test windows (no in-sample tuning on test data).

### NFR-5: Observability
- Log computation stats (matches processed, NaN rates, dropped rows) at INFO level.
- Validation results logged with full statistical detail at INFO level.
