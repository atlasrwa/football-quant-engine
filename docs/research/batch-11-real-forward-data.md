# Batch 11 — Real Forward Data, Odds Integration & Temporal Feature Registry

## Overview

Batch 11 connects the forward research/paper-trading layer (Batch 10) to real-world data through FootyStats, integrates the full FeatureRegistry for point-in-time computation, adds multi-league support, and implements fixture versioning.

## Architecture

```
FootyStats API (/league-matches)
    ↓
FootyStatsFixtureProvider → FutureFixture (upcoming/scheduled)
FootyStatsOddsProvider   → OddsSnapshot (pre-match odds)
    ↓
RegistryTemporalEngine (FeatureRegistry + FeatureTransformEngine)
    ↓
PreMatchSnapshot (immutable, point-in-time, provenance-tracked)
    ↓
MarketReadinessAssessor → gate
    ↓
PaperEligibility → PaperTrade
    ↓
Settlement → CLV (requires closing odds from separate source)
```

## Provider Configuration

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `FOOTYSTATS_API_KEY` | FootyStats API authentication |

No other credentials needed. Standard AWS credential chain handles Bedrock (Batch 9).

### FootyStats Fixture Provider

```python
from src.research.forward import FootyStatsFixtureProvider

provider = FootyStatsFixtureProvider(
    season_ids=[4759, 4760, 4761],  # EPL seasons to monitor
    cache_dir=Path("./cache"),
    fixture_cache_ttl=300.0,  # 5 min TTL
)
fixtures = provider.get_upcoming_fixtures()
```

The provider fetches `/league-matches` for configured seasons, filters to non-complete matches with future kickoff timestamps, and normalizes into `FutureFixture` objects.

### FootyStats Odds Provider

```python
from src.research.forward import FootyStatsOddsProvider

odds_provider = FootyStatsOddsProvider(season_ids=[4759])
odds_provider.load_odds_for_season(4759)
odds = odds_provider.get_odds_snapshot(fixture_id, market="CORNERS_TOTAL")
```

**Supported markets:** GOALS_TOTAL (line 2.5), CORNERS_TOTAL (line 9.5), MATCH_RESULT_1X2.

**Limitations:**
- Single pre-match snapshot per match (no odds movement history)
- No genuine closing odds (CLV requires separate source)
- No per-bookmaker granularity (market average only)
- Timestamp is ESTIMATED (1 hour before kickoff)

## FeatureRegistry Integration

The `RegistryTemporalEngine` bridges the existing `FeatureRegistry` + `FeatureTransformEngine` with forward predictions:

```python
from src.research.forward import RegistryTemporalEngine, create_standard_forward_features
from src.research.feature_registry import FeatureRegistry

registry = FeatureRegistry()
registry.register_many(create_standard_forward_features())  # 22 features

engine = RegistryTemporalEngine(registry=registry)
snapshot = engine.build_snapshot(
    fixture_id="...",
    home_team_id=101,
    away_team_id=202,
    prediction_timestamp=time.time(),
    kickoff_timestamp=fixture.kickoff_timestamp,
    historical_matches=historical_matches,
)
```

### Standard Forward Features (22)

- Rolling means (window 5, 10): total_goals, total_corners, total_cards, dangerous_attacks, shots_on_target, possession
- EWMA: total_goals, total_corners
- Rolling std: total_goals, total_corners

All are `TemporalClass.DERIVED` — computed from historical post-match data of PAST matches.

### Point-in-Time Methodology

1. Historical matches filtered: only `date_unix < prediction_timestamp`
2. Same-timestamp matches excluded (strict mode)
3. Matches sorted chronologically for `FeatureTransformEngine`
4. Engine computes rolling/EWMA/etc using only prior-match history (built into existing engine)
5. Latest feature values represent "what was known at prediction time"
6. Each feature gets `FeatureProvenance` with `information_timestamp`

## Multi-League Support

Five leagues supported by design:
- English Premier League (EPL)
- La Liga
- Serie A
- Bundesliga
- Ligue 1

### Market Readiness Assessment

