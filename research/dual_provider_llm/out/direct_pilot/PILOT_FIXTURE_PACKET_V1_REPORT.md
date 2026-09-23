# Pilot Fixture Packet V1: Provenance and Validation

Exploratory data-packet build for the direct-LLM hypothesis pilot. This report covers **provenance and validation only**. It makes no predictive interpretation. No model was fit, no target outcome was read, and no LLM was called.

| | |
|---|---|
| Packet | `research/dual_provider_llm/out/direct_pilot/PILOT_FIXTURE_PACKET_V1.json` |
| Packet SHA-256 (file bytes) | `ea3fb8353801e2b414c056585173e5204539f3e3555cf5cd7dec2a2eba91556c` |
| Contract | `dual_provider_llm_packet_v1` |
| Builder | `research/dual_provider_llm/build_pilot_packet.py` + `src/research/dual_provider_llm/packet.py` (`dual_provider_pilot_packet_builder_v1`) |
| Built (as_of) | 2026-09-23T04:07:28Z (`as_of_unix` 1790136448); rebuilding with the same `--as-of-unix` is byte-identical |
| Provider | TheStatsAPI only |

## Fixture and selection

| | |
|---|---|
| Fixture | `thestatsapi:mt_022075291` |
| Kickoff | 2026-09-25T18:30:00Z (`cutoff_unix` = 1790361000) |
| Competition | LaLiga 2 (Spain), `comp_0976`, season `sn_1368511` |
| Home | Girona FC (`tm_029137`) |
| Away | Albacete Balompié (`tm_89845`) |

Selection rule, applied mechanically by the builder (not hard-coded):

1. Take scheduled fixtures from the latest cached TheStatsAPI snapshot (20260923; 4 competitions, 168 fixtures).
2. Keep those with kickoff after `as_of`.
3. Require both teams to have at least 10 completed prior TheStatsAPI matches with at least one populated rich field.
4. Sort by (kickoff, provider fixture id) and take the first.

The first ten candidates and their eligibility are recorded in `selection_rule.first_candidates_in_order`. The earliest fixture was eligible.

## History completion (fetched gaps)

The local finished-fixture cache ended at 2026-09-14. Each selected team had one completed league match after that, known only from the scheduled snapshots. With the operator's approval, exactly those two were fetched using the repository's cache-first client (`scripts/thestatsapi_client.get_json`): 4 read-only calls, no LLM.

| Match | Kickoff | Fixture | Role in packet |
|---|---|---|---|
| `mt_466496199` | 2026-09-18 | Albacete Balompié v Córdoba | away team's most recent match |
| `mt_988908403` | 2026-09-19 | Cádiz v Girona FC | home team's most recent match |

Both records were asserted to be `finished`, strictly before the target kickoff, shaped as the normalizer expects, and oriented home/away the same way as their snapshot entries. The cached files (`dpl_match_*`, `dpl_stats_*`) are **not committed**; their SHA-256 values are listed in `provenance.fetched_gap_files`.

## Coverage

| | Girona FC (HOME_TEAM) | Albacete Balompié (AWAY_TEAM) |
|---|---|---|
| Prior matches in cache | 82 | 90 |
| With rich stats | 82 | 90 |
| No stats / stats conflict | 0 / 0 | 0 / 0 |
| Raw recent rows | 10 (2026-05-11 → 2026-09-19) | 10 (2026-05-09 → 2026-09-18) |
| Distinct rich concepts populated | 17 of 17 | 17 of 17 |
| History span | 2024-08-15 → 2026-09-19 | 2024-08-15 → 2026-09-18 |
| By competition/season | `comp_8814` (LaLiga) sn_5761468: 38; sn_7246390: 38; `comp_0976` (LaLiga 2) sn_1368511: 6 | `comp_0976` sn_8425423: 42; sn_8437950: 42; sn_1368511: 6 |

Per-metric FOR coverage over all prior matches is 100% for every concept except these:

| Concept | Girona | Albacete |
|---|---|---|
| `high_claims` | 72% | 74% |
| `red_cards` | 18% | 21% |
| `yellow_cards` | 95% | 99% |
| `saves` | 98% | 99% |
| `fouled_in_final_third` | 98% | 100% |
| `big_chances` | 99% | 100% |
| `fouls` | 99% | 100% |

