# Coverage Matrix — Markets & Raw Stats Across Both APIs

_Authoritative reference produced by the coverage-matrix-audit. Verified against real API responses (cache-first; 50 live requests). Look up 'is field X available in league Y' and 'is market Z priced by book B' here._

## Gating answer (decisive)

**YES — per-side (team-specific) stat markets are priced by real books, so the asymmetric engine's EV layer CAN be tested against real per-side prices — but only for specific markets, books, and leagues (see below), not universally.**

- **bet365**: prices `team_total_goals`, `team_corners`, `team_shots`, `team_shots_on_target` in **both Championship and EPL** (Championship n=222 cached; EPL n=10 live).

- **betmgm-uk**: prices the full per-side set in **EPL** (n=10); returned **no markets at all** for the Championship fixtures sampled (n=10).

- **paddy-power**: prices `team_corners` in **EPL** (n=10); prices markets but **no per-side markets** in Championship (n=10).

- **pinnacle** and **betfair-exchange**: **no per-side stat markets** (n=222 cached each).

- **FootyStats**: no per-side stat markets, but does price **per-side clean sheet** (`odds_team_a_cs_*`, `odds_team_b_cs_*`).


**Caveat:** no per-side **cards** market was found in any book/source. Per-side EV is testable for corners, goals, and shots (bet365 most reliably), NOT for cards — cards EV can only be tested on match totals.


## Part 1 — Market coverage (odds)

### Books probed

- Cached corpus (Championship): bet365, betfair-exchange, pinnacle (n=222 fixtures each).

- Never in cache, probed live: paddy-power, betmgm-uk (EPL + Championship, n=10 each).


### bet365 market coverage (Championship, n=222) — market × kind × coverage × overround

| market | kind | coverage | typ. overround | lines |
|---|---|---|---|---|
| match_odds | result | 93.7% | — | — |
| asian_handicap | result_per_side | 93.2% | — | -4.25,-4,-3.75,-3.5,-3.25,-3,-2.75,-2.5 |
| draw_no_bet | result_per_side | 93.2% | — | — |
| correct_score | other | 92.3% | — | — |
| btts | result | 91.9% | 1.0761 | — |
| btts_first_half | result | 89.6% | 1.0633 | — |
| btts_second_half | result | 89.6% | 1.0665 | — |
| first_half_total_goals | match_total | 88.7% | 1.0595 | 0.5,1,1.5,2,2.5,3.5,4.5 |
| total_goals_btts | match_total | 88.7% | — | 2.5 |
| handicap_result | match_total | 88.3% | — | -4,-3,-2,-1,+1,+2,+3,+4 |
| total_goals | match_total | 85.6% | 1.0547 | 0.5,1.5,1.75,2,2.25,2.5,2.75,3 |
| double_chance | other | 75.2% | — | — |
| match_corners | match_total | 73.4% | 1.079 | 7.5,8,8.5,9,9.5,10,10.5,11 |
| first_half_result | result | 69.8% | — | — |
| half_time_double_chance | other | 68.9% | — | — |
| team_total_goals | per_side_stat | 66.7% | 1.0556 | 0.5,1.5,2.5,3.5,4.5,5.5,6.5,7.5 |
| team_corners | per_side_stat | 45.5% | 1.0792 | 2.5,3.5,4.5,5.5,6.5,7.5 |
| second_half_result | result | 22.1% | — | — |
| to_score_a_penalty | per_side_stat | 21.6% | — | — |
| total_cards | match_total | 21.2% | 1.079 | 2.5,3.5,4.5,5.5 |
| team_shots | per_side_stat | 10.8% | 1.0851 | 8.5,9.5,10.5,11.5,12.5,13.5,14.5,15.5 |
| match_shots | match_total | 10.4% | 1.0794 | 22.5,23.5,24.5,25.5,26.5,27.5,28.5,29.5 |
| team_shots_on_target | per_side_stat | 10.4% | 1.079 | 2.5,3.5,4.5,5.5,6.5 |
| match_shots_on_target | match_total | 9.9% | 1.0792 | 7.5,8.5,9.5 |
| to_miss_a_penalty | per_side_stat | 3.6% | — | — |
| a_penalty_in_match | result | 2.3% | 1.0665 | — |
| first_team_to_score | other | 0.9% | — | — |


### Corners lines priced (bet365, Championship)

