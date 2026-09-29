# Three-family chronological development report

Date: 2026-09-29 (America/Bogota). Status: DEVELOPMENT_ONLY; MARKET_UNTESTED; no model promoted.

## Outcome

The requested offline semantic handling, historical pre-match feature construction and separate nine-target comparisons have been executed. Extra statistics did not improve every target. This is a bounded development run, not confirmation, a prospective pilot, or evidence of profitability.

## Results

Positive log-loss improvement means better. Rich gain = M1 minus M2. Hypothesis gain = M2 minus M2+H. Values are absolute mean binary log-loss differences, not probability changes or betting edges.

| Target | Line | Test fixtures | Rich gain | Hypothesis gain |
| --- | ---: | ---: | ---: | ---: |
| goals.away | 1.5 | 229 | +0.011587 | -0.000208 |
| goals.home | 1.5 | 229 | +0.009045 | -0.000210 |
| goals.total | 2.5 | 229 | +0.006034 | -0.000253 |
| corners.away | 4.5 | 25 | -0.060304 | +0.005914 |
| corners.home | 4.5 | 25 | +0.014996 | +0.007700 |
| corners.total | 9.5 | 25 | -0.074538 | +0.004783 |
| yellow_card_proxy.away | 1.5 | 24 | +0.017529 | -0.015932 |
| yellow_card_proxy.home | 1.5 | 24 | -0.014636 | +0.000401 |
| yellow_card_proxy.total | 3.5 | 24 | +0.005433 | -0.008140 |

Goals improved descriptively with the richer arm; the similarity addition did not improve them. Corners show deterioration in away and total forecasts despite small positive similarity increments. Yellow-card proxy results are mixed. No winning target or parameter setting has been selected for promotion.

Counts are unique fixtures within a family, not independent observations across home, away and total. Families overlap; their sample sizes must not be added.

## Design and chronology

- Frozen input: 560 Nations League fixtures; 220 detailed stat payloads. All comparisons use cached data only. The broader repository contains other cached corpora, which were not silently pooled into this pilot-cohort experiment.
- Fixed M1: regularized Poisson regression on shrunk historical target production/concession, opponent profiles and neutral-aware venue. This is not a head-to-head comparison with production CHAMPION or the original Dixon-Coles implementation.
- Fixed M2: matched M1 plus historical shots/SoT/box shots/big chances for goals; shots/blocked shots/crosses/final-third entries for corners; fouls/tackles for yellow cards.
- Fixed M2+H: matched M2 plus a deterministic, shrunk similar-opponent production deviation, using historical opponent target-concession and shot-concession profiles. Profiles can borrow the historical pool prior when team-specific support is sparse; this is a deliberately limited hypothesis implementation, not proof of all five curated hypotheses.
- Profiles use a 365-day decay half-life and five-match equivalent prior. At least three previous target-labelled matches per team are required.
- Reconstruction cutoff is 24 hours before kickoff; historical matches must precede that cutoff by an additional four-hour completion buffer. This convention does not prove historical publication times.
- Training-only imputation, missing indicators and scaling. One fixed alpha=1 fit per arm; no parameter tuning.
- Separate earlier calibration periods fit shrunk multiplicative corrections to home and away means. Total distributions sum independent side Poissons; independence and Poisson dispersion remain unvalidated assumptions.
- Goals: first fold train before September 2022, calibrate before September 2024, evaluate September–December 2024; second fold train before September 2024, calibrate through December 2024, evaluate 2025–September 2026. Test counts 155 and 74. Earlier test cases may enter later calibration, as in sequential evaluation; no future test cases enter fitting.
- The first registered calendar splits produced insufficient corner/card training support. Those failure records remain unchanged. A separate coverage-based supplement was registered before any corner/card model scores were viewed: train before 2024-11-14, calibrate until 2025-01-01, then evaluate through 2026-09-28. Corners: 45/29/25 train/calibration/test fixtures. Yellow cards: 41/29/24.

## Semantics resolved by explicit exclusion

