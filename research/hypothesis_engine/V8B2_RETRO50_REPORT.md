# V8B2_RETROSPECTIVE_CORRECTED_PILOT50 — Report

EVIDENCE_CLASS: **POST_OUTCOME_SCORER_REPAIR_DIAGNOSTIC**. V8B.2 was built after these 50
outcomes were already opened, so this is corrected diagnostic evidence — usable for debugging,
effect-direction exploration, and budget decisions, but **not** pristine confirmatory evidence.

Zero new Sonnet calls. Frozen Sonnet/R/H selections, frozen V8B.2 scorer, frozen aggregation.
CHAMPION untouched. The 947 sealed fixtures were never referenced.

## Support / evaluability first (these counts are EVALUABILITY, not wins)

```
Arm S (Sonnet):   total 249 | SCORE_OK 5 | INSUFFICIENT_SUPPORT 208 | REFUSED 36 | INVALID 0
Arm R (blind):    total 249 | SCORE_OK 7 | INSUFFICIENT_SUPPORT 226 | REFUSED 16
Arm H (heuristic):total 249 | SCORE_OK 0 | INSUFFICIENT_SUPPORT 247 | REFUSED 2

Fixtures with >=1 arm score:   S = 4    R = 6    H = 0
Paired evaluable (both arms):  S-v-R = 4    S-v-H = 0
```

SCORE_OK counts measure whether a hypothesis was *scoreable*, not whether an arm *won*. Arm
quality is judged only by the frozen scores among paired evaluable fixtures.

## Primary retrospective comparisons (frozen before trace review; self_hash 6c1ce7c6…)

### S vs R (matched blind)
```
PAIRED_SR_N            = 4
PAIRED_SR_MEAN_DIFF    = 0.0
PAIRED_SR_MEDIAN_DIFF  = 0.0
PAIRED_SR_STDEV        = 0.0
PAIRED_SR_POS_ZERO_NEG = 0 / 4 / 0
INFERENCE_STATUS_SR    = INSUFFICIENT_CLUSTERS_FOR_INFERENCE (1 chronological block, g<3; no p-value by frozen design)
```

Every paired evaluable fixture has an S–R difference of **exactly 0.0**. The reason (verified,
not assumed): on all 4 fixtures the matched-blind control **selected the identical hypothesis
IDs as Sonnet**. In the thin scoreable universe at these early-season fixtures, R's frozen
EXACT-tier structural match plus its `hypothesis_id` tie-break resolves to Sonnet's own
selection, so R collapses onto S and carries **no discriminating information**. This is a
structural property of the control at this scale, not a bug and not evidence of Sonnet skill.

Per paired fixture:
```
mt_012232387  S=-1.270191  R=-1.270191  diff=0.0   (same hyp id)
mt_367717156  S=-0.740589  R=-0.740589  diff=0.0   (same hyp id)
mt_250070680  S= 0.347345  R= 0.347345  diff=0.0   (same 2 hyp ids)
mt_406686750  S=-0.017166  R=-0.017166  diff=0.0   (same hyp id)
```

### S vs H (deterministic heuristic)
```
PAIRED_SH_N         = 0
SONNET_VS_HEURISTIC = UNDEFINED_NO_PAIRED_EVALUABLE_FIXTURES
INFERENCE_STATUS_SH = NO_PAIRED_EVALUABLE_FIXTURES
```
H has 0 SCORE_OK across all 50 fixtures, so no S–H comparison exists. Not manufactured.

## Research-yield report (separate from performance)

```
50 fixtures: 47 OK / 2 abstain / 1 invalid
249 valid Sonnet selections
SCORE_OK = 5  (rate 2.01%)
Support-failure counts (Sonnet, accurate/only-actual):
  raw_n=208  unique_fixtures=201  effective_n=133  unique_opponents=57  weight_concentration=16
```

The bottleneck is **research-space measurability**: ~98% of selections cannot be scored because
the conditioned cohorts at these chronologically-earliest (early-season) fixtures are genuinely
thin (raw_n well below the retained MIN_RAW_N=20). The V8B.2 fix removed the *spurious* universal
block (unique_teams), so `unique_opponents` is now only a minority failure — the remaining
attrition is real data thinness, which the fix correctly does not paper over.

## Trace review (descriptive only; performed after the numeric freeze)

