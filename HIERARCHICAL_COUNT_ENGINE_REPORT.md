# Hierarchical Count Models — The Forecasting Engine

Two structural changes, built as one piece of work: **one count distribution per market
family** instead of independent binary classifiers per line, and **hierarchical partial
pooling** with teams nested in leagues.

Objective is pure forecasting — calibrated probabilities across a full line set. Not EV,
not market-beating. **No skill claim is made anywhere in this work**, and the evaluation is
constructed so that none can be drawn from it.

- Model: `src/research/models/hierarchical_market_model.py`
- Family registry, coverage and dispersion audits: `src/research/models/market_family.py`
- Strictly-prior row builder: `src/research/models/side_rows.py`
- Form windows: `src/research/prediction_engine/form_window.py`
- Attribution: `src/research/models/count_attribution.py`
- Evaluation: `src/research/evaluation/hierarchical_lines.py`
- 30-day window: `src/research/prediction_engine/evaluation_window.py`
- Runner (zero API calls): `scripts/hierarchical_forecast_eval.py`
- Artifacts: `data/results/hierarchical_line_evaluation.json`,
  `hierarchical_market_coverage.json`, `hierarchical_dispersion_audit.json`
- Corpus: **15,362 completed fixtures, 25 leagues**, static cache only, zero API calls
- Tests: **155 new**, full suite **2,919 passed**

---

## 1. What replaced what

Corners 8.5, 9.5 and 10.5 were three separate elastic-net fits with nothing constraining
them, so `P(over 9.5) > P(over 8.5)` was reachable — an impossibility. Three models' worth
of parameters were spent on one question: what is the distribution of corners in this match?

The engine now models a **side count** per family and convolves the two sides into the match
total. Three things follow from that choice, and they are the reasons for it:

1. **Every line is the survival function of one PMF.** Monotonicity holds arithmetically.
2. **Both teams to score falls out** of the same two side distributions that produce the
   goals lines, so BTTS cannot contradict over 2.5.
3. **Attack and defence separate.** A corner arrives because one side creates pressure and
   the other yields it. A total-count model cannot tell those apart, and the explanation
   layer needs them apart to say anything in football terms.

```
log mu_side = beta0 + x . beta                  global intercept and slopes
            + u_league                          league intercept, partially pooled
            + sum_k delta_[league,k] x_k         league slope deviations, strongly shrunk
            + attack_[counting team]             team attack state, nested in league
            + concede_[opposing team]            team concede state, nested in league
```

Every random effect is an empirical-Bayes posterior `w * raw + (1 - w) * prior_mean` with
`w = tau^2 / (tau^2 + s^2)`. Thin evidence means large `s^2`, small `w`, and an estimate
close to the prior — the league for a team, the global fit for a league.

Parameter count went the right way: **7 to 9 features per family**, one fit each, against
three-plus independent fits per family previously.

---

## 2. Dispersion: verified, and the default assumption was wrong

The instruction was to use Negative Binomial while checking dispersion empirically rather
than assuming it. Checking changed the answer for four of seven families.

Marginal variance/mean on side counts, and the **residual** ratio after conditioning on
features and random effects, which is the correct conditional test:

| Family | marginal v/m | leagues overdispersed | residual v/m | selected |
|---|---:|---:|---:|---|
| corners | 1.626 | 25/25 | 1.390 | **negative binomial** (α 0.076) |
| shots on target | 1.355 | 25/25 | 1.126 | **negative binomial** (α 0.027) |
| first-half corners | 1.359 | 24/25 | 1.209 | **negative binomial** (α 0.086) |
| goals | 1.061 | 0/25 | 0.927 | Poisson |
| cards | 1.038 | 0/25 | 0.951 | Poisson |
| first-half goals | 1.009 | 0/25 | 0.935 | Poisson |
| first-half cards | 0.961 | 0/25 | 0.919 | Poisson |

**Goals, cards and both first-half discipline families are not overdispersed at side-count
level.** Goals being Poisson is the classical result; cards being Poisson is a finding. Three
of the four Poisson families are mildly *under*dispersed on residuals. Forcing NB on them
would have fitted a dispersion parameter to noise.

