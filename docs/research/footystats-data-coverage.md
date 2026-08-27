# FootyStats Data Coverage Report

## Dataset: EPL 2020/2021 (Sandbox — season_id=4759)

| Metric | Value |
|--------|-------|
| Total Matches | 380 |
| Total Teams | 20 |
| Total Leagues | 1 |
| Total Seasons | 1 |
| Earliest Match | 2020-09-12 |
| Latest Match | 2021-05-23 |
| Data Quality Rate | 100% (380/380 valid) |
| Duplicates | 0 |
| Schema Errors | 0 |

## Field Coverage

| Field | Available | Missing | Coverage % | Usable |
|-------|-----------|---------|------------|--------|
| corners_home | 380 | 0 | 100.0% | ✓ |
| corners_away | 380 | 0 | 100.0% | ✓ |
| total_corners | 380 | 0 | 100.0% | ✓ |
| shots_home | 380 | 0 | 100.0% | ✓ |
| shots_away | 380 | 0 | 100.0% | ✓ |
| shots_on_target_home | 380 | 0 | 100.0% | ✓ |
| shots_on_target_away | 380 | 0 | 100.0% | ✓ |
| yellow_cards_home | 380 | 0 | 100.0% | ✓ |
| yellow_cards_away | 380 | 0 | 100.0% | ✓ |
| red_cards_home | 380 | 0 | 100.0% | ✓ |
| red_cards_away | 380 | 0 | 100.0% | ✓ |
| offsides_home | 365 | 15 | 96.1% | ✓ |
| offsides_away | 365 | 15 | 96.1% | ✓ |
| fouls_home | 380 | 0 | 100.0% | ✓ |
| fouls_away | 380 | 0 | 100.0% | ✓ |
| possession_home | 380 | 0 | 100.0% | ✓ |
| possession_away | 380 | 0 | 100.0% | ✓ |
| attacks_home | 380 | 0 | 100.0% | ✓ |
| attacks_away | 380 | 0 | 100.0% | ✓ |
| dangerous_attacks_home | 380 | 0 | 100.0% | ✓ |
| dangerous_attacks_away | 380 | 0 | 100.0% | ✓ |
| home_xg | 380 | 0 | 100.0% | ✓ |
| away_xg | 380 | 0 | 100.0% | ✓ |
| odds_over_goals | 380 | 0 | 100.0% | ✓ |
| odds_under_goals | 380 | 0 | 100.0% | ✓ |
| odds_over_corners | 379 | 1 | 99.7% | ✓ |
| odds_under_corners | 379 | 1 | 99.7% | ✓ |
| odds_home_win | 379 | 1 | 99.7% | ✓ |
| odds_draw | 379 | 1 | 99.7% | ✓ |
| odds_away_win | 379 | 1 | 99.7% | ✓ |

## League/Season Coverage

| League ID | Season | Matches | Teams | Corners | Cards | Shots | Possession | xG | Goals Odds | Corners Odds |
|-----------|--------|---------|-------|---------|-------|-------|------------|-----|------------|--------------|
| 4759 | 2020/2021 | 380 | 20 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

## Market Readiness

| Market | Status | Notes |
|--------|--------|-------|
| GOALS_TOTAL | **READY** | Full data + odds coverage (100%) |
| CORNERS_TOTAL | **READY** | Full data + odds coverage (99.7%) |
| CARDS_TOTAL | PARTIAL | Full data but NO card market odds from API |
| OFFSIDES_TOTAL | PARTIAL | 96% data coverage, NO offside market odds |
| BTTS | PARTIAL | Goal data available, BTTS odds available but not integrated |
| MATCH_RESULT_1X2 | **READY** | Full data + 1X2 odds (99.7%) |

## Markets with Full Research Capability

The following markets can run the complete research pipeline (discovery → walk-forward → FDR → governance) with real economic evaluation:

1. **GOALS_TOTAL** — Over/Under 2.5 goals with real bookmaker odds
2. **CORNERS_TOTAL** — Over/Under 9.5 corners with real bookmaker odds
3. **MATCH_RESULT_1X2** — Home/Draw/Away with real 1X2 odds

## Markets with Statistical-Only Research

These markets can evaluate predictive quality (calibration, hit rate, stability) but NOT genuine EV/profitability:

4. **CARDS_TOTAL** — Data excellent, but no card market odds from API
5. **OFFSIDES_TOTAL** — Good data (96%), but no offside market odds
6. **BTTS** — Can be derived from goals, limited odds integration

## Known Data Limitations

1. **Single season (sandbox)** — Full subscription would provide 7 EPL seasons + other leagues
2. **No closing odds** — Only pre-match snapshot available; cannot compute CLV
3. **No card/offside odds** — These markets can only be evaluated statistically
4. **No information_available_at** — Post-match stats publication time is estimated (kickoff + 2h)
5. **Offsides 96% coverage** — 15 matches missing offside data (early-season games)
6. **Odds represent a single snapshot** — No line movement history

## Temporal Characteristics

- Data spans 253 days (2020-09-12 to 2021-05-23)
- Matches are well-distributed across the season
- No large temporal gaps
- Sufficient for 3-5 walk-forward folds with monthly periods

## Conclusions

The EPL 2020/21 sandbox dataset provides **high-quality** research data:
- 100% valid records after normalization
- Near-complete field coverage across all major statistics
- Real bookmaker odds for goals, corners, and match result markets
- Sufficient volume (380 matches) for multi-fold walk-forward validation

The primary limitation is that this is a single season — multi-season research requires a full subscription with additional season_ids.
