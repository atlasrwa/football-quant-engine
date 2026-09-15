# V4 — Hypothesis-Derived Deterministic Measurement: Walk-Forward OOS Result

**Execution of the frozen preregistration.** This report executes, without redesign, the
experiment frozen in `research/hypothesis_engine/V4_HYPOTHESIS_DERIVED_OOS_PREREGISTRATION.md`
and `research/hypothesis_oos/out/PREREGISTRATION.json`.

**Spend: $0.00.** No Bedrock, no LLM, no network read, no CHAMPION mutation, no feature
promoted, no calibration touched, no betting recommendation, no stakes.

**FROZEN_VERDICT: FAIL** (mechanical, computed before interpretation — §15).

---

## 1. Preregistration hashes

| artifact | SHA-256 |
|---|---|
| `PREREGISTRATION.json` | `fe38a9518f6a4b3abc4244b9f83c828576bc5aa1a06bac4c8eff02193fa42ea3` |
| design doc `V4_..._PREREGISTRATION.md` | `05f7208606d98d59de763d25196da20c3f8e1614343cbba0985fa34c0bcb31c4` |
| `src/research/hypothesis_oos/compatibility.py` | `50d1c86787881883cbf824e84913e1ce1dc76e867e0992b8d8e2d1e3ec1e54ff` |
| `research/hypothesis_oos/_run_v4_oos.py` (executor) | `bc6db7c17183aa1592d8ae462b33329103d53c4e83b1371fdfac648b9af92843` |
| `V4_OOS_RESULTS.json` (this run) | `9dfb6beceba7999ec97447ec868deaa9aa1a6b80968381a655eae4d105a0c272` |

Feature definition/version: `hd_shrunk_diff` via `cohort_measurement_v1`. Shrinkage:
`SHRINK_K = 6.0`, `MIN_CONDITIONAL_N = 4`, `MIN_COMPARISON_N = 8`, `MIN_PRIOR_MATCHES = 4`.

## 2. Integrity audit

- **Deterministic rebuild:** `PREREGISTRATION.json` was recomputed and is **byte-identical**
  to the frozen artifact (diff empty). PASS.
- **All 11 zero-spend preregistration/leakage tests pass**, plus **3 reconstruction-path
  PIT tests** (`test_v4_oos_execution_leakage.py`) — 14 passed total.
- **CHAMPION unchanged:** frozen sha `0b8f5ff3…` == current sha `0b8f5ff3…`. PASS.
- No frozen scientific artifact differs → integrity **not** aborted; scoring proceeded.

## 3. Leakage audit

- Feature reconstruction enforces strict `historical_fixture_kickoff < prediction_cutoff`
  (equality forbidden), the target fixture is excluded from its own feature, and a future
  match provably does **not** change a past feature value (positive test
  `test_hd_feature_future_does_not_change_past`).
- The frozen `cohort_measurement.execute` leakage backstop (`LEAKAGE_REJECTED`) is active on
  every reconstruction. Zero PIT violations observed → no `V4_OOS_LEAKAGE_ABORT`.

## 4. Quarantine audit

| | |
|---|---|
| corpus total | 5,319 |
| after origin quarantine | 5,308 |
| removed | **11** (exactly the clean V3 origin fixtures) |
| origin ids present in corpus | 11 |
| **origin ids in evaluation universe** | **0** |

The 11 clean origin fixtures (`mt_010243515, mt_010243537, mt_010243938, mt_010244159,
mt_010244193, mt_010441320, mt_010441491, mt_010444904, mt_012232295, mt_012232411,
mt_013233190`) contribute to no training, validation, test scoring, feature fitting,
band fitting, shrinkage, or preprocessing. Verified mechanically.

## 5. Dataset / fold counts

- Universe: 5,308 dual-provider matches, 6 leagues (champ 1656, laliga2 924, laliga 760,
  epl 760, ligue1 610, ligue2 609), 2023-08 → 2026-05.
