# SONNET46_HYPOTHESIS_V3 — Preregistration

**Bedrock inference calls made: 0.** Nothing below was run against a model. Every number is
computed offline from frozen JSON and frozen code.

**Status:** `SONNET46_HYPOTHESIS_V3_SPEND_AUTHORIZATION_REQUIRED`
**Manifest hash:** `cfd9244067c9dc0ca18140f1d02460e9833b1df820cff7070713df6f6f8cce3f`

**V2 is untouched.** `SONNET46_HYPOTHESIS_V2 = FAIL` stands permanently and is not
reinterpreted anywhere here. No file under `out/hypothesis_v1_sonnet46_v2/` was written
(verified: zero files modified since the V2 run closed). Every frozen V2 fact listed in the
task is carried forward as given and is used only to *set bars*, never to re-score V2.

**Production architecture untouched.** No change to CHAMPION, `p_model`, calibration, the
prediction engine, market comparison or prospective publication. No hypothesis becomes a
predictive feature. No deterministic effect estimation is part of this experiment.

---

## 1. The V3 scientific question

> When given a corrected typed contract and an explicit but non-forcing research ontology,
> can Sonnet 4.6 generate fixture-specific, evidence-grounded, deterministic-query-compilable
> conditional football hypotheses that go beyond trivial single-dimension baseline
> comparisons while preserving restraint and capability awareness?

Explicitly **not**: a football prediction experiment; a test of whether any hypothesis is
statistically true. It tests whether Sonnet is useful as the project's *hypothesis-generation
research layer*.

---

## 2. The exact battery — 56 calls

Sized per control by what each has to answer. V2's 64 was not reused by default.

| Control | Calls | Packet | What it answers |
|---|---|---|---|
| `reference` | 12 | frozen reference, as-is | the primary arm; **the only arm** depth and restraint are measured on |
| `repeatability` | 12 | reference packet + hash, unchanged | the same-input noise floor — the **denominator** of gates D12/D13 |
| `identity_alias` | 6 | `controls.identity_alias` | invariance to synthetic display labels |
| `irrelevant_field` | 6 | `controls.irrelevant_field` | invariance to a provably irrelevant note |
| `profile_axis_perturbation` | 6 | `controls_v3` (**new**) | does opponent-profile **axis selection** track the evidence? |
| `availability_ablation` | 6 | `controls_v3` (**new**) | capability boundary; paired with the untouched reference arm |
| `evidence_starvation` | 4 | `controls.evidence_starvation` | abstention rather than invention |
| `unsupported_data_trap` | 4 | `controls.unsupported_data_trap` | capability awareness under bait |
| **Total** | **56** | 44 unique packets | |

**Dropped from V2, with reasons:**

- `venue_flip` (−6): V3's depth question is about conditioning *beyond* venue; venue
  sensitivity is already covered by the availability ablation and the axis perturbation.
- `formation_ablation` (−6): formation is genuinely **contrastive in only 3 of 12** fixtures,
  so an ablation arm would have at most 3 informative cases. **Consequence, stated plainly:
  V3 measures formation utilization on those 3 fixtures and does not control it. No formation
  claim can be made in either direction at N=3**, and `formation_use_rate` must not be read as
  a finding.

**Deliberately over-sampled:** `repeatability` is 6 fixtures × 2 repeats = 12 calls → 3
samples per fixture → **18 same-input pairs**. That median is the denominator of two hard
gates; a noisy floor would turn a borderline identity result into a coin flip. Four extra
calls is the cheapest reliability in the battery.

**Context-addition control — rejected, with reasons recorded in code**
(`controls_v3.CONTEXT_ADDITION_REJECTION`): no packet builder over the raw corpus exists in
the frozen chain, so a second horizon or venue-split evidence item would have to be *derived*
by new code; its point-in-time safety could not be shown without rebuilding and re-auditing
the corpus pipeline; and fabricating values would create a synthetic football effect, which
the design forbids. **Clean substitute:** `availability_ablation` is run as a paired contrast
whose "with the dimension" arm is the **untouched frozen reference packet**, so the addition
direction is measured against real data and nothing is fabricated.

Repeatability fixtures, call order and per-control fixture selection are all "the first *n*
in frozen battery order" — no selection choice is left open.

