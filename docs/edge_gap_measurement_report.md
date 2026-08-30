# Quantify the Edge Gap vs Bet365 — Measurement Report

**Date:** 2026-08-30
**Nature:** Measurement, not discovery. No new candidates, no FDR, no metric-library changes.
**Data:** 100% cached. **Zero API requests** (quota unchanged at 5,518). Reuses
`scripts/ev_test_metrics_vs_bet365.py` **verbatim** — Poisson GLM+L2, team empirical-Bayes
shrinkage, multiplicative de-vig. **No refit, no substitution** of the 7 validated metrics.
**Sample:** 281 unique matches (EPL 266, La Liga 15 with usable odds), 3,088 metric×line×match
rows across cards O3.5/O4.5 and goals O1.5/O2.5/O3.5. **Held-out set untouched.**

## The three questions, answered numerically

1. **What edge is required?** ~**3–4.6 percentage points** (model prob must exceed the
   vig-adjusted fair prob by this much for a +EV flat back bet).
2. **What edge do we have?** Median **−1.3pp** overall (model sits *below* fair market);
   near-zero to slightly negative on goals; the only large-positive cell is a known model
   over-prediction artifact, not edge.
3. **Is there market error to exploit, and is it predictable?** **No.** 23 of 24 reliability
   bins are statistically consistent with pure sampling noise; Bet365 is calibrated to within
   sampling error. There is no reliable error mass, so nothing to predict.

### The gap, in plain percentage points

> **The required edge is ~3–4.6pp. The actual median edge is ~−1.3pp. The gap is ~4–5pp, and
> it is a chasm, not a near-miss.** Separately, and more decisively: even a perfect model has
> nothing to exploit, because Bet365's pricing shows no reliable error beyond sampling noise at
> this sample size.

---

## Measurement 1 — Required break-even edge

Overrounds (confirmed from cached odds): **cards ~7.9–8.1%**, **goals ~5.2%** — matching the
brief's ~8% / ~5%. A back bet at decimal odds `o` is +EV iff `model_p > 1/o`, so the required
edge over the *fair* (de-vigged) prob is `(1/o − fair_p)`.

| Market / line | Overround | Break-even edge (median) | Range across prices |
|---|---|---|---|
| cards O3.5 | 7.88% | **4.18pp** | 3.05 – 4.64pp |
| cards O4.5 | 8.08% | **4.07pp** | 3.05 – 4.64pp |
| goals O1.5 | 5.24% | **4.34pp** | 2.99 – 4.89pp |
| goals O2.5 | 5.26% | **3.03pp** | 1.43 – 4.01pp |
| goals O3.5 | 5.20% | **2.00pp** | 0.80 – 3.06pp |

The threshold is **not constant across the odds range**: it is largest near even-money /
favorites (a fixed overround share is more pp there) and smallest for low-probability overs
(goals O3.5 needs only ~2pp). This is the bar, stated numerically.

## Measurement 2 — Actual edge distribution

`edge = model_p_over − fair_market_p_over`, per match, 7 metrics as-defined.

**Overall (n=3,088 rows):** mean −0.9pp, **median −1.28pp [bootstrap 95% CI −1.57, −1.00]**,
p5 −8.9pp, p25 −4.4pp, p75 +2.4pp, **p95 +10.9pp**. Only **24%** of rows exceed their own
break-even threshold. The distribution is roughly symmetric around a *slightly negative*
centre with fat tails — the fat right tail (p95 ≈ +11pp) is model *noise/over-confidence*, not
concentrated skill (see M3).

| Cell | n | median edge | p95 | break-even | **gap (median→bar)** | % exceed bar |
|---|---|---|---|---|---|---|
| cards O3.5 | 283 | **+6.06pp** | +18.2pp | 4.05pp | −1.88pp* | 63%* |
| cards O4.5 | 516 | −4.60pp | +3.5pp | 3.98pp | **+8.68pp** | 5% |
| goals O1.5 | 763 | +0.03pp | +8.0pp | 4.15pp | **+4.31pp** | 19% |
| goals O2.5 | 763 | −1.54pp | +10.8pp | 3.04pp | **+4.58pp** | 27% |
| goals O3.5 | 763 | −2.86pp | +9.2pp | 1.96pp | **+4.86pp** | 26% |

\* **cards O3.5 is the one cell that appears to clear the bar — but it is a model
over-prediction artifact, not edge.** The model is known to over-predict at the 3.5 cards line
(F013); a large positive `model_p − fair_p` there means the *model* is too high, and M3 shows
the market at that line is calibrated within noise. So the "63% exceed" is the model being
systematically optimistic, which realized-return testing (F013: negative ROI, CIs spanning
zero) already refuted. It is not a real +EV opportunity.

