# V4 — Hypothesis-Derived Deterministic Measurement → Statistical OOS Validation

**Preregistration (design + zero-spend validation only).** Proceeds from
`V3_HYPOTHESIS_MEASUREMENT_READY_FOR_STATISTICAL_VALIDATION`.

**Spend so far: $0.00.** No Bedrock call, no LLM call, no network read, no final OOS
scoring. This document is the *design*; the final statistical experiment is NOT run here
and MUST NOT run until this design is frozen and the zero-spend gates below pass.

**Scientific question (verbatim from mandate).** *Do deterministic measurements derived
from the frozen LLM hypotheses provide stable incremental predictive information in
walk-forward out-of-sample football forecasting beyond appropriate existing quantitative
baselines?*

The LLM is **not** the object under test. The object under test is the **deterministic
quantitative feature** produced from the hypothesis families. Architecture unchanged:

```
LLM hypothesis → deterministic historical measurement → statistical validation
    → possible candidate feature → quant model → calibration → p_model
```

This task stops **before** promotion. `SONNET46_HYPOTHESIS_V3 = FAIL` stands untouched;
CHAMPION (`pilotC_stat_mixer`, artifact sha `0b8f5ff3…`) is read-only; no V2/V3 frozen
artifact is modified; no feature is promoted.

---

## 0. Freeze the anti-selection rule (mandate §1) — stated first, before any other content

The descriptive measurement results in `V3_HYPOTHESIS_MEASUREMENT_REPORT.md` **have
already been observed** (§11: sign split 79+/57−, median difference +0.20, median
|diff|/SE 0.764, per-family |diff|/SE). Therefore, frozen for this stage and enforced in
code:

> **ELIGIBILITY IS STRUCTURAL ONLY.** No hypothesis, family, transform, target, or market
> may be included or excluded on the basis of: conditional-minus-comparison difference;
> its sign; its magnitude; |difference|/SE; apparent significance; or whether the football
> story "looks successful". The only admissible selectors are the six structural gates
> already frozen in `_recommend_next_stage.py` (measurable rate, coverage, sample N,
> distinctness, provider consistency, PIT safety), none of which contains an effect term.

This rule is asserted by a test (`test_v4_no_effect_selection`, §17) that scans the frozen
preregistration artifact and fails if any eligibility field is a function of an observed
effect quantity. The family set below (`opponent_profile`, `unconditional_behavioral_profile`,
`venue`) is inherited **unchanged** from the frozen V3 recommendation — it is not
re-derived from the effect table.

---

## 1. Exact candidate corpus / families (deliverable 1)

Inherited verbatim from `out/v3_hypothesis_measurement/next_stage_recommendation.json`
(`v3_next_stage_eligibility_v1`). No family is added, dropped, or re-ranked here.

| Family | Role in V4 | plans | measured | measurable rate | median cond. N | Structurally eligible |
|---|---|---|---|---|---|---|
| `opponent_profile` | **Primary research target** | 53 | 52 | 0.981 | 14 | YES |
| `unconditional_behavioral_profile` | **Behavioral comparator / negative-control family** | 19 | 16 | 0.842 | 14 | YES |
| `venue` | **Secondary**, only after the tautology exclusion (§3) | 80 | 66 | 0.825 | 28 | YES (conditionally) |
| `formation` | Excluded | 5 | 1 | 0.200 | 8 | no — corpus coverage |
| `meaningful_multi_condition` | Excluded | 1 | 1 | 1.000 | 11 | no — n=1 generator limit |

`formation` and `meaningful_multi_condition` remain excluded for the exact structural
reasons frozen in V3 (corpus formation coverage 0.013–0.250; a single frozen interaction
example). No additional interaction hypotheses are manufactured.

**Frozen opponent_profile candidate inventory (the actual MEASURED records, 53 across 10
fixtures, 36 distinct hypotheses).** Enumerated so the candidate set cannot silently grow:

