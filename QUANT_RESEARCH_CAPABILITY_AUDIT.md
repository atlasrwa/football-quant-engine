# QUANT RESEARCH CAPABILITY AUDIT

## 1. Executive Conclusion

**The current engine is NOT capable of taking raw FootyStats data and automatically discovering new market-relevant metrics and strategies.** It is a hypothesis *testing* platform (evaluates human-defined strategies) — not a hypothesis *generation* or *discovery* platform.

The engine can rigorously validate manually-specified strategies via walk-forward backtesting, FDR correction, and 90-day paper quarantine. But no component exists that generates candidate metrics, searches parameter spaces, discovers feature interactions, or automatically identifies positive-EV relationships from raw data.

**Answer to Section 4 core question: D/E hybrid** — "The engine primarily performs backtesting of manually specified strategies" AND "the architecture supports discovery conceptually, but the implementation is incomplete."

---

## 2. Capability Matrix

| Capability | Exists | Partial | Missing | Evidence |
|---|:---:|:---:|:---:|---|
| Raw data ingestion | ✓ | | | `IngestionPipeline`, `MockProvider`, `FootyStatsClient` |
| FootyStats adapter | | ✓ | | Client exists but ingests only 15 fields out of 50+ available |
| Feature generation | ✓ | | | `FeatureAssembler` with 3 calculators (xg_eff, form, referee) |
| Dynamic feature generation | | | ✓ | Fixed `MatchFeatures` dataclass, no registry/plugin system |
| XMetric generation | ✓ | | | `XMetricEngine` computes xC/xB/xO from DataFrames |
| Automatic metric discovery | | | ✓ | No search, no combinatorial generation, no feature interaction |
| Hypothesis generation | | | ✓ | Strategies must be human-defined JSON |
| Strategy generation | | | ✓ | `StrategyBuilder` is a no-code *constructor*, not a *generator* |
| Market integration | | ✓ | | Over/Under 2.5 goals only; other markets defined but no odds ingested |
| EV calculation | | | ✓ | No `P(model) - P(market)` anywhere; "edge" is threshold distance |
| CLV | ✓ | | | `CLVCalculator` with gold-standard formula `(entry/closing - 1) × 100` |
| Walk-forward | ✓ | | | Both Phase 1 `WalkForwardEngine` and Phase 2 `XMetricBacktester` |
| FDR | ✓ | | | `FDRController` with Benjamini-Hochberg procedure |
| Multiple testing control | ✓ | | | FDR adjusts threshold per submission count |
| Feature interactions | | | ✓ | No interaction terms, products, ratios between features |
| Search space | | | ✓ | No grid search, random search, or optimization |
| Automated candidate ranking | | | ✓ | Manual submission → validation; no ranking of candidates |
| Reproducibility | ✓ | | | Full provenance: Dataset→Feature→Model→BacktestRun versions |
| Dataset versioning | ✓ | | | `DatasetVersion`, `FeatureVersion`, `ModelVersion` with content hashing |
| Next-fixture testing | | ✓ | | Paper prediction + settlement exists; no automated fixture loop |
| Probability calibration | | | ✓ | No probability output, no calibration, no Brier score |
| Bookmaker margin handling | | | ✓ | Raw odds used as-is, no overround correction |
| Multi-market settlement | | | ✓ | Settlement resolves OVER/UNDER vs total goals only |

---

## 3. Current Execution Flow

Only components that **actually exist and execute**:

```
FOOTYSTATS JSON (via fixture file or API)
   ↓
MockProvider._record_to_match() → Match(15 fields, fixed schema)
   ↓
FeatureAssembler.assemble(matches) → MatchFeatures[]
   │  ├── XGEfficiencyCalculator (rolling xG eff delta, window=5)
   │  ├── RollingFormCalculator (W/D/L form, window=6)
   │  └── RefereeVolatilityCalculator (expanding goals std dev)
   ↓
Phase 1: WalkForwardEngine.run(features)
   │  ├── TemporalCrossValidator.generate_folds(train=100, test=20, step=20)
   │  ├── SignalGenerator.generate(features) → weighted composite → OVER/UNDER + edge
   │  ├── StakingCalculator.compute_stake(variance-adjusted)
   │  └── MetricsAggregator → BacktestResult(roi, win_rate, sharpe, drawdown)
   ↓
Phase 2: XMetricBacktester.run(df, strategies)  [PARALLEL PATH, NOT CONNECTED]
   │  ├── XMetricEngine.compute_xC/xB/xO(df) → augmented DataFrame
   │  ├── StrategyEvaluator.evaluate(df, strategies) → Signals
   │  ├── Walk-forward folds (train=200, test=50, step=50)
   │  ├── Settle bets: direction vs actual_total_goals vs line
   │  └── XBacktestResult(bet_records, roi, win_rate, sharpe)
   ↓
StatisticalValidator.validate(bets) → pass/fail (sample≥250, ROI≥3%, p≤0.05)
   ↓
FDRController.is_significant(p_value, submission_count) → adjusted threshold
   ↓
QuarantineTracker.enter_quarantine() → 90-day paper trading period
   ↓
PredictionSettlementService → settlement + CLV computation
   ↓
QuarantineSettlementBridge → paper P&L tracking
   ↓
promote() / reject()
```

