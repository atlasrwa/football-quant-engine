# Requirements Document

## Introduction

The Asymmetric Matchup Engine is a per-side football matchup prediction system that treats a match as an asymmetric interaction between two team profiles rather than a single aggregate total. Existing models predict match totals (e.g. over 9.5 corners) and average away the on-pitch interaction between the two teams. This feature instead builds, for a single fixture, an expectation of what each team is expected to produce and to concede across every modelled outcome, with the driving mechanism made visible and interpretable.

The engine targets team-specific markets (per-side corners, cards, goals, shots on target), which are thinner and less sharply priced than aggregate markets. It derives match-level outcomes (total corners, total cards, total goals, both-teams-to-score, clean sheet per side) from the per-side predictions rather than modelling them directly. It builds continuous, team-identity-keyed, point-in-time team profiles; models two interaction directions separately as distinct hypotheses; respects an empirically measured near-zero cross-market correlation structure; runs across a rich corpus and a broad corpus for comparison; enforces mandatory team-level shrinkage and elastic-net regularization; passes a five-check feature verification gate and a sanity gate before any modelling; and subjects every per-side target to a decisive asymmetry-vs-marginal-baseline test with within-league significance and a fresh multiple-testing correction. It ships an on-demand fixture CLI that reads as a matchup narrative backed by numbers, always carrying a mandatory caveat that a single fixture demonstrates nothing about edge and that the model has not beaten market prices in systematic testing.

This effort is deliberately isolated from prior efforts (Pilot C, Pipeline A, manual work, flagged ledgers) and MUST NOT inherit their multiple-testing families, feature selections, or results. It lives inside the existing Python football quant engine at /home/ubuntu, reusing src/features/, src/research/, and the cached corpora, and adds a new analysis CLI at scripts/asymmetric_analyze.py. Zero API requests are permitted during build or backtest; all data is served from cache. The on-demand fixture tool may make live API requests to fetch fixture or team data that is not cached, capped and reported; build and backtest remain strictly zero-API. A coverage audit (docs/coverage_matrix.md) established which per-side markets are priced and by which books; the expected-value layer targets bet365 for Championship and both bet365 and betmgm-uk for EPL, covers per-side corners, goals, and shots on target (team cards is not priced anywhere), and referee assignment is not available pre-match in either source, so cards conditioning uses the league-level card rate as the primary pre-match path.

## Glossary

