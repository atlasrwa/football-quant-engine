# Implementation Plan: Asymmetric Matchup Engine

## Overview

This plan builds the Asymmetric Matchup Engine inside the existing Python quant engine at `/home/ubuntu`, following the design's package layout (`src/research/asymmetric/*`, `scripts/asymmetric_analyze.py`, `tests/asymmetric/*`) and reusing the existing modules named in the design's "Reused vs New Components" table. Implementation language is **Python** (pydantic v2, scipy, `hypothesis` for property tests, `pytest` for unit/integration), as fixed by the design.

Tasks are ordered so each builds on the previous with no orphaned code: package scaffold + data models first, then corpus loaders, profiler, directional model + shrinkage, interaction model (two directions) + cards conditioning, derived-outcome combiner + correlation check, the gates, the evaluator + fresh FDR family, reporting, the CLI, and finally dual-corpus wiring and the end-to-end run.

All 24 correctness properties from the design are each implemented as exactly one property-based test tagged `# Feature: asymmetric-matchup-engine, Property N: ...` with `@settings(max_examples=100)` (min 100 examples), grouped alongside the component they validate. Property-test and other test sub-tasks are marked optional with `*`; core implementation sub-tasks are not.

Commit-and-push checkpoints (Req 14.1) are embedded as sub-steps; the `hypothesis` dev-dependency addition is flagged as a shared-config change (Req 14.2).

## Tasks

- [x] 1. Scaffold the isolated package and pydantic data models
  - [x] 1.1 Create the `src/research/asymmetric/` package scaffold and test tree
    - Create `src/research/asymmetric/__init__.py` and empty module files per the design's package layout: `profiles.py`, `profile_dimensions.py`, `interaction.py`, `directional_model.py`, `derived.py`, `correlation.py`, `gates.py`, `evaluation.py`, `fdr_family.py`, `reporting.py`, `corpus.py`, `resolution.py`, `live_fetch.py`, `models.py`
    - Create `tests/asymmetric/__init__.py` and a `conftest.py` matching the existing `pytest` `pythonpath=["."]` convention
    - Ensure the package imports nothing from Pilot C, Pipeline A, manual work, or flagged ledgers (isolation)
    - _Requirements: 13.2, 13.4_
  - [x] 1.2 Implement pydantic v2 data models in `models.py`
    - Implement `ProfileDimension`, `AttackingProfile`, `DefensiveProfile`, `TeamMatchProfiles`, `DirectionPrediction`, `FixturePrediction`, `DerivedOutcomes`, `GateCheckResult`, `GateResult`, `Estimate`, `AsymmetryComparison`, `SpendReport` exactly as specified in the design's Data Models section (frozen `ConfigDict`, `pydantic==2.6.1`)
    - Implement `AttackingProfile.vector()` / `DefensiveProfile.vector()` returning continuous feature vectors, and `Estimate.spans_zero` / `Estimate.is_result` properties
    - _Requirements: 1.1, 1.2, 1.16, 2.4, 2.8, 3.1, 10.8, 10.9_
  - [x]* 1.3 Write unit tests for data models
    - Test frozen immutability, `vector()` ordering/length, and `Estimate.spans_zero`/`is_result` boundary behaviour (CI touching zero)
    - _Requirements: 1.2, 10.8, 10.9_
  - [x] 1.4 Commit and push the scaffold
    - Commit `src/research/asymmetric/` scaffold and `models.py`; push. No shared-config change in this unit
    - _Requirements: 14.1_

- [x] 2. Implement cached corpus loaders (zero-API)
  - [x] 2.1 Implement `RichCorpusLoader` and `BroadCorpusLoader` in `corpus.py`
    - Reuse `research/data_source.py` `ResearchMatch` and `research/footystats/` to load the Rich_Corpus (`data/thestatsapi`, ~3189) and Broad_Corpus (FootyStats, ~15362) from cache only
    - Loaders MUST accept an injected data source that reads cache exclusively and MUST NOT import `live_fetch.py`
    - Preserve NULL≠ZERO field semantics from the normalizer
    - _Requirements: 4.1, 4.2, 12.1, 12.2, 13.4_
  - [x]* 2.2 Write unit tests for corpus loaders
    - Test that both loaders read from cache, surface `None` for absent fields (NULL≠ZERO), and expose league identity per match
    - _Requirements: 4.1, 4.2_
  - [x]* 2.3 Write property test for zero API during build/backtest
    - **Property 23: Zero API during build and backtest** — inject an API client stub that raises on any call; assert loaders and any build/backtest path never invoke it
    - **Validates: Requirements 12.1, 12.2**
    - `# Feature: asymmetric-matchup-engine, Property 23: ...`, `@settings(max_examples=100)`
    - _Requirements: 12.1, 12.2_

