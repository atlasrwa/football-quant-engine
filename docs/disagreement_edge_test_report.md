# Disagreement-Concentrated Edge Test

**Date:** 2026-08-29
**Status:** Complete — **FATAL negative result.** Model performance *degrades* with disagreement.
**Cost:** Zero API calls. All inputs cached.

---

## The question

The prior EV test (`docs/ev_test_report.md`, ledger F013) measured *average* edge across all
321 matches and found the market wins by −2.20% mean ΔBSS. But an average can hide a strategy
that is right on a concentrated minority of fixtures and neutral elsewhere.

This test asks a different question: **in the matches where our model most disagrees with the
market, who is right?** The thesis being tested is that edge is *concentrated* where public
narrative and underlying data diverge, and that averaging washes it out.

The verdict: **the thesis is not just unsupported — it is refuted in the most damaging way.**
The model is *most wrong exactly where it disagrees most with the market.* This is the
signature of a mis-specified model, not concealed edge.

---

## Method (no model substitution, no refit, no retune)

The analysis script `scripts/disagreement_edge_test.py` **imports
`scripts/ev_test_metrics_vs_bet365.py` verbatim** and reuses its functions to produce the
per-match model probability and vig-adjusted market probability. Nothing about the model was
changed:

| Component | Detail (identical to the EV test) |
|-----------|-----------------------------------|
| Model | Poisson GLM with L2 regularization (λ=0.01) |
| Team shrinkage | Empirical Bayes, strength=10 |
| Features | The 7 validated metrics exactly as defined in `metric_library.json` |
| Training | Walk-forward: fitted on all corpus data before the earliest odds match |
| Vig removal | **Multiplicative** (proportional): `P_fair = P_raw / Σ P_raw` |
| Sample | Same 321 EPL/La Liga 2024-25 Bet365-cached matches, same crosswalk join |

**Disagreement** for each match, per metric/line, is defined as:

```
disagreement = | model_P(over) − market_fair_P(over) |
```

The *only* new computation is re-slicing those existing per-match numbers by disagreement.

### Bucketing choice (stated up front, no post-hoc boundary tuning)

- **Per metric/line combo → quintiles (5 buckets).** Per-combo sample sizes are 70–281.
  Deciles would put 7–28 matches per bucket — too thin for even a wide CI to mean anything.
  Quintiles give 14–57 per bucket. Boundaries are equal-count splits on sorted disagreement;
  no boundary was moved to improve any result.
- **Pooled across all 17 combos → deciles (10 buckets).** To get the decile resolution the
  brief asks for, we pool all metric/line rows (3,088 rows). Disagreement is **z-scored within
  each combo** before pooling so markets with different overround scales are comparable.
  **Caveat:** the 3,088 rows are *not* independent matches — one fixture contributes to
  multiple metric/line combos — so the pooled CIs understate correlation and the pooled view
  is descriptive, not a clean significance test. It is reported as the requested decile view,
  read alongside the 17 independent per-combo tests.

All buckets and all 17 metric/line combos are reported below. Nothing was dropped.

---

## Step 4 — The decisive cross-bucket pattern

**Pooled deciles (low → high disagreement), model−market BSS head-to-head:**

| Decile | n | Market BSS | Model BSS | **Model − Market BSS** | Dir. acc. | Follow-disagreement ROI (95% CI) |
|--------|---|-----------|-----------|------------------------|-----------|----------------------------------|
| D1 (lowest) | 308 | +8.31% | +8.34% | **+0.04%** | 53% | +0.2% [−12.3, +13.3] |
| D2 | 309 | +11.41% | +11.37% | −0.03% | 53% | +1.4% [−11.1, +14.4] |
| D3 | 309 | +10.06% | +9.44% | −0.62% | 47% | −13.5% [−25.1, −1.4] |
| D4 | 309 | +15.15% | +15.30% | +0.15% | 51% | −7.9% [−19.0, +3.5] |
| D5 | 309 | +16.02% | +13.20% | −2.81% | 44% | −18.4% [−29.9, −6.0] |
| D6 | 308 | +4.01% | +1.68% | −2.33% | 46% | −10.9% [−23.2, +2.0] |
| D7 | 309 | +13.98% | +11.64% | −2.34% | 47% | −9.7% [−21.8, +2.9] |
| D8 | 309 | +10.80% | +11.76% | +0.96% | 50% | +1.5% [−11.6, +15.0] |
| D9 | 309 | +14.29% | +13.22% | −1.07% | 52% | +2.4% [−10.6, +15.8] |
| **D10 (highest)** | 309 | +16.79% | +2.31% | **−14.48%** | **41%** | **−18.1% [−29.9, −5.7]** |

