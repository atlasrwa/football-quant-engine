# Batch 4 — Experiment Engine

## Overview

The Experiment Engine transforms generated candidates into controlled historical experiments that produce statistical evidence about predictive relationships.

This is the first stage where the system can answer:

> "Given a generated candidate and historical data, does this relationship actually contain predictive information for a specified market?"

**This module produces RESEARCH EVIDENCE only. It does not claim profitability.**

## Architecture

```
ResearchCandidate (Batch 3)
        │
        ▼
ExperimentHypothesis
        │
        ▼
ExperimentConfig
        │
        ▼
ResearchDataset ◄── ResearchDataSource (Batch 1)
        │
        ▼
TemporalSplit (TRAIN / VALIDATION / TEST)
        │
        ▼
ExperimentRunner
        │
        ├── Model Training (training data ONLY)
        ├── Probability Generation (evaluation data)
        ├── Market Outcome Resolution
        ├── EV Calculation (where odds exist)
        ├── Calibration Metrics
        ├── Baseline Comparison
        └── Statistical Evidence
        │
        ▼
ExperimentResult
        │
        ├── PredictiveMetrics (Brier, LogLoss, ECE, MCE)
        ├── EconomicMetrics (EV, ROI — only with odds)
        ├── BaselineComparison (candidate vs base rate)
        ├── StatisticalEvidence (p-value, effect size, CI)
        └── EvidenceClassification (research label)
```

## Module Structure

```
src/research/experiment_engine/
├── __init__.py              # Package documentation
├── hypothesis.py            # ExperimentHypothesis (candidate → testable claim)
├── config.py                # ExperimentConfig (complete reproducibility spec)
├── temporal.py              # TemporalSplit, TemporalSplitFactory
├── dataset.py               # ResearchDataset (data source wrapper)
├── result.py                # ExperimentResult, metrics, classification
├── runner.py                # ExperimentRunner (execution engine)
├── reporting.py             # ExperimentReporter (human-readable output)
└── walkforward_adapter.py   # WalkForwardAdapter (Batch 5 boundary)
```

## Experiment Identity

Every experiment is deterministically identified by its content hash. The hash depends on:

- `hypothesis_hash` (from candidate conditions, direction, market)
- `market_type`
- `dataset_version` (content hash of dataset)
- `model_type` + `model_parameters`
- `experiment_version`
- `training_start` / `training_end`
- `evaluation_start` / `evaluation_end`
- `odds_mode`
- `thresholds`
- `random_seed`
- `features`

The hash does **NOT** include `created_at`, random UUIDs, or runtime-dependent values.

**Canonical serialization**: sorted JSON with no whitespace, via `json.dumps(obj, sort_keys=True, separators=(",", ":"))`.

Equivalent configurations always produce the same experiment ID. Different configurations always produce different IDs.

## Dataset Abstraction

The experiment runner does not care where data came from:

```python
ResearchDataSource (ABC)      # Batch 1 interface
        │
        ▼
ResearchDataset               # Wraps source + market + odds
        │
        ▼
ExperimentRunner              # Consumes dataset
```

Supported sources:
- `SyntheticResearchDataSource` — deterministic test data (528 matches, embedded corners relationship)
- Future: FootyStats, CSV, database providers

The same experiment code works identically regardless of data provider.

## Temporal Split

**CRITICAL**: Never evaluate a candidate using information unavailable at prediction time.

```
|-- TRAIN --|-- VALIDATION (optional) --|-- TEST --|
   ↑                                         ↑
   Model fitted here                         Predictions generated here
```

For every match T:
- Training data: `timestamp < prediction_timestamp(T)`
- Features: `information_timestamp <= prediction_timestamp(T)`
- Outcome: only available AFTER prediction

The default experiment is **chronological**. Random splitting exists only as an explicitly labeled utility.

Factory methods:
- `TemporalSplitFactory.from_timestamps(train_start, train_end, test_start, test_end)`
- `TemporalSplitFactory.from_ratios(matches, train_ratio, validation_ratio, test_ratio)`

Validation enforces: `TRAIN.end <= VALIDATION.start <= VALIDATION.end <= TEST.start`

## Candidate Evaluation

For every candidate in the evaluation period:

