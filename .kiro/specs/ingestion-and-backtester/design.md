# Design: Ingestion & Backtester

## References
- #[[file:.kiro/specs/ingestion-and-backtester/requirements.md]]

---

## 1. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Football Quant Engine                           │
├─────────────────┬─────────────────────────┬─────────────────────────┤
│   Ingestion     │   Feature Engineering   │   Backtest Execution    │
│   Module        │   Module                │   Module                │
├─────────────────┼─────────────────────────┼─────────────────────────┤
│ • API Client    │ • xG Efficiency Calc    │ • Walk-Forward Engine   │
│ • JSON Cache    │ • Rolling Form Calc     │ • Staking Calculator    │
│ • Validator     │ • Referee Volatility    │ • Metrics Aggregator    │
│                 │ • Feature Assembler     │ • Bet Logger            │
└────────┬────────┴────────────┬────────────┴──────────┬──────────────┘
         │                     │                       │
         ▼                     ▼                       ▼
    data/raw/            data/features/          data/results/
    (cached JSON)        (feature vectors)       (backtest output)
```

---

## 2. Module Boundaries

### 2.1 Ingestion Module (`src/ingestion/`)

**Responsibility:** Fetch, cache, and validate raw match data from FootyStats.

| Component | File | Role |
|-----------|------|------|
| `FootyStatsClient` | `client.py` | HTTP client with rate limiting, retries, and key management |
| `CacheManager` | `cache.py` | Read/write local JSON cache, cache-hit detection |
| `SchemaValidator` | `validator.py` | Validate raw JSON against required field schema |
| `IngestionPipeline` | `pipeline.py` | Orchestrates client → cache → validation flow |

**Exports:** `List[Match]` — validated, typed match objects ready for feature engineering.

**Dependencies:** `httpx` (async HTTP), `pydantic` (validation), standard library.

---

### 2.2 Feature Engineering Module (`src/features/`)

**Responsibility:** Transform raw match data into computed feature vectors.

| Component | File | Role |
|-----------|------|------|
| `XGEfficiencyCalculator` | `xg_efficiency.py` | Computes per-team xG efficiency delta and rolling mean |
| `RollingFormCalculator` | `rolling_form.py` | Computes normalized rolling form per team |
| `RefereeVolatilityCalculator` | `referee_volatility.py` | Computes referee volatility index with fallback |
| `FeatureAssembler` | `assembler.py` | Combines all features into final match feature vector |

**Exports:** `List[MatchFeatures]` — feature vectors keyed by match ID.

**Dependencies:** `numpy` (statistical ops), ingestion module output.

---

### 2.3 Backtest Execution Module (`src/backtest/`)

**Responsibility:** Execute walk-forward backtest, apply staking logic, compute performance metrics.

| Component | File | Role |
|-----------|------|------|
| `WalkForwardEngine` | `engine.py` | Manages fold iteration, train/test splitting |
| `StakingCalculator` | `staking.py` | Volatility-adjusted stake sizing |
| `SignalGenerator` | `signal.py` | Generates over/under predictions and edge estimates |
| `MetricsAggregator` | `metrics.py` | Computes ROI, Win Rate, Max Drawdown, p-value |
| `BetLogger` | `bet_log.py` | Records per-bet outcomes |

**Exports:** `BacktestResult` — full result object with metrics and bet log.

**Dependencies:** `numpy`, `scipy` (t-test), feature engineering module output.

---

## 3. Data Structures

### 3.1 Match

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class Match:
    """Validated match record from FootyStats ingestion."""
    id: int
    date_unix: int
    league_id: int
    season: str
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    total_goals: int
    home_xg: float
    away_xg: float
    referee: Optional[str]
    over_under_line: float          # e.g., 2.5
    over_odds: Optional[float]      # decimal odds for Over
    under_odds: Optional[float]     # decimal odds for Under
```

### 3.2 MatchFeatures

```python
@dataclass
class MatchFeatures:
    """Computed feature vector for a single match."""
    match_id: int
    date_unix: int
    home_xg_eff_delta_rolling: float
    away_xg_eff_delta_rolling: float
    home_rolling_form: float        # 0–1 normalized
    away_rolling_form: float        # 0–1 normalized
    referee_volatility_index: float
    total_goals: int                # target variable
    over_under_line: float
    over_odds: Optional[float]
    under_odds: Optional[float]
```

### 3.3 StrategyConfig

```python
@dataclass
class StrategyConfig:
    """Configuration for backtest execution."""
    # Walk-forward parameters
    train_window: int = 100         # matches in training fold
    test_window: int = 20           # matches in test fold
    step_size: int = 20             # fold advance step

    # Feature parameters
    xg_rolling_window: int = 5
    form_rolling_window: int = 6
    referee_min_matches: int = 5
    variance_rolling_window: int = 10

    # Staking parameters
    base_stake: float = 1.0
    max_stake_multiplier: float = 3.0
    min_stake_multiplier: float = 0.25
    min_edge_threshold: float = 0.05

    # Reproducibility
    random_seed: int = 42
```

### 3.4 BacktestResult