---

## 4. Discovery Gap

### WHAT THE ENGINE CAN DO TODAY

1. **Ingest** FootyStats data (limited to 15 fields from ~50+ available)
2. **Compute** 5 features (xg_eff_delta ×2, rolling_form ×2, referee_volatility)
3. **Compute** 3 XMetrics (xC, xB, xO) from raw DataFrame columns
4. **Evaluate** human-defined strategy conditions against DataFrame columns
5. **Backtest** strategies with walk-forward temporal validation
6. **Validate** statistically (t-test, minimum sample, minimum ROI)
7. **Control** false discoveries (Benjamini-Hochberg FDR)
8. **Quarantine** for 90-day out-of-sample paper testing
9. **Settle** predictions against actual match outcomes (OVER/UNDER goals only)
10. **Compute** CLV when closing odds are available
11. **Track** full provenance chain (dataset → feature → model → backtest → prediction)

### WHAT IT CANNOT DO TODAY

1. **Discover** new metrics or features automatically
2. **Search** parameter spaces (thresholds, windows, coefficients)
3. **Generate** candidate hypotheses from data
4. **Compute** calibrated probabilities
5. **Calculate** expected value (P_model × odds - 1)
6. **Compare** model probability vs market implied probability
7. **Strip** bookmaker margins from raw odds
8. **Evaluate** incremental information (does new feature improve beyond baseline?)
9. **Generate** feature interactions (ratios, products, z-scores, percentiles)
10. **Rank** candidates by economic value
11. **Settle** non-goals markets (corners, cards, offsides)
12. **Ingest** 80%+ of available FootyStats columns (shots, corners, cards, possession, attacks, etc.)
13. **Run** automated fixture-day prediction loops
14. **Calibrate** or score probability outputs (Brier, log-loss, AUC)

### WHAT REQUIRES HUMAN INPUT

- Strategy definition (JSON with field/operator/value conditions)
- Choice of target market
- Choice of direction (OVER/UNDER)
- Threshold values in conditions
- Feature selection
- XMetric coefficient choice (hard-coded defaults exist)

### WHAT MUST BE BUILT

1. **Extended data model** — ingest all available FootyStats columns
2. **Feature registry** — dynamic feature definition and versioning
3. **Candidate metric generator** — combinatorial feature construction
4. **Hypothesis generator** — automated strategy construction from features
5. **Probability model** — calibrated probability output
6. **EV calculator** — `P(model) × odds - 1` with margin correction
7. **Search engine** — parameter space exploration with FDR integration
8. **Multi-market settlement** — corners, cards, offsides resolution
9. **Incremental evaluator** — does new feature beat baseline?
10. **Automated fixture loop** — daily prediction cycle

---

## 5. FootyStats Integration Gap

### Current State

- `FootyStatsClient` exists with rate limiting and retries
- `MockProvider` loads from fixture JSON files
- `_record_to_match()` maps only 10-12 FootyStats fields
- `Match` dataclass has 15 fixed fields

### Fields Available from FootyStats but NOT Ingested

Based on the XMetricEngine's column expectations (which reference fields NOT in the Match model):

