# SOL 6 execution handoff — proprietary lean football research candidate

Prepared: 28 September 2026, America/Bogota.
Mode: coding-agent execution, offline and isolated.
Paste the launch prompt at the end into Sol and provide this file.

## Mission

Act as a senior statistical engineer and quantitative researcher. Complete a small, reproducible football probability and market-comparison candidate using existing cached data and existing code. Test useful mechanisms from the referenced studies against simple baselines. Deliver working code, bounded empirical comparisons and a candid report—not another architecture proposal.

“Proprietary” means our own reproducible feature construction, parameter estimation, calibration and decision implementation. It does not require inventing a distribution, claiming novel intellectual property, or copying a paper's fitted coefficients.

The user will continue the 40-test MANUAL pilot separately: Scores365 screenshots → contextual research → deterministic analysis → market/Rushbet comparison → pre-kickoff freeze → settlement. It currently has 11 declarations, 7 wins, 4 losses and 29 declarations remaining. Do not edit that pilot, add your candidate's forecasts to it, or switch its formulas.

This task prepares an isolated research candidate for later review. Production replacement remains deferred until the user's pilot review and explicit decision. No deployment or promotion is authorized.

## 1. Authority and hard boundaries

Read local AGENTS.md and QUANT_FOOTBALL_SOURCE_OF_TRUTH.md. The latter's curated M2 versus M2+H direction, three predictive gates and separate economic gate govern this task. If the files are unavailable, use this handoff's conservative constraints and report the missing authoritative source; do not invent its contents or claim full compliance with an unseen document.

Preserve:
- M0 = eligible contemporaneous no-vig market reference.
- M1 = simple regularized statistical baseline.
- M2 = competitive deterministic contextual model.
- M2+H = matched M2 with a registered curated mechanism/feature bundle.
- A matched market-only calibrated comparator and market-adjusted baseline/enhanced comparisons when evidence permits.
- Historical arm names in old experiments. Do not rename HGB experiments as the production champion.
- LLM role: hypotheses/explanations only. No LLM-generated probabilities, fitted weights, uncertainty or EV. Autonomous paid LLM discovery is deferred.

Hard constraints:
- Cached data only for code execution, fitting, replay and tests. No football-provider, bookmaker, exchange, weather or LLM API calls.
- No credential inspection, auth probes, quota checks, cache-refresh fallback, dependency downloads or purchases.
- No new paid model calls or subagents. Use the current Sol session and installed local dependencies.
- No betting, Telegram/publication, deployment, service changes, capture activation or production champion edits.
- No git reset/clean, destructive checkout, blanket staging, force-push or accidental inclusion of unrelated work.
- Local task-specific commits are allowed. Do not push or open a PR; leave the result for review.
- Preserve original V1 outputs. Write new versioned outputs; never overwrite historical evidence.
- The user explicitly EXCLUDED Türkiye–Italy, Sweden–Poland and Romania–Bosnia from 28 September 2026 as incorrectly analyzed. Do not use these fixtures, their analyses or outcomes for fitting, tuning, model choice, metrics or promotion evidence. Resolve exact identities/date before filtering; do not exclude all historical meetings of those teams.
- Synthetic examples prove mathematics/software behavior only, never empirical predictive superiority.

Do not interpret a blocked family as a reason to stop useful independent offline work. Report unsupported inputs honestly. Do not invent neutral venues, timestamps, event counts or publication vintages.

## 2. Locate and preserve the actual work

Verified starting observations, not commands to reset:

Candidate worktree:
  /home/ubuntu/qfe-curated-offline
Branch:
  research/curated-hypotheses-offline
Base HEAD:
  3afa8c716b9d599cce7eec9bac30a0e0ec8c6fb0

Candidate implementation and reports are currently UNCOMMITTED:
  src/research/lean_champion/
  scripts/lean_champion_replay.py
  tests/research/lean_champion/
  research/lean_champion/SPEC_V1.md
  research/lean_champion/REPLAY_V1.json
  research/lean_champion/COMPARISON_V1.json
  research/lean_champion/CANDIDATE_TABLE_V1.md

