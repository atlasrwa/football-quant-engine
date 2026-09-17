# V8C — end-to-end experiment contract matrix (`v8c_contract_v1`)

**Status: written BEFORE any V8C code change (§6). Load-bearing.**
**Successor to V8B.1 / V8B.2. Neither is mutated (§4).**
**ZERO Sonnet calls. ZERO fresh outcome access. CHAMPION read-only.**

---

## 0. What this document is for

V8B.1 spent money and opened 50 outcomes before discovering that `SCORE_OK` was structurally
unreachable. V8B.2 repaired that one gate. This document exists so that the *next* such defect
is found here, on paper and in tests, instead of after the next invoice.

It enumerates every transition in the composed experiment. For each transition it names:

| field | meaning |
|---|---|
| **input** | what the stage is contractually handed |
| **output** | what it must produce |
| **success** | the state that means "this stage worked" |
| **failure** | the explicit, named states that mean "this stage did not work" |
| **PIT** | what the stage may read relative to target kickoff `T` |
| **determinism** | what must be byte-identical across runs |
| **coverage** | the test that proves it |
| **reachability** | the known-good proof that `success` is attainable |

A stage whose `success` state has no reachability proof is **not** a working stage. That is the
V8B.1 lesson, restated as a contract.

---

## 1. Defect status carried into V8C

### 1.1 Confirmed, inherited from V8B.1 (already repaired in V8B.2)

| id | class | description | status |
|---|---|---|---|
| `D-V8B1-SCORER-UNIT` | P1 | fixture scorer gated on `unique_teams >= 6`, which is always `1` at fixture level → `SCORE_OK` unreachable | **repaired in V8B.2** (`unique_opponents >= 6`); carried into V8C unchanged |

### 1.2 Confirmed, open at V8C start — repaired by this mission

| id | class | description | evidence |
|---|---|---|---|
| `D-V8C-P0-CTXCUT` | **P0 — future information** | `execution.build_context` fits opponent-profile terciles and the axis cache on **every match before a single global cut** (`index.kick[int(len(index.kick)*0.7)]` = 2025-12-12), not before each target `T`. 643/1000 manifest fixtures and **50/50 exposed pilot fixtures** kick off *before* that cut, so their opponent-profile band assignments — and therefore cohort membership — are a function of matches that had not happened at `T`. The target fixture's own row is inside the fitting window, so the band is partly a function of the target's own observed values. 181/249 exposed Sonnet selections used an `opponent_profile` condition; 26 used similarity. | `V8C_PIT_ADVERSARIAL_RESULTS.json` |
| `D-V8C-P1-RIDENT` | **P1 — control equals treatment** | `controls.match_blind_control` seeds its exclusion set only with *already-used control ids*, never with Sonnet's own id, so `R_ID == S_ID` is permitted. On the exposed 50 this collapsed R onto S at all 4 paired fixtures, making the V8B.2 S-v-R difference identically 0 by construction. | `V8C_EXPOSED50_STRUCTURAL_REPLAY.json` |
| `D-V8C-P1-HUNIVERSE` | **P1 — arm not comparable** | `controls.heuristic_selections_for_fixture` ranks `heuristic_score` over `search(max_results=50)`, but `search` truncates at `MAX_RESULTS_HARD_CAP` **after sorting by `(capability_status, n_conditions, ir_id)`**. H therefore ranks "top by heuristic *among the 50 lowest ir_ids*", not over the universe S and R draw from. | `V8C_EXPOSED50_STRUCTURAL_REPLAY.json` |
| `D-V8C-P1-MEASSPACE` | **P1 — unmeasurable selection permitted** | S, R and H all select from the *syntactically admissible* universe. The deterministic engine already knows before kickoff that most of it cannot be evaluated; nothing stopped an arm selecting a hypothesis guaranteed to end `SCORE_INSUFFICIENT_SUPPORT`. | `V8C_PRE_T_EVALUABILITY_SPEC.md` |
| `D-V8C-P1-COMPADM` | **P1 — provider-semantic mismatch** | Neither `search` nor `invariants.assert_valid` compares the target fixture's competition against `capability.admissible_competitions(metric)`. A `RESTRICTED` metric (`offsides`: not admissible in `epl`/`ligue1`; `xg`: not in `laliga2`/`ligue2`; `touches_in_penalty_area`: not in `champ`) can enter the selectable universe at a fixture where the provider does not support it. Not triggered in the exposed 50 (0/249) — latent, not benign. | `V8C_EXPOSED50_STRUCTURAL_REPLAY.json` |
| `D-V8C-P1-INFSIZE` | **P1 — inference impossible at intended size** | The frozen chronological blocks are 20 blocks × 50 fixtures over the **1000**-fixture manifest. Any fresh pilot of realistic size spans 1–3 of them, so `estimator.small_cluster_inference` returns `INSUFFICIENT_CLUSTERS_FOR_INFERENCE` by construction — exactly what happened at `paired_n = 4` in V8B.2. The inference path is undefined for the experiment actually intended. | `V8C_END_TO_END_REACHABILITY.json` |