---

## 3. Fixture capability matrix

Recomputed from each frozen packet's manifest, evidence scopes and formation distribution.
`Y` = AVAILABLE (counts in a depth denominator) · `low` = AVAILABLE_LOW_CONTRAST ·
`noev` = COMPILE_AVAILABLE_NO_EVIDENCE · `—` = WITHHELD. **Only `Y` enters a denominator.**

| Fixture | venue | comp | opp_profile | own_form | opp_form | half_state | period | #axes | stratum |
|---|---|---|---|---|---|---|---|---|---|
| mt_010441491 | Y | Y | Y | low | low | — | — | 12 | FORMATION_RICH |
| mt_012232295 | Y | Y | Y | — | — | — | — | 12 | FORMATION_SPARSE |
| mt_010243515 | Y | Y | Y | low | low | — | — | 12 | HIGH_CORNER_PROFILE |
| mt_010243938 | Y | Y | Y | low | low | — | — | 12 | LOW_CORNER_PROFILE |
| **mt_010441320** | Y | Y | Y | **Y** | **Y** | — | — | 12 | HIGH_CARD_PROFILE |
| **mt_010244193** | Y | Y | Y | **Y** | **Y** | — | — | 12 | HIGH_SHOT_VOLUME |
| mt_010244159 | Y | Y | Y | low | low | — | — | 12 | HOME_AWAY_ASYMMETRIC |
| mt_013233190 | Y | Y | Y | low | low | — | — | 12 | THIN_HISTORY |
| **mt_010444904** | Y | Y | Y | **Y** | **Y** | — | — | 12 | FORMATION_RICH |
| mt_012232411 | Y | Y | Y | — | — | — | — | 12 | FORMATION_SPARSE |
| mt_010243537 | Y | Y | Y | — | — | — | — | 12 | HIGH_CORNER_PROFILE |
| mt_010443150 | Y | Y | Y | low | low | — | — | 12 | LOW_CORNER_PROFILE |

**Comparison availability (identical in all 12):** `SUBJECT_OVERALL_BASELINE` Y ·
`SUBJECT_COMPETITION_BASELINE` Y · `SUBJECT_VENUE_BASELINE` noev ·
`SUBJECT_RECENT_VS_LONG_BASELINE` noev · `LEAGUE_ENVIRONMENT_BASELINE` noev.

### Frozen depth denominators

| Dimension | Denominator | Eligible fixtures |
|---|---|---|
| `venue` | **12** | all |
| `competition` | **12** | all |
| `opponent_profile` | **12** | all |
| `own_formation_family` | **3** | mt_010244193, mt_010441320, mt_010444904 |
| `opponent_formation_family` | **3** | same three |
| `half_score_state`, `period` | **no denominator at all** | none — excluded, never a zero |

So `formation_use_rate` = formation hypotheses **/ 3**, never / 12. A dimension withheld
everywhere gets **no denominator**, not a zero numerator.

### Axis availability — a latent contract hole found and closed pre-spend

`vocabulary.PROFILE_AXES` asserts "every axis must be a supported metric". Two entries break
that: **`shots_for` and `shots_against` have no `shots` metric** (the canonical name is
`total_shots`). Such a condition passes schema-v2 *and* passes the frozen compiler — which
only checks membership in `PROFILE_AXES` — and then has no metric for the measurement layer
to resolve a band from. **This is the same class of defect as the V2 venue-casing mismatch.**

`vocabulary.py` is **not** edited (V2's `schema_content_hash` and `battery_hash` are recorded
over it). Instead the axis is gated **twice**:

1. absent from `fixture_condition_space`, so the model never sees it;
2. rejected at validation (`UNSUPPORTED_CONTEXT_SOURCE`) if emitted anyway.

Exposure alone is not a contract. A dimension whose *every* axis is unresolvable for a
fixture is marked WITHHELD outright. Pinned at **exactly 2** entries by
`test_the_axis_metric_hole_is_exactly_two_known_entries`, so a future vocabulary addition
breaks the test rather than silently widening the hole. Per fixture, **12 of 15** axes are
offered (`shots_for`, `shots_against` inventory-broken; `total_bookings_for` not available
for these fixtures).

---

## 4. Hypothesis schema

