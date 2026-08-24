# Design: Automated Strategy Mining & Hypothesis Generator

## References
- #[[file:.kiro/specs/strategy-miner/requirements.md]]
- #[[file:.kiro/specs/ingestion-and-backtester/design.md]]

---

## 1. System Architecture Overview

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                       Strategy Mining Module                                   │
├──────────────────┬──────────────────┬──────────────────┬──────────────────────┤
│  Feature         │  Hypothesis      │  Strategy        │  Statistical         │
│  Combinator      │  Generator       │  Evaluator       │  Filter              │
├──────────────────┼──────────────────┼──────────────────┼──────────────────────┤
│ • Raw metric     │ • Rule tree      │ • 2-season       │ • N >= 250           │
│   extraction     │   construction   │   walk-forward   │ • ROI > +5%          │
│ • Composite      │ • Threshold      │ • Per-hypothesis │ • p-value < 0.05     │
│   ratio gen      │   sweeping       │   backtest       │ • CLV beat > 65%     │
│ • Rolling norm   │ • Deduplication  │ • Batch eval     │ • Ranked output      │
└────────┬─────────┴────────┬─────────┴────────┬─────────┴──────────┬───────────┘
         │                  │                  │                    │
         ▼                  ▼                  ▼                    ▼
  List[FeatureFormula]  List[HypothesisRule]  EvaluationResult  List[MinedStrategyResult]
         │                  │                  │                    │
         └──────────────────┴──────────────────┴────────────────────┘
                                    │
                    Integrates with existing modules:
                    • src/ingestion/ (data sourcing)
                    • src/backtest/metrics.py (MetricsAggregator)
                    • src/backtest/bet_log.py (BetLogger)
                    • src/backtest/staking.py (StakingCalculator)
```

---

## 2. Module Boundaries

### 2.1 Mining Module (`src/mining/`)

All new code lives under `src/mining/` with clear separation of concerns:

| Component | File | Responsibility |
|-----------|------|----------------|
| `FeatureCombinator` | `combinator.py` | Generates composite feature formulas from raw metrics, computes rolling values |
| `HypothesisGenerator` | `generator.py` | Builds rule trees from features + threshold sweeps, deduplicates |
| `StrategyEvaluator` | `evaluator.py` | Executes per-hypothesis backtests across IS/OOS seasons |
| `StatisticalFilter` | `filter.py` | Applies cascading statistical filters, outputs survivors |
| `MarketConfig` | `markets.py` | Market-specific configuration (lines, relevant features, outcome resolution) |

### 2.2 Shared Models (`src/models/mining.py`)

New data structures for the mining module live alongside existing models:

| Structure | Purpose |
|-----------|---------|
| `MarketType` | Enum: GOALS, CORNERS, CARDS, OFFSIDES |
| `FeatureFormula` | Encodes a composite feature (operands + operator + rolling window) |
| `RuleCondition` | Single condition: feature + operator + threshold |
| `HypothesisRule` | Complete rule tree: list of conditions + prediction + market/line |
| `EvaluationMetrics` | Per-season evaluation results |
| `MinedStrategyResult` | Full output: rule + IS metrics + OOS metrics + metadata |
| `MiningConfig` | Configuration for the mining pipeline |

---

## 3. Data Structures

### 3.1 MarketType

```python
from enum import Enum

class MarketType(str, Enum):
    """Supported betting markets."""
    GOALS = "goals"
    CORNERS = "corners"
    CARDS = "cards"
    OFFSIDES = "offsides"
```

### 3.2 FeatureFormula

```python
from dataclasses import dataclass
from typing import Optional

class FormulaOperator(str, Enum):
    """Operators for combining raw metrics."""
    DIVIDE = "/"
    MULTIPLY = "*"
    SUBTRACT = "-"
    ADD = "+"

