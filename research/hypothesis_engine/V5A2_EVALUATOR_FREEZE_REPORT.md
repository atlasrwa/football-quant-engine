# V5A2 — Evaluator Freeze Report

**ZERO SPEND.** Frozen at `spend_usd = 0.0`, before any V5A.2 response exists.

Artifacts: `out/v5a2/EVALUATOR_FREEZE.json` (`b1dc1e2e18635ab6`),
`out/v5a2/evaluator_exercise.json`.

---

## 1. Every threshold is V5A.1's, carried forward unchanged

| Threshold | V5A.1 | V5A.2 |
|---|---|---|
| `PRIMARY_METRIC` | `grounded_accepted_n` | `grounded_accepted_n` |
| `DISCIPLINE_TOLERANCE` | 0.05 | 0.05 |
| `MIN_SELF_NOISE_FLOOR` | 0.5 | 0.5 |
| PASS / MIXED / FAIL gate | paired mean vs floor, discipline veto | identical |

These were decided before V5A.1 ran and are therefore **not reachable by anything V5A.1
revealed**. Moving any of them now would be indistinguishable from tuning the apparatus to
rescue a result. `test_evaluator_thresholds_are_inherited_unchanged` asserts equality against
the frozen `v5a1_evaluator` module directly, so drift cannot be silent.

## 2. What is new is a distinction, not a threshold (§13)

V5A.1 collapsed two questions with different answers:

- **Execution status** — did the battery run to completion?
- **Scientific status** — is there enough valid data to answer the research question?

V5A.1 stopped at 6 of 38 calls, so its execution status was STOPPED. But even had all 38
calls completed, **0 valid research-arm responses** would have made the science
unanswerable. Reporting one number invites reading "FAIL" as "the research idea failed" when
what failed was the plumbing.

`final_verdict()` now returns both, and **issues no PASS/MIXED/FAIL at all unless the run is
EVALUABLE** — because with too little valid data, "FAIL" would be a claim the data cannot
support.

### Evaluability minimums (frozen)

| Minimum | Value | Why this number |
|---|---|---|
| paired fixtures (valid in **both** arms) | 8 | the primary analysis is a paired per-fixture difference; the battery plans 10, and 8 tolerates two losses while leaving a sample no single fixture dominates |
| valid responses per arm | 8 | same |
| repeatability groups per arm | 3 | the self-noise floor is a pooled within-(fixture, arm) SD; below 3 groups it is an anecdote, not an estimate |

Chosen from what the comparison **needs**, not from what V5A.1 achieved. Replayed through
the gate, V5A.1 is `NON_EVALUABLE` on all five counts — which is the correct description of
what happened to it, and the point of having the gate.

## 3. Failure classification and stop rules (§15)

| Class | Meaning |
|---|---|
| `MODEL_SCHEMA_INVALID` | the model wrote something outside a contract it **was shown** — a scientific observation |
| `INFRASTRUCTURE_CONTRACT_FAILURE` | the apparatus could not express a legal response — **our** defect |

V5A.1's stop rule counted them together. Replaying its run through `classify_stop(n_calls=6,
model_invalid=0, infra=2, ...)` now yields:

```
V5A2_STOP_INFRASTRUCTURE_CONTRACT_FAILURE   class: APPARATUS
```

not a model discipline rate. The same six calls, correctly attributed.

| Stop rule | Threshold | vs V5A.1 |
|---|---|---|
| `V5A2_STOP_MODEL_SCHEMA_INVALID_RATE` | > 0.30, after ≥ 6 calls | **threshold unchanged**; numerator is now MODEL failures only |
| `V5A2_STOP_INFRASTRUCTURE_CONTRACT_FAILURE` | ≥ 1 | **new and stricter** — expected value is 0 |
| `V5A2_STOP_TRANSPORT` | 3 consecutive | unchanged |
| `V5A2_STOP_COST_CEILING` | cumulative > ceiling | unchanged |

**On the 0.30 rule, reviewed as §15 requires: it stands.** It fired correctly in V5A.1 given
what it could see; the defect was the numerator, not the number. The `≥ 6 calls` guard is
*made explicit rather than changed* — V5A.1's rule was first evaluated at 6 calls, so 6 is
what it always was. Stating it prevents the rate firing at 1/1.

A per-hypothesis apparatus defect (an ontology term the schema admitted but translation
cannot map) now also sets `failure_class`, so the rule that counts our own bugs can see that
path. Previously it would have escaped as an uncaught traceback mid-paid-run.

## 4. Complete, not merely frozen (§12)

All 14 analysis paths were driven before freezing — see
`V5A2_SYNTHETIC_RESPONSE_COVERAGE.md` §3. 0 failures, including the full paired aggregation
through `final_verdict`. This is the direct response to V5A.1's `KeyError: 'venue_use'`,
which was a frozen-but-incomplete evaluator discovered only after spending money.

## 5. An interpretation caveat that must not be misread

The four availability-aware dimensions — `venue_use`, `recent_vs_long_use`,
`opponent_profile_use`, `formation_use` — report `available: False` and count `0` for
**every base-arm packet**, because the base arm exposes none of those terms.

**These four are within-research-arm descriptives, not cross-arm comparisons.** "Base scored
0 on `opponent_profile_use`" is not a finding about the model; it is a restatement of what
the base packet contains. Reading it as a model result would be a category error.

The primary metric `grounded_accepted_n` is unaffected: both arms have the same ceiling of
12 hypotheses, and the base arm can fill it with unconditioned questions. The verdict gate
is a paired comparison on that metric and remains sound.

## 6. Freeze record

```
module      src/research/hypothesis_oos/v5a2_evaluator.py
spend at freeze                 $0.00
frozen before first paid call   true
run exactly once                true
EVALUATOR_FREEZE.json sha256    b1dc1e2e18635ab6…
```

Nothing in the evaluator may change once execution begins: not the normalization, the
evidence-reference rules, the meaningful-interaction classifier, the groundedness
definition, the availability denominators, the thresholds, the gates, the evaluability
minimums, or the repeatability calculation.

`V5A2_EVALUATOR_FROZEN`