| Category | Available Fields | Currently Ingested |
|----------|-----------------|-------------------|
| **Goals** | homeGoalCount, awayGoalCount, total_goals | ✓ |
| **xG** | team_a_xg, team_b_xg | ✓ |
| **Shots** | shots_home, shots_away, shots_on_target_home, shots_on_target_away, shots_off_target_home, shots_off_target_away | ✗ |
| **Corners** | corners_home, corners_away, total_corners, corners_avg_against_home, corners_avg_against_away | ✗ |
| **Cards** | cards_home, cards_away, referee_cards_per_match | ✗ |
| **Fouls** | fouls_home, fouls_away | ✗ |
| **Attacks** | attacks_home, attacks_away, dangerous_attacks_home, dangerous_attacks_away | ✗ |
| **Possession** | possession_home, possession_away | ✗ |
| **Offsides** | offsides_home, offsides_away | ✗ |
| **PPDA** | ppda_home, ppda_away | ✗ |
| **Odds** | o25_potential, u25_potential (goals O/U 2.5 only) | ✓ (limited) |
| **Other Odds** | corners lines, cards lines, match odds | ✗ |
| **Referee** | referee_name | ✓ |
| **Match Context** | league_id, season, date_unix, home_name, away_name | ✓ |

### Required Adapter Work

1. **Extend Match model** or create a parallel `RawMatchData` model with all 50+ fields
2. **Update `_record_to_match()`** to map all available columns
3. **Store raw data** in database as canonical dataset (preserving unmapped fields)
4. **Create market_prices entries** for all available odds (not just goals O/U 2.5)
5. **Add historical odds ingestion** — FootyStats provides odds data that needs temporal indexing

### Preferred Architecture

```
FootyStats API
     ↓
FootyStatsAdapter (extends current client)
     ↓
RawMatchRecord (50+ fields, all available data)
     ↓
Database: raw_match_data table (schema-flexible JSONB + typed columns)
     ↓
FeatureAssembler / XMetricEngine (consume what they need)
     ↓
Research engine (access full raw data for discovery)
```

---

## 6. Research/Discovery Architecture (Proposed — NOT Implemented)

### New Bounded Context: QUANT RESEARCH

```
src/research/
├── __init__.py
├── feature_registry.py       # Dynamic feature definitions
├── feature_generator.py      # Combinatorial feature construction
├── metric_generator.py       # Candidate metric generation (ratios, z-scores, etc.)
├── hypothesis_generator.py   # Automated strategy construction
├── search_space.py           # Parameter space definition and traversal
├── candidate_evaluator.py    # Walk-forward + EV + incremental evaluation
├── probability_model.py      # Calibrated probability estimation
├── ev_calculator.py          # Expected value with margin correction
├── baseline_models.py        # Naive, league, home/away, market baselines
├── discovery_runner.py       # Orchestrates full discovery pipeline
├── ranking.py                # Rank candidates by economic value
└── config.py                 # Research configuration
```

### Discovery Pipeline

```
RawMatchData (all FootyStats columns)
     ↓
FeatureRegistry.get_base_features()
     ↓
FeatureGenerator.generate_candidates()
     │  ├── Rolling means (windows: 3, 5, 10, 20)
     │  ├── Rolling std devs
     │  ├── Z-scores
     │  ├── Percentiles
     │  ├── Ratios (A/B for relevant pairs)
     │  ├── Differences (A-B)
     │  ├── Home/away adjustments
     │  ├── Team vs opponent comparisons
     │  ├── Referee × team interactions
     │  └── Market-relative features (vs implied probability)
     ↓
MetricGenerator.create_candidates()
     │  ├── Single features with thresholds
     │  ├── Feature pairs with conditions
     │  ├── Multi-condition strategies
     │  └── Adaptive threshold strategies
     ↓
HypothesisGenerator.generate()
     │  ├── Each candidate metric → multiple market hypotheses
     │  ├── Corners O/U, Cards O/U, Goals O/U, etc.
     │  └── Multiple direction variants
     ↓
CandidateEvaluator.evaluate(hypothesis)
     │  ├── Walk-forward backtest (existing XMetricBacktester)
     │  ├── Probability calibration
     │  ├── EV calculation (P_model vs P_market)
     │  ├── Incremental info test (vs baseline)
     │  └── Economic metrics (ROI, CLV, Sharpe)
     ↓
StatisticalValidator + FDRController (existing, unchanged)
     ↓
CandidateRanking.rank(validated_candidates)
     │  ├── By expected value
     │  ├── By CLV
     │  ├── By information ratio
     │  └── By robustness across folds
     ↓
StrategyVersion (existing provenance chain)
     ↓
QuarantineTracker (existing 90-day paper test)
```

### Key Design Principles

1. **Discovery layer wraps existing engine** — does not modify it
2. **FDR applies to ALL candidates tested** — not just manually submitted ones
3. **Walk-forward is mandatory** — no in-sample-only evaluation
4. **Market comparison is primary metric** — not accuracy
5. **Incremental information required** — must beat baseline
6. **Full provenance** — every discovery traceable to dataset + features + parameters

