# Regularized Multi-Feature Models Per Market — Run Report

**Date:** 2026-08-30 · **Zero API requests** (all data cached; no heatmap/spatial attempts) ·
**Held-out access count:** 1 (see `clean_heldout_confirm.json`)

## Design (what changed from the prior run)

The prior run hand-enumerated mechanism-matched stat pairs — a human chose the combinations.
This run replaces the search unit with **one regularized multi-feature model per (market, line,
league)**. All available raw stats go into a single L1-regularized logistic model per market;
**regularization does the feature selection** and the surviving non-zero coefficients are the
discovery output. No hand-picked pairs, no pre-selected mechanisms.

This also fixes the FDR explosion. The multiple-testing family is now **the number of
market/line/league models tested — 48 (primary) + 256 (secondary) = 304**, not ~159,000.

- **Model:** L1 logistic, standardized features, `C ∈ {0.01, 0.03, 0.1, 0.3, 1.0}` chosen by
  4-fold time-ordered CV (neg-log-loss). L1 sparsity performs the selection. Median-imputed
  (train medians) so rows aren't dropped; features kept only at ≥50% train coverage.
- **Evaluation:** walk-forward 60/40, point-in-time features. BSS vs naive base-rate, Brier, ECE.
  Significance via LR chi-square with df = number of selected features.
- **Within-league significance required.** Fresh FDR (Benjamini-Hochberg, α=0.05) over the family.

Binary outcomes throughout, so logistic is appropriate; dispersion of the underlying counts is
not used because every target is a thresholded over/under, not a raw count regression.

## Feature verification on the mixed pool (all 5 pass)

Re-run on the **mixed core+rich pool** (`mm_mixed_verification.json`) because the pool now
includes rich fields that were searched separately last time:

| Check | Result |
|---|---|
| 1. Team-identity trace (rich field: tackles) | PASS — 4/4 traces reconstruct exactly |
| 2. Known signal | goals 0.099, cards 0.110, xG→goals **0.140**, SOT-persist 0.161 — PASS |
| 3. Orientation | corr(h_xg, home)=+0.141 > corr(h_xg, away)=−0.081 — PASS |
| 4. Look-ahead (tackles) | 0/20 mismatches — PASS |
| 5. Shuffle null | true \|r\|=0.141, shuffled max=0.069, z=8.9, empirical p=0.000 — PASS |

## Data

- **Primary — rich corpus, MIXED feature pool:** 3,189 matches with both FootyStats and
  TheStatsAPI data (England Championship 2nd tier 1,656; La Liga 2 924; Ligue 2 609). Core +
  rich TheStatsAPI fields mixed into **one 866-feature pool** (both teams × stat × {for, against}
  × {w3,w5,w10,std} + venue splits + referee rates). FootyStats-exclusive fields (xG-prematch,
  penalties, half-split set-pieces) are not uniformly present across all three rich leagues and
  are noted out of scope for the mixed pool.
- **Secondary — broad corpus, core-only pool:** full FootyStats set, 25 leagues, 15 with ≥260
  matches searched. 290-feature pool. Rich fields do not exist here.

## Headline result

**No model — in either configuration — passes within-league significance or fresh FDR.**

| Config | Feature pool | FDR family | Best OOS BSS | Min p (within-league) | Survivors |
|---|---|---|---|---|---|
| Primary (rich, mixed) | 866 | 48 | +3.35% | 0.49 | **0** |
| Secondary (broad, core) | 290 | 256 | +14.15% | 0.23 | **0** |

The secondary config's higher raw BSS peaks (e.g. Portugal corners_a_4.5 +14.15%) come from
thin per-league test folds (n≈123) and are statistically insignificant (p=0.49) — exactly the
kind of noise the within-league + FDR discipline is designed to reject. Nothing survives.

### Per market/line/league — primary (rich, mixed), all 48 models

`BSS` = Brier skill vs naive base rate (OOS). `sel` = non-zero features / pool. `leans` = top
selected standardized coefficients (the discovery output). None reach significance (all p shown).

