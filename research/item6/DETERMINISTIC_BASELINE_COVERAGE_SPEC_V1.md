# DETERMINISTIC_BASELINE_COVERAGE_SPEC_V1

`item6_baseline_coverage_v1` · frozen · code: `src/research/item6/baseline_coverage.py`

Frozen, machine-readable declaration of the hypothesis-family space the deterministic engine
**already covers**. It is the single source of truth for the baseline-equivalence detector and
the abstract coverage description shown to the model.

## What this spec deliberately does NOT contain

- **No historical OOS success/failure of any baseline family.** Revealing which baseline families
  "worked" would leak outcome information into the Stage-1 evaluator and let the model optimize
  against the prior audit. This file encodes structural shape only.
- **No worked football example.** The abstract descriptions never instantiate a metric pair,
  direction, venue, or profile as an example.

## Grounding: the frozen V8C grammar

The deterministic admissible universe is the tuple
`(target_metric, subject, perspective, comparator, window, conditions)`:

- 24 contract-covered target metrics
- subject ∈ {HOME_TEAM, AWAY_TEAM}; perspective ∈ {FOR, AGAINST}
- 10 comparators (`COMPARATOR_BINDINGS`)
- 3 windows {ALL_PRIOR, W5, W10}
- 76 condition shapes: arity 0/1/2, where arity-2 is **closed** to exactly
  `venue × opponent_profile` and `competition × opponent_profile`.
- 6 opponent-profile axes: goals_for, goals_against, shots_on_target_for,
  shots_on_target_against, possession_for, shots_against.

## Covered structural families (told to the model, abstractly)

| family_id | abstract description |
|---|---|
| `BC_SAME_METRIC_MIRROR` | one observable, own production vs opponent's same-observable concession |
| `BC_UNIVARIATE_PROFILE_SPLIT` | one observable + one opponent-profile band |
| `BC_SIMPLE_VENUE_CONTRAST` | one observable split by home/away |
| `BC_RECENT_VS_LONGRUN` | one observable's recent vs long-run level |
| `BC_TEAM_METRIC_X_OPP_CONCESSION` | direct cross-entity same-observable read |
| `BC_ENVIRONMENT_BASELINE` | one observable vs league/competition baseline |
| `BC_SINGLE_DIM_PROFILE_ALREADY_EXPRESSIBLE` | any arity-0/1 split already in the grammar |
| `BC_SIMILAR_OPPONENT_COHORT` | one observable over a similar-opponent cohort |
| `BC_COVERED_TWO_DIM_INTERACTION` | the two closed arity-2 interactions |
| `BC_SALIENCE_RANKING` | ranking/selecting among already-enumerable relationships |

## Structural axes the baseline grammar CANNOT express (the escape hatches)

A genuinely novel mechanism must use at least one of these:

| structure_id | description |
|---|---|
| `US_MULTI_METRIC_INTERACTION` | joint relationship among ≥2 distinct metrics |
| `US_TWO_DIM_OPP_PROFILE_INTERSECTION` | intersection over two distinct profile axes |
| `US_THRESHOLD_NONLINEARITY` | threshold / piecewise / nonlinear on a continuous observable |
| `US_HALF_STATE_OR_GAME_STATE` | within-match state (half split / prior game state), where resolvable |
| `US_CROSS_METRIC_ASYMMETRY` | asymmetric relationship across different metrics for the two sides |
| `US_SEQUENCING_REGIME` | sequencing / regime / trajectory over ordered prior matches |

Each escape hatch maps to a versioned **additive grammar extension** (`GX_*`) in the formalizer;
V2/V3 grammar is never mutated.

## Nine deterministic research-family labels (structural map, reported)

`ATTACK_VOLUME`, `DEFENSIVE_CONCESSION`, `SET_PIECE_GENERATION`, `DISCIPLINE`,
`POSSESSION_CONTROL`, `FORM_VS_BASELINE`, `CROSS_ENTITY`, `ENVIRONMENT`, `MATCHUP_SIMILARITY`.