---

## 7. Minimal MVP

### Goal: First automatically discovered candidate strategy from FootyStats data

**Phase A — Extended Data Ingestion (1 sprint)**
- Extend `Match` model or create `RawMatchData` with all FootyStats fields
- Update `_record_to_match()` to capture shots, corners, cards, possession, attacks, offsides, fouls, PPDA
- Store raw data in database with content hashing
- Ingest historical odds for multiple markets

**Phase B — Feature Registry + Generation (1 sprint)**
- Create `FeatureRegistry` — dynamic feature definitions (name, computation, dependencies)
- Create `FeatureGenerator` — compute rolling windows, z-scores, ratios from registered base features
- Integrate with existing `FeatureVersion` provenance

**Phase C — Candidate Generation (1 sprint)**
- Create `MetricGenerator` — systematically produce candidate metrics from feature combinations
- Create `HypothesisGenerator` — pair metrics with markets and directions to form strategy candidates
- Define search space bounds (avoid explosion)

**Phase D — Market-Aware Evaluation (1 sprint)**
- Create `EVCalculator` — convert model output to probability, compare with implied market probability
- Create `BaselineModels` — naive frequency, league average, market implied
- Extend settlement to support corners/cards/offsides markets

**Phase E — Discovery Runner (1 sprint)**
- Wire: data → features → candidates → backtest → FDR → ranking
- Run first automated search
- Verify FDR controls false discoveries appropriately
- Produce first automatically-discovered strategy candidate

### Minimum files to create:
```
src/research/__init__.py
src/research/feature_registry.py
src/research/feature_generator.py
src/research/metric_generator.py
src/research/hypothesis_generator.py
src/research/ev_calculator.py
src/research/baseline_models.py
src/research/discovery_runner.py
```

### Minimum existing infrastructure to extend (without modifying):
- Use `XMetricBacktester` as-is for walk-forward evaluation
- Use `StatisticalValidator` as-is for significance testing
- Use `FDRController` as-is — but pass ALL candidate p-values (not just one)
- Use `StrategyEvaluator` as-is for condition evaluation
- Use provenance chain as-is for reproducibility

---

## 8. Recommended Development Phases

### Phase A — FootyStats Full Ingestion
- Extended raw data model (all available columns)
- Historical data loader (multiple seasons, multiple leagues)
- Market price ingestion (all available odds/lines)
- Data quality validation
- **Dependency**: None
- **Output**: Complete historical dataset in database

### Phase B — Research Dataset Infrastructure
- Feature registry with dynamic definitions
- Base feature computation from raw data
- Feature versioning integration
- Look-ahead bias enforcement for all new features
- **Dependency**: Phase A
- **Output**: Versioned feature sets computed from raw data

### Phase C — Candidate Feature Generation
- Rolling window features (multiple windows)
- Statistical transformations (z-score, percentile)
- Ratio features (A/B, A-B)
- Interaction features (A×B)
- Team-relative features (vs opponent, vs league average)
- Home/away adjustments
- **Dependency**: Phase B
- **Output**: Large candidate feature space (hundreds of features)

### Phase D — XMetric Discovery
- Systematic evaluation of single-feature predictive power
- Feature combination search (pairs, triples)
- Threshold optimization
- Market-specific feature relevance
- **Dependency**: Phase C
- **Output**: Ranked candidate metrics by predictive information

### Phase E — Hypothesis Generation
- Automated strategy construction from top metrics
- Multi-condition strategy building
- Market assignment (which metric → which market)
- Direction selection
- **Dependency**: Phase D
- **Output**: Candidate strategy set (hundreds to thousands)

### Phase F — Market-Aware Evaluation
- Probability calibration (logistic regression, isotonic)
- Expected value calculation with margin correction
- Incremental information testing (vs market, vs baseline)
- Economic metric computation (EV, CLV expectation, Sharpe)
- Multi-market settlement (corners, cards, offsides)
- **Dependency**: Phase E + existing walk-forward
- **Output**: Economically-evaluated candidate strategies

### Phase G — FDR / Validation Integration
- Pass ALL candidate p-values to FDRController simultaneously
- Apply Benjamini-Hochberg across full discovery space
- Enforce minimum effect size + minimum sample
- Out-of-sample holdout validation
- **Dependency**: Phase F + existing FDR/Validator
- **Output**: FDR-controlled discovery set