- Axes used: `accurate_crosses_for` (12), `shots_on_target_for` (11), `possession_for` (8),
  `goals_against` (8), `corners_against` (5), `shots_on_target_against` (4),
  `accurate_crosses_against` (3), `fouls_for` (2), `corners_for` (1).
- Bands used: `HIGH` (44), `LOW` (10). No MID hypothesis was generated.
- Comparison cohort: `SUBJECT_OVERALL_BASELINE` (54/54). No opponent_profile hypothesis
  used any other baseline — so the venue-tautology (§3) cannot arise *within* this family,
  but the compatibility rule is still installed globally.
- Target metrics × side: `big_chances` FOR 10 / AGAINST 4, `corners` FOR 5 / AGAINST 1,
  `shots_on_target` FOR 5 / AGAINST 3, `accurate_crosses` FOR 3 / AGAINST 4,
  `shots_inside_box` FOR 1 / AGAINST 3, `touches_in_box` AGAINST 3, `yellow_cards` FOR 3,
  `clearances` FOR 2, `goals` FOR 1 / AGAINST 1, `tackles` FOR 1, `final_third_entries`
  FOR 1 / AGAINST 1, `possession` FOR 1.

This inventory is the source of the identifiability problem in §7 and §18.

---

## 2. Contamination / hindsight-risk analysis (deliverable 2)

Three distinct contamination surfaces, treated separately.

### 2.1 Post-measurement selection (addressed in §0)
Mitigated structurally: family set frozen from V3, no effect term in any gate, asserted by
test.

### 2.2 Hypothesis-origin hindsight (mandate §8) — the dominant risk
The V3 battery sent 12 reference-arm packets; 11 survived whole-response gating (seq 11 was
rejected). The **11 clean origin fixtures** — `mt_010243515, mt_010243537, mt_010243938,
mt_010244159, mt_010244193, mt_010441320, mt_010441491, mt_010444904, mt_012232295,
mt_012232411, mt_013233190` — **generated** the hypotheses. The families were discovered
using those specific fixtures' evidence packets. Two designs are possible:

- **A. Exact frozen hypotheses on their originating fixtures only.** Scientifically clean
  for *description* (this is exactly what §14 of the measurement report did) but yields
  n = 10 fixtures — far too few for a walk-forward predictive OOS test, and every one of
  those fixtures is a hypothesis-origin fixture, so there is no uncontaminated fold.
- **B. Hypothesis *templates/families* evaluated walk-forward across the historical
  corpus.** A *family template* is `(condition dimension, axis, band, target metric, side,
  comparison, window)` with the subject/opponent identities and cutoff **re-bound at each
  historical fixture**. This is what predictive OOS requires.

**V4 uses B, with an explicit origin-quarantine protocol so the 11 clean origin fixtures
(plus the rejected seq-11 fixture, quarantined for completeness → 12 fixture ids total)
cannot contaminate earlier folds:**

1. **Template extraction is identity-blind.** A template carries no fixture id, no club, no
   date, no observed difference/sign/magnitude — only the structural tuple above. A test
   asserts the frozen template set contains none of those fields (`test_v4_templates_are_identity_blind`).
2. **All V3 origin fixture ids are removed from the evaluation universe entirely.** They
   are the generator's training evidence; they never appear in any train or test fold. This
   is stricter than temporal quarantine because origin leakage is not purely temporal (a
   template discovered from a *late* origin fixture must not be evaluated on an *earlier*
   fold either). Enforced by `test_v4_origin_fixtures_excluded`.
3. **Templates are applied prospectively within the walk-forward.** For fold *k*, a
   template's feature at fixture *F* is computed from matches strictly before *F*'s kickoff
   (§7), and the model that consumes it is fit on the train vintage of fold *k* only. The
   template *definition* is frozen once, before fold 1, from the origin fixtures — it is a
   fixed function, not refit per fold, so no post-fold information re-shapes it.
4. **The template family is small and pre-declared** (§13 multiplicity). Because bands are
   only HIGH/LOW and axes are a closed set, the template space is enumerable and frozen.

