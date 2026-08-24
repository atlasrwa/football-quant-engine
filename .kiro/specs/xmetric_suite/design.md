# Design: Proprietary x-Metric Suite (xC, xB, xO)

#[[file:requirements.md]]

## Architecture Overview

The x-Metric Suite introduces a new `src/engine/` module that sits alongside the existing `src/features/` and `src/backtest/` modules. It consumes raw FootyStats DataFrames (CSV-derived) and produces x-Metric columns that feed into a dedicated walk-forward backtester with statistical validation.

```
FootyStats CSV Data
       │
       ▼
┌─────────────────┐
│ engine/xmetrics │  ← Vectorized formula computation (xC, xB, xO)
└────────┬────────┘
         │ DataFrame with xC, xB, xO columns
         ▼
┌─────────────────┐
│ engine/evaluator│  ← Strategy JSON conditions → signals
└────────┬────────┘
         │ Signal list (direction + edge)
         ▼
┌─────────────────┐
│ engine/backtest │  ← Walk-forward chronological backtest
└────────┬────────┘
         │ BacktestResult (ROI, CLV, P&L, drawdown)
         ▼
┌─────────────────┐
│ engine/validator│  ← Statistical significance gate
└────────┬────────┘
         │ ValidationVerdict (pass/fail + stats)
         ▼
     Leaderboard
```

## Module Design

### 1. `src/engine/__init__.py`

Exports all public components.

### 2. `src/engine/xmetrics.py` — Vectorized Formula Engine

**Class: `XMetricEngine`**

```python
@dataclass(frozen=True)
class XMetricCoefficients:
    # xC
    xc_alpha: float = 0.45
    xc_beta: float = 0.30
    xc_gamma: float = 0.25
    # xB
    xb_delta: float = 0.02
    # xO
    xo_eta: float = 1.0

class XMetricEngine:
    def __init__(self, coefficients: XMetricCoefficients = XMetricCoefficients()):
        self.coeff = coefficients

    def compute_xC(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add home_xC, away_xC columns."""

    def compute_xB(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add home_xB, away_xB columns."""

    def compute_xO(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add home_xO, away_xO columns."""

    def compute_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """Chain all three computations."""
```

**Input DataFrame Schema** (FootyStats CSV columns):

| Column | Type | Used By |
|--------|------|---------|
| `shots_off_target_home` / `_away` | int | xC |
| `attacks_home` / `_away` | int | xC |
| `dangerous_attacks_home` / `_away` | int | xC |
| `possession_home` / `_away` | float | xC, xB |
| `corners_avg_against_home` / `_away` | float | xC |
| `fouls_home` / `_away` | int | xB |
| `cards_per_match_home` / `_away` | float | xB |
| `referee_cards_per_match` | float | xB |
| `xg_against_home` / `_away` | float | xB |
| `offsides_home` / `_away` | int | xO |
| `ppda_home` / `_away` | float | xO |
| `date_unix` | int | backtest ordering |
| `corners_line` | float | market line (xC target) |
| `cards_line` | float | market line (xB target) |
| `offsides_line` | float | market line (xO target) |
| `over_odds` / `under_odds` | float | betting odds |

**Vectorized Implementation Strategy:**
- All formulas use `pd.Series` arithmetic — no `.apply()` or `.iterrows()`.
- NaN propagation: missing fields produce NaN in output; downstream filters handle NaN rows.
- Division-by-zero protection: use `np.where(denominator != 0, result, 0.0)`.

### 3. `src/engine/evaluator.py` — Hypothesis Config Loader

**Strategy JSON Schema:**

```json
{
  "name": "High xC Corners Over",
  "metric": "xC",
  "market": "corners_over_under",
  "conditions": [
    {"field": "home_xC", "op": ">", "value": 0.65},
    {"field": "away_xC", "op": ">", "value": 0.55}
  ],
  "logic": "and",
  "direction": "OVER",
  "min_odds": 1.70
}
```

**Class: `StrategyEvaluator`**

```python
@dataclass(frozen=True)
class Condition:
    field: str
    op: str  # >, <, >=, <=, ==, !=
    value: float

@dataclass(frozen=True)
class Strategy:
    name: str
    metric: str
    market: str
    conditions: List[Condition]
    logic: str  # "and" | "or"
    direction: str  # "OVER" | "UNDER" | "BACK" | "LAY"
    min_odds: float = 1.50

@dataclass(frozen=True)
class Signal:
    match_index: int
    strategy_name: str
    direction: str
    edge: float
    odds: float

class StrategyEvaluator:
    OPERATORS: dict  # maps string ops to operator functions

    def load_strategies(self, path: Path) -> List[Strategy]:
        """Load and validate strategy JSON file."""

    def evaluate(self, df: pd.DataFrame, strategies: List[Strategy]) -> List[Signal]:
        """Evaluate all strategies against DataFrame rows."""
```