Other dirty files include curated-offline modules, scripts and reports, plus a tracked modification to:
  src/research/target_aware_market_panel/predictive_v14.py
Preserve them. Candidate compare.py imports the uncommitted curated module; the offline runner is also uncommitted. A clean worktree from HEAD alone WILL NOT contain all required code.

Protected champion artifact:
  /home/ubuntu/data/discovery/pilotC_stat_mixer.json
Observed SHA256:
  0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9

Manual ledger/research worktree, read-only for this task:
  /home/ubuntu/handoff_out/lean_hypothesis_ledger
Research commit:
  ff804d86f2e457979bc693e02f52e22aee7bbe37
Read:
  research/lean_hypothesis_ledger/model_research_20260928/POISSON_CHALLENGE_AND_RECOMMENDATION.md
  research/lean_hypothesis_ledger/model_research_20260928/LOCAL_EVIDENCE.json
  research/lean_hypothesis_ledger/model_research_20260928/MATHEMATICAL_CHECKS.json
  research/lean_hypothesis_ledger/MANUAL_PILOT_FIRST_DECISION_20260928.md

Record actual branch, HEAD, status and hashes before editing. Create an isolated local worktree/branch when possible. Preserve required uncommitted dependencies with a documented copy/patch and source hashes; include only dependencies actually required to reproduce the candidate. Never blindly copy credentials, large data caches or all dirty files. If another process is changing the source tree, snapshot verified files and avoid concurrent writes.

Inspect imports and the offline guard before running code. On the inspected host, relevant tests run through:
  /home/ubuntu/.venv/bin/python scripts/run_curated_offline.py tests/research/lean_champion -q

The runner denies sockets and child processes before project imports. The last observed result was 36 passed. Reverify the current state; do not claim the previous run as your own. The replay CLI has a hardcoded source worktree path: repair it for your isolated candidate before executing, so it cannot overwrite original reports.

Do not stop after reading this document or printing a plan. Proceed through supported work.

## 3. What already exists and what it has not proved

The current corner candidate models total N by negative binomial and home count H conditional on N by beta-binomial; A=N-H. It separates fitting from prediction and computes exact payoff EV.

Saved development replay:
- Training: 2,801 fixtures.
- Evaluation: 1,201 fixtures.
- Eligible market pairs: 50 fixtures / 100 side rows.
- M1 log loss: 0.6909214403.
- Candidate M2 log loss: 0.6918658270.
- Paired improvement M1 minus M2: -0.0009443867.
- Reported 14-day interval: [-0.0025659492, 0.0014945987].
- Bundle calibration is null.
- Market-adjusted modeling is MARKET_UNTESTED.
- The actual incumbent and original manual baseline are UNREPRODUCED.
- Candidate O9.5 probabilities range approximately 40.91%–50.40%.

These are exposed development results. Do not relabel them protected OOS. They show no demonstrated overall improvement; they do not isolate distribution from mean-estimation changes. Narrow predictions warrant investigation but do not prove overshrinkage.

Only the corner path exists in this replacement. Goals/BTTS/team goals and bookings remain to be implemented where data support them. The real 365Scores adapter is unsupported in this worktree; a common import schema is not evidence of a working provider adapter.

## 4. Phase A — close specific integrity gaps first

Reproduce each relevant defect against the unmodified candidate, then add a focused regression test and smallest fix.

Known findings:
1. replay.uncertainty_from_history returns min(0.05, 0.25/sqrt(n)). This is a coverage heuristic, not a validated model-probability interval.
2. decide.py subtracts that probability-unit quantity directly from payoff EV.
3. Missing uncertainty defaults to zero and can appear fully qualified.
4. The half-integer check tests merely “not an integer”; verify that quarter/arbitrary fractional lines cannot pass a half-integer-only policy.
5. Verify the policy's declared primary line is actually enforced by decide(), not only supplied by the CLI.
6. Verify the promised calibration/quote-freshness/contract checks are implemented, not only documented.
7. A historical kickoff before cutoff is not sufficient proof that final statistics were available at that cutoff. Audit completion/receipt eligibility and classify reconstructions correctly.
8. Inspect neutral-venue handling: unknown or supplied-neutral status must not silently become an ordinary home fixture.
9. Make candidate I/O paths portable and versioned; preserve originals.