### 1.3 Investigated and NOT defects

| finding | verdict |
|---|---|
| 876 `InvariantViolation` + 2112 `MISSING_REQUIRED_CONDITION` across the 21,120 enumerated shapes | **not a defect.** All are legitimate structural invalidity (`BASELINE_ABSORPTION`, `IDENTICAL_COHORT_BASELINE`+`SELF_COMPARISON`, `TAUTOLOGICAL_CONDITION`). No valid hypothesis is destroyed by the compiler. |
| `similarity.SimilarityEngine` | **PIT-safe.** Profiles, z-scale and competition baseline are rebuilt per target position and asserted by `assert_profiles_are_pit`. Not affected by `D-V8C-P0-CTXCUT`. |
| `corpus_index.env_mean` | **PIT-safe.** `bisect_left(ks, cutoff_unix)` with `cutoff = target kickoff` is strictly-before. |
| `np_xg` | **already excluded** from the selectable universe by the capability contract. §30 satisfied without change. |
| Exposed-50 attrition counts (208 `raw_n`, 201 `unique_fixtures`, 57 `unique_opponents`, 133 `effective_n`, 16 concentration) | **genuine thin-history attrition, but computed under the leaky context.** Not usable as a clean baseline; recomputed under V8C. Not a defect to "fix" (§5). |

---

## 2. The stage matrix

Notation: `T` = target fixture kickoff. **PIT-STRICT** = may read only observations strictly
earlier than `T`. **POST-T** = runs only after the all-arm freeze is written.

---

### S1 · TARGET FIXTURE

| | |
|---|---|
| **input** | `fixture_id` from the frozen 1000-fixture manifest |
| **output** | `(rec_i, kickoff_unix, competition, home_id, away_id)` |
| **success** | `fixture_id ∈ index.pos_of_fixture` and the fixture is not in the taint registry |
| **failure** | `FIXTURE_NOT_IN_INDEX`, `FIXTURE_TAINTED` |
| **PIT** | identity + schedule only. **Never** the score, stats or settlement. |
| **determinism** | `rec_i` is a pure function of `(kickoff_unix, fixture_id)` sort order |
| **coverage** | `test_pre_t.py::test_target_resolution` |
| **reachability** | 1000/1000 manifest fixtures resolve |

---

### S2 · PRE-T CAPABILITY

| | |
|---|---|
| **input** | target competition; `CapabilityContract` |
| **output** | the metric set admissible **at this fixture's competition** |
| **success** | ≥1 metric with `status ∈ {SUPPORTED, RESTRICTED}` **and** `competition ∈ admissible_competitions(metric)` |
| **failure** | `PRE_T_PROVIDER_UNSUPPORTED` |
| **PIT** | the capability matrix is a frozen provider-coverage artifact; carries no outcome |
| **determinism** | sorted metric list; no set iteration order escapes |
| **coverage** | `test_pre_t.py::test_competition_admissibility_enforced` |
| **reachability** | 21 `SUPPORTED` metrics in all six competitions |
| **repairs** | `D-V8C-P1-COMPADM` |

---

### S3 · DETERMINISTIC HYPOTHESIS UNIVERSE (`ADMISSIBLE_IR`)