- [ ] 3. Implement the Team_Profiler
  - [x] 3.1 Implement named profile dimensions and reduced-profile map in `profile_dimensions.py`
    - Define the five attacking dimensions (`width`, `central_penetration`, `volume_vs_quality`, `set_piece_reliance`, `directness`) and five defensive dimensions (`block_orientation`, `aerial_vs_ground`, `shot_suppression`, `gk_contribution`, `discipline`) with their source raw fields
    - Define the Broad_Corpus reduced-profile map (width from corners, directness from attacks-vs-dangerous-attacks ratio, discipline from fouls and cards; rich-only dimensions marked absent)
    - Build the `gk_contribution` dimension from saves (and `high_claims` where present) and NOT from `goals_prevented`, which the coverage audit found zero-populated across the Rich_Corpus leagues
    - Flag `central_penetration` as reduced-confidence for the Championship because `touches_in_penalty_area` is thin (~5%) there
    - _Requirements: 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 1.14, 1.15, 4.3, 17.1, 17.2, 17.3_
  - [-] 3.2 Implement `TeamProfiler` in `profiles.py`
    - Reuse the "compute-before-update" chronological discipline from `src/features/rolling_form.py` (`deque(maxlen=10)`), expanding fallback under 10 matches, keyed on team identity across home and away matches, all leagues
    - Team identity used only as an aggregation key, never as a feature (identity-free vectors)
    - Mark profiles `insufficient=True` when `< 5` completed matches; record `missing_fields` and exclude affected matches per feature when a raw field is unavailable
    - When `goals_prevented` is unavailable for a league, compute the `gk_contribution` feature from the available goalkeeper fields and record `goals_prevented` in `missing_fields`; carry a reduced-confidence flag on `central_penetration` where `touches_in_penalty_area` is thin
    - Implement `compute_profiles_map(matches)` and `profile_for_team_at(team, as_of_unix, history)`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.16, 1.17, 1.18, 11.1, 11.3, 11.4, 17.1, 17.2, 17.3_
  - [x] 3.3 Implement the reduced-profile variant path in `TeamProfiler`
    - When `reduced=True`, build only the Broad_Corpus dimensions and carry the `reduced` flag on the profile for rich-vs-broad reporting
    - _Requirements: 4.3, 4.5_
  - [x]* 3.4 Write property test for point-in-time invariance
    - **Property 2: Point-in-time invariance** — profile for match M from full history equals profile from history truncated strictly before M
    - **Validates: Requirements 1.4, 6.5, 11.1, 11.3**
    - Uses the `match_histories` strategy; `# Feature: asymmetric-matchup-engine, Property 2: ...`, `@settings(max_examples=100)`
    - _Requirements: 1.4, 11.1, 11.3_
  - [x]* 3.5 Write property test for identity relabel-invariance and all-leagues aggregation
    - **Property 3: Team-identity relabel-invariance and all-leagues aggregation** — relabelling identity (only) yields identical vectors; match count aggregated equals completed-match count across all leagues
    - **Validates: Requirements 1.3, 1.5, 1.18, 11.4**
    - `# Feature: asymmetric-matchup-engine, Property 3: ...`, `@settings(max_examples=100)`
    - _Requirements: 1.3, 1.5, 1.18, 11.4_
  - [x]* 3.6 Write property test for missing-field exclusion
    - **Property 11: Missing-field exclusion** — each affected feature computed only from present-field matches and equals the feature over that subset; absent field recorded in `missing_fields`
    - **Validates: Requirements 1.17**
    - `# Feature: asymmetric-matchup-engine, Property 11: ...`, `@settings(max_examples=100)`
    - _Requirements: 1.17_
  - [x]* 3.7 Write edge-case unit tests for min-history boundary and reduced dimensions
    - Test the `< 5` insufficient boundary exactly at 4 and 5 matches (1.16); test the reduced-profile dimension set for Broad_Corpus (4.3)
    - _Requirements: 1.16, 4.3_
  - [x] 3.8 Commit and push the profiler
    - Commit `profile_dimensions.py`, `profiles.py`, and their tests; push. No shared-config change
    - _Requirements: 14.1_

