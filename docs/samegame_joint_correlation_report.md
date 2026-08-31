# Same-Game Joint Distribution — Is There a Correlation Gap?

**Date:** 2026-08-30
**Scope:** Same-game only (cross-game combinations explicitly out of scope).
**Data:** 100% cached. Zero API calls.
**Verdict:** Hypothesis **FAILS at Step 1**. The market-gap question is **untestable**
with cached data (hard limitation). The naive-vs-joint divergence (Step 5) is reported
regardless and is **small and of the wrong sign** for the hypothesis.

---

## The claim under test

Bookmakers price same-game combinations with a blanket correlation adjustment plus an
inflated margin (~15-25% vs 5-8% on singles). The hypothesis: in identifiable match
profiles the *true* joint probability is materially higher than a blanket adjustment
assumes, by enough to clear the same-game margin. The premise is that a high-tempo,
physical match produces **both** cards and corners — i.e. a **positive** outcome
correlation that is stronger in some profiles.

---

## Step 1 — Model-free correlation structure (the gate)

Realized outcomes only, no model. Corpus: **15,359** complete matches (**15,335** with
valid corners), **50** league-seasons.

Definitions (consistent with the validated marginals):
`total_cards = team_a_yellow + team_b_yellow + reds`; `total_corners = totalCornerCount`
(requires `corner_timings_recorded`); `total_goals = overallGoalCount`.

### Overall correlation (Spearman)

| Pair | Pooled | Within-league-season | n |
|---|---|---|---|
| cards × corners | **−0.047** | **−0.033** | 15,335 |
| cards × goals | **−0.043** | **−0.030** | 15,359 |
| corners × goals | **−0.019** | **−0.028** | 15,335 |

Pearson is essentially identical (−0.048 / −0.041 / −0.019 pooled). Every correlation is
**near zero and negative** — the opposite sign to the hypothesis's premise. The
"high-tempo match → both cards and corners" intuition does **not** hold at the
match-total level; mechanical negative couplings dominate (a dominant side wins more
corners while committing fewer fouls/cards; blowouts can lower late-match intensity).

The within-league-season column z-scores each outcome inside its own league-season
before pooling, to rule out a Simpson-type artifact from mixing leagues with different
mean levels. It does not change the picture.

### By match profile

Splits: **referee card tendency** (look-ahead-free expanding-window referee mean cards,
terciles), **tempo** (total dangerous attacks, terciles), **competitive balance**
(|home_ppg − away_ppg|, median split), **league** (top 12 by n). Within-league-season
Spearman by bucket:

- **Referee tendency:** ranges 0.02–0.06 across strict/avg/lenient — all still ≈0 or negative.
- **Tempo:** ranges 0.01–0.02 — flat. Higher tempo does **not** raise the coupling.
- **Competitive balance:** largest single split is cards×goals (close +0.006 vs
  mismatched −0.059) — both still ≈0/negative.
- **League:** apparent spread up to 0.21, but across 12 buckets of n≈380–557 — the noise regime.

### Gate decision (pre-stated criteria)

- **Multiple-testing family = 60** profile-bucket × pair correlation tests (reported in
  full; no best-slice selection).
- **Criterion A** (overall positive and |ρ| ≥ 0.05): **FALSE** — all overall correlations negative.
- **Criterion B** (any bucket positive, ≥ +0.10, and BH-significant across the family of 60): **FALSE**.
  - Positive **and** BH-significant buckets: **0**.
  - Negative and BH-significant buckets: **6** (the couplings that are real are negative).
  - Largest positive point estimate is +0.117 (league 12325, cards×corners, n=380) — it
    does **not** survive BH correction. This is exactly the multiple-comparison false
    positive the brief warned about.

**Gate FAILS.** Per the brief: *"If correlation is uniform across all profiles, the
hypothesis is dead at this step … Report that plainly and stop."* The correlation is not
merely uniform — it is near-zero and slightly negative everywhere, and the small profile
variation is neither positive, material, nor multiple-testing-robust. **The market-edge
hypothesis is closed.**

---

## Step 2 — Joint distribution (built for Step 5, sanity-gated)

Although the edge hypothesis is closed, the joint model was built to serve the mandatory
Step-5 divergence measurement.

- **Marginals:** the **validated `CountRegressionModel`** (Poisson/NB + L2 + team
  shrinkage) reused verbatim — **no refit of the architecture, no substitution**. Fitted
  distributions: cards λ≈4.24, corners λ≈9.85, goals λ≈2.79 (all Poisson at the corpus level).
- **Joint construction:** a **Gaussian copula** couples the two marginal count PMFs, with
  latent correlation set from the measured Spearman via ρ_gauss = 2·sin(π·ρ_s/6).
  **Why a copula over bivariate-Poisson:** the measured correlation is near-zero and can
  be **negative**; the standard (Holgate shared-shock) bivariate-Poisson can only
  represent **positive** correlation, so it cannot reproduce this data. A Gaussian copula
  preserves the exact validated marginals for any correlation sign.
- **Sanity gate (marginal recovery):** summing the joint over each dimension recovers the
  marginal PMF to **1e-9** (threshold 1e-6). **PASSED.** The vectorized bivariate-normal
  CDF was independently validated against SciPy to ~1e-16.

---