- **Engine**: The Asymmetric Matchup Engine, the complete per-side matchup prediction system described by this document.
- **Fixture**: A single scheduled or historical match between a home team and an away team on a given date.
- **Team_Profiler**: The component that builds continuous feature-vector profiles for a team from rolling and expanding raw statistics.
- **Attacking_Profile**: A team's continuous feature vector describing how it attacks (width, central penetration, volume vs quality, set-piece reliance, directness).
- **Defensive_Profile**: A team's continuous feature vector describing how it defends (block orientation, aerial vs ground, shot suppression, goalkeeper contribution, discipline).
- **Interaction_Model**: The component that models a single direction of a fixture (one team's attack against the opponent's defence) to predict per-side outcomes.
- **Direction**: One asymmetric half of a fixture: either A-attack against B-defence, or B-attack against A-defence. A Fixture has exactly two Directions.
- **Per_Side_Target**: A modelled outcome for one side in one Direction: corners won, cards, goals, or shots on target (SOT).
- **Derived_Outcome**: A match-level outcome computed from per-side predictions: total corners, total cards, total goals, both-teams-to-score (BTTS), or clean sheet per side.
- **Symmetric_Baseline**: A comparison model that uses the same modelling family without the interaction layer, predicting a Per_Side_Target from only that team's own marginal rate.
- **Correlation_Structure**: The empirically measured cross-market correlations on the broad corpus: cards×corners -0.033, cards×goals -0.030, corners×goals -0.028 (95% CI approximately ±0.016).
- **Rich_Corpus**: The cached approximately 3,189-match corpus (Championship, La Liga 2, Ligue 2, plus 99 EPL matches) requiring TheStatsAPI fields, located under /home/ubuntu/data/thestatsapi/.
- **Broad_Corpus**: The cached FootyStats corpus of approximately 15,362 matches with core fields only, supporting a reduced profile across more leagues.
- **Feature_Verification_Gate**: A mandatory pre-modelling gate of five checks: team-identity trace, known-signal check, orientation check, look-ahead check, and shuffle-null check.
- **Sanity_Gate**: A mandatory pre-search gate that records known structural results per league and per target.
- **FDR_Family**: The multiple-testing family for this Engine, counting every target×direction×league model tested, created fresh and never inherited from prior efforts.
- **Analysis_CLI**: The on-demand fixture command-line tool at scripts/asymmetric_analyze.py.
- **Point_In_Time**: A discipline in which every feature value used for a Fixture is computed only from information available strictly before that Fixture, with no incorporation of the target match or any later match.
- **BSS**: Brier Skill Score, measured against a naive baseline.
- **Brier**: The Brier score for probabilistic predictions.
- **ECE**: Expected Calibration Error.
- **CI**: Confidence interval.
- **Prior_Efforts**: Pilot C, Pipeline A, manual work, and flagged ledgers, which are separate from this Engine and MUST NOT be inherited.
- **EV_Layer**: The expected-value comparison layer of the Analysis_CLI that compares model per-side and derived predictions against real book prices; a layer separate from prediction and mechanism.
- **Priced_Books**: The bookmakers confirmed by the coverage audit to price per-side (team-specific) stat markets: bet365 (Championship and EPL) and betmgm-uk (EPL). betmgm-uk did not price the sampled Championship fixtures.
- **Per_Side_Priced_Markets**: The per-side stat markets confirmed available for expected-value testing: team corners, team total goals, and team shots on target. Team cards is NOT priced by any book and cannot be EV-tested per side.

## Requirements

### Requirement 1: Team Profiling

**User Story:** As a football quant researcher, I want each team represented by continuous attacking and defensive profiles built point-in-time from raw statistics, so that the Engine generalises across similar team shapes instead of memorising team identities.

#### Acceptance Criteria

1. THE Team_Profiler SHALL build for each team exactly two profiles: one Attacking_Profile and one Defensive_Profile.
2. THE Team_Profiler SHALL represent every Attacking_Profile and every Defensive_Profile as a continuous feature vector.
3. THE Team_Profiler SHALL exclude team identities and discrete team labels from every Attacking_Profile and every Defensive_Profile.
4. THE Team_Profiler SHALL compute every profile feature under the Point_In_Time discipline from a rolling window of the most recent ten completed matches, and SHALL fall back to an expanding window when fewer than ten completed matches are available.
5. THE Team_Profiler SHALL key every profile computation on team identity across the team's matches, including both home and away matches, and SHALL NOT key any profile computation on fixture slot.
6. THE Attacking_Profile SHALL include width features derived from accurate crosses, wide entries, and corners won.
7. THE Attacking_Profile SHALL include central penetration features derived from touches in the penalty area, final third entries, and shots inside the box.
8. THE Attacking_Profile SHALL include volume-versus-quality features derived from total shots, shots on target, big chances, and npxG per shot.
9. THE Attacking_Profile SHALL include set-piece reliance features derived from corners won and fouls won in advanced areas.
10. THE Attacking_Profile SHALL include directness features derived from the attacks versus dangerous attacks ratio and long balls.
11. THE Defensive_Profile SHALL include block orientation features derived from clearances, interceptions, and tackles.
12. THE Defensive_Profile SHALL include aerial-versus-ground features derived from aerial duel percentage and ground duel percentage.
13. THE Defensive_Profile SHALL include shot suppression features derived from shots conceded inside the box, shots conceded outside the box, and blocked shots.
14. THE Defensive_Profile SHALL include goalkeeper contribution features derived from saves, goals prevented versus expected, and high claims (subject to field availability per Requirement 17).
15. THE Defensive_Profile SHALL include discipline features derived from fouls conceded, tackle success, and cards.
16. WHERE a team has fewer than five completed matches of history, THE Team_Profiler SHALL mark that team's Attacking_Profile and Defensive_Profile as insufficient for full-profile modelling.
17. IF a raw field required for a profile feature is unavailable for a match, THEN THE Team_Profiler SHALL exclude that match from the affected feature, compute the feature from the remaining matches, and record which fields were unavailable.
18. THE Team_Profiler SHALL include a team's matches from all leagues in that team's profile computation, keyed on team identity.

