# Independent Calibration Audit — and What It Would Take to Bet

Three questions, answered in order:

1. Why did the engine score worse than climatology on ECE?
2. What is missing to be more calibrated?
3. What is missing to be production grade, and to actually stake money on it?

The audit is reproducible: `scripts/audit_calibration.py`, artifact
`data/results/calibration_audit.json`, zero API calls.

**Headline: I was wrong about the cause, and the audit found two real bugs in my own
model.** My commit message attributed the ECE gap mostly to a measurement artifact
("a constant base-rate predictor is trivially well-calibrated"). That explanation is
largely false, and testing it is what surfaced the actual defects.

---

## Part 1 — Why the model scored worse

### The method

Comparing raw ECE between two forecasters is not valid on its own, because ECE is
biased upward for a sharper forecaster: a spread-out predictor occupies more
reliability bins, each estimated on less data, and each contributes its own noise.
So each arm was compared against **its own null floor** — the ECE a *perfectly
calibrated* forecaster with that exact probability spread and sample size would
produce, obtained by generating outcomes from the stated probabilities.

`excess ECE = observed ECE − null ECE`. That is the part that is real
miscalibration rather than sampling noise.

Three candidate causes were then measured:

- **A. Measurement artifact** — is the gap just the binning penalty for sharpness?
- **B. Miscalibrated spread** — reliability slope from `logit(y) ~ a + b·logit(p)`.
  `b < 1` means the forecasts are too extreme.
- **C. Broken conditional independence** — the total is the convolution of two side
  distributions, which assumes the sides are independent given their fitted means.

### Candidate A: rejected

| | mean null ECE floor |
|---|---:|
| model | 0.0110 |
| climatology | 0.0103 |

**The floors are essentially identical — 1.1x, not the 3x the artifact story needs.**
The reason is that climatology here is not one constant: it varies by league *and*
by line, so pooled across cells it occupies 5–8 bins with a spread (sd 0.10–0.19)
close to the model's (sd 0.12–0.19). The two arms are being scored on nearly equal
footing, so the binning penalty cannot explain the gap.

What *is* true is that the raw comparison in my original report overstated the
problem: median observed ECE across all 475 cells is 0.0461 against a null floor of
0.0332, so **about 70% of the headline ECE was sampling noise at a median 529
predictions per cell**, not miscalibration. The genuine excess was +0.0140. The FDR
test already accounted for this correctly — which is why only 31 of 475 cells were
flagged — but the report's pooled table did not, and presented raw ECE against raw
ECE. That was a presentation error on my part.

### Candidate B: confirmed, and the dominant cause

Reliability slope, before any fix:

| Family | slope | mean bias | reading |
|---|---:|---:|---|
| first-half corners | 0.613 | −0.004 | badly too extreme |
| corners | 0.788 | −0.001 | too extreme |
| shots on target | 0.795 | +0.031 | too extreme |
| first-half cards | 0.860 | +0.028 | too extreme |
| cards | 0.864 | +0.036 | too extreme |
| goals | 0.883 | +0.015 | too extreme |
| first-half goals | 0.977 | −0.000 | well scaled |

Climatology's slopes sat at 0.861–0.992. So the model's *conditional* signal was
being over-trusted: it pushed probabilities further from the base rate than the
evidence supported. Notably first-half goals is both the best-scaled family and the
best-calibrated one — the diagnosis and the outcome agree.

Tracing this to its source found **two distinct defects**.

#### Defect 1 — Jensen inflation in the uncertainty mixture

The mixture that widens the predictive distribution over `log mu` was not
mean-preserving. Mixing over a log scale multiplies the mean by `exp(variance / 2)`:

| log-mean variance | mean inflation |
|---:|---:|
| 0.05 | +2.5% |
| 0.10 | +5.1% |
| 0.25 (the cap) | **+13.3%** |

Every expected count was inflated, biasing every `P(over)` upward — and worst for
the thin teams the widening exists to serve, since inflation scales with posterior
variance. The observed mean bias matched that ordering exactly: cards (team
shrinkage weight 0.32, high variance) +0.036, against corners (weight 0.68, low
variance) −0.001.

