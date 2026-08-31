# EV Test Report: 7 Discovered Metrics vs Bet365

**Date:** 2026-08-28
**Status:** Complete — negative result (metrics do not beat market)

---

## Executive Summary

The 7 validated metrics (4 cards, 3 goals) were tested head-to-head against cached Bet365 closing prices on 321 EPL/La Liga matches from the 2024-25 season.

**Result: The market wins.** Bet365 is better calibrated than our metrics in 13 of 17 metric/market/line comparisons. The metrics are real (they beat a naive baseline as validated in discovery) but the signal they capture is already priced in by the market. This is not a failure of the metrics — it is evidence that the bar for exploitable edge sits substantially above "better than naive."

---

## Method

| Component | Detail |
|-----------|--------|
| Model architecture | Poisson GLM with L2 regularization (λ=0.01) |
| Team shrinkage | Empirical Bayes, strength=10 (shrink toward global mean) |
| Feature computation | Rolling window averages per team (w5 or w10), point-in-time safe |
| Training | Single point-in-time train/test fit (NOT per-match walk-forward): model fitted once on ALL corpus data strictly before the earliest odds match, coefficients frozen, then applied to every odds-sample match. Point-in-time safe. |
| Vig removal | **Multiplicative** (proportional overround removal): P_fair = P_raw / Σ(P_raw) |
| Join | TheStatsAPI → FootyStats via team crosswalk (confidence ≥ 0.9) + ±1 day date window |
| Sample | 321 matches with Bet365 odds cached; 100% join rate to FootyStats |

---

## Results: Cards Metrics

### Cards Over 3.5 (n=70–73)

| Metric | n | Model BSS | Market BSS | Δ (Model−Market) | Mean Edge | +EV Bets | Realized ROI |
|--------|---|-----------|------------|-------------------|-----------|----------|--------------|
| Minimal pair (w5+w5) | 73 | -4.22% | +0.79% | **-5.01%** | +9.30% | 67/73 (92%) | -5.25% [-27%, +17%] |
| Best pair (w5+w10) | 70 | -2.39% | +1.36% | **-3.75%** | +5.78% | 60/70 (86%) | -3.37% [-26%, +20%] |
| With fouls (b_w10+a_fouls_w5) | 70 | -2.46% | +1.36% | **-3.82%** | +6.06% | 61/70 (87%) | -4.95% [-28%, +18%] |
| Triple half-split | 70 | -2.39% | +1.36% | **-3.75%** | +5.78% | 60/70 (86%) | -3.37% [-26%, +20%] |

**Mean overround:** 7.88%

**Interpretation:** The model systematically OVER-estimates the probability of 4+ cards. The large positive "edge" (5–9%) is a miscalibration artifact — the model thinks overs are much more likely than both the market AND reality suggest. This manifests as negative BSS (worse than naive) and negative realized returns.

### Cards Over 4.5 (n=124–144)

| Metric | n | Model BSS | Market BSS | Δ (Model−Market) | Mean Edge | +EV Bets | Realized ROI |
|--------|---|-----------|------------|-------------------|-----------|----------|--------------|
| Minimal pair (w5+w5) | 144 | -0.02% | -1.12% | **+1.11%** | -1.99% | 50/144 (35%) | -10.56% [-38%, +16%] |
| Best pair (w5+w10) | 124 | -0.10% | -2.17% | **+2.07%** | -5.30% | 15/124 (12%) | -32.27% [-76%, +19%] |
| With fouls (b_w10+a_fouls_w5) | 124 | -0.19% | -2.17% | **+1.98%** | -5.00% | 17/124 (14%) | -27.29% [-75%, +22%] |
| Triple half-split | 124 | -0.10% | -2.17% | **+2.07%** | -5.30% | 15/124 (12%) | -32.27% [-76%, +19%] |

**Mean overround:** 8.10%

**Interpretation:** At the 4.5 line, our model marginally outperforms the market on BSS (+1–2%), but this advantage is tiny and comes with the model UNDER-predicting overs (negative mean edge). The market itself has negative BSS at this line — meaning both the market AND our model are slightly worse than naive at 4.5. The model's marginal advantage is not actionable: realized returns are deeply negative with CIs spanning zero.