```python
from src.research.forward import MarketReadinessAssessor

assessor = MarketReadinessAssessor(
    min_historical_sample=50,
    min_odds_coverage=0.5,
    min_feature_coverage=0.6,
)
result = assessor.assess(
    league_id=47, market="CORNERS_TOTAL",
    historical_sample=200, odds_coverage=0.8, feature_coverage=0.9,
)
# result.readiness: READY / PARTIAL / INSUFFICIENT_DATA / UNAVAILABLE
```

Paper trades are NOT generated for markets failing readiness.

## Fixture Change Handling

```python
from src.research.forward import FixtureVersionTracker

tracker = FixtureVersionTracker(kickoff_change_threshold=3600)
tracker.record(fixture)  # Initial observation
# ... fixture rescheduled ...
if tracker.record(updated_fixture):  # Returns True if meaningful change
    if tracker.should_invalidate_snapshots(fixture_id):
        # Existing snapshots are stale — need new snapshot
        pass
```

- Small kickoff changes (< threshold) are tolerated
- Significant changes trigger snapshot invalidation
- Historical versions are preserved (never deleted)

## CLV Methodology

**Status: CLV CALCULATION AVAILABLE, BUT GENUINE CLOSING ODDS NOT AVAILABLE FROM FOOTYSTATS.**

FootyStats does NOT provide genuine closing odds. CLV calculation requires a dedicated closing odds source (e.g., Pinnacle closing lines). Until such a source is integrated:
- `get_closing_odds()` returns empty list
- CLV marked as unavailable in `MarketReadinessResult`
- System never fabricates closing odds
- System never labels pre-match odds as "closing"

## Temporal Guarantees

| Guarantee | Enforcement |
|-----------|-------------|
| Features use only prior data | `_filter_eligible()` + `FeatureTransformEngine` built-in causality |
| Odds captured before prediction | `is_valid_for_prediction()` check |
| Closing odds isolated | `OddsType.CLOSING` separate from `PRE_MATCH` |
| Snapshot immutable | `frozen=True` + `MappingProxyType` |
| No future match contamination | Explicit timestamp filtering (not relying on sort order) |
| Provenance tracked | `FeatureProvenance` per feature with `information_timestamp` |

## Security

- API keys never in fixtures, odds, snapshots, events, logs
- Credential loaded from environment only
- Cache keys exclude API key
- No betting execution paths exist

## Failure Modes

| Failure | Handling |
|---------|----------|
| API timeout | Graceful failure, empty results, logged |
| API 429 | Retry with backoff (existing client logic) |
| API 401/403 | Immediate `AuthenticationError` |
| Missing team ID | Fixture rejected (returns None) |
| Invalid odds (< 1.0) | Rejected (returns None) |
| Malformed response | Record skipped |
| Provider outage | Empty results, pipeline continues without new data |

## Caching & Rate Limiting

Reuses existing `FootyStatsResearchClient` infrastructure:
- File-based JSON cache (endpoint + params, excluding API key)
- 2-second rate limit between requests
- Exponential backoff on 429
- Fixture-specific TTL (5 minutes default)

## Testing

63 tests in `test_batch11_real_forward.py`:
- Fixture provider (8 tests)
- Odds provider (6 tests)
- Registry engine (6 tests)
- Multi-league readiness (5 tests)
- Fixture versioning (5 tests)
- Deterministic identity (3 tests)
- Provider errors (3 tests)
- Temporal leakage attacks (20 mandatory)
- Security (3 tests)
- Snapshot immutability (2 tests)
- End-to-end integration (2 tests)

## Verification Status

| Aspect | Status |
|--------|--------|
| Unit tested | YES (63 tests) |
| Integration tested | YES (mocked client) |
| Real-data verified | NOT VERIFIED (no live API call in tests) |
| Closing odds | NOT AVAILABLE (FootyStats limitation) |

## Limitations

1. FootyStats provides no genuine closing odds — CLV requires separate source
2. Odds timestamps are ESTIMATED (1h before kickoff), not EXACT
3. Single odds snapshot per match (no movement history from FootyStats)
4. Market average odds only (no per-bookmaker)
5. Real-data smoke test requires live FOOTYSTATS_API_KEY (opt-in only)
6. Feature coverage depends on league data quality (varies)
