# Requirements: Platform Hardening & Anti-Overfitting Suite

## Overview

Upgrade the core execution, backtesting, and validation engines to protect against p-hacking (False Discovery Rate control), model real-world bookmaker friction (vig, slippage, and liquidity caps), abstract the data pipeline via a provider-agnostic adapter layer, and expose a schema converter for no-code strategy generation.

## Functional Requirements

### FR-1: Data Provider Abstraction Layer
- **FR-1.1:** Define an abstract base class `BaseDataLoader` with a `load() -> pd.DataFrame` contract that returns a standardized `MatchRecord`-schema DataFrame.
- **FR-1.2:** Implement `FootyStatsAdapter` that maps raw FootyStats CSV/JSON columns (`dangerous_attacks_home`, `referee_cpm`, `shots_off_target_home`, etc.) to the canonical `MatchRecord` schema.
- **FR-1.3:** Implement `SyntheticDataLoader` that generates randomized, edge-case match data including: missing stats (NaN), extreme referee card counts, postponed/voided fixtures, and boundary values for all x-Metric inputs.
- **FR-1.4:** All loaders must produce DataFrames with identical column schemas regardless of upstream data source.
- **FR-1.5:** Column mapping must be declarative (dict-based) so adding a new provider requires only a new mapping dict, not code changes.

### FR-2: False Discovery Rate (FDR) & Anti-p-Hacking Engine
- **FR-2.1:** Implement the Benjamini-Hochberg (BH) procedure to adjust p-value thresholds based on the number of hypotheses tested within a strategy family.
- **FR-2.2:** Track historical submission count per strategy family and use it as `k` in the BH correction: `adjusted_threshold = (rank / k) * alpha`.
- **FR-2.3:** Add a quarantine status to `ValidationVerdict`: `PENDING_QUARANTINE` (passed stats but awaiting 90-day live track record), `PROMOTED` (fully validated), `REJECTED` (failed).
- **FR-2.4:** Enforce holdout discipline: strategies passing historical backtests must enter a 90-day paper-trading quarantine before receiving live leaderboard promotion.
- **FR-2.5:** Provide `FDRController` class that accepts a batch of p-values and returns adjusted significance decisions.

### FR-3: Bookmaker Market Friction & Liquidity Engine
- **FR-3.1:** Implement a `MarketFrictionConfig` specifying margin rates per market type:
  - Match Odds (1X2 / Asian Handicap): 2.5% – 3.5%
  - Corners (xC): 5.0% – 7.5%
  - Cards (xB): 5.0% – 7.5%
  - Offsides (xO): 5.0% – 7.5%
- **FR-3.2:** Automatically deduct vig from odds before P&L calculation: `effective_odds = odds * (1 - margin)`.
- **FR-3.3:** Implement slippage/line-drag model: `fill_odds = signal_odds - slippage_bps / 10000 * signal_odds` where `slippage_bps` is configurable per market tier.
- **FR-3.4:** Implement liquidity caps per league tier:
  - Tier 1 (Top 5 leagues): max 10 units per match
  - Tier 2 (Major leagues): max 5 units per match
  - Tier 3 (Lower divisions): max 2 units per match
- **FR-3.5:** `FrictionAdjustedBacktester` wraps `XMetricBacktester` to apply friction before settlement.

### FR-4: No-Code Strategy Builder & Schema Exporter
- **FR-4.1:** Implement `StrategyBuilder` class that accepts simple dictionary inputs (metric name, threshold, direction, market) and produces valid `Strategy` objects.
- **FR-4.2:** Provide `to_json()` serialization producing strategy JSON compatible with `StrategyEvaluator.load_strategies()`.
- **FR-4.3:** Provide `from_json()` deserialization that reconstructs `StrategyBuilder` state from JSON.
- **FR-4.4:** Validate all inputs against allowed values (metrics: xC/xB/xO, operators: >/</>=/<=/==/!=, directions: OVER/UNDER/BACK/LAY) at build time.
- **FR-4.5:** Support multi-condition strategies with configurable logic (AND/OR).

## Non-Functional Requirements

### NFR-1: Backward Compatibility
- All existing tests (264) must continue passing unchanged.
- `XMetricBacktester.run()` signature and return type remain unchanged.
- `StatisticalValidator.validate()` continues to work with original `ValidationCriteria`.

### NFR-2: Performance
- FDR correction on 1000 p-values must complete in < 10ms.
- Friction-adjusted backtest adds < 5% overhead vs. vanilla backtest.
- SyntheticDataLoader generates 10,000 rows in < 1 second.

### NFR-3: Extensibility
- Adding a new data provider requires only subclassing `BaseDataLoader` and defining a column mapping.
- New market types can be added to `MarketFrictionConfig` without code changes to the backtester.

### NFR-4: Safety
- FDR correction is applied automatically when `submission_count > 1`.
- Quarantine cannot be bypassed programmatically — requires explicit `promote()` call after 90 days.
- Liquidity caps are enforced even if the user sets higher stakes in config.
