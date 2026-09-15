# V3 Evidence — Human-Readable Fixture Audit

Companion to `V3_EVIDENCE_FORENSIC_AUDIT.md`. ZERO-SPEND, read-only. For each of the 11 clean reference fixtures: the upstream historical data available, the exact evidence Sonnet saw, ALL accepted raw hypotheses (listed in full, unranked, NOT filtered by V4 outcomes), their compiled interpretation, and the important upstream information Sonnet did NOT see.

A human football analyst should be able to read each fixture and judge: *given what Sonnet actually saw, were these sensible questions?* and *what better questions might richer exposed data have enabled?* (Better questions are NOT generated here — no LLM was called.)

---

## mt_010243515 — Brighton & Hove Albion (home) vs Manchester City (away) · epl

**1. Upstream historical data available (PIT-safe, before kickoff):**

- Home (Brighton & Hove Albion): 40 prior matches; venue-splittable metrics 19/19; W10 ok: True; formation coverage 0.175 (7/40), distinct formations 1, contrastive False.
- Away (Manchester City): 40 prior matches; venue-splittable metrics 19/19; W10 ok: True; formation coverage 0.175 (7/40), distinct formations 1, contrastive False.

**2. Exact evidence Sonnet saw:**

- 76 evidence items, all `window=['ALL_PRIOR']` `venue=['ALL']` (unconditional shrunk scalar means), 19 distinct metrics × FOR/AGAINST × HOME/AWAY. No distribution, no per-match rows, no venue/formation/opponent-profile split.
  - `corners_for` = 4.8792 (n=40, HIGH, SHRUNK, thestatsapi)
  - `shots_on_target_for` = 4.9105 (n=40, HIGH, SHRUNK, thestatsapi)
  - `possession_for` = 52.3043 (n=40, HIGH, SHRUNK, thestatsapi)
  - `goals_for` = 1.6466 (n=40, HIGH, SHRUNK, thestatsapi)
- formation_distribution (count histogram only): `{"AWAY_TEAM": {"BACK_FOUR": 3}, "HOME_TEAM": {"BACK_FOUR": 3}}`

**3. Accepted raw hypotheses (10) — verbatim question + structure:**

