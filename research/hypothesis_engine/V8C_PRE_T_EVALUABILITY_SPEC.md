# V8C pre-T evaluability spec (`v8c_pre_t_evaluability_v1`) — P1 MEASSPACE / COMPADM

## 1. The distinction

```
ADMISSIBLE_IR         a hypothesis the ontology grammar + capability contract permit
PRE_T_EVALUABLE_IR    a hypothesis the deterministic engine can PROVE, before kickoff,
                      it will be able to MEASURE at this target fixture
```

V8B let all three arms select from `ADMISSIBLE_IR`. The engine already knew, before the match
was played, that most of that space could not be evaluated — so the experiment spent real money
on selections guaranteed to end `SCORE_INSUFFICIENT_SUPPORT`. Measured on the exposed 50 under
V8C's classifier: **5 / 249 (2.0%)** of historical Sonnet selections were pre-T evaluable.

That is apparatus failure, not evidence about Sonnet.

## 2. Why this is possible at all

Every quantity the post-T scorer gates on is computable from strictly-prior observations:

| quantity | source | pre-T? |
|---|---|:-:|
| cohort / baseline observation sets | `prior_entries` — strictly before `T` by construction | ✓ |
| `raw_n`, `unique_fixtures` | counts over those sets | ✓ |
| `unique_opponents` | distinct opponent ids in those sets | ✓ |
| `effective_n`, `weight_concentration` | Kish ESS / max weight share of cohort weights | ✓ |
| degeneracy | cohort vs baseline fixture sets + weights | ✓ |
| environment mean availability | `env_mean(…, cutoff = target kickoff)` | ✓ |
| `scale_var` | weighted variance of **cohort** values | ✓ |
| **the target's own observed value** | the match itself | **✗** |

Exactly one input is unknowable before kickoff.

## 3. The consistency invariant

```
PRE_T_EVALUABLE  ⇒  post-T status ∈ { SCORE_OK,
                                      SCORE_REFUSED("observed value … unavailable") }
```

Any other post-T status from a `PRE_T_EVALUABLE` hypothesis is a **classifier defect**, not a
data property. Asserted unconditionally in
`test_golden_e2e.py::test_pre_t_evaluable_implies_permitted_post_t_status`, over every scored
selection of the 15-fixture synthetic end-to-end run — and it holds with zero violations.

The invariant is only meaningful because pre-T and post-T share **one** implementation: the
classifier runs the frozen compiler and the frozen V8B.2 support gate with `observed`
withheld. It *is* the post-T computation minus the target value, not a parallel
re-implementation that could drift from it.

This is also why `v8c/scorer.py` exists. If the classifier used the competition-coherent V8C
compiler and the scorer used the frozen one, the two would disagree about cohort membership for
every `opponent_profile` hypothesis and the invariant would break. One profile semantic runs
end to end.

## 4. Statuses

| status | meaning |
|---|---|
| `PRE_T_EVALUABLE` | will be measurable |
| `PRE_T_INSUFFICIENT_RAW_N` | cohort below `MIN_RAW_N = 20` |
| `PRE_T_INSUFFICIENT_FIXTURES` | below `MIN_UNIQUE_FIXTURES = 15` |
| `PRE_T_INSUFFICIENT_OPPONENTS` | below `MIN_UNIQUE_OPPONENTS = 6` |
| `PRE_T_INSUFFICIENT_EFFECTIVE_N` | Kish ESS below `MIN_EFFECTIVE_N = 10.0` |
| `PRE_T_WEIGHT_CONCENTRATION` | max weight share above `0.25` |
| `PRE_T_PROVIDER_UNSUPPORTED` | metric absent from the index, or **not admissible at this fixture's competition** |
| `PRE_T_COMPILER_INVALID` | structurally invalid, or refused at this fixture |
| `PRE_T_DEGENERATE_CONTRAST` | cohort and baseline coincide |
| `PRE_T_NO_SCALE` | cohort has no dispersion to standardize by |

Where several support predicates fail, the status is named by the **first** failing field in a
fixed order (volume → diversity → weighting), so a multi-failure cohort always reports the same
status. Every failing predicate is still listed in `failures`.

**No threshold is changed.** All five support thresholds are imported unchanged from the frozen
V8B.2 classifier, and the scale floor from the frozen scorer.

## 5. COMPADM — the competition gate

Neither `search()` nor `invariants.assert_valid` ever compared the target fixture's competition
against `capability.admissible_competitions(metric)`. `search()` returned
`admissible_competitions` as a *display field* and never used it.

So a `RESTRICTED` metric could enter the selectable universe at a fixture whose competition the
provider does not cover — `offsides` is not admissible in `epl`/`ligue1`, `xg` not in
`laliga2`/`ligue2`, `touches_in_penalty_area` not in `champ`. Not triggered in the exposed 50
(0/249), so it was latent rather than benign.

V8C enforces it as the first gate in the classifier, reported as
`PRE_T_PROVIDER_UNSUPPORTED`, and tested with a real RESTRICTED metric at a real
non-admissible competition.

## 6. What Sonnet sees — and does not

Two projections of every candidate:

| projection | contains | consumer |
|---|---|---|
| `internal` | structural fields **+** the `pre_t` support block | classifier, R matching, H ranking, freeze |
| `llm_facing` | structural fields **only** | the search tool result |

Support magnitudes are withheld from the model because the endpoint must measure **football
reasoning**, not sample-size shopping: if Sonnet could read `raw_n`, a trivially winning policy
is *"pick the largest cohort"*, and the experiment would be measuring whether a model can sort
a column.

Nothing the football question needs is withheld — **every candidate in the space is already
evaluable**, so the support magnitudes carry no decision-relevant information for the task
being studied.

This is enforced separately from `FORBIDDEN_OUTCOME_FIELDS`, which *passes* on these keys
because they are support statistics rather than outcomes. `assert_llm_safe` is the mechanical
check, applied at the tool boundary inside the runner as well as at the projection.

## 7. Not outcome cherry-picking

The filter reads **no** target observation, **no** effect, **no** score, **no** direction and
**no** p-value. It removes only hypotheses the deterministic engine can already prove it will be
unable to measure. That is measurability control — the same discipline as declaring a detector's
sensitivity range before an experiment rather than after.

The PIT adversarial battery is what makes this checkable rather than assertable: injected future
rows and mutated target outcomes produce **byte-identical** evaluable sets, while a genuine
prior row changes them.