@dataclass(frozen=True, slots=True)
class FeatureFormula:
    """Definition of a composite feature derived from raw metrics.

    Example: shots_on_target / shots_total = shot accuracy
    """
    name: str                          # Human-readable: "shot_accuracy"
    operand_a: str                     # Raw metric name: "shots_on_target"
    operator: FormulaOperator          # Operator: "/"
    operand_b: str                     # Raw metric name: "shots_total"
    operand_c: Optional[str] = None    # Optional 3rd operand for triple composites
    operator_b: Optional[FormulaOperator] = None  # Operator between (A op B) op_b C
    rolling_window: int = 5            # Rolling average window
    market_relevance: tuple[MarketType, ...] = ()  # Which markets this feature targets
```

### 3.3 RuleCondition & HypothesisRule

```python
from dataclasses import dataclass, field
from typing import List

class ComparisonOperator(str, Enum):
    """Comparison operators for rule conditions."""
    GT = ">"
    LT = "<"
    GTE = ">="
    LTE = "<="

@dataclass(frozen=True, slots=True)
class RuleCondition:
    """A single condition in a hypothesis rule tree."""
    feature_name: str              # Composite feature identifier
    operator: ComparisonOperator   # Comparison operator
    threshold: float               # Threshold value (from percentile sweep)

    def evaluate(self, feature_value: float) -> bool:
        """Evaluate this condition against a feature value."""
        ...

@dataclass(frozen=True, slots=True)
class HypothesisRule:
    """Complete strategy hypothesis: conditions → prediction.

    All conditions are combined with AND logic.
    Maximum 3 conditions (depth limit).
    """
    rule_id: str                           # Unique identifier (hash of conditions)
    conditions: tuple[RuleCondition, ...]  # 1–3 conditions (AND logic)
    prediction: str                        # "OVER" or "UNDER"
    market: MarketType                     # Target market
    line: float                            # Target line (e.g., 2.5 for goals)

    def evaluate(self, features: dict[str, float]) -> bool:
        """Return True if all conditions are satisfied."""
        ...
```

### 3.4 EvaluationMetrics & MinedStrategyResult

```python
@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    """Metrics for a single evaluation period (IS or OOS)."""
    net_roi_pct: float
    win_rate_pct: float
    max_drawdown_pct: float
    p_value: float
    total_bets: int
    total_staked: float
    total_profit: float
    clv_beat_rate: Optional[float] = None  # Only computed for OOS

@dataclass(slots=True)
class MinedStrategyResult:
    """Complete output for a strategy that survived all filters."""
    rule: HypothesisRule
    is_metrics: EvaluationMetrics          # In-sample results
    oos_metrics: EvaluationMetrics         # Out-of-sample results
    feature_formulas: list[FeatureFormula]  # Formulas used in conditions
    discovery_timestamp: str               # ISO timestamp
    league_id: int
    season_is: str
    season_oos: str

@dataclass(frozen=True, slots=True)
class MiningConfig:
    """Configuration for the full mining pipeline."""
    # Feature generation
    max_features: int = 200
    rolling_window: int = 5

    # Hypothesis generation
    max_hypotheses_per_market: int = 50_000
    max_rule_depth: int = 3
    threshold_percentiles: tuple[int, ...] = (10, 20, 30, 40, 50, 60, 70, 80, 90)

    # Evaluation
    n_workers: int = 1

    # Statistical filters
    min_bets: int = 250
    min_roi_pct: float = 5.0
    max_p_value: float = 0.05
    min_clv_beat_rate: float = 0.65
```

---

## 4. Data Flow

```
┌─────────────────┐
│ IngestionPipeline│  (existing module)
│ league_id +      │
│ season_is/oos    │
└────────┬─────────┘
         │  List[Match] per season
         ▼
┌────────────────────┐
│ FeatureCombinator  │
│ • Extract raw      │
│   metrics          │
│ • Generate         │
│   composites       │
│ • Rolling + norm   │
└────────┬───────────┘
         │  Dict[match_id → Dict[feature_name → float]]
         ▼