Residual, disclosed risk: the *choice of which axes/metrics to templatize* still descends
from what Sonnet happened to propose on 12 fixtures. V4 does not claim this is eliminated;
it is bounded by (a) identity-blindness, (b) origin-fixture exclusion, and (c) treating the
whole exercise as **exploratory** unless the confirmatory gate (§15) is met on the single
pre-declared primary contrast. This is stated in the multiplicity inventory rather than
hidden.

### 2.3 Band-drift / estimand contamination
`PROFILE_BAND_SEMANTICS = "AS_OF_TARGET_CUTOFF"` (frozen in `cohort_measurement.py`). Bands
are resolved once, at each evaluation fixture's cutoff, from candidates strictly before it.
The alternative (re-band at each cohort match's kickoff) is a different estimand that no
module validates; V4 does not use it. This is preregistered, not chosen after the fact.

---

## 3. Resolve the venue tautology structurally (mandate §3, deliverable — venue rule)

V3 measurement found all 7 `SUBJECT_VENUE_BASELINE` plans degenerate: conditioning on venue
and comparing against the same-venue baseline yields an **identical** conditional and
comparison match set (`NOT_DISTINCT`). This is a property of construction, not statistics.

**Frozen rule (`baseline_compatibility_v1`, installed in the downstream research layer
only — NOT in any frozen V3 module):** a comparison baseline may not absorb the same
conditioning dimension the candidate conditions on.

```
INCOMPATIBLE if  conditioning_dimension ∈ dimensions_absorbed_by(comparison_baseline)
```

with the frozen absorption map:

| comparison baseline | absorbs dimension |
|---|---|
| `SUBJECT_VENUE_BASELINE` | `venue` |
| `SUBJECT_COMPETITION_BASELINE` | `competition` |
| `SUBJECT_OVERALL_BASELINE` | (none — always distinct unless unconditioned) |
| `LEAGUE_ENVIRONMENT_BASELINE` | (different population; never absorbs) |
| `SUBJECT_RECENT_VS_LONG_BASELINE` | (window contrast; absorbs no condition dimension) |

Any candidate whose conditioning dimension is absorbed by its comparison is typed
`NOT_DISTINCT_BY_CONSTRUCTION` **before** any data is read, and excluded from V4. It is not
reinterpreted statistically. Implemented in `src/research/hypothesis_oos/compatibility.py`;
asserted by `test_v4_venue_tautology_excluded_by_construction`.

Consequence for V4: because every eligible `opponent_profile` and
`unconditional_behavioral_profile` candidate uses `SUBJECT_OVERALL_BASELINE`, none is
excluded by this rule. The `venue` family's degenerate combination is excluded by
construction, leaving its `SUBJECT_OVERALL_BASELINE` venue candidates only.

---

## 4. Competition-baseline caveat (mandate §4)

`SUBJECT_COMPETITION_BASELINE` is unit-tested but was **exercised zero times** against the
corpus (V3 report §6). V4 does not assume production validity from unit tests.

- No eligible V4 candidate uses `SUBJECT_COMPETITION_BASELINE`, so it is **not required**
  for the primary experiment.
- It is therefore **excluded from V4 by structural reason**: "zero real-data exercise in
  the eligible corpus; not needed by any eligible candidate." Recorded in the frozen
  artifact under `excluded_baselines`.
- A zero-spend deterministic real-data smoke (`test_v4_competition_baseline_realdata_smoke`)
  is still provided so a *future* stage that needs it has a validation entry point; it runs
  the baseline over historical examples and asserts a distinct, populated comparison cohort.
  This is a readiness check, not a V4 inclusion.

---

## 5. Candidate quantitative representation (deliverable 4)

Each eligible template becomes a quantitative feature **without any LLM numerical
judgment**. Every quantity is a pure deterministic function of the PIT cohort. The
**smallest scientifically defensible representation** is preferred; no feature zoo.

**Frozen primary representation — 1 feature per template:**

| feature | definition | source |
|---|---|---|
| `hd_shrunk_diff` | shrunk (conditional mean − comparison mean), shrinkage `n/(n+6)` | `cohort_measurement.execute().shrunk_difference` |

**Frozen secondary representations (used only in the pre-declared ablation, §13), 3
additional:**

| feature | definition | rationale |
|---|---|---|
| `hd_shrunk_cond_mean` | shrunk conditional mean toward the comparison mean | level, not contrast |
| `hd_cond_n` | conditional cohort usable N | reliability signal (raw count, not effect) |
| `hd_available` | 1 if outcome==MEASURED else 0 | missingness indicator (preregistered, §10) |

**Explicitly excluded** to avoid a feature zoo and post-hoc transform selection:
conditional/comparison ratio (undefined/unstable for signed and near-zero metrics like
goal difference), profile-band membership as a raw one-hot (redundant with the axis that
generated it), and any interaction of the above. All four representations are computed
**as-of each prediction cutoff** (§7); none uses full-sample statistics. The choice of
representation is frozen here, before OOS, and is not a function of any observed
performance.

---

## 6. Shrinkage design (deliverable 5)

Reuse the canonical machinery verbatim — no new shrinkage parameter is invented:

| constant | value | canonical source |
|---|---|---|
| `SHRINK_K` | 6.0 | `llm_matchup/cohorts.py:28` = `measurement.py:38` |
| band `MIN_PRIOR_MATCHES` | 4 | `similarity.py:122` |
| `MIN_CONDITIONAL_N` | 4 | `measurement.py:41` |
| `MIN_COMPARISON_N` | 8 | `measurement.py:42` |

Shrinkage is: deterministic; frozen before OOS; computed from history/training vintage
only (the cohort is built strictly before the fixture cutoff); PIT-safe by construction
(§7). `SHRINK_K` is **not tuned against OOS**. If a future stage wants to tune it, that
requires an explicitly nested-training design (an inner `TimeSeriesSplit` on the train
fold only); V4 does not do this and freezes `SHRINK_K = 6.0`.

---

## 7. PIT-safe walk-forward reconstruction (deliverable 3, mandate §7)

**V4 does NOT attach the already-measured V3 values to outcomes.** For every historical
prediction fixture *F* in the OOS experiment, the hypothesis-derived feature is
**reconstructed from scratch** using only matches with `kickoff_unix < F.kickoff_unix`.

Enforced identically to the V3 measurement stage (which passed a clean PIT audit, 0
violations, closest observation −3.98 days), in three independent places already in code:
`HistoryIndex.prior` (strict `<`), explicit target-fixture exclusion in the observation
builder, and the `LEAKAGE_REJECTED` backstop inside `cohort_measurement.execute`.

The target fixture never enters its own feature. Future fixtures never influence: profile
bands (resolved from candidates strictly before *F*), similarity, cohort statistics,
shrinkage, reliability, or normalization. This includes deterministic opponent-profile
construction — `resolve_band` takes the cutoff as a required argument and every candidate
is filtered on it. Boundary case `kickoff == cutoff` is a violation (rule is strict `<`)
and is tested positively (§17).

---

## 8. Target mapping (deliverable 7, mandate §11) — the decisive section

Existing verified predictive targets (CHAMPION / `matchup/design.py::outcome`) are **match
totals over a line**: `goals` {1.5,2.5,3.5}, `corners` {8.5,9.5,10.5}, `cards` {3.5,4.5},
`btts`. These are the only outcome semantics V4 may use; no new outcome is invented.

The frozen `opponent_profile` MEASURED candidates target **single-team, side-specific
process metrics**, tallied in §1:

- **Process/mechanism metrics with NO validated betting target** (9 of 12 distinct target
  metrics): `big_chances`, `shots_on_target`, `shots_inside_box`, `touches_in_box`,
  `accurate_crosses`, `final_third_entries`, `possession`, `clearances`, `tackles`.
  Together these are **~40 of the 53** MEASURED opponent_profile candidates.
- **Metrics that touch a validated market but only as a single side** (3 of 12):
  `corners` (FOR 5 / AGAINST 1), `goals` (FOR 1 / AGAINST 1), `yellow_cards` (FOR 3). The
  betting target is the **match total** (home+away); the candidate measures **one team's
  FOR or AGAINST** conditioned on the opponent's band. These are related but not identical
  estimands.

**Frozen mapping policy:**

| candidate target | classification | V4 use |
|---|---|---|
| `corners` FOR/AGAINST | `MAPS_TO_VALIDATED_TARGET_VIA_SIDE_AGGREGATION` | eligible for the corners market as a **contextual feature added to B1**, not as the target itself |
| `goals` FOR/AGAINST | `MAPS_TO_VALIDATED_TARGET_VIA_SIDE_AGGREGATION` | eligible for goals market, same treatment |
| `yellow_cards` FOR | `MAPS_TO_VALIDATED_TARGET_VIA_SIDE_AGGREGATION` | eligible for cards market, same treatment |
| all 9 process metrics | `NO_VALIDATED_PREDICTIVE_TARGET` | classified as **scientifically-interesting-but-not-yet-predictive**; NOT forced into a market; recorded and set aside |

The mandate is explicit: *"If a hypothesis metric does not map cleanly to a validated
predictive target, classify it separately rather than forcing it into one. The
deterministic measurement may be scientifically interesting without yet being a predictive
feature."* V4 obeys this literally. The 9 process metrics are **not** re-labelled as
"expected goals proxies" or coerced into the goals model.

**The predictive V4 candidate feature is therefore narrow:** for each of the three markets
(corners, goals, cards) that a frozen opponent_profile target touches, a single feature
`hd_shrunk_diff` built from the *side-appropriate* opponent-profile template, added on top
of B1. Both the subject's FOR and the opponent-analog AGAINST templates aggregate to a
match-total-oriented contextual signal via the existing `matchup` A-attack⊕B-defence
convention (`design.py::f_matchup`), so the feature is expressed in the same match-total
frame the champion predicts.

---

## 9. Baselines / challenger definitions (deliverable 6, mandate §9)

Reuse the existing walk-forward OOS harness (`src/research/matchup/harness.py`,
`design.py`) — the same one that produced `FINAL_RESEARCH_REPORT.md`. No parallel evaluator.

| model | definition |
|---|---|
| **B0** | base-rate / champion-parity (`f_champ`, F0). Immutable comparison point. |
| **B1** | conventional quantitative model: `f_champ + f_matchup + f_league_env + f_home_away` — the existing raw-stat / matchup / context features with **no** LLM-derived measurement. This is the goals/cards candidate that already reached `CANDIDATE_WORTH_PROSPECTIVE_TEST`, so it is a genuinely strong baseline, not a strawman. |
| **B2** | B1 **+** the single hypothesis-derived feature `hd_shrunk_diff` for the market's mapped opponent_profile template(s). |

**The key comparison is B2 vs B1** (incremental information of the LLM-derived measurement
over strong existing quant features), not B2 vs B0 and not B2 in isolation. B2 − B0 and
B1 − B0 are reported as context only.

Challenger status: **research challenger**. CHAMPION is read-only (§10). No auto-promotion.

---

## 10. CHAMPION protection (mandate §10)

CHAMPION artifact (`data/discovery/pilotC_stat_mixer.json`, sha `0b8f5ff3…`) and its
scripts are **not modified**. If CHAMPION predictions are used as a benchmark they are read
without mutation from `research/evaluation/champion_walk_forward_oos.json`. No automatic
promotion is permitted regardless of the V4 result. V4 writes only under
`research/hypothesis_oos/` and `src/research/hypothesis_oos/`.

---

## 11. Confounder treatment (deliverable 9, mandate §12)

For `opponent_profile` the frozen confounder set (from `confounder_inventory.json`) is:
opponent strength, team strength, venue, competition, historical sample size, score state,
and **band drift**, plus **profile-selection effects**. No causal claim is made
(`association_type` stays `DESCRIPTIVE_ASSOCIATION` → at most `CONFOUNDER_ADJUSTED_EFFECT`
after adjustment; never causal).

Adjustment strategy in V4: the predictive question is *incremental information after
existing features account for context*. B1 already contains team/opponent strength
(`f_matchup`, rolling FOR/AGAINST), venue (`f_home_away`), and competition environment
(`f_league_env`). Therefore **B2 − B1 is itself the confounder-adjusted test**: any
apparent lift from `hd_shrunk_diff` must survive the presence of the conventional context
features. Historical sample size enters as the preregistered `hd_cond_n` in the ablation
only. Band drift and profile-selection are handled by construction (§2.3, §7) and the
negative controls (§14), not by a regression covariate.

---

## 12. Missingness / coverage policy (deliverable 10, mandate §17)

Candidate contextual features are frequently unavailable (a template requires a bandable
opponent, a sufficient conditional cohort, and a distinct comparison). Frozen before
evaluation:

| state | trigger | handling |
|---|---|---|
| `SUFFICIENT_MEASUREMENT` | `MEASURED` | use `hd_shrunk_diff` |
| `INSUFFICIENT_HISTORY` | `INSUFFICIENT_DATA` | feature absent |
| `NOT_DISTINCT` | identical cohorts | feature absent (and excluded by §3 if by construction) |
| `UNSUPPORTED` | corpus cannot answer | feature absent |
| `MISSING_PROVIDER_EVIDENCE` | opponent unbandable / null | feature absent |

**No favorable neutral value is silently imputed.** When the feature is absent, the model
receives it as NaN and the harness's train-only median imputation applies (the same
convention B1 uses for any missing feature) **and** the preregistered binary `hd_available`
records availability. Because `hd_available` is a feature, it is preregistered here (mandate
§17). A test asserts absence never resolves to a value that biases the contrast toward zero
difference on the favorable side (`test_v4_missingness_not_favorable`).

