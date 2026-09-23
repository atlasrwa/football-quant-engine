# V1.1 Half Markets Handoff (future work only)

Status: **not started.** This note registers future work. It contains no code, ingests no data and changes nothing in V1.

## Why this exists

V1 (`TARGET_AWARE_MARKET_PANEL_V1`) is frozen and provider-bound to TheStatsAPI, with families GOALS, CORNERS, TEAM_TOTALS and BOOKINGS (`V1_SCOPE_FREEZE_V1.json`).

`HALF_TIME_V1_STATUS=OUT_OF_SCOPE_FOR_THIS_PROVIDER-BOUND_V1`

This is **not** a finding that half-time markets are unsupported.

- **TheStatsAPI (V1):** half-level labels exist for first/second-half corners, yellow cards and offsides (halves sum to the full match). Bulk fixture lists carry no half-time score, so half-time goals cannot be settled from TheStatsAPI bulk data. V1 does not include any half-level target because its frozen target/line apparatus was not built for them.
- **FootyStats (external to V1):** a field-presence/coverage count over the local `data/discovery/corpus/league-matches_*` cache (19,526 completed matches, 98 competitions; no V1 cohort outcome read) indicates substantial half-level history: `ht_goals_team_a/b`, `HTGoalCount`, `goals_2hg_team_a/b`, `team_a/b_fh_corners`, `team_a/b_2h_corners`, `team_a/b_fh_cards`, `team_a/b_2h_cards`, and `odds_1st_half_*` / `odds_2nd_half_*` fields. This is a coverage indication only, not a validated capability.

## Must be registered separately

`TARGET_AWARE_MARKET_PANEL_V1_1_HALF_MARKETS`, only **after** all V1 Sol raw responses are frozen (`SOL_RESPONSE_MANIFEST_V1.json`). V1.1 must not modify V1 artifacts or reuse V1 hypotheses as if generated under V1.1.

## V1.1 must independently audit

1. **FootyStats half-time goal fields:** semantics of `ht_goals_team_a/b`, `HTGoalCount`, `goals_2hg_*`; consistency with full-time goals (HT + 2H = FT); sentinel/NULL values (NULL != 0).
2. **First-half / second-half corners:** `*_fh_corners`, `*_2h_corners`; coverage (~0.96 indicated) and FH + 2H = full-match consistency.
3. **First-half / second-half cards:** whether `*_cards` counts cards or booking points, and how yellows/reds/second yellows are counted. Fail closed until the exact semantics are known.
4. **Canonical provider identity:** which provider is the label authority per market; FootyStats ↔ TheStatsAPI fixture/team identity mapping and conflict policy.
5. **Settlement semantics:** exact settlement rule per half market, matched to what bookmaker half markets settle.
6. **Target lines:** a half-market line policy derived from provider-observed lines and frozen before any outcome comparison.
7. **Odds availability:** whether FootyStats `odds_*` fields are timestamped pre-match prices or post-hoc/last-seen values; no closing-line claim without capture-time evidence.
8. **PIT packet construction:** half-level behavioural history strictly before each kickoff, half-family context selectors, baseline semantic coverage for half markets, and a fresh cohort and fresh Sol requests.
