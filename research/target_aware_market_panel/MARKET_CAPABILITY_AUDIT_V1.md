# Market Capability Audit V1

Generated from `MARKET_CAPABILITY_REGISTRY_V1.json`, which is itself derived by scanning the TheStatsAPI cache (`src/research/target_aware_market_panel/registry.py`). Label capability and price capability are separate columns.

Finished fixtures: 5640. Stats payloads (unambiguous): 5623. Conflicting payloads excluded: 16.

| Market | Label | Coverage | Priced (validated) | Timestamped pre-KO | Genuine close | Raw price present | Gen | Model | Market cmp | Reason |
|---|---|---|---|---|---|---|---|---|---|---|
| TOTAL_GOALS | yes | 1.0 | yes | yes | yes | yes | yes | yes | yes |  |
| HOME_GOALS | yes | 1.0 | no | no | no | yes | yes | yes | no | raw prices present but no validated adapter (normalizer/closing) for this key |
| AWAY_GOALS | yes | 1.0 | no | no | no | yes | yes | yes | no | raw prices present but no validated adapter (normalizer/closing) for this key |
| BTTS | yes | 1.0 | yes | yes | no | yes | yes | yes | yes |  |
| TOTAL_CORNERS | yes | 0.9952 | no | no | no | yes | yes | yes | no | raw prices present but no validated adapter (normalizer/closing) for this key |
| HOME_CORNERS | yes | 0.9952 | no | no | no | yes | yes | yes | no | raw prices present but no validated adapter (normalizer/closing) for this key |
| AWAY_CORNERS | yes | 0.9952 | no | no | no | yes | yes | yes | no | raw prices present but no validated adapter (normalizer/closing) for this key |
| TOTAL_YELLOW_CARDS | yes | 0.968 | no | no | no | yes | yes | yes | no | priced quantity differs from label (PROXY_CARDS_MARKET_QUANTITY_DIFFERS) |
| HOME_YELLOW_CARDS | yes | 0.968 | no | no | no | no | no | yes | no | no provider market for this statistic/scope/period |
| AWAY_YELLOW_CARDS | yes | 0.968 | no | no | no | no | no | yes | no | no provider market for this statistic/scope/period |
| TOTAL_CARDS | no | 0.1634 | no | no | no | yes | no | no | no | label: red_cards.all both-side coverage 0.163 < 0.9 |
| HOME_CARDS | no | 0.1634 | no | no | no | no | no | no | no | label: red_cards.all both-side coverage 0.163 < 0.9 |
| AWAY_CARDS | no | 0.1634 | no | no | no | no | no | no | no | label: red_cards.all both-side coverage 0.163 < 0.9 |
| TOTAL_OFFSIDES | yes | 0.9511 | no | no | no | no | no | yes | no | no provider market for this statistic/scope/period |
| HOME_OFFSIDES | yes | 0.9511 | no | no | no | no | no | yes | no | no provider market for this statistic/scope/period |
| AWAY_OFFSIDES | yes | 0.9511 | no | no | no | no | no | yes | no | no provider market for this statistic/scope/period |
| FH_TOTAL_GOALS | no | 0.0 | no | no | no | yes | no | no | no | label: bulk fixture lists carry no half-time score (0/5640 rows); only single-match records do. Needs a provider backfill; never derived fro |
| FH_HOME_GOALS | no | 0.0 | no | no | no | no | no | no | no | label: bulk fixture lists carry no half-time score (0/5640 rows); only single-match records do. Needs a provider backfill; never derived fro |
| FH_AWAY_GOALS | no | 0.0 | no | no | no | no | no | no | no | label: bulk fixture lists carry no half-time score (0/5640 rows); only single-match records do. Needs a provider backfill; never derived fro |
| FH_BTTS | no | 0.0 | no | no | no | yes | no | no | no | label: bulk fixture lists carry no half-time score (0/5640 rows); only single-match records do. Needs a provider backfill; never derived fro |
| FH_TOTAL_CORNERS | yes | 0.9947 | no | no | no | no | no | yes | no | no provider market for this statistic/scope/period |
| FH_HOME_CORNERS | yes | 0.9947 | no | no | no | no | no | yes | no | no provider market for this statistic/scope/period |
| FH_AWAY_CORNERS | yes | 0.9947 | no | no | no | no | no | yes | no | no provider market for this statistic/scope/period |
| FH_TOTAL_YELLOW_CARDS | yes | 0.9667 | no | no | no | no | no | yes | no | no provider market for this statistic/scope/period |
| FH_HOME_YELLOW_CARDS | yes | 0.9667 | no | no | no | no | no | yes | no | no provider market for this statistic/scope/period |
| FH_AWAY_YELLOW_CARDS | yes | 0.9667 | no | no | no | no | no | yes | no | no provider market for this statistic/scope/period |
| FH_TOTAL_CARDS | no | 0.1634 | no | no | no | no | no | no | no | label: red_cards.first_half both-side coverage 0.163 < 0.9 |
| FH_HOME_CARDS | no | 0.1634 | no | no | no | no | no | no | no | label: red_cards.first_half both-side coverage 0.163 < 0.9 |
| FH_AWAY_CARDS | no | 0.1634 | no | no | no | no | no | no | no | label: red_cards.first_half both-side coverage 0.163 < 0.9 |
| FH_TOTAL_OFFSIDES | yes | 0.9509 | no | no | no | no | no | yes | no | no provider market for this statistic/scope/period |
| FH_HOME_OFFSIDES | yes | 0.9509 | no | no | no | no | no | yes | no | no provider market for this statistic/scope/period |
| FH_AWAY_OFFSIDES | yes | 0.9509 | no | no | no | no | no | yes | no | no provider market for this statistic/scope/period |
| SH_TOTAL_GOALS | no | 0.0 | no | no | no | no | no | no | no | label: bulk fixture lists carry no half-time score (0/5640 rows); only single-match records do. Needs a provider backfill; never derived fro |
| SH_HOME_GOALS | no | 0.0 | no | no | no | no | no | no | no | label: bulk fixture lists carry no half-time score (0/5640 rows); only single-match records do. Needs a provider backfill; never derived fro |
| SH_AWAY_GOALS | no | 0.0 | no | no | no | no | no | no | no | label: bulk fixture lists carry no half-time score (0/5640 rows); only single-match records do. Needs a provider backfill; never derived fro |
| SH_BTTS | no | 0.0 | no | no | no | yes | no | no | no | label: bulk fixture lists carry no half-time score (0/5640 rows); only single-match records do. Needs a provider backfill; never derived fro |
| SH_TOTAL_CORNERS | yes | 0.9943 | no | no | no | no | no | yes | no | no provider market for this statistic/scope/period |
| SH_HOME_CORNERS | yes | 0.9943 | no | no | no | no | no | yes | no | no provider market for this statistic/scope/period |
| SH_AWAY_CORNERS | yes | 0.9943 | no | no | no | no | no | yes | no | no provider market for this statistic/scope/period |
| SH_TOTAL_YELLOW_CARDS | yes | 0.9673 | no | no | no | no | no | yes | no | no provider market for this statistic/scope/period |
| SH_HOME_YELLOW_CARDS | yes | 0.9673 | no | no | no | no | no | yes | no | no provider market for this statistic/scope/period |
| SH_AWAY_YELLOW_CARDS | yes | 0.9673 | no | no | no | no | no | yes | no | no provider market for this statistic/scope/period |
| SH_TOTAL_CARDS | no | 0.1634 | no | no | no | no | no | no | no | label: red_cards.second_half both-side coverage 0.163 < 0.9 |
| SH_HOME_CARDS | no | 0.1634 | no | no | no | no | no | no | no | label: red_cards.second_half both-side coverage 0.163 < 0.9 |
| SH_AWAY_CARDS | no | 0.1634 | no | no | no | no | no | no | no | label: red_cards.second_half both-side coverage 0.163 < 0.9 |
| SH_TOTAL_OFFSIDES | yes | 0.9509 | no | no | no | no | no | yes | no | no provider market for this statistic/scope/period |
| SH_HOME_OFFSIDES | yes | 0.9509 | no | no | no | no | no | yes | no | no provider market for this statistic/scope/period |
| SH_AWAY_OFFSIDES | yes | 0.9509 | no | no | no | no | no | yes | no | no provider market for this statistic/scope/period |
| MATCH_RESULT_1X2 | yes | 1.0 | yes | yes | yes | yes | no | no | no | context only (1X2 is not a target of this experiment) |

## Rules

- **eligible_for_oos_modeling**: label supported AND semantics verified AND not context-only
- **eligible_for_hypothesis_generation**: modeling-eligible AND a provider market exists in the raw captures for the same statistic/scope/period (SAME), OR the pre-registered BOOKINGS proxy exception: total yellow cards vs the provider 'total_cards' market, flagged PROXY and never eligible for market comparison
- **eligible_for_market_comparison**: generation-eligible AND validated adapter AND quantity SAME AND pre-kickoff timestamped captures exist

## Semantic notes

- Half-time GOALS cannot be settled: bulk fixture lists carry no half-time score.
- Red cards are mostly null and mixed-zero, so any yellow+red 'cards' label fails closed. TOTAL_YELLOW_CARDS is a provider-native proxy of the 'total_cards' market and is never compared with it.
- Half-level corners and yellows are label-supported (halves sum to the full match) but have no provider market, so they are not generation targets. They are still exposed as half-level context.
- `cma` `last_seen` prices carry no capture time and are never a close. Genuine close = latest `research_odds` capture strictly before kickoff, for markets with a validated closing adapter only.
