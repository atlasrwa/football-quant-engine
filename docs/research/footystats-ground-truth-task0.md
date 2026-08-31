# FootyStats Ground Truth — Task 0

Verified against the **real production API key** (not `key=example`), across three
completed 2025/2026 seasons: England Premier League (season_id=15050, 380 matches),
Spain La Liga (season_id=14956, 380 matches), Italy Serie A (season_id=15068, 380
matches). 1,140 real match records inspected. Odds fields intentionally not
re-verified — out of scope per Task 0 instructions.

Raw JSON evidence (unmodified API responses) saved alongside this report:
- `raw_matches_sample.json` — 9 full match records, 3 per league (League-Matches)
- `raw_team_sample.json` — full `/team` response for one team per league (large: 1,045
  stats keys per team/competition row)
- `league_referees_EPL.json` — full `/league-referees` response (undocumented endpoint)
- `referee_461.json` — full `/referee?referee_id=461` response (undocumented endpoint)
- `league_list.json` — full `/league-list` response (confirms real subscription: 49
  leagues, current 2025/2026 + 2026/2027 season IDs)

## Question 1 — Attacks / dangerous attacks: raw per-match or season-avg only?

**RAW per-match, confirmed.** `team_a_attacks`, `team_b_attacks`,
`team_a_dangerous_attacks`, `team_b_dangerous_attacks` are present on every
League-Matches record (100% coverage, 1140/1140) and genuinely fluctuate match to
match for the same team — proof it's not a repeated season-to-date average pasted
onto every row. Arsenal's `attacks` across 8 consecutive 2025/26 matches:
`81, 114, 84, 96, 106, 98, 109, 79`. A season average would drift slowly and
monotonically; this doesn't.

The separate `/team` endpoint's `stats` block (1,045 keys) *does* only carry
season aggregates — `attacks_avg_home`, `attacks_avg_overall`,
`dangerous_attacks_avg_overall`, etc. But that endpoint is irrelevant to us: the
per-match raw counts we need are already sitting in League-Matches, so we can build
our own look-ahead-free expanding/rolling window from that (same pattern as
`rolling_form.py` / `xg_efficiency.py`) without ever touching the pre-averaged
`/team` numbers.

## Question 2 — PPDA: present or absent?

**Confirmed truly absent** from the raw payload, not just undocumented. Searched
(case-insensitive, regex `ppda|press|high_line|highline|line_height|pressing|
intensity`) across:
- All 215 unique top-level keys observed across all 1,140 match records → 0 hits
- The full 1,045-key `/team` stats block → 0 hits
- `/league-referees` and `/referee` payloads (85 keys) → 0 hits

No PPDA, pressing, or high-line field exists anywhere in this API surface. xB
(`src/engine/xmetrics.py`) must keep using its PPDA proxy (`1/ppda` derived from a
proxy, not FootyStats) — this is not something a schema rewrite can recover; it's a
genuine data-source gap.

## Question 3 — Everything else: inventory

215 unique top-level fields observed on League-Matches records (union across EPL +
La Liga + Serie A, so this is leagues-agnostic, not an EPL quirk). See the table
below for the analytically-relevant subset. Full raw key list available in the
"Everything else" appendix at the bottom of this file if you want the complete
215-field dump instead of the curated table.

## Question 4 — Referee data depth

**Season/competition-aggregate only. No per-match list.** Two referee-specific
endpoints exist (`/league-referees?season_id=X` and `/referee?referee_id=X`,
**both undocumented** in `docs/research/footystats-api-audit.md`), and both return
exactly the same shape: one row per (referee, competition, season) with fields like
`appearances_overall`, `cards_overall`, `cards_per_match_overall`,
`goals_per_match_overall`, `over25_cards_percentage_overall`, etc. Neither endpoint
lists individual matches or per-match card counts for that referee.

This means: **we cannot build our own expanding-window referee volatility calc from
the referee endpoints** — but we don't need to. The building blocks are already in
League-Matches: every match record carries `refereeID` (96.1% coverage, 1095/1140 —
missing on 45 matches, `None` not `-1`) plus that match's own card counts
(`team_a_yellow_cards`, `team_a_red_cards`, etc., both 100% coverage). That's exactly
what `src/features/referee_volatility.py` already does — join `refereeID` across
chronologically-sorted League-Matches rows and compute the expanding stat ourselves.
The referee endpoints are confirmed unnecessary for this and add nothing beyond what
we already derive.

