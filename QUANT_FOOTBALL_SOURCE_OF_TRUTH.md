# Quant Football Engine — Source of Truth V2

Decision date: 2026-10-01 (America/Bogota)

Status: **GOVERNING ARCHITECTURE FOR ALL FUTURE QFE DEVELOPMENT.**

This document supersedes the 2026-09-27 / 2026-09-29 source-of-truth direction for future work. Historical experiments, freezes, manifests, results and commits remain immutable evidence and must not be rewritten to conform to this architecture.

## 1. Mission

Quant Football Engine is now a **deterministic, market-disagreement-focused probabilistic football engine**.

Its technical mission is to produce independent football probabilities that are:
- point-in-time safe;
- strongly calibrated;
- competitive on out-of-sample log loss;
- competitive on Brier score;
- distributionally coherent;
- robust across time and competitions;
- explicit about uncertainty and unsupported cases.

Its research/commercial mission is to identify where those trustworthy probabilities **materially and credibly disagree** with contemporaneous no-vig market probabilities.

Market disagreement remains a first-class goal. However, QFE must never maximize disagreement directly. A larger model-market gap is not evidence of better forecasting or market value.

The governing principle is:

> **Build the best independent probability forecast first. Then search for credible market disagreement.**
## 2. No LLM in the successor engine

The successor QFE architecture does **not** use an LLM in the probability path, hypothesis path, feature path, calibration path, selection path or production path.

No LLM may:
- generate p_model;
- propose numerical probability adjustments;
- generate similarity scores;
- select fixtures because they “look good”;
- create latent matchup scores;
- decide market-disagreement eligibility;
- change calibration;
- choose model weights.

Historical LLM experiments remain valid historical research records. They are not deleted or relabeled. They no longer govern future engine development.

Future QFE research under this source of truth is deterministic/statistical unless this document is explicitly versioned by a later architectural decision.

## 3. Core architecture

The required future pipeline is:

Historical football evidence from verified providers
→ target and provider semantic contracts
→ point-in-time feature reconstruction
→ dynamic latent team/opponent strengths
→ multiple complementary deterministic/statistical model families
→ chronological out-of-fold predictions
→ regularized ensemble
→ dedicated calibration layer
→ frozen independent `p_model`
→ timestamp-matched sportsbook prices
→ no-vig market probability
→ deterministic market-disagreement detector
→ support / uncertainty / domain gates
→ prospective immutable prediction
→ genuine closing-line comparison
→ settlement and evaluation.

The independent football model must remain **odds-blind**. Sportsbook prices enter only after `p_model` is frozen for the relevant decision horizon.

A secondary market-adjusted research model may combine market probability with QFE information solely to test whether QFE adds incremental information beyond the market. It must remain separate from the independent `p_model`.
## 4. Primary optimization objective

Model fitting and model selection must prioritize **future probability quality**, not hit rate, retrospective ROI or disagreement size.

Primary predictive metric:
- chronological out-of-sample **log loss**.

Required supporting metrics:
- Brier score;
- calibration intercept;
- calibration slope;
- reliability curves;
- probability-region support;
- coverage and missingness;
- count-distribution diagnostics where applicable.

Hit rate may be reported later as descriptive commercial context. It is not a model-selection objective.

A model that produces more +10 pp or +20 pp disagreements but worsens log loss or calibration is not an improvement.

## 5. Market-disagreement objective

After a calibrated `p_model` is frozen, compare it with a contemporaneous no-vig market probability `p_market`.

For a binary event:

`disagreement_pp = 100 * (p_model - p_market)`

The sign identifies the side on which QFE is more optimistic than the market.

The detector must not rank opportunities by disagreement magnitude alone. Eligibility must consider deterministic evidence such as:
- calibration quality in the relevant probability region;
- historical OOS support;
- component-model consensus / dispersion;
- training-domain similarity;
- sample depth;
- missingness;
- competition/provider coverage;
- target semantics;
- decision-horizon integrity.

The system must be able to abstain with an explicit unsupported or low-support state instead of forcing a signal.
## 6. Provider policy

TheStatsAPI is the primary candidate evidence provider for the successor architecture where its coverage and semantics are verified.

FootyStats or another provider may be used only under a provider-scoped capability contract. Similarly named fields must never be assumed equivalent across providers.