`hypothesis_set_schema_v2` — hash `7879c6ad5a2ba9265f69a4e7e808d6bfd53144a7348d5788d2676b8135e86077`.

- `conditions[].value` is a **closed enum, narrowed per dimension** by `if/then`;
- `axis` **required** where the dimension declares axes, **forbidden** where it does not;
- every enum is **generated from** `condition_contract`, which projects
  `vocabulary.DIMENSIONS` — no layer redeclares an enum;
- unknown values **fail closed** with a precise path and a named reason;
- **whole-response rejection is retained** (see §9).

Boundary order is fixed: **canonicalize → validate → compile**. The compiler is the
**unchanged frozen v1 compiler**; canonicalization makes its enum check unreachable-by-
encoding rather than patching it.

Prompt: `hypothesis_analyst_prompt_v2`, hash
`821e48ea5d98049b9d7e058ca543463467c3d94ad6f46255f68bb7b2d933509c`. It exposes raw and
opponent attacking/defensive profiles, venue, formation where available, competition and the
supported interactions — and **requires none of them**. It contains no "you must produce a
two-condition hypothesis", no quota for profile/formation/multi-condition/interaction
hypotheses, and states explicitly that a plain unconditional baseline comparison is *"a
correct and complete answer"* when best-supported. The grammar examples list the
**unconditional shape first** and name no team, metric, family or football story — asserted by
`test_prompt_v2_worked_examples_name_no_team_metric_or_football_story`.

---

## 5. Meaningful multi-condition definition — `meaningful_multicondition_v1`, FROZEN

`len(conditions) >= 2` is explicitly **not** the definition. A hypothesis qualifies only if it
survives six independent checks:

1. **≥2 distinct legs** after dropping `ANY` values (padding) and `period=ALL`. Leg identity
   is `(dimension, axis)`, so two profile conditions on the same axis are one leg.
2. **Every leg's dimension is AVAILABLE** for that fixture — read from the *dimension's*
   status, never the comparison's. `LOW_CONTRAST` does not qualify: a formation condition on a
   single-family fixture compares a cohort with itself.
3. **Every axis-bearing leg names a fixture-resolvable axis.**
4. **No duplicate or aliased legs** — `home` and `HOME` canonicalize to one leg.
5. **No contradictory legs** on one dimension (the cohort would be empty).
6. **Not degenerate against the comparison** — `venue=HOME` + `SUBJECT_VENUE_BASELINE` makes
   the cohort *be* the baseline. The compiler accepts this happily, which is exactly why the
   check exists.

Plus: **it must compile, fully.** *All* plans must be `ok`, matching `compile_set`'s
`n_fully_compilable` so depth and gate D3 can never disagree.

It does **not** decide whether the interaction has a real effect — that is downstream.

**Measured baseline: 0 of 132** V2-replayed hypotheses qualify (asserted by
`test_the_classifier_scores_zero_on_the_frozen_v2_reference_responses`).

---

## 6. Controls

**`profile_axis_perturbation`** (new) — scales the away side's **offensive** shot profile
(`shots_on_target_for` + `total_shots_for`, moved together and in the same direction:
×1.60 raise / ×0.55 lower, a frozen 3/3 split). Disjoint from V2's *defensive* surface
(`corners_against`, `accurate_crosses_against`), which is what makes it a test of **axis
selection** rather than a rerun of V2's sensitivity control. `shots_on_target_for` is a
resolvable axis, so an evidence-driven model has a legal axis to move *to*. No note is added —
a note saying "this was perturbed" would be an instruction, not evidence.

- **Gated (D14):** intent delta must touch the perturbed surface. Arbitrary churn is not
  sensitivity.
- **Reported, not gated:** did the *chosen axis* move toward the perturbed family? Returns
  `None` ("not measurable") when neither arm used any profile axis — scoring that False would
  penalise the model for a measurement we could not make.

**`availability_ablation`** (new) — withdraws `opponent_profile` from the manifest while
leaving **all evidence intact**. The question is whether the model respects a stated capability
boundary with the numbers still in front of it.

- **Gated (R1):** zero conditions on the withdrawn dimension. N-independent, so it is
  gateable.
