# Calibration Audit — Are the Regularized Multi-Feature Probabilities Trustworthy?

**Date:** 2026-08-30 · **Measurement only** — no refit-with-different-settings, no retune, no
post-hoc calibration applied · **Zero API requests** (cached data + existing fitted protocol) ·
**Held-out set untouched** (its single prior access unchanged).

## Question

The regularized run settled that there is **no edge**. This audit answers the separate question:
independent of any edge, are these models' probabilities **calibrated** — when they say 65%, does
it happen ~65% of the time? "No edge, well calibrated" is a sellable claim; "no edge, poorly
calibrated" is not.

## Method

`scripts/mm_calibration_audit.py` reproduces the **exact** `mm_models.py` walk-forward fit path
(same 866/290-feature pool, same ≥50% train-coverage filter, train-median imputation, train
standardization, and L1 `LogisticRegressionCV` over the same `C ∈ {0.01,0.03,0.1,0.3,1.0}` grid),
then reads out per model: OOS reliability curve (10 uniform bins), Wilson 95% CI per bucket,
in-sample vs out-of-sample Brier, selected-feature count, effective sample per parameter, and an
over/under-confidence label. Fidelity check: reproduced OOS ECE matches `mm_models.json`
bit-for-bit (primary dist min 0.0094 / median 0.060 / max 0.155). **Binning scheme:** 10 equal-width
bins on [0,1], the same scheme `mm_models.py` used for its stored ECE.

**Jitter:** each model was fit twice; the calibration label was invariant across reruns for
**48/48 primary and 256/256 secondary** models. Calibration conclusions are invariant to the known
liblinear-CV jitter, as the pool/family sizes were in the prior run.

---

## 1. ECE per model (all 48 primary + 256 secondary)

10-bin uniform ECE, out-of-sample.

| Config | n | min | Q1 | median | Q3 | max |
|---|---|---|---|---|---|---|
| Primary (rich, mixed) | 48 | 0.009 | 0.037 | **0.060** | 0.095 | 0.155 |
| Secondary (broad, core) | 256 | 0.002 | 0.051 | **0.079** | 0.115 | 0.307 |

By market family (primary):

| Family | n | ECE median | ECE max |
|---|---|---|---|
| btts | 3 | 0.053 | 0.076 |
| cards | 6 | **0.127** | 0.155 |
| corners | 15 | 0.058 | 0.153 |
| clean sheet | 6 | 0.066 | 0.099 |
| goals | 18 | 0.055 | 0.142 |

Context: the earlier simpler models achieved ECE **0.018–0.05**. The regularized models' *median*
ECE (0.060 / 0.079) is worse than the simpler models' *worst* leagues, and the cards family
(median 0.127) is badly miscalibrated.

**Caveat that inflates the good-looking tail:** 9/48 primary and 23/256 secondary models have
ECE < 0.03, but of those, **2 (primary) and 13 (secondary) selected zero features** — they are
constant base-rate predictors, trivially calibrated by predicting one number, with no skill.
Restricting to models that genuinely condition (≥5 selected features), ECE median rises to
**0.058 (primary) / 0.080 (secondary)**. Low ECE here is not a signal of a useful model.

---

## 2. Reliability curves & confidence classification

Label rule: sign of the confidence mass (predicted−realized on the high side, realized−predicted
on the low side), threshold 0.02.

| Config | calibrated | underconfident | overconfident |
|---|---|---|---|
| Primary (rich) | 5 / 48 | 29 / 48 | 14 / 48 |
| Secondary (broad) | 20 / 256 | 107 / 256 | **129 / 256** |

- **Primary** skews *under*confident (predictions too timid, pulled toward base rate by strong
  L1) — but only 5/48 are actually well-calibrated.
- **Secondary** is dominated by **overconfidence (129/256)** — the exact failure mode the task
  flagged, now recurring with the large feature pool on thinner per-league corpora.
- **Overconfidence is concentrated in the smallest corpus.** The six most overconfident primary
  models are five Ligue 2 models (609 matches) plus one Championship corners model.

**Tail overconfidence, worked example — Ligue 2 goals_2.5 (53 features selected):**