| League | Market/line | BSS % | Brier | ECE | sel | p | Leans on (top selected) |
|---|---|---|---|---|---|---|---|
| Championship | btts | -1.37 | 0.250 | 0.076 | 22/738 | 1.00 | h_goals_home_w5(+0.11), a_goals_prevented_against_std(+0.07), h_touches_in_box_against_std(+0.06) |
| Championship | cards_3.5 | +0.84 | 0.245 | 0.016 | 12/738 | 0.95 | h_shots_outside_box_for_w3(+0.08), a_saves_against_std(+0.06), h_saves_against_w5(+0.04) |
| Championship | cards_4.5 | -1.56 | 0.233 | 0.070 | 19/738 | 1.00 | a_shots_outside_box_home_std(+0.06), h_possession_for_w3(+0.05), h_aerial_duels_won_against_w3(-0.04) |
| Championship | corners_10.5 | -2.41 | 0.250 | 0.077 | 0/738 | 1.00 | (all coef ~0) |
| Championship | corners_8.5 | -0.24 | 0.222 | 0.026 | 8/738 | 1.00 | a_tackles_won_pct_away_w5(-0.07), h_tackles_won_pct_away_w5(-0.04), a_xg_for_w3(+0.04) |
| Championship | corners_9.5 | -1.29 | 0.252 | 0.040 | 12/738 | 1.00 | h_tackles_won_pct_away_w5(-0.05), h_fouled_in_final_third_against_w3(-0.05), a_tackles_won_pct_away_w5(-0.04) |
| Championship | corners_a_4.5 | +1.98 | 0.232 | 0.057 | 18/738 | 0.79 | h_shots_for_w5(+0.08), h_npxg_against_std(-0.07), h_corners_for_std(+0.06) |
| Championship | corners_b_4.5 | +3.35 | 0.238 | 0.019 | 23/738 | 0.54 | h_accurate_crosses_against_std(+0.21), a_goals_for_w10(+0.13), a_clearances_for_w5(-0.11) |
| Championship | cs_away | -1.27 | 0.175 | 0.051 | 15/738 | 1.00 | a_saves_for_std(-0.15), h_hit_woodwork_home_std(-0.09), a_shots_outside_box_against_std(-0.06) |
| Championship | cs_home | -2.21 | 0.207 | 0.086 | 22/738 | 1.00 | a_npxg_home_std(-0.08), a_accurate_crosses_against_w3(+0.08), h_saves_home_std(-0.08) |
| Championship | goals_1.5 | +0.11 | 0.190 | 0.041 | 10/738 | 1.00 | h_goals_home_w5(+0.09), h_shotsOnTarget_home_w5(+0.08), a_shots_outside_box_against_w10(+0.04) |
| Championship | goals_2.5 | -0.26 | 0.251 | 0.033 | 14/738 | 1.00 | h_shotsOnTarget_home_w5(+0.12), a_shots_outside_box_against_std(+0.10), a_goals_prevented_against_w3(+0.05) |
| Championship | goals_3.5 | +0.04 | 0.184 | 0.037 | 11/738 | 1.00 | h_ball_recoveries_against_std(+0.06), h_blocked_shots_for_std(+0.04), a_shots_for_std(+0.04) |
| Championship | goals_4.5 | -3.07 | 0.086 | 0.052 | 2/738 | 1.00 | h_goals_home_std(+0.10), a_goals_prevented_against_w3(+0.04) |
| Championship | goals_a_1.5 | +0.74 | 0.238 | 0.059 | 19/738 | 1.00 | h_shots_inside_box_home_std(+0.11), a_shotsOnTarget_against_std(+0.09), h_blocked_shots_home_std(+0.08) |
| Championship | goals_b_1.5 | +1.73 | 0.210 | 0.019 | 23/738 | 0.99 | a_corners_home_std(+0.09), a_xg_away_w5(+0.08), h_ball_recoveries_against_std(+0.08) |
| La Liga 2 | btts | -0.26 | 0.247 | 0.053 | 5/690 | 1.00 | h_shots_inside_box_for_w3(+0.11), a_touches_in_box_away_std(+0.06), h_goals_home_std(+0.01) |
| La Liga 2 | cards_3.5 | -11.05 | 0.176 | 0.133 | 1/690 | 1.00 | a_tackles_won_pct_away_std(+0.06) |
| La Liga 2 | cards_4.5 | -9.99 | 0.248 | 0.154 | 4/690 | 1.00 | h_fouled_in_final_third_for_w10(+0.05), h_ground_duels_won_against_std(+0.02), a_possession_against_w10(-0.02) |
| La Liga 2 | corners_10.5 | -0.04 | 0.232 | 0.009 | 0/690 | 1.00 | (all coef ~0) |
| La Liga 2 | corners_8.5 | -2.86 | 0.246 | 0.082 | 1/690 | 1.00 | a_accurate_crosses_away_w5(-0.02) |
| La Liga 2 | corners_9.5 | +0.14 | 0.250 | 0.029 | 2/690 | 0.78 | h_tackles_away_std(-0.03), a_accurate_crosses_away_w5(-0.01) |
| La Liga 2 | corners_a_4.5 | -3.71 | 0.250 | 0.095 | 0/690 | 1.00 | (all coef ~0) |
| La Liga 2 | corners_b_4.5 | +0.37 | 0.244 | 0.015 | 4/690 | 0.85 | h_touches_in_box_against_w5(+0.07), a_big_chances_home_std(+0.05), h_touches_in_box_against_std(+0.01) |
| La Liga 2 | cs_away | -1.67 | 0.175 | 0.070 | 63/690 | 1.00 | h_dispossessed_away_w5(-0.21), h_shots_inside_box_for_w5(-0.16), a_aerial_duels_won_home_w5(-0.15) |
| La Liga 2 | cs_home | -4.37 | 0.219 | 0.099 | 4/690 | 1.00 | a_touches_in_box_for_std(-0.03), a_goals_for_w10(-0.03), a_shotsOnTarget_for_std(-0.02) |
| La Liga 2 | goals_1.5 | -3.08 | 0.203 | 0.065 | 76/690 | 1.00 | a_interceptions_home_std(-0.23), a_shotsOnTarget_home_std(+0.20), h_big_chances_for_w5(+0.18) |
| La Liga 2 | goals_2.5 | +1.20 | 0.247 | 0.030 | 5/690 | 0.49 | a_high_claims_home_std(-0.07), h_shots_for_w5(+0.04), h_goals_home_std(+0.04) |
| La Liga 2 | goals_3.5 | -3.99 | 0.202 | 0.088 | 1/690 | 1.00 | h_touches_in_box_for_w3(+0.02) |
| La Liga 2 | goals_4.5 | -6.97 | 0.123 | 0.058 | 51/690 | 1.00 | h_hit_woodwork_against_w5(+0.19), h_high_claims_against_std(+0.15), h_touches_in_box_against_w3(+0.14) |
| La Liga 2 | goals_a_1.5 | -1.76 | 0.245 | 0.093 | 9/690 | 1.00 | h_shots_inside_box_for_w5(+0.15), h_big_chances_home_std(+0.07), h_duels_won_pct_home_w5(+0.03) |
| La Liga 2 | goals_b_1.5 | -0.14 | 0.219 | 0.028 | 1/690 | 1.00 | a_touches_in_box_home_std(+0.04) |
| Ligue 2 | btts | -0.17 | 0.250 | 0.021 | 0/698 | 1.00 | (all coef ~0) |
| Ligue 2 | cards_3.5 | -7.47 | 0.250 | 0.132 | 0/698 | 1.00 | (all coef ~0) |
| Ligue 2 | cards_4.5 | -4.15 | 0.257 | 0.123 | 45/698 | 1.00 | a_aerial_duels_won_home_w5(+0.21), a_ground_duels_won_away_std(+0.21), h_ground_duels_won_against_std(+0.21) |
| Ligue 2 | corners_10.5 | -6.67 | 0.231 | 0.113 | 40/698 | 1.00 | h_goals_against_w10(+0.21), a_aerial_duels_won_against_w3(-0.19), a_touches_in_box_against_w10(+0.19) |
| Ligue 2 | corners_8.5 | -1.36 | 0.250 | 0.058 | 0/698 | 1.00 | (all coef ~0) |
| Ligue 2 | corners_9.5 | -2.81 | 0.250 | 0.083 | 0/698 | 1.00 | (all coef ~0) |
| Ligue 2 | corners_a_4.5 | -3.11 | 0.250 | 0.087 | 0/698 | 1.00 | (all coef ~0) |
| Ligue 2 | corners_b_4.5 | -10.31 | 0.250 | 0.153 | 0/698 | 1.00 | (all coef ~0) |
| Ligue 2 | cs_away | -0.88 | 0.206 | 0.061 | 36/698 | 1.00 | h_fouls_home_w5(-0.24), h_shots_outside_box_against_w3(+0.11), a_ball_recoveries_against_w3(+0.10) |
| Ligue 2 | cs_home | -0.24 | 0.215 | 0.052 | 40/698 | 1.00 | a_dribbles_for_w3(+0.23), a_shots_inside_box_for_std(-0.18), a_aerial_duels_won_against_w5(+0.15) |
| Ligue 2 | goals_1.5 | -4.10 | 0.226 | 0.106 | 37/698 | 1.00 | a_aerial_duels_won_against_w5(-0.23), a_accurate_crosses_for_w3(+0.20), a_goals_against_w5(-0.10) |
| Ligue 2 | goals_2.5 | -11.55 | 0.278 | 0.122 | 53/698 | 1.00 | h_yellow_cards_away_std(-0.25), h_goals_home_w5(-0.20), a_accurate_crosses_for_std(+0.20) |
| Ligue 2 | goals_3.5 | -8.54 | 0.206 | 0.114 | 38/698 | 1.00 | h_yellow_cards_away_std(-0.22), a_accurate_crosses_for_w10(+0.15), h_high_claims_for_std(-0.15) |
| Ligue 2 | goals_4.5 | -0.37 | 0.108 | 0.034 | 25/698 | 1.00 | a_dribbles_for_w10(-0.11), h_ground_duels_won_against_w10(+0.10), a_dispossessed_away_std(+0.10) |
| Ligue 2 | goals_a_1.5 | -8.69 | 0.252 | 0.142 | 2/698 | 1.00 | h_touches_in_box_against_w5(-0.06), h_touches_in_box_against_std(-0.06) |
| Ligue 2 | goals_b_1.5 | -0.98 | 0.229 | 0.047 | 0/698 | 1.00 | (all coef ~0) |