┌────────────────────┐
│ HypothesisGenerator│
│ • Per market:      │
│   threshold sweep  │
│ • Build rule trees │
│ • Deduplicate      │
└────────┬───────────┘
         │  List[HypothesisRule]
         ▼
┌────────────────────┐         ┌─────────────────────┐
│ StrategyEvaluator  │◄────────│ MetricsAggregator   │ (existing)
│ • IS evaluation    │         │ BetLogger           │ (existing)
│ • OOS evaluation   │         │ StakingCalculator   │ (existing)
│ • Batch + parallel │         └─────────────────────┘
└────────┬───────────┘
         │  List[(HypothesisRule, EvaluationMetrics_IS, EvaluationMetrics_OOS)]
         ▼
┌────────────────────┐
│ StatisticalFilter  │
│ 1. N >= 250       │
│ 2. ROI > +5%      │
│ 3. p < 0.05       │
│ 4. CLV > 65%      │
└────────┬───────────┘
         │  List[MinedStrategyResult]
         ▼
  data/results/mined_strategies.jsonl
```

---

## 5. Integration with Existing Modules

### 5.1 Ingestion Integration

The mining module consumes matches from `IngestionPipeline` identically to the existing backtest:

```python
from src.ingestion.pipeline import IngestionPipeline

pipeline = IngestionPipeline()
matches_is = pipeline.ingest_from_fixtures(league_id, season_is)
matches_oos = pipeline.ingest_from_fixtures(league_id, season_oos)
```

The `Match` dataclass will be extended with optional fields for corners, cards, offsides, shots etc. A new `MatchExtended` or addition of optional fields to the existing `Match` model will be needed.

### 5.2 Backtest Module Reuse

```python
from src.backtest.metrics import MetricsAggregator
from src.backtest.bet_log import BetLogger
from src.backtest.staking import StakingCalculator
```

The `StrategyEvaluator` creates a `BetLogger` per hypothesis, records bets, then passes the records to `MetricsAggregator.compute()` for metrics.

### 5.3 Match Model Extension

The existing `Match` dataclass needs additional optional fields:

```python
# Added to src/models/match.py
@dataclass
class Match:
    # ... existing fields ...

    # Extended stats (optional, for mining module)
    home_shots: Optional[int] = None
    away_shots: Optional[int] = None
    home_shots_on_target: Optional[int] = None
    away_shots_on_target: Optional[int] = None
    home_shots_blocked: Optional[int] = None
    away_shots_blocked: Optional[int] = None
    home_corners: Optional[int] = None
    away_corners: Optional[int] = None
    home_fouls: Optional[int] = None
    away_fouls: Optional[int] = None
    home_yellow_cards: Optional[int] = None
    away_yellow_cards: Optional[int] = None
    home_red_cards: Optional[int] = None
    away_red_cards: Optional[int] = None
    home_offsides: Optional[int] = None
    away_offsides: Optional[int] = None
    home_crosses: Optional[int] = None
    away_crosses: Optional[int] = None
    home_through_balls: Optional[int] = None
    away_through_balls: Optional[int] = None
    home_possession_pct: Optional[float] = None
    away_possession_pct: Optional[float] = None
    home_defensive_line_height: Optional[float] = None
    away_defensive_line_height: Optional[float] = None
    total_corners: Optional[int] = None
    total_cards: Optional[int] = None
    total_offsides: Optional[int] = None

    # Closing odds (for CLV calculation)
    closing_over_odds: Optional[float] = None
    closing_under_odds: Optional[float] = None