- **Reported:** `profile_disappearance_rate` = ablated responses with zero profile conditions
  **/ ablation-paired fixtures whose reference response contained ≥1 profile condition**. If
  that denominator is **< 3**, the control reports `INSUFFICIENT_N` rather than a rate — it is
  a denominator the *subject* controls, so it cannot be a hard gate.

**Carried over unchanged:** `repeatability`, `identity_alias`, `irrelevant_field`,
`evidence_starvation`, `unsupported_data_trap`.

All transforms are pure, deterministic, non-mutating, and hash-verified pre-spend.

---

## 7. Eligibility-aware metrics

Depth and restraint are computed on the **12 reference responses only**; discipline on all 56
calls. Every depth denominator comes from §3.

| Reported quantity | Numerator | Denominator |
|---|---|---|
| meaningful multi-condition rate | hypotheses passing the §5 classifier | accepted reference hypotheses |
| condition-count distribution | — | restricting legs per hypothesis |
| opponent-profile utilization | fixtures with ≥1 profile condition | **12** (AVAILABLE everywhere) |
| formation utilization | fixtures with ≥1 formation condition | **3** (contrastive only) |
| venue-only rate | intents whose only condition is venue | all reference intents |
| overall-baseline comparison rate | intents naming `SUBJECT_OVERALL_BASELINE` | all reference intents |
| comparison-cohort diversity | Shannon entropy over comparisons | — |
| condition-family diversity | distinct condition dimensions used | — |
| interaction-family diversity | distinct `frozenset(leg dimensions)` | — |
| **restraint** | ANY-padding, withheld-dimension conditions, gratuitous rate, abstention | all conditions / starved calls |

**"More conditions = better" is explicitly not the success definition.** Depth is a 3-of-4
composite; the restraint gates are what stop it being bought with padding.

---

## 8. Frozen thresholds — 14 discipline + 5 restraint + 4 depth

Full specification (statement, numerator, denominator, direction, threshold, minimum N,
rationale, fail-closed) lives in `verdict_v3.py` and is hashed into the manifest. Summary:

### Discipline — hard gates, all must be met

| Key | Metric | Bar | Min N |
|---|---|---|---|
| D1 | not rejected as SCHEMA_INVALID | ≥ 0.95 | 56 |
| D2 | survives every whole-response gate | ≥ 0.90 | 56 |
| D3 | query compilability | ≥ 0.85 | 60 |
| D4 | evidence grounding | ≥ 0.95 | 60 |
| D5 | fabricated evidence ids | **= 0** | 56 |
| D6 | unavailable capability requests | ≤ 0.05 | 60 |
| D7 | numerical-authority violations (classes A+B) | **= 0** | 56 |
| D8 | latent grading violations | **= 0** | 56 |
| D9 | leakage findings | **= 0** | 56 |
| D10 | median redundancy | ≤ 0.35 | 12 |
| D11 | median metric richness | ≥ 5 | 12 |
| D12 | identity invariance **relative to the measured floor** | ratio ≥ 0.90 | 6 |
| D13 | irrelevant invariance **relative to the measured floor** | ratio ≥ 0.90 | 6 |
| D14 | evidence sensitivity (perturbed surface) | ≥ 0.50 | 6 |

### Restraint — hard gates, all must be met

| Key | Metric | Bar | Min N |
|---|---|---|---|
| R1 | conditions on withheld dimensions | **= 0** | 56 |
| R2 | gratuitous condition rate | ≤ 0.05 | 60 |
| R3 | ANY-padding rate | ≤ 0.02 | 60 |
| R4 | trap responses inventing evidence/context | **= 0** | 4 |
| R5 | abstention on starved packets (**corrected definition**) | ≥ 0.70 | 4 |

### Depth — 3-of-4 composite, each anchored to a measured V2 baseline

| Key | Metric | V2 replay | V3 bar | Min N |
|---|---|---|---|---|
| P1 | meaningful multi-condition rate | **0.000** | ≥ **0.10** | 60 |
| P2 | beyond-venue condition rate | **0.062** | ≥ **0.20** | 60 |
| P3 | opponent-profile fixture utilization | **0.333** | ≥ **0.50** | 8 |
| P4 | comparison entropy (bits, max 2.32) | **0.299** | ≥ **0.60** | 60 |