Fixed by subtracting `variance / 2` from the location, so the mixture widens the
distribution and leaves its mean where the fit put it. Locked in by
`test_the_uncertainty_mixture_is_mean_preserving`.

#### Defect 2 — the conditional signal was over-extended, not merely uncertain

My first hypothesis was that coefficient estimation uncertainty was not propagated.
That was true, and I fixed it — the inverse observed information is now carried into
the predictive variance. **It made almost no difference**, and measuring why was the
useful part:

```
mean random-effect variance   0.01831
mean coefficient variance     0.00034   <- 1.8% of the total
```

At 30,000 training rows the slopes really are precisely estimated. Overconfidence
was not uncertainty about the coefficients. It was the coefficients being *too
large*:

```
corners: slope of observed count on fitted log-mu
  IN-SAMPLE      b = 1.008   (sd of log-mu 0.200)
  OUT-OF-SAMPLE  b = 0.754   (sd of log-mu 0.196)
```

In-sample the fit is perfect by construction, which is exactly why this stayed
invisible until it was measured out of sample. The fitted spread in `log mu` is
about a quarter too wide for the relationship that actually holds on unseen
fixtures. The ridge penalty (0.02) and the empirical-Bayes shrinkage were not enough,
and neither was ever tuned against held-out data.

Fixed by estimating a **scalar shrinkage of the fitted log-mean deviation on a
held-out tail of each training fold**. A probe model is fitted on the earlier
portion and scored on the later portion, so the estimate can see the gap. The
recovered scales land almost exactly on the independently measured out-of-sample
slopes:

| Family | measured OOS slope | fitted scale |
|---|---:|---:|
| corners | 0.754 | 0.750 |
| goals | — | 0.825 |
| cards | — | 0.825 |
| shots on target | — | 0.750 |
| first-half corners | — | 0.700 |

The shrinkage is applied to the deviation from the **league-typical** mean, not to
the baseline — shrinking the baseline would drag every league toward a global average
that no league occupies. And because it is one scalar applied to the mean *before*
any line is read, **cross-line monotonicity is preserved by construction**, which a
per-line recalibration map would have destroyed. Asserted by
`test_signal_scale_preserves_monotonicity` across scales 0.2 to 1.3.

### Candidate C: confirmed for cards, and in the opposite direction for corners

Residual correlation between the two sides after conditioning on their fitted means:

| Family | residual corr | observed/implied total variance | verdict |
|---|---:|---:|---|
| cards | **+0.181** | 1.105 | variance understated ~10% |
| first-half cards | **+0.137** | 1.038 | variance understated ~4% |
| corners | **−0.209** | 0.806 | variance *overstated* ~20% |
| first-half corners | −0.162 | 0.879 | overstated ~12% |
| goals | −0.023 | 0.916 | acceptable |
| shots on target | −0.039 | 0.973 | acceptable |
| first-half goals | −0.047 | 0.935 | acceptable |

Two genuinely different mechanisms, and the signs are informative:

- **Cards are positively coupled.** A bad-tempered match produces cards for both
  sides. Conditional independence understates the variance of the total, so the
  published tails are too thin.
- **Corners are negatively coupled.** Territorial dominance is competitive — a team
  camped in the opposition half wins corners *instead of* its opponent. The
  convolution *overstates* total variance by 20%.

This is unfixed. It is the largest remaining piece of model misspecification and
needs a dependence structure, not a parameter tweak.

### Result of the two fixes

Excess ECE over each arm's own null floor, six leagues:

| Family | before | after Jensen fix | after both fixes | climatology | model now better? |
|---|---:|---:|---:|---:|:---:|
| shots on target | +0.0285 | +0.0233 | **+0.0109** | −0.0035 | no |
| cards | +0.0297 | +0.0271 | **+0.0237** | +0.0283 | **yes** |
| first-half corners | +0.0197 | +0.0212 | **+0.0154** | +0.0175 | **yes** |
| first-half cards | +0.0195 | +0.0174 | **+0.0141** | +0.0135 | ~tie |
| corners | +0.0081 | +0.0087 | **+0.0056** | +0.0041 | no |
| first-half goals | +0.0037 | +0.0072 | **+0.0027** | +0.0026 | ~tie |
| goals | +0.0097 | +0.0027 | **+0.0021** | −0.0001 | ~tie |

