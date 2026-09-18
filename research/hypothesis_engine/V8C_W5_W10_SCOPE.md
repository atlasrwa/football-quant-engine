# V8C W5/W10 confirmatory scope (`v8c_w5w10_scope_v1`)

**Declaration of scope. NO THRESHOLD IS CHANGED.**

## The arithmetic

```
W5  cohort  <=  5 observations
W10 cohort  <= 10 observations
MIN_RAW_N    = 20        (frozen V8B.2 support contract)
```

A literal `W5` or `W10` cohort **cannot** satisfy `MIN_RAW_N` by construction. Not usually —
ever. They are therefore non-selectable under the frozen support contract, and every one of them
classifies as `PRE_T_INSUFFICIENT_RAW_N`.

## The V8C declaration

1. **W5/W10 remain ontology-recognised structures.** `compiler._select` implements both
   (`entries[-5:]`, `entries[-10:]`), and the V8C grammar enumerates them. They are part of the
   declared space.

2. **They are OUTSIDE the confirmatory `PRE_T_EVALUABLE` selectable estimand** under this frozen
   support contract. No arm — S, R or H — can select one, because none is evaluable.

3. **Recent-regime analysis in V8C is carried by the supported machinery**: the
   `SUBJECT_RECENT_VS_LONG_BASELINE` comparator and the decay-weighted `ALL_PRIOR` recency
   family. Those express "recent form vs long-run form" over a cohort that *can* clear the
   support floor, which is the same football question with a statistically admissible estimator.

4. **Literal bounded windows require a future versioned support experiment** — a successor
   support contract with a window-aware floor, preregistered before any fresh outcome. That is
   a scientific decision about the scorer, not an apparatus repair, and it is not made here.

## Why they were still restored to the grammar

Restoring them was correct even though nothing selects them:

- the search space is now a **declared design object** rather than an accident of a helper
  function's default argument (`window_choices=("ALL_PRIOR",)`);
- their exclusion is now **reported** (`PRE_T_INSUFFICIENT_RAW_N`) rather than silently
  invisible, so a reader can see that the question was asked and why it cannot be answered.

## What must not be said

- Not: *"W5/W10 are part of the confirmatory search space."* They are enumerated, not selectable.
- Not: *"restoring W5/W10 expanded what Sonnet can choose."* It did not; the evaluable universe
  is unchanged by their presence.
- Not: *"MIN_RAW_N should be lowered so W5/W10 work."* Weakening a support threshold to admit a
  structure is fitting the contract to the grammar.

## Classification

Logged as **`P2-GRAMMAR-WINDOW`**. Whether this is an acceptable explicit scope exclusion or a
scientific-scope inconsistency requiring a successor support contract is **a decision for the
independent audit**, not one taken here.
