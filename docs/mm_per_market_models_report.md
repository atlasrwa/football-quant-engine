# Regularized Multi-Feature Models Per Market

**Date:** 2026-08-30
**Design:** One regularized (L1, CV-selected C) multi-feature logistic model per (market, line, league). The full raw-stat pool is fed in; **L1 regularization selects the features** — no hand-picked combinations. This is the corrected search unit (the prior run hand-enumerated pairs).
**Data:** Primary = 3,189-match rich corpus (Championship / La Liga 2 / Ligue 2 / 99 EPL) with **broad + rich fields mixed into one pool**. Secondary = 15,362-match FootyStats corpus, core fields only.
**Fresh FDR family (this run only):** 48 models (primary) + 256 (secondary) = **304**. The inherited 23,869 is not used.
**API cost:** 0 (all cached; no spatial/heatmap attempts). **Held-out access count:** 0 (no model survived FDR, so there was nothing to confirm).
**Artifacts:** `scripts/clean_features.py`, `clean_rich_loader.py`, `mm_verify_mixed.py`, `mm_models.py`, `mm_stage2_ev.py`; results in `data/discovery/mm_*.json`.

---

## Headline

- **Prediction:** With the full mixed pool and L1 selecting features, **no per-market model achieves within-league significance** — 0 of 304 survive fresh FDR (primary min p=0.49, secondary min p=0.23). The best out-of-sample BSS in the rich mixed run is +3.35% (Championship corners per-side, p=0.54); the mean per-league model is slightly *worse* than naive out-of-sample. Regularized multi-feature models over raw stats do not reliably beat naive at per-league sample sizes.
- **Rich vs core (key deliverable):** The rich mixed pool does **not** materially outperform core-only. Its best model (+3.35%, non-significant) is no better than the broad tier's noise, and rich-only fields never dominate the selected-feature lists in a stable way. **This does not justify acquiring the rich data at scale for prediction.**
- **Per-side vs totals:** Per-side targets predict *less badly* than match totals (mean BSS −1.71% vs −2.89% rich; −1.22% vs −4.39% broad) — the asymmetry hypothesis is directionally supported, but both remain negative-mean and non-significant.
- **EV:** No model passed validity+FDR, so **there is no survivor to bet**. Illustrative EV on the best bettable-market non-survivors shows **no market beaten** — every realized-ROI CI spans zero.

---

## Method notes

**Features** are the verified team-consistent, point-in-time engine from the prior run (team-identity keyed, for/against, explicit home/away splits, windows w3/w5/w10/season-to-date, referee expanding rates). All **five verification checks were re-run on the mixed pool** (`mm_mixed_verification.json`) and passed: rich-field trace (tackles) correctly team-keyed; known-signal (goals 0.099, cards 0.110, xG→goals 0.140, SOT 0.161); orientation +0.14 home vs −0.08 away; look-ahead clean; shuffle-null z=8.9, empirical p=0 (the shuffle check was upgraded from an arbitrary "5×max" rule to a principled permutation test — stricter, not looser).

**Model:** L1-regularized logistic (sklearn `LogisticRegressionCV`, C∈{0.01,…,1.0} chosen by 4-fold CV), median-imputed, standardized, walk-forward 60/40. L1 gives genuine sparsity — median **9 (rich) / 11 (broad)** features selected from pools of **866 / 290**. An initial L2 attempt overfit catastrophically (BSS −25% to −45%) because 290–866 features on ~180–300 training rows is hopelessly over-parameterized under L2; L1 sparsity is the correct tool and fixed it.

**Dispersion (empirical):** goals var/mean 0.99, corners 1.15, cards 1.01 — near-Poisson, so the logistic-on-binarized-over/under formulation is appropriate (no NB needed).

**Scope note on "mix both sources":** the mixed pool is the full TheStatsAPI field set (core observables + rich-only fields) on the 3,189 corpus — this is exactly the two prior tiers merged into one pool. Truly FootyStats-exclusive fields (xG-prematch, penalties, half-split set-pieces) were not added: the FootyStats corpus does not contain La Liga 2 at all and the team crosswalk covers only Championship (not Ligue 2 / La Liga 2), so an asymmetric join across the three rich leagues was judged not worth the noise. Stated as a limitation.

## Stage 1 — per market/line/league (what the models lean on)

**Primary (rich, mixed pool), family = 48, survivors = 0.** Top out-of-sample models (all non-significant; features = what L1 selected):