- [x] 4. Implement the directional count model (elastic-net + shrinkage)
  - [x] 4.1 Implement `DirectionalCountModel` in `directional_model.py`
    - Extend the reused MLE from `src/research/models/count_regression.py`: reuse `_select_distribution` (`DistributionType.AUTO`, NB vs Poisson) and report the empirical dispersion ratio
    - Replace the L2-only penalty with elastic-net `lambda * (alpha_mix * sum(sqrt(w^2 + eps)) + (1 - alpha_mix) * sum(w^2))` (defaults `lambda=0.05`, `alpha_mix=0.5`), keeping L-BFGS-B stable via smoothed absolute value
    - Remove the team-identity effect layer; apply `n/(n+k)` (`k=10.0`) shrinkage to per-team profile-feature estimates toward the global mean
    - Implement `fit`, `predict_distribution` (full PMF via Poisson/NB), `predict_expected_count`; keep coefficients readable for reporting
    - _Requirements: 5.1, 5.3, 5.4, 5.5, 5.6, 10.3_
  - [x] 4.2 Wire binary derived outcomes to the logistic model
    - Use the existing `LogisticRegressionModel` in `probability.py` for binary Derived_Outcomes
    - _Requirements: 5.2_
  - [x]* 4.3 Write property test for shrinkage monotonicity
    - **Property 8: Team-level shrinkage monotonicity** — increasing n moves the shrunk estimate monotonically toward the team mean; weight `n/(n+k)` strictly increasing in n
    - **Validates: Requirements 5.1, 5.6**
    - `# Feature: asymmetric-matchup-engine, Property 8: ...`, `@settings(max_examples=100)`
    - _Requirements: 5.1, 5.6_
  - [x]* 4.4 Write property test for dispersion-driven distribution selection
    - **Property 9: Dispersion-driven distribution selection** — NB selected when variance/mean exceeds threshold, Poisson otherwise; empirical dispersion ratio reported
    - **Validates: Requirements 5.3**
    - `# Feature: asymmetric-matchup-engine, Property 9: ...`, `@settings(max_examples=100)`
    - _Requirements: 5.3_
  - [x]* 4.5 Write property test for elastic-net behaviour
    - **Property 10: Elastic-net regularization shrinks coefficients and retains correlated features** — increasing lambda gives non-increasing L2 coefficient norm; two correlated informative features both retain non-zero weight
    - **Validates: Requirements 5.4, 5.5**
    - `# Feature: asymmetric-matchup-engine, Property 10: ...`, `@settings(max_examples=100)`
    - _Requirements: 5.4, 5.5_
  - [x]* 4.6 Write property test for valid predictive distributions
    - **Property 4: Valid predictive distributions** — every PMF entry in [0,1] and entries sum to 1 within tolerance, for each target
    - **Validates: Requirements 2.4, 2.5, 2.6, 2.7**
    - `# Feature: asymmetric-matchup-engine, Property 4: ...`, `@settings(max_examples=100)`
    - _Requirements: 2.4, 2.5, 2.6, 2.7_
  - [x] 4.7 Commit and push the directional model
    - Commit `directional_model.py` and tests; push. No shared-config change
    - _Requirements: 14.1_

