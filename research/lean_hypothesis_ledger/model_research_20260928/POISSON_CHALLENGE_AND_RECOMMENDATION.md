# Poisson challenge: a bounded model recommendation for Quant Football Engine

Date: 28 September 2026. Status: research recommendation, not implementation or promotion.

## Decision

Poisson is a useful baseline, not a universal best model. The best justified next candidate for corners is an opponent/venue-adjusted negative-binomial total with a coherent conditional team allocation. For goals, prioritize a reproducible, regularized attack/defense rate estimator before replacing Poisson. For bookings, do not prescribe negative binomial automatically: a recent yellow-card study finds underdispersion, making a mean-parameterized Conway–Maxwell–Poisson model a relevant conditional challenger.

No paper establishes which model will improve our own future forecasts. The recommendation identifies bounded, testable alternatives. Larger model–market gaps are not a success criterion.

Our agreed manual workflow is recorded in the ledger. Finish the existing 40-declaration pilot; 11 are declared and 29 remain. The three user-excluded fixture analyses and outcomes are audit-only and are not evidence for choosing these models. No pilot formula, champion, fitted bundle or decision threshold changed during this research.

## 1. Separate four different questions

1. **Mean:** How many goals/corners/cards should this team or match produce against this opposition, at this venue, in this competition?
2. **Distribution:** Given that mean and context, how variable is the count, including its tails?
3. **Dependence:** How are the two teams' counts related?
4. **Estimation uncertainty:** How uncertain are the fitted rates, dispersion, dependence and calibration?

A distribution cannot repair a systematically wrong mean. Conversely, an accurate mean can still produce badly priced threshold probabilities under the wrong distribution.

A conditional Poisson count has variance equal to its conditional mean. Independent home and away counts are an additional assumption, not a consequence of saying 'Poisson'. A high variance in a pooled sample of unequal teams does not by itself prove that conditional Poisson fails. Examine dispersion after accounting for supported covariates.

A changing deterministic event rate can still integrate to a Poisson count; merely observing different first/second-half tempos does not establish the need for another full-time count distribution. State-dependent stochastic intensities, clustering and omitted heterogeneity require a more careful model.

Deterministic analysis means a reproducible numerical mapping from eligible inputs and a frozen fitted bundle to probabilities. Negative binomial, Dixon–Coles, Weibull and CMP models can all have deterministic prediction. Bayesian training is not mandatory; regularized likelihood or empirical Bayes can keep computation small. Simulation randomness is not required to price a fitted count distribution.

## 2. Evidence that challenges the default

| Primary source | What it supports | What it does not establish |
|---|---|---|
| Maher (1982), S1 | Investigates Poisson models after accounting for team attack and defense, challenging premature preference for negative binomial. | Raw averages are sufficient or Poisson is always best. |
| Dixon & Coles (1997), S2 | Football-specific rate fitting, changing team strength and a local low-score dependence correction. | A universal tail correction or a guaranteed O2.5 improvement. |
| Yip et al. (2024 publication; inspected 2023 author manuscript), S3 | Tests overdispersed corner models, including negative binomial and geometric-Poisson. The manuscript reports an out-of-sample betting simulation in which varying-shape NB outperforms Poisson. | Transfer to our snapshots, leagues, current prices or football-only model. The study uses cross-market odds. |
| Philipson (2026), S4 | Yellow-card counts in five European leagues show underdispersion; a bivariate mean-parameterized CMP copula improves WAIC versus compared Poisson variants. | Prospective betting profitability, or transfer to international fixtures and all-card/booking-point contracts. |
| Baio & Blangiardo (2010), S5 | Hierarchical football models pool sparse teams, but excessive shrinkage can flatten genuinely different teams. | Hierarchical or Bayesian automatically means accurate. |
| Boshnakov, Kharrat & McHale (2017), S6 | A bivariate Weibull-count/copula alternative has published out-of-sample calibration and betting comparisons against Poisson variants. | Present-day transferable returns or a reason to implement it before simpler baselines. |
| Duan et al. (2020), S7 | NGBoost learns conditional distribution parameters rather than only a point forecast. | Football advantage, an appropriate count likelihood by default, or free epistemic uncertainty estimates. |
| Gneiting & Raftery (2007), S8 | Proper scoring rules evaluate honest probability forecasts rather than rewarding arbitrary extremity. | Hit rate or disagreement magnitude is enough to choose a model. |

