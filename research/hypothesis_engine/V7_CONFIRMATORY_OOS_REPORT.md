# V7 — Confirmatory OOS Result

## 1. Executive verdict

| | |
|---|---|
| `EXECUTION_STATUS` | **COMPLETE** — all frozen folds executed, all artifacts written and hashed |
| `APPARATUS_STATUS` | **INTACT** — 26/26 frozen hashes verified pre-OOS; CHAMPION unchanged; leakage suite 11/11 |
| `SCIENTIFIC_EVALUABILITY` | **SEVERELY LIMITED.** Only **16 of 132** LLM canonical families (12.1%) reached a computable OOS estimate. 59.8% were `UNMEASURABLE`; a further 28.0% compiled to a **contrastless** signal under the frozen comparator definition |
| `END_TO_END_ENDPOINT_RESULT` | **LLM UNDERPERFORMS THE GENERIC NULL.** 5.3% vs 19.4% survival from the full canonical denominator (≈3.7× worse) |
| `CONDITIONAL_SIGNAL_ENDPOINT_RESULT` | **NO DETECTABLE DIFFERENCE.** 16 matched pairs; LLM 0.0534 vs weighted control 0.0609; diff **−0.0075**, clustered SE 0.0079, t = −0.91, **p = 0.391** |
| `OVERALL_V7_SCIENTIFIC_INTERPRETATION` | Under its frozen design, V7 finds **no evidence** that V6.1-generated hypotheses correspond to OOS-stable relationships beyond a structurally comparable generic null — on either endpoint. The end-to-end result is decisively *against* the LLM; the conditional result is a *null*, on a sample too small to detect any but a large effect |

This is not a `PASS`/`FAIL`: the frozen evaluator defines no such verdict, and the two endpoints
disagree in character (one adverse, one null).

## 2. OOS integrity

```
CONFIRMATORY_OOS_COMPUTED = true
CONFIRMATORY_OOS_VIEWED   = true
POST_OOS_DESIGN_CHANGES   = 0
BEDROCK_USED              = false
KIRO_HANDOFF_REQUIRED     = false
CANDIDATE_FEATURE_PROMOTION = false
```

Pre-OOS: 26/26 declared artifact hashes verified; the whole apparatus re-froze byte-identically
(29 artifacts); the Control-B chain reproduced exactly — **24,000 pool → 15,738 families →
6,056 eligible → 452 weight-carrying → total control weight 48.0** = matched LLM count. The
measurement engine's spec was written and hashed (`f7276c763b615da6…`) **before the first
effect**, and that hash still recomputes from code.

## 3. Universe accounting (Endpoint A)

| | LLM | null (uniform) |
|---|---|---|
| canonical | 132 | 1,980 |
| measurable | **53 (40.2%)** | **1,167 (58.9%)** |
| support-eligible (computable estimate) | **16 (12.1%)** | **983 (49.7%)** |
| OOS-surviving | **7 (5.3%)** | **385 (19.4%)** |

### Failure-mode composition

| terminal state | LLM | null |
|---|---|---|
| `UNMEASURABLE` | 79 (59.8%) | 813 (41.1%) |
| `TAUTOLOGICAL` | **37 (28.0%)** | 184 (9.3%) |
| `OOS_DIRECTION_UNSTABLE` | 7 (5.3%) | 292 (14.7%) |
| `OOS_NO_EFFECT` | 2 (1.5%) | 298 (15.1%) |
| `OOS_FAIL` | 0 | 8 (0.4%) |
| `CANDIDATE_FEATURE_ELIGIBLE` | 7 (5.3%) | 385 (19.4%) |

The LLM loses at **both** gates: it is less often measurable, and when measurable it is three
times more often contrastless.

## 4. Conditional matched comparison (Endpoint B)

| | |
|---|---|
| LLM eligible | 53 |
| matched (frozen weights, reused verbatim) | 48 |
| **matched pairs with a computable score on both sides** | **16** |
| LLM families unscored | **32**, all 32 `TAUTOLOGICAL` (contrastless signal, no score exists to compare) — leaving the **16** scored pairs above |
| control weighted N / Kish ESS | 48.0 / **153.9** |
| unmatched fraction | 0.094 |
| balance (frozen, pre-OOS) | worst \|SMD\| 0.186, 0/31 levels failing |
| mean LLM score | **0.0534** |
| mean weighted control score | **0.0609** |
| **estimate (LLM − control)** | **−0.0075** |
| naive SE / clustered SE | 0.0056 / **0.0079** (9 clusters) |
| clustered t / p | −0.91 / **0.391** |