| | |
|---|---|
| **input** | capability-restricted metric set; frozen ontology grammar |
| **output** | every structurally valid IR, canonical id, **fully enumerated — never truncated** |
| **success** | non-empty |
| **failure** | `PRE_T_COMPILER_INVALID` per candidate (`MISSING_REQUIRED_CONDITION`, `BASELINE_ABSORPTION`, `IDENTICAL_COHORT_BASELINE`, `SELF_COMPARISON`, `TAUTOLOGICAL_CONDITION`) |
| **PIT** | structural only. Reads no corpus row at all. |
| **determinism** | `itertools.product` over sorted inputs; ids sorted before use |
| **coverage** | `test_pre_t.py::test_universe_enumeration_complete` |
| **reachability** | 21,120 shapes → **19,008** structurally valid IRs, 19,008 distinct ids |
| **note** | V8B.1's `MAX_RESULTS_HARD_CAP = 50` is a **presentation cap for the LLM**, never the universe. V8C computes evaluability over the full 19,008 and filters *before* truncating. |

---

### S4 · PRE-T SUPPORT / MEASURABILITY  ← **the new stage**

| | |
|---|---|
| **input** | IR, PIT index, `rec_i`, **per-target** PIT context |
| **output** | `PreTEvaluability(status, raw_n, unique_fixtures, unique_opponents, effective_n, weight_concentration, scale_var, failures)` |
| **success** | `PRE_T_EVALUABLE` |
| **failure** | `PRE_T_INSUFFICIENT_RAW_N`, `PRE_T_INSUFFICIENT_FIXTURES`, `PRE_T_INSUFFICIENT_OPPONENTS`, `PRE_T_INSUFFICIENT_EFFECTIVE_N`, `PRE_T_WEIGHT_CONCENTRATION`, `PRE_T_PROVIDER_UNSUPPORTED`, `PRE_T_COMPILER_INVALID`, `PRE_T_DEGENERATE_CONTRAST`, `PRE_T_NO_SCALE` |
| **PIT** | **PIT-STRICT.** Must not call `index.team_value(rec_i = target, …)`. Enforced by the target-blind index wrapper, whose read-audit log is hashed into the freeze manifest. |
| **determinism** | identical to the scorer's own cohort computation, by construction — it *is* the scorer's cohort computation with `observed` withheld |
| **coverage** | `test_pre_t.py`, `test_pit_adversarial.py` |
| **reachability** | proven on the exposed 50 and on the synthetic golden case |
| **repairs** | `D-V8C-P1-MEASSPACE` |

**The consistency invariant (§8), stated exactly.** Everything the post-T scorer gates on is
computable pre-T: the cohort/baseline observation sets, all five support quantities,
degeneracy, environment-mean availability, and `scale_var` (a weighted variance of *cohort*
values). The single quantity that is genuinely unknowable before `T` is the target's own
observed value. Therefore:

```
PRE_T_EVALUABLE  ⇒  post-T status ∈ { SCORE_OK,
                                      SCORE_REFUSED("observed value … unavailable") }
```

Any other post-T status from a `PRE_T_EVALUABLE` hypothesis is a **classifier defect**, not a
data property. Asserted unconditionally (§15) over the exposed 50 and every synthetic case.

---

### S5 · SELECTABLE UNIVERSE (`PRE_T_EVALUABLE_IR_SPACE`)

| | |
|---|---|
| **input** | `ADMISSIBLE_IR` + S4 verdict per candidate |
| **output** | the ordered list of `PRE_T_EVALUABLE` candidate dicts, structural fields only |
| **success** | non-empty → `MEASURABLE_UNIVERSE_REACHABLE` |
| **failure** | `EMPTY_EVALUABLE_UNIVERSE` (fixture is not pilot-eligible; **never** silently substituted) |
| **PIT** | PIT-STRICT; `FORBIDDEN_OUTCOME_FIELDS` assertion retained from V8B.1 |
| **determinism** | sorted by `(capability_status_rank, n_conditions, ir_id)` — all structural |
| **coverage** | `test_experiment_end_to_end_reachability.py::MEASURABLE_UNIVERSE_REACHABLE` |
| **reachability** | exposed-50 replay + sealed-947 preflight |