- [x] 5. Implement the Interaction_Model (two directions) with cards conditioning
  - [x] 5.1 Implement referee card-rate conditioning
    - Add `RefereeCardRate` (adapting `src/features/referee_volatility.py`): expanding, look-ahead-free, league-fallback; when referee is missing or insufficiently observed, substitute the league-level expanding card rate and set `referee_substituted=True`
    - Treat the league-level expanding-window card rate as the PRIMARY pre-match conditioning path (not merely a fallback), because referee assignment is unavailable pre-match in both data sources; use a referee-specific rate ONLY in backtest on completed fixtures with a known post-match referee id; the Analysis_CLI never conditions a pre-match cards prediction on a referee-specific rate
    - _Requirements: 2.7, 2.11, 16.1, 16.2, 16.3, 16.4_
  - [x] 5.2 Implement `InteractionModel` in `interaction.py`
    - Model each fixture as exactly two Directions (A-attack vs B-defence, B-attack vs A-defence), each a separately fitted `DirectionalCountModel`; never collapse to a symmetric feature
    - Build the linear predictor from attacker's attacking dimensions + defender's defensive dimensions + named interaction cross-terms; add the referee card-rate term for the cards target
    - Implement `fit(dataset)` and `predict_fixture(fixture_ctx)` returning per-side full predictive distributions for corners, cards, goals, SOT with named driving features surfaced
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.11_
  - [x]* 5.3 Write property test for directions never collapsing
    - **Property 1: Directions never collapse to a symmetric output** — differing profiles give non-identical direction distributions; swapping A and B swaps the outputs
    - **Validates: Requirements 2.1, 2.2, 2.3**
    - Uses the `fixture_contexts` strategy; `# Feature: asymmetric-matchup-engine, Property 1: ...`, `@settings(max_examples=100)`
    - _Requirements: 2.1, 2.2, 2.3_
  - [x]* 5.4 Write property test for referee substitution and flagging
    - **Property 5: Referee substitution and flagging for cards** — uses referee rate when assigned and observed; otherwise substitutes league rate and sets `referee_substituted=True`; substituted prediction equals the league-rate-conditioned prediction
    - **Validates: Requirements 2.7, 2.11**
    - `# Feature: asymmetric-matchup-engine, Property 5: ...`, `@settings(max_examples=100)`
    - _Requirements: 2.7, 2.11_
  - [x] 5.5 Commit and push the interaction model
    - Commit `interaction.py`, referee conditioning, and tests; push. No shared-config change
    - _Requirements: 14.1_

- [x] 6. Implement the Derived_Outcome combiner and correlation check
  - [x] 6.1 Implement `DerivedOutcomeCombiner` in `derived.py`
    - Mirror `src/research/models/derived_goals.py`: derive total corners/cards/goals via discrete convolution of the two per-side distributions; BTTS = `P(A>=1)*P(B>=1)`; clean sheet per side = `P(opponent goals = 0)`, all under the stated independence assumption emitted alongside each outcome
    - Never model any Derived_Outcome directly
    - _Requirements: 2.9, 2.10, 3.1_
  - [x] 6.2 Implement Correlation_Structure constants and comparison in `correlation.py`
    - Encode measured constants (cards×corners -0.033, cards×goals -0.030, corners×goals -0.028, 95% CI ±0.016); compute implied correlation from the per-side joint; red-flag when implied lies outside `measured ± max(CI, 0.05)`; always report measured values and CIs alongside the comparison
    - _Requirements: 3.2, 3.3, 3.4_
  - [x]* 6.3 Write property test for derived combination under independence
    - **Property 6: Derived combination under independence** — total = discrete convolution and a valid PMF; total mean = sum of per-side means; BTTS = `P(A>=1)*P(B>=1)`
    - **Validates: Requirements 2.9, 3.1**
    - Uses the `count_pmfs` strategy; `# Feature: asymmetric-matchup-engine, Property 6: ...`, `@settings(max_examples=100)`
    - _Requirements: 2.9, 3.1_
  - [x]* 6.4 Write property test for implied-vs-measured correlation red flag
    - **Property 7: Implied-vs-measured correlation red flag** — red flag raised iff implied correlation lies outside the measured value by more than the reported tolerance
    - **Validates: Requirements 3.2, 3.3, 3.4**
    - `# Feature: asymmetric-matchup-engine, Property 7: ...`, `@settings(max_examples=100)`
    - _Requirements: 3.2, 3.3, 3.4_
  - [x]* 6.5 Write unit tests for derive-don't-model and reported constants
    - Assert no Derived_Outcome is modelled directly (2.10); assert measured correlation constants and ±0.016 CI are reported (3.4)
    - _Requirements: 2.10, 3.4_
  - [x] 6.6 Commit and push the combiner and correlation check
    - Commit `derived.py`, `correlation.py`, and tests; push. No shared-config change
    - _Requirements: 14.1_

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement the Feature_Verification_Gate and Sanity_Gate
  - [x] 8.1 Implement the five-check `FeatureVerificationGate` in `gates.py`
    - Implement team-identity trace (print for 3–5 teams), known-signal (xG→goals >= ~0.10, rolling goals→goals positive), orientation (team_a features align with team_a outcomes, verified against source), look-ahead (recompute from truncated history and assert equality), shuffle-null (permuted mapping collapses to chance)
    - Run before any modelling; report every check; on any failure set `passed=False`, `stopped_modelling=True`, and stop before modelling
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_
  - [x] 8.2 Implement the `SanityGate` records in `gates.py`
    - Record (do not re-diagnose) corners near-zero team-level persistence (7.2) and cards disciplinary-persistence absence in the Championship across three seasons (7.3); run per league and per target; surface `SanityRecord` entries; skip re-diagnosis
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - [x]* 8.3 Write property test for gate stopping on any failure
    - **Property 14: Gate stops modelling on any failure** — any failing check yields `passed=False` and `stopped_modelling=True`; no downstream modelling
    - **Validates: Requirements 6.1, 6.7, 6.8**
    - `# Feature: asymmetric-matchup-engine, Property 14: ...`, `@settings(max_examples=100)`
    - _Requirements: 6.1, 6.7, 6.8_
  - [x]* 8.4 Write property test for shuffle-null collapse
    - **Property 13: Shuffle-null collapses to chance** — permuted feature-to-outcome mapping yields out-of-sample BSS within tolerance of zero
    - **Validates: Requirements 6.6**
    - `# Feature: asymmetric-matchup-engine, Property 13: ...`, `@settings(max_examples=100)`
    - _Requirements: 6.6_
  - [x]* 8.5 Write unit tests for gate reporting and sanity records
    - Assert the identity trace prints 3–5 teams (6.2), known-signal threshold check (6.3), orientation cross-check against source (6.4), and that sanity records are present and not re-diagnosed (7.2–7.4)
    - _Requirements: 6.2, 6.3, 6.4, 7.2, 7.3, 7.4_
  - [x]* 8.6 Write the point-in-time enforcement verification test
    - Verify the look-ahead gate check recomputes a sampled feature from truncated history (strictly before M) and asserts equality with the pipeline value across profiling, interaction modelling, and validation
    - _Requirements: 6.5, 11.1, 11.3_
  - [x] 8.7 Commit and push the gates
    - Commit `gates.py` and tests; push. No shared-config change
    - _Requirements: 14.1_