For binary no-push, no-commission bets:
  EV(p) = odds*p - 1
  lower_EV = odds*p_lower - 1

If p_lower=p-delta, subtract odds*delta from EV, not delta. For general contracts, price the full candidate/refitted distributions through payoff states. Do not call an arbitrary haircut a confidence bound.

Maintain separate fields for point estimate, uncertainty method/status, lower estimate where valid, and qualification. Missing defensible uncertainty may allow a diagnostic row; it must not pass a policy that requires a conservative bound. Calibration missingness must also be explicit.

Do not replace the heuristic with another arbitrary percentage. Estimate uncertainty from eligible chronological refits/calibration only when supported within the budget; otherwise mark it unavailable and fail the corresponding qualification gate.

Exact two-way normalized reciprocal no-vig, offered break-even and payoff EV remain distinct. No overround/2 adjustment or double vig subtraction. Retain reference/execution overlap and quote age. No default bookmaker eligibility without semantics/timestamp support.

## 5. Phase B — audit studies and data before choosing models

Create one concise evidence matrix for the studies below: mechanism, required inputs, reported evidence type, transfer risks, local support, and implement/defer decision.

Use the attached research report and any locally available primary papers/code. Bibliographic links are references, not permission to fetch dependencies or live data. If a paper's full method is unavailable, say “not fully reproduced”; do not claim replication from an abstract. Do not spend a long new literature-search session or duplicate the existing architecture documents.

Study-to-task mapping:
- Maher 1982, DOI 10.1111/j.1467-9574.1982.tb00782.x:
  opponent attack/defense rate estimation; retain Poisson as a serious baseline.
- Dixon–Coles 1997, DOI 10.1111/1467-9876.00065:
  time weighting and four-cell low-score correction. At fixed rates, the standard correction leaves O2.5 and higher total-over probabilities unchanged. Test this identity.
- Yip et al. 2024, DOI 10.1080/01605682.2024.2306170, manuscript arxiv.org/abs/2112.13001:
  NB/geometric-Poisson corner dispersion. Their cross-market features are not football-only evidence.
- Philipson 2026, DOI 10.1093/jrsssa/qnag014:
  underdispersed yellow-card counts; mean-parameterized CMP is a conditional challenger. WAIC/posterior checking is not our prospective betting validation.
- Baio–Blangiardo 2010, DOI 10.1080/02664760802684177:
  partial pooling and risk of overshrinkage.
- Boshnakov–Kharrat–McHale 2017, DOI 10.1016/j.ijforecast.2016.11.006:
  Weibull-count/copula goals alternative; defer until a simple goal baseline shows a concrete defect.
- Duan et al. 2020, proceedings.mlr.press/v119/duan20a.html:
  probabilistic boosting; deferred in this task.
- Gneiting–Raftery 2007, DOI 10.1198/016214506000001437:
  proper scoring rules; disagreement size and hit rate are not model-selection objectives.

Audit cached support for ALL requested families at the beginning, not only corners:
- dated team counts and opponent identities;
- venue, competition, domain (club/international/age/gender);
- goals, xG and npxG as separate definitions;
- corners for/against;
- yellow/red/second-yellow/bench event semantics;
- referee assignment vintage and usable earlier history;
- prior H2H, similar-opponent features, forecast weather vintages;
- complete market contracts, quote and receipt times, executable-price evidence;
- historical exposure map and missingness.

Averages and sample sizes alone cannot identify dispersion or dependence. No invented match rows from screenshots. Current-match state, realized weather or post-match referee metadata cannot become pre-match evidence. Preserve provider separation and earlier exclusions.

## 6. Phase C — implement the smallest supported candidate

Shared requirements:
- Training, snapshot construction, inference, pricing and selection remain separate.
- Serialize fitted coefficients, preprocessing, regularization, calibration, source definitions, cutoff, configuration and provenance.
- No training inside predict().
- Finite nonnegative PMFs, explicit tail-error handling, monotone thresholds and coherent team/total probabilities.
- Missing optional context has an explicit baseline fallback; required missing evidence is UNSUPPORTED.
- Do not add a generic framework, orchestration platform or new deep model.

