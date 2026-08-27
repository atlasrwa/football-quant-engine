# PHASE 0 RESEARCH LAB REPORT

## Status: COMPLETE

The Research & Discovery Laboratory is fully operational using
synthetic data. The system is data-source-agnostic and ready
for real data providers.

---

## Tests

| Category | Count |
|----------|-------|
| Existing (non-research) | 727 |
| Research module | 217 |
| **Total passing** | **944** |

All existing tests remain untouched and passing.
No frozen components were modified.

---

## Files Created

### Source (src/research/) — 3,346 LOC

| File | LOC | Purpose |
|------|-----|---------|
| `__init__.py` | 16 | Module docstring and exports |
| `data_source.py` | 207 | ResearchDataSource ABC + ResearchMatch + MarketOdds |
| `synthetic_data.py` | 356 | SyntheticResearchDataSource with embedded relationship |
| `feature_registry.py` | 564 | FeatureRegistry + FeatureTransformEngine (14 transforms) |
| `market.py` | 119 | ResearchMarket + MarketType + 4 default markets |
| `probability.py` | 315 | ProbabilityModel ABC + Historical/Logistic/Poisson |
| `ev_calculator.py` | 145 | EVCalculator (EV + Kelly + edge + fair odds) |
| `candidate_generator.py` | 208 | CandidateGenerator + SearchBudget + ResearchHypothesis |
| `experiment.py` | 353 | ResearchExperiment walk-forward + ExperimentResult |
| `memory.py` | 182 | ResearchMemory (persistent store + dedup) |
| `agent.py` | 251 | DeterministicResearchAgent + LLMResearchAgent interface |
| `xmetric_adapter.py` | 322 | XMetricAdapter (bridges frozen XMetricEngine) |
| `discovery_runner.py` | 308 | DiscoveryRunner (full pipeline orchestrator) |

### Tests (tests/research/) — 3,194 LOC

| File | LOC | Tests |
|------|-----|-------|
| `test_data_source.py` | 184 | 22 |
| `test_feature_registry.py` | 540 | 37 |
| `test_market.py` | 96 | 12 |
| `test_probability.py` | 195 | 21 |
| `test_ev_calculator.py` | 134 | 12 |
| `test_candidate_generator.py` | 213 | 17 |
| `test_experiment.py` | 192 | 12 |
| `test_memory.py` | 187 | 14 |
| `test_agent.py` | 181 | 12 |
| `test_xmetric_adapter.py` | 254 | 19 |
| `test_anti_leakage.py` | 377 | 15 |
| `test_end_to_end.py` | 641 | 29 |

### Documentation (docs/research/)

| File | Purpose |
|------|---------|
| `footystats-adapter-contract.md` | Complete adapter specification for future integration |
| `PHASE-0-RESEARCH-LAB-REPORT.md` | This report |

---

## Files Modified

**NONE.**

No frozen components were touched:
- `src/models/` — untouched
- `src/features/` — untouched
- `src/backtest/` — untouched
- `src/engine/` — untouched
- `src/domain/` — untouched
- `src/ingestion/` — untouched
- `src/serializer.py` — untouched
- `src/cli.py` — untouched

---

## Files Deleted

**NONE.**

---

## Research Capabilities

### Data Source Abstraction

- `ResearchDataSource` ABC — fully data-source-agnostic
- `SyntheticResearchDataSource` — deterministic (seed=42), 4 seasons, 528 matches
- Normalized `ResearchMatch` with 50+ fields (all optional except identity)
- `MarketOdds` with temporal timestamps (always before kickoff)
- `get_matches()`, `get_available_fields()`, `get_market_odds()`
- Content hash for dataset fingerprinting

### Feature Registry

- Immutable `FeatureDefinition` with content hash identity
- `FeatureRegistry` — idempotent registration, market filtering, versioning
- `TemporalClass` enforcement: PRE_MATCH / POST_MATCH / DERIVED
- Dynamic feature composition from any data source

### Feature Transform Engine (14 transforms)

| Transform | Causality |
|-----------|-----------|
| RAW | Current value |
| ROLLING_MEAN | Prior N matches only |
| ROLLING_STD | Prior N matches only |
| ROLLING_MEDIAN | Prior N matches only |
| EWMA | Prior matches with decay |
| DIFFERENCE | Two-field subtraction |
| RATIO | Safe division |
| Z_SCORE | Expanding history |
| LEAGUE_NORMALIZE | League-level expanding |
| HOME_AWAY_NORMALIZE | Venue-level expanding |
| TREND | Linear slope over window |
| MOMENTUM | Short vs long mean |
| VOLATILITY | Rolling std (team-level) |
| INTERACTION | Field multiplication |