| pred bin | n | predicted | realized | realized 95% CI | pred outside CI? |
|---|---|---|---|---|---|
| [0.5,0.6) | 56 | 0.551 | 0.571 | [0.44, 0.69] | no |
| [0.6,0.7) | 46 | 0.652 | 0.457 | [0.32, 0.60] | **yes** |
| [0.7,0.8) | 35 | 0.742 | 0.543 | [0.38, 0.70] | **yes** |
| [0.8,0.9) | 8 | 0.833 | 0.125 | [0.02, 0.47] | **yes** |
| [0.9,1.0) | 1 | 0.902 | 0.000 | [0.00, 0.79] | **yes** |

Every high-confidence bucket predicts materially higher than it realizes: the model says 74–90%
and the truth is 0–54%. This is textbook tail overconfidence driven by extreme estimates from a
53-feature fit on ~365 test matches.

---

## 3. Shrinkage diagnostics

**Important structural finding:** these models have **no team-level shrinkage layer**. The task
assumed "team-level shrinkage as established," but `mm_models.py` fits a plain L1 logistic — the
*only* shrinkage is the L1 penalty (the `C` parameter). There are no per-team λ parameters to
report a distribution over, and no "pull toward pooled mean" that varies with team sample size.
That mechanism exists in the *simpler* count-regression models (`count_regression.py`:
`shrinkage = count/(count+10)`, so a team with 3 matches keeps 23% of its own signal and a team
with 40 keeps 80%) — not here.

L1 strength actually chosen by CV, and resulting sparsity:

| Config | C chosen (count) | features selected (min/median/max) | collapsed to 0 features |
|---|---|---|---|
| Primary (rich, 698-pool) | 0.01×8, 0.03×29, 0.1×11 | 0 / 10 / 76 | 10 / 48 |
| Secondary (broad, 290-pool) | 0.01×67, 0.03×1, 0.1×182, 0.3×6 | 0 / 11 / 62 | 67 / 256 |

The primary CV picked *strong* L1 (77% at C≤0.03), which is why primary skews underconfident and
its overfit gap is small. The secondary picked weaker L1 (C=0.1 most common) and pays for it with
overconfidence. In neither config does L1-only shrinkage substitute for the team-level shrinkage
the simpler models use to tame extreme per-team estimates — which is the mechanism behind the
tail overconfidence above.

---

## 4. Overfitting assessment

Direct signal = OOS Brier − in-sample Brier (positive = overfit).

| Config | overfit gap (median) | gap (max) | eff. sample / selected param (median) |
|---|---|---|---|
| Primary (rich) | +0.009 | +0.094 | 94.8 |
| Secondary (broad) | +0.026 | +0.169 | **18.6** |

- Primary's gap is small in aggregate because strong L1 keeps few features; but the **max gap
  (+0.094) is a Ligue 2 model**, and Ligue 2 has the largest median gap (+0.012) of the three
  rich leagues — the smallest corpus overfits most, as flagged.
- Secondary's gaps are 2–4× larger. The worst leagues by median gap: Belgium Pro League (+0.043),
  England Premier League (+0.042), USA MLS (+0.036), Italy Serie A (+0.033). These pair thin
  per-league corpora (~300–380 matches) with ~11 selected features → **effective sample per
  parameter median 18.6**, well below the ~50+ rule of thumb for stable logistic coefficients.

Largest in-sample/out-of-sample divergence overall: secondary Spain La Liga (max gap +0.169) and
Belgium (+0.142); within primary, Ligue 2 (+0.094).

---

## 5. Comparison vs the earlier simpler models — the key benchmark

Same leagues, same markets (match-total corners 9.5 and cards 3.5). Simpler = Poisson/NB
count-regression with team shrinkage (`robustness_results.json`, ~9–11 parameters). Regularized =
L1 multi-feature (0–76 selected from 290–866 pool).