```

---

## 6. Market Configuration

Each market has specific outcome resolution logic and relevant features:

```python
MARKET_CONFIGS = {
    MarketType.GOALS: {
        "lines": [0.5, 1.5, 2.5, 3.5, 4.5],
        "outcome_field": "total_goals",
        "relevant_metrics": [
            "shots_total", "shots_on_target", "home_xg", "away_xg",
            "crosses_total", "through_balls",
        ],
    },
    MarketType.CORNERS: {
        "lines": [7.5, 8.5, 9.5, 10.5, 11.5],
        "outcome_field": "total_corners",
        "relevant_metrics": [
            "crosses_total", "shots_blocked", "possession_pct",
            "defensive_line_height", "corners_total",
        ],
    },
    MarketType.CARDS: {
        "lines": [2.5, 3.5, 4.5, 5.5],
        "outcome_field": "total_cards",
        "relevant_metrics": [
            "fouls_committed", "cards_yellow", "cards_red",
            "referee_card_avg",
        ],
    },
    MarketType.OFFSIDES: {
        "lines": [1.5, 2.5, 3.5],
        "outcome_field": "total_offsides",
        "relevant_metrics": [
            "through_balls", "defensive_line_height",
            "offsides_total",
        ],
    },
}
```

---

## 7. Directory Structure (additions)

```
src/
├── mining/
│   ├── __init__.py
│   ├── combinator.py       # FeatureCombinator
│   ├── generator.py        # HypothesisGenerator
│   ├── evaluator.py        # StrategyEvaluator
│   ├── filter.py           # StatisticalFilter
│   └── markets.py          # MarketType configs, outcome resolution
├── models/
│   ├── mining.py           # FeatureFormula, HypothesisRule, MinedStrategyResult, MiningConfig
│   └── match.py            # Extended with optional stats fields
tests/
├── test_mining/
│   ├── __init__.py
│   ├── test_combinator.py
│   ├── test_generator.py
│   ├── test_evaluator.py
│   └── test_filter.py
├── fixtures/
│   └── 4759_2023_extended.json  # Fixture with full stats for mining tests
```

---

## 8. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Separate `FeatureFormula` from computed values | Formula is the *recipe*; values are computed per-match. Enables serialization of discovered strategies without storing all data. |
| AND-only rule trees (no OR) | Simpler search space, easier to interpret. OR logic can be expressed as two separate rules. |
| Canonical condition ordering | Enables O(1) deduplication via hashing sorted condition tuples. |
| Precompute features once per season | Avoids redundant computation across 50K+ hypothesis evaluations. Feature matrix computed once, indexed by match_id. |
| 2-season protocol (not k-fold) | True out-of-sample: IS discovery followed by OOS verification prevents overfitting to noise. More realistic than time-series CV for strategy discovery. |
| Filter cascade (cheapest first) | `N >= 250` is a simple count (O(1)). ROI check is O(1) on precomputed metrics. p-value is O(1). CLV requires per-bet comparison (O(N)). Ordering minimizes total computation. |
| Optional `Match` fields for extended stats | Backward-compatible with existing ingestion pipeline. Mining module gracefully skips matches missing stats. |
| `max_hypotheses` cap | Prevents runaway computation. 50K rules × 400 matches = 20M evaluations — tractable in under 5 min single-core. |
| JSONL output (not JSON array) | Append-friendly for incremental discovery runs. Each line is a self-contained result. |

---

## 9. Performance Considerations

- **Feature matrix**: Precomputed as a NumPy array `(n_matches × n_features)` for vectorized condition evaluation.
- **Batch condition evaluation**: Each condition `feature > threshold` is evaluated as a vectorized boolean mask across all matches simultaneously.
- **Hypothesis evaluation**: Compound conditions are evaluated via element-wise `AND` of boolean masks, yielding qualifying match indices in O(n_matches) per hypothesis.
- **Memory**: Feature matrix for 800 matches × 200 features = 1.28 MB (float64). 50K hypothesis results ≈ 50 MB. Well within 2 GB NFR.
- **Parallelism**: Hypothesis evaluation is embarrassingly parallel — each hypothesis is independent. `multiprocessing.Pool` with chunk_size for distribution.