## Question 5 — Undocumented fields

`docs/research/footystats-api-audit.md` documents roughly 55 of the 215 fields
actually present. Notable undocumented-but-present fields, grouped by relevance:

**Two entire undocumented endpoints:**
- `GET /league-referees?season_id=X` — season-aggregate referee stats (23 referees
  returned for EPL 2025/26)
- `GET /referee?referee_id=X` — same shape, one row per competition the referee
  worked (e.g. Anthony Taylor: Premier League row + FA Cup row, both same season)

**Undocumented per-match raw counters (100% coverage, same reliability as documented
fields):**
- `team_a_freekicks` / `team_b_freekicks`
- `team_a_throwins` / `team_b_throwins`
- `team_a_goalkicks` / `team_b_goalkicks`
- `team_a_penalties_won` / `team_a_penalty_goals` / `team_a_penalty_missed`
  (+ team_b equivalents)
- `coach_a_ID` / `coach_b_ID` — manager identity (75.4% coverage, 860/1140; useful
  for a manager-change feature, not currently modeled anywhere)
- `team_a_2h_cards` / `team_a_fh_cards` / `team_a_2h_corners` / `team_a_fh_corners`
  and `total_2h_cards` / `total_fh_cards` — half-split breakdowns
- `team_a_0_10_min_goals`, `team_a_cards_0_10_min`, `team_a_corners_0_10_min` —
  early-minute-window breakdowns
- `attendance` (99.1% coverage), `stadium_name`, `stadium_location`

**`_recorded` sentinel flags (undocumented, gate the fields above):**
`attacks_recorded`, `freekicks_recorded`, `throwins_recorded`, `goalkicks_recorded`,
`pens_recorded`, `card_timings_recorded`, `corner_timings_recorded`,
`goal_timings_recorded`. All were `1` (or `2` for `corner_timings_recorded`) on
nearly every match in this sample, with a handful of `-1` (14/380 for
`card_timings_recorded`, 7/380 for `corner_timings_recorded` in EPL) — the doc's
existing "-1 = not recorded" convention holds for these too, just wasn't documented
for this specific set of flags.

**Large undocumented odds surface** (out of scope per Task 0, noted for completeness
only): 1st-half/2nd-half markets, draw-no-bet, double chance, clean-sheet odds,
win-to-nil odds, team-to-score-first odds, and extra corners/goals lines beyond what
the doc lists. Confirms the doc's "multiple lines" note undersold the actual breadth.

---

## Summary Table

| Field | Raw per-match or season-avg-only | Status |
|---|---|---|
| `team_a_attacks` / `team_b_attacks` | Raw per-match (100% cov, verified fluctuating) | Confirmed present |
| `team_a_dangerous_attacks` / `team_b_dangerous_attacks` | Raw per-match (100% cov, verified fluctuating) | Confirmed present |
| `/team` endpoint attacks (`attacks_avg_*`) | Season-avg only | Confirmed present, not needed |
| PPDA / pressing / high-line (any field) | — | **Confirmed absent** (searched full raw payload + docs) |
| `team_a_corners` / `team_b_corners` / `totalCornerCount` | Raw per-match (100% cov) | Confirmed present |
| `team_a_yellow_cards` / `team_a_red_cards` (+ team_b) | Raw per-match (100% cov) | Confirmed present |
| `team_a_offsides` / `team_b_offsides` | Raw per-match (94.7% cov, `-1`=not recorded) | Confirmed present |
| `team_a_shots` / `_shotsOnTarget` / `_shotsOffTarget` (+ team_b) | Raw per-match (100% cov) | Confirmed present |
| `team_a_fouls` / `team_b_fouls` | Raw per-match (100% cov) | Confirmed present |
| `team_a_possession` / `team_b_possession` | Raw per-match (100% cov) | Confirmed present |
| `team_a_xg` / `team_b_xg` (post-match) | Raw per-match (100% cov) | Confirmed present |
| `team_a_xg_prematch` / `team_b_xg_prematch` | Raw per-match, pre-kickoff (100% cov) | Confirmed present |
| `refereeID` | Raw per-match identity, no per-match ref stats (96.1% cov) | Confirmed present |
| `/league-referees`, `/referee` (referee history) | Season/competition-aggregate only, no per-match list | Confirmed present, **undocumented endpoint** |
| `team_a_freekicks` / `team_a_throwins` / `team_a_goalkicks` (+ team_b) | Raw per-match (100% cov) | **Undocumented-but-present** |
| `team_a_penalties_won` / `_penalty_goals` / `_penalty_missed` (+ team_b) | Raw per-match (100% cov) | **Undocumented-but-present** |
| `coach_a_ID` / `coach_b_ID` | Raw per-match identity (75.4% cov) | **Undocumented-but-present** |
| `team_a_2h_cards` / `_fh_cards` / `_2h_corners` / `_fh_corners` (+ totals) | Raw per-match, half-split (100% cov) | **Undocumented-but-present** |
| `team_a_0_10_min_goals` / `_cards_0_10_min` / `_corners_0_10_min` | Raw per-match, minute-window (100% cov) | **Undocumented-but-present** |
| `attendance` / `stadium_name` / `stadium_location` | Raw per-match (99.1% cov attendance) | **Undocumented-but-present** |
| `*_recorded` sentinel flags (8 fields) | Raw per-match boolean gate | **Undocumented-but-present** |
| Extended odds surface (1H/2H, DNB, double chance, clean sheet, win-to-nil, extra lines) | Pre-match, per-match | **Undocumented-but-present** (out of scope, noted only) |