Reading the discovery output: where L1 keeps features, the model does lean on plausible
mechanisms (goals models lean on shots-on-target and shots-inside-box; corners lean on crosses
and tackles-won%; clean-sheet leans on saves and npxG-against). But the OOS BSS is at or below
zero for the large majority, and no lean reaches significance. The engine finds the right
*shapes* and no *edge*.

## Rich (mixed) vs broad (core) — the key comparison

Comparable leagues appear in both corpora (Championship, Ligue 2). Δ = rich BSS − broad BSS:

- **Championship (n=1,656 rich):** mixed features improve OOS BSS on 13/16 targets (e.g.
  goals_b_1.5 +17.7pp, cards_4.5 +16.4pp, cs_home +8.6pp). Direction favors rich here.
- **Ligue 2 (n=609 rich):** direction is mixed and often *worse* with rich features (goals_a_1.5
  −11.2pp, goals_2.5/3.5 −8.5pp), consistent with the larger 866-feature pool overfitting a
  smaller corpus even under L1.

**Verdict, stated plainly: the rich (mixed) model does NOT materially outperform the core-only
model in a way that generalizes.** On the largest rich league it looks better; on the smallest it
looks worse; and in *neither* corpus does any model clear within-league significance or FDR.
Both configs' best models sit at BSS ≈ 0 after honest regularization. **This does not justify
acquiring the rich data at scale** — the apparent Championship gains are within noise (all p ≈ 1
or ≥0.5) and do not survive multiple-testing correction.

