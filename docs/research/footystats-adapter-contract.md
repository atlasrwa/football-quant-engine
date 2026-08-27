# FootyStats Adapter Contract

## Purpose

This document specifies exactly how a future FootyStats API adapter will
populate the `ResearchDataSource` interface. When this phase is complete,
connecting FootyStats should be a **DATA SOURCE problem**, not a
**RESEARCH ENGINE problem**.

The Research Laboratory is data-source-agnostic. It consumes
`ResearchDataSource`. The FootyStats adapter is one possible implementation.

```
FootyStatsAdapter
        |
        v
ResearchDataSource (interface)
        |
        v
Research Laboratory (unchanged)
```

---

## Interface to Implement

The adapter must implement `src/research/data_source.ResearchDataSource`:

```python
class FootyStatsAdapter(ResearchDataSource):
    def get_matches(
        self,
        league_id: Optional[int] = None,
        season: Optional[str] = None,
        min_date: Optional[int] = None,
        max_date: Optional[int] = None,
    ) -> list[ResearchMatch]: ...

    def get_available_fields(self) -> list[str]: ...

    def get_market_odds(
        self,
        match_ids: Optional[list[int]] = None,
        market: Optional[str] = None,
    ) -> list[MarketOdds]: ...
```

---

## Field Mapping: FootyStats API -> ResearchMatch

The adapter is responsible for mapping FootyStats JSON response fields
to the normalized `ResearchMatch` dataclass fields.

### Identity Fields

| ResearchMatch Field | FootyStats API Field | Notes |
|---------------------|---------------------|-------|
| `match_id` | `id` | FootyStats match ID (integer) |
| `date_unix` | `date_unix` | Unix timestamp of kickoff |
| `league_id` | `competition_id` | FootyStats competition ID |
| `season` | `season` | e.g. "2023/2024" |
| `home_team` | `homeTeam` or `home_name` | Normalized team name |
| `away_team` | `awayTeam` or `away_name` | Normalized team name |

### Result Fields (POST-MATCH)

| ResearchMatch Field | FootyStats API Field | Notes |
|---------------------|---------------------|-------|
| `home_goals` | `homeGoalCount` | Final score |
| `away_goals` | `awayGoalCount` | Final score |
| `total_goals` | Computed: `homeGoalCount + awayGoalCount` | |
| `ht_home_goals` | `ht_home_goals` or `team_a_ht_goals` | Half-time |
| `ht_away_goals` | `ht_away_goals` or `team_b_ht_goals` | Half-time |

### Statistical Fields (POST-MATCH)

| ResearchMatch Field | FootyStats API Field | Notes |
|---------------------|---------------------|-------|
| `shots_home` | `team_a_shots` | Total shots |
| `shots_away` | `team_b_shots` | Total shots |
| `shots_on_target_home` | `team_a_shotsOnTarget` | |
| `shots_on_target_away` | `team_b_shotsOnTarget` | |
| `shots_off_target_home` | `team_a_shotsOffTarget` | Or computed |
| `shots_off_target_away` | `team_b_shotsOffTarget` | Or computed |
| `corners_home` | `team_a_corners` | |
| `corners_away` | `team_b_corners` | |
| `total_corners` | Computed: `team_a_corners + team_b_corners` | |
| `yellow_cards_home` | `team_a_yellow_cards` | |
| `yellow_cards_away` | `team_b_yellow_cards` | |
| `red_cards_home` | `team_a_red_cards` | |
| `red_cards_away` | `team_b_red_cards` | |
| `total_cards` | Computed: sum of all cards | |
| `offsides_home` | `team_a_offsides` | |
| `offsides_away` | `team_b_offsides` | |
| `total_offsides` | Computed: `team_a_offsides + team_b_offsides` | |
| `fouls_home` | `team_a_fouls_committed` | |
| `fouls_away` | `team_b_fouls_committed` | |
| `attacks_home` | `team_a_attacks` | |
| `attacks_away` | `team_b_attacks` | |
| `dangerous_attacks_home` | `team_a_dangerous_attacks` | |
| `dangerous_attacks_away` | `team_b_dangerous_attacks` | |
| `possession_home` | `team_a_possession` | Percentage (0-100) |
| `possession_away` | `team_b_possession` | Percentage (0-100) |
| `home_xg` | `team_a_xg` | Expected goals |
| `away_xg` | `team_b_xg` | Expected goals |
| `ppda_home` | `team_a_ppda` | Passes per defensive action |
| `ppda_away` | `team_b_ppda` | Passes per defensive action |

### Odds Fields (PRE-MATCH)