### Requirement 2: Interaction and Direction Modelling

**User Story:** As a football quant researcher, I want each fixture modelled as two separate directional interactions between one team's attack and the opponent's defence, so that the asymmetric on-pitch interaction is captured as two distinct hypotheses rather than a single symmetric feature.

#### Acceptance Criteria

1. THE Interaction_Model SHALL model each Fixture as exactly two Directions.
2. THE Interaction_Model SHALL model the A-attack against B-defence Direction and the B-attack against A-defence Direction separately.
3. THE Interaction_Model SHALL NOT collapse the two Directions into a single symmetric feature.
4. FOR each Direction, THE Interaction_Model SHALL predict the side's corners won as a Per_Side_Target represented as a full predictive distribution rather than a point estimate.
5. FOR each Direction, THE Interaction_Model SHALL predict the side's goals as a Per_Side_Target represented as a full predictive distribution rather than a point estimate.
6. FOR each Direction, THE Interaction_Model SHALL predict the side's shots on target as a Per_Side_Target represented as a full predictive distribution rather than a point estimate.
7. FOR each Direction, THE Interaction_Model SHALL predict the side's cards as a Per_Side_Target represented as a full predictive distribution rather than a point estimate, conditioned on the referee expanding-window card rate.
8. FOR each Per_Side_Target, THE Interaction_Model SHALL derive predictions from named driving features evaluated against the opponent's profile dimensions.
9. THE Engine SHALL derive total corners, total cards, total goals, both-teams-to-score, and clean sheet per side as Derived_Outcomes computed by combining the two Directions' Per_Side_Target predictive distributions under the independence assumption stated in Requirement 3.
10. THE Engine SHALL treat Per_Side_Targets as the primary modelled outputs and SHALL NOT model any Derived_Outcome directly.
11. IF the referee assignment for a Fixture is missing, THEN THE Interaction_Model SHALL condition the cards Per_Side_Target on a league-level expanding-window card rate in place of the referee expanding-window card rate, and SHALL flag that the referee-specific conditioning was substituted.

### Requirement 3: Correlation Structure Respect

**User Story:** As a football quant researcher, I want the Engine to respect the empirically measured near-zero cross-market correlation structure, so that derived joint outcomes remain consistent with reality and any deviation is surfaced rather than smoothed over.

#### Acceptance Criteria

1. WHERE the Engine produces a joint or derived outcome, THE Engine SHALL state the independence assumption used to produce that outcome.
2. WHEN the Engine produces a Derived_Outcome, THE Engine SHALL compute the correlation implied by the per-side model and compare it against the measured Correlation_Structure.
3. IF a per-side model implies a correlation that differs materially from the measured Correlation_Structure, THEN THE Engine SHALL report the difference as a red flag.
4. THE Engine SHALL report the measured Correlation_Structure values and their 95% CI alongside any correlation comparison.

### Requirement 4: Dual-Corpus Data Handling

**User Story:** As a football quant researcher, I want the Engine to run against both the rich corpus and the broad corpus and report both, so that I can tell whether the rich fields earn their keep at the profile level.

#### Acceptance Criteria