### Phase H — Automated Next-Fixture Testing
- Daily fixture ingestion
- Feature computation for upcoming matches
- Prediction generation from validated strategies
- Paper bet placement
- Post-match settlement + CLV tracking
- Performance monitoring
- **Dependency**: Phase G + existing quarantine system
- **Output**: Automated prediction loop

### Phase I — Production Integration
- Connect discovery output to existing Phase 3.3/3.4 trust layer
- Strategy promotion pipeline
- Broadcast of validated predictions
- Attestation of discoveries
- Performance dashboards
- **Dependency**: Phase H + existing Phases 3.1-3.4
- **Output**: Full production research laboratory

---

## 9. Critical Risks

### Look-Ahead Bias
- **Current status**: Well-handled in existing features (deque pattern, expanding means)
- **Risk in discovery**: New features MUST be computed using only pre-match data
- **Mitigation**: Enforce temporal ordering in FeatureGenerator; all rolling computations use strict t-1 convention

### Data Leakage
- **Current status**: No issues identified
- **Risk in discovery**: Feature selection based on full dataset leaks future information
- **Mitigation**: Feature importance must be evaluated within walk-forward folds only

### Multiple Testing / False Discovery
- **Current status**: FDRController handles this correctly
- **Risk in discovery**: Testing thousands of candidates without proper FDR adjustment = guaranteed false discoveries
- **Mitigation**: Pass ALL candidate p-values to Benjamini-Hochberg simultaneously; adjust significance threshold by total candidates tested

### Overfitting
- **Current status**: Walk-forward prevents in-sample fitting
- **Risk in discovery**: Threshold optimization within training data can overfit
- **Mitigation**: Walk-forward with strict temporal separation; thresholds chosen on training, evaluated on test, NEVER adapted to test performance

### Market Leakage / Odds Timestamp Leakage
- **Current status**: Opening odds (o25_potential) used — may or may not be pre-match
- **Risk in discovery**: Using closing odds as features would leak settlement outcome information
- **Mitigation**: Only use opening/pre-match odds as features; closing odds used only for CLV evaluation post-settlement

### Survivorship Bias
- **Current status**: Not addressed
- **Risk in discovery**: Only evaluating strategies that "looked good" historically
- **Mitigation**: Record ALL candidates evaluated (including failures); FDR correction accounts for total search space

### Repeated Backtest Contamination
- **Current status**: FDRController.is_significant() penalizes repeated submissions
- **Risk in discovery**: Automated search runs thousands of backtests on same data
- **Mitigation**: FDR MUST track total hypothesis count across discovery sessions; holdout set for final validation

### Feature Selection Bias
- **Current status**: Features are fixed (no selection)
- **Risk in discovery**: Selecting features that happen to correlate with historical outcomes
- **Mitigation**: Feature importance must be evaluated per-fold; cross-validated importance; require consistency across folds

### Settlement Logic Limitation
- **Current status**: Only resolves OVER/UNDER vs total goals
- **Risk in discovery**: Cannot validate corner/card/offside strategies
- **Mitigation**: Extend `_resolve_outcome()` to support alternative actual values (total_corners, total_cards, etc.) via adapter pattern

---

## 10. Final Recommendation

**Build the Quant Research / Discovery layer BEFORE Phase 3.5 hardening.**

Reasoning:

1. **The platform's entire value proposition depends on discovering market edge.** Without discovery, the production trust layer (Phases 3.1-3.4) is infrastructure without purpose. It's a beautifully secured vault with nothing to put in it.

2. **The existing quant engine provides excellent validation infrastructure** (walk-forward, FDR, quarantine, CLV) but zero discovery capability. The most impactful work is building the discovery layer ON TOP of the existing validation.

3. **Phase 3.5 hardening adds marginal value** to a system that cannot yet discover anything. The trust layer is already robust (963 tests, RLS, immutability, idempotency).

4. **The discovery layer can be built without modifying the existing engine.** It wraps `XMetricBacktester`, `StatisticalValidator`, `FDRController`, and `QuarantineTracker` — using them as-is.

5. **FootyStats integration is the critical unblocking dependency.** The extended raw data model is required before any discovery can occur. This should be Phase A.

**Recommended immediate next step**: Phase A (FootyStats Full Ingestion) → Phase B (Feature Registry) → Phase C (Candidate Generation).

The platform should become a football quantitative research laboratory first, and additional production hardening can follow once the research loop is operational and generating candidates worth securing.