- Chronological **expanding** walk-forward, 4 folds; fold 1 is train-only (first test block
  is fold 2). Confirmatory corners cell: 3 scored folds, n_test 1320 / 1320 / 1321.
- Total confirmatory OOS predictions: **3,961** (of 5,281 assembled corners fixtures).
- Random split: none. Future-trained preprocessing: none (median-impute + standardise +
  elastic-net fit train-only inside `fit_predict_logit`).

## 6. Feature availability / coverage

| cell | hd coverage |
|---|---|
| confirmatory corners@9.5 | **0.9063** (4,786 / 5,281 assembled) |
| irrelevant-axis control | 0.8856 |
| band-shuffle control | 0.9078 |
| unconditional comparator control | **0.0000** (degenerate — see §10) |
| exploratory goals@2.5 | 0.9000 |
| exploratory cards@4.5 | 0.8961 |

Coverage is high where a bandable opponent + sufficient conditional cohort exist.
Missingness handled as preregistered (NaN + train-only median impute + `hd_available`); no
favorable imputation.

## 7. B0 / B1 / B2 metrics (confirmatory corners@9.5, pooled OOS)

| model | LogLoss | Brier | ECE | calib slope | AUC | n |
|---|---|---|---|---|---|---|
| **B0** champion-parity | 0.69578 | 0.25129 | 0.0357 | 0.424 | 0.5216 | 3961 |
| **B1** matchup+context | 0.69613 | 0.25137 | 0.0329 | 0.413 | 0.5336 | 3961 |
| **B2** = B1 + hd_shrunk_diff | 0.69613 | 0.25137 | 0.0308 | 0.412 | 0.5336 | 3961 |

Note: on this common-support 6-league corners universe, B1 does **not** beat B0 on LogLoss
(B0 is marginally lower); B1 lifts AUC (0.522→0.534) as in the prior contextual-matchup
study. That is a property of the baselines, not of the hypothesis feature.

## 8. Confirmatory result — B2 − B1 (the sole confirmatory contrast)

| quantity | value |
|---|---|
| ΔLogLoss (B2 − B1), pooled | **0.00000** |
| ΔBrier (B2 − B1), pooled | **0.00000** |
| AUC | 0.5336 → 0.5336 (unchanged) |
| ECE | 0.0329 → 0.0308 (slightly better) |
| block-bootstrap mean ΔLL | 2.6e-09 |
| 95% CI | **[−8.04e-05, +9.33e-05]** (straddles 0) |
| P(B2 better) | 0.5325 |
| band | **INCONCLUSIVE** |

Individual predictions do shift (max \|Δp\| ≈ 0.023, verified), but the net pooled effect is
indistinguishable from zero. Values are reported to 5 dp; no rounding changes any threshold
decision (the CI straddles zero by ~1e-4 either side).

**Fold-level direction (B2 − B1 LogLoss):** fold2 0.00000 (not improved), fold3 −0.00004
(improved), fold4 +0.00004 (not improved) → **1 of 3 improved**. Not consistent.

## 9. Bootstrap uncertainty

- Method (frozen): paired **competition-block** bootstrap of ΔLogLoss(B2−B1), **400
  resamples**, **seed 20240914**, 6 competition blocks. Not switched, not re-seeded.
- Result: mean ≈ 0, 95% CI [−8.04e-05, +9.33e-05], P(better) 0.5325 → **INCONCLUSIVE**.

## 10. Negative controls

| control | ΔLogLoss vs B1 | interpretation |
|---|---|---|
| irrelevant-axis (`fouls_for` band → corners) | **+0.00001** | ≈ null, as expected for an unrelated axis |
| PIT-safe band shuffle | **−0.00025** | shuffled labels improve B1 *slightly more* than the real feature |
| unconditional comparator (band=ANY) | 0.00000 (coverage 0) | degenerated: band=ANY = unconditioned → `NOT_DISTINCT`, feature absent |