Selection is on residual rather than marginal dispersion because marginal variance/mean is
the wrong test once covariates exist: a family whose mean genuinely varies across fixtures
looks overdispersed even when the conditional law is exactly Poisson. Note the gap between
the two columns — every family's marginal ratio overstates its residual ratio.

Per-league residual dispersion is measured and reported, but **not** used to give each league
its own α: on a few hundred rows that estimate is noisier than the pooled one, which is the
same variance argument that rules out independent per-league slopes.

---

## 3. The full line set

All seven families are buildable in **all 25 leagues**.

| Family | Lines | Coverage floor met | Lowest league coverage |
|---|---|---|---|
| goals | 2.5, 3.5 | 25/25 | 100.0% |
| corners | 7.5, 8.5, 9.5, 10.5 | 25/25 | 99.3% (Scotland) |
| cards | 2.5, 3.5, 4.5 | 25/25 | 99.6% (Brazil) |
| shots on target | 7.5, 8.5, 9.5, 10.5 | 25/25 | 99.3% (Scotland) |
| first-half goals | 0.5, 1.5 | 25/25 | 100.0% |
| first-half corners | 3.5, 4.5 | 25/25 | **86.5% (Denmark)** |
| first-half cards | 0.5, 1.5 | 25/25 | 99.6% (Brazil) |
| BTTS | derived from goals | — | — |

**Shots-on-target lines, and why.** The market has no conventional ladder, so it was chosen
from the observed distribution: match totals have median 9, interquartile range 6–11, mean
8.75. The four lines 7.5/8.5/9.5/10.5 sit inside the IQR and bracket the median, giving
P(over) from 0.63 down to 0.28. Tail lines were rejected on power grounds, not taste: at
12.5 the over happens in about one match in eight, so a 30-day window would hold a handful
of positives per league and the reliability curve would be noise.

**First-half field availability, checked before committing.** The schema audit's finding
that half-split fields are per-half rather than cumulative was re-verified on the data:
first-half plus second-half equals the match total in 97.6% of corners fixtures and 100.0%
of cards and goals fixtures. Population rates were then measured per league, since that is
where they vary. First-half corners is the weak one — Denmark 86.5%, Netherlands 89.5%, MLS
89.5%, Finland 89.2% — but all clear the 80% floor, so nothing was excluded. The exclusion
mechanism is live and tested rather than hypothetical: a league below the floor is dropped
for that family with a stated reason, never zero-filled. The `-1` sentinel is treated as
missing throughout, because collapsing it to zero would turn "not recorded" into "no corners
in the first half".

**Mechanism features that do not exist in this corpus** are named rather than quietly
substituted. Final-third entries, accurate crosses, clearances, big chances, shots inside the
box, touches in the penalty area, blocked shots, interceptions, tackles and duel percentages
are TheStatsAPI rich fields available only for the Championship cache, not across the 25-league
FootyStats corpus where pooling is meaningful. Declared proxies: `dangerous_attacks` for
final-third entries, `shots_off_target` for the blocked/wide shots that actually produce
corners, `xg` for npxG. Each family carries its `unavailable_mechanisms` list into the report.

---

## 4. Monotonicity

**88,413 fixtures checked across 7 families and 25 leagues. 0 violations.**

