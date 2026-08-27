# FootyStats API Audit

## API Overview

| Property | Value |
|----------|-------|
| Base URL | `https://api.football-data-api.com` |
| Authentication | Query parameter `key=<API_KEY>` |
| Response format | JSON |
| Rate limit | 1800 requests/hour |
| Rate limit reset | Hourly (timestamp in `metadata.request_limit_refresh_next`) |
| Default pagination | 300 matches per page |
| Max per page | Configurable via `&max_per_page=X` (up to 500) |
| Sandbox key | `example` (provides EPL 2020/21 + Mexico Liga MX) |
| Timezone | Unix timestamps (UTC) |

## Authentication

- Method: API key as query parameter (`?key=<API_KEY>`)
- No OAuth, no bearer tokens
- Rate limit info returned in every response's `metadata` block
- Invalid key returns HTTP error (not tested with real expired keys)

## Available Endpoints

### League List
```
GET /league-list?key=<KEY>&chosen_leagues_only=true
```
Returns leagues available in the subscription with season IDs.

### League Matches (Match Schedule & Stats)
```
GET /league-matches?key=<KEY>&season_id=<SEASON_ID>&max_per_page=<N>&page=<P>
```
Returns full match schedule with stats for a season. This is the primary data endpoint.
- Pagination: `pager.current_page`, `pager.max_page`, `pager.total_results`
- Default 300 per page, max 500

### Match Details
```
GET /match?key=<KEY>&match_id=<MATCH_ID>
```
Single match with additional H2H, trends, lineups.

### League Teams
```
GET /league-teams?key=<KEY>&season_id=<SEASON_ID>&include=stats
```
Team stats for a season.

### Team
```
GET /team?key=<KEY>&team_id=<TEAM_ID>
```
Individual team data.

### League Season Stats
```
GET /league-season?key=<KEY>&season_id=<SEASON_ID>
```
League-level statistics and team array.

### League Table
```
GET /league-table?key=<KEY>&season_id=<SEASON_ID>
```
Standings/league tables.

## Pagination

| Field | Location | Meaning |
|-------|----------|---------|
| `pager.current_page` | Response root | Current page number |
| `pager.max_page` | Response root | Total pages available |
| `pager.results_per_page` | Response root | Items per page |
| `pager.total_results` | Response root | Total matches in dataset |

Request parameters: `&page=<N>` and `&max_per_page=<N>`

## Rate Limiting

| Field | Location | Meaning |
|-------|----------|---------|
| `metadata.request_limit` | Response | Max requests per hour (1800) |
| `metadata.request_remaining` | Response | Remaining requests this hour |
| `metadata.request_reset_message` | Response | Human-readable reset info |
| `metadata.request_limit_refresh_next` | Response | Unix timestamp of next reset |

## Match Record Schema (215 fields observed)

### Identity & Metadata

| API Field | Type | Nullable | Meaning | ResearchMatch Target |
|-----------|------|----------|---------|---------------------|
| `id` | int | No | Unique match ID | `match_id` |
| `date_unix` | int | No | Kickoff timestamp (UTC) | `date_unix` |
| `competition_id` | int | No | Season/competition ID | `league_id` |
| `season` | str | No | e.g. "2020/2021" | `season` |
| `homeID` | int | No | Home team ID | (team identity) |
| `awayID` | int | No | Away team ID | (team identity) |
| `home_name` | str | No | Home team display name | `home_team` |
| `away_name` | str | No | Away team display name | `away_team` |
| `status` | str | No | "complete", "incomplete", etc. | (filter criterion) |
| `game_week` | int | No | Matchday number | (metadata) |
| `roundID` | int | No | Round identifier | (metadata) |
| `refereeID` | int | Yes | Referee ID | `referee` |

### Results (POST-MATCH)

| API Field | Type | Nullable | Meaning | ResearchMatch Target |
|-----------|------|----------|---------|---------------------|
| `homeGoalCount` | int | No | Home goals FT | `home_goals` |
| `awayGoalCount` | int | No | Away goals FT | `away_goals` |
| `totalGoalCount` | int | No | Total goals | `total_goals` |
| `ht_goals_team_a` | int | Yes | Home goals HT | `ht_home_goals` |
| `ht_goals_team_b` | int | Yes | Away goals HT | `ht_away_goals` |
| `winningTeam` | int | Yes | Winner team ID | (derived) |

### Shots (POST-MATCH)

| API Field | Type | Nullable | Meaning | ResearchMatch Target |
|-----------|------|----------|---------|---------------------|
| `team_a_shots` | int | Yes | Home total shots | `shots_home` |
| `team_b_shots` | int | Yes | Away total shots | `shots_away` |
| `team_a_shotsOnTarget` | int | Yes | Home SOT | `shots_on_target_home` |
| `team_b_shotsOnTarget` | int | Yes | Away SOT | `shots_on_target_away` |
| `team_a_shotsOffTarget` | int | Yes | Home shots off | `shots_off_target_home` |
| `team_b_shotsOffTarget` | int | Yes | Away shots off | `shots_off_target_away` |

### Corners (POST-MATCH)

| API Field | Type | Nullable | Meaning | ResearchMatch Target |
|-----------|------|----------|---------|---------------------|
| `team_a_corners` | int | Yes | Home corners | `corners_home` |
| `team_b_corners` | int | Yes | Away corners | `corners_away` |
| `totalCornerCount` | int | Yes | Total corners | `total_corners` |

### Cards (POST-MATCH)

