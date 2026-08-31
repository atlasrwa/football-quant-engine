# The Edge Gap, Quantified

**Date:** 2026-08-30
**Type:** Measurement only — no discovery, no refit, no metric changes
**API requests:** 0 (all cached). No live-access step was reached.
**Data:** 321 EPL/La Liga matches with cached Bet365 closing prices, 2024/25 season
(the discovery/older season). The held-out 2025/26 season was **not** touched.
**Method reuse:** The 7 validated metrics and their Poisson-GLM+L2+shrinkage model
were run **exactly as defined** (imported verbatim from
`scripts/ev_test_metrics_vs_bet365.py`). No model substitution, no refit of a
different model. Vig removed multiplicatively (proportional), matching the
validated pipeline.
**Raw output:** `data/results/edge_gap_measurement.json`
**Script:** `scripts/quantify_edge_gap.py`

This report converts "we keep failing to find edge" into a distance. It answers
three questions numerically and states the gap in plain percentage points (pp).

---

## Answer up front (the deliverable)

1. **What edge is required?** Roughly **4 pp** for the shorter-priced markets
   (cards 3.5, cards 4.5, goals 1.5) and **2–3 pp** for the longer-priced goals
   lines (goals 2.5 ≈ 3.0 pp, goals 3.5 ≈ 2.0 pp). The threshold is *not* constant
   — it falls as the odds lengthen, because a smaller share of the vig sits on the
   longer side.

2. **What edge do we have?** After removing the vig, the **median actual edge is
   negative or within ~1 pp of zero for essentially every metric/line** — with one
   apparent exception at cards 3.5 that Measurement 3 shows is a model
   *miscalibration* artifact, not real edge. The best legitimate median edge is
   **goals 2.5 with `goals_count_xg`: +0.7 pp** (95% CI −0.4 to +2.0 pp).

3. **Is there market error to exploit, and is it predictable?** For almost every
   market/line, **no** — Bet365's every well-populated reliability bucket lands
   within its 95% CI of the price. The single exception is **cards 4.5**, where the
   market appears to over-price the "over" by a weighted **~7 pp**; but (a) at
   n=144 that error's CI still spans zero, and (b) it is **not predictable
   ex-ante** — 0 of 5 tested pre-match characteristics produced a split whose CI
   excludes zero.

**The gap, in plain pp:** For the goals markets (the ones with real sample depth,
n=241–281), the honest median edge is **about 0 to +1 pp against a 2–4 pp
threshold — a shortfall of roughly 2 to 4 pp.** This is the "chasm," not the
"materially close" case: no realistic tuning of a 2-feature Poisson GLM closes a
2–4 pp gap when the market's own pricing error is already sub-2 pp on the matches
that matter.

---

## Measurement 1 — The required edge threshold

Break-even for a flat-stake back of the OVER at decimal odds `O` needs
`p_model = 1/O`. Against the vig-adjusted (fair) market probability `p_fair`, the
required edge is `1/O − p_fair`, which equals your side's share of the overround.

| Market / line | Overround (from cached odds) | Required edge — mean | median |
|---|---|---|---|
| Cards 3.5 | 7.87% | 4.05 pp | 4.18 pp |
| Cards 4.5 | 8.10% | 4.00 pp | 4.07 pp |
| Goals 1.5 | 5.24% | 4.15 pp | 4.34 pp |
| Goals 2.5 | 5.25% | 3.04 pp | 3.03 pp |
| Goals 3.5 | 5.20% | 1.96 pp | 2.00 pp |

Overrounds confirm the prior figures: **~5% goals, ~8% cards.** (Corners are not in
this top-tier 321-match odds cache, so no corners threshold is computed here; the
corners efficiency question is covered in `MARKET_EFFICIENCY_TIER_REPORT.md`.)

**The threshold varies by odds level** (why goals 1.5 needs ~4 pp but goals 3.5
only ~2 pp — the over side is priced longer at 3.5, so less vig sits on it):

| Price on the OVER (decimal) | 1.5 | 1.8 | 2.0 | 2.5 | 3.0 | 4.0 |
|---|---|---|---|---|---|---|
| Cards 3.5 (8% overround) | 4.86 | 4.05 | 3.65 | 2.92 | 2.43 | 1.82 |
| Goals (5.2% overround) | 3.30 | 2.77 | 2.49 | 1.99 | 1.66 | 1.24 |