**This is measurability control, not outcome cherry-picking (§7/§9).** The filter reads no
target observation, no effect, no score and no direction. It removes only hypotheses the
deterministic engine can already prove it will be unable to measure.

---

### S6 · S ARM (Sonnet)

| | |
|---|---|
| **input** | evidence packet + `search()` over `PRE_T_EVALUABLE_IR_SPACE` |
| **output** | ≤ K canonical hypothesis ids + prose |
| **success** | `OK` with ≥1 valid selection |
| **failure** | `OK_ABSTAIN` (legitimate, preserved), `INVALID_UNKNOWN_HYPOTHESIS_ID` |
| **PIT** | the model sees structural fields only — no effect, no outcome, no historical result |
| **determinism** | **not required** (the model is the treatment). Its *selections* are frozen before any outcome is opened. |
| **coverage** | `test_experiment_end_to_end_reachability.py` (synthetic S-style selector) |
| **reachability** | 249 valid selections over 50 fixtures in V8B.1 |
| **NEW SPEND** | **zero in this mission.** Football reasoning prompt unchanged (§9); the only change is *which* candidates `search` returns. |

---

### S7 · R ARM (matched blind control)

| | |
|---|---|
| **input** | `SonnetShape` (six structural fields, no prose) + `PRE_T_EVALUABLE_IR_SPACE` |
| **output** | one control per Sonnet selection, in Sonnet's own order, sized to `K_valid(T)` |
| **success** | `MATCHED` with **`R_ID != S_ID`, mandatory** |
| **failure** | `UNMATCHED_DISTINCT_CONTROL` — explicit, never fabricated, never duplicated |
| **PIT** | PIT-STRICT. No prose, no outcome, no scorer output. |
| **determinism** | frozen tier order `EXACT → CONDITIONS_PM1 → CAPABILITY_EITHER → MECHANISM_FAMILY → SIDE_EITHER → UNMATCHED`; ties broken by `ir_id` |
| **coverage** | `test_controls.py`, `test_experiment_end_to_end_reachability.py::R_IDENTITY_COUNT == 0` |
| **reachability** | `DISTINCT_R_COVERAGE` over exposed-50 + sealed-947 structure |
| **repairs** | `D-V8C-P1-RIDENT` |

The **only** new hard condition is `candidate_id != Sonnet_id`, applied per pair, seeded into
the existing exclusion set (§11). The tier hierarchy is otherwise untouched. The freeze
refuses if `MATCHED_BLIND_IDENTITY_COUNT > 0` (§12).

---

### S8 · H ARM (deterministic heuristic)

| | |
|---|---|
| **input** | `K_valid(T)` + `PRE_T_EVALUABLE_IR_SPACE` |
| **output** | top-`K_valid(T)` by the **frozen, unmodified** `heuristic_score` |
| **success** | ≥1 selection |
| **failure** | `H_UNAVAILABLE_EMPTY_UNIVERSE` |
| **PIT** | PIT-STRICT |
| **determinism** | `sort(-score, ir_id)` over the **full** evaluable set |
| **coverage** | `test_controls.py`, unconditional `H_SCORE_OK_REACHABLE` assertion (§14) |
| **reachability** | proven on synthetic golden + exposed-50 replay |
| **repairs** | `D-V8C-P1-HUNIVERSE` |

Ranking formula and all five coefficients are imported byte-identically from
`hypothesis_v8b1.controls` (§13). Only the **candidate set** changes, so that all three arms
answer the same question: *which measurable hypothesis should be selected?*

---

### S9 · ALL-ARM FREEZE

| | |
|---|---|
| **input** | S, R, H selections for every fixture |
| **output** | signed freeze record: ids, shapes, tiers, `K_valid`, hashes |
| **success** | written, hashed, committed **before** any target outcome is read |
| **failure** | `FREEZE_REFUSED` (see S16) |
| **PIT** | this is the seal. Nothing after it may change anything before it. |
| **determinism** | byte-identical manifest for identical inputs (§28) |
| **coverage** | `test_determinism.py` |