### Cards Summary

The cards metrics show a consistent pattern:
- At 3.5 (higher base rate ≈60–70% over): model over-shoots, market is correctly calibrated
- At 4.5 (lower base rate ≈35–40% over): model marginally better than market, but both struggle

The signal validated in discovery (+1–2% BSS vs naive) is genuine but **orders of magnitude too small** to overcome the market's calibration advantage. The market already incorporates team-level card tendencies.

---

## Results: Goals Metrics

### Goals Over 1.5 (n=241–281)

| Metric | n | Model BSS | Market BSS | Δ (Model−Market) | Mean Edge | +EV Bets | Realized ROI |
|--------|---|-----------|------------|-------------------|-----------|----------|--------------|
| SOT + xG conceded (w10) | 241 | -0.83% | +0.55% | **-1.37%** | -0.74% | 98/241 (41%) | -4.92% [-16%, +6%] |
| SOT + goal count (w10+w5) | 241 | -1.07% | +0.55% | **-1.62%** | -0.66% | 112/241 (46%) | -1.06% [-11%, +8%] |
| Goals + xG (w5) | 281 | +0.80% | +1.18% | **-0.39%** | +1.30% | 174/281 (62%) | -2.86% [-11%, +5%] |

### Goals Over 2.5 (n=241–281)

| Metric | n | Model BSS | Market BSS | Δ (Model−Market) | Mean Edge | +EV Bets | Realized ROI |
|--------|---|-----------|------------|-------------------|-----------|----------|--------------|
| SOT + xG conceded (w10) | 241 | +0.20% | +2.15% | **-1.95%** | -2.79% | 77/241 (32%) | -12.17% [-33%, +9%] |
| SOT + goal count (w10+w5) | 241 | -0.72% | +2.15% | **-2.87%** | -2.56% | 89/241 (37%) | -6.48% [-25%, +13%] |
| Goals + xG (w5) | 281 | -0.29% | +2.70% | **-2.99%** | +0.43% | 150/281 (53%) | -3.01% [-17%, +11%] |

### Goals Over 3.5 (n=241–281)

| Metric | n | Model BSS | Market BSS | Δ (Model−Market) | Mean Edge | +EV Bets | Realized ROI |
|--------|---|-----------|------------|-------------------|-----------|----------|--------------|
| SOT + xG conceded (w10) | 241 | -0.93% | +4.31% | **-5.23%** | -4.32% | 64/241 (27%) | -43.06% [-70%, -13%] |
| SOT + goal count (w10+w5) | 241 | -1.51% | +4.31% | **-5.82%** | -3.98% | 64/241 (27%) | -34.78% [-62%, -4%] |
| Goals + xG (w5) | 281 | -2.98% | +3.05% | **-6.02%** | -0.93% | 132/281 (47%) | -18.04% [-39%, +4%] |

**Mean overround (goals):** 5.2%

### Goals Summary

The market dominates conclusively on goals. At every line and for every metric:
- Market BSS is positive (better than naive)
- Model BSS is mostly negative (worse than naive)
- The gap widens at higher lines (3.5) where the market's advantage grows to +4–6% BSS

The goals market is the most liquid and most modeled in sports betting. Bet365 has decades of data, proprietary models with far more features (team news, formations, motivation, weather), and prices adjusted by sharp money. Our 2-feature Poisson GLM cannot compete.

---

## Aggregate Statistics

| Measure | Value |
|---------|-------|
| Total comparisons (metric × line) | 17 |
| Model beats market (BSS) | 4 / 17 (24%) |
| Market beats model (BSS) | 13 / 17 (76%) |
| Mean Δ(BSS) model vs market | **-2.20%** |
| Best model performance | Cards 4.5, best_pair: +2.07% BSS above market |
| Worst model performance | Goals 3.5, goals_count_xg: -6.02% BSS below market |
| Realized ROI (any metric, any line) | ALL NEGATIVE |
| Any CI excluding zero on the positive side? | No |