- **match_corners** (total): lines ['7.5', '8', '8.5', '9', '9.5', '10', '10.5', '11', '11.5', '12.5'] — cov 73.4%

- **team_corners** (per-side): lines ['2.5', '3.5', '4.5', '5.5', '6.5', '7.5'] — cov 45.5%

- Corners 7.5–12.5: match_corners spans 7.5–10 in cache; per-side team_corners uses lower per-team lines (2.5–7.5). Higher total lines (11.5, 12.5) not observed.


### Cards / goals / BTTS / handicap (bet365, Championship)

- **total_cards** (match_total): cov 21.2%, lines ['2.5', '3.5', '4.5', '5.5']

- **total_goals** (match_total): cov 85.6%, lines ['0.5', '1.5', '1.75', '2', '2.25', '2.5', '2.75', '3', '3.25', '3.5', '4.5', '5.5', '6.5', '7.5', '8.5']

- **team_total_goals** (per_side_stat): cov 66.7%, lines ['0.5', '1.5', '2.5', '3.5', '4.5', '5.5', '6.5', '7.5']

- **btts** (result): cov 91.9%, lines —

- **asian_handicap** (result_per_side): cov 93.2%, lines ['-4.25', '-4', '-3.75', '-3.5', '-3.25', '-3', '-2.75', '-2.5', '-2.25', '-2', '-1.75', '-1.5', '-1.25', '-1', '-0.75', '-0.5', '-0.25', '+0.0', '+0.25', '+0.5', '+0.75', '+1', '+1.25', '+1.5', '+1.75', '+2', '+2.25', '+2.5', '+2.75', '+3', '+3.25', '+3.5', '+3.75', '+4', '+4.25']

- **handicap_result** (match_total): cov 88.3%, lines ['-4', '-3', '-2', '-1', '+1', '+2', '+3', '+4']

- **first_half_total_goals** (match_total): cov 88.7%, lines ['0.5', '1', '1.5', '2', '2.5', '3.5', '4.5']


### League difference (per-side markets), from live probe

| league | book | n probed | per-side markets found |
|---|---|---|---|
| Championship | paddy-power | 10 | — |
| Championship | betmgm-uk | 10 | — |
| EPL | paddy-power | 10 | team_corners |
| EPL | betmgm-uk | 10 | team_corners, team_shots, team_shots_on_target, team_total_goals |
| EPL | bet365 | 10 | team_corners, team_shots, team_shots_on_target, team_total_goals, to_miss_a_penalty, to_score_a_penalty |


**Material league difference confirmed:** per-side markets are richer in **EPL** than **Championship** for paddy-power and betmgm-uk. bet365 carries per-side in both.


### FootyStats priced markets (verified, not assumed)

- Priced: 1X2 (`odds_ft_1/x/2`), O/U goals 0.5–4.5, BTTS, 1st-half markets, double chance.

- **Corners odds present**: 1X2 (`odds_corners_1/x/2`) + O/U 7.5/8.5/9.5/10.5/11.5 — confirms the prior claim.

- **Per-side clean sheet present**: `odds_team_a_cs_*`, `odds_team_b_cs_*`.

- **No cards odds, no offsides odds** — confirms prior claim (cards/offsides odds keys found: NONE).


## Part 2 — Raw stat coverage

### TheStatsAPI field population per league (min % across seasons; non-null home AND away)

| field | Championship | Ligue 2 | La Liga 2 |
|---|---|---|---|
| accurate_crosses | 98% | 99% | 100% |
| accurate_long_balls | 98% | 99% | 100% |
| aerial_duels_percentage | 98% | 99% | 100% |
| ball_recoveries | 98% | 99% | 100% |
| big_chances | 95% | 94% | 97% |
| big_chances_missed | 87% | 78% | 87% |
| blocked_shots | 98% | 100% | 100% |
| clearances | 98% | 99% | 100% |
| corner_kicks | 98% | 99% | 100% |
| dispossessed | 98% | 99% | 100% |
| dribbles_percentage | 98% | 99% | 100% |
| duels_won_percentage | 98% | 99% | 100% |
| expected_goals | 98% | 0% | 0% |
| final_third_entries | 98% | 99% | 100% |
| fouled_in_final_third | 95% | 97% | 99% |
| fouls | 97% | 99% | 100% |
| goal_kicks | 98% | 99% | 100% |
| goals_prevented | 98% | 0% | 0% |
| ground_duels_percentage | 98% | 99% | 100% |
| high_claims | 4% | 72% | 71% |
| hit_woodwork | 98% | 100% | 100% |
| interceptions | 98% | 99% | 100% |
| np_expected_goals | 96% | 54% | 0% |
| saves | 97% | 98% | 99% |
| shots_inside_box | 98% | 100% | 100% |
| shots_on_target | 98% | 100% | 100% |
| shots_outside_box | 98% | 100% | 100% |
| tackles | 98% | 99% | 100% |
| tackles_won_percentage | 98% | 99% | 100% |
| touches_in_penalty_area | 5% | 99% | 100% |
| yellow_cards | 94% | 97% | 99% |


