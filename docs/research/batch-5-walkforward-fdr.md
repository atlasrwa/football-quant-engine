# Batch 5 — Walk-Forward Validation & FDR Governance

## Overview

Batch 5 adds rigorous multi-period out-of-sample validation and multiple-testing
governance on top of the Batch 4 Experiment Engine.

The system can now answer:

> "Does this apparently predictive relationship survive repeated out-of-sample
> testing across time, while controlling for the fact that we searched many
> hypotheses?"

## Architecture

```
Candidate
    ↓
Hypothesis
    ↓
Experiment (Batch 4)
    ↓
Walk-Forward Validation (Batch 5)
    ↓
Aggregate Evidence (Fisher's combined test)
    ↓
Multiple-Testing Correction (Benjamini-Hochberg)
    ↓
Research Classification
    ↓
Quarantine Eligibility
```

## Walk-Forward Architecture

### Module: `src/research/walkforward/`

The walk-forward system evaluates each hypothesis across multiple chronological
time periods, refitting the model for each period.

### Components

| File | Class | Purpose |
|------|-------|---------|
| `config.py` | `WalkForwardConfig` | Full configuration for walk-forward evaluation |
| `folds.py` | `FoldGenerator`, `FoldSpec` | Generates deterministic fold boundaries |
| `result.py` | `FoldResult`, `WalkForwardResult` | Per-fold and aggregate results |
| `orchestrator.py` | `WalkForwardOrchestrator` | Runs ExperimentRunner per fold |

### Fold Construction

Folds are generated deterministically from:
- Data start/end timestamps
- WalkForwardConfig parameters

Two window types are supported:

**EXPANDING:**
```
Fold 1: Train [Jan-Jun],   Test [Jul-Sep]
Fold 2: Train [Jan-Sep],   Test [Oct-Dec]
Fold 3: Train [Jan-Dec],   Test [Jan-Mar+1]
```
Training window grows with each fold. More data for later folds.

**ROLLING:**
```
Fold 1: Train [Jan-Jun],   Test [Jul-Sep]
Fold 2: Train [Apr-Sep],   Test [Oct-Dec]
Fold 3: Train [Jul-Dec],   Test [Jan-Mar+1]
```
Fixed-size training window slides forward. Tests regime adaptation.

### Temporal Guarantees

For every fold, the following strict ordering holds:

```
training_end ≤ [gap] ≤ validation_start ≤ validation_end ≤ [gap] ≤ test_start ≤ test_end
```

- No overlap between train, validation, and test segments
- A prediction for match T uses only information available before T
- Future outcomes, odds, statistics, and league averages are never accessible
- Optional gap_period prevents boundary contamination

### Configuration

```python
WalkForwardConfig(
    initial_training_period=180 * DAY,  # Minimum training window
    test_period=90 * DAY,               # Test window per fold
    step_period=90 * DAY,               # Advance between folds
    validation_period=30 * DAY,         # Optional validation (0 = none)
    minimum_training_observations=50,   # Min matches in training
    minimum_test_observations=10,       # Min matches in test
    window_type=WindowType.EXPANDING,   # EXPANDING or ROLLING
    minimum_folds=3,                    # Min folds for valid result
    maximum_folds=50,                   # Performance cap
    gap_period=7 * DAY,                 # Gap between segments
)
```

## Model Refitting

Models are refitted inside each walk-forward fold. The orchestrator:

1. Creates a **fresh model instance** via `model_factory()` for each fold
2. Passes fold-specific training data to `model.fit()`
3. Uses the fitted model for test predictions only
4. Never shares model state between folds

This prevents the following forms of leakage:
- Training on future data
- Parameter sharing across temporal periods
- Hyperparameter selection using test data

## Baseline Comparison

Each fold preserves the Batch 4 baseline comparison:
- Historical base rate computed from training data only
- Candidate performance compared against unconditional frequency
- Brier score improvement measured against naive baseline

## Fold Aggregation

### Methodology

Fold results are aggregated using **Fisher's combined probability test**:

```
X = -2 × Σ ln(p_i)
X ~ χ² with 2k degrees of freedom
```

This treats each fold as semi-independent evidence. It is more conservative
than concatenating all predictions and running a single test, because it
respects the fold structure.

### Stability Metrics

- `positive_fold_ratio`: Fraction of folds with positive outcome
- `roi_std`: Standard deviation of fold-level ROI
- `roi_iqr`: Interquartile range of fold ROIs
- `roi_mad`: Median absolute deviation
- `max_consecutive_negative`: Longest streak of losing folds
- `worst_fold_roi` / `best_fold_roi`: Extreme values

A candidate should not be considered robust because one fold produced
exceptional performance.

## FDR — Multiple Testing Correction

### Module: `src/research/fdr/`

### Problem

When testing 1000 hypotheses at α=0.05, we expect ~50 false positives
even when all hypotheses are null. Raw p-values cannot be treated as
independent proof.

### Solution: Benjamini-Hochberg Procedure

The research layer uses the frozen `FDRController` (in `src/engine/fdr.py`)
through an adapter pattern:

```
WalkForwardResult[] → extract combined p-values → FDRController.correct()
→ map back to hypothesis identifiers → FDRHypothesisResult[]
```

### Research Families

A research family defines the correction scope:

```python
ResearchFamily(
    family_id="deterministic_hash",
    market_type="CORNERS_TOTAL",
    dataset_version="abc123",
    research_run_id="run_001",
    candidate_generation_config="gen_config_hash",
    model_family="historical_frequency",
)
```