**Which V2 thresholds were reused, and why.** D3/D4/D6/D10/D11 are V2's bars retained
unchanged — they are contract properties, and the corrected ontology gives no reason to move
them. D7/D8 keep zero tolerance. **D12/D13 are deliberately not V2's**: V2 required absolute
Jaccard ≥ 0.80 while the generator's own same-input floor measured 0.333, so the gate measured
sampling noise rather than identity sensitivity; V3 judges both relative to the measured
floor. **R5 keeps V2's 0.70 but with the corrected definition** in which an empty hypothesis
set is *full* abstention (V2 scored the ideal answer as 0.0).

### Verdict rule — mechanically reproducible

```
FAIL   if any DISCIPLINE or RESTRAINT gate is not met, OR fewer than 2 DEPTH criteria met
MIXED  if all gates met AND exactly 2 DEPTH criteria met
PASS   if all gates met AND at least 3 DEPTH criteria met
```

- **A single multi-condition hypothesis is not sufficient for PASS** (1/144 = 0.007 → P1 unmet
  → 0 depth criteria → FAIL). Asserted by test.
- **Universal interaction generation is not required** — 0.12 / 0.22 / 0.50 / 0.61 passes all
  four while leaving ~88% of hypotheses single-condition. Asserted by test.
- **Gratuitous complexity cannot buy a pass** — all four depth criteria met with
  `R3_any_padding = 0.40` yields **FAIL**. Asserted by test.
- **Depth alone can never produce PASS.** Asserted by test.
- **Fail-closed on N:** a criterion below its minimum N scores **NOT MET**, never "excluded" —
  excluding it would change the 3-of-4 denominator and make the verdict irreproducible.

**MIXED is a real landing zone, not a hedge.** Every depth criterion has a measured V2 baseline
of ~0. A model clearing two of four has changed behaviour substantially and is still short of
the bar; "disciplined, restrained, partially deeper" is an informative result and must not be
read as an inconclusive run.

### Dry verdict on V2's recorded behaviour

Applying the frozen V3 bar to the V2 replay measurements: **0 of 4 depth criteria met**
(P1 0.000<0.10, P2 0.062<0.20, P3 0.333<0.50, P4 0.299<0.60). Diagnostic only — V2's verdict
is FAIL and is not recomputed. It demonstrates the bar is a **real** bar.

---

## 9. Stop rule — `WHOLE_RESPONSE_SCHEMA_REJECTION_STOP`

Whole-response rejection is **retained**: the V3 model sees the closed enum in its tool spec,
which V2's model never did.

| Element | Frozen value |
|---|---|
| Metric | `n_schema_rejected / n_completed` |
| **Numerator** | completed calls whose whole-response failure is **exactly `SCHEMA_INVALID`**. A `NUMERICAL_AUTHORITY_VIOLATION`, a `LATENT_GRADING_VIOLATION` or a per-hypothesis rejection **does not count** — those are discipline results the experiment exists to measure, and halting on them would destroy the measurement. |
| **Denominator** | completed calls so far, in frozen seq order, across every control arm |
| **Checkpoints** | after calls **12, 24, 36, 48, 56** |
| **Minimum N** | 12 |
| **Threshold** | **≥ 0.25** |

**Rationale for 0.25:** 16 of the 64 frozen V2 responses carry at least one contract-invalid
condition and would be whole-rejected under schema-v2 — the documented 16/64 base rate. V3's
model is *shown* the enum, so 0.25 is exactly the "no better than V2" line. Reaching it means
contract exposure did not work — an infrastructure/prompt failure, not a result about the
model's research ability.

**On trip:** stop inference immediately · preserve every completed call and its provenance ·
write the ledger with `stop_triggered=true` and the tripping checkpoint · declare
`SONNET46_HYPOTHESIS_V3 = INFRASTRUCTURE_OR_PROMPT_FAILURE` · **do not** salvage, repair or
partially accept any malformed response · **do not** compute a PASS/MIXED/FAIL verdict from
the partial battery · **do not** alter the schema, prompt or contract and resume under this
experiment id — a changed contract is a different experiment and requires a new id.

---

## 10. Immutable hashes

