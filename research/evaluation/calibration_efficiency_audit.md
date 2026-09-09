# Phase 0 Audit — Calibration & Efficiency Experiment

Baseline `main` = `184f09d` (contains PR #4). Branch `experiment/calibration-efficiency`.
Evaluation only; champion untouched. Findings are grounded in code, not docs.

## The six audit questions

**1. How are home and away corner distributions generated?**
`HierarchicalCountModel` (`src/research/models/hierarchical_market_model.py`) fits ONE
hierarchical count model per market family over per-SIDE rows (`SideRow`): global
intercept+slopes, partially-pooled league intercept, nested team attack/concede
states, capped league-varying slopes, out-of-sample signal-scale shrinkage, and a
Gauss-Hermite uncertainty mixture over `log mu`. `predict_side(row)` →
`UncertainSideDistribution`.

**2. How are they combined into a total?**
`MatchCountDistribution.__post_init__` (line ~346):
`total = np.convolve(home_pmf, away_pmf)`. `p_over(line)` is the survival function of
that single convolved total PMF (line ~362). This is the ONLY place the total exists.

**3. Is independence actually assumed?** YES — the convolution IS the independence
assumption (home ⟂ away given fitted means). Made textual in `p_both_score`
("Conditional independence given the fitted means is the assumption"). A second,
separate engine `src/research/asymmetric/derived.py` also convolves under an explicit
`INDEPENDENCE_ASSUMPTION`.

**4. Where was residual home/away dependence measured?**
`scripts/audit_calibration.py` "Candidate C": Pearson residuals per side
(`(obs-mu)/sqrt(mu)`), `residual_correlation = corrcoef(home_res, away_res)`, plus
observed vs convolution-implied total variance. Recorded in
`CALIBRATION_AUDIT_AND_ROADMAP.md` as corners **−0.209** (observed/implied variance
0.806 → total variance overstated ~20%), first-half corners −0.162, cards **+0.181**
(positively coupled), goals −0.023 (fine). Documented as unfixed, needing a dependence
structure.

**5. Do xG/shots currently enter champion features?**
Per `market_family.py default_market_families()`:
- GOALS family produce = (shots_on_target, xg, shots, dangerous_attacks); `own_produce_xg`
  league-varying → **xG and shots ALREADY champion features for goals**.
- SHOTS_ON_TARGET family already uses xg + shots.
- CORNERS family produce = (corners, dangerous_attacks, shots_off_target); concede =
  (corners, dangerous_attacks) → **xG and total-shots are NOT corners features**.
- CARDS family does not use xG/shots.
Feature→corpus key map exists for xg (`team_a_xg`/`team_b_xg`) and shots
(`team_a_shots`/`team_b_shots`).

**6. Are FootyStats and TheStatsAPI xG/shots semantically comparable?**
From PR #4: providers AGREE on goals/corners/cards/possession/SoT (corr ≥0.99) but
DISAGREE on shots (corr 0.80, MAD 2.24 — different shot definition) and xG (corr 0.55,
MAD 0.69 — different xG models). Semantic detail (blocked shots, penalty xG) is NOT
documented by either provider payload → the deep semantic questions are
SEMANTICALLY_UNCERTAIN (addressed in Phase A1).

## Consequences for the two experiments

- **Experiment B (corners dependence)** targets the per-side convolution CHAMPION
  (`HierarchicalCountModel`/`MatchCountDistribution`). The dependence layer inserts at
  exactly one point — replace `np.convolve` with a copula-coupled joint whose margins
  are the two side PMFs. The marginal engine is preserved untouched. The −0.209 figure
  is reproducible via `audit_calibration.py`'s method on the champion corpus
  (`load_discovery_set()+load_heldout_set()`, `build_fixture_rows`, `training_rows`).
- **Experiment A (xG/shots)** is narrower than the brief assumes because xG/shots are
  ALREADY champion goals/SoT features. The defensible tests are:
  (a) does adding xG/shots to the CORNERS family (where absent) help corners? and
  (b) does the PROVIDER choice of xG/shots (FS vs TheStatsAPI) change goals results?
  PR #4 already found provider switching non-credible on the single-total arm; the
  champion goals family is where xG actually feeds, so provider-of-xG is the sharpest A test.

## Harness reuse
- Champion walk-forward: `scripts/audit_calibration.py::capture` + `src/research/models/side_rows.py`
  (`build_fixture_rows`, `training_rows`), `family_by_name`, corpus loaders.
- PR #4 infra: `src/research/experiments/provider_comparison/` (paired dataset, bridge,
  bootstrap, market, metrics) for provider-arm A tests + paired uncertainty.
- Corners lines: 7.5, 8.5, 9.5, 10.5. Distribution AUTO (Poisson/NB2 by residual dispersion).
