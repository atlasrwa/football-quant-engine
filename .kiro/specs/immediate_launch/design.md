# Design: Frontend Strategy Builder UI, Community Signal Pipeline & Execution Deep-Linker

#[[file:requirements.md]]

## Architecture

```
┌─────────────────────────────────┐
│ GET /api/v1/builder/templates   │ ← 10 benchmark strategies
└─────────────────┬───────────────┘
                  │
         ┌────────┴─────────┐
         ▼                  ▼
  StrategyBuilder      StrategyEvaluator
         │                  │
         └────────┬─────────┘
                  ▼
┌──────────────────────────────────────────┐
│ CommunityBroadcaster                     │
│  - polls QuarantineTracker (promoted)    │
│  - fetches fixtures (FootyStatsAPI)      │
│  - evaluates conditions                  │
│  - dispatches to Telegram/Discord        │
│  - attaches deep-links                   │
└──────────────────┬───────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────┐
│ DeepLinker                               │
│  - Stake / Rollbit / Polymarket URLs     │
│  - Telegram inline keyboard buttons      │
│  - Affiliate tag injection               │
└──────────────────────────────────────────┘
```

## Module Layout

```
src/
├── api/routes/
│   ├── builder.py          # existing
│   └── builder_ui.py       # templates endpoint (NEW)
├── engine/signals/
│   ├── crypto_exporter.py  # existing
│   ├── community_broadcaster.py  # (NEW)
│   └── deeplinker.py       # (NEW)
data/
└── strategies/benchmarks/
    ├── xc_premier_corners_over.json
    ├── xc_laliga_corners_pressure.json
    ├── xc_bundesliga_wing_attack.json
    ├── xc_seriea_deep_penetration.json
    ├── xb_epl_card_intensity.json
    ├── xb_laliga_referee_friction.json
    ├── xb_ligue1_foul_pressure.json
    ├── xo_epl_high_line_trap.json
    ├── xo_bundesliga_counter_offside.json
    └── xo_seriea_direct_attack.json
```

## Component Design

### 1. `src/api/routes/builder_ui.py`

```python
BENCHMARK_STRATEGIES: List[dict] = [...]  # 10 strategies

def get_templates() -> List[dict]:
    """Return all benchmark strategy templates."""

def get_template_by_metric(metric: str) -> List[dict]:
    """Filter templates by metric type."""
```

### 2. `src/engine/signals/community_broadcaster.py`

```python
@dataclass
class BroadcastConfig:
    poll_interval_seconds: int = 300  # 5 minutes
    quiet_hours: tuple[int, int] = (1, 6)  # 1am-6am UTC
    telegram_url: str | None = None
    discord_url: str | None = None
    dry_run: bool = False

class CommunityBroadcaster:
    def __init__(self, config: BroadcastConfig, ...): ...

    async def run_once(self, current_signals: List[Signal], match_data: List[dict]) -> List[SignalPayload]:
        """Process and broadcast signals for current fixtures."""

    def format_broadcast_telegram(self, payload: SignalPayload, deep_links: dict) -> str:
        """Format with inline deep-link buttons."""

    def format_broadcast_discord(self, payload: SignalPayload, deep_links: dict) -> dict:
        """Format rich embed with action links."""

    def is_quiet_hours(self, hour_utc: int) -> bool:
        """Check if current time is in quiet hours."""
```

### 3. `src/engine/signals/deeplinker.py`

```python
@dataclass(frozen=True, slots=True)
class DeepLink:
    platform: str       # "stake" | "rollbit" | "polymarket"
    url: str
    label: str
    affiliate_tag: str | None = None

@dataclass(frozen=True, slots=True)
class DeepLinkConfig:
    stake_base_url: str = "https://stake.com/sports/football"
    rollbit_base_url: str = "https://rollbit.com/sports/soccer"
    polymarket_base_url: str = "https://polymarket.com/event"
    affiliate_stake: str | None = None
    affiliate_rollbit: str | None = None

class DeepLinker:
    def __init__(self, config: DeepLinkConfig | None = None): ...

    def generate_links(self, signal: Signal, match_info: dict) -> List[DeepLink]: ...
    def generate_stake_url(self, match_info: dict, market: str) -> str: ...
    def generate_rollbit_url(self, match_info: dict, market: str) -> str: ...
    def generate_polymarket_url(self, match_info: dict, market: str) -> str: ...
    def generate_telegram_buttons(self, links: List[DeepLink], proof_hash: str) -> List[dict]: ...
```

### 4. Benchmark Strategies

Each JSON file follows the existing strategy schema:
```json
{
  "name": "EPL Corner Pressure Over",
  "metric": "xC",
  "market": "corners_over_under",
  "conditions": [
    {"field": "home_xC", "op": ">", "value": 2.8},
    {"field": "away_xC", "op": ">", "value": 2.2}
  ],
  "logic": "and",
  "direction": "OVER",
  "min_odds": 1.75,
  "description": "...",
  "target_leagues": [1625]
}
```
