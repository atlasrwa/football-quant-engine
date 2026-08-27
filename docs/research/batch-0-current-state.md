# Batch 0 — Current Platform State Audit

## Test Baseline

```
Total tests:    932 passed, 12 failed (pre-existing)
Research tests: 217 passed, 0 failed
Engine tests:   715 passed, 12 failed (broadcaster/integrity gate — unrelated to quant engine)
```

The 12 failures are all in `test_community_broadcaster.py`, `test_integration_pipeline.py`,
`test_integrity.py`, `test_integrity_gate.py`, and `test_trust_boundaries.py`. These are
pre-existing issues in the broadcaster validation trust badge logic, not in the quant engine
or research layer.

---

## What Raw FootyStats Data Currently Enters

The `FootyStatsClient` (src/ingestion/client.py) fetches from two endpoints:
- `GET /league-matches` — bulk match data for a league/season
- `GET /match` — single match detail

### Fields Currently Ingested

| FootyStats API Field | Stored As | Type |
|---------------------|-----------|------|
| `id` | `Match.id` | int |
| `date_unix` | `Match.date_unix` | int |
| `league_id` | `Match.league_id` | int |
| `season` | `Match.season` | str |
| `home_name` | `Match.home_team` | str |
| `away_name` | `Match.away_team` | str |
| `homeGoalCount` | `Match.home_goals` | int |
| `awayGoalCount` | `Match.away_goals` | int |
| `team_a_xg` | `Match.home_xg` | float (default 0.0) |
| `team_b_xg` | `Match.away_xg` | float (default 0.0) |
| `referee_name` | `Match.referee` | Optional[str] |
| `o25_potential` | `Match.over_odds` | Optional[float] |
| `u25_potential` | `Match.under_odds` | Optional[float] |
| (computed) | `Match.total_goals` | int |
| (hardcoded) | `Match.over_under_line` | 2.5 |

**Total ingested fields: 13 from API + 2 computed = 15 total**

### Additional Fields Available in FootyStats but NOT Ingested

| Category | Missing Fields |
|----------|---------------|
| Shots | `team_a_shots`, `team_b_shots`, `team_a_shotsOnTarget`, `team_b_shotsOnTarget`, `team_a_shotsOffTarget`, `team_b_shotsOffTarget` |
| Corners | `team_a_corners`, `team_b_corners` |
| Cards | `team_a_yellow_cards`, `team_b_yellow_cards`, `team_a_red_cards`, `team_b_red_cards` |
| Fouls | `team_a_fouls_committed`, `team_b_fouls_committed` |
| Offsides | `team_a_offsides`, `team_b_offsides` |
| Possession | `team_a_possession`, `team_b_possession` |
| Attacks | `team_a_attacks`, `team_b_attacks`, `team_a_dangerous_attacks`, `team_b_dangerous_attacks` |
| PPDA | `team_a_ppda`, `team_b_ppda` |
| Half-time | `ht_goals_team_a`, `ht_goals_team_b` |
| 1X2 Odds | `odds_ft_1`, `odds_ft_x`, `odds_ft_2` |
| Corner Odds | `odds_corners_over`, `odds_corners_under` |
| Card Odds | `odds_cards_over`, `odds_cards_under` |
| BTTS Odds | `btts_potential` |
| Other Lines | Over/Under at 1.5, 3.5, 4.5 |
| Team Stats | `home_ppg`, `away_ppg`, attack/defense strength |
| Form | `pre_match_home_form`, `pre_match_away_form` |

**Approximately 40+ useful fields are available from FootyStats but not currently ingested.**

---

## Existing Feature Capabilities

### Feature System (src/features/)

The `FeatureAssembler` combines three calculators:
1. **XGEfficiencyCalculator**: Rolling mean of `(actual_goals - xG) / xG` per team
2. **RollingFormCalculator**: Normalized W/D/L points over rolling window (0–1 scale)
3. **RefereeVolatilityCalculator**: Std dev of total goals for the assigned referee

Output: `MatchFeatures` dataclass with 11 fields:
- `home_xg_eff_delta_rolling`, `away_xg_eff_delta_rolling`
- `home_rolling_form`, `away_rolling_form`
- `referee_volatility_index`
- `total_goals`, `over_under_line`, `over_odds`, `under_odds`
- `match_id`, `date_unix`

**Limitations:**
- Only 3 feature families (xG efficiency, form, referee)
- Input limited to goals, xG, and referee name
- No access to shots, corners, cards, possession, attacks, etc.
- Fixed rolling windows (not configurable per-feature)
- No interaction features, no difference/ratio features

### Research Feature Registry (src/research/feature_registry.py)