Reliability slopes moved toward 1 in every family:

| Family | before | after |
|---|---:|---:|
| corners | 0.788 | **0.880** |
| shots on target | 0.795 | **0.872** |
| first-half corners | 0.613 | **0.714** |
| goals | 0.883 | **0.934** |
| first-half cards | 0.860 | 0.869 |
| cards | 0.864 | 0.866 |
| first-half goals | 0.977 | 0.981 |

Shots on target improved most: excess ECE down 62%. Mean bias on goals fell from
+0.0153 to +0.0015. The model went from behind climatology in all 7 families to
ahead or level in 4 of 7.

### Result on the full 25-league corpus

Re-running the whole walk-forward (475 cells, 88,413 fixtures) with both fixes:

| | before | after |
|---|---:|---:|
| cells FDR-flagged as miscalibrated | 31 | **0** |
| median observed ECE | 0.0461 | **0.0402** |
| median **excess** ECE over the null floor | +0.0140 | **+0.0081** |
| cells at or below their null floor | 115/475 | **144/475** |
| lines where model Brier beats climatology | 12/19 | **17/19** |
| lines where model ECE beats climatology | 2/19 | 4/19 |
| monotonicity violations | 0 | 0 |

Median ECE by family: corners 0.0510 → 0.0394, shots on target 0.0573 → 0.0460,
first-half corners 0.0480 → 0.0440, cards 0.0437 → 0.0415, first-half cards
0.0350 → 0.0328, first-half goals 0.0291 → 0.0273, goals 0.0412 → 0.0411.

**Every cell now passes the calibration test at q = 0.05.** ΔBrier against
climatology went from mixed — negative on all four corners lines — to positive on 17
of 19 lines; only first-half corners remains negative.

Fitted signal scales at the final fold are higher than on the six-league subset
(0.775–0.975 against 0.700–0.825), which is the correct behaviour: the final fold has
far more data, so there is less over-extension to correct. The scale is a measurement,
not a constant.

**The remaining honest gap is raw ECE against climatology, 4 of 19 lines.** That
comparison is the unfair one — at 12,700 pooled predictions the two arms occupy
different numbers of reliability bins — and the fair per-cell excess-ECE comparison
now has the model ahead or level on 4 of 7 families. But it is not yet a clean win,
and shots on target and goals remain behind on both.

---

## Part 2 — What is missing to be more calibrated

Ranked by expected value per unit of effort, from the audit rather than from taste.

### 1. A dependence structure between the two sides (largest remaining defect)

Cards understate total variance by 10%, corners overstate by 20%. Both are
systematic and both are now measured. Options, cheapest first:

- **A shared match-level random effect** on `log mu` for both sides, fitted per
  family. One extra parameter, induces positive correlation. Handles cards; cannot
  produce the negative correlation corners needs.
- **A fitted correlation on the count copula.** Replace the independent convolution
  with a Gaussian-copula coupling of the two side distributions, correlation
  estimated from residuals per family, allowed to be negative. Handles both signs.
  Monotonicity survives, since the total is still one PMF.
- **Model the split directly**: total and share, i.e. fit total count and the home
  share separately. Structurally sidesteps the correlation, but loses the clean
  attack/defence separation the explanation layer uses.

The copula is the right answer. Roughly a day, and it is the only item here that
addresses a defect the audit has already localised to a specific number.

### 2. Non-stationarity, especially in cards

Cards is the one family where **climatology is also badly calibrated** (excess
+0.0283). When a constant base rate estimated on training data misses on test data,
the base rate itself is moving — referee directives, rule changes, mid-season
crackdowns. No amount of conditional modelling fixes a drifting intercept.

- Time-decayed climatology and a time-decayed league intercept (the half-life
  machinery already exists in `DixonColesModel`, it is simply not wired into this
  path).
- A season-level random walk on the league intercept rather than one intercept per
  season-instance.
- Report the drift so it is visible: base rate per season per league, per family.

### 3. Tune regularisation instead of shrinking after the fact