Asserted three ways: by construction (one convolved total PMF), by test
(`test_line_ladder_is_monotone`, parametrised over every family's full declared ladder), and
by a runtime check on every scored fixture in the walk-forward whose violation count is
reported. The property survives the uncertainty mixture because a convex combination of
non-increasing survival functions is non-increasing — tested separately.

This is the specific defect the architecture exists to prevent, so it is not trusted, it is
measured.

---

## 5. Calibration — the primary result

Walk-forward, expanding folds, 61 folds per family, compute-before-update over complete
equal-kickoff batches. Standardisation, dispersion selection, the NB dispersion and every
empirical-Bayes prior variance and shrinkage weight are fitted inside the training fold.
Climatology is league-and-line specific from each fold's training snapshot only.

**The primary endpoint is calibration, and it is not a contrast.** The null hypothesis per
cell is *these forecasts are calibrated*, tested by parametric bootstrap: outcomes resampled
from the model's own stated probabilities, over whole league-week blocks. A **finding is a
detection of miscalibration**. That inverts the usual direction deliberately — FDR correction
here protects against crying "broken" too often, and no arrangement of the output can be read
as a skill claim.

| Family | cells | median ECE | flagged miscalibrated |
|---|---:|---:|---:|
| first-half goals | 50 | 0.0291 | 0 |
| first-half cards | 50 | 0.0350 | 3 |
| goals | 50 | 0.0412 | 2 |
| cards | 75 | 0.0437 | 4 |
| first-half corners | 50 | 0.0480 | 4 |
| corners | 100 | 0.0510 | 9 |
| shots on target | 100 | 0.0573 | 9 |

Overall median ECE **0.0461**; 272 of 475 cells below 0.05. Fresh Benjamini-Hochberg family
of **475 cells** (25 leagues × 19 lines), q = 0.05, **0 insufficient**, 31 flagged.

Per-league, best to worst median ECE — reported in full, never pooled-only:

| League | median ECE | max ECE | flagged | | League | median ECE | max ECE | flagged |
|---|---:|---:|---:|---|---|---:|---:|---:|
| Italy Serie B | 0.0317 | 0.0753 | 1 | | Sweden Allsvenskan | 0.0466 | 0.0811 | 0 |
| Turkey Süper Lig | 0.0338 | 0.0636 | 0 | | Belgium Pro League | 0.0468 | 0.0683 | 0 |
| Germany Bundesliga | 0.0370 | 0.0694 | 0 | | Germany 2. Bundesliga | 0.0481 | 0.0942 | 1 |
| Switzerland Super League | 0.0403 | 0.0649 | 0 | | Scotland Premiership | 0.0492 | 0.0778 | 0 |
| France Ligue 2 | 0.0404 | 0.0717 | 0 | | Netherlands Eredivisie | 0.0530 | 0.1051 | 3 |
| France Ligue 1 | 0.0410 | 0.0830 | 0 | | Italy Serie A | 0.0534 | 0.0816 | 3 |
| Brazil Serie A | 0.0420 | 0.0650 | 0 | | Poland Ekstraklasa | 0.0540 | 0.0957 | 2 |
| Spain La Liga | 0.0421 | 0.0635 | 0 | | Portugal Liga NOS | 0.0552 | 0.0808 | 1 |
| USA MLS | 0.0425 | 0.0752 | 0 | | Greece Super League | 0.0556 | 0.0858 | 0 |
| Norway Eliteserien | 0.0432 | 0.0923 | 0 | | Finland Veikkausliiga | 0.0558 | 0.0962 | 0 |
| Australia A-League | 0.0437 | 0.0868 | 0 | | Austria Bundesliga | 0.0609 | 0.0896 | 0 |
| Denmark Superliga | 0.0455 | 0.0801 | 0 | | England Premier League | 0.0656 | 0.0982 | 11 |
| England Championship | 0.0461 | 0.0662 | 9 | | | | | |

**The four leagues that could not fit independently are all scored under pooling** — Austria,
Denmark, Finland and Australia sit at median ECE 0.061, 0.046, 0.056 and 0.044, none flagged.
That is the pooling working as intended: a league too thin to stand alone borrows strength
and still produces usable probabilities.

**20 of 31 flags fall in the Premier League and Championship**, which are also the two
leagues with the most scored fixtures. More predictions means more power to detect a given
miscalibration, so a flag concentration in the largest cells is what a correctly-powered test
looks like, not evidence those two leagues are uniquely broken. Shots on target and corners
carry 18 of 31 flags and also have the two worst median ECEs — those are the families where
calibration work remains.

### The honest caveat: climatology is better calibrated

Pooled across leagues, per line, model against league climatology:

| Family | line | model ECE | climatology ECE | ΔBrier vs climatology |
|---|---:|---:|---:|---:|
| goals | 2.5 | 0.0251 | 0.0110 | +0.00150 |
| goals | 3.5 | 0.0324 | 0.0098 | −0.00040 |
| corners | 7.5 | 0.0298 | 0.0149 | −0.00061 |
| corners | 8.5 | 0.0316 | 0.0184 | −0.00070 |
| corners | 9.5 | 0.0411 | 0.0143 | −0.00194 |
| corners | 10.5 | 0.0423 | 0.0116 | −0.00194 |
| cards | 2.5 / 3.5 / 4.5 | 0.031 / 0.032 / 0.033 | 0.022 / 0.029 / 0.030 | +0.0018 / +0.0027 / +0.0024 |
| shots on target | 7.5 → 10.5 | 0.034 → 0.037 | 0.007 → 0.010 | +0.0015 / +0.0017 / +0.0006 / −0.0004 |
| first-half goals | 0.5 / 1.5 | 0.0106 / 0.0248 | 0.0107 / 0.0132 | +0.0011 / +0.0008 |
| first-half corners | 3.5 / 4.5 | 0.0333 / 0.0436 | 0.0133 / 0.0183 | −0.0012 / −0.0014 |
| first-half cards | 0.5 / 1.5 | 0.0367 / 0.0223 | 0.0177 / 0.0274 | −0.0001 / +0.0013 |

**The model is not better calibrated than a constant league base rate on 17 of 19 lines**,
and ΔBrier is mixed — positive for cards, most shots-on-target lines, goals 2.5 and the
first-half goals lines; negative for all four corners lines and both first-half corners lines.

Part of this is structural: a constant base-rate predictor is trivially well-calibrated, so
beating it on ECE is hard by construction, and the same caveat was the one gate the earlier
league-count work failed. But it should not be waved away on that basis. A conditional model
that is sharper on some families and no better calibrated than climatology on nearly all of
them has real calibration work outstanding — most obviously on corners, where it is worse on
both ECE and Brier at every line.

What this pass does establish is coherence, per-league coverage including the previously
unfittable leagues, and informative estimates for thin teams. It does not establish that the
conditional model is better than a base rate.

### Skill

Reported per cell as `brier_delta_vs_climatology`, marked `reported_but_unresolved`, outside
the FDR family, with `skill_claim_blocked: true` on every cell and pooled row. The
pooled-versus-within-league question is still open and the content gate blocks skill claims.
Nothing here is promoted.

---

## 6. Both teams to score, derived rather than fitted

Derived as `P(home ≥ 1) × P(away ≥ 1)` from the two goals side distributions, against a
directly fitted logistic regression on the same feature block, refit inside every training
fold. 12,718 scored fixtures:

| | ECE | Brier | log loss |
|---|---:|---:|---:|
| derived from the goals fit | 0.0173 | **0.2465** | **0.6862** |
| direct classifier | **0.0035** | 0.2472 | 0.6875 |

**Split decision, reported as one.** The derived version wins on Brier and log loss and is
preferred on log loss in 14 of 25 leagues; the direct classifier is markedly better
calibrated. Since calibration is this engine's primary metric, that is a genuine tension and
not a rounding detail.

The derived version is kept, for a reason that is architectural rather than metric: it cannot
contradict the goals lines. `P(BTTS) ≤ P(over 1.5)` holds by construction and is tested. A
separately fitted classifier can and eventually will publish a BTTS probability incompatible
with the over 2.5 probability sitting next to it in the same message, which is the class of
defect this whole piece of work exists to remove. The calibration gap is recorded as the price
paid, is small in absolute terms, and is a candidate for a post-hoc calibration map applied to
the derived probability — which would preserve coherence, since a monotone map cannot reorder
the lines.

---

## 7. Form windows — last 5, current season only, shrinking

The window is a team's last five completed **current-season** matches. When the current season
holds fewer than five, the window is the matches that exist. Three matches means a three-match
window. It never reaches back into the prior season.

Previously a fixed five-match window abstained whenever the current season could not fill it.
That was honest but uninformative, and it produced the Nantes-versus-Nancy case: four
completed matches each, both rolling windows abstaining, only season-to-date populated, every
market landing near the base rate. Under the shrinking window plus partial pooling, a
four-match team gets a four-match window, shrinks hard toward its league prior, and produces
an informative estimate with appropriately wide uncertainty.

**Prior season enters as a prior, never as window backfill.** A team's prior for the current
season is its previous-season posterior multiplied by a decay factor that halves every 6
current-season matches: weight 1.00 at 0 matches, 0.50 at 6, 0.25 at 12, under 0.02 by 35.
The two mechanisms are kept absolutely separate — the window builder filters to the current
season-instance *before* the window is taken, so backfill is structurally impossible rather
than merely discouraged, and it has no access to prior-season rows at all. Tested directly:
ten prior-season matches at 20 corners followed by three current-season matches at 2 corners
yields a mean of exactly 2.0.

**Uncertainty reaches the output.** The empirical-Bayes posterior variance of the random
effects is integrated over by Gauss-Hermite quadrature on `log mu`, so a thin team's
probabilities are genuinely pulled toward the base rate rather than merely annotated as
uncertain. Tested: an unseen pairing produces a wider central 80% interval on the total than a
well-observed one. Monotonicity survives, since a mixture of survival functions is one.

**The minimum-history gate now keys on window availability**, which was the open question. It
had to be settled because under the fixed window the two criteria could disagree in the worst
direction: a team with three or four matches passed the `min 3` raw-count floor while every
rolling window abstained, so the fixture was priced with no rolling form behind any feature.
The gate now requires both an available window and the raw-count floor, and the shrinking
window makes them agree instead of contradict. The floor of 3 remains binding and is kept: a
one-match window is available but is not enough history to publish from.

On this corpus the median cell used the full 5 matches and only 3.6% of scored fixtures ran on
a shrunken window, because the corpus is mostly mature seasons. The shrinking behaviour is an
early-season and promoted-side mechanism, and that is exactly when it matters.

---

## 8. Per-fixture explanation — why this number

Every published market surfaces its drivers: `weight × standardised feature value` for that
fixture, ranked by size, translated into football language, plus the team attack and concede
states. Real output, verbatim:

```
corners leans higher: KV Mechelen allows more corners than the league;
Sint-Truiden generates more corners than the league; KV Mechelen attacking
pressure allowed well above their norm. Expected corners 10.3 against 9.9 for a
league-typical fixture.

cards leans higher: Pau fouls drawn far above their norm; Pau generates more
cards than the league; Guingamp cards drawn from opponents well above their norm.
Expected cards 4.5 against 4.1 for a league-typical fixture.

goals: no strong signal either way. The model puts this fixture close to a typical
one in this league (2.7 expected against 2.7 for the league norm).
```

**Attribution comes only from the fitted model.** Every driver's contribution is asserted
term by term to equal `weight × standardised_value`, with the weight equal to the global slope
plus any shrunk league deviation; the feature contributions are asserted to reconstruct
`log mu` exactly. Direction is the sign of a fitted contribution and nothing else, so a weight
that flips sign flips every statement built from it. `FEATURE_LEXICON` is a vocabulary, not a
heuristic: it maps a feature name to a neutral noun phrase, carrying no direction, no
magnitude and no conditional logic.

**No rule mining.** There is no threshold search, no percentile discretisation and no
condition-pair enumeration, and no place to add one. Searching for "when X > p70 and Y > p60,
corners exceed 10.5 in 68% of matches" throws away information and generates exactly the
multiple-testing burden that wiped out every prior discovery run under FDR correction. The
regression already learns those conditions continuously with fewer degrees of freedom.

**Near the base rate it says so.** `no strong signal either way` is a real output on **27% of
fixtures**, decided by comparing the fixture against a reference fixture built from the model's
own training means with team states removed — so even the neutrality threshold is
model-derived rather than a hand-set base rate. Structural terms (`is_home`, `support_n`) are
excluded from the ranking because they take the same value in every fixture and cancel against
the reference; they remain in the audit record.

Thin evidence is stated plainly: *"Note: Aston Villa's estimate leans on the league average
(38 match-sides of its own record)"*, and prior-season carry-over is named when it is still
material.

**The content gate applies to explanation text.** Every phrase in the lexicon and every
generated explanation across all seven families is asserted clean of skill, edge, expected
value and recommendation language.

---

## 9. The 30-day evaluation window

Nothing published from this engine counts as evidence until 30 days of settled forecasts have
accumulated on the corrected pipeline. Prior forecasts were generated on the stale corpus and
are diagnostic only.

The mechanism is built and wired, not merely planned. `open_window` is called on the first
forecast actually delivered (`scripts/forecast_broadcast.py`, on `DeliveryStatus.SENT`),
idempotent for the same commitment hash and non-fatal on failure so it cannot block a
broadcast. It writes an append-once epoch file recording the commitment hash, generation
time, model version and corpus content hash.

Three refusals, each tested, all there to stop the window being reinterpreted once partial
results are visible:

- **Re-marking the epoch is refused.** Moving the start after publication began would let the
  window be chosen to suit the results.
- **Changing the length of an open window is refused.** It is 30 days because that was decided
  in advance.
- **Producing calibration figures before the window closes is refused**, reporting days
  remaining instead. A counts-only mode exists for operational visibility and still computes
  no calibration figure.

Forecasts generated before the epoch are excluded structurally by `EvaluationWindow.includes`.
The existing minimum-sample gate is kept: below ~200 settled observations per cell, no ECE is
computed and `insufficient settled predictions — N of ~200` is reported instead.

**Most cells will be underpowered, and the arithmetic says so in advance.** Four leagues at
roughly 40 fixtures a month gives about 40 settled observations per league-market-line cell
against the 200 the gate requires — a shortfall of 160, and about five months to fill a single
cell. `projected_power` states this before the window opens, so it cannot be discovered at the
end and rationalised. At 30 days the report will lead with sample counts and the count of
cells with enough settled observations to say anything at all, which is expected to be zero at
per-line granularity.

---

## 10. Integration and provenance

**The observability gap is fixed.** The broadcast text printed current-season counts but never
the per-team windows map, so a reader saw `Nantes 4, Nancy 4 (min 3)` with no way to tell that
every rolling window had abstained. That map was in the ledger and inside the commitment hash
the whole time. It is now rendered, in both provenance shapes:

```
current_season_matches: Nantes 4, Nancy 4 (min 3)
windows_declared: w5, w10, std
windows[Nantes]: std=populated, w10=abstain, w5=abstain
windows[Nancy]: std=populated, w10=abstain, w5=abstain
```

```
windows[Nantes]: last5=4/5 matches used, shrunk, season 12345
windows[Nancy]: last5=3/5 matches used, shrunk, season 12345
window_policy: current season only; shrinks below the declared window rather than
  backfilling from the prior season
history_gate_keys_on: window_availability_and_min_current_season_matches
shrinkage_weights: away_attack=0.24, home_attack=0.31, league=0.89
prior_season_contribution: away_attack=0.02, home_attack=-0.04
```

A forecast built on 4 matches is now distinguishable from one built on 30 in the published
message, not only in the ledger — asserted by test.

Existing gates are respected, not bypassed. The freshness gate, the prior-only snapshot and
same-match leakage assertions, the minimum-history rules and the content gate are all
unchanged and still enforced; 2,919 tests pass with no regressions. Leakage discipline in the
new row builder is independently re-derived: `assert_no_same_match_leakage` rebuilds the
history from scratch and asserts every emitted feature equals its prior-only value. It ran
clean across all seven families on the full 15,362-fixture corpus.

At the final fold, median league shrinkage weight runs 0.56–0.96 by family and median team
weight 0.10–0.68, so partial pooling is doing real work rather than collapsing to either
extreme. Both start near zero in the earliest folds, when there is too little data to
distinguish any league or team from the global fit, and rise as evidence accumulates — which
is the behaviour partial pooling is supposed to have. First-half cards shrinks team states
hardest (final-fold median weight 0.10), which is correct: first-half cards are sparse, so
individual team records carry little information and the league rate should dominate.

---

## 11. Two defects found and fixed during the build

**Thin leagues were coming out over-confident.** A league's own between-team variance
component is a method-of-moments estimate that on a dozen rows frequently collapses to zero,
which asserts that every team in that league is identical — and made a thin league look *more*
certain than a rich one, the exact opposite of what the hierarchy is for. Fixed by partially
pooling the variance component itself toward the global between-team variance with weight
`n / (n + 20)`. Caught by a test asserting thin leagues carry wider modelled uncertainty.

**The bootstrap was silently destroyed for one league.** MLS carries `game_week = 0` on 78% of
its fixtures — the provider's "not set" value, which the block key was accepting as a real
match-week. That collapsed the entire league into 2 bootstrap blocks, and all 19 MLS cells
were reported insufficient for what looked like a data-volume reason but was really a provider
quirk. Treating `0` as unset alongside `None` and `-1` restored proper ISO-week blocking:
**insufficient cells went from 19 to 0 and the valid FDR family from 456 to 475**. The flagged
count also fell from 38 to 31, because a bootstrap over 2 clusters was producing a
meaningless null. The same pattern exists in the older `league_count.py` block key; that file
was left untouched so the published `LEAGUE_COUNT_HIERARCHICAL_REPORT.md` stays reproducible.

Both are the kind of defect that produces plausible-looking numbers rather than an error, which
is why they are reported rather than quietly corrected.

---

## 12. Ground rules, checked

| Rule | Status |
|---|---|
| Count distribution per market family; never independent classifiers per line | 7 families, one fit each, every line from one PMF |
| Prior season as a decaying prior only — never rolling-window backfill | Halves every 6 matches; window has no access to prior season; tested |
| Monotonicity across lines asserted by test | 88,413 fixtures, 0 violations; parametrised test over every ladder |
| Compact mechanism-motivated features; no broad search | 7–9 per family; unavailable mechanisms named |
| Calibration leads; skill claims stay blocked | Primary endpoint is a miscalibration test; `skill_claim_blocked` on every cell |
| Explanation from fitted weights only; no rule-mining, no hand-authored narratives | Contributions asserted term by term; no threshold search |
| Form window shrinks below 5 rather than backfilling | Tested; provenance records matches used |
| 30-day evaluation window; no verdict before it closes | Append-once epoch; three refusals tested |
| Per-league reporting; fresh FDR family | 475 cells, all 25 leagues, 0 insufficient |
| Pilot C / manual / scanner records untouched | No new module references those paths; reserved basenames refused |

---

## 13. What this does and does not establish

**Established.** Line probabilities are coherent by construction and verified on 88,413
fixtures. All seven families are buildable and scored in all 25 leagues, including the four
that could not fit independently. Dispersion was measured rather than assumed, and the
measurement contradicted the default for four of seven families. A four-match team produces an
informative estimate with wide uncertainty instead of an abstention or a coin flip, and the
width reaches the published probability. BTTS cannot contradict the goals lines. Provenance
now makes the evidence behind a forecast visible in the message itself.

**Not established.** That the conditional model is better calibrated than a league base rate —
it is not, on 17 of 19 lines. That it beats climatology on Brier — mixed, and negative on all
four corners lines. Any skill claim whatsoever. Whether pooled or within-league is the right
frame; that question remains open.

The clearest outstanding work is calibration on corners and shots on target, which carry the
worst median ECE and 18 of 31 miscalibration flags. A post-hoc calibration map applied to the
count distribution's mean would preserve monotonicity, and is the natural next step.

Nothing here is promoted. Nothing published before the epoch marker counts. The 30-day window
has not opened, and no verdict is available until it closes.