The Phase 0 research layer adds a generalized `FeatureRegistry` with:
- 15 transform types: RAW, ROLLING_MEAN, ROLLING_STD, ROLLING_MEDIAN, EWMA, DIFFERENCE, RATIO, Z_SCORE, LEAGUE_NORMALIZE, HOME_AWAY_NORMALIZE, TREND, MOMENTUM, VOLATILITY, INTERACTION
- Content-hash-based identity
- Market applicability tagging
- Temporal class annotation (PRE_MATCH, POST_MATCH, DERIVED)
- Version tracking

This registry is fully functional but operates on the `ResearchDataSource` abstraction
(currently backed by synthetic data), not the live FootyStats ingestion pipeline.

---

## Existing X Metrics

### XMetricEngine (src/engine/xmetrics.py)

Three proprietary metrics:

| Metric | Formula | Inputs |
|--------|---------|--------|
| **xC** (Corner Pressure) | α·(dangerous_attacks/attacks) + β·shots_off_target + γ·opp_corners_avg | attacks, dangerous_attacks, shots_off_target, corners_avg_against |
| **xB** (Booking Intensity) | fouls × ref_cards_per_foul + δ·(100-possession)·opp_dribbles | fouls, possession, referee_cards_per_match, xg_against |
| **xO** (Offsides Trap) | η·offsides × (opp_HLI / league_baseline) | offsides, ppda (expanding baseline) |

Coefficients: `α=0.45, β=0.30, γ=0.25, δ=0.02, η=1.0`

**Note:** These metrics require fields that are NOT currently ingested from FootyStats
(dangerous_attacks, shots_off_target, corners_avg_against, etc.). They operate on
pre-computed DataFrame columns. The research layer bridges these via `XMetricAdapter`.

---

## Existing Backtest Capabilities

### Original WalkForwardEngine (src/backtest/engine.py)
- Input: `List[MatchFeatures]`
- Pipeline: FeatureAssembler → SignalGenerator → StakingCalculator → BetLogger
- Output: `BacktestResult` with folds, bet records, metrics
- Market: Goals Over/Under 2.5 only

### XMetricBacktester (src/engine/backtest.py)
- Input: DataFrame with xMetric columns + Strategy definitions (JSON conditions)
- Pipeline: StrategyEvaluator → per-fold evaluation → settlement → aggregation
- Output: `XBacktestResult` with XBetRecords, FoldMetrics, PredictionEvents
- Walk-forward: Sliding window (train_window=200, test_window=50, step_size=50)
- Settlement: Inline goals Over/Under (actual vs line)
- Provenance: Optional PredictionEvent emission with proof hashes

### Research Experiment (src/research/experiment.py)
- Input: Match dicts + feature values + hypothesis + market + probability model
- Pipeline: Walk-forward → model fit → predict → EV calculation → bet settlement
- Output: `ExperimentResult` with ROI, Sharpe, p-value, significance
- Market: Any `ResearchMarket` (GOALS, CORNERS, CARDS, OFFSIDES)

---

## Current Market Limitations

### Domain Definitions (src/domain/market.py)
6 `MarketType` enum values defined:
- OVER_UNDER, MATCH_RESULT, BOTH_TEAMS_TO_SCORE, ASIAN_HANDICAP, CORNERS_OVER_UNDER, CARDS_OVER_UNDER

### Operational Reality
- **Only Goals Over/Under 2.5 is fully functional** end-to-end
- The evaluator only maps OVER → "over_odds" and UNDER → "under_odds" columns
- BACK/LAY directions have no odds column mapping (return None)
- Settlement is hardcoded: `actual_total_goals` vs `market_line`
- The `over_under_line` is hardcoded to 2.5 in the Match model
- No corners, cards, or offsides markets flow through the production backtest

### Research Layer Markets (src/research/market.py)
4 markets fully supported in research mode:
- GOALS_TOTAL (line 2.5), CORNERS_TOTAL (line 9.5), CARDS_TOTAL (line 3.5), OFFSIDES_TOTAL (line 4.5)

These operate independently from the production engine using the `ResearchDataSource` abstraction.

---

## Settlement Limitations

### Production Settlement (src/domain/settlement.py + src/domain/factories.py)
- `SettlementFactory.settle_prediction()`: Resolves based on `actual_total_goals` vs `market_line`
- OVER wins if actual > line, UNDER wins if actual < line
- Push (exact line) → VOID
- Settlement record includes: entry_odds, closing_odds, CLV, P&L
- CLV computation: `(entry_odds / closing_odds - 1) × 100`

### Limitations
- Settlement only understands total goals
- No settlement logic for corners, cards, offsides, BTTS, or team totals
- No Asian handicap settlement
- No half-time market settlement
- CLV requires actual closing odds (unavailable for most markets)

---

## Probability Limitations

### Production Engine
- No explicit probability layer exists in the production engine
- The `SignalGenerator` computes a composite "edge" score (weighted feature sum)
- Edge is NOT calibrated probability
- The `StrategyEvaluator` computes edge as normalized distance from thresholds
- No distinction between edge score and true probability

