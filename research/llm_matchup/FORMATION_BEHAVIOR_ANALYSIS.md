# Formation Behavior Analysis (`formation_policy_v1` / `formation_family_v1`)

Deterministic, historical-resolution analysis produced by
`src/research/llm_matchup/gen_formation_analysis.py`. No LLM calls. All numbers derive from
completed historical matches conditioned on the **resolved** (actually-played) formation.

Artifacts:
- `out/formation_profiles.csv` — per `(team, venue, resolved_formation, metric)` behavioral
  profile with `sample_n`, `team_baseline`, `formation_delta`, `reliability`.
- `out/formation_matchups.csv` — `(team_formation × opp_formation)` occupancy + mean for
  corner-relevant metrics at both `EXACT_x_EXACT` and `FAMILY_x_FAMILY` levels.
- `out/formation_information_gain.json` — variance-reduction measure (§33).
- `out/formation_analysis_summary.json` — headline numbers.

## 1. Coverage

- Resolved-formation lineup files: **1001**, all overlapping the corpus.
- Distinct exact formations observed: **21** (dominant `4-2-3-1` = 777 side-instances,
  `4-4-2` = 271, `4-3-3` = 191, `3-4-2-1` = 143, `4-1-4-1` = 132, `5-3-2` = 95, ...).
- `69` side-instances have a null formation → mapped to `UNKNOWN_FORMATION` (never fabricated).
- Profile rows: **6016**. Matchup rows: **609**.

## 2. Same formation ≠ same style (brief §5, §17) — the central finding

Teams playing the **same** nominal formation exhibit **radically different** measured
behavior. Home `crosses` under a resolved `4-2-3-1` (samples `n ≥ 5`):

| Team | Crosses / match (4-2-3-1, home) | n |
|------|-------------------------------:|---:|
| Athletic Club | 2.67 | 6 |
| Sheffield United | 3.00 | 7 |
| Burnley | 3.57 | 7 |
| Sunderland | 3.70 | 10 |
| … | … | … |
| Fulham | 6.50 | 6 |
| Leicester City | 6.50 | 6 |
| Córdoba | 7.83 | 6 |
| Chelsea | 8.80 | 5 |

A **3.3× spread** in crossing volume across teams that all nominally line up `4-2-3-1`.
This is the empirical justification for the mandate's rule: **formation is a conditioning
key, not a football explanation.** The engine must respond to the measured behavior under
the formation (`fc_*` / `formation_delta_*` evidence), never to the label. The B1
label-shuffle control tests whether Sonnet respects this.

## 3. Exact-cohort sparsity — why the hierarchy matters (brief §8)

| Cohort level | median n | max n |
|--------------|---------:|------:|
| `EXACT_x_EXACT` (formation × opp formation) | **3** | 346 |
| `FAMILY_x_FAMILY` | **20** | 668 |

Most exact formation-vs-formation cohorts are tiny (median 3). A naive "trust the exact
matchup" approach would massively overfit. The hierarchical shrinkage ladder in
`formation_evidence.formation_matchup()` (EXACT×EXACT → FAMILY×EXACT → EXACT×FAMILY →
FAMILY×FAMILY → VENUE_OVERALL → TEAM_BASELINE → COMPETITION_PRIOR) with a
`MIN_FORMATION_N = 3` usability floor and empirical-Bayes shrinkage guarantees a tiny exact
cohort cannot masquerade as strong evidence. In practice most estimates resolve at the
`FAMILY` or `VENUE_OVERALL` tier and are flagged `EXACT_FORMATION_SPARSE` /
`FORMATION_FAMILY_ONLY`.

## 4. Does formation carry information beyond team/venue? (brief §33)

Variance-reduction measure: fraction of within-`(team, venue)` behavioral variance
explained by additionally conditioning on the resolved formation.

| Metric | Variance explained by formation | n_obs |
|--------|-------------------------------:|------:|
| possession | 31.7 % | 1645 |
| clearances | 30.8 % | 1645 |
| corners | 23.6 % | 1644 |
| total_shots | 23.8 % | 1645 |
| crosses | 23.4 % | 1645 |
| blocked_shots | 21.5 % | 1645 |
| touches_in_box | 21.1 % | 1531 |

**Caveat (important):** formation-conditional groups are small (many `n ≤ 2`), so this is
an **optimistic upper bound** — some of the "explained" variance is overfitting to tiny
groups. It should be read as *"formation plausibly carries real information about behavior,
especially for possession and clearance load"*, not as a calibrated effect size.

## 5. Answering the two scientific questions (brief §34)

- **RESOLUTION question** — *Does knowing the historical formation help organize football
  mechanisms?* **Provisional YES.** Same-formation behavioral spread is large and
  systematic per team; conditioning on formation reduces behavioral variance by ~21–32 %
  (upper bound). Formation is a useful organizing/conditioning variable.
- **FORECAST question** — *Can we estimate tomorrow's formation accurately enough before
  kickoff to improve prediction?* **Open.** This data source has **no announcement
  timestamp**, so historical pre-match availability is UNPROVEN. A projection baseline
  (mode of prior resolved formations) exists in the harness but is not validated for
  forecast accuracy. This is deferred to Phase C (see `PHASE_B_PLAN.md` §9 scenarios).

These two questions must not be conflated: resolved formation is football-resolution
evidence; pre-match formation is a forecast input.

## 6. Family mapping stability

`FORMATION_FAMILY_V1.json` maps all 21 observed formations deterministically (table +
digit-structure derivation) with no club/league knowledge. Verified in
`tests/research/test_formation_policy.py::test_family_mapping_is_deterministic_and_total`.
Family occupancy across the 1001 lineups: `BACK4_1STRIKER` 1152, `BACK3_WINGBACK` 316,
`BACK4_2STRIKER` 294, `BACK5_DEFENSIVE` 144, `UNKNOWN_FORMATION` 69, `BACK3_OTHER` 27.