| ResearchMatch Field | FootyStats API Field | Notes |
|---------------------|---------------------|-------|
| `odds_over_goals` | `odds_ft_over25` | Over 2.5 goals decimal odds |
| `odds_under_goals` | `odds_ft_under25` | Under 2.5 goals decimal odds |
| `line_goals` | Fixed: `2.5` | Standard goals line |
| `odds_over_corners` | `odds_corners_over` | Over 9.5 corners |
| `odds_under_corners` | `odds_corners_under` | Under 9.5 corners |
| `line_corners` | Fixed: `9.5` | Standard corners line |
| `odds_over_cards` | `odds_cards_over` | Over 3.5 cards |
| `odds_under_cards` | `odds_cards_under` | Under 3.5 cards |
| `line_cards` | Fixed: `3.5` | Standard cards line |
| `odds_over_offsides` | Custom: may not be available | |
| `odds_under_offsides` | Custom: may not be available | |
| `line_offsides` | Fixed: `4.5` | Standard offsides line |
| `odds_home_win` | `odds_ft_1` | 1X2 home win |
| `odds_draw` | `odds_ft_x` | 1X2 draw |
| `odds_away_win` | `odds_ft_2` | 1X2 away win |

### Referee Field

| ResearchMatch Field | FootyStats API Field | Notes |
|---------------------|---------------------|-------|
| `referee` | `referee_id` or `referee_name` | Standardized name |

---

## MarketOdds Mapping

For each match, the adapter should emit `MarketOdds` records:

```python
MarketOdds(
    match_id=match.id,
    market="GOALS_TOTAL",       # or CORNERS_TOTAL, CARDS_TOTAL, OFFSIDES_TOTAL
    line=2.5,                   # market-specific line
    over_odds=match.odds_ft_over25,
    under_odds=match.odds_ft_under25,
    timestamp=match.date_unix - 3600,  # pre-match snapshot
)
```

The `timestamp` on MarketOdds MUST be before the match kickoff (`date_unix`).
This enforces temporal causality: odds are pre-match information.

---

## Implementation Requirements

### 1. Authentication

```python
class FootyStatsAdapter(ResearchDataSource):
    def __init__(self, api_key: str, base_url: str = "https://api.football-data-api.com"):
        self._api_key = api_key
        self._base_url = base_url
        self._client = httpx.Client(...)
```

The adapter must handle:
- API key authentication (query parameter or header)
- Rate limiting (respect FootyStats rate limits)
- Retry logic with exponential backoff
- Response caching (avoid redundant API calls)

### 2. Data Fetching Strategy

```
get_matches() flow:
    1. Check local cache (SQLite or file-based)
    2. If cache miss → call FootyStats API
    3. Transform response → ResearchMatch
    4. Store in cache
    5. Return filtered results
```

Endpoints to use:
- `GET /league-matches` — match results for a league/season
- `GET /match` — single match detail with full stats
- `GET /league-season` — league metadata

### 3. Field Availability

Not all FootyStats responses include all fields. The adapter must:
- Return `None` for unavailable fields (ResearchMatch handles this)
- Implement `get_available_fields()` based on what the API actually returns
- Log warnings for expected but missing fields

### 4. Temporal Guarantees

The adapter MUST ensure:
- `date_unix` is the actual kickoff timestamp
- Odds timestamps are BEFORE kickoff
- Post-match stats are only from completed matches (`status == "complete"`)
- No future data leaks into historical queries

### 5. Content Hash

The `compute_content_hash()` method inherited from `ResearchDataSource`
provides a dataset fingerprint. The adapter should:
- Include API response metadata in the hash
- Allow the research engine to detect when data has changed

---

## Leagues to Support (Initial)

| League | FootyStats ID | Priority |
|--------|--------------|----------|
| English Premier League | TBD | HIGH |
| English Championship | TBD | HIGH |
| La Liga | TBD | MEDIUM |
| Bundesliga | TBD | MEDIUM |
| Serie A | TBD | MEDIUM |
| Ligue 1 | TBD | LOW |

---

## Error Handling

The adapter must handle:
- API key invalid/expired → raise `AuthenticationError`
- Rate limit exceeded → retry with backoff
- Match data incomplete → populate available fields, leave rest as None
- Network errors → retry with exponential backoff
- API schema changes → graceful degradation with warnings

---

## Testing Strategy

When implementing the adapter:

1. **Unit tests** with mocked API responses (no real API calls in CI)
2. **Integration tests** with real API key (manual, not in CI)
3. **Validation tests**: compare adapter output against known match results
4. **Temporal causality tests**: verify no post-kickoff data appears in pre-match fields

---

## Migration Path

```
Phase 0 (current):
    SyntheticResearchDataSource → Research Laboratory ✓

Phase 1 (next):
    FootyStatsAdapter → Research Laboratory
    SyntheticResearchDataSource → Research Laboratory (still used for testing)

Phase 2 (future):
    FootyStatsAdapter ─┐
    CSVDataSource     ─┼─→ Research Laboratory
    DatabaseSource    ─┘
```

The research engine code requires ZERO changes when switching from
SyntheticResearchDataSource to FootyStatsAdapter. Only the data source
instantiation changes.

---

## DO NOT Implement in Phase 0

- No API key purchase
- No real API calls
- No FootyStats account setup
- No production credentials

This document serves as the complete specification for future implementation.
When Phase 0 is complete, a developer can implement `FootyStatsAdapter`
by following this contract without needing to understand the research engine internals.