---

### S10 · TARGET OUTCOME

| | |
|---|---|
| **input** | frozen selections + target `rec_i` |
| **output** | the single observed value for the target fixture's own metric |
| **success** | `observed is not None` |
| **failure** | `SCORE_REFUSED("observed value … unavailable")` — **NULL is never ZERO** |
| **PIT** | the **only** permitted seal crossing, through `compiler.compile_query`, after S9 |
| **coverage** | `test_negative_battery.py::test_null_target` |
| **reachability** | exposed 50 only. **The 947 are never opened in this mission.** |

---

### S11 · FIXTURE SCORER

| | |
|---|---|
| **input** | IR, index, `rec_i`, per-target PIT context |
| **output** | `FixtureScore(status, score, …)` |
| **success** | `SCORE_OK` |
| **failure** | `SCORE_REFUSED`, `SCORE_INSUFFICIENT_SUPPORT`, `SCORE_UNDEFINED` |
| **PIT** | cohort/baseline PIT-STRICT; target observed read once |
| **determinism** | pure function of `(IR, corpus, context)` |
| **coverage** | `tests/research/hypothesis_v8b2/test_scorer.py` (retained) + V8C reachability suite |
| **reachability** | `S/R/H_SCORE_OK_REACHABLE`, **unconditional** (§15) |
| **formula** | `score = ((observed − b̂)² − (observed − ĉ)²) / weighted_var(cohort)`, higher-is-better — unchanged from V8B.2 |

---

### S12 · ARM AGGREGATION

| | |
|---|---|
| **input** | per-fixture, per-arm `FixtureScore` list |
| **output** | `ARM_SCORE(T)` per arm |
| **success** | a float |
| **failure** | `None` when the arm has **zero** `SCORE_OK` at `T` — never coerced to `0.0` |
| **determinism** | equal-weight mean over the arm's own `SCORE_OK` selections |
| **coverage** | `test_aggregation.py` — six predeclared cases (§18) |

Predeclared aggregation cases, all asserted:

| case | expected |
|---|---|
| exactly 1 `SCORE_OK` | that score |
| several `SCORE_OK` | equal-weight mean |
| some OK + some unsupported | mean of the OK subset only; attrition ledgered |
| arm abstained (`K_valid = 0`) | `None` |
| R `UNMATCHED` for every selection | `None` |
| `INVALID_UNKNOWN_HYPOTHESIS_ID` | excluded from the mean, counted in yield |

---

### S13/S14 · PAIRED S-v-R and S-v-H

| | |
|---|---|
| **input** | `ARM_SCORE_S(T)`, `ARM_SCORE_R(T)`, `ARM_SCORE_H(T)` |
| **output** | `D_R(T) = S − R`, `D_H(T) = S − H` |
| **success** | `PAIRED_SR_REACHABLE`, `PAIRED_SH_REACHABLE` |
| **failure** | fixture contributes nothing when **either** side is `None` (**listwise**) |
| **PIT** | post-freeze only |
| **determinism** | fixture order from the frozen manifest |
| **coverage** | `test_aggregation.py` |

Hard rules, tested: **no silent fixture substitution**, **no cross-fixture pairing**, at most
one value per fixture per endpoint. Explicit handling asserted for: S valid / R unavailable,
S valid / H unavailable, S abstains, R unmatched.

---

### S15 · INFERENCE

| | |
|---|---|
| **input** | paired differences + chronological block labels |
| **output** | `small_cluster_inference(...)` verbatim from `hypothesis_v71.estimator` |
| **success** | `inference_status == "EXACT"` (`3 ≤ G ≤ 20`, exact enumerated sign-flip) |
| **failure** | `INSUFFICIENT_CLUSTERS_FOR_INFERENCE` (`G < 3`) — an **explicit, predeclared small-N state**, never an invented p-value |
| **determinism** | exact enumeration; no sampling, no seed |
| **coverage** | `test_aggregation.py::test_inference_small_n_state`, `::test_inference_exact_state` |
| **repairs** | `D-V8C-P1-INFSIZE` |

