# V8C readiness report

**Branch** `feat/v8c-experiment-repair` (from `938acaf58`)
**Status** `V8C_FREEZE = REFUSED` — 17 of 18 gate conditions PASS; one artifact deliberately not produced
**CHAMPION** `0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9` — unchanged before and after
**Sonnet calls** 0 · **Spend** $0 · **Sealed-947 outcomes viewed** false

---

## 1. Headline

Every defect named in the repair mission is closed, each with a test. The freeze gate refuses on
exactly one condition — `SEALED_947_OUTCOMES_NOT_VIEWED` — because its evidence artifact,
`V8C_SEALED947_STRUCTURAL_PREFLIGHT.json`, does not exist: **the preflight was deliberately not
run on instruction.**

That refusal is the gate working. An absent artifact evaluates to `FALSE`, never to a default
`TRUE`, and there is no override flag.

`READY_FOR_PAID_FRESH_PILOT = false` — because sealed-reserve coverage is unknown, **not**
because defects remain.

---

## 2. Defect dispositions

| id | class | disposition | proof |
|---|---|---|---|
| `OUTCOME-SEAL` | **P0** | **CLOSED** — two physically separate processes | `test_two_process_seal_end_to_end` spawns process 1, waits for it to exit, then spawns process 2 |
| `CTXCUT` | **P0** | **CLOSED** — per-target strict `< T` context, regression-protected | `test_pit_adversarial.py` ×4 |
| `PROFILE-COMP` | P1 | **CLOSED** — `(team, competition, axis, T)` | `test_compiler_equivalence.py` ×2 |
| `UNIVERSE-GRAMMAR` | P1 | **CLOSED** — declared grammar, spec written before code | `test_universe_grammar.py` |
| `SEARCH-REACHABILITY` | P1 | **CLOSED** — deterministic pagination, `unreachable == 0` computed | `test_search_reachability_is_total` |
| `MEASSPACE` | P1 | **CLOSED** — two projections + live control | hiding *and* retention tests |
| `PACKET-RAW` | P1 | **CLOSED** — match-level rows, FOR+AGAINST, `_REF_POS` gone | serial-vs-parallel hash equivalence |
| `RUNNER-WIRE` | P1 | **CLOSED** — search answers from the V8C universe | `test_packet_runner.py` |
| `CACHE` | P1 | **CLOSED** — new namespace, 12-field identity | V8B-poison refusal test |
| `R CONTROL` | P1 | **CLOSED** — all Sonnet ids excluded, asserted | `test_controls_pairing.py` |
| `R PAIRING` | P1 | **CLOSED** — matched-pair estimand, triples persisted | `test_sr_is_matched_pair_not_arm_mean` |
| `H` | P1 | **CLOSED** — frozen formula, whole universe, unpaired | `test_h_picks_the_true_argmax_not_the_first_page` |
| `INVALID-S` | P1 | **CLOSED** — explicit terminal states | `test_invalid_sonnet_id_is_an_explicit_terminal_state` |
| `INFERENCE` | P1 | **CLOSED** — qualifying-block rule | 4 / 14 / 15 regression tests |
| `ENV-SEASON` | P1 | **CLOSED** — documented, not silently re-implemented | `V8C_SCORE_STABILITY_AUDIT` + `env_semantics.py` |
| `GOLDEN` | P1 | **CLOSED** — one metric mutated | `test_negative_mutations_are_one_dimension_at_a_time` |
| `BLIND-SEAL` | P1 | **CLOSED** — `.vals`/`.recs` sealed, sanitized records | `test_blind_index_seals_every_documented_accessor` |
| `RESEARCH-FAMILY` | P1 | **CLOSED** — structural map, prose-free | `test_research_family_is_total_and_prose_free` |
| `SCORE-STABILITY` | P1 | **AUDITED, NO CHANGE** | see §5 |

**New defects found and fixed during the repair** (both mine, both regression-tested):
`GR.resolve` re-walked the whole grammar per id (millions of redundant IR builds) → memoized;
its first cache key used `id(capability)`, which CPython reuses after GC and could serve one
contract's map for another → content fingerprint.