- [x] 9. Implement the asymmetry evaluator, symmetric baseline, and fresh FDR family
  - [x] 9.1 Implement `SymmetricBaseline` in `evaluation.py`
    - Same Poisson/NB family using only the team's own marginal rate for the target, with no interaction layer
    - _Requirements: 8.1_
  - [x] 9.2 Implement `build_asymmetric_family` in `fdr_family.py`
    - Wrap `src/research/fdr/family.py` `ResearchFamilyBuilder`: build a fresh family with `hypothesis_count` = number of target×direction×league models tested; deterministic `family_id` from this engine's run identity, dataset version, and model family; never inherit any prior-effort family
    - _Requirements: 8.8, 8.10, 13.3_
  - [x] 9.3 Implement `AsymmetryEvaluator` in `evaluation.py`
    - Drive walk-forward CV folds from `src/research/walkforward/folds.py`; compare Interaction vs Symmetric_Baseline out-of-sample per market and per league; never report interaction performance in isolation
    - Beat criterion: BSS improvement strictly positive with bootstrap 95% CI lower bound > 0, else report failure; require within-league significance at alpha 0.05; label pooled-only significance as artifact; label below-minimum within-league sample as insufficient-sample and exclude from findings/artifacts
    - Correct within-league significance via Benjamini-Hochberg q=0.05 through `src/research/fdr/adapter.py` `FDRAdapter`; report the FDR family size
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.9, 8.11, 11.2_
  - [x]* 9.4 Write property test for out-of-sample fold disjointness
    - **Property 12: Out-of-sample fold disjointness** — fit fixture ids disjoint from score fixture ids for every fold
    - **Validates: Requirements 8.2, 11.2**
    - Uses the `match_histories` strategy; `# Feature: asymmetric-matchup-engine, Property 12: ...`, `@settings(max_examples=100)`
    - _Requirements: 8.2, 11.2_
  - [x]* 9.5 Write property test for asymmetry verdict decision logic
    - **Property 16: Asymmetry verdict decision logic** — verdict is "finding" only if BSS improvement strictly positive with 95% CI lower bound > 0 AND within-league significant at 0.05 AND survives BH q=0.05; otherwise "fails"
    - **Validates: Requirements 8.1, 8.3, 8.5, 8.6, 8.9**
    - Uses the `estimates` strategy; `# Feature: asymmetric-matchup-engine, Property 16: ...`, `@settings(max_examples=100)`
    - _Requirements: 8.1, 8.3, 8.5, 8.6, 8.9_
  - [x]* 9.6 Write property test for pooled-only artifact labelling
    - **Property 17: Pooled-only significance is an artifact** — significant only when pooled and not within league yields verdict "artifact", never "finding"
    - **Validates: Requirements 8.7**
    - `# Feature: asymmetric-matchup-engine, Property 17: ...`, `@settings(max_examples=100)`
    - _Requirements: 8.7_
  - [x]* 9.7 Write property test for insufficient-sample exclusion
    - **Property 18: Insufficient-sample exclusion** — below-minimum within-league sample yields verdict "insufficient-sample" and is excluded from findings and artifacts
    - **Validates: Requirements 8.11**
    - `# Feature: asymmetric-matchup-engine, Property 18: ...`, `@settings(max_examples=100)`
    - _Requirements: 8.11_
  - [x]* 9.8 Write property test for fresh FDR family sizing
    - **Property 19: Fresh FDR family sizing** — `hypothesis_count` equals number of target×direction×league models tested; `family_id` is a deterministic function of only this engine's run identity, dataset version, and model family
    - **Validates: Requirements 8.8, 8.10, 13.3**
    - `# Feature: asymmetric-matchup-engine, Property 19: ...`, `@settings(max_examples=100)`
    - _Requirements: 8.8, 8.10, 13.3_
  - [x]* 9.9 Write integration test for fresh-family isolation from prior efforts
    - Assert the constructed family is disjoint from prior-effort families and that no prior-effort scripts are imported in the build path (13.3)
    - _Requirements: 8.10, 13.3_
  - [x] 9.10 Commit and push the evaluator and FDR family
    - Commit `evaluation.py`, `fdr_family.py`, and tests; push. No shared-config change
    - _Requirements: 14.1_