---

## 13. Multiplicity inventory (deliverable 13, mandate §16)

Enumerated **before** testing; kept deliberately small.

| axis | count | frozen choice |
|---|---|---|
| families | 3 | opponent_profile (research), unconditional (control), venue (secondary) |
| markets | 3 | corners, goals, cards (only those a frozen opponent_profile target touches) |
| target metrics | mapped only | side-aggregated to the market total (§8) |
| transforms | 1 primary + 3 ablation | `hd_shrunk_diff` primary; mean/N/available in ablation |
| candidate features per B2 cell | 1 | one `hd_shrunk_diff` per market |

**Confirmatory vs exploratory labelling (frozen):**

- **Confirmatory (exactly ONE pre-declared primary contrast):** `opponent_profile`,
  `corners` market, `hd_shrunk_diff`, **B2 vs B1**, pooled ΔLogLoss with block-bootstrap CI.
  Corners is chosen as primary **not** on any observed V3 effect but on the structural
  fact that it is the frozen opponent_profile target metric with the most MEASURED
  candidates (`corners` FOR/AGAINST = 6) that also maps to a validated market — a
  pre-data, structural criterion, recorded as such.
- **Exploratory (everything else):** goals and cards markets; all ablation transforms; the
  `unconditional` and `venue` families; per-league and per-fold breakdowns. These are
  reported with effect estimates and CIs but explicitly labelled EXPLORATORY, and a
  Benjamini–Hochberg FDR note is applied across the exploratory family using the existing
  `src/research/fdr/` machinery.

