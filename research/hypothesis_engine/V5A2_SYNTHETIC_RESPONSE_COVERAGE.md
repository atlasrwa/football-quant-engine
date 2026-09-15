# V5A2 — Synthetic Response Coverage

**ZERO SPEND.** All responses here are hand-constructed or generated. No model was called,
and **nothing in this report is evidence about any model's behaviour.** It measures only
whether the apparatus can express, accept, reject and score the full space of legal and
illegal responses.

Artifacts: `out/v5a2/surface_battery.json`, `out/v5a2/evaluator_exercise.json`.

---

## 1. Model-visible enum coverage (§10)

Every member of every enum the model can write, exercised at least once:

| Enum | Members | Covered |
|---|---|---|
| `research_family` | 13 | 13 |
| `subject` | 6 | 6 |
| `side` | 2 | 2 |
| `window` | 4 | 4 |
| `comparison` | 5 | 5 |
| `sufficiency` | 2 | 2 |
| `priority` | 3 | 3 |
| `target_metrics` | 27 | 27 |
| `required_capabilities` | 19 | 19 |
| `conditions.dimension` | 8 | 8 |
| `conditions.value` | 17 | 17 |
| `conditions.axis` | 15 | 15 |
| **total** | **121** | **121** |

**`MODEL_VISIBLE_ENUM_COVERAGE = 1.0000`**

Coverage is computed from fields the generator **records**, never re-parsed out of a case-id
label. An earlier version parsed the label and reported 0.8443 — it was measuring the label,
not the case. A coverage number derived by re-parsing your own formatting is not a coverage
number.

## 2. Response-shape coverage

| Shape | Generated | Apparatus outcome |
|---|---|---|
| well-formed, fully grounded | yes | accepted |
| well-formed, unexposed term | yes | `UNSUPPORTED_CONTEXT_SOURCE`, reason names term + declared state |
| abstention, no refs | yes | accepted |
| abstention, valid refs | yes | accepted (D2) |
| abstention, fabricated refs | yes | `INSUFFICIENT_EVIDENCE` |
| sufficient, no refs | yes | rejected |
| fabricated evidence id | yes | `INSUFFICIENT_EVIDENCE` |
| unknown / retired dimension | yes | `SCHEMA_INVALID` |
| internal-namespace leak | yes | `SCHEMA_INVALID` |
| cross-dimension value | yes | `SCHEMA_INVALID` |
| profile without axis / axis on axisless dim | yes | `SCHEMA_INVALID` |
| unknown metric | yes | `SCHEMA_INVALID` |
| excluded metric (`npxg`) | yes | `UNSUPPORTED_CONTEXT_SOURCE` |
| extra property | yes | `SCHEMA_INVALID` |
| numeric claim in prose | yes | `NUMERICAL_AUTHORITY_VIOLATION` |
| empty hypothesis list | yes | scored, rates all 0.0 |
| `NO_TOOL_USE` (null payload) | yes | scored, `whole_response_failure = NO_TOOL_USE` |

## 3. Evaluator path coverage (§12)

`v5a1_evaluator` was hashed and preregistered **without ever having been run over a full
response set**, and the first thing the analysis driver did on real paid data was raise
`KeyError: 'venue_use'`. The evaluator was *frozen* but not *complete*, and the difference
only appeared after money had been spent.

Every path is therefore driven before the freeze. 14 paths, **0 failures**:

| Path | Result |
|---|---|
| normal response, base arm | rates computed |
| normal response, research arm | rates computed |
| `NO_TOOL_USE` (raw `None`) | rates computed, no `KeyError` |
| whole-response `SCHEMA_INVALID` | rates computed, no `KeyError` |
| abstention-only response | rates computed, `grounded_abstention_rate` populated |
| empty hypothesis list | rates computed |
| firewall-blocked response | `n_firewall_blocked` populated |
| self-noise, zero variance | floor falls back to `MIN_SELF_NOISE_FLOOR` |
| self-noise, no groups | pooled SD 0.0, floor 0.5 |
| self-noise, real spread | pooled SD computed |
| evaluability, empty arm | `NON_EVALUABLE` with 5 reasons |
| evaluability, full run | `EVALUABLE` |
| **full paired aggregation → `final_verdict`** | executes end to end |
| base-arm availability dimensions | all four report `available: False`, count 0 |

The full paired aggregation over all 10 fixtures × both arms produced
`execution=COMPLETE scientific=EVALUABLE verdict=FAIL` on synthetic data where both arms
were given the same number of acceptable hypotheses. **That is the correct output** — a
zero paired difference must not produce a PASS — and it confirms the gate cannot manufacture
one.

## 4. What this does not show

- Nothing here is evidence about Sonnet, or about whether full-fidelity evidence helps.
- The synthetic responses were written by the same person who wrote the validator, so they
  cannot demonstrate that the contract is *discoverable* from the packet. That is what the
  paid experiment tests, and it is allowed to fail.
- 100 % enum coverage means every enum member was exercised once, not that every
  *combination* was. Combinatorial coverage is not claimed.

`V5A2_SYNTHETIC_SURFACE_COVERAGE_100_PERCENT`
