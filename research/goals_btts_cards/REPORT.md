# Goals, BTTS and cards: calibration development

2026-09-29. Corners locked and unchanged. No corner fitting or comparisons ran in this experiment.

Scope is goals, BTTS and cards. The objective is calibrated probabilities and valid timestamped market comparison; larger disagreement alone is not success.

## What changed

- BTTS derives from the same independent Poisson goal distribution as home, away and total goals. Independence remains a model assumption to validate.
- A bounded joint calibration candidate estimates two side intercepts and a shared slope using only the earlier calibration segment, with regularization toward the unadjusted distribution. This preserves a compatible joint goal distribution.
- A deterministic binary no-push market comparison function checks fixture, market, side, period, line, quote timing and verified settlement semantics, then computes no-vig market probability, disagreement and executable-odds EV before costs. It does not authorize betting or certify probability quality.
- The existing corners model is byte-identical to the frozen source. The protection hash is 6497afc1c203d1da9f7f8385fbbfa49e03b2be0afb4f05f7155d1b401cfe191d.

## Development results

Positive gain means candidate calibration improves mean binary log loss versus the earlier M2 calibration. It is not an odds edge or probability adjustment.

| Target | Fixtures | Log-loss gain | Baseline Brier | Candidate Brier |
| --- | ---: | ---: | ---: | ---: |
| btts | 229 | +0.000147 | 0.254434 | 0.254350 |
| goals.away | 229 | -0.001267 | 0.216723 | 0.217119 |
| goals.home | 229 | -0.002467 | 0.224811 | 0.225950 |
| goals.total | 229 | +0.001636 | 0.245847 | 0.244977 |
| yellow_card_proxy.away | 24 | +0.001137 | 0.259617 | 0.259529 |
| yellow_card_proxy.home | 24 | +0.002391 | 0.227402 | 0.226307 |
| yellow_card_proxy.total | 24 | +0.004516 | 0.284183 | 0.282755 |

Every descriptive week-block 95% interval includes zero. The adjustment is not promoted. Total goals and BTTS improved slightly, team goals worsened slightly, and yellow-card proxy scores improved slightly with too little evidence for a reliable conclusion.

## Limits and pipeline state

This reuses previously exposed development data and is explicitly POST_EXPOSURE_DEVELOPMENT_ONLY. It cannot serve as independent confirmation. Early rich-stat training support is poor; goals/BTTS have 229 test fixtures, yellow cards only 24. Side and total cases are dependent.

These are goals over 1.5 for each side, total goals over 2.5, BTTS yes, and provider-yellow-card proxy over 1.5 per side/3.5 total. No inference about every possible line is warranted.

True bookmaker cards remain unsupported because provider-yellow-card labels are not proven equivalent to the available market. No proxy-based bookmaker EV is emitted. No matched historical odds exist in this pilot cache for these fixtures at the registered horizon, so real market disagreement, market-adjusted value and CLV remain MARKET_UNTESTED.

Four new tests passed: BTTS joint identity/symmetry, corners excluded from the new runner, market identity/timing/semantics guards, and bounded positive calibration. Result hashes and the protected model hash were verified. Earlier tests and evidence remain intact.

Registered code/specification commit: 344e68c. Branch: research/three-family-evidence-v1. Full probabilities, calibration parameters and intervals are in research/goals_btts_cards/out. No deployment, no production activation, no live provider calls, no paid LLM calls.

## Next research priority

Improve rich historical training coverage using the broader existing cached corpus, then compare goals/BTTS/cards on separately registered chronological folds. Avoid repeated calibration tuning on these same exposed cases. Preserve the existing corners model throughout.