These are research results in their own settings, not our validation. We did not copy any paper's fitted coefficients, ROI, referee effects or league dispersion into the pilot.

## 3. Recommended family models

### Goals: improve the rate estimator first

Proposed development baseline: a time-weighted, partially pooled attack/defense Poisson model, with competition and verified venue effects. Estimate home and away scoring intensities from eligible earlier matches rather than selecting a mixture of GF, xG, opponent GA and xGA after inspecting prices.

A conceptual rate equation is:

log(lambda_home) = competition baseline + supported home effect + home attack + away defensive weakness + supported covariates.

The away equation is analogous. Parameters, time weighting and regularization must be learned or fixed on earlier development data. Do not invent coefficients for weather, injuries or H2H. Preserve xG/npxG semantics, source coverage and sample overlap; use xG as a tested covariate rather than treating fractional xG as literal goal counts. The model's parameters require histories beyond a single summary screenshot.

Dixon–Coles is a cheap additional candidate for low scores, draws and BTTS. Its standard tau correction changes only (0,0), (0,1), (1,0) and (1,1). At fixed lambdas, those corrections sum to zero and every modified cell has at most two total goals. Therefore O2.5 and higher total-over probabilities are unchanged. Re-estimating the rates under the full fitted model can change them. This is an algebraic consequence of S2, verified in our synthetic check, not an empirical football result.

If held-out residual/tail diagnostics still reject Poisson after rate correction, a bivariate Weibull-count model is a credible later candidate because it can address dispersion and dependence. Defer its extra implementation until such a defect is demonstrated.

### Corners: negative-binomial total plus conditional team allocation

Recommended challenger:

- N = H + A follows negative binomial with mean mu and shape r.
- H conditional on N follows binomial as the simplest allocation model.
- Test beta-binomial allocation only when the conditional team share is too variable for binomial; A = N - H.
- Model mu and the expected home share from supported team production, opposition concession and venue/competition context. Pool sparsely estimated effects.

For NB, variance = mu + mu squared / r. Poisson is the limiting case as r grows. Estimate dispersion on the relevant earlier residuals, not from arbitrary 'typical corner variance', and test whether estimated extra dispersion improves out-of-time forecasts.

The beta-binomial component changes allocation and team-market probabilities. At fixed total PMF it cannot improve total-corner probabilities, because the conditional probabilities sum to one for every N. A primary total-corners test cannot establish the value of a pure allocation modification. Team-market evaluation must be separately specified.

The total/allocation structure is our engineering recommendation for coherence; the corner paper does not validate this exact architecture. A geometric-Poisson/Pólya–Aeppli count model is a secondary challenger if NB still misses clustering/tails. Do not confuse geometric-Poisson with generalized Poisson or a Gaussian process.

No constant dispersion is guaranteed across leagues or match types. Start pooled and simple; add a dispersion regression only when supported. Do not add complexity merely because a larger gap appears.

### Bookings: diagnose dispersion and contract first

Begin with an explicitly defined yellow-card count, team/opponent discipline, competition and eligible referee history with shrinkage. Compare Poisson against one dispersion-aware alternative chosen on development evidence.

- Residual overdispersion: negative binomial is a reasonable candidate.
- Residual underdispersion: NB cannot represent it; consider mean-parameterized CMP.
- Residual dependence: evaluate a coherent joint construction only if it adds supported value.