### Corners — complete the first matched comparison

Retain the reproducible existing implementation as a named comparator.

A. Mean comparison:
  Compare a simple baseline and regularized opponent-adjusted mean estimator under a COMMON distribution.
  Use supported production/concession, venue and competition inputs.
  Fit scaling/regularization only on earlier training/development data.
  Do not force wider probabilities; tune against proper scores.

B. Distribution comparison:
  Hold predicted means IDENTICAL between Poisson and NB; fit dispersion on earlier data only.
  Compare conditional dispersion rather than raw pooled variance.
  Do not let both rates and distribution change and attribute the entire gain to NB.

C. Team allocation comparison:
  Hold the total distribution fixed; compare binomial against beta-binomial allocation.
  Evaluate team counts/markets separately: an allocation change cannot alter the already fixed total PMF.
  Keep team-market findings development-only unless separately registered.

If NB already belongs to M2, a dispersion hypothesis H must be an identifiable extension, e.g. supported conditional versus constant dispersion; it cannot add the identical mechanism twice.

### Goals — complete a supported development path

Where dated integer goal histories are available, fit regularized/partially pooled team attack and opponent defense with competition and verified venue effects and explicitly specified time weighting. Document identification constraints, sparse-team fallback and neutral treatment.

Derive total goals, team goals, BTTS and result probabilities from the same joint distribution. Compare plain Poisson with Dixon–Coles as one bounded extension where fit is supported. Keep fitted xG covariates separate from integer target counts; do not invent GF/xG mixing weights.

No arbitrary lambda entry justified by LLM judgment. No claim to have recovered the old manual goal estimator. A new estimator gets a new model identifier and separate results.

### Bookings — contract and dispersion gate

If cached target definitions and histories are adequate, implement a team/opponent/competition count baseline with eligible shrunk referee effects when supported.

Assess residual dispersion on development data:
- approximately equidispersed: Poisson baseline;
- supported overdispersion: NB challenger;
- supported underdispersion: mean-parameterized CMP only if an installed, inspectable implementation is available and can be verified within the bounded task.

Do not write a new copula/CMP numerical library merely to fill a checklist. If unsupported, finish the baseline and report the advanced candidate deferred. Do not substitute NB for underdispersion. Weighted bookings cannot be priced from yellow-card counts alone.

## 7. Bounded evaluation and experiment discipline

Before new empirical fitting, write a short versioned specification using DEVELOPMENT information only:
- supported primary cohort/family/contract and decision horizon;
- model roles and exact mechanisms;
- exposure map, chronological train/development/calibration/evaluation periods;
- coverage and quote requirements;
- proper-score primary statistic, minimum worthwhile improvement and calibration noninferiority rule;
- finite configuration/search budget, time-block uncertainty and multiplicity policy;
- selection policy and stop conditions.

Keep the established corner 9.5 / T-60 target as the initial comparison unless coverage/semantics show a documented reason to change it before scoring. Goals/bookings are separate development extensions, not additional confirmation claims.

Budget:
- At most SIX complete candidate configurations per supported family, including baseline and mechanism ablations.
- At most THREE chronological development folds for configuration comparison.
- No Cartesian-product search beyond this cap, no post-result extra variants and no retries aimed at favorable metrics.
- Reuse frozen predictions for pricing/calibration/score reports where mathematically appropriate.
- Distinguish predictive-score bootstrap uncertainty from fitted-probability uncertainty.
- Stop optional model expansion when the budget is exhausted; a negative/inconclusive result is complete work.

These caps limit work, not guarantee adequate evidence. Define parameters and exact fits before execution. Do not choose numerical thresholds to make an already observed result pass.

Respect temporal eligibility; advance rolling features only as observations truly become available. Fit transformations and calibration on earlier data only. Fit coherent distribution-level calibration where supported, otherwise label identity calibration without claiming calibrated performance.

Previously exposed data stay DEVELOPMENT_ONLY even after a new freeze. If genuinely untouched cached data do not exist, produce development results and a precise future evaluation requirement rather than manufacturing a holdout.