## Step 3 — Comparison vs naive multiplication and vs the market

### Naive product vs joint model (both computable)

Event = leg A over AND leg B over, at standard lines (cards O3.5, corners O9.5, goals O2.5),
averaged across all matches:

| Pair | Naive P(A)×P(B) | Joint P(A∩B) | Signed gap | Relative | Max abs gap |
|---|---|---|---|---|---|
| cards O3.5 × corners O9.5 | 29.58% | 28.94% | **−0.64pp** | −2.5% | 0.78pp |
| cards O3.5 × goals O2.5 | 30.70% | 30.06% | **−0.63pp** | −2.3% | 0.72pp |
| corners O9.5 × goals O2.5 | 27.12% | 26.84% | **−0.29pp** | −1.2% | 0.31pp |

The joint is **below** the naive product everywhere (the negative correlation slightly
*reduces* the co-occurrence probability). Naive multiplication therefore **overstates**
these same-game Over∩Over probabilities by roughly 1–2.5% relative — the opposite
direction to the hypothesis, which needed the true joint to be *higher* than a blanket
assumption.

### Market-implied probability — **untestable (hard limitation)**

The cached odds contain **no same-game combination prices for any target cross-market
pair.** Across 420 odds files:

- cards × corners combo: **0 files**
- cards × goals combo: **0 files**
- corners × goals combo: **0 files**

The only combination markets cached are `total_goals_btts` (10 files) and `correct_score`
(10 files) — both **goals-internal** (functions of the scoreline), neither of which tests
the cross-market correlation hypothesis. **The market-gap comparison cannot be performed
with cached data.** This is reported as a hard limitation, not worked around.

### Overround context (single markets — the only margin evidence available)

Bet365 single-market overrounds (last_seen): goals@2.5 **5.3%** (n=420), cards **~7.9–8.0%**
(n=134/205), corners **~8.2%** (n=89/266/58). These match the brief's "5–8% on singles". A
same-game combination is priced *above* its legs (the brief cites 15–25%). Since all gaps
must be reported net of overround: the naive-vs-joint divergence (≤0.8pp, ~1–2.5% relative,
**wrong sign**) is far below even the single-leg margins, let alone a combination margin.
There is no scenario in which a ≤0.8pp same-direction-wrong gap clears a 15–25% overround.

---

## Step 4 — Honest interpretation

- **No profile shows a positive, material, multiple-testing-robust correlation.** The
  hypothesis fails at the correlation-structure step, before any market comparison is even
  needed. This is a clean, valuable negative: **same-game cross-market combinations
  (cards/corners/goals) are not a modelling-gap opportunity** at the match-total level.
- **Multiple-testing family = 60** profile-bucket × pair tests; reported in full. The one
  positive-looking slice (league 12325 cards×corners, +0.117, n=380) is not BH-robust and
  is presented as noise, not as a finding.
- **The market-gap question remains formally untested** because no same-game combination
  prices are cached for the target pairs. Even so, the direction and magnitude of the
  naive-vs-joint gap make an exploitable edge implausible: the true joint is *lower* than
  naive, and the deviation is ~1pp against margins of 8%+ per leg.
- **Confidence / caveats:** correlations are model-free on n≈15k, so the near-zero central
  estimates are tight (a Spearman of −0.03 at n=15,335 has a 95% CI of roughly ±0.016 —
  bounded well away from the positive, material values the hypothesis requires). The
  copula divergence inherits the validated marginals; it is a descriptive quantity, not an
  edge claim, so it was computed on the full corpus without a held-out split. **The
  held-out set was not touched.**

## Step 5 — Naive-vs-joint divergence (standalone deliverable)

Independent of any market edge, the practically useful number for anyone structuring
same-game combinations of these markets: **modelling the joint instead of multiplying
marginals changes the combined Over∩Over probability by under 1 percentage point
(~1–2.5% relative), and in the direction of a slightly *lower* joint.** This holds
uniformly across tempo, competitive-balance and referee-tendency profiles (bucket-to-bucket
movement < 0.05pp). In other words, for cards/corners/goals totals, **P(A)×P(B) is a good
approximation** — it is wrong by only ~1pp, and it errs on the high side. That is a
legitimate, honest thing to be able to tell a user: the common shortcut is close to
correct here, not badly broken.

---

## Ground-rules compliance

- Zero API calls — all cached. ✓
- Same-game only; cross-game out of scope. ✓
- Validated marginals reused verbatim; **no refit, no substitution** (the F009 lesson). ✓
- Step 1 gated Step 2; joint sanity gate passed before Step 3. ✓
- Multiple-testing family size reported (60); no post-hoc best-slice selection. ✓
- All gaps reported net of overround (overrounds stated explicitly). ✓
- Held-out set untouched. ✓

## Artifacts

| Item | Path |
|---|---|
| Step 1 correlations | `scripts/samegame_step1_correlation.py` → `data/results/samegame_step1_correlation.json` |
| Step 1 gate decision | `scripts/samegame_step1b_gate.py` → `data/results/samegame_step1b_gate.json` |
| Step 2/5 joint + divergence | `scripts/samegame_step2_joint.py` → `data/results/samegame_step2_joint.json` |
| Step 3 coverage + overround | `scripts/samegame_step3_coverage.py` → `data/results/samegame_step3_coverage.json` |
