# QFE Team Corners V1 — Build Report

## Scientific status

QFE Team Corners V1 is an independent prospective research experiment. It does not
modify V3.7.1, V3.8.1, or CHAMPION. The LLM contributes no probability or numerical
feature. All probabilities are produced deterministically from frozen statistical code.

The model is trained from 4,487 historical matches with provider-native home and away
corner counts. Point-in-time feature reconstruction produced 7,836 eligible team-side
rows. Rows are chronological and target-fixture features use only prior matches.

## Frozen architecture

The predictive object is a team-corner count distribution. Three deterministic mean
estimators are combined before converting the count distribution to market-line
probabilities:

1. hierarchical team FOR × opponent AGAINST, with competition/venue shrinkage;
2. decay-weighted recent team FOR × opponent AGAINST;
3. ridge pressure model using prior shots, SoT, accurate crosses, possession and
   final-third entries.

Weights are learned on a chronological tuning tranche. Final probabilities use a
Negative Binomial distribution and one monotone Platt calibration.
## Chronological split and learned parameters

- Train team-side rows: 4,776
- Tuning team-side rows: 1,546
- Untouched holdout team-side rows: 1,514
- Ridge lambda: 0.1
- Ensemble: 70% hierarchical / 10% decay / 20% pressure
- Negative Binomial alpha: 0.0843487188
- Platt intercept: 0.1263556768
- Platt slope: 1.0422755151

The untouched holdout was not used to choose ridge lambda, ensemble weights,
dispersion, or calibration.

## Untouched holdout

Across the six preregistered lines (2.5–7.5), calibrated line-observations:
- Log Loss: 0.5673503
- Brier: 0.1923069
- ECE (10 bins): 0.0155344

Raw before Platt:
- Log Loss: 0.5681789
- Brier: 0.1926565
- ECE: 0.0220575

Calibration therefore improved all three proper-score/calibration diagnostics on the
untouched holdout. This is supporting evidence only, not prospective validation.
Count prediction on the same holdout:
- Ensemble MAE 2.1369, RMSE 2.7298, Poisson NLL 2.4181
- Hierarchical NLL 2.4222
- Decay NLL 2.4338
- Pressure NLL 2.4742

The ensemble beat each component on holdout count NLL.

Per-line calibrated ECE:
- 2.5: 0.0256
- 3.5: 0.0223
- 4.5: 0.0201
- 5.5: 0.0154
- 6.5: 0.0224
- 7.5: 0.0163

By role:
- Away: LL 0.5532, Brier 0.1866, ECE 0.0220
- Home: LL 0.5815, Brier 0.1981, ECE 0.0240

No role or preregistered line was removed after viewing these results.
## Prospective protocol

Cohort target: 50 fixtures with a valid Bet365 team-corners market and sufficient
point-in-time model history. Lines are whatever Bet365 actually quotes among
2.5–7.5. A fixture can produce at most one declaration per team side.

Frozen gate:
- selected probability >= 60%;
- model minus proportional no-vig market >= 5 percentage points;
- selected probability must exceed raw price break-even.

EARLY and MID snapshots may trigger declarations. FINAL snapshots are repeated in the
5–20 minute pre-kickoff window; the latest valid response-received quote is the
closing benchmark. Settlement requires the stable post-match score gate plus
provider-native team corner stats.

## Non-primary canary

A pre-freeze Kazakhstan–Moldova cached Bet365 snapshot was used only to verify market
orientation and line parsing. It is explicitly excluded from prospective evidence and
must never be backfilled into the V1 ledger.

## Promotion rule

No result from this build promotes the model to CHAMPION. Promotion requires genuine
prospective proper-score, calibration, market, closing-line and settlement evidence.