- [x] 10. Implement reporting
  - [x] 10.1 Implement `reporting.py` report assembly
    - Assemble headline per-side vs baseline per market and per league; rich-vs-broad comparison; readable elastic-net coefficients per dimension; ECE and reliability curves per target via `src/research/calibration.py` `CalibrationEvaluator`; out-of-sample BSS vs naive baseline, Brier, and ECE; all results including failures with no post-hoc selection; fresh FDR family size; a CI for every reported estimate; label any estimate whose CI spans zero as "not a result"
    - _Requirements: 4.4, 4.5, 5.7, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9_
  - [x]* 10.2 Write property test for CI presence and CI-spanning-zero suppression
    - **Property 15: Confidence interval on every estimate and CI-spanning-zero suppression** — `ci_low <= point <= ci_high`; estimate is a result iff its CI does not span zero; spanning-zero labelled "not a result"
    - **Validates: Requirements 10.8, 10.9**
    - Uses the `estimates` strategy; `# Feature: asymmetric-matchup-engine, Property 15: ...`, `@settings(max_examples=100)`
    - _Requirements: 10.8, 10.9_
  - [x]* 10.3 Write unit test for tail-calibration bins
    - Assert tail-calibration bins are produced against realised outcomes via `CalibrationEvaluator` (5.7)
    - _Requirements: 5.7, 10.4_
  - [x] 10.4 Commit and push reporting
    - Commit `reporting.py` and tests; push. No shared-config change
    - _Requirements: 14.1_