- Regulation goals use score.regulation; extra-time and shootout scores never replace regulation goals.
- All-period corners and other rich statistics are excluded when extra time or duration remains ambiguous.
- Twelve matches have additive half/full discrepancies; six have no extra time recorded. Affected cells are quarantined, not overwritten with an invented correction. Full root-cause resolution requires better provider evidence; the current safe action is exclusion.
- Duplicate stat aliases are checked for conflicts. Missing and invalid values remain missing. Rates/percentages are not summed or relabelled as counts.
- Provider yellow cards remain a research proxy. Existing capability audit documents that the available total-cards market measures a different quantity; no verified team-side yellow-card price adapter exists. Real bookings market validation is therefore unsupported.
- xG/npxG, manager, referee, lineups and halftime-state features were not fitted because their coverage/semantics/availability conditions are not established here. Their raw evidence remains intact.

## Calibration and uncertainty

| Target | M1 Brier | M2 Brier | M2+H Brier | M2 calibration intercept/slope |
| --- | ---: | ---: | ---: | --- |
| goals.away | 0.222269 | 0.216723 | 0.216827 | 0.164 / 1.324 |
| goals.home | 0.229196 | 0.224811 | 0.224909 | -0.133 / 1.960 |
| goals.total | 0.248720 | 0.245847 | 0.245957 | -0.205 / 1.522 |
| corners.away | 0.187336 | 0.210557 | 0.207854 | -3.157 / -2.034 |
| corners.home | 0.240733 | 0.233425 | 0.229781 | -1.011 / 1.795 |
| corners.total | 0.197634 | 0.234747 | 0.232517 | -1.567 / -0.608 |
| yellow_card_proxy.away | 0.267673 | 0.259617 | 0.266115 | -0.925 / 1.230 |
| yellow_card_proxy.home | 0.220718 | 0.227402 | 0.225197 | 1.385 / -0.927 |
| yellow_card_proxy.total | 0.287344 | 0.284183 | 0.286888 | -0.001 / 0.169 |

Calibration parameters above are descriptive diagnostics on evaluation predictions, not refitted predictions. Ideal values are intercept 0 and slope 1. Calibration noninferiority is NOT established. Mean-rate correction alone is not proof of calibrated event probabilities.

Full outputs include reliability bins, count log loss and paired UTC-week-block bootstrap intervals. Only 12 goal blocks, five corner blocks and four card blocks are available. Intervals are nominal and unadjusted for multiple comparisons; no significance-based promotion is justified.

## Material limitation: rich training support

In the first goals fold, only 6 of 378 training team rows have at least three historical observations for every rich feature; in the second, 50 of 496. Corresponding test counts are 199/310 and 107/148. Missingness shifts substantially across time. The observed richer-arm gains cannot be cleanly attributed to reliable shot/chance information; missingness effects and sparse training remain plausible explanations. Corner/card training rows have much better rich-stat support but very small sample sizes.

This limitation is a reason to expand the cached historical corpus in a separately registered experiment, not to relabel this result as confirmed.

## Market and pipeline status

The pilot odds cache contains 28 files and zero fixture overlap with this historical corpus at the registered horizon. M0, market-only calibration, market-adjusted comparisons, closing-line value and prospective settlement were not fabricated and remain MARKET_UNTESTED. All candidates stop before promotion.

The numerical pipeline was preserved: predefined grounded question → deterministic lagged measurement → chronological model comparison → earlier calibration → evaluation. No LLM probability, effect adjustment or similarity score was used; similarity is computed in code. No autonomous discovery or paid LLM call occurred.

## Verification and artifacts

15 boundary/regression tests passed, including own/future-outcome leakage, cutoff equality, identity, period conflicts and training-only transforms. Output hashes, finite probabilities and side/total mean coherence were verified.

Repository branch: research/three-family-evidence-v1. Registered comparison commit: d297b3d. Coverage supplement specification: 02ccd68. Results and feature lineage are stored under research/three_family_evidence/out/development_v1 and development_v2; full source hashes and data hashes are in their manifests.

Production CHAMPION, frozen V3 and capture jobs were unchanged. Live calls: 0. Promotions: 0. Code and results are committed locally; not deployed.

## Recommended next step

Use the existing broader provider-native cached corpus to obtain adequate rich prehistory, with a new coverage audit and frozen comparison before evaluating results. Resolve yellow-card/bookmaker equivalence before any bookings market claim. Do not promote the current richer corner specification, and do not claim proven hypothesis-layer value from this run.
