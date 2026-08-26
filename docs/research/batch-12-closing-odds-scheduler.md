# Batch 12 — Closing Odds, Production Scheduler & Real-Data Validation

## Overview

Batch 12 adds genuine closing odds infrastructure, a production scheduler for the forward pipeline, and health monitoring. It maintains strict separation between entry odds (prediction) and closing odds (evaluation).

**Closing odds are EVALUATION-ONLY. They must NEVER influence predictions, staking, or eligibility.**

## CLV Methodology

**PRICE-BASED CLV** (single documented convention):

```
CLV = (entry_odds / closing_odds) - 1
```

- **Positive CLV**: Entry odds better than closing → sharp signal
- **Negative CLV**: Entry odds worse than closing
- **Zero**: At closing line

Optional overround-adjusted CLV available when both sides of market are known.

## Architecture

```
ClosingOddsProvider (abstract)
    ├── DeterministicClosingOddsProvider (testing)
    └── [Future: Pinnacle/Betfair adapter]
         ↓
    ClosingOddsObservation (immutable)
         ↓
    ClosingLineValidator (10 rules)
         ↓
    CLVEngine → CLVCalculation (immutable)
         ↓
    Paper Trade evaluation (post-settlement only)
```

## Closing Odds Provider

```python
from src.research.closing import ClosingOddsProvider, DeterministicClosingOddsProvider

provider = DeterministicClosingOddsProvider()
provider.add_observation(ClosingOddsObservation(...))
closing = provider.get_closing_odds(fixture_id, market="CORNERS_TOTAL")
```

### Timestamp Semantics

| Semantics | Meaning | Usable for CLV? |
|-----------|---------|-----------------|
| EXACT_CLOSE | Provider marks as exact closing | YES (genuine) |
| LAST_BEFORE_KICKOFF | Last snapshot pre-kickoff | YES (genuine) |
| PROVIDER_ESTIMATED | Provider's estimate | NO (estimated only) |
| RETRIEVAL_TIME | When we fetched it | NO (weakest) |

### Validation Rules (10)

1. Same fixture as paper trade
2. Same market
3. Same selection  
4. closing_timestamp > entry_timestamp
5. closing_timestamp <= kickoff + tolerance
6. No post-kickoff data
7. Source provenance exists
8. Valid decimal odds (>= 1.0)
9. No impossible timestamp ordering
10. No duplicates

## Production Scheduler

```python
from src.research.scheduler import SchedulerEngine, SchedulerConfig, JobType

engine = SchedulerEngine(config=SchedulerConfig())
engine.register_handler(JobType.REFRESH_FIXTURES, refresh_fn)
engine.register_handler(JobType.SETTLE_TRADES, settle_fn)
results = engine.run_cycle()
```

### Job Types (13)

REFRESH_FIXTURES → DETECT_FIXTURE_CHANGES → BUILD_SNAPSHOTS → CAPTURE_PREMATCH_ODDS → EVALUATE_ELIGIBILITY → GENERATE_PAPER_TRADES → MONITOR_OPEN_TRADES → DETECT_COMPLETED → SETTLE_TRADES → RETRIEVE_CLOSING_ODDS → CALCULATE_CLV → GENERATE_REPORTS → AI_RESEARCH_CYCLE

### Job Dependencies (enforced)

```
REFRESH_FIXTURES
    ↓
DETECT_COMPLETED → SETTLE_TRADES → RETRIEVE_CLOSING_ODDS → CALCULATE_CLV → REPORTS
    ↓
BUILD_SNAPSHOTS → CAPTURE_ODDS → EVALUATE_ELIGIBILITY → GENERATE_TRADES
```

### Safety Controls

- Bounded jobs per cycle (configurable, default 20)
- Timeout per job (default 300s)
- Max retry attempts (default 3)
- Dependency enforcement (no out-of-order execution)
- DAG verified cycle-free
- Events emitted for every lifecycle transition

## Health Monitoring

```python
from src.research.scheduler.health import HealthMonitor

monitor = HealthMonitor()
monitor.record_fixture_refresh()
monitor.record_heartbeat()
health = monitor.check_health(open_trades=5, missing_closing_odds=2)
# health.overall_status: HEALTHY / DEGRADED / UNHEALTHY
```

Monitors: fixture freshness, odds freshness, scheduler heartbeat, provider errors, stale jobs.

## Odds Normalization

```python
from src.research.closing import OddsNormalizer

normalizer = OddsNormalizer()
normalizer.normalize_market("over_under_2.5")  # → "GOALS_TOTAL"
normalizer.normalize_selection("1")  # → "HOME"
normalizer.normalize_bookmaker("PinnacleSports")  # → "pinnacle"
```

Fixture mapping with confidence scoring: EXACT > HIGH > MEDIUM > LOW > REJECTED.

## Known Limitations

1. No real closing odds provider yet (Pinnacle/Betfair adapter not implemented)
2. CLV requires genuine closing data — FootyStats cannot provide this
3. Real-data smoke test requires closing odds API credentials
4. Performance benchmarks not run at scale in this batch

## Testing

65 tests covering: provider contract, normalization, validation, CLV math, overround, scheduler lifecycle, dependencies, safety, health, 12 temporal leakage attacks, provider failures, security, idempotency, AI boundary, integration.