**Every other cell shows a gap of +4.3 to +8.7pp** between the median edge and the bar — i.e.
the median bet is 4–9pp short of break-even. Per-league (EPL vs La Liga) is dominated by EPL
(La Liga n=15); no league reverses the picture.

## Measurement 3 — Bet365's error distribution (the decisive question)

Reliability construction: bin matches by market fair prob, compare each bin's mean market prob
against its realized over-rate. Raw picture *looks* like large error:

| Market/line | n | mean \|bin error\| | max \|bin error\| | bins within 2pp | signed |
|---|---|---|---|---|---|
| cards O3.5 | 73 | 6.14pp | 10.8pp | 25% | −0.7pp |
| cards O4.5 | 144 | 8.56pp | 13.1pp | 20% | +8.6pp |
| goals O1.5 | 281 | 3.65pp | 8.0pp | 40% | −1.8pp |
| goals O2.5 | 281 | 3.11pp | 5.7pp | 40% | +0.1pp |
| goals O3.5 | 281 | 7.02pp | 13.0pp | 0% | +1.9pp |
| **pooled** | — | **5.68pp** | — | **25%** | — |

**But these bin errors are sampling noise, not mispricing.** The critical test: does the market
prob fall inside the bin's realized-rate 95% CI? If yes, that bin's error is consistent with
pure noise. **Result: 23 of 24 bins are noise-consistent.** Only 1 of 24 (goals O3.5, the ~25%
bucket, n=41) lies beyond its CI — and with 24 bins tested, ~1.2 such false positives are
expected by chance at 95%. Bin sizes are 14–81 matches, so a realized rate's own 95% CI spans
±10–25pp — swamping the apparent "errors."

**Conclusion:** Bet365 is calibrated to within sampling error on essentially every bucket. The
5–13pp "errors" are the noise the brief warned averages would hide — here it's thin-sample bin
noise. **There is structurally no reliable error mass to exploit, regardless of model quality.**

## Measurement 4 — Predictability

Because M3's noise check shows **no reliable error**, the premise for M4 (a subset of genuinely
mispriced matches) does not hold. For completeness, the only ex-ante split examined was
**league** (multiple-comparison **family size = 1**; other pre-match characteristics —
referee, team, season — were already shown flat or anti-informative in F014/F016 and were not
re-mined, to keep the family honest). La Liga goals bins show large signed errors (−11pp at
O1.5, −6.7pp at O2.5) but at **n=15** — squarely within noise and consistent with M3. **There
is no predictable error pattern; any apparent one is a thin-sample artifact and would be a
hypothesis for held-out confirmation, not a result.**

## Interpretation (only what the numbers support)

- The brief posed two reference cases: "~1pp edge vs ~5pp bar = chasm" versus "~4pp vs ~5pp =
  materially different." **The data shows the chasm.** The median edge is *negative* (~−1.3pp);
  even the goals cells sit ~4–5pp below break-even; and the one positive cell is a model
  over-prediction the market prices correctly.
- More fundamentally, M3 makes the model question secondary: **there is no reliable market
  error to capture** at this sample size, so no realistic model improvement closes the gap.
- **Caveats (honest):** samples are thin (n=73 for cards O3.5 up to n=281 for goals; La Liga
  only n=15). CIs are wide and stated throughout. M3's "noise-consistent" verdict is itself a
  statement about *power*: with these n we cannot detect sub-~10pp per-bin mispricing even if it
  existed. The correct reading is not "we proved the market is perfect" but "we can rule out
  large exploitable error, and the model is nowhere near the bar even if small error exists."

## Ground-rules compliance

- Zero API calls — all cached; quota remains 5,518. ✓
- No refit/substitution of the 7 metrics (imported ev_test verbatim). ✓
- Distributions reported, not just means (full percentiles, per cell). ✓
- CIs on estimates; thin-n stated plainly. ✓
- Multiple-comparison discipline in M4 (family size = 1, reported; no best-slice mining). ✓
- Held-out set untouched. ✓
- No new candidates / FDR / metric-library changes. ✓
- No shared/global config changed. ✓

## Artifacts

| Item | Path |
|---|---|
| Measurement script (reuses ev_test verbatim) | `scripts/edge_gap_measurement.py` |
| Results | `data/results/edge_gap_measurement.json` |
| Reused pipeline | `scripts/ev_test_metrics_vs_bet365.py` (unmodified) |