The signal scale is a correction applied *after* an over-extended fit. Better to not
over-extend: tune the ridge by inner-fold cross-validation inside each training
fold. The scale should then come out near 1.0 on its own, and a scale that still
lands at 0.75 after tuning would be telling us the features are weak rather than the
penalty is loose. Keep the scale as a safety net and as a diagnostic.

### 4. Isotonic recalibration of the total distribution

A monotone map applied to the fitted **mean** (not per line) preserves coherence and
would mop up whatever curvature the single scalar cannot. This is also the natural
fix for the BTTS calibration gap (derived ECE 0.0173 vs direct 0.0035) without
giving up coherence with the goals lines.

### 5. Better features for the weak families

Shots on target remains the worst family, and it is the one whose named mechanisms
are most absent from the broad corpus — no touches in the penalty area, no big
chances, no blocked shots. The Championship rich cache has all of them. The honest
options are to narrow shots on target to leagues where the rich fields exist, or to
publish it with wider intervals, or to drop it. **It should not be published at the
same implied confidence as goals.**

### 6. Per-league dispersion, once there is enough data

Currently one α per family. Per-league residual dispersion is already measured and
reported; it is not used because on a few hundred rows it is noisier than the pooled
estimate. With a hierarchical prior on α it could be partially pooled like everything
else.

---

## Part 3 — Production grade

What exists: freshness gate, leakage assertions, commit-then-send with hash
commitments, content gate, append-only ledgers, minimum-history gate, minimum-sample
gate, per-league FDR, coverage and dispersion audits, 2,900+ tests. That is a
stronger base than most.

What is missing, in dependency order:

### Correctness and coherence
- **Cross-family coherence is unguarded, though not currently violated.** Nothing
  asserts that first-half goals ≤ full-match goals, or first-half corners ≤
  full-match corners, for the same fixture — they are separate fits and nothing ties
  them together. I checked before claiming it was broken: **0 violations in 635
  tested fixtures for both pairs**, because the half families are fitted on
  genuinely smaller counts and land below the full-match means on their own. So this
  is an unguarded invariant rather than an active bug. It still deserves an
  assertion, because "true by accident" and "true by construction" fail differently:
  the first breaks silently the first time a half family's league intercept drifts.
  A test is now in place; the structural fix, if it ever fires, is to fit the half as
  a share of the match rather than as an independent count.
- BTTS-versus-goals coherence *is* enforced structurally and tested.

### Operational
- **No model-drift alarm.** If `signal_scale` collapses, dispersion jumps, or a
  league's ECE degrades fold over fold, nothing notices. The health report exists;
  these fields are not in it.
- **No fallback on fit failure.** A family whose fit raises is silently skipped for
  that fold. It should degrade to climatology explicitly, labelled as such in
  provenance, not vanish.
- **Refit cost has doubled** with the probe fit. Fine offline; wants caching or an
  incremental update before it runs against every scheduled broadcast.
- **No shadow mode.** New model versions should run alongside the incumbent and be
  compared on identical fixtures before replacing it.
- **Reproducibility is asserted but not pinned**: no seed recorded in the model
  version hash, no environment lock captured with the artifact.

### Evaluation
- The 30-day window is built but **not open**, and the power arithmetic says
  per-league-per-line calibration is roughly five months away, not one.
- **Pool intelligently instead of waiting.** A cell needs ~200 settled
  observations; a market pooled across lines and leagues reaches that in weeks.
  Report per-market-pooled first, per-league later, and say which is which.
- The **cross-family and cross-line coherence checks should run on live output**,
  not only in the offline evaluation.

---

## Part 4 — Using the forecast to bet, and testing the experiment

Direct answer: **the engine is not ready for money, and the audit says why in
numbers rather than in caution.** But the experiment is worth building now, because
building it is what makes the eventual decision evidence-based.

### Why not yet

1. **No price has ever been compared.** Betting requires beating a closing price
   after vig, typically 4–6% on these markets. Calibration is necessary and nowhere
   near sufficient. This engine has never been scored against a price — the EV
   objective was declared closed and out of scope, and `capture_prices_for_fixture`
   stores prices without ever feeding them back.
