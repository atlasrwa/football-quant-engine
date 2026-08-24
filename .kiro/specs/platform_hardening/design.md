# Design: Platform Hardening & Anti-Overfitting Suite

#[[file:requirements.md]]

## Architecture Overview

```
Raw Data Sources                    Engine Core
─────────────────                  ─────────────────
FootyStats CSV ──┐                ┌─ XMetricEngine
Other Provider ──┼─► DataAdapter ─┤─ StrategyEvaluator
Synthetic Gen  ──┘   (canonical)  ├─ FrictionBacktester ──► FDR Validator
                                  └─ StrategyBuilder
```

## Module Layout

```
src/engine/
├── data/
│   ├── __init__.py
│   ├── base.py           # BaseDataLoader ABC, MatchRecord schema
│   ├── footystats.py     # FootyStatsAdapter
│   └── synthetic.py      # SyntheticDataLoader
├── friction.py           # MarketFrictionConfig, FrictionAdjustedBacktester
├── fdr.py                # FDRController, QuarantineTracker
├── builder.py            # StrategyBuilder, schema export
├── backtest.py           # (unchanged)
├── evaluator.py          # (unchanged)
├── validator.py          # (unchanged, FDR wraps externally)
└── xmetrics.py           # (unchanged)
```

## Component Design

### 1. Data Provider Abstraction (`src/engine/data/`)

#### `base.py`

```python
from abc import ABC, abstractmethod

# Canonical column schema — every loader must produce these columns
MATCH_RECORD_SCHEMA: dict[str, type] = {
    "match_id": int,
    "date_unix": int,
    "league_id": int,
    "season": str,
    "home_team": str,
    "away_team": str,
    # xC inputs
    "attacks_home": float,
    "attacks_away": float,
    "dangerous_attacks_home": float,
    "dangerous_attacks_away": float,
    "shots_off_target_home": float,
    "shots_off_target_away": float,
    "corners_avg_against_home": float,
    "corners_avg_against_away": float,
    # xB inputs
    "fouls_home": float,
    "fouls_away": float,
    "possession_home": float,
    "possession_away": float,
    "referee_cards_per_match": float,
    "xg_against_home": float,
    "xg_against_away": float,
    # xO inputs
    "offsides_home": float,
    "offsides_away": float,
    "ppda_home": float,
    "ppda_away": float,
    # Market data
    "over_odds": float,
    "under_odds": float,
    "market_line": float,
    # Outcome (for backtesting)
    "actual_total": float,
}

class BaseDataLoader(ABC):
    """Abstract base for all data providers."""

    @abstractmethod
    def load(self, **kwargs) -> pd.DataFrame:
        """Load data and return canonical MatchRecord DataFrame."""
        ...

    def validate_schema(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ensure DataFrame conforms to MatchRecord schema."""
        ...
```

#### `footystats.py`

```python
class FootyStatsAdapter(BaseDataLoader):
    """Maps FootyStats CSV/JSON to canonical MatchRecord schema."""

    COLUMN_MAP: dict[str, str] = {
        "id": "match_id",
        "date_unix": "date_unix",
        "competition_id": "league_id",
        "homeGoalCount": "home_goals",
        "awayGoalCount": "away_goals",
        # ... full mapping
    }

    def load(self, path: Path | None = None, data: pd.DataFrame | None = None) -> pd.DataFrame:
        """Load from file path or pre-loaded DataFrame."""
        ...
```

#### `synthetic.py`

```python
class SyntheticDataLoader(BaseDataLoader):
    """Generates randomized match data for stress testing."""

    def __init__(self, n: int = 1000, seed: int = 42,
                 nan_rate: float = 0.05, extreme_rate: float = 0.02):
        ...

    def load(self, **kwargs) -> pd.DataFrame:
        """Generate synthetic data with edge cases."""
        ...
```

### 2. FDR Controller & Quarantine (`src/engine/fdr.py`)

```python
@dataclass(frozen=True, slots=True)
class FDRResult:
    """Result of FDR correction for a single hypothesis."""
    original_p: float
    adjusted_threshold: float
    rank: int
    rejected: bool  # True = significant after correction

class FDRController:
    """Benjamini-Hochberg False Discovery Rate controller."""

    def __init__(self, alpha: float = 0.05):
        self.alpha = alpha

    def correct(self, p_values: List[float]) -> List[FDRResult]:
        """Apply BH procedure to a batch of p-values.

        BH: sort p-values, reject if p_i <= (i/m) * alpha
        where i = rank, m = total hypotheses.
        """
        ...

    def adjusted_threshold(self, rank: int, total: int) -> float:
        """Get BH-adjusted threshold for a specific rank."""
        return (rank / total) * self.alpha


class QuarantineStatus(Enum):
    PENDING_QUARANTINE = "PENDING_QUARANTINE"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"


@dataclass
class QuarantineEntry:
    strategy_name: str
    status: QuarantineStatus
    entry_date: datetime
    promotion_date: datetime | None = None
    paper_pnl: float = 0.0


class QuarantineTracker:
    """Tracks 90-day live quarantine for validated strategies."""

    QUARANTINE_DAYS: int = 90

    def __init__(self):
        self._entries: dict[str, QuarantineEntry] = {}

    def enter_quarantine(self, strategy_name: str, entry_date: datetime) -> QuarantineEntry:
        ...

    def check_status(self, strategy_name: str, current_date: datetime) -> QuarantineStatus:
        ...

    def promote(self, strategy_name: str, current_date: datetime) -> bool:
        """Promote if quarantine period elapsed. Returns success."""
        ...
```

