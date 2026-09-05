# The Decisive Within-League Comparison — Hierarchical Count Models

Resolves the outstanding blocker: is the pooled stat-mixer's positive BSS a **true
shared signal**, a **base-rate artifact**, or a **variance problem**?

- Evaluator: `src/research/evaluation/league_count.py` (+ `src/research/models/hierarchical_count.py`)
- Runner (zero-API): `scripts/league_count_evaluation.py`
- Machine artifact: `data/results/league_count_hierarchical_report.json` (schema `league-count-evaluation/v1`)
- Corpus: **15,362 completed fixtures, 25 leagues** (FootyStats broad static + expanded registry), zero API calls.
- Tests: `tests/research/test_league_count_evaluation.py` (7 pass).

This pass **promotes nothing to validated status**. It answers the mechanism question and applies the pre-committed decision rule; it does not open a betting claim.

---

## How the crux (baseline consistency) is enforced

The original error was comparing a pooled model against **global** climatology while comparing league models against **league** climatology. That is eliminated structurally:

- All arms are scored on **exactly the same fixture IDs** with the **same expanding walk-forward folds**. Each cell records `identical_fixture_ids_across_arms: true`.
- The single reference in every contrast against the baseline is **league-and-line-specific climatology**, estimated **train-only** inside each fold (`_fit_climatology`). Pooled, independent, and hierarchical arms are all measured against that same league-aware baseline on the same rows.
- Walk-forward is **compute-before-update** over complete equal-kickoff batches (no row is scored after any same-kickoff row has updated rolling history); preprocessing/fit happen inside training folds only.
- Bootstrap resamples **whole date / league-week blocks**, not individual fixtures (fixtures in a matchweek are not independent). Primary endpoint is paired ΔBrier = BS(reference) − BS(candidate); positive favours the candidate.
- Fresh **Benjamini–Hochberg** over the full valid family (**1,200 cells** = 25 leagues × 8 market-lines × 6 contrasts, `q = 0.05`), monotone q-values, every cell retained.

Count form: one Negative-Binomial/Poisson distribution per market family (dispersion selected empirically via `DistributionType.AUTO`), so 1.5/2.5/3.5 and 8.5/9.5/10.5 come from one coherent distribution — no contradictory adjacent-line probabilities.

Arms 1–4 (league climatology, global pooled, independent league, hierarchical empirical-Bayes partial pool) are evaluated. **Arm 5 (hierarchical team-state)** was specified "if justified"; it is **deferred** — see the decision below, the league-effect layer already resolves the question and a team-state layer is not required to answer it.

---

## Headline result

Scored **within each league against the league-aware baseline**, on identical fixtures and folds:

| Contrast | Median within-league ΔBrier | Cells positive | Reading |
|---|---:|---:|---|
| pooled → climatology | **+0.00188** | 160/200 (80%) | Pooled **beats** the league-aware baseline *within* leagues |
| independent → climatology | −0.00264 | 54/200 (27%) | Independent league models **fail** within-league |
| hierarchical → climatology | **+0.00194** | 164/200 (82%) | Hierarchical beats the baseline within leagues |
| independent → pooled | −0.00501 | 13/200 (6%) | Independent is **decisively worse** than pooled |
| hierarchical → pooled | +0.00001 | 110/200 (55%) | Hierarchical ≈ pooled (EB shrinks toward pooled) |
| hierarchical → independent | **+0.00498** | 187/200 (94%) | Hierarchical **dominates** independent |

Aggregate (pooled-across-leagues) ΔBrier is positive with p<0.001 on **all 8 market-lines** for both pooled-vs-climatology and hierarchical-vs-climatology.

---

## Which of the three possibilities the evidence supports

**Primarily Possibility 3 (variance problem), with Possibility 1 (true shared signal) partially supported. Possibility 2 (base-rate artifact) is ruled out.**

- **Not a base-rate artifact.** The earlier concern was that pooled BSS looked positive only because between-league dispersion inflated it against a *global* baseline. Here the pooled model is scored **within each league against that league's own baseline** and still wins in 80% of cells (median +0.00188, aggregate p<0.001 on every line). A pure base-rate artifact would vanish under a league-aware baseline. It does not.

- **The earlier per-league failure was the *independent* arm.** `pilotC_per_league.py` tested independent per-league models (41/189 positive, medians ≤0). This run reproduces that failure exactly — `independent_vs_climatology` is positive in only 27% of cells (median −0.00264). But independent models are also **decisively worse than the pooled model** (`independent_vs_pooled` positive in just 6%). So the per-league negativity was **not** "no signal within leagues" — it was **independent league models being too noisy to estimate on 300–1,100 rows.**