## Everything else — full 215-field raw key list

<details>
<summary>Click to expand full field list (union across 1,140 real matches, 3 leagues)</summary>

GoalCount_2hg, HTGoalCount, attacks_recorded, attendance, avg_potential,
awayGoalCount, awayGoals, awayGoals_timings, awayID, away_image, away_name,
away_ppg, away_url, btts, btts_2hg_potential, btts_fhg_potential, btts_potential,
card_timings_recorded, cards_potential, coach_a_ID, coach_b_ID, competition_id,
corner_2h_count, corner_fh_count, corner_timings_recorded, corners_o105_potential,
corners_o85_potential, corners_o95_potential, corners_potential, date_unix,
freekicks_recorded, game_week, goalTimingDisabled, goal_timings_recorded,
goalkicks_recorded, goals_2hg_team_a, goals_2hg_team_b, homeGoalCount, homeGoals,
homeGoals_timings, homeID, home_image, home_name, home_ppg, home_url,
ht_goals_team_a, ht_goals_team_b, id, match_url, matches_completed_minimum,
no_home_away, o05HT_potential, o05_2H_potential, o05_potential, o15HT_potential,
o15_2H_potential, o15_potential, o25_potential, o35_potential, o45_potential,
odds_1st_half_over05/15/25/35, odds_1st_half_result_1/x/2,
odds_1st_half_under05/15/25/35, odds_2nd_half_over05/15/25/35,
odds_2nd_half_result_1/x/2, odds_2nd_half_under05/15/25/35,
odds_btts_1st_half_no/yes, odds_btts_2nd_half_no/yes, odds_btts_no/yes,
odds_corners_1/x/2, odds_corners_over_75/85/95/105/115,
odds_corners_under_75/85/95/105/115, odds_dnb_1/2, odds_doublechance_12/1x/x2,
odds_ft_1/x/2, odds_ft_over05/15/25/35/45, odds_ft_under05/15/25/35/45,
odds_team_a_cs_no/yes, odds_team_b_cs_no/yes, odds_team_to_score_first_1/x/2,
odds_win_to_nil_1/2, offsides_potential, over05/15/25/35/45/55, overallGoalCount,
pens_recorded, pre_match_away_ppg, pre_match_home_ppg,
pre_match_teamA_overall_ppg, pre_match_teamB_overall_ppg, refereeID,
revised_game_week, roundID, season, stadium_location, stadium_name, status,
team_a_0_10_min_goals, team_a_2h_cards, team_a_2h_corners, team_a_attacks,
team_a_cards_0_10_min, team_a_cards_num, team_a_corners,
team_a_corners_0_10_min, team_a_dangerous_attacks, team_a_fh_cards,
team_a_fh_corners, team_a_fouls, team_a_freekicks, team_a_goalkicks,
team_a_offsides, team_a_penalties_won, team_a_penalty_goals,
team_a_penalty_missed, team_a_possession, team_a_red_cards, team_a_shots,
team_a_shotsOffTarget, team_a_shotsOnTarget, team_a_throwins, team_a_xg,
team_a_xg_prematch, team_a_yellow_cards, team_b_* (same set as team_a_*),
throwins_recorded, totalCornerCount, totalGoalCount, total_2h_cards,
total_fh_cards, total_xg, total_xg_prematch, u05/15/25/35/45_potential,
winningTeam

</details>