Before modeling, maintain a provider capability registry containing, at minimum:
- raw provider/path;
- field name;
- interpreted definition;
- unit;
- period;
- side semantics;
- missing-value semantics;
- competition coverage;
- historical depth;
- provenance;
- eligibility for pre-match modeling.

No implicit blending is allowed.

Missing is not zero.

Unsupported evidence produces an explicit unsupported state; do not manufacture proxies merely to preserve coverage.

## 7. Target contract

Each family × side × period × market definition requires its own target contract.

Initial families:
- goals: home, away, match total;
- corners: home, away, match total;
- bookings/cards: home, away, match total, only after provider/bookmaker settlement semantics are reconciled.

Targets must specify:
- regulation versus extra time;
- push/void behavior where applicable;
- side and period;
- line semantics;
- settlement rules;
- card treatment for bookings markets.

A provider-native card count is not automatically a bookmaker bookings label.
## 8. Point-in-time dataset construction

For every historical fixture at time `t`, reconstruct only information available strictly before the prediction timestamp for that fixture.

All of the following must be fitted or calculated from eligible earlier data only:
- rolling/decayed features;
- opponent adjustments;
- competition priors;
- latent strengths;
- feature scaling;
- imputation;
- similarity spaces;
- dimensionality reduction;
- model hyperparameters;
- ensemble weights;
- calibration mappings.

A historical match's own post-match shots, corners, cards, goals or xG can never predict that same match pre-match.

Future matches may never influence past feature values.

Retrospective availability that cannot be proven point-in-time must be labelled as reconstructed and may not be represented as originally timestamped evidence.

## 9. Decision horizons

Evaluation must be horizon matched.

A QFE probability created at T-24h must be compared with a market snapshot from the same registered horizon or an explicitly defined tolerance window, not with a near-kickoff market and then treated as an equal-information comparison.

Every prediction must bind:
- fixture ID;
- kickoff;
- prediction timestamp;
- decision horizon;
- feature version;
- model version;
- ensemble version;
- calibration version;
- provider provenance.

Different horizons are separate evaluation problems.
## 10. Dynamic latent team strength

Raw W5/W10 averages are observations, not true team ability.

The successor engine should estimate evolving latent states such as:
- goal attack strength;
- goal defensive strength;
- corner-generation strength;
- corner-concession strength;
- booking propensity;
- opponent booking pressure;
- other target-specific states justified by evidence.

These states should be:
- time varying;
- opponent adjusted;
- venue aware where supported;
- partially pooled;
- uncertainty aware where feasible;
- shrunk toward competition/global priors when evidence is sparse.

Recent information may move latent strength, but small samples must not dominate it.

## 11. Hierarchical shrinkage

Use partial pooling wherever sparse group estimates would otherwise become unstable.

Conceptual hierarchy may include:

global → family → competition → team → current team state.

Promoted teams, new competitions, short histories and rare contexts require stronger shrinkage than mature, well-observed entities.

The purpose is to reduce probability inflation caused by noise while preserving real, well-supported differences.

## 12. Complementary model families

Do not search for one magical model. Maintain deliberately different model families and let out-of-sample evidence determine their value.

At minimum investigate:

1. **Structured count model**
   - Poisson as a baseline, not a dogma;
   - dynamic attack/defence structure;
   - Dixon-Coles/bivariate/dependence extensions for goals where justified;
   - negative-binomial or other dispersion-aware count models for corners/cards where justified;
   - coherent team and total distributions.

2. **Dynamic strength model**
   - state-space, Bayesian updating, decay-weighted hierarchical estimation, or a comparable deterministic approach;
   - selected by chronological OOS evidence.
3. **Nonlinear tabular ML model**
   - e.g. strongly regularized gradient-boosted trees;
   - captures nonlinear interactions among validated pre-match features;
   - must use chronological folds and leakage-safe preprocessing.

4. **Deterministic similar-opponent model**
   - similarity computed from measurable pre-fixture features;
   - scaling/distance/neighbor weighting learned without future information;
   - no invented similarity scores.

5. **Conservative shrinkage baseline**
   - long-run strength, venue, opponent adjustment and strong shrinkage;
   - deliberately resistant to short-run noise;
   - used as both benchmark and possible ensemble anchor.

Model complexity is promoted only if it improves future probability quality.

## 13. Full distributions, not only expected counts

QFE predicts market-event probabilities, not merely expected goals/corners/cards.

A model can estimate a mean count well and still produce wrong probabilities in the tails.