**Pilot-scoped blocking rule, predeclared here, derived from the estimator's own frozen
bounds — not from any result (§20/§26).** The 1000-fixture blocks stay frozen for the full
experiment. A *pilot* of `n` fixtures gets its own blocks over the pilot's own kickoff order:

```
G(n) = min(MAX_ENUMERATED_G, max(SIGN_FLIP_MIN_CLUSTERS, floor(n / MIN_FIXTURES_PER_BLOCK)))
     = min(20, max(3, floor(n / 5)))
```

`MIN_FIXTURES_PER_BLOCK = 5` is the smallest block for which a block mean is an average rather
than a single fixture restated; `3` and `20` are `estimator.SIGN_FLIP_MIN_CLUSTERS` and
`estimator.MAX_ENUMERATED_G`, both frozen upstream and not chosen here. Blocks are contiguous
in kickoff order, ceiling-divided. `INFERENCE_REACHABLE` means **the semantics are defined and
the small-N state is returned explicitly at the intended size** — it does *not* mean a
significant p-value, and no p-value is required to pass (§20).

---

### S16 · RESULT / FREEZE GATE

`V8C_FREEZE = REFUSED` unless **every** condition holds. No override flag (§33).

```
P0_OPEN == 0                          PRE_T_EVALUABLE_UNIVERSE_REACHABLE == true
P1_OPEN == 0                          DISTINCT_R_REACHABLE == true
END_TO_END_REACHABILITY == PASS       R_IDENTITY_COUNT == 0
SCORE_OK_SYNTHETIC_REACHABLE == true  H_REACHABLE == true
SCORE_OK_REAL_CORPUS_REACHABLE == true
PAIRED_SR_REACHABLE == true           AGGREGATION_REACHABLE == true
PAIRED_SH_REACHABLE == true           INFERENCE_REACHABLE == true
PIT == PASS                           DETERMINISM == PASS
CHAMPION_UNCHANGED == true
```

**No PASS by definition (§34).** Every boolean in `V8C_FREEZE_MANIFEST.json` is bound to a
test-artifact hash, the sha256 of the code module that produced it, and the input corpus/
fixture identity. A hardcoded `true` with no evidence hash is itself a freeze refusal.

---

## 3. Pilot eligibility rule (§26), derived before any Sonnet call

A fixture is `PILOT_ELIGIBLE` iff:

```
pre_t_evaluable_candidates >= K_MIN   AND   distinct_R_feasible   AND   H_feasible
```

`K_MIN` is derived **operationally**, from what the experiment structurally needs at one
fixture, not tuned to yield a target fixture count (§26 explicitly forbids that):

| requirement | candidates consumed |
|---|---|
| S must have a genuine *choice*, not a forced pick | ≥ 2 |
| R must find a control distinct from S | ≥ 1 more |
| H must rank rather than restate S's pick | ≥ 1 more |
| **`K_MIN`** | **4** |

`distinct_R_feasible` = at least one `PRE_T_EVALUABLE` candidate exists that is not the
hypothetical S pick, under the frozen tier hierarchy. `H_feasible` = the evaluable set is
non-empty. All three conditions are **structural**; none reads an outcome, an effect, a score
or a direction (§27).

---

## 4. Evidence-class discipline

| corpus | class | permitted use |
|---|---|---|
| exposed 50 | `DEVELOPMENT / APPARATUS_DIAGNOSTIC` | support distributions, control-distinctness, endpoint reachability, aggregation debugging, real-corpus regression |
| exposed 50 | — | **may NOT** be used to claim fresh Sonnet advantage, or to choose any threshold (§21) |
| sealed 947 | `SEALED` | **pre-T structure only.** No scoring, no target observation, no settlement. `SEALED_947_OUTCOMES_VIEWED = false`, enforced by the target-blind index wrapper's read-audit log. |

No threshold in V8C is chosen by reference to any arm's score, sign or magnitude. The one
numeric change inherited from V8B.2 (`unique_teams` → `unique_opponents`) was a unit
correction, argued from the V7.1 docstring's own stated purpose, and is retained unchanged.