Values are required edge in pp. **This is the bar.**

---

## Measurement 2 — The actual edge distribution

`edge = model_probability − vig_adjusted_market_probability`, per match, per metric,
per line. Full distribution below (pp). CIs on the median from 10k bootstrap.

| Metric / line | p5 | p25 | median | p75 | p95 | median 95% CI | threshold | **gap (thr−median)** | frac > thr |
|---|---|---|---|---|---|---|---|---|---|
| cards_minimal_pair / 3.5 | −1.2 | +5.5 | **+8.1** | +13.2 | +20.2 | [6.9, 10.1] | 4.05 | −4.1 | 82% |
| cards_best_pair / 3.5 | −4.5 | +2.3 | **+4.7** | +9.7 | +16.4 | [3.6, 6.8] | 4.05 | −0.7 | 56% |
| cards_with_fouls / 3.5 | −4.2 | +2.6 | **+5.0** | +10.0 | +16.7 | [3.9, 7.0] | 4.05 | −0.9 | 57% |
| cards_triple / 3.5 | −4.5 | +2.3 | **+4.7** | +9.7 | +16.4 | [3.6, 6.8] | 4.05 | −0.7 | 56% |
| cards_minimal_pair / 4.5 | −9.7 | −5.3 | **−2.0** | +1.0 | +6.2 | [−3.1, −1.1] | 4.00 | +6.0 | 11% |
| cards_best_pair / 4.5 | −12.0 | −8.5 | **−5.5** | −2.6 | +1.8 | [−6.5, −4.5] | 4.00 | +9.5 | 2% |
| cards_with_fouls / 4.5 | −11.8 | −8.3 | **−5.2** | −2.3 | +2.1 | [−6.2, −4.2] | 4.00 | +9.2 | 2% |
| cards_triple / 4.5 | −12.0 | −8.5 | **−5.5** | −2.6 | +1.8 | [−6.5, −4.5] | 4.00 | +9.5 | 2% |
| goals_sot_xg / 1.5 | −7.3 | −3.8 | **−1.0** | +1.7 | +7.2 | [−1.4, −0.6] | 4.15 | +5.2 | 13% |
| goals_sot_count / 1.5 | −8.3 | −3.8 | **−0.4** | +2.0 | +7.0 | [−1.1, +0.2] | 4.15 | +4.6 | 12% |
| goals_count_xg / 1.5 | −7.2 | −2.0 | **+1.5** | +4.4 | +8.4 | [0.9, 2.1] | 4.15 | +2.7 | 28% |
| goals_sot_xg / 2.5 | −15.0 | −7.7 | **−2.8** | +1.7 | +8.9 | [−3.6, −2.1] | 3.04 | +5.8 | 19% |
| goals_sot_count / 2.5 | −14.7 | −7.3 | **−2.4** | +1.7 | +8.3 | [−3.5, −1.0] | 3.04 | +5.5 | 17% |
| goals_count_xg / 2.5 | −13.3 | −5.1 | **+0.7** | +5.5 | +11.9 | [−0.4, +2.0] | 3.04 | +2.3 | 38% |
| goals_sot_xg / 3.5 | −17.3 | −9.1 | **−4.3** | +0.2 | +7.3 | [−5.2, −3.4] | 1.96 | +6.3 | 17% |
| goals_sot_count / 3.5 | −15.7 | −8.3 | **−3.3** | +0.5 | +6.5 | [−4.7, −2.2] | 1.96 | +5.3 | 17% |
| goals_count_xg / 3.5 | −14.7 | −6.2 | **−0.5** | +4.4 | +11.5 | [−1.6, +0.4] | 1.96 | +2.5 | 37% |

### How to read this

- **The wide spread is noise, not opportunity.** Every distribution has a p95 of
  +6 to +20 pp, so on individual matches the model *looks* like it has big edges.
  But the p5 is deeply negative and the median tells the real story. The 5th–95th
  spread is the model disagreeing with the market in both directions — prior work
  already showed performance *degrades* with disagreement, i.e. the spread is the
  model being wrong, not right (`disagreement_edge_test_report.md`).

