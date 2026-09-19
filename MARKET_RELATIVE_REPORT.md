# Market-Relative Test — Do Raw Stats Add Anything the Price Doesn't Have?

**Verdict: no.** Used as a residual on top of the de-vigged market price, leak-free
prior-only aggregate statistics add no reliable information beyond the price. Across
80 merged cached FootyStats league-seasons and 156 market×season cells, **zero** cells
show the residual model beating the market after Benjamini–Hochberg correction.

This tests the missing analysis angle directly. Earlier experiments modelled outcomes
independently and compared them with naive climatology. This experiment uses the
fixture's own de-vigged pre-match market probability as the baseline and asks only
whether aggregate statistics improve it.

## What was built

- **`src/research/models/market_relative.py` — `MarketRelativeCountModel`**

  ```text
  log(lambda_i) = log(lambda_market_i) + sum_j beta_j * (x_ij - mean_j)
  ```

  Two-way pre-match O/U odds are de-vigged and the fair over probability is inverted
  to a Poisson expected count. Leak-free prior rolling features can then move the
  prediction only relative to that market offset. There is no free intercept or team
  effect, and L2 shrinkage defaults to 5. Missing odds cause abstention; too little
  training data or any optimizer failure, including an exception, safely installs a
  market-only fallback. A zero residual reproduces the de-vigged market probability
  exactly. Missing and non-finite predictors are handled consistently between fit and
  prediction.

- **`src/research/models/prior_only_features.py`** adds the corpus odds mapping and
  attaches canonical target/line metadata. Non-finite and sentinel odds are rejected,
  reattaching odds invalidates cached lambdas, and the model rejects rows attached for
  a different target or line.

- **`scripts/market_relative_test.py`** runs expanding-window walk-forward evaluation
  with refits every 50 matches after a 100-match burn-in. It produces aligned
  walk-forward naive, market, and market-residual forecast series. Cached pagination
  files are merged and deduplicated by season before analysis; this fixed the previous
  inconsistency where 168 page-level entries were tested but only 156 unique result
  keys were retained.

  Uncertainty uses 10,000 paired circular moving-block bootstrap draws rather than IID
  fixture resampling. The adaptive block length is `min(50, n, max(5, ceil(sqrt(n))))`
  (8–22 fixtures in this corpus), preserving local dependence from rolling histories
  and shared refits. Full-precision p-values feed BH FDR at q=0.10.

- **`tests/test_market_relative.py`** contains six focused invariant tests. Together
  with the existing prior-feature tests, the focused validation run contains 17 tests.

Markets covered are goals O/U 2.5 and corners O/U 9.5, the two supported markets with
inline pre-match odds in the cached FootyStats corpus. Cards remain out of scope because
this corpus does not provide pre-match cards odds.

## Corrected results

Seed 20260902; 10,000 circular moving-block bootstrap draws per cell; BH family = 156;
q = 0.10; within-league evaluation only.

| Market | Cells | Market vs walk-forward naive, median | Residual vs market, mean | Residual vs market, median | Residual > market | CI entirely > 0 |
|---|---:|---:|---:|---:|---:|---:|
| Goals O/U 2.5 | 78 | **+2.67%** | **−2.23%** | **−2.06%** | 8/78 | 1 |
| Corners O/U 9.5 | 78 | **+1.10%** | **−3.38%** | **−3.08%** | 7/78 | 0 |

- The market beats the strictly prior walk-forward naive forecast by a median 2.67%
  Brier skill for goals and 1.10% for corners.
- The aggregate-stat residual is negative on average and at the median for both markets.
  It beats the market point estimate in only 8 goals cells and 7 corners cells.
- One goals cell has a nominal paired confidence interval above zero, but no positive
  cell survives correction across the 156-cell family.
- Mean standardized residual beta norm across refits that actually generated evaluated
  forecasts is 0.208 for goals and 0.139 for corners. The residual remains small and
  does not translate into out-of-sample skill over the market.

Artifact: `data/results/market_relative_test.json`. Its `family_size` is 156 and its
`cells` object contains exactly 156 entries. Each cell records its bootstrap block
length, mean residual beta norm across used refits, and number of used refits.

## Interpretation

This closes the plausible “the aggregate stats were framed incorrectly” gap. Measuring
against naive was not sufficient; measuring incremental information over the de-vigged
price was the right test. Under that stronger benchmark, these aggregate rolling
statistics still do not provide reliable residual signal.

Future signal research should prioritize genuinely point-in-time inputs that may not be
fully reflected at the decision timestamp: confirmed lineups and late withdrawals,
player availability, referee assignment, rest and congestion, and precise odds capture
time. That is primarily a forward data-collection problem, not another reprocessing
pass over the same aggregate corpus.

## Scope and honesty notes

- This is a research measurement, not a product, EV, ROI, or market-beating claim.
- Only the existing de-vig primitive is reused from the deprecated EV layer; that layer
  is not reactivated.
- FootyStats pre-match odds lack a true capture timestamp. They are suitable for this
  relative skill test but not sufficient for a CLV or deployable EV claim.
- The anti-leakage structural assertion runs once on the immutable feature set before
  walk-forward fitting. Every expanding training window is a prefix of that checked set.
- Reporting remains within league-season; results are not pooled across competitions.