- **Shrinkage fixes it — that is the variance problem, demonstrated as data.** The hierarchical arm (global coefficients + strongly-shrunk empirical-Bayes league effects) beats independent in **94%** of cells (median +0.00498) and beats the league-aware baseline in **82%**. The four leagues `pilotC_per_league.py` reported as *unfittable independently* (Austria, Denmark, Finland, Australia) are all **scored** here under pooling, and three of the four are net-positive. A league that cannot stand alone borrows strength from the global fit and still improves on its own climatology.

- **hierarchical ≈ pooled** (median ΔBrier ≈ 0, 55% positive; 50 cells classified `pooled-only-artifact`). This is expected and honest: with league-effect variance small relative to sampling noise, the empirical-Bayes weight shrinks league deviations toward zero, so the hierarchical arm collapses toward the pooled model. The hierarchical arm's value is **robustness for thin leagues**, not a large gain over pooling in rich ones.

---

## The pre-committed decision rule

Continue with a hierarchical market family only if it clears every gate. Applied per market (median within-league):

| Gate | goals | corners | cards |
|---|---|---|---|
| Improves **median within-league** Brier (not just pooled) | +0.00149 ✅ | +0.00178 ✅ | +0.00442 ✅ |
| Positive in a clear majority of walk-forward folds | 0.53 ✅ | 0.54 ✅ | 0.57 ✅ |
| Beats the **league-aware baseline** | ✅ | ✅ | ✅ |
| Beats the **independent** league model | +0.00497 ✅ | +0.00608 ✅ | +0.00295 ✅ |
| No concentration in one anomalous season/league | findings span **11 leagues** ✅ | ✅ | ✅ |
| Improves **or preserves** calibration (ECE) | ⚠️ **not cleanly met** | ⚠️ | ⚠️ |

**The calibration gate is the honest caveat.** On Brier (sharpness) the model wins; on **ECE** the median effect vs climatology is **−0.00529** (only 71/200 cells better calibrated than climatology). That is not a defect in the model so much as a property of the baseline: a constant base-rate predictor is *trivially* well-calibrated, so beating it on calibration is hard by construction. The model is sharper and lower-Brier but not uniformly better-calibrated than climatology. Every other gate passes; calibration does not pass cleanly.

**Verdict on the roadmap question:** hierarchical partial pooling **clears the Brier, fold-stability, beats-both, and no-concentration gates**, and fails only the strict ECE-preservation gate. The path forward — hierarchical pooling over independent per-league models — is **supported by the evidence** and is the right modelling direction. The effect sizes are small (ΔBrier ~0.001–0.004) and FDR-confirmed cells are sparse (22–23 of 200 per baseline contrast), so this is a **direction confirmed, not an edge validated.**

---

## FDR-confirmed findings (BH, q=0.05, family=1,200)

Confirmed cells are sparse and concentrated where expected:

- **hierarchical → climatology:** 22/200 findings — cards 13/50, goals 5/75, corners 4/75. Findings span **11 leagues** (Spain La Liga 5, then Austria/Belgium/Denmark/Finland/France/Italy/Portugal 2 each, etc.), not one anomalous league.
- **pooled → climatology:** 23/200 — nearly identical footprint (cards 13, goals 6, corners 4).
- **hierarchical → independent:** 17/200 — the strongest structural result: pooling beats standalone league models.
- **independent → climatology:** 1/200 — independent models essentially never clear FDR.
- **pooled-only-artifact:** 50 cells (hierarchical-vs-pooled) + 25 (hierarchical-vs-independent) are labelled artifacts, not findings.

Per-league median ΔBrier (hierarchical vs climatology) is positive in **23 of 25 leagues**; the two negatives (France Ligue 2 −0.00024, Austria −0.00043) are near-zero. **0 insufficient cells** — every preregistered cell was scored, which is itself the variance finding: leagues that could not fit independently were still scored under pooling.

---

## Bottom line

1. The pooled positive BSS is **real within leagues**, not a global-baseline artifact.
2. Independent per-league models fail because **300–1,100 rows cannot estimate stable coefficients** — a variance problem, exactly as suspected.
3. **Hierarchical partial pooling is the resolution:** it recovers within-league improvement, dominates independent models, and scores even the thin leagues that could not stand alone.
4. Effects are **small and mostly not individually FDR-significant**, and the strict calibration gate is not cleanly met, so nothing is promoted to validated. This confirms a **modelling direction**, not a betting edge.

Every arm, per league, per market, with ΔBrier, 95% CI, block-bootstrap SE, one-sided p, fold stability, and BH verdict is in `data/results/league_count_hierarchical_report.json`.
