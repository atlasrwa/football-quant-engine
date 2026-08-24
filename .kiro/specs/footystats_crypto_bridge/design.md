# Design: FootyStats Live API Client, Crypto-Native Signal Exporter & Beat the Bookie Metrics

#[[file:requirements.md]]

## Architecture Overview

```
FootyStats JSON API
       │
       ▼
┌──────────────────────┐
│ footystats_api.py    │ ← Rate-limited async client + disk cache
│  (TokenBucket +      │
│   DiskCache)         │
└──────────┬───────────┘
           │ raw JSON
           ▼
┌──────────────────────┐
│ FootyStatsAdapter    │ ← Existing adapter (unchanged)
└──────────┬───────────┘
           │ canonical DataFrame
           ▼
┌──────────────────────┐     ┌────────────────────┐
│ XMetricEngine        │────►│ StrategyEvaluator  │
└──────────────────────┘     └────────┬───────────┘
                                      │ Signals
                              ┌───────┴────────┐
                              ▼                ▼
                   ┌──────────────┐  ┌────────────────────┐
                   │ bookie.py    │  │ crypto_exporter.py  │
                   │ (BTBR, Edge, │  │ (Webhook + Hash)   │
                   │  Confidence) │  └────────────────────┘
                   └──────────────┘

┌─────────────────────────┐
│ src/api/routes/builder  │ ← FastAPI endpoint
│  POST /compile          │
│  GET  /result/{id}      │
└─────────────────────────┘
```

## Module Layout

```
src/
├── engine/
│   ├── data/
│   │   ├── footystats_api.py    # Live API client (NEW)
│   │   └── ...                  # existing
│   ├── metrics/
│   │   ├── __init__.py
│   │   └── bookie.py            # Beat the Bookie metrics (NEW)
│   ├── signals/
│   │   ├── __init__.py
│   │   └── crypto_exporter.py   # Webhook + hash (NEW)
│   └── ...                      # existing
├── api/
│   ├── __init__.py
│   └── routes/
│       ├── __init__.py
│       └── builder.py           # FastAPI endpoint (NEW)
```

## Component Design

### 1. `src/engine/data/footystats_api.py`

```python
class TokenBucket:
    """Async-compatible token bucket rate limiter."""
    def __init__(self, rate: float = 1.0, capacity: int = 60): ...
    async def acquire(self) -> None: ...

class FootyStatsAPIClient:
    """Live async client for FootyStats JSON API."""

    BASE_URL = "https://api.football-data-api.com"

    def __init__(self, api_key: str, cache_dir: str = "data/cache",
                 rate_limit: float = 1.0, cache_ttl_live: int = 3600,
                 cache_ttl_historical: int = 86400): ...

    async def get_todays_matches(self, league_id: int | None = None) -> List[dict]: ...
    async def get_match(self, match_id: int) -> dict: ...
    async def get_league_referees(self, league_id: int) -> List[dict]: ...

    async def _request(self, endpoint: str, params: dict) -> dict: ...
    def _cache_key(self, endpoint: str, params: dict) -> str: ...
```

### 2. `src/engine/metrics/bookie.py`

```python
@dataclass(frozen=True, slots=True)
class BookieMetrics:
    """Beat the Bookie aggregate metrics."""
    btbr_pct: float              # Beat the Bookie Rate %
    vig_adjusted_edge_pct: float # Expected ROI after vig
    confidence_index: float      # 0-100 (from FDR p-value)
    total_signals: int
    signals_beating_close: int
    raw_edge_pct: float          # Pre-vig edge

class BookieMetricsCalculator:
    """Computes Beat the Bookie metrics from bet records and signals."""

    def __init__(self, friction_config: MarketFrictionConfig | None = None): ...

    def compute(self, bet_records: List[XBetRecord],
                closing_odds: List[float] | None = None,
                fdr_p_value: float = 0.05) -> BookieMetrics: ...

    def compute_btbr(self, entry_odds: List[float], closing_odds: List[float]) -> float: ...
    def compute_vig_adjusted_edge(self, roi_pct: float, market: str) -> float: ...
    def compute_confidence_index(self, fdr_p_value: float) -> float: ...
```

### 3. `src/engine/signals/crypto_exporter.py`

```python
@dataclass(frozen=True, slots=True)
class SignalPayload:
    """Formatted signal for webhook dispatch."""
    match_info: str
    market_line: str
    direction: str
    recommended_stake: float  # Kelly fraction (capped)
    edge_pct: float
    confidence: float
    fdr_validated: bool
    proof_hash: str
    timestamp: int

class KellyCalculator:
    """Kelly criterion stake sizing."""
    MAX_FRACTION: float = 0.25  # Quarter-Kelly cap

    def compute(self, win_prob: float, odds: float) -> float: ...

class ProofOfAlpha:
    """SHA-256 hash for on-chain strategy verification."""

    @staticmethod
    def generate_hash(strategy_json: str, timestamp: int,
                      verdict_json: str) -> str: ...

class CryptoSignalExporter:
    """Dispatches formatted signals to Telegram/Discord webhooks."""

    def __init__(self, telegram_url: str | None = None,
                 discord_url: str | None = None,
                 dry_run: bool = False): ...

    async def dispatch(self, signal: Signal, match_info: dict,
                       metrics: BookieMetrics,
                       verdict: ValidationVerdict | None = None) -> SignalPayload: ...

    def format_telegram(self, payload: SignalPayload) -> str: ...
    def format_discord(self, payload: SignalPayload) -> dict: ...

    async def _send_webhook(self, url: str, data: dict | str) -> bool: ...
```

### 4. `src/api/routes/builder.py`

```python
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/builder")

class CompileRequest(BaseModel):
    name: str
    metric: str  # xC | xB | xO
    market: str
    conditions: List[ConditionSchema]
    logic: str = "and"
    direction: str
    min_odds: float = 1.50

class CompileResponse(BaseModel):
    job_id: str
    strategy_json: str
    status: str = "queued"

class BacktestResultResponse(BaseModel):
    job_id: str
    status: str  # "running" | "completed" | "failed"
    result: dict | None = None

@router.post("/compile")
async def compile_strategy(req: CompileRequest, bg: BackgroundTasks) -> CompileResponse: ...

@router.get("/result/{job_id}")
async def get_result(job_id: str) -> BacktestResultResponse: ...
```

## Key Design Decisions

1. **Rate limiter is async-native** — uses `asyncio.Event` to avoid blocking.
2. **Disk cache uses content-hash keys** — endpoint + sorted params → MD5 key.
3. **Webhook failures are non-fatal** — logged at WARNING, pipeline continues.
4. **Kelly is quarter-capped** — prevents ruin from estimation errors.
5. **Proof-of-Alpha is deterministic** — same inputs always produce same hash.
6. **FastAPI endpoint is thin** — delegates all logic to existing engine modules.