1. THE Engine SHALL use the Rich_Corpus as the primary data source for full-profile modelling.
2. THE Engine SHALL use the Broad_Corpus as the secondary data source for reduced-profile modelling.
3. WHERE the Broad_Corpus is used, THE Team_Profiler SHALL build a reduced profile that derives width from corners, directness from the attacks versus dangerous attacks ratio, and discipline from fouls and cards.
4. THE Engine SHALL report results from the Rich_Corpus and results from the Broad_Corpus.
5. THE Engine SHALL report a comparison between Rich_Corpus results and Broad_Corpus results that indicates whether the rich fields improve profile-level performance.

### Requirement 5: Model, Shrinkage, and Regularization

**User Story:** As a football quant researcher, I want count models with mandatory team-level shrinkage and elastic-net regularization, so that predictions avoid the tail overconfidence seen when shrinkage was omitted and avoid arbitrary dropping of correlated features.

#### Acceptance Criteria

1. THE Engine SHALL model count Per_Side_Targets using a Poisson or negative-binomial model with team-level shrinkage.
2. THE Engine SHALL model binary Derived_Outcomes using a logistic model.
3. THE Engine SHALL check count-model dispersion empirically and report the dispersion result.
4. THE Engine SHALL apply regularization to every model.
5. THE Engine SHALL use elastic-net regularization in preference to pure L1 regularization.
6. THE Engine SHALL include a team-level shrinkage layer of the form n/(n+k) in every count model.
7. THE Engine SHALL report calibration of tail predictions against realised outcomes.

### Requirement 6: Feature Verification Gate

**User Story:** As a football quant researcher, I want a five-check feature verification gate that runs and reports before any modelling, so that mis-keyed, look-ahead, or mis-oriented features are caught before they corrupt results.

#### Acceptance Criteria

1. THE Engine SHALL run the Feature_Verification_Gate before performing any modelling.
2. THE Engine SHALL run a team-identity trace check that confirms rolling features aggregate the correct team's matches across both home and away matches, and SHALL print the trace for between three and five teams.
3. THE Engine SHALL run a known-signal check that confirms the xG-to-goals association is approximately 0.10 or greater rather than approximately 0.00, and confirms rolling goals to goals is positive.
4. THE Engine SHALL run an orientation check that confirms team_a features align with team_a outcomes and verifies the alignment against the source data.
5. THE Engine SHALL run a look-ahead check that confirms no feature incorporates the target match or any later match.
6. THE Engine SHALL run a shuffle-null check that confirms a permuted feature-to-outcome mapping collapses to chance performance.
7. THE Engine SHALL report the result of every Feature_Verification_Gate check.
8. IF any Feature_Verification_Gate check fails, THEN THE Engine SHALL stop before modelling and report the failure.

### Requirement 7: Sanity Gate

**User Story:** As a football quant researcher, I want a sanity gate that records known structural results per league and per target before searching, so that the Engine does not waste effort re-diagnosing already-known non-signals.

#### Acceptance Criteria

1. THE Engine SHALL run the Sanity_Gate for each league and each target before searching for signal.
2. THE Sanity_Gate SHALL record that corners has near-zero team-level persistence at rolling-window timescales.
3. THE Sanity_Gate SHALL record that cards disciplinary persistence is absent in the Championship across three seasons.
4. THE Engine SHALL report the recorded Sanity_Gate structural results and SHALL NOT re-diagnose them.

### Requirement 8: Decisive Asymmetry-versus-Marginal Test

**User Story:** As a football quant researcher, I want every per-side target compared against a symmetric marginal baseline with within-league significance and a fresh multiple-testing family, so that a genuine asymmetry finding is distinguished from a pooled-only artifact.

#### Acceptance Criteria

