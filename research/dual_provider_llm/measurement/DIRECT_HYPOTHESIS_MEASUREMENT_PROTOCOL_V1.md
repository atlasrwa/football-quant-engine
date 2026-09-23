# Direct Hypothesis Measurement Protocol V1

**Status:** design frozen. No historical effect has been computed.
**Next step:** run the gated runner, and only after explicit authorization.

This protocol compiles the six frozen ChatGPT hypotheses (`CHATGPT_HYPOTHESES_V1.json`, sha256 `989557336d24…605b`) into deterministic historical measurements. The LLM's role ended when it proposed the questions. Every number in the apparatus is a named constant in `src/research/dual_provider_llm/measurement/support.py`, each with a written rationale. The hypotheses contain no numeric parameters. Numbers that appear in their prose (window labels such as `RECENT_5`) are recorded and never used.

The machine-readable specs are in `DIRECT_HYPOTHESIS_QUERY_SPECS_V1.json`. This document explains them.

**What this measures and what it does not.** Each measurement is historical evidence about whether a pattern existed in past matches. It is not a forecast of Girona v Albacete, not a probability and not a model. The target match's result and statistics are never loaded.

## 1. Universe and point-in-time rules

- **Data.** TheStatsAPI finished league matches in the local cache: the same sources and conflict exclusions as the pilot packet, plus the two fetched gap matches, whose hashes must equal those recorded in the packet.
- **Global cutoff.** Only matches with kickoff strictly before the target kickoff (`cutoff_unix` 1790361000) are loaded. The target fixture id is removed explicitly as well.
- **Per-match cutoff.** For a historical subject match at kickoff *t*, the opponent profile, the scaling reference and the strength proxy all use only matches strictly before *t*. There are no season-level or retrospective aggregates.
- **Query point.** The target's own profile or state is built with the identical rule at the target kickoff.

## 2. Scaling and competition

**Competition policy: B, competition-standardized.** Each observation is converted to a robust z-score within its own competition:

> (value − median) / (1.4826 × MAD)

- The median and MAD come from that competition's team-match values over matches strictly before the query time.
- At least 200 reference values are required; otherwise the observation is unscaleable and counts as missing.
- If MAD is 0, the fallback scale is IQR/1.349.
- A conceded (AGAINST) value is scaled against the same metric's distribution, because it is the producing side's FOR value.
- DP4 and DP5 standardize within competition × venue.

This makes LaLiga and LaLiga 2 values comparable as "relative to their league". It does **not** correct a team's own change of regime on promotion or relegation; see §8.

## 3. Similarity, neighbours and missingness

- **Profile.** The mean z of each dimension over the team's last 10 venue-matched prior matches. Each dimension needs at least 5 non-null values, and all dimensions are required. There is no imputation and no partial profile.
- **Distance.** Robust-standardized Euclidean, taken as the RMS over dimensions: `sqrt(mean_j (p_j − q_j)²)`.
- **Neighbours.** The nearest max(10, ⌈n/3⌉) eligible subject matches, with ties broken by (distance rounded to 12 decimals, kickoff, match_id). The rest form the comparison group. The tercile is the engine's domain-neutral grid, not a tuned value.
- **Why last-10 and not ALL_PRIOR.** The frozen evidence refs cite `ALL_PRIOR.HOME/AWAY`, but the length of ALL_PRIOR depends on when the corpus starts. The same last-10 rule is therefore used for the query point and for every historical profile. This divergence is recorded in each affected spec.
- **Missingness.** NULL ≠ ZERO throughout.
  - A subject match with any null output metric is ineligible.
  - A required metric that is non-null in under 80% of candidates makes the measurement `UNSUPPORTED_METRIC`.
  - Unknown metrics, and `blocked_shots`, raise an error (fail closed).

## 4. Support, frozen before any measurement

| Rule | Value | Applies to |
|---|---|---|
| MIN_SUBJECT_MATCHES | 30 eligible | every neighbour or group design; DP3's low-possession set |
| MIN_SIMILAR_MATCHES | 10 per group | neighbour and comparison groups |
| MIN_OBS_PER_PARAMETER | 10 | DP2's 4-parameter interaction model, so ≥ 40 matches, including its neighbour-subset secondary |
| MIN_PROFILE_MATCHES_PER_DIM | 5 of 10 | every profile dimension |
| MIN_LONG_RUN_MATCHES | 20 | DP5's long-run reference |
| MIN_METRIC_COVERAGE | 0.8 | every required metric |

Failing any rule returns an explicit `INSUFFICIENT_SUPPORT`, `UNSUPPORTED_METRIC` or `NO_QUERY_PROFILE` status. Such a result is legitimate.

## 5. Opponent strength

**Definition.** The opponent's mean goal difference over its last 10 same-competition matches before the subject match, with at least 5 required, otherwise the value is missing.

**Use.** Neighbour-vs-comparison balance diagnostics and strength-adjusted secondaries only. It **never** gates eligibility, so promoted and relegated opponents are not silently dropped. Closing odds and standings are not used.

## 6. The six measurements