## Stage 2 — EV vs cached Bet365 odds (`mm_stage2_ev.json`)

**No model passed Stage 1, so strictly there is nothing to bet.** EV rows are ILLUSTRATIVE on the
best-BSS non-survivor models where cached odds exist; positive edge here is *not* a finding.
Edges are net of multiplicative overround and compared against measured thresholds, not zero.

| Market | League | n | edge median (pp) | threshold (pp) | overround | flags | ROI (backtest) | 95% CI |
|---|---|---|---|---|---|---|---|---|
| goals 2.5 | La Liga 2 | 18 | +3.75 | 3.04 | 6.06% | 15 | -6.6% | [-66.1, +52.9] |
| cards 3.5 | Championship | 125 | +4.13 | 4.05 | 8.11% | 84 | -3.8% | [-24.0, +16.4] |
| corners 9.5 | La Liga 2 | 12 | +1.00 | 4.00 | 8.08% | 8 | -22.5% | [-100, +55] |
| goals 1.5 | Championship | 206 | -2.19 | 4.15 | 4.90% | 111 | +17.4% | [-14.3, +50.6] |
| goals 3.5 | Championship | 206 | +0.07 | 1.96 | 4.96% | 99 | +13.1% | [-14.1, +42.3] |

Every ROI CI spans zero — no bettable edge. **Reliability filter** (both teams' rolling history
present via ≥50% coverage; non-extreme model prob; flag |edge|≥3pp net of overround) removed 0
flags here because imputation already guaranteed history presence and no probability hit the
0.02/0.98 extreme; the prior degradation-at-large-divergence pattern therefore has no thin-history
tail to bite on in these folds.

