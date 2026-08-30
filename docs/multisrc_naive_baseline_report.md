# Multi-Source Discovery — Naive-Baseline Addendum (24 new fields, 3 second-tier leagues)

**Date:** 2026-08-30
**Relationship to prior work:** The discovery run (Steps 1–4, failure-ledger **F018**,
2026-08-29) already searched the ~24 TheStatsAPI-unique fields across Championship / Ligue 2 /
La Liga 2 and found **0 FDR survivors**. That run's Step 5 was a *market* calibration (Bet365).
**This brief specifies a different Step 5: naive-baseline only, odds explicitly out of scope.**
That naive-baseline view was never produced, so it is computed here.
**Budget: ZERO API requests** — everything reuses cached stats and the same walk-forward models.
Monthly quota unchanged at **5,518** (this addendum spent nothing).

**Verdict:** unchanged and, if anything, **strengthened**. The ~24 new fields do **not** beat a
naive baseline in any material way, and do **not** beat the existing FootyStats-derived metrics
where both are testable. The single strongest screening candidate is actually **worse than
naive** on calibrated probability.

---

## Steps 1–4 — verified reproducible from cache (zero requests)

Re-ran the cached analysis (all confirmed cache-only, no API calls):

- **Step 1 merge gate — PASSED.** 552 TheStatsAPI Championship-overlap matches → **420 clean
  1:1 joins** (76.1%, limited by crosswalk coverage; 0 no-match, 0 multi-candidate). Shared-field
  agreement: yellow_cards **95.0%** exact, corners **97.6%**, SOT 82.1%, fouls 89.3%, possession
  85.0% (MAD 0.44pp). Falsification: correct join cards 95.0% vs **shuffled null 21.8%** — a
  73-point gap; the join is real. *(The script prints a conservative "MERGE SUSPECT" because its
  hard rule wants the worst count field ≥95% and SOT is 82.1%; the deeper analysis resolves this
  — objective outcomes agree strongly, SOT/fouls carry provider measurement noise, and the
  single-source-per-league feature design means no cross-source contamination is possible. Gate
  cleared.)*
- **Step 3 sanity gate — reproduces exactly.** Search only where it passes: **champ/goals,
  ligue2/cards, laliga2/cards**. Everything else untestable (champ/cards fails as expected per
  F017). Independent finding retained: cards persistence is **league-specific** (present in
  Ligue 2 / La Liga 2, flat in Championship), not a down-tier property.
- **Step 4 discovery — 0 survivors.** 968 new candidates, cumulative FDR family **22,855 →
  23,823**, 484 computable candidates screened, **zero survive** BH against the cumulative family.

## Step 5 — naive-baseline signal test (the new work)

For each scored predictor I converted the Poisson `predicted_lambda` to P(count > line) and
scored against a **naive baseline = point-in-time expanding over-rate**, reusing the exact
walk-forward models (no refit, no substitution). Metrics: Brier, **BSS vs naive**, ECE.

### The 7 existing metrics vs naive (first line, BSS %)

| League | best cards metric | best goals metric |
|---|---|---|
| Championship | −1.2 to −1.8% (flat, per F017) | goals_sot_xg **+0.56%** |
| Ligue 2 | cards_minimal_pair **+3.18%** | +0.39% |
| La Liga 2 | cards_minimal_pair **+2.90%** | −0.5 to −3.0% |

All small — consistent with the accumulated "signal at par / priced-in" history (F002/F003/F013).

### New-field candidates vs naive

| Cell | best new-field candidate | BSS vs naive |
|---|---|---|
| champ/goals@2.5 | `shotsOnTarget_w10 + big_chances_w10` | **+1.12%** |
| ligue2/cards@3.5 | `yellow_cards_w5 + tackles_w10` | +1.34% |
| laliga2/cards@3.5 | `fouls_w10 + clearances_w10` | +0.60% |

### Step 5b — does the richer data add anything? (the direct test)

| Gate cell | best FootyStats metric | best NEW-field candidate | new beats FS? |
|---|---|---|---|
| champ/goals@2.5 | goals_sot_xg **+0.56%** | shotsOnTarget+big_chances **+1.12%** | yes (by ~0.5pp) |
| ligue2/cards@3.5 | cards_minimal_pair **+3.18%** | yellow+tackles +1.34% | **no** |
| laliga2/cards@3.5 | cards_minimal_pair **+2.90%** | ball_recoveries+clearances +1.0% | **no** |

