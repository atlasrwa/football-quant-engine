# Quant Football Engine — source of truth

Decision date: 2026-09-27 (America/Bogota)
Scope amended: 2026-09-29 (America/Bogota), by explicit user instruction.

Status: governing research direction for the next implementation cycle. This document does not claim that code has been changed, tests have passed, or a market advantage has been established.

## Objective

A hypothesis earns promotion by improving genuinely out-of-sample probability forecasts beyond a competitive baseline, maintaining or improving calibration, and adding predictive value after market information is included. Market disagreement alone is not success.

Current approach: a small curated library of executable hypotheses, measured deterministically and evaluated across a coverage-selected competition cohort. Autonomous LLM discovery is deferred. This tests curated feature value, not autonomous LLM superiority.

## Initial library

The data and research scope now covers goals, corners and bookings, each for home team, away team and match total. This supersedes the earlier single-family starting restriction. Validation and promotion remain independent for each family and market target; evidence for match totals does not automatically validate team sides. Sharing fitted parameters is allowed, but sharing a promotion verdict is not.

The five candidates below remain the original curated library. Goals and bookings extensions must receive executable definitions and bounded development budgets before testing; their inclusion in scope is not evidence that their features work.

1. Conditional corner dispersion: variability beyond opponent-adjusted mean production changes total-corner probabilities.
2. Schedule illusion: opponent-adjusted recent form improves on raw recent form.
3. Shot versus corner suppression: defensive profiles affect corners differently from shots.
4. Similar-opponent profiles: performance against statistically comparable opponents improves transfer beyond ordinary ratings.
5. Dependence between team corner counts: a joint structure improves total-corner forecasts beyond independent team distributions.

These are unproven candidates. Use only hypotheses supported by actual cached inputs. Missing inputs produce UNSUPPORTED, not imagined proxies. A hypothesis may require a distributional extension rather than an extra column; label that comparison explicitly and keep it bounded.

## Required comparisons

- M0: contemporaneous no-vig market reference, only where adequate cached quotes exist.
- M1: simple regularized statistical baseline.
- M2: competitive deterministic model using generic and contextual features.
- M2+H: matched M2 with the curated hypothesis feature or registered feature bundle.

Use M2+H for this cycle to avoid confusing curated hypotheses with the earlier M3 autonomous-LLM thesis. Preserve historical arm labels in old experiments; do not rewrite old results.

Evaluate standalone M2 versus M2+H and matched market-adjusted versions. Include a market-only calibrated comparator. Fit adjustments on earlier out-of-fold predictions and regularize toward the market. Do not require a standalone model to beat the market globally before testing whether it supplies complementary information.

## Three promotion gates

### 1. Out-of-sample predictive improvement

Primary statistic: paired log-loss improvement, defined as loss(M2) minus loss(M2+H), on the same eligible forecast cases. Positive means improvement. Report effect size, confidence interval, sample size and coverage. Predeclare a minimum worthwhile effect before opening protected results. Brier score and count-distribution diagnostics are supporting evidence.

### 2. Calibration preserved or improved

Evaluate reliability curves, calibration intercept/slope and probability-region support. Predeclare a noninferiority tolerance and evaluation method using development data only. Failure to detect calibration harm does not establish noninferiority. Do not promote based on ECE alone. Insufficient precision means INCONCLUSIVE.

### 3. Incremental market-adjusted value

The hypothesis-enhanced market-adjusted forecast must improve on the matched baseline market-adjusted forecast out of sample, with effect size and uncertainty reported. Comparison with the market-only model must also be reported. A larger model-market gap is not an improvement by itself.

Predictive promotion requires all three gates. A hypothesis passing only the first two remains a predictive research candidate. Missing trustworthy historical odds means MARKET_UNTESTED, not failure and not a pass.

Individual features need not each achieve standalone significance if evaluated as a preregistered bundle. Use development ablations to assess contributions; do not claim each member of a successful bundle is independently validated.

## Commercial validation is a separate gate

Predictive promotion does not authorize betting. Economic evidence requires a frozen selection policy, timestamped executable-price evidence, net payoff calculations, prospective commitments, suitable closing comparisons and settlement. For binary no-push bets, EV = p * offered_odds - 1 before separately applicable costs. A conservative net-EV bound must clear the predeclared economic threshold; merely exceeding no-vig market probability is insufficient.

## Experiment discipline

- Select competitions and markets using coverage and semantics before inspecting returns.
- Cover all three families and both team sides plus match totals in the data and research layer now. Register each evaluation separately at a fixed decision horizon. Full-time half-integer lines are an initial evaluation preference where supported; periods and settlement rules must be explicit.
- Pool evidence across suitable competitions, shrinking sparse competition effects toward the shared effect. Do not pool incompatible provider definitions.
- Use the same hypothesis definitions across competitions. Any competition-specific specialization discovered in development requires later independent evaluation.
- Use chronological development, calibration and protected evaluation periods. Previously exposed data remain development data even if frozen.
- Feature selection, similarity construction, scaling, tuning and calibration must use eligible earlier data only.
- Freeze a bounded search budget, hypothesis definitions, main comparison, effect thresholds, calibration tolerance, multiplicity policy and stopping rules before confirmation.
- Use paired time-block uncertainty estimates; keep all rows for a fixture together. Multiple lines do not create independent matches.
- Preserve every attempted hypothesis, parameter variant, rejection and unavailable prediction. Report performance coverage and missingness.
- Distinguish retrospective reconstruction from point-in-time replay. Never invent availability timestamps or backdate commitments.
- Keep hypothesis generation odds-blind; evaluate market value in the separate market layer.

