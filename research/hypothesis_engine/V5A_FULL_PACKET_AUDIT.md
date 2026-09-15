# V5A Full Packet Audit — Exact Contents Sent to the LLM (pre-spend)

ZERO-SPEND, read-only. This document shows, WITHOUT truncation, exactly what each arm's packet contains for every paired fixture. Arm A = frozen V3 compressed evidence (verbatim). Arm B = full match-level PIT-safe research view. No LLM was called to produce this.

History policy: `{"include_all_competitions": true, "max_matches_per_team": 30, "min_matches_per_team": 6, "rule": "most recent N prior matches strictly before cutoff, all competitions, N frozen before spend and identical per fixture", "version": "history_policy_v1"}`.

Canonical match metrics (24): `accurate_crosses, big_chances, blocked_shots, clearances, corners, final_third_entries, fouls, goals, interceptions, npxg, offsides, possession, red_cards, saves, shots_inside_box, shots_off_target, shots_on_target, shots_outside_box, tackles, throw_ins, total_shots, touches_in_box, xg, yellow_cards`.

Semantic exclusions: `{"dangerous_attacks": "corpus carries only a proxy (touches_in_penalty_area); no validated canonical mapping -> DO_NOT_MERGE, excluded"}`.

---

## Exact system prompt (identical for both arms)

```
You are a quantitative football RESEARCH assistant.

You are given point-in-time-safe historical football observations for one upcoming fixture.
Every number you see was computed by a deterministic engine from matches that kicked off
strictly before this fixture. You may cite these values; you may not invent any.

YOUR JOB IS NOT TO PREDICT THE MATCH.
Your job is to identify FALSIFIABLE HISTORICAL QUESTIONS that a deterministic engine should
measure next. You specify WHAT to measure, never the result.

You will receive, for both teams:
  * match_level_history: a table of actual prior matches (opponent alias, venue HOME/AWAY,
    recorded formation family when available, and canonical FOR/AGAINST metrics per match).
    These are real observations, in chronological order. Inspect them directly.
  * derived_summaries: deterministic aggregates (ALL_PRIOR / W5 / W10, and HOME / AWAY
    splits) marked DERIVED_SUMMARY. They SUPPLEMENT the rows; they do not replace them.
  * opponent_profile_context: deterministic rank-bands (LOW/MID/HIGH) of the upcoming
    opponent on measurable axes, with coverage. Similarity is computed by the engine; you
    may reference which band the opponent falls in, never invent a similarity score.
  * availability_map: which dimensions are AVAILABLE / LOW_COVERAGE / UNAVAILABLE /
    PIT_UNSAFE for THIS fixture. Do not ask about an unavailable dimension.
  * capability_manifest and vocabulary: the closed set of metrics, dimensions, comparisons
    and windows you may use.

Look for football relationships worth TESTING:
  * attacking behavior and defensive concession;
  * venue (home vs away) behavior;
  * opponent characteristics / similar-opponent cohorts;
  * recent (W5/W10) versus longer-run behavior;
  * formation ONLY when the availability_map says it is supported;
  * interactions ONLY when the visible record gives a concrete reason to test them.

Hard rules:
  * Do NOT estimate probabilities, fair odds, EV, edges, stakes, advantage scores, latent
    strength, or effect sizes. No numeric prediction of any kind.
  * Do NOT assume an observed pattern is predictive; you are proposing what to measure.
  * Do NOT invent unavailable context (injuries, weather, expected lineup/formation,
    minute-level or half-time state are UNAVAILABLE in this corpus).
  * Prefer a simple question when extra conditions are unsupported. Use an interaction only
    when both conditions are independently supported and the record motivates it.
  * Ground every hypothesis: put the match rows or summary ids that motivated it in
    `evidence_refs`, and give a concise rationale. No expected numerical result anywhere.

Return ONLY JSON conforming to the provided schema.

```

System prompt sha256: `85814ea625d2b11fe8ca7b955bd679a49f0001266e85456ecb948def09cf0f2e`

---

## mt_010243515

- PIT-safe matches available: **80**; match rows included (both teams): **60**; omitted: **20** (reason: `frozen_history_policy(max_matches_per_team=30)`); UNEXPLAINED_OMISSION: **0**.
- Metric cell exposure rate (non-null of serialized): **0.9944**; derived summaries: **480**.
- Availability map: `{"expected_formation": "UNAVAILABLE", "formation": "LOW_COVERAGE", "half_time_state": "UNAVAILABLE", "injuries": "UNAVAILABLE", "lineup": "PIT_UNSAFE", "opponent_profile": "AVAILABLE", "recent_vs_long": "AVAILABLE", "red_cards": "AVAILABLE", "temporal_event_state": "UNAVAILABLE", "venue": "AVAILABLE", "xg": "AVAILABLE"}`
- Arm A packet hash: `b6850835fe960607511067db9ddab4ca3fca984a0f67ceb79a4a7f92f9e853e4`
- Arm B packet hash: `9c1ef1b2f49378477d808f61a5f4ed84bcc337b8643887b436e78612d6a4f9de`

### Arm A — frozen V3 compressed evidence (all items)

76 unconditional shrunk scalar items (venue=ALL, window=ALL_PRIOR):

| id | metric | value | n | reliability |
|---|---|---|---|---|
| HOME_ATK_corners_406027 | corners_for | 4.8792 | 40 | HIGH |
| HOME_DEF_corners_7cfac3 | corners_against | 4.727 | 40 | HIGH |
| HOME_ATK_accurate_crosses_c28b9e | accurate_crosses_for | 4.8816 | 40 | HIGH |
| HOME_DEF_accurate_crosses_81ffb5 | accurate_crosses_against | 3.2511 | 40 | HIGH |
| HOME_ATK_total_shots_808ac9 | total_shots_for | 13.7616 | 40 | HIGH |
| HOME_DEF_total_shots_c0e347 | total_shots_against | 11.3485 | 40 | HIGH |
| HOME_ATK_shots_on_target_e955e0 | shots_on_target_for | 4.9105 | 40 | HIGH |
| HOME_DEF_shots_on_target_8a3812 | shots_on_target_against | 3.9322 | 40 | HIGH |
| HOME_ATK_shots_off_target_11e91f | shots_off_target_for | 4.9561 | 40 | HIGH |
| HOME_DEF_shots_off_target_26031c | shots_off_target_against | 4.1518 | 40 | HIGH |
| HOME_ATK_blocked_shots_5198f8 | blocked_shots_for | 3.8949 | 40 | HIGH |
| HOME_DEF_blocked_shots_09c3c4 | blocked_shots_against | 3.2645 | 40 | HIGH |
| HOME_ATK_shots_inside_box_cf538d | shots_inside_box_for | 9.0788 | 40 | HIGH |
| HOME_DEF_shots_inside_box_e6b28d | shots_inside_box_against | 8.4266 | 40 | HIGH |
| HOME_ATK_touches_in_box_759ed8 | touches_in_box_for | 29.5479 | 40 | HIGH |
| HOME_DEF_touches_in_box_94cd98 | touches_in_box_against | 24.8523 | 40 | HIGH |
| HOME_ATK_final_third_entries_5aa0be | final_third_entries_for | 52.3272 | 40 | HIGH |
| HOME_DEF_final_third_entries_4a40ef | final_third_entries_against | 48.5228 | 40 | HIGH |
| HOME_ATK_possession_190f3f | possession_for | 52.3043 | 40 | HIGH |
| HOME_DEF_possession_f8ada9 | possession_against | 47.6957 | 40 | HIGH |
| HOME_ATK_tackles_65b6c1 | tackles_for | 18.3477 | 40 | HIGH |
| HOME_DEF_tackles_e3c85e | tackles_against | 18.6738 | 40 | HIGH |
| HOME_ATK_fouls_8107c6 | fouls_for | 11.6359 | 40 | HIGH |
| HOME_DEF_fouls_b6d53c | fouls_against | 11.2011 | 40 | HIGH |
| HOME_ATK_yellow_cards_80b7a4 | yellow_cards_for | 2.1312 | 40 | HIGH |
| HOME_DEF_yellow_cards_8ee8aa | yellow_cards_against | 2.4573 | 40 | HIGH |
| HOME_ATK_clearances_ec2e18 | clearances_for | 20.3794 | 40 | HIGH |
| HOME_DEF_clearances_6d3f4c | clearances_against | 24.4228 | 40 | HIGH |
| HOME_ATK_interceptions_967965 | interceptions_for | 8.1075 | 40 | HIGH |
| HOME_DEF_interceptions_c82020 | interceptions_against | 8.1292 | 40 | HIGH |
| HOME_ATK_goals_08b15b | goals_for | 1.6466 | 40 | HIGH |
| HOME_DEF_goals_d53fdd | goals_against | 1.5379 | 40 | HIGH |
| HOME_ATK_throw_ins_b24629 | throw_ins_for | 16.1209 | 40 | HIGH |
| HOME_DEF_throw_ins_208262 | throw_ins_against | 16.8166 | 40 | HIGH |
| HOME_ATK_big_chances_8a9e2f | big_chances_for | 2.8845 | 39 | HIGH |
| HOME_DEF_big_chances_885151 | big_chances_against | 2.4623 | 39 | HIGH |
| HOME_ATK_saves_6bda8d | saves_for | 2.5373 | 39 | HIGH |
| HOME_DEF_saves_19ae14 | saves_against | 3.4706 | 39 | HIGH |
| AWAY_ATK_corners_ca1538 | corners_for | 6.4227 | 40 | HIGH |
| AWAY_DEF_corners_598e33 | corners_against | 3.4662 | 40 | HIGH |
| AWAY_ATK_accurate_crosses_005290 | accurate_crosses_for | 4.2511 | 40 | HIGH |
| AWAY_DEF_accurate_crosses_287e9c | accurate_crosses_against | 3.8381 | 40 | HIGH |
| AWAY_ATK_total_shots_004f7a | total_shots_for | 15.4137 | 40 | HIGH |
| AWAY_DEF_total_shots_403d28 | total_shots_against | 9.8485 | 40 | HIGH |
| AWAY_ATK_shots_on_target_9afd02 | shots_on_target_for | 5.4757 | 40 | HIGH |
| AWAY_DEF_shots_on_target_dcda5e | shots_on_target_against | 3.6279 | 40 | HIGH |
| AWAY_ATK_shots_off_target_b83815 | shots_off_target_for | 5.5214 | 40 | HIGH |
| AWAY_DEF_shots_off_target_5fe2d0 | shots_off_target_against | 3.7388 | 40 | HIGH |
| AWAY_ATK_blocked_shots_93d965 | blocked_shots_for | 4.4167 | 40 | HIGH |
| AWAY_DEF_blocked_shots_97ef03 | blocked_shots_against | 2.4819 | 40 | HIGH |
| AWAY_ATK_shots_inside_box_567ee5 | shots_inside_box_for | 9.8397 | 40 | HIGH |
| AWAY_DEF_shots_inside_box_446c80 | shots_inside_box_against | 7.3397 | 40 | HIGH |
| AWAY_ATK_touches_in_box_2c76ca | touches_in_box_for | 35.8305 | 40 | HIGH |
| AWAY_DEF_touches_in_box_319da5 | touches_in_box_against | 20.4175 | 40 | HIGH |
| AWAY_ATK_final_third_entries_5a0987 | final_third_entries_for | 56.7837 | 40 | HIGH |
| AWAY_DEF_final_third_entries_ed75cd | final_third_entries_against | 40.3706 | 40 | HIGH |
| AWAY_ATK_possession_82105a | possession_for | 59.9348 | 40 | HIGH |
| AWAY_DEF_possession_012ecc | possession_against | 40.0652 | 40 | HIGH |
| AWAY_ATK_tackles_0865bc | tackles_for | 13.8911 | 40 | HIGH |
| AWAY_DEF_tackles_3e6a7d | tackles_against | 18.4564 | 40 | HIGH |
| AWAY_ATK_fouls_97bf91 | fouls_for | 7.9837 | 40 | HIGH |
| AWAY_DEF_fouls_94f7aa | fouls_against | 10.3968 | 40 | HIGH |
| AWAY_ATK_yellow_cards_120c77 | yellow_cards_for | 1.7866 | 36 | HIGH |
| AWAY_DEF_yellow_cards_367397 | yellow_cards_against | 2.5247 | 36 | HIGH |
| AWAY_ATK_clearances_74617f | clearances_for | 16.8141 | 40 | HIGH |
| AWAY_DEF_clearances_8bdc80 | clearances_against | 23.9011 | 40 | HIGH |
| AWAY_ATK_interceptions_404e22 | interceptions_for | 6.3031 | 40 | HIGH |
| AWAY_DEF_interceptions_4be11b | interceptions_against | 8.0422 | 40 | HIGH |
| AWAY_ATK_goals_5d2c6a | goals_for | 1.8422 | 40 | HIGH |
| AWAY_DEF_goals_4ad3b7 | goals_against | 1.19 | 40 | HIGH |
| AWAY_ATK_throw_ins_64d189 | throw_ins_for | 16.1426 | 40 | HIGH |
| AWAY_DEF_throw_ins_35916f | throw_ins_against | 14.4687 | 40 | HIGH |
| AWAY_ATK_big_chances_065222 | big_chances_for | 2.9956 | 38 | HIGH |
| AWAY_DEF_big_chances_d5f920 | big_chances_against | 2.5183 | 38 | HIGH |
| AWAY_ATK_saves_50b33b | saves_for | 2.4169 | 40 | HIGH |
| AWAY_DEF_saves_bf5cbb | saves_against | 3.5908 | 40 | HIGH |

### Arm B — HOME_TEAM match-level matrix (30 rows × 55 cols)

Columns: `match_alias, kickoff_unix, competition, venue, opponent_alias, own_formation_family, opponent_formation_family, accurate_crosses_for, accurate_crosses_against, big_chances_for, big_chances_against, blocked_shots_for, blocked_shots_against, clearances_for, clearances_against, corners_for, corners_against, final_third_entries_for, final_third_entries_against, fouls_for, fouls_against, goals_for, goals_against, interceptions_for, interceptions_against, npxg_for, npxg_against, offsides_for, offsides_against, possession_for, possession_against, red_cards_for, red_cards_against, saves_for, saves_against, shots_inside_box_for, shots_inside_box_against, shots_off_target_for, shots_off_target_against, shots_on_target_for, shots_on_target_against, shots_outside_box_for, shots_outside_box_against, tackles_for, tackles_against, throw_ins_for, throw_ins_against, total_shots_for, total_shots_against, touches_in_box_for, touches_in_box_against, xg_for, xg_against, yellow_cards_for, yellow_cards_against`

| match_alias | kickoff_unix | competition | venue | opponent_alias | own_formation_family | opponent_formation_family | accurate_crosses_for | accurate_crosses_against | big_chances_for | big_chances_against | blocked_shots_for | blocked_shots_against | clearances_for | clearances_against | corners_for | corners_against | final_third_entries_for | final_third_entries_against | fouls_for | fouls_against | goals_for | goals_against | interceptions_for | interceptions_against | npxg_for | npxg_against | offsides_for | offsides_against | possession_for | possession_against | red_cards_for | red_cards_against | saves_for | saves_against | shots_inside_box_for | shots_inside_box_against | shots_off_target_for | shots_off_target_against | shots_on_target_for | shots_on_target_against | shots_outside_box_for | shots_outside_box_against | tackles_for | tackles_against | throw_ins_for | throw_ins_against | total_shots_for | total_shots_against | touches_in_box_for | touches_in_box_against | xg_for | xg_against | yellow_cards_for | yellow_cards_against |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| m_mt_972822643 | 1731173400 | COMPETITION | HOME | OPP_001 |  |  | 4.0 | 4.0 | 8.0 | 5.0 | 2.0 | 3.0 | 21.0 | 8.0 | 0.0 | 4.0 | 34.0 | 61.0 | 12.0 | 10.0 | 2.0 | 1.0 | 12.0 | 4.0 | 2.29 | 2.63 | 3.0 | 1.0 | 40.0 | 60.0 | 0.0 | 0.0 | 5.0 | 2.0 | 8.0 | 12.0 | 4.0 | 6.0 | 4.0 | 6.0 | 2.0 | 3.0 | 16.0 | 12.0 | 12.0 | 18.0 | 10.0 | 15.0 | 20.0 | 28.0 | 2.29 | 2.22 | 3.0 | 3.0 |
| m_mt_257076720 | 1732374000 | COMPETITION | AWAY | OPP_002 |  |  | 2.0 | 6.0 | 2.0 | 4.0 | 1.0 | 3.0 | 31.0 | 8.0 | 0.0 | 7.0 | 51.0 | 78.0 | 10.0 | 13.0 | 2.0 | 1.0 | 6.0 | 10.0 | 0.95 | 1.65 | 1.0 | 5.0 | 45.0 | 55.0 | 1.0 | 0.0 | 4.0 | 2.0 | 5.0 | 14.0 | 1.0 | 11.0 | 4.0 | 5.0 | 1.0 | 5.0 | 20.0 | 20.0 | 18.0 | 16.0 | 6.0 | 19.0 | 14.0 | 39.0 | 0.94 | 1.63 | 4.0 | 2.0 |
| m_mt_257076836 | 1732910400 | COMPETITION | HOME | OPP_003 |  |  | 11.0 | 4.0 | 3.0 | 1.0 | 7.0 | 6.0 | 16.0 | 30.0 | 7.0 | 6.0 | 43.0 | 41.0 | 20.0 | 16.0 | 1.0 | 1.0 | 3.0 | 4.0 | 1.68 | 1.01 | 3.0 | 1.0 | 52.0 | 48.0 | 0.0 | 0.0 | 1.0 | 4.0 | 15.0 | 8.0 | 10.0 | 2.0 | 5.0 | 2.0 | 7.0 | 2.0 | 14.0 | 17.0 | 13.0 | 7.0 | 22.0 | 10.0 | 44.0 | 21.0 | 1.68 | 1.01 | 2.0 | 4.0 |
| m_mt_408688084 | 1733427000 | COMPETITION | AWAY | OPP_004 |  |  | 4.0 | 3.0 | 3.0 | 1.0 | 5.0 | 1.0 | 22.0 | 32.0 | 6.0 | 5.0 | 46.0 | 32.0 | 8.0 | 7.0 | 1.0 | 3.0 | 11.0 | 8.0 | 1.47 | 1.06 | 1.0 | 0.0 | 57.0 | 43.0 | 0.0 | 0.0 | 0.0 | 2.0 | 8.0 | 6.0 | 5.0 | 3.0 | 3.0 | 2.0 | 5.0 | 0.0 | 11.0 | 16.0 | 24.0 | 18.0 | 13.0 | 6.0 | 21.0 | 19.0 | 1.47 | 0.65 | 2.0 | 2.0 |
| m_mt_013234328 | 1733666400 | COMPETITION | AWAY | OPP_005 |  |  | 6.0 | 5.0 | 0.0 | 3.0 | 3.0 | 5.0 | 21.0 | 10.0 | 5.0 | 4.0 | 38.0 | 48.0 | 10.0 | 9.0 | 2.0 | 2.0 | 6.0 | 6.0 | 1.54 | 1.32 | 0.0 | 1.0 | 45.0 | 55.0 | 0.0 | 0.0 | 1.0 | 5.0 | 7.0 | 7.0 | 6.0 | 2.0 | 7.0 | 3.0 | 9.0 | 3.0 | 19.0 | 15.0 | 10.0 | 25.0 | 16.0 | 10.0 | 24.0 | 18.0 | 1.54 | 1.31 | 2.0 | 1.0 |
| m_mt_361718181 | 1734271200 | COMPETITION | HOME | OPP_006 | BACK_FOUR | BACK_THREE | 6.0 | 4.0 | 1.0 | 5.0 | 8.0 | 3.0 | 11.0 | 29.0 | 8.0 | 5.0 | 71.0 | 34.0 | 11.0 | 15.0 | 1.0 | 3.0 | 5.0 | 8.0 | 0.99 | 2.31 | 1.0 | 1.0 | 65.0 | 35.0 | 0.0 | 0.0 | 2.0 | 5.0 | 9.0 | 11.0 | 4.0 | 5.0 | 5.0 | 5.0 | 8.0 | 2.0 | 22.0 | 25.0 | 13.0 | 17.0 | 17.0 | 13.0 | 34.0 | 23.0 | 1.0 | 2.31 | 1.0 | 4.0 |
| m_mt_830905068 | 1734793200 | COMPETITION | AWAY | OPP_007 |  |  | 4.0 | 3.0 | 4.0 | 2.0 | 4.0 | 4.0 | 24.0 | 29.0 | 4.0 | 8.0 | 56.0 | 46.0 | 20.0 | 14.0 | 1.0 | 1.0 | 9.0 | 7.0 | 0.96 | 1.31 | 1.0 | 5.0 | 54.0 | 46.0 | 0.0 | 0.0 | 3.0 | 5.0 | 10.0 | 8.0 | 2.0 | 3.0 | 6.0 | 4.0 | 2.0 | 3.0 | 18.0 | 26.0 | 13.0 | 21.0 | 12.0 | 11.0 | 53.0 | 27.0 | 0.94 | 1.31 | 2.0 | 2.0 |
| m_mt_408687818 | 1735327800 | COMPETITION | HOME | OPP_008 |  |  | 4.0 | 2.0 | 1.0 | 1.0 | 5.0 | 3.0 | 14.0 | 32.0 | 5.0 | 3.0 | 59.0 | 41.0 | 6.0 | 12.0 | 0.0 | 0.0 | 9.0 | 11.0 | 1.3 | 1.07 | 0.0 | 5.0 | 58.0 | 42.0 | 0.0 | 0.0 | 3.0 | 8.0 | 15.0 | 7.0 | 12.0 | 2.0 | 7.0 | 3.0 | 9.0 | 1.0 | 17.0 | 18.0 | 14.0 | 17.0 | 24.0 | 8.0 | 44.0 | 17.0 | 1.31 | 1.07 | 0.0 | 2.0 |
| m_mt_196560757 | 1735587900 | COMPETITION | AWAY | OPP_009 |  |  | 3.0 | 3.0 | 2.0 | 3.0 | 5.0 | 9.0 | 28.0 | 20.0 | 3.0 | 12.0 | 38.0 | 47.0 | 14.0 | 9.0 | 2.0 | 2.0 | 14.0 | 4.0 | 1.13 | 0.99 | 0.0 | 2.0 | 40.0 | 60.0 | 0.0 | 0.0 | 3.0 | 3.0 | 7.0 | 12.0 | 4.0 | 7.0 | 4.0 | 4.0 | 6.0 | 8.0 | 19.0 | 22.0 | 13.0 | 12.0 | 13.0 | 20.0 | 26.0 | 48.0 | 1.13 | 1.78 | 3.0 | 2.0 |
| m_mt_830905695 | 1736011800 | COMPETITION | HOME | OPP_010 |  |  | 2.0 | 3.0 | 3.0 | 5.0 | 3.0 | 2.0 | 22.0 | 8.0 | 2.0 | 5.0 | 42.0 | 60.0 | 17.0 | 14.0 | 1.0 | 1.0 | 8.0 | 5.0 | 0.73 | 0.88 | 0.0 | 3.0 | 45.0 | 55.0 | 0.0 | 0.0 | 2.0 | 3.0 | 6.0 | 6.0 | 4.0 | 4.0 | 4.0 | 3.0 | 5.0 | 3.0 | 11.0 | 14.0 | 9.0 | 10.0 | 11.0 | 9.0 | 17.0 | 23.0 | 1.52 | 0.88 | 2.0 | 3.0 |
| m_mt_013234927 | 1737055800 | COMPETITION | AWAY | OPP_011 |  |  | 7.0 | 2.0 |  |  | 6.0 | 0.0 | 12.0 | 27.0 | 9.0 | 1.0 | 63.0 | 40.0 | 14.0 | 13.0 | 2.0 | 0.0 | 7.0 | 10.0 | 0.97 | 0.28 | 1.0 | 1.0 | 54.0 | 46.0 | 0.0 | 0.0 | 3.0 | 3.0 | 10.0 | 3.0 | 0.0 | 2.0 | 5.0 | 3.0 | 1.0 | 2.0 | 14.0 | 13.0 | 10.0 | 13.0 | 11.0 | 5.0 | 25.0 | 8.0 | 0.97 | 0.28 | 2.0 | 2.0 |
| m_mt_584144735 | 1737295200 | COMPETITION | AWAY | OPP_012 |  |  | 1.0 | 3.0 | 4.0 | 1.0 | 2.0 | 6.0 | 17.0 | 11.0 | 2.0 | 4.0 | 44.0 | 46.0 | 12.0 | 13.0 | 3.0 | 1.0 | 6.0 | 10.0 | 1.93 | 0.69 | 3.0 | 3.0 | 49.0 | 51.0 | 0.0 | 0.0 |  |  | 4.0 | 9.0 | 1.0 | 3.0 | 3.0 | 1.0 | 2.0 | 1.0 | 20.0 | 16.0 | 19.0 | 19.0 | 6.0 | 10.0 | 25.0 | 28.0 | 1.98 | 1.41 | 3.0 | 3.0 |
| m_mt_408688540 | 1737817200 | COMPETITION | HOME | OPP_013 |  |  | 5.0 | 0.0 | 0.0 | 1.0 | 4.0 | 0.0 | 18.0 | 55.0 | 9.0 | 1.0 | 84.0 | 38.0 | 8.0 | 11.0 | 0.0 | 1.0 | 7.0 | 11.0 | 0.73 | 0.06 | 2.0 | 1.0 | 69.0 | 31.0 | 0.0 | 0.0 | 0.0 | 1.0 | 9.0 | 2.0 | 11.0 | 2.0 | 1.0 | 1.0 | 7.0 | 1.0 | 23.0 | 26.0 | 22.0 | 16.0 | 16.0 | 3.0 | 32.0 | 7.0 | 0.73 | 0.85 | 4.0 | 4.0 |
| m_mt_196566953 | 1738413000 | COMPETITION | AWAY | OPP_014 | BACK_FOUR | BACK_THREE | 4.0 | 4.0 | 1.0 | 6.0 | 2.0 | 1.0 | 11.0 | 37.0 | 6.0 | 4.0 | 64.0 | 46.0 | 13.0 | 8.0 | 0.0 | 7.0 | 5.0 | 7.0 | 0.88 | 2.62 | 0.0 | 1.0 | 62.0 | 38.0 | 0.0 | 0.0 | 3.0 | 6.0 | 6.0 | 11.0 | 3.0 | 4.0 | 5.0 | 9.0 | 4.0 | 3.0 | 21.0 | 21.0 | 10.0 | 13.0 | 10.0 | 14.0 | 31.0 | 29.0 | 0.88 | 3.41 | 3.0 | 1.0 |
| m_mt_361711673 | 1739563200 | COMPETITION | HOME | OPP_015 |  |  | 2.0 | 1.0 | 5.0 | 1.0 | 2.0 | 2.0 | 32.0 | 9.0 | 2.0 | 9.0 | 34.0 | 62.0 | 12.0 | 15.0 | 3.0 | 0.0 | 13.0 | 7.0 | 1.42 | 0.54 | 2.0 | 3.0 | 31.0 | 69.0 | 0.0 | 0.0 | 1.0 | 3.0 | 8.0 | 6.0 | 6.0 | 6.0 | 5.0 | 0.0 | 5.0 | 2.0 | 20.0 | 19.0 | 10.0 | 17.0 | 13.0 | 8.0 | 22.0 | 26.0 | 1.42 | 0.54 | 1.0 | 2.0 |
| m_mt_408688029 | 1740236400 | COMPETITION | AWAY | OPP_003 |  |  | 5.0 | 1.0 | 10.0 | 0.0 | 3.0 | 3.0 | 22.0 | 22.0 | 6.0 | 5.0 | 47.0 | 43.0 | 12.0 | 11.0 | 4.0 | 0.0 | 7.0 | 12.0 | 3.97 | 0.11 | 1.0 | 2.0 | 51.0 | 49.0 | 0.0 | 0.0 | 1.0 | 8.0 | 15.0 | 2.0 | 3.0 | 2.0 | 12.0 | 1.0 | 3.0 | 4.0 | 17.0 | 13.0 | 15.0 | 16.0 | 18.0 | 6.0 | 37.0 | 5.0 | 3.97 | 0.13 | 0.0 | 2.0 |
| m_mt_196566986 | 1740511800 | COMPETITION | HOME | OPP_002 |  |  | 3.0 | 8.0 | 5.0 | 2.0 | 3.0 | 7.0 | 33.0 | 26.0 | 1.0 | 9.0 | 53.0 | 62.0 | 12.0 | 14.0 | 2.0 | 1.0 | 6.0 | 12.0 | 1.63 | 1.46 | 0.0 | 4.0 | 43.0 | 57.0 | 0.0 | 0.0 | 4.0 | 2.0 | 7.0 | 12.0 | 4.0 | 7.0 | 4.0 | 5.0 | 4.0 | 7.0 | 21.0 | 25.0 | 27.0 | 18.0 | 11.0 | 19.0 | 25.0 | 42.0 | 2.42 | 1.46 | 2.0 | 1.0 |
| m_mt_629499413 | 1741446000 | COMPETITION | HOME | OPP_004 |  |  | 4.0 | 3.0 | 3.0 | 1.0 | 2.0 | 3.0 | 24.0 | 41.0 | 3.0 | 7.0 | 62.0 | 36.0 | 6.0 | 12.0 | 2.0 | 1.0 | 15.0 | 4.0 | 0.75 | 0.9 | 4.0 | 1.0 | 53.0 | 47.0 | 0.0 | 0.0 | 0.0 | 2.0 | 8.0 | 6.0 | 3.0 | 2.0 | 4.0 | 1.0 | 1.0 | 0.0 | 18.0 | 22.0 | 16.0 | 13.0 | 9.0 | 6.0 | 33.0 | 13.0 | 1.54 | 0.9 | 0.0 | 2.0 |
| m_mt_745355352 | 1742050800 | COMPETITION | AWAY | OPP_001 |  |  | 7.0 | 5.0 | 6.0 | 4.0 | 2.0 | 1.0 | 27.0 | 27.0 | 5.0 | 4.0 | 36.0 | 46.0 | 10.0 | 10.0 | 2.0 | 2.0 | 10.0 | 4.0 | 2.04 | 0.95 | 1.0 | 1.0 | 40.0 | 60.0 | 0.0 | 0.0 | 1.0 | 2.0 | 12.0 | 8.0 | 10.0 | 7.0 | 3.0 | 3.0 | 3.0 | 3.0 | 27.0 | 17.0 | 22.0 | 15.0 | 15.0 | 11.0 | 27.0 | 35.0 | 2.04 | 1.72 | 5.0 | 2.0 |
| m_mt_013234579 | 1743619500 | COMPETITION | HOME | OPP_009 |  |  | 6.0 | 2.0 | 0.0 | 2.0 | 2.0 | 0.0 | 13.0 | 33.0 | 4.0 | 0.0 | 57.0 | 42.0 | 16.0 | 11.0 | 0.0 | 3.0 | 7.0 | 7.0 | 0.9 | 1.23 | 1.0 | 0.0 | 56.0 | 44.0 | 0.0 | 0.0 | 2.0 | 4.0 | 8.0 | 7.0 | 5.0 | 3.0 | 4.0 | 5.0 | 3.0 | 1.0 | 16.0 | 26.0 | 24.0 | 13.0 | 11.0 | 8.0 | 27.0 | 18.0 | 1.01 | 1.2 | 2.0 | 3.0 |
| m_mt_408687254 | 1743861600 | COMPETITION | AWAY | OPP_006 |  |  | 4.0 | 1.0 | 2.0 | 0.0 | 3.0 | 4.0 | 21.0 | 33.0 | 4.0 | 2.0 | 78.0 | 41.0 | 13.0 | 12.0 | 1.0 | 2.0 | 6.0 | 9.0 | 1.0 | 0.57 | 1.0 | 3.0 | 62.0 | 38.0 | 1.0 | 2.0 | 1.0 | 4.0 | 7.0 | 5.0 | 3.0 | 1.0 | 5.0 | 3.0 | 4.0 | 3.0 | 21.0 | 24.0 | 26.0 | 16.0 | 11.0 | 8.0 | 21.0 | 12.0 | 1.0 | 0.6 | 3.0 | 4.0 |
| m_mt_361718476 | 1744466400 | COMPETITION | HOME | OPP_005 | BACK_FOUR | BACK_FOUR | 8.0 | 5.0 | 7.0 | 2.0 | 5.0 | 3.0 | 14.0 | 26.0 | 3.0 | 6.0 | 59.0 | 42.0 | 9.0 | 11.0 | 2.0 | 2.0 | 7.0 | 5.0 | 2.33 | 1.51 | 1.0 | 1.0 | 59.0 | 41.0 | 0.0 | 0.0 | 4.0 | 5.0 | 15.0 | 11.0 | 9.0 | 6.0 | 7.0 | 6.0 | 6.0 | 4.0 | 15.0 | 13.0 | 12.0 | 18.0 | 21.0 | 15.0 | 47.0 | 24.0 | 3.91 | 1.5 | 2.0 | 5.0 |
| m_mt_745359695 | 1745071200 | COMPETITION | AWAY | OPP_008 |  |  | 7.0 | 8.0 | 2.0 | 6.0 | 3.0 | 3.0 | 27.0 | 23.0 | 7.0 | 4.0 | 56.0 | 58.0 | 11.0 | 7.0 | 2.0 | 4.0 | 9.0 | 9.0 | 1.42 | 2.26 | 0.0 | 1.0 | 54.0 | 46.0 | 1.0 | 0.0 | 4.0 | 1.0 | 7.0 | 14.0 | 6.0 | 5.0 | 3.0 | 8.0 | 5.0 | 2.0 | 18.0 | 20.0 | 19.0 | 22.0 | 12.0 | 16.0 | 32.0 | 36.0 | 1.43 | 2.17 | 3.0 | 3.0 |
| m_mt_629493593 | 1745676000 | COMPETITION | HOME | OPP_007 |  |  | 6.0 | 2.0 | 2.0 | 2.0 | 5.0 | 4.0 | 20.0 | 41.0 | 8.0 | 1.0 | 60.0 | 53.0 | 7.0 | 9.0 | 3.0 | 2.0 | 3.0 | 7.0 | 1.31 | 1.27 | 4.0 | 3.0 | 53.0 | 47.0 | 0.0 | 0.0 | 2.0 | 6.0 | 7.0 | 8.0 | 2.0 | 4.0 | 9.0 | 4.0 | 9.0 | 4.0 | 24.0 | 9.0 | 14.0 | 21.0 | 16.0 | 12.0 | 36.0 | 26.0 | 1.35 | 1.25 | 1.0 | 1.0 |
| m_mt_361718244 | 1746363600 | COMPETITION | HOME | OPP_016 |  |  | 2.0 | 3.0 | 1.0 | 1.0 | 1.0 | 4.0 | 26.0 | 28.0 | 1.0 | 4.0 | 53.0 | 50.0 | 15.0 | 10.0 | 1.0 | 1.0 | 10.0 | 6.0 | 0.69 | 1.08 | 1.0 | 1.0 | 46.0 | 54.0 | 0.0 | 0.0 | 4.0 | 1.0 | 4.0 | 7.0 | 2.0 | 4.0 | 2.0 | 5.0 | 1.0 | 6.0 | 15.0 | 14.0 | 14.0 | 23.0 | 5.0 | 13.0 | 18.0 | 32.0 | 0.69 | 1.87 | 2.0 | 1.0 |
| m_mt_257076130 | 1746885600 | COMPETITION | AWAY | OPP_017 | BACK_FOUR | BACK_THREE | 4.0 | 4.0 | 2.0 | 1.0 | 1.0 | 2.0 | 30.0 | 26.0 | 4.0 | 7.0 | 45.0 | 51.0 | 12.0 | 8.0 | 2.0 | 0.0 | 11.0 | 9.0 | 0.78 | 0.91 | 1.0 | 0.0 | 44.0 | 56.0 | 0.0 | 0.0 | 4.0 | 0.0 | 3.0 | 8.0 | 4.0 | 5.0 | 2.0 | 3.0 | 4.0 | 2.0 | 25.0 | 17.0 | 14.0 | 20.0 | 7.0 | 10.0 | 15.0 | 25.0 | 1.57 | 0.91 | 1.0 | 1.0 |
| m_mt_196560835 | 1747681200 | COMPETITION | HOME | OPP_018 |  |  | 5.0 | 1.0 | 2.0 | 3.0 | 4.0 | 7.0 | 14.0 | 24.0 | 3.0 | 3.0 | 46.0 | 36.0 | 9.0 | 8.0 | 3.0 | 2.0 | 7.0 | 8.0 | 2.23 | 2.23 | 2.0 | 1.0 | 49.0 | 51.0 | 0.0 | 0.0 | 3.0 | 9.0 | 17.0 | 12.0 | 9.0 | 6.0 | 12.0 | 5.0 | 8.0 | 6.0 | 27.0 | 9.0 | 17.0 | 15.0 | 25.0 | 18.0 | 60.0 | 45.0 | 2.2 | 2.23 | 1.0 | 0.0 |
| m_mt_361718222 | 1748185200 | COMPETITION | AWAY | OPP_019 |  |  | 12.0 | 0.0 | 5.0 | 3.0 | 8.0 | 1.0 | 7.0 | 39.0 | 11.0 | 2.0 | 67.0 | 26.0 | 8.0 | 13.0 | 4.0 | 1.0 | 7.0 | 11.0 | 1.45 | 1.25 | 2.0 | 1.0 | 67.0 | 33.0 | 0.0 | 0.0 | 1.0 | 4.0 | 18.0 | 4.0 | 7.0 | 1.0 | 8.0 | 2.0 | 5.0 | 0.0 | 18.0 | 13.0 | 10.0 | 21.0 | 23.0 | 4.0 | 47.0 | 10.0 | 2.24 | 2.03 | 1.0 | 3.0 |
| m_mt_191506756 | 1755352800 | COMPETITION | HOME | OPP_004 |  |  | 4.0 | 3.0 | 2.0 | 1.0 | 1.0 | 1.0 | 27.0 | 15.0 | 4.0 | 3.0 | 47.0 | 49.0 | 16.0 | 15.0 | 1.0 | 1.0 | 9.0 | 2.0 | 0.69 | 0.79 | 3.0 | 2.0 | 50.0 | 50.0 | 0.0 | 0.0 | 1.0 | 3.0 | 6.0 | 5.0 | 5.0 | 4.0 | 4.0 | 2.0 | 4.0 | 2.0 | 19.0 | 15.0 | 10.0 | 20.0 | 10.0 | 7.0 | 25.0 | 19.0 | 1.48 | 0.76 | 3.0 | 3.0 |
| m_mt_363781453 | 1756040400 | COMPETITION | AWAY | OPP_013 | BACK_FOUR | BACK_FOUR | 3.0 | 4.0 | 3.0 | 2.0 | 4.0 | 1.0 | 24.0 | 35.0 | 2.0 | 2.0 | 58.0 | 73.0 | 15.0 | 7.0 | 0.0 | 2.0 | 5.0 | 8.0 | 1.65 | 1.59 | 6.0 | 0.0 | 58.0 | 42.0 | 0.0 | 0.0 | 1.0 | 4.0 | 7.0 | 6.0 | 5.0 | 7.0 | 4.0 | 3.0 | 6.0 | 5.0 | 17.0 | 15.0 | 27.0 | 19.0 | 13.0 | 11.0 | 29.0 | 18.0 | 2.43 | 1.6 | 3.0 | 4.0 |

### Arm B — AWAY_TEAM match-level matrix (30 rows × 55 cols)

Columns: `match_alias, kickoff_unix, competition, venue, opponent_alias, own_formation_family, opponent_formation_family, accurate_crosses_for, accurate_crosses_against, big_chances_for, big_chances_against, blocked_shots_for, blocked_shots_against, clearances_for, clearances_against, corners_for, corners_against, final_third_entries_for, final_third_entries_against, fouls_for, fouls_against, goals_for, goals_against, interceptions_for, interceptions_against, npxg_for, npxg_against, offsides_for, offsides_against, possession_for, possession_against, red_cards_for, red_cards_against, saves_for, saves_against, shots_inside_box_for, shots_inside_box_against, shots_off_target_for, shots_off_target_against, shots_on_target_for, shots_on_target_against, shots_outside_box_for, shots_outside_box_against, tackles_for, tackles_against, throw_ins_for, throw_ins_against, total_shots_for, total_shots_against, touches_in_box_for, touches_in_box_against, xg_for, xg_against, yellow_cards_for, yellow_cards_against`

| match_alias | kickoff_unix | competition | venue | opponent_alias | own_formation_family | opponent_formation_family | accurate_crosses_for | accurate_crosses_against | big_chances_for | big_chances_against | blocked_shots_for | blocked_shots_against | clearances_for | clearances_against | corners_for | corners_against | final_third_entries_for | final_third_entries_against | fouls_for | fouls_against | goals_for | goals_against | interceptions_for | interceptions_against | npxg_for | npxg_against | offsides_for | offsides_against | possession_for | possession_against | red_cards_for | red_cards_against | saves_for | saves_against | shots_inside_box_for | shots_inside_box_against | shots_off_target_for | shots_off_target_against | shots_on_target_for | shots_on_target_against | shots_outside_box_for | shots_outside_box_against | tackles_for | tackles_against | throw_ins_for | throw_ins_against | total_shots_for | total_shots_against | touches_in_box_for | touches_in_box_against | xg_for | xg_against | yellow_cards_for | yellow_cards_against |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| m_mt_972822643 | 1731173400 | COMPETITION | AWAY | OPP_020 |  |  | 4.0 | 4.0 | 5.0 | 8.0 | 3.0 | 2.0 | 8.0 | 21.0 | 4.0 | 0.0 | 61.0 | 34.0 | 10.0 | 12.0 | 1.0 | 2.0 | 4.0 | 12.0 | 2.63 | 2.29 | 1.0 | 3.0 | 60.0 | 40.0 | 0.0 | 0.0 | 2.0 | 5.0 | 12.0 | 8.0 | 6.0 | 4.0 | 6.0 | 4.0 | 3.0 | 2.0 | 12.0 | 16.0 | 18.0 | 12.0 | 15.0 | 10.0 | 28.0 | 20.0 | 2.22 | 2.29 | 3.0 | 3.0 |
| m_mt_745359014 | 1732383000 | COMPETITION | HOME | OPP_019 |  |  | 7.0 | 3.0 | 4.0 | 6.0 | 7.0 | 0.0 | 13.0 | 26.0 | 9.0 | 3.0 | 61.0 | 26.0 | 19.0 | 9.0 | 0.0 | 4.0 | 9.0 | 5.0 | 2.15 | 2.51 | 2.0 | 3.0 | 58.0 | 42.0 | 0.0 | 0.0 | 3.0 | 5.0 | 17.0 | 7.0 | 11.0 | 2.0 | 5.0 | 7.0 | 6.0 | 2.0 | 13.0 | 13.0 | 16.0 | 9.0 | 23.0 | 9.0 | 43.0 | 17.0 | 2.14 | 2.51 | 4.0 | 2.0 |
| m_mt_013234975 | 1733068800 | COMPETITION | AWAY | OPP_018 |  |  | 0.0 | 4.0 | 1.0 | 5.0 | 3.0 | 4.0 | 21.0 | 13.0 | 4.0 | 7.0 | 48.0 | 40.0 | 8.0 | 9.0 | 0.0 | 2.0 | 5.0 | 6.0 | 0.84 | 2.78 | 3.0 | 4.0 | 56.0 | 44.0 | 0.0 | 0.0 | 5.0 | 3.0 | 7.0 | 11.0 | 3.0 | 7.0 | 2.0 | 7.0 | 1.0 | 7.0 | 17.0 | 22.0 | 13.0 | 21.0 | 8.0 | 18.0 | 30.0 | 30.0 | 0.84 | 3.57 | 3.0 | 1.0 |
| m_mt_972822733 | 1733340600 | COMPETITION | HOME | OPP_014 |  |  | 6.0 | 3.0 | 4.0 | 1.0 | 3.0 | 2.0 | 15.0 | 18.0 | 8.0 | 2.0 | 52.0 | 39.0 | 7.0 | 15.0 | 3.0 | 0.0 | 5.0 | 14.0 | 2.41 | 1.04 | 1.0 | 2.0 | 67.0 | 33.0 | 0.0 | 0.0 | 3.0 | 3.0 | 12.0 | 8.0 | 7.0 | 7.0 | 7.0 | 3.0 | 5.0 | 4.0 | 16.0 | 24.0 | 16.0 | 14.0 | 17.0 | 12.0 | 42.0 | 14.0 | 2.41 | 1.04 | 2.0 | 4.0 |
| m_mt_408687860 | 1733583600 | COMPETITION | AWAY | OPP_006 |  |  | 5.0 | 3.0 | 3.0 | 1.0 | 4.0 | 8.0 | 16.0 | 23.0 | 8.0 | 6.0 | 65.0 | 41.0 | 10.0 | 4.0 | 2.0 | 2.0 | 7.0 | 6.0 | 1.45 | 1.34 | 2.0 | 3.0 | 68.0 | 32.0 | 1.0 | 0.0 | 1.0 | 2.0 | 9.0 | 6.0 | 4.0 | 1.0 | 4.0 | 3.0 | 3.0 | 6.0 | 14.0 | 18.0 | 17.0 | 14.0 | 12.0 | 12.0 | 34.0 | 15.0 | 1.45 | 1.34 | 2.0 | 1.0 |
| m_mt_257076702 | 1734280200 | COMPETITION | HOME | OPP_012 | BACK_FOUR | BACK_THREE | 2.0 | 4.0 | 0.0 | 3.0 | 3.0 | 3.0 | 10.0 | 18.0 | 8.0 | 2.0 | 63.0 | 39.0 | 5.0 | 14.0 | 1.0 | 2.0 | 10.0 | 17.0 | 0.95 | 1.29 | 0.0 | 6.0 | 52.0 | 48.0 | 0.0 | 0.0 | 1.0 | 2.0 | 5.0 | 7.0 | 4.0 | 4.0 | 3.0 | 3.0 | 5.0 | 3.0 | 14.0 | 24.0 | 19.0 | 11.0 | 10.0 | 10.0 | 18.0 | 22.0 | 0.95 | 2.08 | 1.0 | 1.0 |
| m_mt_584142427 | 1734784200 | COMPETITION | AWAY | OPP_009 |  |  | 2.0 | 2.0 | 2.0 | 4.0 | 1.0 | 2.0 | 15.0 | 17.0 | 4.0 | 5.0 | 64.0 | 33.0 | 7.0 | 14.0 | 1.0 | 2.0 | 5.0 | 4.0 | 1.03 | 1.67 | 0.0 | 3.0 | 56.0 | 44.0 | 0.0 | 0.0 | 4.0 | 5.0 | 7.0 | 10.0 | 5.0 | 3.0 | 6.0 | 6.0 | 5.0 | 1.0 | 6.0 | 22.0 | 10.0 | 13.0 | 12.0 | 11.0 | 22.0 | 17.0 | 1.03 | 1.67 | 3.0 | 3.0 |
| m_mt_257076715 | 1735216200 | COMPETITION | HOME | OPP_013 |  |  | 10.0 | 6.0 | 4.0 | 1.0 | 10.0 | 2.0 | 11.0 | 35.0 | 8.0 | 5.0 | 73.0 | 55.0 | 5.0 | 10.0 | 1.0 | 1.0 | 1.0 | 7.0 | 1.55 | 0.67 | 2.0 | 2.0 | 66.0 | 34.0 | 0.0 | 0.0 | 2.0 | 4.0 | 16.0 | 5.0 | 9.0 | 3.0 | 5.0 | 3.0 | 8.0 | 3.0 | 16.0 | 17.0 | 15.0 | 11.0 | 24.0 | 8.0 | 50.0 | 15.0 | 2.09 | 0.63 | 1.0 | 4.0 |
| m_mt_972821464 | 1735482600 | COMPETITION | AWAY | OPP_005 |  |  | 5.0 | 5.0 | 2.0 | 3.0 | 3.0 | 2.0 | 16.0 | 10.0 | 4.0 | 4.0 | 45.0 | 53.0 | 6.0 | 11.0 | 2.0 | 0.0 | 5.0 | 9.0 | 1.27 | 1.26 | 2.0 | 3.0 | 46.0 | 54.0 | 0.0 | 0.0 | 3.0 | 3.0 | 8.0 | 10.0 | 6.0 | 5.0 | 5.0 | 4.0 | 6.0 | 1.0 | 10.0 | 14.0 | 19.0 | 14.0 | 14.0 | 11.0 | 26.0 | 26.0 | 1.27 | 1.3 | 1.0 | 2.0 |
| m_mt_830905643 | 1736002800 | COMPETITION | HOME | OPP_007 |  |  | 1.0 | 7.0 | 3.0 | 3.0 | 3.0 | 3.0 | 17.0 | 17.0 | 7.0 | 1.0 | 42.0 | 37.0 | 8.0 | 13.0 | 4.0 | 1.0 | 6.0 | 7.0 | 1.91 | 1.37 | 1.0 | 2.0 | 56.0 | 44.0 | 0.0 | 0.0 | 3.0 | 4.0 | 7.0 | 14.0 | 0.0 | 10.0 | 7.0 | 4.0 | 3.0 | 3.0 | 12.0 | 13.0 | 13.0 | 16.0 | 10.0 | 17.0 | 28.0 | 23.0 | 1.91 | 1.37 | 2.0 | 1.0 |
| m_mt_629493922 | 1736883000 | COMPETITION | AWAY | OPP_008 |  |  | 7.0 | 5.0 | 5.0 | 4.0 | 2.0 | 3.0 | 30.0 | 20.0 | 5.0 | 4.0 | 37.0 | 53.0 | 4.0 | 4.0 | 2.0 | 2.0 | 9.0 | 9.0 | 2.21 | 2.58 | 0.0 | 4.0 | 55.0 | 45.0 | 0.0 | 0.0 | 3.0 | 6.0 | 15.0 | 16.0 | 11.0 | 9.0 | 8.0 | 6.0 | 6.0 | 2.0 | 12.0 | 10.0 | 15.0 | 14.0 | 21.0 | 18.0 | 45.0 | 41.0 | 2.2 | 2.58 |  |  |
| m_mt_745359545 | 1737304200 | COMPETITION | AWAY | OPP_011 |  |  | 0.0 | 3.0 | 5.0 | 1.0 | 5.0 | 3.0 | 12.0 | 21.0 | 7.0 | 4.0 | 63.0 | 38.0 | 7.0 | 4.0 | 6.0 | 0.0 | 7.0 | 8.0 | 3.06 | 0.51 | 1.0 | 1.0 | 67.0 | 33.0 | 0.0 | 0.0 | 4.0 | 3.0 | 14.0 | 5.0 | 3.0 | 1.0 | 9.0 | 4.0 | 3.0 | 3.0 | 14.0 | 13.0 | 11.0 | 8.0 | 17.0 | 8.0 | 40.0 | 14.0 | 2.84 | 0.65 | 1.0 | 0.0 |
| m_mt_584144867 | 1737826200 | COMPETITION | HOME | OPP_015 |  |  | 2.0 | 0.0 | 7.0 | 3.0 | 3.0 | 3.0 | 15.0 | 12.0 | 2.0 | 3.0 | 41.0 | 37.0 | 6.0 | 8.0 | 3.0 | 1.0 | 6.0 | 4.0 | 2.5 | 1.8 | 5.0 | 2.0 | 57.0 | 43.0 | 0.0 | 0.0 | 3.0 | 3.0 | 9.0 | 7.0 | 6.0 | 3.0 | 6.0 | 4.0 | 6.0 | 3.0 | 13.0 | 12.0 | 20.0 | 28.0 | 15.0 | 10.0 | 26.0 | 23.0 | 2.5 | 1.8 | 3.0 | 2.0 |
| m_mt_584144878 | 1738513800 | COMPETITION | AWAY | OPP_010 | BACK_FOUR | BACK_FOUR | 3.0 | 1.0 | 1.0 | 2.0 | 0.0 | 3.0 | 21.0 | 21.0 | 2.0 | 5.0 | 43.0 | 39.0 | 7.0 | 6.0 | 1.0 | 5.0 | 6.0 | 6.0 | 0.81 | 1.0 | 1.0 | 3.0 | 54.0 | 46.0 | 0.0 | 0.0 | 2.0 | 3.0 | 5.0 | 8.0 | 3.0 | 2.0 | 4.0 | 7.0 | 2.0 | 4.0 | 13.0 | 13.0 | 14.0 | 14.0 | 7.0 | 12.0 | 15.0 | 17.0 | 0.81 | 1.04 | 0.0 | 2.0 |
| m_mt_830900304 | 1739631600 | COMPETITION | HOME | OPP_016 |  |  | 7.0 | 3.0 | 4.0 | 0.0 | 2.0 | 1.0 | 19.0 | 20.0 | 7.0 | 4.0 | 60.0 | 29.0 | 5.0 | 13.0 | 4.0 | 0.0 | 6.0 | 7.0 | 1.9 | 0.48 | 0.0 | 3.0 | 62.0 | 38.0 | 0.0 | 0.0 | 1.0 | 3.0 | 7.0 | 3.0 | 2.0 | 1.0 | 7.0 | 1.0 | 4.0 | 0.0 | 10.0 | 26.0 | 13.0 | 15.0 | 11.0 | 3.0 | 24.0 | 10.0 | 1.9 | 0.48 | 0.0 | 1.0 |
| m_mt_361718418 | 1740328200 | COMPETITION | HOME | OPP_018 |  |  | 3.0 | 2.0 | 0.0 | 1.0 | 8.0 | 2.0 | 17.0 | 34.0 | 7.0 | 5.0 | 75.0 | 26.0 | 3.0 | 10.0 | 0.0 | 2.0 | 3.0 | 4.0 | 0.65 | 0.71 | 2.0 | 4.0 | 66.0 | 34.0 | 0.0 | 0.0 | 2.0 | 5.0 | 6.0 | 6.0 | 3.0 | 2.0 | 5.0 | 4.0 | 10.0 | 2.0 | 5.0 | 22.0 | 20.0 | 6.0 | 16.0 | 8.0 | 40.0 | 27.0 | 0.65 | 0.71 |  |  |
| m_mt_408688045 | 1740598200 | COMPETITION | AWAY | OPP_019 |  |  | 2.0 | 8.0 | 4.0 | 2.0 | 5.0 | 2.0 | 17.0 | 15.0 | 3.0 | 8.0 | 40.0 | 48.0 | 15.0 | 12.0 | 1.0 | 0.0 | 10.0 | 7.0 | 2.12 | 1.33 | 2.0 | 0.0 | 44.0 | 56.0 | 0.0 | 0.0 | 6.0 | 4.0 | 8.0 | 11.0 | 2.0 | 3.0 | 5.0 | 6.0 | 4.0 | 0.0 | 20.0 | 26.0 | 18.0 | 19.0 | 12.0 | 11.0 | 29.0 | 27.0 | 2.12 | 1.33 | 0.0 | 3.0 |
| m_mt_361711762 | 1741437000 | COMPETITION | AWAY | OPP_014 |  |  | 1.0 | 7.0 |  |  | 3.0 | 2.0 | 19.0 | 25.0 | 2.0 | 3.0 | 56.0 | 50.0 | 7.0 | 9.0 | 0.0 | 1.0 | 5.0 | 5.0 | 0.86 | 0.73 | 1.0 | 1.0 | 69.0 | 31.0 | 0.0 | 0.0 | 3.0 | 3.0 | 6.0 | 6.0 | 8.0 | 3.0 | 3.0 | 4.0 | 8.0 | 3.0 | 18.0 | 17.0 | 17.0 | 15.0 | 14.0 | 9.0 | 24.0 | 18.0 | 0.86 | 0.73 | 2.0 | 3.0 |
| m_mt_745355352 | 1742050800 | COMPETITION | HOME | OPP_020 |  |  | 5.0 | 7.0 | 4.0 | 6.0 | 1.0 | 2.0 | 27.0 | 27.0 | 4.0 | 5.0 | 46.0 | 36.0 | 10.0 | 10.0 | 2.0 | 2.0 | 4.0 | 10.0 | 0.95 | 2.04 | 1.0 | 1.0 | 60.0 | 40.0 | 0.0 | 0.0 | 2.0 | 1.0 | 8.0 | 12.0 | 7.0 | 10.0 | 3.0 | 3.0 | 3.0 | 3.0 | 17.0 | 27.0 | 15.0 | 22.0 | 11.0 | 15.0 | 35.0 | 27.0 | 1.72 | 2.04 | 2.0 | 5.0 |
| m_mt_013234585 | 1743619500 | COMPETITION | HOME | OPP_005 |  |  | 3.0 | 1.0 | 2.0 | 0.0 | 8.0 | 0.0 | 16.0 | 26.0 | 5.0 | 0.0 | 76.0 | 26.0 | 11.0 | 8.0 | 2.0 | 0.0 | 3.0 | 6.0 | 2.24 | 0.07 | 2.0 | 1.0 | 72.0 | 28.0 | 0.0 | 0.0 | 0.0 | 3.0 | 11.0 | 1.0 | 5.0 | 2.0 | 5.0 | 0.0 | 7.0 | 1.0 | 9.0 | 19.0 | 10.0 | 9.0 | 18.0 | 2.0 | 46.0 | 4.0 | 2.24 | 0.07 | 1.0 | 4.0 |
| m_mt_972821374 | 1743953400 | COMPETITION | AWAY | OPP_012 |  |  | 0.0 | 4.0 | 1.0 | 0.0 | 1.0 | 6.0 | 21.0 | 18.0 | 3.0 | 5.0 | 69.0 | 35.0 | 9.0 | 13.0 | 0.0 | 0.0 | 8.0 | 15.0 | 0.49 | 0.93 | 2.0 | 1.0 | 59.0 | 41.0 | 0.0 | 0.0 | 2.0 | 6.0 | 4.0 | 8.0 | 3.0 | 5.0 | 5.0 | 2.0 | 5.0 | 5.0 | 21.0 | 32.0 | 18.0 | 17.0 | 9.0 | 13.0 | 15.0 | 29.0 | 0.49 | 0.91 | 2.0 | 3.0 |
| m_mt_196560856 | 1744457400 | COMPETITION | HOME | OPP_006 | BACK_FOUR | BACK_THREE | 2.0 | 4.0 | 12.0 | 3.0 | 5.0 | 0.0 | 11.0 | 23.0 | 1.0 | 4.0 | 68.0 | 18.0 | 10.0 | 16.0 | 5.0 | 2.0 | 7.0 | 13.0 | 4.02 | 1.82 | 1.0 | 3.0 | 68.0 | 32.0 | 0.0 | 0.0 | 1.0 | 3.0 | 16.0 | 6.0 | 7.0 | 5.0 | 9.0 | 3.0 | 5.0 | 2.0 | 10.0 | 12.0 | 11.0 | 15.0 | 21.0 | 8.0 | 32.0 | 10.0 | 3.81 | 1.82 | 2.0 | 3.0 |
| m_mt_830905700 | 1745071200 | COMPETITION | AWAY | OPP_013 |  |  | 3.0 | 6.0 | 3.0 | 1.0 | 2.0 | 3.0 | 22.0 | 23.0 | 5.0 | 2.0 | 73.0 | 46.0 | 6.0 | 7.0 | 2.0 | 0.0 | 5.0 | 13.0 | 2.04 | 0.91 | 0.0 | 5.0 | 67.0 | 33.0 | 0.0 | 0.0 | 2.0 | 4.0 | 8.0 | 7.0 | 3.0 | 2.0 | 7.0 | 3.0 | 4.0 | 1.0 | 7.0 | 19.0 | 16.0 | 13.0 | 12.0 | 8.0 | 25.0 | 21.0 | 2.04 | 0.91 | 0.0 | 4.0 |
| m_mt_257076883 | 1745348400 | COMPETITION | HOME | OPP_009 |  |  | 9.0 | 2.0 | 2.0 | 4.0 | 2.0 | 1.0 | 15.0 | 23.0 | 10.0 | 2.0 | 62.0 | 33.0 | 9.0 | 10.0 | 2.0 | 1.0 | 5.0 | 3.0 | 1.33 | 0.97 | 2.0 | 2.0 | 62.0 | 38.0 | 0.0 | 0.0 | 2.0 | 4.0 | 10.0 | 6.0 | 6.0 | 3.0 | 6.0 | 3.0 | 4.0 | 1.0 | 12.0 | 16.0 | 15.0 | 16.0 | 14.0 | 7.0 | 24.0 | 23.0 | 1.09 | 1.68 | 3.0 | 3.0 |
| m_mt_972821437 | 1746212400 | COMPETITION | HOME | OPP_017 |  |  | 3.0 | 2.0 | 1.0 | 2.0 | 2.0 | 1.0 | 15.0 | 19.0 | 4.0 | 5.0 | 74.0 | 25.0 | 7.0 | 11.0 | 1.0 | 0.0 | 6.0 | 6.0 | 0.71 | 0.43 | 0.0 | 1.0 | 64.0 | 36.0 | 0.0 | 0.0 | 0.0 | 1.0 | 5.0 | 4.0 | 5.0 | 4.0 | 2.0 | 1.0 | 4.0 | 2.0 | 19.0 | 29.0 | 21.0 | 19.0 | 9.0 | 6.0 | 40.0 | 15.0 | 0.65 | 0.44 |  |  |
| m_mt_408687141 | 1746885600 | COMPETITION | AWAY | OPP_003 | BACK_FOUR | BACK_THREE | 10.0 | 1.0 |  |  | 13.0 | 2.0 | 8.0 | 52.0 | 15.0 | 1.0 | 64.0 | 37.0 | 8.0 | 9.0 | 0.0 | 0.0 | 3.0 | 11.0 | 1.82 | 0.1 | 1.0 | 2.0 | 72.0 | 28.0 | 0.0 | 0.0 | 0.0 | 4.0 | 14.0 | 2.0 | 8.0 | 0.0 | 5.0 | 0.0 | 12.0 | 0.0 | 12.0 | 13.0 | 20.0 | 8.0 | 26.0 | 2.0 | 76.0 | 7.0 | 1.82 | 0.1 | 0.0 | 2.0 |
| m_mt_838200836 | 1747767600 | COMPETITION | HOME | OPP_002 |  |  | 2.0 | 6.0 | 3.0 | 2.0 | 2.0 | 2.0 | 19.0 | 25.0 | 3.0 | 1.0 | 56.0 | 57.0 | 7.0 | 13.0 | 3.0 | 1.0 | 7.0 | 5.0 | 1.54 | 1.12 | 2.0 | 3.0 | 57.0 | 43.0 | 1.0 | 1.0 | 1.0 | 2.0 | 5.0 | 6.0 | 5.0 | 4.0 | 5.0 | 2.0 | 7.0 | 2.0 | 8.0 | 10.0 | 15.0 | 14.0 | 12.0 | 8.0 | 21.0 | 17.0 | 1.54 | 1.12 | 1.0 | 3.0 |
| m_mt_745359007 | 1748185200 | COMPETITION | AWAY | OPP_004 |  |  | 3.0 | 5.0 | 3.0 | 4.0 | 8.0 | 4.0 | 14.0 | 29.0 | 6.0 | 1.0 | 57.0 | 43.0 | 5.0 | 11.0 | 2.0 | 0.0 | 13.0 | 11.0 | 2.34 | 1.31 | 0.0 | 2.0 | 53.0 | 47.0 | 0.0 | 0.0 | 3.0 | 3.0 | 16.0 | 11.0 | 7.0 | 6.0 | 5.0 | 3.0 | 4.0 | 2.0 | 14.0 | 18.0 | 17.0 | 16.0 | 20.0 | 13.0 | 46.0 | 32.0 | 2.99 | 1.28 |  |  |
| m_mt_191506771 | 1755361800 | COMPETITION | AWAY | OPP_017 |  |  | 6.0 | 4.0 | 3.0 | 0.0 | 4.0 | 3.0 | 22.0 | 20.0 | 5.0 | 4.0 | 48.0 | 46.0 | 7.0 | 13.0 | 4.0 | 0.0 | 7.0 | 6.0 | 2.47 | 0.56 | 0.0 | 4.0 | 58.0 | 42.0 | 0.0 | 0.0 | 3.0 | 0.0 | 8.0 | 6.0 | 7.0 | 3.0 | 4.0 | 3.0 | 7.0 | 3.0 | 18.0 | 25.0 | 17.0 | 24.0 | 15.0 | 9.0 | 28.0 | 19.0 | 2.47 | 0.56 | 2.0 | 1.0 |
| m_mt_585124974 | 1755948600 | COMPETITION | HOME | OPP_019 | BACK_FOUR | BACK_FOUR | 5.0 | 4.0 | 2.0 | 3.0 | 3.0 | 2.0 | 23.0 | 25.0 | 7.0 | 2.0 | 47.0 | 50.0 | 7.0 | 12.0 | 0.0 | 2.0 | 6.0 | 7.0 | 1.55 | 1.12 | 0.0 | 1.0 | 61.0 | 39.0 | 0.0 | 0.0 | 3.0 | 4.0 | 6.0 | 10.0 | 3.0 | 5.0 | 4.0 | 5.0 | 4.0 | 2.0 | 20.0 | 24.0 | 23.0 | 21.0 | 10.0 | 12.0 | 34.0 | 26.0 | 1.55 | 1.11 | 1.0 | 4.0 |

### Arm B — derived summaries (DERIVED_SUMMARY), HOME 240 + AWAY 240

HOME_TEAM (metric·side·window·venue = value [n, reliability]):

- accurate_crosses·FOR·ALL_PRIOR·ALL = 4.8333 [n=30, HIGH]
- accurate_crosses·FOR·W5·ALL = 5.6 [n=5, LOW]
- accurate_crosses·FOR·W10·ALL = 5.5 [n=10, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·HOME = 4.8 [n=15, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·AWAY = 4.8667 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·ALL = 3.2333 [n=30, HIGH]
- accurate_crosses·AGAINST·W5·ALL = 2.4 [n=5, LOW]
- accurate_crosses·AGAINST·W10·ALL = 3.1 [n=10, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·HOME = 3.0 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·AWAY = 3.4667 [n=15, MEDIUM]
- big_chances·FOR·ALL_PRIOR·ALL = 3.069 [n=29, HIGH]
- big_chances·FOR·W5·ALL = 2.8 [n=5, LOW]
- big_chances·FOR·W10·ALL = 2.8 [n=10, MEDIUM]
- big_chances·FOR·ALL_PRIOR·HOME = 2.8667 [n=15, MEDIUM]
- big_chances·FOR·ALL_PRIOR·AWAY = 3.2857 [n=14, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·ALL = 2.3793 [n=29, HIGH]
- big_chances·AGAINST·W5·ALL = 2.0 [n=5, LOW]
- big_chances·AGAINST·W10·ALL = 2.1 [n=10, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·HOME = 2.2 [n=15, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·AWAY = 2.5714 [n=14, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·ALL = 3.5333 [n=30, HIGH]
- blocked_shots·FOR·W5·ALL = 3.6 [n=5, LOW]
- blocked_shots·FOR·W10·ALL = 3.5 [n=10, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·HOME = 3.6 [n=15, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·AWAY = 3.4667 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·ALL = 3.0667 [n=30, HIGH]
- blocked_shots·AGAINST·W5·ALL = 2.4 [n=5, LOW]
- blocked_shots·AGAINST·W10·ALL = 3.0 [n=10, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·HOME = 3.2 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·AWAY = 2.9333 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·ALL = 20.9667 [n=30, HIGH]
- clearances·FOR·W5·ALL = 20.4 [n=5, LOW]
- clearances·FOR·W10·ALL = 21.0 [n=10, MEDIUM]
- clearances·FOR·ALL_PRIOR·HOME = 20.3333 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·AWAY = 21.6 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·ALL = 26.1333 [n=30, HIGH]
- clearances·AGAINST·W5·ALL = 27.8 [n=5, LOW]
- clearances·AGAINST·W10·ALL = 29.0 [n=10, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·HOME = 27.0 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·AWAY = 25.2667 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·ALL = 4.4667 [n=30, HIGH]
- corners·FOR·W5·ALL = 4.8 [n=5, LOW]
- corners·FOR·W10·ALL = 4.7 [n=10, MEDIUM]
- corners·FOR·ALL_PRIOR·HOME = 4.0 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·AWAY = 4.9333 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·ALL = 4.5667 [n=30, HIGH]
- corners·AGAINST·W5·ALL = 3.4 [n=5, LOW]
- corners·AGAINST·W10·ALL = 3.4 [n=10, MEDIUM]
- corners·AGAINST·ALL_PRIOR·HOME = 4.4 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·AWAY = 4.7333 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·ALL = 53.0333 [n=30, HIGH]
- final_third_entries·FOR·W5·ALL = 52.6 [n=5, LOW]
- final_third_entries·FOR·W10·ALL = 56.9 [n=10, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·HOME = 53.6 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·AWAY = 52.4667 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·ALL = 47.6 [n=30, HIGH]
- final_third_entries·AGAINST·W5·ALL = 47.0 [n=5, LOW]
- final_third_entries·AGAINST·W10·ALL = 47.9 [n=10, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·HOME = 47.1333 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·AWAY = 48.0667 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·ALL = 11.9333 [n=30, HIGH]
- fouls·FOR·W5·ALL = 12.0 [n=5, LOW]
- fouls·FOR·W10·ALL = 11.5 [n=10, MEDIUM]
- fouls·FOR·ALL_PRIOR·HOME = 11.7333 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·AWAY = 12.1333 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·ALL = 11.2333 [n=30, HIGH]
- fouls·AGAINST·W5·ALL = 10.2 [n=5, LOW]
- fouls·AGAINST·W10·ALL = 10.0 [n=10, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·HOME = 12.2 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·AWAY = 10.2667 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·ALL = 1.6667 [n=30, HIGH]
- goals·FOR·W5·ALL = 2.0 [n=5, LOW]
- goals·FOR·W10·ALL = 1.9 [n=10, MEDIUM]
- goals·FOR·ALL_PRIOR·HOME = 1.4667 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·AWAY = 1.8667 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·ALL = 1.6 [n=30, HIGH]
- goals·AGAINST·W5·ALL = 1.2 [n=5, LOW]
- goals·AGAINST·W10·ALL = 1.7 [n=10, MEDIUM]
- goals·AGAINST·ALL_PRIOR·HOME = 1.3333 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·AWAY = 1.8667 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·ALL = 8.0 [n=30, HIGH]
- interceptions·FOR·W5·ALL = 7.8 [n=5, LOW]
- interceptions·FOR·W10·ALL = 7.4 [n=10, MEDIUM]
- interceptions·FOR·ALL_PRIOR·HOME = 8.0667 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·AWAY = 7.9333 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·ALL = 7.5 [n=30, HIGH]
- interceptions·AGAINST·W5·ALL = 7.6 [n=5, LOW]
- interceptions·AGAINST·W10·ALL = 7.4 [n=10, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·HOME = 6.7333 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·AWAY = 8.2667 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·ALL = 1.3937 [n=30, HIGH]
- npxg·FOR·W5·ALL = 1.36 [n=5, LOW]
- npxg·FOR·W10·ALL = 1.355 [n=10, MEDIUM]
- npxg·FOR·ALL_PRIOR·HOME = 1.3113 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·AWAY = 1.476 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·ALL = 1.2177 [n=30, HIGH]
- npxg·AGAINST·W5·ALL = 1.354 [n=5, LOW]
- npxg·AGAINST·W10·ALL = 1.346 [n=10, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·HOME = 1.2647 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·AWAY = 1.1707 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·ALL = 1.5333 [n=30, HIGH]
- offsides·FOR·W5·ALL = 2.8 [n=5, LOW]
- offsides·FOR·W10·ALL = 2.1 [n=10, MEDIUM]
- offsides·FOR·ALL_PRIOR·HOME = 1.8 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·AWAY = 1.2667 [n=15, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·ALL = 1.8 [n=30, HIGH]
- offsides·AGAINST·W5·ALL = 0.8 [n=5, LOW]
- offsides·AGAINST·W10·ALL = 1.3 [n=10, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·HOME = 1.8667 [n=15, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·AWAY = 1.7333 [n=15, MEDIUM]
- possession·FOR·ALL_PRIOR·ALL = 51.7 [n=30, HIGH]
- possession·FOR·W5·ALL = 53.6 [n=5, LOW]
- possession·FOR·W10·ALL = 54.2 [n=10, MEDIUM]
- possession·FOR·ALL_PRIOR·HOME = 51.2667 [n=15, MEDIUM]
- possession·FOR·ALL_PRIOR·AWAY = 52.1333 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·ALL = 48.3 [n=30, HIGH]
- possession·AGAINST·W5·ALL = 46.4 [n=5, LOW]
- possession·AGAINST·W10·ALL = 45.8 [n=10, MEDIUM]
- possession·AGAINST·ALL_PRIOR·HOME = 48.7333 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·AWAY = 47.8667 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·ALL = 0.1 [n=30, HIGH]
- red_cards·FOR·W5·ALL = 0.0 [n=5, LOW]
- red_cards·FOR·W10·ALL = 0.2 [n=10, MEDIUM]
- red_cards·FOR·ALL_PRIOR·HOME = 0.0 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·AWAY = 0.2 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·ALL = 0.0667 [n=30, HIGH]
- red_cards·AGAINST·W5·ALL = 0.0 [n=5, LOW]
- red_cards·AGAINST·W10·ALL = 0.2 [n=10, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·HOME = 0.0 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·AWAY = 0.1333 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·ALL = 2.2069 [n=29, HIGH]
- saves·FOR·W5·ALL = 2.0 [n=5, LOW]
- saves·FOR·W10·ALL = 2.5 [n=10, MEDIUM]
- saves·FOR·ALL_PRIOR·HOME = 2.2667 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·AWAY = 2.1429 [n=14, MEDIUM]
- saves·AGAINST·ALL_PRIOR·ALL = 3.6897 [n=29, HIGH]
- saves·AGAINST·W5·ALL = 4.0 [n=5, LOW]
- saves·AGAINST·W10·ALL = 3.7 [n=10, MEDIUM]
- saves·AGAINST·ALL_PRIOR·HOME = 3.8667 [n=15, MEDIUM]
- saves·AGAINST·ALL_PRIOR·AWAY = 3.5 [n=14, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·ALL = 8.9333 [n=30, HIGH]
- shots_inside_box·FOR·W5·ALL = 10.2 [n=5, LOW]
- shots_inside_box·FOR·W10·ALL = 9.1 [n=10, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·HOME = 9.4667 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·AWAY = 8.4 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·ALL = 7.9 [n=30, HIGH]
- shots_inside_box·AGAINST·W5·ALL = 7.0 [n=5, LOW]
- shots_inside_box·AGAINST·W10·ALL = 8.0 [n=10, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·HOME = 8.0 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·AWAY = 7.8 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·ALL = 5.0 [n=30, HIGH]
- shots_off_target·FOR·W5·ALL = 6.0 [n=5, LOW]
- shots_off_target·FOR·W10·ALL = 5.2 [n=10, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·HOME = 6.0 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·AWAY = 4.0 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·ALL = 4.2 [n=30, HIGH]
- shots_off_target·AGAINST·W5·ALL = 4.6 [n=5, LOW]
- shots_off_target·AGAINST·W10·ALL = 4.3 [n=10, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·HOME = 4.2 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·AWAY = 4.2 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·ALL = 5.0333 [n=30, HIGH]
- shots_on_target·FOR·W5·ALL = 6.0 [n=5, LOW]
- shots_on_target·FOR·W10·ALL = 5.6 [n=10, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·HOME = 5.1333 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·AWAY = 4.9333 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·ALL = 3.5667 [n=30, HIGH]
- shots_on_target·AGAINST·W5·ALL = 3.0 [n=5, LOW]
- shots_on_target·AGAINST·W10·ALL = 4.1 [n=10, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·HOME = 3.5333 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·AWAY = 3.6 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·ALL = 4.6333 [n=30, HIGH]
- shots_outside_box·FOR·W5·ALL = 5.4 [n=5, LOW]
- shots_outside_box·FOR·W10·ALL = 5.2 [n=10, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·HOME = 5.2667 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·AWAY = 4.0 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·ALL = 2.9333 [n=30, HIGH]
- shots_outside_box·AGAINST·W5·ALL = 3.0 [n=5, LOW]
- shots_outside_box·AGAINST·W10·ALL = 3.4 [n=10, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·HOME = 2.9333 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·AWAY = 2.9333 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·ALL = 18.7667 [n=30, HIGH]
- tackles·FOR·W5·ALL = 21.2 [n=5, LOW]
- tackles·FOR·W10·ALL = 19.9 [n=10, MEDIUM]
- tackles·FOR·ALL_PRIOR·HOME = 18.5333 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·AWAY = 19.0 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·ALL = 17.7333 [n=30, HIGH]
- tackles·AGAINST·W5·ALL = 13.8 [n=5, LOW]
- tackles·AGAINST·W10·ALL = 14.9 [n=10, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·HOME = 17.6 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·AWAY = 17.8667 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·ALL = 15.9 [n=30, HIGH]
- throw_ins·FOR·W5·ALL = 15.6 [n=5, LOW]
- throw_ins·FOR·W10·ALL = 16.3 [n=10, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·HOME = 15.1333 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·AWAY = 16.6667 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·ALL = 16.9667 [n=30, HIGH]
- throw_ins·AGAINST·W5·ALL = 19.0 [n=5, LOW]
- throw_ins·AGAINST·W10·ALL = 19.5 [n=10, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·HOME = 16.2 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·AWAY = 17.7333 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·ALL = 13.5667 [n=30, HIGH]
- total_shots·FOR·W5·ALL = 15.6 [n=5, LOW]
- total_shots·FOR·W10·ALL = 14.3 [n=10, MEDIUM]
- total_shots·FOR·ALL_PRIOR·HOME = 14.7333 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·AWAY = 12.4 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·ALL = 10.8333 [n=30, HIGH]
- total_shots·AGAINST·W5·ALL = 10.0 [n=5, LOW]
- total_shots·AGAINST·W10·ALL = 11.4 [n=10, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·HOME = 10.9333 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·AWAY = 10.7333 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·ALL = 30.3667 [n=30, HIGH]
- touches_in_box·FOR·W5·ALL = 35.2 [n=5, LOW]
- touches_in_box·FOR·W10·ALL = 33.0 [n=10, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·HOME = 32.2667 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·AWAY = 28.4667 [n=15, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·ALL = 24.0333 [n=30, HIGH]
- touches_in_box·AGAINST·W5·ALL = 23.4 [n=5, LOW]
- touches_in_box·AGAINST·W10·ALL = 24.7 [n=10, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·HOME = 24.2667 [n=15, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·AWAY = 23.8 [n=15, MEDIUM]
- xg·FOR·ALL_PRIOR·ALL = 1.636 [n=30, HIGH]
- xg·FOR·W5·ALL = 1.984 [n=5, LOW]
- xg·FOR·W10·ALL = 1.83 [n=10, MEDIUM]
- xg·FOR·ALL_PRIOR·HOME = 1.6367 [n=15, MEDIUM]
- xg·FOR·ALL_PRIOR·AWAY = 1.6353 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·ALL = 1.3663 [n=30, HIGH]
- xg·AGAINST·W5·ALL = 1.506 [n=5, LOW]
- xg·AGAINST·W10·ALL = 1.492 [n=10, MEDIUM]
- xg·AGAINST·ALL_PRIOR·HOME = 1.3367 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·AWAY = 1.396 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·ALL = 2.1 [n=30, HIGH]
- yellow_cards·FOR·W5·ALL = 1.8 [n=5, LOW]
- yellow_cards·FOR·W10·ALL = 2.0 [n=10, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·HOME = 1.7333 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·AWAY = 2.4667 [n=15, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·ALL = 2.4 [n=30, HIGH]
- yellow_cards·AGAINST·W5·ALL = 2.2 [n=5, LOW]
- yellow_cards·AGAINST·W10·ALL = 2.5 [n=10, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·HOME = 2.5333 [n=15, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·AWAY = 2.2667 [n=15, MEDIUM]

AWAY_TEAM:

- accurate_crosses·FOR·ALL_PRIOR·ALL = 3.9333 [n=30, HIGH]
- accurate_crosses·FOR·W5·ALL = 5.2 [n=5, LOW]
- accurate_crosses·FOR·W10·ALL = 4.3 [n=10, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·HOME = 4.4667 [n=15, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·AWAY = 3.4 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·ALL = 3.8667 [n=30, HIGH]
- accurate_crosses·AGAINST·W5·ALL = 4.0 [n=5, LOW]
- accurate_crosses·AGAINST·W10·ALL = 3.8 [n=10, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·HOME = 3.6 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·AWAY = 4.1333 [n=15, MEDIUM]
- big_chances·FOR·ALL_PRIOR·ALL = 3.2143 [n=28, HIGH]
- big_chances·FOR·W5·ALL = 2.75 [n=4, LOW]
- big_chances·FOR·W10·ALL = 3.3333 [n=9, MEDIUM]
- big_chances·FOR·ALL_PRIOR·HOME = 3.4667 [n=15, MEDIUM]
- big_chances·FOR·ALL_PRIOR·AWAY = 2.9231 [n=13, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·ALL = 2.6071 [n=28, HIGH]
- big_chances·AGAINST·W5·ALL = 2.25 [n=4, LOW]
- big_chances·AGAINST·W10·ALL = 2.1111 [n=9, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·HOME = 2.5333 [n=15, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·AWAY = 2.6923 [n=13, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·ALL = 3.9667 [n=30, HIGH]
- blocked_shots·FOR·W5·ALL = 6.0 [n=5, LOW]
- blocked_shots·FOR·W10·ALL = 4.2 [n=10, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·HOME = 4.1333 [n=15, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·AWAY = 3.8 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·ALL = 2.4333 [n=30, HIGH]
- blocked_shots·AGAINST·W5·ALL = 2.6 [n=5, LOW]
- blocked_shots·AGAINST·W10·ALL = 2.4 [n=10, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·HOME = 1.6 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·AWAY = 3.2667 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·ALL = 16.8333 [n=30, HIGH]
- clearances·FOR·W5·ALL = 17.2 [n=5, LOW]
- clearances·FOR·W10·ALL = 17.0 [n=10, MEDIUM]
- clearances·FOR·ALL_PRIOR·HOME = 16.2 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·AWAY = 17.4667 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·ALL = 22.5333 [n=30, HIGH]
- clearances·AGAINST·W5·ALL = 30.2 [n=5, LOW]
- clearances·AGAINST·W10·ALL = 25.7 [n=10, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·HOME = 23.2 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·AWAY = 21.8667 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·ALL = 5.5667 [n=30, HIGH]
- corners·FOR·W5·ALL = 7.2 [n=5, LOW]
- corners·FOR·W10·ALL = 5.9 [n=10, MEDIUM]
- corners·FOR·ALL_PRIOR·HOME = 6.0 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·AWAY = 5.1333 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·ALL = 3.4333 [n=30, HIGH]
- corners·AGAINST·W5·ALL = 1.8 [n=5, LOW]
- corners·AGAINST·W10·ALL = 2.7 [n=10, MEDIUM]
- corners·AGAINST·ALL_PRIOR·HOME = 2.9333 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·AWAY = 3.9333 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·ALL = 57.6333 [n=30, HIGH]
- final_third_entries·FOR·W5·ALL = 54.4 [n=5, LOW]
- final_third_entries·FOR·W10·ALL = 61.8 [n=10, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·HOME = 59.7333 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·AWAY = 55.5333 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·ALL = 38.9667 [n=30, HIGH]
- final_third_entries·AGAINST·W5·ALL = 46.6 [n=5, LOW]
- final_third_entries·AGAINST·W10·ALL = 39.0 [n=10, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·HOME = 35.5333 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·AWAY = 42.4 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·ALL = 7.8333 [n=30, HIGH]
- fouls·FOR·W5·ALL = 6.8 [n=5, LOW]
- fouls·FOR·W10·ALL = 7.5 [n=10, MEDIUM]
- fouls·FOR·ALL_PRIOR·HOME = 7.9333 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·AWAY = 7.7333 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·ALL = 10.3333 [n=30, HIGH]
- fouls·AGAINST·W5·ALL = 11.6 [n=5, LOW]
- fouls·AGAINST·W10·ALL = 11.5 [n=10, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·HOME = 11.4667 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·AWAY = 9.2 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·ALL = 1.8333 [n=30, HIGH]
- goals·FOR·W5·ALL = 1.8 [n=5, LOW]
- goals·FOR·W10·ALL = 1.9 [n=10, MEDIUM]
- goals·FOR·ALL_PRIOR·HOME = 2.0667 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·AWAY = 1.6 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·ALL = 1.1667 [n=30, HIGH]
- goals·AGAINST·W5·ALL = 0.6 [n=5, LOW]
- goals·AGAINST·W10·ALL = 0.6 [n=10, MEDIUM]
- goals·AGAINST·ALL_PRIOR·HOME = 1.2667 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·AWAY = 1.0667 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·ALL = 6.1 [n=30, HIGH]
- interceptions·FOR·W5·ALL = 7.2 [n=5, LOW]
- interceptions·FOR·W10·ALL = 6.7 [n=10, MEDIUM]
- interceptions·FOR·ALL_PRIOR·HOME = 5.6 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·AWAY = 6.6 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·ALL = 8.1 [n=30, HIGH]
- interceptions·AGAINST·W5·ALL = 8.0 [n=5, LOW]
- interceptions·AGAINST·W10·ALL = 9.0 [n=10, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·HOME = 7.6667 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·AWAY = 8.5333 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·ALL = 1.7267 [n=30, HIGH]
- npxg·FOR·W5·ALL = 1.944 [n=5, LOW]
- npxg·FOR·W10·ALL = 1.831 [n=10, MEDIUM]
- npxg·FOR·ALL_PRIOR·HOME = 1.7573 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·AWAY = 1.696 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·ALL = 1.2247 [n=30, HIGH]
- npxg·AGAINST·W5·ALL = 0.842 [n=5, LOW]
- npxg·AGAINST·W10·ALL = 0.927 [n=10, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·HOME = 1.1627 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·AWAY = 1.2867 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·ALL = 1.2333 [n=30, HIGH]
- offsides·FOR·W5·ALL = 0.6 [n=5, LOW]
- offsides·FOR·W10·ALL = 0.8 [n=10, MEDIUM]
- offsides·FOR·ALL_PRIOR·HOME = 1.4 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·AWAY = 1.0667 [n=15, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·ALL = 2.5 [n=30, HIGH]
- offsides·AGAINST·W5·ALL = 2.4 [n=5, LOW]
- offsides·AGAINST·W10·ALL = 2.4 [n=10, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·HOME = 2.4 [n=15, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·AWAY = 2.6 [n=15, MEDIUM]
- possession·FOR·ALL_PRIOR·ALL = 60.4 [n=30, HIGH]
- possession·FOR·W5·ALL = 60.2 [n=5, LOW]
- possession·FOR·W10·ALL = 62.1 [n=10, MEDIUM]
- possession·FOR·ALL_PRIOR·HOME = 61.8667 [n=15, MEDIUM]
- possession·FOR·ALL_PRIOR·AWAY = 58.9333 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·ALL = 39.6 [n=30, HIGH]
- possession·AGAINST·W5·ALL = 39.8 [n=5, LOW]
- possession·AGAINST·W10·ALL = 37.9 [n=10, MEDIUM]
- possession·AGAINST·ALL_PRIOR·HOME = 38.1333 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·AWAY = 41.0667 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·ALL = 0.0667 [n=30, HIGH]
- red_cards·FOR·W5·ALL = 0.2 [n=5, LOW]
- red_cards·FOR·W10·ALL = 0.1 [n=10, MEDIUM]
- red_cards·FOR·ALL_PRIOR·HOME = 0.0667 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·AWAY = 0.0667 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·ALL = 0.0333 [n=30, HIGH]
- red_cards·AGAINST·W5·ALL = 0.2 [n=5, LOW]
- red_cards·AGAINST·W10·ALL = 0.1 [n=10, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·HOME = 0.0667 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·AWAY = 0.0 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·ALL = 2.3333 [n=30, HIGH]
- saves·FOR·W5·ALL = 2.0 [n=5, LOW]
- saves·FOR·W10·ALL = 1.7 [n=10, MEDIUM]
- saves·FOR·ALL_PRIOR·HOME = 1.8 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·AWAY = 2.8667 [n=15, MEDIUM]
- saves·AGAINST·ALL_PRIOR·ALL = 3.3667 [n=30, HIGH]
- saves·AGAINST·W5·ALL = 2.6 [n=5, LOW]
- saves·AGAINST·W10·ALL = 3.1 [n=10, MEDIUM]
- saves·AGAINST·ALL_PRIOR·HOME = 3.1333 [n=15, MEDIUM]
- saves·AGAINST·ALL_PRIOR·AWAY = 3.6 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·ALL = 9.3667 [n=30, HIGH]
- shots_inside_box·FOR·W5·ALL = 9.8 [n=5, LOW]
- shots_inside_box·FOR·W10·ALL = 9.2 [n=10, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·HOME = 9.3333 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·AWAY = 9.4 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·ALL = 7.5667 [n=30, HIGH]
- shots_inside_box·AGAINST·W5·ALL = 7.0 [n=5, LOW]
- shots_inside_box·AGAINST·W10·ALL = 6.6 [n=10, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·HOME = 6.8 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·AWAY = 8.3333 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·ALL = 5.3 [n=30, HIGH]
- shots_off_target·FOR·W5·ALL = 6.0 [n=5, LOW]
- shots_off_target·FOR·W10·ALL = 5.4 [n=10, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·HOME = 5.3333 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·AWAY = 5.2667 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·ALL = 3.9667 [n=30, HIGH]
- shots_off_target·AGAINST·W5·ALL = 3.6 [n=5, LOW]
- shots_off_target·AGAINST·W10·ALL = 3.7 [n=10, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·HOME = 4.3333 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·AWAY = 3.6 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·ALL = 5.2333 [n=30, HIGH]
- shots_on_target·FOR·W5·ALL = 4.6 [n=5, LOW]
- shots_on_target·FOR·W10·ALL = 5.2 [n=10, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·HOME = 5.2667 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·AWAY = 5.2 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·ALL = 3.6 [n=30, HIGH]
- shots_on_target·AGAINST·W5·ALL = 2.6 [n=5, LOW]
- shots_on_target·AGAINST·W10·ALL = 2.5 [n=10, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·HOME = 3.0667 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·AWAY = 4.1333 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·ALL = 5.1333 [n=30, HIGH]
- shots_outside_box·FOR·W5·ALL = 6.8 [n=5, LOW]
- shots_outside_box·FOR·W10·ALL = 5.6 [n=10, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·HOME = 5.4 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·AWAY = 4.8667 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·ALL = 2.4333 [n=30, HIGH]
- shots_outside_box·AGAINST·W5·ALL = 1.8 [n=5, LOW]
- shots_outside_box·AGAINST·W10·ALL = 2.0 [n=10, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·HOME = 2.2 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·AWAY = 2.6667 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·ALL = 13.4 [n=30, HIGH]
- tackles·FOR·W5·ALL = 14.4 [n=5, LOW]
- tackles·FOR·W10·ALL = 14.1 [n=10, MEDIUM]
- tackles·FOR·ALL_PRIOR·HOME = 12.9333 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·AWAY = 13.8667 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·ALL = 18.8667 [n=30, HIGH]
- tackles·AGAINST·W5·ALL = 18.0 [n=5, LOW]
- tackles·AGAINST·W10·ALL = 19.8 [n=10, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·HOME = 19.2 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·AWAY = 18.5333 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·ALL = 16.0667 [n=30, HIGH]
- throw_ins·FOR·W5·ALL = 18.4 [n=5, LOW]
- throw_ins·FOR·W10·ALL = 17.3 [n=10, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·HOME = 16.1333 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·AWAY = 16.0 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·ALL = 14.9333 [n=30, HIGH]
- throw_ins·AGAINST·W5·ALL = 16.6 [n=5, LOW]
- throw_ins·AGAINST·W10·ALL = 16.3 [n=10, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·HOME = 15.0667 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·AWAY = 14.8 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·ALL = 14.5 [n=30, HIGH]
- total_shots·FOR·W5·ALL = 16.6 [n=5, LOW]
- total_shots·FOR·W10·ALL = 14.8 [n=10, MEDIUM]
- total_shots·FOR·ALL_PRIOR·HOME = 14.7333 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·AWAY = 14.2667 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·ALL = 10.0 [n=30, HIGH]
- total_shots·AGAINST·W5·ALL = 8.8 [n=5, LOW]
- total_shots·AGAINST·W10·ALL = 8.6 [n=10, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·HOME = 9.0 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·AWAY = 11.0 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·ALL = 32.8667 [n=30, HIGH]
- touches_in_box·FOR·W5·ALL = 41.0 [n=5, LOW]
- touches_in_box·FOR·W10·ALL = 34.1 [n=10, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·HOME = 33.5333 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·AWAY = 32.2 [n=15, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·ALL = 20.2 [n=30, HIGH]
- touches_in_box·AGAINST·W5·ALL = 20.2 [n=5, LOW]
- touches_in_box·AGAINST·W10·ALL = 19.9 [n=10, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·HOME = 18.2 [n=15, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·AWAY = 22.2 [n=15, MEDIUM]
- xg·FOR·ALL_PRIOR·ALL = 1.7533 [n=30, HIGH]
- xg·FOR·W5·ALL = 2.074 [n=5, LOW]
- xg·FOR·W10·ALL = 1.845 [n=10, MEDIUM]
- xg·FOR·ALL_PRIOR·HOME = 1.81 [n=15, MEDIUM]
- xg·FOR·ALL_PRIOR·AWAY = 1.6967 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·ALL = 1.3053 [n=30, HIGH]
- xg·AGAINST·W5·ALL = 0.834 [n=5, LOW]
- xg·AGAINST·W10·ALL = 0.993 [n=10, MEDIUM]
- xg·AGAINST·ALL_PRIOR·HOME = 1.26 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·AWAY = 1.3507 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·ALL = 1.6154 [n=26, HIGH]
- yellow_cards·FOR·W5·ALL = 1.0 [n=4, LOW]
- yellow_cards·FOR·W10·ALL = 1.375 [n=8, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·HOME = 1.7692 [n=13, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·AWAY = 1.4615 [n=13, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·ALL = 2.5 [n=26, HIGH]
- yellow_cards·AGAINST·W5·ALL = 2.5 [n=4, LOW]
- yellow_cards·AGAINST·W10·ALL = 2.875 [n=8, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·HOME = 2.8462 [n=13, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·AWAY = 2.1538 [n=13, MEDIUM]

### Arm B — opponent-profile context (deterministic bands)

```json
{
 "axes": {
  "accurate_crosses_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "corners_against": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "corners_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  },
  "goals_against": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "goals_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  },
  "possession_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  },
  "shots_on_target_against": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "shots_on_target_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  }
 },
 "similarity_version": "opponent_similarity_v1_pending"
}
```

---

## mt_010243537

- PIT-safe matches available: **154**; match rows included (both teams): **60**; omitted: **94** (reason: `frozen_history_policy(max_matches_per_team=30)`); UNEXPLAINED_OMISSION: **0**.
- Metric cell exposure rate (non-null of serialized): **0.9951**; derived summaries: **480**.
- Availability map: `{"expected_formation": "UNAVAILABLE", "formation": "LOW_COVERAGE", "half_time_state": "UNAVAILABLE", "injuries": "UNAVAILABLE", "lineup": "PIT_UNSAFE", "opponent_profile": "AVAILABLE", "recent_vs_long": "AVAILABLE", "red_cards": "AVAILABLE", "temporal_event_state": "UNAVAILABLE", "venue": "AVAILABLE", "xg": "AVAILABLE"}`
- Arm A packet hash: `52c2ce304d8cf12acc70200a56d52ba9ae30bff363e78a5fe0b479eae9546da3`
- Arm B packet hash: `3eb1c8377463891a159407866b77b05974176191b7ab910841cc7ebe179c302f`

### Arm A — frozen V3 compressed evidence (all items)

76 unconditional shrunk scalar items (venue=ALL, window=ALL_PRIOR):

| id | metric | value | n | reliability |
|---|---|---|---|---|
| HOME_ATK_corners_406027 | corners_for | 5.4716 | 103 | HIGH |
| HOME_DEF_corners_7cfac3 | corners_against | 4.3065 | 103 | HIGH |
| HOME_ATK_accurate_crosses_c28b9e | accurate_crosses_for | 3.8842 | 103 | HIGH |
| HOME_DEF_accurate_crosses_81ffb5 | accurate_crosses_against | 3.8108 | 103 | HIGH |
| HOME_ATK_total_shots_808ac9 | total_shots_for | 13.1202 | 103 | HIGH |
| HOME_DEF_total_shots_c0e347 | total_shots_against | 11.2853 | 103 | HIGH |
| HOME_ATK_shots_on_target_e955e0 | shots_on_target_for | 4.2526 | 103 | HIGH |
| HOME_DEF_shots_on_target_8a3812 | shots_on_target_against | 3.6196 | 103 | HIGH |
| HOME_ATK_shots_off_target_11e91f | shots_off_target_for | 4.4841 | 103 | HIGH |
| HOME_DEF_shots_off_target_26031c | shots_off_target_against | 4.1354 | 103 | HIGH |
| HOME_ATK_blocked_shots_5198f8 | blocked_shots_for | 4.3835 | 103 | HIGH |
| HOME_DEF_blocked_shots_09c3c4 | blocked_shots_against | 3.5303 | 103 | HIGH |
| HOME_ATK_shots_inside_box_cf538d | shots_inside_box_for | 8.5117 | 103 | HIGH |
| HOME_DEF_shots_inside_box_e6b28d | shots_inside_box_against | 7.3741 | 103 | HIGH |
| HOME_ATK_touches_in_box_759ed8 | touches_in_box_for | 23.9872 | 58 | HIGH |
| HOME_DEF_touches_in_box_94cd98 | touches_in_box_against | 21.7216 | 58 | HIGH |
| HOME_ATK_final_third_entries_5aa0be | final_third_entries_for | 53.5874 | 103 | HIGH |
| HOME_DEF_final_third_entries_4a40ef | final_third_entries_against | 54.5966 | 103 | HIGH |
| HOME_ATK_possession_190f3f | possession_for | 51.4312 | 103 | HIGH |
| HOME_DEF_possession_f8ada9 | possession_against | 48.5688 | 103 | HIGH |
| HOME_ATK_tackles_65b6c1 | tackles_for | 16.9003 | 103 | HIGH |
| HOME_DEF_tackles_e3c85e | tackles_against | 18.4324 | 103 | HIGH |
| HOME_ATK_fouls_8107c6 | fouls_for | 10.2582 | 103 | HIGH |
| HOME_DEF_fouls_b6d53c | fouls_against | 12.5793 | 103 | HIGH |
| HOME_ATK_yellow_cards_80b7a4 | yellow_cards_for | 2.1619 | 98 | HIGH |
| HOME_DEF_yellow_cards_8ee8aa | yellow_cards_against | 2.5754 | 98 | HIGH |
| HOME_ATK_clearances_ec2e18 | clearances_for | 21.2256 | 103 | HIGH |
| HOME_DEF_clearances_6d3f4c | clearances_against | 21.7577 | 103 | HIGH |
| HOME_ATK_interceptions_967965 | interceptions_for | 8.0476 | 103 | HIGH |
| HOME_DEF_interceptions_c82020 | interceptions_against | 8.2128 | 103 | HIGH |
| HOME_ATK_goals_08b15b | goals_for | 1.206 | 104 | HIGH |
| HOME_DEF_goals_d53fdd | goals_against | 1.0696 | 104 | HIGH |
| HOME_ATK_throw_ins_b24629 | throw_ins_for | 19.8712 | 103 | HIGH |
| HOME_DEF_throw_ins_208262 | throw_ins_against | 19.5776 | 103 | HIGH |
| HOME_ATK_big_chances_8a9e2f | big_chances_for | 1.9293 | 100 | HIGH |
| HOME_DEF_big_chances_885151 | big_chances_against | 1.8444 | 100 | HIGH |
| HOME_ATK_saves_6bda8d | saves_for | 2.5041 | 103 | HIGH |
| HOME_DEF_saves_19ae14 | saves_against | 3.0454 | 103 | HIGH |
| AWAY_ATK_corners_ca1538 | corners_for | 5.9001 | 50 | HIGH |
| AWAY_DEF_corners_598e33 | corners_against | 4.7573 | 50 | HIGH |
| AWAY_ATK_accurate_crosses_005290 | accurate_crosses_for | 4.6854 | 50 | HIGH |
| AWAY_DEF_accurate_crosses_287e9c | accurate_crosses_against | 3.9354 | 50 | HIGH |
| AWAY_ATK_total_shots_004f7a | total_shots_for | 14.5018 | 50 | HIGH |
| AWAY_DEF_total_shots_403d28 | total_shots_against | 12.3768 | 50 | HIGH |
| AWAY_ATK_shots_on_target_9afd02 | shots_on_target_for | 5.081 | 50 | HIGH |
| AWAY_DEF_shots_on_target_dcda5e | shots_on_target_against | 4.5453 | 50 | HIGH |
| AWAY_ATK_shots_off_target_b83815 | shots_off_target_for | 5.3708 | 50 | HIGH |
| AWAY_DEF_shots_off_target_5fe2d0 | shots_off_target_against | 4.3529 | 50 | HIGH |
| AWAY_ATK_blocked_shots_93d965 | blocked_shots_for | 4.05 | 50 | HIGH |
| AWAY_DEF_blocked_shots_97ef03 | blocked_shots_against | 3.4785 | 50 | HIGH |
| AWAY_ATK_shots_inside_box_567ee5 | shots_inside_box_for | 9.5674 | 50 | HIGH |
| AWAY_DEF_shots_inside_box_446c80 | shots_inside_box_against | 8.2995 | 50 | HIGH |
| AWAY_ATK_touches_in_box_2c76ca | touches_in_box_for | 27.3426 | 50 | HIGH |
| AWAY_DEF_touches_in_box_319da5 | touches_in_box_against | 25.414 | 50 | HIGH |
| AWAY_ATK_final_third_entries_5a0987 | final_third_entries_for | 59.3041 | 50 | HIGH |
| AWAY_DEF_final_third_entries_ed75cd | final_third_entries_against | 54.0006 | 50 | HIGH |
| AWAY_ATK_possession_82105a | possession_for | 49.6071 | 50 | HIGH |
| AWAY_DEF_possession_012ecc | possession_against | 50.3929 | 50 | HIGH |
| AWAY_ATK_tackles_0865bc | tackles_for | 17.9309 | 50 | HIGH |
| AWAY_DEF_tackles_3e6a7d | tackles_against | 17.1988 | 50 | HIGH |
| AWAY_ATK_fouls_97bf91 | fouls_for | 13.2526 | 50 | HIGH |
| AWAY_DEF_fouls_94f7aa | fouls_against | 10.6633 | 50 | HIGH |
| AWAY_ATK_yellow_cards_120c77 | yellow_cards_for | 2.4614 | 50 | HIGH |
| AWAY_DEF_yellow_cards_367397 | yellow_cards_against | 2.3185 | 50 | HIGH |
| AWAY_ATK_clearances_74617f | clearances_for | 26.5283 | 50 | HIGH |
| AWAY_DEF_clearances_8bdc80 | clearances_against | 26.7247 | 50 | HIGH |
| AWAY_ATK_interceptions_404e22 | interceptions_for | 8.932 | 50 | HIGH |
| AWAY_DEF_interceptions_4be11b | interceptions_against | 7.2713 | 50 | HIGH |
| AWAY_ATK_goals_5d2c6a | goals_for | 1.5296 | 50 | HIGH |
| AWAY_DEF_goals_4ad3b7 | goals_against | 1.3332 | 50 | HIGH |
| AWAY_ATK_throw_ins_64d189 | throw_ins_for | 18.285 | 50 | HIGH |
| AWAY_DEF_throw_ins_35916f | throw_ins_against | 20.1242 | 50 | HIGH |
| AWAY_ATK_big_chances_065222 | big_chances_for | 2.6511 | 47 | HIGH |
| AWAY_DEF_big_chances_d5f920 | big_chances_against | 2.1794 | 47 | HIGH |
| AWAY_ATK_saves_50b33b | saves_for | 3.2133 | 50 | HIGH |
| AWAY_DEF_saves_bf5cbb | saves_against | 3.6776 | 50 | HIGH |

### Arm B — HOME_TEAM match-level matrix (30 rows × 55 cols)

Columns: `match_alias, kickoff_unix, competition, venue, opponent_alias, own_formation_family, opponent_formation_family, accurate_crosses_for, accurate_crosses_against, big_chances_for, big_chances_against, blocked_shots_for, blocked_shots_against, clearances_for, clearances_against, corners_for, corners_against, final_third_entries_for, final_third_entries_against, fouls_for, fouls_against, goals_for, goals_against, interceptions_for, interceptions_against, npxg_for, npxg_against, offsides_for, offsides_against, possession_for, possession_against, red_cards_for, red_cards_against, saves_for, saves_against, shots_inside_box_for, shots_inside_box_against, shots_off_target_for, shots_off_target_against, shots_on_target_for, shots_on_target_against, shots_outside_box_for, shots_outside_box_against, tackles_for, tackles_against, throw_ins_for, throw_ins_against, total_shots_for, total_shots_against, touches_in_box_for, touches_in_box_against, xg_for, xg_against, yellow_cards_for, yellow_cards_against`

| match_alias | kickoff_unix | competition | venue | opponent_alias | own_formation_family | opponent_formation_family | accurate_crosses_for | accurate_crosses_against | big_chances_for | big_chances_against | blocked_shots_for | blocked_shots_against | clearances_for | clearances_against | corners_for | corners_against | final_third_entries_for | final_third_entries_against | fouls_for | fouls_against | goals_for | goals_against | interceptions_for | interceptions_against | npxg_for | npxg_against | offsides_for | offsides_against | possession_for | possession_against | red_cards_for | red_cards_against | saves_for | saves_against | shots_inside_box_for | shots_inside_box_against | shots_off_target_for | shots_off_target_against | shots_on_target_for | shots_on_target_against | shots_outside_box_for | shots_outside_box_against | tackles_for | tackles_against | throw_ins_for | throw_ins_against | total_shots_for | total_shots_against | touches_in_box_for | touches_in_box_against | xg_for | xg_against | yellow_cards_for | yellow_cards_against |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| m_mt_745923965 | 1737817200 | COMP_002 | HOME | OPP_001 |  |  | 5.0 | 5.0 | 0.0 | 2.0 | 6.0 | 0.0 | 10.0 | 46.0 | 7.0 | 2.0 | 85.0 | 42.0 | 7.0 | 21.0 | 2.0 | 2.0 | 3.0 | 7.0 | 0.59 | 1.06 | 2.0 | 2.0 | 69.0 | 31.0 | 0.0 | 0.0 | 2.0 | 3.0 | 10.0 | 6.0 | 1.0 | 4.0 | 5.0 | 3.0 | 2.0 | 1.0 | 17.0 | 17.0 | 26.0 | 20.0 | 12.0 | 7.0 | 20.0 | 15.0 | 0.59 | 1.05 | 1.0 | 4.0 |
| m_mt_836642672 | 1738612800 | COMP_002 | AWAY | OPP_002 |  |  | 5.0 | 4.0 | 2.0 | 2.0 | 2.0 | 4.0 | 14.0 | 18.0 | 5.0 | 1.0 | 58.0 | 72.0 | 15.0 | 11.0 | 3.0 | 2.0 | 10.0 | 5.0 | 2.1 | 1.43 | 4.0 | 0.0 | 47.0 | 53.0 | 0.0 | 0.0 | 2.0 | 7.0 | 9.0 | 8.0 | 1.0 | 4.0 | 9.0 | 4.0 | 3.0 | 4.0 | 16.0 | 18.0 | 19.0 | 25.0 | 12.0 | 12.0 | 24.0 | 15.0 | 2.05 | 1.32 | 3.0 | 2.0 |
| m_mt_013482445 | 1739017800 | COMP_002 | HOME | OPP_003 |  |  | 5.0 | 1.0 | 5.0 | 2.0 | 3.0 | 3.0 | 17.0 | 37.0 | 7.0 | 3.0 | 60.0 | 51.0 | 12.0 | 20.0 | 2.0 | 2.0 | 6.0 | 9.0 | 3.0 | 0.75 | 2.0 | 0.0 | 50.0 | 50.0 | 0.0 | 0.0 | 3.0 | 5.0 | 11.0 | 5.0 | 4.0 | 3.0 | 7.0 | 5.0 | 3.0 | 6.0 | 21.0 | 15.0 | 21.0 | 12.0 | 14.0 | 11.0 | 26.0 | 11.0 | 2.97 | 1.54 | 5.0 | 1.0 |
| m_mt_584271214 | 1739389500 | COMP_002 | HOME | OPP_004 |  |  | 0.0 | 1.0 | 2.0 | 1.0 | 3.0 | 2.0 | 34.0 | 17.0 | 6.0 | 1.0 | 59.0 | 61.0 | 6.0 | 9.0 | 2.0 | 0.0 | 5.0 | 5.0 | 1.32 | 0.32 | 1.0 | 2.0 | 66.0 | 34.0 | 0.0 | 0.0 | 1.0 | 1.0 | 10.0 | 2.0 | 7.0 | 1.0 | 3.0 | 1.0 | 3.0 | 2.0 | 14.0 | 19.0 | 21.0 | 17.0 | 13.0 | 4.0 | 19.0 | 13.0 | 1.24 | 0.31 | 0.0 | 2.0 |
| m_mt_401159259 | 1739822400 | COMP_002 | AWAY | OPP_005 |  |  | 2.0 | 8.0 | 1.0 | 1.0 | 0.0 | 11.0 | 47.0 | 7.0 | 0.0 | 10.0 | 31.0 | 81.0 | 11.0 | 11.0 | 1.0 | 2.0 | 7.0 | 5.0 | 0.54 | 2.05 | 0.0 | 2.0 | 34.0 | 66.0 | 0.0 | 0.0 | 2.0 | 4.0 | 4.0 | 10.0 | 0.0 | 6.0 | 6.0 | 4.0 | 2.0 | 11.0 | 20.0 | 20.0 | 13.0 | 25.0 | 6.0 | 21.0 | 7.0 | 27.0 | 0.52 | 2.05 | 6.0 | 3.0 |
| m_mt_972168167 | 1740227400 | COMP_002 | HOME | OPP_006 | BACK_FOUR | BACK_FOUR | 9.0 | 1.0 | 1.0 | 2.0 | 7.0 | 3.0 | 32.0 | 41.0 | 5.0 | 3.0 | 90.0 | 49.0 | 6.0 | 15.0 | 0.0 | 1.0 | 5.0 | 6.0 | 1.13 | 1.19 | 2.0 | 4.0 | 61.0 | 39.0 | 0.0 | 0.0 | 3.0 | 2.0 | 11.0 | 4.0 | 8.0 | 1.0 | 2.0 | 4.0 | 6.0 | 4.0 | 11.0 | 21.0 | 23.0 | 19.0 | 17.0 | 8.0 | 26.0 | 9.0 | 0.83 | 0.92 | 0.0 | 3.0 |
| m_mt_629314463 | 1740772800 | COMP_002 | AWAY | OPP_007 |  |  | 5.0 | 7.0 | 1.0 | 2.0 | 5.0 | 2.0 | 48.0 | 17.0 | 9.0 | 5.0 | 45.0 | 63.0 | 13.0 | 10.0 | 2.0 | 1.0 | 9.0 | 8.0 | 1.04 | 1.41 | 1.0 | 0.0 | 42.0 | 58.0 | 0.0 | 0.0 | 3.0 | 2.0 | 8.0 | 7.0 | 2.0 | 3.0 | 4.0 | 4.0 | 3.0 | 2.0 | 19.0 | 19.0 | 23.0 | 18.0 | 11.0 | 9.0 | 17.0 | 25.0 | 1.04 | 1.13 | 1.0 | 1.0 |
| m_mt_361807748 | 1741446000 | COMP_002 | HOME | OPP_008 |  |  | 3.0 | 4.0 | 2.0 | 2.0 | 8.0 | 3.0 | 41.0 | 33.0 | 4.0 | 3.0 | 55.0 | 60.0 | 10.0 | 16.0 | 2.0 | 1.0 | 7.0 | 7.0 | 2.45 | 0.57 | 2.0 | 0.0 | 58.0 | 42.0 | 0.0 | 0.0 | 1.0 | 2.0 | 16.0 | 2.0 | 7.0 | 1.0 | 4.0 | 2.0 | 3.0 | 4.0 | 13.0 | 25.0 | 16.0 | 23.0 | 19.0 | 6.0 | 35.0 | 10.0 | 2.45 | 0.5 | 1.0 | 2.0 |
| m_mt_745923305 | 1741722300 | COMP_002 | HOME | OPP_009 |  |  | 4.0 | 2.0 | 4.0 | 1.0 | 9.0 | 5.0 | 24.0 | 49.0 | 7.0 | 2.0 | 71.0 | 50.0 | 10.0 | 11.0 | 1.0 | 1.0 | 4.0 | 8.0 | 2.08 | 0.86 | 0.0 | 3.0 | 53.0 | 47.0 | 0.0 | 0.0 | 1.0 | 1.0 | 12.0 | 6.0 | 9.0 | 8.0 | 2.0 | 2.0 | 8.0 | 9.0 | 14.0 | 13.0 | 22.0 | 17.0 | 20.0 | 15.0 | 35.0 | 18.0 | 2.11 | 0.79 | 1.0 | 3.0 |
| m_mt_196035566 | 1742050800 | COMP_002 | AWAY | OPP_010 |  |  | 1.0 | 6.0 | 0.0 | 3.0 | 1.0 | 9.0 | 20.0 | 9.0 | 1.0 | 6.0 | 61.0 | 73.0 | 11.0 | 9.0 | 0.0 | 3.0 | 7.0 | 10.0 | 0.57 | 2.07 | 4.0 | 4.0 | 45.0 | 55.0 | 0.0 | 0.0 | 3.0 | 1.0 | 5.0 | 16.0 | 4.0 | 7.0 | 1.0 | 5.0 | 1.0 | 5.0 | 23.0 | 25.0 | 11.0 | 14.0 | 6.0 | 21.0 | 14.0 | 29.0 | 0.44 | 2.86 | 2.0 | 1.0 |
| m_mt_408756664 | 1743260400 | COMP_002 | HOME | OPP_011 |  |  | 3.0 | 2.0 | 5.0 | 0.0 | 5.0 | 2.0 | 18.0 | 23.0 | 6.0 | 1.0 | 42.0 | 71.0 | 14.0 | 13.0 | 1.0 | 0.0 | 11.0 | 8.0 | 1.46 | 0.79 | 1.0 | 2.0 | 46.0 | 54.0 | 0.0 | 0.0 | 2.0 | 5.0 | 10.0 | 4.0 | 2.0 | 1.0 | 6.0 | 2.0 | 3.0 | 1.0 | 31.0 | 25.0 | 22.0 | 18.0 | 13.0 | 5.0 | 26.0 | 10.0 | 1.81 | 0.48 | 4.0 | 3.0 |
| m_mt_196048133 | 1743852600 | COMP_002 | AWAY | OPP_012 |  |  | 0.0 | 4.0 | 1.0 | 1.0 | 1.0 | 10.0 | 55.0 | 34.0 | 6.0 | 6.0 | 38.0 | 67.0 | 14.0 | 15.0 | 1.0 | 0.0 | 5.0 | 5.0 | 0.48 | 1.71 | 3.0 | 1.0 | 36.0 | 64.0 | 0.0 | 0.0 | 2.0 | 2.0 | 2.0 | 11.0 | 3.0 | 8.0 | 3.0 | 3.0 | 5.0 | 10.0 | 24.0 | 14.0 | 23.0 | 20.0 | 7.0 | 21.0 | 12.0 | 40.0 | 0.23 | 1.71 | 3.0 | 2.0 |
| m_mt_196048100 | 1744137900 | COMP_002 | AWAY | OPP_013 |  |  | 4.0 | 6.0 | 1.0 | 2.0 | 3.0 | 3.0 | 22.0 | 20.0 | 4.0 | 4.0 | 46.0 | 57.0 | 14.0 | 13.0 | 0.0 | 0.0 | 7.0 | 5.0 | 0.76 | 0.95 | 3.0 | 2.0 | 44.0 | 56.0 | 0.0 | 0.0 | 3.0 | 3.0 | 5.0 | 6.0 | 1.0 | 4.0 | 3.0 | 4.0 | 2.0 | 5.0 | 16.0 | 24.0 | 11.0 | 12.0 | 7.0 | 11.0 | 22.0 | 25.0 | 0.71 | 0.82 | 4.0 | 2.0 |
| m_mt_408792226 | 1744466400 | COMP_002 | HOME | OPP_014 |  |  | 3.0 | 6.0 | 0.0 | 1.0 | 8.0 | 1.0 | 21.0 | 39.0 | 4.0 | 1.0 | 72.0 | 55.0 | 13.0 | 16.0 | 0.0 | 1.0 | 4.0 | 7.0 | 0.68 | 0.92 | 5.0 | 2.0 | 68.0 | 32.0 | 0.0 | 0.0 | 1.0 | 3.0 | 7.0 | 8.0 | 1.0 | 6.0 | 3.0 | 2.0 | 5.0 | 1.0 | 10.0 | 22.0 | 23.0 | 22.0 | 12.0 | 9.0 | 21.0 | 15.0 | 0.67 | 0.9 | 2.0 | 3.0 |
| m_mt_584265778 | 1744984800 | COMP_002 | AWAY | OPP_015 |  |  | 2.0 | 10.0 | 0.0 | 4.0 | 1.0 | 6.0 | 40.0 | 10.0 | 2.0 | 5.0 | 27.0 | 98.0 | 9.0 | 5.0 | 1.0 | 2.0 | 9.0 | 2.0 | 0.37 | 2.0 | 0.0 | 2.0 | 23.0 | 77.0 | 1.0 | 0.0 | 4.0 | 1.0 | 2.0 | 14.0 | 1.0 | 14.0 | 2.0 | 7.0 | 2.0 | 13.0 | 14.0 | 16.0 | 17.0 | 23.0 | 4.0 | 27.0 | 10.0 | 45.0 | 0.37 | 2.0 | 3.0 | 1.0 |
| m_mt_629386119 | 1745244000 | COMP_002 | HOME | OPP_016 |  |  | 12.0 | 2.0 | 0.0 | 1.0 | 8.0 | 1.0 | 14.0 | 36.0 | 10.0 | 2.0 | 71.0 | 36.0 | 7.0 | 15.0 | 0.0 | 1.0 | 7.0 | 12.0 | 0.81 | 0.3 | 1.0 | 1.0 | 58.0 | 42.0 | 0.0 | 0.0 | 0.0 | 3.0 | 9.0 | 1.0 | 6.0 | 0.0 | 2.0 | 1.0 | 7.0 | 1.0 | 18.0 | 17.0 | 22.0 | 20.0 | 16.0 | 2.0 | 34.0 | 5.0 | 0.81 | 0.29 | 1.0 | 2.0 |
| m_mt_361853526 | 1745676000 | COMP_002 | AWAY | OPP_017 |  |  | 4.0 | 1.0 | 0.0 | 2.0 | 5.0 | 6.0 | 25.0 | 24.0 | 6.0 | 3.0 | 71.0 | 57.0 | 10.0 | 15.0 | 0.0 | 2.0 | 5.0 | 7.0 | 0.59 | 1.66 |  |  | 69.0 | 31.0 | 0.0 | 0.0 | 2.0 | 0.0 | 7.0 | 8.0 | 5.0 | 7.0 | 0.0 | 4.0 | 3.0 | 9.0 | 13.0 | 20.0 | 27.0 | 15.0 | 10.0 | 17.0 | 19.0 | 17.0 | 0.45 | 1.39 | 1.0 | 3.0 |
| m_mt_361853547 | 1746271800 | COMP_002 | HOME | OPP_018 |  |  | 9.0 | 4.0 | 0.0 | 2.0 | 5.0 | 1.0 | 15.0 | 46.0 | 11.0 | 1.0 | 80.0 | 28.0 | 13.0 | 11.0 | 0.0 | 1.0 | 4.0 | 7.0 | 0.57 | 0.54 | 4.0 | 1.0 | 58.0 | 42.0 | 0.0 | 0.0 | 0.0 | 4.0 | 7.0 | 4.0 | 1.0 | 3.0 | 5.0 | 1.0 | 4.0 | 1.0 | 13.0 | 24.0 | 25.0 | 18.0 | 11.0 | 5.0 | 24.0 | 9.0 | 0.57 | 0.36 | 2.0 | 3.0 |
| m_mt_838950600 | 1755352800 | COMPETITION | HOME | OPP_019 |  |  | 5.0 | 5.0 | 2.0 | 0.0 | 1.0 | 6.0 | 32.0 | 16.0 | 5.0 | 7.0 | 48.0 | 78.0 | 8.0 | 10.0 | 3.0 | 0.0 | 9.0 | 4.0 | 0.75 | 0.56 |  |  | 37.0 | 63.0 | 0.0 | 0.0 | 4.0 | 2.0 | 9.0 | 7.0 | 4.0 | 2.0 | 5.0 | 4.0 | 1.0 | 5.0 | 14.0 | 12.0 | 17.0 | 20.0 | 10.0 | 12.0 | 15.0 | 28.0 | 0.68 | 0.56 | 0.0 | 1.0 |
| m_mt_252067135 | 1755957600 | COMPETITION | AWAY | OPP_020 |  |  | 5.0 | 4.0 | 2.0 | 2.0 | 5.0 | 1.0 | 27.0 | 29.0 | 3.0 | 4.0 | 68.0 | 58.0 | 5.0 | 9.0 | 0.0 | 2.0 | 7.0 | 7.0 | 0.77 | 1.0 | 2.0 | 0.0 | 58.0 | 42.0 | 0.0 | 0.0 | 0.0 | 1.0 | 6.0 | 4.0 | 3.0 | 4.0 | 1.0 | 2.0 | 3.0 | 3.0 | 18.0 | 22.0 | 19.0 | 11.0 | 9.0 | 7.0 | 17.0 | 17.0 | 0.77 | 1.0 | 1.0 | 0.0 |
| m_mt_979812313 | 1756562400 | COMPETITION | HOME | OPP_021 |  |  | 3.0 | 6.0 | 2.0 | 2.0 | 3.0 | 1.0 | 34.0 | 34.0 | 3.0 | 4.0 | 70.0 | 44.0 | 11.0 | 12.0 | 2.0 | 1.0 | 7.0 | 4.0 | 0.76 | 0.41 | 0.0 | 3.0 | 54.0 | 46.0 | 0.0 | 0.0 | 3.0 | 1.0 | 9.0 | 5.0 | 6.0 | 2.0 | 3.0 | 4.0 | 3.0 | 2.0 | 28.0 | 9.0 | 22.0 | 16.0 | 12.0 | 7.0 | 16.0 | 14.0 | 1.54 | 1.2 | 3.0 | 2.0 |
| m_mt_585124997 | 1757772000 | COMPETITION | AWAY | OPP_022 | BACK_FOUR | BACK_THREE | 4.0 | 5.0 | 0.0 | 3.0 | 2.0 | 4.0 | 34.0 | 25.0 | 3.0 | 5.0 | 60.0 | 45.0 | 8.0 | 10.0 | 0.0 | 0.0 | 10.0 | 6.0 | 0.4 | 1.78 | 2.0 | 0.0 | 44.0 | 56.0 | 0.0 | 0.0 | 6.0 | 0.0 | 5.0 | 8.0 | 4.0 | 4.0 | 0.0 | 6.0 | 1.0 | 6.0 | 13.0 | 10.0 | 21.0 | 23.0 | 6.0 | 14.0 | 17.0 | 21.0 | 0.36 | 1.77 | 1.0 | 1.0 |
| m_mt_979812971 | 1758459600 | COMPETITION | HOME | OPP_023 |  |  | 2.0 | 4.0 | 1.0 | 2.0 | 4.0 | 6.0 | 34.0 | 28.0 | 6.0 | 5.0 | 41.0 | 67.0 | 14.0 | 8.0 | 1.0 | 1.0 | 8.0 | 3.0 | 1.04 | 0.78 | 0.0 | 3.0 | 29.0 | 71.0 | 1.0 | 0.0 | 1.0 | 3.0 | 10.0 | 6.0 | 6.0 | 4.0 | 4.0 | 2.0 | 4.0 | 6.0 | 20.0 | 11.0 | 15.0 | 18.0 | 14.0 | 12.0 | 16.0 | 34.0 | 1.04 | 0.78 | 2.0 | 1.0 |
| m_mt_404678415 | 1758990600 | COMPETITION | AWAY | OPP_024 |  |  | 3.0 | 8.0 | 3.0 | 1.0 | 3.0 | 6.0 | 42.0 | 20.0 | 4.0 | 7.0 | 42.0 | 80.0 | 6.0 | 11.0 | 1.0 | 0.0 | 6.0 | 1.0 | 1.19 | 1.66 | 1.0 | 0.0 | 35.0 | 65.0 | 0.0 | 0.0 | 6.0 | 2.0 | 8.0 | 15.0 | 5.0 | 10.0 | 3.0 | 6.0 | 3.0 | 7.0 | 10.0 | 16.0 | 13.0 | 24.0 | 11.0 | 22.0 | 22.0 | 38.0 | 1.19 | 1.65 | 2.0 | 4.0 |
| m_mt_363781331 | 1759586400 | COMPETITION | AWAY | OPP_025 |  |  | 4.0 | 5.0 | 2.0 | 2.0 | 1.0 | 2.0 | 31.0 | 24.0 | 3.0 | 2.0 | 47.0 | 55.0 | 12.0 | 10.0 | 0.0 | 2.0 | 9.0 | 10.0 | 0.71 | 1.93 | 2.0 | 1.0 | 49.0 | 51.0 | 0.0 | 0.0 | 4.0 | 3.0 | 5.0 | 11.0 | 4.0 | 7.0 | 3.0 | 6.0 | 3.0 | 4.0 | 21.0 | 16.0 | 20.0 | 23.0 | 8.0 | 15.0 | 14.0 | 32.0 | 0.71 | 1.88 | 4.0 | 1.0 |
| m_mt_363782504 | 1760796000 | COMPETITION | HOME | OPP_026 | BACK_FOUR | BACK_FOUR | 3.0 | 11.0 | 2.0 | 0.0 | 3.0 | 5.0 | 36.0 | 40.0 | 2.0 | 2.0 | 47.0 | 65.0 | 5.0 | 12.0 | 2.0 | 0.0 | 7.0 | 8.0 | 0.75 | 0.78 | 2.0 | 2.0 | 41.0 | 59.0 | 0.0 | 0.0 | 3.0 | 1.0 | 5.0 | 8.0 | 3.0 | 8.0 | 2.0 | 3.0 | 3.0 | 8.0 | 14.0 | 15.0 | 17.0 | 26.0 | 8.0 | 16.0 | 17.0 | 38.0 | 0.65 | 0.83 |  |  |
| m_mt_252068300 | 1761400800 | COMPETITION | AWAY | OPP_027 |  |  | 1.0 | 4.0 | 2.0 | 2.0 | 4.0 | 4.0 | 33.0 | 18.0 | 1.0 | 9.0 | 55.0 | 61.0 | 13.0 | 15.0 | 2.0 | 1.0 | 8.0 | 3.0 | 1.31 | 0.9 | 2.0 | 3.0 | 32.0 | 68.0 | 0.0 | 0.0 | 6.0 | 2.0 | 7.0 | 10.0 | 2.0 | 5.0 | 4.0 | 7.0 | 3.0 | 6.0 | 14.0 | 8.0 | 13.0 | 15.0 | 10.0 | 16.0 | 17.0 | 26.0 | 1.31 | 0.9 | 1.0 | 1.0 |
| m_mt_469165990 | 1762200000 | COMPETITION | HOME | OPP_028 | BACK_THREE | BACK_FOUR | 6.0 | 2.0 | 1.0 | 1.0 | 7.0 | 3.0 | 21.0 | 45.0 | 4.0 | 1.0 | 80.0 | 47.0 | 10.0 | 12.0 | 1.0 | 1.0 | 5.0 | 8.0 | 1.23 | 0.89 | 2.0 | 0.0 | 61.0 | 39.0 | 0.0 | 0.0 | 1.0 | 2.0 | 12.0 | 5.0 | 7.0 | 3.0 | 3.0 | 2.0 | 5.0 | 3.0 | 14.0 | 14.0 | 17.0 | 21.0 | 17.0 | 8.0 | 29.0 | 19.0 | 1.22 | 0.89 | 3.0 | 2.0 |
| m_mt_010243952 | 1762623000 | COMPETITION | HOME | OPP_029 |  |  | 0.0 | 4.0 | 2.0 | 4.0 | 2.0 | 4.0 | 39.0 | 25.0 | 2.0 | 2.0 | 43.0 | 62.0 | 13.0 | 13.0 | 2.0 | 2.0 | 6.0 | 3.0 | 0.42 | 2.0 | 2.0 | 0.0 | 35.0 | 65.0 | 0.0 | 0.0 | 5.0 | 0.0 | 6.0 | 12.0 | 2.0 | 6.0 | 2.0 | 7.0 | 0.0 | 5.0 | 16.0 | 12.0 | 17.0 | 21.0 | 6.0 | 17.0 | 14.0 | 32.0 | 0.44 | 1.91 | 2.0 | 1.0 |
| m_mt_404678291 | 1763823600 | COMPETITION | AWAY | OPP_030 |  |  | 2.0 | 8.0 | 0.0 | 4.0 | 1.0 | 5.0 | 25.0 | 28.0 | 4.0 | 7.0 | 51.0 | 51.0 | 13.0 | 5.0 | 0.0 | 1.0 | 9.0 | 6.0 | 0.2 | 2.16 | 3.0 | 1.0 | 43.0 | 57.0 | 0.0 | 0.0 | 4.0 | 2.0 | 4.0 | 18.0 | 1.0 | 13.0 | 2.0 | 6.0 | 0.0 | 6.0 | 21.0 | 11.0 | 17.0 | 20.0 | 4.0 | 24.0 | 22.0 | 46.0 | 0.17 | 2.16 | 3.0 | 3.0 |

### Arm B — AWAY_TEAM match-level matrix (30 rows × 55 cols)

Columns: `match_alias, kickoff_unix, competition, venue, opponent_alias, own_formation_family, opponent_formation_family, accurate_crosses_for, accurate_crosses_against, big_chances_for, big_chances_against, blocked_shots_for, blocked_shots_against, clearances_for, clearances_against, corners_for, corners_against, final_third_entries_for, final_third_entries_against, fouls_for, fouls_against, goals_for, goals_against, interceptions_for, interceptions_against, npxg_for, npxg_against, offsides_for, offsides_against, possession_for, possession_against, red_cards_for, red_cards_against, saves_for, saves_against, shots_inside_box_for, shots_inside_box_against, shots_off_target_for, shots_off_target_against, shots_on_target_for, shots_on_target_against, shots_outside_box_for, shots_outside_box_against, tackles_for, tackles_against, throw_ins_for, throw_ins_against, total_shots_for, total_shots_against, touches_in_box_for, touches_in_box_against, xg_for, xg_against, yellow_cards_for, yellow_cards_against`

| match_alias | kickoff_unix | competition | venue | opponent_alias | own_formation_family | opponent_formation_family | accurate_crosses_for | accurate_crosses_against | big_chances_for | big_chances_against | blocked_shots_for | blocked_shots_against | clearances_for | clearances_against | corners_for | corners_against | final_third_entries_for | final_third_entries_against | fouls_for | fouls_against | goals_for | goals_against | interceptions_for | interceptions_against | npxg_for | npxg_against | offsides_for | offsides_against | possession_for | possession_against | red_cards_for | red_cards_against | saves_for | saves_against | shots_inside_box_for | shots_inside_box_against | shots_off_target_for | shots_off_target_against | shots_on_target_for | shots_on_target_against | shots_outside_box_for | shots_outside_box_against | tackles_for | tackles_against | throw_ins_for | throw_ins_against | total_shots_for | total_shots_against | touches_in_box_for | touches_in_box_against | xg_for | xg_against | yellow_cards_for | yellow_cards_against |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| m_mt_257076801 | 1736883000 | COMPETITION | AWAY | OPP_027 |  |  | 2.0 | 5.0 | 1.0 | 5.0 | 1.0 | 9.0 | 27.0 | 8.0 | 3.0 | 9.0 | 47.0 | 49.0 | 16.0 | 15.0 | 2.0 | 2.0 | 10.0 | 5.0 | 0.4 | 2.59 | 1.0 | 2.0 | 43.0 | 57.0 | 0.0 | 0.0 | 8.0 | 1.0 | 6.0 | 16.0 | 3.0 | 7.0 | 3.0 | 10.0 | 1.0 | 10.0 | 16.0 | 11.0 | 19.0 | 22.0 | 7.0 | 26.0 | 21.0 | 33.0 | 1.18 | 2.5 | 3.0 | 2.0 |
| m_mt_408688525 | 1737203400 | COMPETITION | AWAY | OPP_031 |  |  | 5.0 | 3.0 | 3.0 | 0.0 | 2.0 | 3.0 | 29.0 | 27.0 | 5.0 | 7.0 | 49.0 | 34.0 | 16.0 | 5.0 | 4.0 | 1.0 | 9.0 | 1.0 | 2.05 | 0.83 | 0.0 | 1.0 | 44.0 | 56.0 | 0.0 | 0.0 | 2.0 | 5.0 | 12.0 | 5.0 | 5.0 | 2.0 | 7.0 | 3.0 | 2.0 | 3.0 | 19.0 | 11.0 | 10.0 | 23.0 | 14.0 | 8.0 | 29.0 | 28.0 | 2.08 | 0.47 | 4.0 | 1.0 |
| m_mt_257077911 | 1737817200 | COMPETITION | HOME | OPP_024 |  |  | 2.0 | 6.0 | 3.0 | 1.0 | 3.0 | 5.0 | 34.0 | 24.0 | 3.0 | 9.0 | 53.0 | 56.0 | 9.0 | 12.0 | 5.0 | 0.0 | 9.0 | 5.0 | 1.71 | 0.98 | 2.0 | 2.0 | 51.0 | 49.0 | 0.0 | 0.0 | 4.0 | 5.0 | 11.0 | 11.0 | 3.0 | 9.0 | 10.0 | 4.0 | 5.0 | 7.0 | 22.0 | 11.0 | 10.0 | 20.0 | 16.0 | 18.0 | 31.0 | 34.0 | 1.69 | 0.98 | 2.0 | 3.0 |
| m_mt_257077593 | 1738422000 | COMPETITION | HOME | OPP_032 | BACK_FOUR | BACK_FOUR | 4.0 | 3.0 | 3.0 | 4.0 | 3.0 | 7.0 | 24.0 | 26.0 | 3.0 | 3.0 | 60.0 | 49.0 | 15.0 | 9.0 | 0.0 | 2.0 | 10.0 | 11.0 | 1.6 | 1.74 | 4.0 | 1.0 | 49.0 | 51.0 | 0.0 | 0.0 | 5.0 | 4.0 | 8.0 | 12.0 | 8.0 | 5.0 | 3.0 | 7.0 | 6.0 | 7.0 | 19.0 | 18.0 | 14.0 | 21.0 | 14.0 | 19.0 | 29.0 | 34.0 | 1.58 | 2.52 | 2.0 | 3.0 |
| m_mt_196566965 | 1739631600 | COMPETITION | AWAY | OPP_033 |  |  | 5.0 | 4.0 | 3.0 | 1.0 | 4.0 | 4.0 | 26.0 | 28.0 | 6.0 | 4.0 | 60.0 | 53.0 | 15.0 | 13.0 | 3.0 | 1.0 | 9.0 | 11.0 | 1.2 | 0.79 |  |  | 55.0 | 45.0 | 0.0 | 0.0 | 3.0 | 5.0 | 10.0 | 7.0 | 3.0 | 3.0 | 7.0 | 4.0 | 4.0 | 4.0 | 16.0 | 27.0 | 27.0 | 16.0 | 14.0 | 11.0 | 30.0 | 25.0 | 1.2 | 0.79 | 3.0 | 1.0 |
| m_mt_830900363 | 1740236400 | COMPETITION | HOME | OPP_026 |  |  | 3.0 | 2.0 | 1.0 | 3.0 | 3.0 | 3.0 | 27.0 | 40.0 | 6.0 | 7.0 | 75.0 | 42.0 | 17.0 | 9.0 | 0.0 | 1.0 | 11.0 | 7.0 | 0.89 | 2.0 | 1.0 | 1.0 | 45.0 | 55.0 | 1.0 | 0.0 | 5.0 | 3.0 | 6.0 | 8.0 | 2.0 | 5.0 | 3.0 | 5.0 | 2.0 | 5.0 | 13.0 | 30.0 | 23.0 | 16.0 | 8.0 | 13.0 | 23.0 | 15.0 | 0.62 | 1.97 | 3.0 | 3.0 |
| m_mt_196566986 | 1740511800 | COMPETITION | AWAY | OPP_034 |  |  | 8.0 | 3.0 | 2.0 | 5.0 | 7.0 | 3.0 | 26.0 | 33.0 | 9.0 | 1.0 | 62.0 | 53.0 | 14.0 | 12.0 | 1.0 | 2.0 | 12.0 | 6.0 | 1.46 | 1.63 | 4.0 | 0.0 | 57.0 | 43.0 | 0.0 | 0.0 | 2.0 | 4.0 | 12.0 | 7.0 | 7.0 | 4.0 | 5.0 | 4.0 | 7.0 | 4.0 | 25.0 | 21.0 | 18.0 | 27.0 | 19.0 | 11.0 | 42.0 | 25.0 | 1.46 | 2.42 | 1.0 | 2.0 |
| m_mt_745355347 | 1741528800 | COMPETITION | AWAY | OPP_035 |  |  | 5.0 | 6.0 | 5.0 | 1.0 | 5.0 | 5.0 | 28.0 | 20.0 | 6.0 | 3.0 | 41.0 | 56.0 | 16.0 | 15.0 | 2.0 | 2.0 | 15.0 | 8.0 | 2.2 | 0.74 | 3.0 | 0.0 | 39.0 | 61.0 | 0.0 | 0.0 | 2.0 | 6.0 | 15.0 | 8.0 | 4.0 | 3.0 | 8.0 | 4.0 | 2.0 | 4.0 | 29.0 | 12.0 | 13.0 | 36.0 | 17.0 | 12.0 | 27.0 | 29.0 | 2.2 | 1.53 | 3.0 | 3.0 |
| m_mt_013233224 | 1742059800 | COMPETITION | HOME | OPP_021 |  |  | 9.0 | 2.0 | 3.0 | 2.0 | 5.0 | 1.0 | 33.0 | 39.0 | 4.0 | 3.0 | 71.0 | 61.0 | 13.0 | 7.0 | 1.0 | 2.0 | 9.0 | 8.0 | 1.67 | 0.83 | 4.0 | 2.0 | 59.0 | 41.0 | 0.0 | 0.0 | 2.0 | 5.0 | 13.0 | 7.0 | 7.0 | 5.0 | 5.0 | 4.0 | 4.0 | 3.0 | 16.0 | 18.0 | 20.0 | 22.0 | 17.0 | 10.0 | 44.0 | 26.0 | 1.67 | 0.83 | 3.0 | 0.0 |
| m_mt_629493560 | 1743619500 | COMPETITION | HOME | OPP_036 |  |  | 8.0 | 2.0 | 2.0 | 3.0 | 7.0 | 2.0 | 18.0 | 58.0 | 8.0 | 3.0 | 98.0 | 50.0 | 14.0 | 15.0 | 1.0 | 2.0 | 9.0 | 6.0 | 2.02 | 1.17 |  |  | 64.0 | 36.0 | 0.0 | 0.0 | 0.0 | 5.0 | 11.0 | 7.0 | 10.0 | 6.0 | 7.0 | 2.0 | 13.0 | 3.0 | 16.0 | 14.0 | 19.0 | 21.0 | 24.0 | 10.0 | 28.0 | 16.0 | 1.87 | 1.17 | 1.0 | 2.0 |
| m_mt_013234510 | 1743861600 | COMPETITION | AWAY | OPP_019 |  |  | 7.0 | 5.0 | 2.0 | 1.0 | 3.0 | 1.0 | 28.0 | 30.0 | 7.0 | 4.0 | 52.0 | 58.0 | 13.0 | 13.0 | 2.0 | 2.0 | 7.0 | 7.0 | 2.14 | 0.69 | 1.0 | 4.0 | 44.0 | 56.0 | 0.0 | 0.0 | 2.0 | 4.0 | 7.0 | 6.0 | 4.0 | 5.0 | 4.0 | 3.0 | 4.0 | 3.0 | 22.0 | 11.0 | 17.0 | 25.0 | 11.0 | 9.0 | 21.0 | 16.0 | 2.12 | 0.69 | 2.0 | 2.0 |
| m_mt_973123668 | 1744657200 | COMPETITION | HOME | OPP_030 | BACK_FOUR | BACK_FOUR | 5.0 | 7.0 | 2.0 | 1.0 | 4.0 | 4.0 | 46.0 | 24.0 | 6.0 | 9.0 | 52.0 | 77.0 | 11.0 | 10.0 | 1.0 | 0.0 | 4.0 | 9.0 | 1.44 | 1.07 | 2.0 | 1.0 | 41.0 | 59.0 | 0.0 | 0.0 | 7.0 | 2.0 | 8.0 | 7.0 | 5.0 | 1.0 | 3.0 | 7.0 | 4.0 | 5.0 | 15.0 | 12.0 | 21.0 | 25.0 | 12.0 | 12.0 | 15.0 | 37.0 | 1.46 | 1.07 | 3.0 | 2.0 |
| m_mt_629493032 | 1745071200 | COMPETITION | AWAY | OPP_022 |  |  | 7.0 | 2.0 | 1.0 | 0.0 | 5.0 | 3.0 | 34.0 | 32.0 | 4.0 | 5.0 | 61.0 | 44.0 | 10.0 | 13.0 | 0.0 | 0.0 | 6.0 | 7.0 | 0.73 | 0.37 | 1.0 | 1.0 | 73.0 | 27.0 | 0.0 | 1.0 | 0.0 | 4.0 | 9.0 | 3.0 | 6.0 | 2.0 | 4.0 | 0.0 | 6.0 | 2.0 | 12.0 | 10.0 | 18.0 | 23.0 | 15.0 | 5.0 | 30.0 | 16.0 | 0.72 | 0.37 | 4.0 | 5.0 |
| m_mt_408687170 | 1745758800 | COMPETITION | HOME | OPP_025 |  |  | 4.0 | 2.0 | 1.0 | 2.0 | 1.0 | 13.0 | 34.0 | 18.0 | 5.0 | 10.0 | 35.0 | 49.0 | 11.0 | 12.0 | 1.0 | 1.0 | 11.0 | 9.0 | 0.53 | 2.52 | 2.0 | 2.0 | 38.0 | 62.0 | 1.0 | 0.0 | 5.0 | 0.0 | 5.0 | 17.0 | 6.0 | 6.0 | 1.0 | 6.0 | 3.0 | 8.0 | 9.0 | 15.0 | 24.0 | 21.0 | 8.0 | 25.0 | 14.0 | 44.0 | 0.53 | 2.52 | 4.0 | 2.0 |
| m_mt_584142347 | 1746289800 | COMPETITION | AWAY | OPP_029 |  |  | 6.0 | 1.0 | 3.0 | 4.0 | 2.0 | 4.0 | 17.0 | 15.0 | 3.0 | 2.0 | 46.0 | 42.0 | 16.0 | 7.0 | 2.0 | 1.0 | 9.0 | 8.0 | 0.97 | 1.42 | 0.0 | 3.0 | 50.0 | 50.0 | 0.0 | 0.0 | 3.0 | 0.0 | 6.0 | 12.0 | 5.0 | 5.0 | 2.0 | 4.0 | 3.0 | 1.0 | 12.0 | 12.0 | 13.0 | 14.0 | 9.0 | 13.0 | 10.0 | 32.0 | 0.97 | 1.42 | 2.0 | 0.0 |
| m_mt_196560713 | 1746894600 | COMPETITION | HOME | OPP_023 | BACK_FOUR | BACK_FOUR | 5.0 | 2.0 | 2.0 | 2.0 | 3.0 | 0.0 | 33.0 | 23.0 | 10.0 | 0.0 | 79.0 | 53.0 | 19.0 | 12.0 | 0.0 | 1.0 | 4.0 | 5.0 | 0.84 | 0.99 | 2.0 | 0.0 | 66.0 | 34.0 | 0.0 | 1.0 | 2.0 | 4.0 | 8.0 | 4.0 | 3.0 | 3.0 | 4.0 | 3.0 | 2.0 | 2.0 | 16.0 | 13.0 | 15.0 | 17.0 | 10.0 | 6.0 | 27.0 | 15.0 | 0.8 | 0.98 | 4.0 | 5.0 |
| m_mt_838200836 | 1747767600 | COMPETITION | AWAY | OPP_037 |  |  | 6.0 | 2.0 | 2.0 | 3.0 | 2.0 | 2.0 | 25.0 | 19.0 | 1.0 | 3.0 | 57.0 | 56.0 | 13.0 | 7.0 | 1.0 | 3.0 | 5.0 | 7.0 | 1.12 | 1.54 | 3.0 | 2.0 | 43.0 | 57.0 | 1.0 | 1.0 | 2.0 | 1.0 | 6.0 | 5.0 | 4.0 | 5.0 | 2.0 | 5.0 | 2.0 | 7.0 | 10.0 | 8.0 | 14.0 | 15.0 | 8.0 | 12.0 | 17.0 | 21.0 | 1.12 | 1.54 | 3.0 | 1.0 |
| m_mt_629493534 | 1748185200 | COMPETITION | HOME | OPP_038 |  |  | 7.0 | 2.0 | 3.0 | 0.0 | 6.0 | 0.0 | 11.0 | 30.0 | 6.0 | 1.0 | 63.0 | 38.0 | 19.0 | 16.0 | 2.0 | 0.0 | 7.0 | 6.0 | 1.62 | 0.27 | 2.0 | 2.0 | 63.0 | 37.0 | 0.0 | 0.0 | 0.0 | 5.0 | 10.0 | 2.0 | 7.0 | 3.0 | 7.0 | 0.0 | 10.0 | 1.0 | 15.0 | 18.0 | 23.0 | 9.0 | 20.0 | 3.0 | 52.0 | 12.0 | 1.62 | 0.27 | 0.0 | 2.0 |
| m_mt_585124389 | 1755284400 | COMPETITION | AWAY | OPP_032 |  |  | 5.0 | 5.0 | 3.0 | 3.0 | 3.0 | 2.0 | 45.0 | 41.0 | 7.0 | 6.0 | 45.0 | 61.0 | 10.0 | 7.0 | 2.0 | 4.0 | 11.0 | 4.0 | 1.7 | 2.21 | 2.0 | 2.0 | 39.0 | 61.0 | 0.0 | 0.0 | 6.0 | 1.0 | 8.0 | 15.0 | 4.0 | 7.0 | 3.0 | 10.0 | 2.0 | 4.0 | 20.0 | 16.0 | 17.0 | 27.0 | 10.0 | 19.0 | 28.0 | 36.0 | 1.7 | 2.21 | 2.0 | 1.0 |
| m_mt_979812497 | 1755957600 | COMPETITION | HOME | OPP_026 | BACK_FOUR | BACK_THREE | 3.0 | 5.0 | 2.0 | 0.0 | 5.0 | 2.0 | 32.0 | 30.0 | 8.0 | 3.0 | 70.0 | 61.0 | 13.0 | 16.0 | 1.0 | 0.0 | 6.0 | 9.0 | 1.29 | 0.47 | 2.0 | 2.0 | 59.0 | 41.0 | 0.0 | 1.0 | 1.0 | 3.0 | 8.0 | 3.0 | 5.0 | 3.0 | 4.0 | 1.0 | 6.0 | 3.0 | 12.0 | 21.0 | 24.0 | 18.0 | 14.0 | 6.0 | 30.0 | 14.0 | 1.29 | 0.46 | 2.0 | 4.0 |
| m_mt_404678285 | 1756562400 | COMPETITION | AWAY | OPP_035 |  |  | 5.0 | 5.0 | 3.0 | 0.0 | 5.0 | 1.0 | 31.0 | 33.0 | 8.0 | 0.0 | 61.0 | 67.0 | 13.0 | 17.0 | 1.0 | 0.0 | 9.0 | 4.0 | 1.58 | 0.19 | 3.0 | 2.0 | 39.0 | 61.0 | 0.0 | 0.0 | 1.0 | 5.0 | 15.0 | 3.0 | 9.0 | 3.0 | 6.0 | 1.0 | 5.0 | 2.0 | 28.0 | 16.0 | 15.0 | 25.0 | 20.0 | 5.0 | 29.0 | 18.0 | 1.59 | 0.19 | 4.0 | 2.0 |
| m_mt_252067171 | 1757772000 | COMPETITION | HOME | OPP_034 |  |  | 4.0 | 3.0 | 1.0 | 2.0 | 4.0 | 2.0 | 35.0 | 35.0 | 4.0 | 4.0 | 65.0 | 56.0 | 16.0 | 10.0 | 2.0 | 1.0 | 3.0 | 6.0 | 0.66 | 0.61 | 1.0 | 0.0 | 51.0 | 49.0 | 0.0 | 0.0 | 1.0 | 3.0 | 7.0 | 5.0 | 4.0 | 2.0 | 5.0 | 2.0 | 6.0 | 1.0 | 18.0 | 20.0 | 17.0 | 20.0 | 13.0 | 6.0 | 28.0 | 24.0 | 1.45 | 0.62 | 4.0 | 4.0 |
| m_mt_252067239 | 1758459600 | COMPETITION | HOME | OPP_031 |  |  | 0.0 | 2.0 |  |  | 6.0 | 1.0 | 28.0 | 35.0 | 5.0 | 2.0 | 71.0 | 67.0 | 7.0 | 10.0 | 0.0 | 0.0 | 16.0 | 8.0 | 0.46 | 0.23 | 3.0 | 2.0 | 56.0 | 44.0 | 0.0 | 0.0 | 1.0 | 2.0 | 4.0 | 1.0 | 3.0 | 2.0 | 2.0 | 1.0 | 7.0 | 3.0 | 15.0 | 19.0 | 21.0 | 28.0 | 11.0 | 4.0 | 16.0 | 17.0 | 0.46 | 0.14 | 2.0 | 1.0 |
| m_mt_626439691 | 1758981600 | COMPETITION | AWAY | OPP_005 |  |  | 3.0 | 9.0 | 1.0 | 3.0 | 3.0 | 6.0 | 30.0 | 25.0 | 4.0 | 7.0 | 60.0 | 48.0 | 13.0 | 12.0 | 2.0 | 2.0 | 7.0 | 9.0 | 0.75 | 1.84 | 2.0 | 0.0 | 59.0 | 41.0 | 0.0 | 0.0 | 6.0 | 3.0 | 7.0 | 16.0 | 4.0 | 5.0 | 5.0 | 8.0 | 5.0 | 3.0 | 23.0 | 27.0 | 28.0 | 14.0 | 12.0 | 19.0 | 21.0 | 35.0 | 0.82 | 1.84 | 2.0 | 2.0 |
| m_mt_252067281 | 1759518000 | COMPETITION | HOME | OPP_030 |  |  | 1.0 | 3.0 | 1.0 | 1.0 | 3.0 | 4.0 | 23.0 | 38.0 | 4.0 | 3.0 | 89.0 | 55.0 | 8.0 | 10.0 | 3.0 | 1.0 | 8.0 | 7.0 | 1.2 | 0.88 | 2.0 | 2.0 | 54.0 | 46.0 | 0.0 | 0.0 | 3.0 | 3.0 | 6.0 | 5.0 | 2.0 | 4.0 | 6.0 | 4.0 | 5.0 | 7.0 | 10.0 | 11.0 | 28.0 | 19.0 | 11.0 | 12.0 | 30.0 | 17.0 | 1.12 | 0.88 | 0.0 | 1.0 |
| m_mt_363782552 | 1760796000 | COMPETITION | AWAY | OPP_022 |  |  | 2.0 | 6.0 | 3.0 | 7.0 | 0.0 | 7.0 | 47.0 | 32.0 | 5.0 | 6.0 | 43.0 | 60.0 | 16.0 | 8.0 | 3.0 | 3.0 | 12.0 | 6.0 | 2.03 | 3.5 | 3.0 | 3.0 | 48.0 | 52.0 | 0.0 | 0.0 | 4.0 | 2.0 | 5.0 | 15.0 | 3.0 | 6.0 | 5.0 | 7.0 | 3.0 | 5.0 | 18.0 | 23.0 | 14.0 | 17.0 | 8.0 | 20.0 | 19.0 | 41.0 | 2.03 | 4.44 | 4.0 | 1.0 |
| m_mt_585123682 | 1761487200 | COMPETITION | HOME | OPP_024 |  |  | 2.0 | 3.0 |  |  | 4.0 | 2.0 | 16.0 | 18.0 | 6.0 | 4.0 | 45.0 | 62.0 | 17.0 | 7.0 | 2.0 | 0.0 | 12.0 | 9.0 | 0.58 | 0.37 | 3.0 | 0.0 | 52.0 | 48.0 | 0.0 | 0.0 | 4.0 | 3.0 | 5.0 | 3.0 | 4.0 | 2.0 | 5.0 | 4.0 | 8.0 | 5.0 | 9.0 | 19.0 | 21.0 | 19.0 | 13.0 | 8.0 | 16.0 | 7.0 | 0.58 | 0.37 | 3.0 | 1.0 |
| m_mt_585123649 | 1762101000 | COMPETITION | AWAY | OPP_037 | BACK_FOUR | BACK_FOUR | 1.0 | 4.0 | 1.0 | 4.0 | 1.0 | 3.0 | 27.0 | 23.0 | 4.0 | 9.0 | 55.0 | 53.0 | 11.0 | 8.0 | 1.0 | 3.0 | 5.0 | 9.0 | 0.63 | 2.22 | 3.0 | 0.0 | 52.0 | 48.0 | 0.0 | 0.0 | 4.0 | 4.0 | 4.0 | 13.0 | 2.0 | 4.0 | 5.0 | 8.0 | 4.0 | 2.0 | 23.0 | 10.0 | 7.0 | 19.0 | 8.0 | 15.0 | 17.0 | 43.0 | 0.72 | 2.22 | 2.0 | 2.0 |
| m_mt_010243910 | 1762696800 | COMPETITION | AWAY | OPP_023 |  |  | 2.0 | 3.0 | 2.0 | 2.0 | 4.0 | 6.0 | 35.0 | 22.0 | 9.0 | 6.0 | 43.0 | 54.0 | 20.0 | 8.0 | 0.0 | 4.0 | 11.0 | 6.0 | 0.82 | 1.7 | 2.0 | 0.0 | 48.0 | 52.0 | 0.0 | 0.0 | 4.0 | 3.0 | 6.0 | 10.0 | 5.0 | 2.0 | 3.0 | 8.0 | 6.0 | 6.0 | 16.0 | 20.0 | 22.0 | 15.0 | 12.0 | 16.0 | 12.0 | 27.0 | 1.61 | 1.7 | 2.0 | 2.0 |
| m_mt_585124351 | 1763823600 | COMPETITION | HOME | OPP_019 |  |  | 15.0 | 1.0 | 4.0 | 0.0 | 7.0 | 1.0 | 11.0 | 57.0 | 9.0 | 2.0 | 95.0 | 49.0 | 9.0 | 10.0 | 2.0 | 2.0 | 7.0 | 9.0 | 3.31 | 0.64 | 2.0 | 2.0 | 76.0 | 24.0 | 0.0 | 0.0 | 0.0 | 10.0 | 22.0 | 4.0 | 11.0 | 2.0 | 10.0 | 2.0 | 6.0 | 1.0 | 19.0 | 13.0 | 27.0 | 10.0 | 28.0 | 5.0 | 57.0 | 8.0 | 4.05 | 0.65 | 3.0 | 2.0 |

### Arm B — derived summaries (DERIVED_SUMMARY), HOME 240 + AWAY 240

HOME_TEAM (metric·side·window·venue = value [n, reliability]):

- accurate_crosses·FOR·ALL_PRIOR·ALL = 3.8 [n=30, HIGH]
- accurate_crosses·FOR·W5·ALL = 2.4 [n=5, LOW]
- accurate_crosses·FOR·W10·ALL = 2.8 [n=10, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·HOME = 4.5 [n=16, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·AWAY = 3.0 [n=14, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·ALL = 4.6667 [n=30, HIGH]
- accurate_crosses·AGAINST·W5·ALL = 5.8 [n=5, LOW]
- accurate_crosses·AGAINST·W10·ALL = 5.7 [n=10, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·HOME = 3.75 [n=16, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·AWAY = 5.7143 [n=14, MEDIUM]
- big_chances·FOR·ALL_PRIOR·ALL = 1.4667 [n=30, HIGH]
- big_chances·FOR·W5·ALL = 1.4 [n=5, LOW]
- big_chances·FOR·W10·ALL = 1.5 [n=10, MEDIUM]
- big_chances·FOR·ALL_PRIOR·HOME = 1.8125 [n=16, MEDIUM]
- big_chances·FOR·ALL_PRIOR·AWAY = 1.0714 [n=14, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·ALL = 1.8 [n=30, HIGH]
- big_chances·AGAINST·W5·ALL = 2.2 [n=5, LOW]
- big_chances·AGAINST·W10·ALL = 2.1 [n=10, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·HOME = 1.4375 [n=16, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·AWAY = 2.2143 [n=14, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·ALL = 3.8667 [n=30, HIGH]
- blocked_shots·FOR·W5·ALL = 3.4 [n=5, LOW]
- blocked_shots·FOR·W10·ALL = 3.0 [n=10, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·HOME = 5.125 [n=16, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·AWAY = 2.4286 [n=14, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·ALL = 3.9667 [n=30, HIGH]
- blocked_shots·AGAINST·W5·ALL = 4.2 [n=5, LOW]
- blocked_shots·AGAINST·W10·ALL = 4.0 [n=10, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·HOME = 2.875 [n=16, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·AWAY = 5.2143 [n=14, MEDIUM]
- clearances·FOR·ALL_PRIOR·ALL = 29.5 [n=30, HIGH]
- clearances·FOR·W5·ALL = 30.8 [n=5, LOW]
- clearances·FOR·W10·ALL = 32.9 [n=10, MEDIUM]
- clearances·FOR·ALL_PRIOR·HOME = 26.375 [n=16, MEDIUM]
- clearances·FOR·ALL_PRIOR·AWAY = 33.0714 [n=14, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·ALL = 27.9333 [n=30, HIGH]
- clearances·AGAINST·W5·ALL = 31.2 [n=5, LOW]
- clearances·AGAINST·W10·ALL = 28.7 [n=10, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·HOME = 34.6875 [n=16, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·AWAY = 20.2143 [n=14, MEDIUM]
- corners·FOR·ALL_PRIOR·ALL = 4.6667 [n=30, HIGH]
- corners·FOR·W5·ALL = 2.6 [n=5, LOW]
- corners·FOR·W10·ALL = 3.2 [n=10, MEDIUM]
- corners·FOR·ALL_PRIOR·HOME = 5.5625 [n=16, MEDIUM]
- corners·FOR·ALL_PRIOR·AWAY = 3.6429 [n=14, MEDIUM]
- corners·AGAINST·ALL_PRIOR·ALL = 3.8 [n=30, HIGH]
- corners·AGAINST·W5·ALL = 4.2 [n=5, LOW]
- corners·AGAINST·W10·ALL = 4.4 [n=10, MEDIUM]
- corners·AGAINST·ALL_PRIOR·HOME = 2.5 [n=16, MEDIUM]
- corners·AGAINST·ALL_PRIOR·AWAY = 5.2857 [n=14, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·ALL = 57.1333 [n=30, HIGH]
- final_third_entries·FOR·W5·ALL = 55.2 [n=5, LOW]
- final_third_entries·FOR·W10·ALL = 53.6 [n=10, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·HOME = 63.375 [n=16, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·AWAY = 50.0 [n=14, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·ALL = 59.4667 [n=30, HIGH]
- final_third_entries·AGAINST·W5·ALL = 57.2 [n=5, LOW]
- final_third_entries·AGAINST·W10·ALL = 57.7 [n=10, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·HOME = 54.125 [n=16, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·AWAY = 65.5714 [n=14, MEDIUM]
- fouls·FOR·ALL_PRIOR·ALL = 10.4333 [n=30, HIGH]
- fouls·FOR·W5·ALL = 10.8 [n=5, LOW]
- fouls·FOR·W10·ALL = 10.5 [n=10, MEDIUM]
- fouls·FOR·ALL_PRIOR·HOME = 9.9375 [n=16, MEDIUM]
- fouls·FOR·ALL_PRIOR·AWAY = 11.0 [n=14, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·ALL = 12.1 [n=30, HIGH]
- fouls·AGAINST·W5·ALL = 11.4 [n=5, LOW]
- fouls·AGAINST·W10·ALL = 10.8 [n=10, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·HOME = 13.375 [n=16, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·AWAY = 10.6429 [n=14, MEDIUM]
- goals·FOR·ALL_PRIOR·ALL = 1.0667 [n=30, HIGH]
- goals·FOR·W5·ALL = 1.4 [n=5, LOW]
- goals·FOR·W10·ALL = 1.1 [n=10, MEDIUM]
- goals·FOR·ALL_PRIOR·HOME = 1.3125 [n=16, MEDIUM]
- goals·FOR·ALL_PRIOR·AWAY = 0.7857 [n=14, MEDIUM]
- goals·AGAINST·ALL_PRIOR·ALL = 1.1 [n=30, HIGH]
- goals·AGAINST·W5·ALL = 1.0 [n=5, LOW]
- goals·AGAINST·W10·ALL = 0.9 [n=10, MEDIUM]
- goals·AGAINST·ALL_PRIOR·HOME = 0.9375 [n=16, MEDIUM]
- goals·AGAINST·ALL_PRIOR·AWAY = 1.2857 [n=14, MEDIUM]
- interceptions·FOR·ALL_PRIOR·ALL = 6.8667 [n=30, HIGH]
- interceptions·FOR·W5·ALL = 7.0 [n=5, LOW]
- interceptions·FOR·W10·ALL = 7.5 [n=10, MEDIUM]
- interceptions·FOR·ALL_PRIOR·HOME = 6.125 [n=16, MEDIUM]
- interceptions·FOR·ALL_PRIOR·AWAY = 7.7143 [n=14, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·ALL = 6.2 [n=30, HIGH]
- interceptions·AGAINST·W5·ALL = 5.6 [n=5, LOW]
- interceptions·AGAINST·W10·ALL = 5.2 [n=10, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·HOME = 6.625 [n=16, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·AWAY = 5.7143 [n=14, MEDIUM]
- npxg·FOR·ALL_PRIOR·ALL = 1.0023 [n=30, HIGH]
- npxg·FOR·W5·ALL = 0.782 [n=5, LOW]
- npxg·FOR·W10·ALL = 0.801 [n=10, MEDIUM]
- npxg·FOR·ALL_PRIOR·HOME = 1.19 [n=16, MEDIUM]
- npxg·FOR·ALL_PRIOR·AWAY = 0.7879 [n=14, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·ALL = 1.181 [n=30, HIGH]
- npxg·AGAINST·W5·ALL = 1.346 [n=5, LOW]
- npxg·AGAINST·W10·ALL = 1.329 [n=10, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·HOME = 0.795 [n=16, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·AWAY = 1.6221 [n=14, MEDIUM]
- offsides·FOR·ALL_PRIOR·ALL = 1.8929 [n=28, HIGH]
- offsides·FOR·W5·ALL = 2.2 [n=5, LOW]
- offsides·FOR·W10·ALL = 1.6 [n=10, MEDIUM]
- offsides·FOR·ALL_PRIOR·HOME = 1.7333 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·AWAY = 2.0769 [n=13, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·ALL = 1.4643 [n=28, HIGH]
- offsides·AGAINST·W5·ALL = 1.2 [n=5, LOW]
- offsides·AGAINST·W10·ALL = 1.3 [n=10, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·HOME = 1.6667 [n=15, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·AWAY = 1.2308 [n=13, MEDIUM]
- possession·FOR·ALL_PRIOR·ALL = 48.1667 [n=30, HIGH]
- possession·FOR·W5·ALL = 42.4 [n=5, LOW]
- possession·FOR·W10·ALL = 42.3 [n=10, MEDIUM]
- possession·FOR·ALL_PRIOR·HOME = 52.75 [n=16, MEDIUM]
- possession·FOR·ALL_PRIOR·AWAY = 42.9286 [n=14, MEDIUM]
- possession·AGAINST·ALL_PRIOR·ALL = 51.8333 [n=30, HIGH]
- possession·AGAINST·W5·ALL = 57.6 [n=5, LOW]
- possession·AGAINST·W10·ALL = 57.7 [n=10, MEDIUM]
- possession·AGAINST·ALL_PRIOR·HOME = 47.25 [n=16, MEDIUM]
- possession·AGAINST·ALL_PRIOR·AWAY = 57.0714 [n=14, MEDIUM]
- red_cards·FOR·ALL_PRIOR·ALL = 0.0667 [n=30, HIGH]
- red_cards·FOR·W5·ALL = 0.0 [n=5, LOW]
- red_cards·FOR·W10·ALL = 0.1 [n=10, MEDIUM]
- red_cards·FOR·ALL_PRIOR·HOME = 0.0625 [n=16, MEDIUM]
- red_cards·FOR·ALL_PRIOR·AWAY = 0.0714 [n=14, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·ALL = 0.0 [n=30, HIGH]
- red_cards·AGAINST·W5·ALL = 0.0 [n=5, LOW]
- red_cards·AGAINST·W10·ALL = 0.0 [n=10, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·HOME = 0.0 [n=16, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·AWAY = 0.0 [n=14, MEDIUM]
- saves·FOR·ALL_PRIOR·ALL = 2.6 [n=30, HIGH]
- saves·FOR·W5·ALL = 3.8 [n=5, LOW]
- saves·FOR·W10·ALL = 3.9 [n=10, MEDIUM]
- saves·FOR·ALL_PRIOR·HOME = 1.9375 [n=16, MEDIUM]
- saves·FOR·ALL_PRIOR·AWAY = 3.3571 [n=14, MEDIUM]
- saves·AGAINST·ALL_PRIOR·ALL = 2.2667 [n=30, HIGH]
- saves·AGAINST·W5·ALL = 1.4 [n=5, LOW]
- saves·AGAINST·W10·ALL = 1.6 [n=10, MEDIUM]
- saves·AGAINST·ALL_PRIOR·HOME = 2.375 [n=16, MEDIUM]
- saves·AGAINST·ALL_PRIOR·AWAY = 2.1429 [n=14, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·ALL = 7.7 [n=30, HIGH]
- shots_inside_box·FOR·W5·ALL = 6.8 [n=5, LOW]
- shots_inside_box·FOR·W10·ALL = 7.1 [n=10, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·HOME = 9.625 [n=16, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·AWAY = 5.5 [n=14, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·ALL = 7.7 [n=30, HIGH]
- shots_inside_box·AGAINST·W5·ALL = 10.6 [n=5, LOW]
- shots_inside_box·AGAINST·W10·ALL = 9.8 [n=10, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·HOME = 5.3125 [n=16, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·AWAY = 10.4286 [n=14, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·ALL = 3.6667 [n=30, HIGH]
- shots_off_target·FOR·W5·ALL = 3.0 [n=5, LOW]
- shots_off_target·FOR·W10·ALL = 4.0 [n=10, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·HOME = 4.625 [n=16, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·AWAY = 2.5714 [n=14, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·ALL = 4.9667 [n=30, HIGH]
- shots_off_target·AGAINST·W5·ALL = 7.0 [n=5, LOW]
- shots_off_target·AGAINST·W10·ALL = 6.2 [n=10, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·HOME = 3.3125 [n=16, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·AWAY = 6.8571 [n=14, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·ALL = 3.3 [n=30, HIGH]
- shots_on_target·FOR·W5·ALL = 2.6 [n=5, LOW]
- shots_on_target·FOR·W10·ALL = 2.6 [n=10, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·HOME = 3.625 [n=16, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·AWAY = 2.9286 [n=14, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·ALL = 3.7667 [n=30, HIGH]
- shots_on_target·AGAINST·W5·ALL = 5.0 [n=5, LOW]
- shots_on_target·AGAINST·W10·ALL = 4.9 [n=10, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·HOME = 2.8125 [n=16, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·AWAY = 4.8571 [n=14, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·ALL = 3.1333 [n=30, HIGH]
- shots_outside_box·FOR·W5·ALL = 2.2 [n=5, LOW]
- shots_outside_box·FOR·W10·ALL = 2.5 [n=10, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·HOME = 3.75 [n=16, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·AWAY = 2.4286 [n=14, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·ALL = 5.0 [n=30, HIGH]
- shots_outside_box·AGAINST·W5·ALL = 5.6 [n=5, LOW]
- shots_outside_box·AGAINST·W10·ALL = 5.3 [n=10, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·HOME = 3.6875 [n=16, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·AWAY = 6.5 [n=14, MEDIUM]
- tackles·FOR·ALL_PRIOR·ALL = 17.0 [n=30, HIGH]
- tackles·FOR·W5·ALL = 15.8 [n=5, LOW]
- tackles·FOR·W10·ALL = 17.1 [n=10, MEDIUM]
- tackles·FOR·ALL_PRIOR·HOME = 16.75 [n=16, MEDIUM]
- tackles·FOR·ALL_PRIOR·AWAY = 17.2857 [n=14, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·ALL = 17.0 [n=30, HIGH]
- tackles·AGAINST·W5·ALL = 12.0 [n=5, LOW]
- tackles·AGAINST·W10·ALL = 12.2 [n=10, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·HOME = 16.9375 [n=16, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·AWAY = 17.0714 [n=14, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·ALL = 19.1 [n=30, HIGH]
- throw_ins·FOR·W5·ALL = 16.2 [n=5, LOW]
- throw_ins·FOR·W10·ALL = 17.2 [n=10, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·HOME = 20.375 [n=16, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·AWAY = 17.6429 [n=14, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·ALL = 19.2 [n=30, HIGH]
- throw_ins·AGAINST·W5·ALL = 20.6 [n=5, LOW]
- throw_ins·AGAINST·W10·ALL = 20.7 [n=10, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·HOME = 19.25 [n=16, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·AWAY = 19.1429 [n=14, MEDIUM]
- total_shots·FOR·ALL_PRIOR·ALL = 10.8333 [n=30, HIGH]
- total_shots·FOR·W5·ALL = 9.0 [n=5, LOW]
- total_shots·FOR·W10·ALL = 9.6 [n=10, MEDIUM]
- total_shots·FOR·ALL_PRIOR·HOME = 13.375 [n=16, MEDIUM]
- total_shots·FOR·ALL_PRIOR·AWAY = 7.9286 [n=14, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·ALL = 12.7 [n=30, HIGH]
- total_shots·AGAINST·W5·ALL = 16.2 [n=5, LOW]
- total_shots·AGAINST·W10·ALL = 15.1 [n=10, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·HOME = 9.0 [n=16, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·AWAY = 16.9286 [n=14, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·ALL = 20.2333 [n=30, HIGH]
- touches_in_box·FOR·W5·ALL = 19.8 [n=5, LOW]
- touches_in_box·FOR·W10·ALL = 18.4 [n=10, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·HOME = 23.3125 [n=16, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·AWAY = 16.7143 [n=14, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·ALL = 22.7667 [n=30, HIGH]
- touches_in_box·AGAINST·W5·ALL = 32.2 [n=5, LOW]
- touches_in_box·AGAINST·W10·ALL = 30.0 [n=10, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·HOME = 17.5 [n=16, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·AWAY = 28.7857 [n=14, MEDIUM]
- xg·FOR·ALL_PRIOR·ALL = 0.998 [n=30, HIGH]
- xg·FOR·W5·ALL = 0.758 [n=5, LOW]
- xg·FOR·W10·ALL = 0.863 [n=10, MEDIUM]
- xg·FOR·ALL_PRIOR·HOME = 1.2263 [n=16, MEDIUM]
- xg·FOR·ALL_PRIOR·AWAY = 0.7371 [n=14, MEDIUM]
- xg·AGAINST·ALL_PRIOR·ALL = 1.1983 [n=30, HIGH]
- xg·AGAINST·W5·ALL = 1.338 [n=5, LOW]
- xg·AGAINST·W10·ALL = 1.397 [n=10, MEDIUM]
- xg·AGAINST·ALL_PRIOR·HOME = 0.8319 [n=16, MEDIUM]
- xg·AGAINST·ALL_PRIOR·AWAY = 1.6171 [n=14, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·ALL = 2.1379 [n=29, HIGH]
- yellow_cards·FOR·W5·ALL = 2.25 [n=4, LOW]
- yellow_cards·FOR·W10·ALL = 2.3333 [n=9, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·HOME = 1.8 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·AWAY = 2.5 [n=14, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·ALL = 2.0 [n=29, HIGH]
- yellow_cards·AGAINST·W5·ALL = 1.75 [n=4, LOW]
- yellow_cards·AGAINST·W10·ALL = 1.7778 [n=9, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·HOME = 2.2 [n=15, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·AWAY = 1.7857 [n=14, MEDIUM]

AWAY_TEAM:

- accurate_crosses·FOR·ALL_PRIOR·ALL = 4.7 [n=30, HIGH]
- accurate_crosses·FOR·W5·ALL = 4.4 [n=5, LOW]
- accurate_crosses·FOR·W10·ALL = 3.5 [n=10, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·HOME = 4.8 [n=15, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·AWAY = 4.6 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·ALL = 3.6 [n=30, HIGH]
- accurate_crosses·AGAINST·W5·ALL = 3.4 [n=5, LOW]
- accurate_crosses·AGAINST·W10·ALL = 3.9 [n=10, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·HOME = 3.0 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·AWAY = 4.2 [n=15, MEDIUM]
- big_chances·FOR·ALL_PRIOR·ALL = 2.25 [n=28, HIGH]
- big_chances·FOR·W5·ALL = 2.5 [n=4, LOW]
- big_chances·FOR·W10·ALL = 2.0 [n=8, MEDIUM]
- big_chances·FOR·ALL_PRIOR·HOME = 2.1538 [n=13, MEDIUM]
- big_chances·FOR·ALL_PRIOR·AWAY = 2.3333 [n=15, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·ALL = 2.1429 [n=28, HIGH]
- big_chances·AGAINST·W5·ALL = 3.25 [n=4, LOW]
- big_chances·AGAINST·W10·ALL = 2.375 [n=8, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·HOME = 1.6154 [n=13, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·AWAY = 2.6 [n=15, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·ALL = 3.7 [n=30, HIGH]
- blocked_shots·FOR·W5·ALL = 3.2 [n=5, LOW]
- blocked_shots·FOR·W10·ALL = 3.7 [n=10, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·HOME = 4.2667 [n=15, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·AWAY = 3.1333 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·ALL = 3.5333 [n=30, HIGH]
- blocked_shots·AGAINST·W5·ALL = 3.8 [n=5, LOW]
- blocked_shots·AGAINST·W10·ALL = 3.3 [n=10, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·HOME = 3.1333 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·AWAY = 3.9333 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·ALL = 28.6667 [n=30, HIGH]
- clearances·FOR·W5·ALL = 27.2 [n=5, LOW]
- clearances·FOR·W10·ALL = 28.3 [n=10, MEDIUM]
- clearances·FOR·ALL_PRIOR·HOME = 27.0 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·AWAY = 30.3333 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·ALL = 29.4333 [n=30, HIGH]
- clearances·AGAINST·W5·ALL = 30.4 [n=5, LOW]
- clearances·AGAINST·W10·ALL = 31.8 [n=10, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·HOME = 33.0 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·AWAY = 25.8667 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·ALL = 5.6 [n=30, HIGH]
- corners·FOR·W5·ALL = 6.6 [n=5, LOW]
- corners·FOR·W10·ALL = 5.8 [n=10, MEDIUM]
- corners·FOR·ALL_PRIOR·HOME = 5.8 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·AWAY = 5.4 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·ALL = 4.5 [n=30, HIGH]
- corners·AGAINST·W5·ALL = 5.4 [n=5, LOW]
- corners·AGAINST·W10·ALL = 4.3 [n=10, MEDIUM]
- corners·AGAINST·ALL_PRIOR·HOME = 4.2 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·AWAY = 4.8 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·ALL = 60.1 [n=30, HIGH]
- final_third_entries·FOR·W5·ALL = 56.2 [n=5, LOW]
- final_third_entries·FOR·W10·ALL = 62.7 [n=10, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·HOME = 68.0667 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·AWAY = 52.1333 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·ALL = 53.7667 [n=30, HIGH]
- final_third_entries·AGAINST·W5·ALL = 55.6 [n=5, LOW]
- final_third_entries·AGAINST·W10·ALL = 57.1 [n=10, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·HOME = 55.0 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·AWAY = 52.5333 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·ALL = 13.6667 [n=30, HIGH]
- fouls·FOR·W5·ALL = 14.6 [n=5, LOW]
- fouls·FOR·W10·ALL = 13.0 [n=10, MEDIUM]
- fouls·FOR·ALL_PRIOR·HOME = 13.2 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·AWAY = 14.1333 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·ALL = 10.8333 [n=30, HIGH]
- fouls·AGAINST·W5·ALL = 8.2 [n=5, LOW]
- fouls·AGAINST·W10·ALL = 10.0 [n=10, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·HOME = 11.0 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·AWAY = 10.6667 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·ALL = 1.5667 [n=30, HIGH]
- goals·FOR·W5·ALL = 1.6 [n=5, LOW]
- goals·FOR·W10·ALL = 1.6 [n=10, MEDIUM]
- goals·FOR·ALL_PRIOR·HOME = 1.4 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·AWAY = 1.7333 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·ALL = 1.4333 [n=30, HIGH]
- goals·AGAINST·W5·ALL = 2.4 [n=5, LOW]
- goals·AGAINST·W10·ALL = 1.6 [n=10, MEDIUM]
- goals·AGAINST·ALL_PRIOR·HOME = 0.8667 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·AWAY = 2.0 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·ALL = 8.7667 [n=30, HIGH]
- interceptions·FOR·W5·ALL = 9.4 [n=5, LOW]
- interceptions·FOR·W10·ALL = 9.0 [n=10, MEDIUM]
- interceptions·FOR·ALL_PRIOR·HOME = 8.4 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·AWAY = 9.1333 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·ALL = 7.0667 [n=30, HIGH]
- interceptions·AGAINST·W5·ALL = 7.8 [n=5, LOW]
- interceptions·AGAINST·W10·ALL = 7.3 [n=10, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·HOME = 7.6 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·AWAY = 6.5333 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·ALL = 1.32 [n=30, HIGH]
- npxg·FOR·W5·ALL = 1.474 [n=5, LOW]
- npxg·FOR·W10·ALL = 1.202 [n=10, MEDIUM]
- npxg·FOR·ALL_PRIOR·HOME = 1.3213 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·AWAY = 1.3187 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·ALL = 1.2343 [n=30, HIGH]
- npxg·AGAINST·W5·ALL = 1.686 [n=5, LOW]
- npxg·AGAINST·W10·ALL = 1.218 [n=10, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·HOME = 0.9847 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·AWAY = 1.484 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·ALL = 2.1429 [n=28, HIGH]
- offsides·FOR·W5·ALL = 2.6 [n=5, LOW]
- offsides·FOR·W10·ALL = 2.4 [n=10, MEDIUM]
- offsides·FOR·ALL_PRIOR·HOME = 2.2857 [n=14, MEDIUM]
- offsides·FOR·ALL_PRIOR·AWAY = 2.0 [n=14, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·ALL = 1.3929 [n=28, HIGH]
- offsides·AGAINST·W5·ALL = 1.0 [n=5, LOW]
- offsides·AGAINST·W10·ALL = 1.1 [n=10, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·HOME = 1.3571 [n=14, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·AWAY = 1.4286 [n=14, MEDIUM]
- possession·FOR·ALL_PRIOR·ALL = 51.9 [n=30, HIGH]
- possession·FOR·W5·ALL = 55.2 [n=5, LOW]
- possession·FOR·W10·ALL = 53.5 [n=10, MEDIUM]
- possession·FOR·ALL_PRIOR·HOME = 54.9333 [n=15, MEDIUM]
- possession·FOR·ALL_PRIOR·AWAY = 48.8667 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·ALL = 48.1 [n=30, HIGH]
- possession·AGAINST·W5·ALL = 44.8 [n=5, LOW]
- possession·AGAINST·W10·ALL = 46.5 [n=10, MEDIUM]
- possession·AGAINST·ALL_PRIOR·HOME = 45.0667 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·AWAY = 51.1333 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·ALL = 0.1 [n=30, HIGH]
- red_cards·FOR·W5·ALL = 0.0 [n=5, LOW]
- red_cards·FOR·W10·ALL = 0.0 [n=10, MEDIUM]
- red_cards·FOR·ALL_PRIOR·HOME = 0.1333 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·AWAY = 0.0667 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·ALL = 0.1333 [n=30, HIGH]
- red_cards·AGAINST·W5·ALL = 0.0 [n=5, LOW]
- red_cards·AGAINST·W10·ALL = 0.0 [n=10, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·HOME = 0.1333 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·AWAY = 0.1333 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·ALL = 2.9667 [n=30, HIGH]
- saves·FOR·W5·ALL = 3.2 [n=5, LOW]
- saves·FOR·W10·ALL = 2.8 [n=10, MEDIUM]
- saves·FOR·ALL_PRIOR·HOME = 2.6667 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·AWAY = 3.2667 [n=15, MEDIUM]
- saves·AGAINST·ALL_PRIOR·ALL = 3.5 [n=30, HIGH]
- saves·AGAINST·W5·ALL = 4.4 [n=5, LOW]
- saves·AGAINST·W10·ALL = 3.8 [n=10, MEDIUM]
- saves·AGAINST·ALL_PRIOR·HOME = 3.8 [n=15, MEDIUM]
- saves·AGAINST·ALL_PRIOR·AWAY = 3.2 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·ALL = 8.6667 [n=30, HIGH]
- shots_inside_box·FOR·W5·ALL = 8.4 [n=5, LOW]
- shots_inside_box·FOR·W10·ALL = 8.1 [n=10, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·HOME = 8.8 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·AWAY = 8.5333 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·ALL = 7.9 [n=30, HIGH]
- shots_inside_box·AGAINST·W5·ALL = 9.0 [n=5, LOW]
- shots_inside_box·AGAINST·W10·ALL = 7.5 [n=10, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·HOME = 6.4 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·AWAY = 9.4 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·ALL = 4.9333 [n=30, HIGH]
- shots_off_target·FOR·W5·ALL = 5.0 [n=5, LOW]
- shots_off_target·FOR·W10·ALL = 4.7 [n=10, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·HOME = 5.3333 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·AWAY = 4.5333 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·ALL = 4.0333 [n=30, HIGH]
- shots_off_target·AGAINST·W5·ALL = 3.2 [n=5, LOW]
- shots_off_target·AGAINST·W10·ALL = 3.2 [n=10, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·HOME = 3.8667 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·AWAY = 4.2 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·ALL = 4.8 [n=30, HIGH]
- shots_on_target·FOR·W5·ALL = 5.6 [n=5, LOW]
- shots_on_target·FOR·W10·ALL = 5.2 [n=10, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·HOME = 5.0 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·AWAY = 4.6 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·ALL = 4.3667 [n=30, HIGH]
- shots_on_target·AGAINST·W5·ALL = 5.8 [n=5, LOW]
- shots_on_target·AGAINST·W10·ALL = 4.5 [n=10, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·HOME = 3.4667 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·AWAY = 5.2667 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·ALL = 4.7667 [n=30, HIGH]
- shots_outside_box·FOR·W5·ALL = 5.4 [n=5, LOW]
- shots_outside_box·FOR·W10·ALL = 5.5 [n=10, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·HOME = 5.8 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·AWAY = 3.7333 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·ALL = 4.0333 [n=30, HIGH]
- shots_outside_box·AGAINST·W5·ALL = 3.8 [n=5, LOW]
- shots_outside_box·AGAINST·W10·ALL = 3.5 [n=10, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·HOME = 4.0667 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·AWAY = 4.0 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·ALL = 17.1 [n=30, HIGH]
- tackles·FOR·W5·ALL = 17.0 [n=5, LOW]
- tackles·FOR·W10·ALL = 17.9 [n=10, MEDIUM]
- tackles·FOR·ALL_PRIOR·HOME = 14.9333 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·AWAY = 19.2667 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·ALL = 16.2333 [n=30, HIGH]
- tackles·AGAINST·W5·ALL = 17.0 [n=5, LOW]
- tackles·AGAINST·W10·ALL = 17.8 [n=10, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·HOME = 16.8 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·AWAY = 15.6667 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·ALL = 18.6333 [n=30, HIGH]
- throw_ins·FOR·W5·ALL = 18.2 [n=5, LOW]
- throw_ins·FOR·W10·ALL = 20.0 [n=10, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·HOME = 20.4667 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·AWAY = 16.8 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·ALL = 20.1333 [n=30, HIGH]
- throw_ins·AGAINST·W5·ALL = 16.0 [n=5, LOW]
- throw_ins·AGAINST·W10·ALL = 18.6 [n=10, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·HOME = 19.0667 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·AWAY = 21.2 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·ALL = 13.4333 [n=30, HIGH]
- total_shots·FOR·W5·ALL = 13.8 [n=5, LOW]
- total_shots·FOR·W10·ALL = 13.6 [n=10, MEDIUM]
- total_shots·FOR·ALL_PRIOR·HOME = 14.6 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·AWAY = 12.2667 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·ALL = 11.9333 [n=30, HIGH]
- total_shots·AGAINST·W5·ALL = 12.8 [n=5, LOW]
- total_shots·AGAINST·W10·ALL = 11.0 [n=10, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·HOME = 10.4667 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·AWAY = 13.4 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·ALL = 26.4333 [n=30, HIGH]
- touches_in_box·FOR·W5·ALL = 24.2 [n=5, LOW]
- touches_in_box·FOR·W10·ALL = 24.5 [n=10, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·HOME = 29.3333 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·AWAY = 23.5333 [n=15, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·ALL = 24.8333 [n=30, HIGH]
- touches_in_box·AGAINST·W5·ALL = 25.2 [n=5, LOW]
- touches_in_box·AGAINST·W10·ALL = 23.7 [n=10, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·HOME = 21.3333 [n=15, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·AWAY = 28.3333 [n=15, MEDIUM]
- xg·FOR·ALL_PRIOR·ALL = 1.4103 [n=30, HIGH]
- xg·FOR·W5·ALL = 1.798 [n=5, LOW]
- xg·FOR·W10·ALL = 1.443 [n=10, MEDIUM]
- xg·FOR·ALL_PRIOR·HOME = 1.386 [n=15, MEDIUM]
- xg·FOR·ALL_PRIOR·AWAY = 1.4347 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·ALL = 1.3253 [n=30, HIGH]
- xg·AGAINST·W5·ALL = 1.876 [n=5, LOW]
- xg·AGAINST·W10·ALL = 1.305 [n=10, MEDIUM]
- xg·AGAINST·ALL_PRIOR·HOME = 1.0287 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·AWAY = 1.622 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·ALL = 2.5667 [n=30, HIGH]
- yellow_cards·FOR·W5·ALL = 2.8 [n=5, LOW]
- yellow_cards·FOR·W10·ALL = 2.6 [n=10, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·HOME = 2.4 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·AWAY = 2.7333 [n=15, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·ALL = 2.0667 [n=30, HIGH]
- yellow_cards·AGAINST·W5·ALL = 1.6 [n=5, LOW]
- yellow_cards·AGAINST·W10·ALL = 1.8 [n=10, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·HOME = 2.3333 [n=15, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·AWAY = 1.8 [n=15, MEDIUM]

### Arm B — opponent-profile context (deterministic bands)

```json
{
 "axes": {
  "accurate_crosses_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  },
  "corners_against": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "corners_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  },
  "goals_against": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "goals_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "possession_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "shots_on_target_against": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  },
  "shots_on_target_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  }
 },
 "similarity_version": "opponent_similarity_v1_pending"
}
```

---

## mt_010243938

- PIT-safe matches available: **139**; match rows included (both teams): **60**; omitted: **79** (reason: `frozen_history_policy(max_matches_per_team=30)`); UNEXPLAINED_OMISSION: **0**.
- Metric cell exposure rate (non-null of serialized): **0.9965**; derived summaries: **480**.
- Availability map: `{"expected_formation": "UNAVAILABLE", "formation": "LOW_COVERAGE", "half_time_state": "UNAVAILABLE", "injuries": "UNAVAILABLE", "lineup": "PIT_UNSAFE", "opponent_profile": "AVAILABLE", "recent_vs_long": "AVAILABLE", "red_cards": "AVAILABLE", "temporal_event_state": "UNAVAILABLE", "venue": "AVAILABLE", "xg": "AVAILABLE"}`
- Arm A packet hash: `11580c1bd6d7bb65faf4c2121254cb80e2ef4735e4384113d09b8ddaaee1f9ae`
- Arm B packet hash: `3e19a19ba60b34a066f92360dba0be68ff263cd9fabb22d4be5d31c7cc66b2a3`

### Arm A — frozen V3 compressed evidence (all items)

76 unconditional shrunk scalar items (venue=ALL, window=ALL_PRIOR):

| id | metric | value | n | reliability |
|---|---|---|---|---|
| HOME_ATK_corners_406027 | corners_for | 4.4164 | 69 | HIGH |
| HOME_DEF_corners_7cfac3 | corners_against | 5.2431 | 69 | HIGH |
| HOME_ATK_accurate_crosses_c28b9e | accurate_crosses_for | 3.752 | 69 | HIGH |
| HOME_DEF_accurate_crosses_81ffb5 | accurate_crosses_against | 4.5653 | 69 | HIGH |
| HOME_ATK_total_shots_808ac9 | total_shots_for | 12.6811 | 69 | HIGH |
| HOME_DEF_total_shots_c0e347 | total_shots_against | 12.1211 | 69 | HIGH |
| HOME_ATK_shots_on_target_e955e0 | shots_on_target_for | 4.3489 | 69 | HIGH |
| HOME_DEF_shots_on_target_8a3812 | shots_on_target_against | 4.1489 | 69 | HIGH |
| HOME_ATK_shots_off_target_11e91f | shots_off_target_for | 4.597 | 69 | HIGH |
| HOME_DEF_shots_off_target_26031c | shots_off_target_against | 4.5703 | 69 | HIGH |
| HOME_ATK_blocked_shots_5198f8 | blocked_shots_for | 3.7354 | 69 | HIGH |
| HOME_DEF_blocked_shots_09c3c4 | blocked_shots_against | 3.4021 | 69 | HIGH |
| HOME_ATK_shots_inside_box_cf538d | shots_inside_box_for | 8.7702 | 69 | HIGH |
| HOME_DEF_shots_inside_box_e6b28d | shots_inside_box_against | 8.3436 | 69 | HIGH |
| HOME_ATK_touches_in_box_759ed8 | touches_in_box_for | 23.2629 | 69 | HIGH |
| HOME_DEF_touches_in_box_94cd98 | touches_in_box_against | 24.3829 | 69 | HIGH |
| HOME_ATK_final_third_entries_5aa0be | final_third_entries_for | 51.768 | 69 | HIGH |
| HOME_DEF_final_third_entries_4a40ef | final_third_entries_against | 59.8613 | 69 | HIGH |
| HOME_ATK_possession_190f3f | possession_for | 44.6 | 69 | HIGH |
| HOME_DEF_possession_f8ada9 | possession_against | 55.4 | 69 | HIGH |
| HOME_ATK_tackles_65b6c1 | tackles_for | 19.2519 | 69 | HIGH |
| HOME_DEF_tackles_e3c85e | tackles_against | 15.1319 | 69 | HIGH |
| HOME_ATK_fouls_8107c6 | fouls_for | 10.9254 | 69 | HIGH |
| HOME_DEF_fouls_b6d53c | fouls_against | 10.3654 | 69 | HIGH |
| HOME_ATK_yellow_cards_80b7a4 | yellow_cards_for | 2.2051 | 65 | HIGH |
| HOME_DEF_yellow_cards_8ee8aa | yellow_cards_against | 2.2333 | 65 | HIGH |
| HOME_ATK_clearances_ec2e18 | clearances_for | 29.7002 | 69 | HIGH |
| HOME_DEF_clearances_6d3f4c | clearances_against | 26.6335 | 69 | HIGH |
| HOME_ATK_interceptions_967965 | interceptions_for | 8.5347 | 69 | HIGH |
| HOME_DEF_interceptions_c82020 | interceptions_against | 8.7614 | 69 | HIGH |
| HOME_ATK_goals_08b15b | goals_for | 1.2606 | 69 | HIGH |
| HOME_DEF_goals_d53fdd | goals_against | 1.2739 | 69 | HIGH |
| HOME_ATK_throw_ins_b24629 | throw_ins_for | 16.6697 | 69 | HIGH |
| HOME_DEF_throw_ins_208262 | throw_ins_against | 19.1363 | 69 | HIGH |
| HOME_ATK_big_chances_8a9e2f | big_chances_for | 2.6936 | 68 | HIGH |
| HOME_DEF_big_chances_885151 | big_chances_against | 2.4639 | 68 | HIGH |
| HOME_ATK_saves_6bda8d | saves_for | 2.8347 | 69 | HIGH |
| HOME_DEF_saves_19ae14 | saves_against | 3.0214 | 69 | HIGH |
| AWAY_ATK_corners_ca1538 | corners_for | 4.5162 | 70 | HIGH |
| AWAY_DEF_corners_598e33 | corners_against | 5.832 | 70 | HIGH |
| AWAY_ATK_accurate_crosses_005290 | accurate_crosses_for | 3.8605 | 70 | HIGH |
| AWAY_DEF_accurate_crosses_287e9c | accurate_crosses_against | 5.4789 | 70 | HIGH |
| AWAY_ATK_total_shots_004f7a | total_shots_for | 11.6063 | 70 | HIGH |
| AWAY_DEF_total_shots_403d28 | total_shots_against | 15.08 | 70 | HIGH |
| AWAY_ATK_shots_on_target_9afd02 | shots_on_target_for | 3.7259 | 70 | HIGH |
| AWAY_DEF_shots_on_target_dcda5e | shots_on_target_against | 5.0417 | 70 | HIGH |
| AWAY_ATK_shots_off_target_b83815 | shots_off_target_for | 4.3392 | 70 | HIGH |
| AWAY_DEF_shots_off_target_5fe2d0 | shots_off_target_against | 5.6155 | 70 | HIGH |
| AWAY_ATK_blocked_shots_93d965 | blocked_shots_for | 3.5415 | 70 | HIGH |
| AWAY_DEF_blocked_shots_97ef03 | blocked_shots_against | 4.4231 | 70 | HIGH |
| AWAY_ATK_shots_inside_box_567ee5 | shots_inside_box_for | 8.2601 | 70 | HIGH |
| AWAY_DEF_shots_inside_box_446c80 | shots_inside_box_against | 10.3259 | 70 | HIGH |
| AWAY_ATK_touches_in_box_2c76ca | touches_in_box_for | 21.7068 | 70 | HIGH |
| AWAY_DEF_touches_in_box_319da5 | touches_in_box_against | 29.5884 | 70 | HIGH |
| AWAY_ATK_final_third_entries_5a0987 | final_third_entries_for | 50.4552 | 70 | HIGH |
| AWAY_DEF_final_third_entries_ed75cd | final_third_entries_against | 58.521 | 70 | HIGH |
| AWAY_ATK_possession_82105a | possession_for | 46.0395 | 70 | HIGH |
| AWAY_DEF_possession_012ecc | possession_against | 53.9605 | 70 | HIGH |
| AWAY_ATK_tackles_0865bc | tackles_for | 17.3538 | 70 | HIGH |
| AWAY_DEF_tackles_3e6a7d | tackles_against | 17.8538 | 70 | HIGH |
| AWAY_ATK_fouls_97bf91 | fouls_for | 11.2816 | 70 | HIGH |
| AWAY_DEF_fouls_94f7aa | fouls_against | 10.6895 | 70 | HIGH |
| AWAY_ATK_yellow_cards_120c77 | yellow_cards_for | 2.0625 | 67 | HIGH |
| AWAY_DEF_yellow_cards_367397 | yellow_cards_against | 1.7611 | 67 | HIGH |
| AWAY_ATK_clearances_74617f | clearances_for | 27.7567 | 70 | HIGH |
| AWAY_DEF_clearances_8bdc80 | clearances_against | 21.8752 | 70 | HIGH |
| AWAY_ATK_interceptions_404e22 | interceptions_for | 8.9224 | 70 | HIGH |
| AWAY_DEF_interceptions_4be11b | interceptions_against | 7.5672 | 70 | HIGH |
| AWAY_ATK_goals_5d2c6a | goals_for | 1.244 | 70 | HIGH |
| AWAY_DEF_goals_4ad3b7 | goals_against | 1.6782 | 70 | HIGH |
| AWAY_ATK_throw_ins_64d189 | throw_ins_for | 17.0161 | 70 | HIGH |
| AWAY_DEF_throw_ins_35916f | throw_ins_against | 18.9372 | 70 | HIGH |
| AWAY_ATK_big_chances_065222 | big_chances_for | 1.9648 | 70 | HIGH |
| AWAY_DEF_big_chances_d5f920 | big_chances_against | 2.6096 | 70 | HIGH |
| AWAY_ATK_saves_50b33b | saves_for | 3.508 | 70 | HIGH |
| AWAY_DEF_saves_bf5cbb | saves_against | 2.5474 | 70 | HIGH |

### Arm B — HOME_TEAM match-level matrix (30 rows × 55 cols)

Columns: `match_alias, kickoff_unix, competition, venue, opponent_alias, own_formation_family, opponent_formation_family, accurate_crosses_for, accurate_crosses_against, big_chances_for, big_chances_against, blocked_shots_for, blocked_shots_against, clearances_for, clearances_against, corners_for, corners_against, final_third_entries_for, final_third_entries_against, fouls_for, fouls_against, goals_for, goals_against, interceptions_for, interceptions_against, npxg_for, npxg_against, offsides_for, offsides_against, possession_for, possession_against, red_cards_for, red_cards_against, saves_for, saves_against, shots_inside_box_for, shots_inside_box_against, shots_off_target_for, shots_off_target_against, shots_on_target_for, shots_on_target_against, shots_outside_box_for, shots_outside_box_against, tackles_for, tackles_against, throw_ins_for, throw_ins_against, total_shots_for, total_shots_against, touches_in_box_for, touches_in_box_against, xg_for, xg_against, yellow_cards_for, yellow_cards_against`

| match_alias | kickoff_unix | competition | venue | opponent_alias | own_formation_family | opponent_formation_family | accurate_crosses_for | accurate_crosses_against | big_chances_for | big_chances_against | blocked_shots_for | blocked_shots_against | clearances_for | clearances_against | corners_for | corners_against | final_third_entries_for | final_third_entries_against | fouls_for | fouls_against | goals_for | goals_against | interceptions_for | interceptions_against | npxg_for | npxg_against | offsides_for | offsides_against | possession_for | possession_against | red_cards_for | red_cards_against | saves_for | saves_against | shots_inside_box_for | shots_inside_box_against | shots_off_target_for | shots_off_target_against | shots_on_target_for | shots_on_target_against | shots_outside_box_for | shots_outside_box_against | tackles_for | tackles_against | throw_ins_for | throw_ins_against | total_shots_for | total_shots_against | touches_in_box_for | touches_in_box_against | xg_for | xg_against | yellow_cards_for | yellow_cards_against |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| m_mt_010243573 | 1756040400 | COMPETITION | HOME | OPP_001 | BACK_THREE | BACK_FOUR | 6.0 | 3.0 | 2.0 | 2.0 | 0.0 | 1.0 | 21.0 | 15.0 | 1.0 | 3.0 | 51.0 | 70.0 | 11.0 | 11.0 | 1.0 | 1.0 | 7.0 | 10.0 | 1.1 | 0.93 | 2.0 | 2.0 | 42.0 | 58.0 | 0.0 | 0.0 | 0.0 | 3.0 | 7.0 | 8.0 | 4.0 | 7.0 | 4.0 | 1.0 | 1.0 | 1.0 | 20.0 | 12.0 | 14.0 | 16.0 | 8.0 | 9.0 | 21.0 | 20.0 | 1.1 | 0.93 | 3.0 | 3.0 |
| m_mt_252067156 | 1756663200 | COMPETITION | AWAY | OPP_002 |  |  | 2.0 | 6.0 | 4.0 | 2.0 | 1.0 | 1.0 | 37.0 | 17.0 | 1.0 | 10.0 | 51.0 | 79.0 | 14.0 | 7.0 | 3.0 | 0.0 | 10.0 | 6.0 | 1.86 | 1.14 | 2.0 | 0.0 | 42.0 | 58.0 | 0.0 | 0.0 | 4.0 | 1.0 | 5.0 | 10.0 | 1.0 | 8.0 | 4.0 | 4.0 | 1.0 | 3.0 | 26.0 | 11.0 | 9.0 | 20.0 | 6.0 | 13.0 | 14.0 | 20.0 | 2.65 | 1.14 | 3.0 | 2.0 |
| m_mt_585124997 | 1757772000 | COMPETITION | HOME | OPP_003 | BACK_THREE | BACK_FOUR | 5.0 | 4.0 | 3.0 | 0.0 | 4.0 | 2.0 | 25.0 | 34.0 | 5.0 | 3.0 | 45.0 | 60.0 | 10.0 | 8.0 | 0.0 | 0.0 | 6.0 | 10.0 | 1.78 | 0.4 | 0.0 | 2.0 | 56.0 | 44.0 | 0.0 | 0.0 | 0.0 | 6.0 | 8.0 | 5.0 | 4.0 | 4.0 | 6.0 | 0.0 | 6.0 | 1.0 | 10.0 | 13.0 | 23.0 | 21.0 | 14.0 | 6.0 | 21.0 | 17.0 | 1.77 | 0.36 | 1.0 | 1.0 |
| m_mt_404678402 | 1758376800 | COMPETITION | AWAY | OPP_004 |  |  | 8.0 | 7.0 | 4.0 | 1.0 | 6.0 | 1.0 | 35.0 | 22.0 | 8.0 | 8.0 | 47.0 | 56.0 | 5.0 | 15.0 | 2.0 | 1.0 | 10.0 | 7.0 | 2.31 | 0.62 | 2.0 | 1.0 | 43.0 | 57.0 | 0.0 | 0.0 | 2.0 | 1.0 | 14.0 | 7.0 | 9.0 | 4.0 | 3.0 | 3.0 | 4.0 | 1.0 | 22.0 | 9.0 | 12.0 | 19.0 | 18.0 | 8.0 | 27.0 | 20.0 | 2.31 | 0.66 | 3.0 | 3.0 |
| m_mt_191506100 | 1758981600 | COMPETITION | HOME | OPP_005 |  |  | 2.0 | 8.0 | 7.0 | 6.0 | 2.0 | 5.0 | 32.0 | 36.0 | 2.0 | 6.0 | 58.0 | 93.0 | 10.0 | 8.0 | 2.0 | 1.0 | 9.0 | 10.0 | 2.96 | 2.14 | 2.0 | 1.0 | 28.0 | 72.0 | 0.0 | 0.0 | 3.0 | 5.0 | 12.0 | 13.0 | 7.0 | 11.0 | 7.0 | 4.0 | 4.0 | 7.0 | 24.0 | 7.0 | 20.0 | 18.0 | 16.0 | 20.0 | 33.0 | 28.0 | 2.92 | 2.14 | 1.0 | 3.0 |
| m_mt_585124557 | 1759669200 | COMPETITION | AWAY | OPP_006 |  |  | 3.0 | 6.0 | 5.0 | 5.0 | 3.0 | 2.0 | 38.0 | 35.0 | 4.0 | 2.0 | 56.0 | 66.0 | 16.0 | 13.0 | 1.0 | 2.0 | 14.0 | 11.0 | 1.58 | 1.37 | 1.0 | 0.0 | 50.0 | 50.0 | 0.0 | 0.0 | 5.0 | 5.0 | 11.0 | 10.0 | 4.0 | 5.0 | 8.0 | 7.0 | 4.0 | 4.0 | 31.0 | 19.0 | 22.0 | 31.0 | 15.0 | 14.0 | 23.0 | 28.0 | 1.53 | 2.03 | 3.0 | 2.0 |
| m_mt_363782552 | 1760796000 | COMPETITION | HOME | OPP_007 |  |  | 6.0 | 2.0 | 7.0 | 3.0 | 7.0 | 0.0 | 32.0 | 47.0 | 6.0 | 5.0 | 60.0 | 43.0 | 8.0 | 16.0 | 3.0 | 3.0 | 6.0 | 12.0 | 3.5 | 2.03 | 3.0 | 3.0 | 52.0 | 48.0 | 0.0 | 0.0 | 2.0 | 4.0 | 15.0 | 5.0 | 6.0 | 3.0 | 7.0 | 5.0 | 5.0 | 3.0 | 23.0 | 18.0 | 17.0 | 14.0 | 20.0 | 8.0 | 41.0 | 19.0 | 4.44 | 2.03 | 1.0 | 4.0 |
| m_mt_404671901 | 1761487200 | COMPETITION | AWAY | OPP_008 |  |  | 3.0 | 4.0 | 0.0 | 2.0 | 3.0 | 3.0 | 44.0 | 28.0 | 3.0 | 4.0 | 46.0 | 87.0 | 11.0 | 6.0 | 0.0 | 1.0 | 12.0 | 6.0 | 0.5 | 0.96 | 1.0 | 2.0 | 40.0 | 60.0 | 0.0 | 0.0 | 2.0 | 1.0 | 5.0 | 7.0 | 3.0 | 4.0 | 1.0 | 3.0 | 2.0 | 3.0 | 16.0 | 12.0 | 19.0 | 17.0 | 7.0 | 10.0 | 15.0 | 25.0 | 0.45 | 0.92 |  |  |
| m_mt_363782510 | 1762009200 | COMPETITION | HOME | OPP_009 | BACK_THREE | BACK_FOUR | 2.0 | 1.0 | 1.0 | 1.0 | 4.0 | 2.0 | 31.0 | 38.0 | 6.0 | 5.0 | 57.0 | 66.0 | 7.0 | 11.0 | 2.0 | 0.0 | 12.0 | 4.0 | 0.7 | 0.64 | 1.0 | 3.0 | 36.0 | 64.0 | 0.0 | 0.0 | 2.0 | 2.0 | 6.0 | 2.0 | 3.0 | 2.0 | 3.0 | 2.0 | 4.0 | 4.0 | 13.0 | 16.0 | 23.0 | 19.0 | 10.0 | 6.0 | 24.0 | 16.0 | 0.7 | 0.54 | 0.0 | 3.0 |
| m_mt_585124346 | 1762696800 | COMPETITION | HOME | OPP_010 |  |  | 6.0 | 4.0 | 0.0 | 1.0 | 1.0 | 3.0 | 32.0 | 22.0 | 4.0 | 8.0 | 47.0 | 48.0 | 10.0 | 12.0 | 0.0 | 0.0 | 14.0 | 4.0 | 0.75 | 0.38 | 2.0 | 1.0 | 42.0 | 58.0 | 0.0 | 0.0 | 3.0 | 2.0 | 8.0 | 5.0 | 7.0 | 1.0 | 2.0 | 3.0 | 2.0 | 2.0 | 21.0 | 16.0 | 23.0 | 17.0 | 10.0 | 7.0 | 30.0 | 28.0 | 0.75 | 0.39 | 1.0 | 4.0 |
| m_mt_191506895 | 1763823600 | COMPETITION | AWAY | OPP_011 |  |  | 0.0 | 2.0 | 2.0 | 2.0 | 3.0 | 2.0 | 30.0 | 44.0 | 4.0 | 1.0 | 53.0 | 59.0 | 9.0 | 13.0 | 2.0 | 0.0 | 10.0 | 8.0 | 1.27 | 1.86 | 3.0 | 2.0 | 52.0 | 48.0 | 0.0 | 0.0 | 1.0 | 2.0 | 6.0 | 5.0 | 3.0 | 5.0 | 4.0 | 1.0 | 4.0 | 3.0 | 19.0 | 21.0 | 16.0 | 19.0 | 10.0 | 8.0 | 23.0 | 24.0 | 1.27 | 1.79 | 3.0 | 2.0 |
| m_mt_979812384 | 1764504000 | COMPETITION | HOME | OPP_012 |  |  | 4.0 | 3.0 | 3.0 | 2.0 | 5.0 | 0.0 | 44.0 | 31.0 | 4.0 | 4.0 | 62.0 | 70.0 | 14.0 | 14.0 | 1.0 | 2.0 | 7.0 | 10.0 | 1.03 | 1.36 | 3.0 | 0.0 | 44.0 | 56.0 | 0.0 | 0.0 | 4.0 | 2.0 | 11.0 | 8.0 | 6.0 | 8.0 | 3.0 | 6.0 | 3.0 | 6.0 | 14.0 | 16.0 | 14.0 | 23.0 | 14.0 | 14.0 | 26.0 | 18.0 | 1.83 | 1.19 | 3.0 | 2.0 |
| m_mt_979812330 | 1764790200 | COMPETITION | AWAY | OPP_013 |  |  | 5.0 | 5.0 | 2.0 | 2.0 | 0.0 | 6.0 | 42.0 | 42.0 | 3.0 | 3.0 | 49.0 | 65.0 | 8.0 | 9.0 | 1.0 | 0.0 | 11.0 | 16.0 | 0.67 | 0.95 | 3.0 | 0.0 | 42.0 | 58.0 | 0.0 | 0.0 | 3.0 | 2.0 | 3.0 | 8.0 | 0.0 | 1.0 | 3.0 | 4.0 | 0.0 | 3.0 | 17.0 | 13.0 | 20.0 | 29.0 | 3.0 | 11.0 | 22.0 | 29.0 | 0.59 | 0.95 |  |  |
| m_mt_404678451 | 1765125000 | COMPETITION | AWAY | OPP_014 |  |  | 3.0 | 7.0 | 4.0 | 2.0 | 5.0 | 3.0 | 28.0 | 23.0 | 4.0 | 6.0 | 50.0 | 69.0 | 8.0 | 5.0 | 2.0 | 1.0 | 9.0 | 8.0 | 1.69 | 0.76 | 2.0 | 3.0 | 37.0 | 63.0 | 0.0 | 0.0 | 3.0 | 3.0 | 9.0 | 9.0 | 1.0 | 5.0 | 5.0 | 4.0 | 2.0 | 3.0 | 20.0 | 12.0 | 14.0 | 25.0 | 11.0 | 12.0 | 18.0 | 26.0 | 1.65 | 0.76 |  |  |
| m_mt_404678489 | 1765720800 | COMPETITION | HOME | OPP_015 |  |  | 2.0 | 3.0 | 1.0 | 2.0 | 6.0 | 0.0 | 20.0 | 39.0 | 2.0 | 2.0 | 40.0 | 65.0 | 9.0 | 6.0 | 0.0 | 3.0 | 5.0 | 8.0 | 1.88 | 0.45 | 3.0 | 2.0 | 39.0 | 61.0 | 0.0 | 0.0 | 3.0 | 4.0 | 12.0 | 5.0 | 6.0 | 1.0 | 4.0 | 6.0 | 4.0 | 2.0 | 23.0 | 14.0 | 19.0 | 11.0 | 16.0 | 7.0 | 33.0 | 13.0 | 1.88 | 1.19 | 2.0 | 0.0 |
| m_mt_010243001 | 1766260800 | COMPETITION | AWAY | OPP_016 |  |  | 2.0 | 6.0 | 2.0 | 4.0 | 3.0 | 5.0 | 58.0 | 29.0 | 5.0 | 9.0 | 40.0 | 50.0 | 10.0 | 5.0 | 1.0 | 4.0 | 6.0 | 7.0 | 0.78 | 3.27 | 3.0 | 2.0 | 47.0 | 53.0 | 0.0 | 0.0 | 2.0 | 2.0 | 5.0 | 14.0 | 3.0 | 7.0 | 3.0 | 8.0 | 4.0 | 6.0 | 22.0 | 15.0 | 8.0 | 34.0 | 9.0 | 20.0 | 19.0 | 37.0 | 1.56 | 2.67 | 3.0 | 1.0 |
| m_mt_979814067 | 1766939400 | COMPETITION | HOME | OPP_017 | BACK_THREE | BACK_FOUR | 4.0 | 3.0 | 2.0 | 1.0 | 5.0 | 1.0 | 23.0 | 50.0 | 3.0 | 2.0 | 78.0 | 52.0 | 7.0 | 5.0 | 0.0 | 1.0 | 7.0 | 6.0 | 1.47 | 0.88 | 1.0 | 3.0 | 62.0 | 38.0 | 0.0 | 0.0 | 3.0 | 2.0 | 9.0 | 5.0 | 8.0 | 3.0 | 2.0 | 4.0 | 6.0 | 3.0 | 16.0 | 20.0 | 21.0 | 20.0 | 15.0 | 8.0 | 35.0 | 18.0 | 1.47 | 0.88 | 3.0 | 2.0 |
| m_mt_979814081 | 1767288600 | COMPETITION | HOME | OPP_014 |  |  | 1.0 | 7.0 | 3.0 | 3.0 | 4.0 | 6.0 | 29.0 | 35.0 | 6.0 | 3.0 | 54.0 | 75.0 | 7.0 | 10.0 | 1.0 | 1.0 | 9.0 | 9.0 | 1.91 | 1.76 | 5.0 | 1.0 | 40.0 | 60.0 | 0.0 | 0.0 | 4.0 | 1.0 | 9.0 | 12.0 | 5.0 | 6.0 | 2.0 | 5.0 | 2.0 | 5.0 | 14.0 | 16.0 | 15.0 | 17.0 | 11.0 | 17.0 | 37.0 | 31.0 | 1.93 | 1.76 | 0.0 | 5.0 |
| m_mt_838956269 | 1767538800 | COMPETITION | AWAY | OPP_018 |  |  | 2.0 | 7.0 | 1.0 | 5.0 | 5.0 | 2.0 | 45.0 | 35.0 | 6.0 | 8.0 | 43.0 | 62.0 | 12.0 | 5.0 | 0.0 | 2.0 | 11.0 | 7.0 | 0.73 | 2.25 | 2.0 | 5.0 | 41.0 | 59.0 | 0.0 | 0.0 | 5.0 | 1.0 | 9.0 | 11.0 | 5.0 | 3.0 | 1.0 | 7.0 | 2.0 | 1.0 | 28.0 | 16.0 | 17.0 | 16.0 | 11.0 | 12.0 | 26.0 | 35.0 | 0.7 | 2.08 | 3.0 | 1.0 |
| m_mt_838950677 | 1767814200 | COMPETITION | HOME | OPP_002 |  |  | 3.0 | 4.0 | 3.0 | 3.0 | 4.0 | 5.0 | 31.0 | 21.0 | 3.0 | 5.0 | 46.0 | 49.0 | 8.0 | 3.0 | 0.0 | 0.0 | 4.0 | 9.0 | 1.51 | 1.74 | 2.0 | 0.0 | 41.0 | 59.0 | 0.0 | 0.0 | 4.0 | 5.0 | 9.0 | 11.0 | 2.0 | 7.0 | 5.0 | 3.0 | 2.0 | 4.0 | 20.0 | 14.0 | 17.0 | 18.0 | 11.0 | 15.0 | 21.0 | 37.0 | 1.5 | 1.74 | 2.0 | 0.0 |
| m_mt_404678252 | 1768662000 | COMPETITION | AWAY | OPP_003 |  |  | 2.0 | 7.0 | 2.0 | 3.0 | 2.0 | 1.0 | 36.0 | 35.0 | 4.0 | 3.0 | 62.0 | 62.0 | 15.0 | 8.0 | 1.0 | 2.0 | 9.0 | 11.0 | 0.5 | 1.84 | 2.0 | 0.0 | 43.0 | 57.0 | 0.0 | 0.0 | 5.0 | 1.0 | 5.0 | 10.0 | 2.0 | 5.0 | 2.0 | 7.0 | 1.0 | 3.0 | 12.0 | 15.0 | 12.0 | 25.0 | 6.0 | 13.0 | 16.0 | 18.0 | 0.61 | 1.71 | 3.0 | 3.0 |
| m_mt_363781486 | 1769349600 | COMPETITION | HOME | OPP_019 |  |  | 3.0 | 4.0 | 5.0 | 5.0 | 3.0 | 1.0 | 24.0 | 46.0 | 4.0 | 5.0 | 54.0 | 35.0 | 11.0 | 10.0 | 1.0 | 3.0 | 10.0 | 14.0 | 1.89 | 1.42 | 2.0 | 1.0 | 43.0 | 57.0 | 1.0 | 0.0 | 2.0 | 5.0 | 12.0 | 8.0 | 3.0 | 3.0 | 7.0 | 6.0 | 1.0 | 2.0 | 17.0 | 16.0 | 17.0 | 16.0 | 13.0 | 10.0 | 26.0 | 21.0 | 1.88 | 2.2 | 4.0 | 2.0 |
| m_mt_585124958 | 1769954400 | COMPETITION | AWAY | OPP_001 |  |  | 6.0 | 2.0 | 2.0 | 2.0 | 3.0 | 3.0 | 24.0 | 25.0 | 7.0 | 5.0 | 74.0 | 46.0 | 12.0 | 4.0 | 1.0 | 1.0 | 5.0 | 10.0 | 1.13 | 0.49 | 0.0 | 2.0 | 67.0 | 33.0 | 0.0 | 1.0 | 0.0 | 1.0 | 9.0 | 6.0 | 8.0 | 5.0 | 3.0 | 1.0 | 5.0 | 3.0 | 14.0 | 16.0 | 16.0 | 17.0 | 14.0 | 9.0 | 26.0 | 18.0 | 1.92 | 0.49 | 3.0 | 1.0 |
| m_mt_252067295 | 1770559200 | COMPETITION | AWAY | OPP_010 |  |  | 3.0 | 2.0 | 1.0 | 1.0 | 0.0 | 3.0 | 33.0 | 33.0 | 4.0 | 3.0 | 58.0 | 73.0 | 9.0 | 12.0 | 1.0 | 0.0 | 10.0 | 3.0 | 1.16 | 0.85 | 3.0 | 3.0 | 37.0 | 63.0 | 0.0 | 0.0 | 2.0 | 3.0 | 6.0 | 5.0 | 3.0 | 2.0 | 4.0 | 2.0 | 1.0 | 2.0 | 21.0 | 17.0 | 18.0 | 12.0 | 7.0 | 7.0 | 24.0 | 13.0 | 1.16 | 0.85 | 3.0 | 1.0 |
| m_mt_747395705 | 1770838200 | COMPETITION | HOME | OPP_013 | BACK_THREE | BACK_THREE | 11.0 | 3.0 | 3.0 | 1.0 | 11.0 | 1.0 | 25.0 | 37.0 | 8.0 | 2.0 | 67.0 | 54.0 | 11.0 | 8.0 | 2.0 | 3.0 | 8.0 | 7.0 | 1.9 | 0.51 | 1.0 | 1.0 | 65.0 | 35.0 | 0.0 | 0.0 | 1.0 | 1.0 | 15.0 | 4.0 | 7.0 | 4.0 | 3.0 | 3.0 | 6.0 | 4.0 | 14.0 | 16.0 | 17.0 | 15.0 | 21.0 | 8.0 | 39.0 | 19.0 | 1.8 | 0.53 | 2.0 | 1.0 |
| m_mt_838955384 | 1771768800 | COMPETITION | HOME | OPP_011 |  |  | 5.0 | 7.0 | 4.0 | 2.0 | 4.0 | 3.0 | 31.0 | 49.0 | 7.0 | 3.0 | 60.0 | 55.0 | 19.0 | 13.0 | 1.0 | 0.0 | 6.0 | 12.0 | 1.67 | 0.89 | 0.0 | 1.0 | 61.0 | 39.0 | 0.0 | 1.0 | 7.0 | 2.0 | 9.0 | 7.0 | 7.0 | 2.0 | 3.0 | 7.0 | 5.0 | 5.0 | 15.0 | 17.0 | 26.0 | 21.0 | 14.0 | 12.0 | 24.0 | 16.0 | 1.67 | 1.68 | 5.0 | 3.0 |
| m_mt_838955357 | 1772373600 | COMPETITION | AWAY | OPP_012 |  |  | 1.0 | 11.0 | 0.0 | 3.0 | 2.0 | 5.0 | 27.0 | 13.0 | 1.0 | 7.0 | 49.0 | 56.0 | 12.0 | 13.0 | 1.0 | 2.0 | 6.0 | 3.0 | 0.39 | 1.33 | 2.0 | 1.0 | 39.0 | 61.0 | 1.0 | 0.0 | 9.0 | 2.0 | 5.0 | 11.0 | 3.0 | 4.0 | 3.0 | 11.0 | 3.0 | 9.0 | 17.0 | 13.0 | 11.0 | 10.0 | 8.0 | 20.0 | 13.0 | 32.0 | 0.38 | 2.12 | 2.0 | 2.0 |
| m_mt_252066579 | 1772740800 | COMPETITION | AWAY | OPP_017 |  |  | 2.0 | 5.0 | 3.0 | 1.0 | 3.0 | 5.0 | 32.0 | 28.0 | 3.0 | 6.0 | 52.0 | 40.0 | 14.0 | 14.0 | 3.0 | 1.0 | 5.0 | 9.0 | 0.99 | 1.58 | 1.0 | 1.0 | 60.0 | 40.0 | 0.0 | 1.0 | 3.0 | 1.0 | 8.0 | 10.0 | 2.0 | 3.0 | 4.0 | 4.0 | 1.0 | 2.0 | 23.0 | 17.0 | 13.0 | 22.0 | 9.0 | 12.0 | 22.0 | 23.0 | 1.78 | 1.58 | 2.0 | 3.0 |
| m_mt_252066585 | 1773583200 | COMPETITION | HOME | OPP_016 | BACK_THREE | BACK_THREE | 4.0 | 5.0 | 0.0 | 1.0 | 7.0 | 3.0 | 51.0 | 55.0 | 8.0 | 3.0 | 67.0 | 51.0 | 12.0 | 11.0 | 0.0 | 0.0 | 2.0 | 6.0 | 0.67 | 0.33 | 5.0 | 2.0 | 67.0 | 33.0 | 0.0 | 1.0 | 3.0 | 0.0 | 7.0 | 7.0 | 5.0 | 4.0 | 0.0 | 3.0 | 5.0 | 3.0 | 10.0 | 16.0 | 22.0 | 24.0 | 12.0 | 10.0 | 26.0 | 21.0 | 0.67 | 1.12 | 2.0 | 3.0 |
| m_mt_747399462 | 1775998800 | COMPETITION | HOME | OPP_018 |  |  | 5.0 | 1.0 | 4.0 | 2.0 | 3.0 | 3.0 | 41.0 | 16.0 | 2.0 | 4.0 | 60.0 | 64.0 | 17.0 | 12.0 | 2.0 | 1.0 | 12.0 | 12.0 | 1.57 | 1.14 | 1.0 | 0.0 | 41.0 | 59.0 | 0.0 | 0.0 | 2.0 | 3.0 | 9.0 | 5.0 | 3.0 | 1.0 | 5.0 | 3.0 | 2.0 | 2.0 | 21.0 | 6.0 | 20.0 | 28.0 | 11.0 | 7.0 | 21.0 | 14.0 | 2.56 | 1.13 | 0.0 | 3.0 |

### Arm B — AWAY_TEAM match-level matrix (30 rows × 55 cols)

Columns: `match_alias, kickoff_unix, competition, venue, opponent_alias, own_formation_family, opponent_formation_family, accurate_crosses_for, accurate_crosses_against, big_chances_for, big_chances_against, blocked_shots_for, blocked_shots_against, clearances_for, clearances_against, corners_for, corners_against, final_third_entries_for, final_third_entries_against, fouls_for, fouls_against, goals_for, goals_against, interceptions_for, interceptions_against, npxg_for, npxg_against, offsides_for, offsides_against, possession_for, possession_against, red_cards_for, red_cards_against, saves_for, saves_against, shots_inside_box_for, shots_inside_box_against, shots_off_target_for, shots_off_target_against, shots_on_target_for, shots_on_target_against, shots_outside_box_for, shots_outside_box_against, tackles_for, tackles_against, throw_ins_for, throw_ins_against, total_shots_for, total_shots_against, touches_in_box_for, touches_in_box_against, xg_for, xg_against, yellow_cards_for, yellow_cards_against`

| match_alias | kickoff_unix | competition | venue | opponent_alias | own_formation_family | opponent_formation_family | accurate_crosses_for | accurate_crosses_against | big_chances_for | big_chances_against | blocked_shots_for | blocked_shots_against | clearances_for | clearances_against | corners_for | corners_against | final_third_entries_for | final_third_entries_against | fouls_for | fouls_against | goals_for | goals_against | interceptions_for | interceptions_against | npxg_for | npxg_against | offsides_for | offsides_against | possession_for | possession_against | red_cards_for | red_cards_against | saves_for | saves_against | shots_inside_box_for | shots_inside_box_against | shots_off_target_for | shots_off_target_against | shots_on_target_for | shots_on_target_against | shots_outside_box_for | shots_outside_box_against | tackles_for | tackles_against | throw_ins_for | throw_ins_against | total_shots_for | total_shots_against | touches_in_box_for | touches_in_box_against | xg_for | xg_against | yellow_cards_for | yellow_cards_against |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| m_mt_747395699 | 1756645200 | COMPETITION | AWAY | OPP_001 |  |  | 7.0 | 4.0 | 4.0 | 1.0 | 0.0 | 5.0 | 32.0 | 16.0 | 7.0 | 9.0 | 33.0 | 80.0 | 6.0 | 14.0 | 3.0 | 0.0 | 6.0 | 6.0 | 1.63 | 0.73 |  |  | 42.0 | 58.0 | 0.0 | 0.0 | 3.0 | 5.0 | 10.0 | 9.0 | 4.0 | 3.0 | 8.0 | 3.0 | 2.0 | 2.0 | 16.0 | 19.0 | 12.0 | 17.0 | 12.0 | 11.0 | 18.0 | 29.0 | 2.42 | 0.73 |  |  |
| m_mt_838950787 | 1757781000 | COMPETITION | HOME | OPP_017 |  |  | 3.0 | 5.0 | 1.0 | 2.0 | 0.0 | 5.0 | 41.0 | 10.0 | 2.0 | 13.0 | 48.0 | 60.0 | 8.0 | 7.0 | 0.0 | 3.0 | 5.0 | 3.0 | 0.65 | 1.29 | 0.0 | 4.0 | 36.0 | 64.0 | 1.0 | 0.0 | 2.0 | 4.0 | 6.0 | 10.0 | 3.0 | 4.0 | 4.0 | 5.0 | 1.0 | 4.0 | 13.0 | 16.0 | 19.0 | 21.0 | 7.0 | 14.0 | 10.0 | 37.0 | 0.6 | 1.29 | 0.0 | 1.0 |
| m_mt_404678402 | 1758376800 | COMPETITION | HOME | OPP_020 |  |  | 7.0 | 8.0 | 1.0 | 4.0 | 1.0 | 6.0 | 22.0 | 35.0 | 8.0 | 8.0 | 56.0 | 47.0 | 15.0 | 5.0 | 1.0 | 2.0 | 7.0 | 10.0 | 0.62 | 2.31 | 1.0 | 2.0 | 57.0 | 43.0 | 0.0 | 0.0 | 1.0 | 2.0 | 7.0 | 14.0 | 4.0 | 9.0 | 3.0 | 3.0 | 1.0 | 4.0 | 9.0 | 22.0 | 19.0 | 12.0 | 8.0 | 18.0 | 20.0 | 27.0 | 0.66 | 2.31 | 3.0 | 3.0 |
| m_mt_363376157 | 1759172400 | COMPETITION | AWAY | OPP_006 |  |  | 4.0 | 3.0 | 1.0 | 0.0 | 6.0 | 3.0 | 36.0 | 37.0 | 5.0 | 3.0 | 53.0 | 51.0 | 16.0 | 7.0 | 1.0 | 1.0 | 6.0 | 5.0 | 1.19 | 0.72 | 2.0 | 0.0 | 48.0 | 52.0 | 0.0 | 0.0 | 5.0 | 2.0 | 10.0 | 9.0 | 5.0 | 3.0 | 3.0 | 6.0 | 4.0 | 3.0 | 16.0 | 11.0 | 22.0 | 19.0 | 14.0 | 12.0 | 29.0 | 30.0 | 1.19 | 0.73 | 4.0 | 3.0 |
| m_mt_010243058 | 1759586400 | COMPETITION | AWAY | OPP_008 |  |  | 2.0 | 3.0 | 2.0 | 4.0 | 1.0 | 9.0 | 50.0 | 27.0 | 3.0 | 8.0 | 34.0 | 44.0 | 14.0 | 14.0 | 0.0 | 2.0 | 12.0 | 7.0 | 0.43 | 2.12 | 1.0 | 1.0 | 32.0 | 68.0 | 0.0 | 0.0 | 3.0 | 0.0 | 4.0 | 16.0 | 3.0 | 7.0 | 0.0 | 5.0 | 0.0 | 5.0 | 17.0 | 23.0 | 18.0 | 16.0 | 4.0 | 21.0 | 8.0 | 46.0 | 0.49 | 2.77 | 2.0 | 0.0 |
| m_mt_375612438 | 1760986800 | COMPETITION | HOME | OPP_009 |  |  | 2.0 | 13.0 | 0.0 | 5.0 | 3.0 | 5.0 | 42.0 | 29.0 | 6.0 | 10.0 | 33.0 | 52.0 | 10.0 | 10.0 | 0.0 | 2.0 | 3.0 | 6.0 | 0.33 | 2.31 | 3.0 | 2.0 | 43.0 | 57.0 | 0.0 | 0.0 | 4.0 | 1.0 | 2.0 | 20.0 | 3.0 | 10.0 | 1.0 | 7.0 | 5.0 | 2.0 | 16.0 | 11.0 | 26.0 | 23.0 | 7.0 | 22.0 | 14.0 | 42.0 | 0.33 | 2.31 | 1.0 | 1.0 |
| m_mt_404671962 | 1761332400 | COMPETITION | AWAY | OPP_016 |  |  | 3.0 | 5.0 | 0.0 | 3.0 | 3.0 | 3.0 | 12.0 | 39.0 | 4.0 | 3.0 | 63.0 | 37.0 | 11.0 | 12.0 | 1.0 | 2.0 | 4.0 | 12.0 | 0.65 | 1.53 | 1.0 | 1.0 | 59.0 | 41.0 | 0.0 | 0.0 | 3.0 | 2.0 | 4.0 | 8.0 | 3.0 | 5.0 | 3.0 | 5.0 | 5.0 | 5.0 | 12.0 | 21.0 | 30.0 | 18.0 | 9.0 | 13.0 | 10.0 | 10.0 | 0.65 | 1.49 | 3.0 | 3.0 |
| m_mt_252068388 | 1762092000 | COMPETITION | HOME | OPP_018 | BACK_FOUR | BACK_FOUR | 6.0 | 2.0 | 2.0 | 0.0 | 3.0 | 2.0 | 41.0 | 19.0 | 7.0 | 6.0 | 41.0 | 89.0 | 5.0 | 10.0 | 3.0 | 1.0 | 7.0 | 9.0 | 2.76 | 0.56 | 4.0 | 0.0 | 37.0 | 63.0 | 0.0 | 0.0 | 3.0 | 7.0 | 10.0 | 6.0 | 3.0 | 6.0 | 9.0 | 4.0 | 5.0 | 6.0 | 21.0 | 8.0 | 17.0 | 25.0 | 15.0 | 12.0 | 21.0 | 22.0 | 1.75 | 0.52 | 1.0 | 2.0 |
| m_mt_191506714 | 1762614000 | COMPETITION | HOME | OPP_013 |  |  | 4.0 | 3.0 | 3.0 | 4.0 | 8.0 | 7.0 | 30.0 | 28.0 | 7.0 | 4.0 | 47.0 | 68.0 | 15.0 | 13.0 | 3.0 | 2.0 | 13.0 | 7.0 | 3.13 | 1.06 | 2.0 | 1.0 | 43.0 | 57.0 | 0.0 | 0.0 | 5.0 | 3.0 | 8.0 | 9.0 | 1.0 | 2.0 | 6.0 | 7.0 | 7.0 | 7.0 | 14.0 | 16.0 | 15.0 | 17.0 | 15.0 | 16.0 | 22.0 | 25.0 | 3.02 | 1.06 | 2.0 | 2.0 |
| m_mt_585124351 | 1763823600 | COMPETITION | AWAY | OPP_007 |  |  | 1.0 | 15.0 | 0.0 | 4.0 | 1.0 | 7.0 | 57.0 | 11.0 | 2.0 | 9.0 | 49.0 | 95.0 | 10.0 | 9.0 | 2.0 | 2.0 | 9.0 | 7.0 | 0.64 | 3.31 | 2.0 | 2.0 | 24.0 | 76.0 | 0.0 | 0.0 | 10.0 | 0.0 | 4.0 | 22.0 | 2.0 | 11.0 | 2.0 | 10.0 | 1.0 | 6.0 | 13.0 | 19.0 | 10.0 | 27.0 | 5.0 | 28.0 | 8.0 | 57.0 | 0.65 | 4.05 | 2.0 | 3.0 |
| m_mt_191506867 | 1764511500 | COMPETITION | HOME | OPP_005 |  |  | 2.0 | 2.0 | 0.0 | 3.0 | 5.0 | 0.0 | 21.0 | 29.0 | 7.0 | 2.0 | 47.0 | 63.0 | 12.0 | 14.0 | 0.0 | 2.0 | 9.0 | 4.0 | 0.31 | 1.24 | 2.0 | 1.0 | 44.0 | 56.0 | 1.0 | 0.0 | 3.0 | 0.0 | 4.0 | 5.0 | 2.0 | 4.0 | 0.0 | 5.0 | 3.0 | 4.0 | 13.0 | 11.0 | 14.0 | 23.0 | 7.0 | 9.0 | 11.0 | 20.0 | 0.29 | 1.24 | 3.0 | 0.0 |
| m_mt_191506144 | 1764878400 | COMPETITION | AWAY | OPP_012 |  |  | 3.0 | 5.0 | 1.0 | 3.0 | 5.0 | 8.0 | 39.0 | 17.0 | 6.0 | 6.0 | 60.0 | 65.0 | 9.0 | 13.0 | 1.0 | 1.0 | 20.0 | 5.0 | 0.8 | 1.85 | 2.0 | 3.0 | 35.0 | 65.0 | 0.0 | 0.0 | 3.0 | 1.0 | 10.0 | 13.0 | 3.0 | 5.0 | 3.0 | 4.0 | 1.0 | 4.0 | 15.0 | 19.0 | 19.0 | 28.0 | 11.0 | 17.0 | 28.0 | 43.0 | 0.79 | 1.8 | 2.0 | 2.0 |
| m_mt_747395721 | 1765116000 | COMPETITION | AWAY | OPP_010 |  |  | 3.0 | 13.0 | 3.0 | 3.0 | 3.0 | 10.0 | 41.0 | 13.0 | 6.0 | 10.0 | 39.0 | 59.0 | 8.0 | 12.0 | 1.0 | 1.0 | 13.0 | 9.0 | 1.27 | 1.87 | 1.0 | 1.0 | 32.0 | 68.0 | 0.0 | 0.0 | 4.0 | 4.0 | 12.0 | 15.0 | 6.0 | 8.0 | 5.0 | 4.0 | 2.0 | 7.0 | 14.0 | 12.0 | 13.0 | 16.0 | 14.0 | 22.0 | 24.0 | 44.0 | 1.14 | 1.87 | 2.0 | 2.0 |
| m_mt_191506177 | 1765720800 | COMPETITION | HOME | OPP_002 |  |  | 0.0 | 3.0 | 2.0 | 1.0 | 3.0 | 1.0 | 14.0 | 13.0 | 5.0 | 3.0 | 56.0 | 41.0 | 18.0 | 13.0 | 2.0 | 3.0 | 9.0 | 6.0 | 1.13 | 0.73 | 1.0 | 1.0 | 41.0 | 59.0 | 0.0 | 0.0 | 2.0 | 1.0 | 7.0 | 4.0 | 4.0 | 2.0 | 3.0 | 4.0 | 3.0 | 3.0 | 17.0 | 22.0 | 18.0 | 12.0 | 10.0 | 7.0 | 19.0 | 12.0 | 1.03 | 0.67 | 1.0 | 2.0 |
| m_mt_626439663 | 1766242800 | COMPETITION | AWAY | OPP_015 |  |  | 1.0 | 6.0 | 2.0 | 8.0 | 0.0 | 2.0 | 13.0 | 9.0 | 0.0 | 6.0 | 28.0 | 54.0 | 10.0 | 16.0 | 0.0 | 3.0 | 12.0 | 9.0 | 1.14 | 2.13 | 2.0 | 1.0 | 34.0 | 66.0 | 0.0 | 0.0 | 5.0 | 4.0 | 5.0 | 14.0 | 4.0 | 7.0 | 3.0 | 8.0 | 2.0 | 3.0 | 24.0 | 12.0 | 14.0 | 12.0 | 7.0 | 17.0 | 12.0 | 40.0 | 0.98 | 2.1 | 1.0 | 1.0 |
| m_mt_979814078 | 1766847600 | COMPETITION | HOME | OPP_014 | BACK_FOUR | BACK_FOUR | 2.0 | 10.0 | 1.0 | 1.0 | 5.0 | 6.0 | 25.0 | 34.0 | 5.0 | 4.0 | 47.0 | 65.0 | 8.0 | 8.0 | 0.0 | 1.0 | 9.0 | 12.0 | 0.91 | 1.62 | 7.0 | 2.0 | 44.0 | 56.0 | 0.0 | 0.0 | 4.0 | 2.0 | 7.0 | 11.0 | 4.0 | 6.0 | 2.0 | 5.0 | 4.0 | 6.0 | 29.0 | 15.0 | 19.0 | 24.0 | 11.0 | 17.0 | 27.0 | 35.0 | 0.91 | 1.62 | 1.0 | 3.0 |
| m_mt_979814012 | 1767123000 | COMPETITION | HOME | OPP_010 |  |  | 2.0 | 1.0 | 4.0 | 4.0 | 3.0 | 4.0 | 27.0 | 24.0 | 5.0 | 5.0 | 50.0 | 61.0 | 11.0 | 18.0 | 2.0 | 2.0 | 9.0 | 16.0 | 1.17 | 1.37 | 1.0 | 1.0 | 39.0 | 61.0 | 0.0 | 0.0 | 5.0 | 2.0 | 10.0 | 8.0 | 3.0 | 6.0 | 4.0 | 6.0 | 0.0 | 8.0 | 27.0 | 13.0 | 14.0 | 16.0 | 10.0 | 16.0 | 21.0 | 31.0 | 2.06 | 2.94 | 3.0 | 5.0 |
| m_mt_979814043 | 1767452400 | COMPETITION | AWAY | OPP_011 |  |  | 7.0 | 5.0 | 0.0 | 3.0 | 0.0 | 0.0 | 15.0 | 34.0 | 7.0 | 6.0 | 80.0 | 34.0 | 10.0 | 11.0 | 0.0 | 3.0 | 6.0 | 9.0 | 0.32 | 1.08 | 1.0 | 1.0 | 67.0 | 33.0 | 0.0 | 0.0 | 5.0 | 0.0 | 4.0 | 8.0 | 6.0 | 3.0 | 0.0 | 8.0 | 2.0 | 3.0 | 27.0 | 23.0 | 16.0 | 27.0 | 6.0 | 11.0 | 25.0 | 14.0 | 0.25 | 1.87 | 0.0 | 1.0 |
| m_mt_404678127 | 1767729600 | COMPETITION | HOME | OPP_001 |  |  | 2.0 | 5.0 | 3.0 | 1.0 | 5.0 | 4.0 | 33.0 | 32.0 | 6.0 | 5.0 | 69.0 | 70.0 | 15.0 | 9.0 | 1.0 | 2.0 | 7.0 | 6.0 | 0.95 | 0.73 | 1.0 | 0.0 | 47.0 | 53.0 | 0.0 | 0.0 | 3.0 | 3.0 | 11.0 | 7.0 | 6.0 | 4.0 | 3.0 | 5.0 | 3.0 | 6.0 | 28.0 | 15.0 | 23.0 | 27.0 | 14.0 | 13.0 | 17.0 | 26.0 | 0.95 | 1.38 | 3.0 | 0.0 |
| m_mt_747395644 | 1768662000 | COMPETITION | AWAY | OPP_017 |  |  | 6.0 | 9.0 | 3.0 | 3.0 | 7.0 | 4.0 | 44.0 | 14.0 | 5.0 | 11.0 | 37.0 | 65.0 | 17.0 | 12.0 | 2.0 | 1.0 | 18.0 | 9.0 | 2.69 | 1.75 | 1.0 | 1.0 | 38.0 | 62.0 | 0.0 | 0.0 | 5.0 | 2.0 | 17.0 | 15.0 | 6.0 | 11.0 | 4.0 | 6.0 | 0.0 | 6.0 | 27.0 | 16.0 | 12.0 | 18.0 | 17.0 | 21.0 | 29.0 | 51.0 | 2.69 | 1.68 | 3.0 | 5.0 |
| m_mt_979812329 | 1769257800 | COMPETITION | HOME | OPP_003 |  |  | 2.0 | 4.0 | 4.0 | 2.0 | 3.0 | 1.0 | 24.0 | 30.0 | 3.0 | 3.0 | 56.0 | 55.0 | 9.0 | 16.0 | 3.0 | 1.0 | 6.0 | 3.0 | 0.64 | 0.65 | 0.0 | 1.0 | 47.0 | 53.0 | 0.0 | 0.0 | 1.0 | 2.0 | 7.0 | 4.0 | 5.0 | 4.0 | 5.0 | 2.0 | 6.0 | 3.0 | 25.0 | 12.0 | 24.0 | 25.0 | 13.0 | 7.0 | 25.0 | 13.0 | 1.43 | 0.65 | 2.0 | 4.0 |
| m_mt_252067182 | 1769880600 | COMPETITION | AWAY | OPP_019 |  |  | 2.0 | 6.0 | 2.0 | 4.0 | 3.0 | 4.0 | 46.0 | 24.0 | 3.0 | 9.0 | 62.0 | 80.0 | 13.0 | 11.0 | 2.0 | 3.0 | 7.0 | 8.0 | 1.12 | 2.79 | 2.0 | 0.0 | 30.0 | 70.0 | 1.0 | 0.0 | 3.0 | 4.0 | 8.0 | 11.0 | 2.0 | 4.0 | 6.0 | 6.0 | 3.0 | 3.0 | 13.0 | 14.0 | 13.0 | 17.0 | 11.0 | 14.0 | 22.0 | 36.0 | 1.12 | 2.55 | 2.0 | 3.0 |
| m_mt_010243083 | 1770476400 | COMPETITION | AWAY | OPP_013 |  |  | 3.0 | 7.0 | 2.0 | 2.0 | 0.0 | 8.0 | 34.0 | 23.0 | 2.0 | 5.0 | 50.0 | 57.0 | 10.0 | 11.0 | 2.0 | 0.0 | 15.0 | 2.0 | 1.02 | 1.28 | 1.0 | 0.0 | 47.0 | 53.0 | 0.0 | 0.0 | 5.0 | 2.0 | 3.0 | 11.0 | 2.0 | 5.0 | 4.0 | 5.0 | 3.0 | 7.0 | 14.0 | 14.0 | 18.0 | 25.0 | 6.0 | 18.0 | 16.0 | 23.0 | 1.02 | 1.28 | 1.0 | 3.0 |
| m_mt_585124545 | 1770754500 | COMPETITION | HOME | OPP_012 | BACK_FOUR | BACK_FOUR | 3.0 | 7.0 | 2.0 | 1.0 | 3.0 | 2.0 | 23.0 | 12.0 | 5.0 | 3.0 | 48.0 | 72.0 | 10.0 | 4.0 | 1.0 | 1.0 | 15.0 | 8.0 | 1.09 | 0.63 | 1.0 | 3.0 | 35.0 | 65.0 | 0.0 | 0.0 | 1.0 | 2.0 | 4.0 | 8.0 | 1.0 | 4.0 | 3.0 | 3.0 | 3.0 | 1.0 | 17.0 | 19.0 | 14.0 | 28.0 | 7.0 | 9.0 | 9.0 | 21.0 | 1.08 | 0.62 | 1.0 | 1.0 |
| m_mt_747399436 | 1771695000 | COMPETITION | HOME | OPP_007 |  |  | 8.0 | 1.0 | 2.0 | 0.0 | 7.0 | 4.0 | 30.0 | 25.0 | 9.0 | 5.0 | 51.0 | 58.0 | 10.0 | 11.0 | 0.0 | 0.0 | 9.0 | 9.0 | 2.91 | 0.65 | 2.0 | 3.0 | 42.0 | 58.0 | 0.0 | 0.0 | 5.0 | 3.0 | 16.0 | 4.0 | 10.0 | 1.0 | 3.0 | 5.0 | 4.0 | 6.0 | 21.0 | 17.0 | 17.0 | 19.0 | 20.0 | 10.0 | 35.0 | 17.0 | 2.87 | 0.65 | 1.0 | 1.0 |
| m_mt_626433239 | 1772290800 | COMPETITION | AWAY | OPP_005 |  |  | 4.0 | 2.0 | 2.0 | 2.0 | 3.0 | 7.0 | 19.0 | 22.0 | 5.0 | 10.0 | 52.0 | 58.0 | 11.0 | 12.0 | 2.0 | 5.0 | 13.0 | 6.0 | 2.01 | 1.75 | 1.0 | 1.0 | 51.0 | 49.0 | 0.0 | 0.0 | 2.0 | 3.0 | 8.0 | 13.0 | 4.0 | 4.0 | 4.0 | 7.0 | 3.0 | 5.0 | 14.0 | 21.0 | 21.0 | 20.0 | 11.0 | 18.0 | 31.0 | 35.0 | 1.84 | 1.75 | 2.0 | 2.0 |
| m_mt_363788607 | 1772652600 | COMPETITION | AWAY | OPP_014 |  |  | 2.0 | 9.0 | 3.0 | 0.0 | 2.0 | 4.0 | 32.0 | 20.0 | 5.0 | 6.0 | 42.0 | 64.0 | 12.0 | 14.0 | 1.0 | 0.0 | 13.0 | 4.0 | 1.09 | 1.01 | 7.0 | 0.0 | 40.0 | 60.0 | 0.0 | 0.0 | 5.0 | 3.0 | 6.0 | 10.0 | 4.0 | 4.0 | 3.0 | 5.0 | 3.0 | 3.0 | 7.0 | 11.0 | 16.0 | 18.0 | 9.0 | 13.0 | 13.0 | 29.0 | 1.09 | 1.01 | 4.0 | 2.0 |
| m_mt_585122832 | 1773518400 | COMPETITION | HOME | OPP_015 |  |  | 1.0 | 10.0 | 1.0 | 1.0 | 0.0 | 7.0 | 34.0 | 15.0 | 1.0 | 15.0 | 32.0 | 85.0 | 14.0 | 5.0 | 1.0 | 1.0 | 11.0 | 12.0 | 0.54 | 2.12 | 3.0 | 2.0 | 29.0 | 71.0 | 0.0 | 0.0 | 5.0 | 0.0 | 1.0 | 19.0 | 0.0 | 11.0 | 1.0 | 6.0 | 0.0 | 5.0 | 26.0 | 7.0 | 21.0 | 16.0 | 1.0 | 24.0 | 5.0 | 39.0 | 0.54 | 2.12 | 2.0 | 2.0 |
| m_mt_010244105 | 1774188900 | COMPETITION | AWAY | OPP_002 |  |  | 6.0 | 5.0 | 1.0 | 3.0 | 5.0 | 7.0 | 20.0 | 17.0 | 6.0 | 6.0 | 35.0 | 62.0 | 7.0 | 3.0 | 0.0 | 2.0 | 10.0 | 2.0 | 0.89 | 1.72 | 4.0 | 0.0 | 41.0 | 59.0 | 0.0 | 0.0 | 4.0 | 1.0 | 8.0 | 13.0 | 3.0 | 9.0 | 1.0 | 7.0 | 1.0 | 10.0 | 13.0 | 18.0 | 14.0 | 20.0 | 9.0 | 23.0 | 19.0 | 38.0 | 0.94 | 1.68 | 1.0 | 0.0 |
| m_mt_747395095 | 1775847600 | COMPETITION | HOME | OPP_011 |  |  | 4.0 | 3.0 | 6.0 | 0.0 | 4.0 | 3.0 | 21.0 | 19.0 | 5.0 | 2.0 | 53.0 | 40.0 | 11.0 | 7.0 | 4.0 | 0.0 | 5.0 | 8.0 | 1.69 | 0.61 | 0.0 | 1.0 | 44.0 | 56.0 | 0.0 | 0.0 | 4.0 | 3.0 | 14.0 | 9.0 | 7.0 | 8.0 | 7.0 | 3.0 | 4.0 | 5.0 | 23.0 | 17.0 | 25.0 | 25.0 | 18.0 | 14.0 | 24.0 | 22.0 | 2.35 | 0.59 | 2.0 | 2.0 |

### Arm B — derived summaries (DERIVED_SUMMARY), HOME 240 + AWAY 240

HOME_TEAM (metric·side·window·venue = value [n, reliability]):

- accurate_crosses·FOR·ALL_PRIOR·ALL = 3.7 [n=30, HIGH]
- accurate_crosses·FOR·W5·ALL = 3.4 [n=5, LOW]
- accurate_crosses·FOR·W10·ALL = 4.2 [n=10, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·HOME = 4.3125 [n=16, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·AWAY = 3.0 [n=14, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·ALL = 4.6333 [n=30, HIGH]
- accurate_crosses·AGAINST·W5·ALL = 5.8 [n=5, LOW]
- accurate_crosses·AGAINST·W10·ALL = 4.7 [n=10, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·HOME = 3.875 [n=16, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·AWAY = 5.5 [n=14, MEDIUM]
- big_chances·FOR·ALL_PRIOR·ALL = 2.6667 [n=30, HIGH]
- big_chances·FOR·W5·ALL = 2.2 [n=5, LOW]
- big_chances·FOR·W10·ALL = 2.4 [n=10, MEDIUM]
- big_chances·FOR·ALL_PRIOR·HOME = 3.0 [n=16, MEDIUM]
- big_chances·FOR·ALL_PRIOR·AWAY = 2.2857 [n=14, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·ALL = 2.3333 [n=30, HIGH]
- big_chances·AGAINST·W5·ALL = 1.8 [n=5, LOW]
- big_chances·AGAINST·W10·ALL = 2.1 [n=10, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·HOME = 2.1875 [n=16, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·AWAY = 2.5 [n=14, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·ALL = 3.6333 [n=30, HIGH]
- blocked_shots·FOR·W5·ALL = 3.8 [n=5, LOW]
- blocked_shots·FOR·W10·ALL = 3.8 [n=10, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·HOME = 4.375 [n=16, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·AWAY = 2.7857 [n=14, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·ALL = 2.6 [n=30, HIGH]
- blocked_shots·AGAINST·W5·ALL = 3.8 [n=5, LOW]
- blocked_shots·AGAINST·W10·ALL = 2.8 [n=10, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·HOME = 2.25 [n=16, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·AWAY = 3.0 [n=14, MEDIUM]
- clearances·FOR·ALL_PRIOR·ALL = 33.3667 [n=30, HIGH]
- clearances·FOR·W5·ALL = 36.4 [n=5, LOW]
- clearances·FOR·W10·ALL = 32.4 [n=10, MEDIUM]
- clearances·FOR·ALL_PRIOR·HOME = 30.75 [n=16, MEDIUM]
- clearances·FOR·ALL_PRIOR·AWAY = 36.3571 [n=14, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·ALL = 32.6667 [n=30, HIGH]
- clearances·AGAINST·W5·ALL = 32.2 [n=5, LOW]
- clearances·AGAINST·W10·ALL = 33.7 [n=10, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·HOME = 35.6875 [n=16, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·AWAY = 29.2143 [n=14, MEDIUM]
- corners·FOR·ALL_PRIOR·ALL = 4.2667 [n=30, HIGH]
- corners·FOR·W5·ALL = 4.2 [n=5, LOW]
- corners·FOR·W10·ALL = 4.8 [n=10, MEDIUM]
- corners·FOR·ALL_PRIOR·HOME = 4.4375 [n=16, MEDIUM]
- corners·FOR·ALL_PRIOR·AWAY = 4.0714 [n=14, MEDIUM]
- corners·AGAINST·ALL_PRIOR·ALL = 4.6 [n=30, HIGH]
- corners·AGAINST·W5·ALL = 4.6 [n=5, LOW]
- corners·AGAINST·W10·ALL = 4.1 [n=10, MEDIUM]
- corners·AGAINST·ALL_PRIOR·HOME = 3.9375 [n=16, MEDIUM]
- corners·AGAINST·ALL_PRIOR·AWAY = 5.3571 [n=14, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·ALL = 54.5333 [n=30, HIGH]
- final_third_entries·FOR·W5·ALL = 57.6 [n=5, LOW]
- final_third_entries·FOR·W10·ALL = 60.3 [n=10, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·HOME = 56.625 [n=16, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·AWAY = 52.1429 [n=14, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·ALL = 60.6667 [n=30, HIGH]
- final_third_entries·AGAINST·W5·ALL = 53.2 [n=5, LOW]
- final_third_entries·AGAINST·W10·ALL = 53.6 [n=10, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·HOME = 59.375 [n=16, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·AWAY = 62.1429 [n=14, MEDIUM]
- fouls·FOR·ALL_PRIOR·ALL = 10.8667 [n=30, HIGH]
- fouls·FOR·W5·ALL = 14.8 [n=5, LOW]
- fouls·FOR·W10·ALL = 13.2 [n=10, MEDIUM]
- fouls·FOR·ALL_PRIOR·HOME = 10.6875 [n=16, MEDIUM]
- fouls·FOR·ALL_PRIOR·AWAY = 11.0714 [n=14, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·ALL = 9.5667 [n=30, HIGH]
- fouls·AGAINST·W5·ALL = 12.6 [n=5, LOW]
- fouls·AGAINST·W10·ALL = 10.5 [n=10, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·HOME = 9.875 [n=16, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·AWAY = 9.2143 [n=14, MEDIUM]
- goals·FOR·ALL_PRIOR·ALL = 1.1667 [n=30, HIGH]
- goals·FOR·W5·ALL = 1.4 [n=5, LOW]
- goals·FOR·W10·ALL = 1.3 [n=10, MEDIUM]
- goals·FOR·ALL_PRIOR·HOME = 1.0 [n=16, MEDIUM]
- goals·FOR·ALL_PRIOR·AWAY = 1.3571 [n=14, MEDIUM]
- goals·AGAINST·ALL_PRIOR·ALL = 1.2 [n=30, HIGH]
- goals·AGAINST·W5·ALL = 0.8 [n=5, LOW]
- goals·AGAINST·W10·ALL = 1.3 [n=10, MEDIUM]
- goals·AGAINST·ALL_PRIOR·HOME = 1.1875 [n=16, MEDIUM]
- goals·AGAINST·ALL_PRIOR·AWAY = 1.2143 [n=14, MEDIUM]
- interceptions·FOR·ALL_PRIOR·ALL = 8.4 [n=30, HIGH]
- interceptions·FOR·W5·ALL = 6.2 [n=5, LOW]
- interceptions·FOR·W10·ALL = 7.3 [n=10, MEDIUM]
- interceptions·FOR·ALL_PRIOR·HOME = 7.75 [n=16, MEDIUM]
- interceptions·FOR·ALL_PRIOR·AWAY = 9.1429 [n=14, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·ALL = 8.5 [n=30, HIGH]
- interceptions·AGAINST·W5·ALL = 8.4 [n=5, LOW]
- interceptions·AGAINST·W10·ALL = 8.7 [n=10, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·HOME = 8.9375 [n=16, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·AWAY = 8.0 [n=14, MEDIUM]
- npxg·FOR·ALL_PRIOR·ALL = 1.395 [n=30, HIGH]
- npxg·FOR·W5·ALL = 1.058 [n=5, LOW]
- npxg·FOR·W10·ALL = 1.187 [n=10, MEDIUM]
- npxg·FOR·ALL_PRIOR·HOME = 1.6431 [n=16, MEDIUM]
- npxg·FOR·ALL_PRIOR·AWAY = 1.1114 [n=14, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·ALL = 1.209 [n=30, HIGH]
- npxg·AGAINST·W5·ALL = 1.054 [n=5, LOW]
- npxg·AGAINST·W10·ALL = 1.038 [n=10, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·HOME = 1.0625 [n=16, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·AWAY = 1.3764 [n=14, MEDIUM]
- offsides·FOR·ALL_PRIOR·ALL = 2.0 [n=30, HIGH]
- offsides·FOR·W5·ALL = 1.8 [n=5, LOW]
- offsides·FOR·W10·ALL = 1.7 [n=10, MEDIUM]
- offsides·FOR·ALL_PRIOR·HOME = 2.0625 [n=16, MEDIUM]
- offsides·FOR·ALL_PRIOR·AWAY = 1.9286 [n=14, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·ALL = 1.5 [n=30, HIGH]
- offsides·AGAINST·W5·ALL = 1.0 [n=5, LOW]
- offsides·AGAINST·W10·ALL = 1.2 [n=10, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·HOME = 1.4375 [n=16, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·AWAY = 1.5714 [n=14, MEDIUM]
- possession·FOR·ALL_PRIOR·ALL = 46.6333 [n=30, HIGH]
- possession·FOR·W5·ALL = 53.6 [n=5, LOW]
- possession·FOR·W10·ALL = 52.3 [n=10, MEDIUM]
- possession·FOR·ALL_PRIOR·HOME = 47.4375 [n=16, MEDIUM]
- possession·FOR·ALL_PRIOR·AWAY = 45.7143 [n=14, MEDIUM]
- possession·AGAINST·ALL_PRIOR·ALL = 53.3667 [n=30, HIGH]
- possession·AGAINST·W5·ALL = 46.4 [n=5, LOW]
- possession·AGAINST·W10·ALL = 47.7 [n=10, MEDIUM]
- possession·AGAINST·ALL_PRIOR·HOME = 52.5625 [n=16, MEDIUM]
- possession·AGAINST·ALL_PRIOR·AWAY = 54.2857 [n=14, MEDIUM]
- red_cards·FOR·ALL_PRIOR·ALL = 0.0667 [n=30, HIGH]
- red_cards·FOR·W5·ALL = 0.2 [n=5, LOW]
- red_cards·FOR·W10·ALL = 0.2 [n=10, MEDIUM]
- red_cards·FOR·ALL_PRIOR·HOME = 0.0625 [n=16, MEDIUM]
- red_cards·FOR·ALL_PRIOR·AWAY = 0.0714 [n=14, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·ALL = 0.1333 [n=30, HIGH]
- red_cards·AGAINST·W5·ALL = 0.6 [n=5, LOW]
- red_cards·AGAINST·W10·ALL = 0.4 [n=10, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·HOME = 0.125 [n=16, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·AWAY = 0.1429 [n=14, MEDIUM]
- saves·FOR·ALL_PRIOR·ALL = 2.9667 [n=30, HIGH]
- saves·FOR·W5·ALL = 4.8 [n=5, LOW]
- saves·FOR·W10·ALL = 3.4 [n=10, MEDIUM]
- saves·FOR·ALL_PRIOR·HOME = 2.6875 [n=16, MEDIUM]
- saves·FOR·ALL_PRIOR·AWAY = 3.2857 [n=14, MEDIUM]
- saves·AGAINST·ALL_PRIOR·ALL = 2.4333 [n=30, HIGH]
- saves·AGAINST·W5·ALL = 1.6 [n=5, LOW]
- saves·AGAINST·W10·ALL = 1.9 [n=10, MEDIUM]
- saves·AGAINST·ALL_PRIOR·HOME = 2.9375 [n=16, MEDIUM]
- saves·AGAINST·ALL_PRIOR·AWAY = 1.8571 [n=14, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·ALL = 8.6 [n=30, HIGH]
- shots_inside_box·FOR·W5·ALL = 7.6 [n=5, LOW]
- shots_inside_box·FOR·W10·ALL = 8.5 [n=10, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·HOME = 9.875 [n=16, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·AWAY = 7.1429 [n=14, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·ALL = 7.7667 [n=30, HIGH]
- shots_inside_box·AGAINST·W5·ALL = 8.0 [n=5, LOW]
- shots_inside_box·AGAINST·W10·ALL = 7.3 [n=10, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·HOME = 6.875 [n=16, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·AWAY = 8.7857 [n=14, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·ALL = 4.3333 [n=30, HIGH]
- shots_off_target·FOR·W5·ALL = 4.0 [n=5, LOW]
- shots_off_target·FOR·W10·ALL = 4.3 [n=10, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·HOME = 5.1875 [n=16, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·AWAY = 3.3571 [n=14, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·ALL = 4.2667 [n=30, HIGH]
- shots_off_target·AGAINST·W5·ALL = 2.8 [n=5, LOW]
- shots_off_target·AGAINST·W10·ALL = 3.3 [n=10, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·HOME = 4.1875 [n=16, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·AWAY = 4.3571 [n=14, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·ALL = 3.7 [n=30, HIGH]
- shots_on_target·FOR·W5·ALL = 3.0 [n=5, LOW]
- shots_on_target·FOR·W10·ALL = 3.4 [n=10, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·HOME = 3.9375 [n=16, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·AWAY = 3.4286 [n=14, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·ALL = 4.2333 [n=30, HIGH]
- shots_on_target·AGAINST·W5·ALL = 5.6 [n=5, LOW]
- shots_on_target·AGAINST·W10·ALL = 4.7 [n=10, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·HOME = 3.8125 [n=16, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·AWAY = 4.7143 [n=14, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·ALL = 3.0667 [n=30, HIGH]
- shots_outside_box·FOR·W5·ALL = 3.2 [n=5, LOW]
- shots_outside_box·FOR·W10·ALL = 3.0 [n=10, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·HOME = 3.625 [n=16, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·AWAY = 2.4286 [n=14, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·ALL = 3.3333 [n=30, HIGH]
- shots_outside_box·AGAINST·W5·ALL = 4.2 [n=5, LOW]
- shots_outside_box·AGAINST·W10·ALL = 3.5 [n=10, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·HOME = 3.375 [n=16, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·AWAY = 3.2857 [n=14, MEDIUM]
- tackles·FOR·ALL_PRIOR·ALL = 18.7667 [n=30, HIGH]
- tackles·FOR·W5·ALL = 17.2 [n=5, LOW]
- tackles·FOR·W10·ALL = 16.4 [n=10, MEDIUM]
- tackles·FOR·ALL_PRIOR·HOME = 17.1875 [n=16, MEDIUM]
- tackles·FOR·ALL_PRIOR·AWAY = 20.5714 [n=14, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·ALL = 14.6333 [n=30, HIGH]
- tackles·AGAINST·W5·ALL = 13.8 [n=5, LOW]
- tackles·AGAINST·W10·ALL = 14.9 [n=10, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·HOME = 14.5625 [n=16, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·AWAY = 14.7143 [n=14, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·ALL = 17.1667 [n=30, HIGH]
- throw_ins·FOR·W5·ALL = 18.4 [n=5, LOW]
- throw_ins·FOR·W10·ALL = 17.2 [n=10, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·HOME = 19.25 [n=16, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·AWAY = 14.7857 [n=14, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·ALL = 19.8 [n=30, HIGH]
- throw_ins·AGAINST·W5·ALL = 21.0 [n=5, LOW]
- throw_ins·AGAINST·W10·ALL = 19.0 [n=10, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·HOME = 18.625 [n=16, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·AWAY = 21.1429 [n=14, MEDIUM]
- total_shots·FOR·ALL_PRIOR·ALL = 11.6667 [n=30, HIGH]
- total_shots·FOR·W5·ALL = 10.8 [n=5, LOW]
- total_shots·FOR·W10·ALL = 11.5 [n=10, MEDIUM]
- total_shots·FOR·ALL_PRIOR·HOME = 13.5 [n=16, MEDIUM]
- total_shots·FOR·ALL_PRIOR·AWAY = 9.5714 [n=14, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·ALL = 11.1 [n=30, HIGH]
- total_shots·AGAINST·W5·ALL = 12.2 [n=5, LOW]
- total_shots·AGAINST·W10·ALL = 10.8 [n=10, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·HOME = 10.25 [n=16, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·AWAY = 12.0714 [n=14, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·ALL = 24.8667 [n=30, HIGH]
- touches_in_box·FOR·W5·ALL = 21.2 [n=5, LOW]
- touches_in_box·FOR·W10·ALL = 23.7 [n=10, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·HOME = 28.625 [n=16, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·AWAY = 20.5714 [n=14, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·ALL = 22.8 [n=30, HIGH]
- touches_in_box·AGAINST·W5·ALL = 21.2 [n=5, LOW]
- touches_in_box·AGAINST·W10·ALL = 19.5 [n=10, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·HOME = 21.0 [n=16, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·AWAY = 24.8571 [n=14, MEDIUM]
- xg·FOR·ALL_PRIOR·ALL = 1.581 [n=30, HIGH]
- xg·FOR·W5·ALL = 1.412 [n=5, LOW]
- xg·FOR·W10·ALL = 1.443 [n=10, MEDIUM]
- xg·FOR·ALL_PRIOR·HOME = 1.8044 [n=16, MEDIUM]
- xg·FOR·ALL_PRIOR·AWAY = 1.3257 [n=14, MEDIUM]
- xg·AGAINST·ALL_PRIOR·ALL = 1.3187 [n=30, HIGH]
- xg·AGAINST·W5·ALL = 1.526 [n=5, LOW]
- xg·AGAINST·W10·ALL = 1.341 [n=10, MEDIUM]
- xg·AGAINST·ALL_PRIOR·HOME = 1.2381 [n=16, MEDIUM]
- xg·AGAINST·ALL_PRIOR·AWAY = 1.4107 [n=14, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·ALL = 2.2593 [n=27, HIGH]
- yellow_cards·FOR·W5·ALL = 2.2 [n=5, LOW]
- yellow_cards·FOR·W10·ALL = 2.6 [n=10, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·HOME = 1.875 [n=16, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·AWAY = 2.8182 [n=11, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·ALL = 2.2222 [n=27, HIGH]
- yellow_cards·AGAINST·W5·ALL = 2.8 [n=5, LOW]
- yellow_cards·AGAINST·W10·ALL = 2.2 [n=10, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·HOME = 2.4375 [n=16, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·AWAY = 1.9091 [n=11, MEDIUM]

AWAY_TEAM:

- accurate_crosses·FOR·ALL_PRIOR·ALL = 3.4 [n=30, HIGH]
- accurate_crosses·FOR·W5·ALL = 3.4 [n=5, LOW]
- accurate_crosses·FOR·W10·ALL = 3.5 [n=10, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·HOME = 3.2 [n=15, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·AWAY = 3.6 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·ALL = 5.8 [n=30, HIGH]
- accurate_crosses·AGAINST·W5·ALL = 5.8 [n=5, LOW]
- accurate_crosses·AGAINST·W10·ALL = 5.4 [n=10, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·HOME = 5.1333 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·AWAY = 6.4667 [n=15, MEDIUM]
- big_chances·FOR·ALL_PRIOR·ALL = 1.9333 [n=30, HIGH]
- big_chances·FOR·W5·ALL = 2.6 [n=5, LOW]
- big_chances·FOR·W10·ALL = 2.5 [n=10, MEDIUM]
- big_chances·FOR·ALL_PRIOR·HOME = 2.1333 [n=15, MEDIUM]
- big_chances·FOR·ALL_PRIOR·AWAY = 1.7333 [n=15, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·ALL = 2.4 [n=30, HIGH]
- big_chances·AGAINST·W5·ALL = 1.2 [n=5, LOW]
- big_chances·AGAINST·W10·ALL = 1.5 [n=10, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·HOME = 1.9333 [n=15, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·AWAY = 2.8667 [n=15, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·ALL = 3.0667 [n=30, HIGH]
- blocked_shots·FOR·W5·ALL = 2.8 [n=5, LOW]
- blocked_shots·FOR·W10·ALL = 3.0 [n=10, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·HOME = 3.5333 [n=15, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·AWAY = 2.6 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·ALL = 4.6 [n=30, HIGH]
- blocked_shots·AGAINST·W5·ALL = 5.6 [n=5, LOW]
- blocked_shots·AGAINST·W10·ALL = 4.7 [n=10, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·HOME = 3.8 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·AWAY = 5.4 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·ALL = 30.6 [n=30, HIGH]
- clearances·FOR·W5·ALL = 25.2 [n=5, LOW]
- clearances·FOR·W10·ALL = 28.3 [n=10, MEDIUM]
- clearances·FOR·ALL_PRIOR·HOME = 28.5333 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·AWAY = 32.6667 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·ALL = 22.5667 [n=30, HIGH]
- clearances·AGAINST·W5·ALL = 18.6 [n=5, LOW]
- clearances·AGAINST·W10·ALL = 20.7 [n=10, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·HOME = 23.6 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·AWAY = 21.5333 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·ALL = 4.9 [n=30, HIGH]
- corners·FOR·W5·ALL = 4.4 [n=5, LOW]
- corners·FOR·W10·ALL = 4.4 [n=10, MEDIUM]
- corners·FOR·ALL_PRIOR·HOME = 5.4 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·AWAY = 4.4 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·ALL = 6.5 [n=30, HIGH]
- corners·AGAINST·W5·ALL = 7.8 [n=5, LOW]
- corners·AGAINST·W10·ALL = 6.4 [n=10, MEDIUM]
- corners·AGAINST·ALL_PRIOR·HOME = 5.8667 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·AWAY = 7.1333 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·ALL = 48.3667 [n=30, HIGH]
- final_third_entries·FOR·W5·ALL = 42.8 [n=5, LOW]
- final_third_entries·FOR·W10·ALL = 48.1 [n=10, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·HOME = 48.9333 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·AWAY = 47.8 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·ALL = 61.0333 [n=30, HIGH]
- final_third_entries·AGAINST·W5·ALL = 61.8 [n=5, LOW]
- final_third_entries·AGAINST·W10·ALL = 63.1 [n=10, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·HOME = 61.7333 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·AWAY = 60.3333 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·ALL = 11.1667 [n=30, HIGH]
- fouls·FOR·W5·ALL = 11.0 [n=5, LOW]
- fouls·FOR·W10·ALL = 10.7 [n=10, MEDIUM]
- fouls·FOR·ALL_PRIOR·HOME = 11.4 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·AWAY = 10.9333 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·ALL = 10.7 [n=30, HIGH]
- fouls·AGAINST·W5·ALL = 8.2 [n=5, LOW]
- fouls·AGAINST·W10·ALL = 9.4 [n=10, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·HOME = 10.0 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·AWAY = 11.4 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·ALL = 1.3 [n=30, HIGH]
- goals·FOR·W5·ALL = 1.6 [n=5, LOW]
- goals·FOR·W10·ALL = 1.6 [n=10, MEDIUM]
- goals·FOR·ALL_PRIOR·HOME = 1.4 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·AWAY = 1.2 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·ALL = 1.6333 [n=30, HIGH]
- goals·AGAINST·W5·ALL = 1.6 [n=5, LOW]
- goals·AGAINST·W10·ALL = 1.3 [n=10, MEDIUM]
- goals·AGAINST·ALL_PRIOR·HOME = 1.5333 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·AWAY = 1.7333 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·ALL = 9.6 [n=30, HIGH]
- interceptions·FOR·W5·ALL = 10.4 [n=5, LOW]
- interceptions·FOR·W10·ALL = 10.4 [n=10, MEDIUM]
- interceptions·FOR·ALL_PRIOR·HOME = 8.2667 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·AWAY = 10.9333 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·ALL = 7.3 [n=30, HIGH]
- interceptions·AGAINST·W5·ALL = 6.4 [n=5, LOW]
- interceptions·AGAINST·W10·ALL = 6.2 [n=10, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·HOME = 7.9333 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·AWAY = 6.6667 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·ALL = 1.1907 [n=30, HIGH]
- npxg·FOR·W5·ALL = 1.244 [n=5, LOW]
- npxg·FOR·W10·ALL = 1.3 [n=10, MEDIUM]
- npxg·FOR·ALL_PRIOR·HOME = 1.2553 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·AWAY = 1.126 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·ALL = 1.4507 [n=30, HIGH]
- npxg·AGAINST·W5·ALL = 1.442 [n=5, LOW]
- npxg·AGAINST·W10·ALL = 1.321 [n=10, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·HOME = 1.192 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·AWAY = 1.7093 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·ALL = 1.931 [n=29, HIGH]
- offsides·FOR·W5·ALL = 3.0 [n=5, LOW]
- offsides·FOR·W10·ALL = 2.1 [n=10, MEDIUM]
- offsides·FOR·ALL_PRIOR·HOME = 1.8667 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·AWAY = 2.0 [n=14, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·ALL = 1.2414 [n=29, HIGH]
- offsides·AGAINST·W5·ALL = 0.8 [n=5, LOW]
- offsides·AGAINST·W10·ALL = 1.1 [n=10, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·HOME = 1.6 [n=15, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·AWAY = 0.8571 [n=14, MEDIUM]
- possession·FOR·ALL_PRIOR·ALL = 41.6 [n=30, HIGH]
- possession·FOR·W5·ALL = 41.0 [n=5, LOW]
- possession·FOR·W10·ALL = 40.6 [n=10, MEDIUM]
- possession·FOR·ALL_PRIOR·HOME = 41.8667 [n=15, MEDIUM]
- possession·FOR·ALL_PRIOR·AWAY = 41.3333 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·ALL = 58.4 [n=30, HIGH]
- possession·AGAINST·W5·ALL = 59.0 [n=5, LOW]
- possession·AGAINST·W10·ALL = 59.4 [n=10, MEDIUM]
- possession·AGAINST·ALL_PRIOR·HOME = 58.1333 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·AWAY = 58.6667 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·ALL = 0.1 [n=30, HIGH]
- red_cards·FOR·W5·ALL = 0.0 [n=5, LOW]
- red_cards·FOR·W10·ALL = 0.1 [n=10, MEDIUM]
- red_cards·FOR·ALL_PRIOR·HOME = 0.1333 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·AWAY = 0.0667 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·ALL = 0.0 [n=30, HIGH]
- red_cards·AGAINST·W5·ALL = 0.0 [n=5, LOW]
- red_cards·AGAINST·W10·ALL = 0.0 [n=10, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·HOME = 0.0 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·AWAY = 0.0 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·ALL = 3.7667 [n=30, HIGH]
- saves·FOR·W5·ALL = 4.0 [n=5, LOW]
- saves·FOR·W10·ALL = 3.5 [n=10, MEDIUM]
- saves·FOR·ALL_PRIOR·HOME = 3.2 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·AWAY = 4.3333 [n=15, MEDIUM]
- saves·AGAINST·ALL_PRIOR·ALL = 2.2667 [n=30, HIGH]
- saves·AGAINST·W5·ALL = 2.0 [n=5, LOW]
- saves·AGAINST·W10·ALL = 2.3 [n=10, MEDIUM]
- saves·AGAINST·ALL_PRIOR·HOME = 2.3333 [n=15, MEDIUM]
- saves·AGAINST·ALL_PRIOR·AWAY = 2.2 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·ALL = 7.5667 [n=30, HIGH]
- shots_inside_box·FOR·W5·ALL = 7.4 [n=5, LOW]
- shots_inside_box·FOR·W10·ALL = 7.5 [n=10, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·HOME = 7.6 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·AWAY = 7.5333 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·ALL = 10.8333 [n=30, HIGH]
- shots_inside_box·AGAINST·W5·ALL = 12.8 [n=5, LOW]
- shots_inside_box·AGAINST·W10·ALL = 10.2 [n=10, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·HOME = 9.2 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·AWAY = 12.4667 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·ALL = 3.7667 [n=30, HIGH]
- shots_off_target·FOR·W5·ALL = 3.6 [n=5, LOW]
- shots_off_target·FOR·W10·ALL = 3.8 [n=10, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·HOME = 3.7333 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·AWAY = 3.8 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·ALL = 5.6667 [n=30, HIGH]
- shots_off_target·AGAINST·W5·ALL = 7.2 [n=5, LOW]
- shots_off_target·AGAINST·W10·ALL = 5.4 [n=10, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·HOME = 5.4 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·AWAY = 5.9333 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·ALL = 3.4333 [n=30, HIGH]
- shots_on_target·FOR·W5·ALL = 3.2 [n=5, LOW]
- shots_on_target·FOR·W10·ALL = 3.7 [n=10, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·HOME = 3.6 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·AWAY = 3.2667 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·ALL = 5.3 [n=30, HIGH]
- shots_on_target·AGAINST·W5·ALL = 5.6 [n=5, LOW]
- shots_on_target·AGAINST·W10·ALL = 4.9 [n=10, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·HOME = 4.6667 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·AWAY = 5.9333 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·ALL = 2.7 [n=30, HIGH]
- shots_outside_box·FOR·W5·ALL = 2.2 [n=5, LOW]
- shots_outside_box·FOR·W10·ALL = 3.0 [n=10, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·HOME = 3.2667 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·AWAY = 2.1333 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·ALL = 4.7333 [n=30, HIGH]
- shots_outside_box·AGAINST·W5·ALL = 5.6 [n=5, LOW]
- shots_outside_box·AGAINST·W10·ALL = 4.8 [n=10, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·HOME = 4.6667 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·AWAY = 4.8 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·ALL = 18.0333 [n=30, HIGH]
- tackles·FOR·W5·ALL = 16.6 [n=5, LOW]
- tackles·FOR·W10·ALL = 17.3 [n=10, MEDIUM]
- tackles·FOR·ALL_PRIOR·HOME = 19.9333 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·AWAY = 16.1333 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·ALL = 15.8 [n=30, HIGH]
- tackles·AGAINST·W5·ALL = 14.8 [n=5, LOW]
- tackles·AGAINST·W10·ALL = 15.0 [n=10, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·HOME = 14.7333 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·AWAY = 16.8667 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·ALL = 17.7667 [n=30, HIGH]
- throw_ins·FOR·W5·ALL = 19.4 [n=5, LOW]
- throw_ins·FOR·W10·ALL = 18.3 [n=10, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·HOME = 19.0 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·AWAY = 16.5333 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·ALL = 20.3667 [n=30, HIGH]
- throw_ins·AGAINST·W5·ALL = 19.8 [n=5, LOW]
- throw_ins·AGAINST·W10·ALL = 21.3 [n=10, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·HOME = 20.8667 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·AWAY = 19.8667 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·ALL = 10.2667 [n=30, HIGH]
- total_shots·FOR·W5·ALL = 9.6 [n=5, LOW]
- total_shots·FOR·W10·ALL = 10.5 [n=10, MEDIUM]
- total_shots·FOR·ALL_PRIOR·HOME = 10.8667 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·AWAY = 9.6667 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·ALL = 15.5667 [n=30, HIGH]
- total_shots·AGAINST·W5·ALL = 18.4 [n=5, LOW]
- total_shots·AGAINST·W10·ALL = 15.0 [n=10, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·HOME = 13.8667 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·AWAY = 17.2667 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·ALL = 19.0667 [n=30, HIGH]
- touches_in_box·FOR·W5·ALL = 18.4 [n=5, LOW]
- touches_in_box·FOR·W10·ALL = 19.9 [n=10, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·HOME = 18.6667 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·AWAY = 19.4667 [n=15, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·ALL = 30.4667 [n=30, HIGH]
- touches_in_box·AGAINST·W5·ALL = 32.6 [n=5, LOW]
- touches_in_box·AGAINST·W10·ALL = 27.3 [n=10, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·HOME = 25.9333 [n=15, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·AWAY = 35.0 [n=15, MEDIUM]
- xg·FOR·ALL_PRIOR·ALL = 1.2377 [n=30, HIGH]
- xg·FOR·W5·ALL = 1.352 [n=5, LOW]
- xg·FOR·W10·ALL = 1.428 [n=10, MEDIUM]
- xg·FOR·ALL_PRIOR·HOME = 1.3247 [n=15, MEDIUM]
- xg·FOR·ALL_PRIOR·AWAY = 1.1507 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·ALL = 1.5777 [n=30, HIGH]
- xg·AGAINST·W5·ALL = 1.43 [n=5, LOW]
- xg·AGAINST·W10·ALL = 1.29 [n=10, MEDIUM]
- xg·AGAINST·ALL_PRIOR·HOME = 1.3313 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·AWAY = 1.824 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·ALL = 1.8966 [n=29, HIGH]
- yellow_cards·FOR·W5·ALL = 2.2 [n=5, LOW]
- yellow_cards·FOR·W10·ALL = 1.8 [n=10, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·HOME = 1.7333 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·AWAY = 2.0714 [n=14, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·ALL = 2.0345 [n=29, HIGH]
- yellow_cards·AGAINST·W5·ALL = 1.6 [n=5, LOW]
- yellow_cards·AGAINST·W10·ALL = 2.0 [n=10, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·HOME = 1.9333 [n=15, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·AWAY = 2.1429 [n=14, MEDIUM]

### Arm B — opponent-profile context (deterministic bands)

```json
{
 "axes": {
  "accurate_crosses_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "corners_against": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  },
  "corners_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "goals_against": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  },
  "goals_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "possession_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "shots_on_target_against": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  },
  "shots_on_target_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  }
 },
 "similarity_version": "opponent_similarity_v1_pending"
}
```

---

## mt_010244159

- PIT-safe matches available: **142**; match rows included (both teams): **60**; omitted: **82** (reason: `frozen_history_policy(max_matches_per_team=30)`); UNEXPLAINED_OMISSION: **0**.
- Metric cell exposure rate (non-null of serialized): **0.9958**; derived summaries: **480**.
- Availability map: `{"expected_formation": "UNAVAILABLE", "formation": "LOW_COVERAGE", "half_time_state": "UNAVAILABLE", "injuries": "UNAVAILABLE", "lineup": "PIT_UNSAFE", "opponent_profile": "AVAILABLE", "recent_vs_long": "AVAILABLE", "red_cards": "AVAILABLE", "temporal_event_state": "UNAVAILABLE", "venue": "AVAILABLE", "xg": "AVAILABLE"}`
- Arm A packet hash: `9ad28ea4dabdcd04ba8b8491bc66a46d681e41ca6ef9e15e8e261e467e084855`
- Arm B packet hash: `767c9cae6c127413cc013b284bc47b16c2fc2d0c92cf58cd03cc796b6d10541d`

### Arm A — frozen V3 compressed evidence (all items)

76 unconditional shrunk scalar items (venue=ALL, window=ALL_PRIOR):

| id | metric | value | n | reliability |
|---|---|---|---|---|
| HOME_ATK_corners_406027 | corners_for | 5.0813 | 71 | HIGH |
| HOME_DEF_corners_7cfac3 | corners_against | 5.1073 | 71 | HIGH |
| HOME_ATK_accurate_crosses_c28b9e | accurate_crosses_for | 5.4725 | 71 | HIGH |
| HOME_DEF_accurate_crosses_81ffb5 | accurate_crosses_against | 3.8621 | 71 | HIGH |
| HOME_ATK_total_shots_808ac9 | total_shots_for | 13.066 | 71 | HIGH |
| HOME_DEF_total_shots_c0e347 | total_shots_against | 11.6894 | 71 | HIGH |
| HOME_ATK_shots_on_target_e955e0 | shots_on_target_for | 4.1451 | 71 | HIGH |
| HOME_DEF_shots_on_target_8a3812 | shots_on_target_against | 4.1321 | 71 | HIGH |
| HOME_ATK_shots_off_target_11e91f | shots_off_target_for | 4.971 | 71 | HIGH |
| HOME_DEF_shots_off_target_26031c | shots_off_target_against | 4.2307 | 71 | HIGH |
| HOME_ATK_blocked_shots_5198f8 | blocked_shots_for | 3.9632 | 71 | HIGH |
| HOME_DEF_blocked_shots_09c3c4 | blocked_shots_against | 3.3268 | 71 | HIGH |
| HOME_ATK_shots_inside_box_cf538d | shots_inside_box_for | 9.1269 | 71 | HIGH |
| HOME_DEF_shots_inside_box_e6b28d | shots_inside_box_against | 8.2049 | 71 | HIGH |
| HOME_ATK_touches_in_box_759ed8 | touches_in_box_for | 25.4277 | 71 | HIGH |
| HOME_DEF_touches_in_box_94cd98 | touches_in_box_against | 24.2459 | 71 | HIGH |
| HOME_ATK_final_third_entries_5aa0be | final_third_entries_for | 52.2938 | 71 | HIGH |
| HOME_DEF_final_third_entries_4a40ef | final_third_entries_against | 54.8912 | 71 | HIGH |
| HOME_ATK_possession_190f3f | possession_for | 51.8831 | 71 | HIGH |
| HOME_DEF_possession_f8ada9 | possession_against | 48.1169 | 71 | HIGH |
| HOME_ATK_tackles_65b6c1 | tackles_for | 17.2696 | 71 | HIGH |
| HOME_DEF_tackles_e3c85e | tackles_against | 14.4774 | 71 | HIGH |
| HOME_ATK_fouls_8107c6 | fouls_for | 11.0573 | 71 | HIGH |
| HOME_DEF_fouls_b6d53c | fouls_against | 9.6417 | 71 | HIGH |
| HOME_ATK_yellow_cards_80b7a4 | yellow_cards_for | 2.2332 | 65 | HIGH |
| HOME_DEF_yellow_cards_8ee8aa | yellow_cards_against | 1.8811 | 65 | HIGH |
| HOME_ATK_clearances_ec2e18 | clearances_for | 25.4002 | 71 | HIGH |
| HOME_DEF_clearances_6d3f4c | clearances_against | 24.2443 | 71 | HIGH |
| HOME_ATK_interceptions_967965 | interceptions_for | 8.1186 | 71 | HIGH |
| HOME_DEF_interceptions_c82020 | interceptions_against | 8.3913 | 71 | HIGH |
| HOME_ATK_goals_08b15b | goals_for | 1.3706 | 71 | HIGH |
| HOME_DEF_goals_d53fdd | goals_against | 1.4096 | 71 | HIGH |
| HOME_ATK_throw_ins_b24629 | throw_ins_for | 18.0038 | 71 | HIGH |
| HOME_DEF_throw_ins_208262 | throw_ins_against | 17.0557 | 71 | HIGH |
| HOME_ATK_big_chances_8a9e2f | big_chances_for | 1.9383 | 70 | HIGH |
| HOME_DEF_big_chances_885151 | big_chances_against | 2.3594 | 70 | HIGH |
| HOME_ATK_saves_6bda8d | saves_for | 2.7843 | 70 | HIGH |
| HOME_DEF_saves_19ae14 | saves_against | 2.7975 | 70 | HIGH |
| AWAY_ATK_corners_ca1538 | corners_for | 5.6268 | 71 | HIGH |
| AWAY_DEF_corners_598e33 | corners_against | 4.7047 | 71 | HIGH |
| AWAY_ATK_accurate_crosses_005290 | accurate_crosses_for | 3.5504 | 71 | HIGH |
| AWAY_DEF_accurate_crosses_287e9c | accurate_crosses_against | 3.9919 | 71 | HIGH |
| AWAY_ATK_total_shots_004f7a | total_shots_for | 12.7803 | 71 | HIGH |
| AWAY_DEF_total_shots_403d28 | total_shots_against | 12.4296 | 71 | HIGH |
| AWAY_ATK_shots_on_target_9afd02 | shots_on_target_for | 4.4568 | 71 | HIGH |
| AWAY_DEF_shots_on_target_dcda5e | shots_on_target_against | 4.262 | 71 | HIGH |
| AWAY_ATK_shots_off_target_b83815 | shots_off_target_for | 4.6463 | 71 | HIGH |
| AWAY_DEF_shots_off_target_5fe2d0 | shots_off_target_against | 4.8541 | 71 | HIGH |
| AWAY_ATK_blocked_shots_93d965 | blocked_shots_for | 3.6905 | 71 | HIGH |
| AWAY_DEF_blocked_shots_97ef03 | blocked_shots_against | 3.3268 | 71 | HIGH |
| AWAY_ATK_shots_inside_box_567ee5 | shots_inside_box_for | 8.5555 | 71 | HIGH |
| AWAY_DEF_shots_inside_box_446c80 | shots_inside_box_against | 8.3217 | 71 | HIGH |
| AWAY_ATK_touches_in_box_2c76ca | touches_in_box_for | 26.6355 | 71 | HIGH |
| AWAY_DEF_touches_in_box_319da5 | touches_in_box_against | 24.6225 | 71 | HIGH |
| AWAY_ATK_final_third_entries_5a0987 | final_third_entries_for | 49.2938 | 71 | HIGH |
| AWAY_DEF_final_third_entries_ed75cd | final_third_entries_against | 50.4237 | 71 | HIGH |
| AWAY_ATK_possession_82105a | possession_for | 51.8701 | 71 | HIGH |
| AWAY_DEF_possession_012ecc | possession_against | 48.1299 | 71 | HIGH |
| AWAY_ATK_tackles_0865bc | tackles_for | 16.1268 | 71 | HIGH |
| AWAY_DEF_tackles_3e6a7d | tackles_against | 18.3086 | 71 | HIGH |
| AWAY_ATK_fouls_97bf91 | fouls_for | 10.3171 | 71 | HIGH |
| AWAY_DEF_fouls_94f7aa | fouls_against | 12.9404 | 71 | HIGH |
| AWAY_ATK_yellow_cards_120c77 | yellow_cards_for | 1.8124 | 71 | HIGH |
| AWAY_DEF_yellow_cards_367397 | yellow_cards_against | 2.5527 | 71 | HIGH |
| AWAY_ATK_clearances_74617f | clearances_for | 20.4911 | 71 | HIGH |
| AWAY_DEF_clearances_8bdc80 | clearances_against | 22.8677 | 71 | HIGH |
| AWAY_ATK_interceptions_404e22 | interceptions_for | 6.3134 | 71 | HIGH |
| AWAY_DEF_interceptions_4be11b | interceptions_against | 9.1575 | 71 | HIGH |
| AWAY_ATK_goals_5d2c6a | goals_for | 1.4745 | 71 | HIGH |
| AWAY_DEF_goals_4ad3b7 | goals_against | 1.3057 | 71 | HIGH |
| AWAY_ATK_throw_ins_64d189 | throw_ins_for | 14.4194 | 71 | HIGH |
| AWAY_DEF_throw_ins_35916f | throw_ins_against | 13.783 | 71 | HIGH |
| AWAY_ATK_big_chances_065222 | big_chances_for | 2.6709 | 69 | HIGH |
| AWAY_DEF_big_chances_d5f920 | big_chances_against | 2.2975 | 69 | HIGH |
| AWAY_ATK_saves_50b33b | saves_for | 2.891 | 71 | HIGH |
| AWAY_DEF_saves_bf5cbb | saves_against | 3.0468 | 71 | HIGH |

### Arm B — HOME_TEAM match-level matrix (30 rows × 55 cols)

Columns: `match_alias, kickoff_unix, competition, venue, opponent_alias, own_formation_family, opponent_formation_family, accurate_crosses_for, accurate_crosses_against, big_chances_for, big_chances_against, blocked_shots_for, blocked_shots_against, clearances_for, clearances_against, corners_for, corners_against, final_third_entries_for, final_third_entries_against, fouls_for, fouls_against, goals_for, goals_against, interceptions_for, interceptions_against, npxg_for, npxg_against, offsides_for, offsides_against, possession_for, possession_against, red_cards_for, red_cards_against, saves_for, saves_against, shots_inside_box_for, shots_inside_box_against, shots_off_target_for, shots_off_target_against, shots_on_target_for, shots_on_target_against, shots_outside_box_for, shots_outside_box_against, tackles_for, tackles_against, throw_ins_for, throw_ins_against, total_shots_for, total_shots_against, touches_in_box_for, touches_in_box_against, xg_for, xg_against, yellow_cards_for, yellow_cards_against`

| match_alias | kickoff_unix | competition | venue | opponent_alias | own_formation_family | opponent_formation_family | accurate_crosses_for | accurate_crosses_against | big_chances_for | big_chances_against | blocked_shots_for | blocked_shots_against | clearances_for | clearances_against | corners_for | corners_against | final_third_entries_for | final_third_entries_against | fouls_for | fouls_against | goals_for | goals_against | interceptions_for | interceptions_against | npxg_for | npxg_against | offsides_for | offsides_against | possession_for | possession_against | red_cards_for | red_cards_against | saves_for | saves_against | shots_inside_box_for | shots_inside_box_against | shots_off_target_for | shots_off_target_against | shots_on_target_for | shots_on_target_against | shots_outside_box_for | shots_outside_box_against | tackles_for | tackles_against | throw_ins_for | throw_ins_against | total_shots_for | total_shots_against | touches_in_box_for | touches_in_box_against | xg_for | xg_against | yellow_cards_for | yellow_cards_against |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| m_mt_747395666 | 1757772000 | COMPETITION | HOME | OPP_001 | BACK_FOUR | BACK_FOUR | 3.0 | 1.0 | 2.0 | 1.0 | 0.0 | 4.0 | 23.0 | 30.0 | 3.0 | 3.0 | 76.0 | 54.0 | 20.0 | 15.0 | 1.0 | 0.0 | 6.0 | 7.0 | 0.92 | 0.79 | 1.0 | 3.0 | 54.0 | 46.0 | 0.0 | 0.0 | 3.0 | 3.0 | 3.0 | 7.0 | 2.0 | 3.0 | 3.0 | 3.0 | 2.0 | 3.0 | 24.0 | 18.0 | 25.0 | 15.0 | 5.0 | 10.0 | 10.0 | 21.0 | 0.85 | 0.79 | 1.0 | 2.0 |
| m_mt_585124572 | 1758394800 | COMPETITION | HOME | OPP_002 |  |  | 5.0 | 2.0 | 3.0 | 1.0 | 6.0 | 3.0 | 39.0 | 18.0 | 2.0 | 10.0 | 40.0 | 46.0 | 11.0 | 13.0 | 3.0 | 1.0 | 6.0 | 5.0 | 1.01 | 0.6 | 2.0 | 2.0 | 53.0 | 47.0 | 0.0 | 0.0 | 2.0 | 2.0 | 8.0 | 8.0 | 5.0 | 2.0 | 3.0 | 3.0 | 6.0 | 0.0 | 19.0 | 13.0 | 16.0 | 23.0 | 14.0 | 8.0 | 27.0 | 17.0 | 1.01 | 0.6 | 4.0 | 1.0 |
| m_mt_252067206 | 1759064400 | COMPETITION | AWAY | OPP_003 |  |  | 7.0 | 1.0 | 1.0 | 3.0 | 3.0 | 2.0 | 23.0 | 26.0 | 8.0 | 2.0 | 56.0 | 43.0 | 13.0 | 10.0 | 1.0 | 3.0 | 9.0 | 7.0 | 1.06 | 1.11 | 4.0 | 2.0 | 52.0 | 48.0 | 0.0 | 0.0 | 1.0 | 3.0 | 9.0 | 4.0 | 4.0 | 3.0 | 4.0 | 4.0 | 2.0 | 5.0 | 16.0 | 10.0 | 18.0 | 11.0 | 11.0 | 9.0 | 27.0 | 18.0 | 0.92 | 1.11 | 4.0 | 1.0 |
| m_mt_252067281 | 1759518000 | COMPETITION | AWAY | OPP_004 |  |  | 3.0 | 1.0 | 1.0 | 1.0 | 4.0 | 3.0 | 38.0 | 23.0 | 3.0 | 4.0 | 55.0 | 89.0 | 10.0 | 8.0 | 1.0 | 3.0 | 7.0 | 8.0 | 0.88 | 1.2 | 2.0 | 2.0 | 46.0 | 54.0 | 0.0 | 0.0 | 3.0 | 3.0 | 5.0 | 6.0 | 4.0 | 2.0 | 4.0 | 6.0 | 7.0 | 5.0 | 11.0 | 10.0 | 19.0 | 28.0 | 12.0 | 11.0 | 17.0 | 30.0 | 0.88 | 1.12 | 1.0 | 0.0 |
| m_mt_747390117 | 1760805000 | COMPETITION | HOME | OPP_005 |  |  | 2.0 | 5.0 | 0.0 | 3.0 | 3.0 | 4.0 | 35.0 | 29.0 | 6.0 | 10.0 | 37.0 | 80.0 | 11.0 | 4.0 | 0.0 | 1.0 | 7.0 | 1.0 | 0.4 | 1.32 | 0.0 | 2.0 | 37.0 | 63.0 | 0.0 | 0.0 | 4.0 | 0.0 | 6.0 | 14.0 | 6.0 | 7.0 | 0.0 | 5.0 | 3.0 | 2.0 | 20.0 | 9.0 | 17.0 | 17.0 | 9.0 | 16.0 | 16.0 | 46.0 | 0.44 | 1.87 |  |  |
| m_mt_747390194 | 1761400800 | COMPETITION | AWAY | OPP_006 |  |  | 1.0 | 6.0 | 2.0 | 4.0 | 5.0 | 5.0 | 21.0 | 20.0 | 3.0 | 4.0 | 48.0 | 51.0 | 18.0 | 11.0 | 1.0 | 2.0 | 9.0 | 7.0 | 1.53 | 2.18 | 1.0 | 0.0 | 49.0 | 51.0 | 0.0 | 0.0 | 5.0 | 4.0 | 8.0 | 10.0 | 2.0 | 6.0 | 5.0 | 7.0 | 4.0 | 8.0 | 19.0 | 14.0 | 23.0 | 19.0 | 12.0 | 18.0 | 25.0 | 35.0 | 1.53 | 2.14 | 2.0 | 0.0 |
| m_mt_747390153 | 1762009200 | COMPETITION | HOME | OPP_007 | BACK_FOUR | BACK_FIVE | 6.0 | 4.0 | 2.0 | 1.0 | 8.0 | 1.0 | 22.0 | 31.0 | 10.0 | 1.0 | 58.0 | 64.0 | 13.0 | 14.0 | 3.0 | 0.0 | 4.0 | 10.0 | 1.42 | 0.39 | 3.0 | 0.0 | 63.0 | 37.0 | 0.0 | 1.0 | 2.0 | 4.0 | 11.0 | 3.0 | 5.0 | 2.0 | 6.0 | 2.0 | 8.0 | 2.0 | 6.0 | 17.0 | 31.0 | 13.0 | 19.0 | 5.0 | 37.0 | 17.0 | 1.39 | 0.24 | 1.0 | 3.0 |
| m_mt_585124337 | 1762614000 | COMPETITION | AWAY | OPP_008 |  |  | 2.0 | 6.0 | 0.0 | 4.0 | 3.0 | 4.0 | 34.0 | 23.0 | 5.0 | 7.0 | 37.0 | 53.0 | 14.0 | 11.0 | 0.0 | 2.0 | 13.0 | 4.0 | 0.41 | 1.44 | 1.0 | 5.0 | 50.0 | 50.0 | 0.0 | 0.0 | 3.0 | 4.0 | 5.0 | 6.0 | 1.0 | 5.0 | 4.0 | 5.0 | 3.0 | 8.0 | 17.0 | 15.0 | 18.0 | 22.0 | 8.0 | 14.0 | 19.0 | 26.0 | 0.4 | 1.44 | 2.0 | 2.0 |
| m_mt_404678291 | 1763823600 | COMPETITION | HOME | OPP_009 |  |  | 8.0 | 2.0 | 4.0 | 0.0 | 5.0 | 1.0 | 28.0 | 25.0 | 7.0 | 4.0 | 51.0 | 51.0 | 5.0 | 13.0 | 1.0 | 0.0 | 6.0 | 9.0 | 2.16 | 0.2 | 1.0 | 3.0 | 57.0 | 43.0 | 0.0 | 0.0 | 2.0 | 4.0 | 18.0 | 4.0 | 13.0 | 1.0 | 6.0 | 2.0 | 6.0 | 0.0 | 11.0 | 21.0 | 20.0 | 17.0 | 24.0 | 4.0 | 46.0 | 22.0 | 2.16 | 0.17 | 3.0 | 3.0 |
| m_mt_363781417 | 1764446400 | COMPETITION | AWAY | OPP_010 |  |  | 1.0 | 6.0 | 0.0 | 2.0 | 3.0 | 6.0 | 45.0 | 19.0 | 2.0 | 8.0 | 32.0 | 73.0 | 7.0 | 11.0 | 2.0 | 1.0 | 9.0 | 11.0 | 0.42 | 0.86 | 4.0 | 3.0 | 37.0 | 63.0 | 0.0 | 0.0 | 0.0 | 1.0 | 3.0 | 10.0 | 1.0 | 6.0 | 3.0 | 2.0 | 4.0 | 4.0 | 25.0 | 14.0 | 23.0 | 26.0 | 7.0 | 14.0 | 14.0 | 26.0 | 0.42 | 0.86 | 2.0 | 3.0 |
| m_mt_404678226 | 1764703800 | COMPETITION | HOME | OPP_011 |  |  | 5.0 | 4.0 | 1.0 | 3.0 | 3.0 | 4.0 | 19.0 | 27.0 | 7.0 | 2.0 | 47.0 | 41.0 | 9.0 | 7.0 | 4.0 | 5.0 | 11.0 | 16.0 | 1.01 | 2.48 | 4.0 | 1.0 | 57.0 | 43.0 | 0.0 | 0.0 | 0.0 | 1.0 | 9.0 | 9.0 | 3.0 | 3.0 | 6.0 | 4.0 | 3.0 | 2.0 | 18.0 | 16.0 | 18.0 | 18.0 | 12.0 | 11.0 | 23.0 | 23.0 | 0.91 | 2.17 | 0.0 | 1.0 |
| m_mt_404678451 | 1765125000 | COMPETITION | HOME | OPP_012 |  |  | 7.0 | 3.0 | 2.0 | 4.0 | 3.0 | 5.0 | 23.0 | 28.0 | 6.0 | 4.0 | 69.0 | 50.0 | 5.0 | 8.0 | 1.0 | 2.0 | 8.0 | 9.0 | 0.76 | 1.69 | 3.0 | 2.0 | 63.0 | 37.0 | 0.0 | 0.0 | 3.0 | 3.0 | 9.0 | 9.0 | 5.0 | 1.0 | 4.0 | 5.0 | 3.0 | 2.0 | 12.0 | 20.0 | 25.0 | 14.0 | 12.0 | 11.0 | 26.0 | 18.0 | 0.76 | 1.65 |  |  |
| m_mt_747395793 | 1765647000 | COMPETITION | AWAY | OPP_013 | BACK_FOUR | BACK_FOUR | 4.0 | 3.0 | 2.0 | 5.0 | 0.0 | 4.0 | 38.0 | 10.0 | 4.0 | 10.0 | 43.0 | 88.0 | 8.0 | 8.0 | 3.0 | 2.0 | 12.0 | 9.0 | 1.96 | 2.49 | 0.0 | 1.0 | 47.0 | 53.0 | 0.0 | 0.0 | 6.0 | 1.0 | 6.0 | 10.0 | 2.0 | 4.0 | 4.0 | 8.0 | 0.0 | 6.0 | 22.0 | 13.0 | 19.0 | 23.0 | 6.0 | 16.0 | 15.0 | 25.0 | 2.23 | 2.46 | 2.0 | 1.0 |
| m_mt_209363267 | 1766433600 | COMPETITION | HOME | OPP_014 |  |  | 4.0 | 2.0 | 2.0 | 0.0 | 6.0 | 4.0 | 29.0 | 16.0 | 1.0 | 5.0 | 37.0 | 66.0 | 5.0 | 9.0 | 1.0 | 0.0 | 11.0 | 8.0 | 0.71 | 0.6 | 2.0 | 2.0 | 50.0 | 50.0 | 0.0 | 0.0 | 2.0 | 0.0 | 8.0 | 6.0 | 4.0 | 6.0 | 1.0 | 2.0 | 3.0 | 6.0 | 20.0 | 8.0 | 18.0 | 22.0 | 11.0 | 12.0 | 24.0 | 21.0 | 1.5 | 0.6 | 5.0 | 4.0 |
| m_mt_979814078 | 1766847600 | COMPETITION | AWAY | OPP_015 | BACK_FOUR | BACK_FOUR | 10.0 | 2.0 | 1.0 | 1.0 | 6.0 | 5.0 | 34.0 | 25.0 | 4.0 | 5.0 | 65.0 | 47.0 | 8.0 | 8.0 | 1.0 | 0.0 | 12.0 | 9.0 | 1.62 | 0.91 | 2.0 | 7.0 | 56.0 | 44.0 | 0.0 | 0.0 | 2.0 | 4.0 | 11.0 | 7.0 | 6.0 | 4.0 | 5.0 | 2.0 | 6.0 | 4.0 | 15.0 | 29.0 | 24.0 | 19.0 | 17.0 | 11.0 | 35.0 | 27.0 | 1.62 | 0.91 | 3.0 | 1.0 |
| m_mt_979814081 | 1767288600 | COMPETITION | AWAY | OPP_012 |  |  | 7.0 | 1.0 | 3.0 | 3.0 | 6.0 | 4.0 | 35.0 | 29.0 | 3.0 | 6.0 | 75.0 | 54.0 | 10.0 | 7.0 | 1.0 | 1.0 | 9.0 | 9.0 | 1.76 | 1.91 | 1.0 | 5.0 | 60.0 | 40.0 | 0.0 | 0.0 | 1.0 | 4.0 | 12.0 | 9.0 | 6.0 | 5.0 | 5.0 | 2.0 | 5.0 | 2.0 | 16.0 | 14.0 | 17.0 | 15.0 | 17.0 | 11.0 | 31.0 | 37.0 | 1.76 | 1.93 | 5.0 | 0.0 |
| m_mt_979814024 | 1767539700 | COMPETITION | HOME | OPP_016 |  |  | 1.0 | 1.0 | 1.0 | 3.0 | 3.0 | 3.0 | 40.0 | 24.0 | 3.0 | 8.0 | 39.0 | 87.0 | 11.0 | 4.0 | 2.0 | 2.0 | 10.0 | 5.0 | 0.72 | 1.37 | 2.0 | 4.0 | 42.0 | 58.0 | 0.0 | 0.0 |  |  | 5.0 | 7.0 | 3.0 | 5.0 | 2.0 | 2.0 | 3.0 | 3.0 | 15.0 | 7.0 | 17.0 | 27.0 | 8.0 | 10.0 | 15.0 | 33.0 | 0.74 | 1.37 | 1.0 | 1.0 |
| m_mt_747395006 | 1767814200 | COMPETITION | HOME | OPP_017 |  |  | 4.0 | 4.0 | 0.0 | 4.0 | 8.0 | 3.0 | 28.0 | 30.0 | 2.0 | 11.0 | 55.0 | 54.0 | 11.0 | 6.0 | 2.0 | 1.0 | 9.0 | 8.0 | 1.23 | 2.53 | 1.0 | 2.0 | 55.0 | 45.0 | 0.0 | 1.0 | 4.0 | 3.0 | 9.0 | 11.0 | 3.0 | 5.0 | 5.0 | 6.0 | 7.0 | 3.0 | 16.0 | 13.0 | 15.0 | 11.0 | 16.0 | 14.0 | 34.0 | 25.0 | 1.2 | 2.39 | 3.0 | 3.0 |
| m_mt_585124962 | 1768662000 | COMPETITION | AWAY | OPP_001 |  |  | 1.0 | 5.0 | 0.0 | 5.0 | 2.0 | 1.0 | 31.0 | 13.0 | 3.0 | 7.0 | 48.0 | 55.0 | 11.0 | 6.0 | 0.0 | 1.0 | 10.0 | 7.0 | 0.38 | 1.43 | 3.0 | 8.0 | 54.0 | 46.0 | 0.0 | 0.0 | 4.0 | 1.0 | 5.0 | 10.0 | 5.0 | 8.0 | 1.0 | 5.0 | 3.0 | 4.0 | 16.0 | 10.0 | 16.0 | 21.0 | 8.0 | 14.0 | 7.0 | 22.0 | 0.39 | 1.43 | 5.0 | 1.0 |
| m_mt_585124925 | 1769266800 | COMPETITION | HOME | OPP_018 |  |  | 2.0 | 8.0 | 2.0 | 4.0 | 3.0 | 4.0 | 41.0 | 23.0 | 6.0 | 6.0 | 40.0 | 44.0 | 10.0 | 6.0 | 2.0 | 1.0 | 7.0 | 12.0 | 1.13 | 1.55 | 1.0 | 3.0 | 50.0 | 50.0 | 0.0 | 0.0 | 3.0 | 2.0 | 5.0 | 10.0 | 5.0 | 4.0 | 4.0 | 5.0 | 7.0 | 3.0 | 11.0 | 16.0 | 24.0 | 14.0 | 12.0 | 13.0 | 19.0 | 28.0 | 1.13 | 1.5 | 1.0 | 1.0 |
| m_mt_191506881 | 1769954400 | COMPETITION | AWAY | OPP_019 |  |  | 8.0 | 6.0 | 2.0 | 3.0 | 5.0 | 3.0 | 9.0 | 29.0 | 7.0 | 3.0 | 54.0 | 66.0 | 9.0 | 6.0 | 2.0 | 3.0 | 13.0 | 8.0 | 1.19 | 1.81 | 2.0 | 1.0 | 58.0 | 42.0 | 0.0 | 0.0 | 3.0 | 4.0 | 8.0 | 12.0 | 3.0 | 4.0 | 6.0 | 6.0 | 6.0 | 1.0 | 17.0 | 22.0 | 20.0 | 12.0 | 14.0 | 13.0 | 25.0 | 26.0 | 1.97 | 1.74 | 1.0 | 2.0 |
| m_mt_363781303 | 1770476400 | COMPETITION | HOME | OPP_008 |  |  | 10.0 | 6.0 | 4.0 | 2.0 | 2.0 | 3.0 | 22.0 | 29.0 | 6.0 | 6.0 | 45.0 | 51.0 | 11.0 | 12.0 | 1.0 | 2.0 | 8.0 | 8.0 | 2.07 | 1.85 | 2.0 | 2.0 | 55.0 | 45.0 | 0.0 | 0.0 | 2.0 | 3.0 | 11.0 | 12.0 | 8.0 | 10.0 | 3.0 | 3.0 | 2.0 | 4.0 | 19.0 | 16.0 | 12.0 | 15.0 | 13.0 | 16.0 | 26.0 | 28.0 | 1.97 | 1.68 | 1.0 | 5.0 |
| m_mt_979812949 | 1770838200 | COMPETITION | AWAY | OPP_011 | BACK_FOUR | BACK_FOUR | 4.0 | 1.0 | 1.0 | 2.0 | 3.0 | 5.0 | 11.0 | 16.0 | 4.0 | 4.0 | 33.0 | 59.0 | 10.0 | 8.0 | 0.0 | 3.0 | 8.0 | 7.0 | 1.42 | 1.37 | 1.0 | 3.0 | 44.0 | 56.0 | 0.0 | 0.0 | 2.0 | 3.0 | 12.0 | 5.0 | 8.0 | 3.0 | 3.0 | 5.0 | 2.0 | 8.0 | 23.0 | 22.0 | 22.0 | 11.0 | 14.0 | 13.0 | 21.0 | 18.0 | 1.42 | 1.37 | 1.0 | 3.0 |
| m_mt_252066526 | 1771768800 | COMPETITION | AWAY | OPP_009 |  |  | 3.0 | 1.0 | 3.0 | 3.0 | 3.0 | 5.0 | 37.0 | 25.0 | 4.0 | 6.0 | 44.0 | 61.0 | 13.0 | 6.0 | 3.0 | 1.0 | 10.0 | 5.0 | 1.09 | 1.04 | 1.0 | 1.0 | 47.0 | 53.0 | 0.0 | 0.0 | 1.0 | 1.0 | 9.0 | 8.0 | 5.0 | 5.0 | 4.0 | 2.0 | 3.0 | 4.0 | 19.0 | 12.0 | 23.0 | 18.0 | 12.0 | 12.0 | 19.0 | 34.0 | 1.87 | 1.82 | 1.0 | 1.0 |
| m_mt_585122828 | 1772373600 | COMPETITION | HOME | OPP_010 |  |  | 3.0 | 6.0 | 3.0 | 1.0 | 4.0 | 7.0 | 35.0 | 18.0 | 5.0 | 8.0 | 49.0 | 51.0 | 11.0 | 14.0 | 2.0 | 1.0 | 10.0 | 10.0 | 2.14 | 0.88 | 1.0 | 1.0 | 54.0 | 46.0 | 0.0 | 0.0 | 0.0 | 2.0 | 15.0 | 10.0 | 10.0 | 5.0 | 4.0 | 1.0 | 3.0 | 3.0 | 12.0 | 16.0 | 16.0 | 21.0 | 18.0 | 13.0 | 34.0 | 30.0 | 2.14 | 0.88 | 3.0 | 3.0 |
| m_mt_363788607 | 1772652600 | COMPETITION | HOME | OPP_015 |  |  | 9.0 | 2.0 | 0.0 | 3.0 | 4.0 | 2.0 | 20.0 | 32.0 | 6.0 | 5.0 | 64.0 | 42.0 | 14.0 | 12.0 | 0.0 | 1.0 | 4.0 | 13.0 | 1.01 | 1.09 | 0.0 | 7.0 | 60.0 | 40.0 | 0.0 | 0.0 | 3.0 | 5.0 | 10.0 | 6.0 | 4.0 | 4.0 | 5.0 | 3.0 | 3.0 | 3.0 | 11.0 | 7.0 | 18.0 | 16.0 | 13.0 | 9.0 | 29.0 | 13.0 | 1.01 | 1.09 | 2.0 | 4.0 |
| m_mt_404677011 | 1773583200 | COMPETITION | AWAY | OPP_014 | BACK_FOUR | BACK_FOUR | 2.0 | 3.0 | 1.0 | 1.0 | 2.0 | 5.0 | 21.0 | 22.0 | 4.0 | 5.0 | 59.0 | 54.0 | 10.0 | 8.0 | 0.0 | 0.0 | 9.0 | 6.0 | 0.67 | 0.71 | 1.0 | 3.0 | 54.0 | 46.0 | 0.0 | 0.0 | 2.0 | 1.0 | 4.0 | 5.0 | 3.0 | 4.0 | 1.0 | 2.0 | 1.0 | 6.0 | 16.0 | 8.0 | 20.0 | 29.0 | 5.0 | 11.0 | 14.0 | 18.0 | 0.67 | 0.71 | 3.0 | 2.0 |
| m_mt_626433488 | 1774105200 | COMPETITION | HOME | OPP_013 |  |  | 5.0 | 4.0 | 4.0 | 4.0 | 6.0 | 3.0 | 23.0 | 22.0 | 6.0 | 6.0 | 69.0 | 57.0 | 6.0 | 9.0 | 3.0 | 1.0 | 5.0 | 8.0 | 2.48 | 1.25 | 1.0 | 0.0 | 55.0 | 45.0 | 0.0 | 1.0 | 4.0 | 3.0 | 17.0 | 6.0 | 10.0 | 1.0 | 6.0 | 5.0 | 5.0 | 3.0 | 18.0 | 12.0 | 19.0 | 12.0 | 22.0 | 9.0 | 42.0 | 16.0 | 3.23 | 1.24 | 2.0 | 2.0 |
| m_mt_191500989 | 1775925000 | COMPETITION | AWAY | OPP_016 |  |  | 11.0 | 2.0 | 2.0 | 4.0 | 8.0 | 6.0 | 28.0 | 26.0 | 9.0 | 6.0 | 44.0 | 45.0 | 4.0 | 10.0 | 0.0 | 2.0 | 15.0 | 7.0 | 1.07 | 1.81 | 2.0 | 4.0 | 47.0 | 53.0 | 0.0 | 0.0 | 3.0 | 4.0 | 13.0 | 14.0 | 7.0 | 7.0 | 4.0 | 5.0 | 6.0 | 4.0 | 20.0 | 17.0 | 18.0 | 26.0 | 19.0 | 18.0 | 42.0 | 47.0 | 1.04 | 1.59 |  |  |
| m_mt_252067861 | 1776511800 | COMPETITION | AWAY | OPP_002 |  |  | 2.0 | 8.0 | 1.0 | 4.0 | 6.0 | 3.0 | 22.0 | 15.0 | 3.0 | 9.0 | 41.0 | 58.0 | 13.0 | 8.0 | 0.0 | 0.0 | 5.0 | 3.0 | 0.8 | 1.37 | 1.0 | 1.0 | 52.0 | 48.0 | 0.0 | 0.0 | 4.0 | 0.0 | 8.0 | 12.0 | 5.0 | 6.0 | 0.0 | 4.0 | 3.0 | 1.0 | 13.0 | 12.0 | 20.0 | 19.0 | 11.0 | 13.0 | 20.0 | 22.0 | 0.77 | 1.43 | 1.0 | 0.0 |

### Arm B — AWAY_TEAM match-level matrix (30 rows × 55 cols)

Columns: `match_alias, kickoff_unix, competition, venue, opponent_alias, own_formation_family, opponent_formation_family, accurate_crosses_for, accurate_crosses_against, big_chances_for, big_chances_against, blocked_shots_for, blocked_shots_against, clearances_for, clearances_against, corners_for, corners_against, final_third_entries_for, final_third_entries_against, fouls_for, fouls_against, goals_for, goals_against, interceptions_for, interceptions_against, npxg_for, npxg_against, offsides_for, offsides_against, possession_for, possession_against, red_cards_for, red_cards_against, saves_for, saves_against, shots_inside_box_for, shots_inside_box_against, shots_off_target_for, shots_off_target_against, shots_on_target_for, shots_on_target_against, shots_outside_box_for, shots_outside_box_against, tackles_for, tackles_against, throw_ins_for, throw_ins_against, total_shots_for, total_shots_against, touches_in_box_for, touches_in_box_against, xg_for, xg_against, yellow_cards_for, yellow_cards_against`

| match_alias | kickoff_unix | competition | venue | opponent_alias | own_formation_family | opponent_formation_family | accurate_crosses_for | accurate_crosses_against | big_chances_for | big_chances_against | blocked_shots_for | blocked_shots_against | clearances_for | clearances_against | corners_for | corners_against | final_third_entries_for | final_third_entries_against | fouls_for | fouls_against | goals_for | goals_against | interceptions_for | interceptions_against | npxg_for | npxg_against | offsides_for | offsides_against | possession_for | possession_against | red_cards_for | red_cards_against | saves_for | saves_against | shots_inside_box_for | shots_inside_box_against | shots_off_target_for | shots_off_target_against | shots_on_target_for | shots_on_target_against | shots_outside_box_for | shots_outside_box_against | tackles_for | tackles_against | throw_ins_for | throw_ins_against | total_shots_for | total_shots_against | touches_in_box_for | touches_in_box_against | xg_for | xg_against | yellow_cards_for | yellow_cards_against |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| m_mt_626439003 | 1757772000 | COMPETITION | AWAY | OPP_008 |  |  | 3.0 | 8.0 | 0.0 | 3.0 | 5.0 | 9.0 | 19.0 | 17.0 | 3.0 | 10.0 | 43.0 | 53.0 | 15.0 | 17.0 | 0.0 | 0.0 | 4.0 | 5.0 | 0.44 | 2.08 | 2.0 | 2.0 | 52.0 | 48.0 | 0.0 | 0.0 | 2.0 | 1.0 | 3.0 | 14.0 | 1.0 | 9.0 | 1.0 | 2.0 | 4.0 | 6.0 | 16.0 | 23.0 | 14.0 | 20.0 | 7.0 | 20.0 | 8.0 | 46.0 | 0.54 | 2.08 | 3.0 | 3.0 |
| m_mt_979812971 | 1758459600 | COMPETITION | AWAY | OPP_009 |  |  | 4.0 | 2.0 | 2.0 | 1.0 | 6.0 | 4.0 | 28.0 | 34.0 | 5.0 | 6.0 | 67.0 | 41.0 | 8.0 | 14.0 | 1.0 | 1.0 | 3.0 | 8.0 | 0.78 | 1.04 | 3.0 | 0.0 | 71.0 | 29.0 | 0.0 | 1.0 | 3.0 | 1.0 | 6.0 | 10.0 | 4.0 | 6.0 | 2.0 | 4.0 | 6.0 | 4.0 | 11.0 | 20.0 | 18.0 | 15.0 | 12.0 | 14.0 | 34.0 | 16.0 | 0.78 | 1.04 | 1.0 | 2.0 |
| m_mt_252067206 | 1759064400 | COMPETITION | HOME | OPP_020 |  |  | 1.0 | 7.0 | 3.0 | 1.0 | 2.0 | 3.0 | 26.0 | 23.0 | 2.0 | 8.0 | 43.0 | 56.0 | 10.0 | 13.0 | 3.0 | 1.0 | 7.0 | 9.0 | 1.11 | 1.06 | 2.0 | 4.0 | 48.0 | 52.0 | 0.0 | 0.0 | 3.0 | 1.0 | 4.0 | 9.0 | 3.0 | 4.0 | 4.0 | 4.0 | 5.0 | 2.0 | 10.0 | 16.0 | 11.0 | 18.0 | 9.0 | 11.0 | 18.0 | 27.0 | 1.11 | 0.92 | 1.0 | 4.0 |
| m_mt_363781348 | 1759669200 | COMPETITION | HOME | OPP_013 |  |  | 8.0 | 3.0 | 2.0 | 1.0 | 3.0 | 2.0 | 23.0 | 5.0 | 6.0 | 4.0 | 40.0 | 60.0 | 9.0 | 15.0 | 2.0 | 1.0 | 5.0 | 13.0 | 1.16 | 0.41 | 3.0 | 5.0 | 55.0 | 45.0 | 0.0 | 0.0 | 1.0 | 5.0 | 12.0 | 3.0 | 5.0 | 1.0 | 7.0 | 2.0 | 3.0 | 2.0 | 15.0 | 27.0 | 9.0 | 17.0 | 15.0 | 5.0 | 23.0 | 12.0 | 1.16 | 0.4 | 3.0 | 1.0 |
| m_mt_747390141 | 1760878800 | COMPETITION | AWAY | OPP_010 |  |  | 0.0 | 5.0 | 0.0 | 3.0 | 2.0 | 2.0 | 29.0 | 29.0 | 6.0 | 6.0 | 43.0 | 47.0 | 7.0 | 11.0 | 2.0 | 1.0 | 2.0 | 6.0 | 0.32 | 0.75 | 1.0 | 6.0 | 47.0 | 53.0 | 0.0 | 0.0 | 2.0 | 0.0 | 2.0 | 6.0 | 4.0 | 4.0 | 2.0 | 3.0 | 6.0 | 3.0 | 24.0 | 25.0 | 21.0 | 23.0 | 8.0 | 9.0 | 7.0 | 28.0 | 0.32 | 0.75 | 0.0 | 2.0 |
| m_mt_363782563 | 1761487200 | COMPETITION | HOME | OPP_011 |  |  | 3.0 | 7.0 | 2.0 | 2.0 | 5.0 | 9.0 | 19.0 | 19.0 | 5.0 | 6.0 | 48.0 | 52.0 | 8.0 | 16.0 | 1.0 | 0.0 | 7.0 | 11.0 | 0.82 | 1.19 | 1.0 | 3.0 | 47.0 | 53.0 | 0.0 | 0.0 | 3.0 | 2.0 | 8.0 | 14.0 | 1.0 | 5.0 | 3.0 | 4.0 | 1.0 | 4.0 | 18.0 | 14.0 | 13.0 | 14.0 | 9.0 | 18.0 | 26.0 | 33.0 | 0.81 | 1.18 | 1.0 | 4.0 |
| m_mt_252068377 | 1762027200 | COMPETITION | AWAY | OPP_016 | BACK_FOUR | BACK_FOUR | 1.0 | 1.0 | 0.0 | 4.0 | 1.0 | 5.0 | 26.0 | 25.0 | 4.0 | 1.0 | 51.0 | 63.0 | 11.0 | 13.0 | 0.0 | 2.0 | 6.0 | 6.0 | 0.41 | 1.19 | 0.0 | 8.0 | 47.0 | 53.0 | 0.0 | 0.0 | 2.0 | 3.0 | 4.0 | 7.0 | 6.0 | 7.0 | 3.0 | 4.0 | 6.0 | 9.0 | 11.0 | 12.0 | 12.0 | 17.0 | 10.0 | 16.0 | 22.0 | 21.0 | 0.41 | 1.19 | 3.0 | 2.0 |
| m_mt_010243910 | 1762696800 | COMPETITION | HOME | OPP_004 |  |  | 3.0 | 2.0 | 2.0 | 2.0 | 6.0 | 4.0 | 22.0 | 35.0 | 6.0 | 9.0 | 54.0 | 43.0 | 8.0 | 20.0 | 4.0 | 0.0 | 6.0 | 11.0 | 1.7 | 0.82 | 0.0 | 2.0 | 52.0 | 48.0 | 0.0 | 0.0 | 3.0 | 4.0 | 10.0 | 6.0 | 2.0 | 5.0 | 8.0 | 3.0 | 6.0 | 6.0 | 20.0 | 16.0 | 15.0 | 22.0 | 16.0 | 12.0 | 27.0 | 12.0 | 1.7 | 1.61 | 2.0 | 2.0 |
| m_mt_838950742 | 1763906400 | COMPETITION | AWAY | OPP_001 |  |  | 4.0 | 4.0 | 1.0 | 3.0 | 4.0 | 4.0 | 18.0 | 21.0 | 3.0 | 3.0 | 51.0 | 62.0 | 16.0 | 18.0 | 2.0 | 1.0 | 7.0 | 12.0 | 1.58 | 1.96 | 2.0 | 4.0 | 52.0 | 48.0 | 0.0 | 0.0 | 3.0 | 2.0 | 8.0 | 9.0 | 7.0 | 5.0 | 3.0 | 5.0 | 6.0 | 5.0 | 20.0 | 26.0 | 15.0 | 11.0 | 14.0 | 14.0 | 23.0 | 24.0 | 1.58 | 1.79 | 1.0 | 5.0 |
| m_mt_585124983 | 1764511500 | COMPETITION | HOME | OPP_007 |  |  | 5.0 | 5.0 | 0.0 | 1.0 | 4.0 | 3.0 | 26.0 | 28.0 | 7.0 | 3.0 | 65.0 | 51.0 | 13.0 | 21.0 | 1.0 | 0.0 | 4.0 | 6.0 | 0.94 | 0.37 | 0.0 | 2.0 | 52.0 | 48.0 | 0.0 | 0.0 | 4.0 | 5.0 | 9.0 | 7.0 | 6.0 | 2.0 | 6.0 | 4.0 | 7.0 | 2.0 | 16.0 | 22.0 | 13.0 | 10.0 | 16.0 | 9.0 | 28.0 | 20.0 | 0.94 | 0.49 | 0.0 | 4.0 |
| m_mt_747395600 | 1764790200 | COMPETITION | AWAY | OPP_018 |  |  | 4.0 | 4.0 | 6.0 | 3.0 | 2.0 | 3.0 | 25.0 | 16.0 | 6.0 | 5.0 | 37.0 | 54.0 | 9.0 | 10.0 | 4.0 | 3.0 | 8.0 | 9.0 | 2.62 | 2.21 | 1.0 | 4.0 | 44.0 | 56.0 | 0.0 | 0.0 | 4.0 | 6.0 | 12.0 | 12.0 | 2.0 | 6.0 | 10.0 | 7.0 | 2.0 | 4.0 | 23.0 | 23.0 | 16.0 | 11.0 | 14.0 | 16.0 | 25.0 | 29.0 | 2.41 | 2.21 | 2.0 | 2.0 |
| m_mt_626439685 | 1765024200 | COMPETITION | HOME | OPP_005 |  |  | 1.0 | 4.0 | 5.0 | 4.0 | 7.0 | 1.0 | 23.0 | 24.0 | 3.0 | 3.0 | 53.0 | 59.0 | 10.0 | 8.0 | 2.0 | 1.0 | 6.0 | 11.0 | 2.28 | 1.92 | 0.0 | 3.0 | 47.0 | 53.0 | 0.0 | 0.0 | 7.0 | 4.0 | 13.0 | 9.0 | 2.0 | 5.0 | 6.0 | 9.0 | 2.0 | 6.0 | 15.0 | 20.0 | 17.0 | 16.0 | 15.0 | 15.0 | 43.0 | 33.0 | 2.16 | 1.92 | 0.0 | 2.0 |
| m_mt_191506177 | 1765720800 | COMPETITION | AWAY | OPP_015 |  |  | 3.0 | 0.0 | 1.0 | 2.0 | 1.0 | 3.0 | 13.0 | 14.0 | 3.0 | 5.0 | 41.0 | 56.0 | 13.0 | 18.0 | 3.0 | 2.0 | 6.0 | 9.0 | 0.73 | 1.13 | 1.0 | 1.0 | 59.0 | 41.0 | 0.0 | 0.0 | 1.0 | 2.0 | 4.0 | 7.0 | 2.0 | 4.0 | 4.0 | 3.0 | 3.0 | 3.0 | 22.0 | 17.0 | 12.0 | 18.0 | 7.0 | 10.0 | 12.0 | 19.0 | 0.67 | 1.03 | 2.0 | 1.0 |
| m_mt_626439604 | 1766334600 | COMPETITION | HOME | OPP_019 |  |  | 1.0 | 4.0 | 2.0 | 3.0 | 5.0 | 3.0 | 22.0 | 21.0 | 5.0 | 5.0 | 27.0 | 49.0 | 4.0 | 2.0 | 2.0 | 1.0 | 7.0 | 9.0 | 1.51 | 1.32 | 3.0 | 1.0 | 43.0 | 57.0 | 0.0 | 0.0 | 5.0 | 2.0 | 8.0 | 5.0 | 3.0 | 6.0 | 4.0 | 6.0 | 4.0 | 10.0 | 18.0 | 26.0 | 8.0 | 19.0 | 12.0 | 15.0 | 20.0 | 34.0 | 1.54 | 1.33 | 1.0 | 2.0 |
| m_mt_191507434 | 1766856600 | COMPETITION | AWAY | OPP_017 | BACK_FOUR | BACK_FOUR | 1.0 | 4.0 | 5.0 | 2.0 | 2.0 | 7.0 | 28.0 | 6.0 | 7.0 | 6.0 | 25.0 | 58.0 | 8.0 | 16.0 | 2.0 | 1.0 | 4.0 | 9.0 | 1.25 | 2.15 |  |  | 37.0 | 63.0 | 0.0 | 0.0 | 2.0 | 6.0 | 7.0 | 8.0 | 1.0 | 4.0 | 8.0 | 3.0 | 4.0 | 6.0 | 8.0 | 26.0 | 13.0 | 6.0 | 11.0 | 14.0 | 19.0 | 42.0 | 1.19 | 2.14 | 3.0 | 5.0 |
| m_mt_010249713 | 1767125700 | COMPETITION | AWAY | OPP_005 |  |  | 1.0 | 5.0 | 5.0 | 6.0 | 4.0 | 7.0 | 17.0 | 17.0 | 3.0 | 3.0 | 23.0 | 51.0 | 9.0 | 18.0 | 1.0 | 4.0 | 3.0 | 8.0 | 3.39 | 3.04 | 0.0 | 4.0 | 54.0 | 46.0 | 0.0 | 0.0 | 3.0 | 2.0 | 9.0 | 17.0 | 4.0 | 8.0 | 3.0 | 7.0 | 2.0 | 5.0 | 10.0 | 17.0 | 17.0 | 8.0 | 11.0 | 22.0 | 21.0 | 38.0 | 2.67 | 3.04 | 3.0 | 2.0 |
| m_mt_626435898 | 1767443400 | COMPETITION | HOME | OPP_014 |  |  | 2.0 | 0.0 | 2.0 | 2.0 | 4.0 | 2.0 | 12.0 | 28.0 | 4.0 | 4.0 | 65.0 | 18.0 | 10.0 | 20.0 | 3.0 | 1.0 | 11.0 | 14.0 | 1.69 | 0.89 | 1.0 | 4.0 | 73.0 | 27.0 | 0.0 | 0.0 | 4.0 | 1.0 | 5.0 | 6.0 | 3.0 | 3.0 | 4.0 | 5.0 | 6.0 | 4.0 | 18.0 | 19.0 | 17.0 | 8.0 | 11.0 | 10.0 | 46.0 | 13.0 | 1.59 | 0.89 | 1.0 | 2.0 |
| m_mt_838950677 | 1767814200 | COMPETITION | AWAY | OPP_012 |  |  | 4.0 | 3.0 | 3.0 | 3.0 | 5.0 | 4.0 | 21.0 | 31.0 | 5.0 | 3.0 | 49.0 | 46.0 | 3.0 | 8.0 | 0.0 | 0.0 | 9.0 | 4.0 | 1.74 | 1.51 | 0.0 | 2.0 | 59.0 | 41.0 | 0.0 | 0.0 | 5.0 | 4.0 | 11.0 | 9.0 | 7.0 | 2.0 | 3.0 | 5.0 | 4.0 | 2.0 | 14.0 | 20.0 | 18.0 | 17.0 | 15.0 | 11.0 | 37.0 | 21.0 | 1.74 | 1.5 | 0.0 | 2.0 |
| m_mt_010243904 | 1768753800 | COMPETITION | HOME | OPP_008 |  |  | 4.0 | 2.0 | 0.0 | 1.0 | 6.0 | 4.0 | 16.0 | 28.0 | 6.0 | 4.0 | 50.0 | 44.0 | 15.0 | 13.0 | 0.0 | 1.0 | 5.0 | 13.0 | 1.34 | 0.52 | 1.0 | 4.0 | 64.0 | 36.0 | 0.0 | 0.0 | 2.0 | 5.0 | 12.0 | 5.0 | 7.0 | 2.0 | 5.0 | 3.0 | 6.0 | 4.0 | 14.0 | 18.0 | 20.0 | 12.0 | 18.0 | 9.0 | 30.0 | 16.0 | 1.36 | 0.56 | 1.0 | 2.0 |
| m_mt_747395655 | 1769349600 | COMPETITION | AWAY | OPP_006 |  |  | 5.0 | 6.0 | 2.0 | 3.0 | 2.0 | 7.0 | 29.0 | 22.0 | 5.0 | 6.0 | 57.0 | 80.0 | 12.0 | 7.0 | 2.0 | 0.0 | 7.0 | 5.0 | 1.16 | 2.3 | 0.0 | 2.0 | 40.0 | 60.0 | 0.0 | 0.0 | 4.0 | 6.0 | 7.0 | 9.0 | 4.0 | 4.0 | 8.0 | 4.0 | 7.0 | 6.0 | 22.0 | 25.0 | 12.0 | 14.0 | 14.0 | 15.0 | 27.0 | 24.0 | 1.16 | 2.3 | 2.0 | 1.0 |
| m_mt_404678210 | 1769954400 | COMPETITION | HOME | OPP_002 |  |  | 8.0 | 1.0 | 3.0 | 0.0 | 11.0 | 1.0 | 19.0 | 35.0 | 12.0 | 1.0 | 42.0 | 53.0 | 8.0 | 8.0 | 0.0 | 1.0 | 3.0 | 14.0 | 2.0 | 0.53 | 1.0 | 6.0 | 72.0 | 28.0 | 0.0 | 1.0 | 0.0 | 5.0 | 17.0 | 5.0 | 11.0 | 4.0 | 5.0 | 2.0 | 10.0 | 1.0 | 18.0 | 7.0 | 16.0 | 18.0 | 27.0 | 6.0 | 75.0 | 12.0 | 1.98 | 0.53 | 1.0 | 3.0 |
| m_mt_404678498 | 1770476400 | COMPETITION | AWAY | OPP_004 |  |  | 4.0 | 3.0 | 1.0 | 2.0 | 3.0 | 4.0 | 37.0 | 20.0 | 4.0 | 11.0 | 51.0 | 65.0 | 11.0 | 4.0 | 1.0 | 1.0 | 7.0 | 10.0 | 0.45 | 2.33 | 3.0 | 3.0 | 47.0 | 53.0 | 0.0 | 0.0 | 7.0 | 3.0 | 5.0 | 12.0 | 0.0 | 7.0 | 4.0 | 9.0 | 2.0 | 8.0 | 18.0 | 10.0 | 17.0 | 21.0 | 7.0 | 20.0 | 20.0 | 26.0 | 0.44 | 2.31 | 1.0 | 1.0 |
| m_mt_626439652 | 1770838200 | COMPETITION | HOME | OPP_018 | BACK_FOUR | BACK_FOUR | 5.0 | 5.0 |  |  | 4.0 | 1.0 | 22.0 | 13.0 | 7.0 | 5.0 | 50.0 | 57.0 | 9.0 | 15.0 | 1.0 | 0.0 | 7.0 | 13.0 | 0.73 | 0.66 | 0.0 | 3.0 | 50.0 | 50.0 | 0.0 | 0.0 | 3.0 | 2.0 | 10.0 | 7.0 | 10.0 | 5.0 | 1.0 | 3.0 | 5.0 | 2.0 | 11.0 | 16.0 | 12.0 | 23.0 | 15.0 | 9.0 | 31.0 | 24.0 | 0.72 | 0.5 | 2.0 | 3.0 |
| m_mt_404678420 | 1771686000 | COMPETITION | HOME | OPP_001 |  |  | 7.0 | 5.0 | 1.0 | 2.0 | 5.0 | 4.0 | 20.0 | 40.0 | 7.0 | 2.0 | 65.0 | 36.0 | 11.0 | 16.0 | 1.0 | 1.0 | 7.0 | 10.0 | 1.39 | 1.25 | 4.0 | 5.0 | 67.0 | 33.0 | 0.0 | 0.0 | 3.0 | 3.0 | 6.0 | 8.0 | 7.0 | 6.0 | 4.0 | 4.0 | 10.0 | 6.0 | 14.0 | 22.0 | 23.0 | 16.0 | 16.0 | 14.0 | 29.0 | 20.0 | 1.39 | 1.35 | 1.0 | 4.0 |
| m_mt_747399497 | 1772222400 | COMPETITION | AWAY | OPP_007 |  |  | 7.0 | 2.0 | 2.0 | 3.0 | 6.0 | 3.0 | 15.0 | 26.0 | 5.0 | 0.0 | 53.0 | 38.0 | 19.0 | 12.0 | 0.0 | 2.0 | 8.0 | 11.0 | 1.06 | 0.92 | 0.0 | 1.0 | 61.0 | 39.0 | 0.0 | 0.0 | 0.0 | 4.0 | 10.0 | 6.0 | 3.0 | 4.0 | 5.0 | 2.0 | 4.0 | 3.0 | 10.0 | 16.0 | 15.0 | 15.0 | 14.0 | 9.0 | 24.0 | 11.0 | 1.06 | 0.92 | 3.0 | 3.0 |
| m_mt_626433295 | 1772652600 | COMPETITION | HOME | OPP_017 |  |  | 1.0 | 3.0 | 2.0 | 5.0 | 1.0 | 4.0 | 14.0 | 15.0 | 3.0 | 8.0 | 41.0 | 37.0 | 10.0 | 9.0 | 1.0 | 4.0 | 7.0 | 8.0 | 0.88 | 3.92 | 2.0 | 2.0 | 43.0 | 57.0 | 0.0 | 0.0 | 4.0 | 3.0 | 6.0 | 14.0 | 4.0 | 3.0 | 4.0 | 8.0 | 3.0 | 1.0 | 11.0 | 15.0 | 16.0 | 20.0 | 9.0 | 15.0 | 17.0 | 35.0 | 0.88 | 3.92 | 3.0 | 2.0 |
| m_mt_010244193 | 1773583200 | COMPETITION | AWAY | OPP_019 | BACK_FOUR | BACK_FOUR | 6.0 | 2.0 | 3.0 | 3.0 | 2.0 | 4.0 | 32.0 | 22.0 | 6.0 | 6.0 | 51.0 | 56.0 | 5.0 | 10.0 | 1.0 | 3.0 | 7.0 | 12.0 | 1.02 | 1.07 | 1.0 | 1.0 | 47.0 | 53.0 | 0.0 | 0.0 | 3.0 | 1.0 | 6.0 | 11.0 | 5.0 | 6.0 | 2.0 | 6.0 | 3.0 | 5.0 | 16.0 | 18.0 | 11.0 | 11.0 | 9.0 | 16.0 | 31.0 | 21.0 | 1.02 | 1.07 | 2.0 | 3.0 |
| m_mt_010244105 | 1774188900 | COMPETITION | HOME | OPP_015 |  |  | 5.0 | 6.0 | 3.0 | 1.0 | 7.0 | 5.0 | 17.0 | 20.0 | 6.0 | 6.0 | 62.0 | 35.0 | 3.0 | 7.0 | 2.0 | 0.0 | 2.0 | 10.0 | 1.72 | 0.89 | 0.0 | 4.0 | 59.0 | 41.0 | 0.0 | 0.0 | 1.0 | 4.0 | 13.0 | 8.0 | 9.0 | 3.0 | 7.0 | 1.0 | 10.0 | 1.0 | 18.0 | 13.0 | 20.0 | 14.0 | 23.0 | 9.0 | 38.0 | 19.0 | 1.68 | 0.94 | 0.0 | 1.0 |
| m_mt_404678175 | 1775998800 | COMPETITION | AWAY | OPP_014 |  |  | 3.0 | 6.0 | 3.0 | 1.0 | 1.0 | 5.0 | 12.0 | 21.0 | 3.0 | 7.0 | 50.0 | 41.0 | 10.0 | 15.0 | 1.0 | 1.0 | 8.0 | 9.0 | 1.25 | 1.2 | 2.0 | 1.0 | 59.0 | 41.0 | 0.0 | 0.0 | 4.0 | 5.0 | 8.0 | 9.0 | 7.0 | 6.0 | 5.0 | 4.0 | 4.0 | 6.0 | 15.0 | 15.0 | 15.0 | 5.0 | 12.0 | 15.0 | 22.0 | 35.0 | 1.02 | 1.15 | 2.0 | 2.0 |
| m_mt_191506707 | 1776603600 | COMPETITION | HOME | OPP_009 |  |  | 6.0 | 4.0 | 7.0 | 3.0 | 3.0 | 1.0 | 20.0 | 23.0 | 4.0 | 5.0 | 41.0 | 48.0 | 11.0 | 11.0 | 4.0 | 3.0 | 5.0 | 7.0 | 2.66 | 1.76 | 0.0 | 3.0 | 50.0 | 50.0 | 0.0 | 0.0 | 4.0 | 3.0 | 10.0 | 8.0 | 5.0 | 2.0 | 7.0 | 7.0 | 5.0 | 2.0 | 10.0 | 14.0 | 13.0 | 14.0 | 15.0 | 10.0 | 26.0 | 16.0 | 2.84 | 1.73 | 1.0 | 3.0 |

### Arm B — derived summaries (DERIVED_SUMMARY), HOME 240 + AWAY 240

HOME_TEAM (metric·side·window·venue = value [n, reliability]):

- accurate_crosses·FOR·ALL_PRIOR·ALL = 4.6667 [n=30, HIGH]
- accurate_crosses·FOR·W5·ALL = 5.8 [n=5, LOW]
- accurate_crosses·FOR·W10·ALL = 5.7 [n=10, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·HOME = 4.9333 [n=15, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·AWAY = 4.4 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·ALL = 3.5333 [n=30, HIGH]
- accurate_crosses·AGAINST·W5·ALL = 3.8 [n=5, LOW]
- accurate_crosses·AGAINST·W10·ALL = 3.9 [n=10, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·HOME = 3.6 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·AWAY = 3.4667 [n=15, MEDIUM]
- big_chances·FOR·ALL_PRIOR·ALL = 1.6667 [n=30, HIGH]
- big_chances·FOR·W5·ALL = 1.6 [n=5, LOW]
- big_chances·FOR·W10·ALL = 2.1 [n=10, MEDIUM]
- big_chances·FOR·ALL_PRIOR·HOME = 2.0 [n=15, MEDIUM]
- big_chances·FOR·ALL_PRIOR·AWAY = 1.3333 [n=15, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·ALL = 2.6333 [n=30, HIGH]
- big_chances·AGAINST·W5·ALL = 3.2 [n=5, LOW]
- big_chances·AGAINST·W10·ALL = 2.7 [n=10, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·HOME = 2.2667 [n=15, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·AWAY = 3.0 [n=15, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·ALL = 4.1 [n=30, HIGH]
- blocked_shots·FOR·W5·ALL = 5.2 [n=5, LOW]
- blocked_shots·FOR·W10·ALL = 4.3 [n=10, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·HOME = 4.2667 [n=15, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·AWAY = 3.9333 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·ALL = 3.7333 [n=30, HIGH]
- blocked_shots·AGAINST·W5·ALL = 3.8 [n=5, LOW]
- blocked_shots·AGAINST·W10·ALL = 4.2 [n=10, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·HOME = 3.4 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·AWAY = 4.0667 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·ALL = 28.4667 [n=30, HIGH]
- clearances·FOR·W5·ALL = 22.8 [n=5, LOW]
- clearances·FOR·W10·ALL = 22.8 [n=10, MEDIUM]
- clearances·FOR·ALL_PRIOR·HOME = 28.4667 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·AWAY = 28.4667 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·ALL = 23.4333 [n=30, HIGH]
- clearances·AGAINST·W5·ALL = 23.4 [n=5, LOW]
- clearances·AGAINST·W10·ALL = 23.4 [n=10, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·HOME = 25.4667 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·AWAY = 21.4 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·ALL = 4.7333 [n=30, HIGH]
- corners·FOR·W5·ALL = 5.6 [n=5, LOW]
- corners·FOR·W10·ALL = 5.4 [n=10, MEDIUM]
- corners·FOR·ALL_PRIOR·HOME = 5.0667 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·AWAY = 4.4 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·ALL = 5.8333 [n=30, HIGH]
- corners·AGAINST·W5·ALL = 6.2 [n=5, LOW]
- corners·AGAINST·W10·ALL = 5.8 [n=10, MEDIUM]
- corners·AGAINST·ALL_PRIOR·HOME = 5.9333 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·AWAY = 5.7333 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·ALL = 50.3333 [n=30, HIGH]
- final_third_entries·FOR·W5·ALL = 55.4 [n=5, LOW]
- final_third_entries·FOR·W10·ALL = 50.2 [n=10, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·HOME = 51.7333 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·AWAY = 48.9333 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·ALL = 57.8 [n=30, HIGH]
- final_third_entries·AGAINST·W5·ALL = 51.2 [n=5, LOW]
- final_third_entries·AGAINST·W10·ALL = 54.4 [n=10, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·HOME = 55.8667 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·AWAY = 59.7333 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·ALL = 10.3667 [n=30, HIGH]
- fouls·FOR·W5·ALL = 9.4 [n=5, LOW]
- fouls·FOR·W10·ALL = 10.1 [n=10, MEDIUM]
- fouls·FOR·ALL_PRIOR·HOME = 10.2 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·AWAY = 10.5333 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·ALL = 9.0667 [n=30, HIGH]
- fouls·AGAINST·W5·ALL = 9.4 [n=5, LOW]
- fouls·AGAINST·W10·ALL = 9.3 [n=10, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·HOME = 9.7333 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·AWAY = 8.4 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·ALL = 1.3667 [n=30, HIGH]
- goals·FOR·W5·ALL = 0.6 [n=5, LOW]
- goals·FOR·W10·ALL = 1.1 [n=10, MEDIUM]
- goals·FOR·ALL_PRIOR·HOME = 1.7333 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·AWAY = 1.0 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·ALL = 1.4 [n=30, HIGH]
- goals·AGAINST·W5·ALL = 0.8 [n=5, LOW]
- goals·AGAINST·W10·ALL = 1.4 [n=10, MEDIUM]
- goals·AGAINST·ALL_PRIOR·HOME = 1.2 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·AWAY = 1.6 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·ALL = 8.7333 [n=30, HIGH]
- interceptions·FOR·W5·ALL = 7.6 [n=5, LOW]
- interceptions·FOR·W10·ALL = 8.7 [n=10, MEDIUM]
- interceptions·FOR·ALL_PRIOR·HOME = 7.4667 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·AWAY = 10.0 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·ALL = 7.8667 [n=30, HIGH]
- interceptions·AGAINST·W5·ALL = 7.4 [n=5, LOW]
- interceptions·AGAINST·W10·ALL = 7.5 [n=10, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·HOME = 8.6 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·AWAY = 7.1333 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·ALL = 1.181 [n=30, HIGH]
- npxg·FOR·W5·ALL = 1.206 [n=5, LOW]
- npxg·FOR·W10·ALL = 1.394 [n=10, MEDIUM]
- npxg·FOR·ALL_PRIOR·HOME = 1.278 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·AWAY = 1.084 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·ALL = 1.341 [n=30, HIGH]
- npxg·AGAINST·W5·ALL = 1.246 [n=5, LOW]
- npxg·AGAINST·W10·ALL = 1.318 [n=10, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·HOME = 1.2393 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·AWAY = 1.4427 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·ALL = 1.6667 [n=30, HIGH]
- offsides·FOR·W5·ALL = 1.0 [n=5, LOW]
- offsides·FOR·W10·ALL = 1.2 [n=10, MEDIUM]
- offsides·FOR·ALL_PRIOR·HOME = 1.6 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·AWAY = 1.7333 [n=15, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·ALL = 2.6667 [n=30, HIGH]
- offsides·AGAINST·W5·ALL = 3.0 [n=5, LOW]
- offsides·AGAINST·W10·ALL = 2.3 [n=10, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·HOME = 2.2667 [n=15, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·AWAY = 3.0667 [n=15, MEDIUM]
- possession·FOR·ALL_PRIOR·ALL = 51.9333 [n=30, HIGH]
- possession·FOR·W5·ALL = 53.6 [n=5, LOW]
- possession·FOR·W10·ALL = 52.6 [n=10, MEDIUM]
- possession·FOR·ALL_PRIOR·HOME = 53.6667 [n=15, MEDIUM]
- possession·FOR·ALL_PRIOR·AWAY = 50.2 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·ALL = 48.0667 [n=30, HIGH]
- possession·AGAINST·W5·ALL = 46.4 [n=5, LOW]
- possession·AGAINST·W10·ALL = 47.4 [n=10, MEDIUM]
- possession·AGAINST·ALL_PRIOR·HOME = 46.3333 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·AWAY = 49.8 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·ALL = 0.0 [n=30, HIGH]
- red_cards·FOR·W5·ALL = 0.0 [n=5, LOW]
- red_cards·FOR·W10·ALL = 0.0 [n=10, MEDIUM]
- red_cards·FOR·ALL_PRIOR·HOME = 0.0 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·AWAY = 0.0 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·ALL = 0.1 [n=30, HIGH]
- red_cards·AGAINST·W5·ALL = 0.2 [n=5, LOW]
- red_cards·AGAINST·W10·ALL = 0.1 [n=10, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·HOME = 0.2 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·AWAY = 0.0 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·ALL = 2.5517 [n=29, HIGH]
- saves·FOR·W5·ALL = 3.2 [n=5, LOW]
- saves·FOR·W10·ALL = 2.4 [n=10, MEDIUM]
- saves·FOR·ALL_PRIOR·HOME = 2.4286 [n=14, MEDIUM]
- saves·FOR·ALL_PRIOR·AWAY = 2.6667 [n=15, MEDIUM]
- saves·AGAINST·ALL_PRIOR·ALL = 2.5172 [n=29, HIGH]
- saves·AGAINST·W5·ALL = 2.6 [n=5, LOW]
- saves·AGAINST·W10·ALL = 2.6 [n=10, MEDIUM]
- saves·AGAINST·ALL_PRIOR·HOME = 2.5 [n=14, MEDIUM]
- saves·AGAINST·ALL_PRIOR·AWAY = 2.5333 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·ALL = 8.7333 [n=30, HIGH]
- shots_inside_box·FOR·W5·ALL = 10.4 [n=5, LOW]
- shots_inside_box·FOR·W10·ALL = 10.7 [n=10, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·HOME = 9.6 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·AWAY = 7.8667 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·ALL = 8.3333 [n=30, HIGH]
- shots_inside_box·AGAINST·W5·ALL = 8.6 [n=5, LOW]
- shots_inside_box·AGAINST·W10·ALL = 9.0 [n=10, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·HOME = 8.1333 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·AWAY = 8.5333 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·ALL = 4.9333 [n=30, HIGH]
- shots_off_target·FOR·W5·ALL = 5.8 [n=5, LOW]
- shots_off_target·FOR·W10·ALL = 6.3 [n=10, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·HOME = 5.7333 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·AWAY = 4.1333 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·ALL = 4.3667 [n=30, HIGH]
- shots_off_target·AGAINST·W5·ALL = 4.4 [n=5, LOW]
- shots_off_target·AGAINST·W10·ALL = 4.9 [n=10, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·HOME = 3.9333 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·AWAY = 4.8 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·ALL = 3.7 [n=30, HIGH]
- shots_on_target·FOR·W5·ALL = 3.2 [n=5, LOW]
- shots_on_target·FOR·W10·ALL = 3.6 [n=10, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·HOME = 3.8667 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·AWAY = 3.5333 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·ALL = 3.8667 [n=30, HIGH]
- shots_on_target·AGAINST·W5·ALL = 3.8 [n=5, LOW]
- shots_on_target·AGAINST·W10·ALL = 3.6 [n=10, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·HOME = 3.4 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·AWAY = 4.3333 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·ALL = 3.9667 [n=30, HIGH]
- shots_outside_box·FOR·W5·ALL = 3.6 [n=5, LOW]
- shots_outside_box·FOR·W10·ALL = 3.4 [n=10, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·HOME = 4.2667 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·AWAY = 3.6667 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·ALL = 3.6333 [n=30, HIGH]
- shots_outside_box·AGAINST·W5·ALL = 3.4 [n=5, LOW]
- shots_outside_box·AGAINST·W10·ALL = 3.7 [n=10, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·HOME = 2.6 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·AWAY = 4.6667 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·ALL = 16.5667 [n=30, HIGH]
- tackles·FOR·W5·ALL = 15.6 [n=5, LOW]
- tackles·FOR·W10·ALL = 16.8 [n=10, MEDIUM]
- tackles·FOR·ALL_PRIOR·HOME = 15.4667 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·AWAY = 17.6667 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·ALL = 14.3667 [n=30, HIGH]
- tackles·AGAINST·W5·ALL = 11.2 [n=5, LOW]
- tackles·AGAINST·W10·ALL = 14.4 [n=10, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·HOME = 13.9333 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·AWAY = 14.8 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·ALL = 19.7 [n=30, HIGH]
- throw_ins·FOR·W5·ALL = 19.0 [n=5, LOW]
- throw_ins·FOR·W10·ALL = 18.8 [n=10, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·HOME = 19.4 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·AWAY = 20.0 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·ALL = 18.4667 [n=30, HIGH]
- throw_ins·AGAINST·W5·ALL = 20.4 [n=5, LOW]
- throw_ins·AGAINST·W10·ALL = 17.9 [n=10, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·HOME = 17.0 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·AWAY = 19.9333 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·ALL = 12.7 [n=30, HIGH]
- total_shots·FOR·W5·ALL = 14.0 [n=5, LOW]
- total_shots·FOR·W10·ALL = 14.1 [n=10, MEDIUM]
- total_shots·FOR·ALL_PRIOR·HOME = 13.8667 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·AWAY = 11.5333 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·ALL = 11.9667 [n=30, HIGH]
- total_shots·AGAINST·W5·ALL = 12.0 [n=5, LOW]
- total_shots·AGAINST·W10·ALL = 12.7 [n=10, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·HOME = 10.7333 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·AWAY = 13.2 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·ALL = 24.6333 [n=30, HIGH]
- touches_in_box·FOR·W5·ALL = 29.4 [n=5, LOW]
- touches_in_box·FOR·W10·ALL = 27.2 [n=10, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·HOME = 27.2 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·AWAY = 22.0667 [n=15, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·ALL = 25.6333 [n=30, HIGH]
- touches_in_box·AGAINST·W5·ALL = 23.2 [n=5, LOW]
- touches_in_box·AGAINST·W10·ALL = 25.2 [n=10, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·HOME = 23.8667 [n=15, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·AWAY = 27.4 [n=15, MEDIUM]
- xg·FOR·ALL_PRIOR·ALL = 1.2777 [n=30, HIGH]
- xg·FOR·W5·ALL = 1.344 [n=5, LOW]
- xg·FOR·W10·ALL = 1.609 [n=10, MEDIUM]
- xg·FOR·ALL_PRIOR·HOME = 1.3627 [n=15, MEDIUM]
- xg·FOR·ALL_PRIOR·AWAY = 1.1927 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·ALL = 1.3433 [n=30, HIGH]
- xg·AGAINST·W5·ALL = 1.212 [n=5, LOW]
- xg·AGAINST·W10·ALL = 1.355 [n=10, MEDIUM]
- xg·AGAINST·ALL_PRIOR·HOME = 1.216 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·AWAY = 1.4707 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·ALL = 2.2222 [n=27, HIGH]
- yellow_cards·FOR·W5·ALL = 2.0 [n=4, LOW]
- yellow_cards·FOR·W10·ALL = 1.6667 [n=9, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·HOME = 2.0769 [n=13, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·AWAY = 2.3571 [n=14, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·ALL = 1.8519 [n=27, HIGH]
- yellow_cards·AGAINST·W5·ALL = 2.0 [n=4, LOW]
- yellow_cards·AGAINST·W10·ALL = 2.4444 [n=9, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·HOME = 2.5385 [n=13, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·AWAY = 1.2143 [n=14, MEDIUM]

AWAY_TEAM:

- accurate_crosses·FOR·ALL_PRIOR·ALL = 3.6667 [n=30, HIGH]
- accurate_crosses·FOR·W5·ALL = 4.2 [n=5, LOW]
- accurate_crosses·FOR·W10·ALL = 5.2 [n=10, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·HOME = 4.0 [n=15, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·AWAY = 3.3333 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·ALL = 3.7667 [n=30, HIGH]
- accurate_crosses·AGAINST·W5·ALL = 4.2 [n=5, LOW]
- accurate_crosses·AGAINST·W10·ALL = 3.7 [n=10, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·HOME = 3.8667 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·AWAY = 3.6667 [n=15, MEDIUM]
- big_chances·FOR·ALL_PRIOR·ALL = 2.3448 [n=29, HIGH]
- big_chances·FOR·W5·ALL = 3.6 [n=5, LOW]
- big_chances·FOR·W10·ALL = 2.7778 [n=9, MEDIUM]
- big_chances·FOR·ALL_PRIOR·HOME = 2.4286 [n=14, MEDIUM]
- big_chances·FOR·ALL_PRIOR·AWAY = 2.2667 [n=15, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·ALL = 2.4138 [n=29, HIGH]
- big_chances·AGAINST·W5·ALL = 2.6 [n=5, LOW]
- big_chances·AGAINST·W10·ALL = 2.2222 [n=9, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·HOME = 2.0 [n=14, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·AWAY = 2.8 [n=15, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·ALL = 3.9667 [n=30, HIGH]
- blocked_shots·FOR·W5·ALL = 2.8 [n=5, LOW]
- blocked_shots·FOR·W10·ALL = 4.3 [n=10, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·HOME = 4.8667 [n=15, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·AWAY = 3.0667 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·ALL = 3.9333 [n=30, HIGH]
- blocked_shots·AGAINST·W5·ALL = 3.8 [n=5, LOW]
- blocked_shots·AGAINST·W10·ALL = 3.2 [n=10, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·HOME = 3.1333 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·AWAY = 4.7333 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·ALL = 21.6667 [n=30, HIGH]
- clearances·FOR·W5·ALL = 19.0 [n=5, LOW]
- clearances·FOR·W10·ALL = 20.8 [n=10, MEDIUM]
- clearances·FOR·ALL_PRIOR·HOME = 20.0667 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·AWAY = 23.2667 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·ALL = 22.6 [n=30, HIGH]
- clearances·AGAINST·W5·ALL = 20.2 [n=5, LOW]
- clearances·AGAINST·W10·ALL = 23.5 [n=10, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·HOME = 23.8 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·AWAY = 21.4 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·ALL = 5.0333 [n=30, HIGH]
- corners·FOR·W5·ALL = 4.4 [n=5, LOW]
- corners·FOR·W10·ALL = 5.7 [n=10, MEDIUM]
- corners·FOR·ALL_PRIOR·HOME = 5.5333 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·AWAY = 4.5333 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·ALL = 5.0333 [n=30, HIGH]
- corners·AGAINST·W5·ALL = 6.4 [n=5, LOW]
- corners·AGAINST·W10·ALL = 5.1 [n=10, MEDIUM]
- corners·AGAINST·ALL_PRIOR·HOME = 4.8667 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·AWAY = 5.2 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·ALL = 47.9333 [n=30, HIGH]
- final_third_entries·FOR·W5·ALL = 49.0 [n=5, LOW]
- final_third_entries·FOR·W10·ALL = 50.6 [n=10, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·HOME = 49.7333 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·AWAY = 46.1333 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·ALL = 50.3 [n=30, HIGH]
- final_third_entries·AGAINST·W5·ALL = 43.4 [n=5, LOW]
- final_third_entries·AGAINST·W10·ALL = 46.6 [n=10, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·HOME = 46.5333 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·AWAY = 54.0667 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·ALL = 9.8333 [n=30, HIGH]
- fouls·FOR·W5·ALL = 7.8 [n=5, LOW]
- fouls·FOR·W10·ALL = 9.7 [n=10, MEDIUM]
- fouls·FOR·ALL_PRIOR·HOME = 9.2667 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·AWAY = 10.4 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·ALL = 12.8333 [n=30, HIGH]
- fouls·AGAINST·W5·ALL = 10.4 [n=5, LOW]
- fouls·AGAINST·W10·ALL = 10.7 [n=10, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·HOME = 12.9333 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·AWAY = 12.7333 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·ALL = 1.5667 [n=30, HIGH]
- goals·FOR·W5·ALL = 1.8 [n=5, LOW]
- goals·FOR·W10·ALL = 1.2 [n=10, MEDIUM]
- goals·FOR·ALL_PRIOR·HOME = 1.8 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·AWAY = 1.3333 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·ALL = 1.2333 [n=30, HIGH]
- goals·AGAINST·W5·ALL = 2.2 [n=5, LOW]
- goals·AGAINST·W10·ALL = 1.6 [n=10, MEDIUM]
- goals·AGAINST·ALL_PRIOR·HOME = 1.0 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·AWAY = 1.4667 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·ALL = 5.9333 [n=30, HIGH]
- interceptions·FOR·W5·ALL = 5.8 [n=5, LOW]
- interceptions·FOR·W10·ALL = 6.1 [n=10, MEDIUM]
- interceptions·FOR·ALL_PRIOR·HOME = 5.9333 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·AWAY = 5.9333 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·ALL = 9.4 [n=30, HIGH]
- interceptions·AGAINST·W5·ALL = 9.2 [n=5, LOW]
- interceptions·AGAINST·W10·ALL = 10.4 [n=10, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·HOME = 10.6 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·AWAY = 8.2 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·ALL = 1.3377 [n=30, HIGH]
- npxg·FOR·W5·ALL = 1.506 [n=5, LOW]
- npxg·FOR·W10·ALL = 1.316 [n=10, MEDIUM]
- npxg·FOR·ALL_PRIOR·HOME = 1.462 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·AWAY = 1.2133 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·ALL = 1.413 [n=30, HIGH]
- npxg·AGAINST·W5·ALL = 1.768 [n=5, LOW]
- npxg·AGAINST·W10·ALL = 1.453 [n=10, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·HOME = 1.1673 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·AWAY = 1.6587 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·ALL = 1.1724 [n=29, HIGH]
- offsides·FOR·W5·ALL = 1.0 [n=5, LOW]
- offsides·FOR·W10·ALL = 1.3 [n=10, MEDIUM]
- offsides·FOR·ALL_PRIOR·HOME = 1.2 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·AWAY = 1.1429 [n=14, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·ALL = 3.1034 [n=29, HIGH]
- offsides·AGAINST·W5·ALL = 2.2 [n=5, LOW]
- offsides·AGAINST·W10·ALL = 2.9 [n=10, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·HOME = 3.4 [n=15, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·AWAY = 2.7857 [n=14, MEDIUM]
- possession·FOR·ALL_PRIOR·ALL = 53.2667 [n=30, HIGH]
- possession·FOR·W5·ALL = 51.6 [n=5, LOW]
- possession·FOR·W10·ALL = 55.5 [n=10, MEDIUM]
- possession·FOR·ALL_PRIOR·HOME = 54.8 [n=15, MEDIUM]
- possession·FOR·ALL_PRIOR·AWAY = 51.7333 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·ALL = 46.7333 [n=30, HIGH]
- possession·AGAINST·W5·ALL = 48.4 [n=5, LOW]
- possession·AGAINST·W10·ALL = 44.5 [n=10, MEDIUM]
- possession·AGAINST·ALL_PRIOR·HOME = 45.2 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·AWAY = 48.2667 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·ALL = 0.0 [n=30, HIGH]
- red_cards·FOR·W5·ALL = 0.0 [n=5, LOW]
- red_cards·FOR·W10·ALL = 0.0 [n=10, MEDIUM]
- red_cards·FOR·ALL_PRIOR·HOME = 0.0 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·AWAY = 0.0 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·ALL = 0.0667 [n=30, HIGH]
- red_cards·AGAINST·W5·ALL = 0.0 [n=5, LOW]
- red_cards·AGAINST·W10·ALL = 0.1 [n=10, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·HOME = 0.0667 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·AWAY = 0.0667 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·ALL = 3.0667 [n=30, HIGH]
- saves·FOR·W5·ALL = 3.2 [n=5, LOW]
- saves·FOR·W10·ALL = 2.9 [n=10, MEDIUM]
- saves·FOR·ALL_PRIOR·HOME = 3.1333 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·AWAY = 3.0 [n=15, MEDIUM]
- saves·AGAINST·ALL_PRIOR·ALL = 3.1667 [n=30, HIGH]
- saves·AGAINST·W5·ALL = 3.2 [n=5, LOW]
- saves·AGAINST·W10·ALL = 3.3 [n=10, MEDIUM]
- saves·AGAINST·ALL_PRIOR·HOME = 3.2667 [n=15, MEDIUM]
- saves·AGAINST·ALL_PRIOR·AWAY = 3.0667 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·ALL = 8.1667 [n=30, HIGH]
- shots_inside_box·FOR·W5·ALL = 8.6 [n=5, LOW]
- shots_inside_box·FOR·W10·ALL = 9.1 [n=10, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·HOME = 9.5333 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·AWAY = 6.8 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·ALL = 8.6667 [n=30, HIGH]
- shots_inside_box·AGAINST·W5·ALL = 10.0 [n=5, LOW]
- shots_inside_box·AGAINST·W10·ALL = 8.8 [n=10, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·HOME = 7.6 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·AWAY = 9.7333 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·ALL = 4.5 [n=30, HIGH]
- shots_off_target·FOR·W5·ALL = 6.0 [n=5, LOW]
- shots_off_target·FOR·W10·ALL = 6.1 [n=10, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·HOME = 5.2 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·AWAY = 3.8 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·ALL = 4.6 [n=30, HIGH]
- shots_off_target·AGAINST·W5·ALL = 4.0 [n=5, LOW]
- shots_off_target·AGAINST·W10·ALL = 4.6 [n=10, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·HOME = 3.7333 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·AWAY = 5.4667 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·ALL = 4.6 [n=30, HIGH]
- shots_on_target·FOR·W5·ALL = 5.0 [n=5, LOW]
- shots_on_target·FOR·W10·ALL = 4.4 [n=10, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·HOME = 5.0 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·AWAY = 4.2 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·ALL = 4.4333 [n=30, HIGH]
- shots_on_target·AGAINST·W5·ALL = 5.2 [n=5, LOW]
- shots_on_target·AGAINST·W10·ALL = 4.6 [n=10, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·HOME = 4.3333 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·AWAY = 4.5333 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·ALL = 4.8667 [n=30, HIGH]
- shots_outside_box·FOR·W5·ALL = 5.0 [n=5, LOW]
- shots_outside_box·FOR·W10·ALL = 5.6 [n=10, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·HOME = 5.5333 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·AWAY = 4.2 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·ALL = 4.2667 [n=30, HIGH]
- shots_outside_box·AGAINST·W5·ALL = 3.0 [n=5, LOW]
- shots_outside_box·AGAINST·W10·ALL = 3.5 [n=10, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·HOME = 3.5333 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·AWAY = 5.0 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·ALL = 15.5333 [n=30, HIGH]
- tackles·FOR·W5·ALL = 14.0 [n=5, LOW]
- tackles·FOR·W10·ALL = 14.1 [n=10, MEDIUM]
- tackles·FOR·ALL_PRIOR·HOME = 15.0667 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·AWAY = 16.0 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·ALL = 18.6 [n=30, HIGH]
- tackles·AGAINST·W5·ALL = 15.0 [n=5, LOW]
- tackles·AGAINST·W10·ALL = 14.6 [n=10, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·HOME = 17.6667 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·AWAY = 19.5333 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·ALL = 14.9667 [n=30, HIGH]
- throw_ins·FOR·W5·ALL = 15.0 [n=5, LOW]
- throw_ins·FOR·W10·ALL = 15.8 [n=10, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·HOME = 14.8667 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·AWAY = 15.0667 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·ALL = 15.1 [n=30, HIGH]
- throw_ins·AGAINST·W5·ALL = 12.8 [n=5, LOW]
- throw_ins·AGAINST·W10·ALL = 15.7 [n=10, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·HOME = 16.0667 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·AWAY = 14.1333 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·ALL = 13.0333 [n=30, HIGH]
- total_shots·FOR·W5·ALL = 13.6 [n=5, LOW]
- total_shots·FOR·W10·ALL = 14.7 [n=10, MEDIUM]
- total_shots·FOR·ALL_PRIOR·HOME = 15.0667 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·AWAY = 11.0 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·ALL = 12.9333 [n=30, HIGH]
- total_shots·AGAINST·W5·ALL = 13.0 [n=5, LOW]
- total_shots·AGAINST·W10·ALL = 12.3 [n=10, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·HOME = 11.1333 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·AWAY = 14.7333 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·ALL = 26.9667 [n=30, HIGH]
- touches_in_box·FOR·W5·ALL = 26.8 [n=5, LOW]
- touches_in_box·FOR·W10·ALL = 31.3 [n=10, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·HOME = 31.8 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·AWAY = 22.1333 [n=15, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·ALL = 24.2333 [n=30, HIGH]
- touches_in_box·AGAINST·W5·ALL = 25.2 [n=5, LOW]
- touches_in_box·AGAINST·W10·ALL = 21.9 [n=10, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·HOME = 21.7333 [n=15, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·AWAY = 26.7333 [n=15, MEDIUM]
- xg·FOR·ALL_PRIOR·ALL = 1.2957 [n=30, HIGH]
- xg·FOR·W5·ALL = 1.488 [n=5, LOW]
- xg·FOR·W10·ALL = 1.303 [n=10, MEDIUM]
- xg·FOR·ALL_PRIOR·HOME = 1.4573 [n=15, MEDIUM]
- xg·FOR·ALL_PRIOR·AWAY = 1.134 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·ALL = 1.4263 [n=30, HIGH]
- xg·AGAINST·W5·ALL = 1.762 [n=5, LOW]
- xg·AGAINST·W10·ALL = 1.442 [n=10, MEDIUM]
- xg·AGAINST·ALL_PRIOR·HOME = 1.218 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·AWAY = 1.6347 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·ALL = 1.5333 [n=30, HIGH]
- yellow_cards·FOR·W5·ALL = 1.6 [n=5, LOW]
- yellow_cards·FOR·W10·ALL = 1.6 [n=10, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·HOME = 1.2 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·AWAY = 1.8667 [n=15, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·ALL = 2.5 [n=30, HIGH]
- yellow_cards·AGAINST·W5·ALL = 2.2 [n=5, LOW]
- yellow_cards·AGAINST·W10·ALL = 2.5 [n=10, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·HOME = 2.6 [n=15, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·AWAY = 2.4 [n=15, MEDIUM]

### Arm B — opponent-profile context (deterministic bands)

```json
{
 "axes": {
  "accurate_crosses_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "corners_against": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "corners_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "goals_against": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "goals_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "possession_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "shots_on_target_against": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "shots_on_target_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  }
 },
 "similarity_version": "opponent_similarity_v1_pending"
}
```

---

## mt_010244193

- PIT-safe matches available: **134**; match rows included (both teams): **60**; omitted: **74** (reason: `frozen_history_policy(max_matches_per_team=30)`); UNEXPLAINED_OMISSION: **0**.
- Metric cell exposure rate (non-null of serialized): **0.9958**; derived summaries: **480**.
- Availability map: `{"expected_formation": "UNAVAILABLE", "formation": "LOW_COVERAGE", "half_time_state": "UNAVAILABLE", "injuries": "UNAVAILABLE", "lineup": "PIT_UNSAFE", "opponent_profile": "AVAILABLE", "recent_vs_long": "AVAILABLE", "red_cards": "AVAILABLE", "temporal_event_state": "UNAVAILABLE", "venue": "AVAILABLE", "xg": "AVAILABLE"}`
- Arm A packet hash: `cbe7696b7f3a8f83b46e33ea538fb80898220f811970146aa2fb3d87ac132c6f`
- Arm B packet hash: `4e559ec0c67b3343f4fa44d5fb46c74a34ed9aec6b51e2ec0405b2349b9f3af3`

### Arm A — frozen V3 compressed evidence (all items)

76 unconditional shrunk scalar items (venue=ALL, window=ALL_PRIOR):

| id | metric | value | n | reliability |
|---|---|---|---|---|
| HOME_ATK_corners_406027 | corners_for | 4.8519 | 67 | HIGH |
| HOME_DEF_corners_7cfac3 | corners_against | 4.7286 | 67 | HIGH |
| HOME_ATK_accurate_crosses_c28b9e | accurate_crosses_for | 4.3736 | 67 | HIGH |
| HOME_DEF_accurate_crosses_81ffb5 | accurate_crosses_against | 3.7983 | 67 | HIGH |
| HOME_ATK_total_shots_808ac9 | total_shots_for | 14.5759 | 67 | HIGH |
| HOME_DEF_total_shots_c0e347 | total_shots_against | 11.0005 | 67 | HIGH |
| HOME_ATK_shots_on_target_e955e0 | shots_on_target_for | 5.0295 | 67 | HIGH |
| HOME_DEF_shots_on_target_8a3812 | shots_on_target_against | 3.8652 | 67 | HIGH |
| HOME_ATK_shots_off_target_11e91f | shots_off_target_for | 5.2576 | 67 | HIGH |
| HOME_DEF_shots_off_target_26031c | shots_off_target_against | 4.0247 | 67 | HIGH |
| HOME_ATK_blocked_shots_5198f8 | blocked_shots_for | 4.3026 | 67 | HIGH |
| HOME_DEF_blocked_shots_09c3c4 | blocked_shots_against | 3.1108 | 67 | HIGH |
| HOME_ATK_shots_inside_box_cf538d | shots_inside_box_for | 9.4069 | 67 | HIGH |
| HOME_DEF_shots_inside_box_e6b28d | shots_inside_box_against | 7.6397 | 67 | HIGH |
| HOME_ATK_touches_in_box_759ed8 | touches_in_box_for | 27.2688 | 67 | HIGH |
| HOME_DEF_touches_in_box_94cd98 | touches_in_box_against | 22.7482 | 67 | HIGH |
| HOME_ATK_final_third_entries_5aa0be | final_third_entries_for | 52.5421 | 67 | HIGH |
| HOME_DEF_final_third_entries_4a40ef | final_third_entries_against | 50.4052 | 67 | HIGH |
| HOME_ATK_possession_190f3f | possession_for | 53.274 | 67 | HIGH |
| HOME_DEF_possession_f8ada9 | possession_against | 46.726 | 67 | HIGH |
| HOME_ATK_tackles_65b6c1 | tackles_for | 19.6741 | 67 | HIGH |
| HOME_DEF_tackles_e3c85e | tackles_against | 17.1261 | 67 | HIGH |
| HOME_ATK_fouls_8107c6 | fouls_for | 10.1736 | 66 | HIGH |
| HOME_DEF_fouls_b6d53c | fouls_against | 10.618 | 66 | HIGH |
| HOME_ATK_yellow_cards_80b7a4 | yellow_cards_for | 1.9799 | 64 | HIGH |
| HOME_DEF_yellow_cards_8ee8aa | yellow_cards_against | 2.0656 | 64 | HIGH |
| HOME_ATK_clearances_ec2e18 | clearances_for | 21.2607 | 67 | HIGH |
| HOME_DEF_clearances_6d3f4c | clearances_against | 23.7949 | 67 | HIGH |
| HOME_ATK_interceptions_967965 | interceptions_for | 8.5625 | 67 | HIGH |
| HOME_DEF_interceptions_c82020 | interceptions_against | 8.8365 | 67 | HIGH |
| HOME_ATK_goals_08b15b | goals_for | 1.4186 | 67 | HIGH |
| HOME_DEF_goals_d53fdd | goals_against | 1.4049 | 67 | HIGH |
| HOME_ATK_throw_ins_b24629 | throw_ins_for | 17.6544 | 67 | HIGH |
| HOME_DEF_throw_ins_208262 | throw_ins_against | 16.5448 | 67 | HIGH |
| HOME_ATK_big_chances_8a9e2f | big_chances_for | 2.525 | 65 | HIGH |
| HOME_DEF_big_chances_885151 | big_chances_against | 2.2574 | 65 | HIGH |
| HOME_ATK_saves_6bda8d | saves_for | 2.4946 | 66 | HIGH |
| HOME_DEF_saves_19ae14 | saves_against | 3.6057 | 66 | HIGH |
| AWAY_ATK_corners_ca1538 | corners_for | 5.6738 | 67 | HIGH |
| AWAY_DEF_corners_598e33 | corners_against | 4.6327 | 67 | HIGH |
| AWAY_ATK_accurate_crosses_005290 | accurate_crosses_for | 3.4695 | 67 | HIGH |
| AWAY_DEF_accurate_crosses_287e9c | accurate_crosses_against | 3.9627 | 67 | HIGH |
| AWAY_ATK_total_shots_004f7a | total_shots_for | 12.6718 | 67 | HIGH |
| AWAY_DEF_total_shots_403d28 | total_shots_against | 12.4252 | 67 | HIGH |
| AWAY_ATK_shots_on_target_9afd02 | shots_on_target_for | 4.4131 | 67 | HIGH |
| AWAY_DEF_shots_on_target_dcda5e | shots_on_target_against | 4.2487 | 67 | HIGH |
| AWAY_ATK_shots_off_target_b83815 | shots_off_target_for | 4.5453 | 67 | HIGH |
| AWAY_DEF_shots_off_target_5fe2d0 | shots_off_target_against | 4.8877 | 67 | HIGH |
| AWAY_ATK_blocked_shots_93d965 | blocked_shots_for | 3.7136 | 67 | HIGH |
| AWAY_DEF_blocked_shots_97ef03 | blocked_shots_against | 3.3026 | 67 | HIGH |
| AWAY_ATK_shots_inside_box_567ee5 | shots_inside_box_for | 8.5165 | 67 | HIGH |
| AWAY_DEF_shots_inside_box_446c80 | shots_inside_box_against | 8.2836 | 67 | HIGH |
| AWAY_ATK_touches_in_box_2c76ca | touches_in_box_for | 26.4879 | 67 | HIGH |
| AWAY_DEF_touches_in_box_319da5 | touches_in_box_against | 24.7208 | 67 | HIGH |
| AWAY_ATK_final_third_entries_5a0987 | final_third_entries_for | 49.1997 | 67 | HIGH |
| AWAY_DEF_final_third_entries_ed75cd | final_third_entries_against | 50.7202 | 67 | HIGH |
| AWAY_ATK_possession_82105a | possession_for | 51.7671 | 67 | HIGH |
| AWAY_DEF_possession_012ecc | possession_against | 48.2329 | 67 | HIGH |
| AWAY_ATK_tackles_0865bc | tackles_for | 16.2083 | 67 | HIGH |
| AWAY_DEF_tackles_3e6a7d | tackles_against | 18.496 | 67 | HIGH |
| AWAY_ATK_fouls_97bf91 | fouls_for | 10.4863 | 67 | HIGH |
| AWAY_DEF_fouls_94f7aa | fouls_against | 13.0616 | 67 | HIGH |
| AWAY_ATK_yellow_cards_120c77 | yellow_cards_for | 1.8437 | 67 | HIGH |
| AWAY_DEF_yellow_cards_367397 | yellow_cards_against | 2.5698 | 67 | HIGH |
| AWAY_ATK_clearances_74617f | clearances_for | 20.4935 | 67 | HIGH |
| AWAY_DEF_clearances_8bdc80 | clearances_against | 22.9319 | 67 | HIGH |
| AWAY_ATK_interceptions_404e22 | interceptions_for | 6.357 | 67 | HIGH |
| AWAY_DEF_interceptions_4be11b | interceptions_against | 9.1378 | 67 | HIGH |
| AWAY_ATK_goals_5d2c6a | goals_for | 1.446 | 67 | HIGH |
| AWAY_DEF_goals_4ad3b7 | goals_against | 1.2816 | 67 | HIGH |
| AWAY_ATK_throw_ins_64d189 | throw_ins_for | 14.3941 | 67 | HIGH |
| AWAY_DEF_throw_ins_35916f | throw_ins_against | 13.9284 | 67 | HIGH |
| AWAY_ATK_big_chances_065222 | big_chances_for | 2.5954 | 65 | HIGH |
| AWAY_DEF_big_chances_d5f920 | big_chances_against | 2.3137 | 65 | HIGH |
| AWAY_ATK_saves_50b33b | saves_for | 2.8851 | 67 | HIGH |
| AWAY_DEF_saves_bf5cbb | saves_against | 3.0358 | 67 | HIGH |

### Arm B — HOME_TEAM match-level matrix (30 rows × 55 cols)

Columns: `match_alias, kickoff_unix, competition, venue, opponent_alias, own_formation_family, opponent_formation_family, accurate_crosses_for, accurate_crosses_against, big_chances_for, big_chances_against, blocked_shots_for, blocked_shots_against, clearances_for, clearances_against, corners_for, corners_against, final_third_entries_for, final_third_entries_against, fouls_for, fouls_against, goals_for, goals_against, interceptions_for, interceptions_against, npxg_for, npxg_against, offsides_for, offsides_against, possession_for, possession_against, red_cards_for, red_cards_against, saves_for, saves_against, shots_inside_box_for, shots_inside_box_against, shots_off_target_for, shots_off_target_against, shots_on_target_for, shots_on_target_against, shots_outside_box_for, shots_outside_box_against, tackles_for, tackles_against, throw_ins_for, throw_ins_against, total_shots_for, total_shots_against, touches_in_box_for, touches_in_box_against, xg_for, xg_against, yellow_cards_for, yellow_cards_against`

| match_alias | kickoff_unix | competition | venue | opponent_alias | own_formation_family | opponent_formation_family | accurate_crosses_for | accurate_crosses_against | big_chances_for | big_chances_against | blocked_shots_for | blocked_shots_against | clearances_for | clearances_against | corners_for | corners_against | final_third_entries_for | final_third_entries_against | fouls_for | fouls_against | goals_for | goals_against | interceptions_for | interceptions_against | npxg_for | npxg_against | offsides_for | offsides_against | possession_for | possession_against | red_cards_for | red_cards_against | saves_for | saves_against | shots_inside_box_for | shots_inside_box_against | shots_off_target_for | shots_off_target_against | shots_on_target_for | shots_on_target_against | shots_outside_box_for | shots_outside_box_against | tackles_for | tackles_against | throw_ins_for | throw_ins_against | total_shots_for | total_shots_against | touches_in_box_for | touches_in_box_against | xg_for | xg_against | yellow_cards_for | yellow_cards_against |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| m_mt_196560708 | 1748185200 | COMPETITION | HOME | OPP_001 |  |  | 6.0 | 0.0 | 3.0 | 0.0 | 2.0 | 3.0 | 19.0 | 20.0 | 4.0 | 3.0 | 66.0 | 45.0 | 10.0 | 10.0 | 2.0 | 0.0 | 7.0 | 6.0 | 2.19 | 0.39 | 5.0 | 3.0 | 67.0 | 33.0 | 0.0 | 1.0 | 1.0 | 8.0 | 14.0 | 4.0 | 13.0 | 2.0 | 10.0 | 1.0 | 11.0 | 2.0 | 20.0 | 9.0 | 12.0 | 8.0 | 25.0 | 6.0 | 52.0 | 18.0 | 2.95 | 0.39 | 2.0 | 2.0 |
| m_mt_626439509 | 1755444600 | COMPETITION | HOME | OPP_002 |  |  | 3.0 | 2.0 | 0.0 | 1.0 | 8.0 | 3.0 | 23.0 | 30.0 | 3.0 | 4.0 | 54.0 | 35.0 | 10.0 | 19.0 | 0.0 | 1.0 | 4.0 | 4.0 | 1.53 | 1.31 | 1.0 | 2.0 | 61.0 | 39.0 | 0.0 | 0.0 | 2.0 | 7.0 | 15.0 | 5.0 | 7.0 | 3.0 | 7.0 | 3.0 | 7.0 | 4.0 | 22.0 | 18.0 | 20.0 | 15.0 | 22.0 | 9.0 | 36.0 | 20.0 | 1.52 | 1.31 | 1.0 | 4.0 |
| m_mt_191506839 | 1756049400 | COMPETITION | AWAY | OPP_003 | BACK_THREE | BACK_FOUR | 4.0 | 10.0 | 2.0 | 3.0 | 1.0 | 5.0 | 27.0 | 24.0 | 6.0 | 9.0 | 50.0 | 47.0 | 10.0 | 12.0 | 1.0 | 1.0 | 5.0 | 8.0 | 0.84 | 1.77 | 1.0 | 2.0 | 48.0 | 52.0 | 0.0 | 0.0 | 2.0 | 3.0 | 8.0 | 10.0 | 6.0 | 4.0 | 3.0 | 4.0 | 2.0 | 3.0 | 17.0 | 10.0 | 17.0 | 21.0 | 10.0 | 13.0 | 25.0 | 38.0 | 1.63 | 1.76 | 1.0 | 1.0 |
| m_mt_626439031 | 1756562400 | COMPETITION | HOME | OPP_004 |  |  | 12.0 | 1.0 | 4.0 | 2.0 | 7.0 | 2.0 | 17.0 | 38.0 | 7.0 | 1.0 | 59.0 | 48.0 | 9.0 | 9.0 | 3.0 | 2.0 | 1.0 | 9.0 | 2.75 | 1.25 | 1.0 | 1.0 | 62.0 | 38.0 | 0.0 | 0.0 | 1.0 | 5.0 | 19.0 | 5.0 | 13.0 | 1.0 | 6.0 | 3.0 | 7.0 | 1.0 | 16.0 | 20.0 | 21.0 | 13.0 | 26.0 | 6.0 | 39.0 | 17.0 | 3.54 | 1.2 | 1.0 | 5.0 |
| m_mt_979812396 | 1757863800 | COMPETITION | AWAY | OPP_005 |  |  | 6.0 | 1.0 | 2.0 | 4.0 | 2.0 | 0.0 | 10.0 | 33.0 | 4.0 | 2.0 | 66.0 | 41.0 | 8.0 | 8.0 | 0.0 | 3.0 | 13.0 | 10.0 | 1.51 | 2.68 | 3.0 | 2.0 | 55.0 | 45.0 | 0.0 | 0.0 | 3.0 | 2.0 | 7.0 | 12.0 | 8.0 | 7.0 | 2.0 | 6.0 | 5.0 | 1.0 | 23.0 | 13.0 | 21.0 | 26.0 | 12.0 | 13.0 | 29.0 | 26.0 | 1.52 | 2.63 |  |  |
| m_mt_747395742 | 1758385800 | COMPETITION | HOME | OPP_006 |  |  | 8.0 | 2.0 | 3.0 | 1.0 | 4.0 | 2.0 | 19.0 | 29.0 | 5.0 | 5.0 | 49.0 | 54.0 | 13.0 | 14.0 | 2.0 | 1.0 | 10.0 | 8.0 | 1.84 | 0.39 | 3.0 | 2.0 | 41.0 | 59.0 | 1.0 | 1.0 | 0.0 | 2.0 | 6.0 | 4.0 | 3.0 | 2.0 | 4.0 | 1.0 | 5.0 | 1.0 | 21.0 | 16.0 | 23.0 | 20.0 | 11.0 | 5.0 | 21.0 | 16.0 | 1.84 | 0.43 | 2.0 | 5.0 |
| m_mt_010243025 | 1758972600 | COMPETITION | AWAY | OPP_007 |  |  | 3.0 | 7.0 | 4.0 | 6.0 | 4.0 | 1.0 | 29.0 | 23.0 | 2.0 | 4.0 | 44.0 | 61.0 | 10.0 | 14.0 | 1.0 | 3.0 | 4.0 | 7.0 | 1.54 | 1.99 | 1.0 | 2.0 | 56.0 | 44.0 | 0.0 | 0.0 | 5.0 | 5.0 | 9.0 | 7.0 | 4.0 | 1.0 | 6.0 | 8.0 | 5.0 | 3.0 | 16.0 | 14.0 | 17.0 | 22.0 | 14.0 | 10.0 | 17.0 | 23.0 | 2.03 | 1.99 | 2.0 | 2.0 |
| m_mt_363781331 | 1759586400 | COMPETITION | HOME | OPP_008 |  |  | 5.0 | 4.0 | 2.0 | 2.0 | 2.0 | 1.0 | 24.0 | 31.0 | 2.0 | 3.0 | 55.0 | 47.0 | 10.0 | 12.0 | 2.0 | 0.0 | 10.0 | 9.0 | 1.93 | 0.71 | 1.0 | 2.0 | 51.0 | 49.0 | 0.0 | 0.0 | 3.0 | 4.0 | 11.0 | 5.0 | 7.0 | 4.0 | 6.0 | 3.0 | 4.0 | 3.0 | 16.0 | 21.0 | 23.0 | 20.0 | 15.0 | 8.0 | 32.0 | 14.0 | 1.88 | 0.71 | 1.0 | 4.0 |
| m_mt_252068399 | 1760887800 | COMPETITION | AWAY | OPP_009 |  |  | 4.0 | 9.0 | 5.0 | 5.0 | 3.0 | 2.0 | 46.0 | 28.0 | 4.0 | 9.0 | 63.0 | 63.0 |  |  | 2.0 | 1.0 | 6.0 | 5.0 | 1.34 | 2.75 | 1.0 | 1.0 | 36.0 | 64.0 | 0.0 | 0.0 | 5.0 | 2.0 | 10.0 | 16.0 | 5.0 | 11.0 | 4.0 | 6.0 | 2.0 | 3.0 | 15.0 | 13.0 | 17.0 | 31.0 | 12.0 | 19.0 | 16.0 | 52.0 | 1.34 | 2.75 | 2.0 | 0.0 |
| m_mt_363782585 | 1761409800 | COMPETITION | HOME | OPP_010 |  |  | 1.0 | 5.0 | 4.0 | 1.0 | 1.0 | 4.0 | 15.0 | 18.0 | 1.0 | 6.0 | 46.0 | 45.0 | 4.0 | 13.0 | 4.0 | 2.0 | 14.0 | 12.0 | 1.28 | 1.12 | 2.0 | 2.0 | 44.0 | 56.0 | 0.0 | 0.0 | 3.0 | 5.0 | 7.0 | 10.0 | 3.0 | 8.0 | 9.0 | 5.0 | 6.0 | 7.0 | 21.0 | 18.0 | 16.0 | 14.0 | 13.0 | 17.0 | 21.0 | 20.0 | 1.29 | 1.12 | 2.0 | 2.0 |
| m_mt_404671919 | 1762009200 | COMPETITION | AWAY | OPP_011 | BACK_THREE | BACK_FOUR | 5.0 | 5.0 | 0.0 | 1.0 | 5.0 | 6.0 | 22.0 | 18.0 | 5.0 | 8.0 | 63.0 | 57.0 | 0.0 | 17.0 | 2.0 | 2.0 | 9.0 | 9.0 | 1.14 | 2.0 | 1.0 | 2.0 | 59.0 | 41.0 | 0.0 | 0.0 | 1.0 | 4.0 | 8.0 | 11.0 | 6.0 | 8.0 | 7.0 | 3.0 | 10.0 | 6.0 | 12.0 | 17.0 | 12.0 | 15.0 | 18.0 | 17.0 | 18.0 | 24.0 | 1.15 | 2.0 | 1.0 | 1.0 |
| m_mt_363781242 | 1762605000 | COMPETITION | AWAY | OPP_012 |  |  | 4.0 | 5.0 | 2.0 | 3.0 | 1.0 | 3.0 | 23.0 | 17.0 | 3.0 | 5.0 | 40.0 | 65.0 | 8.0 | 10.0 | 2.0 | 2.0 | 6.0 | 7.0 | 0.77 | 0.92 | 3.0 | 2.0 | 45.0 | 55.0 | 0.0 | 0.0 | 2.0 | 0.0 | 5.0 | 6.0 | 2.0 | 3.0 | 2.0 | 4.0 | 0.0 | 4.0 | 21.0 | 26.0 | 26.0 | 18.0 | 5.0 | 10.0 | 19.0 | 18.0 | 0.63 | 0.92 | 1.0 | 5.0 |
| m_mt_027927049 | 1764014400 | COMPETITION | HOME | OPP_013 |  |  | 7.0 | 1.0 | 3.0 | 0.0 | 7.0 | 1.0 | 19.0 | 46.0 | 9.0 | 1.0 | 70.0 | 45.0 | 12.0 | 9.0 | 0.0 | 1.0 | 8.0 | 11.0 | 1.71 | 0.21 | 1.0 | 2.0 | 70.0 | 30.0 | 0.0 | 1.0 | 0.0 | 6.0 | 17.0 | 2.0 | 12.0 | 1.0 | 6.0 | 1.0 | 8.0 | 1.0 | 14.0 | 6.0 | 19.0 | 18.0 | 25.0 | 3.0 | 50.0 | 10.0 | 1.71 | 0.21 | 2.0 | 0.0 |
| m_mt_979812384 | 1764504000 | COMPETITION | AWAY | OPP_014 |  |  | 3.0 | 4.0 | 2.0 | 3.0 | 0.0 | 5.0 | 31.0 | 44.0 | 4.0 | 4.0 | 70.0 | 62.0 | 14.0 | 14.0 | 2.0 | 1.0 | 10.0 | 7.0 | 1.36 | 1.03 | 0.0 | 3.0 | 56.0 | 44.0 | 0.0 | 0.0 | 2.0 | 4.0 | 8.0 | 11.0 | 8.0 | 6.0 | 6.0 | 3.0 | 6.0 | 3.0 | 16.0 | 14.0 | 23.0 | 14.0 | 14.0 | 14.0 | 18.0 | 26.0 | 1.19 | 1.83 | 2.0 | 3.0 |
| m_mt_191506144 | 1764878400 | COMPETITION | HOME | OPP_015 |  |  | 5.0 | 3.0 | 3.0 | 1.0 | 8.0 | 5.0 | 17.0 | 39.0 | 6.0 | 6.0 | 65.0 | 60.0 | 13.0 | 9.0 | 1.0 | 1.0 | 5.0 | 20.0 | 1.85 | 0.8 | 3.0 | 2.0 | 65.0 | 35.0 | 0.0 | 0.0 | 1.0 | 3.0 | 13.0 | 10.0 | 5.0 | 3.0 | 4.0 | 3.0 | 4.0 | 1.0 | 19.0 | 15.0 | 28.0 | 19.0 | 17.0 | 11.0 | 43.0 | 28.0 | 1.8 | 0.79 | 2.0 | 2.0 |
| m_mt_641836814 | 1765224000 | COMPETITION | AWAY | OPP_016 |  |  | 3.0 | 6.0 | 8.0 | 1.0 | 14.0 | 3.0 | 27.0 | 24.0 | 9.0 | 1.0 | 50.0 | 61.0 | 12.0 | 17.0 | 4.0 | 1.0 | 7.0 | 13.0 | 3.51 | 0.58 | 3.0 | 2.0 | 63.0 | 37.0 | 0.0 | 0.0 | 1.0 | 4.0 | 20.0 | 4.0 | 3.0 | 3.0 | 10.0 | 2.0 | 7.0 | 4.0 | 16.0 | 26.0 | 23.0 | 19.0 | 27.0 | 8.0 | 42.0 | 21.0 | 4.24 | 0.41 | 2.0 | 3.0 |
| m_mt_732455509 | 1765828800 | COMPETITION | HOME | OPP_017 |  |  | 6.0 | 3.0 | 2.0 | 6.0 | 10.0 | 0.0 | 47.0 | 29.0 | 5.0 | 4.0 | 53.0 | 65.0 | 15.0 | 12.0 | 4.0 | 4.0 | 3.0 | 8.0 | 3.4 | 2.03 | 0.0 | 1.0 | 57.0 | 43.0 | 0.0 | 0.0 | 5.0 | 5.0 | 18.0 | 9.0 | 6.0 | 5.0 | 9.0 | 9.0 | 7.0 | 5.0 | 16.0 | 14.0 | 19.0 | 20.0 | 25.0 | 14.0 | 49.0 | 24.0 | 3.4 | 1.94 | 2.0 | 3.0 |
| m_mt_626439604 | 1766334600 | COMPETITION | AWAY | OPP_001 |  |  | 4.0 | 1.0 | 3.0 | 2.0 | 3.0 | 5.0 | 21.0 | 22.0 | 5.0 | 5.0 | 49.0 | 27.0 | 2.0 | 4.0 | 1.0 | 2.0 | 9.0 | 7.0 | 1.32 | 1.51 | 1.0 | 3.0 | 57.0 | 43.0 | 0.0 | 0.0 | 2.0 | 5.0 | 5.0 | 8.0 | 6.0 | 3.0 | 6.0 | 4.0 | 10.0 | 4.0 | 26.0 | 18.0 | 19.0 | 8.0 | 15.0 | 12.0 | 34.0 | 20.0 | 1.33 | 1.54 | 2.0 | 1.0 |
| m_mt_626435815 | 1766779200 | COMPETITION | HOME | OPP_018 | BACK_FOUR | BACK_FOUR | 3.0 | 7.0 | 1.0 | 1.0 | 0.0 | 7.0 | 44.0 | 13.0 | 2.0 | 11.0 | 35.0 | 84.0 | 9.0 | 5.0 | 1.0 | 0.0 | 18.0 | 6.0 | 1.17 | 1.18 | 0.0 | 1.0 | 33.0 | 67.0 | 0.0 | 0.0 | 3.0 | 2.0 | 8.0 | 14.0 | 6.0 | 6.0 | 3.0 | 3.0 | 1.0 | 2.0 | 20.0 | 15.0 | 20.0 | 16.0 | 9.0 | 16.0 | 15.0 | 43.0 | 1.17 | 1.18 | 2.0 | 1.0 |
| m_mt_626435846 | 1767125700 | COMPETITION | HOME | OPP_016 |  |  | 6.0 | 4.0 | 2.0 | 2.0 | 4.0 | 2.0 | 16.0 | 28.0 | 8.0 | 4.0 | 58.0 | 36.0 | 9.0 | 12.0 | 1.0 | 1.0 | 4.0 | 10.0 | 0.8 | 1.26 | 3.0 | 1.0 | 56.0 | 44.0 | 0.0 | 0.0 | 3.0 | 5.0 | 10.0 | 8.0 | 5.0 | 5.0 | 6.0 | 4.0 | 5.0 | 3.0 | 21.0 | 20.0 | 19.0 | 14.0 | 15.0 | 11.0 | 21.0 | 23.0 | 0.84 | 1.16 | 0.0 | 2.0 |
| m_mt_010249730 | 1767529800 | COMPETITION | AWAY | OPP_019 | BACK_THREE | BACK_THREE | 2.0 | 3.0 | 3.0 | 1.0 | 5.0 | 2.0 | 38.0 | 23.0 | 4.0 | 6.0 | 66.0 | 67.0 | 9.0 | 9.0 | 1.0 | 1.0 | 8.0 | 17.0 | 1.59 | 0.9 | 3.0 | 1.0 | 55.0 | 45.0 | 0.0 | 0.0 | 2.0 | 1.0 | 9.0 | 8.0 | 8.0 | 6.0 | 2.0 | 3.0 | 6.0 | 3.0 | 25.0 | 18.0 | 16.0 | 20.0 | 15.0 | 11.0 | 22.0 | 25.0 | 1.58 | 0.9 | 1.0 | 0.0 |
| m_mt_363781218 | 1767816900 | COMPETITION | AWAY | OPP_004 |  |  | 9.0 | 0.0 | 5.0 | 0.0 | 7.0 | 5.0 | 13.0 | 25.0 | 6.0 | 2.0 | 74.0 | 36.0 | 8.0 | 9.0 | 2.0 | 2.0 | 6.0 | 7.0 | 2.6 | 0.28 | 0.0 | 3.0 | 65.0 | 35.0 | 0.0 | 0.0 | 0.0 | 6.0 | 21.0 | 6.0 | 13.0 | 1.0 | 10.0 | 1.0 | 9.0 | 1.0 | 19.0 | 16.0 | 16.0 | 16.0 | 30.0 | 7.0 | 43.0 | 9.0 | 2.55 | 0.24 | 0.0 | 2.0 |
| m_mt_747395622 | 1768653000 | COMPETITION | HOME | OPP_005 |  |  | 4.0 | 2.0 | 6.0 | 0.0 | 1.0 | 3.0 | 27.0 | 19.0 | 1.0 | 6.0 | 50.0 | 59.0 | 13.0 | 8.0 | 2.0 | 0.0 | 12.0 | 9.0 | 2.29 | 0.47 | 6.0 | 1.0 | 32.0 | 68.0 | 0.0 | 0.0 | 1.0 | 5.0 | 10.0 | 5.0 | 4.0 | 3.0 | 7.0 | 1.0 | 1.0 | 2.0 | 24.0 | 13.0 | 16.0 | 13.0 | 11.0 | 7.0 | 21.0 | 35.0 | 2.27 | 0.45 | 2.0 | 3.0 |
| m_mt_838950793 | 1769358600 | COMPETITION | AWAY | OPP_002 |  |  | 1.0 | 4.0 | 1.0 | 1.0 | 2.0 | 6.0 | 25.0 | 20.0 | 2.0 | 9.0 | 54.0 | 47.0 | 9.0 | 11.0 | 3.0 | 2.0 | 6.0 | 11.0 | 0.83 | 1.2 | 0.0 | 3.0 | 43.0 | 57.0 | 0.0 | 0.0 | 3.0 | 0.0 | 3.0 | 9.0 | 5.0 | 5.0 | 3.0 | 4.0 | 7.0 | 6.0 | 14.0 | 11.0 | 12.0 | 17.0 | 10.0 | 15.0 | 9.0 | 28.0 | 0.73 | 1.2 | 0.0 | 2.0 |
| m_mt_191506881 | 1769954400 | COMPETITION | HOME | OPP_003 |  |  | 6.0 | 8.0 | 3.0 | 2.0 | 3.0 | 5.0 | 29.0 | 9.0 | 3.0 | 7.0 | 66.0 | 54.0 | 6.0 | 9.0 | 3.0 | 2.0 | 8.0 | 13.0 | 1.81 | 1.19 | 1.0 | 2.0 | 42.0 | 58.0 | 0.0 | 0.0 | 4.0 | 3.0 | 12.0 | 8.0 | 4.0 | 3.0 | 6.0 | 6.0 | 1.0 | 6.0 | 22.0 | 17.0 | 12.0 | 20.0 | 13.0 | 14.0 | 26.0 | 25.0 | 1.74 | 1.97 | 2.0 | 1.0 |
| m_mt_626439626 | 1770467400 | COMPETITION | HOME | OPP_012 |  |  | 4.0 | 4.0 | 3.0 | 1.0 | 6.0 | 5.0 | 11.0 | 30.0 | 7.0 | 0.0 | 77.0 | 38.0 | 12.0 | 11.0 | 2.0 | 0.0 | 5.0 | 9.0 | 1.79 | 0.49 | 3.0 | 1.0 | 65.0 | 35.0 | 0.0 | 1.0 | 1.0 | 8.0 | 10.0 | 4.0 | 7.0 | 1.0 | 10.0 | 1.0 | 13.0 | 3.0 | 17.0 | 16.0 | 18.0 | 8.0 | 23.0 | 7.0 | 37.0 | 17.0 | 1.79 | 0.49 | 1.0 | 2.0 |
| m_mt_585124545 | 1770754500 | COMPETITION | AWAY | OPP_015 | BACK_FOUR | BACK_FOUR | 7.0 | 3.0 | 1.0 | 2.0 | 2.0 | 3.0 | 12.0 | 23.0 | 3.0 | 5.0 | 72.0 | 48.0 | 4.0 | 10.0 | 1.0 | 1.0 | 8.0 | 15.0 | 0.63 | 1.09 | 3.0 | 1.0 | 65.0 | 35.0 | 0.0 | 0.0 | 2.0 | 1.0 | 8.0 | 4.0 | 4.0 | 1.0 | 3.0 | 3.0 | 1.0 | 3.0 | 19.0 | 17.0 | 28.0 | 14.0 | 9.0 | 7.0 | 21.0 | 9.0 | 0.62 | 1.08 | 1.0 | 1.0 |
| m_mt_153746445 | 1771876800 | COMPETITION | AWAY | OPP_013 |  |  | 1.0 | 3.0 | 1.0 | 0.0 | 2.0 | 6.0 | 16.0 | 9.0 | 0.0 | 4.0 | 46.0 | 40.0 | 6.0 | 10.0 | 1.0 | 0.0 | 8.0 | 10.0 | 1.27 | 0.62 | 0.0 | 1.0 | 57.0 | 43.0 | 0.0 | 0.0 | 2.0 | 1.0 | 6.0 | 3.0 | 6.0 | 0.0 | 3.0 | 2.0 | 5.0 | 5.0 | 6.0 | 16.0 | 12.0 | 17.0 | 11.0 | 8.0 | 13.0 | 10.0 | 0.85 | 0.29 |  |  |
| m_mt_838955357 | 1772373600 | COMPETITION | HOME | OPP_014 |  |  | 11.0 | 1.0 | 3.0 | 0.0 | 5.0 | 2.0 | 13.0 | 27.0 | 7.0 | 1.0 | 56.0 | 49.0 | 13.0 | 12.0 | 2.0 | 1.0 | 3.0 | 6.0 | 1.33 | 0.39 | 1.0 | 2.0 | 61.0 | 39.0 | 0.0 | 1.0 | 2.0 | 9.0 | 11.0 | 5.0 | 4.0 | 3.0 | 11.0 | 3.0 | 9.0 | 3.0 | 13.0 | 17.0 | 10.0 | 11.0 | 20.0 | 8.0 | 32.0 | 13.0 | 2.12 | 0.38 | 2.0 | 2.0 |
| m_mt_585122841 | 1772655300 | COMPETITION | AWAY | OPP_018 |  |  | 2.0 | 6.0 | 4.0 | 2.0 | 5.0 | 1.0 | 17.0 | 33.0 | 4.0 | 2.0 | 48.0 | 48.0 | 16.0 | 15.0 | 1.0 | 2.0 | 10.0 | 9.0 | 1.29 | 1.43 |  |  | 55.0 | 45.0 | 0.0 | 1.0 | 3.0 | 4.0 | 8.0 | 8.0 | 4.0 | 6.0 | 5.0 | 5.0 | 6.0 | 4.0 | 12.0 | 17.0 | 17.0 | 21.0 | 14.0 | 12.0 | 31.0 | 23.0 | 1.28 | 2.22 | 3.0 | 4.0 |

### Arm B — AWAY_TEAM match-level matrix (30 rows × 55 cols)

Columns: `match_alias, kickoff_unix, competition, venue, opponent_alias, own_formation_family, opponent_formation_family, accurate_crosses_for, accurate_crosses_against, big_chances_for, big_chances_against, blocked_shots_for, blocked_shots_against, clearances_for, clearances_against, corners_for, corners_against, final_third_entries_for, final_third_entries_against, fouls_for, fouls_against, goals_for, goals_against, interceptions_for, interceptions_against, npxg_for, npxg_against, offsides_for, offsides_against, possession_for, possession_against, red_cards_for, red_cards_against, saves_for, saves_against, shots_inside_box_for, shots_inside_box_against, shots_off_target_for, shots_off_target_against, shots_on_target_for, shots_on_target_against, shots_outside_box_for, shots_outside_box_against, tackles_for, tackles_against, throw_ins_for, throw_ins_against, total_shots_for, total_shots_against, touches_in_box_for, touches_in_box_against, xg_for, xg_against, yellow_cards_for, yellow_cards_against`

| match_alias | kickoff_unix | competition | venue | opponent_alias | own_formation_family | opponent_formation_family | accurate_crosses_for | accurate_crosses_against | big_chances_for | big_chances_against | blocked_shots_for | blocked_shots_against | clearances_for | clearances_against | corners_for | corners_against | final_third_entries_for | final_third_entries_against | fouls_for | fouls_against | goals_for | goals_against | interceptions_for | interceptions_against | npxg_for | npxg_against | offsides_for | offsides_against | possession_for | possession_against | red_cards_for | red_cards_against | saves_for | saves_against | shots_inside_box_for | shots_inside_box_against | shots_off_target_for | shots_off_target_against | shots_on_target_for | shots_on_target_against | shots_outside_box_for | shots_outside_box_against | tackles_for | tackles_against | throw_ins_for | throw_ins_against | total_shots_for | total_shots_against | touches_in_box_for | touches_in_box_against | xg_for | xg_against | yellow_cards_for | yellow_cards_against |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| m_mt_196560708 | 1748185200 | COMPETITION | AWAY | OPP_020 |  |  | 0.0 | 6.0 | 0.0 | 3.0 | 3.0 | 2.0 | 20.0 | 19.0 | 3.0 | 4.0 | 45.0 | 66.0 | 10.0 | 10.0 | 0.0 | 2.0 | 6.0 | 7.0 | 0.39 | 2.19 | 3.0 | 5.0 | 33.0 | 67.0 | 1.0 | 0.0 | 8.0 | 1.0 | 4.0 | 14.0 | 2.0 | 13.0 | 1.0 | 10.0 | 2.0 | 11.0 | 9.0 | 20.0 | 8.0 | 12.0 | 6.0 | 25.0 | 18.0 | 52.0 | 0.39 | 2.95 | 2.0 | 2.0 |
| m_mt_626439541 | 1755343800 | COMPETITION | HOME | OPP_018 |  |  | 3.0 | 6.0 | 1.0 | 2.0 | 0.0 | 7.0 | 20.0 | 22.0 | 3.0 | 6.0 | 46.0 | 55.0 | 13.0 | 11.0 | 0.0 | 0.0 | 10.0 | 12.0 | 0.2 | 1.43 | 2.0 | 1.0 | 40.0 | 60.0 | 1.0 | 0.0 | 3.0 | 3.0 | 3.0 | 9.0 | 0.0 | 6.0 | 3.0 | 3.0 | 0.0 | 7.0 | 11.0 | 10.0 | 18.0 | 9.0 | 3.0 | 16.0 | 14.0 | 33.0 | 0.2 | 1.43 | 1.0 | 1.0 |
| m_mt_838950688 | 1755957600 | COMPETITION | AWAY | OPP_007 | BACK_FOUR | BACK_FOUR | 3.0 | 5.0 | 0.0 | 2.0 | 8.0 | 3.0 | 12.0 | 47.0 | 9.0 | 2.0 | 69.0 | 40.0 | 9.0 | 11.0 | 0.0 | 1.0 | 5.0 | 9.0 | 1.23 | 1.57 | 0.0 | 1.0 | 76.0 | 24.0 | 0.0 | 0.0 | 1.0 | 2.0 | 12.0 | 8.0 | 7.0 | 4.0 | 2.0 | 2.0 | 5.0 | 1.0 | 14.0 | 29.0 | 23.0 | 13.0 | 17.0 | 9.0 | 43.0 | 25.0 | 1.23 | 1.27 | 2.0 | 1.0 |
| m_mt_252067156 | 1756663200 | COMPETITION | HOME | OPP_014 |  |  | 6.0 | 2.0 | 2.0 | 4.0 | 1.0 | 1.0 | 17.0 | 37.0 | 10.0 | 1.0 | 79.0 | 51.0 | 7.0 | 14.0 | 0.0 | 3.0 | 6.0 | 10.0 | 1.14 | 1.86 | 0.0 | 2.0 | 58.0 | 42.0 | 0.0 | 0.0 | 1.0 | 4.0 | 10.0 | 5.0 | 8.0 | 1.0 | 4.0 | 4.0 | 3.0 | 1.0 | 11.0 | 26.0 | 20.0 | 9.0 | 13.0 | 6.0 | 20.0 | 14.0 | 1.14 | 2.65 | 2.0 | 3.0 |
| m_mt_626439003 | 1757772000 | COMPETITION | AWAY | OPP_013 |  |  | 3.0 | 8.0 | 0.0 | 3.0 | 5.0 | 9.0 | 19.0 | 17.0 | 3.0 | 10.0 | 43.0 | 53.0 | 15.0 | 17.0 | 0.0 | 0.0 | 4.0 | 5.0 | 0.44 | 2.08 | 2.0 | 2.0 | 52.0 | 48.0 | 0.0 | 0.0 | 2.0 | 1.0 | 3.0 | 14.0 | 1.0 | 9.0 | 1.0 | 2.0 | 4.0 | 6.0 | 16.0 | 23.0 | 14.0 | 20.0 | 7.0 | 20.0 | 8.0 | 46.0 | 0.54 | 2.08 | 3.0 | 3.0 |
| m_mt_979812971 | 1758459600 | COMPETITION | AWAY | OPP_008 |  |  | 4.0 | 2.0 | 2.0 | 1.0 | 6.0 | 4.0 | 28.0 | 34.0 | 5.0 | 6.0 | 67.0 | 41.0 | 8.0 | 14.0 | 1.0 | 1.0 | 3.0 | 8.0 | 0.78 | 1.04 | 3.0 | 0.0 | 71.0 | 29.0 | 0.0 | 1.0 | 3.0 | 1.0 | 6.0 | 10.0 | 4.0 | 6.0 | 2.0 | 4.0 | 6.0 | 4.0 | 11.0 | 20.0 | 18.0 | 15.0 | 12.0 | 14.0 | 34.0 | 16.0 | 0.78 | 1.04 | 1.0 | 2.0 |
| m_mt_252067206 | 1759064400 | COMPETITION | HOME | OPP_003 |  |  | 1.0 | 7.0 | 3.0 | 1.0 | 2.0 | 3.0 | 26.0 | 23.0 | 2.0 | 8.0 | 43.0 | 56.0 | 10.0 | 13.0 | 3.0 | 1.0 | 7.0 | 9.0 | 1.11 | 1.06 | 2.0 | 4.0 | 48.0 | 52.0 | 0.0 | 0.0 | 3.0 | 1.0 | 4.0 | 9.0 | 3.0 | 4.0 | 4.0 | 4.0 | 5.0 | 2.0 | 10.0 | 16.0 | 11.0 | 18.0 | 9.0 | 11.0 | 18.0 | 27.0 | 1.11 | 0.92 | 1.0 | 4.0 |
| m_mt_363781348 | 1759669200 | COMPETITION | HOME | OPP_004 |  |  | 8.0 | 3.0 | 2.0 | 1.0 | 3.0 | 2.0 | 23.0 | 5.0 | 6.0 | 4.0 | 40.0 | 60.0 | 9.0 | 15.0 | 2.0 | 1.0 | 5.0 | 13.0 | 1.16 | 0.41 | 3.0 | 5.0 | 55.0 | 45.0 | 0.0 | 0.0 | 1.0 | 5.0 | 12.0 | 3.0 | 5.0 | 1.0 | 7.0 | 2.0 | 3.0 | 2.0 | 15.0 | 27.0 | 9.0 | 17.0 | 15.0 | 5.0 | 23.0 | 12.0 | 1.16 | 0.4 | 3.0 | 1.0 |
| m_mt_747390141 | 1760878800 | COMPETITION | AWAY | OPP_012 |  |  | 0.0 | 5.0 | 0.0 | 3.0 | 2.0 | 2.0 | 29.0 | 29.0 | 6.0 | 6.0 | 43.0 | 47.0 | 7.0 | 11.0 | 2.0 | 1.0 | 2.0 | 6.0 | 0.32 | 0.75 | 1.0 | 6.0 | 47.0 | 53.0 | 0.0 | 0.0 | 2.0 | 0.0 | 2.0 | 6.0 | 4.0 | 4.0 | 2.0 | 3.0 | 6.0 | 3.0 | 24.0 | 25.0 | 21.0 | 23.0 | 8.0 | 9.0 | 7.0 | 28.0 | 0.32 | 0.75 | 0.0 | 2.0 |
| m_mt_363782563 | 1761487200 | COMPETITION | HOME | OPP_005 |  |  | 3.0 | 7.0 | 2.0 | 2.0 | 5.0 | 9.0 | 19.0 | 19.0 | 5.0 | 6.0 | 48.0 | 52.0 | 8.0 | 16.0 | 1.0 | 0.0 | 7.0 | 11.0 | 0.82 | 1.19 | 1.0 | 3.0 | 47.0 | 53.0 | 0.0 | 0.0 | 3.0 | 2.0 | 8.0 | 14.0 | 1.0 | 5.0 | 3.0 | 4.0 | 1.0 | 4.0 | 18.0 | 14.0 | 13.0 | 14.0 | 9.0 | 18.0 | 26.0 | 33.0 | 0.81 | 1.18 | 1.0 | 4.0 |
| m_mt_252068377 | 1762027200 | COMPETITION | AWAY | OPP_009 | BACK_FOUR | BACK_FOUR | 1.0 | 1.0 | 0.0 | 4.0 | 1.0 | 5.0 | 26.0 | 25.0 | 4.0 | 1.0 | 51.0 | 63.0 | 11.0 | 13.0 | 0.0 | 2.0 | 6.0 | 6.0 | 0.41 | 1.19 | 0.0 | 8.0 | 47.0 | 53.0 | 0.0 | 0.0 | 2.0 | 3.0 | 4.0 | 7.0 | 6.0 | 7.0 | 3.0 | 4.0 | 6.0 | 9.0 | 11.0 | 12.0 | 12.0 | 17.0 | 10.0 | 16.0 | 22.0 | 21.0 | 0.41 | 1.19 | 3.0 | 2.0 |
| m_mt_010243910 | 1762696800 | COMPETITION | HOME | OPP_017 |  |  | 3.0 | 2.0 | 2.0 | 2.0 | 6.0 | 4.0 | 22.0 | 35.0 | 6.0 | 9.0 | 54.0 | 43.0 | 8.0 | 20.0 | 4.0 | 0.0 | 6.0 | 11.0 | 1.7 | 0.82 | 0.0 | 2.0 | 52.0 | 48.0 | 0.0 | 0.0 | 3.0 | 4.0 | 10.0 | 6.0 | 2.0 | 5.0 | 8.0 | 3.0 | 6.0 | 6.0 | 20.0 | 16.0 | 15.0 | 22.0 | 16.0 | 12.0 | 27.0 | 12.0 | 1.7 | 1.61 | 2.0 | 2.0 |
| m_mt_838950742 | 1763906400 | COMPETITION | AWAY | OPP_019 |  |  | 4.0 | 4.0 | 1.0 | 3.0 | 4.0 | 4.0 | 18.0 | 21.0 | 3.0 | 3.0 | 51.0 | 62.0 | 16.0 | 18.0 | 2.0 | 1.0 | 7.0 | 12.0 | 1.58 | 1.96 | 2.0 | 4.0 | 52.0 | 48.0 | 0.0 | 0.0 | 3.0 | 2.0 | 8.0 | 9.0 | 7.0 | 5.0 | 3.0 | 5.0 | 6.0 | 5.0 | 20.0 | 26.0 | 15.0 | 11.0 | 14.0 | 14.0 | 23.0 | 24.0 | 1.58 | 1.79 | 1.0 | 5.0 |
| m_mt_585124983 | 1764511500 | COMPETITION | HOME | OPP_016 |  |  | 5.0 | 5.0 | 0.0 | 1.0 | 4.0 | 3.0 | 26.0 | 28.0 | 7.0 | 3.0 | 65.0 | 51.0 | 13.0 | 21.0 | 1.0 | 0.0 | 4.0 | 6.0 | 0.94 | 0.37 | 0.0 | 2.0 | 52.0 | 48.0 | 0.0 | 0.0 | 4.0 | 5.0 | 9.0 | 7.0 | 6.0 | 2.0 | 6.0 | 4.0 | 7.0 | 2.0 | 16.0 | 22.0 | 13.0 | 10.0 | 16.0 | 9.0 | 28.0 | 20.0 | 0.94 | 0.49 | 0.0 | 4.0 |
| m_mt_747395600 | 1764790200 | COMPETITION | AWAY | OPP_010 |  |  | 4.0 | 4.0 | 6.0 | 3.0 | 2.0 | 3.0 | 25.0 | 16.0 | 6.0 | 5.0 | 37.0 | 54.0 | 9.0 | 10.0 | 4.0 | 3.0 | 8.0 | 9.0 | 2.62 | 2.21 | 1.0 | 4.0 | 44.0 | 56.0 | 0.0 | 0.0 | 4.0 | 6.0 | 12.0 | 12.0 | 2.0 | 6.0 | 10.0 | 7.0 | 2.0 | 4.0 | 23.0 | 23.0 | 16.0 | 11.0 | 14.0 | 16.0 | 25.0 | 29.0 | 2.41 | 2.21 | 2.0 | 2.0 |
| m_mt_626439685 | 1765024200 | COMPETITION | HOME | OPP_002 |  |  | 1.0 | 4.0 | 5.0 | 4.0 | 7.0 | 1.0 | 23.0 | 24.0 | 3.0 | 3.0 | 53.0 | 59.0 | 10.0 | 8.0 | 2.0 | 1.0 | 6.0 | 11.0 | 2.28 | 1.92 | 0.0 | 3.0 | 47.0 | 53.0 | 0.0 | 0.0 | 7.0 | 4.0 | 13.0 | 9.0 | 2.0 | 5.0 | 6.0 | 9.0 | 2.0 | 6.0 | 15.0 | 20.0 | 17.0 | 16.0 | 15.0 | 15.0 | 43.0 | 33.0 | 2.16 | 1.92 | 0.0 | 2.0 |
| m_mt_191506177 | 1765720800 | COMPETITION | AWAY | OPP_015 |  |  | 3.0 | 0.0 | 1.0 | 2.0 | 1.0 | 3.0 | 13.0 | 14.0 | 3.0 | 5.0 | 41.0 | 56.0 | 13.0 | 18.0 | 3.0 | 2.0 | 6.0 | 9.0 | 0.73 | 1.13 | 1.0 | 1.0 | 59.0 | 41.0 | 0.0 | 0.0 | 1.0 | 2.0 | 4.0 | 7.0 | 2.0 | 4.0 | 4.0 | 3.0 | 3.0 | 3.0 | 22.0 | 17.0 | 12.0 | 18.0 | 7.0 | 10.0 | 12.0 | 19.0 | 0.67 | 1.03 | 2.0 | 1.0 |
| m_mt_626439604 | 1766334600 | COMPETITION | HOME | OPP_020 |  |  | 1.0 | 4.0 | 2.0 | 3.0 | 5.0 | 3.0 | 22.0 | 21.0 | 5.0 | 5.0 | 27.0 | 49.0 | 4.0 | 2.0 | 2.0 | 1.0 | 7.0 | 9.0 | 1.51 | 1.32 | 3.0 | 1.0 | 43.0 | 57.0 | 0.0 | 0.0 | 5.0 | 2.0 | 8.0 | 5.0 | 3.0 | 6.0 | 4.0 | 6.0 | 4.0 | 10.0 | 18.0 | 26.0 | 8.0 | 19.0 | 12.0 | 15.0 | 20.0 | 34.0 | 1.54 | 1.33 | 1.0 | 2.0 |
| m_mt_191507434 | 1766856600 | COMPETITION | AWAY | OPP_006 | BACK_FOUR | BACK_FOUR | 1.0 | 4.0 | 5.0 | 2.0 | 2.0 | 7.0 | 28.0 | 6.0 | 7.0 | 6.0 | 25.0 | 58.0 | 8.0 | 16.0 | 2.0 | 1.0 | 4.0 | 9.0 | 1.25 | 2.15 |  |  | 37.0 | 63.0 | 0.0 | 0.0 | 2.0 | 6.0 | 7.0 | 8.0 | 1.0 | 4.0 | 8.0 | 3.0 | 4.0 | 6.0 | 8.0 | 26.0 | 13.0 | 6.0 | 11.0 | 14.0 | 19.0 | 42.0 | 1.19 | 2.14 | 3.0 | 5.0 |
| m_mt_010249713 | 1767125700 | COMPETITION | AWAY | OPP_002 |  |  | 1.0 | 5.0 | 5.0 | 6.0 | 4.0 | 7.0 | 17.0 | 17.0 | 3.0 | 3.0 | 23.0 | 51.0 | 9.0 | 18.0 | 1.0 | 4.0 | 3.0 | 8.0 | 3.39 | 3.04 | 0.0 | 4.0 | 54.0 | 46.0 | 0.0 | 0.0 | 3.0 | 2.0 | 9.0 | 17.0 | 4.0 | 8.0 | 3.0 | 7.0 | 2.0 | 5.0 | 10.0 | 17.0 | 17.0 | 8.0 | 11.0 | 22.0 | 21.0 | 38.0 | 2.67 | 3.04 | 3.0 | 2.0 |
| m_mt_626435898 | 1767443400 | COMPETITION | HOME | OPP_011 |  |  | 2.0 | 0.0 | 2.0 | 2.0 | 4.0 | 2.0 | 12.0 | 28.0 | 4.0 | 4.0 | 65.0 | 18.0 | 10.0 | 20.0 | 3.0 | 1.0 | 11.0 | 14.0 | 1.69 | 0.89 | 1.0 | 4.0 | 73.0 | 27.0 | 0.0 | 0.0 | 4.0 | 1.0 | 5.0 | 6.0 | 3.0 | 3.0 | 4.0 | 5.0 | 6.0 | 4.0 | 18.0 | 19.0 | 17.0 | 8.0 | 11.0 | 10.0 | 46.0 | 13.0 | 1.59 | 0.89 | 1.0 | 2.0 |
| m_mt_838950677 | 1767814200 | COMPETITION | AWAY | OPP_014 |  |  | 4.0 | 3.0 | 3.0 | 3.0 | 5.0 | 4.0 | 21.0 | 31.0 | 5.0 | 3.0 | 49.0 | 46.0 | 3.0 | 8.0 | 0.0 | 0.0 | 9.0 | 4.0 | 1.74 | 1.51 | 0.0 | 2.0 | 59.0 | 41.0 | 0.0 | 0.0 | 5.0 | 4.0 | 11.0 | 9.0 | 7.0 | 2.0 | 3.0 | 5.0 | 4.0 | 2.0 | 14.0 | 20.0 | 18.0 | 17.0 | 15.0 | 11.0 | 37.0 | 21.0 | 1.74 | 1.5 | 0.0 | 2.0 |
| m_mt_010243904 | 1768753800 | COMPETITION | HOME | OPP_013 |  |  | 4.0 | 2.0 | 0.0 | 1.0 | 6.0 | 4.0 | 16.0 | 28.0 | 6.0 | 4.0 | 50.0 | 44.0 | 15.0 | 13.0 | 0.0 | 1.0 | 5.0 | 13.0 | 1.34 | 0.52 | 1.0 | 4.0 | 64.0 | 36.0 | 0.0 | 0.0 | 2.0 | 5.0 | 12.0 | 5.0 | 7.0 | 2.0 | 5.0 | 3.0 | 6.0 | 4.0 | 14.0 | 18.0 | 20.0 | 12.0 | 18.0 | 9.0 | 30.0 | 16.0 | 1.36 | 0.56 | 1.0 | 2.0 |
| m_mt_747395655 | 1769349600 | COMPETITION | AWAY | OPP_018 |  |  | 5.0 | 6.0 | 2.0 | 3.0 | 2.0 | 7.0 | 29.0 | 22.0 | 5.0 | 6.0 | 57.0 | 80.0 | 12.0 | 7.0 | 2.0 | 0.0 | 7.0 | 5.0 | 1.16 | 2.3 | 0.0 | 2.0 | 40.0 | 60.0 | 0.0 | 0.0 | 4.0 | 6.0 | 7.0 | 9.0 | 4.0 | 4.0 | 8.0 | 4.0 | 7.0 | 6.0 | 22.0 | 25.0 | 12.0 | 14.0 | 14.0 | 15.0 | 27.0 | 24.0 | 1.16 | 2.3 | 2.0 | 1.0 |
| m_mt_404678210 | 1769954400 | COMPETITION | HOME | OPP_007 |  |  | 8.0 | 1.0 | 3.0 | 0.0 | 11.0 | 1.0 | 19.0 | 35.0 | 12.0 | 1.0 | 42.0 | 53.0 | 8.0 | 8.0 | 0.0 | 1.0 | 3.0 | 14.0 | 2.0 | 0.53 | 1.0 | 6.0 | 72.0 | 28.0 | 0.0 | 1.0 | 0.0 | 5.0 | 17.0 | 5.0 | 11.0 | 4.0 | 5.0 | 2.0 | 10.0 | 1.0 | 18.0 | 7.0 | 16.0 | 18.0 | 27.0 | 6.0 | 75.0 | 12.0 | 1.98 | 0.53 | 1.0 | 3.0 |
| m_mt_404678498 | 1770476400 | COMPETITION | AWAY | OPP_017 |  |  | 4.0 | 3.0 | 1.0 | 2.0 | 3.0 | 4.0 | 37.0 | 20.0 | 4.0 | 11.0 | 51.0 | 65.0 | 11.0 | 4.0 | 1.0 | 1.0 | 7.0 | 10.0 | 0.45 | 2.33 | 3.0 | 3.0 | 47.0 | 53.0 | 0.0 | 0.0 | 7.0 | 3.0 | 5.0 | 12.0 | 0.0 | 7.0 | 4.0 | 9.0 | 2.0 | 8.0 | 18.0 | 10.0 | 17.0 | 21.0 | 7.0 | 20.0 | 20.0 | 26.0 | 0.44 | 2.31 | 1.0 | 1.0 |
| m_mt_626439652 | 1770838200 | COMPETITION | HOME | OPP_010 | BACK_FOUR | BACK_FOUR | 5.0 | 5.0 |  |  | 4.0 | 1.0 | 22.0 | 13.0 | 7.0 | 5.0 | 50.0 | 57.0 | 9.0 | 15.0 | 1.0 | 0.0 | 7.0 | 13.0 | 0.73 | 0.66 | 0.0 | 3.0 | 50.0 | 50.0 | 0.0 | 0.0 | 3.0 | 2.0 | 10.0 | 7.0 | 10.0 | 5.0 | 1.0 | 3.0 | 5.0 | 2.0 | 11.0 | 16.0 | 12.0 | 23.0 | 15.0 | 9.0 | 31.0 | 24.0 | 0.72 | 0.5 | 2.0 | 3.0 |
| m_mt_404678420 | 1771686000 | COMPETITION | HOME | OPP_019 |  |  | 7.0 | 5.0 | 1.0 | 2.0 | 5.0 | 4.0 | 20.0 | 40.0 | 7.0 | 2.0 | 65.0 | 36.0 | 11.0 | 16.0 | 1.0 | 1.0 | 7.0 | 10.0 | 1.39 | 1.25 | 4.0 | 5.0 | 67.0 | 33.0 | 0.0 | 0.0 | 3.0 | 3.0 | 6.0 | 8.0 | 7.0 | 6.0 | 4.0 | 4.0 | 10.0 | 6.0 | 14.0 | 22.0 | 23.0 | 16.0 | 16.0 | 14.0 | 29.0 | 20.0 | 1.39 | 1.35 | 1.0 | 4.0 |
| m_mt_747399497 | 1772222400 | COMPETITION | AWAY | OPP_016 |  |  | 7.0 | 2.0 | 2.0 | 3.0 | 6.0 | 3.0 | 15.0 | 26.0 | 5.0 | 0.0 | 53.0 | 38.0 | 19.0 | 12.0 | 0.0 | 2.0 | 8.0 | 11.0 | 1.06 | 0.92 | 0.0 | 1.0 | 61.0 | 39.0 | 0.0 | 0.0 | 0.0 | 4.0 | 10.0 | 6.0 | 3.0 | 4.0 | 5.0 | 2.0 | 4.0 | 3.0 | 10.0 | 16.0 | 15.0 | 15.0 | 14.0 | 9.0 | 24.0 | 11.0 | 1.06 | 0.92 | 3.0 | 3.0 |
| m_mt_626433295 | 1772652600 | COMPETITION | HOME | OPP_006 |  |  | 1.0 | 3.0 | 2.0 | 5.0 | 1.0 | 4.0 | 14.0 | 15.0 | 3.0 | 8.0 | 41.0 | 37.0 | 10.0 | 9.0 | 1.0 | 4.0 | 7.0 | 8.0 | 0.88 | 3.92 | 2.0 | 2.0 | 43.0 | 57.0 | 0.0 | 0.0 | 4.0 | 3.0 | 6.0 | 14.0 | 4.0 | 3.0 | 4.0 | 8.0 | 3.0 | 1.0 | 11.0 | 15.0 | 16.0 | 20.0 | 9.0 | 15.0 | 17.0 | 35.0 | 0.88 | 3.92 | 3.0 | 2.0 |

### Arm B — derived summaries (DERIVED_SUMMARY), HOME 240 + AWAY 240

HOME_TEAM (metric·side·window·venue = value [n, reliability]):

- accurate_crosses·FOR·ALL_PRIOR·ALL = 4.8333 [n=30, HIGH]
- accurate_crosses·FOR·W5·ALL = 5.0 [n=5, LOW]
- accurate_crosses·FOR·W10·ALL = 4.7 [n=10, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·HOME = 5.8 [n=15, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·AWAY = 3.8667 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·ALL = 3.8 [n=30, HIGH]
- accurate_crosses·AGAINST·W5·ALL = 3.4 [n=5, LOW]
- accurate_crosses·AGAINST·W10·ALL = 3.4 [n=10, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·HOME = 3.1333 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·AWAY = 4.4667 [n=15, MEDIUM]
- big_chances·FOR·ALL_PRIOR·ALL = 2.8333 [n=30, HIGH]
- big_chances·FOR·W5·ALL = 2.4 [n=5, LOW]
- big_chances·FOR·W10·ALL = 3.0 [n=10, MEDIUM]
- big_chances·FOR·ALL_PRIOR·HOME = 2.8 [n=15, MEDIUM]
- big_chances·FOR·ALL_PRIOR·AWAY = 2.8667 [n=15, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·ALL = 1.8 [n=30, HIGH]
- big_chances·AGAINST·W5·ALL = 1.0 [n=5, LOW]
- big_chances·AGAINST·W10·ALL = 0.9 [n=10, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·HOME = 1.3333 [n=15, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·AWAY = 2.2667 [n=15, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·ALL = 4.1333 [n=30, HIGH]
- blocked_shots·FOR·W5·ALL = 4.0 [n=5, LOW]
- blocked_shots·FOR·W10·ALL = 3.8 [n=10, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·HOME = 4.5333 [n=15, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·AWAY = 3.7333 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·ALL = 3.2667 [n=30, HIGH]
- blocked_shots·AGAINST·W5·ALL = 3.4 [n=5, LOW]
- blocked_shots·AGAINST·W10·ALL = 3.8 [n=10, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·HOME = 3.0 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·AWAY = 3.5333 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·ALL = 23.2333 [n=30, HIGH]
- clearances·FOR·W5·ALL = 13.8 [n=5, LOW]
- clearances·FOR·W10·ALL = 20.1 [n=10, MEDIUM]
- clearances·FOR·ALL_PRIOR·HOME = 22.6667 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·AWAY = 23.8 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·ALL = 25.7333 [n=30, HIGH]
- clearances·AGAINST·W5·ALL = 24.4 [n=5, LOW]
- clearances·AGAINST·W10·ALL = 21.8 [n=10, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·HOME = 27.0667 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·AWAY = 24.4 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·ALL = 4.3667 [n=30, HIGH]
- corners·FOR·W5·ALL = 4.2 [n=5, LOW]
- corners·FOR·W10·ALL = 3.7 [n=10, MEDIUM]
- corners·FOR·ALL_PRIOR·HOME = 4.6667 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·AWAY = 4.0667 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·ALL = 4.5667 [n=30, HIGH]
- corners·AGAINST·W5·ALL = 2.4 [n=5, LOW]
- corners·AGAINST·W10·ALL = 4.2 [n=10, MEDIUM]
- corners·AGAINST·ALL_PRIOR·HOME = 4.1333 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·AWAY = 5.0 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·ALL = 57.1333 [n=30, HIGH]
- final_third_entries·FOR·W5·ALL = 59.8 [n=5, LOW]
- final_third_entries·FOR·W10·ALL = 60.9 [n=10, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·HOME = 57.2667 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·AWAY = 57.0 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·ALL = 51.1333 [n=30, HIGH]
- final_third_entries·AGAINST·W5·ALL = 44.6 [n=5, LOW]
- final_third_entries·AGAINST·W10·ALL = 48.6 [n=10, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·HOME = 50.9333 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·AWAY = 51.3333 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·ALL = 9.4483 [n=29, HIGH]
- fouls·FOR·W5·ALL = 10.2 [n=5, LOW]
- fouls·FOR·W10·ALL = 9.6 [n=10, MEDIUM]
- fouls·FOR·ALL_PRIOR·HOME = 10.5333 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·AWAY = 8.2857 [n=14, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·ALL = 11.1724 [n=29, HIGH]
- fouls·AGAINST·W5·ALL = 11.6 [n=5, LOW]
- fouls·AGAINST·W10·ALL = 10.4 [n=10, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·HOME = 10.9333 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·AWAY = 11.4286 [n=14, MEDIUM]
- goals·FOR·ALL_PRIOR·ALL = 1.7667 [n=30, HIGH]
- goals·FOR·W5·ALL = 1.4 [n=5, LOW]
- goals·FOR·W10·ALL = 1.8 [n=10, MEDIUM]
- goals·FOR·ALL_PRIOR·HOME = 1.9333 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·AWAY = 1.6 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·ALL = 1.3333 [n=30, HIGH]
- goals·AGAINST·W5·ALL = 0.8 [n=5, LOW]
- goals·AGAINST·W10·ALL = 1.1 [n=10, MEDIUM]
- goals·AGAINST·ALL_PRIOR·HOME = 1.0667 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·AWAY = 1.6 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·ALL = 7.5667 [n=30, HIGH]
- interceptions·FOR·W5·ALL = 6.8 [n=5, LOW]
- interceptions·FOR·W10·ALL = 7.4 [n=10, MEDIUM]
- interceptions·FOR·ALL_PRIOR·HOME = 7.4667 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·AWAY = 7.6667 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·ALL = 9.4 [n=30, HIGH]
- interceptions·AGAINST·W5·ALL = 9.8 [n=5, LOW]
- interceptions·AGAINST·W10·ALL = 10.6 [n=10, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·HOME = 9.3333 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·AWAY = 9.4667 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·ALL = 1.6403 [n=30, HIGH]
- npxg·FOR·W5·ALL = 1.262 [n=5, LOW]
- npxg·FOR·W10·ALL = 1.543 [n=10, MEDIUM]
- npxg·FOR·ALL_PRIOR·HOME = 1.8447 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·AWAY = 1.436 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·ALL = 1.1313 [n=30, HIGH]
- npxg·AGAINST·W5·ALL = 0.804 [n=5, LOW]
- npxg·AGAINST·W10·ALL = 0.806 [n=10, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·HOME = 0.8793 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·AWAY = 1.3833 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·ALL = 1.7586 [n=29, HIGH]
- offsides·FOR·W5·ALL = 1.75 [n=4, LOW]
- offsides·FOR·W10·ALL = 1.8889 [n=9, MEDIUM]
- offsides·FOR·ALL_PRIOR·HOME = 2.0667 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·AWAY = 1.4286 [n=14, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·ALL = 1.8276 [n=29, HIGH]
- offsides·AGAINST·W5·ALL = 1.25 [n=4, LOW]
- offsides·AGAINST·W10·ALL = 1.6667 [n=9, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·HOME = 1.6667 [n=15, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·AWAY = 2.0 [n=14, MEDIUM]
- possession·FOR·ALL_PRIOR·ALL = 54.0667 [n=30, HIGH]
- possession·FOR·W5·ALL = 60.6 [n=5, LOW]
- possession·FOR·W10·ALL = 54.0 [n=10, MEDIUM]
- possession·FOR·ALL_PRIOR·HOME = 53.8 [n=15, MEDIUM]
- possession·FOR·ALL_PRIOR·AWAY = 54.3333 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·ALL = 45.9333 [n=30, HIGH]
- possession·AGAINST·W5·ALL = 39.4 [n=5, LOW]
- possession·AGAINST·W10·ALL = 46.0 [n=10, MEDIUM]
- possession·AGAINST·ALL_PRIOR·HOME = 46.2 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·AWAY = 45.6667 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·ALL = 0.0333 [n=30, HIGH]
- red_cards·FOR·W5·ALL = 0.0 [n=5, LOW]
- red_cards·FOR·W10·ALL = 0.0 [n=10, MEDIUM]
- red_cards·FOR·ALL_PRIOR·HOME = 0.0667 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·AWAY = 0.0 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·ALL = 0.2 [n=30, HIGH]
- red_cards·AGAINST·W5·ALL = 0.6 [n=5, LOW]
- red_cards·AGAINST·W10·ALL = 0.3 [n=10, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·HOME = 0.3333 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·AWAY = 0.0667 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·ALL = 2.1667 [n=30, HIGH]
- saves·FOR·W5·ALL = 2.0 [n=5, LOW]
- saves·FOR·W10·ALL = 2.0 [n=10, MEDIUM]
- saves·FOR·ALL_PRIOR·HOME = 2.0 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·AWAY = 2.3333 [n=15, MEDIUM]
- saves·AGAINST·ALL_PRIOR·ALL = 3.9667 [n=30, HIGH]
- saves·AGAINST·W5·ALL = 4.6 [n=5, LOW]
- saves·AGAINST·W10·ALL = 3.8 [n=10, MEDIUM]
- saves·AGAINST·ALL_PRIOR·HOME = 5.1333 [n=15, MEDIUM]
- saves·AGAINST·ALL_PRIOR·AWAY = 2.8 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·ALL = 10.5333 [n=30, HIGH]
- shots_inside_box·FOR·W5·ALL = 8.6 [n=5, LOW]
- shots_inside_box·FOR·W10·ALL = 9.8 [n=10, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·HOME = 12.0667 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·AWAY = 9.0 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·ALL = 7.3667 [n=30, HIGH]
- shots_inside_box·AGAINST·W5·ALL = 4.8 [n=5, LOW]
- shots_inside_box·AGAINST·W10·ALL = 6.0 [n=10, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·HOME = 6.5333 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·AWAY = 8.2 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·ALL = 6.2333 [n=30, HIGH]
- shots_off_target·FOR·W5·ALL = 5.0 [n=5, LOW]
- shots_off_target·FOR·W10·ALL = 5.9 [n=10, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·HOME = 6.6 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·AWAY = 5.8667 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·ALL = 3.8333 [n=30, HIGH]
- shots_off_target·AGAINST·W5·ALL = 2.2 [n=5, LOW]
- shots_off_target·AGAINST·W10·ALL = 2.9 [n=10, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·HOME = 3.3333 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·AWAY = 4.3333 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·ALL = 5.8667 [n=30, HIGH]
- shots_on_target·FOR·W5·ALL = 6.4 [n=5, LOW]
- shots_on_target·FOR·W10·ALL = 6.0 [n=10, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·HOME = 6.9333 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·AWAY = 4.8 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·ALL = 3.5 [n=30, HIGH]
- shots_on_target·AGAINST·W5·ALL = 2.8 [n=5, LOW]
- shots_on_target·AGAINST·W10·ALL = 2.9 [n=10, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·HOME = 3.1333 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·AWAY = 3.8667 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·ALL = 5.6667 [n=30, HIGH]
- shots_outside_box·FOR·W5·ALL = 6.8 [n=5, LOW]
- shots_outside_box·FOR·W10·ALL = 5.8 [n=10, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·HOME = 5.9333 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·AWAY = 5.4 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·ALL = 3.2333 [n=30, HIGH]
- shots_outside_box·AGAINST·W5·ALL = 3.6 [n=5, LOW]
- shots_outside_box·AGAINST·W10·ALL = 3.6 [n=10, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·HOME = 2.9333 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·AWAY = 3.5333 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·ALL = 17.9667 [n=30, HIGH]
- tackles·FOR·W5·ALL = 13.4 [n=5, LOW]
- tackles·FOR·W10·ALL = 17.1 [n=10, MEDIUM]
- tackles·FOR·ALL_PRIOR·HOME = 18.8 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·AWAY = 17.1333 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·ALL = 16.0333 [n=30, HIGH]
- tackles·AGAINST·W5·ALL = 16.6 [n=5, LOW]
- tackles·AGAINST·W10·ALL = 15.8 [n=10, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·HOME = 15.6667 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·AWAY = 16.4 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·ALL = 18.4 [n=30, HIGH]
- throw_ins·FOR·W5·ALL = 17.0 [n=5, LOW]
- throw_ins·FOR·W10·ALL = 15.7 [n=10, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·HOME = 18.4 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·AWAY = 18.4 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·ALL = 16.9333 [n=30, HIGH]
- throw_ins·AGAINST·W5·ALL = 14.2 [n=5, LOW]
- throw_ins·AGAINST·W10·ALL = 15.7 [n=10, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·HOME = 15.2667 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·AWAY = 18.6 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·ALL = 16.2 [n=30, HIGH]
- total_shots·FOR·W5·ALL = 15.4 [n=5, LOW]
- total_shots·FOR·W10·ALL = 15.6 [n=10, MEDIUM]
- total_shots·FOR·ALL_PRIOR·HOME = 18.0 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·AWAY = 14.4 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·ALL = 10.6 [n=30, HIGH]
- total_shots·AGAINST·W5·ALL = 8.4 [n=5, LOW]
- total_shots·AGAINST·W10·ALL = 9.6 [n=10, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·HOME = 9.4667 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·AWAY = 11.7333 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·ALL = 28.4 [n=30, HIGH]
- touches_in_box·FOR·W5·ALL = 26.8 [n=5, LOW]
- touches_in_box·FOR·W10·ALL = 25.5 [n=10, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·HOME = 33.0 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·AWAY = 23.8 [n=15, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·ALL = 22.5 [n=30, HIGH]
- touches_in_box·AGAINST·W5·ALL = 14.4 [n=5, LOW]
- touches_in_box·AGAINST·W10·ALL = 19.4 [n=10, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·HOME = 21.5333 [n=15, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·AWAY = 23.4667 [n=15, MEDIUM]
- xg·FOR·ALL_PRIOR·ALL = 1.751 [n=30, HIGH]
- xg·FOR·W5·ALL = 1.332 [n=5, LOW]
- xg·FOR·W10·ALL = 1.553 [n=10, MEDIUM]
- xg·FOR·ALL_PRIOR·HOME = 1.9907 [n=15, MEDIUM]
- xg·FOR·ALL_PRIOR·AWAY = 1.5113 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·ALL = 1.183 [n=30, HIGH]
- xg·AGAINST·W5·ALL = 0.892 [n=5, LOW]
- xg·AGAINST·W10·ALL = 0.922 [n=10, MEDIUM]
- xg·AGAINST·ALL_PRIOR·HOME = 0.9153 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·AWAY = 1.4507 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·ALL = 1.5 [n=28, HIGH]
- yellow_cards·FOR·W5·ALL = 1.75 [n=4, LOW]
- yellow_cards·FOR·W10·ALL = 1.3333 [n=9, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·HOME = 1.6 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·AWAY = 1.3846 [n=13, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·ALL = 2.25 [n=28, HIGH]
- yellow_cards·AGAINST·W5·ALL = 2.25 [n=4, LOW]
- yellow_cards·AGAINST·W10·ALL = 1.8889 [n=9, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·HOME = 2.5333 [n=15, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·AWAY = 1.9231 [n=13, MEDIUM]

AWAY_TEAM:

- accurate_crosses·FOR·ALL_PRIOR·ALL = 3.4 [n=30, HIGH]
- accurate_crosses·FOR·W5·ALL = 4.8 [n=5, LOW]
- accurate_crosses·FOR·W10·ALL = 4.7 [n=10, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·HOME = 3.8667 [n=15, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·AWAY = 2.9333 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·ALL = 3.8 [n=30, HIGH]
- accurate_crosses·AGAINST·W5·ALL = 3.6 [n=5, LOW]
- accurate_crosses·AGAINST·W10·ALL = 3.0 [n=10, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·HOME = 3.7333 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·AWAY = 3.8667 [n=15, MEDIUM]
- big_chances·FOR·ALL_PRIOR·ALL = 1.8966 [n=29, HIGH]
- big_chances·FOR·W5·ALL = 1.5 [n=4, LOW]
- big_chances·FOR·W10·ALL = 1.7778 [n=9, MEDIUM]
- big_chances·FOR·ALL_PRIOR·HOME = 1.9286 [n=14, MEDIUM]
- big_chances·FOR·ALL_PRIOR·AWAY = 1.8667 [n=15, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·ALL = 2.5172 [n=29, HIGH]
- big_chances·AGAINST·W5·ALL = 3.0 [n=4, LOW]
- big_chances·AGAINST·W10·ALL = 2.3333 [n=9, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·HOME = 2.1429 [n=14, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·AWAY = 2.8667 [n=15, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·ALL = 3.9333 [n=30, HIGH]
- blocked_shots·FOR·W5·ALL = 3.8 [n=5, LOW]
- blocked_shots·FOR·W10·ALL = 4.7 [n=10, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·HOME = 4.2667 [n=15, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·AWAY = 3.6 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·ALL = 3.8667 [n=30, HIGH]
- blocked_shots·AGAINST·W5·ALL = 3.2 [n=5, LOW]
- blocked_shots·AGAINST·W10·ALL = 3.4 [n=10, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·HOME = 3.2667 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·AWAY = 4.4667 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·ALL = 21.2667 [n=30, HIGH]
- clearances·FOR·W5·ALL = 21.6 [n=5, LOW]
- clearances·FOR·W10·ALL = 20.5 [n=10, MEDIUM]
- clearances·FOR·ALL_PRIOR·HOME = 20.0667 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·AWAY = 22.4667 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·ALL = 23.9 [n=30, HIGH]
- clearances·AGAINST·W5·ALL = 22.8 [n=5, LOW]
- clearances·AGAINST·W10·ALL = 25.8 [n=10, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·HOME = 24.8667 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·AWAY = 22.9333 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·ALL = 5.2333 [n=30, HIGH]
- corners·FOR·W5·ALL = 5.2 [n=5, LOW]
- corners·FOR·W10·ALL = 5.8 [n=10, MEDIUM]
- corners·FOR·ALL_PRIOR·HOME = 5.7333 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·AWAY = 4.7333 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·ALL = 4.6667 [n=30, HIGH]
- corners·AGAINST·W5·ALL = 5.2 [n=5, LOW]
- corners·AGAINST·W10·ALL = 4.4 [n=10, MEDIUM]
- corners·AGAINST·ALL_PRIOR·HOME = 4.6 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·AWAY = 4.7333 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·ALL = 49.1 [n=30, HIGH]
- final_third_entries·FOR·W5·ALL = 52.0 [n=5, LOW]
- final_third_entries·FOR·W10·ALL = 52.3 [n=10, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·HOME = 51.2 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·AWAY = 47.0 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·ALL = 51.3667 [n=30, HIGH]
- final_third_entries·AGAINST·W5·ALL = 46.6 [n=5, LOW]
- final_third_entries·AGAINST·W10·ALL = 47.4 [n=10, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·HOME = 48.0667 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·AWAY = 54.6667 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·ALL = 10.1667 [n=30, HIGH]
- fouls·FOR·W5·ALL = 12.0 [n=5, LOW]
- fouls·FOR·W10·ALL = 10.8 [n=10, MEDIUM]
- fouls·FOR·ALL_PRIOR·HOME = 9.6667 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·AWAY = 10.6667 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·ALL = 12.9333 [n=30, HIGH]
- fouls·AGAINST·W5·ALL = 11.2 [n=5, LOW]
- fouls·AGAINST·W10·ALL = 11.2 [n=10, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·HOME = 13.4 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·AWAY = 12.4667 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·ALL = 1.3 [n=30, HIGH]
- goals·FOR·W5·ALL = 0.8 [n=5, LOW]
- goals·FOR·W10·ALL = 0.9 [n=10, MEDIUM]
- goals·FOR·ALL_PRIOR·HOME = 1.4 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·AWAY = 1.2 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·ALL = 1.2 [n=30, HIGH]
- goals·AGAINST·W5·ALL = 1.6 [n=5, LOW]
- goals·AGAINST·W10·ALL = 1.1 [n=10, MEDIUM]
- goals·AGAINST·ALL_PRIOR·HOME = 1.0 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·AWAY = 1.4 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·ALL = 6.1 [n=30, HIGH]
- interceptions·FOR·W5·ALL = 7.2 [n=5, LOW]
- interceptions·FOR·W10·ALL = 7.1 [n=10, MEDIUM]
- interceptions·FOR·ALL_PRIOR·HOME = 6.5333 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·AWAY = 5.6667 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·ALL = 9.4 [n=30, HIGH]
- interceptions·AGAINST·W5·ALL = 10.4 [n=5, LOW]
- interceptions·AGAINST·W10·ALL = 10.2 [n=10, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·HOME = 10.9333 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·AWAY = 7.8667 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·ALL = 1.2147 [n=30, HIGH]
- npxg·FOR·W5·ALL = 0.902 [n=5, LOW]
- npxg·FOR·W10·ALL = 1.244 [n=10, MEDIUM]
- npxg·FOR·ALL_PRIOR·HOME = 1.2593 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·AWAY = 1.17 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·ALL = 1.484 [n=30, HIGH]
- npxg·AGAINST·W5·ALL = 1.816 [n=5, LOW]
- npxg·AGAINST·W10·ALL = 1.483 [n=10, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·HOME = 1.21 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·AWAY = 1.758 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·ALL = 1.2414 [n=29, HIGH]
- offsides·FOR·W5·ALL = 1.8 [n=5, LOW]
- offsides·FOR·W10·ALL = 1.2 [n=10, MEDIUM]
- offsides·FOR·ALL_PRIOR·HOME = 1.3333 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·AWAY = 1.1429 [n=14, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·ALL = 3.1034 [n=29, HIGH]
- offsides·AGAINST·W5·ALL = 2.8 [n=5, LOW]
- offsides·AGAINST·W10·ALL = 3.2 [n=10, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·HOME = 3.1333 [n=15, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·AWAY = 3.0714 [n=14, MEDIUM]
- possession·FOR·ALL_PRIOR·ALL = 53.0 [n=30, HIGH]
- possession·FOR·W5·ALL = 53.6 [n=5, LOW]
- possession·FOR·W10·ALL = 57.6 [n=10, MEDIUM]
- possession·FOR·ALL_PRIOR·HOME = 54.0667 [n=15, MEDIUM]
- possession·FOR·ALL_PRIOR·AWAY = 51.9333 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·ALL = 47.0 [n=30, HIGH]
- possession·AGAINST·W5·ALL = 46.4 [n=5, LOW]
- possession·AGAINST·W10·ALL = 42.4 [n=10, MEDIUM]
- possession·AGAINST·ALL_PRIOR·HOME = 45.9333 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·AWAY = 48.0667 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·ALL = 0.0667 [n=30, HIGH]
- red_cards·FOR·W5·ALL = 0.0 [n=5, LOW]
- red_cards·FOR·W10·ALL = 0.0 [n=10, MEDIUM]
- red_cards·FOR·ALL_PRIOR·HOME = 0.0667 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·AWAY = 0.0667 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·ALL = 0.0667 [n=30, HIGH]
- red_cards·AGAINST·W5·ALL = 0.0 [n=5, LOW]
- red_cards·AGAINST·W10·ALL = 0.1 [n=10, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·HOME = 0.0667 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·AWAY = 0.0667 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·ALL = 3.1 [n=30, HIGH]
- saves·FOR·W5·ALL = 3.4 [n=5, LOW]
- saves·FOR·W10·ALL = 3.2 [n=10, MEDIUM]
- saves·FOR·ALL_PRIOR·HOME = 3.0667 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·AWAY = 3.1333 [n=15, MEDIUM]
- saves·AGAINST·ALL_PRIOR·ALL = 3.0667 [n=30, HIGH]
- saves·AGAINST·W5·ALL = 3.0 [n=5, LOW]
- saves·AGAINST·W10·ALL = 3.6 [n=10, MEDIUM]
- saves·AGAINST·ALL_PRIOR·HOME = 3.2667 [n=15, MEDIUM]
- saves·AGAINST·ALL_PRIOR·AWAY = 2.8667 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·ALL = 7.9 [n=30, HIGH]
- shots_inside_box·FOR·W5·ALL = 7.4 [n=5, LOW]
- shots_inside_box·FOR·W10·ALL = 8.9 [n=10, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·HOME = 8.8667 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·AWAY = 6.9333 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·ALL = 8.6667 [n=30, HIGH]
- shots_inside_box·AGAINST·W5·ALL = 9.4 [n=5, LOW]
- shots_inside_box·AGAINST·W10·ALL = 8.1 [n=10, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·HOME = 7.4667 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·AWAY = 9.8667 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·ALL = 4.2 [n=30, HIGH]
- shots_off_target·FOR·W5·ALL = 4.8 [n=5, LOW]
- shots_off_target·FOR·W10·ALL = 5.6 [n=10, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·HOME = 4.8 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·AWAY = 3.6 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·ALL = 4.8333 [n=30, HIGH]
- shots_off_target·AGAINST·W5·ALL = 5.0 [n=5, LOW]
- shots_off_target·AGAINST·W10·ALL = 4.0 [n=10, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·HOME = 3.8667 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·AWAY = 5.8 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·ALL = 4.2333 [n=30, HIGH]
- shots_on_target·FOR·W5·ALL = 3.6 [n=5, LOW]
- shots_on_target·FOR·W10·ALL = 4.3 [n=10, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·HOME = 4.5333 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·AWAY = 3.9333 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·ALL = 4.4667 [n=30, HIGH]
- shots_on_target·AGAINST·W5·ALL = 5.2 [n=5, LOW]
- shots_on_target·AGAINST·W10·ALL = 4.5 [n=10, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·HOME = 4.2667 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·AWAY = 4.6667 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·ALL = 4.4667 [n=30, HIGH]
- shots_outside_box·FOR·W5·ALL = 4.8 [n=5, LOW]
- shots_outside_box·FOR·W10·ALL = 5.7 [n=10, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·HOME = 4.7333 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·AWAY = 4.2 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·ALL = 4.4667 [n=30, HIGH]
- shots_outside_box·AGAINST·W5·ALL = 4.0 [n=5, LOW]
- shots_outside_box·AGAINST·W10·ALL = 3.7 [n=10, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·HOME = 3.8667 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·AWAY = 5.0667 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·ALL = 15.0667 [n=30, HIGH]
- tackles·FOR·W5·ALL = 12.8 [n=5, LOW]
- tackles·FOR·W10·ALL = 15.0 [n=10, MEDIUM]
- tackles·FOR·ALL_PRIOR·HOME = 14.6667 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·AWAY = 15.4667 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·ALL = 19.4333 [n=30, HIGH]
- tackles·AGAINST·W5·ALL = 15.8 [n=5, LOW]
- tackles·AGAINST·W10·ALL = 16.8 [n=10, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·HOME = 18.2667 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·AWAY = 20.6 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·ALL = 15.3 [n=30, HIGH]
- throw_ins·FOR·W5·ALL = 16.6 [n=5, LOW]
- throw_ins·FOR·W10·ALL = 16.6 [n=10, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·HOME = 15.2 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·AWAY = 15.4 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·ALL = 15.0667 [n=30, HIGH]
- throw_ins·AGAINST·W5·ALL = 19.0 [n=5, LOW]
- throw_ins·AGAINST·W10·ALL = 16.4 [n=10, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·HOME = 15.4 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·AWAY = 14.7333 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·ALL = 12.3667 [n=30, HIGH]
- total_shots·FOR·W5·ALL = 12.2 [n=5, LOW]
- total_shots·FOR·W10·ALL = 14.6 [n=10, MEDIUM]
- total_shots·FOR·ALL_PRIOR·HOME = 13.6 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·AWAY = 11.1333 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·ALL = 13.1333 [n=30, HIGH]
- total_shots·AGAINST·W5·ALL = 13.4 [n=5, LOW]
- total_shots·AGAINST·W10·ALL = 11.8 [n=10, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·HOME = 11.3333 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·AWAY = 14.9333 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·ALL = 26.2333 [n=30, HIGH]
- touches_in_box·FOR·W5·ALL = 24.2 [n=5, LOW]
- touches_in_box·FOR·W10·ALL = 33.6 [n=10, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·HOME = 29.8 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·AWAY = 22.6667 [n=15, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·ALL = 25.3333 [n=30, HIGH]
- touches_in_box·AGAINST·W5·ALL = 23.2 [n=5, LOW]
- touches_in_box·AGAINST·W10·ALL = 20.2 [n=10, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·HOME = 22.5333 [n=15, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·AWAY = 28.1333 [n=15, MEDIUM]
- xg·FOR·ALL_PRIOR·ALL = 1.1757 [n=30, HIGH]
- xg·FOR·W5·ALL = 0.898 [n=5, LOW]
- xg·FOR·W10·ALL = 1.232 [n=10, MEDIUM]
- xg·FOR·ALL_PRIOR·HOME = 1.2453 [n=15, MEDIUM]
- xg·FOR·ALL_PRIOR·AWAY = 1.106 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·ALL = 1.54 [n=30, HIGH]
- xg·AGAINST·W5·ALL = 1.8 [n=5, LOW]
- xg·AGAINST·W10·ALL = 1.478 [n=10, MEDIUM]
- xg·AGAINST·ALL_PRIOR·HOME = 1.312 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·AWAY = 1.768 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·ALL = 1.6 [n=30, HIGH]
- yellow_cards·FOR·W5·ALL = 2.0 [n=5, LOW]
- yellow_cards·FOR·W10·ALL = 1.5 [n=10, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·HOME = 1.3333 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·AWAY = 1.8667 [n=15, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·ALL = 2.4333 [n=30, HIGH]
- yellow_cards·AGAINST·W5·ALL = 2.6 [n=5, LOW]
- yellow_cards·AGAINST·W10·ALL = 2.3 [n=10, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·HOME = 2.6 [n=15, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·AWAY = 2.2667 [n=15, MEDIUM]

### Arm B — opponent-profile context (deterministic bands)

```json
{
 "axes": {
  "accurate_crosses_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "corners_against": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "corners_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "goals_against": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "goals_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "possession_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "shots_on_target_against": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "shots_on_target_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  }
 },
 "similarity_version": "opponent_similarity_v1_pending"
}
```

---

## mt_010441320

- PIT-safe matches available: **128**; match rows included (both teams): **60**; omitted: **68** (reason: `frozen_history_policy(max_matches_per_team=30)`); UNEXPLAINED_OMISSION: **0**.
- Metric cell exposure rate (non-null of serialized): **0.9979**; derived summaries: **480**.
- Availability map: `{"expected_formation": "UNAVAILABLE", "formation": "LOW_COVERAGE", "half_time_state": "UNAVAILABLE", "injuries": "UNAVAILABLE", "lineup": "PIT_UNSAFE", "opponent_profile": "AVAILABLE", "recent_vs_long": "AVAILABLE", "red_cards": "AVAILABLE", "temporal_event_state": "UNAVAILABLE", "venue": "AVAILABLE", "xg": "AVAILABLE"}`
- Arm A packet hash: `0eec1200e7c2c9c3b87702263d7639d0b5f817d2c7771ebc4cc15d6f059c590a`
- Arm B packet hash: `85a33b51ecf4151c317588cfeecf60376d6b7f99b8ab6b3213e40e5375ff8194`

### Arm A — frozen V3 compressed evidence (all items)

76 unconditional shrunk scalar items (venue=ALL, window=ALL_PRIOR):

| id | metric | value | n | reliability |
|---|---|---|---|---|
| HOME_ATK_corners_406027 | corners_for | 4.8814 | 64 | HIGH |
| HOME_DEF_corners_7cfac3 | corners_against | 4.5385 | 64 | HIGH |
| HOME_ATK_accurate_crosses_c28b9e | accurate_crosses_for | 3.7918 | 64 | HIGH |
| HOME_DEF_accurate_crosses_81ffb5 | accurate_crosses_against | 3.8489 | 64 | HIGH |
| HOME_ATK_total_shots_808ac9 | total_shots_for | 11.9975 | 64 | HIGH |
| HOME_DEF_total_shots_c0e347 | total_shots_against | 10.9689 | 64 | HIGH |
| HOME_ATK_shots_on_target_e955e0 | shots_on_target_for | 4.0138 | 64 | HIGH |
| HOME_DEF_shots_on_target_8a3812 | shots_on_target_against | 4.1709 | 64 | HIGH |
| HOME_ATK_shots_off_target_11e91f | shots_off_target_for | 4.8857 | 64 | HIGH |
| HOME_DEF_shots_off_target_26031c | shots_off_target_against | 4.2 | 64 | HIGH |
| HOME_ATK_blocked_shots_5198f8 | blocked_shots_for | 3.0982 | 64 | HIGH |
| HOME_DEF_blocked_shots_09c3c4 | blocked_shots_against | 2.5982 | 64 | HIGH |
| HOME_ATK_shots_inside_box_cf538d | shots_inside_box_for | 7.4582 | 64 | HIGH |
| HOME_DEF_shots_inside_box_e6b28d | shots_inside_box_against | 7.401 | 64 | HIGH |
| HOME_ATK_touches_in_box_759ed8 | touches_in_box_for | 20.025 | 64 | HIGH |
| HOME_DEF_touches_in_box_94cd98 | touches_in_box_against | 20.1679 | 64 | HIGH |
| HOME_ATK_final_third_entries_5aa0be | final_third_entries_for | 53.345 | 64 | HIGH |
| HOME_DEF_final_third_entries_4a40ef | final_third_entries_against | 53.1879 | 64 | HIGH |
| HOME_ATK_possession_190f3f | possession_for | 51.8429 | 64 | HIGH |
| HOME_DEF_possession_f8ada9 | possession_against | 48.1571 | 64 | HIGH |
| HOME_ATK_tackles_65b6c1 | tackles_for | 17.1772 | 64 | HIGH |
| HOME_DEF_tackles_e3c85e | tackles_against | 16.8486 | 64 | HIGH |
| HOME_ATK_fouls_8107c6 | fouls_for | 13.6958 | 64 | HIGH |
| HOME_DEF_fouls_b6d53c | fouls_against | 12.2386 | 64 | HIGH |
| HOME_ATK_yellow_cards_80b7a4 | yellow_cards_for | 2.6801 | 64 | HIGH |
| HOME_DEF_yellow_cards_8ee8aa | yellow_cards_against | 2.3229 | 64 | HIGH |
| HOME_ATK_clearances_ec2e18 | clearances_for | 24.1229 | 64 | HIGH |
| HOME_DEF_clearances_6d3f4c | clearances_against | 23.0229 | 64 | HIGH |
| HOME_ATK_interceptions_967965 | interceptions_for | 8.9619 | 64 | HIGH |
| HOME_DEF_interceptions_c82020 | interceptions_against | 7.5619 | 64 | HIGH |
| HOME_ATK_goals_08b15b | goals_for | 1.1987 | 64 | HIGH |
| HOME_DEF_goals_d53fdd | goals_against | 1.4844 | 64 | HIGH |
| HOME_ATK_throw_ins_b24629 | throw_ins_for | 19.9477 | 64 | HIGH |
| HOME_DEF_throw_ins_208262 | throw_ins_against | 21.1477 | 64 | HIGH |
| HOME_ATK_big_chances_8a9e2f | big_chances_for | 1.7161 | 63 | HIGH |
| HOME_DEF_big_chances_885151 | big_chances_against | 2.3972 | 63 | HIGH |
| HOME_ATK_saves_6bda8d | saves_for | 2.6739 | 64 | HIGH |
| HOME_DEF_saves_19ae14 | saves_against | 2.8168 | 64 | HIGH |
| AWAY_ATK_corners_ca1538 | corners_for | 5.5099 | 64 | HIGH |
| AWAY_DEF_corners_598e33 | corners_against | 4.9814 | 64 | HIGH |
| AWAY_ATK_accurate_crosses_005290 | accurate_crosses_for | 4.3346 | 64 | HIGH |
| AWAY_DEF_accurate_crosses_287e9c | accurate_crosses_against | 4.1489 | 64 | HIGH |
| AWAY_ATK_total_shots_004f7a | total_shots_for | 13.4261 | 64 | HIGH |
| AWAY_DEF_total_shots_403d28 | total_shots_against | 12.1118 | 64 | HIGH |
| AWAY_ATK_shots_on_target_9afd02 | shots_on_target_for | 4.4709 | 64 | HIGH |
| AWAY_DEF_shots_on_target_dcda5e | shots_on_target_against | 4.0995 | 64 | HIGH |
| AWAY_ATK_shots_off_target_b83815 | shots_off_target_for | 5.6 | 64 | HIGH |
| AWAY_DEF_shots_off_target_5fe2d0 | shots_off_target_against | 4.6285 | 64 | HIGH |
| AWAY_ATK_blocked_shots_93d965 | blocked_shots_for | 3.3553 | 64 | HIGH |
| AWAY_DEF_blocked_shots_97ef03 | blocked_shots_against | 3.3839 | 64 | HIGH |
| AWAY_ATK_shots_inside_box_567ee5 | shots_inside_box_for | 7.6725 | 64 | HIGH |
| AWAY_DEF_shots_inside_box_446c80 | shots_inside_box_against | 7.9153 | 64 | HIGH |
| AWAY_ATK_touches_in_box_2c76ca | touches_in_box_for | 19.9536 | 64 | HIGH |
| AWAY_DEF_touches_in_box_319da5 | touches_in_box_against | 22.7393 | 64 | HIGH |
| AWAY_ATK_final_third_entries_5a0987 | final_third_entries_for | 56.345 | 64 | HIGH |
| AWAY_DEF_final_third_entries_ed75cd | final_third_entries_against | 55.2307 | 64 | HIGH |
| AWAY_ATK_possession_82105a | possession_for | 52.2571 | 64 | HIGH |
| AWAY_DEF_possession_012ecc | possession_against | 47.7429 | 64 | HIGH |
| AWAY_ATK_tackles_0865bc | tackles_for | 16.8629 | 64 | HIGH |
| AWAY_DEF_tackles_3e6a7d | tackles_against | 15.7772 | 64 | HIGH |
| AWAY_ATK_fouls_97bf91 | fouls_for | 13.358 | 63 | HIGH |
| AWAY_DEF_fouls_94f7aa | fouls_against | 11.2276 | 63 | HIGH |
| AWAY_ATK_yellow_cards_120c77 | yellow_cards_for | 2.5885 | 63 | HIGH |
| AWAY_DEF_yellow_cards_367397 | yellow_cards_against | 2.1247 | 63 | HIGH |
| AWAY_ATK_clearances_74617f | clearances_for | 24.18 | 64 | HIGH |
| AWAY_DEF_clearances_8bdc80 | clearances_against | 24.7086 | 64 | HIGH |
| AWAY_ATK_interceptions_404e22 | interceptions_for | 8.4333 | 64 | HIGH |
| AWAY_DEF_interceptions_4be11b | interceptions_against | 8.0047 | 64 | HIGH |
| AWAY_ATK_goals_5d2c6a | goals_for | 1.0701 | 64 | HIGH |
| AWAY_DEF_goals_4ad3b7 | goals_against | 1.2129 | 64 | HIGH |
| AWAY_ATK_throw_ins_64d189 | throw_ins_for | 21.4049 | 64 | HIGH |
| AWAY_DEF_throw_ins_35916f | throw_ins_against | 22.2049 | 64 | HIGH |
| AWAY_ATK_big_chances_065222 | big_chances_for | 2.1799 | 63 | HIGH |
| AWAY_DEF_big_chances_d5f920 | big_chances_against | 2.3972 | 63 | HIGH |
| AWAY_ATK_saves_50b33b | saves_for | 2.8431 | 63 | HIGH |
| AWAY_DEF_saves_bf5cbb | saves_against | 3.4373 | 63 | HIGH |

### Arm B — HOME_TEAM match-level matrix (30 rows × 55 cols)

Columns: `match_alias, kickoff_unix, competition, venue, opponent_alias, own_formation_family, opponent_formation_family, accurate_crosses_for, accurate_crosses_against, big_chances_for, big_chances_against, blocked_shots_for, blocked_shots_against, clearances_for, clearances_against, corners_for, corners_against, final_third_entries_for, final_third_entries_against, fouls_for, fouls_against, goals_for, goals_against, interceptions_for, interceptions_against, npxg_for, npxg_against, offsides_for, offsides_against, possession_for, possession_against, red_cards_for, red_cards_against, saves_for, saves_against, shots_inside_box_for, shots_inside_box_against, shots_off_target_for, shots_off_target_against, shots_on_target_for, shots_on_target_against, shots_outside_box_for, shots_outside_box_against, tackles_for, tackles_against, throw_ins_for, throw_ins_against, total_shots_for, total_shots_against, touches_in_box_for, touches_in_box_against, xg_for, xg_against, yellow_cards_for, yellow_cards_against`

| match_alias | kickoff_unix | competition | venue | opponent_alias | own_formation_family | opponent_formation_family | accurate_crosses_for | accurate_crosses_against | big_chances_for | big_chances_against | blocked_shots_for | blocked_shots_against | clearances_for | clearances_against | corners_for | corners_against | final_third_entries_for | final_third_entries_against | fouls_for | fouls_against | goals_for | goals_against | interceptions_for | interceptions_against | npxg_for | npxg_against | offsides_for | offsides_against | possession_for | possession_against | red_cards_for | red_cards_against | saves_for | saves_against | shots_inside_box_for | shots_inside_box_against | shots_off_target_for | shots_off_target_against | shots_on_target_for | shots_on_target_against | shots_outside_box_for | shots_outside_box_against | tackles_for | tackles_against | throw_ins_for | throw_ins_against | total_shots_for | total_shots_against | touches_in_box_for | touches_in_box_against | xg_for | xg_against | yellow_cards_for | yellow_cards_against |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| m_mt_830906287 | 1746886500 | COMPETITION | AWAY | OPP_001 |  |  | 9.0 | 2.0 | 4.0 | 2.0 | 4.0 | 1.0 | 11.0 | 50.0 | 6.0 | 3.0 | 67.0 | 48.0 | 16.0 | 11.0 | 2.0 | 3.0 | 13.0 | 6.0 | 1.53 | 0.88 | 3.0 | 1.0 | 50.0 | 50.0 | 0.0 | 1.0 | 1.0 | 8.0 | 13.0 | 5.0 | 5.0 | 3.0 | 10.0 | 4.0 | 6.0 | 3.0 | 19.0 | 11.0 | 20.0 | 13.0 | 19.0 | 8.0 | 21.0 | 14.0 | 2.31 | 0.71 | 2.0 | 0.0 |
| m_mt_408681904 | 1747164600 | COMPETITION | HOME | OPP_002 | BACK_FOUR | BACK_FOUR | 0.0 | 3.0 | 1.0 | 0.0 | 4.0 | 6.0 | 32.0 | 28.0 | 4.0 | 2.0 | 67.0 | 51.0 | 22.0 | 15.0 | 1.0 | 0.0 | 9.0 | 7.0 | 1.31 | 0.47 | 1.0 | 1.0 | 46.0 | 54.0 | 0.0 | 0.0 | 3.0 | 3.0 | 7.0 | 1.0 | 3.0 | 5.0 | 3.0 | 3.0 | 3.0 | 13.0 | 27.0 | 15.0 | 14.0 | 28.0 | 10.0 | 14.0 | 19.0 | 9.0 | 1.07 | 0.45 | 6.0 | 6.0 |
| m_mt_745350133 | 1747587600 | COMPETITION | HOME | OPP_003 |  |  | 2.0 | 1.0 | 1.0 | 2.0 | 1.0 | 5.0 | 21.0 | 11.0 | 1.0 | 7.0 | 37.0 | 65.0 | 7.0 | 9.0 | 0.0 | 2.0 | 15.0 | 9.0 | 0.51 | 2.02 | 1.0 | 1.0 | 37.0 | 63.0 | 2.0 | 0.0 | 4.0 | 1.0 | 3.0 | 6.0 | 4.0 | 5.0 | 1.0 | 6.0 | 3.0 | 10.0 | 16.0 | 17.0 | 10.0 | 14.0 | 6.0 | 16.0 | 6.0 | 34.0 | 0.51 | 2.02 | 0.0 | 1.0 |
| m_mt_972824013 | 1748182500 | COMPETITION | AWAY | OPP_004 |  |  | 4.0 | 5.0 | 3.0 | 1.0 | 2.0 | 3.0 | 13.0 | 17.0 | 5.0 | 3.0 | 48.0 | 45.0 | 14.0 | 8.0 | 2.0 | 4.0 | 10.0 | 4.0 | 1.51 | 1.05 | 3.0 | 0.0 | 49.0 | 51.0 | 0.0 | 0.0 | 3.0 | 4.0 | 12.0 | 8.0 | 9.0 | 2.0 | 6.0 | 7.0 | 5.0 | 4.0 | 14.0 | 9.0 | 15.0 | 9.0 | 17.0 | 12.0 | 33.0 | 30.0 | 1.51 | 1.06 | 1.0 | 0.0 |
| m_mt_191000453 | 1755451800 | COMPETITION | AWAY | OPP_005 |  |  | 2.0 | 4.0 | 0.0 | 3.0 | 2.0 | 8.0 | 31.0 | 12.0 | 1.0 | 10.0 | 57.0 | 57.0 | 12.0 | 8.0 | 2.0 | 3.0 | 12.0 | 6.0 | 1.01 | 2.1 | 8.0 | 0.0 | 54.0 | 46.0 | 0.0 | 0.0 | 0.0 | 4.0 | 10.0 | 11.0 | 4.0 | 3.0 | 6.0 | 3.0 | 2.0 | 3.0 | 18.0 | 11.0 | 17.0 | 21.0 | 12.0 | 14.0 | 22.0 | 29.0 | 1.01 | 2.89 | 2.0 | 0.0 |
| m_mt_979111880 | 1756150200 | COMPETITION | HOME | OPP_006 | BACK_FOUR | BACK_FIVE | 7.0 | 2.0 | 1.0 | 3.0 | 1.0 | 2.0 | 22.0 | 31.0 | 5.0 | 3.0 | 65.0 | 45.0 | 10.0 | 24.0 | 1.0 | 2.0 | 5.0 | 2.0 | 0.51 | 0.77 | 4.0 | 1.0 | 71.0 | 29.0 | 0.0 | 0.0 | 4.0 | 3.0 | 8.0 | 3.0 | 8.0 | 1.0 | 3.0 | 6.0 | 4.0 | 6.0 | 24.0 | 16.0 | 21.0 | 24.0 | 12.0 | 9.0 | 26.0 | 17.0 | 0.51 | 0.71 | 2.0 | 2.0 |
| m_mt_838555523 | 1756575000 | COMPETITION | AWAY | OPP_007 |  |  | 3.0 | 6.0 | 2.0 | 3.0 | 3.0 | 9.0 | 47.0 | 16.0 | 3.0 | 11.0 | 44.0 | 51.0 | 14.0 | 5.0 | 2.0 | 0.0 | 3.0 | 2.0 | 1.32 | 2.13 | 0.0 | 2.0 | 41.0 | 59.0 | 0.0 | 0.0 | 5.0 | 2.0 | 10.0 | 12.0 | 6.0 | 6.0 | 4.0 | 5.0 | 3.0 | 8.0 | 17.0 | 15.0 | 13.0 | 23.0 | 13.0 | 20.0 | 24.0 | 43.0 | 1.26 | 2.12 | 1.0 | 0.0 |
| m_mt_585222485 | 1757703600 | COMPETITION | HOME | OPP_008 | BACK_THREE | BACK_THREE | 6.0 | 3.0 | 0.0 | 3.0 | 2.0 | 0.0 | 25.0 | 27.0 | 2.0 | 2.0 | 73.0 | 47.0 | 23.0 | 19.0 | 2.0 | 2.0 | 8.0 | 8.0 | 0.4 | 0.96 | 1.0 | 0.0 | 53.0 | 47.0 | 0.0 | 0.0 | 0.0 | 1.0 | 4.0 | 2.0 | 2.0 | 3.0 | 3.0 | 2.0 | 3.0 | 3.0 | 21.0 | 26.0 | 21.0 | 13.0 | 7.0 | 5.0 | 17.0 | 15.0 | 0.38 | 0.95 | 4.0 | 3.0 |
| m_mt_747999535 | 1758385800 | COMPETITION | AWAY | OPP_009 |  |  | 5.0 | 4.0 | 2.0 | 1.0 | 2.0 | 1.0 | 19.0 | 17.0 | 4.0 | 4.0 | 44.0 | 65.0 | 19.0 | 20.0 | 2.0 | 1.0 | 8.0 | 7.0 | 0.48 | 0.17 | 4.0 | 3.0 | 52.0 | 48.0 | 0.0 | 0.0 | 4.0 | 1.0 | 5.0 | 4.0 | 4.0 | 2.0 | 3.0 | 5.0 | 4.0 | 4.0 | 20.0 | 21.0 | 23.0 | 29.0 | 9.0 | 8.0 | 20.0 | 13.0 | 0.48 | 0.95 | 7.0 | 1.0 |
| m_mt_585222936 | 1758655800 | COMPETITION | HOME | OPP_004 |  |  | 9.0 | 1.0 | 1.0 | 6.0 | 8.0 | 3.0 | 22.0 | 28.0 | 3.0 | 3.0 | 57.0 | 51.0 | 17.0 | 14.0 | 1.0 | 2.0 | 10.0 | 10.0 | 0.98 | 1.95 | 0.0 | 3.0 | 65.0 | 35.0 | 0.0 | 0.0 | 3.0 | 1.0 | 10.0 | 11.0 | 6.0 | 4.0 | 2.0 | 5.0 | 6.0 | 1.0 | 23.0 | 18.0 | 24.0 | 20.0 | 16.0 | 12.0 | 33.0 | 26.0 | 0.97 | 1.95 | 2.0 | 3.0 |
| m_mt_010443713 | 1759060800 | COMPETITION | AWAY | OPP_010 |  |  | 0.0 | 6.0 | 1.0 | 2.0 | 2.0 | 5.0 | 35.0 | 20.0 | 4.0 | 12.0 | 46.0 | 67.0 | 15.0 | 11.0 | 1.0 | 0.0 | 8.0 | 6.0 | 0.55 | 1.89 | 1.0 | 0.0 | 36.0 | 64.0 | 0.0 | 1.0 | 6.0 | 0.0 | 2.0 | 13.0 | 1.0 | 7.0 | 1.0 | 6.0 | 2.0 | 5.0 | 15.0 | 14.0 | 21.0 | 25.0 | 4.0 | 18.0 | 15.0 | 26.0 | 0.63 | 1.89 | 2.0 | 3.0 |
| m_mt_191006418 | 1759673700 | COMPETITION | HOME | OPP_011 |  |  | 6.0 | 5.0 | 5.0 | 5.0 | 2.0 | 5.0 | 20.0 | 15.0 | 7.0 | 6.0 | 39.0 | 46.0 | 18.0 | 9.0 | 4.0 | 1.0 | 8.0 | 4.0 | 1.98 | 1.46 | 10.0 | 0.0 | 39.0 | 61.0 | 0.0 | 0.0 | 7.0 | 1.0 | 12.0 | 14.0 | 6.0 | 4.0 | 5.0 | 8.0 | 1.0 | 3.0 | 18.0 | 19.0 | 14.0 | 19.0 | 13.0 | 17.0 | 34.0 | 30.0 | 2.8 | 2.25 | 7.0 | 5.0 |
| m_mt_747995269 | 1760788800 | COMPETITION | HOME | OPP_012 |  |  | 11.0 | 2.0 | 1.0 | 3.0 | 7.0 | 0.0 | 21.0 | 33.0 | 9.0 | 2.0 | 46.0 | 55.0 | 16.0 | 13.0 | 1.0 | 3.0 | 9.0 | 5.0 | 1.26 | 1.85 | 3.0 | 0.0 | 58.0 | 42.0 | 0.0 | 0.0 | 3.0 | 3.0 | 11.0 | 6.0 | 2.0 | 1.0 | 4.0 | 6.0 | 2.0 | 1.0 | 15.0 | 16.0 | 15.0 | 21.0 | 13.0 | 7.0 | 28.0 | 12.0 | 1.26 | 1.85 | 2.0 | 1.0 |
| m_mt_979112699 | 1761332400 | COMPETITION | AWAY | OPP_013 | BACK_FOUR | BACK_FOUR | 2.0 | 4.0 | 0.0 | 3.0 | 2.0 | 0.0 | 19.0 | 28.0 | 9.0 | 1.0 | 66.0 | 48.0 | 14.0 | 19.0 | 1.0 | 2.0 | 8.0 | 12.0 | 0.23 | 0.82 | 1.0 | 2.0 | 60.0 | 40.0 | 0.0 | 0.0 | 1.0 | 0.0 | 2.0 | 4.0 | 3.0 | 2.0 | 1.0 | 3.0 | 4.0 | 1.0 | 13.0 | 22.0 | 27.0 | 18.0 | 6.0 | 5.0 | 16.0 | 19.0 | 0.23 | 1.61 | 3.0 | 1.0 |
| m_mt_010444221 | 1762010100 | COMPETITION | AWAY | OPP_014 |  |  | 4.0 | 4.0 | 0.0 | 6.0 | 1.0 | 3.0 | 29.0 | 10.0 | 4.0 | 9.0 | 41.0 | 49.0 | 12.0 | 9.0 | 0.0 | 3.0 | 4.0 | 10.0 | 0.35 | 2.75 |  |  | 53.0 | 47.0 | 0.0 | 0.0 | 3.0 | 2.0 | 5.0 | 12.0 | 7.0 | 6.0 | 2.0 | 6.0 | 5.0 | 3.0 | 24.0 | 15.0 | 18.0 | 21.0 | 10.0 | 15.0 | 10.0 | 27.0 | 0.46 | 3.53 | 3.0 | 0.0 |
| m_mt_191000573 | 1762614900 | COMPETITION | HOME | OPP_015 |  |  | 3.0 | 4.0 | 3.0 | 1.0 | 4.0 | 5.0 | 26.0 | 23.0 | 5.0 | 6.0 | 51.0 | 49.0 | 21.0 | 13.0 | 1.0 | 0.0 | 5.0 | 8.0 | 0.91 | 0.98 | 6.0 | 0.0 | 47.0 | 53.0 | 0.0 | 0.0 | 3.0 | 3.0 | 6.0 | 6.0 | 2.0 | 1.0 | 4.0 | 3.0 | 4.0 | 3.0 | 24.0 | 19.0 | 23.0 | 22.0 | 10.0 | 9.0 | 20.0 | 19.0 | 1.7 | 1.29 | 5.0 | 3.0 |
| m_mt_404777611 | 1764014400 | COMPETITION | AWAY | OPP_016 |  |  | 6.0 | 3.0 | 1.0 | 2.0 | 8.0 | 1.0 | 17.0 | 27.0 | 13.0 | 4.0 | 52.0 | 63.0 | 7.0 | 18.0 | 1.0 | 2.0 | 2.0 | 7.0 | 1.74 | 1.06 | 1.0 | 0.0 | 67.0 | 33.0 | 0.0 | 0.0 | 3.0 | 5.0 | 16.0 | 7.0 | 8.0 | 2.0 | 6.0 | 5.0 | 6.0 | 1.0 | 17.0 | 20.0 | 20.0 | 29.0 | 22.0 | 8.0 | 41.0 | 18.0 | 1.75 | 1.06 | 1.0 | 4.0 |
| m_mt_363888850 | 1764515700 | COMPETITION | HOME | OPP_017 |  |  | 2.0 | 3.0 | 1.0 | 2.0 | 2.0 | 2.0 | 20.0 | 41.0 | 6.0 | 4.0 | 68.0 | 36.0 | 14.0 | 22.0 | 0.0 | 2.0 | 10.0 | 11.0 | 0.35 | 1.17 | 2.0 | 0.0 | 65.0 | 35.0 | 1.0 | 0.0 | 2.0 | 2.0 | 4.0 | 8.0 | 4.0 | 3.0 | 3.0 | 4.0 | 5.0 | 1.0 | 15.0 | 18.0 | 20.0 | 24.0 | 9.0 | 9.0 | 16.0 | 24.0 | 0.37 | 1.17 | 2.0 | 3.0 |
| m_mt_585222275 | 1765120500 | COMPETITION | AWAY | OPP_018 |  |  | 2.0 | 2.0 | 1.0 | 2.0 | 0.0 | 3.0 | 35.0 | 12.0 | 2.0 | 2.0 | 52.0 | 54.0 | 18.0 | 12.0 | 1.0 | 1.0 | 8.0 | 7.0 | 0.29 | 1.29 | 3.0 | 3.0 | 52.0 | 48.0 | 0.0 | 0.0 | 2.0 | 1.0 | 3.0 | 8.0 | 3.0 | 5.0 | 1.0 | 3.0 | 1.0 | 3.0 | 24.0 | 10.0 | 15.0 | 24.0 | 4.0 | 11.0 | 7.0 | 21.0 | 0.32 | 1.19 | 6.0 | 3.0 |
| m_mt_747999930 | 1765717200 | COMPETITION | HOME | OPP_019 | BACK_FIVE | BACK_FOUR | 4.0 | 3.0 | 3.0 | 1.0 | 4.0 | 0.0 | 26.0 | 16.0 | 5.0 | 3.0 | 43.0 | 51.0 | 11.0 | 12.0 | 4.0 | 0.0 | 7.0 | 11.0 | 1.99 | 0.64 | 3.0 | 1.0 | 56.0 | 44.0 | 0.0 | 1.0 | 1.0 | 3.0 | 11.0 | 3.0 | 2.0 | 3.0 | 7.0 | 1.0 | 2.0 | 1.0 | 14.0 | 14.0 | 24.0 | 23.0 | 13.0 | 4.0 | 25.0 | 13.0 | 2.03 | 0.64 | 1.0 | 2.0 |
| m_mt_404777776 | 1766260800 | COMPETITION | AWAY | OPP_003 | BACK_FIVE | BACK_FOUR | 4.0 | 5.0 | 3.0 | 6.0 | 4.0 | 3.0 | 22.0 | 13.0 | 5.0 | 6.0 | 33.0 | 52.0 | 19.0 | 13.0 | 0.0 | 2.0 | 8.0 | 4.0 | 1.5 | 1.54 | 0.0 | 1.0 | 47.0 | 53.0 | 1.0 | 0.0 | 6.0 | 5.0 | 10.0 | 15.0 | 5.0 | 7.0 | 5.0 | 8.0 | 4.0 | 3.0 | 16.0 | 13.0 | 13.0 | 16.0 | 14.0 | 18.0 | 25.0 | 36.0 | 1.56 | 2.33 | 5.0 | 2.0 |
| m_mt_747999961 | 1767531600 | COMPETITION | HOME | OPP_020 | BACK_THREE | BACK_FOUR | 6.0 | 3.0 | 3.0 | 4.0 | 5.0 | 1.0 | 19.0 | 31.0 | 5.0 | 1.0 | 73.0 | 46.0 | 16.0 | 10.0 | 0.0 | 3.0 | 12.0 | 6.0 | 1.05 | 1.03 | 2.0 | 0.0 | 64.0 | 36.0 | 0.0 | 0.0 | 1.0 | 7.0 | 12.0 | 4.0 | 3.0 | 1.0 | 7.0 | 4.0 | 3.0 | 2.0 | 11.0 | 18.0 | 21.0 | 14.0 | 15.0 | 6.0 | 32.0 | 7.0 | 1.7 | 1.03 | 3.0 | 4.0 |
| m_mt_747999972 | 1768248000 | COMPETITION | HOME | OPP_001 |  |  | 7.0 | 0.0 | 0.0 | 2.0 | 3.0 | 0.0 | 8.0 | 24.0 | 6.0 | 1.0 | 60.0 | 41.0 | 16.0 | 16.0 | 0.0 | 1.0 | 11.0 | 6.0 | 0.16 | 0.88 | 4.0 | 0.0 | 59.0 | 41.0 | 0.0 | 0.0 | 6.0 | 2.0 | 3.0 | 7.0 | 2.0 | 2.0 | 2.0 | 7.0 | 4.0 | 2.0 | 17.0 | 7.0 | 16.0 | 9.0 | 7.0 | 9.0 | 22.0 | 12.0 | 0.27 | 1.63 | 3.0 | 3.0 |
| m_mt_838555024 | 1768852800 | COMPETITION | AWAY | OPP_008 |  |  | 4.0 | 3.0 | 3.0 | 2.0 | 6.0 | 3.0 | 37.0 | 32.0 | 7.0 | 9.0 | 42.0 | 47.0 | 12.0 | 11.0 | 2.0 | 2.0 | 15.0 | 7.0 | 1.85 | 1.62 | 1.0 | 0.0 | 50.0 | 50.0 | 0.0 | 0.0 | 3.0 | 6.0 | 13.0 | 7.0 | 11.0 | 2.0 | 8.0 | 5.0 | 12.0 | 3.0 | 19.0 | 27.0 | 22.0 | 19.0 | 25.0 | 10.0 | 24.0 | 24.0 | 2.82 | 1.62 | 1.0 | 3.0 |
| m_mt_363888723 | 1769275800 | COMPETITION | HOME | OPP_005 |  |  | 4.0 | 7.0 | 2.0 | 3.0 | 1.0 | 5.0 | 50.0 | 21.0 | 5.0 | 5.0 | 55.0 | 66.0 | 16.0 | 12.0 | 2.0 | 1.0 | 11.0 | 12.0 | 1.3 | 1.74 | 1.0 | 0.0 | 50.0 | 50.0 | 0.0 | 0.0 | 3.0 | 5.0 | 8.0 | 8.0 | 2.0 | 7.0 | 7.0 | 3.0 | 2.0 | 7.0 | 20.0 | 19.0 | 20.0 | 31.0 | 10.0 | 15.0 | 21.0 | 37.0 | 2.09 | 1.74 | 2.0 | 1.0 |
| m_mt_363888843 | 1770062400 | COMPETITION | AWAY | OPP_012 |  |  | 1.0 | 6.0 | 2.0 | 3.0 | 8.0 | 2.0 | 18.0 | 47.0 | 8.0 | 4.0 | 61.0 | 51.0 | 8.0 | 16.0 | 1.0 | 4.0 | 5.0 | 19.0 | 0.84 | 1.84 | 5.0 | 1.0 | 67.0 | 33.0 | 0.0 | 0.0 | 2.0 | 4.0 | 8.0 | 10.0 | 2.0 | 2.0 | 5.0 | 7.0 | 7.0 | 1.0 | 16.0 | 15.0 | 23.0 | 20.0 | 15.0 | 11.0 | 26.0 | 20.0 | 0.84 | 2.63 | 1.0 | 1.0 |
| m_mt_404777192 | 1770563700 | COMPETITION | HOME | OPP_007 |  |  | 3.0 | 4.0 | 1.0 | 4.0 | 1.0 | 4.0 | 17.0 | 25.0 | 5.0 | 7.0 | 44.0 | 42.0 | 16.0 | 13.0 | 1.0 | 1.0 | 6.0 | 7.0 | 0.77 | 1.66 | 5.0 | 0.0 | 51.0 | 49.0 | 0.0 | 0.0 | 5.0 | 2.0 | 6.0 | 10.0 | 7.0 | 5.0 | 3.0 | 6.0 | 5.0 | 5.0 | 19.0 | 19.0 | 21.0 | 12.0 | 11.0 | 15.0 | 18.0 | 21.0 | 0.81 | 2.45 | 3.0 | 3.0 |
| m_mt_626333092 | 1771090200 | COMPETITION | HOME | OPP_009 |  |  | 3.0 | 9.0 | 0.0 | 3.0 | 1.0 | 4.0 | 39.0 | 18.0 | 0.0 | 3.0 | 43.0 | 63.0 | 16.0 | 13.0 | 1.0 | 1.0 | 16.0 | 8.0 | 0.27 | 1.06 | 2.0 | 1.0 | 25.0 | 75.0 | 2.0 | 0.0 | 0.0 | 1.0 | 2.0 | 10.0 | 1.0 | 7.0 | 2.0 | 1.0 | 2.0 | 2.0 | 13.0 | 8.0 | 14.0 | 27.0 | 4.0 | 12.0 | 11.0 | 31.0 | 0.27 | 1.06 | 5.0 | 0.0 |
| m_mt_979112081 | 1771765200 | COMPETITION | AWAY | OPP_006 |  |  | 3.0 | 2.0 |  |  | 1.0 | 2.0 | 34.0 | 19.0 | 2.0 | 2.0 | 67.0 | 50.0 | 18.0 | 5.0 | 1.0 | 0.0 | 10.0 | 7.0 | 0.28 | 0.32 | 4.0 | 3.0 | 69.0 | 31.0 | 0.0 | 1.0 | 3.0 | 0.0 | 4.0 | 4.0 | 4.0 | 1.0 | 1.0 | 3.0 | 2.0 | 2.0 | 11.0 | 14.0 | 17.0 | 23.0 | 6.0 | 6.0 | 9.0 | 9.0 | 0.28 | 0.32 | 1.0 | 1.0 |
| m_mt_252665756 | 1772386200 | COMPETITION | AWAY | OPP_017 | BACK_THREE | BACK_FOUR | 2.0 | 2.0 | 1.0 | 2.0 | 5.0 | 4.0 | 13.0 | 24.0 | 3.0 | 4.0 | 48.0 | 38.0 | 15.0 | 12.0 | 2.0 | 2.0 | 9.0 | 8.0 | 0.95 | 1.58 | 2.0 | 0.0 | 55.0 | 45.0 | 0.0 | 0.0 | 0.0 | 3.0 | 8.0 | 7.0 | 3.0 | 3.0 | 6.0 | 2.0 | 6.0 | 2.0 | 17.0 | 19.0 | 21.0 | 13.0 | 14.0 | 9.0 | 20.0 | 13.0 | 0.94 | 1.58 | 3.0 | 3.0 |

### Arm B — AWAY_TEAM match-level matrix (30 rows × 55 cols)

Columns: `match_alias, kickoff_unix, competition, venue, opponent_alias, own_formation_family, opponent_formation_family, accurate_crosses_for, accurate_crosses_against, big_chances_for, big_chances_against, blocked_shots_for, blocked_shots_against, clearances_for, clearances_against, corners_for, corners_against, final_third_entries_for, final_third_entries_against, fouls_for, fouls_against, goals_for, goals_against, interceptions_for, interceptions_against, npxg_for, npxg_against, offsides_for, offsides_against, possession_for, possession_against, red_cards_for, red_cards_against, saves_for, saves_against, shots_inside_box_for, shots_inside_box_against, shots_off_target_for, shots_off_target_against, shots_on_target_for, shots_on_target_against, shots_outside_box_for, shots_outside_box_against, tackles_for, tackles_against, throw_ins_for, throw_ins_against, total_shots_for, total_shots_against, touches_in_box_for, touches_in_box_against, xg_for, xg_against, yellow_cards_for, yellow_cards_against`

| match_alias | kickoff_unix | competition | venue | opponent_alias | own_formation_family | opponent_formation_family | accurate_crosses_for | accurate_crosses_against | big_chances_for | big_chances_against | blocked_shots_for | blocked_shots_against | clearances_for | clearances_against | corners_for | corners_against | final_third_entries_for | final_third_entries_against | fouls_for | fouls_against | goals_for | goals_against | interceptions_for | interceptions_against | npxg_for | npxg_against | offsides_for | offsides_against | possession_for | possession_against | red_cards_for | red_cards_against | saves_for | saves_against | shots_inside_box_for | shots_inside_box_against | shots_off_target_for | shots_off_target_against | shots_on_target_for | shots_on_target_against | shots_outside_box_for | shots_outside_box_against | tackles_for | tackles_against | throw_ins_for | throw_ins_against | total_shots_for | total_shots_against | touches_in_box_for | touches_in_box_against | xg_for | xg_against | yellow_cards_for | yellow_cards_against |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| m_mt_408681598 | 1746817200 | COMPETITION | AWAY | OPP_002 |  |  | 7.0 | 4.0 | 1.0 | 1.0 | 5.0 | 2.0 | 48.0 | 22.0 | 8.0 | 8.0 | 57.0 | 67.0 | 9.0 | 8.0 | 1.0 | 0.0 | 6.0 | 12.0 | 1.24 | 0.69 | 2.0 | 0.0 | 59.0 | 41.0 | 0.0 | 0.0 | 2.0 | 4.0 | 11.0 | 8.0 | 6.0 | 7.0 | 5.0 | 2.0 | 5.0 | 3.0 | 14.0 | 20.0 | 28.0 | 35.0 | 16.0 | 11.0 | 20.0 | 24.0 | 1.24 | 0.68 | 3.0 | 2.0 |
| m_mt_013239720 | 1747328400 | COMPETITION | HOME | OPP_017 |  |  | 10.0 | 1.0 | 2.0 | 1.0 | 6.0 | 3.0 | 19.0 | 25.0 | 10.0 | 7.0 | 58.0 | 37.0 | 8.0 | 18.0 | 2.0 | 2.0 | 12.0 | 5.0 | 1.2 | 0.36 | 3.0 | 0.0 | 53.0 | 47.0 | 0.0 | 0.0 | 1.0 | 4.0 | 6.0 | 4.0 | 8.0 | 4.0 | 6.0 | 3.0 | 14.0 | 6.0 | 16.0 | 14.0 | 16.0 | 16.0 | 20.0 | 10.0 | 27.0 | 12.0 | 1.19 | 1.17 | 1.0 | 3.0 |
| m_mt_584143674 | 1747587600 | COMPETITION | AWAY | OPP_001 |  |  | 3.0 | 7.0 | 3.0 | 4.0 | 1.0 | 13.0 | 16.0 | 15.0 | 2.0 | 9.0 | 44.0 | 58.0 | 17.0 | 10.0 | 2.0 | 1.0 | 9.0 | 1.0 | 1.17 | 1.91 | 3.0 | 2.0 | 38.0 | 62.0 | 0.0 | 0.0 | 5.0 | 0.0 | 3.0 | 16.0 | 4.0 | 4.0 | 2.0 | 7.0 | 4.0 | 8.0 | 11.0 | 20.0 | 23.0 | 25.0 | 7.0 | 24.0 | 7.0 | 36.0 | 1.03 | 2.64 | 3.0 | 2.0 |
| m_mt_830906259 | 1748113200 | COMPETITION | HOME | OPP_012 |  |  | 6.0 | 4.0 | 3.0 | 1.0 | 9.0 | 2.0 | 16.0 | 37.0 | 11.0 | 2.0 | 67.0 | 63.0 | 9.0 | 14.0 | 0.0 | 0.0 | 10.0 | 8.0 | 2.28 | 0.64 | 3.0 | 3.0 | 57.0 | 43.0 | 0.0 | 0.0 | 2.0 | 8.0 | 17.0 | 5.0 | 10.0 | 5.0 | 8.0 | 2.0 | 10.0 | 4.0 | 14.0 | 16.0 | 23.0 | 20.0 | 27.0 | 9.0 | 47.0 | 14.0 | 2.11 | 0.66 | 2.0 | 2.0 |
| m_mt_010444723 | 1755277200 | COMPETITION | AWAY | OPP_007 |  |  | 9.0 | 2.0 | 4.0 | 1.0 | 1.0 | 3.0 | 18.0 | 18.0 | 4.0 | 2.0 | 57.0 | 46.0 | 17.0 | 8.0 | 3.0 | 1.0 | 8.0 | 3.0 | 2.64 | 0.56 | 1.0 | 1.0 | 56.0 | 44.0 | 0.0 | 1.0 | 1.0 | 2.0 | 12.0 | 3.0 | 10.0 | 2.0 | 5.0 | 2.0 | 4.0 | 4.0 | 27.0 | 13.0 | 19.0 | 25.0 | 16.0 | 7.0 | 26.0 | 9.0 | 3.43 | 0.56 | 1.0 | 0.0 |
| m_mt_747999192 | 1756143000 | COMPETITION | AWAY | OPP_005 | BACK_FOUR | BACK_FOUR | 3.0 | 4.0 | 1.0 | 2.0 | 3.0 | 4.0 | 20.0 | 25.0 | 6.0 | 3.0 | 45.0 | 47.0 | 13.0 | 13.0 | 0.0 | 1.0 | 13.0 | 5.0 | 0.29 | 0.72 | 7.0 | 0.0 | 59.0 | 41.0 | 0.0 | 0.0 | 3.0 | 1.0 | 2.0 | 5.0 | 2.0 | 3.0 | 1.0 | 4.0 | 4.0 | 6.0 | 16.0 | 14.0 | 21.0 | 12.0 | 6.0 | 11.0 | 12.0 | 29.0 | 0.29 | 1.51 | 4.0 | 0.0 |
| m_mt_838555590 | 1756668600 | COMPETITION | HOME | OPP_011 |  |  | 4.0 | 4.0 | 5.0 | 4.0 | 3.0 | 3.0 | 12.0 | 24.0 | 9.0 | 4.0 | 72.0 | 45.0 | 16.0 | 8.0 | 1.0 | 1.0 | 8.0 | 8.0 | 1.93 | 1.04 | 7.0 | 2.0 | 43.0 | 57.0 | 0.0 | 0.0 | 2.0 | 5.0 | 9.0 | 8.0 | 3.0 | 6.0 | 6.0 | 3.0 | 3.0 | 4.0 | 17.0 | 18.0 | 18.0 | 15.0 | 12.0 | 12.0 | 13.0 | 23.0 | 1.85 | 1.83 | 4.0 | 1.0 |
| m_mt_585222479 | 1757867400 | COMPETITION | AWAY | OPP_015 |  |  | 7.0 | 2.0 | 0.0 | 2.0 | 6.0 | 1.0 | 18.0 | 32.0 | 6.0 | 3.0 | 83.0 | 36.0 | 7.0 | 13.0 | 0.0 | 2.0 | 8.0 | 9.0 | 1.09 | 1.59 | 1.0 | 0.0 | 64.0 | 36.0 | 0.0 | 0.0 | 4.0 | 6.0 | 12.0 | 6.0 | 7.0 | 1.0 | 6.0 | 7.0 | 7.0 | 3.0 | 13.0 | 9.0 | 20.0 | 18.0 | 19.0 | 9.0 | 33.0 | 13.0 | 1.04 | 1.77 | 2.0 | 3.0 |
| m_mt_979111462 | 1758456000 | COMPETITION | HOME | OPP_001 |  |  | 2.0 | 2.0 | 3.0 | 3.0 | 2.0 | 3.0 | 22.0 | 29.0 | 5.0 | 7.0 | 85.0 | 55.0 | 8.0 | 10.0 | 1.0 | 1.0 | 8.0 | 9.0 | 1.08 | 0.91 | 1.0 | 0.0 | 59.0 | 41.0 | 0.0 | 0.0 | 4.0 | 4.0 | 8.0 | 6.0 | 8.0 | 1.0 | 5.0 | 5.0 | 7.0 | 3.0 | 11.0 | 13.0 | 18.0 | 26.0 | 15.0 | 9.0 | 23.0 | 21.0 | 0.99 | 0.81 | 1.0 | 1.0 |
| m_mt_626333565 | 1758742200 | COMPETITION | AWAY | OPP_014 |  |  | 1.0 | 12.0 | 3.0 | 7.0 | 0.0 | 4.0 | 20.0 | 15.0 | 6.0 | 8.0 | 43.0 | 50.0 | 12.0 | 6.0 | 2.0 | 3.0 | 7.0 | 12.0 | 1.6 | 3.66 | 2.0 | 3.0 | 39.0 | 61.0 | 0.0 | 0.0 | 5.0 | 1.0 | 5.0 | 17.0 | 6.0 | 8.0 | 3.0 | 8.0 | 4.0 | 3.0 | 21.0 | 12.0 | 21.0 | 22.0 | 9.0 | 20.0 | 15.0 | 46.0 | 1.6 | 3.61 | 5.0 | 3.0 |
| m_mt_010443713 | 1759060800 | COMPETITION | HOME | OPP_021 |  |  | 6.0 | 0.0 | 2.0 | 1.0 | 5.0 | 2.0 | 20.0 | 35.0 | 12.0 | 4.0 | 67.0 | 46.0 | 11.0 | 15.0 | 0.0 | 1.0 | 6.0 | 8.0 | 1.89 | 0.55 | 0.0 | 1.0 | 64.0 | 36.0 | 1.0 | 0.0 | 0.0 | 6.0 | 13.0 | 2.0 | 7.0 | 1.0 | 6.0 | 1.0 | 5.0 | 2.0 | 14.0 | 15.0 | 25.0 | 21.0 | 18.0 | 4.0 | 26.0 | 15.0 | 1.89 | 0.63 | 3.0 | 2.0 |
| m_mt_191006394 | 1759681800 | COMPETITION | AWAY | OPP_013 |  |  | 2.0 | 0.0 | 3.0 | 1.0 | 2.0 | 6.0 | 28.0 | 13.0 | 5.0 | 7.0 | 42.0 | 55.0 | 21.0 | 13.0 | 1.0 | 0.0 | 11.0 | 8.0 | 0.8 | 0.82 | 1.0 | 0.0 | 49.0 | 51.0 | 0.0 | 0.0 | 3.0 | 1.0 | 5.0 | 7.0 | 3.0 | 1.0 | 2.0 | 3.0 | 2.0 | 3.0 | 13.0 | 11.0 | 19.0 | 14.0 | 7.0 | 10.0 | 10.0 | 23.0 | 0.8 | 0.79 | 2.0 | 1.0 |
| m_mt_191006365 | 1760891400 | COMPETITION | AWAY | OPP_020 |  |  | 2.0 | 7.0 | 5.0 | 1.0 | 2.0 | 8.0 | 59.0 | 12.0 | 4.0 | 11.0 | 36.0 | 62.0 |  |  | 3.0 | 0.0 | 9.0 | 6.0 | 1.55 | 0.91 | 0.0 | 1.0 | 46.0 | 54.0 | 0.0 | 0.0 | 4.0 | 1.0 | 7.0 | 9.0 | 3.0 | 5.0 | 5.0 | 4.0 | 3.0 | 8.0 | 27.0 | 16.0 | 16.0 | 26.0 | 10.0 | 17.0 | 10.0 | 41.0 | 1.55 | 0.91 | 1.0 | 0.0 |
| m_mt_252667532 | 1761508800 | COMPETITION | HOME | OPP_009 | BACK_FOUR | BACK_FOUR | 7.0 | 4.0 | 2.0 | 1.0 | 2.0 | 7.0 | 30.0 | 24.0 | 7.0 | 5.0 | 44.0 | 48.0 | 13.0 | 11.0 | 1.0 | 0.0 | 8.0 | 1.0 | 1.18 | 0.97 | 2.0 | 0.0 | 54.0 | 46.0 | 0.0 | 0.0 | 2.0 | 4.0 | 8.0 | 6.0 | 8.0 | 3.0 | 5.0 | 2.0 | 7.0 | 6.0 | 18.0 | 27.0 | 22.0 | 19.0 | 15.0 | 12.0 | 26.0 | 20.0 | 1.18 | 0.84 | 1.0 | 3.0 |
| m_mt_404777677 | 1762002000 | COMPETITION | AWAY | OPP_004 |  |  | 2.0 | 1.0 | 1.0 | 3.0 | 3.0 | 3.0 | 10.0 | 30.0 | 5.0 | 3.0 | 52.0 | 40.0 | 11.0 | 7.0 | 0.0 | 4.0 | 7.0 | 10.0 | 0.97 | 3.15 | 0.0 | 1.0 | 53.0 | 47.0 | 0.0 | 0.0 | 3.0 | 3.0 | 7.0 | 11.0 | 7.0 | 6.0 | 3.0 | 7.0 | 6.0 | 5.0 | 17.0 | 10.0 | 11.0 | 16.0 | 13.0 | 16.0 | 21.0 | 36.0 | 1.02 | 3.02 | 1.0 | 1.0 |
| m_mt_979111827 | 1762701300 | COMPETITION | HOME | OPP_003 |  |  | 3.0 | 6.0 | 2.0 | 1.0 | 3.0 | 6.0 | 31.0 | 23.0 | 5.0 | 8.0 | 48.0 | 55.0 | 17.0 | 7.0 | 0.0 | 0.0 | 3.0 | 10.0 | 1.21 | 0.98 | 1.0 | 1.0 | 46.0 | 54.0 | 0.0 | 0.0 | 5.0 | 2.0 | 7.0 | 10.0 | 8.0 | 10.0 | 2.0 | 5.0 | 6.0 | 11.0 | 20.0 | 10.0 | 23.0 | 26.0 | 13.0 | 21.0 | 22.0 | 42.0 | 1.2 | 0.98 | 3.0 | 2.0 |
| m_mt_838555972 | 1763902800 | COMPETITION | AWAY | OPP_019 |  |  | 4.0 | 4.0 | 1.0 | 1.0 | 2.0 | 1.0 | 25.0 | 22.0 | 6.0 | 5.0 | 47.0 | 46.0 | 13.0 | 11.0 | 0.0 | 0.0 | 9.0 | 7.0 | 0.95 | 0.44 | 1.0 | 2.0 | 61.0 | 39.0 | 1.0 | 1.0 | 2.0 | 3.0 | 5.0 | 5.0 | 6.0 | 4.0 | 3.0 | 3.0 | 6.0 | 3.0 | 10.0 | 19.0 | 24.0 | 18.0 | 11.0 | 8.0 | 16.0 | 19.0 | 0.95 | 0.43 | 2.0 | 1.0 |
| m_mt_252666026 | 1764619200 | COMPETITION | HOME | OPP_018 |  |  | 5.0 | 2.0 | 3.0 | 1.0 | 3.0 | 4.0 | 26.0 | 42.0 | 10.0 | 5.0 | 54.0 | 68.0 | 11.0 | 9.0 | 1.0 | 1.0 | 9.0 | 5.0 | 1.33 | 0.71 | 1.0 | 0.0 | 56.0 | 44.0 | 0.0 | 0.0 | 0.0 | 5.0 | 9.0 | 6.0 | 9.0 | 4.0 | 7.0 | 2.0 | 10.0 | 4.0 | 15.0 | 12.0 | 28.0 | 27.0 | 19.0 | 10.0 | 15.0 | 18.0 | 1.3 | 0.71 | 1.0 | 1.0 |
| m_mt_010444470 | 1765128600 | COMPETITION | AWAY | OPP_016 |  |  | 3.0 | 2.0 | 0.0 | 2.0 | 3.0 | 2.0 | 24.0 | 26.0 | 2.0 | 6.0 | 51.0 | 36.0 | 22.0 | 19.0 | 0.0 | 1.0 | 6.0 | 12.0 | 0.25 | 0.54 | 1.0 | 1.0 | 64.0 | 36.0 | 1.0 | 1.0 | 1.0 | 2.0 | 2.0 | 6.0 | 1.0 | 5.0 | 2.0 | 2.0 | 4.0 | 3.0 | 7.0 | 16.0 | 24.0 | 21.0 | 6.0 | 9.0 | 18.0 | 18.0 | 0.25 | 1.33 | 8.0 | 4.0 |
| m_mt_585222216 | 1765828800 | COMPETITION | HOME | OPP_017 |  |  | 6.0 | 3.0 | 3.0 | 1.0 | 7.0 | 3.0 | 17.0 | 44.0 | 8.0 | 3.0 | 60.0 | 50.0 | 10.0 | 7.0 | 0.0 | 0.0 | 3.0 | 13.0 | 1.57 | 0.76 | 4.0 | 0.0 | 59.0 | 41.0 | 0.0 | 0.0 | 6.0 | 7.0 | 9.0 | 5.0 | 9.0 | 4.0 | 7.0 | 6.0 | 14.0 | 8.0 | 17.0 | 12.0 | 19.0 | 33.0 | 23.0 | 13.0 | 17.0 | 14.0 | 1.55 | 0.76 | 4.0 | 1.0 |
| m_mt_585222227 | 1766338200 | COMPETITION | AWAY | OPP_008 |  |  | 2.0 | 8.0 | 1.0 | 7.0 | 4.0 | 3.0 | 15.0 | 18.0 | 5.0 | 4.0 | 47.0 | 65.0 | 11.0 | 15.0 | 0.0 | 4.0 | 8.0 | 6.0 | 0.92 | 2.4 | 4.0 | 1.0 | 53.0 | 47.0 | 0.0 | 0.0 | 2.0 | 8.0 | 8.0 | 16.0 | 6.0 | 9.0 | 8.0 | 6.0 | 10.0 | 2.0 | 12.0 | 13.0 | 14.0 | 17.0 | 18.0 | 18.0 | 20.0 | 24.0 | 0.92 | 2.4 | 3.0 | 2.0 |
| m_mt_404777718 | 1767384000 | COMPETITION | HOME | OPP_006 | BACK_FOUR | BACK_FOUR | 7.0 | 8.0 | 0.0 | 1.0 | 4.0 | 2.0 | 28.0 | 23.0 | 3.0 | 2.0 | 73.0 | 68.0 | 13.0 | 10.0 | 1.0 | 1.0 | 7.0 | 3.0 | 0.89 | 0.74 | 5.0 | 2.0 | 60.0 | 40.0 | 0.0 | 0.0 | 3.0 | 3.0 | 6.0 | 8.0 | 5.0 | 6.0 | 4.0 | 4.0 | 7.0 | 4.0 | 18.0 | 16.0 | 32.0 | 32.0 | 13.0 | 12.0 | 15.0 | 12.0 | 0.89 | 0.77 | 3.0 | 4.0 |
| m_mt_585222254 | 1768136400 | COMPETITION | HOME | OPP_012 |  |  | 5.0 | 8.0 | 2.0 | 2.0 | 2.0 | 2.0 | 26.0 | 28.0 | 6.0 | 5.0 | 62.0 | 49.0 | 14.0 | 14.0 | 2.0 | 1.0 | 7.0 | 6.0 | 1.58 | 0.75 | 2.0 | 1.0 | 53.0 | 47.0 | 1.0 | 0.0 | 1.0 | 3.0 | 9.0 | 7.0 | 7.0 | 5.0 | 5.0 | 2.0 | 5.0 | 2.0 | 20.0 | 11.0 | 21.0 | 21.0 | 14.0 | 9.0 | 18.0 | 10.0 | 2.37 | 0.72 | 1.0 | 5.0 |
| m_mt_626333366 | 1768757400 | COMPETITION | AWAY | OPP_001 |  |  | 3.0 | 0.0 | 1.0 | 3.0 | 7.0 | 3.0 | 17.0 | 31.0 | 7.0 | 5.0 | 63.0 | 50.0 | 14.0 | 7.0 | 0.0 | 3.0 | 10.0 | 6.0 | 1.18 | 1.1 | 1.0 | 4.0 | 51.0 | 49.0 | 1.0 | 0.0 | 4.0 | 3.0 | 9.0 | 6.0 | 4.0 | 1.0 | 3.0 | 7.0 | 5.0 | 5.0 | 14.0 | 15.0 | 18.0 | 16.0 | 14.0 | 11.0 | 21.0 | 20.0 | 1.18 | 1.87 | 3.0 | 4.0 |
| m_mt_626333344 | 1769259600 | COMPETITION | HOME | OPP_015 |  |  | 5.0 | 3.0 | 1.0 | 2.0 | 4.0 | 3.0 | 33.0 | 33.0 | 4.0 | 3.0 | 62.0 | 53.0 | 12.0 | 15.0 | 1.0 | 3.0 | 3.0 | 8.0 | 0.88 | 1.19 | 2.0 | 2.0 | 67.0 | 33.0 | 0.0 | 0.0 | 3.0 | 3.0 | 6.0 | 6.0 | 3.0 | 6.0 | 4.0 | 5.0 | 5.0 | 8.0 | 26.0 | 14.0 | 22.0 | 32.0 | 11.0 | 14.0 | 26.0 | 27.0 | 0.78 | 1.18 | 2.0 | 2.0 |
| m_mt_010444327 | 1769950800 | COMPETITION | AWAY | OPP_003 |  |  | 0.0 | 3.0 | 2.0 | 3.0 | 3.0 | 4.0 | 28.0 | 17.0 | 4.0 | 9.0 | 37.0 | 57.0 | 18.0 | 6.0 | 1.0 | 2.0 | 12.0 | 7.0 | 0.96 | 1.36 | 1.0 | 1.0 | 43.0 | 57.0 | 2.0 | 0.0 | 4.0 | 3.0 | 4.0 | 12.0 | 4.0 | 6.0 | 4.0 | 6.0 | 7.0 | 4.0 | 23.0 | 21.0 | 14.0 | 11.0 | 11.0 | 16.0 | 16.0 | 54.0 | 0.96 | 2.14 | 8.0 | 2.0 |
| m_mt_979111907 | 1771168500 | COMPETITION | HOME | OPP_014 |  |  | 3.0 | 5.0 | 6.0 | 1.0 | 3.0 | 3.0 | 38.0 | 23.0 | 4.0 | 8.0 | 44.0 | 48.0 | 10.0 | 13.0 | 3.0 | 0.0 | 10.0 | 6.0 | 1.68 | 1.17 | 3.0 | 0.0 | 41.0 | 59.0 | 0.0 | 0.0 | 3.0 | 6.0 | 8.0 | 7.0 | 1.0 | 2.0 | 9.0 | 4.0 | 5.0 | 2.0 | 12.0 | 11.0 | 15.0 | 27.0 | 13.0 | 9.0 | 19.0 | 32.0 | 1.56 | 1.1 | 1.0 | 3.0 |
| m_mt_979112078 | 1771686900 | COMPETITION | AWAY | OPP_017 |  |  | 5.0 | 3.0 | 2.0 | 3.0 | 5.0 | 5.0 | 19.0 | 18.0 | 5.0 | 3.0 | 47.0 | 41.0 | 13.0 | 14.0 | 1.0 | 1.0 | 12.0 | 10.0 | 0.83 | 1.84 | 4.0 | 0.0 | 53.0 | 47.0 | 0.0 | 0.0 | 2.0 | 2.0 | 7.0 | 9.0 | 4.0 | 6.0 | 3.0 | 3.0 | 5.0 | 5.0 | 14.0 | 17.0 | 16.0 | 15.0 | 12.0 | 14.0 | 21.0 | 19.0 | 0.83 | 1.83 | 3.0 | 4.0 |
| m_mt_191009695 | 1772283600 | COMPETITION | HOME | OPP_005 | BACK_FOUR | BACK_FOUR | 8.0 | 3.0 | 3.0 | 0.0 | 2.0 | 4.0 | 44.0 | 26.0 | 5.0 | 4.0 | 72.0 | 84.0 | 8.0 | 17.0 | 1.0 | 1.0 | 8.0 | 4.0 | 1.33 | 0.54 | 3.0 | 0.0 | 50.0 | 50.0 | 0.0 | 0.0 | 1.0 | 6.0 | 9.0 | 4.0 | 6.0 | 2.0 | 7.0 | 2.0 | 6.0 | 4.0 | 23.0 | 17.0 | 19.0 | 28.0 | 15.0 | 8.0 | 16.0 | 18.0 | 1.33 | 0.54 | 2.0 | 3.0 |
| m_mt_460091491 | 1772647200 | COMPETITION | HOME | OPP_019 | BACK_FOUR | BACK_FOUR | 2.0 | 3.0 | 4.0 | 2.0 | 6.0 | 4.0 | 12.0 | 20.0 | 12.0 | 2.0 | 43.0 | 48.0 | 10.0 | 10.0 | 3.0 | 0.0 | 9.0 | 10.0 | 1.69 | 1.0 | 1.0 | 1.0 | 52.0 | 48.0 | 0.0 | 0.0 | 2.0 | 4.0 | 12.0 | 5.0 | 6.0 | 2.0 | 7.0 | 2.0 | 7.0 | 3.0 | 26.0 | 16.0 | 15.0 | 18.0 | 19.0 | 8.0 | 36.0 | 13.0 | 2.45 | 0.99 | 0.0 | 2.0 |

### Arm B — derived summaries (DERIVED_SUMMARY), HOME 240 + AWAY 240

HOME_TEAM (metric·side·window·venue = value [n, reliability]):

- accurate_crosses·FOR·ALL_PRIOR·ALL = 4.1333 [n=30, HIGH]
- accurate_crosses·FOR·W5·ALL = 2.4 [n=5, LOW]
- accurate_crosses·FOR·W10·ALL = 3.7 [n=10, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·HOME = 4.8667 [n=15, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·AWAY = 3.4 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·ALL = 3.6 [n=30, HIGH]
- accurate_crosses·AGAINST·W5·ALL = 4.6 [n=5, LOW]
- accurate_crosses·AGAINST·W10·ALL = 4.1 [n=10, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·HOME = 3.3333 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·AWAY = 3.8667 [n=15, MEDIUM]
- big_chances·FOR·ALL_PRIOR·ALL = 1.5862 [n=29, HIGH]
- big_chances·FOR·W5·ALL = 1.0 [n=4, LOW]
- big_chances·FOR·W10·ALL = 1.6667 [n=9, MEDIUM]
- big_chances·FOR·ALL_PRIOR·HOME = 1.5333 [n=15, MEDIUM]
- big_chances·FOR·ALL_PRIOR·AWAY = 1.6429 [n=14, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·ALL = 2.7586 [n=29, HIGH]
- big_chances·AGAINST·W5·ALL = 3.0 [n=4, LOW]
- big_chances·AGAINST·W10·ALL = 3.2222 [n=9, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·HOME = 2.8 [n=15, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·AWAY = 2.7143 [n=14, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·ALL = 3.2 [n=30, HIGH]
- blocked_shots·FOR·W5·ALL = 3.2 [n=5, LOW]
- blocked_shots·FOR·W10·ALL = 3.5 [n=10, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·HOME = 3.0667 [n=15, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·AWAY = 3.3333 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·ALL = 3.0 [n=30, HIGH]
- blocked_shots·AGAINST·W5·ALL = 3.2 [n=5, LOW]
- blocked_shots·AGAINST·W10·ALL = 2.8 [n=10, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·HOME = 2.8 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·AWAY = 3.2 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·ALL = 24.9333 [n=30, HIGH]
- clearances·FOR·W5·ALL = 24.2 [n=5, LOW]
- clearances·FOR·W10·ALL = 25.7 [n=10, MEDIUM]
- clearances·FOR·ALL_PRIOR·HOME = 24.5333 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·AWAY = 25.3333 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·ALL = 23.8667 [n=30, HIGH]
- clearances·AGAINST·W5·ALL = 26.6 [n=5, LOW]
- clearances·AGAINST·W10·ALL = 25.4 [n=10, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·HOME = 24.8 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·AWAY = 22.9333 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·ALL = 4.8 [n=30, HIGH]
- corners·FOR·W5·ALL = 3.6 [n=5, LOW]
- corners·FOR·W10·ALL = 4.6 [n=10, MEDIUM]
- corners·FOR·ALL_PRIOR·HOME = 4.5333 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·AWAY = 5.0667 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·ALL = 4.6333 [n=30, HIGH]
- corners·AGAINST·W5·ALL = 4.0 [n=5, LOW]
- corners·AGAINST·W10·ALL = 4.2 [n=10, MEDIUM]
- corners·AGAINST·ALL_PRIOR·HOME = 3.6667 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·AWAY = 5.6 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·ALL = 52.9667 [n=30, HIGH]
- final_third_entries·FOR·W5·ALL = 52.6 [n=5, LOW]
- final_third_entries·FOR·W10·ALL = 52.6 [n=10, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·HOME = 54.7333 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·AWAY = 51.2 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·ALL = 51.3 [n=30, HIGH]
- final_third_entries·AGAINST·W5·ALL = 48.8 [n=5, LOW]
- final_third_entries·AGAINST·W10·ALL = 49.6 [n=10, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·HOME = 50.2667 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·AWAY = 52.3333 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·ALL = 15.0667 [n=30, HIGH]
- fouls·FOR·W5·ALL = 14.6 [n=5, LOW]
- fouls·FOR·W10·ALL = 15.2 [n=10, MEDIUM]
- fouls·FOR·ALL_PRIOR·HOME = 15.9333 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·AWAY = 14.2 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·ALL = 13.0667 [n=30, HIGH]
- fouls·AGAINST·W5·ALL = 11.8 [n=5, LOW]
- fouls·AGAINST·W10·ALL = 12.1 [n=10, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·HOME = 14.2667 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·AWAY = 11.8667 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·ALL = 1.3 [n=30, HIGH]
- goals·FOR·W5·ALL = 1.2 [n=5, LOW]
- goals·FOR·W10·ALL = 1.0 [n=10, MEDIUM]
- goals·FOR·ALL_PRIOR·HOME = 1.2667 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·AWAY = 1.3333 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·ALL = 1.6667 [n=30, HIGH]
- goals·AGAINST·W5·ALL = 1.6 [n=5, LOW]
- goals·AGAINST·W10·ALL = 1.7 [n=10, MEDIUM]
- goals·AGAINST·ALL_PRIOR·HOME = 1.4 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·AWAY = 1.9333 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·ALL = 8.8333 [n=30, HIGH]
- interceptions·FOR·W5·ALL = 9.2 [n=5, LOW]
- interceptions·FOR·W10·ALL = 10.3 [n=10, MEDIUM]
- interceptions·FOR·ALL_PRIOR·HOME = 9.4667 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·AWAY = 8.2 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·ALL = 7.5333 [n=30, HIGH]
- interceptions·AGAINST·W5·ALL = 9.8 [n=5, LOW]
- interceptions·AGAINST·W10·ALL = 8.4 [n=10, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·HOME = 7.6 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·AWAY = 7.4667 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·ALL = 0.9393 [n=30, HIGH]
- npxg·FOR·W5·ALL = 0.622 [n=5, LOW]
- npxg·FOR·W10·ALL = 0.897 [n=10, MEDIUM]
- npxg·FOR·ALL_PRIOR·HOME = 0.9167 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·AWAY = 0.962 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·ALL = 1.3227 [n=30, HIGH]
- npxg·AGAINST·W5·ALL = 1.292 [n=5, LOW]
- npxg·AGAINST·W10·ALL = 1.327 [n=10, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·HOME = 1.2427 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·AWAY = 1.4027 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·ALL = 2.7931 [n=29, HIGH]
- offsides·FOR·W5·ALL = 3.6 [n=5, LOW]
- offsides·FOR·W10·ALL = 2.6 [n=10, MEDIUM]
- offsides·FOR·ALL_PRIOR·HOME = 3.0 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·AWAY = 2.5714 [n=14, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·ALL = 0.8276 [n=29, HIGH]
- offsides·AGAINST·W5·ALL = 1.0 [n=5, LOW]
- offsides·AGAINST·W10·ALL = 0.6 [n=10, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·HOME = 0.5333 [n=15, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·AWAY = 1.1429 [n=14, MEDIUM]
- possession·FOR·ALL_PRIOR·ALL = 52.9333 [n=30, HIGH]
- possession·FOR·W5·ALL = 53.4 [n=5, LOW]
- possession·FOR·W10·ALL = 53.7 [n=10, MEDIUM]
- possession·FOR·ALL_PRIOR·HOME = 52.4 [n=15, MEDIUM]
- possession·FOR·ALL_PRIOR·AWAY = 53.4667 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·ALL = 47.0667 [n=30, HIGH]
- possession·AGAINST·W5·ALL = 46.6 [n=5, LOW]
- possession·AGAINST·W10·ALL = 46.3 [n=10, MEDIUM]
- possession·AGAINST·ALL_PRIOR·HOME = 47.6 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·AWAY = 46.5333 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·ALL = 0.2 [n=30, HIGH]
- red_cards·FOR·W5·ALL = 0.4 [n=5, LOW]
- red_cards·FOR·W10·ALL = 0.3 [n=10, MEDIUM]
- red_cards·FOR·ALL_PRIOR·HOME = 0.3333 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·AWAY = 0.0667 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·ALL = 0.1333 [n=30, HIGH]
- red_cards·AGAINST·W5·ALL = 0.2 [n=5, LOW]
- red_cards·AGAINST·W10·ALL = 0.1 [n=10, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·HOME = 0.0667 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·AWAY = 0.2 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·ALL = 2.9 [n=30, HIGH]
- saves·FOR·W5·ALL = 2.0 [n=5, LOW]
- saves·FOR·W10·ALL = 2.9 [n=10, MEDIUM]
- saves·FOR·ALL_PRIOR·HOME = 3.0 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·AWAY = 2.8 [n=15, MEDIUM]
- saves·AGAINST·ALL_PRIOR·ALL = 2.7667 [n=30, HIGH]
- saves·AGAINST·W5·ALL = 2.0 [n=5, LOW]
- saves·AGAINST·W10·ALL = 3.5 [n=10, MEDIUM]
- saves·AGAINST·ALL_PRIOR·HOME = 2.5333 [n=15, MEDIUM]
- saves·AGAINST·ALL_PRIOR·AWAY = 3.0 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·ALL = 7.6 [n=30, HIGH]
- shots_inside_box·FOR·W5·ALL = 5.6 [n=5, LOW]
- shots_inside_box·FOR·W10·ALL = 7.4 [n=10, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·HOME = 7.1333 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·AWAY = 8.0667 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·ALL = 7.5333 [n=30, HIGH]
- shots_inside_box·AGAINST·W5·ALL = 8.2 [n=5, LOW]
- shots_inside_box·AGAINST·W10·ALL = 8.2 [n=10, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·HOME = 6.6 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·AWAY = 8.4667 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·ALL = 4.3 [n=30, HIGH]
- shots_off_target·FOR·W5·ALL = 3.4 [n=5, LOW]
- shots_off_target·FOR·W10·ALL = 4.0 [n=10, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·HOME = 3.6 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·AWAY = 5.0 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·ALL = 3.5 [n=30, HIGH]
- shots_off_target·AGAINST·W5·ALL = 3.6 [n=5, LOW]
- shots_off_target·AGAINST·W10·ALL = 3.7 [n=10, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·HOME = 3.4667 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·AWAY = 3.5333 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·ALL = 4.0333 [n=30, HIGH]
- shots_on_target·FOR·W5·ALL = 3.4 [n=5, LOW]
- shots_on_target·FOR·W10·ALL = 4.6 [n=10, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·HOME = 3.7333 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·AWAY = 4.3333 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·ALL = 4.5667 [n=30, HIGH]
- shots_on_target·AGAINST·W5·ALL = 3.8 [n=5, LOW]
- shots_on_target·AGAINST·W10·ALL = 4.6 [n=10, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·HOME = 4.3333 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·AWAY = 4.8 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·ALL = 3.9333 [n=30, HIGH]
- shots_outside_box·FOR·W5·ALL = 4.4 [n=5, LOW]
- shots_outside_box·FOR·W10·ALL = 4.7 [n=10, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·HOME = 3.2667 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·AWAY = 4.6 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·ALL = 3.5333 [n=30, HIGH]
- shots_outside_box·AGAINST·W5·ALL = 2.4 [n=5, LOW]
- shots_outside_box·AGAINST·W10·ALL = 2.9 [n=10, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·HOME = 4.0 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·AWAY = 3.0667 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·ALL = 17.9 [n=30, HIGH]
- tackles·FOR·W5·ALL = 15.2 [n=5, LOW]
- tackles·FOR·W10·ALL = 15.9 [n=10, MEDIUM]
- tackles·FOR·ALL_PRIOR·HOME = 18.4667 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·AWAY = 17.3333 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·ALL = 16.1667 [n=30, HIGH]
- tackles·AGAINST·W5·ALL = 15.0 [n=5, LOW]
- tackles·AGAINST·W10·ALL = 15.9 [n=10, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·HOME = 16.6 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·AWAY = 15.7333 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·ALL = 18.7667 [n=30, HIGH]
- throw_ins·FOR·W5·ALL = 19.2 [n=5, LOW]
- throw_ins·FOR·W10·ALL = 18.8 [n=10, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·HOME = 18.5333 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·AWAY = 19.0 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·ALL = 20.1333 [n=30, HIGH]
- throw_ins·AGAINST·W5·ALL = 19.0 [n=5, LOW]
- throw_ins·AGAINST·W10·ALL = 18.4 [n=10, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·HOME = 20.0667 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·AWAY = 20.2 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·ALL = 11.5333 [n=30, HIGH]
- total_shots·FOR·W5·ALL = 10.0 [n=5, LOW]
- total_shots·FOR·W10·ALL = 12.1 [n=10, MEDIUM]
- total_shots·FOR·ALL_PRIOR·HOME = 10.4 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·AWAY = 12.6667 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·ALL = 11.0667 [n=30, HIGH]
- total_shots·AGAINST·W5·ALL = 10.6 [n=5, LOW]
- total_shots·AGAINST·W10·ALL = 11.1 [n=10, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·HOME = 10.6 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·AWAY = 11.5333 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·ALL = 21.3667 [n=30, HIGH]
- touches_in_box·FOR·W5·ALL = 16.8 [n=5, LOW]
- touches_in_box·FOR·W10·ALL = 20.8 [n=10, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·HOME = 21.8667 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·AWAY = 20.8667 [n=15, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·ALL = 21.6333 [n=30, HIGH]
- touches_in_box·AGAINST·W5·ALL = 18.8 [n=5, LOW]
- touches_in_box·AGAINST·W10·ALL = 21.0 [n=10, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·HOME = 20.4667 [n=15, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·AWAY = 22.8 [n=15, MEDIUM]
- xg·FOR·ALL_PRIOR·ALL = 1.1047 [n=30, HIGH]
- xg·FOR·W5·ALL = 0.628 [n=5, LOW]
- xg·FOR·W10·ALL = 1.158 [n=10, MEDIUM]
- xg·FOR·ALL_PRIOR·HOME = 1.116 [n=15, MEDIUM]
- xg·FOR·ALL_PRIOR·AWAY = 1.0933 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·ALL = 1.556 [n=30, HIGH]
- xg·AGAINST·W5·ALL = 1.608 [n=5, LOW]
- xg·AGAINST·W10·ALL = 1.639 [n=10, MEDIUM]
- xg·AGAINST·ALL_PRIOR·HOME = 1.4127 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·AWAY = 1.6993 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·ALL = 2.8667 [n=30, HIGH]
- yellow_cards·FOR·W5·ALL = 2.6 [n=5, LOW]
- yellow_cards·FOR·W10·ALL = 2.7 [n=10, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·HOME = 3.1333 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·AWAY = 2.6 [n=15, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·ALL = 2.0667 [n=30, HIGH]
- yellow_cards·AGAINST·W5·ALL = 1.6 [n=5, LOW]
- yellow_cards·AGAINST·W10·ALL = 2.1 [n=10, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·HOME = 2.6667 [n=15, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·AWAY = 1.4667 [n=15, MEDIUM]

AWAY_TEAM:

- accurate_crosses·FOR·ALL_PRIOR·ALL = 4.4 [n=30, HIGH]
- accurate_crosses·FOR·W5·ALL = 3.6 [n=5, LOW]
- accurate_crosses·FOR·W10·ALL = 4.0 [n=10, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·HOME = 5.2667 [n=15, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·AWAY = 3.5333 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·ALL = 3.8333 [n=30, HIGH]
- accurate_crosses·AGAINST·W5·ALL = 3.4 [n=5, LOW]
- accurate_crosses·AGAINST·W10·ALL = 4.4 [n=10, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·HOME = 3.7333 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·AWAY = 3.9333 [n=15, MEDIUM]
- big_chances·FOR·ALL_PRIOR·ALL = 2.3 [n=30, HIGH]
- big_chances·FOR·W5·ALL = 3.4 [n=5, LOW]
- big_chances·FOR·W10·ALL = 2.2 [n=10, MEDIUM]
- big_chances·FOR·ALL_PRIOR·HOME = 2.7333 [n=15, MEDIUM]
- big_chances·FOR·ALL_PRIOR·AWAY = 1.8667 [n=15, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·ALL = 2.1 [n=30, HIGH]
- big_chances·AGAINST·W5·ALL = 1.8 [n=5, LOW]
- big_chances·AGAINST·W10·ALL = 2.4 [n=10, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·HOME = 1.4667 [n=15, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·AWAY = 2.7333 [n=15, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·ALL = 3.6 [n=30, HIGH]
- blocked_shots·FOR·W5·ALL = 3.8 [n=5, LOW]
- blocked_shots·FOR·W10·ALL = 4.0 [n=10, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·HOME = 4.0667 [n=15, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·AWAY = 3.1333 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·ALL = 3.7667 [n=30, HIGH]
- blocked_shots·AGAINST·W5·ALL = 4.0 [n=5, LOW]
- blocked_shots·AGAINST·W10·ALL = 3.3 [n=10, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·HOME = 3.4 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·AWAY = 4.1333 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·ALL = 24.6333 [n=30, HIGH]
- clearances·FOR·W5·ALL = 28.2 [n=5, LOW]
- clearances·FOR·W10·ALL = 26.0 [n=10, MEDIUM]
- clearances·FOR·ALL_PRIOR·HOME = 24.9333 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·AWAY = 24.3333 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·ALL = 25.0 [n=30, HIGH]
- clearances·AGAINST·W5·ALL = 20.8 [n=5, LOW]
- clearances·AGAINST·W10·ALL = 23.7 [n=10, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·HOME = 29.0667 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·AWAY = 20.9333 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·ALL = 6.2 [n=30, HIGH]
- corners·FOR·W5·ALL = 6.0 [n=5, LOW]
- corners·FOR·W10·ALL = 5.5 [n=10, MEDIUM]
- corners·FOR·ALL_PRIOR·HOME = 7.4 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·AWAY = 5.0 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·ALL = 5.1667 [n=30, HIGH]
- corners·AGAINST·W5·ALL = 5.2 [n=5, LOW]
- corners·AGAINST·W10·ALL = 4.5 [n=10, MEDIUM]
- corners·AGAINST·ALL_PRIOR·HOME = 4.6 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·AWAY = 5.7333 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·ALL = 55.4 [n=30, HIGH]
- final_third_entries·FOR·W5·ALL = 48.6 [n=5, LOW]
- final_third_entries·FOR·W10·ALL = 55.0 [n=10, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·HOME = 60.7333 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·AWAY = 50.0667 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·ALL = 52.4333 [n=30, HIGH]
- final_third_entries·AGAINST·W5·ALL = 55.6 [n=5, LOW]
- final_third_entries·AGAINST·W10·ALL = 56.3 [n=10, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·HOME = 54.4667 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·AWAY = 50.4 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·ALL = 12.6897 [n=29, HIGH]
- fouls·FOR·W5·ALL = 11.8 [n=5, LOW]
- fouls·FOR·W10·ALL = 12.3 [n=10, MEDIUM]
- fouls·FOR·ALL_PRIOR·HOME = 11.3333 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·AWAY = 14.1429 [n=14, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·ALL = 11.3103 [n=29, HIGH]
- fouls·AGAINST·W5·ALL = 12.0 [n=5, LOW]
- fouls·AGAINST·W10·ALL = 12.1 [n=10, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·HOME = 11.8667 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·AWAY = 10.7143 [n=14, MEDIUM]
- goals·FOR·ALL_PRIOR·ALL = 1.0333 [n=30, HIGH]
- goals·FOR·W5·ALL = 1.8 [n=5, LOW]
- goals·FOR·W10·ALL = 1.3 [n=10, MEDIUM]
- goals·FOR·ALL_PRIOR·HOME = 1.1333 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·AWAY = 0.9333 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·ALL = 1.1667 [n=30, HIGH]
- goals·AGAINST·W5·ALL = 0.8 [n=5, LOW]
- goals·AGAINST·W10·ALL = 1.6 [n=10, MEDIUM]
- goals·AGAINST·ALL_PRIOR·HOME = 0.8 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·AWAY = 1.5333 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·ALL = 8.2 [n=30, HIGH]
- interceptions·FOR·W5·ALL = 10.2 [n=5, LOW]
- interceptions·FOR·W10·ALL = 8.6 [n=10, MEDIUM]
- interceptions·FOR·ALL_PRIOR·HOME = 7.4 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·AWAY = 9.0 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·ALL = 7.2667 [n=30, HIGH]
- interceptions·AGAINST·W5·ALL = 7.4 [n=5, LOW]
- interceptions·AGAINST·W10·ALL = 6.6 [n=10, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·HOME = 6.9333 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·AWAY = 7.6 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·ALL = 1.272 [n=30, HIGH]
- npxg·FOR·W5·ALL = 1.298 [n=5, LOW]
- npxg·FOR·W10·ALL = 1.194 [n=10, MEDIUM]
- npxg·FOR·ALL_PRIOR·HOME = 1.448 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·AWAY = 1.096 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·ALL = 1.1333 [n=30, HIGH]
- npxg·AGAINST·W5·ALL = 1.182 [n=5, LOW]
- npxg·AGAINST·W10·ALL = 1.209 [n=10, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·HOME = 0.8207 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·AWAY = 1.446 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·ALL = 2.2333 [n=30, HIGH]
- offsides·FOR·W5·ALL = 2.4 [n=5, LOW]
- offsides·FOR·W10·ALL = 2.6 [n=10, MEDIUM]
- offsides·FOR·ALL_PRIOR·HOME = 2.5333 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·AWAY = 1.9333 [n=15, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·ALL = 1.0 [n=30, HIGH]
- offsides·AGAINST·W5·ALL = 0.4 [n=5, LOW]
- offsides·AGAINST·W10·ALL = 1.2 [n=10, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·HOME = 0.8667 [n=15, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·AWAY = 1.1333 [n=15, MEDIUM]
- possession·FOR·ALL_PRIOR·ALL = 53.4 [n=30, HIGH]
- possession·FOR·W5·ALL = 47.8 [n=5, LOW]
- possession·FOR·W10·ALL = 52.3 [n=10, MEDIUM]
- possession·FOR·ALL_PRIOR·HOME = 54.2667 [n=15, MEDIUM]
- possession·FOR·ALL_PRIOR·AWAY = 52.5333 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·ALL = 46.6 [n=30, HIGH]
- possession·AGAINST·W5·ALL = 52.2 [n=5, LOW]
- possession·AGAINST·W10·ALL = 47.7 [n=10, MEDIUM]
- possession·AGAINST·ALL_PRIOR·HOME = 45.7333 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·AWAY = 47.4667 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·ALL = 0.2333 [n=30, HIGH]
- red_cards·FOR·W5·ALL = 0.4 [n=5, LOW]
- red_cards·FOR·W10·ALL = 0.4 [n=10, MEDIUM]
- red_cards·FOR·ALL_PRIOR·HOME = 0.1333 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·AWAY = 0.3333 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·ALL = 0.1 [n=30, HIGH]
- red_cards·AGAINST·W5·ALL = 0.0 [n=5, LOW]
- red_cards·AGAINST·W10·ALL = 0.0 [n=10, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·HOME = 0.0 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·AWAY = 0.2 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·ALL = 2.6667 [n=30, HIGH]
- saves·FOR·W5·ALL = 2.4 [n=5, LOW]
- saves·FOR·W10·ALL = 2.5 [n=10, MEDIUM]
- saves·FOR·ALL_PRIOR·HOME = 2.3333 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·AWAY = 3.0 [n=15, MEDIUM]
- saves·AGAINST·ALL_PRIOR·ALL = 3.6667 [n=30, HIGH]
- saves·AGAINST·W5·ALL = 4.2 [n=5, LOW]
- saves·AGAINST·W10·ALL = 4.1 [n=10, MEDIUM]
- saves·AGAINST·ALL_PRIOR·HOME = 4.6667 [n=15, MEDIUM]
- saves·AGAINST·ALL_PRIOR·AWAY = 2.6667 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·ALL = 7.8333 [n=30, HIGH]
- shots_inside_box·FOR·W5·ALL = 8.0 [n=5, LOW]
- shots_inside_box·FOR·W10·ALL = 7.8 [n=10, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·HOME = 9.0667 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·AWAY = 6.6 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·ALL = 7.5 [n=30, HIGH]
- shots_inside_box·AGAINST·W5·ALL = 7.4 [n=5, LOW]
- shots_inside_box·AGAINST·W10·ALL = 8.0 [n=10, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·HOME = 5.9333 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·AWAY = 9.0667 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·ALL = 5.7 [n=30, HIGH]
- shots_off_target·FOR·W5·ALL = 4.2 [n=5, LOW]
- shots_off_target·FOR·W10·ALL = 4.6 [n=10, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·HOME = 6.5333 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·AWAY = 4.8667 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·ALL = 4.3 [n=30, HIGH]
- shots_off_target·AGAINST·W5·ALL = 3.6 [n=5, LOW]
- shots_off_target·AGAINST·W10·ALL = 4.5 [n=10, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·HOME = 4.0667 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·AWAY = 4.5333 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·ALL = 4.7667 [n=30, HIGH]
- shots_on_target·FOR·W5·ALL = 6.0 [n=5, LOW]
- shots_on_target·FOR·W10·ALL = 5.4 [n=10, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·HOME = 5.8667 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·AWAY = 3.6667 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·ALL = 3.9667 [n=30, HIGH]
- shots_on_target·AGAINST·W5·ALL = 3.4 [n=5, LOW]
- shots_on_target·AGAINST·W10·ALL = 4.1 [n=10, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·HOME = 3.2 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·AWAY = 4.7333 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·ALL = 6.2333 [n=30, HIGH]
- shots_outside_box·FOR·W5·ALL = 6.0 [n=5, LOW]
- shots_outside_box·FOR·W10·ALL = 6.2 [n=10, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·HOME = 7.4 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·AWAY = 5.0667 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·ALL = 4.5333 [n=30, HIGH]
- shots_outside_box·AGAINST·W5·ALL = 3.6 [n=5, LOW]
- shots_outside_box·AGAINST·W10·ALL = 3.9 [n=10, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·HOME = 4.7333 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·AWAY = 4.3333 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·ALL = 16.8667 [n=30, HIGH]
- tackles·FOR·W5·ALL = 19.6 [n=5, LOW]
- tackles·FOR·W10·ALL = 18.8 [n=10, MEDIUM]
- tackles·FOR·ALL_PRIOR·HOME = 17.8 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·AWAY = 15.9333 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·ALL = 14.9333 [n=30, HIGH]
- tackles·AGAINST·W5·ALL = 16.4 [n=5, LOW]
- tackles·AGAINST·W10·ALL = 15.1 [n=10, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·HOME = 14.8 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·AWAY = 15.0667 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·ALL = 20.1333 [n=30, HIGH]
- throw_ins·FOR·W5·ALL = 15.8 [n=5, LOW]
- throw_ins·FOR·W10·ALL = 18.6 [n=10, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·HOME = 21.0667 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·AWAY = 19.2 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·ALL = 21.7333 [n=30, HIGH]
- throw_ins·AGAINST·W5·ALL = 19.8 [n=5, LOW]
- throw_ins·AGAINST·W10·ALL = 21.7 [n=10, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·HOME = 24.0667 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·AWAY = 19.4 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·ALL = 14.0667 [n=30, HIGH]
- total_shots·FOR·W5·ALL = 14.0 [n=5, LOW]
- total_shots·FOR·W10·ALL = 14.0 [n=10, MEDIUM]
- total_shots·FOR·ALL_PRIOR·HOME = 16.4667 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·AWAY = 11.6667 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·ALL = 12.0333 [n=30, HIGH]
- total_shots·AGAINST·W5·ALL = 11.0 [n=5, LOW]
- total_shots·AGAINST·W10·ALL = 11.9 [n=10, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·HOME = 10.6667 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·AWAY = 13.4 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·ALL = 20.4 [n=30, HIGH]
- touches_in_box·FOR·W5·ALL = 21.6 [n=5, LOW]
- touches_in_box·FOR·W10·ALL = 20.8 [n=10, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·HOME = 23.0667 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·AWAY = 17.7333 [n=15, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·ALL = 23.4 [n=30, HIGH]
- touches_in_box·AGAINST·W5·ALL = 27.2 [n=5, LOW]
- touches_in_box·AGAINST·W10·ALL = 22.9 [n=10, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·HOME = 19.4 [n=15, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·AWAY = 27.4 [n=15, MEDIUM]
- xg·FOR·ALL_PRIOR·ALL = 1.3243 [n=30, HIGH]
- xg·FOR·W5·ALL = 1.426 [n=5, LOW]
- xg·FOR·W10·ALL = 1.327 [n=10, MEDIUM]
- xg·FOR·ALL_PRIOR·HOME = 1.5093 [n=15, MEDIUM]
- xg·FOR·ALL_PRIOR·AWAY = 1.1393 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·ALL = 1.306 [n=30, HIGH]
- xg·AGAINST·W5·ALL = 1.32 [n=5, LOW]
- xg·AGAINST·W10·ALL = 1.354 [n=10, MEDIUM]
- xg·AGAINST·ALL_PRIOR·HOME = 0.9127 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·AWAY = 1.6993 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·ALL = 2.6 [n=30, HIGH]
- yellow_cards·FOR·W5·ALL = 2.8 [n=5, LOW]
- yellow_cards·FOR·W10·ALL = 2.6 [n=10, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·HOME = 1.9333 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·AWAY = 3.2667 [n=15, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·ALL = 2.1333 [n=30, HIGH]
- yellow_cards·AGAINST·W5·ALL = 2.8 [n=5, LOW]
- yellow_cards·AGAINST·W10·ALL = 3.1 [n=10, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·HOME = 2.3333 [n=15, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·AWAY = 1.9333 [n=15, MEDIUM]

### Arm B — opponent-profile context (deterministic bands)

```json
{
 "axes": {
  "accurate_crosses_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "corners_against": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  },
  "corners_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  },
  "goals_against": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "goals_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "possession_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  },
  "shots_on_target_against": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "shots_on_target_for": {
   "AWAY": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 23,
    "candidate_n": 23,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  }
 },
 "similarity_version": "opponent_similarity_v1_pending"
}
```

---

## mt_010441491

- PIT-safe matches available: **116**; match rows included (both teams): **60**; omitted: **56** (reason: `frozen_history_policy(max_matches_per_team=30)`); UNEXPLAINED_OMISSION: **0**.
- Metric cell exposure rate (non-null of serialized): **0.9889**; derived summaries: **480**.
- Availability map: `{"expected_formation": "UNAVAILABLE", "formation": "LOW_COVERAGE", "half_time_state": "UNAVAILABLE", "injuries": "UNAVAILABLE", "lineup": "PIT_UNSAFE", "opponent_profile": "AVAILABLE", "recent_vs_long": "AVAILABLE", "red_cards": "AVAILABLE", "temporal_event_state": "UNAVAILABLE", "venue": "AVAILABLE", "xg": "AVAILABLE"}`
- Arm A packet hash: `fe1d269c0d7c23607ee90b882e2073e8a6770034de6bad0037299cec0276ce23`
- Arm B packet hash: `b83d8bd7e882c88dfca98590076f02ba1a146af12686d554073afbe6dbb09bc1`

### Arm A — frozen V3 compressed evidence (all items)

76 unconditional shrunk scalar items (venue=ALL, window=ALL_PRIOR):

| id | metric | value | n | reliability |
|---|---|---|---|---|
| HOME_ATK_corners_406027 | corners_for | 5.0959 | 37 | HIGH |
| HOME_DEF_corners_7cfac3 | corners_against | 4.561 | 37 | HIGH |
| HOME_ATK_accurate_crosses_c28b9e | accurate_crosses_for | 3.3441 | 37 | HIGH |
| HOME_DEF_accurate_crosses_81ffb5 | accurate_crosses_against | 4.1115 | 37 | HIGH |
| HOME_ATK_total_shots_808ac9 | total_shots_for | 13.9296 | 37 | HIGH |
| HOME_DEF_total_shots_c0e347 | total_shots_against | 11.7668 | 37 | HIGH |
| HOME_ATK_shots_on_target_e955e0 | shots_on_target_for | 4.8651 | 37 | HIGH |
| HOME_DEF_shots_on_target_8a3812 | shots_on_target_against | 4.3535 | 37 | HIGH |
| HOME_ATK_shots_off_target_11e91f | shots_off_target_for | 5.5139 | 37 | HIGH |
| HOME_DEF_shots_off_target_26031c | shots_off_target_against | 4.5604 | 37 | HIGH |
| HOME_ATK_blocked_shots_5198f8 | blocked_shots_for | 3.5508 | 37 | HIGH |
| HOME_DEF_blocked_shots_09c3c4 | blocked_shots_against | 2.8531 | 37 | HIGH |
| HOME_ATK_shots_inside_box_cf538d | shots_inside_box_for | 7.7941 | 37 | HIGH |
| HOME_DEF_shots_inside_box_e6b28d | shots_inside_box_against | 7.9802 | 37 | HIGH |
| HOME_ATK_touches_in_box_759ed8 | touches_in_box_for | 20.9949 | 37 | HIGH |
| HOME_DEF_touches_in_box_94cd98 | touches_in_box_against | 21.3204 | 37 | HIGH |
| HOME_ATK_final_third_entries_5aa0be | final_third_entries_for | 55.1348 | 37 | HIGH |
| HOME_DEF_final_third_entries_4a40ef | final_third_entries_against | 50.5999 | 37 | HIGH |
| HOME_ATK_possession_190f3f | possession_for | 58.814 | 37 | HIGH |
| HOME_DEF_possession_f8ada9 | possession_against | 41.186 | 37 | HIGH |
| HOME_ATK_tackles_65b6c1 | tackles_for | 15.317 | 37 | HIGH |
| HOME_DEF_tackles_e3c85e | tackles_against | 18.6193 | 37 | HIGH |
| HOME_ATK_fouls_8107c6 | fouls_for | 13.4476 | 37 | HIGH |
| HOME_DEF_fouls_b6d53c | fouls_against | 14.936 | 37 | HIGH |
| HOME_ATK_yellow_cards_80b7a4 | yellow_cards_for | 2.6303 | 37 | HIGH |
| HOME_DEF_yellow_cards_8ee8aa | yellow_cards_against | 2.8629 | 37 | HIGH |
| HOME_ATK_clearances_ec2e18 | clearances_for | 24.0946 | 37 | HIGH |
| HOME_DEF_clearances_6d3f4c | clearances_against | 21.7922 | 37 | HIGH |
| HOME_ATK_interceptions_967965 | interceptions_for | 7.9453 | 37 | HIGH |
| HOME_DEF_interceptions_c82020 | interceptions_against | 9.2709 | 37 | HIGH |
| HOME_ATK_goals_08b15b | goals_for | 1.4821 | 37 | HIGH |
| HOME_DEF_goals_d53fdd | goals_against | 1.2728 | 37 | HIGH |
| HOME_ATK_throw_ins_b24629 | throw_ins_for | 18.9501 | 37 | HIGH |
| HOME_DEF_throw_ins_208262 | throw_ins_against | 21.0432 | 37 | HIGH |
| HOME_ATK_big_chances_8a9e2f | big_chances_for | 2.4316 | 37 | HIGH |
| HOME_DEF_big_chances_885151 | big_chances_against | 2.6176 | 37 | HIGH |
| HOME_ATK_saves_6bda8d | saves_for | 3.1537 | 36 | HIGH |
| HOME_DEF_saves_19ae14 | saves_against | 3.4394 | 36 | HIGH |
| AWAY_ATK_corners_ca1538 | corners_for | 4.8132 | 79 | HIGH |
| AWAY_DEF_corners_598e33 | corners_against | 5.2014 | 79 | HIGH |
| AWAY_ATK_accurate_crosses_005290 | accurate_crosses_for | 4.3152 | 79 | HIGH |
| AWAY_DEF_accurate_crosses_287e9c | accurate_crosses_against | 5.1388 | 79 | HIGH |
| AWAY_ATK_total_shots_004f7a | total_shots_for | 12.5997 | 79 | HIGH |
| AWAY_DEF_total_shots_403d28 | total_shots_against | 13.682 | 79 | HIGH |
| AWAY_ATK_shots_on_target_9afd02 | shots_on_target_for | 4.2494 | 79 | HIGH |
| AWAY_DEF_shots_on_target_dcda5e | shots_on_target_against | 4.3671 | 79 | HIGH |
| AWAY_ATK_shots_off_target_b83815 | shots_off_target_for | 5.1894 | 79 | HIGH |
| AWAY_DEF_shots_off_target_5fe2d0 | shots_off_target_against | 5.5188 | 79 | HIGH |
| AWAY_ATK_blocked_shots_93d965 | blocked_shots_for | 3.161 | 79 | HIGH |
| AWAY_DEF_blocked_shots_97ef03 | blocked_shots_against | 3.7963 | 79 | HIGH |
| AWAY_ATK_shots_inside_box_567ee5 | shots_inside_box_for | 8.0488 | 79 | HIGH |
| AWAY_DEF_shots_inside_box_446c80 | shots_inside_box_against | 9.0253 | 79 | HIGH |
| AWAY_ATK_touches_in_box_2c76ca | touches_in_box_for | 20.6445 | 79 | HIGH |
| AWAY_DEF_touches_in_box_319da5 | touches_in_box_against | 24.6092 | 79 | HIGH |
| AWAY_ATK_final_third_entries_5a0987 | final_third_entries_for | 53.9858 | 79 | HIGH |
| AWAY_DEF_final_third_entries_ed75cd | final_third_entries_against | 57.8211 | 79 | HIGH |
| AWAY_ATK_possession_82105a | possession_for | 43.9176 | 79 | HIGH |
| AWAY_DEF_possession_012ecc | possession_against | 56.0824 | 79 | HIGH |
| AWAY_ATK_tackles_0865bc | tackles_for | 15.3721 | 79 | HIGH |
| AWAY_DEF_tackles_3e6a7d | tackles_against | 14.078 | 79 | HIGH |
| AWAY_ATK_fouls_97bf91 | fouls_for | 10.5676 | 79 | HIGH |
| AWAY_DEF_fouls_94f7aa | fouls_against | 11.6264 | 79 | HIGH |
| AWAY_ATK_yellow_cards_120c77 | yellow_cards_for | 2.0727 | 78 | HIGH |
| AWAY_DEF_yellow_cards_367397 | yellow_cards_against | 2.3108 | 78 | HIGH |
| AWAY_ATK_clearances_74617f | clearances_for | 23.8243 | 79 | HIGH |
| AWAY_DEF_clearances_8bdc80 | clearances_against | 25.942 | 79 | HIGH |
| AWAY_ATK_interceptions_404e22 | interceptions_for | 8.8782 | 79 | HIGH |
| AWAY_DEF_interceptions_4be11b | interceptions_against | 8.2429 | 79 | HIGH |
| AWAY_ATK_goals_5d2c6a | goals_for | 1.3262 | 79 | HIGH |
| AWAY_DEF_goals_4ad3b7 | goals_against | 1.3615 | 79 | HIGH |
| AWAY_ATK_throw_ins_64d189 | throw_ins_for | 22.4336 | 79 | HIGH |
| AWAY_DEF_throw_ins_35916f | throw_ins_against | 20.3983 | 79 | HIGH |
| AWAY_ATK_big_chances_065222 | big_chances_for | 2.3124 | 79 | HIGH |
| AWAY_DEF_big_chances_d5f920 | big_chances_against | 2.0419 | 79 | HIGH |
| AWAY_ATK_saves_50b33b | saves_for | 3.0768 | 78 | HIGH |
| AWAY_DEF_saves_bf5cbb | saves_against | 3.0054 | 78 | HIGH |

### Arm B — HOME_TEAM match-level matrix (30 rows × 55 cols)

Columns: `match_alias, kickoff_unix, competition, venue, opponent_alias, own_formation_family, opponent_formation_family, accurate_crosses_for, accurate_crosses_against, big_chances_for, big_chances_against, blocked_shots_for, blocked_shots_against, clearances_for, clearances_against, corners_for, corners_against, final_third_entries_for, final_third_entries_against, fouls_for, fouls_against, goals_for, goals_against, interceptions_for, interceptions_against, npxg_for, npxg_against, offsides_for, offsides_against, possession_for, possession_against, red_cards_for, red_cards_against, saves_for, saves_against, shots_inside_box_for, shots_inside_box_against, shots_off_target_for, shots_off_target_against, shots_on_target_for, shots_on_target_against, shots_outside_box_for, shots_outside_box_against, tackles_for, tackles_against, throw_ins_for, throw_ins_against, total_shots_for, total_shots_against, touches_in_box_for, touches_in_box_against, xg_for, xg_against, yellow_cards_for, yellow_cards_against`

| match_alias | kickoff_unix | competition | venue | opponent_alias | own_formation_family | opponent_formation_family | accurate_crosses_for | accurate_crosses_against | big_chances_for | big_chances_against | blocked_shots_for | blocked_shots_against | clearances_for | clearances_against | corners_for | corners_against | final_third_entries_for | final_third_entries_against | fouls_for | fouls_against | goals_for | goals_against | interceptions_for | interceptions_against | npxg_for | npxg_against | offsides_for | offsides_against | possession_for | possession_against | red_cards_for | red_cards_against | saves_for | saves_against | shots_inside_box_for | shots_inside_box_against | shots_off_target_for | shots_off_target_against | shots_on_target_for | shots_on_target_against | shots_outside_box_for | shots_outside_box_against | tackles_for | tackles_against | throw_ins_for | throw_ins_against | total_shots_for | total_shots_against | touches_in_box_for | touches_in_box_against | xg_for | xg_against | yellow_cards_for | yellow_cards_against |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| m_mt_979112718 | 1759595400 | COMPETITION | HOME | OPP_001 | BACK_FOUR | BACK_THREE | 1.0 | 2.0 | 2.0 | 1.0 | 1.0 | 2.0 | 22.0 | 20.0 | 7.0 | 1.0 | 59.0 | 45.0 | 9.0 | 9.0 | 1.0 | 2.0 | 6.0 | 7.0 |  |  | 5.0 | 1.0 | 60.0 | 40.0 | 1.0 | 0.0 | 3.0 | 3.0 | 5.0 | 6.0 | 3.0 | 4.0 | 4.0 | 5.0 | 3.0 | 5.0 | 16.0 | 19.0 | 17.0 | 17.0 | 8.0 | 11.0 | 17.0 | 13.0 | 0.7 | 1.23 | 2.0 | 3.0 |
| m_mt_747995479 | 1760200200 | COMPETITION | AWAY | OPP_002 |  |  | 0.0 | 6.0 | 1.0 | 5.0 | 4.0 | 0.0 | 13.0 | 26.0 | 4.0 | 2.0 | 63.0 | 38.0 | 13.0 | 18.0 | 0.0 | 3.0 | 5.0 | 10.0 |  |  | 1.0 | 5.0 | 62.0 | 38.0 | 1.0 | 0.0 | 2.0 | 3.0 | 6.0 | 6.0 | 3.0 | 4.0 | 3.0 | 5.0 | 4.0 | 3.0 | 19.0 | 17.0 | 16.0 | 18.0 | 10.0 | 9.0 | 21.0 | 17.0 | 0.67 | 1.23 | 2.0 | 4.0 |
| m_mt_252666762 | 1760725800 | COMPETITION | HOME | OPP_003 |  |  | 7.0 | 4.0 | 1.0 | 0.0 | 3.0 | 3.0 | 19.0 | 23.0 | 5.0 | 3.0 | 53.0 | 50.0 | 16.0 | 15.0 | 0.0 | 0.0 | 6.0 | 3.0 |  |  | 0.0 | 2.0 | 61.0 | 39.0 | 0.0 | 0.0 | 4.0 | 3.0 | 7.0 | 11.0 | 7.0 | 6.0 | 3.0 | 4.0 | 6.0 | 2.0 | 18.0 | 31.0 | 28.0 | 29.0 | 13.0 | 13.0 | 21.0 | 14.0 | 1.27 | 1.0 | 4.0 | 2.0 |
| m_mt_404777841 | 1761483600 | COMPETITION | AWAY | OPP_004 |  |  | 4.0 | 0.0 | 4.0 | 6.0 | 11.0 | 4.0 | 13.0 | 22.0 | 7.0 | 2.0 | 51.0 | 51.0 | 13.0 | 12.0 | 1.0 | 4.0 | 5.0 | 11.0 | 0.37 | 0.62 | 2.0 | 1.0 | 53.0 | 47.0 | 0.0 | 1.0 | 3.0 | 3.0 | 11.0 | 11.0 | 7.0 | 5.0 | 5.0 | 7.0 | 12.0 | 5.0 | 15.0 | 19.0 | 21.0 | 17.0 | 23.0 | 16.0 | 38.0 | 31.0 | 1.48 | 2.65 | 3.0 | 2.0 |
| m_mt_626333586 | 1762088400 | COMPETITION | HOME | OPP_005 |  |  | 3.0 | 1.0 | 1.0 | 0.0 | 7.0 | 0.0 | 21.0 | 27.0 | 9.0 | 3.0 | 45.0 | 55.0 | 19.0 | 14.0 | 0.0 | 0.0 | 9.0 | 19.0 | 0.33 | 0.01 | 2.0 | 1.0 | 56.0 | 44.0 | 0.0 | 0.0 | 1.0 | 3.0 | 10.0 | 2.0 | 4.0 | 4.0 | 4.0 | 1.0 | 5.0 | 3.0 | 10.0 | 11.0 | 20.0 | 22.0 | 15.0 | 5.0 | 19.0 | 5.0 | 1.31 | 0.26 | 3.0 | 2.0 |
| m_mt_838555655 | 1762614900 | COMPETITION | AWAY | OPP_006 |  |  | 2.0 | 7.0 | 2.0 | 3.0 | 10.0 | 2.0 | 31.0 | 16.0 | 3.0 | 1.0 | 57.0 | 60.0 | 21.0 | 23.0 | 2.0 | 2.0 | 14.0 | 15.0 | 0.49 | 0.25 | 1.0 | 1.0 | 54.0 | 46.0 | 0.0 | 0.0 | 3.0 | 1.0 | 11.0 | 10.0 | 7.0 | 3.0 | 3.0 | 5.0 | 9.0 | 0.0 | 7.0 | 26.0 | 16.0 | 27.0 | 20.0 | 10.0 | 25.0 | 23.0 | 1.72 | 1.34 | 5.0 | 1.0 |
| m_mt_191000707 | 1763218800 | COMPETITION | AWAY | OPP_007 | BACK_FOUR | BACK_FOUR | 3.0 | 7.0 | 1.0 | 2.0 | 4.0 | 2.0 | 36.0 | 18.0 | 2.0 | 4.0 | 56.0 | 47.0 | 8.0 | 9.0 | 0.0 | 1.0 | 4.0 | 7.0 | 0.13 | 0.45 | 1.0 | 3.0 | 67.0 | 33.0 | 0.0 | 0.0 | 5.0 | 6.0 | 5.0 | 11.0 | 7.0 | 9.0 | 6.0 | 6.0 | 12.0 | 6.0 | 11.0 | 14.0 | 21.0 | 22.0 | 17.0 | 17.0 | 15.0 | 33.0 | 0.82 | 1.9 | 1.0 | 1.0 |
| m_mt_363888453 | 1763824500 | COMPETITION | HOME | OPP_008 |  |  | 2.0 | 3.0 | 1.0 | 6.0 | 2.0 | 3.0 | 27.0 | 16.0 | 2.0 | 4.0 | 61.0 | 73.0 | 14.0 | 13.0 | 1.0 | 3.0 | 6.0 | 16.0 | 0.33 | 0.86 | 2.0 | 0.0 | 57.0 | 43.0 | 0.0 | 0.0 | 3.0 | 3.0 | 8.0 | 12.0 | 4.0 | 7.0 | 4.0 | 6.0 | 2.0 | 4.0 | 20.0 | 16.0 | 27.0 | 22.0 | 10.0 | 16.0 | 13.0 | 37.0 | 1.08 | 2.75 | 2.0 | 2.0 |
| m_mt_838555760 | 1764358200 | COMPETITION | AWAY | OPP_009 | BACK_FOUR | BACK_FOUR | 3.0 | 9.0 | 1.0 | 7.0 | 1.0 | 5.0 | 28.0 | 9.0 | 5.0 | 8.0 | 39.0 | 63.0 | 8.0 | 11.0 | 1.0 | 1.0 | 5.0 | 11.0 | 0.31 | 0.81 | 6.0 | 1.0 | 56.0 | 44.0 | 0.0 | 0.0 | 9.0 | 1.0 | 6.0 | 17.0 | 7.0 | 8.0 | 2.0 | 10.0 | 4.0 | 6.0 | 18.0 | 24.0 | 24.0 | 17.0 | 10.0 | 23.0 | 17.0 | 30.0 | 0.86 | 3.87 | 3.0 | 3.0 |
| m_mt_838555828 | 1765026000 | COMPETITION | HOME | OPP_010 |  |  | 4.0 | 5.0 | 4.0 | 3.0 | 5.0 | 4.0 | 22.0 | 26.0 | 10.0 | 4.0 | 44.0 | 55.0 | 14.0 | 13.0 | 1.0 | 2.0 | 6.0 | 9.0 | 0.48 | 0.62 | 1.0 | 2.0 | 60.0 | 40.0 | 0.0 | 0.0 | 6.0 | 4.0 | 13.0 | 12.0 | 8.0 | 5.0 | 6.0 | 8.0 | 6.0 | 5.0 | 14.0 | 14.0 | 19.0 | 29.0 | 19.0 | 17.0 | 31.0 | 35.0 | 2.26 | 2.73 | 1.0 | 2.0 |
| m_mt_252666267 | 1765638900 | COMPETITION | AWAY | OPP_011 |  |  | 2.0 | 5.0 | 0.0 | 2.0 | 4.0 | 6.0 | 21.0 | 16.0 | 6.0 | 8.0 | 54.0 | 38.0 | 13.0 | 19.0 | 1.0 | 0.0 | 9.0 | 6.0 | 0.24 | 0.42 | 2.0 | 4.0 | 68.0 | 32.0 | 0.0 | 0.0 | 5.0 | 1.0 | 5.0 | 12.0 | 3.0 | 6.0 | 2.0 | 5.0 | 4.0 | 5.0 | 17.0 | 30.0 | 19.0 | 30.0 | 9.0 | 17.0 | 16.0 | 25.0 | 0.97 | 1.8 | 2.0 | 3.0 |
| m_mt_252666830 | 1766235600 | COMPETITION | HOME | OPP_012 |  |  | 6.0 | 5.0 | 4.0 | 3.0 | 1.0 | 2.0 | 23.0 | 29.0 | 1.0 | 4.0 | 55.0 | 44.0 | 13.0 | 11.0 | 1.0 | 0.0 | 8.0 | 6.0 | 0.33 | 0.2 | 3.0 | 4.0 | 60.0 | 40.0 | 0.0 | 0.0 | 1.0 | 3.0 | 9.0 | 9.0 | 7.0 | 7.0 | 4.0 | 1.0 | 3.0 | 1.0 | 18.0 | 26.0 | 21.0 | 23.0 | 12.0 | 10.0 | 29.0 | 17.0 | 1.59 | 1.53 | 3.0 | 4.0 |
| m_mt_404778958 | 1767539700 | COMPETITION | AWAY | OPP_013 | BACK_FOUR | BACK_FOUR | 4.0 | 5.0 | 2.0 | 4.0 | 4.0 | 0.0 | 15.0 | 31.0 | 8.0 | 4.0 | 62.0 | 47.0 | 12.0 | 15.0 | 1.0 | 2.0 | 10.0 | 11.0 | 0.2 | 0.59 | 4.0 | 3.0 | 67.0 | 33.0 | 0.0 | 0.0 | 3.0 | 7.0 | 6.0 | 6.0 | 0.0 | 2.0 | 8.0 | 5.0 | 6.0 | 1.0 | 11.0 | 14.0 | 19.0 | 22.0 | 12.0 | 7.0 | 22.0 | 16.0 | 1.97 | 1.25 | 2.0 | 2.0 |
| m_mt_191006405 | 1768066200 | COMPETITION | HOME | OPP_014 |  |  | 9.0 | 1.0 | 2.0 | 1.0 | 4.0 | 0.0 | 8.0 | 41.0 | 10.0 | 1.0 | 84.0 | 32.0 | 6.0 | 13.0 | 1.0 | 1.0 | 8.0 | 7.0 | 0.55 | 0.11 | 2.0 | 0.0 | 72.0 | 28.0 | 0.0 | 0.0 | 1.0 | 4.0 | 14.0 | 1.0 | 9.0 | 0.0 | 5.0 | 2.0 | 4.0 | 1.0 | 13.0 | 16.0 | 22.0 | 11.0 | 18.0 | 2.0 | 30.0 | 7.0 | 2.06 | 0.54 | 1.0 | 4.0 |
| m_mt_979112611 | 1768741200 | COMPETITION | AWAY | OPP_015 | BACK_FOUR | BACK_FOUR | 4.0 | 6.0 | 2.0 | 2.0 | 5.0 | 6.0 | 39.0 | 18.0 | 1.0 | 7.0 | 37.0 | 55.0 | 15.0 | 23.0 | 2.0 | 1.0 | 5.0 | 8.0 | 0.4 | 0.31 | 2.0 | 2.0 | 61.0 | 39.0 | 0.0 | 0.0 | 4.0 | 1.0 | 8.0 | 11.0 | 6.0 | 5.0 | 3.0 | 5.0 | 6.0 | 5.0 | 18.0 | 10.0 | 12.0 | 22.0 | 14.0 | 16.0 | 23.0 | 20.0 | 1.33 | 1.51 | 4.0 | 2.0 |
| m_mt_191006386 | 1769346000 | COMPETITION | HOME | OPP_006 |  |  | 5.0 | 5.0 | 1.0 | 3.0 | 6.0 | 1.0 | 16.0 | 24.0 | 3.0 | 1.0 | 75.0 | 32.0 | 18.0 | 16.0 | 1.0 | 1.0 | 11.0 | 4.0 | 0.39 | 0.13 | 2.0 | 1.0 | 73.0 | 27.0 | 0.0 | 0.0 | 0.0 | 4.0 | 11.0 | 5.0 | 8.0 | 4.0 | 5.0 | 1.0 | 8.0 | 1.0 | 19.0 | 15.0 | 16.0 | 15.0 | 19.0 | 6.0 | 32.0 | 15.0 | 1.01 | 0.68 | 2.0 | 4.0 |
| m_mt_363881683 | 1769967000 | COMPETITION | AWAY | OPP_008 | BACK_FOUR | BACK_FOUR | 1.0 | 4.0 | 2.0 | 5.0 | 1.0 | 8.0 | 21.0 | 28.0 | 6.0 | 6.0 | 53.0 | 45.0 | 12.0 | 27.0 | 0.0 | 2.0 | 6.0 | 11.0 | 0.2 | 0.7 | 3.0 | 2.0 | 61.0 | 39.0 | 0.0 | 0.0 | 4.0 | 5.0 | 5.0 | 14.0 | 4.0 | 4.0 | 5.0 | 6.0 | 5.0 | 4.0 | 14.0 | 33.0 | 26.0 | 11.0 | 10.0 | 18.0 | 17.0 | 35.0 | 0.81 | 3.35 | 4.0 | 3.0 |
| m_mt_252667570 | 1770469200 | COMPETITION | HOME | OPP_002 |  |  | 2.0 | 0.0 | 2.0 | 2.0 | 3.0 | 1.0 | 16.0 | 29.0 | 2.0 | 3.0 | 65.0 | 45.0 | 11.0 | 18.0 | 1.0 | 2.0 | 7.0 | 8.0 | 0.18 | 0.22 | 1.0 | 2.0 | 73.0 | 27.0 | 0.0 | 0.0 | 0.0 | 2.0 | 7.0 | 4.0 | 8.0 | 4.0 | 3.0 | 2.0 | 7.0 | 3.0 | 14.0 | 20.0 | 33.0 | 11.0 | 14.0 | 7.0 | 20.0 | 11.0 | 0.97 | 0.5 | 4.0 | 5.0 |
| m_mt_626339482 | 1771011000 | COMPETITION | AWAY | OPP_010 | BACK_FOUR | BACK_FOUR | 1.0 | 3.0 | 2.0 | 4.0 | 3.0 | 3.0 | 15.0 | 26.0 | 5.0 | 6.0 | 49.0 | 46.0 | 19.0 | 12.0 | 2.0 | 3.0 | 12.0 | 19.0 | 0.3 | 0.59 | 0.0 | 2.0 | 59.0 | 41.0 | 0.0 | 0.0 | 2.0 | 5.0 | 8.0 | 9.0 | 5.0 | 6.0 | 7.0 | 6.0 | 7.0 | 6.0 | 10.0 | 15.0 | 15.0 | 19.0 | 15.0 | 15.0 | 23.0 | 26.0 | 2.23 | 1.32 | 4.0 | 2.0 |
| m_mt_838550940 | 1771773300 | COMPETITION | HOME | OPP_016 |  |  | 6.0 | 1.0 | 2.0 | 0.0 | 5.0 | 0.0 | 26.0 | 16.0 | 6.0 | 5.0 | 64.0 | 52.0 | 20.0 | 18.0 | 2.0 | 1.0 | 8.0 | 7.0 | 0.43 | 0.12 | 2.0 | 0.0 | 61.0 | 39.0 | 0.0 | 1.0 | 1.0 | 4.0 | 9.0 | 2.0 | 6.0 | 4.0 | 6.0 | 2.0 | 8.0 | 4.0 | 9.0 | 19.0 | 17.0 | 20.0 | 17.0 | 6.0 | 27.0 | 10.0 | 1.09 | 0.29 | 3.0 | 4.0 |
| m_mt_838555600 | 1772479800 | COMPETITION | AWAY | OPP_017 |  |  | 0.0 | 4.0 | 3.0 | 3.0 | 1.0 | 4.0 | 30.0 | 8.0 | 3.0 | 9.0 | 48.0 | 48.0 | 10.0 | 16.0 | 4.0 | 1.0 | 5.0 | 10.0 | 0.48 | 0.25 | 3.0 | 5.0 | 42.0 | 58.0 | 0.0 | 0.0 | 3.0 | 4.0 | 7.0 | 7.0 | 4.0 | 5.0 | 8.0 | 4.0 | 6.0 | 6.0 | 25.0 | 19.0 | 16.0 | 26.0 | 13.0 | 13.0 | 18.0 | 26.0 | 1.68 | 1.39 | 4.0 | 0.0 |
| m_mt_404777127 | 1772982900 | COMPETITION | HOME | OPP_009 |  |  | 6.0 | 4.0 | 5.0 | 1.0 | 5.0 | 1.0 | 34.0 | 23.0 | 9.0 | 0.0 | 61.0 | 78.0 | 8.0 | 11.0 | 1.0 | 0.0 | 12.0 | 7.0 | 0.33 | 0.13 | 1.0 | 2.0 | 66.0 | 34.0 | 0.0 | 0.0 | 0.0 | 3.0 | 9.0 | 2.0 | 14.0 | 3.0 | 3.0 | 0.0 | 13.0 | 2.0 | 10.0 | 14.0 | 20.0 | 25.0 | 22.0 | 4.0 | 26.0 | 12.0 | 1.54 | 0.51 | 4.0 | 2.0 |
| m_mt_404777279 | 1773587700 | COMPETITION | AWAY | OPP_003 | BACK_FOUR | BACK_THREE | 3.0 | 4.0 | 1.0 | 1.0 | 4.0 | 3.0 | 15.0 | 22.0 | 9.0 | 6.0 | 61.0 | 50.0 | 15.0 | 12.0 | 1.0 | 1.0 | 8.0 | 6.0 | 0.23 | 0.29 | 1.0 | 3.0 | 62.0 | 38.0 | 0.0 | 0.0 | 4.0 | 3.0 | 4.0 | 6.0 | 4.0 | 3.0 | 4.0 | 5.0 | 8.0 | 5.0 | 24.0 | 19.0 | 21.0 | 25.0 | 12.0 | 11.0 | 9.0 | 15.0 | 0.98 | 1.19 | 3.0 | 4.0 |
| m_mt_404777210 | 1774106100 | COMPETITION | HOME | OPP_018 |  |  | 1.0 | 2.0 | 1.0 | 1.0 | 4.0 | 1.0 | 18.0 | 25.0 | 5.0 | 4.0 | 74.0 | 45.0 | 8.0 | 11.0 | 0.0 | 1.0 | 2.0 | 7.0 | 0.1 | 0.17 | 1.0 | 1.0 | 73.0 | 27.0 | 0.0 | 0.0 | 1.0 | 3.0 | 5.0 | 3.0 | 7.0 | 2.0 | 3.0 | 2.0 | 9.0 | 2.0 | 8.0 | 21.0 | 17.0 | 19.0 | 14.0 | 5.0 | 17.0 | 8.0 | 0.46 | 0.42 | 4.0 | 4.0 |
| m_mt_838555832 | 1774793700 | COMPETITION | AWAY | OPP_014 | BACK_FOUR | BACK_FOUR | 3.0 | 4.0 | 6.0 | 3.0 | 0.0 | 2.0 | 46.0 | 19.0 | 2.0 | 1.0 | 45.0 | 60.0 | 15.0 | 15.0 | 4.0 | 0.0 | 6.0 | 2.0 | 0.53 | 0.14 | 2.0 | 1.0 | 48.0 | 52.0 | 0.0 | 0.0 | 6.0 | 3.0 | 7.0 | 5.0 | 4.0 | 2.0 | 7.0 | 6.0 | 4.0 | 5.0 | 10.0 | 15.0 | 17.0 | 27.0 | 11.0 | 10.0 | 19.0 | 22.0 | 1.09 | 1.62 | 2.0 | 3.0 |
| m_mt_585222513 | 1775062800 | COMPETITION | HOME | OPP_004 |  |  | 2.0 | 6.0 | 4.0 | 6.0 | 6.0 | 2.0 | 12.0 | 45.0 | 8.0 | 5.0 | 73.0 | 51.0 | 17.0 | 16.0 | 3.0 | 3.0 | 7.0 | 10.0 | 0.45 | 0.33 | 4.0 | 0.0 | 67.0 | 33.0 | 0.0 | 0.0 | 3.0 | 5.0 | 7.0 | 10.0 | 5.0 | 4.0 | 8.0 | 6.0 | 12.0 | 2.0 | 19.0 | 11.0 | 16.0 | 16.0 | 19.0 | 12.0 | 19.0 | 18.0 |  |  | 4.0 | 3.0 |
| m_mt_585222596 | 1775398500 | COMPETITION | HOME | OPP_019 |  |  | 6.0 | 1.0 | 8.0 | 2.0 | 3.0 | 2.0 | 13.0 | 15.0 | 6.0 | 2.0 | 61.0 | 36.0 | 12.0 | 17.0 | 6.0 | 2.0 | 5.0 | 6.0 | 0.96 | 0.55 | 3.0 | 1.0 | 66.0 | 34.0 | 0.0 | 1.0 | 1.0 | 3.0 | 15.0 | 6.0 | 9.0 | 4.0 | 9.0 | 3.0 | 6.0 | 3.0 | 16.0 | 20.0 | 24.0 | 18.0 | 21.0 | 9.0 | 30.0 | 16.0 |  |  | 1.0 | 4.0 |
| m_mt_838550227 | 1776011400 | COMPETITION | AWAY | OPP_005 |  |  | 3.0 | 3.0 | 2.0 | 1.0 | 1.0 | 2.0 | 40.0 | 17.0 | 3.0 | 6.0 | 46.0 | 56.0 | 13.0 | 14.0 | 1.0 | 0.0 | 4.0 | 10.0 | 0.24 | 0.36 | 0.0 | 3.0 | 60.0 | 40.0 | 0.0 | 0.0 | 5.0 | 2.0 | 4.0 | 8.0 | 3.0 | 4.0 | 3.0 | 5.0 | 3.0 | 3.0 | 15.0 | 24.0 | 17.0 | 27.0 | 7.0 | 11.0 | 16.0 | 27.0 | 0.59 | 0.84 | 2.0 | 4.0 |
| m_mt_404770775 | 1776600000 | COMPETITION | HOME | OPP_011 | BACK_FOUR | BACK_FOUR | 5.0 | 1.0 | 1.0 | 0.0 | 4.0 | 1.0 | 20.0 | 32.0 | 8.0 | 2.0 | 68.0 | 39.0 | 10.0 | 13.0 | 1.0 | 0.0 | 5.0 | 13.0 | 0.2 | 0.07 | 1.0 | 3.0 | 70.0 | 30.0 | 0.0 | 0.0 |  |  | 7.0 | 3.0 | 6.0 | 3.0 | 1.0 | 0.0 | 4.0 | 1.0 | 10.0 | 19.0 | 13.0 | 22.0 | 11.0 | 4.0 | 32.0 | 14.0 | 0.75 | 0.18 | 1.0 | 4.0 |
| m_mt_747994950 | 1777221000 | COMPETITION | AWAY | OPP_001 |  |  | 4.0 | 7.0 | 7.0 | 6.0 | 1.0 | 3.0 | 21.0 | 12.0 | 5.0 | 9.0 | 58.0 | 52.0 | 13.0 | 12.0 | 4.0 | 0.0 | 7.0 | 5.0 | 0.67 | 0.36 | 2.0 | 2.0 | 57.0 | 43.0 | 0.0 | 0.0 | 8.0 | 6.0 | 12.0 | 12.0 | 4.0 | 6.0 | 10.0 | 8.0 | 3.0 | 5.0 | 15.0 | 13.0 | 15.0 | 24.0 | 15.0 | 17.0 | 23.0 | 23.0 | 2.08 | 2.14 | 1.0 | 5.0 |

### Arm B — AWAY_TEAM match-level matrix (30 rows × 55 cols)

Columns: `match_alias, kickoff_unix, competition, venue, opponent_alias, own_formation_family, opponent_formation_family, accurate_crosses_for, accurate_crosses_against, big_chances_for, big_chances_against, blocked_shots_for, blocked_shots_against, clearances_for, clearances_against, corners_for, corners_against, final_third_entries_for, final_third_entries_against, fouls_for, fouls_against, goals_for, goals_against, interceptions_for, interceptions_against, npxg_for, npxg_against, offsides_for, offsides_against, possession_for, possession_against, red_cards_for, red_cards_against, saves_for, saves_against, shots_inside_box_for, shots_inside_box_against, shots_off_target_for, shots_off_target_against, shots_on_target_for, shots_on_target_against, shots_outside_box_for, shots_outside_box_against, tackles_for, tackles_against, throw_ins_for, throw_ins_against, total_shots_for, total_shots_against, touches_in_box_for, touches_in_box_against, xg_for, xg_against, yellow_cards_for, yellow_cards_against`

| match_alias | kickoff_unix | competition | venue | opponent_alias | own_formation_family | opponent_formation_family | accurate_crosses_for | accurate_crosses_against | big_chances_for | big_chances_against | blocked_shots_for | blocked_shots_against | clearances_for | clearances_against | corners_for | corners_against | final_third_entries_for | final_third_entries_against | fouls_for | fouls_against | goals_for | goals_against | interceptions_for | interceptions_against | npxg_for | npxg_against | offsides_for | offsides_against | possession_for | possession_against | red_cards_for | red_cards_against | saves_for | saves_against | shots_inside_box_for | shots_inside_box_against | shots_off_target_for | shots_off_target_against | shots_on_target_for | shots_on_target_against | shots_outside_box_for | shots_outside_box_against | tackles_for | tackles_against | throw_ins_for | throw_ins_against | total_shots_for | total_shots_against | touches_in_box_for | touches_in_box_against | xg_for | xg_against | yellow_cards_for | yellow_cards_against |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| m_mt_010443143 | 1759775400 | COMPETITION | AWAY | OPP_014 | BACK_FOUR | BACK_FOUR | 1.0 | 1.0 | 0.0 | 1.0 | 3.0 | 4.0 | 23.0 | 26.0 | 1.0 | 6.0 | 63.0 | 49.0 | 11.0 | 19.0 | 0.0 | 0.0 | 4.0 | 5.0 |  |  | 1.0 | 3.0 | 48.0 | 52.0 | 1.0 | 0.0 | 1.0 | 3.0 | 5.0 | 5.0 | 3.0 | 1.0 | 3.0 | 1.0 | 4.0 | 1.0 | 18.0 | 18.0 | 19.0 | 18.0 | 9.0 | 6.0 | 13.0 | 20.0 | 0.8 | 0.82 | 1.0 | 1.0 |
| m_mt_747995404 | 1760270400 | COMPETITION | HOME | OPP_013 |  |  | 7.0 | 3.0 | 3.0 | 0.0 | 5.0 | 1.0 | 30.0 | 27.0 | 6.0 | 3.0 | 49.0 | 59.0 | 8.0 | 17.0 | 0.0 | 0.0 | 17.0 | 7.0 |  |  | 3.0 | 2.0 | 40.0 | 60.0 | 0.0 | 0.0 | 1.0 | 4.0 | 8.0 | 2.0 | 4.0 | 1.0 | 4.0 | 1.0 | 5.0 | 1.0 | 17.0 | 13.0 | 21.0 | 24.0 | 13.0 | 3.0 | 22.0 | 13.0 | 1.23 | 0.6 | 1.0 | 3.0 |
| m_mt_979111220 | 1760883300 | COMPETITION | AWAY | OPP_008 |  |  | 2.0 | 10.0 | 5.0 | 3.0 | 1.0 | 5.0 | 25.0 | 18.0 | 3.0 | 9.0 | 39.0 | 61.0 | 18.0 | 14.0 | 1.0 | 0.0 | 12.0 | 5.0 |  |  | 2.0 | 0.0 | 36.0 | 64.0 | 1.0 | 2.0 | 5.0 | 7.0 | 9.0 | 15.0 | 2.0 | 12.0 | 8.0 | 5.0 | 2.0 | 7.0 | 16.0 | 16.0 | 15.0 | 18.0 | 11.0 | 22.0 | 24.0 | 40.0 | 1.94 | 1.78 | 3.0 | 5.0 |
| m_mt_626333959 | 1761401700 | COMPETITION | HOME | OPP_017 |  |  | 10.0 | 4.0 | 4.0 | 5.0 | 7.0 | 2.0 | 17.0 | 43.0 | 9.0 | 4.0 | 61.0 | 43.0 | 8.0 | 10.0 | 1.0 | 3.0 | 10.0 | 9.0 | 0.69 | 0.54 | 1.0 | 0.0 | 49.0 | 51.0 | 0.0 | 0.0 | 6.0 | 3.0 | 14.0 | 7.0 | 10.0 | 2.0 | 4.0 | 9.0 | 7.0 | 6.0 | 19.0 | 23.0 | 38.0 | 18.0 | 21.0 | 13.0 | 33.0 | 19.0 | 1.63 | 2.27 |  |  |
| m_mt_363888133 | 1762018200 | COMPETITION | HOME | OPP_006 |  |  | 8.0 | 9.0 | 2.0 | 5.0 | 3.0 | 9.0 | 34.0 | 19.0 | 7.0 | 7.0 | 61.0 | 55.0 | 13.0 | 6.0 | 2.0 | 1.0 | 8.0 | 11.0 | 0.51 | 0.46 | 1.0 | 1.0 | 40.0 | 60.0 | 0.0 | 0.0 | 3.0 | 4.0 | 11.0 | 14.0 | 5.0 | 7.0 | 6.0 | 4.0 | 3.0 | 6.0 | 9.0 | 12.0 | 15.0 | 22.0 | 14.0 | 20.0 | 27.0 | 35.0 | 1.11 | 2.41 | 3.0 | 0.0 |
| m_mt_838555699 | 1762614900 | COMPETITION | AWAY | OPP_018 |  |  | 5.0 | 7.0 | 3.0 | 5.0 | 1.0 | 6.0 | 30.0 | 31.0 | 3.0 | 4.0 | 67.0 | 78.0 | 11.0 | 15.0 | 2.0 | 3.0 | 9.0 | 10.0 | 0.88 | 0.57 | 0.0 | 2.0 | 42.0 | 58.0 | 0.0 | 0.0 | 5.0 | 7.0 | 8.0 | 14.0 | 7.0 | 8.0 | 9.0 | 8.0 | 9.0 | 8.0 | 8.0 | 9.0 | 35.0 | 21.0 | 17.0 | 22.0 | 24.0 | 32.0 | 2.99 | 3.45 | 3.0 | 1.0 |
| m_mt_191000707 | 1763218800 | COMPETITION | HOME | OPP_020 | BACK_FOUR | BACK_FOUR | 7.0 | 3.0 | 2.0 | 1.0 | 2.0 | 4.0 | 18.0 | 36.0 | 4.0 | 2.0 | 47.0 | 56.0 | 9.0 | 8.0 | 1.0 | 0.0 | 7.0 | 4.0 | 0.45 | 0.13 | 3.0 | 1.0 | 33.0 | 67.0 | 0.0 | 0.0 | 6.0 | 5.0 | 11.0 | 5.0 | 9.0 | 7.0 | 6.0 | 6.0 | 6.0 | 12.0 | 14.0 | 11.0 | 22.0 | 21.0 | 17.0 | 17.0 | 33.0 | 15.0 | 1.9 | 0.82 | 1.0 | 1.0 |
| m_mt_010444589 | 1763753400 | COMPETITION | AWAY | OPP_021 |  |  | 1.0 | 5.0 | 1.0 | 3.0 | 2.0 | 3.0 | 18.0 | 25.0 | 3.0 | 5.0 | 51.0 | 58.0 | 16.0 | 16.0 | 1.0 | 2.0 | 10.0 | 8.0 | 0.15 | 0.28 | 3.0 | 3.0 | 40.0 | 60.0 | 0.0 | 0.0 | 1.0 | 3.0 | 5.0 | 8.0 | 5.0 | 4.0 | 3.0 | 3.0 | 5.0 | 2.0 | 10.0 | 18.0 | 26.0 | 18.0 | 10.0 | 10.0 | 12.0 | 21.0 | 0.6 | 1.53 | 5.0 | 1.0 |
| m_mt_747999633 | 1764437400 | COMPETITION | HOME | OPP_012 |  |  | 2.0 | 3.0 | 1.0 | 2.0 | 3.0 | 4.0 | 22.0 | 26.0 | 9.0 | 5.0 | 44.0 | 48.0 | 10.0 | 5.0 | 0.0 | 2.0 | 2.0 | 7.0 | 0.13 | 0.32 | 1.0 | 3.0 | 42.0 | 58.0 | 0.0 | 0.0 | 1.0 | 4.0 | 8.0 | 4.0 | 8.0 | 1.0 | 3.0 | 3.0 | 6.0 | 4.0 | 11.0 | 12.0 | 24.0 | 15.0 | 14.0 | 8.0 | 15.0 | 13.0 | 1.02 | 1.03 | 1.0 | 1.0 |
| m_mt_363888432 | 1765206900 | COMPETITION | AWAY | OPP_022 |  |  | 3.0 | 7.0 | 1.0 | 0.0 | 2.0 | 3.0 | 22.0 | 17.0 | 5.0 | 5.0 | 59.0 | 51.0 | 12.0 | 14.0 | 1.0 | 0.0 | 10.0 | 10.0 | 0.22 | 0.12 | 0.0 | 1.0 | 46.0 | 54.0 | 0.0 | 0.0 | 3.0 | 1.0 | 4.0 | 7.0 | 5.0 | 7.0 | 2.0 | 3.0 | 5.0 | 6.0 | 23.0 | 10.0 | 29.0 | 30.0 | 9.0 | 13.0 | 9.0 | 13.0 | 0.75 | 0.74 | 1.0 | 3.0 |
| m_mt_585222572 | 1765725300 | COMPETITION | HOME | OPP_004 |  |  | 6.0 | 2.0 | 1.0 | 1.0 | 1.0 | 5.0 | 19.0 | 23.0 | 6.0 | 5.0 | 57.0 | 67.0 | 9.0 | 4.0 | 1.0 | 3.0 | 13.0 | 11.0 | 0.35 | 0.39 | 2.0 | 3.0 | 43.0 | 57.0 | 0.0 | 0.0 | 2.0 | 5.0 | 9.0 | 11.0 | 5.0 | 2.0 | 5.0 | 5.0 | 2.0 | 1.0 | 16.0 | 13.0 | 29.0 | 24.0 | 11.0 | 12.0 | 26.0 | 25.0 | 1.14 | 2.16 | 3.0 | 1.0 |
| m_mt_252666896 | 1766338200 | COMPETITION | AWAY | OPP_003 |  |  | 2.0 | 9.0 | 2.0 | 3.0 | 2.0 | 3.0 | 29.0 | 18.0 | 5.0 | 6.0 | 41.0 | 54.0 | 12.0 | 12.0 | 1.0 | 1.0 | 2.0 | 8.0 | 0.16 | 0.75 | 0.0 | 2.0 | 43.0 | 57.0 | 0.0 | 0.0 | 4.0 | 3.0 | 8.0 | 13.0 | 7.0 | 10.0 | 4.0 | 5.0 | 5.0 | 5.0 | 17.0 | 11.0 | 18.0 | 21.0 | 13.0 | 18.0 | 16.0 | 29.0 |  |  | 3.0 | 4.0 |
| m_mt_747999644 | 1767547800 | COMPETITION | HOME | OPP_001 | BACK_FOUR | BACK_FOUR | 4.0 | 3.0 | 3.0 | 2.0 | 5.0 | 5.0 | 34.0 | 28.0 | 5.0 | 5.0 | 41.0 | 59.0 | 11.0 | 8.0 | 1.0 | 3.0 | 12.0 | 7.0 | 0.78 | 0.44 | 2.0 | 0.0 | 42.0 | 58.0 | 0.0 | 0.0 | 2.0 | 3.0 | 9.0 | 7.0 | 6.0 | 2.0 | 4.0 | 5.0 | 6.0 | 5.0 | 21.0 | 13.0 | 24.0 | 22.0 | 15.0 | 12.0 | 20.0 | 22.0 | 2.01 | 1.82 | 1.0 | 3.0 |
| m_mt_585224623 | 1768058100 | COMPETITION | AWAY | OPP_002 |  |  | 5.0 | 4.0 | 2.0 | 1.0 | 6.0 | 6.0 | 17.0 | 17.0 | 8.0 | 2.0 | 56.0 | 66.0 | 12.0 | 20.0 | 0.0 | 0.0 | 11.0 | 8.0 | 0.34 | 0.15 | 0.0 | 7.0 | 54.0 | 46.0 | 0.0 | 0.0 | 3.0 | 6.0 | 14.0 | 7.0 | 8.0 | 4.0 | 6.0 | 3.0 | 6.0 | 6.0 | 16.0 | 9.0 | 22.0 | 19.0 | 20.0 | 13.0 | 29.0 | 26.0 | 2.28 | 0.39 | 1.0 | 4.0 |
| m_mt_626339864 | 1768757400 | COMPETITION | HOME | OPP_005 | BACK_FIVE | BACK_FOUR | 8.0 | 4.0 | 2.0 | 2.0 | 8.0 | 3.0 | 34.0 | 24.0 | 6.0 | 6.0 | 58.0 | 57.0 | 2.0 | 6.0 | 1.0 | 0.0 | 9.0 | 11.0 | 0.44 | 0.23 | 1.0 | 1.0 | 47.0 | 53.0 | 0.0 | 0.0 | 3.0 | 1.0 | 9.0 | 7.0 | 4.0 | 3.0 | 2.0 | 3.0 | 5.0 | 2.0 | 22.0 | 12.0 | 21.0 | 24.0 | 14.0 | 9.0 | 21.0 | 18.0 | 1.29 | 1.07 | 2.0 | 1.0 |
| m_mt_404778545 | 1769259600 | COMPETITION | AWAY | OPP_011 |  |  | 6.0 | 5.0 | 1.0 | 1.0 | 6.0 | 2.0 | 22.0 | 33.0 | 9.0 | 5.0 | 43.0 | 53.0 | 10.0 | 6.0 | 1.0 | 0.0 | 12.0 | 10.0 | 0.42 | 0.07 | 0.0 | 1.0 | 38.0 | 62.0 | 0.0 | 1.0 | 0.0 | 2.0 | 12.0 | 6.0 | 4.0 | 5.0 | 3.0 | 0.0 | 1.0 | 1.0 | 12.0 | 17.0 | 34.0 | 16.0 | 13.0 | 7.0 | 20.0 | 19.0 | 1.29 | 0.54 | 2.0 | 4.0 |
| m_mt_191006931 | 1769872500 | COMPETITION | HOME | OPP_016 |  |  | 6.0 | 4.0 | 3.0 | 1.0 | 3.0 | 4.0 | 24.0 | 21.0 | 6.0 | 4.0 | 40.0 | 71.0 | 11.0 | 8.0 | 2.0 | 0.0 | 16.0 | 6.0 | 0.45 | 0.35 | 3.0 | 2.0 | 37.0 | 63.0 | 0.0 | 0.0 | 3.0 | 2.0 | 8.0 | 5.0 | 3.0 | 1.0 | 4.0 | 3.0 | 2.0 | 3.0 | 29.0 | 17.0 | 20.0 | 33.0 | 10.0 | 8.0 | 21.0 | 24.0 | 1.11 | 0.95 | 2.0 | 3.0 |
| m_mt_010443139 | 1770563700 | COMPETITION | AWAY | OPP_012 |  |  | 7.0 | 2.0 | 4.0 | 0.0 | 3.0 | 4.0 | 18.0 | 21.0 | 1.0 | 4.0 | 62.0 | 47.0 | 10.0 | 7.0 | 1.0 | 2.0 | 12.0 | 14.0 | 0.72 | 0.18 | 3.0 | 1.0 | 46.0 | 54.0 | 0.0 | 0.0 | 0.0 | 3.0 | 12.0 | 6.0 | 9.0 | 7.0 | 4.0 | 1.0 | 4.0 | 6.0 | 11.0 | 9.0 | 18.0 | 14.0 | 16.0 | 12.0 | 22.0 | 18.0 | 2.09 | 0.44 | 2.0 | 3.0 |
| m_mt_979112734 | 1771176600 | COMPETITION | HOME | OPP_009 | BACK_FIVE | BACK_FOUR | 3.0 | 3.0 | 1.0 | 4.0 | 2.0 | 2.0 | 15.0 | 28.0 | 4.0 | 2.0 | 61.0 | 47.0 | 10.0 | 12.0 | 1.0 | 1.0 | 7.0 | 4.0 | 0.17 | 0.18 | 1.0 | 1.0 | 43.0 | 57.0 | 0.0 | 0.0 | 1.0 | 1.0 | 6.0 | 7.0 | 5.0 | 5.0 | 2.0 | 2.0 | 3.0 | 2.0 | 9.0 | 7.0 | 22.0 | 15.0 | 9.0 | 9.0 | 12.0 | 22.0 | 1.2 | 1.7 | 1.0 | 0.0 |
| m_mt_747995320 | 1771790400 | COMPETITION | AWAY | OPP_004 |  |  | 3.0 | 7.0 | 1.0 | 2.0 | 2.0 | 2.0 | 22.0 | 20.0 | 3.0 | 4.0 | 54.0 | 46.0 | 17.0 | 13.0 | 0.0 | 1.0 | 10.0 | 5.0 | 0.18 | 0.36 |  |  | 45.0 | 55.0 | 0.0 | 0.0 | 7.0 | 3.0 | 6.0 | 12.0 | 4.0 | 5.0 | 2.0 | 8.0 | 2.0 | 3.0 | 22.0 | 19.0 | 24.0 | 23.0 | 8.0 | 15.0 | 13.0 | 39.0 | 0.34 | 1.23 | 1.0 | 2.0 |
| m_mt_979112870 | 1772220600 | COMPETITION | HOME | OPP_010 |  |  | 4.0 | 7.0 | 4.0 | 4.0 | 2.0 | 6.0 | 19.0 | 29.0 | 5.0 | 7.0 | 39.0 | 56.0 | 9.0 | 8.0 | 1.0 | 1.0 | 10.0 | 11.0 | 0.3 | 0.63 | 3.0 | 2.0 | 34.0 | 66.0 | 0.0 | 0.0 | 4.0 | 4.0 | 8.0 | 11.0 | 4.0 | 8.0 | 5.0 | 5.0 | 3.0 | 8.0 | 15.0 | 8.0 | 25.0 | 30.0 | 11.0 | 19.0 | 23.0 | 30.0 | 0.91 | 1.92 | 1.0 | 1.0 |
| m_mt_363888242 | 1772896500 | COMPETITION | AWAY | OPP_006 |  |  | 4.0 | 1.0 | 1.0 | 1.0 | 7.0 | 3.0 | 20.0 | 53.0 | 12.0 | 5.0 | 74.0 | 65.0 | 14.0 | 11.0 | 0.0 | 0.0 | 9.0 | 11.0 | 0.17 | 0.14 | 1.0 | 0.0 | 55.0 | 45.0 | 0.0 | 1.0 | 4.0 | 6.0 | 4.0 | 5.0 | 1.0 | 2.0 | 6.0 | 4.0 | 10.0 | 4.0 | 16.0 | 12.0 | 23.0 | 25.0 | 14.0 | 9.0 | 23.0 | 15.0 | 1.31 | 0.73 | 2.0 | 1.0 |
| m_mt_979111308 | 1773689400 | COMPETITION | HOME | OPP_021 | BACK_FIVE | BACK_FOUR | 5.0 | 1.0 | 2.0 | 3.0 | 7.0 | 2.0 | 4.0 | 37.0 | 4.0 | 2.0 | 51.0 | 51.0 | 17.0 | 9.0 | 2.0 | 1.0 | 15.0 | 6.0 | 0.29 | 0.29 | 3.0 | 4.0 | 42.0 | 58.0 | 0.0 | 0.0 | 3.0 | 3.0 | 11.0 | 8.0 | 8.0 | 3.0 | 4.0 | 4.0 | 8.0 | 1.0 | 14.0 | 12.0 | 21.0 | 22.0 | 19.0 | 9.0 | 24.0 | 20.0 | 1.69 | 0.72 | 3.0 | 2.0 |
| m_mt_747999600 | 1774106100 | COMPETITION | AWAY | OPP_019 |  |  | 1.0 | 12.0 | 5.0 | 0.0 | 4.0 | 4.0 | 41.0 | 13.0 | 5.0 | 6.0 | 61.0 | 82.0 | 12.0 | 12.0 | 4.0 | 0.0 | 14.0 | 9.0 | 0.45 | 0.5 | 3.0 | 1.0 | 33.0 | 67.0 | 0.0 | 1.0 | 5.0 | 1.0 | 6.0 | 15.0 | 3.0 | 8.0 | 5.0 | 5.0 | 6.0 | 2.0 | 21.0 | 18.0 | 17.0 | 34.0 | 12.0 | 17.0 | 19.0 | 52.0 | 2.35 | 2.25 | 5.0 | 4.0 |
| m_mt_747999666 | 1774728000 | COMPETITION | HOME | OPP_008 |  |  | 3.0 | 5.0 | 2.0 | 0.0 | 5.0 | 3.0 | 31.0 | 41.0 | 6.0 | 8.0 | 68.0 | 50.0 | 12.0 | 16.0 | 1.0 | 1.0 | 11.0 | 5.0 | 0.25 | 0.37 | 3.0 | 1.0 | 37.0 | 63.0 | 0.0 | 1.0 | 4.0 | 3.0 | 9.0 | 8.0 | 2.0 | 4.0 | 4.0 | 6.0 | 2.0 | 5.0 | 6.0 | 13.0 | 21.0 | 11.0 | 11.0 | 13.0 | 21.0 | 24.0 | 0.67 | 1.55 | 4.0 | 6.0 |
| m_mt_404777464 | 1774976400 | COMPETITION | AWAY | OPP_015 |  |  | 4.0 | 8.0 | 1.0 | 5.0 | 3.0 | 3.0 | 28.0 | 30.0 | 3.0 | 9.0 | 68.0 | 50.0 | 12.0 | 9.0 | 1.0 | 1.0 | 15.0 | 11.0 | 0.12 | 0.32 | 0.0 | 2.0 | 60.0 | 40.0 | 0.0 | 0.0 | 5.0 | 2.0 | 4.0 | 9.0 | 3.0 | 5.0 | 3.0 | 5.0 | 5.0 | 4.0 | 16.0 | 8.0 | 16.0 | 24.0 | 9.0 | 13.0 | 12.0 | 26.0 |  |  | 4.0 | 1.0 |
| m_mt_252666278 | 1775312100 | COMPETITION | HOME | OPP_022 |  |  | 4.0 | 3.0 | 1.0 | 2.0 | 2.0 | 0.0 | 5.0 | 40.0 | 5.0 | 2.0 | 69.0 | 66.0 | 11.0 | 17.0 | 2.0 | 3.0 | 4.0 | 13.0 | 0.18 | 0.59 | 2.0 | 2.0 | 54.0 | 46.0 | 0.0 | 0.0 | 1.0 | 0.0 | 5.0 | 5.0 | 4.0 | 3.0 | 1.0 | 4.0 | 2.0 | 2.0 | 16.0 | 15.0 | 35.0 | 20.0 | 7.0 | 7.0 | 18.0 | 12.0 |  |  | 4.0 | 2.0 |
| m_mt_363888331 | 1775916900 | COMPETITION | AWAY | OPP_001 |  |  | 2.0 | 8.0 | 0.0 | 3.0 | 3.0 | 10.0 | 22.0 | 20.0 | 4.0 | 10.0 | 43.0 | 50.0 | 13.0 | 16.0 | 1.0 | 2.0 | 14.0 | 8.0 | 0.23 | 0.73 | 2.0 | 1.0 | 44.0 | 56.0 | 0.0 | 0.0 | 2.0 | 2.0 | 4.0 | 12.0 | 3.0 | 5.0 | 3.0 | 5.0 | 5.0 | 8.0 | 13.0 | 11.0 | 21.0 | 20.0 | 9.0 | 20.0 | 15.0 | 30.0 | 0.59 | 2.18 | 3.0 | 1.0 |
| m_mt_747995117 | 1776616200 | COMPETITION | HOME | OPP_003 |  |  | 7.0 | 9.0 | 1.0 | 2.0 | 2.0 | 5.0 | 33.0 | 23.0 | 3.0 | 6.0 | 51.0 | 65.0 | 18.0 | 10.0 | 4.0 | 1.0 | 15.0 | 6.0 | 0.65 | 0.28 |  |  | 27.0 | 73.0 | 0.0 | 0.0 | 3.0 | 2.0 | 8.0 | 8.0 | 4.0 | 6.0 | 6.0 | 4.0 | 4.0 | 7.0 | 9.0 | 15.0 | 27.0 | 25.0 | 12.0 | 15.0 | 18.0 | 20.0 | 1.89 | 1.89 | 2.0 | 3.0 |
| m_mt_252665672 | 1777055400 | COMPETITION | HOME | OPP_018 |  |  | 7.0 | 2.0 | 1.0 | 1.0 | 8.0 | 3.0 | 5.0 | 49.0 | 10.0 | 3.0 | 84.0 | 45.0 | 7.0 | 6.0 | 0.0 | 3.0 | 12.0 | 12.0 | 0.57 | 0.4 | 1.0 | 2.0 | 61.0 | 39.0 | 0.0 | 0.0 | 2.0 | 5.0 | 16.0 | 7.0 | 12.0 | 4.0 | 5.0 | 4.0 | 9.0 | 4.0 | 12.0 | 17.0 | 29.0 | 9.0 | 25.0 | 11.0 | 25.0 | 12.0 |  |  | 2.0 | 1.0 |

### Arm B — derived summaries (DERIVED_SUMMARY), HOME 240 + AWAY 240

HOME_TEAM (metric·side·window·venue = value [n, reliability]):

- accurate_crosses·FOR·ALL_PRIOR·ALL = 3.4 [n=30, HIGH]
- accurate_crosses·FOR·W5·ALL = 4.0 [n=5, LOW]
- accurate_crosses·FOR·W10·ALL = 3.3 [n=10, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·HOME = 4.3333 [n=15, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·AWAY = 2.4667 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·ALL = 3.8333 [n=30, HIGH]
- accurate_crosses·AGAINST·W5·ALL = 3.6 [n=5, LOW]
- accurate_crosses·AGAINST·W10·ALL = 3.6 [n=10, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·HOME = 2.7333 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·AWAY = 4.9333 [n=15, MEDIUM]
- big_chances·FOR·ALL_PRIOR·ALL = 2.5 [n=30, HIGH]
- big_chances·FOR·W5·ALL = 4.4 [n=5, LOW]
- big_chances·FOR·W10·ALL = 3.8 [n=10, MEDIUM]
- big_chances·FOR·ALL_PRIOR·HOME = 2.6 [n=15, MEDIUM]
- big_chances·FOR·ALL_PRIOR·AWAY = 2.4 [n=15, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·ALL = 2.7667 [n=30, HIGH]
- big_chances·AGAINST·W5·ALL = 3.0 [n=5, LOW]
- big_chances·AGAINST·W10·ALL = 2.4 [n=10, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·HOME = 1.9333 [n=15, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·AWAY = 3.6 [n=15, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·ALL = 3.7667 [n=30, HIGH]
- blocked_shots·FOR·W5·ALL = 3.0 [n=5, LOW]
- blocked_shots·FOR·W10·ALL = 2.9 [n=10, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·HOME = 3.9333 [n=15, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·AWAY = 3.6 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·ALL = 2.4333 [n=30, HIGH]
- blocked_shots·AGAINST·W5·ALL = 2.0 [n=5, LOW]
- blocked_shots·AGAINST·W10·ALL = 2.1 [n=10, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·HOME = 1.5333 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·AWAY = 3.3333 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·ALL = 22.7 [n=30, HIGH]
- clearances·FOR·W5·ALL = 21.2 [n=5, LOW]
- clearances·FOR·W10·ALL = 24.9 [n=10, MEDIUM]
- clearances·FOR·ALL_PRIOR·HOME = 19.8 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·AWAY = 25.6 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·ALL = 22.6333 [n=30, HIGH]
- clearances·AGAINST·W5·ALL = 24.2 [n=5, LOW]
- clearances·AGAINST·W10·ALL = 21.8 [n=10, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·HOME = 26.0667 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·AWAY = 19.2 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·ALL = 5.3333 [n=30, HIGH]
- corners·FOR·W5·ALL = 6.0 [n=5, LOW]
- corners·FOR·W10·ALL = 5.8 [n=10, MEDIUM]
- corners·FOR·ALL_PRIOR·HOME = 6.0667 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·AWAY = 4.6 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·ALL = 4.0333 [n=30, HIGH]
- corners·AGAINST·W5·ALL = 4.8 [n=5, LOW]
- corners·AGAINST·W10·ALL = 4.4 [n=10, MEDIUM]
- corners·AGAINST·ALL_PRIOR·HOME = 2.8 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·AWAY = 5.2667 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·ALL = 57.3667 [n=30, HIGH]
- final_third_entries·FOR·W5·ALL = 61.2 [n=5, LOW]
- final_third_entries·FOR·W10·ALL = 59.5 [n=10, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·HOME = 62.8 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·AWAY = 51.9333 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·ALL = 49.6 [n=30, HIGH]
- final_third_entries·AGAINST·W5·ALL = 46.8 [n=5, LOW]
- final_third_entries·AGAINST·W10·ALL = 51.5 [n=10, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·HOME = 48.8 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·AWAY = 50.4 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·ALL = 13.1667 [n=30, HIGH]
- fouls·FOR·W5·ALL = 13.0 [n=5, LOW]
- fouls·FOR·W10·ALL = 12.1 [n=10, MEDIUM]
- fouls·FOR·ALL_PRIOR·HOME = 13.0 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·AWAY = 13.3333 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·ALL = 14.8667 [n=30, HIGH]
- fouls·AGAINST·W5·ALL = 14.4 [n=5, LOW]
- fouls·AGAINST·W10·ALL = 13.7 [n=10, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·HOME = 13.8667 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·AWAY = 15.8667 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·ALL = 1.4667 [n=30, HIGH]
- goals·FOR·W5·ALL = 3.0 [n=5, LOW]
- goals·FOR·W10·ALL = 2.5 [n=10, MEDIUM]
- goals·FOR·ALL_PRIOR·HOME = 1.3333 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·AWAY = 1.6 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·ALL = 1.3 [n=30, HIGH]
- goals·AGAINST·W5·ALL = 1.0 [n=5, LOW]
- goals·AGAINST·W10·ALL = 0.8 [n=10, MEDIUM]
- goals·AGAINST·ALL_PRIOR·HOME = 1.2 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·AWAY = 1.4 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·ALL = 7.0333 [n=30, HIGH]
- interceptions·FOR·W5·ALL = 5.6 [n=5, LOW]
- interceptions·FOR·W10·ALL = 6.1 [n=10, MEDIUM]
- interceptions·FOR·ALL_PRIOR·HOME = 7.0667 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·AWAY = 7.0 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·ALL = 9.0333 [n=30, HIGH]
- interceptions·AGAINST·W5·ALL = 8.8 [n=5, LOW]
- interceptions·AGAINST·W10·ALL = 7.6 [n=10, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·HOME = 8.6 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·AWAY = 9.4667 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·ALL = 0.3648 [n=27, HIGH]
- npxg·FOR·W5·ALL = 0.504 [n=5, LOW]
- npxg·FOR·W10·ALL = 0.419 [n=10, MEDIUM]
- npxg·FOR·ALL_PRIOR·HOME = 0.3892 [n=13, MEDIUM]
- npxg·FOR·ALL_PRIOR·AWAY = 0.3421 [n=14, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·ALL = 0.3578 [n=27, HIGH]
- npxg·AGAINST·W5·ALL = 0.334 [n=5, LOW]
- npxg·AGAINST·W10·ALL = 0.265 [n=10, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·HOME = 0.2708 [n=13, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·AWAY = 0.4386 [n=14, MEDIUM]
- offsides·FOR·ALL_PRIOR·ALL = 2.0 [n=30, HIGH]
- offsides·FOR·W5·ALL = 2.0 [n=5, LOW]
- offsides·FOR·W10·ALL = 1.8 [n=10, MEDIUM]
- offsides·FOR·ALL_PRIOR·HOME = 2.0 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·AWAY = 2.0 [n=15, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·ALL = 1.9333 [n=30, HIGH]
- offsides·AGAINST·W5·ALL = 1.8 [n=5, LOW]
- offsides·AGAINST·W10·ALL = 2.1 [n=10, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·HOME = 1.3333 [n=15, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·AWAY = 2.5333 [n=15, MEDIUM]
- possession·FOR·ALL_PRIOR·ALL = 61.7333 [n=30, HIGH]
- possession·FOR·W5·ALL = 64.0 [n=5, LOW]
- possession·FOR·W10·ALL = 61.1 [n=10, MEDIUM]
- possession·FOR·ALL_PRIOR·HOME = 65.0 [n=15, MEDIUM]
- possession·FOR·ALL_PRIOR·AWAY = 58.4667 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·ALL = 38.2667 [n=30, HIGH]
- possession·AGAINST·W5·ALL = 36.0 [n=5, LOW]
- possession·AGAINST·W10·ALL = 38.9 [n=10, MEDIUM]
- possession·AGAINST·ALL_PRIOR·HOME = 35.0 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·AWAY = 41.5333 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·ALL = 0.0667 [n=30, HIGH]
- red_cards·FOR·W5·ALL = 0.0 [n=5, LOW]
- red_cards·FOR·W10·ALL = 0.0 [n=10, MEDIUM]
- red_cards·FOR·ALL_PRIOR·HOME = 0.0667 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·AWAY = 0.0667 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·ALL = 0.1 [n=30, HIGH]
- red_cards·AGAINST·W5·ALL = 0.2 [n=5, LOW]
- red_cards·AGAINST·W10·ALL = 0.1 [n=10, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·HOME = 0.1333 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·AWAY = 0.0667 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·ALL = 3.1379 [n=29, HIGH]
- saves·FOR·W5·ALL = 4.25 [n=4, LOW]
- saves·FOR·W10·ALL = 3.4444 [n=9, MEDIUM]
- saves·FOR·ALL_PRIOR·HOME = 1.7857 [n=14, MEDIUM]
- saves·FOR·ALL_PRIOR·AWAY = 4.4 [n=15, MEDIUM]
- saves·AGAINST·ALL_PRIOR·ALL = 3.3793 [n=29, HIGH]
- saves·AGAINST·W5·ALL = 4.0 [n=4, LOW]
- saves·AGAINST·W10·ALL = 3.5556 [n=9, MEDIUM]
- saves·AGAINST·ALL_PRIOR·HOME = 3.3571 [n=14, MEDIUM]
- saves·AGAINST·ALL_PRIOR·AWAY = 3.4 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·ALL = 8.0333 [n=30, HIGH]
- shots_inside_box·FOR·W5·ALL = 9.0 [n=5, LOW]
- shots_inside_box·FOR·W10·ALL = 7.7 [n=10, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·HOME = 9.0667 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·AWAY = 7.0 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·ALL = 7.7667 [n=30, HIGH]
- shots_inside_box·AGAINST·W5·ALL = 7.8 [n=5, LOW]
- shots_inside_box·AGAINST·W10·ALL = 6.2 [n=10, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·HOME = 5.8667 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·AWAY = 9.6667 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·ALL = 5.7667 [n=30, HIGH]
- shots_off_target·FOR·W5·ALL = 5.4 [n=5, LOW]
- shots_off_target·FOR·W10·ALL = 6.0 [n=10, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·HOME = 7.0 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·AWAY = 4.5333 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·ALL = 4.4333 [n=30, HIGH]
- shots_off_target·AGAINST·W5·ALL = 4.2 [n=5, LOW]
- shots_off_target·AGAINST·W10·ALL = 3.6 [n=10, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·HOME = 4.0667 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·AWAY = 4.8 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·ALL = 4.8 [n=30, HIGH]
- shots_on_target·FOR·W5·ALL = 6.2 [n=5, LOW]
- shots_on_target·FOR·W10·ALL = 5.6 [n=10, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·HOME = 4.5333 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·AWAY = 5.0667 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·ALL = 4.3667 [n=30, HIGH]
- shots_on_target·AGAINST·W5·ALL = 4.4 [n=5, LOW]
- shots_on_target·AGAINST·W10·ALL = 3.9 [n=10, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·HOME = 2.8667 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·AWAY = 5.8667 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·ALL = 6.3 [n=30, HIGH]
- shots_outside_box·FOR·W5·ALL = 5.6 [n=5, LOW]
- shots_outside_box·FOR·W10·ALL = 6.8 [n=10, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·HOME = 6.4 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·AWAY = 6.2 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·ALL = 3.4667 [n=30, HIGH]
- shots_outside_box·AGAINST·W5·ALL = 2.8 [n=5, LOW]
- shots_outside_box·AGAINST·W10·ALL = 3.4 [n=10, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·HOME = 2.6 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·AWAY = 4.3333 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·ALL = 14.7667 [n=30, HIGH]
- tackles·FOR·W5·ALL = 15.0 [n=5, LOW]
- tackles·FOR·W10·ALL = 15.2 [n=10, MEDIUM]
- tackles·FOR·ALL_PRIOR·HOME = 14.2667 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·AWAY = 15.2667 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·ALL = 18.8 [n=30, HIGH]
- tackles·AGAINST·W5·ALL = 17.4 [n=5, LOW]
- tackles·AGAINST·W10·ALL = 17.5 [n=10, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·HOME = 18.1333 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·AWAY = 19.4667 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·ALL = 19.5 [n=30, HIGH]
- throw_ins·FOR·W5·ALL = 17.0 [n=5, LOW]
- throw_ins·FOR·W10·ALL = 17.6 [n=10, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·HOME = 20.6667 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·AWAY = 18.3333 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·ALL = 21.1 [n=30, HIGH]
- throw_ins·AGAINST·W5·ALL = 21.4 [n=5, LOW]
- throw_ins·AGAINST·W10·ALL = 22.9 [n=10, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·HOME = 19.9333 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·AWAY = 22.2667 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·ALL = 14.3333 [n=30, HIGH]
- total_shots·FOR·W5·ALL = 14.6 [n=5, LOW]
- total_shots·FOR·W10·ALL = 14.5 [n=10, MEDIUM]
- total_shots·FOR·ALL_PRIOR·HOME = 15.4667 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·AWAY = 13.2 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·ALL = 11.2333 [n=30, HIGH]
- total_shots·AGAINST·W5·ALL = 10.6 [n=5, LOW]
- total_shots·AGAINST·W10·ALL = 9.6 [n=10, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·HOME = 8.4667 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·AWAY = 14.0 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·ALL = 22.1667 [n=30, HIGH]
- touches_in_box·FOR·W5·ALL = 24.0 [n=5, LOW]
- touches_in_box·FOR·W10·ALL = 20.9 [n=10, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·HOME = 24.2 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·AWAY = 20.1333 [n=15, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·ALL = 20.0333 [n=30, HIGH]
- touches_in_box·AGAINST·W5·ALL = 19.6 [n=5, LOW]
- touches_in_box·AGAINST·W10·ALL = 18.1 [n=10, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·HOME = 15.4667 [n=15, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·AWAY = 24.6 [n=15, MEDIUM]
- xg·FOR·ALL_PRIOR·ALL = 1.2632 [n=28, HIGH]
- xg·FOR·W5·ALL = 1.14 [n=3, LOW]
- xg·FOR·W10·ALL = 1.1462 [n=8, MEDIUM]
- xg·FOR·ALL_PRIOR·HOME = 1.2377 [n=13, MEDIUM]
- xg·FOR·ALL_PRIOR·AWAY = 1.2853 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·ALL = 1.4293 [n=28, HIGH]
- xg·AGAINST·W5·ALL = 1.0533 [n=3, LOW]
- xg·AGAINST·W10·ALL = 1.0362 [n=8, MEDIUM]
- xg·AGAINST·ALL_PRIOR·HOME = 0.9708 [n=13, MEDIUM]
- xg·AGAINST·ALL_PRIOR·AWAY = 1.8267 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·ALL = 2.7 [n=30, HIGH]
- yellow_cards·FOR·W5·ALL = 1.8 [n=5, LOW]
- yellow_cards·FOR·W10·ALL = 2.6 [n=10, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·HOME = 2.6 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·AWAY = 2.8 [n=15, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·ALL = 2.9333 [n=30, HIGH]
- yellow_cards·AGAINST·W5·ALL = 4.0 [n=5, LOW]
- yellow_cards·AGAINST·W10·ALL = 3.3 [n=10, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·HOME = 3.2667 [n=15, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·AWAY = 2.6 [n=15, MEDIUM]

AWAY_TEAM:

- accurate_crosses·FOR·ALL_PRIOR·ALL = 4.5667 [n=30, HIGH]
- accurate_crosses·FOR·W5·ALL = 4.8 [n=5, LOW]
- accurate_crosses·FOR·W10·ALL = 4.1 [n=10, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·HOME = 5.6875 [n=16, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·AWAY = 3.2857 [n=14, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·ALL = 5.0333 [n=30, HIGH]
- accurate_crosses·AGAINST·W5·ALL = 6.0 [n=5, LOW]
- accurate_crosses·AGAINST·W10·ALL = 5.6 [n=10, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·HOME = 4.0625 [n=16, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·AWAY = 6.1429 [n=14, MEDIUM]
- big_chances·FOR·ALL_PRIOR·ALL = 2.0 [n=30, HIGH]
- big_chances·FOR·W5·ALL = 0.8 [n=5, LOW]
- big_chances·FOR·W10·ALL = 1.8 [n=10, MEDIUM]
- big_chances·FOR·ALL_PRIOR·HOME = 2.0625 [n=16, MEDIUM]
- big_chances·FOR·ALL_PRIOR·AWAY = 1.9286 [n=14, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·ALL = 2.1 [n=30, HIGH]
- big_chances·AGAINST·W5·ALL = 2.6 [n=5, LOW]
- big_chances·AGAINST·W10·ALL = 2.1 [n=10, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·HOME = 2.1875 [n=16, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·AWAY = 2.0 [n=14, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·ALL = 3.6667 [n=30, HIGH]
- blocked_shots·FOR·W5·ALL = 3.6 [n=5, LOW]
- blocked_shots·FOR·W10·ALL = 4.3 [n=10, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·HOME = 4.0625 [n=16, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·AWAY = 3.2143 [n=14, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·ALL = 3.8667 [n=30, HIGH]
- blocked_shots·AGAINST·W5·ALL = 4.2 [n=5, LOW]
- blocked_shots·AGAINST·W10·ALL = 3.9 [n=10, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·HOME = 3.625 [n=16, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·AWAY = 4.1429 [n=14, MEDIUM]
- clearances·FOR·ALL_PRIOR·ALL = 22.7 [n=30, HIGH]
- clearances·FOR·W5·ALL = 18.6 [n=5, LOW]
- clearances·FOR·W10·ALL = 20.8 [n=10, MEDIUM]
- clearances·FOR·ALL_PRIOR·HOME = 21.5 [n=16, MEDIUM]
- clearances·FOR·ALL_PRIOR·AWAY = 24.0714 [n=14, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·ALL = 27.8667 [n=30, HIGH]
- clearances·AGAINST·W5·ALL = 32.4 [n=5, LOW]
- clearances·AGAINST·W10·ALL = 33.5 [n=10, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·HOME = 30.875 [n=16, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·AWAY = 24.4286 [n=14, MEDIUM]
- corners·FOR·ALL_PRIOR·ALL = 5.3333 [n=30, HIGH]
- corners·FOR·W5·ALL = 5.0 [n=5, LOW]
- corners·FOR·W10·ALL = 5.7 [n=10, MEDIUM]
- corners·FOR·ALL_PRIOR·HOME = 5.9375 [n=16, MEDIUM]
- corners·FOR·ALL_PRIOR·AWAY = 4.6429 [n=14, MEDIUM]
- corners·AGAINST·ALL_PRIOR·ALL = 5.0333 [n=30, HIGH]
- corners·AGAINST·W5·ALL = 6.0 [n=5, LOW]
- corners·AGAINST·W10·ALL = 5.8 [n=10, MEDIUM]
- corners·AGAINST·ALL_PRIOR·HOME = 4.4375 [n=16, MEDIUM]
- corners·AGAINST·ALL_PRIOR·AWAY = 5.7143 [n=14, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·ALL = 55.4 [n=30, HIGH]
- final_third_entries·FOR·W5·ALL = 63.0 [n=5, LOW]
- final_third_entries·FOR·W10·ALL = 60.8 [n=10, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·HOME = 55.0625 [n=16, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·AWAY = 55.7857 [n=14, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·ALL = 56.8333 [n=30, HIGH]
- final_third_entries·AGAINST·W5·ALL = 55.2 [n=5, LOW]
- final_third_entries·AGAINST·W10·ALL = 58.0 [n=10, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·HOME = 55.9375 [n=16, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·AWAY = 57.8571 [n=14, MEDIUM]
- fouls·FOR·ALL_PRIOR·ALL = 11.5 [n=30, HIGH]
- fouls·FOR·W5·ALL = 12.2 [n=5, LOW]
- fouls·FOR·W10·ALL = 12.5 [n=10, MEDIUM]
- fouls·FOR·ALL_PRIOR·HOME = 10.3125 [n=16, MEDIUM]
- fouls·FOR·ALL_PRIOR·AWAY = 12.8571 [n=14, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·ALL = 11.1333 [n=30, HIGH]
- fouls·AGAINST·W5·ALL = 11.6 [n=5, LOW]
- fouls·AGAINST·W10·ALL = 11.4 [n=10, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·HOME = 9.375 [n=16, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·AWAY = 13.1429 [n=14, MEDIUM]
- goals·FOR·ALL_PRIOR·ALL = 1.1333 [n=30, HIGH]
- goals·FOR·W5·ALL = 1.6 [n=5, LOW]
- goals·FOR·W10·ALL = 1.6 [n=10, MEDIUM]
- goals·FOR·ALL_PRIOR·HOME = 1.25 [n=16, MEDIUM]
- goals·FOR·ALL_PRIOR·AWAY = 1.0 [n=14, MEDIUM]
- goals·AGAINST·ALL_PRIOR·ALL = 1.1667 [n=30, HIGH]
- goals·AGAINST·W5·ALL = 2.0 [n=5, LOW]
- goals·AGAINST·W10·ALL = 1.3 [n=10, MEDIUM]
- goals·AGAINST·ALL_PRIOR·HOME = 1.4375 [n=16, MEDIUM]
- goals·AGAINST·ALL_PRIOR·AWAY = 0.8571 [n=14, MEDIUM]
- interceptions·FOR·ALL_PRIOR·ALL = 10.4 [n=30, HIGH]
- interceptions·FOR·W5·ALL = 12.0 [n=5, LOW]
- interceptions·FOR·W10·ALL = 11.9 [n=10, MEDIUM]
- interceptions·FOR·ALL_PRIOR·HOME = 10.5 [n=16, MEDIUM]
- interceptions·FOR·ALL_PRIOR·AWAY = 10.2857 [n=14, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·ALL = 8.4 [n=30, HIGH]
- interceptions·AGAINST·W5·ALL = 10.0 [n=5, LOW]
- interceptions·AGAINST·W10·ALL = 9.2 [n=10, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·HOME = 8.125 [n=16, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·AWAY = 8.7143 [n=14, MEDIUM]
- npxg·FOR·ALL_PRIOR·ALL = 0.3796 [n=27, HIGH]
- npxg·FOR·W5·ALL = 0.35 [n=5, LOW]
- npxg·FOR·W10·ALL = 0.321 [n=10, MEDIUM]
- npxg·FOR·ALL_PRIOR·HOME = 0.414 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·AWAY = 0.3367 [n=12, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·ALL = 0.3619 [n=27, HIGH]
- npxg·AGAINST·W5·ALL = 0.464 [n=5, LOW]
- npxg·AGAINST·W10·ALL = 0.425 [n=10, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·HOME = 0.3733 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·AWAY = 0.3475 [n=12, MEDIUM]
- offsides·FOR·ALL_PRIOR·ALL = 1.6071 [n=28, HIGH]
- offsides·FOR·W5·ALL = 1.25 [n=4, LOW]
- offsides·FOR·W10·ALL = 2.0 [n=9, MEDIUM]
- offsides·FOR·ALL_PRIOR·HOME = 2.0 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·AWAY = 1.1538 [n=13, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·ALL = 1.75 [n=28, HIGH]
- offsides·AGAINST·W5·ALL = 1.75 [n=4, LOW]
- offsides·AGAINST·W10·ALL = 1.6667 [n=9, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·HOME = 1.6667 [n=15, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·AWAY = 1.8462 [n=13, MEDIUM]
- possession·FOR·ALL_PRIOR·ALL = 43.3667 [n=30, HIGH]
- possession·FOR·W5·ALL = 49.2 [n=5, LOW]
- possession·FOR·W10·ALL = 44.7 [n=10, MEDIUM]
- possession·FOR·ALL_PRIOR·HOME = 41.9375 [n=16, MEDIUM]
- possession·FOR·ALL_PRIOR·AWAY = 45.0 [n=14, MEDIUM]
- possession·AGAINST·ALL_PRIOR·ALL = 56.6333 [n=30, HIGH]
- possession·AGAINST·W5·ALL = 50.8 [n=5, LOW]
- possession·AGAINST·W10·ALL = 55.3 [n=10, MEDIUM]
- possession·AGAINST·ALL_PRIOR·HOME = 58.0625 [n=16, MEDIUM]
- possession·AGAINST·ALL_PRIOR·AWAY = 55.0 [n=14, MEDIUM]
- red_cards·FOR·ALL_PRIOR·ALL = 0.0667 [n=30, HIGH]
- red_cards·FOR·W5·ALL = 0.0 [n=5, LOW]
- red_cards·FOR·W10·ALL = 0.0 [n=10, MEDIUM]
- red_cards·FOR·ALL_PRIOR·HOME = 0.0 [n=16, MEDIUM]
- red_cards·FOR·ALL_PRIOR·AWAY = 0.1429 [n=14, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·ALL = 0.2 [n=30, HIGH]
- red_cards·AGAINST·W5·ALL = 0.0 [n=5, LOW]
- red_cards·AGAINST·W10·ALL = 0.3 [n=10, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·HOME = 0.0625 [n=16, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·AWAY = 0.3571 [n=14, MEDIUM]
- saves·FOR·ALL_PRIOR·ALL = 3.0 [n=30, HIGH]
- saves·FOR·W5·ALL = 2.6 [n=5, LOW]
- saves·FOR·W10·ALL = 3.3 [n=10, MEDIUM]
- saves·FOR·ALL_PRIOR·HOME = 2.8125 [n=16, MEDIUM]
- saves·FOR·ALL_PRIOR·AWAY = 3.2143 [n=14, MEDIUM]
- saves·AGAINST·ALL_PRIOR·ALL = 3.2667 [n=30, HIGH]
- saves·AGAINST·W5·ALL = 2.2 [n=5, LOW]
- saves·AGAINST·W10·ALL = 2.8 [n=10, MEDIUM]
- saves·AGAINST·ALL_PRIOR·HOME = 3.0625 [n=16, MEDIUM]
- saves·AGAINST·ALL_PRIOR·AWAY = 3.5 [n=14, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·ALL = 8.3667 [n=30, HIGH]
- shots_inside_box·FOR·W5·ALL = 7.4 [n=5, LOW]
- shots_inside_box·FOR·W10·ALL = 7.5 [n=10, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·HOME = 9.375 [n=16, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·AWAY = 7.2143 [n=14, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·ALL = 8.3333 [n=30, HIGH]
- shots_inside_box·AGAINST·W5·ALL = 8.2 [n=5, LOW]
- shots_inside_box·AGAINST·W10·ALL = 8.8 [n=10, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·HOME = 7.25 [n=16, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·AWAY = 9.5714 [n=14, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·ALL = 5.2333 [n=30, HIGH]
- shots_off_target·FOR·W5·ALL = 5.2 [n=5, LOW]
- shots_off_target·FOR·W10·ALL = 4.4 [n=10, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·HOME = 5.8125 [n=16, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·AWAY = 4.5714 [n=14, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·ALL = 4.7333 [n=30, HIGH]
- shots_off_target·AGAINST·W5·ALL = 4.6 [n=5, LOW]
- shots_off_target·AGAINST·W10·ALL = 4.8 [n=10, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·HOME = 3.6875 [n=16, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·AWAY = 5.9286 [n=14, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·ALL = 4.2 [n=30, HIGH]
- shots_on_target·FOR·W5·ALL = 3.6 [n=5, LOW]
- shots_on_target·FOR·W10·ALL = 4.2 [n=10, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·HOME = 4.0625 [n=16, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·AWAY = 4.3571 [n=14, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·ALL = 4.1333 [n=30, HIGH]
- shots_on_target·AGAINST·W5·ALL = 4.4 [n=5, LOW]
- shots_on_target·AGAINST·W10·ALL = 4.6 [n=10, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·HOME = 4.25 [n=16, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·AWAY = 4.0 [n=14, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·ALL = 4.7333 [n=30, HIGH]
- shots_outside_box·FOR·W5·ALL = 5.0 [n=5, LOW]
- shots_outside_box·FOR·W10·ALL = 5.4 [n=10, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·HOME = 4.5625 [n=16, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·AWAY = 4.9286 [n=14, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·ALL = 4.4 [n=30, HIGH]
- shots_outside_box·AGAINST·W5·ALL = 5.0 [n=5, LOW]
- shots_outside_box·AGAINST·W10·ALL = 4.5 [n=10, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·HOME = 4.3125 [n=16, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·AWAY = 4.5 [n=14, MEDIUM]
- tackles·FOR·ALL_PRIOR·ALL = 15.2667 [n=30, HIGH]
- tackles·FOR·W5·ALL = 13.2 [n=5, LOW]
- tackles·FOR·W10·ALL = 13.8 [n=10, MEDIUM]
- tackles·FOR·ALL_PRIOR·HOME = 14.9375 [n=16, MEDIUM]
- tackles·FOR·ALL_PRIOR·AWAY = 15.6429 [n=14, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·ALL = 13.2667 [n=30, HIGH]
- tackles·AGAINST·W5·ALL = 13.2 [n=5, LOW]
- tackles·AGAINST·W10·ALL = 12.9 [n=10, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·HOME = 13.3125 [n=16, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·AWAY = 13.2143 [n=14, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·ALL = 23.7 [n=30, HIGH]
- throw_ins·FOR·W5·ALL = 25.6 [n=5, LOW]
- throw_ins·FOR·W10·ALL = 23.5 [n=10, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·HOME = 24.625 [n=16, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·AWAY = 22.6429 [n=14, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·ALL = 21.2 [n=30, HIGH]
- throw_ins·AGAINST·W5·ALL = 19.6 [n=5, LOW]
- throw_ins·AGAINST·W10·ALL = 22.0 [n=10, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·HOME = 20.9375 [n=16, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·AWAY = 21.5 [n=14, MEDIUM]
- total_shots·FOR·ALL_PRIOR·ALL = 13.1 [n=30, HIGH]
- total_shots·FOR·W5·ALL = 12.4 [n=5, LOW]
- total_shots·FOR·W10·ALL = 12.9 [n=10, MEDIUM]
- total_shots·FOR·ALL_PRIOR·HOME = 13.9375 [n=16, MEDIUM]
- total_shots·FOR·ALL_PRIOR·AWAY = 12.1429 [n=14, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·ALL = 12.7333 [n=30, HIGH]
- total_shots·AGAINST·W5·ALL = 13.2 [n=5, LOW]
- total_shots·AGAINST·W10·ALL = 13.3 [n=10, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·HOME = 11.5625 [n=16, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·AWAY = 14.0714 [n=14, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·ALL = 20.3333 [n=30, HIGH]
- touches_in_box·FOR·W5·ALL = 17.6 [n=5, LOW]
- touches_in_box·FOR·W10·ALL = 19.8 [n=10, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·HOME = 22.4375 [n=16, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·AWAY = 17.9286 [n=14, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·ALL = 23.4667 [n=30, HIGH]
- touches_in_box·AGAINST·W5·ALL = 20.0 [n=5, LOW]
- touches_in_box·AGAINST·W10·ALL = 24.1 [n=10, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·HOME = 20.25 [n=16, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·AWAY = 27.1429 [n=14, MEDIUM]
- xg·FOR·ALL_PRIOR·ALL = 1.3896 [n=26, HIGH]
- xg·FOR·W5·ALL = 1.24 [n=2, LOW]
- xg·FOR·W10·ALL = 1.3443 [n=7, LOW]
- xg·FOR·ALL_PRIOR·HOME = 1.3429 [n=14, MEDIUM]
- xg·FOR·ALL_PRIOR·AWAY = 1.4442 [n=12, MEDIUM]
- xg·AGAINST·ALL_PRIOR·ALL = 1.4227 [n=26, HIGH]
- xg·AGAINST·W5·ALL = 2.035 [n=2, LOW]
- xg·AGAINST·W10·ALL = 1.6057 [n=7, LOW]
- xg·AGAINST·ALL_PRIOR·HOME = 1.4936 [n=14, MEDIUM]
- xg·AGAINST·ALL_PRIOR·AWAY = 1.34 [n=12, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·ALL = 2.3103 [n=29, HIGH]
- yellow_cards·FOR·W5·ALL = 3.0 [n=5, LOW]
- yellow_cards·FOR·W10·ALL = 3.0 [n=10, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·HOME = 2.0667 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·AWAY = 2.5714 [n=14, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·ALL = 2.1724 [n=29, HIGH]
- yellow_cards·AGAINST·W5·ALL = 1.6 [n=5, LOW]
- yellow_cards·AGAINST·W10·ALL = 2.2 [n=10, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·HOME = 1.8667 [n=15, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·AWAY = 2.5 [n=14, MEDIUM]

### Arm B — opponent-profile context (deterministic bands)

```json
{
 "axes": {
  "accurate_crosses_for": {
   "AWAY": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "corners_against": {
   "AWAY": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  },
  "corners_for": {
   "AWAY": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   },
   "HOME": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  },
  "goals_against": {
   "AWAY": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "goals_for": {
   "AWAY": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   },
   "HOME": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "possession_for": {
   "AWAY": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   },
   "HOME": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "shots_on_target_against": {
   "AWAY": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "shots_on_target_for": {
   "AWAY": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   },
   "HOME": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  }
 },
 "similarity_version": "opponent_similarity_v1_pending"
}
```

---

## mt_010444904

- PIT-safe matches available: **70**; match rows included (both teams): **44**; omitted: **26** (reason: `frozen_history_policy(max_matches_per_team=30)`); UNEXPLAINED_OMISSION: **0**.
- Metric cell exposure rate (non-null of serialized): **0.9451**; derived summaries: **476**.
- Availability map: `{"expected_formation": "UNAVAILABLE", "formation": "LOW_COVERAGE", "half_time_state": "UNAVAILABLE", "injuries": "UNAVAILABLE", "lineup": "PIT_UNSAFE", "opponent_profile": "AVAILABLE", "recent_vs_long": "AVAILABLE", "red_cards": "AVAILABLE", "temporal_event_state": "UNAVAILABLE", "venue": "AVAILABLE", "xg": "AVAILABLE"}`
- Arm A packet hash: `3a464720dfbad42a378ac07d7339eb5624db9d58de5276ca5a6a7cd89ebde1f4`
- Arm B packet hash: `0dbaba57c287ad070db1e9cd4ad15a6b15b02cdb57a4b845de376358a1504444`

### Arm A — frozen V3 compressed evidence (all items)

76 unconditional shrunk scalar items (venue=ALL, window=ALL_PRIOR):

| id | metric | value | n | reliability |
|---|---|---|---|---|
| HOME_ATK_corners_406027 | corners_for | 4.03 | 56 | HIGH |
| HOME_DEF_corners_7cfac3 | corners_against | 4.9816 | 56 | HIGH |
| HOME_ATK_accurate_crosses_c28b9e | accurate_crosses_for | 4.6298 | 56 | HIGH |
| HOME_DEF_accurate_crosses_81ffb5 | accurate_crosses_against | 4.7266 | 56 | HIGH |
| HOME_ATK_total_shots_808ac9 | total_shots_for | 10.9365 | 56 | HIGH |
| HOME_DEF_total_shots_c0e347 | total_shots_against | 12.3075 | 56 | HIGH |
| HOME_ATK_shots_on_target_e955e0 | shots_on_target_for | 3.6576 | 56 | HIGH |
| HOME_DEF_shots_on_target_8a3812 | shots_on_target_against | 3.7867 | 56 | HIGH |
| HOME_ATK_shots_off_target_11e91f | shots_off_target_for | 4.824 | 56 | HIGH |
| HOME_DEF_shots_off_target_26031c | shots_off_target_against | 5.3562 | 56 | HIGH |
| HOME_ATK_blocked_shots_5198f8 | blocked_shots_for | 2.4549 | 56 | HIGH |
| HOME_DEF_blocked_shots_09c3c4 | blocked_shots_against | 3.1646 | 56 | HIGH |
| HOME_ATK_shots_inside_box_cf538d | shots_inside_box_for | 7.0892 | 56 | HIGH |
| HOME_DEF_shots_inside_box_e6b28d | shots_inside_box_against | 7.9763 | 56 | HIGH |
| HOME_ATK_touches_in_box_759ed8 | touches_in_box_for | 19.8503 | 56 | HIGH |
| HOME_DEF_touches_in_box_94cd98 | touches_in_box_against | 20.4471 | 56 | HIGH |
| HOME_ATK_final_third_entries_5aa0be | final_third_entries_for | 55.2213 | 56 | HIGH |
| HOME_DEF_final_third_entries_4a40ef | final_third_entries_against | 53.3503 | 56 | HIGH |
| HOME_ATK_possession_190f3f | possession_for | 48.4032 | 56 | HIGH |
| HOME_DEF_possession_f8ada9 | possession_against | 51.5968 | 56 | HIGH |
| HOME_ATK_tackles_65b6c1 | tackles_for | 15.3795 | 56 | HIGH |
| HOME_DEF_tackles_e3c85e | tackles_against | 15.3312 | 56 | HIGH |
| HOME_ATK_fouls_8107c6 | fouls_for | 13.9893 | 56 | HIGH |
| HOME_DEF_fouls_b6d53c | fouls_against | 14.2473 | 56 | HIGH |
| HOME_ATK_yellow_cards_80b7a4 | yellow_cards_for | 2.7116 | 54 | HIGH |
| HOME_DEF_yellow_cards_8ee8aa | yellow_cards_against | 2.3283 | 54 | HIGH |
| HOME_ATK_clearances_ec2e18 | clearances_for | 23.3256 | 56 | HIGH |
| HOME_DEF_clearances_6d3f4c | clearances_against | 21.9063 | 56 | HIGH |
| HOME_ATK_interceptions_967965 | interceptions_for | 8.0497 | 56 | HIGH |
| HOME_DEF_interceptions_c82020 | interceptions_against | 7.4529 | 56 | HIGH |
| HOME_ATK_goals_08b15b | goals_for | 1.1873 | 56 | HIGH |
| HOME_DEF_goals_d53fdd | goals_against | 1.1712 | 56 | HIGH |
| HOME_ATK_throw_ins_b24629 | throw_ins_for | 19.8147 | 56 | HIGH |
| HOME_DEF_throw_ins_208262 | throw_ins_against | 20.6695 | 56 | HIGH |
| HOME_ATK_big_chances_8a9e2f | big_chances_for | 1.647 | 55 | HIGH |
| HOME_DEF_big_chances_885151 | big_chances_against | 2.3519 | 55 | HIGH |
| HOME_ATK_saves_6bda8d | saves_for | 2.6582 | 55 | HIGH |
| HOME_DEF_saves_19ae14 | saves_against | 2.4451 | 55 | HIGH |
| AWAY_ATK_corners_ca1538 | corners_for | 4.143 | 14 | MEDIUM |
| AWAY_DEF_corners_598e33 | corners_against | 4.393 | 14 | MEDIUM |
| AWAY_ATK_accurate_crosses_005290 | accurate_crosses_for | 3.3524 | 14 | MEDIUM |
| AWAY_DEF_accurate_crosses_287e9c | accurate_crosses_against | 4.7524 | 14 | MEDIUM |
| AWAY_ATK_total_shots_004f7a | total_shots_for | 11.4031 | 14 | MEDIUM |
| AWAY_DEF_total_shots_403d28 | total_shots_against | 12.9031 | 14 | MEDIUM |
| AWAY_ATK_shots_on_target_9afd02 | shots_on_target_for | 3.9886 | 14 | MEDIUM |
| AWAY_DEF_shots_on_target_dcda5e | shots_on_target_against | 4.2886 | 14 | MEDIUM |
| AWAY_ATK_shots_off_target_b83815 | shots_off_target_for | 4.7043 | 14 | MEDIUM |
| AWAY_DEF_shots_off_target_5fe2d0 | shots_off_target_against | 5.5043 | 14 | MEDIUM |
| AWAY_ATK_blocked_shots_93d965 | blocked_shots_for | 2.7101 | 14 | MEDIUM |
| AWAY_DEF_blocked_shots_97ef03 | blocked_shots_against | 3.1101 | 14 | MEDIUM |
| AWAY_ATK_shots_inside_box_567ee5 | shots_inside_box_for | 6.7266 | 14 | MEDIUM |
| AWAY_DEF_shots_inside_box_446c80 | shots_inside_box_against | 8.4766 | 14 | MEDIUM |
| AWAY_ATK_touches_in_box_2c76ca | touches_in_box_for | 18.786 | 14 | MEDIUM |
| AWAY_DEF_touches_in_box_319da5 | touches_in_box_against | 22.086 | 14 | MEDIUM |
| AWAY_ATK_final_third_entries_5a0987 | final_third_entries_for | 48.886 | 14 | MEDIUM |
| AWAY_DEF_final_third_entries_ed75cd | final_third_entries_against | 57.486 | 14 | MEDIUM |
| AWAY_ATK_possession_82105a | possession_for | 47.8 | 14 | MEDIUM |
| AWAY_DEF_possession_012ecc | possession_against | 52.2 | 14 | MEDIUM |
| AWAY_ATK_tackles_0865bc | tackles_for | 17.9766 | 14 | MEDIUM |
| AWAY_DEF_tackles_3e6a7d | tackles_against | 15.2266 | 14 | MEDIUM |
| AWAY_ATK_fouls_97bf91 | fouls_for | 13.1756 | 13 | MEDIUM |
| AWAY_DEF_fouls_94f7aa | fouls_against | 12.2282 | 13 | MEDIUM |
| AWAY_ATK_yellow_cards_120c77 | yellow_cards_for | 1.6349 | 14 | MEDIUM |
| AWAY_DEF_yellow_cards_367397 | yellow_cards_against | 2.4849 | 14 | MEDIUM |
| AWAY_ATK_clearances_74617f | clearances_for | 25.1594 | 14 | MEDIUM |
| AWAY_DEF_clearances_8bdc80 | clearances_against | 21.2094 | 14 | MEDIUM |
| AWAY_ATK_interceptions_404e22 | interceptions_for | 8.5041 | 14 | MEDIUM |
| AWAY_DEF_interceptions_4be11b | interceptions_against | 7.7541 | 14 | MEDIUM |
| AWAY_ATK_goals_5d2c6a | goals_for | 1.1807 | 14 | MEDIUM |
| AWAY_DEF_goals_4ad3b7 | goals_against | 1.3307 | 14 | MEDIUM |
| AWAY_ATK_throw_ins_64d189 | throw_ins_for | 18.9256 | 14 | MEDIUM |
| AWAY_DEF_throw_ins_35916f | throw_ins_against | 20.4756 | 14 | MEDIUM |
| AWAY_ATK_big_chances_065222 | big_chances_for | 1.4733 | 14 | MEDIUM |
| AWAY_DEF_big_chances_d5f920 | big_chances_against | 2.3233 | 14 | MEDIUM |
| AWAY_ATK_saves_50b33b | saves_for | 2.8075 | 14 | MEDIUM |
| AWAY_DEF_saves_bf5cbb | saves_against | 2.8575 | 14 | MEDIUM |

### Arm B — HOME_TEAM match-level matrix (30 rows × 55 cols)

Columns: `match_alias, kickoff_unix, competition, venue, opponent_alias, own_formation_family, opponent_formation_family, accurate_crosses_for, accurate_crosses_against, big_chances_for, big_chances_against, blocked_shots_for, blocked_shots_against, clearances_for, clearances_against, corners_for, corners_against, final_third_entries_for, final_third_entries_against, fouls_for, fouls_against, goals_for, goals_against, interceptions_for, interceptions_against, npxg_for, npxg_against, offsides_for, offsides_against, possession_for, possession_against, red_cards_for, red_cards_against, saves_for, saves_against, shots_inside_box_for, shots_inside_box_against, shots_off_target_for, shots_off_target_against, shots_on_target_for, shots_on_target_against, shots_outside_box_for, shots_outside_box_against, tackles_for, tackles_against, throw_ins_for, throw_ins_against, total_shots_for, total_shots_against, touches_in_box_for, touches_in_box_against, xg_for, xg_against, yellow_cards_for, yellow_cards_against`

| match_alias | kickoff_unix | competition | venue | opponent_alias | own_formation_family | opponent_formation_family | accurate_crosses_for | accurate_crosses_against | big_chances_for | big_chances_against | blocked_shots_for | blocked_shots_against | clearances_for | clearances_against | corners_for | corners_against | final_third_entries_for | final_third_entries_against | fouls_for | fouls_against | goals_for | goals_against | interceptions_for | interceptions_against | npxg_for | npxg_against | offsides_for | offsides_against | possession_for | possession_against | red_cards_for | red_cards_against | saves_for | saves_against | shots_inside_box_for | shots_inside_box_against | shots_off_target_for | shots_off_target_against | shots_on_target_for | shots_on_target_against | shots_outside_box_for | shots_outside_box_against | tackles_for | tackles_against | throw_ins_for | throw_ins_against | total_shots_for | total_shots_against | touches_in_box_for | touches_in_box_against | xg_for | xg_against | yellow_cards_for | yellow_cards_against |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| m_mt_408750510 | 1739640600 | COMPETITION | AWAY | OPP_001 |  |  | 4.0 | 6.0 | 7.0 | 2.0 | 3.0 | 6.0 | 55.0 | 15.0 | 3.0 | 5.0 | 57.0 | 67.0 | 13.0 | 21.0 | 3.0 | 2.0 | 11.0 | 8.0 |  |  | 4.0 | 2.0 | 32.0 | 68.0 | 0.0 | 0.0 | 0.0 | 6.0 | 14.0 | 8.0 | 4.0 | 2.0 | 9.0 | 3.0 | 2.0 | 3.0 | 17.0 | 13.0 | 18.0 | 34.0 | 16.0 | 11.0 | 28.0 | 17.0 |  |  | 5.0 | 3.0 |
| m_mt_584278736 | 1740340800 | COMPETITION | HOME | OPP_002 |  |  | 3.0 | 5.0 | 1.0 | 3.0 | 2.0 | 0.0 | 29.0 | 17.0 | 6.0 | 3.0 | 64.0 | 52.0 | 7.0 | 16.0 | 0.0 | 0.0 | 15.0 | 8.0 |  |  | 2.0 | 4.0 | 45.0 | 55.0 | 0.0 | 0.0 | 0.0 | 4.0 | 8.0 | 7.0 | 5.0 | 8.0 | 4.0 | 0.0 | 3.0 | 1.0 | 17.0 | 19.0 | 16.0 | 18.0 | 11.0 | 8.0 | 17.0 | 17.0 |  |  | 1.0 | 1.0 |
| m_mt_196039306 | 1740936600 | COMPETITION | AWAY | OPP_003 |  |  | 0.0 | 6.0 | 1.0 | 5.0 | 0.0 | 3.0 | 24.0 | 28.0 | 2.0 | 4.0 | 49.0 | 60.0 | 17.0 | 6.0 | 0.0 | 3.0 | 9.0 | 6.0 |  |  | 1.0 | 6.0 | 51.0 | 49.0 | 1.0 | 0.0 | 1.0 | 2.0 | 4.0 | 7.0 | 3.0 | 5.0 | 2.0 | 4.0 | 1.0 | 5.0 | 9.0 | 27.0 | 25.0 | 18.0 | 5.0 | 12.0 | 22.0 | 17.0 |  |  | 3.0 | 1.0 |
| m_mt_408750504 | 1741533300 | COMPETITION | AWAY | OPP_004 |  |  | 4.0 | 4.0 | 2.0 | 0.0 | 0.0 | 0.0 | 25.0 | 26.0 | 4.0 | 6.0 | 69.0 | 48.0 | 14.0 | 18.0 | 2.0 | 0.0 | 11.0 | 4.0 |  |  | 1.0 | 2.0 | 47.0 | 53.0 | 0.0 | 0.0 | 1.0 | 0.0 | 4.0 | 2.0 | 4.0 | 5.0 | 2.0 | 1.0 | 2.0 | 4.0 | 18.0 | 22.0 | 16.0 | 18.0 | 6.0 | 6.0 | 19.0 | 14.0 |  |  | 2.0 | 0.0 |
| m_mt_972167661 | 1742146200 | COMPETITION | HOME | OPP_005 |  |  | 2.0 | 5.0 | 2.0 | 0.0 | 4.0 | 2.0 | 41.0 | 17.0 | 6.0 | 6.0 | 62.0 | 61.0 | 7.0 | 11.0 | 1.0 | 0.0 | 8.0 | 5.0 |  |  | 1.0 | 3.0 | 47.0 | 53.0 | 0.0 | 0.0 | 0.0 | 3.0 | 8.0 | 2.0 | 7.0 | 4.0 | 4.0 | 0.0 | 7.0 | 4.0 | 22.0 | 10.0 | 16.0 | 32.0 | 15.0 | 6.0 | 21.0 | 15.0 |  |  | 2.0 | 0.0 |
| m_mt_257695935 | 1742751000 | COMPETITION | AWAY | OPP_006 | BACK_FOUR | BACK_FOUR | 4.0 | 4.0 | 3.0 | 3.0 | 2.0 | 1.0 | 13.0 | 22.0 | 3.0 | 6.0 | 41.0 | 45.0 | 11.0 | 22.0 | 1.0 | 2.0 | 9.0 | 11.0 |  |  | 1.0 | 5.0 | 59.0 | 41.0 | 0.0 | 0.0 | 5.0 | 5.0 | 11.0 | 5.0 | 8.0 | 4.0 | 6.0 | 6.0 | 5.0 | 6.0 | 9.0 | 17.0 | 26.0 | 14.0 | 16.0 | 11.0 | 25.0 | 11.0 |  |  | 1.0 | 3.0 |
| m_mt_629312865 | 1743445800 | COMPETITION | HOME | OPP_007 |  |  | 4.0 | 6.0 | 1.0 | 0.0 | 4.0 | 3.0 | 19.0 | 26.0 | 3.0 | 3.0 | 56.0 | 34.0 | 17.0 | 24.0 | 0.0 | 0.0 | 4.0 | 3.0 |  |  | 0.0 | 3.0 | 54.0 | 46.0 | 0.0 | 0.0 | 2.0 | 1.0 | 4.0 | 5.0 | 4.0 | 5.0 | 1.0 | 2.0 | 5.0 | 5.0 | 8.0 | 14.0 | 19.0 | 16.0 | 9.0 | 10.0 | 8.0 | 14.0 |  |  | 0.0 | 4.0 |
| m_mt_629312853 | 1743966000 | COMPETITION | AWAY | OPP_008 |  |  | 4.0 | 5.0 | 1.0 | 1.0 | 3.0 | 5.0 | 18.0 | 24.0 | 6.0 | 9.0 | 64.0 | 39.0 | 12.0 | 8.0 | 0.0 | 1.0 | 2.0 | 19.0 |  |  | 1.0 | 1.0 | 50.0 | 50.0 | 0.0 | 0.0 | 5.0 | 5.0 | 7.0 | 10.0 | 7.0 | 6.0 | 6.0 | 7.0 | 9.0 | 8.0 | 19.0 | 14.0 | 30.0 | 15.0 | 16.0 | 18.0 | 21.0 | 27.0 |  |  |  |  |
| m_mt_257695372 | 1744475400 | COMPETITION | HOME | OPP_009 |  |  | 5.0 | 5.0 | 2.0 | 2.0 | 3.0 | 1.0 | 10.0 | 23.0 | 4.0 | 5.0 | 49.0 | 65.0 | 16.0 | 13.0 | 0.0 | 1.0 | 7.0 | 8.0 |  |  | 4.0 | 2.0 | 41.0 | 59.0 | 0.0 | 0.0 | 3.0 | 5.0 | 8.0 | 3.0 | 6.0 | 6.0 | 6.0 | 4.0 | 7.0 | 8.0 | 14.0 | 7.0 | 10.0 | 14.0 | 15.0 | 11.0 | 19.0 | 15.0 |  |  | 4.0 | 2.0 |
| m_mt_361806518 | 1745089200 | COMPETITION | AWAY | OPP_010 | BACK_FOUR | BACK_FOUR | 4.0 | 5.0 | 2.0 | 2.0 | 3.0 | 3.0 | 23.0 | 29.0 | 2.0 | 3.0 | 74.0 | 63.0 | 10.0 | 11.0 | 2.0 | 2.0 | 7.0 | 12.0 |  |  | 0.0 | 7.0 | 57.0 | 43.0 | 0.0 | 0.0 | 1.0 | 0.0 | 9.0 | 7.0 | 4.0 | 6.0 | 2.0 | 3.0 | 0.0 | 5.0 | 13.0 | 19.0 | 23.0 | 35.0 | 9.0 | 12.0 | 21.0 | 20.0 |  |  | 1.0 | 2.0 |
| m_mt_745921193 | 1745605800 | COMPETITION | HOME | OPP_011 |  |  | 4.0 | 6.0 | 1.0 | 0.0 | 2.0 | 2.0 | 24.0 | 20.0 | 1.0 | 5.0 | 50.0 | 55.0 | 10.0 | 14.0 | 1.0 | 0.0 | 10.0 | 5.0 |  |  | 2.0 | 0.0 | 40.0 | 60.0 | 0.0 | 0.0 | 3.0 | 0.0 | 5.0 | 7.0 | 6.0 | 5.0 | 1.0 | 3.0 | 4.0 | 3.0 | 21.0 | 16.0 | 13.0 | 19.0 | 9.0 | 10.0 | 21.0 | 21.0 |  |  | 1.0 | 1.0 |
| m_mt_361805527 | 1746210600 | COMPETITION | AWAY | OPP_012 |  |  | 4.0 | 4.0 | 0.0 | 5.0 | 1.0 | 9.0 | 34.0 | 17.0 | 2.0 | 10.0 | 48.0 | 67.0 | 14.0 | 11.0 | 2.0 | 4.0 | 8.0 | 4.0 |  |  | 1.0 | 0.0 | 33.0 | 67.0 | 1.0 | 0.0 | 7.0 | 0.0 | 4.0 | 23.0 | 2.0 | 7.0 | 2.0 | 11.0 | 1.0 | 4.0 | 16.0 | 13.0 | 13.0 | 15.0 | 5.0 | 27.0 | 8.0 | 54.0 |  |  | 3.0 | 1.0 |
| m_mt_257693381 | 1746815400 | COMPETITION | HOME | OPP_013 |  |  | 11.0 | 3.0 | 2.0 | 3.0 | 4.0 | 1.0 | 12.0 | 44.0 | 9.0 | 6.0 | 48.0 | 43.0 | 15.0 | 14.0 | 2.0 | 1.0 | 6.0 | 4.0 |  |  | 3.0 | 0.0 | 64.0 | 36.0 | 0.0 | 3.0 | 4.0 | 1.0 | 11.0 | 7.0 | 13.0 | 3.0 | 3.0 | 4.0 | 9.0 | 1.0 | 5.0 | 5.0 | 14.0 | 12.0 | 20.0 | 8.0 | 41.0 | 13.0 |  |  | 5.0 | 4.0 |
| m_mt_830542232 | 1747569600 | COMPETITION | AWAY | OPP_014 | BACK_FOUR | BACK_FOUR | 1.0 | 1.0 | 1.0 | 2.0 | 1.0 | 4.0 | 19.0 | 13.0 | 6.0 | 4.0 | 72.0 | 40.0 | 11.0 | 14.0 | 0.0 | 1.0 | 7.0 | 12.0 |  |  | 3.0 | 1.0 | 55.0 | 45.0 | 0.0 | 0.0 | 2.0 | 1.0 | 5.0 | 5.0 | 7.0 | 4.0 | 1.0 | 3.0 | 4.0 | 6.0 | 12.0 | 17.0 | 17.0 | 24.0 | 9.0 | 11.0 | 15.0 | 11.0 |  |  | 1.0 | 0.0 |
| m_mt_196034499 | 1748190600 | COMPETITION | HOME | OPP_015 |  |  | 8.0 | 7.0 | 1.0 | 0.0 | 6.0 | 3.0 | 21.0 | 19.0 | 3.0 | 2.0 | 69.0 | 53.0 | 7.0 | 6.0 | 4.0 | 0.0 | 7.0 | 3.0 |  |  | 0.0 | 1.0 | 45.0 | 55.0 | 0.0 | 0.0 | 1.0 | 1.0 | 8.0 | 5.0 | 4.0 | 4.0 | 5.0 | 1.0 | 7.0 | 3.0 | 9.0 | 9.0 | 19.0 | 18.0 | 15.0 | 8.0 | 18.0 | 20.0 |  |  |  |  |
| m_mt_013487725 | 1748795400 | COMPETITION | AWAY | OPP_016 |  |  | 5.0 | 4.0 | 1.0 | 1.0 | 3.0 | 3.0 | 36.0 | 18.0 | 3.0 | 8.0 | 40.0 | 43.0 | 8.0 | 11.0 | 1.0 | 2.0 | 8.0 | 7.0 |  |  | 1.0 | 3.0 | 48.0 | 52.0 | 0.0 | 0.0 | 5.0 | 4.0 | 9.0 | 8.0 | 2.0 | 4.0 | 5.0 | 7.0 | 1.0 | 6.0 | 11.0 | 10.0 | 27.0 | 17.0 | 10.0 | 14.0 | 15.0 | 20.0 |  |  | 1.0 | 0.0 |
| m_mt_747999116 | 1755451800 | COMPETITION | HOME | OPP_017 |  |  | 9.0 | 1.0 | 2.0 | 0.0 | 9.0 | 0.0 | 5.0 | 43.0 | 7.0 | 0.0 | 87.0 | 57.0 | 14.0 | 9.0 | 1.0 | 0.0 | 6.0 | 8.0 |  |  | 2.0 | 0.0 | 72.0 | 28.0 | 0.0 | 1.0 | 0.0 | 2.0 | 13.0 | 0.0 | 12.0 | 1.0 | 3.0 | 0.0 | 11.0 | 1.0 | 10.0 | 11.0 | 20.0 | 12.0 | 24.0 | 1.0 | 36.0 | 1.0 | 1.28 | 0.0 | 3.0 | 2.0 |
| m_mt_363888188 | 1755891000 | COMPETITION | AWAY | OPP_018 |  |  | 5.0 | 5.0 | 2.0 | 4.0 | 1.0 | 2.0 | 25.0 | 17.0 | 5.0 | 7.0 | 42.0 | 59.0 | 17.0 | 13.0 | 1.0 | 1.0 | 8.0 | 7.0 |  |  | 2.0 | 2.0 | 49.0 | 51.0 | 0.0 | 0.0 | 3.0 | 2.0 | 8.0 | 5.0 | 6.0 | 3.0 | 3.0 | 4.0 | 2.0 | 4.0 | 17.0 | 14.0 | 24.0 | 23.0 | 10.0 | 9.0 | 24.0 | 18.0 | 1.36 | 0.59 | 1.0 | 2.0 |
| m_mt_585222398 | 1756652400 | COMPETITION | HOME | OPP_003 |  |  | 4.0 | 4.0 | 1.0 | 2.0 | 3.0 | 2.0 | 44.0 | 19.0 | 7.0 | 4.0 | 53.0 | 62.0 | 15.0 | 13.0 | 2.0 | 1.0 | 4.0 | 10.0 |  |  | 2.0 | 3.0 | 52.0 | 48.0 | 0.0 | 1.0 | 3.0 | 0.0 | 4.0 | 8.0 | 1.0 | 6.0 | 2.0 | 4.0 | 2.0 | 4.0 | 13.0 | 12.0 | 19.0 | 22.0 | 6.0 | 12.0 | 23.0 | 18.0 | 0.62 | 0.85 | 4.0 | 3.0 |
| m_mt_626339815 | 1757254500 | COMPETITION | AWAY | OPP_019 | BACK_THREE | BACK_FOUR | 6.0 | 4.0 | 0.0 | 5.0 | 1.0 | 4.0 | 18.0 | 14.0 | 5.0 | 1.0 | 52.0 | 46.0 | 13.0 | 20.0 | 3.0 | 3.0 | 5.0 | 6.0 |  |  | 2.0 | 0.0 | 48.0 | 52.0 | 0.0 | 0.0 | 2.0 | 0.0 | 4.0 | 10.0 | 6.0 | 8.0 | 2.0 | 5.0 | 5.0 | 7.0 | 17.0 | 16.0 | 19.0 | 28.0 | 9.0 | 17.0 | 12.0 | 19.0 | 0.72 | 2.35 | 3.0 | 4.0 |
| m_mt_010443745 | 1757772900 | COMPETITION | HOME | OPP_007 |  |  | 4.0 | 4.0 | 1.0 | 6.0 | 4.0 | 4.0 | 30.0 | 25.0 | 5.0 | 4.0 | 49.0 | 45.0 | 15.0 | 12.0 | 1.0 | 0.0 | 8.0 | 8.0 |  |  |  |  | 42.0 | 58.0 | 0.0 | 0.0 | 4.0 | 3.0 | 6.0 | 12.0 | 4.0 | 9.0 | 4.0 | 4.0 | 6.0 | 5.0 | 21.0 | 15.0 | 27.0 | 24.0 | 12.0 | 17.0 | 21.0 | 24.0 | 0.85 | 2.51 | 2.0 | 3.0 |
| m_mt_585224739 | 1758472200 | COMPETITION | AWAY | OPP_004 | BACK_FOUR | BACK_FOUR | 1.0 | 3.0 | 2.0 | 3.0 | 1.0 | 8.0 | 46.0 | 9.0 | 2.0 | 5.0 | 56.0 | 74.0 | 11.0 | 10.0 | 1.0 | 0.0 | 7.0 | 4.0 |  |  | 0.0 | 5.0 | 38.0 | 62.0 | 0.0 | 0.0 | 5.0 | 2.0 | 3.0 | 9.0 | 3.0 | 4.0 | 3.0 | 5.0 | 4.0 | 8.0 | 21.0 | 30.0 | 25.0 | 25.0 | 7.0 | 17.0 | 12.0 | 38.0 | 1.0 | 1.04 | 2.0 | 1.0 |
| m_mt_363881037 | 1759068900 | COMPETITION | HOME | OPP_020 |  |  | 2.0 | 8.0 | 2.0 | 1.0 | 0.0 | 1.0 | 25.0 | 18.0 | 1.0 | 1.0 | 41.0 | 56.0 | 10.0 | 16.0 | 0.0 | 0.0 | 10.0 | 12.0 |  |  | 4.0 | 1.0 | 42.0 | 58.0 | 0.0 | 0.0 | 3.0 | 3.0 | 3.0 | 9.0 | 5.0 | 7.0 | 3.0 | 3.0 | 5.0 | 2.0 | 15.0 | 12.0 | 17.0 | 20.0 | 8.0 | 11.0 | 10.0 | 18.0 | 0.64 | 0.75 | 2.0 | 2.0 |
| m_mt_838550302 | 1759690800 | COMPETITION | AWAY | OPP_021 | BACK_FOUR | BACK_FOUR | 6.0 | 3.0 | 0.0 | 3.0 | 2.0 | 1.0 | 21.0 | 26.0 | 5.0 | 6.0 | 47.0 | 65.0 | 18.0 | 11.0 | 0.0 | 1.0 | 11.0 | 12.0 |  |  | 2.0 | 2.0 | 39.0 | 61.0 | 0.0 | 0.0 | 0.0 | 3.0 | 5.0 | 8.0 | 3.0 | 12.0 | 3.0 | 1.0 | 3.0 | 6.0 | 13.0 | 4.0 | 9.0 | 20.0 | 8.0 | 14.0 | 17.0 | 16.0 | 0.45 | 1.25 | 4.0 | 1.0 |
| m_mt_585224833 | 1760286600 | COMPETITION | HOME | OPP_015 |  |  | 3.0 | 4.0 | 1.0 | 1.0 | 3.0 | 3.0 | 19.0 | 33.0 | 13.0 | 2.0 | 74.0 | 35.0 | 12.0 | 12.0 | 1.0 | 0.0 | 8.0 | 6.0 |  |  | 1.0 | 3.0 | 59.0 | 41.0 | 0.0 | 0.0 | 1.0 | 1.0 | 6.0 | 4.0 | 6.0 | 5.0 | 2.0 | 1.0 | 5.0 | 5.0 | 13.0 | 16.0 | 10.0 | 14.0 | 11.0 | 9.0 | 19.0 | 20.0 | 1.02 | 0.85 | 2.0 | 3.0 |
| m_mt_010444331 | 1760985000 | COMPETITION | HOME | OPP_010 |  |  | 3.0 | 4.0 | 2.0 | 5.0 | 1.0 | 2.0 | 25.0 | 31.0 | 1.0 | 4.0 | 55.0 | 44.0 | 14.0 | 19.0 | 1.0 | 3.0 | 5.0 | 6.0 |  |  | 3.0 | 1.0 | 60.0 | 40.0 | 0.0 | 0.0 | 1.0 | 2.0 | 7.0 | 11.0 | 5.0 | 7.0 | 3.0 | 4.0 | 2.0 | 2.0 | 18.0 | 15.0 | 31.0 | 26.0 | 9.0 | 13.0 | 16.0 | 20.0 | 0.95 | 2.56 | 3.0 | 4.0 |
| m_mt_979111298 | 1761409800 | COMPETITION | AWAY | OPP_005 |  |  | 4.0 | 14.0 | 0.0 | 4.0 | 5.0 | 5.0 | 28.0 | 21.0 | 4.0 | 8.0 | 42.0 | 54.0 | 17.0 | 7.0 | 0.0 | 0.0 | 10.0 | 3.0 | 0.14 | 0.39 | 0.0 | 3.0 | 42.0 | 58.0 | 0.0 | 0.0 | 1.0 | 1.0 | 5.0 | 13.0 | 5.0 | 12.0 | 1.0 | 1.0 | 6.0 | 5.0 | 12.0 | 12.0 | 22.0 | 24.0 | 11.0 | 18.0 | 9.0 | 23.0 | 0.45 | 2.05 | 2.0 | 1.0 |
| m_mt_626333586 | 1762088400 | COMPETITION | AWAY | OPP_022 |  |  | 1.0 | 3.0 | 0.0 | 1.0 | 0.0 | 7.0 | 27.0 | 21.0 | 3.0 | 9.0 | 55.0 | 45.0 | 14.0 | 19.0 | 0.0 | 0.0 | 19.0 | 9.0 | 0.01 | 0.33 | 1.0 | 2.0 | 44.0 | 56.0 | 0.0 | 0.0 | 3.0 | 1.0 | 2.0 | 10.0 | 4.0 | 4.0 | 1.0 | 4.0 | 3.0 | 5.0 | 11.0 | 10.0 | 22.0 | 20.0 | 5.0 | 15.0 | 5.0 | 19.0 | 0.26 | 1.31 | 2.0 | 3.0 |
| m_mt_838555633 | 1762718400 | COMPETITION | HOME | OPP_023 |  |  | 3.0 | 2.0 | 2.0 | 0.0 | 1.0 | 5.0 | 24.0 | 20.0 | 2.0 | 4.0 | 57.0 | 57.0 | 16.0 | 17.0 | 0.0 | 0.0 | 10.0 | 15.0 | 0.17 | 0.08 | 2.0 | 3.0 | 49.0 | 51.0 | 0.0 | 0.0 | 1.0 | 2.0 | 5.0 | 6.0 | 4.0 | 5.0 | 2.0 | 1.0 | 2.0 | 5.0 | 16.0 | 18.0 | 13.0 | 21.0 | 7.0 | 11.0 | 17.0 | 17.0 | 0.74 | 0.82 | 6.0 | 1.0 |
| m_mt_404777116 | 1763306100 | COMPETITION | AWAY | OPP_013 | BACK_FOUR | BACK_FOUR | 2.0 | 9.0 | 2.0 | 1.0 | 1.0 | 4.0 | 25.0 | 26.0 | 5.0 | 13.0 | 46.0 | 42.0 | 11.0 | 13.0 | 0.0 | 3.0 | 3.0 | 11.0 | 0.12 | 0.37 | 3.0 | 0.0 | 42.0 | 58.0 | 0.0 | 0.0 | 6.0 | 2.0 | 4.0 | 10.0 | 3.0 | 3.0 | 3.0 | 9.0 | 3.0 | 6.0 | 13.0 | 14.0 | 21.0 | 16.0 | 7.0 | 16.0 | 14.0 | 33.0 | 0.54 | 2.07 | 0.0 | 3.0 |

### Arm B — AWAY_TEAM match-level matrix (14 rows × 55 cols)

Columns: `match_alias, kickoff_unix, competition, venue, opponent_alias, own_formation_family, opponent_formation_family, accurate_crosses_for, accurate_crosses_against, big_chances_for, big_chances_against, blocked_shots_for, blocked_shots_against, clearances_for, clearances_against, corners_for, corners_against, final_third_entries_for, final_third_entries_against, fouls_for, fouls_against, goals_for, goals_against, interceptions_for, interceptions_against, npxg_for, npxg_against, offsides_for, offsides_against, possession_for, possession_against, red_cards_for, red_cards_against, saves_for, saves_against, shots_inside_box_for, shots_inside_box_against, shots_off_target_for, shots_off_target_against, shots_on_target_for, shots_on_target_against, shots_outside_box_for, shots_outside_box_against, tackles_for, tackles_against, throw_ins_for, throw_ins_against, total_shots_for, total_shots_against, touches_in_box_for, touches_in_box_against, xg_for, xg_against, yellow_cards_for, yellow_cards_against`

| match_alias | kickoff_unix | competition | venue | opponent_alias | own_formation_family | opponent_formation_family | accurate_crosses_for | accurate_crosses_against | big_chances_for | big_chances_against | blocked_shots_for | blocked_shots_against | clearances_for | clearances_against | corners_for | corners_against | final_third_entries_for | final_third_entries_against | fouls_for | fouls_against | goals_for | goals_against | interceptions_for | interceptions_against | npxg_for | npxg_against | offsides_for | offsides_against | possession_for | possession_against | red_cards_for | red_cards_against | saves_for | saves_against | shots_inside_box_for | shots_inside_box_against | shots_off_target_for | shots_off_target_against | shots_on_target_for | shots_on_target_against | shots_outside_box_for | shots_outside_box_against | tackles_for | tackles_against | throw_ins_for | throw_ins_against | total_shots_for | total_shots_against | touches_in_box_for | touches_in_box_against | xg_for | xg_against | yellow_cards_for | yellow_cards_against |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| m_mt_838555226 | 1755286200 | COMPETITION | AWAY | OPP_010 |  |  | 1.0 | 6.0 | 0.0 | 4.0 | 4.0 | 2.0 | 19.0 | 19.0 | 3.0 | 3.0 | 35.0 | 75.0 | 10.0 | 13.0 | 1.0 | 5.0 | 6.0 | 11.0 |  |  | 0.0 | 3.0 | 35.0 | 65.0 | 1.0 | 0.0 | 2.0 | 1.0 | 1.0 | 13.0 | 3.0 | 6.0 | 1.0 | 7.0 | 7.0 | 2.0 | 14.0 | 11.0 | 15.0 | 18.0 | 8.0 | 15.0 | 4.0 | 26.0 | 0.35 | 3.49 | 1.0 | 1.0 |
| m_mt_191000684 | 1756056600 | COMPETITION | HOME | OPP_013 |  |  | 3.0 | 5.0 | 0.0 | 2.0 | 0.0 | 3.0 | 26.0 | 15.0 | 3.0 | 5.0 | 63.0 | 64.0 | 9.0 | 15.0 | 0.0 | 1.0 | 11.0 | 4.0 |  |  | 0.0 | 1.0 | 41.0 | 59.0 | 0.0 | 0.0 | 1.0 | 6.0 | 7.0 | 9.0 | 4.0 | 7.0 | 6.0 | 3.0 | 3.0 | 4.0 | 17.0 | 12.0 | 17.0 | 18.0 | 10.0 | 13.0 | 14.0 | 27.0 | 0.52 | 1.45 | 1.0 | 2.0 |
| m_mt_404777247 | 1756495800 | COMPETITION | AWAY | OPP_011 |  |  | 1.0 | 7.0 | 0.0 | 3.0 | 2.0 | 6.0 | 31.0 | 12.0 | 3.0 | 10.0 | 32.0 | 73.0 | 12.0 | 12.0 | 0.0 | 1.0 | 5.0 | 4.0 |  |  |  |  | 42.0 | 58.0 | 0.0 | 0.0 | 5.0 | 2.0 | 3.0 | 11.0 | 5.0 | 5.0 | 2.0 | 6.0 | 6.0 | 6.0 | 17.0 | 13.0 | 13.0 | 19.0 | 9.0 | 17.0 | 6.0 | 30.0 | 0.38 | 1.73 | 1.0 | 4.0 |
| m_mt_252667300 | 1757262600 | COMPETITION | HOME | OPP_018 | BACK_FOUR | BACK_FOUR | 4.0 | 8.0 | 0.0 | 5.0 | 4.0 | 4.0 | 18.0 | 29.0 | 9.0 | 3.0 | 45.0 | 44.0 | 17.0 | 9.0 | 0.0 | 0.0 | 8.0 | 9.0 |  |  | 5.0 | 2.0 | 52.0 | 48.0 | 0.0 | 0.0 | 5.0 | 2.0 | 4.0 | 8.0 | 3.0 | 2.0 | 1.0 | 5.0 | 4.0 | 3.0 | 23.0 | 17.0 | 19.0 | 22.0 | 8.0 | 11.0 | 12.0 | 24.0 | 0.24 | 2.11 | 0.0 | 3.0 |
| m_mt_838550426 | 1757859300 | COMPETITION | AWAY | OPP_001 |  |  | 4.0 | 6.0 | 5.0 | 2.0 | 2.0 | 6.0 | 38.0 | 11.0 | 1.0 | 11.0 | 51.0 | 48.0 | 15.0 | 8.0 | 4.0 | 2.0 | 19.0 | 5.0 |  |  | 2.0 | 1.0 | 41.0 | 59.0 | 0.0 | 0.0 | 6.0 | 1.0 | 8.0 | 13.0 | 4.0 | 6.0 | 5.0 | 8.0 | 3.0 | 7.0 | 20.0 | 13.0 | 22.0 | 30.0 | 11.0 | 20.0 | 16.0 | 29.0 | 1.56 | 2.54 | 2.0 | 0.0 |
| m_mt_838550479 | 1758377700 | COMPETITION | HOME | OPP_002 | BACK_FOUR | BACK_FOUR | 2.0 | 6.0 | 0.0 | 4.0 | 3.0 | 1.0 | 20.0 | 9.0 | 1.0 | 4.0 | 53.0 | 56.0 | 15.0 | 11.0 | 1.0 | 3.0 | 12.0 | 8.0 |  |  | 0.0 | 2.0 | 53.0 | 47.0 | 1.0 | 0.0 | 5.0 | 1.0 | 6.0 | 10.0 | 5.0 | 4.0 | 2.0 | 8.0 | 4.0 | 3.0 | 25.0 | 19.0 | 25.0 | 20.0 | 10.0 | 13.0 | 25.0 | 31.0 | 0.54 | 3.17 | 2.0 | 5.0 |
| m_mt_626339229 | 1759077000 | COMPETITION | AWAY | OPP_023 |  |  | 3.0 | 9.0 | 1.0 | 3.0 | 2.0 | 3.0 | 41.0 | 18.0 | 2.0 | 2.0 | 32.0 | 89.0 | 21.0 | 14.0 | 1.0 | 0.0 | 9.0 | 5.0 |  |  |  |  | 31.0 | 69.0 | 0.0 | 0.0 | 1.0 | 3.0 | 5.0 | 13.0 | 3.0 | 14.0 | 4.0 | 1.0 | 4.0 | 5.0 | 22.0 | 17.0 | 16.0 | 35.0 | 9.0 | 18.0 | 9.0 | 31.0 | 1.0 | 1.82 | 3.0 | 3.0 |
| m_mt_010443143 | 1759775400 | COMPETITION | HOME | OPP_003 | BACK_FOUR | BACK_FOUR | 1.0 | 1.0 | 1.0 | 0.0 | 4.0 | 3.0 | 26.0 | 23.0 | 6.0 | 1.0 | 49.0 | 63.0 | 19.0 | 11.0 | 0.0 | 0.0 | 5.0 | 4.0 |  |  | 3.0 | 1.0 | 52.0 | 48.0 | 0.0 | 1.0 | 3.0 | 1.0 | 5.0 | 5.0 | 1.0 | 3.0 | 1.0 | 3.0 | 1.0 | 4.0 | 18.0 | 18.0 | 18.0 | 19.0 | 6.0 | 9.0 | 20.0 | 13.0 | 0.82 | 0.8 | 1.0 | 1.0 |
| m_mt_404778014 | 1760380200 | COMPETITION | AWAY | OPP_012 |  |  | 4.0 | 5.0 | 0.0 | 4.0 | 4.0 | 4.0 | 32.0 | 29.0 | 6.0 | 4.0 | 56.0 | 64.0 |  |  | 0.0 | 1.0 | 7.0 | 6.0 |  |  | 4.0 | 2.0 | 45.0 | 55.0 | 0.0 | 0.0 | 3.0 | 5.0 | 9.0 | 12.0 | 6.0 | 10.0 | 5.0 | 5.0 | 6.0 | 7.0 | 24.0 | 29.0 | 17.0 | 16.0 | 15.0 | 19.0 | 24.0 | 25.0 | 1.01 | 2.38 | 2.0 | 4.0 |
| m_mt_252666783 | 1760805000 | COMPETITION | AWAY | OPP_024 |  |  | 3.0 | 2.0 | 4.0 | 0.0 | 0.0 | 3.0 | 20.0 | 16.0 | 5.0 | 3.0 | 56.0 | 42.0 | 10.0 | 10.0 | 5.0 | 0.0 | 9.0 | 9.0 |  |  | 1.0 | 1.0 | 58.0 | 42.0 | 0.0 | 2.0 | 2.0 | 7.0 | 11.0 | 2.0 | 6.0 | 4.0 | 13.0 | 2.0 | 8.0 | 7.0 | 20.0 | 12.0 | 18.0 | 20.0 | 19.0 | 9.0 | 28.0 | 10.0 | 2.18 | 0.3 | 2.0 | 5.0 |
| m_mt_010444303 | 1761393600 | COMPETITION | HOME | OPP_020 |  |  | 4.0 | 2.0 | 2.0 | 3.0 | 6.0 | 1.0 | 16.0 | 48.0 | 8.0 | 2.0 | 46.0 | 47.0 | 15.0 | 11.0 | 0.0 | 1.0 | 5.0 | 13.0 | 0.35 | 0.13 | 1.0 | 3.0 | 67.0 | 33.0 | 0.0 | 0.0 | 0.0 | 2.0 | 8.0 | 5.0 | 7.0 | 3.0 | 2.0 | 1.0 | 7.0 | 0.0 | 17.0 | 10.0 | 14.0 | 14.0 | 15.0 | 5.0 | 34.0 | 17.0 | 1.28 | 1.42 | 3.0 | 1.0 |
| m_mt_747999012 | 1762010100 | COMPETITION | HOME | OPP_017 |  |  | 7.0 | 6.0 | 1.0 | 1.0 | 3.0 | 1.0 | 14.0 | 33.0 | 6.0 | 2.0 | 52.0 | 60.0 | 11.0 | 13.0 | 3.0 | 2.0 | 6.0 | 5.0 | 0.49 | 0.31 | 2.0 | 1.0 | 60.0 | 40.0 | 0.0 | 0.0 | 3.0 | 4.0 | 13.0 | 7.0 | 8.0 | 4.0 | 7.0 | 6.0 | 5.0 | 4.0 | 13.0 | 14.0 | 21.0 | 20.0 | 18.0 | 11.0 | 30.0 | 11.0 | 1.12 | 0.66 | 0.0 | 3.0 |
| m_mt_747999043 | 1762623000 | COMPETITION | AWAY | OPP_008 |  |  | 2.0 | 1.0 | 1.0 | 3.0 | 1.0 | 1.0 | 13.0 | 12.0 | 1.0 | 1.0 | 45.0 | 47.0 | 11.0 | 12.0 | 0.0 | 3.0 | 6.0 | 12.0 | 0.08 | 0.44 | 1.0 | 2.0 | 45.0 | 55.0 | 0.0 | 0.0 | 0.0 | 5.0 | 4.0 | 7.0 | 5.0 | 5.0 | 5.0 | 3.0 | 7.0 | 2.0 | 12.0 | 15.0 | 21.0 | 13.0 | 11.0 | 9.0 | 15.0 | 24.0 | 0.7 | 1.87 | 0.0 | 1.0 |
| m_mt_979111440 | 1763407800 | COMPETITION | HOME | OPP_004 | BACK_FOUR | BACK_FOUR | 2.0 | 5.0 | 2.0 | 0.0 | 1.0 | 6.0 | 48.0 | 9.0 | 1.0 | 9.0 | 35.0 | 50.0 | 6.0 | 14.0 | 1.0 | 0.0 | 11.0 | 9.0 | 0.13 | 0.13 | 3.0 | 2.0 | 34.0 | 66.0 | 0.0 | 1.0 | 3.0 | 0.0 | 4.0 | 8.0 | 4.0 | 7.0 | 1.0 | 3.0 | 2.0 | 8.0 | 22.0 | 9.0 | 17.0 | 20.0 | 6.0 | 16.0 | 14.0 | 19.0 | 0.85 | 1.31 | 0.0 | 2.0 |

### Arm B — derived summaries (DERIVED_SUMMARY), HOME 238 + AWAY 238

HOME_TEAM (metric·side·window·venue = value [n, reliability]):

- accurate_crosses·FOR·ALL_PRIOR·ALL = 4.0 [n=30, HIGH]
- accurate_crosses·FOR·W5·ALL = 2.6 [n=5, LOW]
- accurate_crosses·FOR·W10·ALL = 2.9 [n=10, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·HOME = 4.6429 [n=14, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·AWAY = 3.4375 [n=16, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·ALL = 4.8 [n=30, HIGH]
- accurate_crosses·AGAINST·W5·ALL = 6.4 [n=5, LOW]
- accurate_crosses·AGAINST·W10·ALL = 5.4 [n=10, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·HOME = 4.5714 [n=14, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·AWAY = 5.0 [n=16, MEDIUM]
- big_chances·FOR·ALL_PRIOR·ALL = 1.5 [n=30, HIGH]
- big_chances·FOR·W5·ALL = 1.2 [n=5, LOW]
- big_chances·FOR·W10·ALL = 1.2 [n=10, MEDIUM]
- big_chances·FOR·ALL_PRIOR·HOME = 1.5 [n=14, MEDIUM]
- big_chances·FOR·ALL_PRIOR·AWAY = 1.5 [n=16, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·ALL = 2.1667 [n=30, HIGH]
- big_chances·AGAINST·W5·ALL = 2.2 [n=5, LOW]
- big_chances·AGAINST·W10·ALL = 2.5 [n=10, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·HOME = 1.6429 [n=14, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·AWAY = 2.625 [n=16, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·ALL = 2.4333 [n=30, HIGH]
- blocked_shots·FOR·W5·ALL = 1.6 [n=5, LOW]
- blocked_shots·FOR·W10·ALL = 1.8 [n=10, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·HOME = 3.2857 [n=14, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·AWAY = 1.6875 [n=16, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·ALL = 3.1333 [n=30, HIGH]
- blocked_shots·AGAINST·W5·ALL = 4.6 [n=5, LOW]
- blocked_shots·AGAINST·W10·ALL = 4.0 [n=10, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·HOME = 2.0714 [n=14, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·AWAY = 4.0625 [n=16, MEDIUM]
- clearances·FOR·ALL_PRIOR·ALL = 25.5 [n=30, HIGH]
- clearances·FOR·W5·ALL = 25.8 [n=5, LOW]
- clearances·FOR·W10·ALL = 27.0 [n=10, MEDIUM]
- clearances·FOR·ALL_PRIOR·HOME = 23.4286 [n=14, MEDIUM]
- clearances·FOR·ALL_PRIOR·AWAY = 27.3125 [n=16, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·ALL = 22.7 [n=30, HIGH]
- clearances·AGAINST·W5·ALL = 23.8 [n=5, LOW]
- clearances·AGAINST·W10·ALL = 23.0 [n=10, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·HOME = 25.3571 [n=14, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·AWAY = 20.375 [n=16, MEDIUM]
- corners·FOR·ALL_PRIOR·ALL = 4.2667 [n=30, HIGH]
- corners·FOR·W5·ALL = 3.0 [n=5, LOW]
- corners·FOR·W10·ALL = 4.1 [n=10, MEDIUM]
- corners·FOR·ALL_PRIOR·HOME = 4.8571 [n=14, MEDIUM]
- corners·FOR·ALL_PRIOR·AWAY = 3.75 [n=16, MEDIUM]
- corners·AGAINST·ALL_PRIOR·ALL = 5.1 [n=30, HIGH]
- corners·AGAINST·W5·ALL = 7.6 [n=5, LOW]
- corners·AGAINST·W10·ALL = 5.6 [n=10, MEDIUM]
- corners·AGAINST·ALL_PRIOR·HOME = 3.5 [n=14, MEDIUM]
- corners·AGAINST·ALL_PRIOR·AWAY = 6.5 [n=16, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·ALL = 55.6 [n=30, HIGH]
- final_third_entries·FOR·W5·ALL = 51.0 [n=5, LOW]
- final_third_entries·FOR·W10·ALL = 52.2 [n=10, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·HOME = 58.1429 [n=14, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·AWAY = 53.375 [n=16, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·ALL = 52.5333 [n=30, HIGH]
- final_third_entries·AGAINST·W5·ALL = 48.4 [n=5, LOW]
- final_third_entries·AGAINST·W10·ALL = 51.7 [n=10, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·HOME = 51.3571 [n=14, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·AWAY = 53.5625 [n=16, MEDIUM]
- fouls·FOR·ALL_PRIOR·ALL = 12.8667 [n=30, HIGH]
- fouls·FOR·W5·ALL = 14.4 [n=5, LOW]
- fouls·FOR·W10·ALL = 13.8 [n=10, MEDIUM]
- fouls·FOR·ALL_PRIOR·HOME = 12.5 [n=14, MEDIUM]
- fouls·FOR·ALL_PRIOR·AWAY = 13.1875 [n=16, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·ALL = 13.7 [n=30, HIGH]
- fouls·AGAINST·W5·ALL = 15.0 [n=5, LOW]
- fouls·AGAINST·W10·ALL = 13.6 [n=10, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·HOME = 14.0 [n=14, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·AWAY = 13.4375 [n=16, MEDIUM]
- goals·FOR·ALL_PRIOR·ALL = 1.0 [n=30, HIGH]
- goals·FOR·W5·ALL = 0.2 [n=5, LOW]
- goals·FOR·W10·ALL = 0.4 [n=10, MEDIUM]
- goals·FOR·ALL_PRIOR·HOME = 1.0 [n=14, MEDIUM]
- goals·FOR·ALL_PRIOR·AWAY = 1.0 [n=16, MEDIUM]
- goals·AGAINST·ALL_PRIOR·ALL = 1.0333 [n=30, HIGH]
- goals·AGAINST·W5·ALL = 1.2 [n=5, LOW]
- goals·AGAINST·W10·ALL = 0.7 [n=10, MEDIUM]
- goals·AGAINST·ALL_PRIOR·HOME = 0.4286 [n=14, MEDIUM]
- goals·AGAINST·ALL_PRIOR·AWAY = 1.5625 [n=16, MEDIUM]
- interceptions·FOR·ALL_PRIOR·ALL = 8.1 [n=30, HIGH]
- interceptions·FOR·W5·ALL = 9.4 [n=5, LOW]
- interceptions·FOR·W10·ALL = 9.1 [n=10, MEDIUM]
- interceptions·FOR·ALL_PRIOR·HOME = 7.7143 [n=14, MEDIUM]
- interceptions·FOR·ALL_PRIOR·AWAY = 8.4375 [n=16, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·ALL = 7.8667 [n=30, HIGH]
- interceptions·AGAINST·W5·ALL = 8.8 [n=5, LOW]
- interceptions·AGAINST·W10·ALL = 8.6 [n=10, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·HOME = 7.2143 [n=14, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·AWAY = 8.4375 [n=16, MEDIUM]
- npxg·FOR·ALL_PRIOR·ALL = 0.11 [n=4, LOW]
- npxg·FOR·W5·ALL = 0.11 [n=4, LOW]
- npxg·FOR·W10·ALL = 0.11 [n=4, LOW]
- npxg·FOR·ALL_PRIOR·AWAY = 0.09 [n=3, LOW]
- npxg·AGAINST·ALL_PRIOR·ALL = 0.2925 [n=4, LOW]
- npxg·AGAINST·W5·ALL = 0.2925 [n=4, LOW]
- npxg·AGAINST·W10·ALL = 0.2925 [n=4, LOW]
- npxg·AGAINST·ALL_PRIOR·AWAY = 0.3633 [n=3, LOW]
- offsides·FOR·ALL_PRIOR·ALL = 1.6897 [n=29, HIGH]
- offsides·FOR·W5·ALL = 1.8 [n=5, LOW]
- offsides·FOR·W10·ALL = 1.7778 [n=9, MEDIUM]
- offsides·FOR·ALL_PRIOR·HOME = 2.0 [n=13, MEDIUM]
- offsides·FOR·ALL_PRIOR·AWAY = 1.4375 [n=16, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·ALL = 2.2414 [n=29, HIGH]
- offsides·AGAINST·W5·ALL = 1.8 [n=5, LOW]
- offsides·AGAINST·W10·ALL = 2.2222 [n=9, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·HOME = 1.8462 [n=13, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·AWAY = 2.5625 [n=16, MEDIUM]
- possession·FOR·ALL_PRIOR·ALL = 48.2 [n=30, HIGH]
- possession·FOR·W5·ALL = 47.4 [n=5, LOW]
- possession·FOR·W10·ALL = 45.7 [n=10, MEDIUM]
- possession·FOR·ALL_PRIOR·HOME = 50.8571 [n=14, MEDIUM]
- possession·FOR·ALL_PRIOR·AWAY = 45.875 [n=16, MEDIUM]
- possession·AGAINST·ALL_PRIOR·ALL = 51.8 [n=30, HIGH]
- possession·AGAINST·W5·ALL = 52.6 [n=5, LOW]
- possession·AGAINST·W10·ALL = 54.3 [n=10, MEDIUM]
- possession·AGAINST·ALL_PRIOR·HOME = 49.1429 [n=14, MEDIUM]
- possession·AGAINST·ALL_PRIOR·AWAY = 54.125 [n=16, MEDIUM]
- red_cards·FOR·ALL_PRIOR·ALL = 0.0667 [n=30, HIGH]
- red_cards·FOR·W5·ALL = 0.0 [n=5, LOW]
- red_cards·FOR·W10·ALL = 0.0 [n=10, MEDIUM]
- red_cards·FOR·ALL_PRIOR·HOME = 0.0 [n=14, MEDIUM]
- red_cards·FOR·ALL_PRIOR·AWAY = 0.125 [n=16, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·ALL = 0.1667 [n=30, HIGH]
- red_cards·AGAINST·W5·ALL = 0.0 [n=5, LOW]
- red_cards·AGAINST·W10·ALL = 0.0 [n=10, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·HOME = 0.3571 [n=14, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·AWAY = 0.0 [n=16, MEDIUM]
- saves·FOR·ALL_PRIOR·ALL = 2.4333 [n=30, HIGH]
- saves·FOR·W5·ALL = 2.4 [n=5, LOW]
- saves·FOR·W10·ALL = 2.5 [n=10, MEDIUM]
- saves·FOR·ALL_PRIOR·HOME = 1.8571 [n=14, MEDIUM]
- saves·FOR·ALL_PRIOR·AWAY = 2.9375 [n=16, MEDIUM]
- saves·AGAINST·ALL_PRIOR·ALL = 2.0667 [n=30, HIGH]
- saves·AGAINST·W5·ALL = 1.6 [n=5, LOW]
- saves·AGAINST·W10·ALL = 2.0 [n=10, MEDIUM]
- saves·AGAINST·ALL_PRIOR·HOME = 2.0 [n=14, MEDIUM]
- saves·AGAINST·ALL_PRIOR·AWAY = 2.125 [n=16, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·ALL = 6.4667 [n=30, HIGH]
- shots_inside_box·FOR·W5·ALL = 4.6 [n=5, LOW]
- shots_inside_box·FOR·W10·ALL = 4.6 [n=10, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·HOME = 6.8571 [n=14, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·AWAY = 6.125 [n=16, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·ALL = 7.5333 [n=30, HIGH]
- shots_inside_box·AGAINST·W5·ALL = 10.0 [n=5, LOW]
- shots_inside_box·AGAINST·W10·ALL = 9.2 [n=10, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·HOME = 6.1429 [n=14, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·AWAY = 8.75 [n=16, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·ALL = 5.1 [n=30, HIGH]
- shots_off_target·FOR·W5·ALL = 4.2 [n=5, LOW]
- shots_off_target·FOR·W10·ALL = 4.2 [n=10, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·HOME = 5.8571 [n=14, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·AWAY = 4.4375 [n=16, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·ALL = 5.4667 [n=30, HIGH]
- shots_off_target·AGAINST·W5·ALL = 6.2 [n=5, LOW]
- shots_off_target·AGAINST·W10·ALL = 6.8 [n=10, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·HOME = 5.3571 [n=14, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·AWAY = 5.5625 [n=16, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·ALL = 3.1333 [n=30, HIGH]
- shots_on_target·FOR·W5·ALL = 2.0 [n=5, LOW]
- shots_on_target·FOR·W10·ALL = 2.5 [n=10, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·HOME = 3.0714 [n=14, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·AWAY = 3.1875 [n=16, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·ALL = 3.5 [n=30, HIGH]
- shots_on_target·AGAINST·W5·ALL = 3.8 [n=5, LOW]
- shots_on_target·AGAINST·W10·ALL = 3.3 [n=10, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·HOME = 2.2143 [n=14, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·AWAY = 4.625 [n=16, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·ALL = 4.2 [n=30, HIGH]
- shots_outside_box·FOR·W5·ALL = 3.2 [n=5, LOW]
- shots_outside_box·FOR·W10·ALL = 3.9 [n=10, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·HOME = 5.3571 [n=14, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·AWAY = 3.1875 [n=16, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·ALL = 4.5667 [n=30, HIGH]
- shots_outside_box·AGAINST·W5·ALL = 4.6 [n=5, LOW]
- shots_outside_box·AGAINST·W10·ALL = 4.9 [n=10, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·HOME = 3.5 [n=14, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·AWAY = 5.5 [n=16, MEDIUM]
- tackles·FOR·ALL_PRIOR·ALL = 14.3333 [n=30, HIGH]
- tackles·FOR·W5·ALL = 14.0 [n=5, LOW]
- tackles·FOR·W10·ALL = 15.3 [n=10, MEDIUM]
- tackles·FOR·ALL_PRIOR·HOME = 14.4286 [n=14, MEDIUM]
- tackles·FOR·ALL_PRIOR·AWAY = 14.25 [n=16, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·ALL = 14.3667 [n=30, HIGH]
- tackles·AGAINST·W5·ALL = 13.8 [n=5, LOW]
- tackles·AGAINST·W10·ALL = 14.6 [n=10, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·HOME = 12.7857 [n=14, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·AWAY = 15.75 [n=16, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·ALL = 19.3667 [n=30, HIGH]
- throw_ins·FOR·W5·ALL = 21.8 [n=5, LOW]
- throw_ins·FOR·W10·ALL = 19.7 [n=10, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·HOME = 17.4286 [n=14, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·AWAY = 21.0625 [n=16, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·ALL = 20.4667 [n=30, HIGH]
- throw_ins·AGAINST·W5·ALL = 21.4 [n=5, LOW]
- throw_ins·AGAINST·W10·ALL = 21.0 [n=10, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·HOME = 19.1429 [n=14, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·AWAY = 21.625 [n=16, MEDIUM]
- total_shots·FOR·ALL_PRIOR·ALL = 10.6667 [n=30, HIGH]
- total_shots·FOR·W5·ALL = 7.8 [n=5, LOW]
- total_shots·FOR·W10·ALL = 8.5 [n=10, MEDIUM]
- total_shots·FOR·ALL_PRIOR·HOME = 12.2143 [n=14, MEDIUM]
- total_shots·FOR·ALL_PRIOR·AWAY = 9.3125 [n=16, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·ALL = 12.1 [n=30, HIGH]
- total_shots·AGAINST·W5·ALL = 14.6 [n=5, LOW]
- total_shots·AGAINST·W10·ALL = 14.1 [n=10, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·HOME = 9.6429 [n=14, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·AWAY = 14.25 [n=16, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·ALL = 18.4667 [n=30, HIGH]
- touches_in_box·FOR·W5·ALL = 12.2 [n=5, LOW]
- touches_in_box·FOR·W10·ALL = 14.0 [n=10, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·HOME = 20.5 [n=14, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·AWAY = 16.6875 [n=16, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·ALL = 19.6667 [n=30, HIGH]
- touches_in_box·AGAINST·W5·ALL = 22.4 [n=5, LOW]
- touches_in_box·AGAINST·W10·ALL = 22.8 [n=10, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·HOME = 16.6429 [n=14, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·AWAY = 22.3125 [n=16, MEDIUM]
- xg·FOR·ALL_PRIOR·ALL = 0.7771 [n=14, MEDIUM]
- xg·FOR·W5·ALL = 0.588 [n=5, LOW]
- xg·FOR·W10·ALL = 0.69 [n=10, MEDIUM]
- xg·FOR·ALL_PRIOR·HOME = 0.8714 [n=7, LOW]
- xg·FOR·ALL_PRIOR·AWAY = 0.6829 [n=7, LOW]
- xg·AGAINST·ALL_PRIOR·ALL = 1.3571 [n=14, MEDIUM]
- xg·AGAINST·W5·ALL = 1.762 [n=5, LOW]
- xg·AGAINST·W10·ALL = 1.521 [n=10, MEDIUM]
- xg·AGAINST·ALL_PRIOR·HOME = 1.1914 [n=7, LOW]
- xg·AGAINST·ALL_PRIOR·AWAY = 1.5229 [n=7, LOW]
- yellow_cards·FOR·ALL_PRIOR·ALL = 2.3571 [n=28, HIGH]
- yellow_cards·FOR·W5·ALL = 2.6 [n=5, LOW]
- yellow_cards·FOR·W10·ALL = 2.5 [n=10, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·HOME = 2.6923 [n=13, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·AWAY = 2.0667 [n=15, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·ALL = 1.9643 [n=28, HIGH]
- yellow_cards·AGAINST·W5·ALL = 2.4 [n=5, LOW]
- yellow_cards·AGAINST·W10·ALL = 2.2 [n=10, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·HOME = 2.3077 [n=13, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·AWAY = 1.6667 [n=15, MEDIUM]

AWAY_TEAM:

- accurate_crosses·FOR·ALL_PRIOR·ALL = 2.9286 [n=14, MEDIUM]
- accurate_crosses·FOR·W5·ALL = 3.6 [n=5, LOW]
- accurate_crosses·FOR·W10·ALL = 3.2 [n=10, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·HOME = 3.2857 [n=7, LOW]
- accurate_crosses·FOR·ALL_PRIOR·AWAY = 2.5714 [n=7, LOW]
- accurate_crosses·AGAINST·ALL_PRIOR·ALL = 4.9286 [n=14, MEDIUM]
- accurate_crosses·AGAINST·W5·ALL = 3.2 [n=5, LOW]
- accurate_crosses·AGAINST·W10·ALL = 4.3 [n=10, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·HOME = 4.7143 [n=7, LOW]
- accurate_crosses·AGAINST·ALL_PRIOR·AWAY = 5.1429 [n=7, LOW]
- big_chances·FOR·ALL_PRIOR·ALL = 1.2143 [n=14, MEDIUM]
- big_chances·FOR·W5·ALL = 2.0 [n=5, LOW]
- big_chances·FOR·W10·ALL = 1.7 [n=10, MEDIUM]
- big_chances·FOR·ALL_PRIOR·HOME = 0.8571 [n=7, LOW]
- big_chances·FOR·ALL_PRIOR·AWAY = 1.5714 [n=7, LOW]
- big_chances·AGAINST·ALL_PRIOR·ALL = 2.4286 [n=14, MEDIUM]
- big_chances·AGAINST·W5·ALL = 1.4 [n=5, LOW]
- big_chances·AGAINST·W10·ALL = 2.0 [n=10, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·HOME = 2.1429 [n=7, LOW]
- big_chances·AGAINST·ALL_PRIOR·AWAY = 2.7143 [n=7, LOW]
- blocked_shots·FOR·ALL_PRIOR·ALL = 2.5714 [n=14, MEDIUM]
- blocked_shots·FOR·W5·ALL = 2.2 [n=5, LOW]
- blocked_shots·FOR·W10·ALL = 2.6 [n=10, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·HOME = 3.0 [n=7, LOW]
- blocked_shots·FOR·ALL_PRIOR·AWAY = 2.1429 [n=7, LOW]
- blocked_shots·AGAINST·ALL_PRIOR·ALL = 3.1429 [n=14, MEDIUM]
- blocked_shots·AGAINST·W5·ALL = 2.4 [n=5, LOW]
- blocked_shots·AGAINST·W10·ALL = 2.9 [n=10, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·HOME = 2.7143 [n=7, LOW]
- blocked_shots·AGAINST·ALL_PRIOR·AWAY = 3.5714 [n=7, LOW]
- clearances·FOR·ALL_PRIOR·ALL = 25.8571 [n=14, MEDIUM]
- clearances·FOR·W5·ALL = 22.2 [n=5, LOW]
- clearances·FOR·W10·ALL = 26.8 [n=10, MEDIUM]
- clearances·FOR·ALL_PRIOR·HOME = 24.0 [n=7, LOW]
- clearances·FOR·ALL_PRIOR·AWAY = 27.7143 [n=7, LOW]
- clearances·AGAINST·ALL_PRIOR·ALL = 20.2143 [n=14, MEDIUM]
- clearances·AGAINST·W5·ALL = 23.6 [n=5, LOW]
- clearances·AGAINST·W10·ALL = 20.8 [n=10, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·HOME = 23.7143 [n=7, LOW]
- clearances·AGAINST·ALL_PRIOR·AWAY = 16.7143 [n=7, LOW]
- corners·FOR·ALL_PRIOR·ALL = 3.9286 [n=14, MEDIUM]
- corners·FOR·W5·ALL = 4.2 [n=5, LOW]
- corners·FOR·W10·ALL = 3.7 [n=10, MEDIUM]
- corners·FOR·ALL_PRIOR·HOME = 4.8571 [n=7, LOW]
- corners·FOR·ALL_PRIOR·AWAY = 3.0 [n=7, LOW]
- corners·AGAINST·ALL_PRIOR·ALL = 4.2857 [n=14, MEDIUM]
- corners·AGAINST·W5·ALL = 3.4 [n=5, LOW]
- corners·AGAINST·W10·ALL = 3.9 [n=10, MEDIUM]
- corners·AGAINST·ALL_PRIOR·HOME = 3.7143 [n=7, LOW]
- corners·AGAINST·ALL_PRIOR·AWAY = 4.8571 [n=7, LOW]
- final_third_entries·FOR·ALL_PRIOR·ALL = 46.4286 [n=14, MEDIUM]
- final_third_entries·FOR·W5·ALL = 46.8 [n=5, LOW]
- final_third_entries·FOR·W10·ALL = 47.5 [n=10, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·HOME = 49.0 [n=7, LOW]
- final_third_entries·FOR·ALL_PRIOR·AWAY = 43.8571 [n=7, LOW]
- final_third_entries·AGAINST·ALL_PRIOR·ALL = 58.7143 [n=14, MEDIUM]
- final_third_entries·AGAINST·W5·ALL = 49.2 [n=5, LOW]
- final_third_entries·AGAINST·W10·ALL = 56.6 [n=10, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·HOME = 54.8571 [n=7, LOW]
- final_third_entries·AGAINST·ALL_PRIOR·AWAY = 62.5714 [n=7, LOW]
- fouls·FOR·ALL_PRIOR·ALL = 13.1538 [n=13, MEDIUM]
- fouls·FOR·W5·ALL = 10.6 [n=5, LOW]
- fouls·FOR·W10·ALL = 13.6667 [n=9, MEDIUM]
- fouls·FOR·ALL_PRIOR·HOME = 13.1429 [n=7, LOW]
- fouls·FOR·ALL_PRIOR·AWAY = 13.1667 [n=6, LOW]
- fouls·AGAINST·ALL_PRIOR·ALL = 11.7692 [n=13, MEDIUM]
- fouls·AGAINST·W5·ALL = 12.0 [n=5, LOW]
- fouls·AGAINST·W10·ALL = 11.5556 [n=9, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·HOME = 12.0 [n=7, LOW]
- fouls·AGAINST·ALL_PRIOR·AWAY = 11.5 [n=6, LOW]
- goals·FOR·ALL_PRIOR·ALL = 1.1429 [n=14, MEDIUM]
- goals·FOR·W5·ALL = 1.8 [n=5, LOW]
- goals·FOR·W10·ALL = 1.5 [n=10, MEDIUM]
- goals·FOR·ALL_PRIOR·HOME = 0.7143 [n=7, LOW]
- goals·FOR·ALL_PRIOR·AWAY = 1.5714 [n=7, LOW]
- goals·AGAINST·ALL_PRIOR·ALL = 1.3571 [n=14, MEDIUM]
- goals·AGAINST·W5·ALL = 1.2 [n=5, LOW]
- goals·AGAINST·W10·ALL = 1.2 [n=10, MEDIUM]
- goals·AGAINST·ALL_PRIOR·HOME = 1.0 [n=7, LOW]
- goals·AGAINST·ALL_PRIOR·AWAY = 1.7143 [n=7, LOW]
- interceptions·FOR·ALL_PRIOR·ALL = 8.5 [n=14, MEDIUM]
- interceptions·FOR·W5·ALL = 7.4 [n=5, LOW]
- interceptions·FOR·W10·ALL = 8.9 [n=10, MEDIUM]
- interceptions·FOR·ALL_PRIOR·HOME = 8.2857 [n=7, LOW]
- interceptions·FOR·ALL_PRIOR·AWAY = 8.7143 [n=7, LOW]
- interceptions·AGAINST·ALL_PRIOR·ALL = 7.4286 [n=14, MEDIUM]
- interceptions·AGAINST·W5·ALL = 9.6 [n=5, LOW]
- interceptions·AGAINST·W10·ALL = 7.6 [n=10, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·HOME = 7.4286 [n=7, LOW]
- interceptions·AGAINST·ALL_PRIOR·AWAY = 7.4286 [n=7, LOW]
- npxg·FOR·ALL_PRIOR·ALL = 0.2625 [n=4, LOW]
- npxg·FOR·W5·ALL = 0.2625 [n=4, LOW]
- npxg·FOR·W10·ALL = 0.2625 [n=4, LOW]
- npxg·FOR·ALL_PRIOR·HOME = 0.3233 [n=3, LOW]
- npxg·AGAINST·ALL_PRIOR·ALL = 0.2525 [n=4, LOW]
- npxg·AGAINST·W5·ALL = 0.2525 [n=4, LOW]
- npxg·AGAINST·W10·ALL = 0.2525 [n=4, LOW]
- npxg·AGAINST·ALL_PRIOR·HOME = 0.19 [n=3, LOW]
- offsides·FOR·ALL_PRIOR·ALL = 1.8333 [n=12, MEDIUM]
- offsides·FOR·W5·ALL = 1.6 [n=5, LOW]
- offsides·FOR·W10·ALL = 1.8889 [n=9, MEDIUM]
- offsides·FOR·ALL_PRIOR·HOME = 2.0 [n=7, LOW]
- offsides·FOR·ALL_PRIOR·AWAY = 1.6 [n=5, LOW]
- offsides·AGAINST·ALL_PRIOR·ALL = 1.75 [n=12, MEDIUM]
- offsides·AGAINST·W5·ALL = 1.8 [n=5, LOW]
- offsides·AGAINST·W10·ALL = 1.6667 [n=9, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·HOME = 1.7143 [n=7, LOW]
- offsides·AGAINST·ALL_PRIOR·AWAY = 1.8 [n=5, LOW]
- possession·FOR·ALL_PRIOR·ALL = 46.8571 [n=14, MEDIUM]
- possession·FOR·W5·ALL = 52.8 [n=5, LOW]
- possession·FOR·W10·ALL = 48.6 [n=10, MEDIUM]
- possession·FOR·ALL_PRIOR·HOME = 51.2857 [n=7, LOW]
- possession·FOR·ALL_PRIOR·AWAY = 42.4286 [n=7, LOW]
- possession·AGAINST·ALL_PRIOR·ALL = 53.1429 [n=14, MEDIUM]
- possession·AGAINST·W5·ALL = 47.2 [n=5, LOW]
- possession·AGAINST·W10·ALL = 51.4 [n=10, MEDIUM]
- possession·AGAINST·ALL_PRIOR·HOME = 48.7143 [n=7, LOW]
- possession·AGAINST·ALL_PRIOR·AWAY = 57.5714 [n=7, LOW]
- red_cards·FOR·ALL_PRIOR·ALL = 0.1429 [n=14, MEDIUM]
- red_cards·FOR·W5·ALL = 0.0 [n=5, LOW]
- red_cards·FOR·W10·ALL = 0.1 [n=10, MEDIUM]
- red_cards·FOR·ALL_PRIOR·HOME = 0.1429 [n=7, LOW]
- red_cards·FOR·ALL_PRIOR·AWAY = 0.1429 [n=7, LOW]
- red_cards·AGAINST·ALL_PRIOR·ALL = 0.2857 [n=14, MEDIUM]
- red_cards·AGAINST·W5·ALL = 0.6 [n=5, LOW]
- red_cards·AGAINST·W10·ALL = 0.4 [n=10, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·HOME = 0.2857 [n=7, LOW]
- red_cards·AGAINST·ALL_PRIOR·AWAY = 0.2857 [n=7, LOW]
- saves·FOR·ALL_PRIOR·ALL = 2.7857 [n=14, MEDIUM]
- saves·FOR·W5·ALL = 1.6 [n=5, LOW]
- saves·FOR·W10·ALL = 2.6 [n=10, MEDIUM]
- saves·FOR·ALL_PRIOR·HOME = 2.8571 [n=7, LOW]
- saves·FOR·ALL_PRIOR·AWAY = 2.7143 [n=7, LOW]
- saves·AGAINST·ALL_PRIOR·ALL = 2.8571 [n=14, MEDIUM]
- saves·AGAINST·W5·ALL = 3.6 [n=5, LOW]
- saves·AGAINST·W10·ALL = 2.9 [n=10, MEDIUM]
- saves·AGAINST·ALL_PRIOR·HOME = 2.2857 [n=7, LOW]
- saves·AGAINST·ALL_PRIOR·AWAY = 3.4286 [n=7, LOW]
- shots_inside_box·FOR·ALL_PRIOR·ALL = 6.2857 [n=14, MEDIUM]
- shots_inside_box·FOR·W5·ALL = 8.0 [n=5, LOW]
- shots_inside_box·FOR·W10·ALL = 7.3 [n=10, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·HOME = 6.7143 [n=7, LOW]
- shots_inside_box·FOR·ALL_PRIOR·AWAY = 5.8571 [n=7, LOW]
- shots_inside_box·AGAINST·ALL_PRIOR·ALL = 8.7857 [n=14, MEDIUM]
- shots_inside_box·AGAINST·W5·ALL = 5.8 [n=5, LOW]
- shots_inside_box·AGAINST·W10·ALL = 8.2 [n=10, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·HOME = 7.4286 [n=7, LOW]
- shots_inside_box·AGAINST·ALL_PRIOR·AWAY = 10.1429 [n=7, LOW]
- shots_off_target·FOR·ALL_PRIOR·ALL = 4.5714 [n=14, MEDIUM]
- shots_off_target·FOR·W5·ALL = 6.0 [n=5, LOW]
- shots_off_target·FOR·W10·ALL = 4.9 [n=10, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·HOME = 4.5714 [n=7, LOW]
- shots_off_target·FOR·ALL_PRIOR·AWAY = 4.5714 [n=7, LOW]
- shots_off_target·AGAINST·ALL_PRIOR·ALL = 5.7143 [n=14, MEDIUM]
- shots_off_target·AGAINST·W5·ALL = 4.6 [n=5, LOW]
- shots_off_target·AGAINST·W10·ALL = 6.0 [n=10, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·HOME = 4.2857 [n=7, LOW]
- shots_off_target·AGAINST·ALL_PRIOR·AWAY = 7.1429 [n=7, LOW]
- shots_on_target·FOR·ALL_PRIOR·ALL = 3.9286 [n=14, MEDIUM]
- shots_on_target·FOR·W5·ALL = 5.6 [n=5, LOW]
- shots_on_target·FOR·W10·ALL = 4.5 [n=10, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·HOME = 2.8571 [n=7, LOW]
- shots_on_target·FOR·ALL_PRIOR·AWAY = 5.0 [n=7, LOW]
- shots_on_target·AGAINST·ALL_PRIOR·ALL = 4.3571 [n=14, MEDIUM]
- shots_on_target·AGAINST·W5·ALL = 3.0 [n=5, LOW]
- shots_on_target·AGAINST·W10·ALL = 4.0 [n=10, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·HOME = 4.1429 [n=7, LOW]
- shots_on_target·AGAINST·ALL_PRIOR·AWAY = 4.5714 [n=7, LOW]
- shots_outside_box·FOR·ALL_PRIOR·ALL = 4.7857 [n=14, MEDIUM]
- shots_outside_box·FOR·W5·ALL = 5.8 [n=5, LOW]
- shots_outside_box·FOR·W10·ALL = 4.7 [n=10, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·HOME = 3.7143 [n=7, LOW]
- shots_outside_box·FOR·ALL_PRIOR·AWAY = 5.8571 [n=7, LOW]
- shots_outside_box·AGAINST·ALL_PRIOR·ALL = 4.4286 [n=14, MEDIUM]
- shots_outside_box·AGAINST·W5·ALL = 4.2 [n=5, LOW]
- shots_outside_box·AGAINST·W10·ALL = 4.7 [n=10, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·HOME = 3.7143 [n=7, LOW]
- shots_outside_box·AGAINST·ALL_PRIOR·AWAY = 5.1429 [n=7, LOW]
- tackles·FOR·ALL_PRIOR·ALL = 18.8571 [n=14, MEDIUM]
- tackles·FOR·W5·ALL = 16.8 [n=5, LOW]
- tackles·FOR·W10·ALL = 19.3 [n=10, MEDIUM]
- tackles·FOR·ALL_PRIOR·HOME = 19.2857 [n=7, LOW]
- tackles·FOR·ALL_PRIOR·AWAY = 18.4286 [n=7, LOW]
- tackles·AGAINST·ALL_PRIOR·ALL = 14.9286 [n=14, MEDIUM]
- tackles·AGAINST·W5·ALL = 12.0 [n=5, LOW]
- tackles·AGAINST·W10·ALL = 15.6 [n=10, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·HOME = 14.1429 [n=7, LOW]
- tackles·AGAINST·ALL_PRIOR·AWAY = 15.7143 [n=7, LOW]
- throw_ins·FOR·ALL_PRIOR·ALL = 18.0714 [n=14, MEDIUM]
- throw_ins·FOR·W5·ALL = 18.2 [n=5, LOW]
- throw_ins·FOR·W10·ALL = 18.9 [n=10, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·HOME = 18.7143 [n=7, LOW]
- throw_ins·FOR·ALL_PRIOR·AWAY = 17.4286 [n=7, LOW]
- throw_ins·AGAINST·ALL_PRIOR·ALL = 20.2857 [n=14, MEDIUM]
- throw_ins·AGAINST·W5·ALL = 17.4 [n=5, LOW]
- throw_ins·AGAINST·W10·ALL = 20.7 [n=10, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·HOME = 19.0 [n=7, LOW]
- throw_ins·AGAINST·ALL_PRIOR·AWAY = 21.5714 [n=7, LOW]
- total_shots·FOR·ALL_PRIOR·ALL = 11.0714 [n=14, MEDIUM]
- total_shots·FOR·W5·ALL = 13.8 [n=5, LOW]
- total_shots·FOR·W10·ALL = 12.0 [n=10, MEDIUM]
- total_shots·FOR·ALL_PRIOR·HOME = 10.4286 [n=7, LOW]
- total_shots·FOR·ALL_PRIOR·AWAY = 11.7143 [n=7, LOW]
- total_shots·AGAINST·ALL_PRIOR·ALL = 13.2143 [n=14, MEDIUM]
- total_shots·AGAINST·W5·ALL = 10.0 [n=5, LOW]
- total_shots·AGAINST·W10·ALL = 12.9 [n=10, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·HOME = 11.1429 [n=7, LOW]
- total_shots·AGAINST·ALL_PRIOR·AWAY = 15.2857 [n=7, LOW]
- touches_in_box·FOR·ALL_PRIOR·ALL = 17.9286 [n=14, MEDIUM]
- touches_in_box·FOR·W5·ALL = 24.2 [n=5, LOW]
- touches_in_box·FOR·W10·ALL = 21.5 [n=10, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·HOME = 21.2857 [n=7, LOW]
- touches_in_box·FOR·ALL_PRIOR·AWAY = 14.5714 [n=7, LOW]
- touches_in_box·AGAINST·ALL_PRIOR·ALL = 22.6429 [n=14, MEDIUM]
- touches_in_box·AGAINST·W5·ALL = 16.2 [n=5, LOW]
- touches_in_box·AGAINST·W10·ALL = 21.0 [n=10, MEDIUM]
- touches_in_box·AGAINST·ALL_PRIOR·HOME = 20.2857 [n=7, LOW]
- touches_in_box·AGAINST·ALL_PRIOR·AWAY = 25.0 [n=7, LOW]
- xg·FOR·ALL_PRIOR·ALL = 0.8964 [n=14, MEDIUM]
- xg·FOR·W5·ALL = 1.226 [n=5, LOW]
- xg·FOR·W10·ALL = 1.106 [n=10, MEDIUM]
- xg·FOR·ALL_PRIOR·HOME = 0.7671 [n=7, LOW]
- xg·FOR·ALL_PRIOR·AWAY = 1.0257 [n=7, LOW]
- xg·AGAINST·ALL_PRIOR·ALL = 1.7893 [n=14, MEDIUM]
- xg·AGAINST·W5·ALL = 1.112 [n=5, LOW]
- xg·AGAINST·W10·ALL = 1.627 [n=10, MEDIUM]
- xg·AGAINST·ALL_PRIOR·HOME = 1.56 [n=7, LOW]
- xg·AGAINST·ALL_PRIOR·AWAY = 2.0186 [n=7, LOW]
- yellow_cards·FOR·ALL_PRIOR·ALL = 1.2857 [n=14, MEDIUM]
- yellow_cards·FOR·W5·ALL = 1.0 [n=5, LOW]
- yellow_cards·FOR·W10·ALL = 1.5 [n=10, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·HOME = 1.0 [n=7, LOW]
- yellow_cards·FOR·ALL_PRIOR·AWAY = 1.5714 [n=7, LOW]
- yellow_cards·AGAINST·ALL_PRIOR·ALL = 2.5 [n=14, MEDIUM]
- yellow_cards·AGAINST·W5·ALL = 2.4 [n=5, LOW]
- yellow_cards·AGAINST·W10·ALL = 2.5 [n=10, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·HOME = 2.4286 [n=7, LOW]
- yellow_cards·AGAINST·ALL_PRIOR·AWAY = 2.5714 [n=7, LOW]

### Arm B — opponent-profile context (deterministic bands)

```json
{
 "axes": {
  "accurate_crosses_for": {
   "AWAY": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   },
   "HOME": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "corners_against": {
   "AWAY": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   },
   "HOME": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "corners_for": {
   "AWAY": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "goals_against": {
   "AWAY": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "goals_for": {
   "AWAY": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "possession_for": {
   "AWAY": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "shots_on_target_against": {
   "AWAY": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  },
  "shots_on_target_for": {
   "AWAY": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 29,
    "candidate_n": 29,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  }
 },
 "similarity_version": "opponent_similarity_v1_pending"
}
```

---

## mt_012232295

- PIT-safe matches available: **74**; match rows included (both teams): **60**; omitted: **14** (reason: `frozen_history_policy(max_matches_per_team=30)`); UNEXPLAINED_OMISSION: **0**.
- Metric cell exposure rate (non-null of serialized): **0.959**; derived summaries: **466**.
- Availability map: `{"expected_formation": "UNAVAILABLE", "formation": "LOW_COVERAGE", "half_time_state": "UNAVAILABLE", "injuries": "UNAVAILABLE", "lineup": "PIT_UNSAFE", "opponent_profile": "AVAILABLE", "recent_vs_long": "AVAILABLE", "red_cards": "AVAILABLE", "temporal_event_state": "UNAVAILABLE", "venue": "AVAILABLE", "xg": "AVAILABLE"}`
- Arm A packet hash: `354341bb6f586d7f156d73fa3f37b003b517a38c19fb61092d5a843bfb06361a`
- Arm B packet hash: `62b8e2d452ff352bb87e8b63157cb32ab5ccf17078d61b6b92e288cde0424cd4`

### Arm A — frozen V3 compressed evidence (all items)

76 unconditional shrunk scalar items (venue=ALL, window=ALL_PRIOR):

| id | metric | value | n | reliability |
|---|---|---|---|---|
| HOME_ATK_corners_406027 | corners_for | 5.2968 | 37 | HIGH |
| HOME_DEF_corners_7cfac3 | corners_against | 5.1805 | 37 | HIGH |
| HOME_ATK_accurate_crosses_c28b9e | accurate_crosses_for | 4.6259 | 37 | HIGH |
| HOME_DEF_accurate_crosses_81ffb5 | accurate_crosses_against | 3.5328 | 37 | HIGH |
| HOME_ATK_total_shots_808ac9 | total_shots_for | 15.0069 | 37 | HIGH |
| HOME_DEF_total_shots_c0e347 | total_shots_against | 10.9604 | 37 | HIGH |
| HOME_ATK_shots_on_target_e955e0 | shots_on_target_for | 5.3322 | 37 | HIGH |
| HOME_DEF_shots_on_target_8a3812 | shots_on_target_against | 3.774 | 37 | HIGH |
| HOME_ATK_shots_off_target_11e91f | shots_off_target_for | 5.1519 | 37 | HIGH |
| HOME_DEF_shots_off_target_26031c | shots_off_target_against | 3.8264 | 37 | HIGH |
| HOME_ATK_blocked_shots_5198f8 | blocked_shots_for | 4.5228 | 37 | HIGH |
| HOME_DEF_blocked_shots_09c3c4 | blocked_shots_against | 3.36 | 37 | HIGH |
| HOME_ATK_shots_inside_box_cf538d | shots_inside_box_for | 10.1889 | 37 | HIGH |
| HOME_DEF_shots_inside_box_e6b28d | shots_inside_box_against | 7.0493 | 37 | HIGH |
| HOME_ATK_touches_in_box_759ed8 | touches_in_box_for | 22.1235 | 3 | LOW |
| HOME_DEF_touches_in_box_94cd98 | touches_in_box_against | 24.1235 | 3 | LOW |
| HOME_ATK_final_third_entries_5aa0be | final_third_entries_for | 59.5201 | 37 | HIGH |
| HOME_DEF_final_third_entries_4a40ef | final_third_entries_against | 54.4969 | 37 | HIGH |
| HOME_ATK_possession_190f3f | possession_for | 53.1628 | 37 | HIGH |
| HOME_DEF_possession_f8ada9 | possession_against | 46.8372 | 37 | HIGH |
| HOME_ATK_tackles_65b6c1 | tackles_for | 16.0896 | 37 | HIGH |
| HOME_DEF_tackles_e3c85e | tackles_against | 15.5082 | 37 | HIGH |
| HOME_ATK_fouls_8107c6 | fouls_for | 12.0613 | 37 | HIGH |
| HOME_DEF_fouls_b6d53c | fouls_against | 10.5031 | 37 | HIGH |
| HOME_ATK_yellow_cards_80b7a4 | yellow_cards_for | 2.3641 | 35 | HIGH |
| HOME_DEF_yellow_cards_8ee8aa | yellow_cards_against | 2.047 | 35 | HIGH |
| HOME_ATK_clearances_ec2e18 | clearances_for | 16.9225 | 37 | HIGH |
| HOME_DEF_clearances_6d3f4c | clearances_against | 19.3644 | 37 | HIGH |
| HOME_ATK_interceptions_967965 | interceptions_for | 9.0335 | 37 | HIGH |
| HOME_DEF_interceptions_c82020 | interceptions_against | 11.1265 | 37 | HIGH |
| HOME_ATK_goals_08b15b | goals_for | 1.9117 | 37 | HIGH |
| HOME_DEF_goals_d53fdd | goals_against | 1.3303 | 37 | HIGH |
| HOME_ATK_throw_ins_b24629 | throw_ins_for | 22.9871 | 37 | HIGH |
| HOME_DEF_throw_ins_208262 | throw_ins_against | 21.8243 | 37 | HIGH |
| HOME_ATK_big_chances_8a9e2f | big_chances_for | 2.4486 | 35 | HIGH |
| HOME_DEF_big_chances_885151 | big_chances_against | 1.6925 | 35 | HIGH |
| HOME_ATK_saves_6bda8d | saves_for | 2.5328 | 37 | HIGH |
| HOME_DEF_saves_19ae14 | saves_against | 3.4631 | 37 | HIGH |
| AWAY_ATK_corners_ca1538 | corners_for | 5.3898 | 37 | HIGH |
| AWAY_DEF_corners_598e33 | corners_against | 4.9015 | 37 | HIGH |
| AWAY_ATK_accurate_crosses_005290 | accurate_crosses_for | 4.2073 | 37 | HIGH |
| AWAY_DEF_accurate_crosses_287e9c | accurate_crosses_against | 3.8584 | 37 | HIGH |
| AWAY_ATK_total_shots_004f7a | total_shots_for | 11.4023 | 37 | HIGH |
| AWAY_DEF_total_shots_403d28 | total_shots_against | 12.1232 | 37 | HIGH |
| AWAY_ATK_shots_on_target_9afd02 | shots_on_target_for | 3.4019 | 37 | HIGH |
| AWAY_DEF_shots_on_target_dcda5e | shots_on_target_against | 3.8671 | 37 | HIGH |
| AWAY_ATK_shots_off_target_b83815 | shots_off_target_for | 4.6868 | 37 | HIGH |
| AWAY_DEF_shots_off_target_5fe2d0 | shots_off_target_against | 4.431 | 37 | HIGH |
| AWAY_ATK_blocked_shots_93d965 | blocked_shots_for | 3.3135 | 37 | HIGH |
| AWAY_DEF_blocked_shots_97ef03 | blocked_shots_against | 3.8251 | 37 | HIGH |
| AWAY_ATK_shots_inside_box_567ee5 | shots_inside_box_for | 7.2354 | 37 | HIGH |
| AWAY_DEF_shots_inside_box_446c80 | shots_inside_box_against | 7.0959 | 37 | HIGH |
| AWAY_ATK_touches_in_box_2c76ca | touches_in_box_for | 22.1235 | 3 | LOW |
| AWAY_DEF_touches_in_box_319da5 | touches_in_box_against | 19.7901 | 3 | LOW |
| AWAY_ATK_final_third_entries_5a0987 | final_third_entries_for | 50.9387 | 37 | HIGH |
| AWAY_DEF_final_third_entries_ed75cd | final_third_entries_against | 61.2876 | 37 | HIGH |
| AWAY_ATK_possession_82105a | possession_for | 44.7442 | 37 | HIGH |
| AWAY_DEF_possession_012ecc | possession_against | 55.2558 | 37 | HIGH |
| AWAY_ATK_tackles_0865bc | tackles_for | 16.7175 | 37 | HIGH |
| AWAY_DEF_tackles_3e6a7d | tackles_against | 16.8803 | 37 | HIGH |
| AWAY_ATK_fouls_97bf91 | fouls_for | 12.4566 | 37 | HIGH |
| AWAY_DEF_fouls_94f7aa | fouls_against | 10.3171 | 37 | HIGH |
| AWAY_ATK_yellow_cards_120c77 | yellow_cards_for | 2.3472 | 37 | HIGH |
| AWAY_DEF_yellow_cards_367397 | yellow_cards_against | 2.0449 | 37 | HIGH |
| AWAY_ATK_clearances_74617f | clearances_for | 19.2714 | 37 | HIGH |
| AWAY_DEF_clearances_8bdc80 | clearances_against | 20.3876 | 37 | HIGH |
| AWAY_ATK_interceptions_404e22 | interceptions_for | 9.3125 | 37 | HIGH |
| AWAY_DEF_interceptions_4be11b | interceptions_against | 8.1963 | 37 | HIGH |
| AWAY_ATK_goals_5d2c6a | goals_for | 0.8884 | 37 | HIGH |
| AWAY_DEF_goals_4ad3b7 | goals_against | 1.4698 | 37 | HIGH |
| AWAY_ATK_throw_ins_64d189 | throw_ins_for | 22.7313 | 37 | HIGH |
| AWAY_DEF_throw_ins_35916f | throw_ins_against | 25.8011 | 37 | HIGH |
| AWAY_ATK_big_chances_065222 | big_chances_for | 1.451 | 37 | HIGH |
| AWAY_DEF_big_chances_d5f920 | big_chances_against | 2.1021 | 37 | HIGH |
| AWAY_ATK_saves_50b33b | saves_for | 2.3003 | 37 | HIGH |
| AWAY_DEF_saves_bf5cbb | saves_against | 2.4398 | 37 | HIGH |

### Arm B — HOME_TEAM match-level matrix (30 rows × 55 cols)

Columns: `match_alias, kickoff_unix, competition, venue, opponent_alias, own_formation_family, opponent_formation_family, accurate_crosses_for, accurate_crosses_against, big_chances_for, big_chances_against, blocked_shots_for, blocked_shots_against, clearances_for, clearances_against, corners_for, corners_against, final_third_entries_for, final_third_entries_against, fouls_for, fouls_against, goals_for, goals_against, interceptions_for, interceptions_against, npxg_for, npxg_against, offsides_for, offsides_against, possession_for, possession_against, red_cards_for, red_cards_against, saves_for, saves_against, shots_inside_box_for, shots_inside_box_against, shots_off_target_for, shots_off_target_against, shots_on_target_for, shots_on_target_against, shots_outside_box_for, shots_outside_box_against, tackles_for, tackles_against, throw_ins_for, throw_ins_against, total_shots_for, total_shots_against, touches_in_box_for, touches_in_box_against, xg_for, xg_against, yellow_cards_for, yellow_cards_against`

| match_alias | kickoff_unix | competition | venue | opponent_alias | own_formation_family | opponent_formation_family | accurate_crosses_for | accurate_crosses_against | big_chances_for | big_chances_against | blocked_shots_for | blocked_shots_against | clearances_for | clearances_against | corners_for | corners_against | final_third_entries_for | final_third_entries_against | fouls_for | fouls_against | goals_for | goals_against | interceptions_for | interceptions_against | npxg_for | npxg_against | offsides_for | offsides_against | possession_for | possession_against | red_cards_for | red_cards_against | saves_for | saves_against | shots_inside_box_for | shots_inside_box_against | shots_off_target_for | shots_off_target_against | shots_on_target_for | shots_on_target_against | shots_outside_box_for | shots_outside_box_against | tackles_for | tackles_against | throw_ins_for | throw_ins_against | total_shots_for | total_shots_against | touches_in_box_for | touches_in_box_against | xg_for | xg_against | yellow_cards_for | yellow_cards_against |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| m_mt_743352067 | 1695477600 | COMPETITION | HOME | OPP_001 |  |  | 9.0 | 3.0 | 2.0 | 2.0 | 10.0 | 4.0 | 6.0 | 18.0 | 10.0 | 5.0 | 57.0 | 57.0 | 10.0 | 13.0 | 4.0 | 3.0 | 7.0 | 14.0 | 3.04 | 0.92 | 0.0 | 4.0 | 40.0 | 60.0 | 0.0 | 0.0 | 3.0 | 7.0 | 24.0 | 6.0 | 8.0 | 1.0 | 11.0 | 5.0 | 5.0 | 4.0 | 22.0 | 9.0 | 20.0 | 24.0 | 29.0 | 10.0 |  |  | 3.03 | 0.92 | 3.0 | 4.0 |
| m_mt_978826308 | 1696082400 | COMPETITION | AWAY | OPP_002 |  |  | 10.0 | 4.0 | 3.0 | 1.0 | 9.0 | 2.0 | 13.0 | 25.0 | 6.0 | 5.0 | 64.0 | 77.0 | 11.0 | 10.0 | 1.0 | 1.0 | 6.0 | 10.0 | 1.18 | 1.26 | 1.0 | 3.0 | 61.0 | 39.0 | 0.0 | 0.0 | 5.0 | 5.0 | 15.0 | 6.0 | 6.0 | 4.0 | 6.0 | 6.0 | 6.0 | 6.0 | 10.0 | 11.0 | 18.0 | 23.0 | 21.0 | 12.0 |  |  | 1.3 | 1.26 | 3.0 | 3.0 |
| m_mt_978826361 | 1696358700 | COMPETITION | HOME | OPP_003 |  |  | 1.0 | 0.0 | 0.0 | 2.0 | 3.0 | 3.0 | 7.0 | 18.0 | 6.0 | 5.0 | 50.0 | 42.0 | 16.0 | 11.0 | 3.0 | 0.0 | 9.0 | 11.0 | 1.21 | 0.93 | 1.0 | 1.0 | 50.0 | 50.0 | 0.0 | 0.0 | 6.0 | 3.0 | 9.0 | 6.0 | 5.0 | 4.0 | 6.0 | 6.0 | 5.0 | 7.0 | 14.0 | 14.0 | 16.0 | 13.0 | 14.0 | 13.0 |  |  | 1.21 | 0.93 |  |  |
| m_mt_624491048 | 1696687200 | COMPETITION | HOME | OPP_004 |  |  | 3.0 | 2.0 | 3.0 | 1.0 | 4.0 | 2.0 | 14.0 | 19.0 | 7.0 | 0.0 | 50.0 | 65.0 | 10.0 | 11.0 | 4.0 | 2.0 | 11.0 | 12.0 | 2.37 | 0.33 | 3.0 | 3.0 | 55.0 | 45.0 | 0.0 | 0.0 | 0.0 | 6.0 | 8.0 | 5.0 | 2.0 | 4.0 | 10.0 | 2.0 | 8.0 | 3.0 | 14.0 | 15.0 | 18.0 | 23.0 | 16.0 | 8.0 |  |  | 2.44 | 0.33 | 0.0 | 3.0 |
| m_mt_012238598 | 1698259500 | COMPETITION | AWAY | OPP_005 |  |  | 2.0 | 3.0 | 1.0 | 2.0 | 8.0 | 4.0 | 18.0 | 14.0 | 1.0 | 5.0 | 51.0 | 63.0 | 15.0 | 11.0 | 1.0 | 0.0 | 12.0 | 17.0 | 1.76 | 0.76 | 0.0 | 1.0 | 51.0 | 49.0 | 0.0 | 0.0 | 4.0 | 5.0 | 12.0 | 6.0 | 6.0 | 3.0 | 6.0 | 4.0 | 8.0 | 5.0 | 17.0 | 18.0 | 23.0 | 19.0 | 20.0 | 11.0 |  |  | 1.75 | 0.76 | 4.0 | 0.0 |
| m_mt_581147997 | 1698501600 | COMPETITION | HOME | OPP_006 |  |  | 5.0 | 2.0 | 4.0 | 3.0 | 9.0 | 1.0 | 14.0 | 18.0 | 11.0 | 3.0 | 66.0 | 42.0 | 11.0 | 7.0 | 3.0 | 2.0 | 8.0 | 11.0 | 2.05 | 1.61 | 4.0 | 0.0 | 55.0 | 45.0 | 0.0 | 0.0 | 4.0 | 2.0 | 14.0 | 4.0 | 2.0 | 2.0 | 4.0 | 6.0 | 1.0 | 5.0 | 24.0 | 18.0 | 24.0 | 23.0 | 15.0 | 9.0 |  |  | 2.05 | 1.61 | 4.0 | 2.0 |
| m_mt_250079123 | 1699110000 | COMPETITION | AWAY | OPP_007 |  |  | 6.0 | 4.0 | 3.0 | 2.0 | 8.0 | 5.0 | 16.0 | 21.0 | 8.0 | 7.0 | 60.0 | 50.0 | 11.0 | 9.0 | 2.0 | 2.0 | 9.0 | 19.0 | 1.88 | 0.86 | 3.0 | 2.0 | 67.0 | 33.0 | 0.0 | 0.0 | 2.0 | 5.0 | 13.0 | 6.0 | 2.0 | 5.0 | 7.0 | 3.0 | 4.0 | 7.0 | 21.0 | 23.0 | 38.0 | 28.0 | 17.0 | 13.0 |  |  | 1.68 | 0.86 | 1.0 | 3.0 |
| m_mt_014824725 | 1699387200 | COMPETITION | AWAY | OPP_008 |  |  | 10.0 | 2.0 | 1.0 | 3.0 | 5.0 | 1.0 | 28.0 | 32.0 | 8.0 | 6.0 | 75.0 | 56.0 | 10.0 | 12.0 | 2.0 | 2.0 | 10.0 | 16.0 | 0.92 | 1.13 | 5.0 | 2.0 | 71.0 | 29.0 | 0.0 | 0.0 | 1.0 | 1.0 | 7.0 | 4.0 | 5.0 | 4.0 | 3.0 | 3.0 | 6.0 | 4.0 | 9.0 | 7.0 | 17.0 | 22.0 | 13.0 | 8.0 |  |  | 0.92 | 1.25 | 1.0 | 1.0 |
| m_mt_367710354 | 1699714800 | COMPETITION | HOME | OPP_009 |  |  | 5.0 | 2.0 | 7.0 | 3.0 | 4.0 | 3.0 | 13.0 | 14.0 | 6.0 | 2.0 | 43.0 | 68.0 | 15.0 | 9.0 | 3.0 | 2.0 | 10.0 | 6.0 | 3.04 | 1.64 | 4.0 | 1.0 | 38.0 | 62.0 | 0.0 | 1.0 | 2.0 | 6.0 | 15.0 | 5.0 | 9.0 | 0.0 | 9.0 | 4.0 | 7.0 | 2.0 | 12.0 | 13.0 | 20.0 | 22.0 | 22.0 | 7.0 |  |  | 3.79 | 1.64 | 2.0 | 3.0 |
| m_mt_581147584 | 1700933400 | COMPETITION | AWAY | OPP_010 |  |  | 1.0 | 2.0 | 0.0 | 2.0 | 3.0 | 3.0 | 21.0 | 16.0 | 5.0 | 4.0 | 45.0 | 47.0 | 12.0 | 5.0 | 0.0 | 2.0 | 8.0 | 7.0 | 0.24 | 1.7 | 3.0 | 1.0 | 51.0 | 49.0 | 0.0 | 0.0 | 2.0 | 0.0 | 3.0 | 6.0 | 3.0 | 3.0 | 0.0 | 4.0 | 3.0 | 4.0 | 13.0 | 11.0 | 23.0 | 27.0 | 6.0 | 10.0 |  |  | 0.23 | 1.7 | 2.0 | 1.0 |
| m_mt_012238025 | 1701288000 | COMPETITION | HOME | OPP_011 |  |  | 5.0 | 2.0 |  |  | 7.0 | 1.0 | 14.0 | 9.0 | 4.0 | 2.0 | 67.0 | 60.0 | 9.0 | 13.0 | 3.0 | 1.0 | 10.0 | 10.0 | 1.34 | 0.38 | 4.0 | 0.0 | 60.0 | 40.0 | 0.0 | 0.0 | 2.0 | 4.0 | 13.0 | 4.0 | 5.0 | 1.0 | 7.0 | 3.0 | 6.0 | 1.0 | 19.0 | 16.0 | 20.0 | 24.0 | 19.0 | 5.0 |  |  | 1.32 | 0.38 | 2.0 | 3.0 |
| m_mt_978826914 | 1701529200 | COMPETITION | HOME | OPP_012 |  |  | 1.0 | 6.0 | 2.0 | 1.0 | 3.0 | 6.0 | 20.0 | 10.0 | 1.0 | 6.0 | 49.0 | 48.0 | 14.0 | 11.0 | 2.0 | 1.0 | 10.0 | 11.0 | 1.72 | 0.59 | 1.0 | 4.0 | 55.0 | 45.0 | 0.0 | 0.0 | 1.0 | 1.0 | 8.0 | 6.0 | 7.0 | 8.0 | 3.0 | 1.0 | 5.0 | 9.0 | 4.0 | 24.0 | 16.0 | 20.0 | 13.0 | 15.0 |  |  | 1.72 | 1.38 | 2.0 | 1.0 |
| m_mt_978828227 | 1702134000 | COMPETITION | AWAY | OPP_013 |  |  | 1.0 | 4.0 | 1.0 | 0.0 | 2.0 | 3.0 | 13.0 | 8.0 | 3.0 | 5.0 | 52.0 | 47.0 | 14.0 | 15.0 | 2.0 | 0.0 | 8.0 | 8.0 | 0.94 | 0.49 | 2.0 | 2.0 | 47.0 | 53.0 | 0.0 | 0.0 | 2.0 | 1.0 | 7.0 | 6.0 | 4.0 | 3.0 | 3.0 | 1.0 | 2.0 | 1.0 | 22.0 | 10.0 | 15.0 | 21.0 | 9.0 | 7.0 |  |  | 0.94 | 0.49 | 3.0 | 1.0 |
| m_mt_978828216 | 1702410300 | COMPETITION | AWAY | OPP_014 |  |  | 4.0 | 5.0 | 2.0 | 2.0 | 2.0 | 4.0 | 18.0 | 10.0 | 4.0 | 6.0 | 60.0 | 46.0 | 16.0 | 12.0 | 2.0 | 1.0 | 4.0 | 12.0 | 1.85 | 1.49 | 1.0 | 3.0 | 53.0 | 47.0 | 0.0 | 0.0 | 2.0 | 4.0 | 6.0 | 9.0 | 2.0 | 5.0 | 6.0 | 3.0 | 4.0 | 3.0 | 19.0 | 19.0 | 24.0 | 26.0 | 10.0 | 12.0 |  |  | 1.82 | 1.48 | 4.0 | 2.0 |
| m_mt_195565698 | 1702729800 | COMPETITION | HOME | OPP_015 |  |  | 11.0 | 3.0 | 2.0 | 1.0 | 1.0 | 4.0 | 14.0 | 38.0 | 6.0 | 3.0 | 79.0 | 24.0 | 11.0 | 8.0 | 2.0 | 2.0 | 4.0 | 6.0 | 2.07 | 0.81 | 0.0 | 1.0 | 65.0 | 35.0 | 0.0 | 0.0 | 1.0 | 2.0 | 14.0 | 8.0 | 12.0 | 4.0 | 5.0 | 3.0 | 4.0 | 3.0 | 12.0 | 17.0 | 23.0 | 14.0 | 18.0 | 11.0 |  |  | 2.07 | 0.81 | 2.0 | 0.0 |
| m_mt_367717107 | 1703334600 | COMPETITION | AWAY | OPP_016 |  |  | 1.0 | 3.0 | 0.0 | 4.0 | 0.0 | 3.0 | 14.0 | 13.0 | 0.0 | 5.0 | 56.0 | 56.0 | 15.0 | 10.0 | 0.0 | 4.0 | 12.0 | 11.0 | 0.12 | 1.34 | 1.0 | 2.0 | 45.0 | 55.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.0 | 7.0 | 2.0 | 2.0 | 0.0 | 4.0 | 2.0 | 2.0 | 14.0 | 12.0 | 23.0 | 22.0 | 2.0 | 9.0 |  |  | 0.12 | 1.9 | 4.0 | 1.0 |
| m_mt_012232400 | 1703619900 | COMPETITION | HOME | OPP_017 |  |  | 5.0 | 4.0 | 1.0 | 0.0 | 8.0 | 0.0 | 12.0 | 26.0 | 11.0 | 2.0 | 51.0 | 49.0 | 9.0 | 9.0 | 1.0 | 1.0 | 7.0 | 12.0 | 1.08 | 0.3 | 1.0 | 2.0 | 45.0 | 55.0 | 0.0 | 0.0 | 1.0 | 2.0 | 8.0 | 5.0 | 8.0 | 3.0 | 3.0 | 2.0 | 11.0 | 0.0 | 17.0 | 13.0 | 30.0 | 15.0 | 19.0 | 5.0 | 33.0 | 28.0 | 1.07 | 0.3 | 1.0 | 2.0 |
| m_mt_743353964 | 1703879100 | COMPETITION | HOME | OPP_018 |  |  | 4.0 | 4.0 | 1.0 | 1.0 | 0.0 | 4.0 | 19.0 | 25.0 | 5.0 | 9.0 | 58.0 | 50.0 | 13.0 | 5.0 | 0.0 | 0.0 | 13.0 | 15.0 | 0.64 | 0.43 | 3.0 | 0.0 | 54.0 | 46.0 | 0.0 | 0.0 | 2.0 | 5.0 | 5.0 | 7.0 | 2.0 | 4.0 | 5.0 | 2.0 | 2.0 | 3.0 | 15.0 | 13.0 | 23.0 | 18.0 | 7.0 | 10.0 | 16.0 | 17.0 | 0.66 | 0.43 | 3.0 | 2.0 |
| m_mt_624494390 | 1704121200 | COMPETITION | AWAY | OPP_019 |  |  | 11.0 | 2.0 |  |  | 3.0 | 2.0 | 14.0 | 19.0 | 5.0 | 8.0 | 67.0 | 55.0 | 14.0 | 7.0 | 0.0 | 0.0 | 7.0 | 9.0 | 0.57 | 0.26 | 2.0 | 2.0 | 64.0 | 36.0 | 0.0 | 1.0 | 4.0 | 2.0 | 8.0 | 3.0 | 8.0 | 2.0 | 2.0 | 4.0 | 5.0 | 5.0 | 13.0 | 19.0 | 20.0 | 19.0 | 13.0 | 8.0 |  |  | 0.57 | 0.26 | 2.0 | 3.0 |
| m_mt_839909558 | 1705167000 | COMPETITION | HOME | OPP_020 |  |  | 4.0 | 2.0 | 3.0 | 1.0 | 8.0 | 1.0 | 14.0 | 21.0 | 3.0 | 1.0 | 54.0 | 49.0 | 17.0 | 8.0 | 2.0 | 1.0 | 10.0 | 18.0 | 2.26 | 0.8 | 2.0 | 0.0 | 49.0 | 51.0 | 0.0 | 0.0 | 2.0 | 3.0 | 16.0 | 6.0 | 4.0 | 6.0 | 5.0 | 3.0 | 1.0 | 4.0 | 13.0 | 18.0 | 24.0 | 28.0 | 17.0 | 10.0 |  |  | 2.26 | 0.8 | 5.0 | 2.0 |
| m_mt_582116491 | 1705953600 | COMPETITION | AWAY | OPP_017 |  |  | 5.0 | 4.0 | 2.0 | 1.0 | 3.0 | 5.0 | 18.0 | 23.0 | 8.0 | 8.0 | 40.0 | 52.0 | 11.0 | 6.0 | 1.0 | 1.0 | 6.0 | 8.0 | 1.21 | 1.27 | 1.0 | 1.0 | 44.0 | 56.0 | 0.0 | 0.0 | 6.0 | 2.0 | 5.0 | 9.0 | 5.0 | 3.0 | 3.0 | 7.0 | 6.0 | 6.0 | 12.0 | 21.0 | 22.0 | 19.0 | 11.0 | 15.0 |  |  | 1.17 | 1.25 | 3.0 | 1.0 |
| m_mt_250070631 | 1706972400 | COMPETITION | AWAY | OPP_004 |  |  | 7.0 | 1.0 | 4.0 | 1.0 | 7.0 | 5.0 | 22.0 | 32.0 | 3.0 | 6.0 | 90.0 | 63.0 | 8.0 | 13.0 | 2.0 | 3.0 | 7.0 | 20.0 | 3.27 | 0.74 | 0.0 | 1.0 | 66.0 | 34.0 | 0.0 | 0.0 | 1.0 | 7.0 | 17.0 | 7.0 | 9.0 | 2.0 | 9.0 | 3.0 | 8.0 | 3.0 | 9.0 | 11.0 | 29.0 | 19.0 | 25.0 | 10.0 |  |  | 2.6 | 0.74 |  |  |
| m_mt_839909989 | 1707568200 | COMPETITION | HOME | OPP_010 |  |  | 6.0 | 1.0 | 3.0 | 0.0 | 8.0 | 0.0 | 8.0 | 46.0 | 9.0 | 3.0 | 101.0 | 45.0 | 12.0 | 3.0 | 2.0 | 2.0 | 7.0 | 7.0 | 1.9 | 0.4 | 2.0 | 1.0 | 65.0 | 35.0 | 0.0 | 0.0 | 0.0 | 5.0 | 15.0 | 3.0 | 6.0 | 3.0 | 7.0 | 2.0 | 6.0 | 2.0 | 14.0 | 13.0 | 23.0 | 18.0 | 21.0 | 5.0 |  |  | 1.9 | 0.4 | 2.0 | 3.0 |
| m_mt_406671921 | 1707940800 | COMPETITION | AWAY | OPP_011 |  |  | 3.0 | 6.0 | 3.0 | 1.0 | 1.0 | 3.0 | 22.0 | 24.0 | 5.0 | 9.0 | 49.0 | 43.0 | 13.0 | 12.0 | 4.0 | 0.0 | 7.0 | 7.0 | 0.89 | 0.91 | 0.0 | 3.0 | 66.0 | 34.0 | 0.0 | 0.0 | 4.0 | 1.0 | 8.0 | 9.0 | 3.0 | 7.0 | 4.0 | 4.0 | 0.0 | 5.0 | 14.0 | 23.0 | 15.0 | 19.0 | 8.0 | 14.0 |  |  | 1.68 | 0.91 | 1.0 | 3.0 |
| m_mt_406671976 | 1708182000 | COMPETITION | AWAY | OPP_009 |  |  | 2.0 | 7.0 | 2.0 | 1.0 | 4.0 | 5.0 | 41.0 | 11.0 | 6.0 | 9.0 | 46.0 | 70.0 | 13.0 | 5.0 | 2.0 | 1.0 | 11.0 | 11.0 | 1.3 | 1.46 | 1.0 | 1.0 | 41.0 | 59.0 | 0.0 | 0.0 | 2.0 | 4.0 | 11.0 | 11.0 | 5.0 | 7.0 | 6.0 | 3.0 | 4.0 | 4.0 | 14.0 | 21.0 | 20.0 | 28.0 | 15.0 | 15.0 |  |  | 1.3 | 1.48 | 1.0 | 1.0 |
| m_mt_835502567 | 1708458300 | COMPETITION | HOME | OPP_008 |  |  | 4.0 | 2.0 | 7.0 | 3.0 | 0.0 | 4.0 | 26.0 | 6.0 | 2.0 | 6.0 | 40.0 | 69.0 | 16.0 | 16.0 | 4.0 | 3.0 | 10.0 | 8.0 | 2.01 | 0.92 | 1.0 | 3.0 | 47.0 | 53.0 | 0.0 | 0.0 | 2.0 | 3.0 | 11.0 | 9.0 | 4.0 | 4.0 | 7.0 | 5.0 | 0.0 | 4.0 | 11.0 | 15.0 | 24.0 | 27.0 | 11.0 | 13.0 |  |  | 1.77 | 1.71 | 1.0 | 2.0 |
| m_mt_367782567 | 1708786800 | COMPETITION | HOME | OPP_007 |  |  | 6.0 | 4.0 | 8.0 | 1.0 | 10.0 | 3.0 | 10.0 | 12.0 | 7.0 | 5.0 | 68.0 | 39.0 | 11.0 | 14.0 | 3.0 | 1.0 | 16.0 | 13.0 | 2.46 | 0.48 | 2.0 | 2.0 | 60.0 | 40.0 | 0.0 | 0.0 | 3.0 | 6.0 | 18.0 | 5.0 | 7.0 | 4.0 | 9.0 | 4.0 | 8.0 | 6.0 | 25.0 | 18.0 | 23.0 | 27.0 | 26.0 | 11.0 |  |  | 2.46 | 0.48 | 3.0 | 1.0 |
| m_mt_978812927 | 1709391600 | COMPETITION | AWAY | OPP_006 |  |  | 6.0 | 3.0 | 1.0 | 0.0 | 4.0 | 2.0 | 11.0 | 24.0 | 7.0 | 5.0 | 57.0 | 56.0 | 22.0 | 11.0 | 2.0 | 0.0 | 9.0 | 19.0 | 1.03 | 0.52 | 4.0 | 2.0 | 61.0 | 39.0 | 0.0 | 0.0 | 1.0 | 5.0 | 10.0 | 4.0 | 4.0 | 5.0 | 6.0 | 2.0 | 4.0 | 5.0 | 14.0 | 18.0 | 40.0 | 20.0 | 14.0 | 9.0 |  |  | 1.02 | 0.51 | 3.0 | 1.0 |
| m_mt_978812980 | 1709668800 | COMPETITION | HOME | OPP_005 |  |  | 5.0 | 5.0 | 5.0 | 2.0 | 2.0 | 3.0 | 10.0 | 11.0 | 4.0 | 5.0 | 70.0 | 61.0 | 6.0 | 15.0 | 3.0 | 2.0 | 7.0 | 13.0 | 2.21 | 0.97 | 3.0 | 0.0 | 57.0 | 43.0 | 0.0 | 0.0 | 2.0 | 4.0 | 13.0 | 9.0 | 4.0 | 4.0 | 8.0 | 4.0 | 1.0 | 2.0 | 16.0 | 16.0 | 21.0 | 31.0 | 14.0 | 11.0 |  |  | 2.8 | 0.97 | 1.0 | 3.0 |
| m_mt_195506137 | 1709987400 | COMPETITION | AWAY | OPP_021 |  |  | 3.0 | 5.0 | 0.0 | 4.0 | 1.0 | 6.0 | 21.0 | 21.0 | 2.0 | 4.0 | 70.0 | 49.0 | 8.0 | 5.0 | 1.0 | 2.0 | 6.0 | 9.0 | 0.59 | 2.47 | 3.0 | 0.0 | 57.0 | 43.0 | 0.0 | 0.0 | 3.0 | 3.0 | 5.0 | 11.0 | 3.0 | 3.0 | 4.0 | 6.0 | 3.0 | 4.0 | 17.0 | 13.0 | 27.0 | 20.0 | 8.0 | 15.0 |  |  | 0.59 | 2.44 | 1.0 | 0.0 |

### Arm B — AWAY_TEAM match-level matrix (30 rows × 55 cols)

Columns: `match_alias, kickoff_unix, competition, venue, opponent_alias, own_formation_family, opponent_formation_family, accurate_crosses_for, accurate_crosses_against, big_chances_for, big_chances_against, blocked_shots_for, blocked_shots_against, clearances_for, clearances_against, corners_for, corners_against, final_third_entries_for, final_third_entries_against, fouls_for, fouls_against, goals_for, goals_against, interceptions_for, interceptions_against, npxg_for, npxg_against, offsides_for, offsides_against, possession_for, possession_against, red_cards_for, red_cards_against, saves_for, saves_against, shots_inside_box_for, shots_inside_box_against, shots_off_target_for, shots_off_target_against, shots_on_target_for, shots_on_target_against, shots_outside_box_for, shots_outside_box_against, tackles_for, tackles_against, throw_ins_for, throw_ins_against, total_shots_for, total_shots_against, touches_in_box_for, touches_in_box_against, xg_for, xg_against, yellow_cards_for, yellow_cards_against`

| match_alias | kickoff_unix | competition | venue | opponent_alias | own_formation_family | opponent_formation_family | accurate_crosses_for | accurate_crosses_against | big_chances_for | big_chances_against | blocked_shots_for | blocked_shots_against | clearances_for | clearances_against | corners_for | corners_against | final_third_entries_for | final_third_entries_against | fouls_for | fouls_against | goals_for | goals_against | interceptions_for | interceptions_against | npxg_for | npxg_against | offsides_for | offsides_against | possession_for | possession_against | red_cards_for | red_cards_against | saves_for | saves_against | shots_inside_box_for | shots_inside_box_against | shots_off_target_for | shots_off_target_against | shots_on_target_for | shots_on_target_against | shots_outside_box_for | shots_outside_box_against | tackles_for | tackles_against | throw_ins_for | throw_ins_against | total_shots_for | total_shots_against | touches_in_box_for | touches_in_box_against | xg_for | xg_against | yellow_cards_for | yellow_cards_against |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| m_mt_367710234 | 1695477600 | COMPETITION | AWAY | OPP_009 |  |  | 4.0 | 3.0 | 1.0 | 4.0 | 3.0 | 3.0 | 12.0 | 15.0 | 5.0 | 2.0 | 48.0 | 62.0 | 16.0 | 12.0 | 0.0 | 3.0 | 10.0 | 9.0 | 0.67 | 1.22 | 2.0 | 4.0 | 43.0 | 57.0 | 0.0 | 0.0 | 1.0 | 1.0 | 8.0 | 8.0 | 6.0 | 5.0 | 1.0 | 4.0 | 2.0 | 4.0 | 23.0 | 25.0 | 22.0 | 35.0 | 10.0 | 12.0 |  |  | 0.74 | 2.04 | 2.0 | 2.0 |
| m_mt_839904742 | 1696014000 | COMPETITION | HOME | OPP_020 |  |  | 5.0 | 3.0 | 0.0 | 2.0 | 0.0 | 2.0 | 10.0 | 14.0 | 2.0 | 5.0 | 46.0 | 43.0 | 14.0 | 5.0 | 0.0 | 3.0 | 5.0 | 1.0 | 0.52 | 0.78 | 2.0 | 2.0 | 32.0 | 68.0 | 0.0 | 0.0 | 3.0 | 2.0 | 5.0 | 4.0 | 6.0 | 4.0 | 2.0 | 6.0 | 3.0 | 8.0 | 18.0 | 16.0 | 20.0 | 23.0 | 8.0 | 12.0 |  |  | 0.52 | 1.57 | 2.0 | 0.0 |
| m_mt_624491016 | 1696359600 | COMPETITION | AWAY | OPP_010 |  |  | 2.0 | 11.0 | 1.0 | 5.0 | 0.0 | 5.0 | 28.0 | 15.0 | 4.0 | 10.0 | 43.0 | 76.0 | 12.0 | 2.0 | 0.0 | 1.0 | 16.0 | 4.0 | 0.19 | 1.28 | 3.0 | 1.0 | 28.0 | 72.0 | 0.0 | 0.0 | 2.0 | 2.0 | 1.0 | 11.0 | 2.0 | 9.0 | 2.0 | 3.0 | 3.0 | 6.0 | 16.0 | 11.0 | 12.0 | 26.0 | 4.0 | 17.0 |  |  | 0.19 | 1.28 | 1.0 | 0.0 |
| m_mt_978826384 | 1696687200 | COMPETITION | HOME | OPP_002 |  |  | 4.0 | 5.0 | 1.0 | 1.0 | 2.0 | 2.0 | 25.0 | 24.0 | 5.0 | 4.0 | 72.0 | 46.0 | 16.0 | 13.0 | 0.0 | 0.0 | 7.0 | 8.0 | 0.64 | 0.65 | 2.0 | 2.0 | 44.0 | 56.0 | 0.0 | 0.0 | 0.0 | 1.0 | 4.0 | 2.0 | 2.0 | 5.0 | 1.0 | 0.0 | 1.0 | 5.0 | 18.0 | 6.0 | 28.0 | 26.0 | 5.0 | 7.0 | 15.0 | 10.0 | 0.64 | 0.65 | 1.0 | 1.0 |
| m_mt_406685285 | 1697896800 | COMPETITION | AWAY | OPP_014 |  |  | 6.0 | 3.0 | 1.0 | 0.0 | 2.0 | 4.0 | 23.0 | 13.0 | 5.0 | 4.0 | 48.0 | 74.0 | 6.0 | 15.0 | 0.0 | 1.0 | 16.0 | 9.0 | 0.22 | 0.45 | 2.0 | 1.0 | 41.0 | 59.0 | 0.0 | 0.0 | 2.0 | 2.0 | 6.0 | 4.0 | 6.0 | 5.0 | 2.0 | 3.0 | 4.0 | 8.0 | 21.0 | 20.0 | 25.0 | 33.0 | 10.0 | 12.0 |  |  | 0.38 | 0.45 | 1.0 | 2.0 |
| m_mt_406685210 | 1698259500 | COMPETITION | AWAY | OPP_006 |  |  | 6.0 | 1.0 | 1.0 | 2.0 | 7.0 | 3.0 | 15.0 | 22.0 | 7.0 | 1.0 | 54.0 | 55.0 | 8.0 | 10.0 | 0.0 | 3.0 | 16.0 | 9.0 | 1.09 | 1.06 | 3.0 | 3.0 | 58.0 | 42.0 | 0.0 | 0.0 | 2.0 | 2.0 | 9.0 | 5.0 | 4.0 | 4.0 | 2.0 | 6.0 | 4.0 | 8.0 | 11.0 | 14.0 | 35.0 | 32.0 | 13.0 | 13.0 |  |  | 1.09 | 1.06 | 1.0 | 2.0 |
| m_mt_367710441 | 1698584400 | COMPETITION | HOME | OPP_008 |  |  | 7.0 | 2.0 | 3.0 | 0.0 | 2.0 | 2.0 | 23.0 | 14.0 | 4.0 | 3.0 | 70.0 | 82.0 | 9.0 | 16.0 | 2.0 | 0.0 | 9.0 | 6.0 | 2.64 | 0.32 | 0.0 | 1.0 | 58.0 | 42.0 | 0.0 | 0.0 | 0.0 | 3.0 | 9.0 | 4.0 | 7.0 | 4.0 | 5.0 | 0.0 | 5.0 | 2.0 | 15.0 | 14.0 | 25.0 | 41.0 | 14.0 | 6.0 | 25.0 | 27.0 | 2.6 | 0.42 | 2.0 | 3.0 |
| m_mt_978826396 | 1699110000 | COMPETITION | AWAY | OPP_005 |  |  | 6.0 | 1.0 | 2.0 | 2.0 | 1.0 | 6.0 | 20.0 | 18.0 | 7.0 | 8.0 | 39.0 | 77.0 | 14.0 | 10.0 | 0.0 | 1.0 | 8.0 | 7.0 | 1.29 | 1.63 | 0.0 | 5.0 | 35.0 | 65.0 | 1.0 | 0.0 | 5.0 | 2.0 | 5.0 | 6.0 | 3.0 | 4.0 | 2.0 | 7.0 | 1.0 | 11.0 | 14.0 | 17.0 | 14.0 | 19.0 | 6.0 | 17.0 |  |  | 1.29 | 1.6 | 1.0 | 3.0 |
| m_mt_250079295 | 1699714800 | COMPETITION | HOME | OPP_011 |  |  | 3.0 | 3.0 | 2.0 | 6.0 | 6.0 | 3.0 | 19.0 | 31.0 | 8.0 | 4.0 | 50.0 | 37.0 | 13.0 | 8.0 | 0.0 | 4.0 | 6.0 | 9.0 | 1.73 | 1.93 | 2.0 | 0.0 | 59.0 | 41.0 | 0.0 | 0.0 | 2.0 | 2.0 | 10.0 | 6.0 | 4.0 | 4.0 | 2.0 | 6.0 | 2.0 | 7.0 | 21.0 | 21.0 | 20.0 | 25.0 | 12.0 | 13.0 |  |  | 1.69 | 1.83 | 2.0 | 2.0 |
| m_mt_012238019 | 1700924400 | COMPETITION | AWAY | OPP_007 |  |  | 2.0 | 1.0 | 2.0 | 2.0 | 6.0 | 5.0 | 15.0 | 23.0 | 6.0 | 6.0 | 47.0 | 55.0 | 11.0 | 11.0 | 1.0 | 2.0 | 14.0 | 11.0 | 2.03 | 1.74 | 3.0 | 1.0 | 48.0 | 52.0 | 0.0 | 0.0 | 2.0 | 3.0 | 9.0 | 7.0 | 6.0 | 4.0 | 4.0 | 4.0 | 7.0 | 6.0 | 20.0 | 16.0 | 29.0 | 27.0 | 16.0 | 13.0 |  |  | 1.99 | 1.52 | 5.0 | 1.0 |
| m_mt_624491638 | 1701287100 | COMPETITION | HOME | OPP_017 |  |  | 3.0 | 4.0 | 4.0 | 2.0 | 3.0 | 3.0 | 15.0 | 20.0 | 5.0 | 4.0 | 41.0 | 57.0 | 10.0 | 7.0 | 1.0 | 1.0 | 12.0 | 4.0 | 1.02 | 1.13 | 2.0 | 3.0 | 32.0 | 68.0 | 0.0 | 0.0 | 2.0 | 5.0 | 10.0 | 6.0 | 5.0 | 6.0 | 7.0 | 3.0 | 5.0 | 6.0 | 25.0 | 15.0 | 15.0 | 32.0 | 15.0 | 12.0 |  |  | 1.49 | 1.13 | 2.0 | 1.0 |
| m_mt_367710316 | 1701529200 | COMPETITION | HOME | OPP_001 |  |  | 4.0 | 5.0 | 2.0 | 3.0 | 2.0 | 7.0 | 22.0 | 16.0 | 3.0 | 7.0 | 48.0 | 64.0 | 12.0 | 6.0 | 3.0 | 1.0 | 10.0 | 13.0 | 1.01 | 1.49 | 0.0 | 1.0 | 37.0 | 63.0 | 0.0 | 0.0 | 4.0 | 5.0 | 8.0 | 13.0 | 3.0 | 6.0 | 8.0 | 5.0 | 5.0 | 5.0 | 19.0 | 12.0 | 17.0 | 31.0 | 13.0 | 18.0 |  |  | 1.01 | 1.49 | 2.0 | 1.0 |
| m_mt_195565664 | 1702134000 | COMPETITION | AWAY | OPP_019 |  |  | 5.0 | 3.0 | 1.0 | 3.0 | 0.0 | 5.0 | 27.0 | 20.0 | 5.0 | 4.0 | 54.0 | 70.0 | 11.0 | 7.0 | 1.0 | 0.0 | 13.0 | 18.0 | 0.81 | 1.05 | 1.0 | 5.0 | 51.0 | 49.0 | 0.0 | 0.0 | 4.0 | 1.0 | 5.0 | 8.0 | 4.0 | 4.0 | 2.0 | 4.0 | 1.0 | 5.0 | 17.0 | 9.0 | 33.0 | 30.0 | 6.0 | 13.0 |  |  | 0.81 | 1.84 | 4.0 | 3.0 |
| m_mt_012232321 | 1702496700 | COMPETITION | AWAY | OPP_015 |  |  | 10.0 | 9.0 | 3.0 | 5.0 | 8.0 | 3.0 | 14.0 | 36.0 | 7.0 | 3.0 | 65.0 | 53.0 | 10.0 | 6.0 | 1.0 | 3.0 | 7.0 | 5.0 | 1.4 | 1.6 | 0.0 | 1.0 | 52.0 | 48.0 | 0.0 | 0.0 | 2.0 | 3.0 | 15.0 | 10.0 | 8.0 | 4.0 | 4.0 | 5.0 | 5.0 | 2.0 | 13.0 | 17.0 | 29.0 | 20.0 | 20.0 | 12.0 |  |  | 1.51 | 1.6 | 1.0 | 1.0 |
| m_mt_581141486 | 1702738800 | COMPETITION | HOME | OPP_018 |  |  | 4.0 | 2.0 | 1.0 | 0.0 | 2.0 | 1.0 | 7.0 | 23.0 | 8.0 | 3.0 | 57.0 | 48.0 | 12.0 | 13.0 | 2.0 | 1.0 | 5.0 | 4.0 | 1.34 | 0.35 | 1.0 | 3.0 | 49.0 | 51.0 | 0.0 | 0.0 | 2.0 | 1.0 | 5.0 | 5.0 | 3.0 | 2.0 | 3.0 | 2.0 | 3.0 | 0.0 | 15.0 | 22.0 | 24.0 | 20.0 | 8.0 | 5.0 |  |  | 1.25 | 0.42 | 5.0 | 4.0 |
| m_mt_978828203 | 1703343600 | COMPETITION | HOME | OPP_021 |  |  | 4.0 | 0.0 | 0.0 | 1.0 | 6.0 | 2.0 | 14.0 | 39.0 | 10.0 | 3.0 | 58.0 | 57.0 | 10.0 | 12.0 | 1.0 | 2.0 | 18.0 | 14.0 | 0.84 | 0.67 | 3.0 | 2.0 | 58.0 | 42.0 | 0.0 | 0.0 | 2.0 | 4.0 | 8.0 | 5.0 | 7.0 | 2.0 | 5.0 | 3.0 | 10.0 | 2.0 | 12.0 | 15.0 | 30.0 | 17.0 | 18.0 | 7.0 | 27.0 | 9.0 | 0.84 | 0.66 | 3.0 | 2.0 |
| m_mt_624494981 | 1703602800 | COMPETITION | AWAY | OPP_012 |  |  | 8.0 | 3.0 | 3.0 | 0.0 | 3.0 | 3.0 | 19.0 | 28.0 | 9.0 | 5.0 | 48.0 | 65.0 | 12.0 | 7.0 | 0.0 | 2.0 | 15.0 | 4.0 | 1.58 | 0.5 | 0.0 | 1.0 | 43.0 | 57.0 | 1.0 | 1.0 | 0.0 | 2.0 | 7.0 | 4.0 | 6.0 | 4.0 | 2.0 | 2.0 | 4.0 | 5.0 | 24.0 | 27.0 | 36.0 | 34.0 | 11.0 | 9.0 |  |  | 1.58 | 0.5 | 1.0 | 1.0 |
| m_mt_195565085 | 1703879100 | COMPETITION | AWAY | OPP_004 |  |  | 2.0 | 4.0 | 1.0 | 1.0 | 0.0 | 1.0 | 36.0 | 5.0 | 0.0 | 3.0 | 55.0 | 91.0 | 11.0 | 10.0 | 1.0 | 0.0 | 5.0 | 7.0 | 0.51 | 0.53 | 0.0 | 2.0 | 31.0 | 69.0 | 1.0 | 0.0 | 2.0 | 2.0 | 3.0 | 4.0 | 3.0 | 6.0 | 3.0 | 2.0 | 3.0 | 5.0 | 24.0 | 20.0 | 21.0 | 38.0 | 6.0 | 9.0 |  |  | 0.51 | 0.53 | 2.0 | 4.0 |
| m_mt_406686781 | 1704129300 | COMPETITION | HOME | OPP_003 |  |  | 6.0 | 3.0 | 0.0 | 1.0 | 10.0 | 3.0 | 6.0 | 27.0 | 10.0 | 4.0 | 47.0 | 33.0 | 13.0 | 13.0 | 3.0 | 1.0 | 4.0 | 4.0 | 1.23 | 0.15 | 0.0 | 1.0 | 63.0 | 37.0 | 0.0 | 1.0 | 0.0 | 3.0 | 15.0 | 3.0 | 7.0 | 1.0 | 6.0 | 1.0 | 8.0 | 2.0 | 17.0 | 17.0 | 16.0 | 18.0 | 23.0 | 5.0 |  |  | 1.23 | 0.94 | 3.0 | 4.0 |
| m_mt_250070669 | 1705158000 | COMPETITION | AWAY | OPP_022 |  |  | 1.0 | 5.0 | 1.0 | 4.0 | 0.0 | 3.0 | 36.0 | 8.0 | 3.0 | 14.0 | 16.0 | 75.0 | 12.0 | 9.0 | 0.0 | 4.0 | 11.0 | 11.0 | 0.6 | 1.86 | 3.0 | 4.0 | 30.0 | 70.0 | 0.0 | 0.0 | 1.0 | 4.0 | 4.0 | 11.0 | 2.0 | 5.0 | 4.0 | 7.0 | 2.0 | 4.0 | 16.0 | 10.0 | 6.0 | 23.0 | 6.0 | 15.0 |  |  | 0.6 | 2.42 | 3.0 | 3.0 |
| m_mt_581141218 | 1705762800 | COMPETITION | HOME | OPP_012 |  |  | 2.0 | 4.0 | 2.0 | 1.0 | 2.0 | 7.0 | 15.0 | 31.0 | 6.0 | 7.0 | 41.0 | 51.0 | 14.0 | 11.0 | 1.0 | 2.0 | 11.0 | 11.0 | 1.69 | 1.14 | 5.0 | 0.0 | 46.0 | 54.0 | 0.0 | 0.0 | 4.0 | 4.0 | 8.0 | 9.0 | 4.0 | 3.0 | 5.0 | 6.0 | 3.0 | 7.0 | 14.0 | 15.0 | 28.0 | 22.0 | 11.0 | 16.0 |  |  | 1.56 | 1.13 | 4.0 | 5.0 |
| m_mt_749907509 | 1706730300 | COMPETITION | HOME | OPP_014 |  |  | 4.0 | 4.0 | 1.0 | 2.0 | 8.0 | 3.0 | 15.0 | 17.0 | 5.0 | 4.0 | 50.0 | 50.0 | 8.0 | 13.0 | 0.0 | 0.0 | 3.0 | 10.0 | 1.45 | 0.83 | 1.0 | 2.0 | 60.0 | 40.0 | 0.0 | 0.0 | 2.0 | 5.0 | 10.0 | 5.0 | 6.0 | 5.0 | 5.0 | 2.0 | 9.0 | 5.0 | 11.0 | 29.0 | 23.0 | 23.0 | 19.0 | 10.0 |  |  | 1.43 | 0.86 | 4.0 | 3.0 |
| m_mt_012232488 | 1706972400 | COMPETITION | AWAY | OPP_002 |  |  | 2.0 | 7.0 | 0.0 | 6.0 | 4.0 | 5.0 | 29.0 | 21.0 | 8.0 | 7.0 | 39.0 | 67.0 | 18.0 | 10.0 | 0.0 | 4.0 | 3.0 | 10.0 | 0.49 | 1.89 | 1.0 | 4.0 | 62.0 | 38.0 | 0.0 | 0.0 | 1.0 | 2.0 | 5.0 | 7.0 | 5.0 | 1.0 | 3.0 | 6.0 | 7.0 | 5.0 | 17.0 | 20.0 | 15.0 | 27.0 | 12.0 | 12.0 |  |  | 0.49 | 1.89 | 1.0 | 3.0 |
| m_mt_743353363 | 1707508800 | COMPETITION | HOME | OPP_007 |  |  | 3.0 | 5.0 | 2.0 | 2.0 | 2.0 | 9.0 | 25.0 | 2.0 | 1.0 | 7.0 | 49.0 | 65.0 | 14.0 | 10.0 | 2.0 | 0.0 | 10.0 | 9.0 | 1.52 | 1.78 | 0.0 | 3.0 | 37.0 | 63.0 | 0.0 | 0.0 | 5.0 | 1.0 | 10.0 | 14.0 | 8.0 | 12.0 | 3.0 | 4.0 | 3.0 | 11.0 | 32.0 | 24.0 | 20.0 | 21.0 | 13.0 | 25.0 |  |  | 1.5 | 1.78 | 3.0 | 1.0 |
| m_mt_406686649 | 1707853500 | COMPETITION | AWAY | OPP_017 | BACK_FOUR | BACK_FOUR | 5.0 | 2.0 | 0.0 | 3.0 | 4.0 | 2.0 | 11.0 | 23.0 | 7.0 | 4.0 | 43.0 | 62.0 | 12.0 | 15.0 | 0.0 | 2.0 | 8.0 | 9.0 | 0.5 | 1.86 | 2.0 | 5.0 | 33.0 | 67.0 | 0.0 | 0.0 | 1.0 | 4.0 | 8.0 | 7.0 | 5.0 | 5.0 | 4.0 | 3.0 | 5.0 | 3.0 | 10.0 | 20.0 | 17.0 | 17.0 | 13.0 | 10.0 |  |  | 0.5 | 1.85 | 2.0 | 1.0 |
| m_mt_839956268 | 1708182000 | COMPETITION | AWAY | OPP_011 |  |  | 2.0 | 4.0 | 2.0 | 0.0 | 2.0 | 5.0 | 24.0 | 14.0 | 3.0 | 5.0 | 63.0 | 61.0 | 15.0 | 14.0 | 2.0 | 0.0 | 14.0 | 10.0 | 1.15 | 0.36 | 0.0 | 4.0 | 42.0 | 58.0 | 1.0 | 0.0 | 2.0 | 0.0 | 3.0 | 5.0 | 1.0 | 1.0 | 2.0 | 2.0 | 2.0 | 3.0 | 19.0 | 17.0 | 24.0 | 40.0 | 5.0 | 8.0 |  |  | 1.15 | 0.36 | 3.0 | 3.0 |
| m_mt_743390129 | 1708786800 | COMPETITION | HOME | OPP_005 |  |  | 5.0 | 6.0 | 1.0 | 0.0 | 1.0 | 7.0 | 23.0 | 13.0 | 4.0 | 5.0 | 52.0 | 87.0 | 8.0 | 7.0 | 2.0 | 1.0 | 8.0 | 3.0 | 1.17 | 0.44 | 0.0 | 2.0 | 48.0 | 52.0 | 1.0 | 0.0 | 1.0 | 5.0 | 8.0 | 7.0 | 7.0 | 3.0 | 7.0 | 2.0 | 7.0 | 5.0 | 6.0 | 18.0 | 25.0 | 18.0 | 15.0 | 12.0 |  |  | 1.16 | 0.59 | 3.0 | 3.0 |
| m_mt_012243034 | 1709391600 | COMPETITION | AWAY | OPP_008 |  |  | 6.0 | 2.0 | 4.0 | 1.0 | 5.0 | 3.0 | 15.0 | 33.0 | 10.0 | 2.0 | 58.0 | 54.0 | 14.0 | 16.0 | 1.0 | 0.0 | 9.0 | 11.0 | 1.64 | 0.32 | 2.0 | 3.0 | 49.0 | 51.0 | 0.0 | 0.0 | 0.0 | 3.0 | 13.0 | 4.0 | 8.0 | 3.0 | 4.0 | 1.0 | 4.0 | 3.0 | 8.0 | 21.0 | 34.0 | 24.0 | 17.0 | 7.0 |  |  | 1.64 | 0.31 | 2.0 | 1.0 |
| m_mt_839950896 | 1709667900 | COMPETITION | HOME | OPP_006 |  |  | 4.0 | 2.0 | 2.0 | 0.0 | 8.0 | 7.0 | 19.0 | 34.0 | 8.0 | 2.0 | 41.0 | 53.0 | 12.0 | 13.0 | 1.0 | 0.0 | 10.0 | 8.0 | 1.73 | 0.57 | 3.0 | 0.0 | 54.0 | 46.0 | 0.0 | 0.0 | 3.0 | 2.0 | 12.0 | 9.0 | 7.0 | 3.0 | 3.0 | 3.0 | 6.0 | 4.0 | 18.0 | 22.0 | 29.0 | 27.0 | 18.0 | 13.0 |  |  | 1.7 | 0.57 | 1.0 | 2.0 |
| m_mt_406678400 | 1709928000 | COMPETITION | HOME | OPP_016 |  |  | 1.0 | 3.0 | 2.0 | 4.0 | 3.0 | 4.0 | 16.0 | 27.0 | 8.0 | 5.0 | 41.0 | 60.0 | 16.0 | 9.0 | 0.0 | 2.0 | 8.0 | 4.0 | 0.84 | 2.03 | 0.0 | 2.0 | 40.0 | 60.0 | 0.0 | 0.0 | 4.0 | 2.0 | 5.0 | 10.0 | 3.0 | 2.0 | 3.0 | 7.0 | 4.0 | 3.0 | 21.0 | 28.0 | 23.0 | 24.0 | 9.0 | 13.0 |  |  | 0.84 | 2.02 | 1.0 | 1.0 |

### Arm B — derived summaries (DERIVED_SUMMARY), HOME 232 + AWAY 234

HOME_TEAM (metric·side·window·venue = value [n, reliability]):

- accurate_crosses·FOR·ALL_PRIOR·ALL = 4.8667 [n=30, HIGH]
- accurate_crosses·FOR·W5·ALL = 4.8 [n=5, LOW]
- accurate_crosses·FOR·W10·ALL = 4.7 [n=10, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·HOME = 4.9333 [n=15, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·AWAY = 4.8 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·ALL = 3.2333 [n=30, HIGH]
- accurate_crosses·AGAINST·W5·ALL = 3.8 [n=5, LOW]
- accurate_crosses·AGAINST·W10·ALL = 3.8 [n=10, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·HOME = 2.8 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·AWAY = 3.6667 [n=15, MEDIUM]
- big_chances·FOR·ALL_PRIOR·ALL = 2.5357 [n=28, HIGH]
- big_chances·FOR·W5·ALL = 4.2 [n=5, LOW]
- big_chances·FOR·W10·ALL = 3.5 [n=10, MEDIUM]
- big_chances·FOR·ALL_PRIOR·HOME = 3.4286 [n=14, MEDIUM]
- big_chances·FOR·ALL_PRIOR·AWAY = 1.6429 [n=14, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·ALL = 1.6071 [n=28, HIGH]
- big_chances·AGAINST·W5·ALL = 2.0 [n=5, LOW]
- big_chances·AGAINST·W10·ALL = 1.4 [n=10, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·HOME = 1.5 [n=14, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·AWAY = 1.7143 [n=14, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·ALL = 4.5667 [n=30, HIGH]
- blocked_shots·FOR·W5·ALL = 3.4 [n=5, LOW]
- blocked_shots·FOR·W10·ALL = 4.0 [n=10, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·HOME = 5.1333 [n=15, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·AWAY = 4.0 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·ALL = 3.0667 [n=30, HIGH]
- blocked_shots·AGAINST·W5·ALL = 3.6 [n=5, LOW]
- blocked_shots·AGAINST·W10·ALL = 3.6 [n=10, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·HOME = 2.6 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·AWAY = 3.5333 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·ALL = 16.3667 [n=30, HIGH]
- clearances·FOR·W5·ALL = 15.6 [n=5, LOW]
- clearances·FOR·W10·ALL = 18.9 [n=10, MEDIUM]
- clearances·FOR·ALL_PRIOR·HOME = 13.4 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·AWAY = 19.3333 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·ALL = 19.4667 [n=30, HIGH]
- clearances·AGAINST·W5·ALL = 14.8 [n=5, LOW]
- clearances·AGAINST·W10·ALL = 21.0 [n=10, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·HOME = 19.4 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·AWAY = 19.5333 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·ALL = 5.4333 [n=30, HIGH]
- corners·FOR·W5·ALL = 4.4 [n=5, LOW]
- corners·FOR·W10·ALL = 5.3 [n=10, MEDIUM]
- corners·FOR·ALL_PRIOR·HOME = 6.1333 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·AWAY = 4.7333 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·ALL = 4.9667 [n=30, HIGH]
- corners·AGAINST·W5·ALL = 5.0 [n=5, LOW]
- corners·AGAINST·W10·ALL = 6.0 [n=10, MEDIUM]
- corners·AGAINST·ALL_PRIOR·HOME = 3.8 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·AWAY = 6.1333 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·ALL = 59.5 [n=30, HIGH]
- final_third_entries·FOR·W5·ALL = 61.0 [n=5, LOW]
- final_third_entries·FOR·W10·ALL = 63.1 [n=10, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·HOME = 60.2 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·AWAY = 58.8 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·ALL = 53.2667 [n=30, HIGH]
- final_third_entries·AGAINST·W5·ALL = 54.8 [n=5, LOW]
- final_third_entries·AGAINST·W10·ALL = 54.7 [n=10, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·HOME = 51.2 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·AWAY = 55.3333 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·ALL = 12.4333 [n=30, HIGH]
- fouls·FOR·W5·ALL = 12.6 [n=5, LOW]
- fouls·FOR·W10·ALL = 12.0 [n=10, MEDIUM]
- fouls·FOR·ALL_PRIOR·HOME = 12.0 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·AWAY = 12.8667 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·ALL = 9.8667 [n=30, HIGH]
- fouls·AGAINST·W5·ALL = 12.2 [n=5, LOW]
- fouls·AGAINST·W10·ALL = 10.0 [n=10, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·HOME = 10.2 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·AWAY = 9.5333 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·ALL = 2.0333 [n=30, HIGH]
- goals·FOR·W5·ALL = 2.6 [n=5, LOW]
- goals·FOR·W10·ALL = 2.4 [n=10, MEDIUM]
- goals·FOR·ALL_PRIOR·HOME = 2.6 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·AWAY = 1.4667 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·ALL = 1.4 [n=30, HIGH]
- goals·AGAINST·W5·ALL = 1.6 [n=5, LOW]
- goals·AGAINST·W10·ALL = 1.5 [n=10, MEDIUM]
- goals·AGAINST·ALL_PRIOR·HOME = 1.5333 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·AWAY = 1.2667 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·ALL = 8.7 [n=30, HIGH]
- interceptions·FOR·W5·ALL = 9.6 [n=5, LOW]
- interceptions·FOR·W10·ALL = 8.6 [n=10, MEDIUM]
- interceptions·FOR·ALL_PRIOR·HOME = 9.2667 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·AWAY = 8.1333 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·ALL = 11.6667 [n=30, HIGH]
- interceptions·AGAINST·W5·ALL = 12.4 [n=5, LOW]
- interceptions·AGAINST·W10·ALL = 11.5 [n=10, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·HOME = 11.1333 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·AWAY = 12.2 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·ALL = 1.5717 [n=30, HIGH]
- npxg·FOR·W5·ALL = 1.66 [n=5, LOW]
- npxg·FOR·W10·ALL = 1.687 [n=10, MEDIUM]
- npxg·FOR·ALL_PRIOR·HOME = 1.96 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·AWAY = 1.1833 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·ALL = 0.939 [n=30, HIGH]
- npxg·AGAINST·W5·ALL = 1.072 [n=5, LOW]
- npxg·AGAINST·W10·ALL = 1.014 [n=10, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·HOME = 0.7673 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·AWAY = 1.1107 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·ALL = 1.9333 [n=30, HIGH]
- offsides·FOR·W5·ALL = 2.6 [n=5, LOW]
- offsides·FOR·W10·ALL = 1.7 [n=10, MEDIUM]
- offsides·FOR·ALL_PRIOR·HOME = 2.0667 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·AWAY = 1.8 [n=15, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·ALL = 1.6 [n=30, HIGH]
- offsides·AGAINST·W5·ALL = 1.4 [n=5, LOW]
- offsides·AGAINST·W10·ALL = 1.4 [n=10, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·HOME = 1.4667 [n=15, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·AWAY = 1.7333 [n=15, MEDIUM]
- possession·FOR·ALL_PRIOR·ALL = 54.6667 [n=30, HIGH]
- possession·FOR·W5·ALL = 56.4 [n=5, LOW]
- possession·FOR·W10·ALL = 56.4 [n=10, MEDIUM]
- possession·FOR·ALL_PRIOR·HOME = 53.0 [n=15, MEDIUM]
- possession·FOR·ALL_PRIOR·AWAY = 56.3333 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·ALL = 45.3333 [n=30, HIGH]
- possession·AGAINST·W5·ALL = 43.6 [n=5, LOW]
- possession·AGAINST·W10·ALL = 43.6 [n=10, MEDIUM]
- possession·AGAINST·ALL_PRIOR·HOME = 47.0 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·AWAY = 43.6667 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·ALL = 0.0 [n=30, HIGH]
- red_cards·FOR·W5·ALL = 0.0 [n=5, LOW]
- red_cards·FOR·W10·ALL = 0.0 [n=10, MEDIUM]
- red_cards·FOR·ALL_PRIOR·HOME = 0.0 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·AWAY = 0.0 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·ALL = 0.0667 [n=30, HIGH]
- red_cards·AGAINST·W5·ALL = 0.0 [n=5, LOW]
- red_cards·AGAINST·W10·ALL = 0.0 [n=10, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·HOME = 0.0667 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·AWAY = 0.0667 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·ALL = 2.3667 [n=30, HIGH]
- saves·FOR·W5·ALL = 2.2 [n=5, LOW]
- saves·FOR·W10·ALL = 2.4 [n=10, MEDIUM]
- saves·FOR·ALL_PRIOR·HOME = 2.0667 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·AWAY = 2.6667 [n=15, MEDIUM]
- saves·AGAINST·ALL_PRIOR·ALL = 3.4667 [n=30, HIGH]
- saves·AGAINST·W5·ALL = 4.2 [n=5, LOW]
- saves·AGAINST·W10·ALL = 4.0 [n=10, MEDIUM]
- saves·AGAINST·ALL_PRIOR·HOME = 3.9333 [n=15, MEDIUM]
- saves·AGAINST·ALL_PRIOR·AWAY = 3.0 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·ALL = 10.6 [n=30, HIGH]
- shots_inside_box·FOR·W5·ALL = 11.4 [n=5, LOW]
- shots_inside_box·FOR·W10·ALL = 11.3 [n=10, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·HOME = 12.7333 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·AWAY = 8.4667 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·ALL = 6.4 [n=30, HIGH]
- shots_inside_box·AGAINST·W5·ALL = 7.6 [n=5, LOW]
- shots_inside_box·AGAINST·W10·ALL = 7.7 [n=10, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·HOME = 5.8667 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·AWAY = 6.9333 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·ALL = 5.0667 [n=30, HIGH]
- shots_off_target·FOR·W5·ALL = 4.4 [n=5, LOW]
- shots_off_target·FOR·W10·ALL = 5.0 [n=10, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·HOME = 5.6667 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·AWAY = 4.4667 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·ALL = 3.6667 [n=30, HIGH]
- shots_off_target·AGAINST·W5·ALL = 4.0 [n=5, LOW]
- shots_off_target·AGAINST·W10·ALL = 4.2 [n=10, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·HOME = 3.4667 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·AWAY = 3.8667 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·ALL = 5.4667 [n=30, HIGH]
- shots_on_target·FOR·W5·ALL = 6.8 [n=5, LOW]
- shots_on_target·FOR·W10·ALL = 6.3 [n=10, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·HOME = 6.6 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·AWAY = 4.3333 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·ALL = 3.6333 [n=30, HIGH]
- shots_on_target·AGAINST·W5·ALL = 4.2 [n=5, LOW]
- shots_on_target·AGAINST·W10·ALL = 4.0 [n=10, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·HOME = 3.4667 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·AWAY = 3.8 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·ALL = 4.5 [n=30, HIGH]
- shots_outside_box·FOR·W5·ALL = 3.2 [n=5, LOW]
- shots_outside_box·FOR·W10·ALL = 4.0 [n=10, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·HOME = 4.6667 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·AWAY = 4.3333 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·ALL = 3.9667 [n=30, HIGH]
- shots_outside_box·AGAINST·W5·ALL = 4.2 [n=5, LOW]
- shots_outside_box·AGAINST·W10·ALL = 4.1 [n=10, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·HOME = 3.6667 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·AWAY = 4.2667 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·ALL = 15.0 [n=30, HIGH]
- tackles·FOR·W5·ALL = 16.6 [n=5, LOW]
- tackles·FOR·W10·ALL = 14.6 [n=10, MEDIUM]
- tackles·FOR·ALL_PRIOR·HOME = 15.4667 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·AWAY = 14.5333 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·ALL = 15.6333 [n=30, HIGH]
- tackles·AGAINST·W5·ALL = 16.0 [n=5, LOW]
- tackles·AGAINST·W10·ALL = 16.9 [n=10, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·HOME = 15.4667 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·AWAY = 15.8 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·ALL = 22.6333 [n=30, HIGH]
- throw_ins·FOR·W5·ALL = 27.0 [n=5, LOW]
- throw_ins·FOR·W10·ALL = 24.4 [n=10, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·HOME = 21.6667 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·AWAY = 23.6 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·ALL = 21.9667 [n=30, HIGH]
- throw_ins·AGAINST·W5·ALL = 25.0 [n=5, LOW]
- throw_ins·AGAINST·W10·ALL = 22.8 [n=10, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·HOME = 21.8 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·AWAY = 22.1333 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·ALL = 15.1 [n=30, HIGH]
- total_shots·FOR·W5·ALL = 14.6 [n=5, LOW]
- total_shots·FOR·W10·ALL = 15.3 [n=10, MEDIUM]
- total_shots·FOR·ALL_PRIOR·HOME = 17.4 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·AWAY = 12.8 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·ALL = 10.3667 [n=30, HIGH]
- total_shots·AGAINST·W5·ALL = 11.8 [n=5, LOW]
- total_shots·AGAINST·W10·ALL = 11.8 [n=10, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·HOME = 9.5333 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·AWAY = 11.2 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·ALL = 24.5 [n=2, LOW]
- touches_in_box·AGAINST·ALL_PRIOR·ALL = 22.5 [n=2, LOW]
- xg·FOR·ALL_PRIOR·ALL = 1.608 [n=30, HIGH]
- xg·FOR·W5·ALL = 1.728 [n=5, LOW]
- xg·FOR·W10·ALL = 1.729 [n=10, MEDIUM]
- xg·FOR·ALL_PRIOR·HOME = 2.0367 [n=15, MEDIUM]
- xg·FOR·ALL_PRIOR·AWAY = 1.1793 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·ALL = 1.0127 [n=30, HIGH]
- xg·AGAINST·W5·ALL = 1.222 [n=5, LOW]
- xg·AGAINST·W10·ALL = 1.089 [n=10, MEDIUM]
- xg·AGAINST·ALL_PRIOR·HOME = 0.8727 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·AWAY = 1.1527 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·ALL = 2.2857 [n=28, HIGH]
- yellow_cards·FOR·W5·ALL = 1.8 [n=5, LOW]
- yellow_cards·FOR·W10·ALL = 1.7778 [n=9, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·HOME = 2.2143 [n=14, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·AWAY = 2.3571 [n=14, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·ALL = 1.8571 [n=28, HIGH]
- yellow_cards·AGAINST·W5·ALL = 1.4 [n=5, LOW]
- yellow_cards·AGAINST·W10·ALL = 1.6667 [n=9, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·HOME = 2.2143 [n=14, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·AWAY = 1.5 [n=14, MEDIUM]

AWAY_TEAM:

- accurate_crosses·FOR·ALL_PRIOR·ALL = 4.2 [n=30, HIGH]
- accurate_crosses·FOR·W5·ALL = 3.6 [n=5, LOW]
- accurate_crosses·FOR·W10·ALL = 3.4 [n=10, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·HOME = 3.9333 [n=15, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·AWAY = 4.4667 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·ALL = 3.6667 [n=30, HIGH]
- accurate_crosses·AGAINST·W5·ALL = 3.4 [n=5, LOW]
- accurate_crosses·AGAINST·W10·ALL = 3.9 [n=10, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·HOME = 3.4 [n=15, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·AWAY = 3.9333 [n=15, MEDIUM]
- big_chances·FOR·ALL_PRIOR·ALL = 1.5333 [n=30, HIGH]
- big_chances·FOR·W5·ALL = 2.2 [n=5, LOW]
- big_chances·FOR·W10·ALL = 1.6 [n=10, MEDIUM]
- big_chances·FOR·ALL_PRIOR·HOME = 1.5333 [n=15, MEDIUM]
- big_chances·FOR·ALL_PRIOR·AWAY = 1.5333 [n=15, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·ALL = 2.1 [n=30, HIGH]
- big_chances·AGAINST·W5·ALL = 1.0 [n=5, LOW]
- big_chances·AGAINST·W10·ALL = 1.9 [n=10, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·HOME = 1.6667 [n=15, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·AWAY = 2.5333 [n=15, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·ALL = 3.4 [n=30, HIGH]
- blocked_shots·FOR·W5·ALL = 3.8 [n=5, LOW]
- blocked_shots·FOR·W10·ALL = 3.9 [n=10, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·HOME = 3.8 [n=15, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·AWAY = 3.0 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·ALL = 3.9333 [n=30, HIGH]
- blocked_shots·AGAINST·W5·ALL = 5.2 [n=5, LOW]
- blocked_shots·AGAINST·W10·ALL = 5.2 [n=10, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·HOME = 4.1333 [n=15, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·AWAY = 3.7333 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·ALL = 19.2667 [n=30, HIGH]
- clearances·FOR·W5·ALL = 19.4 [n=5, LOW]
- clearances·FOR·W10·ALL = 19.2 [n=10, MEDIUM]
- clearances·FOR·ALL_PRIOR·HOME = 16.9333 [n=15, MEDIUM]
- clearances·FOR·ALL_PRIOR·AWAY = 21.6 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·ALL = 20.8667 [n=30, HIGH]
- clearances·AGAINST·W5·ALL = 24.2 [n=5, LOW]
- clearances·AGAINST·W10·ALL = 21.5 [n=10, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·HOME = 22.1333 [n=15, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·AWAY = 19.6 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·ALL = 5.7667 [n=30, HIGH]
- corners·FOR·W5·ALL = 6.6 [n=5, LOW]
- corners·FOR·W10·ALL = 6.0 [n=10, MEDIUM]
- corners·FOR·ALL_PRIOR·HOME = 5.8 [n=15, MEDIUM]
- corners·FOR·ALL_PRIOR·AWAY = 5.7333 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·ALL = 4.8333 [n=30, HIGH]
- corners·AGAINST·W5·ALL = 3.8 [n=5, LOW]
- corners·AGAINST·W10·ALL = 4.8 [n=10, MEDIUM]
- corners·AGAINST·ALL_PRIOR·HOME = 4.4667 [n=15, MEDIUM]
- corners·AGAINST·ALL_PRIOR·AWAY = 5.2 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·ALL = 49.4333 [n=30, HIGH]
- final_third_entries·FOR·W5·ALL = 51.0 [n=5, LOW]
- final_third_entries·FOR·W10·ALL = 47.7 [n=10, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·HOME = 50.8667 [n=15, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·AWAY = 48.0 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·ALL = 61.0 [n=30, HIGH]
- final_third_entries·AGAINST·W5·ALL = 63.0 [n=5, LOW]
- final_third_entries·AGAINST·W10·ALL = 61.0 [n=10, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·HOME = 55.5333 [n=15, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·AWAY = 66.4667 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·ALL = 12.1 [n=30, HIGH]
- fouls·FOR·W5·ALL = 13.0 [n=5, LOW]
- fouls·FOR·W10·ALL = 13.1 [n=10, MEDIUM]
- fouls·FOR·ALL_PRIOR·HOME = 12.0667 [n=15, MEDIUM]
- fouls·FOR·ALL_PRIOR·AWAY = 12.1333 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·ALL = 10.3333 [n=30, HIGH]
- fouls·AGAINST·W5·ALL = 11.8 [n=5, LOW]
- fouls·AGAINST·W10·ALL = 11.8 [n=10, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·HOME = 10.4 [n=15, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·AWAY = 10.2667 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·ALL = 0.8333 [n=30, HIGH]
- goals·FOR·W5·ALL = 1.2 [n=5, LOW]
- goals·FOR·W10·ALL = 0.9 [n=10, MEDIUM]
- goals·FOR·ALL_PRIOR·HOME = 1.2 [n=15, MEDIUM]
- goals·FOR·ALL_PRIOR·AWAY = 0.4667 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·ALL = 1.4667 [n=30, HIGH]
- goals·AGAINST·W5·ALL = 0.6 [n=5, LOW]
- goals·AGAINST·W10·ALL = 1.1 [n=10, MEDIUM]
- goals·AGAINST·ALL_PRIOR·HOME = 1.2 [n=15, MEDIUM]
- goals·AGAINST·ALL_PRIOR·AWAY = 1.7333 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·ALL = 9.7 [n=30, HIGH]
- interceptions·FOR·W5·ALL = 9.8 [n=5, LOW]
- interceptions·FOR·W10·ALL = 8.4 [n=10, MEDIUM]
- interceptions·FOR·ALL_PRIOR·HOME = 8.4 [n=15, MEDIUM]
- interceptions·FOR·ALL_PRIOR·AWAY = 11.0 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·ALL = 8.0667 [n=30, HIGH]
- interceptions·AGAINST·W5·ALL = 7.2 [n=5, LOW]
- interceptions·AGAINST·W10·ALL = 8.5 [n=10, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·HOME = 7.2 [n=15, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·AWAY = 8.9333 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·ALL = 1.118 [n=30, HIGH]
- npxg·FOR·W5·ALL = 1.306 [n=5, LOW]
- npxg·FOR·W10·ALL = 1.218 [n=10, MEDIUM]
- npxg·FOR·ALL_PRIOR·HOME = 1.2913 [n=15, MEDIUM]
- npxg·FOR·ALL_PRIOR·AWAY = 0.9447 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·ALL = 1.0537 [n=30, HIGH]
- npxg·AGAINST·W5·ALL = 0.744 [n=5, LOW]
- npxg·AGAINST·W10·ALL = 1.122 [n=10, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·HOME = 0.9507 [n=15, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·AWAY = 1.1567 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·ALL = 1.4333 [n=30, HIGH]
- offsides·FOR·W5·ALL = 1.0 [n=5, LOW]
- offsides·FOR·W10·ALL = 1.4 [n=10, MEDIUM]
- offsides·FOR·ALL_PRIOR·HOME = 1.4 [n=15, MEDIUM]
- offsides·FOR·ALL_PRIOR·AWAY = 1.4667 [n=15, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·ALL = 2.2667 [n=30, HIGH]
- offsides·AGAINST·W5·ALL = 2.2 [n=5, LOW]
- offsides·AGAINST·W10·ALL = 2.5 [n=10, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·HOME = 1.6 [n=15, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·AWAY = 2.9333 [n=15, MEDIUM]
- possession·FOR·ALL_PRIOR·ALL = 45.4333 [n=30, HIGH]
- possession·FOR·W5·ALL = 46.6 [n=5, LOW]
- possession·FOR·W10·ALL = 47.1 [n=10, MEDIUM]
- possession·FOR·ALL_PRIOR·HOME = 47.8 [n=15, MEDIUM]
- possession·FOR·ALL_PRIOR·AWAY = 43.0667 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·ALL = 54.5667 [n=30, HIGH]
- possession·AGAINST·W5·ALL = 53.4 [n=5, LOW]
- possession·AGAINST·W10·ALL = 52.9 [n=10, MEDIUM]
- possession·AGAINST·ALL_PRIOR·HOME = 52.2 [n=15, MEDIUM]
- possession·AGAINST·ALL_PRIOR·AWAY = 56.9333 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·ALL = 0.1667 [n=30, HIGH]
- red_cards·FOR·W5·ALL = 0.4 [n=5, LOW]
- red_cards·FOR·W10·ALL = 0.2 [n=10, MEDIUM]
- red_cards·FOR·ALL_PRIOR·HOME = 0.0667 [n=15, MEDIUM]
- red_cards·FOR·ALL_PRIOR·AWAY = 0.2667 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·ALL = 0.0667 [n=30, HIGH]
- red_cards·AGAINST·W5·ALL = 0.0 [n=5, LOW]
- red_cards·AGAINST·W10·ALL = 0.0 [n=10, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·HOME = 0.0667 [n=15, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·AWAY = 0.0667 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·ALL = 2.0333 [n=30, HIGH]
- saves·FOR·W5·ALL = 2.0 [n=5, LOW]
- saves·FOR·W10·ALL = 2.3 [n=10, MEDIUM]
- saves·FOR·ALL_PRIOR·HOME = 2.2667 [n=15, MEDIUM]
- saves·FOR·ALL_PRIOR·AWAY = 1.8 [n=15, MEDIUM]
- saves·AGAINST·ALL_PRIOR·ALL = 2.6 [n=30, HIGH]
- saves·AGAINST·W5·ALL = 2.4 [n=5, LOW]
- saves·AGAINST·W10·ALL = 2.8 [n=10, MEDIUM]
- saves·AGAINST·ALL_PRIOR·HOME = 3.0 [n=15, MEDIUM]
- saves·AGAINST·ALL_PRIOR·AWAY = 2.2 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·ALL = 7.6 [n=30, HIGH]
- shots_inside_box·FOR·W5·ALL = 8.2 [n=5, LOW]
- shots_inside_box·FOR·W10·ALL = 8.2 [n=10, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·HOME = 8.4667 [n=15, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·AWAY = 6.7333 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·ALL = 6.7667 [n=30, HIGH]
- shots_inside_box·AGAINST·W5·ALL = 7.0 [n=5, LOW]
- shots_inside_box·AGAINST·W10·ALL = 7.7 [n=10, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·HOME = 6.8 [n=15, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·AWAY = 6.7333 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·ALL = 4.9333 [n=30, HIGH]
- shots_off_target·FOR·W5·ALL = 5.2 [n=5, LOW]
- shots_off_target·FOR·W10·ALL = 5.4 [n=10, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·HOME = 5.2667 [n=15, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·AWAY = 4.6 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·ALL = 4.2 [n=30, HIGH]
- shots_off_target·AGAINST·W5·ALL = 2.4 [n=5, LOW]
- shots_off_target·AGAINST·W10·ALL = 3.8 [n=10, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·HOME = 4.1333 [n=15, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·AWAY = 4.2667 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·ALL = 3.5333 [n=30, HIGH]
- shots_on_target·FOR·W5·ALL = 3.8 [n=5, LOW]
- shots_on_target·FOR·W10·ALL = 3.9 [n=10, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·HOME = 4.3333 [n=15, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·AWAY = 2.7333 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·ALL = 3.6333 [n=30, HIGH]
- shots_on_target·AGAINST·W5·ALL = 3.0 [n=5, LOW]
- shots_on_target·AGAINST·W10·ALL = 3.6 [n=10, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·HOME = 3.3333 [n=15, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·AWAY = 3.9333 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·ALL = 4.2667 [n=30, HIGH]
- shots_outside_box·FOR·W5·ALL = 4.6 [n=5, LOW]
- shots_outside_box·FOR·W10·ALL = 5.0 [n=10, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·HOME = 4.9333 [n=15, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·AWAY = 3.6 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·ALL = 5.0 [n=30, HIGH]
- shots_outside_box·AGAINST·W5·ALL = 3.6 [n=5, LOW]
- shots_outside_box·AGAINST·W10·ALL = 4.9 [n=10, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·HOME = 4.8 [n=15, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·AWAY = 5.2 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·ALL = 17.1667 [n=30, HIGH]
- tackles·FOR·W5·ALL = 14.4 [n=5, LOW]
- tackles·FOR·W10·ALL = 15.6 [n=10, MEDIUM]
- tackles·FOR·ALL_PRIOR·HOME = 17.4667 [n=15, MEDIUM]
- tackles·FOR·ALL_PRIOR·AWAY = 16.8667 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·ALL = 17.9333 [n=30, HIGH]
- tackles·AGAINST·W5·ALL = 21.2 [n=5, LOW]
- tackles·AGAINST·W10·ALL = 21.4 [n=10, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·HOME = 18.2667 [n=15, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·AWAY = 17.6 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·ALL = 23.1667 [n=30, HIGH]
- throw_ins·FOR·W5·ALL = 27.0 [n=5, LOW]
- throw_ins·FOR·W10·ALL = 23.8 [n=10, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·HOME = 22.8667 [n=15, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·AWAY = 23.4667 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·ALL = 26.4333 [n=30, HIGH]
- throw_ins·AGAINST·W5·ALL = 26.6 [n=5, LOW]
- throw_ins·AGAINST·W10·ALL = 24.3 [n=10, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·HOME = 24.5333 [n=15, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·AWAY = 28.3333 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·ALL = 11.8667 [n=30, HIGH]
- total_shots·FOR·W5·ALL = 12.8 [n=5, LOW]
- total_shots·FOR·W10·ALL = 13.2 [n=10, MEDIUM]
- total_shots·FOR·ALL_PRIOR·HOME = 13.4 [n=15, MEDIUM]
- total_shots·FOR·ALL_PRIOR·AWAY = 10.3333 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·ALL = 11.7667 [n=30, HIGH]
- total_shots·AGAINST·W5·ALL = 10.6 [n=5, LOW]
- total_shots·AGAINST·W10·ALL = 12.6 [n=10, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·HOME = 11.6 [n=15, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·AWAY = 11.9333 [n=15, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·ALL = 22.3333 [n=3, LOW]
- touches_in_box·FOR·ALL_PRIOR·HOME = 22.3333 [n=3, LOW]
- touches_in_box·AGAINST·ALL_PRIOR·ALL = 15.3333 [n=3, LOW]
- touches_in_box·AGAINST·ALL_PRIOR·HOME = 15.3333 [n=3, LOW]
- xg·FOR·ALL_PRIOR·ALL = 1.131 [n=30, HIGH]
- xg·FOR·W5·ALL = 1.298 [n=5, LOW]
- xg·FOR·W10·ALL = 1.197 [n=10, MEDIUM]
- xg·FOR·ALL_PRIOR·HOME = 1.2973 [n=15, MEDIUM]
- xg·FOR·ALL_PRIOR·AWAY = 0.9647 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·ALL = 1.177 [n=30, HIGH]
- xg·AGAINST·W5·ALL = 0.77 [n=5, LOW]
- xg·AGAINST·W10·ALL = 1.136 [n=10, MEDIUM]
- xg·AGAINST·ALL_PRIOR·HOME = 1.0707 [n=15, MEDIUM]
- xg·AGAINST·ALL_PRIOR·AWAY = 1.2833 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·ALL = 2.2667 [n=30, HIGH]
- yellow_cards·FOR·W5·ALL = 2.0 [n=5, LOW]
- yellow_cards·FOR·W10·ALL = 2.4 [n=10, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·HOME = 2.5333 [n=15, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·AWAY = 2.0 [n=15, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·ALL = 2.1 [n=30, HIGH]
- yellow_cards·AGAINST·W5·ALL = 2.0 [n=5, LOW]
- yellow_cards·AGAINST·W10·ALL = 2.3 [n=10, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·HOME = 2.2 [n=15, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·AWAY = 2.0 [n=15, MEDIUM]

### Arm B — opponent-profile context (deterministic bands)

```json
{
 "axes": {
  "accurate_crosses_for": {
   "AWAY": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   },
   "HOME": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "corners_against": {
   "AWAY": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "corners_for": {
   "AWAY": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   }
  },
  "goals_against": {
   "AWAY": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  },
  "goals_for": {
   "AWAY": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   },
   "HOME": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "possession_for": {
   "AWAY": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   },
   "HOME": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "shots_on_target_against": {
   "AWAY": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "shots_on_target_for": {
   "AWAY": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   },
   "HOME": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  }
 },
 "similarity_version": "opponent_similarity_v1_pending"
}
```

---

## mt_012232411

- PIT-safe matches available: **54**; match rows included (both teams): **54**; omitted: **0** (reason: `None`); UNEXPLAINED_OMISSION: **0**.
- Metric cell exposure rate (non-null of serialized): **0.9545**; derived summaries: **462**.
- Availability map: `{"expected_formation": "UNAVAILABLE", "formation": "LOW_COVERAGE", "half_time_state": "UNAVAILABLE", "injuries": "UNAVAILABLE", "lineup": "PIT_UNSAFE", "opponent_profile": "AVAILABLE", "recent_vs_long": "AVAILABLE", "red_cards": "AVAILABLE", "temporal_event_state": "UNAVAILABLE", "venue": "AVAILABLE", "xg": "AVAILABLE"}`
- Arm A packet hash: `9ec9f0cc535a72f5fc82c0421614ef062d6b07d813f5711909d2f7415b3cfa65`
- Arm B packet hash: `e3e84f0d75ad22fb3182a09f6b4d59b1850159cb99623c7ad2901a5918701f1d`

### Arm A — frozen V3 compressed evidence (all items)

74 unconditional shrunk scalar items (venue=ALL, window=ALL_PRIOR):

| id | metric | value | n | reliability |
|---|---|---|---|---|
| HOME_ATK_corners_406027 | corners_for | 4.8553 | 27 | HIGH |
| HOME_DEF_corners_7cfac3 | corners_against | 5.3704 | 27 | HIGH |
| HOME_ATK_accurate_crosses_c28b9e | accurate_crosses_for | 4.3014 | 27 | HIGH |
| HOME_DEF_accurate_crosses_81ffb5 | accurate_crosses_against | 4.7559 | 27 | HIGH |
| HOME_ATK_total_shots_808ac9 | total_shots_for | 11.2931 | 27 | HIGH |
| HOME_DEF_total_shots_c0e347 | total_shots_against | 13.7477 | 27 | HIGH |
| HOME_ATK_shots_on_target_e955e0 | shots_on_target_for | 3.9216 | 27 | HIGH |
| HOME_DEF_shots_on_target_8a3812 | shots_on_target_against | 4.861 | 27 | HIGH |
| HOME_ATK_shots_off_target_11e91f | shots_off_target_for | 4.2645 | 27 | HIGH |
| HOME_DEF_shots_off_target_26031c | shots_off_target_against | 4.9009 | 27 | HIGH |
| HOME_ATK_blocked_shots_5198f8 | blocked_shots_for | 3.107 | 27 | HIGH |
| HOME_DEF_blocked_shots_09c3c4 | blocked_shots_against | 3.9858 | 27 | HIGH |
| HOME_ATK_shots_inside_box_cf538d | shots_inside_box_for | 7.3372 | 27 | HIGH |
| HOME_DEF_shots_inside_box_e6b28d | shots_inside_box_against | 9.2463 | 27 | HIGH |
| HOME_ATK_final_third_entries_5aa0be | final_third_entries_for | 57.8959 | 27 | HIGH |
| HOME_DEF_final_third_entries_4a40ef | final_third_entries_against | 56.6535 | 27 | HIGH |
| HOME_ATK_possession_190f3f | possession_for | 52.6061 | 27 | HIGH |
| HOME_DEF_possession_f8ada9 | possession_against | 47.3939 | 27 | HIGH |
| HOME_ATK_tackles_65b6c1 | tackles_for | 15.7701 | 27 | HIGH |
| HOME_DEF_tackles_e3c85e | tackles_against | 14.9519 | 27 | HIGH |
| HOME_ATK_fouls_8107c6 | fouls_for | 10.7624 | 27 | HIGH |
| HOME_DEF_fouls_b6d53c | fouls_against | 12.1261 | 27 | HIGH |
| HOME_ATK_yellow_cards_80b7a4 | yellow_cards_for | 2.2508 | 27 | HIGH |
| HOME_DEF_yellow_cards_8ee8aa | yellow_cards_against | 2.3114 | 27 | HIGH |
| HOME_ATK_clearances_ec2e18 | clearances_for | 18.4734 | 27 | HIGH |
| HOME_DEF_clearances_6d3f4c | clearances_against | 16.0188 | 27 | HIGH |
| HOME_ATK_interceptions_967965 | interceptions_for | 10.4183 | 27 | HIGH |
| HOME_DEF_interceptions_c82020 | interceptions_against | 8.8728 | 27 | HIGH |
| HOME_ATK_goals_08b15b | goals_for | 1.3704 | 27 | HIGH |
| HOME_DEF_goals_d53fdd | goals_against | 1.4917 | 27 | HIGH |
| HOME_ATK_throw_ins_b24629 | throw_ins_for | 22.67 | 27 | HIGH |
| HOME_DEF_throw_ins_208262 | throw_ins_against | 22.8821 | 27 | HIGH |
| HOME_ATK_big_chances_8a9e2f | big_chances_for | 1.797 | 27 | HIGH |
| HOME_DEF_big_chances_885151 | big_chances_against | 1.9788 | 27 | HIGH |
| HOME_ATK_saves_6bda8d | saves_for | 3.3357 | 27 | HIGH |
| HOME_DEF_saves_19ae14 | saves_against | 2.4569 | 27 | HIGH |
| AWAY_ATK_corners_ca1538 | corners_for | 7.2795 | 27 | HIGH |
| AWAY_DEF_corners_598e33 | corners_against | 4.4917 | 27 | HIGH |
| AWAY_ATK_accurate_crosses_005290 | accurate_crosses_for | 4.6347 | 27 | HIGH |
| AWAY_DEF_accurate_crosses_287e9c | accurate_crosses_against | 3.6347 | 27 | HIGH |
| AWAY_ATK_total_shots_004f7a | total_shots_for | 15.1416 | 27 | HIGH |
| AWAY_DEF_total_shots_403d28 | total_shots_against | 10.9901 | 27 | HIGH |
| AWAY_ATK_shots_on_target_9afd02 | shots_on_target_for | 5.4973 | 27 | HIGH |
| AWAY_DEF_shots_on_target_dcda5e | shots_on_target_against | 3.4973 | 27 | HIGH |
| AWAY_ATK_shots_off_target_b83815 | shots_off_target_for | 4.9615 | 27 | HIGH |
| AWAY_DEF_shots_off_target_5fe2d0 | shots_off_target_against | 3.9615 | 27 | HIGH |
| AWAY_ATK_blocked_shots_93d965 | blocked_shots_for | 4.6828 | 27 | HIGH |
| AWAY_DEF_blocked_shots_97ef03 | blocked_shots_against | 3.5313 | 27 | HIGH |
| AWAY_ATK_shots_inside_box_567ee5 | shots_inside_box_for | 9.9433 | 27 | HIGH |
| AWAY_DEF_shots_inside_box_446c80 | shots_inside_box_against | 7.0342 | 27 | HIGH |
| AWAY_ATK_touches_in_box_2c76ca | touches_in_box_for | 23.25 | 1 | LOW |
| AWAY_DEF_touches_in_box_319da5 | touches_in_box_against | 21.5357 | 1 | LOW |
| AWAY_ATK_final_third_entries_5a0987 | final_third_entries_for | 62.9262 | 27 | HIGH |
| AWAY_DEF_final_third_entries_ed75cd | final_third_entries_against | 41.8959 | 27 | HIGH |
| AWAY_ATK_possession_82105a | possession_for | 63.1818 | 27 | HIGH |
| AWAY_DEF_possession_012ecc | possession_against | 36.8182 | 27 | HIGH |
| AWAY_ATK_tackles_0865bc | tackles_for | 14.8913 | 27 | HIGH |
| AWAY_DEF_tackles_3e6a7d | tackles_against | 18.2246 | 27 | HIGH |
| AWAY_ATK_fouls_97bf91 | fouls_for | 10.3079 | 27 | HIGH |
| AWAY_DEF_fouls_94f7aa | fouls_against | 11.7321 | 27 | HIGH |
| AWAY_ATK_yellow_cards_120c77 | yellow_cards_for | 2.5841 | 27 | HIGH |
| AWAY_DEF_yellow_cards_367397 | yellow_cards_against | 2.8265 | 27 | HIGH |
| AWAY_ATK_clearances_74617f | clearances_for | 15.0794 | 27 | HIGH |
| AWAY_DEF_clearances_8bdc80 | clearances_against | 21.14 | 27 | HIGH |
| AWAY_ATK_interceptions_404e22 | interceptions_for | 8.9637 | 27 | HIGH |
| AWAY_DEF_interceptions_4be11b | interceptions_against | 10.388 | 27 | HIGH |
| AWAY_ATK_goals_5d2c6a | goals_for | 1.7644 | 27 | HIGH |
| AWAY_DEF_goals_4ad3b7 | goals_against | 1.1886 | 27 | HIGH |
| AWAY_ATK_throw_ins_64d189 | throw_ins_for | 19.6094 | 27 | HIGH |
| AWAY_DEF_throw_ins_35916f | throw_ins_against | 17.1852 | 27 | HIGH |
| AWAY_ATK_big_chances_065222 | big_chances_for | 2.4469 | 26 | HIGH |
| AWAY_DEF_big_chances_d5f920 | big_chances_against | 1.8219 | 26 | HIGH |
| AWAY_ATK_saves_50b33b | saves_for | 2.3054 | 27 | HIGH |
| AWAY_DEF_saves_bf5cbb | saves_against | 3.6387 | 27 | HIGH |

### Arm B — HOME_TEAM match-level matrix (27 rows × 55 cols)

Columns: `match_alias, kickoff_unix, competition, venue, opponent_alias, own_formation_family, opponent_formation_family, accurate_crosses_for, accurate_crosses_against, big_chances_for, big_chances_against, blocked_shots_for, blocked_shots_against, clearances_for, clearances_against, corners_for, corners_against, final_third_entries_for, final_third_entries_against, fouls_for, fouls_against, goals_for, goals_against, interceptions_for, interceptions_against, npxg_for, npxg_against, offsides_for, offsides_against, possession_for, possession_against, red_cards_for, red_cards_against, saves_for, saves_against, shots_inside_box_for, shots_inside_box_against, shots_off_target_for, shots_off_target_against, shots_on_target_for, shots_on_target_against, shots_outside_box_for, shots_outside_box_against, tackles_for, tackles_against, throw_ins_for, throw_ins_against, total_shots_for, total_shots_against, touches_in_box_for, touches_in_box_against, xg_for, xg_against, yellow_cards_for, yellow_cards_against`

| match_alias | kickoff_unix | competition | venue | opponent_alias | own_formation_family | opponent_formation_family | accurate_crosses_for | accurate_crosses_against | big_chances_for | big_chances_against | blocked_shots_for | blocked_shots_against | clearances_for | clearances_against | corners_for | corners_against | final_third_entries_for | final_third_entries_against | fouls_for | fouls_against | goals_for | goals_against | interceptions_for | interceptions_against | npxg_for | npxg_against | offsides_for | offsides_against | possession_for | possession_against | red_cards_for | red_cards_against | saves_for | saves_against | shots_inside_box_for | shots_inside_box_against | shots_off_target_for | shots_off_target_against | shots_on_target_for | shots_on_target_against | shots_outside_box_for | shots_outside_box_against | tackles_for | tackles_against | throw_ins_for | throw_ins_against | total_shots_for | total_shots_against | touches_in_box_for | touches_in_box_against | xg_for | xg_against | yellow_cards_for | yellow_cards_against |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| m_mt_250079725 | 1691244000 | COMPETITION | HOME | OPP_001 |  |  | 2.0 | 3.0 | 2.0 | 0.0 | 1.0 | 0.0 | 14.0 | 20.0 | 5.0 | 5.0 | 47.0 | 50.0 | 9.0 | 12.0 | 1.0 | 1.0 | 9.0 | 13.0 | 1.41 | 0.77 | 2.0 | 1.0 | 59.0 | 41.0 | 0.0 | 0.0 | 4.0 | 4.0 | 7.0 | 7.0 | 4.0 | 6.0 | 6.0 | 5.0 | 4.0 | 4.0 | 21.0 | 20.0 | 40.0 | 30.0 | 11.0 | 11.0 |  |  | 1.37 | 0.77 | 1.0 | 4.0 |
| m_mt_624491586 | 1691848800 | COMPETITION | AWAY | OPP_002 |  |  | 10.0 | 3.0 | 3.0 | 2.0 | 2.0 | 4.0 | 16.0 | 20.0 | 8.0 | 4.0 | 57.0 | 48.0 | 10.0 | 10.0 | 2.0 | 3.0 | 10.0 | 11.0 | 2.43 | 1.11 | 2.0 | 3.0 | 58.0 | 42.0 | 0.0 | 0.0 | 1.0 | 1.0 | 13.0 | 8.0 | 7.0 | 4.0 | 4.0 | 3.0 | 0.0 | 3.0 | 10.0 | 11.0 | 15.0 | 27.0 | 13.0 | 11.0 |  |  | 2.24 | 1.89 | 4.0 | 3.0 |
| m_mt_839904633 | 1692453600 | COMPETITION | HOME | OPP_003 |  |  | 4.0 | 8.0 | 1.0 | 0.0 | 0.0 | 1.0 | 15.0 | 5.0 | 3.0 | 8.0 | 53.0 | 53.0 | 12.0 | 10.0 | 1.0 | 1.0 | 14.0 | 7.0 | 0.73 | 0.86 | 1.0 | 3.0 | 40.0 | 60.0 | 0.0 | 0.0 | 1.0 | 2.0 | 5.0 | 8.0 | 4.0 | 8.0 | 3.0 | 2.0 | 2.0 | 3.0 | 21.0 | 11.0 | 13.0 | 25.0 | 7.0 | 11.0 |  |  | 0.73 | 0.86 | 2.0 | 1.0 |
| m_mt_624491541 | 1693058400 | COMPETITION | AWAY | OPP_004 |  |  | 1.0 | 4.0 | 1.0 | 0.0 | 3.0 | 2.0 | 17.0 | 21.0 | 4.0 | 5.0 | 73.0 | 64.0 | 7.0 | 12.0 | 1.0 | 2.0 | 12.0 | 13.0 | 0.33 | 0.59 | 0.0 | 4.0 | 60.0 | 40.0 | 0.0 | 0.0 | 1.0 | 0.0 | 4.0 | 5.0 | 6.0 | 6.0 | 1.0 | 3.0 | 6.0 | 6.0 | 20.0 | 19.0 | 20.0 | 24.0 | 10.0 | 11.0 |  |  | 0.35 | 0.59 | 1.0 | 2.0 |
| m_mt_250079861 | 1693654200 | COMPETITION | HOME | OPP_005 |  |  | 7.0 | 6.0 | 1.0 | 3.0 | 4.0 | 7.0 | 14.0 | 17.0 | 4.0 | 8.0 | 78.0 | 58.0 | 13.0 | 17.0 | 1.0 | 2.0 | 7.0 | 4.0 | 1.36 | 2.31 | 0.0 | 4.0 | 61.0 | 39.0 | 0.0 | 0.0 | 1.0 | 3.0 | 7.0 | 13.0 | 4.0 | 5.0 | 4.0 | 4.0 | 5.0 | 3.0 | 11.0 | 13.0 | 18.0 | 25.0 | 12.0 | 16.0 |  |  | 1.44 | 2.3 | 3.0 | 2.0 |
| m_mt_195563768 | 1694889900 | COMPETITION | AWAY | OPP_006 |  |  | 2.0 | 3.0 | 1.0 | 3.0 | 3.0 | 2.0 | 21.0 | 20.0 | 2.0 | 2.0 | 68.0 | 62.0 | 11.0 | 13.0 | 0.0 | 2.0 | 13.0 | 8.0 | 0.6 | 0.75 | 3.0 | 2.0 | 51.0 | 49.0 | 0.0 | 0.0 | 4.0 | 3.0 | 5.0 | 8.0 | 3.0 | 4.0 | 3.0 | 7.0 | 4.0 | 5.0 | 14.0 | 14.0 | 28.0 | 28.0 | 9.0 | 13.0 |  |  | 0.6 | 1.54 | 1.0 | 1.0 |
| m_mt_839904666 | 1695149100 | COMPETITION | AWAY | OPP_007 |  |  | 2.0 | 5.0 | 1.0 | 1.0 | 1.0 | 2.0 | 26.0 | 11.0 | 6.0 | 4.0 | 64.0 | 80.0 | 17.0 | 12.0 | 1.0 | 1.0 | 12.0 | 6.0 | 0.43 | 1.05 | 3.0 | 6.0 | 51.0 | 49.0 | 1.0 | 0.0 | 2.0 | 2.0 | 3.0 | 8.0 | 4.0 | 6.0 | 3.0 | 3.0 | 5.0 | 3.0 | 21.0 | 12.0 | 19.0 | 36.0 | 8.0 | 11.0 |  |  | 0.57 | 1.05 | 3.0 | 1.0 |
| m_mt_367710234 | 1695477600 | COMPETITION | HOME | OPP_008 |  |  | 3.0 | 4.0 | 4.0 | 1.0 | 3.0 | 3.0 | 15.0 | 12.0 | 2.0 | 5.0 | 62.0 | 48.0 | 12.0 | 16.0 | 3.0 | 0.0 | 9.0 | 10.0 | 1.22 | 0.67 | 4.0 | 2.0 | 57.0 | 43.0 | 0.0 | 0.0 | 1.0 | 1.0 | 8.0 | 8.0 | 5.0 | 6.0 | 4.0 | 1.0 | 4.0 | 2.0 | 25.0 | 23.0 | 35.0 | 22.0 | 12.0 | 10.0 |  |  | 2.04 | 0.74 | 2.0 | 2.0 |
| m_mt_012238573 | 1696082400 | COMPETITION | AWAY | OPP_009 |  |  | 1.0 | 8.0 | 3.0 | 3.0 | 0.0 | 10.0 | 20.0 | 2.0 | 0.0 | 6.0 | 53.0 | 71.0 | 10.0 | 18.0 | 3.0 | 0.0 | 8.0 | 7.0 | 0.34 | 1.54 | 0.0 | 3.0 | 50.0 | 50.0 | 0.0 | 0.0 | 5.0 | 2.0 | 5.0 | 12.0 | 2.0 | 7.0 | 5.0 | 5.0 | 2.0 | 10.0 | 12.0 | 13.0 | 19.0 | 21.0 | 7.0 | 22.0 |  |  | 1.24 | 1.54 | 2.0 | 2.0 |
| m_mt_978826372 | 1696445100 | COMPETITION | HOME | OPP_010 |  |  | 9.0 | 6.0 | 4.0 | 2.0 | 9.0 | 5.0 | 20.0 | 19.0 | 8.0 | 7.0 | 45.0 | 53.0 | 12.0 | 12.0 | 2.0 | 1.0 | 6.0 | 7.0 | 2.51 | 1.62 | 1.0 | 3.0 | 55.0 | 45.0 | 0.0 | 0.0 | 4.0 | 4.0 | 17.0 | 12.0 | 7.0 | 4.0 | 7.0 | 5.0 | 6.0 | 2.0 | 12.0 | 10.0 | 26.0 | 16.0 | 23.0 | 14.0 |  |  | 2.53 | 1.62 | 4.0 | 2.0 |
| m_mt_195563850 | 1696687200 | COMPETITION | AWAY | OPP_011 |  |  | 6.0 | 6.0 | 3.0 | 5.0 | 6.0 | 6.0 | 31.0 | 14.0 | 7.0 | 12.0 | 67.0 | 67.0 | 5.0 | 11.0 | 3.0 | 1.0 | 13.0 | 7.0 | 1.92 | 1.33 | 2.0 | 2.0 | 51.0 | 49.0 | 0.0 | 0.0 | 6.0 | 3.0 | 12.0 | 10.0 | 2.0 | 3.0 | 6.0 | 7.0 | 2.0 | 6.0 | 18.0 | 10.0 | 25.0 | 25.0 | 14.0 | 16.0 |  |  | 2.07 | 1.31 | 0.0 | 2.0 |
| m_mt_012238537 | 1697896800 | COMPETITION | HOME | OPP_012 |  |  | 3.0 | 5.0 | 0.0 | 3.0 | 4.0 | 5.0 | 19.0 | 9.0 | 3.0 | 3.0 | 42.0 | 67.0 | 10.0 | 5.0 | 1.0 | 3.0 | 9.0 | 11.0 | 0.61 | 3.08 | 2.0 | 1.0 | 38.0 | 62.0 | 0.0 | 0.0 | 4.0 | 3.0 | 6.0 | 12.0 | 3.0 | 6.0 | 4.0 | 7.0 | 5.0 | 6.0 | 9.0 | 17.0 | 20.0 | 14.0 | 11.0 | 18.0 |  |  | 0.69 | 3.07 | 2.0 | 3.0 |
| m_mt_250079171 | 1698173100 | COMPETITION | HOME | OPP_013 |  |  | 8.0 | 4.0 | 1.0 | 1.0 | 2.0 | 3.0 | 7.0 | 21.0 | 6.0 | 4.0 | 64.0 | 61.0 | 7.0 | 14.0 | 0.0 | 1.0 | 11.0 | 8.0 | 0.68 | 0.7 | 2.0 | 0.0 | 59.0 | 41.0 | 0.0 | 0.0 | 4.0 | 3.0 | 4.0 | 7.0 | 4.0 | 4.0 | 3.0 | 5.0 | 5.0 | 5.0 | 18.0 | 26.0 | 33.0 | 31.0 | 9.0 | 12.0 |  |  | 0.68 | 0.73 | 0.0 | 3.0 |
| m_mt_743352600 | 1698501600 | COMPETITION | AWAY | OPP_014 |  |  | 2.0 | 7.0 | 1.0 | 3.0 | 4.0 | 7.0 | 14.0 | 18.0 | 5.0 | 6.0 | 64.0 | 63.0 | 7.0 | 15.0 | 1.0 | 0.0 | 20.0 | 10.0 | 0.62 | 1.75 | 3.0 | 3.0 | 41.0 | 59.0 | 0.0 | 0.0 | 5.0 | 3.0 | 6.0 | 14.0 | 7.0 | 7.0 | 4.0 | 6.0 | 9.0 | 6.0 | 10.0 | 13.0 | 28.0 | 23.0 | 15.0 | 20.0 |  |  | 1.02 | 1.75 | 3.0 | 5.0 |
| m_mt_250079239 | 1699110000 | COMPETITION | HOME | OPP_015 |  |  | 1.0 | 7.0 | 1.0 | 1.0 | 1.0 | 10.0 | 29.0 | 8.0 | 2.0 | 8.0 | 42.0 | 89.0 | 13.0 | 12.0 | 0.0 | 0.0 | 15.0 | 8.0 |  |  | 1.0 | 2.0 | 29.0 | 71.0 | 1.0 | 0.0 | 3.0 | 2.0 | 3.0 | 12.0 | 0.0 | 12.0 | 2.0 | 3.0 | 0.0 | 13.0 | 12.0 | 7.0 | 18.0 | 20.0 | 3.0 | 25.0 |  |  | 0.87 | 1.96 | 4.0 | 3.0 |
| m_mt_367710354 | 1699714800 | COMPETITION | AWAY | OPP_016 |  |  | 2.0 | 5.0 | 3.0 | 7.0 | 3.0 | 4.0 | 14.0 | 13.0 | 2.0 | 6.0 | 68.0 | 43.0 | 9.0 | 15.0 | 2.0 | 3.0 | 6.0 | 10.0 | 1.64 | 3.04 | 1.0 | 4.0 | 62.0 | 38.0 | 1.0 | 0.0 | 6.0 | 2.0 | 5.0 | 15.0 | 0.0 | 9.0 | 4.0 | 9.0 | 2.0 | 7.0 | 13.0 | 12.0 | 22.0 | 20.0 | 7.0 | 22.0 |  |  | 1.64 | 3.79 | 3.0 | 2.0 |
| m_mt_978826971 | 1700924400 | COMPETITION | HOME | OPP_017 |  |  | 3.0 | 7.0 | 1.0 | 1.0 | 5.0 | 5.0 | 15.0 | 9.0 | 2.0 | 1.0 | 48.0 | 59.0 | 12.0 | 11.0 | 2.0 | 2.0 | 16.0 | 7.0 | 1.17 | 1.45 | 4.0 | 3.0 | 55.0 | 45.0 | 0.0 | 0.0 | 7.0 | 2.0 | 10.0 | 11.0 | 6.0 | 4.0 | 4.0 | 9.0 | 5.0 | 7.0 | 21.0 | 11.0 | 13.0 | 21.0 | 15.0 | 18.0 |  |  | 1.3 | 1.44 | 0.0 | 2.0 |
| m_mt_406685464 | 1701287100 | COMPETITION | AWAY | OPP_018 |  |  | 2.0 | 5.0 | 1.0 | 5.0 | 6.0 | 6.0 | 21.0 | 20.0 | 5.0 | 6.0 | 42.0 | 42.0 | 11.0 | 12.0 | 1.0 | 3.0 | 14.0 | 8.0 | 0.24 | 2.41 | 2.0 | 4.0 | 50.0 | 50.0 | 0.0 | 0.0 | 5.0 | 1.0 | 4.0 | 13.0 | 2.0 | 4.0 | 2.0 | 8.0 | 6.0 | 5.0 | 22.0 | 13.0 | 18.0 | 27.0 | 10.0 | 18.0 |  |  | 0.34 | 2.41 | 1.0 | 0.0 |
| m_mt_581141432 | 1701529200 | COMPETITION | HOME | OPP_019 |  |  | 12.0 | 2.0 | 4.0 | 0.0 | 7.0 | 1.0 | 8.0 | 39.0 | 19.0 | 1.0 | 104.0 | 33.0 | 11.0 | 9.0 | 1.0 | 1.0 | 4.0 | 6.0 | 1.47 | 0.29 | 3.0 | 2.0 | 77.0 | 23.0 | 0.0 | 0.0 | 3.0 | 4.0 | 11.0 | 2.0 | 10.0 | 1.0 | 5.0 | 3.0 | 11.0 | 3.0 | 12.0 | 18.0 | 27.0 | 14.0 | 22.0 | 5.0 |  |  | 1.65 | 0.29 | 1.0 | 2.0 |
| m_mt_743353597 | 1702134000 | COMPETITION | AWAY | OPP_020 |  |  | 9.0 | 1.0 | 2.0 | 0.0 | 3.0 | 1.0 | 23.0 | 15.0 | 11.0 | 6.0 | 58.0 | 57.0 | 9.0 | 9.0 | 2.0 | 1.0 | 5.0 | 11.0 | 1.85 | 0.53 | 2.0 | 0.0 | 70.0 | 30.0 | 0.0 | 1.0 | 2.0 | 8.0 | 14.0 | 5.0 | 7.0 | 3.0 | 9.0 | 3.0 | 5.0 | 2.0 | 8.0 | 14.0 | 26.0 | 22.0 | 19.0 | 7.0 |  |  | 2.02 | 0.53 | 3.0 | 4.0 |
| m_mt_581141428 | 1702410300 | COMPETITION | AWAY | OPP_021 |  |  | 3.0 | 6.0 | 1.0 | 3.0 | 3.0 | 5.0 | 26.0 | 20.0 | 3.0 | 6.0 | 46.0 | 61.0 | 14.0 | 11.0 | 1.0 | 1.0 | 10.0 | 16.0 | 0.24 | 2.02 | 1.0 | 5.0 | 56.0 | 44.0 | 0.0 | 0.0 | 3.0 | 0.0 | 3.0 | 13.0 | 3.0 | 7.0 | 2.0 | 4.0 | 5.0 | 3.0 | 10.0 | 20.0 | 26.0 | 18.0 | 8.0 | 16.0 |  |  | 0.67 | 2.78 | 2.0 | 3.0 |
| m_mt_250070791 | 1702738800 | COMPETITION | HOME | OPP_022 |  |  | 3.0 | 2.0 | 3.0 | 2.0 | 2.0 | 3.0 | 17.0 | 11.0 | 4.0 | 4.0 | 56.0 | 41.0 | 14.0 | 14.0 | 1.0 | 2.0 | 11.0 | 6.0 | 1.23 | 1.08 | 2.0 | 1.0 | 58.0 | 42.0 | 0.0 | 0.0 | 2.0 | 2.0 | 9.0 | 8.0 | 5.0 | 2.0 | 3.0 | 4.0 | 1.0 | 1.0 | 18.0 | 15.0 | 25.0 | 20.0 | 10.0 | 9.0 |  |  | 1.32 | 1.08 | 2.0 | 3.0 |
| m_mt_743353519 | 1703274300 | COMPETITION | HOME | OPP_004 |  |  | 5.0 | 6.0 | 1.0 | 0.0 | 2.0 | 1.0 | 17.0 | 18.0 | 4.0 | 3.0 | 62.0 | 60.0 | 10.0 | 8.0 | 2.0 | 1.0 | 5.0 | 4.0 | 0.4 | 0.39 | 3.0 | 2.0 | 62.0 | 38.0 | 0.0 | 0.0 | 3.0 | 2.0 | 8.0 | 5.0 | 4.0 | 4.0 | 4.0 | 4.0 | 2.0 | 4.0 | 14.0 | 18.0 | 19.0 | 22.0 | 10.0 | 9.0 |  |  | 0.77 | 0.39 | 4.0 | 3.0 |
| m_mt_743353973 | 1703602800 | COMPETITION | AWAY | OPP_023 |  |  | 1.0 | 2.0 | 2.0 | 3.0 | 1.0 | 2.0 | 22.0 | 3.0 | 1.0 | 3.0 | 25.0 | 45.0 | 13.0 | 15.0 | 0.0 | 5.0 | 14.0 | 9.0 | 0.39 | 2.05 | 1.0 | 0.0 | 40.0 | 60.0 | 0.0 | 0.0 | 4.0 | 1.0 | 4.0 | 8.0 | 2.0 | 0.0 | 1.0 | 9.0 | 0.0 | 3.0 | 17.0 | 18.0 | 17.0 | 16.0 | 4.0 | 11.0 |  |  | 0.39 | 2.05 | 4.0 | 2.0 |
| m_mt_406686724 | 1703879100 | COMPETITION | AWAY | OPP_003 |  |  | 5.0 | 11.0 | 1.0 | 2.0 | 2.0 | 9.0 | 17.0 | 19.0 | 4.0 | 12.0 | 76.0 | 44.0 | 11.0 | 14.0 | 2.0 | 2.0 | 8.0 | 16.0 |  |  | 1.0 | 3.0 | 51.0 | 49.0 | 0.0 | 0.0 | 3.0 | 2.0 | 8.0 | 16.0 | 6.0 | 7.0 | 4.0 | 5.0 | 4.0 | 5.0 | 22.0 | 18.0 | 15.0 | 25.0 | 12.0 | 21.0 |  |  | 1.2 | 2.61 | 4.0 | 1.0 |
| m_mt_581141242 | 1704121200 | COMPETITION | HOME | OPP_002 |  |  | 6.0 | 6.0 | 1.0 | 2.0 | 2.0 | 3.0 | 29.0 | 16.0 | 3.0 | 5.0 | 60.0 | 61.0 | 10.0 | 7.0 | 1.0 | 0.0 | 15.0 | 6.0 | 0.57 | 1.9 | 2.0 | 1.0 | 42.0 | 58.0 | 0.0 | 0.0 | 5.0 | 3.0 | 7.0 | 9.0 | 4.0 | 2.0 | 4.0 | 5.0 | 3.0 | 1.0 | 15.0 | 7.0 | 19.0 | 25.0 | 10.0 | 10.0 |  |  | 0.67 | 1.9 | 2.0 | 0.0 |
| m_mt_978828128 | 1705158000 | COMPETITION | AWAY | OPP_001 |  |  | 6.0 | 1.0 | 1.0 | 1.0 | 1.0 | 2.0 | 12.0 | 18.0 | 5.0 | 5.0 | 48.0 | 51.0 | 11.0 | 21.0 | 2.0 | 2.0 | 10.0 | 6.0 |  |  | 2.0 | 3.0 | 53.0 | 47.0 | 0.0 | 0.0 | 4.0 | 1.0 | 6.0 | 8.0 | 2.0 | 3.0 | 3.0 | 6.0 | 0.0 | 3.0 | 17.0 | 13.0 | 32.0 | 26.0 | 6.0 | 11.0 |  |  | 0.74 | 1.57 | 3.0 | 5.0 |

### Arm B — AWAY_TEAM match-level matrix (27 rows × 55 cols)

Columns: `match_alias, kickoff_unix, competition, venue, opponent_alias, own_formation_family, opponent_formation_family, accurate_crosses_for, accurate_crosses_against, big_chances_for, big_chances_against, blocked_shots_for, blocked_shots_against, clearances_for, clearances_against, corners_for, corners_against, final_third_entries_for, final_third_entries_against, fouls_for, fouls_against, goals_for, goals_against, interceptions_for, interceptions_against, npxg_for, npxg_against, offsides_for, offsides_against, possession_for, possession_against, red_cards_for, red_cards_against, saves_for, saves_against, shots_inside_box_for, shots_inside_box_against, shots_off_target_for, shots_off_target_against, shots_on_target_for, shots_on_target_against, shots_outside_box_for, shots_outside_box_against, tackles_for, tackles_against, throw_ins_for, throw_ins_against, total_shots_for, total_shots_against, touches_in_box_for, touches_in_box_against, xg_for, xg_against, yellow_cards_for, yellow_cards_against`

| match_alias | kickoff_unix | competition | venue | opponent_alias | own_formation_family | opponent_formation_family | accurate_crosses_for | accurate_crosses_against | big_chances_for | big_chances_against | blocked_shots_for | blocked_shots_against | clearances_for | clearances_against | corners_for | corners_against | final_third_entries_for | final_third_entries_against | fouls_for | fouls_against | goals_for | goals_against | interceptions_for | interceptions_against | npxg_for | npxg_against | offsides_for | offsides_against | possession_for | possession_against | red_cards_for | red_cards_against | saves_for | saves_against | shots_inside_box_for | shots_inside_box_against | shots_off_target_for | shots_off_target_against | shots_on_target_for | shots_on_target_against | shots_outside_box_for | shots_outside_box_against | tackles_for | tackles_against | throw_ins_for | throw_ins_against | total_shots_for | total_shots_against | touches_in_box_for | touches_in_box_against | xg_for | xg_against | yellow_cards_for | yellow_cards_against |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| m_mt_581147491 | 1691175600 | COMPETITION | AWAY | OPP_008 |  |  | 4.0 | 1.0 | 1.0 | 0.0 | 9.0 | 3.0 | 22.0 | 33.0 | 6.0 | 3.0 | 84.0 | 29.0 | 10.0 | 12.0 | 2.0 | 1.0 | 3.0 | 7.0 | 1.39 | 0.56 | 0.0 | 2.0 | 80.0 | 20.0 | 0.0 | 0.0 | 0.0 | 4.0 | 14.0 | 6.0 | 7.0 | 4.0 | 7.0 | 1.0 | 9.0 | 2.0 | 16.0 | 21.0 | 20.0 | 7.0 | 23.0 | 8.0 |  |  | 1.39 | 0.56 | 4.0 | 4.0 |
| m_mt_012238979 | 1691848800 | COMPETITION | HOME | OPP_010 |  |  | 9.0 | 4.0 | 6.0 | 6.0 | 8.0 | 4.0 | 6.0 | 27.0 | 12.0 | 4.0 | 61.0 | 28.0 | 12.0 | 13.0 | 4.0 | 4.0 | 11.0 | 14.0 | 2.2 | 2.09 | 2.0 | 4.0 | 70.0 | 30.0 | 0.0 | 0.0 | 2.0 | 6.0 | 17.0 | 11.0 | 12.0 | 5.0 | 11.0 | 6.0 | 14.0 | 4.0 | 13.0 | 15.0 | 19.0 | 12.0 | 31.0 | 15.0 |  |  | 3.76 | 2.06 | 7.0 | 4.0 |
| m_mt_581147373 | 1692444600 | COMPETITION | AWAY | OPP_011 |  |  | 8.0 | 4.0 | 3.0 | 1.0 | 5.0 | 9.0 | 16.0 | 17.0 | 10.0 | 5.0 | 59.0 | 35.0 | 15.0 | 11.0 | 2.0 | 1.0 | 11.0 | 6.0 |  |  | 4.0 | 0.0 | 61.0 | 39.0 | 0.0 | 0.0 | 1.0 | 8.0 | 13.0 | 9.0 | 5.0 | 4.0 | 9.0 | 2.0 | 6.0 | 6.0 | 15.0 | 24.0 | 25.0 | 15.0 | 19.0 | 15.0 |  |  | 2.11 | 1.38 | 4.0 | 2.0 |
| m_mt_839904699 | 1693058400 | COMPETITION | HOME | OPP_007 |  |  | 2.0 | 3.0 |  |  | 3.0 | 3.0 | 8.0 | 12.0 | 4.0 | 3.0 | 94.0 | 41.0 | 8.0 | 14.0 | 2.0 | 1.0 | 8.0 | 11.0 | 0.42 | 0.64 | 0.0 | 3.0 | 74.0 | 26.0 | 0.0 | 0.0 | 4.0 | 1.0 | 4.0 | 8.0 | 1.0 | 3.0 | 3.0 | 5.0 | 3.0 | 3.0 | 9.0 | 20.0 | 18.0 | 22.0 | 7.0 | 11.0 |  |  | 0.42 | 0.64 | 4.0 | 3.0 |
| m_mt_195563707 | 1693654200 | COMPETITION | AWAY | OPP_015 |  |  | 7.0 | 6.0 | 1.0 | 6.0 | 4.0 | 4.0 | 11.0 | 13.0 | 8.0 | 5.0 | 61.0 | 41.0 | 10.0 | 20.0 | 0.0 | 5.0 | 11.0 | 11.0 |  |  | 1.0 | 4.0 | 68.0 | 32.0 | 0.0 | 0.0 | 5.0 | 2.0 | 6.0 | 10.0 | 7.0 | 4.0 | 2.0 | 10.0 | 7.0 | 8.0 | 21.0 | 25.0 | 17.0 | 20.0 | 13.0 | 18.0 |  |  | 0.84 | 1.94 | 2.0 | 2.0 |
| m_mt_624491594 | 1694804400 | COMPETITION | HOME | OPP_012 |  |  | 5.0 | 2.0 | 3.0 | 7.0 | 7.0 | 3.0 | 13.0 | 27.0 | 9.0 | 3.0 | 57.0 | 27.0 | 11.0 | 12.0 | 1.0 | 4.0 | 6.0 | 8.0 | 1.56 | 4.14 | 0.0 | 1.0 | 55.0 | 45.0 | 1.0 | 0.0 | 4.0 | 7.0 | 8.0 | 12.0 | 4.0 | 4.0 | 8.0 | 8.0 | 11.0 | 3.0 | 23.0 | 22.0 | 32.0 | 15.0 | 19.0 | 15.0 |  |  | 1.56 | 4.14 | 2.0 | 4.0 |
| m_mt_195563771 | 1695149100 | COMPETITION | HOME | OPP_016 |  |  | 5.0 | 3.0 | 0.0 | 2.0 | 6.0 | 4.0 | 11.0 | 25.0 | 9.0 | 3.0 | 46.0 | 49.0 | 9.0 | 13.0 | 0.0 | 1.0 | 13.0 | 7.0 | 0.85 | 0.64 | 3.0 | 0.0 | 59.0 | 41.0 | 0.0 | 0.0 | 2.0 | 3.0 | 8.0 | 5.0 | 4.0 | 4.0 | 3.0 | 3.0 | 5.0 | 6.0 | 10.0 | 18.0 | 19.0 | 29.0 | 13.0 | 11.0 |  |  | 0.84 | 0.67 | 2.0 | 2.0 |
| m_mt_978826497 | 1695477600 | COMPETITION | AWAY | OPP_022 | BACK_FOUR | BACK_FOUR | 3.0 | 1.0 | 2.0 | 4.0 | 4.0 | 2.0 | 16.0 | 18.0 | 7.0 | 5.0 | 47.0 | 62.0 | 7.0 | 16.0 | 1.0 | 2.0 | 14.0 | 12.0 | 1.44 | 2.32 | 1.0 | 4.0 | 49.0 | 51.0 | 0.0 | 0.0 | 3.0 | 4.0 | 9.0 | 10.0 | 6.0 | 7.0 | 5.0 | 5.0 | 6.0 | 4.0 | 12.0 | 22.0 | 9.0 | 25.0 | 15.0 | 14.0 |  |  | 1.44 | 3.11 | 1.0 | 3.0 |
| m_mt_743352622 | 1696073400 | COMPETITION | HOME | OPP_018 |  |  | 2.0 | 4.0 | 3.0 | 0.0 | 4.0 | 5.0 | 24.0 | 7.0 | 5.0 | 6.0 | 49.0 | 49.0 | 14.0 | 13.0 | 3.0 | 1.0 | 6.0 | 8.0 | 1.48 | 0.92 | 4.0 | 3.0 | 47.0 | 53.0 | 0.0 | 0.0 | 4.0 | 2.0 | 8.0 | 12.0 | 1.0 | 5.0 | 5.0 | 5.0 | 2.0 | 3.0 | 17.0 | 13.0 | 22.0 | 24.0 | 10.0 | 15.0 |  |  | 1.48 | 0.92 | 4.0 | 1.0 |
| m_mt_406685252 | 1696359600 | COMPETITION | AWAY | OPP_021 |  |  | 3.0 | 5.0 | 2.0 | 0.0 | 2.0 | 7.0 | 35.0 | 8.0 | 6.0 | 8.0 | 50.0 | 65.0 | 2.0 | 17.0 | 1.0 | 0.0 | 12.0 | 15.0 | 0.81 | 0.72 | 1.0 | 1.0 | 58.0 | 42.0 | 0.0 | 0.0 | 3.0 | 3.0 | 6.0 | 6.0 | 3.0 | 6.0 | 4.0 | 2.0 | 3.0 | 9.0 | 12.0 | 21.0 | 20.0 | 20.0 | 9.0 | 15.0 |  |  | 0.97 | 0.72 | 1.0 | 5.0 |
| m_mt_581147919 | 1696687200 | COMPETITION | HOME | OPP_020 |  |  | 7.0 | 1.0 | 5.0 | 0.0 | 5.0 | 1.0 | 11.0 | 38.0 | 12.0 | 4.0 | 74.0 | 51.0 | 8.0 | 13.0 | 1.0 | 1.0 | 5.0 | 10.0 | 3.59 | 0.14 | 2.0 | 3.0 | 80.0 | 20.0 | 0.0 | 0.0 | 1.0 | 7.0 | 16.0 | 1.0 | 7.0 | 1.0 | 10.0 | 2.0 | 6.0 | 3.0 | 13.0 | 22.0 | 24.0 | 7.0 | 22.0 | 4.0 |  |  | 3.23 | 0.14 | 2.0 | 6.0 |
| m_mt_839904759 | 1697896800 | COMPETITION | AWAY | OPP_017 |  |  | 5.0 | 3.0 | 2.0 | 1.0 | 7.0 | 6.0 | 15.0 | 26.0 | 9.0 | 7.0 | 54.0 | 36.0 | 14.0 | 13.0 | 2.0 | 1.0 | 9.0 | 8.0 | 1.51 | 1.17 | 2.0 | 4.0 | 57.0 | 43.0 | 0.0 | 0.0 | 2.0 | 3.0 | 12.0 | 10.0 | 6.0 | 4.0 | 5.0 | 3.0 | 6.0 | 3.0 | 11.0 | 11.0 | 19.0 | 10.0 | 18.0 | 13.0 |  |  | 1.51 | 1.17 | 3.0 | 5.0 |
| m_mt_624491054 | 1698259500 | COMPETITION | AWAY | OPP_004 |  |  | 6.0 | 5.0 | 1.0 | 1.0 | 1.0 | 4.0 | 17.0 | 18.0 | 2.0 | 7.0 | 38.0 | 61.0 | 13.0 | 16.0 | 2.0 | 2.0 | 4.0 | 9.0 | 0.67 | 0.85 | 0.0 | 1.0 | 72.0 | 28.0 | 0.0 | 0.0 | 3.0 | 4.0 | 7.0 | 7.0 | 7.0 | 2.0 | 5.0 | 5.0 | 6.0 | 4.0 | 14.0 | 13.0 | 15.0 | 16.0 | 13.0 | 11.0 |  |  | 0.85 | 0.85 | 3.0 | 3.0 |
| m_mt_839904776 | 1698492600 | COMPETITION | HOME | OPP_001 |  |  | 6.0 | 2.0 | 4.0 | 1.0 | 2.0 | 2.0 | 16.0 | 15.0 | 4.0 | 4.0 | 59.0 | 35.0 | 8.0 | 12.0 | 3.0 | 1.0 | 8.0 | 12.0 | 2.29 | 0.6 | 1.0 | 2.0 | 71.0 | 29.0 | 0.0 | 0.0 | 1.0 | 2.0 | 7.0 | 6.0 | 4.0 | 6.0 | 5.0 | 2.0 | 4.0 | 4.0 | 20.0 | 24.0 | 15.0 | 27.0 | 11.0 | 10.0 |  |  | 2.29 | 0.6 | 0.0 | 4.0 |
| m_mt_406685247 | 1699110000 | COMPETITION | AWAY | OPP_009 |  |  | 5.0 | 5.0 | 1.0 | 1.0 | 5.0 | 3.0 | 13.0 | 30.0 | 12.0 | 5.0 | 80.0 | 39.0 | 10.0 | 10.0 | 1.0 | 0.0 | 8.0 | 19.0 | 1.1 | 0.55 | 0.0 | 1.0 | 73.0 | 27.0 | 0.0 | 0.0 | 1.0 | 6.0 | 13.0 | 5.0 | 3.0 | 3.0 | 8.0 | 1.0 | 3.0 | 2.0 | 10.0 | 13.0 | 20.0 | 17.0 | 16.0 | 7.0 | 30.0 | 18.0 | 1.1 | 0.53 | 2.0 | 2.0 |
| m_mt_978826968 | 1699714800 | COMPETITION | HOME | OPP_002 | BACK_FOUR | BACK_FOUR | 2.0 | 13.0 | 3.0 | 4.0 | 4.0 | 4.0 | 26.0 | 16.0 | 3.0 | 10.0 | 35.0 | 44.0 | 7.0 | 10.0 | 2.0 | 1.0 | 12.0 | 10.0 | 1.18 | 2.35 | 3.0 | 0.0 | 53.0 | 47.0 | 0.0 | 0.0 | 1.0 | 1.0 | 7.0 | 11.0 | 3.0 | 8.0 | 3.0 | 2.0 | 3.0 | 3.0 | 23.0 | 11.0 | 13.0 | 21.0 | 10.0 | 14.0 |  |  | 1.08 | 2.12 | 3.0 | 0.0 |
| m_mt_624491626 | 1700924400 | COMPETITION | AWAY | OPP_019 |  |  | 3.0 | 8.0 | 3.0 | 1.0 | 8.0 | 5.0 | 13.0 | 26.0 | 7.0 | 2.0 | 72.0 | 47.0 | 11.0 | 5.0 | 1.0 | 1.0 | 8.0 | 7.0 | 1.47 | 0.45 | 1.0 | 3.0 | 78.0 | 22.0 | 0.0 | 0.0 | 1.0 | 3.0 | 13.0 | 8.0 | 4.0 | 3.0 | 4.0 | 2.0 | 3.0 | 2.0 | 12.0 | 13.0 | 13.0 | 9.0 | 16.0 | 10.0 |  |  | 1.47 | 0.45 | 1.0 | 4.0 |
| m_mt_367710380 | 1701287100 | COMPETITION | HOME | OPP_005 |  |  | 4.0 | 7.0 | 0.0 | 2.0 | 4.0 | 4.0 | 12.0 | 20.0 | 6.0 | 3.0 | 79.0 | 51.0 | 11.0 | 14.0 | 1.0 | 0.0 | 9.0 | 10.0 | 0.71 | 0.81 | 2.0 | 3.0 | 67.0 | 33.0 | 0.0 | 0.0 | 1.0 | 4.0 | 9.0 | 6.0 | 5.0 | 3.0 | 5.0 | 1.0 | 5.0 | 2.0 | 10.0 | 25.0 | 14.0 | 15.0 | 14.0 | 8.0 |  |  | 0.71 | 0.81 | 3.0 | 1.0 |
| m_mt_839904809 | 1701529200 | COMPETITION | HOME | OPP_006 |  |  | 3.0 | 2.0 | 4.0 | 2.0 | 5.0 | 5.0 | 9.0 | 15.0 | 7.0 | 3.0 | 66.0 | 32.0 | 6.0 | 9.0 | 2.0 | 0.0 | 10.0 | 17.0 | 2.25 | 0.83 | 2.0 | 1.0 | 64.0 | 36.0 | 0.0 | 0.0 | 2.0 | 4.0 | 11.0 | 4.0 | 7.0 | 2.0 | 6.0 | 3.0 | 7.0 | 6.0 | 20.0 | 23.0 | 22.0 | 17.0 | 18.0 | 10.0 |  |  | 2.5 | 0.83 | 1.0 | 2.0 |
| m_mt_367717182 | 1702134000 | COMPETITION | AWAY | OPP_013 |  |  | 2.0 | 5.0 | 1.0 | 2.0 | 1.0 | 4.0 | 29.0 | 12.0 | 3.0 | 7.0 | 60.0 | 53.0 | 16.0 | 10.0 | 1.0 | 1.0 | 10.0 | 9.0 | 0.8 | 0.53 | 0.0 | 3.0 | 60.0 | 40.0 | 0.0 | 0.0 | 3.0 | 2.0 | 5.0 | 8.0 | 2.0 | 3.0 | 3.0 | 4.0 | 1.0 | 3.0 | 12.0 | 13.0 | 13.0 | 19.0 | 6.0 | 11.0 |  |  | 0.8 | 0.61 | 4.0 | 3.0 |
| m_mt_743353536 | 1702496700 | COMPETITION | AWAY | OPP_003 |  |  | 5.0 | 3.0 | 0.0 | 1.0 | 3.0 | 2.0 | 13.0 | 20.0 | 9.0 | 3.0 | 67.0 | 35.0 | 12.0 | 9.0 | 1.0 | 1.0 | 10.0 | 18.0 | 0.74 | 0.57 | 0.0 | 2.0 | 72.0 | 28.0 | 0.0 | 0.0 | 3.0 | 2.0 | 9.0 | 6.0 | 6.0 | 5.0 | 3.0 | 4.0 | 3.0 | 5.0 | 22.0 | 15.0 | 18.0 | 16.0 | 12.0 | 11.0 |  |  | 0.74 | 0.57 | 3.0 | 1.0 |
| m_mt_012232318 | 1702738800 | COMPETITION | HOME | OPP_014 |  |  | 5.0 | 0.0 | 7.0 | 1.0 | 5.0 | 0.0 | 4.0 | 26.0 | 15.0 | 1.0 | 101.0 | 19.0 | 9.0 | 11.0 | 4.0 | 0.0 | 10.0 | 5.0 | 2.49 | 0.83 | 2.0 | 0.0 | 73.0 | 27.0 | 0.0 | 1.0 | 4.0 | 7.0 | 16.0 | 3.0 | 6.0 | 0.0 | 11.0 | 4.0 | 6.0 | 1.0 | 8.0 | 32.0 | 19.0 | 12.0 | 22.0 | 4.0 |  |  | 3.88 | 0.74 | 3.0 | 4.0 |
| m_mt_581141465 | 1703343600 | COMPETITION | AWAY | OPP_007 |  |  | 3.0 | 2.0 | 2.0 | 0.0 | 8.0 | 4.0 | 17.0 | 17.0 | 5.0 | 7.0 | 37.0 | 25.0 | 12.0 | 8.0 | 1.0 | 0.0 | 9.0 | 8.0 | 1.68 | 0.39 | 3.0 | 5.0 | 61.0 | 39.0 | 1.0 | 0.0 | 2.0 | 3.0 | 12.0 | 4.0 | 2.0 | 6.0 | 4.0 | 2.0 | 2.0 | 8.0 | 15.0 | 21.0 | 24.0 | 14.0 | 14.0 | 12.0 |  |  | 1.66 | 0.39 | 5.0 | 1.0 |
| m_mt_743353973 | 1703602800 | COMPETITION | HOME | OPP_024 |  |  | 2.0 | 1.0 | 3.0 | 2.0 | 2.0 | 1.0 | 3.0 | 22.0 | 3.0 | 1.0 | 45.0 | 25.0 | 15.0 | 13.0 | 5.0 | 0.0 | 9.0 | 14.0 | 2.05 | 0.39 | 0.0 | 1.0 | 60.0 | 40.0 | 0.0 | 0.0 | 1.0 | 4.0 | 8.0 | 4.0 | 0.0 | 2.0 | 9.0 | 1.0 | 3.0 | 0.0 | 18.0 | 17.0 | 16.0 | 17.0 | 11.0 | 4.0 |  |  | 2.05 | 0.39 | 2.0 | 4.0 |
| m_mt_624494356 | 1703872800 | COMPETITION | HOME | OPP_011 |  |  | 10.0 | 3.0 | 4.0 | 0.0 | 10.0 | 3.0 | 10.0 | 32.0 | 9.0 | 3.0 | 87.0 | 24.0 | 8.0 | 8.0 | 2.0 | 1.0 | 7.0 | 7.0 | 2.51 | 0.47 | 4.0 | 3.0 | 78.0 | 22.0 | 0.0 | 0.0 | 0.0 | 7.0 | 16.0 | 4.0 | 9.0 | 4.0 | 7.0 | 1.0 | 10.0 | 4.0 | 15.0 | 16.0 | 18.0 | 16.0 | 26.0 | 8.0 |  |  | 2.98 | 0.47 | 3.0 | 2.0 |
| m_mt_743353902 | 1704121200 | COMPETITION | AWAY | OPP_010 |  |  | 8.0 | 2.0 | 2.0 | 1.0 | 7.0 | 2.0 | 9.0 | 31.0 | 12.0 | 1.0 | 101.0 | 25.0 | 8.0 | 8.0 | 1.0 | 1.0 | 4.0 | 12.0 | 2.5 | 0.83 | 1.0 | 1.0 | 75.0 | 25.0 | 0.0 | 0.0 | 1.0 | 3.0 | 15.0 | 4.0 | 10.0 | 3.0 | 4.0 | 2.0 | 6.0 | 3.0 | 13.0 | 18.0 | 28.0 | 7.0 | 21.0 | 7.0 |  |  | 2.5 | 0.83 | 0.0 | 5.0 |
| m_mt_250070669 | 1705158000 | COMPETITION | HOME | OPP_008 |  |  | 5.0 | 1.0 | 4.0 | 1.0 | 3.0 | 0.0 | 8.0 | 36.0 | 14.0 | 3.0 | 75.0 | 16.0 | 9.0 | 12.0 | 4.0 | 0.0 | 11.0 | 11.0 | 1.86 | 0.6 | 4.0 | 3.0 | 70.0 | 30.0 | 0.0 | 0.0 | 4.0 | 1.0 | 11.0 | 4.0 | 5.0 | 2.0 | 7.0 | 4.0 | 4.0 | 2.0 | 10.0 | 16.0 | 23.0 | 6.0 | 15.0 | 6.0 |  |  | 2.42 | 0.6 | 3.0 | 3.0 |

### Arm B — derived summaries (DERIVED_SUMMARY), HOME 230 + AWAY 232

HOME_TEAM (metric·side·window·venue = value [n, reliability]):

- accurate_crosses·FOR·ALL_PRIOR·ALL = 4.3704 [n=27, HIGH]
- accurate_crosses·FOR·W5·ALL = 4.6 [n=5, LOW]
- accurate_crosses·FOR·W10·ALL = 5.2 [n=10, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·HOME = 5.0769 [n=13, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·AWAY = 3.7143 [n=14, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·ALL = 4.9259 [n=27, HIGH]
- accurate_crosses·AGAINST·W5·ALL = 5.2 [n=5, LOW]
- accurate_crosses·AGAINST·W10·ALL = 4.2 [n=10, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·HOME = 5.0769 [n=13, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·AWAY = 4.7857 [n=14, MEDIUM]
- big_chances·FOR·ALL_PRIOR·ALL = 1.7778 [n=27, HIGH]
- big_chances·FOR·W5·ALL = 1.2 [n=5, LOW]
- big_chances·FOR·W10·ALL = 1.7 [n=10, MEDIUM]
- big_chances·FOR·ALL_PRIOR·HOME = 1.8462 [n=13, MEDIUM]
- big_chances·FOR·ALL_PRIOR·AWAY = 1.7143 [n=14, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·ALL = 2.0 [n=27, HIGH]
- big_chances·AGAINST·W5·ALL = 1.6 [n=5, LOW]
- big_chances·AGAINST·W10·ALL = 1.8 [n=10, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·HOME = 1.2308 [n=13, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·AWAY = 2.7143 [n=14, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·ALL = 2.963 [n=27, HIGH]
- blocked_shots·FOR·W5·ALL = 1.6 [n=5, LOW]
- blocked_shots·FOR·W10·ALL = 2.9 [n=10, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·HOME = 3.2308 [n=13, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·AWAY = 2.7143 [n=14, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·ALL = 4.037 [n=27, HIGH]
- blocked_shots·AGAINST·W5·ALL = 3.4 [n=5, LOW]
- blocked_shots·AGAINST·W10·ALL = 3.3 [n=10, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·HOME = 3.6154 [n=13, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·AWAY = 4.4286 [n=14, MEDIUM]
- clearances·FOR·ALL_PRIOR·ALL = 18.4815 [n=27, HIGH]
- clearances·FOR·W5·ALL = 19.4 [n=5, LOW]
- clearances·FOR·W10·ALL = 19.2 [n=10, MEDIUM]
- clearances·FOR·ALL_PRIOR·HOME = 16.8462 [n=13, MEDIUM]
- clearances·FOR·ALL_PRIOR·AWAY = 20.0 [n=14, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·ALL = 15.4815 [n=27, HIGH]
- clearances·AGAINST·W5·ALL = 14.8 [n=5, LOW]
- clearances·AGAINST·W10·ALL = 17.9 [n=10, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·HOME = 15.6923 [n=13, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·AWAY = 15.2857 [n=14, MEDIUM]
- corners·FOR·ALL_PRIOR·ALL = 4.7407 [n=27, HIGH]
- corners·FOR·W5·ALL = 3.4 [n=5, LOW]
- corners·FOR·W10·ALL = 5.9 [n=10, MEDIUM]
- corners·FOR·ALL_PRIOR·HOME = 5.0 [n=13, MEDIUM]
- corners·FOR·ALL_PRIOR·AWAY = 4.5 [n=14, MEDIUM]
- corners·AGAINST·ALL_PRIOR·ALL = 5.3704 [n=27, HIGH]
- corners·AGAINST·W5·ALL = 5.6 [n=5, LOW]
- corners·AGAINST·W10·ALL = 5.1 [n=10, MEDIUM]
- corners·AGAINST·ALL_PRIOR·HOME = 4.7692 [n=13, MEDIUM]
- corners·AGAINST·ALL_PRIOR·AWAY = 5.9286 [n=14, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·ALL = 58.2222 [n=27, HIGH]
- final_third_entries·FOR·W5·ALL = 54.2 [n=5, LOW]
- final_third_entries·FOR·W10·ALL = 57.7 [n=10, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·HOME = 58.6923 [n=13, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·AWAY = 57.7857 [n=14, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·ALL = 56.7037 [n=27, HIGH]
- final_third_entries·AGAINST·W5·ALL = 52.2 [n=5, LOW]
- final_third_entries·AGAINST·W10·ALL = 49.5 [n=10, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·HOME = 56.3846 [n=13, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·AWAY = 57.0 [n=14, MEDIUM]
- fouls·FOR·ALL_PRIOR·ALL = 10.7407 [n=27, HIGH]
- fouls·FOR·W5·ALL = 11.0 [n=5, LOW]
- fouls·FOR·W10·ALL = 11.4 [n=10, MEDIUM]
- fouls·FOR·ALL_PRIOR·HOME = 11.1538 [n=13, MEDIUM]
- fouls·FOR·ALL_PRIOR·AWAY = 10.3571 [n=14, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·ALL = 12.4074 [n=27, HIGH]
- fouls·AGAINST·W5·ALL = 13.0 [n=5, LOW]
- fouls·AGAINST·W10·ALL = 12.0 [n=10, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·HOME = 11.3077 [n=13, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·AWAY = 13.4286 [n=14, MEDIUM]
- goals·FOR·ALL_PRIOR·ALL = 1.3704 [n=27, HIGH]
- goals·FOR·W5·ALL = 1.4 [n=5, LOW]
- goals·FOR·W10·ALL = 1.3 [n=10, MEDIUM]
- goals·FOR·ALL_PRIOR·HOME = 1.2308 [n=13, MEDIUM]
- goals·FOR·ALL_PRIOR·AWAY = 1.5 [n=14, MEDIUM]
- goals·AGAINST·ALL_PRIOR·ALL = 1.5185 [n=27, HIGH]
- goals·AGAINST·W5·ALL = 2.0 [n=5, LOW]
- goals·AGAINST·W10·ALL = 1.8 [n=10, MEDIUM]
- goals·AGAINST·ALL_PRIOR·HOME = 1.1538 [n=13, MEDIUM]
- goals·AGAINST·ALL_PRIOR·AWAY = 1.8571 [n=14, MEDIUM]
- interceptions·FOR·ALL_PRIOR·ALL = 10.5926 [n=27, HIGH]
- interceptions·FOR·W5·ALL = 10.4 [n=5, LOW]
- interceptions·FOR·W10·ALL = 9.6 [n=10, MEDIUM]
- interceptions·FOR·ALL_PRIOR·HOME = 10.0769 [n=13, MEDIUM]
- interceptions·FOR·ALL_PRIOR·AWAY = 11.0714 [n=14, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·ALL = 8.7037 [n=27, HIGH]
- interceptions·AGAINST·W5·ALL = 8.2 [n=5, LOW]
- interceptions·AGAINST·W10·ALL = 8.8 [n=10, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·HOME = 7.4615 [n=13, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·AWAY = 9.8571 [n=14, MEDIUM]
- npxg·FOR·ALL_PRIOR·ALL = 1.0163 [n=24, HIGH]
- npxg·FOR·W5·ALL = 0.4533 [n=3, LOW]
- npxg·FOR·W10·ALL = 0.7987 [n=8, MEDIUM]
- npxg·FOR·ALL_PRIOR·HOME = 1.1133 [n=12, MEDIUM]
- npxg·FOR·ALL_PRIOR·AWAY = 0.9192 [n=12, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·ALL = 1.3871 [n=24, HIGH]
- npxg·AGAINST·W5·ALL = 1.4467 [n=3, LOW]
- npxg·AGAINST·W10·ALL = 1.3337 [n=8, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·HOME = 1.26 [n=12, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·AWAY = 1.5142 [n=12, MEDIUM]
- offsides·FOR·ALL_PRIOR·ALL = 1.8519 [n=27, HIGH]
- offsides·FOR·W5·ALL = 1.8 [n=5, LOW]
- offsides·FOR·W10·ALL = 1.9 [n=10, MEDIUM]
- offsides·FOR·ALL_PRIOR·HOME = 2.0769 [n=13, MEDIUM]
- offsides·FOR·ALL_PRIOR·AWAY = 1.6429 [n=14, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·ALL = 2.4815 [n=27, HIGH]
- offsides·AGAINST·W5·ALL = 1.8 [n=5, LOW]
- offsides·AGAINST·W10·ALL = 2.1 [n=10, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·HOME = 1.9231 [n=13, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·AWAY = 3.0 [n=14, MEDIUM]
- possession·FOR·ALL_PRIOR·ALL = 53.1852 [n=27, HIGH]
- possession·FOR·W5·ALL = 49.6 [n=5, LOW]
- possession·FOR·W10·ALL = 55.9 [n=10, MEDIUM]
- possession·FOR·ALL_PRIOR·HOME = 53.2308 [n=13, MEDIUM]
- possession·FOR·ALL_PRIOR·AWAY = 53.1429 [n=14, MEDIUM]
- possession·AGAINST·ALL_PRIOR·ALL = 46.8148 [n=27, HIGH]
- possession·AGAINST·W5·ALL = 50.4 [n=5, LOW]
- possession·AGAINST·W10·ALL = 44.1 [n=10, MEDIUM]
- possession·AGAINST·ALL_PRIOR·HOME = 46.7692 [n=13, MEDIUM]
- possession·AGAINST·ALL_PRIOR·AWAY = 46.8571 [n=14, MEDIUM]
- red_cards·FOR·ALL_PRIOR·ALL = 0.1111 [n=27, HIGH]
- red_cards·FOR·W5·ALL = 0.0 [n=5, LOW]
- red_cards·FOR·W10·ALL = 0.0 [n=10, MEDIUM]
- red_cards·FOR·ALL_PRIOR·HOME = 0.0769 [n=13, MEDIUM]
- red_cards·FOR·ALL_PRIOR·AWAY = 0.1429 [n=14, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·ALL = 0.037 [n=27, HIGH]
- red_cards·AGAINST·W5·ALL = 0.0 [n=5, LOW]
- red_cards·AGAINST·W10·ALL = 0.1 [n=10, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·HOME = 0.0 [n=13, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·AWAY = 0.0714 [n=14, MEDIUM]
- saves·FOR·ALL_PRIOR·ALL = 3.4444 [n=27, HIGH]
- saves·FOR·W5·ALL = 3.8 [n=5, LOW]
- saves·FOR·W10·ALL = 3.4 [n=10, MEDIUM]
- saves·FOR·ALL_PRIOR·HOME = 3.2308 [n=13, MEDIUM]
- saves·FOR·ALL_PRIOR·AWAY = 3.6429 [n=14, MEDIUM]
- saves·AGAINST·ALL_PRIOR·ALL = 2.3704 [n=27, HIGH]
- saves·AGAINST·W5·ALL = 1.8 [n=5, LOW]
- saves·AGAINST·W10·ALL = 2.4 [n=10, MEDIUM]
- saves·AGAINST·ALL_PRIOR·HOME = 2.6923 [n=13, MEDIUM]
- saves·AGAINST·ALL_PRIOR·AWAY = 2.0714 [n=14, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·ALL = 7.1852 [n=27, HIGH]
- shots_inside_box·FOR·W5·ALL = 6.6 [n=5, LOW]
- shots_inside_box·FOR·W10·ALL = 7.4 [n=10, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·HOME = 7.8462 [n=13, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·AWAY = 6.5714 [n=14, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·ALL = 9.5185 [n=27, HIGH]
- shots_inside_box·AGAINST·W5·ALL = 9.2 [n=5, LOW]
- shots_inside_box·AGAINST·W10·ALL = 8.7 [n=10, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·HOME = 8.7692 [n=13, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·AWAY = 10.2143 [n=14, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·ALL = 4.1852 [n=27, HIGH]
- shots_off_target·FOR·W5·ALL = 3.6 [n=5, LOW]
- shots_off_target·FOR·W10·ALL = 4.5 [n=10, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·HOME = 4.6154 [n=13, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·AWAY = 3.7857 [n=14, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·ALL = 4.963 [n=27, HIGH]
- shots_off_target·AGAINST·W5·ALL = 3.2 [n=5, LOW]
- shots_off_target·AGAINST·W10·ALL = 3.3 [n=10, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·HOME = 4.9231 [n=13, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·AWAY = 5.0 [n=14, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·ALL = 3.8519 [n=27, HIGH]
- shots_on_target·FOR·W5·ALL = 3.2 [n=5, LOW]
- shots_on_target·FOR·W10·ALL = 3.7 [n=10, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·HOME = 4.0769 [n=13, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·AWAY = 3.6429 [n=14, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·ALL = 5.0 [n=27, HIGH]
- shots_on_target·AGAINST·W5·ALL = 5.8 [n=5, LOW]
- shots_on_target·AGAINST·W10·ALL = 5.1 [n=10, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·HOME = 4.3846 [n=13, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·AWAY = 5.5714 [n=14, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·ALL = 3.8148 [n=27, HIGH]
- shots_outside_box·FOR·W5·ALL = 1.8 [n=5, LOW]
- shots_outside_box·FOR·W10·ALL = 3.7 [n=10, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·HOME = 4.0769 [n=13, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·AWAY = 3.5714 [n=14, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·ALL = 4.4815 [n=27, HIGH]
- shots_outside_box·AGAINST·W5·ALL = 3.2 [n=5, LOW]
- shots_outside_box·AGAINST·W10·ALL = 3.0 [n=10, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·HOME = 4.1538 [n=13, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·AWAY = 4.7857 [n=14, MEDIUM]
- tackles·FOR·ALL_PRIOR·ALL = 15.6667 [n=27, HIGH]
- tackles·FOR·W5·ALL = 17.0 [n=5, LOW]
- tackles·FOR·W10·ALL = 15.5 [n=10, MEDIUM]
- tackles·FOR·ALL_PRIOR·HOME = 16.0769 [n=13, MEDIUM]
- tackles·FOR·ALL_PRIOR·AWAY = 15.2857 [n=14, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·ALL = 14.6667 [n=27, HIGH]
- tackles·AGAINST·W5·ALL = 14.8 [n=5, LOW]
- tackles·AGAINST·W10·ALL = 15.4 [n=10, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·HOME = 15.0769 [n=13, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·AWAY = 14.2857 [n=14, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·ALL = 22.8148 [n=27, HIGH]
- throw_ins·FOR·W5·ALL = 20.4 [n=5, LOW]
- throw_ins·FOR·W10·ALL = 22.4 [n=10, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·HOME = 23.5385 [n=13, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·AWAY = 22.1429 [n=14, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·ALL = 23.0741 [n=27, HIGH]
- throw_ins·AGAINST·W5·ALL = 22.8 [n=5, LOW]
- throw_ins·AGAINST·W10·ALL = 21.5 [n=10, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·HOME = 21.9231 [n=13, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·AWAY = 24.1429 [n=14, MEDIUM]
- total_shots·FOR·ALL_PRIOR·ALL = 11.0 [n=27, HIGH]
- total_shots·FOR·W5·ALL = 8.4 [n=5, LOW]
- total_shots·FOR·W10·ALL = 11.1 [n=10, MEDIUM]
- total_shots·FOR·ALL_PRIOR·HOME = 11.9231 [n=13, MEDIUM]
- total_shots·FOR·ALL_PRIOR·AWAY = 10.1429 [n=14, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·ALL = 14.0 [n=27, HIGH]
- total_shots·AGAINST·W5·ALL = 12.4 [n=5, LOW]
- total_shots·AGAINST·W10·ALL = 11.7 [n=10, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·HOME = 12.9231 [n=13, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·AWAY = 15.0 [n=14, MEDIUM]
- xg·FOR·ALL_PRIOR·ALL = 1.1537 [n=27, HIGH]
- xg·FOR·W5·ALL = 0.754 [n=5, LOW]
- xg·FOR·W10·ALL = 0.977 [n=10, MEDIUM]
- xg·FOR·ALL_PRIOR·HOME = 1.2354 [n=13, MEDIUM]
- xg·FOR·ALL_PRIOR·AWAY = 1.0779 [n=14, MEDIUM]
- xg·AGAINST·ALL_PRIOR·ALL = 1.5763 [n=27, HIGH]
- xg·AGAINST·W5·ALL = 1.704 [n=5, LOW]
- xg·AGAINST·W10·ALL = 1.561 [n=10, MEDIUM]
- xg·AGAINST·ALL_PRIOR·HOME = 1.3192 [n=13, MEDIUM]
- xg·AGAINST·ALL_PRIOR·AWAY = 1.815 [n=14, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·ALL = 2.2593 [n=27, HIGH]
- yellow_cards·FOR·W5·ALL = 3.4 [n=5, LOW]
- yellow_cards·FOR·W10·ALL = 2.6 [n=10, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·HOME = 2.0769 [n=13, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·AWAY = 2.4286 [n=14, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·ALL = 2.3333 [n=27, HIGH]
- yellow_cards·AGAINST·W5·ALL = 2.2 [n=5, LOW]
- yellow_cards·AGAINST·W10·ALL = 2.3 [n=10, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·HOME = 2.3077 [n=13, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·AWAY = 2.3571 [n=14, MEDIUM]

AWAY_TEAM:

- accurate_crosses·FOR·ALL_PRIOR·ALL = 4.7778 [n=27, HIGH]
- accurate_crosses·FOR·W5·ALL = 5.6 [n=5, LOW]
- accurate_crosses·FOR·W10·ALL = 4.7 [n=10, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·HOME = 4.7857 [n=14, MEDIUM]
- accurate_crosses·FOR·ALL_PRIOR·AWAY = 4.7692 [n=13, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·ALL = 3.5556 [n=27, HIGH]
- accurate_crosses·AGAINST·W5·ALL = 1.8 [n=5, LOW]
- accurate_crosses·AGAINST·W10·ALL = 2.6 [n=10, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·HOME = 3.2857 [n=14, MEDIUM]
- accurate_crosses·AGAINST·ALL_PRIOR·AWAY = 3.8462 [n=13, MEDIUM]
- big_chances·FOR·ALL_PRIOR·ALL = 2.5769 [n=26, HIGH]
- big_chances·FOR·W5·ALL = 3.0 [n=5, LOW]
- big_chances·FOR·W10·ALL = 2.7 [n=10, MEDIUM]
- big_chances·FOR·ALL_PRIOR·HOME = 3.5385 [n=13, MEDIUM]
- big_chances·FOR·ALL_PRIOR·AWAY = 1.6154 [n=13, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·ALL = 1.8077 [n=26, HIGH]
- big_chances·AGAINST·W5·ALL = 0.8 [n=5, LOW]
- big_chances·AGAINST·W10·ALL = 1.2 [n=10, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·HOME = 2.1538 [n=13, MEDIUM]
- big_chances·AGAINST·ALL_PRIOR·AWAY = 1.4615 [n=13, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·ALL = 4.8889 [n=27, HIGH]
- blocked_shots·FOR·W5·ALL = 6.0 [n=5, LOW]
- blocked_shots·FOR·W10·ALL = 4.8 [n=10, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·HOME = 4.8571 [n=14, MEDIUM]
- blocked_shots·FOR·ALL_PRIOR·AWAY = 4.9231 [n=13, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·ALL = 3.4815 [n=27, HIGH]
- blocked_shots·AGAINST·W5·ALL = 2.0 [n=5, LOW]
- blocked_shots·AGAINST·W10·ALL = 2.5 [n=10, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·HOME = 2.7857 [n=14, MEDIUM]
- blocked_shots·AGAINST·ALL_PRIOR·AWAY = 4.2308 [n=13, MEDIUM]
- clearances·FOR·ALL_PRIOR·ALL = 14.3333 [n=27, HIGH]
- clearances·FOR·W5·ALL = 9.4 [n=5, LOW]
- clearances·FOR·W10·ALL = 11.4 [n=10, MEDIUM]
- clearances·FOR·ALL_PRIOR·HOME = 11.5 [n=14, MEDIUM]
- clearances·FOR·ALL_PRIOR·AWAY = 17.3846 [n=13, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·ALL = 21.7407 [n=27, HIGH]
- clearances·AGAINST·W5·ALL = 27.6 [n=5, LOW]
- clearances·AGAINST·W10·ALL = 23.1 [n=10, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·HOME = 22.7143 [n=14, MEDIUM]
- clearances·AGAINST·ALL_PRIOR·AWAY = 20.6923 [n=13, MEDIUM]
- corners·FOR·ALL_PRIOR·ALL = 7.7037 [n=27, HIGH]
- corners·FOR·W5·ALL = 8.6 [n=5, LOW]
- corners·FOR·W10·ALL = 8.3 [n=10, MEDIUM]
- corners·FOR·ALL_PRIOR·HOME = 8.0 [n=14, MEDIUM]
- corners·FOR·ALL_PRIOR·AWAY = 7.3846 [n=13, MEDIUM]
- corners·AGAINST·ALL_PRIOR·ALL = 4.2963 [n=27, HIGH]
- corners·AGAINST·W5·ALL = 3.0 [n=5, LOW]
- corners·AGAINST·W10·ALL = 3.2 [n=10, MEDIUM]
- corners·AGAINST·ALL_PRIOR·HOME = 3.6429 [n=14, MEDIUM]
- corners·AGAINST·ALL_PRIOR·AWAY = 5.0 [n=13, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·ALL = 64.3704 [n=27, HIGH]
- final_third_entries·FOR·W5·ALL = 69.0 [n=5, LOW]
- final_third_entries·FOR·W10·ALL = 71.8 [n=10, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·HOME = 66.2857 [n=14, MEDIUM]
- final_third_entries·FOR·ALL_PRIOR·AWAY = 62.3077 [n=13, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·ALL = 38.6667 [n=27, HIGH]
- final_third_entries·AGAINST·W5·ALL = 23.0 [n=5, LOW]
- final_third_entries·AGAINST·W10·ALL = 30.5 [n=10, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·HOME = 35.0714 [n=14, MEDIUM]
- final_third_entries·AGAINST·ALL_PRIOR·AWAY = 42.5385 [n=13, MEDIUM]
- fouls·FOR·ALL_PRIOR·ALL = 10.1852 [n=27, HIGH]
- fouls·FOR·W5·ALL = 10.4 [n=5, LOW]
- fouls·FOR·W10·ALL = 10.6 [n=10, MEDIUM]
- fouls·FOR·ALL_PRIOR·HOME = 9.6429 [n=14, MEDIUM]
- fouls·FOR·ALL_PRIOR·AWAY = 10.7692 [n=13, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·ALL = 11.9259 [n=27, HIGH]
- fouls·AGAINST·W5·ALL = 9.8 [n=5, LOW]
- fouls·AGAINST·W10·ALL = 10.2 [n=10, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·HOME = 11.9286 [n=14, MEDIUM]
- fouls·AGAINST·ALL_PRIOR·AWAY = 11.9231 [n=13, MEDIUM]
- goals·FOR·ALL_PRIOR·ALL = 1.8519 [n=27, HIGH]
- goals·FOR·W5·ALL = 2.6 [n=5, LOW]
- goals·FOR·W10·ALL = 2.2 [n=10, MEDIUM]
- goals·FOR·ALL_PRIOR·HOME = 2.4286 [n=14, MEDIUM]
- goals·FOR·ALL_PRIOR·AWAY = 1.2308 [n=13, MEDIUM]
- goals·AGAINST·ALL_PRIOR·ALL = 1.1481 [n=27, HIGH]
- goals·AGAINST·W5·ALL = 0.4 [n=5, LOW]
- goals·AGAINST·W10·ALL = 0.4 [n=10, MEDIUM]
- goals·AGAINST·ALL_PRIOR·HOME = 1.0714 [n=14, MEDIUM]
- goals·AGAINST·ALL_PRIOR·AWAY = 1.2308 [n=13, MEDIUM]
- interceptions·FOR·ALL_PRIOR·ALL = 8.8148 [n=27, HIGH]
- interceptions·FOR·W5·ALL = 8.0 [n=5, LOW]
- interceptions·FOR·W10·ALL = 8.9 [n=10, MEDIUM]
- interceptions·FOR·ALL_PRIOR·HOME = 8.9286 [n=14, MEDIUM]
- interceptions·FOR·ALL_PRIOR·AWAY = 8.6923 [n=13, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·ALL = 10.5556 [n=27, HIGH]
- interceptions·AGAINST·W5·ALL = 10.4 [n=5, LOW]
- interceptions·AGAINST·W10·ALL = 11.1 [n=10, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·HOME = 10.2857 [n=14, MEDIUM]
- interceptions·AGAINST·ALL_PRIOR·AWAY = 10.8462 [n=13, MEDIUM]
- npxg·FOR·ALL_PRIOR·ALL = 1.582 [n=25, HIGH]
- npxg·FOR·W5·ALL = 2.12 [n=5, LOW]
- npxg·FOR·W10·ALL = 1.759 [n=10, MEDIUM]
- npxg·FOR·ALL_PRIOR·HOME = 1.8171 [n=14, MEDIUM]
- npxg·FOR·ALL_PRIOR·AWAY = 1.2827 [n=11, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·ALL = 0.9756 [n=25, HIGH]
- npxg·AGAINST·W5·ALL = 0.536 [n=5, LOW]
- npxg·AGAINST·W10·ALL = 0.625 [n=10, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·HOME = 1.1036 [n=14, MEDIUM]
- npxg·AGAINST·ALL_PRIOR·AWAY = 0.8127 [n=11, MEDIUM]
- offsides·FOR·ALL_PRIOR·ALL = 1.5926 [n=27, HIGH]
- offsides·FOR·W5·ALL = 2.4 [n=5, LOW]
- offsides·FOR·W10·ALL = 1.8 [n=10, MEDIUM]
- offsides·FOR·ALL_PRIOR·HOME = 2.0714 [n=14, MEDIUM]
- offsides·FOR·ALL_PRIOR·AWAY = 1.0769 [n=13, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·ALL = 2.1481 [n=27, HIGH]
- offsides·AGAINST·W5·ALL = 2.6 [n=5, LOW]
- offsides·AGAINST·W10·ALL = 2.2 [n=10, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·HOME = 1.9286 [n=14, MEDIUM]
- offsides·AGAINST·ALL_PRIOR·AWAY = 2.3846 [n=13, MEDIUM]
- possession·FOR·ALL_PRIOR·ALL = 66.1111 [n=27, HIGH]
- possession·FOR·W5·ALL = 68.8 [n=5, LOW]
- possession·FOR·W10·ALL = 68.0 [n=10, MEDIUM]
- possession·FOR·ALL_PRIOR·HOME = 65.7857 [n=14, MEDIUM]
- possession·FOR·ALL_PRIOR·AWAY = 66.4615 [n=13, MEDIUM]
- possession·AGAINST·ALL_PRIOR·ALL = 33.8889 [n=27, HIGH]
- possession·AGAINST·W5·ALL = 31.2 [n=5, LOW]
- possession·AGAINST·W10·ALL = 32.0 [n=10, MEDIUM]
- possession·AGAINST·ALL_PRIOR·HOME = 34.2143 [n=14, MEDIUM]
- possession·AGAINST·ALL_PRIOR·AWAY = 33.5385 [n=13, MEDIUM]
- red_cards·FOR·ALL_PRIOR·ALL = 0.0741 [n=27, HIGH]
- red_cards·FOR·W5·ALL = 0.2 [n=5, LOW]
- red_cards·FOR·W10·ALL = 0.1 [n=10, MEDIUM]
- red_cards·FOR·ALL_PRIOR·HOME = 0.0714 [n=14, MEDIUM]
- red_cards·FOR·ALL_PRIOR·AWAY = 0.0769 [n=13, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·ALL = 0.037 [n=27, HIGH]
- red_cards·AGAINST·W5·ALL = 0.0 [n=5, LOW]
- red_cards·AGAINST·W10·ALL = 0.1 [n=10, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·HOME = 0.0714 [n=14, MEDIUM]
- red_cards·AGAINST·ALL_PRIOR·AWAY = 0.0 [n=13, MEDIUM]
- saves·FOR·ALL_PRIOR·ALL = 2.1852 [n=27, HIGH]
- saves·FOR·W5·ALL = 1.6 [n=5, LOW]
- saves·FOR·W10·ALL = 2.1 [n=10, MEDIUM]
- saves·FOR·ALL_PRIOR·HOME = 2.2143 [n=14, MEDIUM]
- saves·FOR·ALL_PRIOR·AWAY = 2.1538 [n=13, MEDIUM]
- saves·AGAINST·ALL_PRIOR·ALL = 3.8148 [n=27, HIGH]
- saves·AGAINST·W5·ALL = 3.6 [n=5, LOW]
- saves·AGAINST·W10·ALL = 3.7 [n=10, MEDIUM]
- saves·AGAINST·ALL_PRIOR·HOME = 4.0 [n=14, MEDIUM]
- saves·AGAINST·ALL_PRIOR·AWAY = 3.6154 [n=13, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·ALL = 10.3704 [n=27, HIGH]
- shots_inside_box·FOR·W5·ALL = 12.4 [n=5, LOW]
- shots_inside_box·FOR·W10·ALL = 11.2 [n=10, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·HOME = 10.4286 [n=14, MEDIUM]
- shots_inside_box·FOR·ALL_PRIOR·AWAY = 10.3077 [n=13, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·ALL = 6.8148 [n=27, HIGH]
- shots_inside_box·AGAINST·W5·ALL = 4.0 [n=5, LOW]
- shots_inside_box·AGAINST·W10·ALL = 4.7 [n=10, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·HOME = 6.5 [n=14, MEDIUM]
- shots_inside_box·AGAINST·ALL_PRIOR·AWAY = 7.1538 [n=13, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·ALL = 5.037 [n=27, HIGH]
- shots_off_target·FOR·W5·ALL = 5.2 [n=5, LOW]
- shots_off_target·FOR·W10·ALL = 5.2 [n=10, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·HOME = 4.8571 [n=14, MEDIUM]
- shots_off_target·FOR·ALL_PRIOR·AWAY = 5.2308 [n=13, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·ALL = 3.8148 [n=27, HIGH]
- shots_off_target·AGAINST·W5·ALL = 3.4 [n=5, LOW]
- shots_off_target·AGAINST·W10·ALL = 3.0 [n=10, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·HOME = 3.5 [n=14, MEDIUM]
- shots_off_target·AGAINST·ALL_PRIOR·AWAY = 4.1538 [n=13, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·ALL = 5.7778 [n=27, HIGH]
- shots_on_target·FOR·W5·ALL = 6.2 [n=5, LOW]
- shots_on_target·FOR·W10·ALL = 5.9 [n=10, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·HOME = 6.6429 [n=14, MEDIUM]
- shots_on_target·FOR·ALL_PRIOR·AWAY = 4.8462 [n=13, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·ALL = 3.3333 [n=27, HIGH]
- shots_on_target·AGAINST·W5·ALL = 2.0 [n=5, LOW]
- shots_on_target·AGAINST·W10·ALL = 2.6 [n=10, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·HOME = 3.3571 [n=14, MEDIUM]
- shots_on_target·AGAINST·ALL_PRIOR·AWAY = 3.3077 [n=13, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·ALL = 5.3333 [n=27, HIGH]
- shots_outside_box·FOR·W5·ALL = 5.0 [n=5, LOW]
- shots_outside_box·FOR·W10·ALL = 4.7 [n=10, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·HOME = 5.9286 [n=14, MEDIUM]
- shots_outside_box·FOR·ALL_PRIOR·AWAY = 4.6923 [n=13, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·ALL = 3.8148 [n=27, HIGH]
- shots_outside_box·AGAINST·W5·ALL = 3.4 [n=5, LOW]
- shots_outside_box·AGAINST·W10·ALL = 3.4 [n=10, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·HOME = 3.1429 [n=14, MEDIUM]
- shots_outside_box·AGAINST·ALL_PRIOR·AWAY = 4.5385 [n=13, MEDIUM]
- tackles·FOR·ALL_PRIOR·ALL = 14.5926 [n=27, HIGH]
- tackles·FOR·W5·ALL = 14.2 [n=5, LOW]
- tackles·FOR·W10·ALL = 14.3 [n=10, MEDIUM]
- tackles·FOR·ALL_PRIOR·HOME = 14.9286 [n=14, MEDIUM]
- tackles·FOR·ALL_PRIOR·AWAY = 14.2308 [n=13, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·ALL = 18.6667 [n=27, HIGH]
- tackles·AGAINST·W5·ALL = 17.6 [n=5, LOW]
- tackles·AGAINST·W10·ALL = 19.6 [n=10, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·HOME = 19.5714 [n=14, MEDIUM]
- tackles·AGAINST·ALL_PRIOR·AWAY = 17.6923 [n=13, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·ALL = 19.0741 [n=27, HIGH]
- throw_ins·FOR·W5·ALL = 21.8 [n=5, LOW]
- throw_ins·FOR·W10·ALL = 19.5 [n=10, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·HOME = 19.5714 [n=14, MEDIUM]
- throw_ins·FOR·ALL_PRIOR·AWAY = 18.5385 [n=13, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·ALL = 16.1111 [n=27, HIGH]
- throw_ins·AGAINST·W5·ALL = 12.0 [n=5, LOW]
- throw_ins·AGAINST·W10·ALL = 13.9 [n=10, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·HOME = 17.1429 [n=14, MEDIUM]
- throw_ins·AGAINST·ALL_PRIOR·AWAY = 15.0 [n=13, MEDIUM]
- total_shots·FOR·ALL_PRIOR·ALL = 15.7037 [n=27, HIGH]
- total_shots·FOR·W5·ALL = 17.4 [n=5, LOW]
- total_shots·FOR·W10·ALL = 15.9 [n=10, MEDIUM]
- total_shots·FOR·ALL_PRIOR·HOME = 16.3571 [n=14, MEDIUM]
- total_shots·FOR·ALL_PRIOR·AWAY = 15.0 [n=13, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·ALL = 10.6296 [n=27, HIGH]
- total_shots·AGAINST·W5·ALL = 7.4 [n=5, LOW]
- total_shots·AGAINST·W10·ALL = 8.1 [n=10, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·HOME = 9.6429 [n=14, MEDIUM]
- total_shots·AGAINST·ALL_PRIOR·AWAY = 11.6923 [n=13, MEDIUM]
- touches_in_box·FOR·ALL_PRIOR·ALL = 30.0 [n=1, LOW]
- touches_in_box·AGAINST·ALL_PRIOR·ALL = 18.0 [n=1, LOW]
- xg·FOR·ALL_PRIOR·ALL = 1.7252 [n=27, HIGH]
- xg·FOR·W5·ALL = 2.322 [n=5, LOW]
- xg·FOR·W10·ALL = 2.024 [n=10, MEDIUM]
- xg·FOR·ALL_PRIOR·HOME = 2.0857 [n=14, MEDIUM]
- xg·FOR·ALL_PRIOR·AWAY = 1.3369 [n=13, MEDIUM]
- xg·AGAINST·ALL_PRIOR·ALL = 1.0459 [n=27, HIGH]
- xg·AGAINST·W5·ALL = 0.536 [n=5, LOW]
- xg·AGAINST·W10·ALL = 0.624 [n=10, MEDIUM]
- xg·AGAINST·ALL_PRIOR·HOME = 1.0807 [n=14, MEDIUM]
- xg·AGAINST·ALL_PRIOR·AWAY = 1.0085 [n=13, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·ALL = 2.6667 [n=27, HIGH]
- yellow_cards·FOR·W5·ALL = 2.6 [n=5, LOW]
- yellow_cards·FOR·W10·ALL = 2.7 [n=10, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·HOME = 2.7857 [n=14, MEDIUM]
- yellow_cards·FOR·ALL_PRIOR·AWAY = 2.5385 [n=13, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·ALL = 2.963 [n=27, HIGH]
- yellow_cards·AGAINST·W5·ALL = 3.0 [n=5, LOW]
- yellow_cards·AGAINST·W10·ALL = 2.6 [n=10, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·HOME = 2.8571 [n=14, MEDIUM]
- yellow_cards·AGAINST·ALL_PRIOR·AWAY = 3.0769 [n=13, MEDIUM]

### Arm B — opponent-profile context (deterministic bands)

```json
{
 "axes": {
  "accurate_crosses_for": {
   "AWAY": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   },
   "HOME": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  },
  "corners_against": {
   "AWAY": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "corners_for": {
   "AWAY": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   },
   "HOME": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  },
  "goals_against": {
   "AWAY": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "goals_for": {
   "AWAY": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  },
  "possession_for": {
   "AWAY": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   },
   "HOME": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  },
  "shots_on_target_against": {
   "AWAY": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   },
   "HOME": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "LOW"
   }
  },
  "shots_on_target_for": {
   "AWAY": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "MID"
   },
   "HOME": {
    "bandable_n": 24,
    "candidate_n": 24,
    "coverage_rate": 1.0,
    "status": "AVAILABLE",
    "upcoming_opponent_band": "HIGH"
   }
  }
 },
 "similarity_version": "opponent_similarity_v1_pending"
}
```

---

## Byte-level exports

- Arm B exact request (system + user bytes): `research/hypothesis_oos/out/v5a/BYTELEVEL_ARM_B_mt_010244159.request.txt` (user sha256 `4ab13ca1ce8cc4d1acaadff11b98b19c3edddd9d9913a1a92131068a28c1a054`)
- Arm A exact request: `research/hypothesis_oos/out/v5a/BYTELEVEL_ARM_A_mt_010244159.request.txt` (user sha256 `80d7fefec65892831d8a8e95b6c4d190b0da64ee7d5ced065ead930951cb0e64`)