| Component | Version | Hash |
|---|---|---|
| **Manifest** | `hypothesis_prespend_manifest_v3` | `cfd9244067c9dc0ca18140f1d02460e9833b1df820cff7070713df6f6f8cce3f` |
| Prompt | `hypothesis_analyst_prompt_v2` | `821e48ea5d98049b9d7e058ca543463467c3d94ad6f46255f68bb7b2d933509c` |
| Schema | `hypothesis_set_schema_v2` | `7879c6ad5a2ba9265f69a4e7e808d6bfd53144a7348d5788d2676b8135e86077` |
| Battery | `hypothesis_battery_v1` | `6e70d6e5c6962058e78ba44b79aad0919a78ff540f3bfb158f1c382d786c414b` |
| condition_contract | `hypothesis_condition_contract_v1` | `ae6a89b07525a77c5e07a7e4d355931bbe4981ab99d2c03689cc01f2515d53af` |
| availability | `hypothesis_availability_v1` | `f485cda74cf7d17b09a08ca35e9dd1eb14b288b546cbd535252f1e93e97bcdf5` |
| firewall_v2 | `numerical_authority_firewall_v2` | `400e89b9ecf79e322a3efb661fd5c26a2e5cb087ba0cfd4e3ad3768a7ab94d48` |
| normalize | `hypothesis_intent_v1` | `60a4dca0adc03107763b461b65739fe48db0387a8fc4bdf00982849f212b1949` |
| query_plan | `query_plan_v1` | `184991835110d940819dcf35375d025876ed10c2df1fee94d1f10861d3f8826c` |
| validator_v2 | `hypothesis_validator_v2` | `2a2dc4e68daa76974b8656125f469427b2291a129e3674a6fafe9fdf2be4c284` |
| evaluation_v2 | `hypothesis_evaluation_v2` | `3a3f4538fa897a195e399210744f0f9f2a4a78aa1a8e935ba932527180e11bad` |
| multicondition | `meaningful_multicondition_v1` | `9c4eeec105f028a5ccb6cc4bfe6564d6ae9b47c5bb7c7660cf6923d75f664b5e` |
| verdict_v3 | `hypothesis_verdict_v3` | `a4bedc4fd393fe4629b141340940a5f3fc48cdd78a8b43b5ffabcfa1862ba274` |
| controls | `hypothesis_controls_v1` | `52a76e3bcf5b3b80edb12fe27a0908ee23f4d377e99e83f8e78f0c84f11edb0f` |
| controls_v3 | `hypothesis_controls_v3` | `2d8e9a08f8a8156134d364dbf2d3d88b084fdab830b01487b0999437bbb4f137` |
| schema_v2 module | — | `a9f96e19c52aa7fd8d5df42ee9051b57429c581837b7b161eb1172fd68522718` |
| prompt_v2 module | — | `80a6ba6685fa62369b28c80375e50bfd7a11805afb182eeff9ec7cb77ddfa596` |
| battery_v3 module | — | `4c43352f315d1b73cb0a3ac9eb8c3efcfd419a7a45d3dce49352a047f710939b` |

Vocabulary `hypothesis_vocabulary_v1`; capability inventory `capability_inventory_v1`.
Every one of the 56 call specs additionally carries its **`resulting_packet_hash`** and a
**`serialized_request_sha256`** over the exact transmitted text.

**Model identity:** `us.anthropic.claude-sonnet-4-6` · profile
`arn:aws:bedrock:us-east-1:865147226910:inference-profile/us.anthropic.claude-sonnet-4-6` ·
region `us-east-1` · `{maxTokens: 8192, temperature: 0.0}` · **not date-pinned** (see §13).

**Lifecycle:** manifest → call spec → packet hash → serialized request → raw response →
validation → normalized intent → compiled query plan → evaluation → verdict.

**Cache namespace** `hypothesis_v3_sonnet46`, isolated: the cache key includes model id,
prompt/schema hash and packet hash, so no V1/V2 or legacy response can ever be served to V3.

---

## 11. Call, token and cost plan

Input tokens are **chars/4 of the exact serialized request** for each of the 56 frozen calls.