Multiplicity: BH-FDR per frozen family at q = 0.10 plus EB shrinkage. Of the LLM's 16 scored
families, 8 survive FDR (`attacking_volume` 3/3, `form_baseline` 4/4, `discipline` 1/4); the
null rejects 650 of 983. **Nominal p-values were not used as promotion evidence.**

## 5. Walk-forward results (LLM, all six frozen folds)

| fold | train end → validate end | effects | mean | % positive |
|---|---|---|---|---|
| 0 | 2025-01-01 → 2025-04-01 | 41 | 0.043 | 0.732 |
| 1 | 2025-04-01 → 2025-06-30 | 41 | 0.078 | 0.756 |
| 2 | 2025-06-30 → 2025-09-28 | 41 | **0.010** | **0.537** |
| 3 | 2025-09-28 → 2025-12-27 | 41 | 0.073 | 0.878 |
| 4 | 2025-12-27 → 2026-03-27 | 41 | 0.076 | 0.829 |
| 5 | 2026-03-27 → 2026-05-31 | 41 | 0.059 | 0.780 |

Fold 2 — the mid-season-break block — is materially weaker on both mean and direction. It is
reported, not smoothed.

## 6. Competition stability

All six competitions contributed **equally** (588 evaluable fold-cells each: champ, epl,
laliga, laliga2, ligue1, ligue2). No league was dropped, and no result rests on an easier
subset. The frozen coverage gate held throughout: **xG remained unavailable everywhere**
(Ligue 2 coverage measured 0.000, La Liga 2 0.452), and no similarity dimension used it.

## 7. Hypothesis-family results (LLM, frozen multiplicity families)

| family | terminal states |
|---|---|
| `attacking_volume` | **3 eligible**, 12 tautological, 6 unmeasurable |
| `form_baseline` | **4 eligible**, 19 unmeasurable |
| `attack_quality` | 1 unstable, 2 tautological, 18 unmeasurable |
| `defensive` | 2 unstable, 10 tautological, 23 unmeasurable |
| `discipline` | 2 unstable, 2 no-effect, 5 tautological |
| `opponent_interaction` | 2 unstable, 13 unmeasurable |
| `set_piece` | 8 tautological — **zero evaluable** |

## 8. Candidate survivors (7) — research-eligible only, NOT promoted

Every survivor carries the **same** comparator, `SUBJECT_RECENT_VS_LONG_BASELINE`. None uses
similarity, conditions, or venue.

| id | target | family | window | score | shrunk | dir. agree | p | FDR |
|---|---|---|---|---|---|---|---|---|
| `d922b8d6` | final_third_entries, possession | TEMPO | W5 | +0.180 | +0.176 | 1.00 | 4.0e-07 | ✓ |
| `8696272d` | final_third_entries, possession | TEMPO | W5 | +0.175 | +0.169 | 1.00 | 1.2e-05 | ✓ |
| `bfdb95f3` | big_chances, goals, shots_on_target | FORM | W5 | +0.090 | +0.081 | 1.00 | 1.6e-07 | ✓ |
| `4c6804d9` | shots, shots_inside_box, shots_on_target | ATTACK_VOL | W10 | +0.090 | +0.093 | 0.89 | 4.4e-07 | ✓ |
| `a3fbe728` | big_chances, shots, shots_on_target | FORM | W5 | +0.080 | +0.081 | 0.89 | 1.8e-06 | ✓ |
| `3c85937d` | big_chances, goals, shots_on_target | FORM | W5 | +0.078 | +0.081 | 0.89 | 6.7e-05 | ✓ |
| `d3d94086` | big_chances, corner_kicks, shots, … | FORM | W5 | +0.077 | +0.081 | 0.92 | 1.4e-08 | ✓ |

**Deterministic feature definition** (identical for all seven, per the frozen comparator):
`feature = shrink(time-decayed PIT mean over the subject's prior matches, at each frozen
half-life {180d, 365d}, toward the competition environment) − shrink(un-decayed PIT mean,
same prior matches, same prior)`. Both half-lives are reported and averaged; neither was
selected. Confounders per the frozen family plan (competition one-hots, opponent PIT strength,
subject baseline, card rate); the venue column is constant by construction and dropped as
non-identifiable. Support: 380–779 validation fixtures per fold, `ADEQUATE_SUPPORT` on all six.