- [x] 11. Implement the Analysis_CLI
  - [x] 11.1 Implement team resolution and fixture lookup in `resolution.py`
    - Resolve home/away names: unrecognised → reject and identify the name; ambiguous → reject and list candidates; no scheduled fixture on the date → report no matching fixture; all without producing predictions
    - _Requirements: 9.13, 9.14, 9.15_
  - [x] 11.2 Implement `CappedLiveFetcher` in `live_fetch.py`
    - Reuse `research/footystats/client.py` / `scripts/thestatsapi_client.py` for capped live fetch; admit spend up to the cap; when the next fetch would breach the cap, refuse it and set `cap_exceeded=True`; report `spend_units` = sum of admitted costs; confined to the CLI package, never imported into build/backtest
    - _Requirements: 9.16, 12.3, 12.4_
  - [x] 11.3 Implement `scripts/asymmetric_analyze.py` CLI
    - Accept `--home`, `--away`, `--date` (ISO 8601 YYYY-MM-DD); resolve teams and fixture; cache-then-live-fetch via `CappedLiveFetcher`
    - Coverage handling: zero cached history → report no profile, identify team, terminate without predictions; `>=1` but `< 5` → flag reduced-coverage, state count vs minimum, continue with reduced profile
    - Narrative sections: profiles as named dimensions with numeric values; per-side predictions for corners/cards/goals/SOT with named driving features; derived totals + BTTS; explicit asymmetry statement naming the dominating side and responsible driving feature per outcome; per-team coverage (match count and populated-vs-absent rich fields)
    - EV section: present a distinct labelled EV section only for Per_Side_Priced_Markets (team corners, team total goals, team shots on target) from Priced_Books — bet365 for Championship fixtures, and BOTH bet365 and betmgm-uk for EPL fixtures presented per book unblended; present team cards without a per-side EV and state no per-side price is available (team-cards EV only via the derived total-cards market where priced); reuse `src/research/ev_calculator.py`
    - Append the mandatory caveat to every output including reduced-coverage and error outputs
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11, 9.12, 9.16, 15.1, 15.2, 15.3, 15.4, 15.5, 15.7_
  - [x]* 11.4 Write property test for mandatory caveat on every output
    - **Property 20: Mandatory caveat on every output** — success, reduced-coverage, unrecognised, ambiguous, no-fixture, zero-history, and cap-exceeded outputs all contain the mandatory caveat
    - **Validates: Requirements 9.12**
    - `# Feature: asymmetric-matchup-engine, Property 20: ...`, `@settings(max_examples=100)`
    - _Requirements: 9.12_
  - [x]* 11.5 Write property test for reject-without-predictions on bad resolution
    - **Property 21: Reject-without-predictions on bad resolution** — unrecognised, ambiguous, or no-fixture invocations produce no predictions and identify the offending input
    - **Validates: Requirements 9.13, 9.14, 9.15**
    - `# Feature: asymmetric-matchup-engine, Property 21: ...`, `@settings(max_examples=100)`
    - _Requirements: 9.13, 9.14, 9.15_
  - [x]* 11.6 Write property test for live-fetch spend cap
    - **Property 22: Live-fetch spend cap** — cumulative admitted spend never exceeds the cap; a breaching fetch is refused and sets `cap_exceeded`; reported `spend_units` equals sum of admitted costs
    - **Validates: Requirements 12.4**
    - Uses the `fetch_cost_sequences` strategy; `# Feature: asymmetric-matchup-engine, Property 22: ...`, `@settings(max_examples=100)`
    - _Requirements: 12.4_
  - [x]* 11.7 Write unit/edge tests for CLI narrative and coverage branches
    - Assert narrative sections present on a resolved cached fixture (9.2–9.6); EV section distinct and labelled when odds exist (9.9); coverage branches at exactly 0 and 5 matches (9.7, 9.8)
    - _Requirements: 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9_
  - [x] 11.8 Commit and push the CLI
    - Commit `resolution.py`, `live_fetch.py`, `scripts/asymmetric_analyze.py`, and tests; push. No shared-config change
    - _Requirements: 14.1_
  - [x] 11.9 Implement audit-grounded EV_Layer book/market coverage in the CLI EV section
    - Map league→books (Championship→[bet365]; EPL→[bet365, betmgm-uk]); compute per-side EV only for Per_Side_Priced_Markets from those books; present each EPL book separately (unblended); omit and record when a book does not price a requested market; never compute per-side EV for team cards
    - Reuse `src/research/ev_calculator.py`
    - _Requirements: 9.9, 9.10, 9.11, 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7_
  - [x]* 11.10 Write property test for audit-grounded per-side EV coverage
    - **Property 24: Audit-grounded per-side EV coverage** — EV computed iff market is a Per_Side_Priced_Market and a Priced_Book prices it for that league; team cards never gets per-side EV; Championship uses bet365 only; EPL priced by both books presents both separately
    - **Validates: Requirements 9.9, 9.10, 9.11, 15**
    - `# Feature: asymmetric-matchup-engine, Property 24: ...`, `@settings(max_examples=100)`
    - _Requirements: 9.9, 9.10, 9.11, 15_

- [ ] 12. Add hypothesis dev dependency and finalize property-test suite
  - [~] 12.1 Add `hypothesis` as a dev dependency and flag the shared-config change
    - Add `hypothesis==6.*` to `[project.optional-dependencies].dev` in `pyproject.toml`; add the custom strategies module (`match_histories`, `count_pmfs`, `fixture_contexts`, `estimates`, `fetch_cost_sequences`) under `tests/asymmetric/`
    - Commit and push; **flag this as a shared/global configuration change** per Req 14.2 in the commit message
    - _Requirements: 14.1, 14.2_