| Control | Calls | Mean input (chars/4) | Total |
|---|---|---|---|
| reference | 12 | 13,654 | 163,845 |
| repeatability | 12 | 13,684 | 164,214 |
| identity_alias | 6 | 13,684 | 82,106 |
| irrelevant_field | 6 | 13,694 | 82,167 |
| profile_axis_perturbation | 6 | 13,684 | 82,106 |
| availability_ablation | 6 | 13,656 | 81,933 |
| evidence_starvation | 4 | 4,554 | 18,216 |
| unsupported_data_trap | 4 | 13,732 | 54,928 |
| **Total** | **56** | 13,027 | **729,515** |

**Input-token calibration — a correction V2's manifest did not make.** V2 estimated 770,528
input tokens by chars/4; Bedrock actually billed **1,228,036**. The convention understates
real input by **×1.5938**, so V2's "$8.49 expected" was structurally low. chars/4 is retained
as the primary measurement (exact, reproducible, comparable with V2), but **every cost figure
below is computed on the calibrated count**: 729,515 × 1.5938 = **1,162,701** tokens.

**Output tokens**, frozen from Sonnet 4.6's *own* observed distribution in the completed V2
run (n=64): mean **2,580.1** · median 2,695.5 · **p90 2,957** · max **3,213** · min 110.

At $0.003/1K input and $0.015/1K output:

| Scenario | Output/call | Cost |
|---|---|---|
| Expected (observed mean 2,581) | 2,581 | **$5.66** |
| p90 (2,957) | 2,957 | **$5.97** |
| Observed max (3,213) | 3,213 | **$6.19** |
| **Hard ceiling** — every call returns `maxTokens` | **8,192** | **$10.37** |

The ceiling uses the configured `maxTokens`, not the observed max: it must bound the worst
case the API can actually bill.

---

## 12. Zero-spend verification results

`research/hypothesis_engine/_build_v3.py` — **ALL_CHECKS_PASS: True**. It refuses to write the
manifest if any check fails. Verified:

- call layout is exactly 56 in the frozen shape; `seq` dense and ordered 0–55;
- reference and repeatability bind to the frozen packet hashes, unchanged; repeatability is
  6 fixtures × 2 → 18 same-input pairs;
- every transformed packet is **deterministic**, self-consistent (`packet_hash` recomputes)
  and **non-mutating** (source packets byte-identical after the whole build);
- the profile-axis perturbation moved exactly the two frozen metrics per fixture, with a 3/3
  raise/lower split, on a surface **disjoint from V2's**;
- the availability ablation withdraws the capability and leaves evidence **byte-identical**;
- the prompt never names a withheld dimension and never exposes an unresolvable axis;
- **leakage audit CLEAN — 0 findings** across all 44 materialized packets *and* their exact
  serialized requests;
- **contract soundness on the exact packets that will be sent**: every exposed
  (dimension × value × available axis) combination reaches the compiler with no
  `UNSUPPORTED_DIMENSION` and no `QUERY_INVALID`;
- score-state/period have **no depth denominator**; formation's denominator is 3;
- the verdict function **fails closed** with no measurements, and the stop rule
  short-circuits to `INFRASTRUCTURE_OR_PROMPT_FAILURE`;
- V2's replay meets **0 of 4** depth criteria;
- no `boto3` / `invoke_model` / `bedrock_client` reference in any V3 module.

**Test suite:** `tests/research/hypothesis_engine/` — **487 passed, 1 failed**.

The single failure is **pre-existing and environmental**, unchanged since before any of this
work: `test_architecture_isolation.py::test_champion_produces_p_model_with_the_llm_packages_uninstalled`
— `ModuleNotFoundError: No module named 'sklearn'`. Baseline at the start of the V3
infrastructure task was 272 passed / 1 failed (same test, same cause).

One **new** failure appeared during this task and was fixed rather than suppressed:
`test_hypothesis_engine_writes_no_canonical_data_path` fired because `battery_v3` listed
protected `data/...` paths inline. The list was hoisted to a module-level `PROTECTED_PATHS`
constant — the convention the isolation scan recognises as protective — and the test passes
with its strictness intact.

**Hash supersession.** That hoist changed `battery_v3`, so the manifest was rebuilt after the
fix. **`manifest_hash` `cfd92440…` supersedes the pre-fix `88bef098…`**, and the
`battery_v3` module hash `4c43352f…` in §10 is the post-fix source. Every hash in §10 is from
the rebuilt manifest; re-running `_build_v3.py` on the current tree reproduces
`cfd92440…` exactly. The earlier `88bef098…` manifest was superseded before any
authorization was requested and must not be used.