---

## Coverage Gaps (What Could Not Be Tested)

| Market/Target | Reason Not Tested |
|---------------|-------------------|
| BTTS (Both Teams to Score) | Requires logistic regression (binary target), not Poisson GLM. The metric library specifies `poisson_glm_l2` for all 7 metrics; BTTS would need a different model type. |
| Clean Sheet | Same as BTTS — binary outcome, requires logistic model |
| Cards 2.5 line | Only 15 matches have Bet365 odds for this line — insufficient sample |
| Cards 5.5 line | 51 matches available but not specified in the prompt; metrics were validated on 3.5/4.5 |
| Goals with BTTS/CS framing | The goals metrics predict total count, not whether both teams score |

**Note:** The prompt specified testing against "goals O/U lines, BTTS, clean sheet where cached." The goals O/U lines were tested. BTTS and clean sheet were NOT tested because the 7 metrics all use Poisson count regression (predicting total goals/cards count), which produces P(count > line) naturally but cannot produce P(both teams score > 0) without architectural modification. Testing BTTS would require substituting a logistic model, which the prompt explicitly forbids ("no model substitutions").

---

## Honest Interpretation

### What This Means

1. **The signals are real.** The 7 metrics genuinely predict outcomes better than a naive baseline. This was validated via cumulative FDR and held-out temporal splits. That result stands.

2. **The signals are already priced in.** Bet365 incorporates these factors (and many more) into their odds. A team's recent card rate is not proprietary information — it is elementary match data available to every modeler.

3. **The bar for exploitable edge is much higher than "better than naive."** Our metrics clear the naive bar by +0.5–2.3% BSS. The market clears naive by +0.5–4.3% BSS. To generate edge, we would need to clear the MARKET bar, which is a much harder test.

4. **Sample sizes produce wide confidence intervals.** Cards at 3.5 (n=70–73) is particularly thin. Even if the true model were slightly better than the market, we could not detect it in this sample. However, the consistent direction of the result across all goals comparisons (n=241–281) gives confidence that the goals conclusion is not a sample-size artifact.

5. **Cards at 4.5 is the only glimmer** — our model has +1–2% BSS advantage over the market there. But: (a) confidence intervals are wide, (b) the market itself has negative BSS at that line suggesting it's a difficult line to price, and (c) realized returns are deeply negative despite the BSS edge, meaning the edge is not large enough to overcome the vig.

### What This Does NOT Mean

- This does NOT invalidate the discovery framework. The metrics were designed to beat naive baselines, and they do.
- This does NOT mean all features are useless for betting. It means that 2-feature Poisson GLMs using publicly available rolling averages cannot beat a professional bookmaker.
- This does NOT mean edge is impossible in cards markets. It means the features tested here, in this architecture, are insufficient.

### What Would Be Needed for Exploitable Edge

Based on these results, to beat the market would require:
- Features the market does NOT have (referee assignments, in-play context, private data)
- Better model architecture (not just feature selection within the same Poisson GLM)
- Targeting market inefficiencies (new markets, thin-liquidity leagues, live/in-play)
- The current approach of "find rolling stats that beat naive, hope they also beat the market" is structurally insufficient

---

## Technical Notes

- **Walk-forward discipline maintained:** Model was fit on corpus data strictly BEFORE the odds-sample period. No look-ahead bias.
- **Point-in-time features:** All rolling averages use only matches before the target match's kickoff time.
- **Vig removal method:** Multiplicative (proportional). This is the standard approach and introduces minimal bias for markets with symmetric-ish overround.
- **Triple half-split note:** Results are identical to best_pair because the third feature (2h_cards) receives near-zero weight under L2 regularization — it is collinear with total cards and adds no independent information.
- **No threshold loosening:** All 7 metrics tested. All lines reported. No cherry-picking of favorable results.

---

## Script Location

Analysis script: `scripts/ev_test_metrics_vs_bet365.py`
Raw results: `data/results/ev_test_metrics_vs_bet365.json`
