# Calibration & Efficiency Experiment — Research Report

**Status: evaluation only. The champion model, config, and infrastructure were
not modified. Nothing here is promoted to production.**

Baseline `main` = `184f09d` (contains PR #4). Branch `experiment/calibration-efficiency`.
Two independent experiments were run and evaluated separately; the combined
experiment was deliberately skipped because neither component improved the champion.

## Headline

- **Experiment A (xG / shots signal): KEEP_BASELINE.** xG adds no credible value
  to the champion goals model; total shots is (credibly but negligibly) redundant.
- **Experiment B (corners signed dependence): REJECT.** The residual home/away
  corner dependence (~−0.21) is real and stable, but correcting for it with a
  signed copula makes corners forecasts *credibly worse* on proper scores and
  calibration, because the champion's marginals already over-widen the total.
- **No PROMOTE_CANDIDATE.** The champion should be kept as is on this evidence.

---

## Experiment A — xG / shots

### Semantic comparison (Phase A1)
- `shots_on_target` is semantically comparable across providers (PR #4 corr 0.994).
- `shots` (total) and `xG` are the SAME CONCEPT but MATERIALLY DIFFERENT measurement
  across providers (PR #4 corr 0.80 / 0.55; different shot-inclusion rule; different
  xG models; penalty-xG treatment undocumented). Marked **SEMANTICALLY_UNCERTAIN**;
  not blended across providers.
- Both are per-team, post-match, no capture timestamp → PIT via the fixture-date
  walk-forward (prior fixtures known before a later fixture), missing = NULL not zero.

### Ablation results (Phases A2-A4)
xG and total shots are ALREADY champion features for the GOALS and SHOTS_ON_TARGET
families (Phase 0 audit), so the leakage-safe test is a **feature ablation on the
champion goals family**: same fixtures, model, hyperparameters and walk-forward;
only the feature set varies. 26,072 paired goals predictions/arm across 13,036
fixtures, paired block-bootstrap over match-weeks (diff = arm − A0; <0 = arm better):

| arm | Brier | slope | paired diff vs A0 | 95% CI | P(arm better) |
|---|---|---|---|---|---|
| A0 champion goals | 0.2273 | 0.942 | — | — | — |
| drop xG | 0.2274 | 0.934 | +0.00007 | [−0.00017, +0.00031] | 0.29 |
| drop shots | 0.2272 | 0.943 | −0.00009 | [−0.00016, −0.00002] | 0.99 |
| drop xG + shots | 0.2273 | 0.931 | +0.00007 | [−0.00019, +0.00032] | 0.31 |

### Efficiency accounting (Phase A5)
- Predictive gain from xG: none (CI spans zero). Calibration: unchanged (~0.93).
- "Drop shots" is credibly better but by ~1e-4 Brier — operationally negligible,
  barely survives multiple-comparison adjustment, and removing an existing input
  is a champion change, not an addition.
- No new API dependency is justified: provider-of-xG was already non-credible in
  PR #4, and here the champion's own (FootyStats) xG contributes nothing measurable.

**Recommendation A: KEEP_BASELINE.** (An optional, separate, low-priority follow-up
could consider dropping `shots` from the goals family, but the gain is negligible
and it is out of scope here.)

---

## Experiment B — corners signed dependence

### Reproduced residual dependence (Phase B1)
Independent chronological walk-forward, residual = Pearson residual after the
champion's fitted side means, block-bootstrap by match-week:
- **Overall residual corr = −0.211, 95% CI [−0.226, −0.197], N = 13,010** —
  reproduces the documented −0.209.
- **Stable and pervasive:** negative in ALL 25 leagues (−0.11 … −0.28) and ~all 49
  seasons; almost every league CI excludes zero. Not a one-league/one-season
  artifact. Raw corr −0.256.

### Independence assumption (Phase B2)
Proven from code: the champion builds the total as `np.convolve(home_pmf, away_pmf)`
(`MatchCountDistribution.__post_init__`) — the convolution IS the independence
assumption. The correction inserts exactly there; the marginal engine is untouched.

### Dependence model (Phases B3-B6)
Gaussian copula over the two discrete side PMFs (`dependence.build_joint`):
- rho = 0 reproduces the convolution EXACTLY (max diff 2.8e-17).
- Supports genuine NEGATIVE covariance (Cov(home,away) = −2.46 at rho = −0.3).
- Marginals preserved to ~1e-13 (IPF); joint ≥ 0 and sums to 1; E[total] invariant
  to rho; negative rho reduces total variance as hypothesised.
- Caveat (from adversarial review): the estimated correlation is count-space and is
  fed as the latent copula rho, which slightly UNDER-applies dependence — a
  conservative approximation that only strengthens the REJECT.

### Walk-forward estimation (Phase B7)
rho estimated STRICTLY from prior fixtures only (`RhoState.observe` called after a
fixture is scored); min support 300 else rho = 0 (safe fallback = champion);
capped at |0.6|. Final walk-forward rho = −0.211.

### Results (Phases B8-B10)
52,040 paired predictions / 13,010 fixtures, corner lines 7.5/8.5/9.5/10.5.

| metric | baseline (independence) | dependence | paired diff | 95% CI |
|---|---|---|---|---|
| Brier (pooled) | 0.2277 | 0.2282 | +0.00048 | [+0.00026, +0.00071] |
| log loss (pooled) | 0.6470 | 0.6485 | +0.00144 | [+0.00088, +0.00204] |
| calibration slope | 0.927 | 0.835 | — | (moved AWAY from 1) |

- The dependence correction is **credibly WORSE** (Brier and log-loss CIs both
  exclude zero; P(dependence better) = 0.0). Worse on every individual line.
- Calibration slope moved further from 1.0 (more overconfident).
- Market benchmark: baseline gap to de-vigged pre-match corner market = +0.0022;
  dependence gap = +0.0026 (the correction WIDENS the gap). Odds never entered
  either model.

### Why (the key insight)
The −0.21 dependence is real at the count level, but the champion's side marginals
are NB2 + Gauss-Hermite uncertainty-widened, so the convolution-implied total
variance is ALREADY inflated relative to a plain independent-Poisson total. Adding
negative dependence removes variance the champion needs, over-sharpening the O/U
tails. The champion's pooled slope is already ~0.93 (its `signal_scale` calibration,
added since the older audit that reported ~0.79), so the premise "slope 0.79,
dependence will fix it" is outdated — the slope is already near 1 and dependence
makes it worse.

### Promotion criteria (Phase B, 10 general + 4 dependence-specific)
Joint PMF valid ✓, marginals preserved ✓, line monotonicity ✓, signed rho stable ✓
— but proper-score improvement ✗ (credible degradation), calibration ✗ (slope worse),
market gap ✗ (wider). **Recommendation B: REJECT.**

### Efficiency
Copula ~15 ms/joint vs a microsecond convolution (~3 orders slower); full corners
walk-forward ~10 min; adds a copula + a walk-forward rho estimator + a SciPy
bivariate-normal quadrature = medium complexity and a new numerical failure surface
— all to make forecasts worse. Not worth operating.

---

## Combined experiment
**Skipped.** Neither A nor B produced a credible standalone improvement, so per the
brief we do not search combinations to manufacture a positive result.

---

## Final decision (the seven explicit questions)

1. **Did calibration improve?** No. Dependence worsened the corners slope
   (0.927→0.835); xG/shots left the goals slope unchanged (~0.93).
2. **Did Brier / log loss improve?** No. Dependence credibly worsened both; xG
   ablation showed no credible change.
3. **Did the market gap narrow?** No. Dependence widened the corners gap to market
   (+0.0022 → +0.0026).
4. **Did runtime materially change?** The dependence layer is ~3 orders slower per
   match than the convolution; irrelevant since it is not promoted.
5. **Is TheStatsAPI needed in the production path?** No. xG/shots provider choice
   is non-credible (PR #4), and the champion's own xG adds no measurable value.
6. **Is signed corners dependence worth the complexity?** No. It is a real
   structural statistic that does not translate into a better forecast, because
   the champion marginals already compensate.
7. **Should anything become a PROMOTE_CANDIDATE?** No. KEEP_BASELINE (A) and REJECT
   (B). The engine is best left as it is on this evidence.

## Candidate classifications
- xG signal (goals): **INSUFFICIENT_EVIDENCE** of benefit → KEEP_BASELINE.
- shots signal (goals): marginally droppable (KEEP_BASELINE; optional future cleanup).
- Provider-of-xG in production: **KEEP_BASELINE** (FootyStats), no new dependency.
- Corners signed dependence: **REJECT**.

## Known limitations
- Single champion corpus (25 leagues, ~49 seasons); one xG estimator per provider.
- Count→latent rho scaling is approximate (conservative for the conclusion).
- Genuine closing odds unavailable; market benchmark is de-vigged pre-match only.
- xG/shots value tested via ablation of the champion's existing (FootyStats) signal,
  not a from-scratch multi-provider re-derivation.

## Reproduce
```python
# Experiment B walk-forward + analysis and Experiment A ablation are driven by the
# modules in src/research/experiments/calibration_efficiency/ over the champion
# corpus (src.discovery.corpus.load_discovery_set()+load_heldout_set()).
```
Summary artifacts (small, committed): `_b1_dependence.json`, `_b_analysis.json`,
`_a_analysis.json`, `_a1_semantics.md`, this report. Large prediction dumps are
gitignored.