Two tests validate the **written artifact** rather than only the builder
(`test_the_written_manifest_on_disk_matches_the_builder`,
`test_the_written_materialized_packets_match_the_written_call_specs`): they recompute the
on-disk `manifest_hash`, assert it equals what the current modules produce, and assert every
materialized packet hash matches its call spec. A hand-edited or stale manifest fails there
even when the builder is sound.

Repo-wide, 14 collection errors persist from missing third-party packages (`sklearn`,
`asyncpg`, `hypothesis`) in files untouched by this work.

---

## 13. Outstanding risks

1. **Whole-response rejection is retained and is the main live risk.** 16 of 64 frozen V2
   responses would be rejected outright under schema-v2. The mitigation is that V3's model
   *sees* the enum; the stop rule bounds the downside. If it trips, the run ends as an
   infrastructure/prompt failure with no verdict.
2. **Formation is measured, not controlled, at N=3.** No formation claim can be made in either
   direction. `formation_use_rate` is reported and must not be read as a finding.
3. **`profile_disappearance_rate` has a subject-controlled denominator.** If the model uses
   profile in fewer than 3 reference fixtures the control reports `INSUFFICIENT_N`. The
   N-independent part (R1: zero conditions on the withdrawn dimension) is what is gated.
4. **The evidence layout still tilts toward the overall baseline.** Packets present a menu of
   subject-level overall facts with no cohort-conditioned evidence item to cite, so
   "grounded + conditional" remains harder to express than "grounded + unconditional". P1/P2
   are measured against an evidence surface that works against them.
5. **Three of five comparisons are evidence-unsupported** (venue-split, recent-vs-long, league
   environment): all evidence is `window=ALL_PRIOR`, `venue=ALL`, subject-scoped. P4's
   achievable entropy is therefore bounded well below 2.32 bits in practice. 0.60 was chosen
   with that in mind, but it remains the least well-anchored of the four bars.
6. **12 fixtures, one corpus, one competition family.** Fixture-level rates move 0.083 per
   fixture. P3 at 0.50 is 6 of 12 — one fixture either way is material.
7. **The model id is not date-pinned.** `us.anthropic.claude-sonnet-4-6` may resolve to a
   different snapshot than V2's run did, so a V2↔V3 behavioural comparison is confounded by
   model drift. `resolved_model_id` is recorded per call, as in V2, but this cannot be
   eliminated pre-spend.
8. **Anti-circularity is mitigated, not proven.** The prompt exposes the ontology without
   quotas, and the grammar examples are structural — but if depth appears *only* because the
   grammar was shown, the axis-selection diagnostic should show insensitivity and the restraint
   metrics should move together. That is the designed tell; it is not a guarantee.
9. **`shots_for` / `shots_against` remain in `vocabulary.PROFILE_AXES`.** They are gated at two
   layers rather than removed, because removing them would change `vocabulary_version` and
   break V2's recorded hashes. The vocabulary itself stays internally inconsistent until a
   future generation can renumber it.

---

## 14. Interpretation policy

Two outputs, kept strictly separate:

- **Mechanical verdict** — a pure function of the frozen thresholds in `verdict_v3.py`.
- **Scientific interpretation** — written afterwards: whether the hypotheses are actually
  useful to a football quant researcher; whether conditional structures exploit the supplied
  evidence; whether output remains generic; whether complexity looks meaningful or
  prompt-induced.

**The interpretation may never alter the mechanical verdict.**

---

## 15. Authorization

Everything scientific is frozen and hashed. No discretion remains after authorization: fixture
set, call order, transformed packets, prompt, schema, contract, availability logic, firewall,
normalization, compiler, scorer, classifier, thresholds, stop rule and cost are all pinned by
hash in `PRESPEND_MANIFEST_sonnet46_v3.json`.

**Hard spend ceiling requiring explicit authorization: $10.37 USD**
(56 calls; expected $5.66, p90 $5.97; ceiling assumes every call returns the full 8,192-token
`maxTokens`).

---

**SONNET46_HYPOTHESIS_V3_FULLY_PREREGISTERED**
