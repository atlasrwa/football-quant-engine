# Batch 6 — FootyStats Real-Data Integration

## Overview

Batch 6 introduces real football data from the FootyStats API into the existing
research architecture. The research engine itself is unchanged — only the data
source is swapped from `SyntheticResearchDataSource` to `FootyStatsDataSource`.

## API Contract

| Property | Value |
|----------|-------|
| Base URL | `https://api.football-data-api.com` |
| Authentication | Query parameter `key=<API_KEY>` |
| Rate limit | 1800 requests/hour |
| Pagination | `page` + `max_per_page` (default 300, max 500) |
| Response format | JSON with `success`, `pager`, `metadata`, `data` fields |
| Sandbox key | `example` (provides EPL + Mexico Liga MX) |

## Authentication

- Credentials loaded from `FOOTYSTATS_API_KEY` environment variable
- Fallback to `"example"` (sandbox) if not set
- API key passed as `?key=` query parameter
- Never stored in: research objects, hashes, logs, exceptions, test fixtures

## Adapter Architecture

```
FootyStats API
    ↓
FootyStatsResearchClient (auth, rate limit, pagination, cache)
    ↓
MatchNormalizer (raw JSON → ResearchMatch, null preservation)
    ↓
RecordValidator (quality checks, deduplication, ranges)
    ↓
FootyStatsDataSource (implements ResearchDataSource)
    ↓
ResearchDataset (existing research engine — unchanged)
```

## Raw Schema

215 fields per match record. Key field groups:
- Identity: `id`, `date_unix`, `homeID`, `awayID`, `home_name`, `away_name`, `competition_id`, `season`
- Results: `homeGoalCount`, `awayGoalCount`, `totalGoalCount`
- Shots: `team_a_shots`, `team_b_shots`, `team_a_shotsOnTarget`, `team_b_shotsOnTarget`
- Corners: `team_a_corners`, `team_b_corners`, `totalCornerCount`
- Cards: `team_a_yellow_cards`, `team_b_yellow_cards`, `team_a_red_cards`, `team_b_red_cards`
- Offsides: `team_a_offsides`, `team_b_offsides`
- Possession: `team_a_possession`, `team_b_possession`
- Attacks: `team_a_attacks`, `team_b_attacks`, `team_a_dangerous_attacks`, `team_b_dangerous_attacks`
- xG: `team_a_xg`, `team_b_xg`
- Odds: `odds_ft_over25`, `odds_ft_under25`, `odds_corners_over_95`, `odds_corners_under_95`, `odds_ft_1`, `odds_ft_x`, `odds_ft_2`

## Normalized Schema

Maps to existing `ResearchMatch` dataclass without modification.
See `docs/research/footystats-api-audit.md` for complete field mapping table.

## Null Semantics

| Raw Value | Meaning | Normalized |
|-----------|---------|------------|
| `None` | Field absent | `None` |
| `-1` | "Not recorded" sentinel | `None` |
| `0` (odds) | "Market not available" | `None` |
| `0` (stats) | Legitimate zero (0 corners, 0 cards) | `0` |
| `< 1.0` (odds) | Invalid decimal odds | `None` |

**Rule: NULL ≠ ZERO. Missing data is never fabricated.**

## Temporal Semantics

| Timestamp | Meaning | Source |
|-----------|---------|--------|
| Event time | Match kickoff | `date_unix` |
| Information time | When stats became available (estimated) | `date_unix + 7200` (2 hours) |
| Retrieval time | When data was downloaded | `time.time()` at fetch |

**Limitation:** FootyStats does not provide an explicit `published_at` timestamp.
The +2 hour estimate is conservative. This is documented, not hidden.

Pre-match fields (odds, pre_match_ppg) are available before `date_unix`.
Post-match fields (shots, corners, goals) are available only after `date_unix`.

## Team Identity

- Primary identity: `homeID` / `awayID` (integer, stable across seasons)
- Display name: `home_name` / `away_name` (may change)
- Provenance tracks both `source_home_team_id` and `source_away_team_id`
- Deduplication uses `source_match_id` (not team names)

## League Identity

- Primary identity: `competition_id` (season-specific integer)
- Season string: `"2020/2021"` format
- League names come from `/league-list` endpoint
- Same league across seasons has different `competition_id` values

## Timezone Handling

- All timestamps are Unix (UTC seconds since epoch)
- No timezone conversion needed — UTC throughout
- `date_unix` is kickoff time in UTC