### 3. Market Friction Engine (`src/engine/friction.py`)

```python
@dataclass(frozen=True, slots=True)
class MarketFrictionConfig:
    """Configurable market friction parameters."""

    # Vig margins by market type
    margin_match_odds: float = 0.030  # 3.0%
    margin_corners: float = 0.060    # 6.0%
    margin_cards: float = 0.060      # 6.0%
    margin_offsides: float = 0.060   # 6.0%

    # Slippage in basis points
    slippage_bps_tier1: int = 15     # 0.15%
    slippage_bps_tier2: int = 30     # 0.30%
    slippage_bps_tier3: int = 50     # 0.50%

    # Liquidity caps (max units per match)
    liquidity_cap_tier1: float = 10.0
    liquidity_cap_tier2: float = 5.0
    liquidity_cap_tier3: float = 2.0

    def get_margin(self, market: str) -> float:
        """Get margin for a market type."""
        ...

    def get_slippage_bps(self, league_tier: int) -> int:
        ...

    def get_liquidity_cap(self, league_tier: int) -> float:
        ...


class FrictionAdjustedBacktester:
    """Wraps XMetricBacktester with realistic market friction."""

    def __init__(self, backtester: XMetricBacktester,
                 friction: MarketFrictionConfig | None = None,
                 league_tiers: dict[int, int] | None = None):
        ...

    def run(self, df: pd.DataFrame, strategies: List[Strategy], ...) -> XBacktestResult:
        """Run backtest with friction applied to odds and stakes."""
        ...

    def _apply_vig(self, odds: float, market: str) -> float:
        """Reduce odds by market-specific vig."""
        return odds * (1.0 - self.friction.get_margin(market))

    def _apply_slippage(self, odds: float, league_tier: int) -> float:
        """Apply line drag based on league tier."""
        bps = self.friction.get_slippage_bps(league_tier)
        return odds - (bps / 10000.0) * odds

    def _cap_stake(self, stake: float, league_tier: int) -> float:
        """Enforce liquidity cap."""
        cap = self.friction.get_liquidity_cap(league_tier)
        return min(stake, cap)
```

### 4. Strategy Builder (`src/engine/builder.py`)

```python
class StrategyBuilder:
    """No-code strategy construction from simple parameters."""

    VALID_METRICS = {"xC", "xB", "xO"}
    VALID_MARKETS = {"corners_over_under", "cards_over_under", "offsides_over_under",
                     "match_odds", "asian_handicap"}
    VALID_OPERATORS = {">", "<", ">=", "<=", "==", "!="}
    VALID_DIRECTIONS = {"OVER", "UNDER", "BACK", "LAY"}

    def __init__(self):
        self._name: str = ""
        self._metric: str = ""
        self._market: str = ""
        self._conditions: List[dict] = []
        self._logic: str = "and"
        self._direction: str = "OVER"
        self._min_odds: float = 1.50

    def set_name(self, name: str) -> "StrategyBuilder":
        ...

    def set_metric(self, metric: str) -> "StrategyBuilder":
        ...

    def add_condition(self, field: str, op: str, value: float) -> "StrategyBuilder":
        ...

    def set_direction(self, direction: str) -> "StrategyBuilder":
        ...

    def build(self) -> Strategy:
        """Validate and produce a Strategy object."""
        ...

    def to_json(self) -> str:
        """Serialize to JSON string."""
        ...

    @classmethod
    def from_json(cls, json_str: str) -> "StrategyBuilder":
        """Reconstruct builder from JSON."""
        ...

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyBuilder":
        """Build from a simple flat dict (UI dropdown selections)."""
        ...
```

## Integration Points

- `FrictionAdjustedBacktester` wraps `XMetricBacktester` — no changes to the core backtester.
- `FDRController` is used alongside `StatisticalValidator` — validator is unchanged.
- `BaseDataLoader` outputs DataFrames compatible with `XMetricEngine.compute_all()`.
- `StrategyBuilder.build()` produces `Strategy` objects consumed by `StrategyEvaluator`.

## Data Flow (End-to-End)

```
1. DataLoader.load()          → canonical DataFrame
2. XMetricEngine.compute_all() → DataFrame + xC/xB/xO columns
3. StrategyBuilder.build()     → Strategy objects
4. FrictionAdjustedBacktester  → XBacktestResult (friction-adjusted)
5. StatisticalValidator        → ValidationVerdict
6. FDRController.correct()     → adjusted significance
7. QuarantineTracker           → PENDING_QUARANTINE → PROMOTED/REJECTED
```