- **Cards 3.5 is the one place the median edge exceeds the threshold** (+4.7 to
  +8.1 pp median > 4.05 pp threshold; 56–82% of matches "over" the bar). This is
  the trap. Measurement 3 shows Bet365 is essentially perfectly calibrated at cards
  3.5 (bucket errors ≤2.8 pp, all within CI). So a large positive "edge" there is
  the **model over-estimating the over** — a miscalibration the prior EV report
  already flagged — and it converts to **negative realized ROI** (−3% to −5%). It
  is edge on paper only.

- **The only legitimately positive median edge** is `goals_count_xg` at goals 2.5:
  **+0.7 pp**, CI [−0.4, +2.0]. Against a 3.0 pp threshold, that is a **~2.3 pp
  shortfall**, and the CI includes zero — consistent with no real edge at all.

**Which of the two scenarios does the data show?** The prompt framed it as
"~1 pp vs ~5 pp threshold (a chasm)" versus "~4 pp vs ~5 pp (materially close)."
The data shows the **chasm**: the credible median edge on the deep-sample goals
markets is **0 to +1 pp against a 2–4 pp bar**. We are not one modelling tweak
away; we are a structural distance away.

---

## Measurement 3 — Bet365's own error distribution

For each market/line, matches were binned by Bet365's vig-adjusted implied
probability (deciles); each bucket's predicted rate was compared to its realized
frequency. Buckets with n<8 are noise (their realized rate is uninformative) and
are reported separately, not folded into the verdict.

| Market / line | n | Weighted mean signed error | Weighted mean \|error\| | Max dense-bucket \|error\| | % matches within 5 pp* |
|---|---|---|---|---|---|
| Cards 3.5 | 73 | −1.9 pp | 1.9 pp | 2.8 pp | 100% |
| **Cards 4.5** | 144 | **+7.0 pp** | **7.0 pp** | **10.5 pp** | **58%** |
| Goals 1.5 | 281 | −0.9 pp | 1.1 pp | 3.1 pp | 100% |
| Goals 2.5 | 281 | +0.2 pp | 2.5 pp | 7.7 pp | 91% |
| Goals 3.5 | 281 | +1.3 pp | 4.8 pp | 7.7 pp | 71% |

*within 5 pp is computed on matches sitting in dense (n≥8) buckets.

**Systematic vs random:** In **every dense bucket of every market/line, the
realized rate falls inside the 95% CI implied by the price.** The eye-catching
per-bucket errors seen at first pass (43 pp on goals 1.5, 70 pp on goals 2.5,
18 pp on goals 3.5) were all **n=1–4 buckets** — pure sampling noise on the
tails, statistically consistent with the price. Where the market has real mass
(the n≈50–140 buckets), it is calibrated to within a few pp, with errors that
**scatter in sign** — the signature of *random* noise around a correct central
estimate, not systematic bias.

**The one exception is cards 4.5.** Both dense buckets show the market pricing the
"over" too high: predicted 45.5% vs realized 35.0% (n=60, +10.5 pp) and predicted
52.0% vs realized 47.6% (n=84, +4.4 pp). The errors are **same-signed** (looks
systematic) and only 58% of matches sit within 5 pp. This is the single structural
crack in 321 matches. Caveats that matter: at n=144 each bucket's realized rate
**still lies inside its 95% CI**, so the bias is *directionally suggestive but not
statistically established*; and cards odds in this cache are ~EPL-only, so this is
really "EPL cards 4.5, 2024/25, n=144."

**Structural verdict:** For goals (the deep-sample markets) and cards 3.5, Bet365
is tight enough that **there is structurally no room regardless of model quality.**
Cards 4.5 is the only place where the question "is there error to exploit?" gets a
maybe — so it is the only market that earns a Measurement 4.

---

## Measurement 4 — Are the cards-4.5 errors predictable ex-ante?

Triggered **only** for cards 4.5 (the only market/line with meaningful one-signed
error mass; all others were skipped as tightly calibrated, and that is stated).

Per-match error signal: `residual = fair_p_over − outcome_over` (positive = market
over-priced the over). Overall mean residual +7.0 pp, matching M3.

**Testing family: 5 pre-match characteristics** (reported per multiple-comparison
discipline). With 5 tests at α=0.05, ~0.25 false positives are expected by chance.