**Pattern: DEGRADES WITH DISAGREEMENT.** Correlation between decile index and model−market BSS
is **−0.56**. The relationship is not perfectly monotonic in the middle deciles, but the
direction is unmistakable and the endpoints are decisive: the lowest-disagreement bucket is a
dead heat with the market (+0.04% BSS), while the highest-disagreement bucket collapses to
**−14.48% BSS** — the model gives back almost all of the market's calibration edge precisely
where it is most confident that the market is wrong.

This is the outcome the brief flagged as *"fatal … the most important possible finding."*
It means the model is most wrong exactly when it departs most from the market — the signature
of a mis-specified model rather than an exploitable edge.

### Per-combo confirmation (17 independent tests, quintiles)

The pooled view is corroborated by the independent per-combo tests, so it is not an artifact
of the pooling:

| Pattern (low→high disagreement) | Count of 17 combos |
|---------------------------------|--------------------|
| DEGRADES with disagreement | **8** |
| FLAT / no monotonic relation | 8 |
| IMPROVES with disagreement (supports thesis) | **1** |

The degradation is strongest on goals at high lines, where it is nearly monotone:

| Combo | n | corr(quintile, model−market BSS) | Pattern |
|-------|---|----------------------------------|---------|
| goals_count_xg @ 3.5 | 281 | **−0.93** | DEGRADES |
| goals_sot_xg @ 3.5 | 241 | −0.87 | DEGRADES |
| goals_count_xg @ 2.5 | 281 | −0.81 | DEGRADES |
| goals_sot_count @ 3.5 | 241 | −0.76 | DEGRADES |
| goals_sot_count @ 2.5 | 241 | −0.68 | DEGRADES |
| goals_sot_xg @ 1.5 | 241 | −0.66 | DEGRADES |
| cards_with_fouls @ 3.5 | 70 | −0.52 | DEGRADES |
| goals_sot_count @ 1.5 | 241 | −0.51 | DEGRADES |

**The lone exception:** `cards_minimal_pair @ 4.5` (n=144) shows IMPROVES (corr +0.64). This is
exactly the kind of single favorable slice that multiple-comparison risk predicts you will find
if you cut 17 ways — and it is the same line/metric family flagged in the prior EV test as "the
only glimmer." It is a hypothesis, not a result. Notably, the *other three* cards metrics at
the same 4.5 line are FLAT, not IMPROVES, which undercuts reading `cards_minimal_pair@4.5` as a
real localized edge.

---

## Step 5 — Directional split of the top-disagreement bucket

Splitting the pooled top decile (n=309) by the direction of disagreement:

| Direction | n | Model − Market BSS | Dir. accuracy | Follow ROI (95% CI) |
|-----------|---|--------------------|---------------|---------------------|
| Model says HIGHER than market (bet OVER) | 112 | −15.04% | 49% | −15.4% [−32.6, +2.2] |
| Model says LOWER than market (bet UNDER) | 197 | −14.60% | **37%** | −19.7% [−35.6, −3.1] |

**Both directions lose.** There is no asymmetry that would rescue the narrative-bias mechanism.
The narrative-mispricing story predicts the model should win specifically on the UNDER side (the
public backs OVER on marquee fixtures, the book leans that way, and a data-driven model catches
the over-pricing). We see the opposite: the model is *worse* on the UNDER side (directional
accuracy 37%, ROI −19.7% with a CI that excludes zero). When the model most strongly says
"lower than the market," it is right only 37% of the time — the market's higher number is
closer to reality. This is the reverse of the proposed mechanism.

A secondary observation: in the top decile the model disagrees *downward* far more often than
upward (197 LOWER vs 112 HIGHER). Its large departures are predominantly "the market is too
high," and those departures are predominantly wrong.

---

## Step 6 — What the high-disagreement fixtures look like (hypothesis-generating only)

**This section is exploratory, not validated.** It describes the top-decile fixtures to see
whether they match the "marquee/derby narrative" story.

**Important multiplicity caveat:** the top decile is 309 *rows* but only **86 unique matches** —
each fixture recurs across several metric/line combos, so the raw counts below are inflated by
that repetition and should be read as *relative* prominence, not match counts.

- **League:** overwhelmingly EPL. Competition 12325 (EPL) contributes 285 of 309 rows;
  La Liga (12316) only 24. High disagreement is an EPL phenomenon in this sample.
- **Teams most prominent** (row counts, inflated by multiplicity): Southampton (66),
  Wolverhampton (56), Everton (55), Liverpool (52), Ipswich Town (51), Tottenham (46),
  Arsenal (32), Manchester City (31).
- **Pairings:** Liverpool–Southampton, Everton–Wolves, Chelsea–Southampton, Ipswich–Wolves,
  Ipswich–Liverpool.
- **Referees:** no single referee dominates; the top referee IDs (743, 733, 735, 1248) each
  appear in a similar number of rows — no obvious referee-driven concentration.