1. Determine whether conditions are satisfied
2. Handle NULL/missing values (NULL ≠ 0)
3. Exclude structurally invalid observations
4. Track sample size
5. Generate target outcomes
6. Train model using training data only
7. Generate probabilities for evaluation data
8. Compare probabilities with actual outcomes
9. Calculate market-implied probabilities where odds exist
10. Calculate EV where odds exist
11. Calculate fair odds
12. Record calibration metrics
13. Record predictive metrics

Observation tracking (never silently discards):
- `total_rows`
- `eligible_rows`
- `missing_rows`
- `invalid_rows`
- `insufficient_history_rows`
- `excluded_odds_filter`

## Model Integration

Reuses Batch 2 probability models:

| Model | Description |
|-------|-------------|
| `HistoricalFrequencyModel` | Historical base rate P(OVER) |
| `LogisticRegressionModel` | Feature-based logistic regression |
| `PoissonModel` | Count-based Poisson distribution |

The experiment configuration selects the model. Models are **not** automatically selected. The purpose is research comparison.

If a model cannot estimate the requested market: returns `MODEL_NOT_COMPATIBLE` rather than silently substituting.

## Probability Output

Every prediction preserves:
- `match_id`, `prediction_timestamp`
- `model_probability`
- `actual_outcome`
- `is_hit`
- `market_odds`, `fair_odds`, `implied_probability`
- `expected_value`
- `ev_status` (VALID / MISSING_ODDS / INVALID_ODDS)
- `direction`

**Never fabricates missing odds.** If odds unavailable, EV becomes `MISSING_ODDS` (not zero).

## EV Handling

Three odds modes:

| Mode | Description |
|------|-------------|
| `NO_ODDS` | EV not calculated, probability research continues |
| `SYNTHETIC_ODDS` | Testing machinery only, no profitability claims |
| `HISTORICAL_ODDS` | Real bookmaker odds (future integration) |

EV formula: `P(model) × odds - 1`

## Baseline Comparison

Every experiment compares against a baseline:
- **Historical base rate** from training data
- Brier score comparison (baseline vs candidate model)

Answers: "Does this candidate actually add information?" not merely "Does this candidate correlate?"

## Statistical Evidence