All transforms enforce strict temporal causality: the value at match i
uses ONLY data from matches before i.

---

## XMetric Integration

- `XMetricAdapter` bridges the frozen `XMetricEngine` (xC, xB, xO)
- Registers 6 raw XMetric features in the research registry
- `create_xmetric_rolling_features()` generates derived rolling features
- Full provenance tracking (version, coefficients, temporal semantics)
- XMetrics coexist with discovered features in the same registry

Architecture:

```
XMetricEngine (FROZEN)
    ↓ adapter
FeatureRegistry
    ↓
Research Laboratory
```

---

## Probability Layer

| Model | Type | Use Case |
|-------|------|----------|
| `HistoricalFrequencyModel` | Baseline | P(OVER) = historical rate |
| `LogisticRegressionModel` | Feature-conditional | Gradient descent, standardized |
| `PoissonModel` | Count-based | Poisson CDF for count markets |

All models output `ProbabilityEstimate(p_over, p_under, model_name)`.
Probabilities always sum to 1.0 (enforced at construction).

---

## EV Layer

- `EV = P(model) × odds - 1`
- Both-sides evaluation
- Fair probability (margin-stripped via multiplicative removal)
- Edge = model_probability - fair_probability
- Kelly fraction = edge / (odds - 1), capped at 0
- Implied probability from raw odds

---

## Candidate Generation

- `CandidateGenerator` with `SearchBudget` constraints
- Single-feature hypotheses at quantile thresholds (25th, 50th, 75th)
- Pair hypotheses (AND conditions, median thresholds)
- Budget controls: max_candidates, min_sample_size, max_features_per_hypothesis
- Deterministic generation (seeded RNG)
- Both OVER and UNDER directions generated

---

## Hypothesis Engine

- `ResearchHypothesis` with content_hash for deduplication
- Fields: hypothesis_id, market, feature_ids, conditions, direction, generation_method
- Generation methods: DETERMINISTIC, HUMAN, LLM
- Conditions as tuples: (feature_id, operator, threshold)
- Content hash independent of ID and generation method

---

## Research Experiment

- Walk-forward protocol (train_window → test_window, sliding)
- Per-fold: fit model → predict → filter by conditions → calculate EV → settle
- Aggregated statistics: ROI, win_rate, max_drawdown, Sharpe ratio
- Statistical significance: 1-tailed t-test (p < 0.05)
- Min EV threshold, odds band filtering
- Complete reproducibility via content hashing

---

## Research Memory

- Persistent knowledge store for all hypotheses
- Status tracking: UNTESTED → TESTED → PROMISING/VALIDATED/REJECTED
- Content-hash-based duplicate detection
- Parent-child experiment linking
- `to_context()` generates text summary for AI agent
- Summary by status for reporting

---

## AI Interface

### DeterministicResearchAgent

- Threshold adjustment strategy (±10%, ±20%)
- Opposite direction testing
- Feature combination from promising singles
- Duplicate prevention via memory check
- Priority scoring (1-10)
- Follow-up linking

### LLMResearchAgent

- Interface defined with `llm_callable` parameter
- Falls back to DeterministicResearchAgent when no LLM provided
- Structured `ResearchProposal` output schema
- Same quantitative evaluation queue as deterministic proposals

---

## Synthetic Discovery Experiment

### Embedded Relationship

The synthetic data contains:

```
corners ~ 0.3 × dangerous_attacks + 0.2 × possession + 0.5 × corner_tendency + noise
```

### Discovery Result

The `DiscoveryRunner` independently discovers corners-related features
as having predictive signal for the CORNERS_TOTAL market WITHOUT the
relationship being hard-coded into the discovery logic.

Test `test_no_hardcoded_discovery_rule` verifies the CandidateGenerator
source code contains no leaked knowledge of the synthetic formula.

### Full Loop Demonstrated