| ID | Population | Primary statistic | Null (10,000 resamples, seed 0) | In BH |
|---|---|---|---|---|
| DP1 box pressure | Girona HOME | mean z(corners, shots, SoT), neighbours − comparison. Opponent away profile: possession, box touches, inside-box shots, corners (all conceded) | group-label permutation | yes |
| DP2 wide × central | Girona HOME | coefficient on x1·x2 in z(corners) ~ 1 + x1 + x2 + x1·x2, where x1 = z(accurate crosses) and x2 = z(box touches). Continuous product, no thresholds | Freedman–Lane residual permutation | yes |
| DP3 direct progression | Albacete AWAY, own possession z < 0 (below the competition median) | Spearman ρ(mean z(long balls, final-third entries), mean z(shots, corners)) | outcome permutation | yes |
| DP4 territorial regime | Girona HOME, **excluding** the matches that define the reference states | residual of output on territory: mean in the k matches nearest the shrunk recent state S, minus mean in the k nearest R10 among the rest. S = R10 + n5/(n5+5)·(R5 − R10) | group-label permutation | yes |
| DP5 recent expansion | Albacete AWAY | opponent-adjusted territorial state: shrunk recent 5 away matches minus the long-run away state, averaged over the 4 dimensions | none. Percentile among **disjoint** historical 5-match blocks, **descriptive only** | **no** |
| DP6 pressure resolution | Girona HOME | resolution contrast z(corners) − mean z(SoT, big chances), neighbours − comparison. Opponent away profile: clearances, box touches conceded, shots conceded, inside-box shots conceded | group-label permutation | yes |

- Two-sided permutation p-value: (1 + #|T\*| ≥ |T|) / (1 + 10,000).
- Benjamini–Hochberg at q = 0.10 is applied across the five inferential primaries, and all five are reported.
- DP5 has no valid exchangeable null, because one team's blocks are not exchangeable. It is reported as descriptive and kept outside the BH family.

Design notes:
- **DP3.** "Direct progression" is an observational label for a statistical combination. No tactical intent is inferred.
- **DP5.** Only the three frozen similarity dimensions are opponent-adjusted; corners stay unadjusted because they are not a frozen dimension. Shrinkage uses κ = 5, and the state distance is the RMS.
- **DP6.** `blocked_shots` is never used, preserving the frozen restriction.
- **DP1 and DP4.** Both use `shots`, which the hypothesis names only in prose ("…corners, shots and shots on target"; "corner/shot behavior"). The quote is recorded and checked by the compiler.

### 6.1 Pre-execution implementation amendment: fixed BH family

`PRE_EXECUTION_IMPLEMENTATION_AMENDMENT` (made before any real-data run; not a scientific redesign).

The BH family is always the frozen five: DP1, DP2, DP3, DP4 and DP6 (`N_FROZEN_BH_TESTS = 5`). It never shrinks because of runtime support status.

Non-evaluable frozen family members are represented by p = 1.0 solely for multiplicity bookkeeping, so the preregistered family size stays fixed. A member is non-evaluable when it returns `INSUFFICIENT_SUPPORT`, `UNSUPPORTED_METRIC` or `NO_QUERY_PROFILE`. It is then recorded as:
- `primary_p_value = null`
- `bh_input_p = 1.0`
- `multiplicity_placeholder = true`
- plus its fixed-family `bh_q`

Its interpretation is **not evaluable under the frozen support rule**. It is never evidence for the null.

The results report `N_BH_EVALUABLE` and `N_BH_NON_EVALUABLE`. DP5 stays descriptive and outside the family.

The earlier runner built the family from members with status OK only. That was an implementation defect, corrected here. No design element changed.

## 7. Confounders

| Confounder | How it is handled |
|---|---|
| Venue | restricted to the frozen wording |
| Competition | z-scored |
| Opponent strength | diagnostic and adjusted secondary |
| Opponent style | the profile itself, where the hypothesis defines one |
| Season | composition reported per group |
| Cards | not a frozen variable of any hypothesis; not used |
| Score state, lineups, injuries | unavailable (no half-level data in the pilot; lineups and injuries are out of scope); recorded as unhandled |

## 8. Interpretation limits

1. **Girona's regime.** About 38 of Girona's roughly 41 prior home matches are LaLiga. DP1, DP2, DP4 and DP6 therefore describe *LaLiga-era Girona* queried with a LaLiga 2 opponent. Competition z-scoring does not remove this.
2. **Same-match associations.** DP2, DP3 and DP4 relate covariates and outputs from the same match. They are associations, not pre-match predictors, and not causal.
3. **Provider semantics.**
   - DP2: `accurate_crosses` may include corner deliveries, and `touches_in_box` may include set-piece touches, so part of the association may be mechanical or even reversed.
   - DP3: final-third entries mechanically feed shots.
   - DP6: SoT and big chances overlap, so the contrast compares standardized levels, not shares.
4. **DP5.** The recent away block spans the summer break.
5. **Redundancy.** DP1 and DP6 share their population and 2 of 4 profile dimensions (box touches and inside-box shots conceded), so their neighbour sets will overlap heavily. They are kept as separate tests because their outputs differ: pressure level versus pressure resolution.

## 9. Execution gate

```
python -m src.research.dual_provider_llm.measurement.executor --authorized-head <HEAD>
```

The runner refuses to load real data unless HEAD equals the authorized commit and the worktree is clean. It has **not** been executed. Results would be written to `research/dual_provider_llm/measurement/out/DIRECT_HYPOTHESIS_MEASUREMENT_RESULTS_V1.json`.