The full table is in `coverage_summary.<ROLE>.per_metric_FOR`.

Evidence refs: **1,454** in total.
- 498 are aggregates: 388 ADEQUATE (n ≥ 10), 102 LIMITED (5–9), 8 SPARSE (1–4).
- 956 are raw per-match values.

## Field scope

The packet has 25 concepts, all at FULL_MATCH level. They are listed with provider paths and semantics in `field_scope.concepts`.
- **Standard (8):** goals, shots, shots_on_target, corners, fouls, possession, yellow_cards, red_cards.
- **Rich (17):** shots_inside_box, shots_outside_box, blocked_shots, big_chances, touches_in_box, final_third_entries, fouled_in_final_third, accurate_crosses, accurate_long_balls, aerial_duel_pct, ground_duel_pct, tackles, tackles_won_pct, interceptions, clearances, saves, high_claims.

Excluded, and deliberately not named inside the packet:
- npxG (unsupported);
- xG (not reconciled against npxG);
- goals_prevented (0% populated);
- half-level splits (the TheStatsAPI stats payload is used at period `all` only).

Goals come from historical completed matches' fixture scores; the target match is never read.

Semantics notes carried in the packet:
- FOR is the target team's value. AGAINST is the opponent's value in the same match; for example, AGAINST tackles are tackles made *by the opponent*.
- `possession`, `aerial_duel_pct` and `ground_duel_pct` are complementary between the two sides, so AGAINST is not independent of FOR.
- `blocked_shots` is attributed to the named side as the provider reports it. Whether it counts that side's shots that were blocked, or blocks it made, is **not independently verified**.

## Integrity checks

These are mechanical re-derivations from the raw payload cells. They don't restate how the packet was built.

| Check | Result |
|---|---|
| TARGET_OUTCOME_INCLUDED | false |
| TARGET_POSTMATCH_STATS_INCLUDED | false (the target id appears only in `fixture` / `selection_rule`; no stats file exists for it in the cache) |
| MARKET_DATA_INCLUDED | false |
| P_MODEL_INCLUDED | false |
| FUTURE_MATCH_OBSERVATIONS_INCLUDED | false |
| N_HISTORY_ROWS_AT_OR_AFTER_TARGET_KICKOFF | 0 |
| N_DUPLICATE_EVIDENCE_REFS | 0 |
| N_UNTRACEABLE_NUMERIC_EVIDENCE_ITEMS | 0 (every aggregate recomputed from raw cells; every raw value matches its cell; every non-null raw cell in a raw row is emitted) |
| N_NPXG_ITEMS | 0 |
| N_NULLS_COERCED_TO_ZERO | 0 (a null counted as data, or data hidden as null, would both count here) |
| Forbidden-token scan (odds, p_model, npxg, closing, settlement, score, manager, …) | no hits |
| Team-id continuity | each team id carries one name; no other provider id uses either name |
| Conflicting stats payloads | 16 in the whole cache, **0** in either team's history (conflicts are never resolved by picking a version) |
| Conflicting fixture records | 0 |
| CHAMPION | `0b8f5ff3…c00c9` before and after; not read by the packet |

## Limitations to know before use

1. **History scope.** "Most recent 10" means within the *cached competitions*: league fixture lists for the cached seasons, plus the two fetched league matches. Cup and other competitions were never enumerated.
2. **Division mix.** Girona's ALL_PRIOR window spans two LaLiga seasons (`comp_8814`, 76 matches) and six LaLiga 2 matches. Albacete's is entirely LaLiga 2. Every raw row carries its `competition_id` and `season_id`.
3. **Identity.** The packet is TheStatsAPI-only and keyed by provider team id. No FootyStats evidence is included, because no reviewed cross-provider team mapping exists.
4. **Size.** 448 KB as written (indented), about 382 KB compact, roughly 95k tokens. That is likely too large to paste into a chat box. Uploading the JSON file is the practical path.

## Git hygiene

Committed:
- the builder;
- the library;
- 11 synthetic-only tests;
- this report and the packet.

Not committed: provider cache files, the usage log, budget state and credentials.