Produced for each experiment:
- Sample size
- Mean outcome vs baseline outcome
- Difference
- 95% confidence interval
- Effect size (Cohen's h)
- p-value (one-sample proportion test)
- Significance determination

The result structure is designed for Batch 5 FDR integration:
```
StatisticalEvidence → FDRController.correct() (Batch 5)
```

## Calibration

Reuses Batch 2 `CalibrationEvaluator`:
- **Brier score**: Mean squared error of probabilities (0 = perfect)
- **Log loss**: Logarithmic scoring rule
- **ECE**: Expected Calibration Error
- **MCE**: Maximum Calibration Error

All calibration is evaluated on **out-of-sample** data only.

## Missing Data

- `NULL ≠ 0` — missing values are never replaced with zero
- Division by zero → marked invalid/missing
- Insufficient history → `INSUFFICIENT_DATA` status
- Every experiment reports exact missing/invalid counts

## Failure States

Explicit statuses (never converted to zero):

| Status | Meaning |
|--------|---------|
| `COMPLETED` | Experiment produced evidence |
| `INSUFFICIENT_DATA` | Not enough observations |
| `MODEL_FAILURE` | Model could not fit |
| `MODEL_NOT_COMPATIBLE` | Model cannot handle market |
| `MISSING_TARGET` | Target field unavailable |
| `MISSING_ODDS` | Odds unavailable for EV |
| `INVALID_CONFIGURATION` | Config validation failed |
| `TEMPORAL_VIOLATION` | Temporal ordering violated |

## Evidence Classification

Research labels (NOT production approval):

| Classification | Criteria |
|---------------|----------|
| `INSUFFICIENT_DATA` | < 30 samples |
| `NEGATIVE` | Significant, wrong direction |
| `NEUTRAL` | Not significant |
| `PROMISING` | p < 0.05, effect ≥ 0.02 |
| `STRONG_SIGNAL` | p < 0.01, effect ≥ 0.05 |

These are configurable research thresholds for prioritization.

## Reproducibility

Running the same dataset + candidate + hypothesis + model + configuration produces:
- Same `experiment_id`
- Same predictions
- Same metrics
- Same statistical results

Within expected numerical tolerance. Random seeds are explicitly controlled.

## Walk-Forward Compatibility (Batch 5)

The `WalkForwardAdapter` provides:
- Fold generation (rolling train/test windows)
- Config creation per fold
- Interface for Batch 5 integration

**Does NOT modify** the frozen `WalkForwardEngine` in `src/backtest/engine.py`.

Batch 5 integration path:
```
Candidate → Experiment → WalkForwardEngine → FDR → Quarantine
```

## Performance

Benchmark results (1000 matches × 50 hypotheses × 3 models × 3 markets):
- 450 total experiments
- 315 completed, 135 insufficient data
- 90,936 predictions generated
- 39.7s total execution
- 88ms average per experiment
- 11.3 experiments/second

## Complete Example

```python
from src.research.synthetic_data import SyntheticResearchDataSource
from src.research.market import MarketType, create_default_registry
from src.research.candidates import ResearchCandidate, CandidateCondition, CandidateOperator
from src.research.probability import HistoricalFrequencyModel
from src.research.experiment_engine.hypothesis import ExperimentHypothesis
from src.research.experiment_engine.config import ExperimentConfig, OddsMode
from src.research.experiment_engine.dataset import ResearchDataset
from src.research.experiment_engine.runner import ExperimentRunner
from src.research.experiment_engine.reporting import ExperimentReporter

# 1. Data source
source = SyntheticResearchDataSource(seed=42)
matches = source.get_matches()

# 2. Market
registry = create_default_registry()
market = registry.get(MarketType.CORNERS_TOTAL)

# 3. Candidate → Hypothesis
candidate = ResearchCandidate(
    candidate_id="corner_pressure",
    market_type="CORNERS_TOTAL",
    feature_ids=("dangerous_attacks_home",),
    conditions=(CandidateCondition("dangerous_attacks_home", ">", 20.0),),
    operator_type=CandidateOperator.THRESHOLD_GT,
    direction="OVER",
)
hypothesis = ExperimentHypothesis.from_candidate(candidate)

# 4. Dataset
dataset = ResearchDataset(source=source, market=market)

# 5. Configuration
midpoint = matches[int(len(matches) * 0.6)].date_unix
config = ExperimentConfig(
    hypothesis=hypothesis,
    market_type="CORNERS_TOTAL",
    dataset_version=dataset.content_hash,
    model_type="HistoricalFrequencyModel",
    training_start=matches[0].date_unix,
    training_end=midpoint,
    evaluation_start=midpoint,
    evaluation_end=matches[-1].date_unix + 1,
    odds_mode=OddsMode.SYNTHETIC_ODDS,
)

# 6. Run experiment
model = HistoricalFrequencyModel(min_observations=10)
runner = ExperimentRunner()
result = runner.run(config, dataset, model)

# 7. Report
reporter = ExperimentReporter()
print(reporter.generate_summary(result))

# 8. Access evidence programmatically
print(f"Status: {result.status.value}")
print(f"Classification: {result.classification.value}")
print(f"p-value: {result.statistical_evidence.p_value}")
print(f"Effect size: {result.statistical_evidence.effect_size}")
```

## Limitations

- Single temporal split (not full walk-forward) — Batch 5 adds multi-fold
- No FDR correction applied — Batch 5 integrates FDRController
- No real data provider connected — requires FootyStats adapter
- No persistent storage — results are in-memory only
- No AI/LLM integration
- No real bookmaker odds
- Synthetic odds: do NOT make profitability claims

## Batch 5 Integration Points

| Component | Current State | Batch 5 Action |
|-----------|--------------|----------------|
| WalkForwardAdapter | Interface defined, folds generated | Connect to FDRController |
| StatisticalEvidence | p-values produced | Feed to FDRController.correct() |
| ExperimentResult | Single-split evidence | Aggregate across walk-forward folds |
| QuarantineTracker | Not connected | Receive FDR-corrected results |
| ResearchDataSource | Synthetic only | Connect FootyStats adapter |
| OddsMode | SYNTHETIC/NO_ODDS | Add HISTORICAL_ODDS provider |