In **2 of 3** cells the existing FootyStats metric beats the best new-field candidate. In the one
cell where a new field (big_chances) nominally leads, the margin is ~0.5pp at a BSS of ~1% —
noise-level, and it did not survive FDR.

### The decisive honesty point

The **strongest screening candidate in the entire discovery run** — La Liga 2 cards,
`tackles_w10 + fouls_w10`, Spearman(predicted λ, actual) = **+0.156, p < 0.0001**, the top
near-miss — has **negative BSS vs naive**: **−0.85%** at O3.5, **−1.28%** at O4.5. A strong
rank-correlation between predicted intensity and realized cards did **not** translate into a
calibrated probability that beats simply predicting the base rate. This is exactly why the
screening statistic is a *screen*, not a result — and it strengthens the negative.

### `*_potential` reference bar (FootyStats public projections)

Evaluated as standalone per-match predictors on the FootyStats corpus (n=15,362):

| Projection | BSS vs naive | ECE |
|---|---|---|
| o25_potential (goals O2.5) | **−12.35%** | 0.108 |
| o35_potential | −8.09% | 0.096 |
| cards_potential | −10.78% | 0.110 |
| corners_o95_potential | −12.70% | 0.117 |

Used directly as probabilities, the public projections are **worse-calibrated than naive**
(negative BSS, ECE ~0.10–0.18). This is a *calibration* failure, not zero information:
`o25_potential` still **weakly discriminates** (AUC 0.540, Spearman +0.070, p=4e-18). Honest
reading: the free public estimate is a **low bar** — the discovery metrics' near-naive small
positive BSS already meets or slightly exceeds it, and the new fields add nothing beyond that.

## Step 6 — Honest interpretation

- **The broader claim is now tested against a naive baseline too, not just the market.** The
  ~24 previously-unsearched TheStatsAPI fields (defending block, big chances, touches in box,
  duels, np_xG, half-splits, …) produce **no candidate that survives cumulative FDR**, **no
  candidate that materially beats naive**, and **no candidate that beats the existing FootyStats
  metrics** where both are testable. The strongest one is worse than naive on calibration.
- **This is a stronger negative than any prior run**, and against a baseline that doesn't depend
  on odds at all: it isolates and answers the "is there signal in the richer data?" question in
  the negative for these fields/leagues at this sample size.
- **All candidates reported, worst included; no post-hoc selection.** Point estimates are tiny
  and CIs at per-cell n≈300–900 comfortably span zero; every positive number here is a
  hypothesis at best, not a result.
- **Held-out set: UNTOUCHED.** With 0 FDR survivors there is nothing to confirm, so no held-out
  data was read in any step of this task.
- **Retained by-products (hypotheses, not findings):** cards persistence is league-specific
  (Ligue 2 / La Liga 2 yes, Championship no); the strongest new-field direction is
  defensive-engagement → cards in La Liga 2 — but it fails both FDR *and* the naive-BSS bar.

## Ground-rules compliance

- Step 1 gated everything; Step 3 gated per league/target searching. ✓
- No model substitution; the 7 metrics re-scored as-is (no refit). ✓
- Balanced per-team coverage (full regular seasons; Champ 24×46, Ligue2 18×34, LaLiga2 22×42). ✓
- Cumulative FDR (22,855→23,823); demotions checked — none warranted (the 7 were already
  TESTED_NEGATIVE; they remain non-survivors and are not grandfathered). ✓
- Held-out untouched. ✓
- **Odds out of scope** — naive-baseline comparison only; no odds fetched or referenced in this
  addendum. ✓
- **Zero API requests** — all cached; monthly quota remains 5,518. ✓
- No shared/global config changed. New scripts import the existing modules unmodified. ✓
- Analysis code committed (below). ✓

## Artifacts (new in this addendum)

| Item | Path |
|---|---|
| Naive-baseline Step 5 (BSS/Brier/ECE, 7 metrics + candidates, per league/target/line) | `scripts/multisrc_step5_naive_baseline.py` → `data/results/multisrc_naive_baseline.json` |
| `*_potential` public-projection reference bar | `scripts/multisrc_step5b_potential.py` → `data/results/multisrc_potential_baseline.json` |
| Prior discovery (reused, verified) | `data/results/multisrc_discovery.json`, `docs/multisrc_discovery_report.md` |