All hypotheses within the same family are corrected together.
The family definition prevents:
- Mixing unrelated research universes
- Under-correcting by splitting into artificial sub-groups
- Over-correcting by merging unrelated research runs

### FDR Interpretation

| Status | Meaning |
|--------|---------|
| `FDR_PASS` | Survives multiple-testing correction |
| `FDR_FAIL` | Does not survive correction |
| `INSUFFICIENT_DATA` | No valid p-value available |
| `INVALID_P_VALUE` | P-value out of valid range |

**IMPORTANT:** FDR_PASS does NOT mean profitable. It only means the
hypothesis survives the configured multiple-testing threshold.

## Governance States

### Module: `src/research/governance/`

### State Machine

```
DISCOVERED          → Initial candidate generation
    ↓
PROMISING           → Single experiment shows signal
    ↓
WALK_FORWARD_VALIDATED  → Multi-fold OOS evidence
    ↓
FDR_VALIDATED       → Survives multiple-testing correction
    ↓
QUARANTINE_ELIGIBLE → Meets all governance criteria
    ↓
QUARANTINED         → In paper-trading quarantine (90 days)
    ↓
REJECTED            → Failed at any stage
```

### Governance Criteria (Configurable)

```python
GovernanceCriteria(
    minimum_folds=5,
    minimum_positive_fold_ratio=0.6,
    minimum_sample_size=50,
    maximum_p_value=0.05,
    maximum_fdr_q_value=0.10,
    minimum_effect_size=0.01,
    minimum_calibration_quality=0.30,  # Max Brier score
    minimum_mean_ev=None,              # Optional economic gate
    maximum_allowed_drawdown=None,     # Optional stability gate
    maximum_consecutive_negative=5,
)
```

These are NOT hard-coded universal truths. Different research standards
can use different criteria.

## Quarantine Integration

The `QuarantineAdapter` bridges research governance to the frozen
`QuarantineTracker` in `src/engine/fdr.py`:

1. Research layer determines: "This candidate has satisfied statistical
   prerequisites for quarantine"
2. `QuarantineAdapter.submit_for_quarantine()` calls
   `QuarantineTracker.enter_quarantine()`
3. QuarantineTracker manages the 90-day paper-trading period
4. No automatic promotion to production

## Statistical vs Economic Evidence

These dimensions are kept strictly separate:

| Statistical | Economic |
|-------------|----------|
| p-value | EV |
| confidence interval | ROI |
| effect size | yield |
| FDR correction | drawdown |
| | CLV |

A candidate can be:
- Statistically significant but economically unattractive
- Economically attractive but statistically weak
- Well-calibrated but unprofitable
- FDR-validated but not production-ready

## Failure Behavior

The system fails safely for:
- Insufficient training/test data → `INSUFFICIENT_DATA` status
- Model fitting failure → `MODEL_FAILURE` status
- Missing odds → economic metrics unavailable (not fabricated)
- Invalid p-values → `INVALID_P_VALUE` (excluded from FDR)
- Empty folds → skipped, not crashed
- NaN values → treated as missing, never silently converted to zero

## Reproducibility

Same inputs always produce same outputs:

| Component | Hash |
|-----------|------|
| WalkForwardConfig | `content_hash` (16-char SHA-256 prefix) |
| WalkForwardResult | `content_hash` |
| ResearchFamily | `family_id` |
| ResearchFDRResult | `content_hash` |
| ResearchRunIdentity | `run_id` |
| GovernanceCriteria | `content_hash` |

Hashes exclude: `created_at`, runtime duration, memory addresses.

### ResearchRunIdentity

Captures complete provenance:
- dataset_version
- candidate_generation_version
- experiment_version
- walkforward_config_hash
- model_type + parameters
- fdr_alpha
- governance_criteria_hash
- market_type
- random_seed

## Known Limitations

1. **No real data** — SyntheticResearchDataSource only
2. **No persistence** — in-memory research objects
3. **No research queue** — sequential execution
4. **No AI researcher** — deterministic discovery only
5. **No paper trading integration** — quarantine submission only
6. **No multi-market settlement** — single-market evaluation
7. **No CLV in walk-forward** — requires real closing odds
8. **No hyperparameter search within folds** — validation segment
   architecture preserved but selection not automated
9. **Single model per walk-forward** — no ensemble

## Future Integration Points

### FootyStats (Batch 6+)
- Implement `ResearchDataSource` for FootyStats API
- Real historical odds enable true EV and CLV calculation
- No architecture changes needed

### AI Researcher (Batch 7+)
- Feeds hypotheses into the existing walk-forward pipeline
- Uses `ResearchRunIdentity` for memory
- Does not bypass FDR governance

### Paper Trading (Batch 8+)
- Extends `QuarantineAdapter` with real-time settlement
- 90-day paper trading on live fixtures
- Connects to existing `QuarantineTracker` lifecycle

### Production Promotion
- Requires: real data, real odds, paper trading period
- Uses existing `StatisticalValidator` and `QuarantineTracker`
- NOT implemented in Batch 5

## Performance

Benchmarked on synthetic data (528 matches, 4 seasons):

| Operation | Scale | Time |
|-----------|-------|------|
| Single walk-forward (8 folds) | 1 hypothesis | ~0.2s |
| Multi walk-forward | 51 hypotheses × 3 markets | 1.5s |
| FDR correction | 500 hypotheses | <0.001s |
| Governance pipeline | 100 hypotheses | 0.004s |
| Average per hypothesis | — | ~0.03s |

The system is computationally bounded and does not explode with scale.