**Interpretation:** the high-disagreement fixtures are **not** predominantly marquee derbies.
They are dominated by *promoted / relegation-threatened / high-variance sides* (Southampton,
Ipswich, Wolves, Everton) plus a few big clubs that appear because they *play* those sides. This
is consistent with the mechanical explanation below, and it **does not support** the
narrative-mispricing hypothesis: if anything, the model departs most from the market on teams
with thin or unstable recent histories, and it is wrong when it does.

---

## Why this happens (mechanism)

The disagreement is largest where the model's rolling-average features are least reliable:
newly promoted teams (Ipswich, Southampton) and volatile mid/lower-table sides have short or
noisy histories, so the Poisson GLM produces extreme λ estimates that swing its `P(over)` far
from the market. The market, which incorporates far more information, does not make those
swings. When the two most diverge, it is because the *model* has over-reacted to a noisy rolling
average, not because the market has mispriced a narrative. Hence: high disagreement → model
over-confidence on thin data → model loses.

This also explains why the prior EV test's *average* looked merely "slightly worse than market"
(−2.20%): the low-disagreement matches (most of the sample) are a near dead-heat with the
market, and they dilute the concentrated losses in the high-disagreement tail. Slicing by
disagreement reveals that the loss is *concentrated*, not uniform — the opposite of the
concentrated *edge* the thesis hoped for.

---

## Honest interpretation — limitations (required)

1. **Wide confidence intervals.** Per-combo quintiles hold 14–57 matches; even pooled deciles
   are ~309 *rows* but only ~30 *unique* matches' worth of independent information per bucket.
   Every per-bucket CI is wide. The top-decile follow-ROI CI is [−29.9%, −5.7%] — it excludes
   zero on the *losing* side, which is the direction that matters here, but the point estimate
   is still imprecise.

2. **Multiple-comparison risk cuts both ways.** We ran 17 per-combo tests plus a pooled test.
   The single IMPROVES result (`cards_minimal_pair@4.5`) is exactly what chance would produce
   from 17 slices and should not be read as a discovered edge. Equally, the *degradation*
   finding is robust precisely because it appears in 8/17 independent combos and the pooled
   view, all pointing the same way — a coordinated pattern is far harder to produce by chance
   than one good-looking bucket.

3. **Pooled rows are not independent.** A fixture appears under multiple metric/line combos, so
   the pooled n=3,088 overstates independent information. The pooled decile table is the
   requested decile-resolution view but should be read as descriptive; the 17 per-combo tests
   are the independent evidence.

4. **This is a subset analysis on data already examined.** Same caveat as the brief states: any
   pattern found here is a hypothesis about *this* sample. The degradation direction is
   consistent and mechanistically explicable, which raises confidence, but it is still one
   sample.

---

## Follow-up test (what would confirm this)

Because this is a subset analysis on previously examined data, the finding must be confirmed on
data not used here:

> **Re-run the identical disagreement-decile analysis on held-out or newly acquired matches**
> (a different season, or additional leagues) that were not part of these 321. Use the frozen
> model and the same disagreement definition and bucket boundaries logic. If high-disagreement
> matches again show the worst model−market BSS and negative follow-ROI, the "disagreement is
> anti-informative" conclusion is confirmed and it becomes a stable diagnostic property of the
> model class. If the degradation vanishes, this sample's tail was noise.

A degrading pattern is *less* likely to be a fluke than a positive one (there is no incentive to
manufacture a self-damaging result), but the confirmation step is still required before treating
it as a general property.

---

## Bottom line

- **Thesis (edge concentrated in high-disagreement matches): REFUTED.** Model performance
  *degrades* as disagreement rises (pooled corr −0.56; 8/17 combos DEGRADE, 1 IMPROVES).
- **Top decile: model−market BSS −14.48%, directional accuracy 41%, follow-ROI −18.1%
  [−29.9, −5.7].** The model is most wrong where it is most confident the market is wrong.
- **No narrative-bias asymmetry.** Both over- and under-disagreement lose; the model is *worse*
  on the UNDER side, the reverse of what the narrative mechanism predicts.
- **High-disagreement fixtures are noisy/promoted/mid-table sides, not marquee derbies** —
  consistent with the mechanical explanation (unreliable rolling averages), not narrative
  mispricing.
- This *strengthens* the prior EV-test conclusion (F013): the metrics are not merely priced in
  on average — their disagreements with the market are actively anti-informative.

---

## Artifacts

- Analysis script: `scripts/disagreement_edge_test.py` (imports the EV test module verbatim)
- Raw results: `data/results/disagreement_edge_test.json`
- Reused pipeline: `scripts/ev_test_metrics_vs_bet365.py`
- No shared/global config was modified.