No "pick the best market/family after seeing OOS results and call it confirmed." The single
confirmatory contrast is frozen now.

---

## 14. Negative controls (deliverable 11, mandate §18)

All PIT-safe, none built from future outcomes:

1. **Irrelevant-axis control.** Build `hd_shrunk_diff` from an opponent-profile axis that
   is *structurally unrelated* to the market (e.g. `fouls_for` band for the **corners**
   market). If B2 improves as much with an irrelevant axis as with the mapped axis, the
   apparent lift is generic added-feature capacity, not hypothesis-specific context.
2. **Unconditional behavioral comparator.** The `unconditional_behavioral_profile` family
   feature added to B1 in place of the opponent_profile feature. Isolates "conditioning on
   the opponent's band" from "adding any behavioral summary."
3. **Label-preserving band shuffle (PIT-safe).** Permute the band→opponent assignment
   *within the pre-cutoff candidate pool only*, holding the marginal band sizes fixed, so
   the feature retains its distribution but loses its correspondence to the actual opponent.
   Seeded, deterministic, computed strictly before each cutoff. Never touches outcomes.

A positive confirmatory result is credible only if it **exceeds** all three controls. This
is a frozen acceptance condition, not a post-hoc filter.

---

## 15. Uncertainty method (deliverable 12, mandate §15) — frozen before evaluation