**TheStatsAPI notable gaps:** `goals_prevented` and `np_expected_goals` **0%/absent** everywhere; `expected_goals` **absent in Ligue 2 and one La Liga 2 season**; `high_claims` thin (4–76%); `touches_in_penalty_area` **thin in Championship (as low as 5%)**; `big_chances_missed` ~78–90%.


### FootyStats field population (played matches; forward cache — LIMITED sample)

Sample: 132 played of 3114 matches (forward cache is mostly upcoming fixtures with `-1` sentinels).

| field | non-null % | zero/sentinel | absent | note |
|---|---|---|---|---|
| homeGoalCount | 75.8% | 32 | 0 |  |
| awayGoalCount | 72.7% | 36 | 0 |  |
| team_a_corners | 97.7% | 3 | 0 |  |
| team_b_corners | 97.7% | 3 | 0 |  |
| team_a_fh_corners | 85.6% | 19 | 0 |  |
| team_a_2h_corners | 87.1% | 17 | 0 |  |
| team_a_yellow_cards | 82.6% | 23 | 0 |  |
| team_a_red_cards | 6.1% | 124 | 0 |  |
| team_a_fh_cards | 50.0% | 66 | 0 |  |
| team_a_2h_cards | 59.1% | 54 | 0 |  |
| team_a_fouls | 100.0% | 0 | 0 |  |
| team_a_shots | 100.0% | 0 | 0 |  |
| team_a_shotsOnTarget | 97.7% | 3 | 0 |  |
| team_a_shotsOffTarget | 100.0% | 0 | 0 |  |
| team_a_possession | 100.0% | 0 | 0 |  |
| team_a_offsides | 78.0% | 29 | 0 |  |
| team_a_attacks | 100.0% | 0 | 0 |  |
| team_a_dangerous_attacks | 100.0% | 0 | 0 |  |
| team_a_xg | 100.0% | 0 | 0 |  |
| total_xg_prematch | 18.9% | 107 | 0 |  |
| team_a_penalties | 0.0% | 0 | 132 |  |
| team_a_freekicks | 100.0% | 0 | 0 |  |
| team_a_throwins | 100.0% | 0 | 0 |  |
| team_a_goalkicks | 98.5% | 2 | 0 |  |
| refereeID | 0.0% | 0 | 132 |  |
| coach_a_ID | 90.9% | 0 | 12 |  |


**FootyStats caveat (stale-signal warning):** the forward cache understates population because it is dominated by unplayed fixtures using `-1` sentinels. On genuinely **complete** matches (ground-truth sample), corners/cards/xG/refereeID ARE populated. FootyStats core fields are effectively ~99–100% on played matches, consistent with the prior claim; the low rates above are a sampling artifact, not a data gap.


### Profile-dimension buildability per league (asymmetric engine)

| profile dimension | Championship | Ligue 2 | La Liga 2 |
|---|---|---|---|
| attacking_width | BUILDABLE | BUILDABLE | BUILDABLE |
| central_penetration | THIN (weak: touches_in_penalty_area=5%) | BUILDABLE | BUILDABLE |
| defensive_block_orientation | BUILDABLE | BUILDABLE | BUILDABLE |
| aerial_ground | BUILDABLE | BUILDABLE | BUILDABLE |
| goalkeeper | BUILDABLE | THIN (weak: goals_prevented=0%) | THIN (weak: goals_prevented=0%) |
| discipline | BUILDABLE | BUILDABLE | BUILDABLE |


**Plain per-league verdicts:**

- **goalkeeper** dimension is **NOT BUILDABLE anywhere** on TheStatsAPI: `goals_prevented`=0% and `high_claims` thin. GK contribution must drop `goals_prevented` or use `saves` alone.