| League | Market | OOS BSS | p | n | Leans on (top |coef|) |
|---|---|---|---|---|---|
| Championship | away corners o4.5 | +3.35% | 0.54 | 652 | crosses-conceded, opp goals(w10), clearances |
| Championship | home corners o4.5 | +1.98% | 0.79 | 652 | shots(w5), npxG-conceded, corners(std) |
| Championship | away goals o1.5 | +1.74% | 0.99 | 663 | opp corners(home), opp xG(away), ball-recoveries |
| La Liga 2 | goals o2.5 | +1.20% | 0.49 | 370 | high-claims, shots(w5), goals(home) |
| Championship | cards o3.5 | +0.84% | 0.92 | 625 | shots-outside-box, opp saves, saves |

The selected-feature lists are scattered and unstable across markets — no coherent, repeatable mechanism emerges, which is itself evidence the models are fitting noise.

**Secondary (broad, core), family = 256, survivors = 0.** Highest point BSS is +14.2% (Portugal corners per-side) — but at **n=123, p=0.49**: small-sample noise with enormous CIs. Nothing significant.

**BH rejects 0 in both.** Because the families here are honest and small (48, 256) rather than artificially shrunk, this is a genuine null, not a family-size artifact.

## Stage 1 — the two comparisons the prompt asked for

**Rich vs core:** best rich mixed model +3.35% (p=0.54) vs best comparable core model at similar n around +2–3% (also non-significant); the eye-catching +14% core number is n=123 noise. There is **no evidence the rich fields buy predictive accuracy** over core stats. Verdict: acquiring rich data at scale is **not justified** on these results.

**Per-side vs totals:** per-side mean OOS BSS is consistently *less negative* than totals (−1.71% vs −2.89% rich; −1.22% vs −4.39% broad), consistent with the idea that match totals average away matchup asymmetry. But both are negative-mean and none is significant — a directional hint, not a result.

## Stage 2 — EV vs market

**Primary result: no survivor to bet.** No model passed per-league validity + FDR, so there is no model to take to market. Reported as-is, not substituted.

Illustrative EV on the best-BSS bettable-market non-survivors (rich slice; edges net of multiplicative overround; reliability filter = both-teams history present + non-extreme prob; flag |edge|≥3pp; vs measured thresholds):

| League | Market | Overround | Median edge | Threshold | Flags | Flat ROI | 95% CI |
|---|---|---|---|---|---|---|---|
| La Liga 2 | goals 2.5 | 6.06% | +3.75pp | 3.04pp | 15 | −6.6% | [−66, +53] |
| Championship | cards 3.5 | 8.11% | +4.13pp | 4.05pp | 84 | −3.8% | [−24, +16] |
| Championship | goals 1.5 | 4.90% | −2.19pp | 4.15pp | 111 | +17.4% | [−14, +51] |
| Championship | goals 3.5 | 4.96% | +0.07pp | 1.96pp | 99 | +13.1% | [−14, +42] |
| La Liga 2 | corners 9.5 | 8.08% | +1.00pp | 4.00pp | 8 | −22.5% | [−100, +55] |

**Every ROI CI spans zero.** Where the median edge clears its threshold (goals 2.5, cards 3.5) the realized ROI is negative — the "edge" is model over-estimation, not real. Where realized ROI is positive (goals 1.5/3.5) the model's own median edge is below threshold and the CI is enormous. **No market beaten.** The reliability filter removed few flags (history is almost always present in these leagues); the prior −0.56 divergence-degradation pattern is not separately re-established on this small non-significant set.

**Beating naive vs beating the market:** neither happens here. Some models beat naive by a point or two out-of-sample in point terms, but none significantly, and none converts to a market edge.

## Honest summary

Letting a regularized model choose from the full raw-stat pool (the corrected design you asked for) does not change the conclusion: **at per-league sample sizes, raw observable stats do not yield a model that reliably beats naive, let alone the market.** L1 genuinely sparsified (9–11 features), the mixed rich+core pool was fed in whole, and the search unit was models-not-pairs — and still nothing survives fresh FDR (0/304), rich data shows no advantage over core, and no market is beaten in backtest. Per-side targets are directionally less bad than totals, worth remembering, but not a result on this sample.

## Ground-rules compliance

Regularization selects features (L1, CV-C), no hand-restriction ✓ · broad+rich mixed on the 3,189 corpus ✓ · fresh FDR family = 304 models (not 23,869) ✓ · 5 verification checks re-run on the mixed pool before searching ✓ · point-in-time absolute ✓ · within-league significance required, none pooled-only claimed ✓ · zero API, no heatmap ✓ · held-out reserved for survivors, access count **0** (none to confirm) ✓ · code committed ✓.

**Shared/global config flag:** I installed **scikit-learn** into the project venv (`pip install scikit-learn`) — it was absent and is required for L1/elastic-net with CV. This is an environment/dependency addition (medium-risk); it changed no project config files, no shared code, and the metric library / corpus / `src/` were read-only. Flagging per the standing rule.