For count markets, validate:
- mean;
- variance;
- zero frequency;
- tails;
- over/under dispersion;
- home/away dependence;
- total-count coherence.

Distributional choice is target specific.

Goals, corners and bookings do not need to share the same distribution family.

## 14. Genuine chronological OOF predictions

Every component model must generate immutable out-of-fold predictions on fixtures it did not train on.

OOF artifacts must bind:
- fixture;
- target;
- line;
- fold;
- training cutoff;
- component model/version;
- raw probability;
- availability/abstention state.

These OOF predictions are the only valid substrate for learning ensemble weights and calibration mappings.
## 15. Ensemble layer

Combine complementary models rather than choosing a single development winner.

Initial preferred ensemble:
- interpretable;
- regularized;
- non-negative weights;
- weights sum to one;
- weights fitted on earlier OOF predictions;
- objective: minimize OOS log loss.

Always compare against:
- equal-weight ensemble;
- best single component;
- conservative baseline.

More flexible stacking is allowed only if simpler ensembles are demonstrably insufficient and the added flexibility survives protected evaluation.

Component dispersion must be retained as a diagnostic. A high final probability produced by violently disagreeing components is not equivalent to one supported by broad model consensus.

## 16. Calibration is a first-class model stage

The raw ensemble probability is not automatically `p_model`.

Calibration must be trained on earlier OOF prediction/outcome pairs and frozen before later evaluation.

At minimum compare, where sample support allows:
- logistic/Platt calibration;
- beta calibration;
- isotonic calibration.

Isotonic must not be used automatically on sparse samples.

Evaluate pooled or partially pooled calibration when per-league/per-line samples are too small.

Never calibrate on the protected outcomes used to judge the calibrator.
## 17. Calibration diagnostics

Do not reduce calibration to ECE.

Required diagnostics:
- reliability curve;
- calibration intercept;
- calibration slope;
- support by probability region;
- sample size;
- coverage;
- model confidence distribution.

The engine must explicitly identify unsupported probability regions.

If QFE is well calibrated around 50-65% but has little evidence above 75%, the latter region must not inherit the former's credibility.

## 18. Out-of-distribution and support controls

The disagreement detector must know when the fixture is outside the model's reliable domain.

Potential deterministic diagnostics include:
- feature-space distance from training data;
- team-history depth;
- competition-history depth;
- missing-feature rate;
- component-model dispersion;
- provider capability gaps;
- calibration-region sample support.

OOD controls should primarily affect **eligibility/abstention**, not silently distort `p_model`.

## 19. Market probability layer

Preserve raw offered prices and all quote timestamps.

The primary no-vig method must be preregistered before protected evaluation. Any alternative transformation is a bounded sensitivity analysis and cannot be selected after seeing which makes QFE look best.

The market comparator must be constructed independently from QFE.

The independent football probability must not use odds as an input, feature, calibration target or shrinkage anchor.

## 20. Secondary market-adjusted research arm

Separately test:

market-only calibrated probability
vs. market + standalone QFE
vs. market + any later validated QFE feature bundle.

Strongly regularize toward the market and train only on earlier OOF data.

This arm answers whether QFE contains incremental information beyond the market.

It does **not** replace the independent QFE probability and must not be relabeled as standalone `p_model`.
## 21. Validation design

Use chronological walk-forward evaluation.

Separate:
- development;
- calibration/ensemble fitting;
- protected evaluation;
- later prospective validation.

Once protected evaluation is opened, do not change:
- features;
- targets;
- distributions;
- hyperparameters;
- ensemble method;
- calibration method;
- line set;
- competition cohort;
- decision horizon;
- disagreement rule;
- minimum effect threshold;
- stopping rule

and then present the altered run as the same experiment.

A design defect discovered after freeze requires abort/version/new experiment.

Previously exposed data remain development data.

## 22. Dependency and uncertainty discipline

Multiple lines, team sides and totals from one fixture are dependent observations.

Keep fixture rows in the same fold and the same uncertainty block.

Use paired, fixture/time-block uncertainty for model comparisons.

Report effect size, confidence interval, sample size and coverage; do not report only a point estimate.

## 23. Global forecast evaluation versus disagreement evaluation

Maintain two separate scorecards.

### A. Global probability scorecard
Evaluate all eligible predictions:
- log loss;
- Brier;
- calibration;
- reliability;
- coverage;
- count-distribution diagnostics.