```python
from dataclasses import dataclass, field
from typing import List

@dataclass
class BetRecord:
    """Single bet in the backtest log."""
    match_id: int
    date_unix: int
    prediction: str                 # "OVER" or "UNDER"
    actual_outcome: str             # "OVER" or "UNDER"
    odds: float
    stake: float
    profit_loss: float

@dataclass
class FoldResult:
    """Per-fold breakdown."""
    fold_index: int
    train_start: int                # match index
    train_end: int
    test_start: int
    test_end: int
    net_roi_pct: float
    win_rate_pct: float
    num_bets: int

@dataclass
class BacktestResult:
    """Complete backtest output."""
    # Aggregate metrics
    net_roi_pct: float
    win_rate_pct: float
    max_drawdown_pct: float
    p_value: float
    total_bets: int
    total_staked: float
    total_profit: float

    # Breakdowns
    fold_results: List[FoldResult] = field(default_factory=list)
    bet_log: List[BetRecord] = field(default_factory=list)

    # Config used
    strategy_config: StrategyConfig = field(default_factory=StrategyConfig)
```

---

## 4. Data Flow

```
FootyStats API
      │
      ▼
┌─────────────┐     cache miss      ┌──────────────┐
│  API Client ├─────────────────────►│  JSON Cache  │
└──────┬──────┘                      └──────┬───────┘
       │                                    │
       │         cache hit                  │
       ◄────────────────────────────────────┘
       │
       ▼
┌──────────────┐     invalid        ┌────────────────────┐
│  Validator   ├───────────────────►│  validation_errors │
└──────┬───────┘                    └────────────────────┘
       │ valid
       ▼
  List[Match]
       │
       ▼
┌──────────────────┐
│ Feature Assembler│ ◄── xG Calc, Form Calc, Ref Volatility
└──────┬───────────┘
       │
       ▼
  List[MatchFeatures]
       │
       ▼
┌──────────────────┐
│ Walk-Forward     │ ◄── StrategyConfig
│ Engine           │
└──────┬───────────┘
       │ per fold: train → predict → stake → log
       ▼
  BacktestResult
       │
       ▼
  data/results/backtest_YYYYMMDD_HHMMSS.json
```

---

## 5. Mock Data Generator Interface

For local testing without consuming API quota, the system provides a mock data path using the FootyStats public `key=example` endpoint.

### 5.1 MockDataProvider

```python
from typing import List, Protocol

class DataProvider(Protocol):
    """Interface for match data sourcing."""
    def fetch_matches(self, league_id: int, season: str) -> List[Match]:
        ...

class FootyStatsProvider:
    """Production provider — hits live API with user key."""
    def __init__(self, api_key: str): ...
    def fetch_matches(self, league_id: int, season: str) -> List[Match]: ...

class MockProvider:
    """Test provider — uses key=example endpoint or local fixtures."""
    EXAMPLE_ENDPOINT = "https://api.football-data-api.com/league-matches?key=example&league_id=4759"

    def __init__(self, use_live_example: bool = False): ...
    def fetch_matches(self, league_id: int, season: str) -> List[Match]: ...
```

### 5.2 Local Fixture Strategy

- Mock fixtures live in `tests/fixtures/` as static JSON files mirroring the FootyStats response shape.
- `MockProvider` loads from `tests/fixtures/{league_id}_{season}.json` when `use_live_example=False`.
- When `use_live_example=True`, it fetches from the public `key=example` endpoint and caches the response locally for offline replay.

### 5.3 Synthetic Data Generator

For stress testing and edge case coverage:

```python
class SyntheticMatchGenerator:
    """Generates synthetic match data with controllable distributions."""

    def generate(
        self,
        n_matches: int = 500,
        mean_goals: float = 2.7,
        goal_std: float = 1.4,
        xg_noise: float = 0.3,
        seed: int = 42,
    ) -> List[Match]: ...
```

---

## 6. Directory Structure

```
football-quant-engine/
├── src/
│   ├── __init__.py
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   ├── cache.py
│   │   ├── validator.py
│   │   └── pipeline.py
│   ├── features/
│   │   ├── __init__.py
│   │   ├── xg_efficiency.py
│   │   ├── rolling_form.py
│   │   ├── referee_volatility.py
│   │   └── assembler.py
│   ├── backtest/
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   ├── staking.py
│   │   ├── signal.py
│   │   ├── metrics.py
│   │   └── bet_log.py
│   └── models/
│       ├── __init__.py
│       ├── match.py
│       ├── features.py
│       ├── config.py
│       └── results.py
├── tests/
│   ├── fixtures/
│   │   └── 4759_2023.json
│   ├── test_ingestion.py
│   ├── test_features.py
│   └── test_backtest.py
├── data/
│   ├── raw/
│   ├── features/
│   ├── results/
│   └── errors/
├── pyproject.toml
└── README.md
```

---

## 7. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| `dataclass` over Pydantic for internal models | Lightweight, no serialization overhead in hot loops; Pydantic used only at ingestion boundary |
| Protocol-based `DataProvider` | Enables clean swapping between live API, example endpoint, and synthetic data |
| Walk-forward over k-fold CV | Respects temporal ordering — prevents future data leakage in time-series betting data |
| Separate staking from signal | Decouples "what to bet" from "how much to bet" — allows staking strategy iteration independently |
| JSON output for results | Simple, portable, no DB dependency for MVP; can layer Parquet/SQLite later |