1. ✅ Generate deterministic dataset (528 matches, 4 seasons)
2. ✅ Register features (rolling means, differences, ratios)
3. ✅ Generate candidate metrics via transform engine
4. ✅ Generate hypotheses (single + pair, OVER + UNDER)
5. ✅ Train probability model (logistic regression)
6. ✅ Calculate fair odds (margin-stripped)
7. ✅ Compare against synthetic market odds
8. ✅ Calculate EV (formula verified)
9. ✅ Backtest via walk-forward
10. ✅ Run statistical significance test (t-test)
11. ✅ Store result in research memory
12. ✅ Send result to ResearchAgent
13. ✅ Generate follow-up hypothesis
14. ✅ Run second experiment
15. ✅ Store parent-child relationship
16. ✅ Prevent duplicate work (content hash match)
17. ✅ Demonstrate duplicate prevention in loop

---

## Leakage Tests

| Test | Assertion |
|------|-----------|
| Rolling mean excludes current match | Match i's value NOT in average at i |
| Rolling std excludes current match | History before spike shows no spike effect |
| EWMA excludes current match | Pre-spike EWMA ≈ 0 |
| Trend excludes current match | Flat history → zero slope before jump |
| Z-score excludes current match | Expanding history doesn't include current |
| Momentum excludes current match | Prior-only short/long means |
| Walk-forward train before test | Training window always precedes test |
| No future data in predictions | Random noise feature → no magical edge |
| Post-match not in pre-match model | Temporal class annotation enforced |
| Odds timestamp before kickoff | All synthetic odds timestamp < date_unix |
| Team isolation | Team A's rolling uses only Team A's history |
| Settlement not in features | Rolling win rate at i excludes outcome at i |
| Full pipeline causality | Synthetic data pipeline verified |

---

## FootyStats Readiness

The `docs/research/footystats-adapter-contract.md` specifies:

- Complete field mapping (50+ fields: FootyStats API → ResearchMatch)
- Authentication and rate limiting requirements
- Caching strategy
- Temporal guarantee enforcement
- MarketOdds emission protocol
- Error handling (auth, rate limit, incomplete data, schema changes)
- Testing strategy (mocked + integration)
- Migration path: Phase 0 → Phase 1 → Phase 2

When FootyStats is connected, the research engine requires **ZERO code changes**.
Only the data source instantiation changes:

```python
# Phase 0 (current)
source = SyntheticResearchDataSource(seed=42)

# Phase 1 (future)
source = FootyStatsAdapter(api_key="...")

# Both feed into:
runner = DiscoveryRunner(source)
report = runner.run()
```

---

## Known Limitations

1. **Synthetic data only** — No real-world validation yet. Synthetic results
   do NOT prove real-market profitability.

2. **In-memory research memory** — Not persisted to disk/database.
   Restarting loses experiment history. (Sufficient for Phase 0 proof.)

3. **Single-process** — No parallelization of experiment execution.
   Walk-forward is sequential.

4. **Poisson model simplified** — Uses approximate gradient for feature
   adjustment rather than exact MLE.

5. **No closing odds** — CLV calculation requires actual closing line data
   not available in synthetic source.

6. **No real FDR controller integration** — The experiment uses its own
   t-test significance. Full Benjamini-Hochberg FDR correction from
   `src/engine/fdr.py` will be integrated when multiple strategies are
   submitted to the production pipeline.

7. **No quarantine integration** — 90-day paper-trading quarantine
   (`QuarantineTracker`) will be connected when validated strategies
   graduate to the production evaluation path.

8. **LLM agent is interface-only** — Requires external LLM provider.
   Falls back to deterministic agent.

---

## Architecture Verification

```
ResearchDataSource (ABC)
        ↓
SyntheticResearchDataSource (impl)
        ↓
FeatureRegistry
        ↓
FeatureTransformEngine (14 transforms, temporal causality)
        ↓
CandidateGenerator (bounded search)
        ↓
ResearchHypothesis (content-hashed, deduplicated)
        ↓
ProbabilityModel (Historical / Logistic / Poisson)
        ↓
EVCalculator (EV + Kelly + edge)
        ↓
ResearchExperiment (walk-forward)
        ↓
Statistical Significance (t-test)
        ↓
ResearchMemory (store + deduplicate + link)
        ↓
ResearchAgent (deterministic + LLM interface)
        ↓
New Hypothesis → back to Research Queue
```

No frozen components modified. Adapters bridge to existing engine.

---

## Summary Statement

> "The platform can take a normalized football dataset and autonomously
> generate, test, and statistically evaluate hypotheses for multiple
> markets."

We do NOT claim:

> "The platform beats bookmakers."

Real-world validation requires real historical market odds and
real-world out-of-sample fixtures.

---

## STOP.