**Security:** No `eval()`/`exec()`. Operators are mapped to `operator.gt`, `operator.lt`, etc. via a static dispatch table.

### 4. `src/engine/backtest.py` — Walk-Forward Engine

**Class: `XMetricBacktester`**

```python
@dataclass(frozen=True)
class XBacktestConfig:
    train_window: int = 200
    test_window: int = 50
    step_size: int = 50
    base_stake: float = 1.0
    min_odds: float = 1.50
    max_odds: float = 5.00

@dataclass(frozen=True)
class XBetRecord:
    match_index: int
    strategy_name: str
    direction: str
    odds: float
    stake: float
    outcome: str  # "WIN" | "LOSS" | "VOID"
    profit_loss: float
    clv: float  # closing line value

class XMetricBacktester:
    def __init__(self, config: XBacktestConfig, evaluator: StrategyEvaluator):
        ...

    def run(self, df: pd.DataFrame, strategies: List[Strategy]) -> BacktestResult:
        """Walk-forward backtest."""

    def _generate_folds(self, n: int) -> List[Tuple[range, range]]:
        """Generate train/test index ranges."""

    def _run_fold(self, train_df, test_df, strategies) -> List[XBetRecord]:
        """Execute a single fold (no coefficient tuning on test)."""
```

**Walk-Forward Logic:**
1. Sort DataFrame by `date_unix`.
2. Generate sliding folds: `[0:200]→[200:250]`, `[50:250]→[250:300]`, etc.
3. For each fold: freeze coefficients, evaluate strategies on test window, record bets.
4. Aggregate: total P&L, ROI, max drawdown, per-fold stats.

**CLV Calculation:** `clv = (signal_odds - closing_odds) / closing_odds` — measures how much edge the signal captured before market moved.

### 5. `src/engine/validator.py` — Statistical Significance Gate

**Class: `StatisticalValidator`**

```python
@dataclass(frozen=True)
class ValidationCriteria:
    min_sample_size: int = 250
    max_p_value: float = 0.05
    min_roi_pct: float = 3.0

@dataclass(frozen=True)
class ValidationVerdict:
    passed: bool
    p_value: float
    mean_profit: float
    roi_pct: float
    sample_size: int
    confidence_interval: Tuple[float, float]
    effect_size: float  # Cohen's d
    reason: str

class StatisticalValidator:
    def __init__(self, criteria: ValidationCriteria = ValidationCriteria()):
        ...

    def validate(self, bet_records: List[XBetRecord]) -> ValidationVerdict:
        """Run full statistical validation pipeline."""

    def _t_test(self, profits: np.ndarray) -> Tuple[float, float]:
        """1-sample 1-tailed t-test (H1: mean > 0)."""

    def _cohens_d(self, profits: np.ndarray) -> float:
        """Effect size calculation."""

    def _confidence_interval(self, profits: np.ndarray, alpha: float) -> Tuple[float, float]:
        """95% CI for mean profit."""
```

## Data Flow

1. **CSV Load** → `pd.read_csv()` (handled externally or by CLI)
2. **XMetricEngine.compute_all(df)** → DataFrame gains `home_xC`, `away_xC`, `home_xB`, `away_xB`, `home_xO`, `away_xO`
3. **StrategyEvaluator.evaluate(df, strategies)** → `List[Signal]` for qualifying matches
4. **XMetricBacktester.run(df, strategies)** → `BacktestResult` with fold-level granularity
5. **StatisticalValidator.validate(bets)** → `ValidationVerdict` (promote or reject)

## Integration with Existing Codebase

- **Does NOT modify** existing `src/backtest/`, `src/features/`, or `src/models/`.
- **New dependency:** `pandas` added to `pyproject.toml`.
- **CLI extension:** New subcommand `xmetrics` added to `src/cli.py` with sub-actions: `compute`, `evaluate`, `backtest`, `validate`.
- **Config reuse:** `XBacktestConfig` is independent but follows the same frozen-dataclass pattern as `StrategyConfig`.

## Error Handling

- Missing columns → log warning, fill with NaN, skip affected rows in signals.
- Division by zero → protected with `np.where` guards, returns 0.0.
- Invalid strategy JSON → raise `ValueError` with descriptive message at load time.
- Insufficient data for fold → skip fold, log warning with fold index.

## File Layout

```
src/engine/
├── __init__.py
├── xmetrics.py      # XMetricCoefficients, XMetricEngine
├── evaluator.py     # Condition, Strategy, Signal, StrategyEvaluator
├── backtest.py      # XBacktestConfig, XBetRecord, XMetricBacktester
└── validator.py     # ValidationCriteria, ValidationVerdict, StatisticalValidator

tests/
├── test_xmetrics.py
├── test_evaluator.py
├── test_xbacktest.py
└── test_validator.py
```