Effect sizes are **small** (|r| 0.08–0.18) and the whole surviving set reduces to one
well-known football regularity: **recent form carries information beyond the long-run mean.**
The generic null finds the same thing at four times the rate.

Four of the seven shrink to `+0.0814` *exactly*. That is not a transcription artifact: empirical-Bayes pooling under the frozen multiplicity plan draws same-family estimates of comparable reliability toward the `form_baseline` family mean, and those four are the family's four survivors. The plan is behaving as frozen.

### Why a “null” benchmark survives at 19.4%

A 19.4% survival rate for a mechanically enumerated pool invites the suspicion that the estimator is broken. It is not, and the reason matters for reading Endpoint A. Under the frozen comparator the compiled signal is `C − B`, where **C** is a time-decayed PIT mean and **B** an un-decayed PIT mean over the *same* strictly-prior observations. That difference is non-degenerate precisely when recent matches differ from the long run — i.e. it is a genuine recency contrast, and it is PIT-safe because both terms read only prior fixtures (the three-way probe in §12 confirms this empirically on the executed engine). So the null pool survives at that rate because **generic recency features really do carry out-of-sample information in football**, not because the pipeline waves things through. Endpoint A therefore says something specific: the LLM's contribution was to name that same regularity *less often*, and in *less measurable* form, than blind enumeration of the same structural vocabulary.

## 9. Failures

LLM: `UNMEASURABLE` 79, `TAUTOLOGICAL` 37, `OOS_DIRECTION_UNSTABLE` 7, `OOS_NO_EFFECT` 2,
`OOS_FAIL` 0. Null: 813 / 184 / 292 / 298 / 8.

## 10. End-to-end data compatibility (pre-OOS finding, unchanged)

| origin | compatibility rate | names a coverage-failing metric |
|---|---|---|
| LLM | **0.4015** | **59.9%** (xg 58, touches_in_penalty_area 44) |
| null (uniform) | 0.5894 | 41.1% |

Recorded before OOS and **not rewritten after it**. This is a research-system property, not
football evidence, and it is one of the two reasons the LLM loses Endpoint A.

## 11. Control A — `DESCRIPTIVE_ONLY` / `NON_CONFIRMATORY_FOR_TREATMENT_EFFECT`

| arm | n | surviving | states |
|---|---|---|---|
| base | 44 | **0 (0.0%)** | 28 tautological, 16 unmeasurable |
| research | 88 | **7 (8.0%)** | 63 unmeasurable, 9 tautological, 7 unstable, 2 no-effect, 7 eligible |

The arms share **zero** canonical families, so these are different hypothesis populations, not
a matched contrast. **This is not causal evidence of a richer-context treatment effect** and is
not offered as such.

## 12. Leakage audit (re-run post-execution)

All 11 mutation classes rejected, legitimate PIT observation accepted. Additionally, a
**three-way empirical probe against the executed engine** on a real fold-4 fixture:

| mutation | result |
|---|---|
| corrupt the **target fixture's own** statistic | signal **unchanged** (outcome moved, as it must) |
| corrupt a **future** fixture | signal and outcome **both unchanged** |
| corrupt a **past** fixture of the subject | signal **moved** — the negative control proving the engine genuinely reads history |

## 13. Provider integrity

`corpus_provider = thestatsapi`, `n_distinct_providers = 1`, `footystats_values_loaded = 0`,
pooling guard armed and never fired. Storage blocks never treated as provenance. Shrinkage
integrity: spec k = code k = 8.0, applied in production code.

## 14. Reproducibility

Engine-spec hash recomputes from code and matches the artifact. Both pre-execution engine corrections — axis-name parsing, and dropping constant confounder columns as non-identifiable — were found and fixed **on the development window, before any confirmatory effect was computed**, and both are declared inside the hashed engine spec `f7276c763b615da6…`. No code path changed after the clock started.

A full deterministic re-run of the executor was performed end to end (fresh process, `PYTHONHASHSEED` discipline, same frozen inputs). **All ten evidence artifacts hashed byte-identically to the first execution** — 10/10 SHA-256 matches, zero diffs — and the re-run independently reproduced every headline number: Endpoint A 53/16/7 (LLM) and 1167/983/385 (null), Endpoint B 16 pairs, estimate −0.007536052743368488, clustered p = 0.3910801834229277, 7 candidates, CHAMPION `0b8f5ff3dc4ddf15…` unchanged. The SHA-256 counter-stream RNG and the two frozen control pools reproduced exactly (24,000 → 15,738 → 452 weight-carrying). Per-artifact digests are listed in §17.