## Offline-only implementation constraint

All new development tests, rehearsals, fitting and evaluation use cached data or deterministic fixtures derived from it. Small synthetic inputs are allowed only for explicitly labeled mathematical or boundary tests, never as empirical performance evidence.

No live football-provider, bookmaker, exchange or LLM API calls. No cache-refresh fallback, authentication probes, quota checks, paid canaries or network dependency downloads. Cache misses fail explicitly. Preserve existing provenance and temporal safeguards. No new apparatus unless necessary for a demonstrated integrity gap or this registered experiment.

Keep the production champion unchanged. No publishing, deployment, betting or automatic activation of capture jobs. Offline readiness is distinct from scientific validation. Live validation requires explicit user authorization after the offline report.

## Next implementation sequence

1. Extend the offline evidence layer to goals, corners and bookings, with home, away and total targets. Preserve frozen V3 evidence and isolate successor development.
2. Audit cached field coverage, period semantics, target definitions, neutral venues and provenance without selecting winning leagues. Preserve all supported raw fields; do not assume all belong in a model.
3. Define market-specific M1/M2/M2+H comparisons, eligible cohorts, hypotheses, search budgets and validation criteria. Maintain the existing comparison workflow where compatible.
4. Construct features only from earlier eligible matches; fit opponent adjustment, similarity, preprocessing and missingness handling within chronological training folds.
5. Run bounded development comparisons and ablations separately for each market target. Retain negative results and unavailable predictions.
6. Freeze each selected model/bundle, calibration procedure and promotion criteria before its protected evaluation. No model inherits another target's validation.
7. Evaluate on genuinely untouched cached data if available; otherwise report development evidence and the prospective evidence still needed. Live execution still requires the authorization specified above.

## Three-family evidence and target contract

| Family | Team-side and total targets | Candidate historical evidence |
| --- | --- | --- |
| Goals | Home goals, away goals, match goals | Goals for/against, shots, SoT, box shots, big chances, saves; separately verified optional xG |
| Corners | Home corners, away corners, match corners | Corners for/against, crosses, blocked shots, final-third entries, shots, possession, defensive profiles |
| Bookings | Home bookings, away bookings, match bookings | Provider-native cards, fouls, tackles, duels, opponent fouls drawn and verified referee context |

These are candidate evidence families, not established effect sizes or mandatory features. Available cross-family statistics may inform any target when a grounded hypothesis and validation support it. Keep raw provider paths, units, period, side, source hash and capture metadata. Preserve missingness and distinguish missing values from zero. Do not infer foul-drawn or percentage semantics from ambiguous field names. Preserve npxG as raw evidence without lifting prior model exclusions; inclusion needs a separate verified specification.

Targets must specify regulation versus extra time, card type, second-yellow treatment, bench/staff treatment and bookmaker settlement rules where applicable. A provider-native yellow-card count is not automatically a valid bookings-market label. Retain ambiguous raw evidence but exclude it from affected model inputs/labels until resolved. Do not sum rates or percentages to construct match totals.

Historical half-level statistics require reconciliation of first half, second half and full-match values for additive metrics; extra time must be handled explicitly. Halftime-state hypotheses also require a verified halftime score. No minute-level inference from half-level data. An upcoming halftime state cannot be used in a pre-match forecast.

Keep historical outcomes/statistics separate from prediction inputs. A historical match's own shots cannot predict its own pre-match goals. Retrospective reconstruction must be labelled as such; never invent original publication timestamps. Historical formation/lineup context from prior matches is permitted without exact switch timestamps, but prospective target lineups require pre-freeze availability evidence. Manager identity requires historical fidelity checks; neutral venue unknown stays unknown.

Preserve the pipeline: evidence/context → curated grounded hypothesis → deterministic measurement → sample and confounder checks → chronological OOS → candidate feature/model comparison → calibration → engine-owned p_model → timestamped market comparison → prospective freeze → genuine closing line → settlement. The LLM never supplies probabilities, effect sizes, similarity scores or numerical adjustments. Autonomous LLM discovery remains deferred in this cycle.

For each family × target × period × decision horizon, maintain a separate result state, sample size, coverage, model/calibration version and promotion decision. Register bounded line sets; home/away rows, multiple lines and totals from one fixture are dependent and remain in the same fold/uncertainty block. Account for the expanded hypothesis/market search in the multiplicity policy. Maintain coherent team and total distributions, including validated dependence assumptions.

Compare richer M2 against M1 as well as M2+H against matched M2. Improvement due to ordinary statistical features must not be attributed to the hypothesis layer. Apply the existing three promotion gates separately and retain the separate commercial-validation gate. A ready corners model need not wait for bookings, and bookings cannot inherit corners' success.

Result states: UNSUPPORTED, DEVELOPMENT_ONLY, REJECTED, INCONCLUSIVE, PREDICTIVE_CANDIDATE, MARKET_UNTESTED, or CONFIRMED_INCREMENTAL_VALUE. Define any combination of states explicitly in the report. None implies commercially validated profitability.

Priority: maximum scientific information per unit of engineering complexity.