### Research Layer (src/research/probability.py)
Three models available:
- `HistoricalFrequencyModel`: Baseline (training over-rate)
- `LogisticRegressionModel`: Feature-conditioned (gradient descent)
- `PoissonModel`: Count-based (scipy CDF, feature-adjusted lambda)

These are research-only; they don't feed into the production evaluation pipeline.

---

## EV Limitations

### Production Engine
- No formal EV calculation exists in the production backtest
- The evaluator emits signals when edge exceeds `min_edge_threshold`
- No comparison of model probability vs market-implied probability
- No Kelly fraction computation
- No formal fair-odds derivation

### Research Layer (src/research/ev_calculator.py)
- `EVCalculator.compute()`: EV = P(model) × odds - 1
- Both-sides evaluation
- Kelly fraction
- Edge vs fair probability (margin-stripped)
- This is research-only; not connected to the production signal flow.

---

## Extension Points

### Clean Boundaries for New Work

1. **Data Source Adapter**: `ResearchDataSource` interface allows any data provider
   (FootyStats, CSV, database) to feed the research engine without changes.

2. **Feature Registry**: Already extensible — register new `FeatureDefinition` objects
   with any source fields, transforms, and market applicability.

3. **Market Abstraction**: `ResearchMarket` defines target, line, odds fields — adding
   new markets is configuration, not code.

4. **Probability Models**: `ProbabilityModel` ABC allows new model implementations
   (negative binomial, gradient boosting, neural nets) to plug in.

5. **Research Agent**: `ResearchAgent` ABC supports deterministic and LLM-guided
   hypothesis generation.

6. **XMetric Adapter**: Clean bridge from existing xC/xB/xO into research features.

7. **Persistence Repositories**: Protocol-based — add new repositories for research
   entities without modifying existing ones.

8. **PredictionEvent**: Already supports multiple sources (BACKTEST, LIVE_SIGNAL,
   PAPER_TRADE) — research can emit predictions via the same domain model.

9. **Provenance Chain**: DatasetVersion → FeatureVersion → ModelVersion — extensible
   for research experiment provenance.

---

## Files That Must Remain Frozen

```
src/models/              — Match, MatchFeatures, StrategyConfig, BacktestResult
src/features/            — FeatureAssembler, RollingFormCalculator, XGEfficiencyCalculator, RefereeVolatilityCalculator
src/backtest/            — WalkForwardEngine, SignalGenerator, StakingCalculator, BetLogger, MetricsAggregator
src/engine/              — XMetricEngine, XMetricBacktester, StrategyEvaluator, FDRController, QuarantineTracker, StatisticalValidator, CLVCalculator
src/domain/              — PredictionEvent, Settlement, Market, Provenance, BacktestRun, Factories
src/ingestion/           — FootyStatsClient, IngestionPipeline, SchemaValidator, CacheManager
src/serializer.py
src/cli.py
```

All existing tests must continue to pass unchanged.

---

## Summary

| Capability | Production | Research Layer | Gap |
|-----------|-----------|---------------|-----|
| Data ingestion | 13 fields from FootyStats | Synthetic (all fields) | 40+ fields not ingested |
| Feature engineering | 3 features (xG eff, form, referee) | 15 transform types, dynamic registry | Not connected to real data |
| Markets | Goals O/U 2.5 only | 4 markets (goals, corners, cards, offsides) | No production multi-market |
| Probability | None (edge score only) | 3 models (frequency, logistic, Poisson) | Research-only |
| EV calculation | None | Full EV calculator | Research-only |
| Settlement | Goals only | Any research market | No production multi-market settlement |
| Walk-forward | Production-grade | Research-grade | Both functional |
| FDR/Quarantine | Production-grade | Via p-value in experiments | Not formally connected |
| Research memory | None | In-memory store | Not persistent |
| AI agent | None | Deterministic + LLM interface | LLM not connected |
| Persistence | 16+ PostgreSQL repositories | In-memory only | Research not persisted |
| API | Full REST API | None | No research API |

---

## Conclusion

The platform has a strong foundation:
- A validated walk-forward backtesting engine
- Statistical validation with FDR and quarantine
- Full provenance chain
- Comprehensive persistence layer
- A Phase 0 research laboratory proving the architecture works

The primary gaps for a discovery platform are:
1. **Data**: Most FootyStats fields aren't ingested
2. **Connection**: Research layer operates on synthetic data, not real FootyStats data
3. **Persistence**: Research experiments are in-memory only
4. **Markets**: Only goals O/U operates end-to-end in production
5. **Integration**: Research discoveries don't flow into the production validation pipeline

The architecture is well-designed for extension. The research layer's `ResearchDataSource`
interface was explicitly designed so that a `FootyStatsAdapter` can plug in without
modifying the research engine. The existing frozen components provide the statistical
rigor; the research layer provides the discovery capability.