The 4 evaluable Sonnet selections carry substantive, mechanism-grounded reasoning: corner
concession from deep defending, final-third-entry-vs-SoT conversion deficits, home-possession→
corner pathways, and venue-dependent shot volume. But because R selected the identical
hypotheses on every evaluable fixture, there is no S-vs-R contrast for the traces to explain,
and no evaluable S-vs-H case at all. The traces do not and cannot change the frozen numbers.

## Interpretation

**RETROSPECTIVE_UNEVALUABLE.** The corrected rescore yields no usable signal about Sonnet's
selection quality:
- S-v-R: 4 paired fixtures, all differences exactly 0 because the control converged to Sonnet's
  own picks — zero discriminating information.
- S-v-H: undefined (H has no scoreable hypothesis anywhere in the cohort).
- Even setting the control problem aside, only 4/50 fixtures are evaluable at all, and the
  frozen inference legitimately declines a significance claim (1 block, g<3).

This is post-outcome corrected diagnostic evidence and is not overclaimed as signal.

## Decision: is a fresh small pilot worth $7–11?

```
FRESH_SMALL_PILOT_JUSTIFIED = NO (not at these fixtures / not without an apparatus change)
RECOMMENDED_FRESH_N         = 0 for now
ESTIMATED_FRESH_COST        = $0 (do not spend yet)
```

Rationale: the binding constraint is not sample size but **evaluability** (~2% SCORE_OK) and a
**control that collapses onto Sonnet** on the scoreable subset. A fresh 20–30 fixture cohort
drawn from the same early-season reserve would reproduce both problems and produce ~0–1 paired
evaluable fixtures — buying essentially no discriminating evidence for the money.

Two apparatus questions should be resolved *before* any paid pilot (all deterministic/free):
1. **Evaluability**: fixtures with deeper prehistory (later in the season, or teams with more
   prior matches) would raise the SCORE_OK rate. Selecting the fresh cohort for cohort depth
   (still outcome-blind) is the highest-leverage free change.
2. **Control informativeness**: define/measure how often R structurally collapses onto Sonnet;
   if it collapses whenever both are scoreable, the matched-blind arm cannot discriminate and
   needs reconsideration (a spec question, out of scope here).

I am **not** recommending the full 947, and I am not recommending spend now.

## Required final output

```
RETRO50_COMPLETE = true
TARGET_FIXTURES  = 50

S_TOTAL_HYPOTHESES = 249    S_SCORE_OK = 5
R_TOTAL_HYPOTHESES = 249    R_SCORE_OK = 7
H_TOTAL_HYPOTHESES = 249    H_SCORE_OK = 0

FIXTURES_WITH_S_SCORE = 4
FIXTURES_WITH_R_SCORE = 6
FIXTURES_WITH_H_SCORE = 0

PAIRED_SR_N            = 4
PAIRED_SR_MEAN_DIFF    = 0.0
PAIRED_SR_MEDIAN_DIFF  = 0.0
PAIRED_SR_POS_ZERO_NEG = 0/4/0

PAIRED_SH_N            = 0
PAIRED_SH_MEAN_DIFF    = undefined
PAIRED_SH_MEDIAN_DIFF  = undefined
PAIRED_SH_POS_ZERO_NEG = 0/0/0

INFERENCE_STATUS_SR = INSUFFICIENT_CLUSTERS_FOR_INFERENCE
INFERENCE_STATUS_SH = NO_PAIRED_EVALUABLE_FIXTURES

SUPPORT_FAILURE_COUNTS = raw_n 208, unique_fixtures 201, effective_n 133, unique_opponents 57, weight_concentration 16

CHAMPION_UNCHANGED         = true (0b8f5ff3…c00c9)
SEALED_947_OUTCOMES_VIEWED = false
NEW_SONNET_CALLS           = 0
NEW_SONNET_SPEND           = $0

RETROSPECTIVE_INTERPRETATION = RETROSPECTIVE_UNEVALUABLE
FRESH_SMALL_PILOT_JUSTIFIED  = NO
RECOMMENDED_FRESH_N          = 0
ESTIMATED_FRESH_COST         = $0
```

## Artifacts

- `V8B2_RETRO50_RESCORE.json` — per-hypothesis rescore (all 3 arms)
- `V8B2_RETRO50_PAIRED_SR.json` / `V8B2_RETRO50_PAIRED_SH.json` — honest paired tables
- `V8B2_RETRO50_PRIMARY_RESULT.json` — frozen numeric result (self_hash 6c1ce7c6…)
- `V8B2_RETRO50_REPORT.md` — this report