- **H1** [SET_PIECE_GENERATION] target=['corners'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team generate corners at a rate consistent with its recorded overall baseline, given its notably elevated corners-for average cited in evidence?*
  - conditions: venue=AWAY · comparison: `SUBJECT_VENUE_BASELINE` · window: `ALL_PRIOR`
- **H10** [FORM_VS_BASELINE] target=['goals'] side=AGAINST subject=AWAY_TEAM
  - Q: *Does the away team's goals-against rate over its most recent matches differ from its longer-term baseline, given its recorded overall goals-against average?*
  - conditions: (none) · comparison: `SUBJECT_RECENT_VS_LONG_BASELINE` · window: `W5`
- **H2** [DEFENSIVE_SUPPRESSION] target=['corners'] side=AGAINST subject=AWAY_TEAM
  - Q: *Does the away team suppress opponent corners at a rate that differs from the league environment baseline, given its recorded corners-against average?*
  - conditions: (none) · comparison: `LEAGUE_ENVIRONMENT_BASELINE` · window: `ALL_PRIOR`
- **H3** [TEMPO_AND_TERRITORY] target=['possession', 'final_third_entries'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team's recorded possession-for average translate into a proportionally elevated final-third-entries rate compared to its own overall baseline?*
  - conditions: (none) · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H4** [ATTACK_VOLUME] target=['shots_inside_box', 'touches_in_box'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team generate shots inside the box and touches in the box at a rate consistent with its overall baseline when playing away from home?*
  - conditions: venue=AWAY · comparison: `SUBJECT_VENUE_BASELINE` · window: `ALL_PRIOR`
- **H5** [DEFENSIVE_CONCESSION] target=['touches_in_box', 'shots_inside_box'] side=AGAINST subject=HOME_TEAM
  - Q: *Does the home team concede touches in the box and shots inside the box at a rate that differs from the league environment baseline, given its recorded defensive averages?*
  - conditions: venue=HOME · comparison: `LEAGUE_ENVIRONMENT_BASELINE` · window: `ALL_PRIOR`
- **H6** [ATTACK_QUALITY] target=['big_chances'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team's big-chances-for rate against opponents with a low goals-against profile differ from its overall baseline?*
  - conditions: opponent_profile=LOW · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H7** [DISCIPLINE] target=['yellow_cards'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team's yellow-cards-for rate against opponents with a high possession-for profile differ from its own overall baseline?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H8** [DEFENSIVE_SUPPRESSION] target=['shots_on_target'] side=AGAINST subject=AWAY_TEAM
  - Q: *Does the away team's shots-on-target-against rate when facing opponents with a high shots-on-target-for profile differ from its own overall baseline?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H9** [ATTACK_VOLUME] target=['total_shots'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team's total-shots-for rate when playing at home differ from its own overall baseline, given its recorded home-venue context?*
  - conditions: venue=HOME · comparison: `SUBJECT_VENUE_BASELINE` · window: `ALL_PRIOR`

**4. Compiled interpretation (deterministic):**

- comparisons requested: `{'SUBJECT_VENUE_BASELINE': 3, 'SUBJECT_RECENT_VS_LONG_BASELINE': 1, 'LEAGUE_ENVIRONMENT_BASELINE': 2, 'SUBJECT_OVERALL_BASELINE': 4}`
- condition dimensions requested: `{'venue': 4, 'opponent_profile': 3}`

**5. Important upstream information Sonnet did NOT see:**

- venue-conditioned behavior (home/away splits were derivable for ~19/19 metrics)
- recent-vs-long-run (W5/W10/season all derivable) — collapsed to ALL_PRIOR
- opponent-profile response vs similar opponents (derivable; V4-proven measurable)
- per-match rows / chronology / distribution / cross-metric structure
- formation splits — genuinely provider-limited here (low coverage)

---

## mt_010243537 — Sunderland (home) vs Bournemouth (away) · epl

**1. Upstream historical data available (PIT-safe, before kickoff):**

- Home (Sunderland): 104 prior matches; venue-splittable metrics 19/19; W10 ok: True; formation coverage 0.1058 (11/104), distinct formations 2, contrastive False.
- Away (Bournemouth): 50 prior matches; venue-splittable metrics 19/19; W10 ok: True; formation coverage 0.16 (8/50), distinct formations 1, contrastive False.

**2. Exact evidence Sonnet saw:**

- 76 evidence items, all `window=['ALL_PRIOR']` `venue=['ALL']` (unconditional shrunk scalar means), 19 distinct metrics × FOR/AGAINST × HOME/AWAY. No distribution, no per-match rows, no venue/formation/opponent-profile split.
  - `corners_for` = 5.4716 (n=103, HIGH, SHRUNK, thestatsapi)
  - `shots_on_target_for` = 4.2526 (n=103, HIGH, SHRUNK, thestatsapi)
  - `possession_for` = 51.4312 (n=103, HIGH, SHRUNK, thestatsapi)
  - `goals_for` = 1.206 (n=104, HIGH, SHRUNK, thestatsapi)
- formation_distribution (count histogram only): `{"AWAY_TEAM": {"BACK_FOUR": 3}, "HOME_TEAM": {"BACK_FOUR": 2, "BACK_THREE": 1}}`

**3. Accepted raw hypotheses (10) — verbatim question + structure:**

- **H1** [ATTACK_VOLUME] target=['total_shots', 'shots_inside_box'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team generate more total shots and shots inside the box at home venues compared to its overall baseline, given its recorded total shots and shots inside box averages cited in evidence?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H10** [FORM_VS_BASELINE] target=['goals', 'big_chances'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team's recent goals-for and big chances rate differ from its longer-term baseline, given its recorded goals-for and big-chances-for averages?*
  - conditions: (none) · comparison: `SUBJECT_RECENT_VS_LONG_BASELINE` · window: `W5`
- **H2** [ATTACK_QUALITY] target=['big_chances', 'shots_on_target'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team produce more big chances and shots on target when facing opponents with a low shots-on-target-against profile, compared to its overall baseline?*
  - conditions: opponent_profile=LOW · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H3** [DEFENSIVE_CONCESSION] target=['shots_inside_box', 'touches_in_box'] side=AGAINST subject=HOME_TEAM
  - Q: *Does the home team concede more shots inside the box and touches in the box when facing opponents with a high shots-on-target-for profile, compared to its overall defensive baseline?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H4** [SET_PIECE_GENERATION] target=['corners'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team generate corners at a rate consistent with its overall baseline when playing away from home, given its recorded corners-for average?*
  - conditions: venue=AWAY · comparison: `SUBJECT_VENUE_BASELINE` · window: `ALL_PRIOR`
- **H5** [DISCIPLINE] target=['fouls', 'yellow_cards'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team commit fouls and receive yellow cards at a rate above the league environment baseline, given its recorded fouls-for and yellow-cards-for averages?*
  - conditions: (none) · comparison: `LEAGUE_ENVIRONMENT_BASELINE` · window: `ALL_PRIOR`
- **H6** [TEMPO_AND_TERRITORY] target=['final_third_entries'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team achieve a higher rate of final third entries compared to the home team's defensive baseline for final third entries conceded, given both teams' recorded averages?*
  - conditions: (none) · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H7** [DEFENSIVE_SUPPRESSION] target=['clearances', 'interceptions'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team's clearance and interception volume when playing at home differ from its overall baseline, given its recorded clearances-for and interceptions-for averages?*
  - conditions: venue=HOME · comparison: `SUBJECT_VENUE_BASELINE` · window: `ALL_PRIOR`
- **H8** [ATTACK_QUALITY] target=['big_chances', 'shots_on_target'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team's big chances and shots on target rate when facing opponents with a high accurate-crosses-for profile differ from its overall attacking baseline?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H9** [OPPONENT_PROFILE_INTERACTION] target=['accurate_crosses', 'corners'] side=AGAINST subject=HOME_TEAM
  - Q: *Does the home team concede more accurate crosses and corners when facing opponents with a high accurate-crosses-for profile, compared to its overall defensive baseline?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`

**4. Compiled interpretation (deterministic):**

- comparisons requested: `{'SUBJECT_OVERALL_BASELINE': 6, 'SUBJECT_RECENT_VS_LONG_BASELINE': 1, 'SUBJECT_VENUE_BASELINE': 2, 'LEAGUE_ENVIRONMENT_BASELINE': 1}`
- condition dimensions requested: `{'venue': 3, 'opponent_profile': 4}`

**5. Important upstream information Sonnet did NOT see:**

- venue-conditioned behavior (home/away splits were derivable for ~19/19 metrics)
- recent-vs-long-run (W5/W10/season all derivable) — collapsed to ALL_PRIOR
- opponent-profile response vs similar opponents (derivable; V4-proven measurable)
- per-match rows / chronology / distribution / cross-metric structure
- formation splits — genuinely provider-limited here (low coverage)

---

## mt_010243938 — Crystal Palace (home) vs West Ham United (away) · epl

**1. Upstream historical data available (PIT-safe, before kickoff):**

- Home (Crystal Palace): 69 prior matches; venue-splittable metrics 19/19; W10 ok: True; formation coverage 0.1739 (12/69), distinct formations 1, contrastive False.
- Away (West Ham United): 70 prior matches; venue-splittable metrics 19/19; W10 ok: True; formation coverage 0.1286 (9/70), distinct formations 2, contrastive False.

**2. Exact evidence Sonnet saw:**

- 76 evidence items, all `window=['ALL_PRIOR']` `venue=['ALL']` (unconditional shrunk scalar means), 19 distinct metrics × FOR/AGAINST × HOME/AWAY. No distribution, no per-match rows, no venue/formation/opponent-profile split.
  - `corners_for` = 4.4164 (n=69, HIGH, SHRUNK, thestatsapi)
  - `shots_on_target_for` = 4.3489 (n=69, HIGH, SHRUNK, thestatsapi)
  - `possession_for` = 44.6 (n=69, HIGH, SHRUNK, thestatsapi)
  - `goals_for` = 1.2606 (n=69, HIGH, SHRUNK, thestatsapi)
- formation_distribution (count histogram only): `{"AWAY_TEAM": {"BACK_FOUR": 2}, "HOME_TEAM": {"BACK_THREE": 3}}`

**3. Accepted raw hypotheses (12) — verbatim question + structure:**

- **H1** [DEFENSIVE_CONCESSION] target=['shots_on_target', 'shots_inside_box', 'touches_in_box'] side=AGAINST subject=AWAY_TEAM
  - Q: *Does the away team concede more shots on target, shots inside the box, and touches in the box when playing away compared to its overall baseline, given its recorded shots-on-target-against and touches-in-box-against averages?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H10** [FORM_VS_BASELINE] target=['shots_on_target', 'big_chances'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team's recent shots-on-target-for and big-chances-for rate differ from its longer-term baseline, given its recorded overall averages for those metrics?*
  - conditions: (none) · comparison: `SUBJECT_RECENT_VS_LONG_BASELINE` · window: `W5`
- **H11** [FORM_VS_BASELINE] target=['goals', 'shots_on_target'] side=AGAINST subject=AWAY_TEAM
  - Q: *Does the away team's recent goals-against and shots-on-target-against rate differ from its longer-term baseline, given its recorded overall averages for those metrics?*
  - conditions: (none) · comparison: `SUBJECT_RECENT_VS_LONG_BASELINE` · window: `W5`
- **H12** [SET_PIECE_GENERATION] target=['corners'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team generate more corners against opponents with a high corners-against profile compared to its overall baseline, given its recorded corners-for average?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H2** [DEFENSIVE_CONCESSION] target=['accurate_crosses', 'corners'] side=AGAINST subject=AWAY_TEAM
  - Q: *Does the away team concede more accurate crosses and corners when playing away compared to its overall baseline, given its recorded accurate-crosses-against and corners-against averages?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H3** [VENUE_EFFECT] target=['corners', 'accurate_crosses'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team generate more corners and accurate crosses at home compared to its overall baseline, given its recorded corners-for and accurate-crosses-for averages?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H4** [ATTACK_QUALITY] target=['big_chances', 'shots_on_target'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team generate more big chances and shots on target against opponents with a high goals-against profile compared to its overall baseline, given its recorded big-chances-for and shots-on-target-for averages?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H5** [TEMPO_AND_TERRITORY] target=['possession', 'final_third_entries'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team record a lower possession share and fewer final-third entries at home compared to its overall baseline, given its recorded possession-for and final-third-entries-for averages?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H6** [DEFENSIVE_SUPPRESSION] target=['clearances', 'tackles'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team record more clearances and tackles against opponents with a high shots-on-target-for profile compared to its overall baseline, given its recorded clearances-for and tackles-for averages?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H7** [ATTACK_VOLUME] target=['total_shots', 'shots_inside_box'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team generate fewer total shots and shots inside the box when playing away compared to its overall baseline, given its recorded total-shots-for and shots-inside-box-for averages?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H8** [DISCIPLINE] target=['yellow_cards'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team accumulate more yellow cards when playing away compared to its overall baseline, given its recorded yellow-cards-for average?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H9** [OPPONENT_PROFILE_INTERACTION] target=['big_chances', 'goals'] side=AGAINST subject=AWAY_TEAM
  - Q: *Does the away team concede more big chances and goals against opponents with a high accurate-crosses-for profile compared to its overall baseline, given its recorded big-chances-against and goals-against averages?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`

**4. Compiled interpretation (deterministic):**

- comparisons requested: `{'SUBJECT_OVERALL_BASELINE': 10, 'SUBJECT_RECENT_VS_LONG_BASELINE': 2}`
- condition dimensions requested: `{'venue': 6, 'opponent_profile': 4}`

**5. Important upstream information Sonnet did NOT see:**

- venue-conditioned behavior (home/away splits were derivable for ~19/19 metrics)
- recent-vs-long-run (W5/W10/season all derivable) — collapsed to ALL_PRIOR
- opponent-profile response vs similar opponents (derivable; V4-proven measurable)
- per-match rows / chronology / distribution / cross-metric structure
- formation splits — genuinely provider-limited here (low coverage)

---

## mt_010244159 — Fulham (home) vs Aston Villa (away) · epl

**1. Upstream historical data available (PIT-safe, before kickoff):**

- Home (Fulham): 71 prior matches; venue-splittable metrics 19/19; W10 ok: True; formation coverage 0.1831 (13/71), distinct formations 2, contrastive False.
- Away (Aston Villa): 71 prior matches; venue-splittable metrics 19/19; W10 ok: True; formation coverage 0.169 (12/71), distinct formations 1, contrastive False.

**2. Exact evidence Sonnet saw:**

- 76 evidence items, all `window=['ALL_PRIOR']` `venue=['ALL']` (unconditional shrunk scalar means), 19 distinct metrics × FOR/AGAINST × HOME/AWAY. No distribution, no per-match rows, no venue/formation/opponent-profile split.
  - `corners_for` = 5.0813 (n=71, HIGH, SHRUNK, thestatsapi)
  - `shots_on_target_for` = 4.1451 (n=71, HIGH, SHRUNK, thestatsapi)
  - `possession_for` = 51.8831 (n=71, HIGH, SHRUNK, thestatsapi)
  - `goals_for` = 1.3706 (n=71, HIGH, SHRUNK, thestatsapi)
- formation_distribution (count histogram only): `{"AWAY_TEAM": {"BACK_FOUR": 2}, "HOME_TEAM": {"BACK_FOUR": 2}}`

**3. Accepted raw hypotheses (10) — verbatim question + structure:**

- **H1** [ATTACK_QUALITY] target=['big_chances'] side=AGAINST subject=HOME_TEAM
  - Q: *Does the HOME_TEAM's big chances conceded rate, given its recorded big_chances_against average, differ from the league environment baseline?*
  - conditions: (none) · comparison: `LEAGUE_ENVIRONMENT_BASELINE` · window: `ALL_PRIOR`
- **H10** [DEFENSIVE_CONCESSION] target=['touches_in_box'] side=AGAINST subject=HOME_TEAM
  - Q: *Does the HOME_TEAM's touches_in_box conceded rate against opponents with a HIGH touches_in_box profile differ from its overall baseline?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H2** [ATTACK_QUALITY] target=['big_chances'] side=FOR subject=AWAY_TEAM
  - Q: *Does the AWAY_TEAM's big chances created rate, given its recorded big_chances_for average, differ from the league environment baseline?*
  - conditions: (none) · comparison: `LEAGUE_ENVIRONMENT_BASELINE` · window: `ALL_PRIOR`
- **H3** [SET_PIECE_GENERATION] target=['corners'] side=FOR subject=HOME_TEAM
  - Q: *Does the HOME_TEAM's corners generated rate at home differ from its overall baseline, given its recorded corners_for average across all venues?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H4** [SET_PIECE_GENERATION] target=['corners'] side=FOR subject=AWAY_TEAM
  - Q: *Does the AWAY_TEAM's corners generated rate when playing away differ from its overall baseline, given its recorded corners_for average across all venues?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H5** [ATTACK_VOLUME] target=['accurate_crosses'] side=FOR subject=AWAY_TEAM
  - Q: *Does the AWAY_TEAM's accurate crosses rate against opponents with a HIGH accurate_crosses_against profile differ from its overall baseline?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H6** [DISCIPLINE] target=['yellow_cards'] side=FOR subject=HOME_TEAM
  - Q: *Does the HOME_TEAM's yellow cards rate at home differ from its overall baseline, given its recorded yellow_cards_for average across all venues?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H7** [DISCIPLINE] target=['yellow_cards'] side=FOR subject=AWAY_TEAM
  - Q: *Does the AWAY_TEAM's yellow cards conceded rate against opponents with a HIGH fouls_for profile differ from its overall baseline?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H8** [DEFENSIVE_SUPPRESSION] target=['shots_on_target'] side=AGAINST subject=AWAY_TEAM
  - Q: *Does the AWAY_TEAM's shots_on_target conceded rate when playing away differ from its overall baseline, given its recorded shots_on_target_against average?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H9** [TEMPO_AND_TERRITORY] target=['possession'] side=FOR subject=HOME_TEAM
  - Q: *Does the HOME_TEAM's possession rate at home differ from its overall baseline, given its recorded possession_for average across all venues?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`

**4. Compiled interpretation (deterministic):**

- comparisons requested: `{'LEAGUE_ENVIRONMENT_BASELINE': 2, 'SUBJECT_OVERALL_BASELINE': 8}`
- condition dimensions requested: `{'opponent_profile': 3, 'venue': 5}`

**5. Important upstream information Sonnet did NOT see:**

- venue-conditioned behavior (home/away splits were derivable for ~19/19 metrics)
- recent-vs-long-run (W5/W10/season all derivable) — collapsed to ALL_PRIOR
- opponent-profile response vs similar opponents (derivable; V4-proven measurable)
- per-match rows / chronology / distribution / cross-metric structure
- formation splits — genuinely provider-limited here (low coverage)

---

## mt_010244193 — Manchester United (home) vs Aston Villa (away) · epl

**1. Upstream historical data available (PIT-safe, before kickoff):**

- Home (Manchester United): 67 prior matches; venue-splittable metrics 19/19; W10 ok: True; formation coverage 0.1493 (10/67), distinct formations 2, contrastive True.
- Away (Aston Villa): 67 prior matches; venue-splittable metrics 19/19; W10 ok: True; formation coverage 0.1642 (11/67), distinct formations 1, contrastive False.

**2. Exact evidence Sonnet saw:**

- 76 evidence items, all `window=['ALL_PRIOR']` `venue=['ALL']` (unconditional shrunk scalar means), 19 distinct metrics × FOR/AGAINST × HOME/AWAY. No distribution, no per-match rows, no venue/formation/opponent-profile split.
  - `corners_for` = 4.8519 (n=67, HIGH, SHRUNK, thestatsapi)
  - `shots_on_target_for` = 5.0295 (n=67, HIGH, SHRUNK, thestatsapi)
  - `possession_for` = 53.274 (n=67, HIGH, SHRUNK, thestatsapi)
  - `goals_for` = 1.4186 (n=67, HIGH, SHRUNK, thestatsapi)
- formation_distribution (count histogram only): `{"AWAY_TEAM": {"BACK_FOUR": 2}, "HOME_TEAM": {"BACK_FOUR": 2, "BACK_THREE": 1}}`

**3. Accepted raw hypotheses (8) — verbatim question + structure:**

- **H1** [ATTACK_VOLUME] target=['total_shots'] side=FOR subject=HOME_TEAM
  - Q: *Does the HOME_TEAM generate more total shots at home compared to its overall baseline, given its recorded total-shots-for average across all venues?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H2** [SET_PIECE_GENERATION] target=['corners'] side=FOR subject=AWAY_TEAM
  - Q: *Does the AWAY_TEAM generate corners at a different rate when playing away compared to its overall baseline, given its recorded corners-for average?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H3** [DEFENSIVE_SUPPRESSION] target=['shots_on_target'] side=AGAINST subject=AWAY_TEAM
  - Q: *Does the AWAY_TEAM concede fewer shots on target when facing opponents with a high shots-on-target-for profile, compared to its overall defensive baseline?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H4** [ATTACK_QUALITY] target=['big_chances'] side=FOR subject=HOME_TEAM
  - Q: *Does the HOME_TEAM generate big chances at a different rate against opponents with a low goals-against profile compared to its overall baseline, given its recorded big-chances-for average?*
  - conditions: opponent_profile=LOW · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H5** [DISCIPLINE] target=['fouls', 'yellow_cards'] side=FOR subject=AWAY_TEAM
  - Q: *Does the AWAY_TEAM commit fouls at a different rate when playing away compared to its overall baseline, given its recorded fouls-for average across all venues?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H6** [TEMPO_AND_TERRITORY] target=['possession'] side=FOR subject=HOME_TEAM
  - Q: *Does the HOME_TEAM achieve a higher possession share at home compared to its overall baseline, given its recorded possession-for average?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H7** [DEFENSIVE_CONCESSION] target=['accurate_crosses'] side=AGAINST subject=HOME_TEAM
  - Q: *Does the HOME_TEAM concede more accurate crosses when facing opponents with a high accurate-crosses-for profile, compared to its overall defensive baseline?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H8** [FORMATION_INTERACTION] target=['shots_inside_box'] side=FOR subject=HOME_TEAM
  - Q: *Does the HOME_TEAM generate more shots inside the box when facing back-four opponents compared to its overall baseline, given its recorded shots-inside-box-for average?*
  - conditions: opponent_formation_family=BACK_FOUR · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`

**4. Compiled interpretation (deterministic):**

- comparisons requested: `{'SUBJECT_OVERALL_BASELINE': 8}`
- condition dimensions requested: `{'venue': 4, 'opponent_profile': 3, 'opponent_formation_family': 1}`

**5. Important upstream information Sonnet did NOT see:**

- venue-conditioned behavior (home/away splits were derivable for ~19/19 metrics)
- recent-vs-long-run (W5/W10/season all derivable) — collapsed to ALL_PRIOR
- opponent-profile response vs similar opponents (derivable; V4-proven measurable)
- per-match rows / chronology / distribution / cross-metric structure
- formation-conditioned metrics (a contrastive split existed on at least one side)

---

## mt_010441320 — Sevilla (home) vs Rayo Vallecano (away) · laliga

**1. Upstream historical data available (PIT-safe, before kickoff):**

- Home (Sevilla): 64 prior matches; venue-splittable metrics 19/19; W10 ok: True; formation coverage 0.2188 (14/64), distinct formations 3, contrastive True.
- Away (Rayo Vallecano): 64 prior matches; venue-splittable metrics 19/19; W10 ok: True; formation coverage 0.1562 (10/64), distinct formations 1, contrastive False.

**2. Exact evidence Sonnet saw:**

- 76 evidence items, all `window=['ALL_PRIOR']` `venue=['ALL']` (unconditional shrunk scalar means), 19 distinct metrics × FOR/AGAINST × HOME/AWAY. No distribution, no per-match rows, no venue/formation/opponent-profile split.
  - `corners_for` = 4.8814 (n=64, HIGH, SHRUNK, thestatsapi)
  - `shots_on_target_for` = 4.0138 (n=64, HIGH, SHRUNK, thestatsapi)
  - `possession_for` = 51.8429 (n=64, HIGH, SHRUNK, thestatsapi)
  - `goals_for` = 1.1987 (n=64, HIGH, SHRUNK, thestatsapi)
- formation_distribution (count histogram only): `{"AWAY_TEAM": {"BACK_FOUR": 3}, "HOME_TEAM": {"BACK_FIVE": 2, "BACK_THREE": 2}}`

**3. Accepted raw hypotheses (12) — verbatim question + structure:**

- **H1** [ATTACK_VOLUME] target=['total_shots'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team generate more total shots at home venues compared to its overall baseline, given its recorded total-shots-for average cited in evidence?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H10** [SET_PIECE_GENERATION] target=['corners', 'accurate_crosses'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team generate more corners against opponents who concede a high volume of accurate crosses, compared to its overall baseline?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H11** [ATTACK_QUALITY] target=['big_chances'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team's big-chances-for rate at home differ from its overall baseline, given its recorded big-chances-for average across all venues?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H12** [FORMATION_INTERACTION] target=['shots_inside_box'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team record more shots inside the box against opponents deploying a back-three formation compared to its overall baseline?*
  - conditions: opponent_formation_family=BACK_THREE · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H2** [DEFENSIVE_CONCESSION] target=['big_chances'] side=AGAINST subject=HOME_TEAM
  - Q: *Does the home team concede more big chances when playing at home compared to its overall baseline, given its recorded big-chances-against average?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H3** [ATTACK_QUALITY] target=['big_chances', 'shots_on_target'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team generate more big chances against opponents who concede a high volume of shots on target, compared to its overall baseline?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H4** [DEFENSIVE_SUPPRESSION] target=['touches_in_box'] side=AGAINST subject=HOME_TEAM
  - Q: *Does the home team suppress opponent touches in the box more effectively when playing at home compared to its overall baseline, given its recorded touches-in-box-against average?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H5** [FORMATION_INTERACTION] target=['corners', 'accurate_crosses'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team record more corners and accurate crosses against opponents deploying a back-five formation compared to its overall baseline, given its recorded formation distribution?*
  - conditions: opponent_formation_family=BACK_FIVE · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H6** [FORMATION_INTERACTION] target=['shots_inside_box'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team's shots-inside-box volume differ when deploying a back-five versus a back-three formation, compared to its overall baseline?*
  - conditions: own_formation_family=BACK_FIVE · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H7** [DISCIPLINE] target=['yellow_cards'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team accumulate more yellow cards when playing at home compared to its overall baseline, given its recorded yellow-cards-for average?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H8** [TEMPO_AND_TERRITORY] target=['final_third_entries', 'possession'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team record more final-third entries against opponents with a low possession average, compared to its overall baseline?*
  - conditions: opponent_profile=LOW · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H9** [DEFENSIVE_CONCESSION] target=['touches_in_box'] side=AGAINST subject=AWAY_TEAM
  - Q: *Does the away team concede more touches in the box when playing away compared to its overall baseline, given its recorded touches-in-box-against average?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`

**4. Compiled interpretation (deterministic):**

- comparisons requested: `{'SUBJECT_OVERALL_BASELINE': 12}`
- condition dimensions requested: `{'venue': 6, 'opponent_profile': 3, 'opponent_formation_family': 2, 'own_formation_family': 1}`

**5. Important upstream information Sonnet did NOT see:**

- venue-conditioned behavior (home/away splits were derivable for ~19/19 metrics)
- recent-vs-long-run (W5/W10/season all derivable) — collapsed to ALL_PRIOR
- opponent-profile response vs similar opponents (derivable; V4-proven measurable)
- per-match rows / chronology / distribution / cross-metric structure
- formation-conditioned metrics (a contrastive split existed on at least one side)

---

## mt_010441491 — FC Andorra (home) vs Albacete Balompié (away) · laliga2

**1. Upstream historical data available (PIT-safe, before kickoff):**

- Home (FC Andorra): 37 prior matches; venue-splittable metrics 19/19; W10 ok: True; formation coverage 0.3243 (12/37), distinct formations 1, contrastive False.
- Away (Albacete Balompié): 79 prior matches; venue-splittable metrics 19/19; W10 ok: True; formation coverage 0.1646 (13/79), distinct formations 2, contrastive False.

**2. Exact evidence Sonnet saw:**

- 76 evidence items, all `window=['ALL_PRIOR']` `venue=['ALL']` (unconditional shrunk scalar means), 19 distinct metrics × FOR/AGAINST × HOME/AWAY. No distribution, no per-match rows, no venue/formation/opponent-profile split.
  - `corners_for` = 5.0959 (n=37, HIGH, SHRUNK, thestatsapi)
  - `shots_on_target_for` = 4.8651 (n=37, HIGH, SHRUNK, thestatsapi)
  - `possession_for` = 58.814 (n=37, HIGH, SHRUNK, thestatsapi)
  - `goals_for` = 1.4821 (n=37, HIGH, SHRUNK, thestatsapi)
- formation_distribution (count histogram only): `{"AWAY_TEAM": {"BACK_FIVE": 2}, "HOME_TEAM": {"BACK_FOUR": 5}}`

**3. Accepted raw hypotheses (10) — verbatim question + structure:**

- **H1** [TEMPO_AND_TERRITORY] target=['possession'] side=FOR subject=HOME_TEAM
  - Q: *Does the HOME_TEAM's possession share at home differ from its overall possession baseline, given its recorded possession-for average across all prior matches?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H10** [TEMPO_AND_TERRITORY] target=['final_third_entries'] side=AGAINST subject=AWAY_TEAM
  - Q: *Does the AWAY_TEAM's final-third-entries-against rate when playing away differ from its overall baseline, given its recorded defensive territorial average?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H2** [ATTACK_VOLUME] target=['total_shots', 'shots_on_target'] side=FOR subject=HOME_TEAM
  - Q: *Does the HOME_TEAM generate a different volume of total shots and shots on target at home compared to its overall baseline?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H3** [DEFENSIVE_CONCESSION] target=['shots_inside_box', 'touches_in_box'] side=AGAINST subject=AWAY_TEAM
  - Q: *Does the AWAY_TEAM concede more shots inside the box and touches in the box when playing away compared to its overall baseline, given its recorded defensive averages?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H4** [SET_PIECE_GENERATION] target=['corners'] side=FOR subject=HOME_TEAM
  - Q: *Does the HOME_TEAM generate more corners at home than its overall baseline, given its recorded corners-for average?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H5** [OPPONENT_PROFILE_INTERACTION] target=['accurate_crosses'] side=AGAINST subject=HOME_TEAM
  - Q: *Does the HOME_TEAM's accurate-crosses-against rate differ when facing opponents with a high accurate-crosses-for profile, compared to its overall defensive baseline?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H6** [DEFENSIVE_SUPPRESSION] target=['clearances'] side=FOR subject=AWAY_TEAM
  - Q: *Does the AWAY_TEAM's clearances-for rate when playing away differ from its overall baseline, given its recorded clearances average?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H7** [ATTACK_QUALITY] target=['big_chances'] side=AGAINST subject=AWAY_TEAM
  - Q: *Does the AWAY_TEAM's big-chances-against rate differ when facing opponents with a high possession-for profile, compared to its overall defensive baseline?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H8** [DISCIPLINE] target=['yellow_cards'] side=FOR subject=HOME_TEAM
  - Q: *Does the HOME_TEAM's yellow-cards-for rate at home differ from its overall baseline, given its recorded yellow-cards average?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H9** [ATTACK_QUALITY] target=['big_chances'] side=FOR subject=HOME_TEAM
  - Q: *Does the HOME_TEAM's big-chances-for rate differ when facing opponents with a low shots-on-target-for profile, compared to its overall attacking baseline?*
  - conditions: opponent_profile=LOW · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`

**4. Compiled interpretation (deterministic):**

- comparisons requested: `{'SUBJECT_OVERALL_BASELINE': 10}`
- condition dimensions requested: `{'venue': 7, 'opponent_profile': 3}`

**5. Important upstream information Sonnet did NOT see:**

- venue-conditioned behavior (home/away splits were derivable for ~19/19 metrics)
- recent-vs-long-run (W5/W10/season all derivable) — collapsed to ALL_PRIOR
- opponent-profile response vs similar opponents (derivable; V4-proven measurable)
- per-match rows / chronology / distribution / cross-metric structure
- formation splits — genuinely provider-limited here (low coverage)

---

## mt_010444904 — Cádiz (home) vs Cultural Leonesa (away) · laliga2

**1. Upstream historical data available (PIT-safe, before kickoff):**

- Home (Cádiz): 56 prior matches; venue-splittable metrics 19/19; W10 ok: True; formation coverage 0.2143 (12/56), distinct formations 2, contrastive False.
- Away (Cultural Leonesa): 14 prior matches; venue-splittable metrics 19/19; W10 ok: True; formation coverage 0.2857 (4/14), distinct formations 1, contrastive False.

**2. Exact evidence Sonnet saw:**

- 76 evidence items, all `window=['ALL_PRIOR']` `venue=['ALL']` (unconditional shrunk scalar means), 19 distinct metrics × FOR/AGAINST × HOME/AWAY. No distribution, no per-match rows, no venue/formation/opponent-profile split.
  - `corners_for` = 4.03 (n=56, HIGH, SHRUNK, thestatsapi)
  - `shots_on_target_for` = 3.6576 (n=56, HIGH, SHRUNK, thestatsapi)
  - `possession_for` = 48.4032 (n=56, HIGH, SHRUNK, thestatsapi)
  - `goals_for` = 1.1873 (n=56, HIGH, SHRUNK, thestatsapi)
- formation_distribution (count histogram only): `{"AWAY_TEAM": {"BACK_FOUR": 4}, "HOME_TEAM": {"BACK_FOUR": 3, "BACK_THREE": 1}}`

**3. Accepted raw hypotheses (10) — verbatim question + structure:**

- **H1** [DEFENSIVE_CONCESSION] target=['shots_inside_box'] side=AGAINST subject=AWAY_TEAM
  - Q: *Does the away team concede more shots inside the box when playing away from home, compared to its overall venue-neutral baseline, given its recorded shots_inside_box_against average?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H10** [FORM_VS_BASELINE] target=['shots_on_target'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team's recent shots_on_target_for rate differ from its longer-term baseline, given its recorded shots_on_target_for average?*
  - conditions: (none) · comparison: `SUBJECT_RECENT_VS_LONG_BASELINE` · window: `W5`
- **H2** [DEFENSIVE_CONCESSION] target=['accurate_crosses'] side=AGAINST subject=AWAY_TEAM
  - Q: *Does the away team allow more accurate crosses against when playing away from home, compared to its overall baseline, given its recorded accurate_crosses_against average?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H3** [ATTACK_VOLUME] target=['corners'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team generate more corners when playing at home, compared to its overall baseline, given its recorded corners_for average?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H4** [DISCIPLINE] target=['yellow_cards'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team accumulate yellow cards at a rate that differs from the league environment baseline, given its recorded yellow_cards_for average?*
  - conditions: (none) · comparison: `LEAGUE_ENVIRONMENT_BASELINE` · window: `ALL_PRIOR`
- **H5** [DISCIPLINE] target=['yellow_cards'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team accumulate yellow cards at a rate that differs from the league environment baseline, given its recorded yellow_cards_for average?*
  - conditions: (none) · comparison: `LEAGUE_ENVIRONMENT_BASELINE` · window: `ALL_PRIOR`
- **H6** [DEFENSIVE_SUPPRESSION] target=['big_chances'] side=AGAINST subject=HOME_TEAM
  - Q: *Does the home team concede fewer big chances when playing at home against opponents with a high shots_on_target_for profile, compared to its overall baseline, given its recorded big_chances_against average?*
  - conditions: venue=HOME, opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H7** [ATTACK_QUALITY] target=['big_chances'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team's big chances for rate differ from the league environment baseline, given its recorded big_chances_for average?*
  - conditions: (none) · comparison: `LEAGUE_ENVIRONMENT_BASELINE` · window: `ALL_PRIOR`
- **H8** [TEMPO_AND_TERRITORY] target=['final_third_entries'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team record fewer final third entries when playing away from home, compared to its overall baseline, given its recorded final_third_entries_for average?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H9** [DEFENSIVE_CONCESSION] target=['touches_in_box'] side=AGAINST subject=AWAY_TEAM
  - Q: *Does the away team concede more touches in the box when facing opponents with a high accurate_crosses_for profile, compared to its overall baseline, given its recorded touches_in_box_against average?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`

**4. Compiled interpretation (deterministic):**

- comparisons requested: `{'SUBJECT_OVERALL_BASELINE': 6, 'SUBJECT_RECENT_VS_LONG_BASELINE': 1, 'LEAGUE_ENVIRONMENT_BASELINE': 3}`
- condition dimensions requested: `{'venue': 5, 'opponent_profile': 2}`

**5. Important upstream information Sonnet did NOT see:**

- venue-conditioned behavior (home/away splits were derivable for ~19/19 metrics)
- recent-vs-long-run (W5/W10/season all derivable) — collapsed to ALL_PRIOR
- opponent-profile response vs similar opponents (derivable; V4-proven measurable)
- per-match rows / chronology / distribution / cross-metric structure
- formation splits — genuinely provider-limited here (low coverage)

---

## mt_012232295 — Ipswich Town (home) vs Sheffield Wednesday (away) · champ

**1. Upstream historical data available (PIT-safe, before kickoff):**

- Home (Ipswich Town): 37 prior matches; venue-splittable metrics 18/19; W10 ok: True; formation coverage 0.0 (0/37), distinct formations 0, contrastive False.
- Away (Sheffield Wednesday): 37 prior matches; venue-splittable metrics 18/19; W10 ok: True; formation coverage 0.027 (1/37), distinct formations 1, contrastive False.

**2. Exact evidence Sonnet saw:**

- 76 evidence items, all `window=['ALL_PRIOR']` `venue=['ALL']` (unconditional shrunk scalar means), 19 distinct metrics × FOR/AGAINST × HOME/AWAY. No distribution, no per-match rows, no venue/formation/opponent-profile split.
  - `corners_for` = 5.2968 (n=37, HIGH, SHRUNK, thestatsapi)
  - `shots_on_target_for` = 5.3322 (n=37, HIGH, SHRUNK, thestatsapi)
  - `possession_for` = 53.1628 (n=37, HIGH, SHRUNK, thestatsapi)
  - `goals_for` = 1.9117 (n=37, HIGH, SHRUNK, thestatsapi)
- formation_distribution (count histogram only): `{"AWAY_TEAM": {"BACK_FOUR": 1}, "HOME_TEAM": {}}`

**3. Accepted raw hypotheses (12) — verbatim question + structure:**

- **H1** [ATTACK_VOLUME] target=['total_shots'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team generate more total shots at home compared to its overall baseline, given its recorded total-shots-for average?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H10** [OPPONENT_PROFILE_INTERACTION] target=['accurate_crosses', 'shots_inside_box'] side=AGAINST subject=HOME_TEAM
  - Q: *Does the home team concede more accurate crosses and shots inside the box against opponents with a high accurate-crosses-for profile compared to its overall baseline, given its recorded accurate-crosses-against and shots-inside-box-against averages?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H11** [DEFENSIVE_SUPPRESSION] target=['clearances', 'interceptions'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team's clearances-for and interceptions-for differ when playing away compared to its overall baseline, given its recorded clearances-for and interceptions-for averages?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H12** [ATTACK_QUALITY] target=['shots_on_target', 'big_chances'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team's shots-on-target-for and big-chances-for differ against opponents with a high possession-for profile compared to its overall baseline, given its recorded shots-on-target-for and big-chances-for averages?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H2** [ATTACK_QUALITY] target=['big_chances', 'shots_on_target'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team produce more big chances and shots on target at home compared to its overall baseline, given its recorded shots-on-target-for and big-chances-for averages?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H3** [DEFENSIVE_SUPPRESSION] target=['shots_on_target', 'big_chances'] side=AGAINST subject=HOME_TEAM
  - Q: *Does the home team concede fewer shots on target and big chances at home compared to its overall baseline, given its recorded shots-on-target-against and big-chances-against averages?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H4** [ATTACK_VOLUME] target=['total_shots', 'shots_inside_box'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team's total shots and shots inside the box differ when playing away compared to its overall baseline, given its recorded total-shots-for and shots-inside-box-for averages?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H5** [DEFENSIVE_CONCESSION] target=['final_third_entries', 'shots_inside_box'] side=AGAINST subject=AWAY_TEAM
  - Q: *Does the away team concede more final third entries and shots inside the box when playing away compared to its overall baseline, given its recorded final-third-entries-against and shots-inside-box-against averages?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H6** [SET_PIECE_GENERATION] target=['corners', 'accurate_crosses'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team generate more corners and accurate crosses against opponents with a high corners-against profile compared to its overall baseline, given its recorded corners-for and accurate-crosses-for averages?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H7** [OPPONENT_PROFILE_INTERACTION] target=['goals', 'big_chances'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team's goals-for and big-chances-for differ when facing opponents with a low goals-against profile compared to its overall baseline, given its recorded goals-for and big-chances-for averages?*
  - conditions: opponent_profile=LOW · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H8** [TEMPO_AND_TERRITORY] target=['possession', 'final_third_entries'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team's possession and final third entries at home differ from its overall baseline, given its recorded possession-for and final-third-entries-for averages?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H9** [DISCIPLINE] target=['fouls', 'yellow_cards'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team commit more fouls and receive more yellow cards when playing away compared to its overall baseline, given its recorded fouls-for and yellow-cards-for averages?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`

**4. Compiled interpretation (deterministic):**

- comparisons requested: `{'SUBJECT_OVERALL_BASELINE': 12}`
- condition dimensions requested: `{'venue': 8, 'opponent_profile': 4}`

**5. Important upstream information Sonnet did NOT see:**

- venue-conditioned behavior (home/away splits were derivable for ~18/19 metrics)
- recent-vs-long-run (W5/W10/season all derivable) — collapsed to ALL_PRIOR
- opponent-profile response vs similar opponents (derivable; V4-proven measurable)
- per-match rows / chronology / distribution / cross-metric structure
- formation splits — genuinely provider-limited here (low coverage)

---

## mt_012232411 — Swansea City (home) vs Southampton (away) · champ

**1. Upstream historical data available (PIT-safe, before kickoff):**

- Home (Swansea City): 27 prior matches; venue-splittable metrics 18/19; W10 ok: True; formation coverage 0.0 (0/27), distinct formations 0, contrastive False.
- Away (Southampton): 27 prior matches; venue-splittable metrics 18/19; W10 ok: True; formation coverage 0.0741 (2/27), distinct formations 1, contrastive False.

**2. Exact evidence Sonnet saw:**

- 74 evidence items, all `window=['ALL_PRIOR']` `venue=['ALL']` (unconditional shrunk scalar means), 19 distinct metrics × FOR/AGAINST × HOME/AWAY. No distribution, no per-match rows, no venue/formation/opponent-profile split.
  - `corners_for` = 4.8553 (n=27, HIGH, SHRUNK, thestatsapi)
  - `shots_on_target_for` = 3.9216 (n=27, HIGH, SHRUNK, thestatsapi)
  - `possession_for` = 52.6061 (n=27, HIGH, SHRUNK, thestatsapi)
  - `goals_for` = 1.3704 (n=27, HIGH, SHRUNK, thestatsapi)
- formation_distribution (count histogram only): `{"AWAY_TEAM": {"BACK_FOUR": 1}, "HOME_TEAM": {}}`

**3. Accepted raw hypotheses (10) — verbatim question + structure:**

- **H1** [ATTACK_VOLUME] target=['total_shots', 'shots_on_target'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team generate more total shots and shots on target at home venues compared to its overall baseline, given its recorded overall shots-for averages?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H10** [OPPONENT_PROFILE_INTERACTION] target=['corners'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team's corners-for rate differ from its overall baseline when facing opponents with a high corners-for average?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H2** [TEMPO_AND_TERRITORY] target=['possession', 'final_third_entries'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team maintain a possession share consistent with its recorded overall possession average when playing away from home, and does this translate into a proportionate final-third-entries rate?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H3** [DEFENSIVE_SUPPRESSION] target=['shots_on_target', 'final_third_entries'] side=AGAINST subject=AWAY_TEAM
  - Q: *Does the away team suppress opponent shots on target and final-third entries at a rate consistent with its overall defensive baseline when facing opponents with a high possession share?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H4** [SET_PIECE_GENERATION] target=['corners'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team generate corners at a rate consistent with its overall baseline when facing opponents with a low corners-against average?*
  - conditions: opponent_profile=LOW · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H5** [DEFENSIVE_CONCESSION] target=['shots_inside_box', 'big_chances'] side=AGAINST subject=HOME_TEAM
  - Q: *Does the home team concede more shots inside the box and big chances against opponents with a high shots-on-target-for average compared to its overall defensive baseline?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H6** [ATTACK_QUALITY] target=['big_chances', 'shots_inside_box'] side=FOR subject=AWAY_TEAM
  - Q: *Does the away team generate big chances and shots inside the box at a rate consistent with its overall baseline when facing opponents with a high goals-against average?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H7** [DISCIPLINE] target=['yellow_cards'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team accumulate yellow cards at a rate consistent with its overall baseline when facing opponents with a high fouls-for average?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H8** [DEFENSIVE_SUPPRESSION] target=['clearances'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team's clearances-for rate differ from its overall baseline when facing opponents with a high accurate-crosses-for average?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H9** [VENUE_EFFECT] target=['shots_on_target', 'total_shots'] side=FOR subject=HOME_TEAM
  - Q: *Does the home team's shots-on-target-for and total-shots rate at home differ from its overall baseline, given its recorded overall attacking averages?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`

**4. Compiled interpretation (deterministic):**

- comparisons requested: `{'SUBJECT_OVERALL_BASELINE': 10}`
- condition dimensions requested: `{'venue': 3, 'opponent_profile': 7}`

**5. Important upstream information Sonnet did NOT see:**

- venue-conditioned behavior (home/away splits were derivable for ~18/19 metrics)
- recent-vs-long-run (W5/W10/season all derivable) — collapsed to ALL_PRIOR
- opponent-profile response vs similar opponents (derivable; V4-proven measurable)
- per-match rows / chronology / distribution / cross-metric structure
- formation splits — genuinely provider-limited here (low coverage)

---

## mt_013233190 — Fulham (home) vs Newcastle United (away) · epl

**1. Upstream historical data available (PIT-safe, before kickoff):**

- Home (Fulham): 4 prior matches; venue-splittable metrics 0/19; W10 ok: False; formation coverage 0.25 (1/4), distinct formations 1, contrastive False.
- Away (Newcastle United): 4 prior matches; venue-splittable metrics 0/19; W10 ok: False; formation coverage 0.25 (1/4), distinct formations 1, contrastive False.

**2. Exact evidence Sonnet saw:**

- 76 evidence items, all `window=['ALL_PRIOR']` `venue=['ALL']` (unconditional shrunk scalar means), 19 distinct metrics × FOR/AGAINST × HOME/AWAY. No distribution, no per-match rows, no venue/formation/opponent-profile split.
  - `corners_for` = 5.5829 (n=4, LOW, SHRUNK, thestatsapi)
  - `shots_on_target_for` = 4.4293 (n=4, LOW, SHRUNK, thestatsapi)
  - `possession_for` = 50.5 (n=4, LOW, SHRUNK, thestatsapi)
  - `goals_for` = 1.1976 (n=4, LOW, SHRUNK, thestatsapi)
- formation_distribution (count histogram only): `{"AWAY_TEAM": {"BACK_FOUR": 1}, "HOME_TEAM": {"BACK_FOUR": 1}}`

**3. Accepted raw hypotheses (8) — verbatim question + structure:**

- **H1** [ATTACK_VOLUME] target=['total_shots'] side=FOR subject=HOME_TEAM
  - Q: *Does the HOME_TEAM generate more total shots at home compared to its overall baseline, given its recorded total-shots-for average?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H2** [DEFENSIVE_CONCESSION] target=['shots_inside_box'] side=AGAINST subject=AWAY_TEAM
  - Q: *Does the AWAY_TEAM concede more shots inside the box when playing away compared to its overall baseline, given its recorded shots-inside-box-against average?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H3** [DEFENSIVE_CONCESSION] target=['touches_in_box'] side=AGAINST subject=AWAY_TEAM
  - Q: *Does the AWAY_TEAM allow more touches in the box against when playing away compared to its overall baseline, given its recorded touches-in-box-against average?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H4** [DEFENSIVE_CONCESSION] target=['final_third_entries'] side=AGAINST subject=AWAY_TEAM
  - Q: *Does the AWAY_TEAM concede more final-third entries when playing away compared to its overall baseline, given its recorded final-third-entries-against average?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H5** [ATTACK_QUALITY] target=['shots_inside_box'] side=FOR subject=HOME_TEAM
  - Q: *Does the HOME_TEAM generate more shots inside the box at home compared to its overall baseline, given its recorded shots-inside-box-for average?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H6** [DEFENSIVE_SUPPRESSION] target=['clearances'] side=FOR subject=HOME_TEAM
  - Q: *Does the HOME_TEAM record more clearances at home compared to its overall baseline, given its recorded clearances-for average and the gap relative to its clearances-against average?*
  - conditions: venue=HOME · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H7** [OPPONENT_PROFILE_INTERACTION] target=['corners'] side=FOR subject=HOME_TEAM
  - Q: *Does the HOME_TEAM generate more corners against opponents with a high corners-against profile compared to its overall baseline?*
  - conditions: opponent_profile=HIGH · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`
- **H8** [DISCIPLINE] target=['yellow_cards'] side=FOR subject=AWAY_TEAM
  - Q: *Does the AWAY_TEAM accumulate more yellow cards when playing away compared to its overall baseline, given its recorded yellow-cards-for average?*
  - conditions: venue=AWAY · comparison: `SUBJECT_OVERALL_BASELINE` · window: `ALL_PRIOR`

**4. Compiled interpretation (deterministic):**

- comparisons requested: `{'SUBJECT_OVERALL_BASELINE': 8}`
- condition dimensions requested: `{'venue': 7, 'opponent_profile': 1}`

**5. Important upstream information Sonnet did NOT see:**

- opponent-profile response vs similar opponents (derivable; V4-proven measurable)
- per-match rows / chronology / distribution / cross-metric structure
- formation splits — genuinely provider-limited here (low coverage)

---

## Cross-fixture note

Across the 11 fixtures, 58/112 accepted hypotheses requested venue conditioning or a venue baseline and 37/112 requested opponent-profile conditioning — while the evidence packet contained zero venue-split and zero opponent-profile items. Sonnet was reasoning about conditional football using only unconditional averages. Formation is the one dimension where the upstream provider genuinely lacked coverage (0.00–0.32); everything else conditional was available or derivable but not exposed.

**No hypotheses were ranked, filtered, or cherry-picked by V4 predictive outcomes.**