## 15. CHAMPION

`0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9` before **and** after —
**unchanged**. No feature promoted, no `p_model` touched, no stake computed.

## 16. Apparatus finding (flagged BEFORE the clock started)

The single largest driver of the adverse result is **not** a football fact. The frozen
canonicalizer collapsed questions that were explicitly *subject-vs-opponent* —

> "Does AWAY_TEAM concede a materially higher volume of total shots **compared to HOME_TEAM's
> own shot-concession baseline**?"

— into `SUBJECT_OVERALL_BASELINE`, whose frozen definition pairs a *subject* cohort with a
*subject* baseline. With no conditions and an `ALL_PRIOR` window, cohort ≡ baseline, so the
compiler produces `signal == 0` exactly. **37 of 53 measurable LLM families** terminated this
way, including **all 8** `set_piece` families.

This was identified *before* any OOS was computed and the plain frozen reading was applied
deliberately: re-reading the comparator from the hypothesis prose would have let LLM wording
override the frozen structural canonicalization, which PHASE 2 and PHASE 33 exist to forbid.
The degeneracy is produced by the compiler and auditable, not asserted.

Its consequence must be stated plainly: **for a large part of the LLM universe, V7 did not test
what those hypotheses were asking.** The end-to-end result stands as measured, but it is
substantially a verdict on the *canonicalizer's comparator vocabulary*, not solely on the
LLM's football insight. `analysis_spec.flag_comparator` screens `SELF_COMPARISON` only for
`SUBJECT_CONDITIONAL_VS_BASELINE` and misses the structurally identical
`SUBJECT_OVERALL_BASELINE` case — a defect for a successor experiment to fix. **It was not
patched here**, per the post-authorization rule.

## 17. Final machine states

```
V7_CONFIRMATORY_OOS_EXECUTED     V7_MULTIPLICITY_APPLIED
V7_OOS_EVIDENCE_FROZEN           V7_CANDIDATE_FEATURE_SET_FROZEN
V7_ENDPOINT_A_EVALUATED          V7_CHAMPION_UNCHANGED
V7_ENDPOINT_B_EVALUATED          V7_EXPERIMENT_COMPLETE
```

Evidence artifacts (immutable) in `research/hypothesis_oos/out/v7/oos/`. Digests below are
identical across both independent executions:

| artifact | sha256 |
|---|---|
| `V7_MEASUREMENT_ENGINE_SPEC.json` | `941a596ca757c2296c8f3c9839704f041efc674c6574282f545a8dd82a46a218` |
| `V7_OOS_LLM_EVIDENCE.json` | `e2a772e52af0819e9bfea7954f1caa5a8910f19b64f3fba28066578ba5e1bca3` |
| `V7_OOS_NULL_UNIFORM_EVIDENCE.json` | `5e5908b75adb0a27955902673fe8a262404b0d82e9e4de20ad9440239eb043e3` |
| `V7_OOS_NULL_MATCHED_EVIDENCE.json` | `b36255181cf554f3f30de2bd8cdec041a145a6762e64c7cebe0a10a02d978c28` |
| `V7_OOS_ENDPOINT_A.json` | `4c47cf31b15d23d75cb7fdd050c1dd432c3af5413a5d7bddc60314ee095de73f` |
| `V7_OOS_ENDPOINT_B.json` | `471ba83e7f9d7aefcf9b0ba9cfde51a578f4b08ed43be5eb52da455325195187` |
| `V7_OOS_FOLDS.json` | `b013223d6eae2cb21b6ccc635b11cba784aa201f0c889b218b945020243dc8f3` |
| `V7_OOS_STABILITY.json` | `e60a2cb11b6006d3cb7fb720cd5dc5d7edd5c730b4801884eab4799eb02a3120` |
| `V7_CANDIDATE_FEATURE_SET.json` | `f85cacf25847a0f80c1cda5a260758604c7d960c756bc6fdd576af024b17478f` |
| `V7_OOS_STATES.json` | `253d30b99901072ce9afd3265f68c4ae3210f9500cbe528f63a883d077311f9f` |

`DETERMINISM_VERIFIED = true` (10/10 byte-identical, two independent executions).

**STOP.**