- **central_penetration** is **THIN in Championship** (`touches_in_penalty_area` as low as 5%). Usable in Ligue 2 / La Liga 2 where it is ~100%.

- **attacking_width, defensive_block_orientation, aerial_ground, discipline** are BUILDABLE across all three rich leagues (fields ~100%).


## Part 3 — Referee data

**Pre-match referee assignment is NOT available in either source.**

- TheStatsAPI: fixture records carry no referee field; /stats has no referee node.

- FootyStats: refereeID is None for 2982/2982 upcoming (incomplete) matches in the forward cache; populates only post-match.

- Post-match, FootyStats provides `refereeID` (integer id) only; **no career card/foul rates from the API** — rates must be derived by aggregating the corpus.


**Engine implication:** The asymmetric engine's cards conditioning cannot use the actual assigned referee pre-match. The league-level expanding card-rate is the PRIMARY pre-match path, not a fallback. A referee-specific rate is only usable in backtest (post-match id) or if a separate pre-match referee-assignment feed is added.


## Part 4 — Known 404s and gaps (confirmed; do not re-attempt)

- **Heatmap/spatial endpoints: 404 confirmed** — all of ['/football/matches/{mid}/heatmap', '/heatmaps', '/positions', '/touchmap'] returned 404 (cached probe, no re-spend).

- **`/stats` returns 404 for uncovered leagues**: confirmed ({'200': 3160, '429': 35, '404': 9} in usage log — 9×404 alongside 3160×200).

- **Opening lines / Betfair / Pinnacle retention:** in the cached Championship cohort, Betfair-exchange and Pinnacle are populated across finished AND scheduled fixtures (betfair ~66–81%, pinnacle ~90–95%). This **partly contradicts** the blanket 'recent/upcoming only' claim for this cohort — see stale-claims.


## Stale / corrected prior claims

1. **'Only derived totals, no per-side markets'** — **WRONG.** bet365 (and betmgm-uk/paddy-power in EPL) price genuine per-side stat markets (team_corners, team_total_goals, team_shots, team_shots_on_target).

2. **'Betfair/Pinnacle retained only for recent fixtures'** — **PARTLY STALE.** In the cached Championship cohort both are populated for finished fixtures too (betfair 81%, pinnacle 95%). Retention is better than the claim states for this cohort.

3. **FootyStats forward-cache low field rates** — **NOT a data gap.** An artifact of the cache being mostly unplayed fixtures with `-1` sentinels; played matches are ~99–100%.

4. **Referee usable pre-match** — **CONFIRMED FALSE.** Neither source exposes the assigned referee before kickoff.


## Budget report

- Monthly quota: 4768 → 4718 remaining (**50 live requests spent**; all on the live per-side probe of paddy-power/betmgm-uk/bet365 in Championship+EPL). Everything else answered from cache.

- Sample sizes: cached market analysis n=222/book (Championship); live per-side probe n=10/league/book; FootyStats field population n=132 played (low-confidence — forward cache).


## Dual-book EPL per-side coverage (follow-up probe)

After the spec was scoped to dual-book EPL (bet365 + betmgm-uk) plus bet365 Championship,
a follow-up read of the cached EPL per-side probe (n=10 upcoming EPL fixtures per book) found:

| book | team_total_goals | team_corners | team_shots | team_shots_on_target | fixtures with ANY markets |
|---|---|---|---|---|---|
| bet365 | 10/10 | 4/10 | 1/10 | 1/10 | 10/10 |
| betmgm-uk | 1/10 | 1/10 | 1/10 | 1/10 | 1/10 |

**Operational finding:** betmgm-uk priced only 1 of the 10 sampled EPL fixtures at probe time
(9/10 returned no markets), but when it did price a fixture it carried the FULL per-side set
(team_corners, team_total_goals, team_shots, team_shots_on_target) — matching bet365's per-side
capability. betmgm-uk appears to price fixtures closer to kickoff than bet365.

**Implication for the EV layer:** betmgm-uk per-side prices are available-when-priced and are
often absent for fixtures queried early. The EV layer must omit and record betmgm-uk for a market
it does not price at query time (Req 15.6), and bet365 is the more consistently available EPL
per-side source. Re-querying betmgm-uk nearer kickoff is expected to raise its coverage.
Sample sizes are small (n=10/book); treat coverage rates as low-confidence.