Use paired proper scores on identical fixtures. Group all markets/lines of a fixture in uncertainty estimation. Report coverage, missingness, calibration intercept/slope/reliability support and count/tail diagnostics, not ECE alone.

Market-adjusted evaluation:
- Preserve football-only probabilities and odds-blind hypotheses.
- Where sufficient eligible earlier quote/prediction pairs exist, fit regularized market-adjusted M2 and M2+H plus the matched market-only comparator.
- The inspected minimum is 200 earlier qualifying pairs; do not lower it to accommodate the 50 observed evaluation pairs, and do not count two sides as two independent fixtures.
- If support remains inadequate, preserve guarded implementation and report MARKET_UNTESTED. Do not force a fit.

Audit the five governing hypotheses: conditional dispersion; schedule illusion; shot/corner suppression; similar-opponent profiles; home/away dependence. Mark each supported, unsupported or already included in the baseline. Keep similarity fitting and feature selection inside earlier training data. Do not implement unsupported proxies.

All three source-of-truth gates remain necessary for predictive promotion, and economic validation is separate. This task itself authorizes no promotion.

## 8. Verification and deliverables

Tests should address demonstrated risks:
- exact half-integer/primary-line enforcement, invalid probability/odds and contract mismatch;
- missing uncertainty/calibration cannot masquerade as validated conservative qualification;
- uncertainty-to-payoff conversion and push/quarter-line/commission arithmetic;
- normalization, tail error, monotonicity and team/total identities;
- fixed-rate Dixon–Coles O2.5 invariance;
- same-mean Poisson/NB comparison binding;
- fit/predict separation and fitted-bundle round trip;
- cutoff, completion/receipt eligibility, unknown/neutral venue and provider semantics;
- excluded fixture identities and no leakage from evaluation into fit/calibration;
- network/cache-fallback denial and protected artifact hashes.

Run targeted tests through the offline guard. Run one new versioned end-to-end replay on supported real cached data. Do not rerun old batteries or overwrite V1 outputs.

Deliver in your isolated repository:
1. Small candidate code changes and focused tests.
2. Source/dependency snapshot manifest and source hashes.
3. Study/data capability matrix and finite experiment specification.
4. Frozen fitted bundles and complete prediction/candidate/rejection tables where supported.
5. Machine-readable scores plus a concise human report.
6. Exact reproduction command(s).
7. Task-only local commits and review range; no push.

Final report MUST distinguish:
- implementation completed versus unsupported/deferred for corners, goals and bookings;
- context actually used versus merely stored;
- starting/final HEAD, branch, source snapshot and task commits;
- development versus truly untouched evaluation;
- comparison effects and uncertainty, calibration and market-adjusted status;
- test results, empirical run counts, configuration budget consumption;
- operating costs: no paid API calls/provider calls/dependency downloads, with enforcement scope;
- unchanged champion hash, untouched manual pilot, and excluded fixtures;
- concrete remaining blockers.

Use result states accurately: UNSUPPORTED, DEVELOPMENT_ONLY, REJECTED, INCONCLUSIVE, PREDICTIVE_CANDIDATE, MARKET_UNTESTED, CONFIRMED_INCREMENTAL_VALUE. Do not translate passing tests, a profitable historical subset or a large disagreement into proven advantage.

Finish supported work autonomously. Ask only when a genuine access/authorization boundary prevents progress; do not require approval for routine reversible implementation choices. If blocked on a family, complete the other supported work and report the exact missing evidence.

## Launch prompt

You are Sol 6 acting as the implementation agent for Quant Football Engine. Read SOL6_PROPRIETARY_LEAN_HANDOFF.md and the repository's AGENTS.md / QUANT_FOOTBALL_SOURCE_OF_TRUTH.md. Execute the handoff in an isolated offline research branch, preserving all uncommitted source work and the separate 40-test manual pilot. Reproduce and fix the specific integrity gaps, audit support across corners/goals/bookings, run the bounded matched comparisons on eligible cached data, and deliver task-only local commits, reproducible outputs and an honest final report. No paid API calls, network-dependent execution, production changes, promotion, push or PR. Do the implementation; do not stop at a plan.