## Pagination

The client handles pagination automatically:

```python
matches = client.fetch_season_matches(season_id=4759)  # Fetches all pages
```

Implementation:
1. Request page 1 with `max_per_page`
2. Check `pager.current_page` vs `pager.max_page`
3. If more pages, increment and repeat
4. Stop on empty `data` array or last page reached

## Rate Limiting

- Minimum 2.0 seconds between requests (configurable)
- Exponential backoff on 429 responses
- Authentication errors (401/403) fail immediately (no retry)
- Network errors retry up to 3 times with backoff

## Caching

File-based JSON cache:
- Cache key: endpoint + parameters (excluding API key)
- Cache hit skips HTTP request entirely
- Same data fetched twice uses cache on second call
- Cache is local to the cache_dir provided at initialization
- Credentials never cached

## Dataset Versioning

`FootyStatsDataSource.compute_content_hash()` produces a deterministic SHA-256
based on `(match_id, date_unix)` pairs. This ensures:
- Same data → same hash (regardless of retrieval time)
- Data additions/corrections → different hash
- `ResearchRunIdentity` can reference exact dataset version

## Data Quality

Quality classification per record:
- `VALID` — All checks pass
- `MISSING_REQUIRED_FIELDS` — Core identity/result absent
- `INVALID_STATISTIC` — Values outside valid ranges
- `DUPLICATE` — Same `match_id` seen before
- `TIMESTAMP_ERROR` — Date out of valid range
- `SCHEMA_ERROR` — Structural issues (e.g., home==away)

EPL 2020/21 result: **100% valid** (380/380 records pass all checks).

## Coverage

See `docs/research/footystats-data-coverage.md` for full report.

Summary for EPL 2020/21 (sandbox):
- 380 matches, 20 teams, 1 season
- 100% coverage: corners, shots, cards, possession, attacks, xG, goals odds
- 96% coverage: offsides
- 99.7% coverage: corners odds, 1X2 odds

## Market Readiness

| Market | Status | Reason |
|--------|--------|--------|
| GOALS_TOTAL | READY | Full data + bookmaker odds |
| CORNERS_TOTAL | READY | Full data + bookmaker odds |
| MATCH_RESULT_1X2 | READY | Full data + bookmaker odds |
| CARDS_TOTAL | PARTIAL | Data excellent, no card market odds |
| OFFSIDES_TOTAL | PARTIAL | 96% data, no offside market odds |
| BTTS | PARTIAL | Derivable from goals, limited odds integration |

## Real-Data Smoke Test

Successfully executed on EPL 2020/21:
1. Loaded 380 matches from API (sandbox)
2. 100% normalization success
3. Created ResearchDataset for CORNERS_TOTAL market
4. Generated candidate (dangerous_attacks_home > 30 → OVER corners)
5. Ran walk-forward validation (4 folds, 328 predictions)
6. Produced statistical evidence (combined p-value: 0.29)
7. Applied FDR correction
8. Governance classification executed

**No profitability claims made. This is exploratory evidence only.**

## Known Limitations

1. **Single season in sandbox** — Full subscription provides 7 EPL seasons + 50+ leagues
2. **No closing odds** — Only pre-match snapshot; CLV cannot be computed
3. **No card/offside betting odds** — These markets limited to statistical evaluation
4. **No information_available_at** — Post-match stats publication time estimated
5. **No line movement** — Cannot analyze odds changes over time
6. **Pre-match features are post-match stats from prior matches** — Causality ensured by temporal ordering, not by an explicit pre-match flag
7. **Single data source** — No cross-validation with other providers
8. **Odds represent market average** — Not from a specific bookmaker

## Performance

| Operation | Time | Scale |
|-----------|------|-------|
| Data loading (cached) | 0.05s | 380 matches |
| Coverage computation | 0.003s | 380 matches |
| Dataset creation | 0.05s | 380 matches |
| Walk-forward (1 hyp, 4 folds) | 0.02s | 328 predictions |
| FDR correction | <0.001s | 1 hypothesis |
| **Full pipeline** | **<0.15s** | — |

Bottleneck: data loading and dataset creation (I/O), not computation.
API fetch (uncached): ~5 minutes for 380 matches at 2s rate limit.

## Security

- API key from environment variable only
- Never in: logs, hashes, cache keys, provenance, exceptions
- Cache files contain response data only (no credentials)
- Test fixtures use sandbox key `"example"` (public, documented)