| League | Market | simpler BSS % | simpler ECE | regularized BSS % | regularized ECE | reg. params |
|---|---|---|---|---|---|---|
| England Championship | corners 9.5 | **+7.87** | 0.049 | −0.03 | 0.009* | 0* |
| England Championship | cards 3.5 | **+5.80** | 0.042 | −10.42 | 0.114 | 31 |
| France Ligue 2 | corners 9.5 | **+7.09** | 0.048 | −32.18 | 0.280 | 17 |
| France Ligue 2 | cards 3.5 | **+3.88** | 0.057 | −1.69 | 0.065 | 0* |
| Spain La Liga | corners 9.5 | **+9.83** | 0.041 | −1.12 | 0.053 | 0* |
| Spain La Liga | cards 3.5 | **+6.26** | 0.040 | −0.58 | 0.087 | 14 |
| England Premier League | corners 9.5 | **+8.36** | 0.048 | −5.29 | 0.107 | 13 |
| England Premier League | cards 3.5 | **+10.25** | 0.071 | −2.32 | 0.092 | 10 |
| Germany Bundesliga | corners 9.5 | **+10.81** | 0.035 | −0.06 | 0.012* | 0* |
| Germany Bundesliga | cards 3.5 | **+8.26** | 0.057 | −0.17 | 0.020* | 0* |
| Italy Serie A | corners 9.5 | **+4.14** | 0.063 | −3.22 | 0.080 | 23 |
| Italy Serie A | cards 3.5 | **+9.86** | 0.026 | +2.41 | 0.054 | 16 |

`*` regularized ECE looks small only because L1 collapsed the model to a constant (0 features) — no
skill; not "well calibrated" in any useful sense.

**Verdict on the benchmark, stated plainly: the simpler models are both more skilful AND better
calibrated on every shared league/market.** Where the regularized model conditions on features it
is worse-calibrated (higher ECE) and negative BSS; where it matches the simpler model's ECE it did
so by degenerating to the base rate. The 290–866-feature pool is **introducing variance, not
signal** — exactly the concern raised in the task. The multi-feature approach is actively worse
than the earlier ~10-parameter count regression.

---

## 6. Verdict — are the probabilities trustworthy?

**No — not as they currently stand, in either configuration.** This is a global "no," and the
per-market detail makes it sharper:

- **Secondary (broad, core):** No. 129/256 overconfident, median ECE 0.079, thin effective sample
  (18.6/param), and beaten outright by the simpler models on the shared markets. Do not publish.
- **Primary (rich, mixed):** Mostly no. Only **5/48 models are well-calibrated**; the rest are
  underconfident (29) or overconfident (14). The cards family (median ECE 0.127) is the worst; the
  overconfident tail is concentrated in Ligue 2 (smallest corpus). None of the "calibrated" 5 also
  carry usable skill (BSS at/below 0), so even the calibrated subset is not a product.
- **Any market, any league:** there is no (market, league) cell that is *both* well-calibrated
  *and* skilful. The only trustworthy-looking cells are constant base-rate predictors.

The `mm_models.json` line "BSS at or below zero" is now joined by the calibration finding: these
are **neither skilful nor reliably calibrated**. The honest sellable claim ("we can't beat the
market but our 65% means 65%") is **not supported** by these models.

### What would be required to fix it (recommendation only — not implemented this pass)

1. **Fewer features / stronger shrinkage.** The 866/290-pool is the root cause. The simpler ~10-
   parameter count regression is better on every axis; reverting to it (or hard-capping the L1
   model to a handful of features) is the highest-leverage change.
2. **Add team-level shrinkage.** These L1 models lack the `count/(count+10)` team-effect shrinkage
   the simpler models use; that mechanism is precisely what tames the extreme per-team estimates
   producing the tail overconfidence (Ligue 2 goals_2.5 predicting 0.90 → realizing 0.00).
3. **Post-hoc calibration (Platt / isotonic)** fit on a validation slice would repair the
   reliability curve for the underconfident primary models cheaply — but only after the skill and
   overfitting problems are addressed, since calibrating a zero-skill model just yields a
   well-calibrated restatement of the base rate.

Do the structural fixes (1, 2) before reaching for post-hoc calibration (3).

---

## Ground rules — compliance

- Zero API calls; existing cached data and the existing fit protocol only ✓
- No model refit with different settings, no retune, no post-hoc calibration applied ✓
- All 304 models reported including the worst; no best-slice selection ✓
- Sample sizes + Wilson CIs per bucket; thin buckets shown, not hidden ✓
- Calibration labels shown jitter-invariant (48/48, 256/256) ✓
- Held-out set untouched (single prior access unchanged) ✓
- No shared/global config changed (new standalone script + outputs only) ✓

## Artifacts

- `scripts/mm_calibration_audit.py` → `data/discovery/mm_calibration_audit.json` (per-model
  reliability curves, IS/OOS Brier, labels)
- Benchmark source: `robustness_results.json` (simpler count-regression, 25 leagues)
- Audited models: `data/discovery/mm_models.json` (unchanged)