Diagnostic conclusion: the real mapped-axis feature (ΔLL 0.00000) does **not exceed** the
controls; the band-shuffle control is nominally *better*. Any apparent movement is generic
added-feature capacity / noise, **not** information specific to the opponent-profile
context. The unconditional comparator degenerated by construction and is reported as such
(not repaired — mandate §14).

## 11. Exploratory cells + FDR (labelled EXPLORATORY)

| cell | ΔLogLoss | ΔBrier | band | P(better) | BH-FDR@0.10 pass |
|---|---|---|---|---|---|
| goals@2.5 (EXPLORATORY) | +0.00001 | 0.00000 | INCONCLUSIVE | 0.425 | no |
| cards@4.5 (EXPLORATORY) | +0.00002 | +0.00001 | INCONCLUSIVE | 0.2225 | no |

Benjamini–Hochberg over the exploratory family: **none pass** at q = 0.10. No exploratory
cell is promoted to confirmatory; no exploratory result overrides the confirmatory verdict.

## 12. Calibration

- B2 calibration slope 0.412 — far below the [0.8, 1.25] gate. This under-confidence is
  **inherited from B1 (0.413) and B0 (0.424)**: the base models on this corners universe are
  weakly discriminative and under-dispersed. `hd_shrunk_diff` neither fixes nor worsens it
  (0.413 → 0.412). ECE slightly improves (0.0329 → 0.0308), the one gate B2 passes.
- The slope gate failure is a property of the baseline family on corners, not evidence
  against the hypothesis feature specifically; but per the frozen rule it counts as a gate
  failure regardless.

## 13. Fold / competition diagnostics

- Per-fold LogLoss (B1 → B2): fold2 0.71005 → 0.71005, fold3 0.69232 → 0.69228, fold4
  0.68602 → 0.68606. Movement is in the 4th–5th decimal; direction inconsistent (1/3).
- Six competition blocks; the bootstrap resamples whole competitions, so the near-zero CI
  reflects dependence-respecting uncertainty, not per-prediction independence.

## 14. Frozen gate table

| # | gate | observed | threshold | result |
|---|---|---|---|---|
| 1 | ΔLogLoss(B2−B1) < 0 | 0.00000 | < 0 | **FAIL** |
| 2 | 95% CI entirely < 0 | ci_hi = +9.33e-05 | ci_hi < 0 | **FAIL** |
| 3 | band ∈ {CLEAR, PROMISING} | INCONCLUSIVE | CLEAR\|PROMISING | **FAIL** |
| 4 | calib slope ∈ [0.8, 1.25] | 0.412 | [0.8, 1.25] | **FAIL** |
| 5 | ECE not worse than B1 by >0.01 | −0.0021 | ≤ 0.01 | PASS |
| 6 | lift exceeds all 3 controls | False | True | **FAIL** |
| 7 | fold direction ≥ 3/4 | 1/3 | ≥ 3 | **FAIL** |

## 15. Mechanical verdict

**6 of 7 gates FAIL** (only the ECE gate passes). ΔLogLoss(B2−B1) = 0.00000 (not < 0), so
the verdict is not MIXED.

**FROZEN_VERDICT: FAIL.**

No softening, no "near pass", no upgrade. The verdict was computed before the interpretation
below.

## 16. Scientific interpretation (separate from the verdict)

1. **Did `hd_shrunk_diff` improve B1 OOS?** No. Pooled ΔLogLoss and ΔBrier are 0.00000.
2. **Consistent across folds?** No — 1 of 3 scored folds nominally improved, at the 5th
   decimal.
3. **Present in both LogLoss and Brier?** No — neither moved.
4. **What does uncertainty say?** 95% block-bootstrap CI [−8e-05, +9e-05] straddles zero;
   P(better) 0.53 — a coin flip. INCONCLUSIVE.