**P2 logged, not acted on:** `P2-GRAMMAR-WINDOW` (below), `P2-GRAMMAR-TARGETVENUE` (the compiler
implements `TARGET_VENUE`/`TARGET_VENUE_OPPONENT`, the ontology does not declare them).

---

## 3. What the repaired apparatus demonstrates

A real 15-fixture, two-stage synthetic run (`V8C_END_TO_END_REACHABILITY.json`):

```
S SCORE_OK  45      R SCORE_OK  45      H SCORE_OK  45
S-v-R paired n = 15   (MATCHED-PAIR estimand)
S-v-H paired n = 15   (ARM-MEAN estimand — deliberately different, never comparable)
R_IDENTITY_COUNT                  0
R_CROSS_TREATMENT_OVERLAP_COUNT   0
PAIR_IDENTITY_PRESERVED           true
unreachable_candidate_count       0
target_outcomes_viewed_during_selection   false
```

`PRE_T_EVALUABLE ⇒ post-T ∈ {SCORE_OK, SCORE_REFUSED(observed unavailable)}` holds with **zero
violations** across every scored selection.

**83 tests pass, 0 fail.**

---

## 4. Two numbers that must not be read together

**5 / 249 (2.0%)** — the share of *historical V8B.1 Sonnet selections* that are pre-T evaluable.
This measures the **old** apparatus under the **old** grammar. It diagnoses the measurement-space
defect and **predicts nothing** about a V8C pilot.

**~900 per fixture** — the pre-T evaluable universe under the V8C grammar on the real corpus
(202,176 admissible). This is the space a V8C pilot would actually select from.

Placing these side by side as though the first forecasts the second would be wrong.

---

## 5. Score stability — audited, thresholds untouched

Outcome-blind, over 10,750 cohorts from the exposed-50 development corpus:

| quantity | value |
|---|---|
| `ZERO_VARIANCE_FLOOR` | `1e-18` |
| min observed `scale_var` | **0.033** — 31 orders of magnitude above the floor |
| cohorts with `scale_var < 1e-6` | **0** |
| largest standardized value of a one-unit raw improvement | 30.3 |

No outcome-blind failure is demonstrated, so **no threshold is changed**. The support gate
(`MIN_RAW_N=20`, `MIN_UNIQUE_OPPONENTS=6`, `MIN_EFFECTIVE_N=10`) — not the variance floor — is
what bounds the ratio.

---

## 6. For the reviewer: W5/W10 achieved nothing measurable

The grammar restores `W5` and `W10`, tripling the enumerated space. But a `W5` cohort holds at
most 5 observations and `W10` at most 10, and `MIN_RAW_N = 20`. **Neither window can ever clear
the support gate**, so both are structurally absent from every evaluable universe.

Restoring them was still correct — the space is now *declared* rather than an accident of a
default argument, and their exclusion is now *reported* (`PRE_T_INSUFFICIENT_RAW_N`) rather than
silently invisible. But nobody should expect them to appear in a pilot.

Whether the support thresholds should have a window-aware form is a **scientific** question
about the scorer, not an apparatus defect. Changing `MIN_RAW_N` here would be altering a
threshold mid-mission. Logged as `P2-GRAMMAR-WINDOW`.

---

## 7. What stands between here and a freeze

One thing: run `_run_v8c_sealed947_preflight.py`.

It is written and verified — the sealed reserve derives to exactly **947**
(1000 manifest − 50 exposed − 3 T2 canaries, canary ids read from `V8B1_CANARY_RESULTS.json`
rather than hardcoded, and asserted). Every read goes through `TargetBlindIndex`, so
`SEALED_947_OUTCOMES_VIEWED` would be a **mechanical** result.

**Cost:** 61 s/fixture measured on the real corpus under the V8C grammar → 947 fixtures ÷ 4
cores ≈ **4 hours**. That is why withholding it is a real decision rather than an omission.

After it runs, the gate needs no other input: the remaining 17 conditions already hold.