**Paired block bootstrap of ΔLogLoss(B2 − B1) over competition blocks, 400 resamples**, the
exact method already used in `FINAL_RESEARCH_REPORT.md` / `UNCERTAINTY.csv`. Football-data
dependence is respected by resampling **whole competition blocks** rather than individual
predictions (predictions cluster by fixture/team/competition). Both **pooled** and
**fold-level** ΔLogLoss are reported.

Classification bands are inherited verbatim: CLEAR / PROMISING / MARGINAL / INCONCLUSIVE /
NEGATIVE. The method is fixed **now** and is not chosen after seeing which gives the most
favorable interval.

---

## 16. Evaluation metrics (deliverable 14)

Primary: **Log Loss** and **Brier**. Also reported: calibration slope/intercept and **ECE**;
discrimination (AUC, probability dispersion); prediction count / coverage; **fold-level**
results; **per-league** breakdown where N supports it. `summarize()` in the existing harness
already emits all of these.

Primary scientific comparison: **incremental OOS ΔLogLoss = B2 − B1**, pooled and
fold-level, with the §15 CI. Hit rate / directional accuracy is reported but is **not** the
criterion.

---

## 17. Zero-spend tests proving no leakage (deliverable 17)

Frozen, all `$0.00`, no Bedrock, no network. New suite
`tests/research/hypothesis_oos/test_v4_preregistration.py`:

1. `test_v4_no_effect_selection` — the frozen preregistration artifact contains no
   eligibility field that is a function of an observed difference/sign/magnitude/|diff|/SE.
2. `test_v4_templates_are_identity_blind` — no template carries fixture id, club, date, or
   any observed effect quantity.
3. `test_v4_origin_fixtures_excluded` — the V3 origin fixture ids appear in no train/test
   fold.
4. `test_v4_pit_strict_less_than` — reconstruction refuses `kickoff == cutoff` and
   `kickoff > cutoff`; the leaked-row-flips-result positive test.
5. `test_v4_venue_tautology_excluded_by_construction` — any candidate whose conditioning
   dimension is absorbed by its comparison is `NOT_DISTINCT_BY_CONSTRUCTION` before data.
6. `test_v4_competition_baseline_realdata_smoke` — zero-spend real-data exercise of
   `SUBJECT_COMPETITION_BASELINE`; readiness only.
7. `test_v4_missingness_not_favorable` — absent feature never imputes a favorable value.
8. `test_v4_champion_readonly` — champion artifact sha unchanged; V4 opens it read-only.
9. `test_v4_import_firewall` — the V4 package imports no Bedrock client and no
   production-prediction / p_model path.

---

## 18. Frozen decision rules (deliverable 15)

Mechanical verdict on the single **confirmatory** contrast (opponent_profile · corners ·
`hd_shrunk_diff` · B2 vs B1), evaluated only after this design is frozen:

| verdict | condition |
|---|---|
| **PASS** | pooled ΔLogLoss(B2−B1) < 0 **and** 95% block-bootstrap CI entirely < 0 (CLEAR or PROMISING) **and** calibration preserved (slope ∈ [0.8, 1.25], ECE not worse than B1 by >0.01) **and** the mapped-axis lift **exceeds all three negative controls** (§14) **and** direction consistent across ≥ 3 of 4 folds |
| **MIXED** | ΔLogLoss point estimate < 0 but CI crosses zero (MARGINAL), OR a control is not cleanly beaten, OR fold direction is inconsistent |
| **FAIL** | ΔLogLoss(B2−B1) ≥ 0 pooled, OR calibration degraded, OR a negative control matches/exceeds the mapped axis |

Exploratory cells (goals, cards, other families, ablations) are reported with the same
metrics but can only ever be labelled EXPLORATORY / hypothesis-generating; they cannot
upgrade the verdict. A PASS is **historical-OOS candidate** status only — never promotion,
never prospective confirmation (§19).

---

## 19. Prospective follow-up plan (deliverable 16, mandate §19)

A positive V4 result is **not** prospective confirmation. The required funnel is unchanged:

```
historical OOS candidate (V4 PASS)
  → frozen challenger (definition hashed)
  → prospective shadow predictions (timestamped, before kickoff)
  → timestamped market comparison
  → genuine closing line
  → settlement
  → possible later promotion
```

The existing `src/research/prospective/` shadow machinery is the intended vehicle. OOS and
prospective evidence are kept as separate claims; V4 produces at most the first box.

---

## 18b. Identifiability recommendation (deliverable 18)

**Is the experiment scientifically identifiable with the current data?**

*Partially, and only for a narrow confirmatory contrast.* The honest assessment:

**Identifiable:**
- The **statistical apparatus** is fully identifiable: a strong existing B1, a reused
  walk-forward harness on 5,319 dual-provider matches / 6 leagues, a frozen block-bootstrap,
  PIT-safe reconstruction proven clean in V3, and a single pre-declared confirmatory
  contrast with frozen decision rules.
- The **corners** market is the one cell where a frozen opponent_profile target
  (`corners` FOR/AGAINST, the most-populated mapped metric) meets a validated betting
  target and adequate cohort N (median conditional N = 14; the family measurable rate is
  0.981). B2 vs B1 there is a well-posed incremental-information question.

**Threats that keep it from being fully identifiable (disclosed, not hidden):**
- **Target-mapping loss:** ~40 of 53 MEASURED opponent_profile candidates target process
  metrics with *no* validated betting target and are correctly set aside (§8). The
  predictive experiment therefore rests on a **small** mapped subset, dominated by corners.
- **Origin-fixture scarcity:** the templates descend from 12 fixtures; identity-blinding +
  origin exclusion bound but do not erase this. The result is confirmatory for exactly one
  contrast and exploratory elsewhere.
- **Single-side → match-total estimand gap:** the candidate measures one team's FOR/AGAINST;
  the target is a match total. The A-attack⊕B-defence aggregation is a reasonable frame but
  is itself an assumption, recorded as such.

**Conclusion:** the design is internally consistent, leakage-safe by construction and by
test, free of effect-based selection, and identifiable **for a single narrow confirmatory
contrast (opponent_profile · corners) with everything else exploratory.** That is enough to
preregister and run — provided the claim is scoped to that contrast and not oversold. The
appropriate token is therefore the READY token, with the scope limitation stated in §18b
as a first-class part of the preregistration.

---

## Architecture confirmation

- $0.00. No Bedrock/LLM/network. No final OOS scoring run.
- No V2/V3 frozen artifact modified; `query_plan.py` and `cohort_measurement.py` used, not
  edited; `SONNET46_HYPOTHESIS_V3 = FAIL` untouched.
- CHAMPION read-only (sha `0b8f5ff3…`). `p_model`, calibration, production prediction
  untouched. No promotion, no alpha claim, no closing line read.
- New code confined to `src/research/hypothesis_oos/` and `research/hypothesis_oos/`.