1. FOR each Per_Side_Target, THE Engine SHALL compare the Interaction_Model against a Symmetric_Baseline that uses only the team's own marginal rate.
2. THE Engine SHALL evaluate the Interaction_Model versus Symmetric_Baseline comparison out-of-sample using held-out cross-validation folds, where no fixture used to fit a model contributes to that model's evaluation score.
3. IF the Interaction_Model's out-of-sample BSS improvement over the Symmetric_Baseline for a Per_Side_Target is not strictly positive with a 95% confidence interval lower bound greater than zero, THEN THE Engine SHALL report that the asymmetry hypothesis fails for that Per_Side_Target.
4. THE Engine SHALL report the Interaction_Model versus Symmetric_Baseline comparison per market and per league.
5. THE Engine SHALL NOT report Interaction_Model performance in isolation from the Symmetric_Baseline comparison.
6. THE Engine SHALL require, for any asymmetry finding, that the within-league Interaction_Model versus Symmetric_Baseline BSS improvement is statistically significant at a significance level of 0.05.
7. WHERE a result is statistically significant at the 0.05 level only when leagues are pooled and is not significant at the 0.05 level within its own league, THE Engine SHALL report the result as an artifact rather than a finding.
8. THE Engine SHALL construct a fresh FDR_Family that counts every target×direction×league model tested.
9. THE Engine SHALL report the FDR_Family size and SHALL correct the within-league significance results against it using Benjamini-Hochberg false discovery rate control at a false discovery rate of 0.05.
10. THE Engine SHALL NOT inherit any multiple-testing family from Prior_Efforts.
11. IF a league has fewer matches than the minimum required to compute a within-league significance test for a Per_Side_Target, THEN THE Engine SHALL exclude that league-target combination from any asymmetry finding and SHALL report it as insufficient-sample rather than as a finding or an artifact.

### Requirement 9: On-Demand Fixture CLI

**User Story:** As a football analyst, I want an on-demand CLI that produces a matchup narrative backed by numbers for a single fixture, so that I can read what each team is expected to produce and concede and understand the mechanism.

#### Acceptance Criteria

1. THE Analysis_CLI SHALL accept a home team name, an away team name, and a date in ISO 8601 (YYYY-MM-DD) format as input, following the invocation pattern `python scripts/asymmetric_analyze.py --home "Leeds" --away "Norwich" --date 2026-09-05`.
2. WHEN each of the home team, away team, and date resolves to exactly one recognised team and one scheduled Fixture, THE Analysis_CLI SHALL present each team's Attacking_Profile and Defensive_Profile as named feature dimensions each accompanied by its underlying numeric value.
3. WHEN a Fixture is resolved, THE Analysis_CLI SHALL present, for each team, the Per_Side_Target predictions for corners won, cards, goals, and shots on target, each accompanied by the named driving features used to derive it.
4. WHEN a Fixture is resolved, THE Analysis_CLI SHALL present the Derived_Outcomes for total corners, total cards, total goals, and both-teams-to-score.
5. WHEN a Fixture is resolved, THE Analysis_CLI SHALL state the asymmetry explicitly by naming, for each of total corners, total cards, total goals, and both-teams-to-score, which side dominates the outcome and the named driving feature responsible.
6. WHEN a Fixture is resolved, THE Analysis_CLI SHALL report, per team, the count of matches of history available and the list of rich fields that are populated versus absent.
7. IF a team has fewer than the minimum match count required for a full Attacking_Profile and Defensive_Profile but at least one match of history, THEN THE Analysis_CLI SHALL flag that team as reduced-coverage, state its match count against the required minimum, and continue producing output using the reduced profile.
8. IF a team has zero matches of cached history, THEN THE Analysis_CLI SHALL report that no profile can be produced for that team, identify the affected team, and terminate without producing Per_Side_Target or Derived_Outcome predictions.
9. WHERE odds are available for a Fixture from a Priced_Book, THE Analysis_CLI SHALL present, per Per_Side_Priced_Market and per Derived_Outcome, the model value alongside the market-implied value and the resulting expected value as a distinct labelled EV_Layer section separate from the prediction and mechanism sections.
10. THE Analysis_CLI SHALL source per-side expected-value comparisons from bet365 for Championship fixtures and from both bet365 and betmgm-uk for EPL fixtures.
11. WHERE a Per_Side_Target has no priced market in any Priced_Book, in particular team cards, THE Analysis_CLI SHALL present the model prediction without an expected-value comparison for that Per_Side_Target and SHALL state that no per-side price is available for it.
12. THE Analysis_CLI SHALL include on every output, including reduced-coverage and error outputs, a caveat stating that a single Fixture demonstrates nothing about edge and that the Engine has not beaten market prices in systematic testing.
13. IF a supplied team name does not resolve to any recognised team, THEN THE Analysis_CLI SHALL reject the invocation with an indication identifying the unrecognised name and SHALL NOT produce predictions.
14. IF a supplied team name resolves to more than one recognised team, THEN THE Analysis_CLI SHALL reject the invocation with an indication identifying the ambiguous name and the candidate matches, and SHALL NOT produce predictions.
15. IF no Fixture between the supplied home and away teams is scheduled on the supplied date, THEN THE Analysis_CLI SHALL report that no matching Fixture was found for the supplied teams and date and SHALL NOT produce predictions.
16. WHEN required fixture or team data for the requested Fixture is absent from the cached corpora, THE Analysis_CLI SHALL fetch the missing data via live API requests before producing predictions, subject to the spend cap defined in Requirement 12.