2. **Calibrated is not the same as edged.** On three of seven families the model
   only ties league climatology on excess ECE. A model that matches a base rate
   cannot beat a price that also knows the base rate.
3. **Residual overconfidence points the wrong way for staking.** Slopes still sit at
   0.71–0.88 on four families. Overconfident probabilities systematically overstate
   edge, and any stake sizing computed from them — Kelly especially — overstakes in
   exactly the spots where the model is most wrong.
4. **The known misspecification is concentrated in the tails**, which is where
   priced value usually appears. Corners total variance is overstated 20%: the model
   is *most* wrong precisely at the lines someone would want to bet.
5. **The governance in this repo already forbids it**, and for reasons that were
   learned expensively. The content gate blocks EV and staking language; promotion
   gates require prospective attestation; the 30-day window has not opened. Those
   were built after prior discovery runs collapsed under FDR correction. I am not
   going to route around them.

### The experiment worth building, in order

**Stage 0 — close the loop on price (no stakes).** Prices are already captured. Join
them to forecasts and record, per line: model probability, closing price, implied
probability, and the sign of the difference. Publish nothing. This is the missing
measurement and it costs nothing to start.

**Stage 1 — CLV as the primary endpoint, not profit.** Closing-line value is the
only signal that resolves in weeks rather than years, because it has far less
variance than realised P&L. If the model cannot beat the *opening-to-closing* move,
it will not beat the close. Fail here and stop; the loop is short and cheap.
Existing infrastructure: `data/clv_panel/`, `src/research/closing/`.

**Stage 2 — paper portfolio, attested, flat stakes.** Flat stakes, not Kelly:
fractional Kelly on overconfident probabilities is the fastest route to ruin, and
flat staking makes the calibration question and the sizing question separable.
`src/research/paper/` and the attestation ledger already exist. Commit before
kickoff, hash it, settle honestly, publish misses.

**Stage 3 — the pre-committed decision rule, written before any result is seen.**
Sample size, minimum CLV, per-league requirement, FDR family, and the stop rule, all
fixed in advance. This is the step that prior runs skipped and it is why their
findings evaporated.

**Stage 4 — only then, and only if Stages 1–3 clear, real stakes at a size where
being wrong is affordable.**

### What to fix first if betting is the goal

The order changes from the pure-forecasting order:

1. **The corners copula.** Corners has the most lines, the most liquid market, and a
   20% variance overstatement concentrated in the tails.
2. **Price join and CLV measurement.** Until this exists there is no evidence either way.
3. **Vig-aware comparison.** Compare against the de-vigged two-way price, not the raw one.
4. **Per-market calibration on settled data**, pooled across lines to reach the
   sample gate in weeks rather than months.
5. **Drop or quarantine shots on target** for staking purposes until its features
   exist in the corpus. It is the worst-calibrated family and it is the one with the
   thinnest market.

One thing to be plain about: if you want me to build Stages 0–3, that is a change of
objective from what was declared closed, and it will need the content gate and
promotion gates handled deliberately rather than bypassed — a separate research-only
surface that never touches the published broadcast, which is how the manual
predictor and scanner are already isolated. I can build that. I would not change the
broadcast path to carry it.

---

## Summary

| Question | Answer |
|---|---|
| Why worse on ECE? | Two real bugs, not a measurement artifact. My original explanation was wrong. |
| Bug 1 | Uncertainty mixture inflated the mean by up to 13% (Jensen). Fixed. |
| Bug 2 | Conditional signal over-extended: in-sample slope 1.008 vs 0.754 out of sample. Fixed by out-of-sample scalar shrinkage. |
| Was any of it a measurement artifact? | ~70% of the *headline* ECE was sampling noise, and the FDR test already handled that. The model-vs-climatology gap was not. |
| Result | Excess ECE down in 6 of 7 families, slopes toward 1 in all 7, now ahead of or level with climatology in 4 of 7. |
| Largest remaining defect | Side dependence: cards +0.18 correlation, corners −0.21. Needs a copula. |
| Ready to bet? | No. Never compared against a price, ties a base rate on 3 of 7 families, and residual overconfidence overstates edge. |
| Right next step for betting | Stage 0/1: join captured prices and measure CLV. Cheap, fast, and decisive either way. |