- [ ] 13. Dual-corpus wiring and end-to-end run
  - [~] 13.1 Wire the full build/backtest pipeline across both corpora
    - Connect Loaders → Team_Profiler (full for Rich, reduced for Broad) → Feature_Verification_Gate → Sanity_Gate → Interaction_Model → Per_Side predictions → Derived_Outcome combiner + correlation check → AsymmetryEvaluator (fresh FDR) → Reporting, using `src/research/models/factory.py` extended with asymmetric per-side entries; ensure the build/backtest path never imports `live_fetch.py`
    - Produce the final report: per-side-vs-baseline (per market/league), rich-vs-broad comparison, ECE/reliability per target, FDR family size, and CIs on every estimate
    - _Requirements: 4.1, 4.2, 4.4, 4.5, 10.1, 10.2, 10.4, 10.5, 10.7, 10.8, 13.1, 13.4_
  - [ ]* 13.2 Write the zero-API build/backtest assertion test
    - Inject an API client stub that raises on any call and run a small end-to-end build/backtest slice, asserting the live client is never invoked (complements Property 23)
    - _Requirements: 12.1, 12.2_
  - [ ]* 13.3 Write end-to-end integration tests on a small cached slice
    - Verify walk-forward BSS/Brier/ECE reporting via `CalibrationEvaluator`, fresh FDR family construction + BH correction via `FDRAdapter`, and the rich-vs-broad comparison (1–3 representative examples)
    - _Requirements: 4.4, 4.5, 8.9, 10.4, 10.5_
  - [~] 13.4 Commit and push the wired pipeline
    - Commit the wiring and end-to-end tests; push. No shared-config change
    - _Requirements: 14.1_

- [~] 14. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Sub-tasks marked with `*` are optional test tasks and can be skipped for a faster MVP; core implementation sub-tasks are never optional.
- Implementation language is Python (pydantic v2, scipy, `hypothesis`, `pytest`), fixed by the design; no language selection was required.
- Each of the 24 correctness properties is implemented by exactly one property-based test, tagged `# Feature: asymmetric-matchup-engine, Property N: ...` with a minimum of 100 examples, grouped alongside the component it validates.
- The only shared-config change is adding `hypothesis` to the dev extra in `pyproject.toml` (task 12.1), flagged per Req 14.2. All other commits touch only the new isolated package, the CLI, and its tests.
- The build/backtest path is strictly zero-API (Property 23 + task 13.2); the live fetcher is confined to the CLI package with a spend cap (Property 22).
- Point-in-time discipline is enforced by Property 2 and the look-ahead gate check verification (task 8.6).
- Checkpoints (tasks 7 and 14) ensure incremental validation.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["1.3", "2.1", "3.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "3.2"] },
    { "id": 4, "tasks": ["3.3", "3.4", "3.5", "3.6", "3.7"] },
    { "id": 5, "tasks": ["4.1"] },
    { "id": 6, "tasks": ["4.2", "4.3", "4.4", "4.5", "4.6"] },
    { "id": 7, "tasks": ["5.1"] },
    { "id": 8, "tasks": ["5.2", "5.3", "5.4"] },
    { "id": 9, "tasks": ["6.1", "6.2"] },
    { "id": 10, "tasks": ["6.3", "6.4", "6.5"] },
    { "id": 11, "tasks": ["8.1", "8.2"] },
    { "id": 12, "tasks": ["8.3", "8.4", "8.5", "8.6"] },
    { "id": 13, "tasks": ["9.1", "9.2"] },
    { "id": 14, "tasks": ["9.3"] },
    { "id": 15, "tasks": ["9.4", "9.5", "9.6", "9.7", "9.8", "9.9"] },
    { "id": 16, "tasks": ["10.1"] },
    { "id": 17, "tasks": ["10.2", "10.3"] },
    { "id": 18, "tasks": ["11.1", "11.2"] },
    { "id": 19, "tasks": ["11.3", "11.9"] },
    { "id": 20, "tasks": ["11.4", "11.5", "11.6", "11.7", "11.10"] },
    { "id": 21, "tasks": ["12.1"] },
    { "id": 22, "tasks": ["13.1"] },
    { "id": 23, "tasks": ["13.2", "13.3"] }
  ]
}
```