### Requirement 10: Reporting and Calibration

**User Story:** As a football quant researcher, I want complete headline reporting with calibration, interpretable coefficients, and confidence intervals, so that I can judge the Engine honestly without post-hoc selection.

#### Acceptance Criteria

1. THE Engine SHALL report headline per-side model performance versus the Symmetric_Baseline, per market and per league.
2. THE Engine SHALL report the Rich_Corpus versus Broad_Corpus comparison.
3. THE Engine SHALL report which profile dimensions carry weight using readable elastic-net coefficients.
4. THE Engine SHALL report calibration per target using ECE and reliability curves.
5. THE Engine SHALL report out-of-sample BSS versus a naive baseline, Brier, and ECE.
6. THE Engine SHALL report all results, including failures, and SHALL NOT apply post-hoc selection.
7. THE Engine SHALL report the fresh FDR_Family size.
8. THE Engine SHALL report a CI for every reported estimate.
9. WHERE a point estimate has a CI that spans zero, THE Engine SHALL report that estimate as not constituting a result.

### Requirement 11: Point-in-Time Discipline (Non-Functional)

**User Story:** As a football quant researcher, I want absolute point-in-time discipline throughout the Engine, so that no feature ever leaks information from the target match or later, which previously invalidated a run.

#### Acceptance Criteria

1. THE Engine SHALL compute every feature under the Point_In_Time discipline throughout profiling, interaction modelling, and validation.
2. THE Engine SHALL perform validation using walk-forward evaluation.
3. THE Engine SHALL exclude the target match and any later match from every feature value used to predict that match.
4. THE Engine SHALL key every point-in-time computation on team identity rather than fixture slot.

### Requirement 12: Zero-API-During-Backtest (Non-Functional)

**User Story:** As a football quant researcher, I want zero API usage during build and backtest with any on-demand spend capped and reported, so that reproducible offline work never incurs cost and live spend stays controlled and visible.

#### Acceptance Criteria

1. THE Engine SHALL serve all data for build and backtest from the cached corpora.
2. THE Engine SHALL make zero API requests during build and backtest.
3. WHERE the Analysis_CLI requires fixture or team data that is not present in the cached corpora, THE Analysis_CLI SHALL make live API requests to fetch the missing data.
4. WHERE the Analysis_CLI makes live API requests, THE Analysis_CLI SHALL enforce a cap on spend and SHALL report the spend incurred.

### Requirement 13: Reproducibility and Isolation (Non-Functional)

**User Story:** As a football quant researcher, I want the Engine reproducible and fully isolated from prior efforts, so that its results stand on their own and are not contaminated by inherited artifacts.

#### Acceptance Criteria