## Naive vs market — two distinct findings

- **Beating naive:** a handful of primary models edge slightly above the base-rate naive (max
  +3.35% BSS), but none significantly. Effectively no model reliably beats naive.
- **Beating the market:** no model produces a positive-EV flag whose ROI CI excludes zero against
  the measured thresholds. The market is not beaten.

These are different bars and both are reported: marginally-better-than-naive-but-insignificant is
not the same as market-beating, and neither is achieved.

## Ground rules — compliance checklist

- Regularization (L1, CV-selected C) selects features; no hand-restricted combinations ✓
- Broad + rich fields mixed freely on the 3,189 corpus (866-feature pool) ✓
- Fresh FDR family over market/line/league models: 48 + 256 = 304 (prior families not inherited) ✓
- Five feature checks re-run on the mixed pool before searching — all pass ✓
- Within-league significance required; pooled-only results not reported as findings ✓
- Point-in-time throughout (emit-before-update; look-ahead check 0 mismatches) ✓
- Zero API calls; no heatmap attempts ✓
- Held-out reserved for confirming survivors; access count = 1 (no Stage-1 survivor, so used only
  for the prior run's SOT-persistence prediction confirmation) ✓
- New code committed (`601ee09`); no shared/global config changed beyond adding sklearn to the venv ✓

## Bottom line

Letting regularization pick features from the full mixed pool, with honest within-league
significance and a small fresh FDR family, reproduces the prior run's conclusion by a cleaner
route: **the models recover sensible mechanism shapes but no exploitable edge.** Rich data does
not reliably beat core data, no market is beaten, and there is no survivor to bet.

## Artifacts

- `scripts/mm_verify_mixed.py` → `data/discovery/mm_mixed_verification.json`
- `scripts/mm_models.py` → `data/discovery/mm_models.json`
- `scripts/mm_stage2_ev.py` → `data/discovery/mm_stage2_ev.json`
- `data/discovery/clean_heldout_confirm.json` (held-out access log)