This determines whether QFE is a trustworthy probability engine.

### B. Disagreement scorecard
Evaluate only predictions selected by a **frozen** disagreement policy:
- same proper scoring metrics;
- model versus market probability quality;
- disagreement bins;
- calibration within selected regions;
- closing-line movement;
- settlement after prospective freeze.

This determines whether QFE is particularly informative when it disagrees with the market.
## 24. Disagreement research

Predeclare disagreement bins or another deterministic selection policy before protected/prospective evaluation.

Do not assume larger disagreement is better.

Specifically test whether extreme gaps are:
- genuine incremental signal; or
- model overconfidence / misspecification.

A likely useful diagnostic is performance as a function of disagreement magnitude, but thresholds must be frozen before protected use.

Market disagreement remains the **operational discovery goal** of QFE. Proper scoring rules and calibration determine whether that disagreement deserves trust.

## 25. Commercial validation remains separate

Predictive quality does not authorize betting.

Commercial evidence requires:
- frozen selection policy;
- executable timestamped prices;
- prospective commitments;
- genuine closing prices;
- settlement;
- explicit costs/frictions;
- predefined economic evaluation.

A model can be scientifically improved without being commercially validated.

Market disagreement alone is never proof of expected value.

## 26. CHAMPION and historical protection

Existing CHAMPION, old pilot ledgers, frozen experiments, LLM research and previous model artifacts remain historical evidence.

Do not rewrite, delete, relabel or retroactively repair them to fit this architecture.

The successor engine must be developed in an isolated research namespace.

Promotion to production requires a separately documented decision after:
1. clean offline evidence;
2. protected OOS evidence;
3. calibration acceptance;
4. market-relative incremental analysis;
5. prospective shadow evidence.

## 27. Initial implementation sequence

1. Freeze and archive the present state; do not modify old experiment evidence.
2. Audit TheStatsAPI field coverage and semantics for goals, corners and bookings.
3. Define exact target/settlement contracts.
4. Build the point-in-time historical feature table.
5. Implement dynamic latent team/opponent strengths with shrinkage.
6. Implement the conservative baseline.
7. Implement target-appropriate structured count models.
8. Implement the nonlinear tabular model.
9. Implement deterministic similar-opponent features/model.
10. Generate chronological OOF predictions for every component.
11. Fit and compare constrained ensembles on OOF predictions.
12. Fit and compare calibration methods using earlier OOF data only.
13. Freeze a candidate standalone QFE probability stack.
14. Evaluate global OOS LL, Brier, calibration, coverage and distribution diagnostics.
15. Build timestamp-matched no-vig market comparators.
16. Diagnose where and why QFE differs from the market.
17. Design and freeze a deterministic disagreement eligibility policy using support, OOD and model-consensus diagnostics.
18. Evaluate the disagreement subset separately.
19. Run the secondary market+QFE incremental-information experiment.
20. Only after offline/protected evidence is satisfactory, authorize a new prospective shadow pilot.
21. Freeze every prospective prediction before outcome and closing-line observation.
22. Evaluate closing-line movement, settlement and economic evidence only after the predictive pipeline is frozen.

## 28. Promotion principles

A successor model is not promoted because:
- it found more disagreements;
- it produced larger gaps;
- it won a small settlement sample;
- it improved hit rate;
- it looked better on exposed fixtures.

A successor probability stack earns predictive promotion only through preregistered out-of-sample evidence showing:
- improved or acceptably competitive log loss;
- preserved or improved calibration;
- acceptable Brier score;
- adequate coverage;
- stable probability-region support;
- no integrity defect.

A disagreement detector earns promotion only if its selected subset demonstrates credible incremental information out of sample and then survives prospective validation.

## 29. Governing statement

QFE is no longer an LLM-hypothesis engine.

QFE's future is a **deterministic probabilistic forecasting and market-disagreement engine**.

Its advantage, if one exists, must come from:
- better point-in-time football representation;
- dynamic strength estimation;
- shrinkage;
- complementary models;
- coherent predictive distributions;
- ensemble learning;
- rigorous calibration;
- disciplined market comparison;
- selective abstention when support is weak.

The goal is not to imitate sportsbook odds.

The goal is to build an independent probability engine whose probabilities are trustworthy enough that, when it disagrees with the market, the disagreement is scientifically meaningful and can be tested prospectively.

**Forecast quality first. Credible disagreement second. Prospective evidence decides whether either has value.**