5. **Calibration?** Slope essentially unchanged (0.413→0.412); ECE marginally better. The
   feature is calibration-neutral; the poor slope is a baseline property.
6. **Did negative controls show similar improvement?** Yes — the PIT-safe band shuffle moved
   B1 *more* than the real feature. This is the decisive diagnostic: no opponent-profile-
   specific information is present beyond generic capacity/noise.
7. **Effect specific enough to justify further research?** No. It is neither statistically
   distinguishable from zero nor from its negative controls.
8. **Driven by one competition/fold?** No single competition/fold carries a real effect;
   movements are uniformly negligible.
9. **Coverage sufficient?** Yes (0.906) — the null is not a coverage artifact.
10. **Strongest alternative explanations for the (non-)result:** (a) the estimand gap —
    the candidate measures a single team's side-level conditional mean while the target is
    match-total corners over 9.5, so real side-level context can be diluted by aggregation
    and by the strong existing matchup features already capturing most corners signal;
    (b) B1 already contains opponent/venue/competition context, leaving little orthogonal
    room; (c) the opponent-profile *contrast* (conditional − overall) may simply carry no
    incremental predictive information for corners totals at this sample size. The design
    cannot separate these; it only shows the frozen feature adds nothing here. **No causal
    claim is made.**

## 17. Limitations

- Confirmatory scope is a single narrow contrast (opponent_profile · corners), as
  preregistered; the FAIL is specific to it. Everything else is EXPLORATORY and also null.
- The unconditional-comparator control degenerated (band=ANY ⇒ not distinct), so control #2
  did not provide an informative contrast; controls #1 (irrelevant axis) and #3 (band
  shuffle) did, and both confirm non-specificity.
- Baselines on this corners universe are weakly discriminative (AUC ~0.53, slope ~0.41); a
  richer/better-calibrated B1 could change the room available to any add-on feature. That is
  a property of the market, not a defect to repair inside V4.
- Result is **historical walk-forward OOS only** — not prospective, not market-relative, no
  closing line, no CLV, no settlement.

## 18. Exact artifact paths / hashes

- Design: `research/hypothesis_engine/V4_HYPOTHESIS_DERIVED_OOS_PREREGISTRATION.md`
  (`05f72086…`)
- Prereg: `research/hypothesis_oos/out/PREREGISTRATION.json` (`fe38a951…`)
- Executor: `research/hypothesis_oos/_run_v4_oos.py` (`bc6db7c1…`)
- Compatibility rule: `src/research/hypothesis_oos/compatibility.py` (`50d1c867…`)
- Results: `research/hypothesis_oos/out/V4_OOS_RESULTS.json` (`9dfb6bec…`)
- Tests: `tests/research/hypothesis_oos/test_v4_preregistration.py` (11),
  `tests/research/hypothesis_oos/test_v4_oos_execution_leakage.py` (3) — 14 passed.

## 19. CHAMPION untouched

`data/discovery/pilotC_stat_mixer.json` sha256 = `0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9`,
identical to `CHAMPION_FREEZE.json`. Read-only throughout. No champion script or scope
config modified.

## 20. No feature promoted

`hd_shrunk_diff` was **not** promoted. `p_model`, calibration, production prediction paths,
and the CHAMPION are unchanged. No betting recommendation, no stake, no prospective claim.
Even had V4 passed, that would mean only "candidate survived preregistered historical
walk-forward OOS validation" — never production promotion.

## Prospective boundary

Because the verdict is FAIL, no prospective/shadow challenger is recommended for this
candidate. The opponent-profile → corners-total contrast, as frozen, does not warrant a
prospective stage. A future **V5** (not a repair of V4) would need a generator-side change
(more/better-targeted hypotheses mapping directly to match-total targets) and/or a stronger,
better-calibrated B1 before this question is worth revisiting. Do not repair-and-resume V4.

---

**HYPOTHESIS_DERIVED_V4_OOS_COMPLETE**

**FROZEN_VERDICT: FAIL**
