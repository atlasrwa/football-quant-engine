# Batch 3 — Candidate Discovery Engine

## Architecture

```
FeatureRegistry
      ↓
FeatureFamilyRegistry (organizational categories)
      ↓
ParameterSpace (bounded search domains)
      ↓
CandidateDiscoveryEngine
      ↓
ResearchCandidate (reproducible, hashed)
```

## Candidate Schema

```python
ResearchCandidate:
    candidate_id: str           # Human-readable ID
    market_type: str            # Target market (e.g., "CORNERS_TOTAL")
    feature_ids: tuple[str]     # Features used (sorted for hash)
    conditions: tuple[Condition] # Atomic predicates (AND logic)
    operator_type: Enum         # THRESHOLD_GT, DIFFERENCE_GT, RATIO_GT, etc.
    direction: str              # Expected outcome: OVER/UNDER/HOME/DRAW/AWAY
    generation_method: Enum     # DETERMINISTIC_GRID, DETERMINISTIC_QUANTILE, HUMAN, LLM
    parameters: dict            # Generation parameters
    feature_families: tuple     # Families used
    required_observations: int  # Minimum matches needed
    content_hash: str           # Deterministic identity (16 hex chars)
    status: Enum                # GENERATED → READY (after filtering)
```

## Candidate Condition

```python
CandidateCondition:
    feature_id: str
    operator: str    # ">", "<", ">=", "<="
    threshold: float
```

## Generation Operators

| Operator | Example | Description |
|----------|---------|-------------|
| THRESHOLD_GT | `feature > 5.0` | Single feature above threshold |
| THRESHOLD_LT | `feature < 3.0` | Single feature below threshold |
| DIFFERENCE_GT | `feat_a - feat_b > 2.0` | Difference between two features |
| DIFFERENCE_LT | `feat_a - feat_b < -1.0` | Negative difference |
| RATIO_GT | `feat_a / feat_b > 1.25` | Ratio above threshold |
| RATIO_LT | `feat_a / feat_b < 0.8` | Ratio below threshold |
| INTERACTION_AND | `feat_a > x AND feat_b > y` | Multiple conditions |
| TREND_GT | `trend(feature) > 0` | Positive trend |
| TREND_LT | `trend(feature) < 0` | Negative trend |
| RELATIVE_GT | `home - away > threshold` | Home/away differential |
| RELATIVE_LT | `home - away < threshold` | Negative differential |

## Parameter Search

```python
ParameterRange(name="window", start=3, stop=10, step=1)  → [3,4,5,6,7,8,9,10]
ParameterSet(name="quantile", values=(0.25, 0.50, 0.75))
ParameterGrid(dimensions=(...), max_combinations=1000)
```

Grids enforce `max_combinations` to prevent unbounded iteration.

## Feature Families

| Family | Source Fields | Markets |
|--------|-------------|---------|
| ATTACKING | dangerous_attacks, attacks | GOALS, CORNERS |
| SHOOTING | shots, shots_on_target | GOALS |
| CORNERS | corners | CORNERS |
| CARDS | yellow_cards, red_cards | CARDS |
| OFFSIDES | offsides | OFFSIDES |
| POSSESSION | possession | CORNERS, GOALS |
| DISCIPLINE | fouls | CARDS |
| TEMPO | ppda | CARDS, OFFSIDES |
| FORM | xg | GOALS, BTTS |
| HOME_AWAY | (venue-specific) | GOALS, BTTS |
| XMETRICS | xC, xB, xO | ALL |
| GENERAL | (fallback) | ALL |

## Budget Controls

```python
DiscoveryBudget:
    max_features_per_candidate: 3
    max_interaction_depth: 2
    max_candidates: 500
    max_candidates_per_market: 200
    max_candidates_per_family: 100
    max_parameter_combinations: 100
    min_observations: 50
    correlation_threshold: None  # Optional (0-1)
```

## Deduplication

Content hash uses canonical JSON serialization:
- `feature_ids` sorted alphabetically
- `conditions` sorted by (feature_id, operator, threshold)
- `sort_keys=True` in JSON
- Independent of `candidate_id`, `created_at`, `status`

Equivalent candidates always produce the same 16-character hex hash.

## Hashing Rules

1. Order-independent: `(feat_a, feat_b)` == `(feat_b, feat_a)` in hash
2. Deterministic: same inputs → same hash across runs
3. Unique: different conditions → different hash
4. Lightweight: 16 hex chars (64-bit collision resistance)

## Temporal Guarantees

- Only DERIVED or PRE_MATCH features used in candidates
- POST_MATCH raw values never enter candidate conditions
- `required_observations` enforces minimum historical data
- Feature transform engine enforces causality at compute time

## Missing-Data Behavior

- `CandidateCondition.evaluate(None)` → `None` (not True/False)
- Features with too few observations → candidate filtered out
- Division by zero in ratios → match excluded from sample

## Sample-Size Rules

A candidate is **researchable** only if:
- At least `min_observations` matches have ALL required features present
- Candidates failing this check are filtered before evaluation

## Performance Characteristics

Benchmark (100 features, 200 matches, budget=200):
- Generates candidates in < 1 second
- Budget cap enforced deterministically
- Deduplication is O(n) via hash set
- No external dependencies

## Known Limitations

1. No LLM-guided generation (deferred to Batch 7)
2. No persistence (in-memory only)
3. No walk-forward evaluation (deferred to Batch 4)
4. Correlation filter is threshold-based, not full correlation matrix
5. Trend/momentum operators not yet in main discovery loop (structures exist)
6. No automatic feature importance ranking

## Extension Points for AI

The `GenerationMethod.LLM` enum value exists. Future AI integration:
1. AI proposes feature combinations → creates `ResearchCandidate` with method=LLM
2. Candidate enters same pipeline (dedup, filter, evaluate)
3. AI never bypasses budget, dedup, or statistical validation

## Example: Feature → Candidate

```
Feature: home_corners_avg (rolling_mean, window=5, source=corners_home)
    ↓
Transform: ROLLING_MEAN applied with temporal causality
    ↓
Metric: home_corners_avg = mean(corners_home for last 5 home matches)
    ↓
Candidate: home_corners_avg > 5.8 (75th percentile threshold)
    ↓
Hypothesis: When home_corners_avg > 5.8, P(OVER 9.5 corners) is elevated
    ↓
Status: READY (awaiting evaluation in Batch 4)
```