1. THE Engine SHALL produce reproducible results from the cached corpora.
2. THE Engine SHALL remain separate from Pilot C, Pipeline A, manual work, and flagged ledgers.
3. THE Engine SHALL NOT inherit feature selections, multiple-testing families, or results from Prior_Efforts.
4. THE Engine SHALL integrate with the existing engine at /home/ubuntu, reusing src/features/ and src/research/, and SHALL add the Analysis_CLI at scripts/asymmetric_analyze.py.

### Requirement 14: Version Control and Config-Change Flagging (Non-Functional)

**User Story:** As a football quant researcher, I want work committed and pushed with any shared or global config change flagged, so that changes are tracked and side effects on shared configuration are visible.

#### Acceptance Criteria

1. WHEN a unit of work is complete, THE Engine SHALL commit the change and push it.
2. IF a change modifies shared or global configuration, THEN THE Engine SHALL flag the configuration change.

### Requirement 15: EV Layer Book and Market Coverage (Audit-Grounded)

**User Story:** As a football quant researcher, I want the expected-value layer to reflect the coverage audit's verified book and market availability, so that EV comparisons are only made where real per-side prices exist and their limits are stated plainly.

#### Acceptance Criteria

1. THE EV_Layer SHALL compute per-side expected value only for Per_Side_Priced_Markets and only from Priced_Books.
2. THE EV_Layer SHALL use bet365 as the per-side price source for Championship Fixtures.
3. THE EV_Layer SHALL use both bet365 and betmgm-uk as per-side price sources for EPL Fixtures.
4. WHERE both bet365 and betmgm-uk price the same Per_Side_Priced_Market for an EPL Fixture, THE EV_Layer SHALL present each book's market-implied value and expected value separately rather than blending them.
5. THE EV_Layer SHALL NOT compute a per-side expected value for team cards, and SHALL state that team cards has no per-side price in any Priced_Book.
6. WHERE a Priced_Book does not price a requested Per_Side_Priced_Market for a given league, THE EV_Layer SHALL omit the expected-value comparison for that book and market and SHALL record the omission.
7. THE Engine SHALL continue to derive and report match-total expected value for team cards from the Derived_Outcome total cards market where such a total market is priced.

### Requirement 16: Referee Data Availability Constraint (Audit-Grounded)

**User Story:** As a football quant researcher, I want the cards conditioning to reflect that referee assignment is unavailable pre-match, so that predictions are honest about the referee signal actually usable before kickoff.

#### Acceptance Criteria

1. THE Engine SHALL treat the league-level expanding-window card rate as the primary pre-match conditioning signal for the cards Per_Side_Target.
2. WHERE a referee-specific expanding-window card rate is used, THE Engine SHALL restrict that use to backtest evaluation on completed Fixtures with a known post-match referee identifier.
3. THE Analysis_CLI SHALL NOT condition a pre-match cards prediction on a referee-specific card rate, because referee assignment is not available pre-match from either data source.
4. WHERE the cards Per_Side_Target is conditioned on the league-level card rate in place of a referee-specific rate, THE Engine SHALL flag that the league-level substitution was used.

### Requirement 17: Goalkeeper Dimension Availability (Audit-Grounded)

**User Story:** As a football quant researcher, I want the goalkeeper profile dimension to reflect that goals-prevented is unpopulated, so that the dimension is built only from fields that exist.

#### Acceptance Criteria

1. THE Team_Profiler SHALL build the goalkeeper contribution feature of the Defensive_Profile from saves, and SHALL NOT require goals prevented versus expected, which the coverage audit found to be zero-populated across the Rich_Corpus leagues.
2. WHERE goals prevented versus expected is unavailable for a league, THE Team_Profiler SHALL compute the goalkeeper contribution feature from the available goalkeeper fields and SHALL record that goals prevented was unavailable.
3. WHERE the touches-in-penalty-area field is thin for a league, in particular the Championship, THE Team_Profiler SHALL flag the central penetration feature as reduced-confidence for that league.