| API Field | Type | Nullable | Meaning | ResearchMatch Target |
|-----------|------|----------|---------|---------------------|
| `team_a_yellow_cards` | int | Yes | Home yellows | `yellow_cards_home` |
| `team_b_yellow_cards` | int | Yes | Away yellows | `yellow_cards_away` |
| `team_a_red_cards` | int | Yes | Home reds | `red_cards_home` |
| `team_b_red_cards` | int | Yes | Away reds | `red_cards_away` |
| `team_a_cards_num` | int | Yes | Home total cards | (derived) |
| `team_b_cards_num` | int | Yes | Away total cards | (derived) |

### Offsides (POST-MATCH)

| API Field | Type | Nullable | Meaning | ResearchMatch Target |
|-----------|------|----------|---------|---------------------|
| `team_a_offsides` | int | Yes | Home offsides | `offsides_home` |
| `team_b_offsides` | int | Yes | Away offsides | `offsides_away` |

### Fouls (POST-MATCH)

| API Field | Type | Nullable | Meaning | ResearchMatch Target |
|-----------|------|----------|---------|---------------------|
| `team_a_fouls` | int | Yes | Home fouls | `fouls_home` |
| `team_b_fouls` | int | Yes | Away fouls | `fouls_away` |

### Possession (POST-MATCH)

| API Field | Type | Nullable | Meaning | ResearchMatch Target |
|-----------|------|----------|---------|---------------------|
| `team_a_possession` | int | Yes | Home % (0-100) | `possession_home` |
| `team_b_possession` | int | Yes | Away % (0-100) | `possession_away` |

### Attacks (POST-MATCH)

| API Field | Type | Nullable | Meaning | ResearchMatch Target |
|-----------|------|----------|---------|---------------------|
| `team_a_attacks` | int | Yes | Home attacks | `attacks_home` |
| `team_b_attacks` | int | Yes | Away attacks | `attacks_away` |
| `team_a_dangerous_attacks` | int | Yes | Home dangerous attacks | `dangerous_attacks_home` |
| `team_b_dangerous_attacks` | int | Yes | Away dangerous attacks | `dangerous_attacks_away` |

### xG (POST-MATCH)

| API Field | Type | Nullable | Meaning | ResearchMatch Target |
|-----------|------|----------|---------|---------------------|
| `team_a_xg` | float | Yes | Home post-match xG | `home_xg` |
| `team_b_xg` | float | Yes | Away post-match xG | `away_xg` |
| `team_a_xg_prematch` | float | Yes | Home pre-match xG model | (pre-match feature) |
| `team_b_xg_prematch` | float | Yes | Away pre-match xG model | (pre-match feature) |

### Pre-Match Stats (available BEFORE kickoff)

| API Field | Type | Nullable | Meaning | Temporal Status |
|-----------|------|----------|---------|----------------|
| `pre_match_home_ppg` | float | Yes | Pre-match home PPG | PRE-MATCH |
| `pre_match_away_ppg` | float | Yes | Pre-match away PPG | PRE-MATCH |
| `pre_match_teamA_overall_ppg` | float | Yes | Team A overall PPG | PRE-MATCH |
| `pre_match_teamB_overall_ppg` | float | Yes | Team B overall PPG | PRE-MATCH |
| `team_a_xg_prematch` | float | Yes | Team A pre-match xG | PRE-MATCH |
| `team_b_xg_prematch` | float | Yes | Team B pre-match xG | PRE-MATCH |
| `btts_potential` | int | Yes | BTTS probability estimate | PRE-MATCH |
| `o25_potential` | int | Yes | Over 2.5 probability | PRE-MATCH |
| `corners_potential` | float | Yes | Expected corners | PRE-MATCH |

### Odds (PRE-MATCH)

| API Field | Type | Nullable | Meaning | ResearchMatch Target |
|-----------|------|----------|---------|---------------------|
| `odds_ft_1` | float | Yes | Home win | `odds_home_win` |
| `odds_ft_x` | float | Yes | Draw | `odds_draw` |
| `odds_ft_2` | float | Yes | Away win | `odds_away_win` |
| `odds_ft_over25` | float | Yes | Over 2.5 goals | `odds_over_goals` |
| `odds_ft_under25` | float | Yes | Under 2.5 goals | `odds_under_goals` |
| `odds_corners_over_95` | float | Yes | Over 9.5 corners | `odds_over_corners` |
| `odds_corners_under_95` | float | Yes | Under 9.5 corners | `odds_under_corners` |
| `odds_btts_yes` | float | Yes | BTTS yes | (BTTS market) |
| `odds_btts_no` | float | Yes | BTTS no | (BTTS market) |

**Note:** Corner and card odds are available at multiple lines (7.5, 8.5, 9.5, 10.5, 11.5).
Goal odds available at multiple lines (0.5, 1.5, 2.5, 3.5, 4.5).

### Null Behavior

- Fields with value `-1` (e.g., `freekicks_recorded: -1`, `team_a_throwins: -1`) indicate NOT RECORDED
- Fields with value `0` may be legitimate zero (0 corners, 0 cards) or indicate unavailability
- Odds with value `0` indicate market not available
- The adapter MUST treat `-1` and `0` odds as NULL, not as real values

### Historical Depth (Sandbox)

The example key provides:
- England Premier League: seasons 2018/19 through 2024/25 (7 seasons)
- Mexico Liga MX: 2019/20 only

Full subscriptions provide broader league coverage.

## Known Limitations

1. **No publication timestamp** — API does not indicate when stats were first published. We know `date_unix` is kickoff time but cannot determine exactly when post-match stats became available.
2. **Odds are pre-match snapshots** — no closing line data, no odds movement history.
3. **No card market odds** — cards betting odds not present in observed data.
4. **No offside market odds** — offside betting odds not present in observed data.
5. **`-1` sentinel values** — used for "not recorded" rather than NULL, requires special handling.
6. **Team names may change** — must use `homeID`/`awayID` for stable identity.
7. **No explicit information_available_at timestamp** — temporal causality must be inferred from match status and `date_unix`.