| Characteristic | Split | Δ mean residual | 95% CI | CI excludes 0? |
|---|---|---|---|---|
| League | comp A (n=139) vs comp B (n=5) | — | — | insufficient n (cards odds ~EPL-only) |
| Time of season | early gw vs late gw | −12.2 pp | [−28.1, +3.9] | No |
| Team-strength gap | mismatch vs even (ppg gap) | +0.3 pp | [−15.8, +16.7] | No |
| Expected tempo | high vs low (pre-match O2.5 price) | −1.3 pp | [−17.1, +14.6] | No |
| Referee | frequent (≥3 matches) vs rare | −8.6 pp | [−37.1, +23.3] | No |

**Result: 0 of 5 splits have a CI excluding zero.** No observable pre-match
characteristic identifies the mispriced matches. The largest point differences
(time-of-season −12 pp, referee −9 pp) have CIs several times wider than the
effect — indistinguishable from noise at this sample size, and each is one draw
from a family of 5.

Any of these could be a real pattern hiding under a thin sample — but **each is a
hypothesis, not a result.** Confirming any would require the held-out 2025/26
season, which was deliberately **not** touched. As it stands, the cards-4.5 error
is real-ish in aggregate but **not addressable ex-ante**, so it is not actionable:
you cannot bet the average, only individual matches, and nothing tells you which
ones in advance.

---

## Bottom line

- **Required edge:** ~4 pp (cards, goals 1.5), ~3 pp (goals 2.5), ~2 pp (goals 3.5).
- **Actual edge:** median 0 to +1 pp where the sample is deep; the only market with
  a median above its threshold (cards 3.5) is model miscalibration, not edge, and
  loses money in realized ROI.
- **Market error to exploit:** none in the deep-sample markets (Bet365's dense
  buckets all sit within CI of realized rates); one directional crack at cards 4.5
  (~7 pp over-pricing of the over) that is neither statistically established at
  n=144 nor predictable from any of 5 pre-match characteristics.

**The gap, plainly: about 2 to 4 percentage points on the goals markets, and it is
a chasm rather than a near-miss.** A 2-feature Poisson GLM does not close a 2–4 pp
gap against a market whose own residual error is under 2 pp on the matches that
carry the mass. The decisive number for the next decision is: **median actual edge
≈ 0–1 pp; required edge ≈ 2–4 pp; shortfall ≈ 2–4 pp.**

---

## Caveats (stated, not buried)

- **Thin samples, wide CIs.** Cards 3.5 n=70–73, cards 4.5 n=124–144, goals
  n=241–281. All median-edge and error CIs are correspondingly wide; several span
  zero. Point estimates here are not settled facts. The *direction* is consistent
  across the deep goals sample (n≈281), which is why the goals conclusion is more
  than a sample artifact; the cards conclusions are softer.
- **Cards odds are essentially EPL-only** in this cache, so cards findings are EPL
  2024/25, not "cards in general."
- **No corners** in this 321-match top-tier odds cache; corners efficiency lives in
  `MARKET_EFFICIENCY_TIER_REPORT.md` (Tier-1 corners BSS ≈ +0.007, ΔBSS us−market
  ≈ −0.010 — the market wins there too).
- **Multiplicative de-vig** was used (matching the validated pipeline). A different
  de-vig (e.g. Shin, additive) would shift `p_fair` by a fraction of the overround
  and move edges by tenths of a pp — not enough to change any conclusion.

## Process / ground-rules compliance

- **Zero API calls.** The measurement reads only cached JSON (`json.load`/`glob`);
  no network path is exercised. The on-disk `_budget_state.json` is from a prior
  session and was not modified by this run. (Note: that file records
  `last_monthly_remaining = 5770`, a prior-session snapshot; this run decremented
  nothing, so whatever the live quota was — the brief cites 5,518 — it is unchanged
  by this task.)
- **No refit / no substitution.** The 7 metrics and their model were imported and
  executed verbatim from the validated `ev_test_metrics_vs_bet365.py`. The
  Session-2-style model substitution error was avoided.
- **Held-out untouched.** Odds sample is the 2024/25 discovery season; the 2025/26
  held-out season (corpus index 0) was not read.
- **Distributions, not means.** Full percentiles reported for every edge
  distribution; the whole point was that averages hid the shape.
- **Multiple-comparison discipline.** M4 family size (5) reported; every split
  shown; no cherry-picking; any pattern flagged as needing held-out confirmation.
- **No new candidates, no FDR entries, no metric-library or shared-config changes.**
  Two new files were added and nothing shared was modified:
  `scripts/quantify_edge_gap.py` and `data/results/edge_gap_measurement.json`,
  plus this report. No global/shared config was touched.
