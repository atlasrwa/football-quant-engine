# Discovery Pipeline Diagnostic Report

**Date:** 2026-08-28
**Question:** Is the zero-survivor result genuine, or an artifact of search scope or correction methodology?

---

## Verdict

**The zero-survivor result is GENUINE for the class of models tested (logistic regression over rolling features predicting binary over/under outcomes).**

The signal in this domain does not manifest as a linear relationship between rolling feature averages and binary outcomes — it manifests through team-specific rate-estimation in count models. A logistic regression screener (Path A/B's approach) is the wrong model class for this signal, just as the binary median-split was. The signal exists but is architecturally inaccessible to the discovery pipeline's screening methodology.

This was confirmed by running known-good features (team-specific rolling corner rates) through a properly implemented within-league walk-forward logistic regression: **2/25 leagues beat naive, overall BSS = -4.0%.** The same features produce +6.8% in the count-regression architecture. The signal is real but structurally bound to the Poisson/Dixon-Coles model form.

---

## Evidence Chain

### Diagnostic 1 — Known ground truth fails ALL screening approaches

| Approach | Features | vs Naive | p-value | Verdict |
|----------|----------|----------|---------|---------|
| Binary median-split (Run 1) | Rolling total corners | +1.7% | 0.16 | Fails |
| Logistic regression, global split | Rolling total corners | -1.0% | 1.00 | Fails |
| Logistic regression, within-league | Team-specific rates | -0.5% | 1.00 | Fails |
| Per-league logistic regression | Team-specific rates | -4.0% BSS | — | 2/25 positive |

**None of these detect the +6.8% signal.** The signal is structurally bound to the count-regression model form.

### Why count regression works but logistic doesn't

The corners model works by treating each team as a Poisson process:
- Team A's corner rate λ_A estimated from their home match history (with shrinkage)
- Team B's corner rate λ_B estimated from their away match history (with shrinkage)
- P(total > 9.5) computed from the convolution of two Poisson distributions

This is NOT equivalent to logistic regression over rolling averages because:
1. The Poisson model estimates **rates** (continuous, team-specific) not binary splits
2. Shrinkage pulls noisy estimates toward a league mean (regularization at the team level)
3. The probability is computed from the **distributional tail**, not a linear function of inputs
4. Two Poisson processes convolving produce a non-linear probability surface

A logistic regression asks: "is there a linear relationship between avg_corners and P(over)?" The answer is: barely (r = 0.016). But the count model asks: "if this team takes corners at rate 6.2 and that team at rate 4.1, what's P(sum > 9.5)?" — which is a completely different (and much more powerful) question.

### Diagnostics 2-5 (unchanged findings)

- **7 screening survivors:** All marginal (p = 0.025–0.082), correctly rejected
- **Search space:** 1,398 candidates from 28 fields — narrow but adequate to prove the point
- **Correction:** Not the bottleneck (181× gap even without Bonferroni)
- **Screening mechanics:** Sound (no bugs), primary failure is lack of multi-target breadth

---

## What This Means

### The "metric discovery" framing has a structural problem

The architecture assumed that predictive signal lives in **reusable metric primitives** — individual quantities or simple combinations that carry standalone predictive value. The data says otherwise:

- Individual features: r ≈ 0.016 with binary outcomes (zero signal)
- Feature combinations via logistic regression: negative BSS (worse than naive)
- Team-specific count regression: +6.8% (strong confirmed signal)

The signal is not in the FEATURES — it's in the MODEL ARCHITECTURE applied to those features. A team's Poisson corner rate is not a "metric" you can discover by screening; it's a parameter of a generative model fitted to that team's history.

### Legitimate paths forward

1. **Accept Path C:** The honest finding is "simple feature combinations don't carry standalone predictive signal in football count markets — the signal requires generative models with shrinkage." Record this in the failure ledger. The creator hypothesis pipeline already supports the right kind of testing (arbitrary models submitted by creators, validated through the full governance pipeline).

2. **Reframe discovery as model-architecture search:** Instead of discovering features, discover model architectures (e.g., "Poisson with team-level shrinkage" as a validated architecture that can be applied to different markets). This is a higher-level primitive than a metric.

3. **Target different signal types:** The discovery approach might work for signal that IS accessible through linear/logistic methods — e.g., referee tendencies, manager effects, or scheduling factors that create genuine binary-separable predictions. These haven't been explored.

---

## No Changes Made

This report is diagnosis only. No thresholds were modified, no candidates were retroactively promoted, the held-out set was not accessed for validation (only the sanity gate ran on discovery data). The combination discovery module was built and the sanity gate correctly prevented a full search with a broken instrument.