The mean parameterization matters: the ordinary CMP rate parameter is not generally its mean. Do not insert the screenshot average into that parameter and label the result fitted.

Cards, yellows, second yellows, reds, bench cards and weighted booking points are different targets. A model for yellow-card counts alone does not price every bookings contract.

## 4. Two mathematical checks that prevent misleading upgrades

The accompanying script contains synthetic inputs only. These numbers are not fitted football parameters or recommendations.

### More variance can increase OR decrease an Over probability

Hold the mean at 10. Compare Poisson (variance 10) with NB shape 10 (variance 20):

| Market | Poisson | Negative binomial |
|---|---:|---:|
| Over 8.5 | 66.72% | 59.27% |
| Over 9.5 | 54.21% | 50.00% |
| Over 12.5 | 20.84% | 26.17% |

An 'overdispersion upgrade' does not imply more Overs. Its effect depends on the threshold. This illustration cannot identify a suitable r for our data.

### Low-score correction is not an O2.5 upgrade at fixed rates

With synthetic lambdas 1.6 and 1.2 and rho -0.1, the standard Dixon–Coles correction changes BTTS from 55.77% to 56.94%, while O2.5 stays 53.05%. Full grid normalization and unchanged total-over probabilities were checked.

### Probability uncertainty must be priced in the correct units

For a binary no-push, no-commission contract, EV = d*p - 1. If a valid probability lower bound is p - delta, its EV is d*(p-delta)-1, not EV - delta.

Synthetic example: p=0.60, odds=2.10 and an assumed allowance delta=0.04. Point EV is 26%; the corresponding lower EV is 17.6%, not 22%. This verifies arithmetic only. The allowance itself is not validated uncertainty.

For pushes, split lines, commission and dependent state probabilities, price every fitted/refitted distribution through the full payoff function instead of transferring this scalar formula uncritically.

## 5. What the existing prototype tells us

Read-only evidence was inspected in /home/ubuntu/qfe-curated-offline. Its base HEAD remains 3afa8c716 and candidate code is uncommitted. Current artifact hashes and numerical results are captured in LOCAL_EVIDENCE.json, not presented as committed/immutable historical availability.

The prototype already implements NB total plus beta-binomial allocation. Its recorded 1,201-case evaluation gives M1 log loss 0.690921 and candidate 0.691866; improvement is -0.000944, with a 14-day interval [-0.002566, 0.001495]. Only 50 fixtures have eligible market pairs. The candidate is not shown to outperform the baseline overall, and the actual incumbent/manual baseline comparisons remain unreproduced.

This is not evidence that NB is inherently worse: the compared models change both the mean estimator and distribution, so the score difference does not isolate dispersion. At the same time, the model name does not justify replacing the pilot.

Its saved O9.5 probabilities span about 40.91% to 50.40%; the fitted mean coefficients are small and calibration is null. Investigate whether this reflects weak features, scaling/regularization, genuine weak signal, or other design limits. The narrow range alone does not prove over-shrinkage.

Two concrete pre-promotion issues:

1. Uncertainty is min(0.05, 0.25/sqrt(n)), a history-size heuristic rather than measured refit/calibration uncertainty.
2. That probability-unit quantity is subtracted directly from EV; missing uncertainty defaults to zero. Neither establishes a valid conservative economic bound.

This research did not repair those files or rerun a fitting battery. Fixing arithmetic and estimation provenance takes priority over trying a larger algorithm.

## 6. Spend credits on identifiable comparisons

For the future champion evaluation, after the manual-pilot review or explicit separate authorization:

1. **Reproduce inputs first.** Dated match-level counts, opponent identities, venue, competition, provider semantics and availability. A mean and N alone do not identify dispersion, dependence or a referee effect. Derived histories with unknown original receipt times stay development-only.
2. **Isolate the mean.** Compare the reproducible existing baseline and a regularized opponent-adjusted rate model on identical eligible data and a common distribution. Do not label a newly reconstructed historical formula the original manual baseline.
3. **Isolate the distribution.** Hold predicted means fixed and compare Poisson against NB for corner totals; fit shape on earlier training data only. This is the highest-value first distribution comparison.
4. **Isolate allocation.** With the same total distribution, compare binomial versus beta-binomial on team counts/markets. Do not claim a gain from total-only scores.
5. **Keep the search small.** One distribution challenger per family at a time; CMP only if supported by card dispersion, Weibull only if the goal baseline exhibits a concrete defect, geometric-Poisson only if NB corners remain inadequate. Defer boosting/ensembles.
6. **Freeze chronology and evidence.** Fit/calibrate/select only on earlier data; keep fixtures together across lines. Evaluate proper scores, calibration and count/tail fit with time-block uncertainty; apply the governing three gates and separate economic gate.
7. **Separate football-only and market-aware models.** A model using goal/result odds to predict corners is not odds-blind. Compare market-adjusted baseline/enhanced forecasts against a market-only comparator on the same quotes.
8. **Freeze the policy before results.** Report every eligible case, rejection and missing quote. Neither the excluded fixtures nor repeatedly inspected development history becomes a protected holdout.

This is a proposed bounded comparison plan, not a claim that any threshold, coverage gate or new candidate has been approved for live pilot use. Keep the manual pilot going under its recorded methods; do not silently change model versions or combine methods as one frozen strategy.

## Practical conclusion

The highest-value improvement is not 'replace Poisson everywhere'. It is to estimate opponent-adjusted rates reproducibly, identify residual dispersion/dependence by family, and price the resulting probabilities correctly. The strongest near-term distribution challenger is NB for corners. Goals may benefit more from a better Poisson rate model than a new count family. CMP is a serious bookings candidate when underdispersion is actually present.

No superiority claim, champion promotion, new pilot selection, paid model call or live football-provider call was made. This work used literature search, read-only code/artifact inspection and synthetic arithmetic.

## Primary references

S1. Maher (1982), Modelling association football scores.
https://doi.org/10.1111/j.1467-9574.1982.tb00782.x

S2. Dixon & Coles (1997), Modelling Association Football Scores and Inefficiencies in the Football Betting Market.
https://doi.org/10.1111/1467-9876.00065
Inspected paper copy: https://www.ajbuckeconbikesail.net/wkpapers/Airports/MVPoisson/soccer_betting.pdf

S3. Yip, Zou, Hung & Yiu (2024), Forecasting number of corner kicks taken in association football using compound Poisson distribution.
https://doi.org/10.1080/01605682.2024.2306170
Inspected author manuscript v3 (6 November 2023): https://arxiv.org/pdf/2112.13001
The manuscript's NB result uses cross-market information and its own historical simulation. It is not a raw-Scores365 replication.

S4. Philipson (2026), Yellow fever: an investigation into referee consistency in the Big 5 leagues of European football using a bivariate mean-parameterized Conway–Maxwell–Poisson copula model.
https://doi.org/10.1093/jrsssa/qnag014
Its model-comparison evidence is WAIC/posterior checking, not our chronological executable-odds validation.

S5. Baio & Blangiardo (2010), Bayesian hierarchical model for the prediction of football results.
https://discovery.ucl.ac.uk/16040/1/16040.pdf

S6. Boshnakov, Kharrat & McHale (2017), A bivariate Weibull count model for forecasting association football scores.
https://doi.org/10.1016/j.ijforecast.2016.11.006
Author manuscript: https://pure.manchester.ac.uk/ws/portalfiles/portal/49399144/ijfpaper.pdf

S7. Duan et al. (2020), NGBoost: Natural Gradient Boosting for Probabilistic Prediction.
https://proceedings.mlr.press/v119/duan20a.html

S8. Gneiting & Raftery (2007), Strictly Proper Scoring Rules, Prediction, and Estimation.
https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf
