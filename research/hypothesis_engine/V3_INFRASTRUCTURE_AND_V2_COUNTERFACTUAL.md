# V3 Measurement Apparatus — Build, Validation, and V2 Counterfactual Replay

**Bedrock inference calls made: 0.** Every number below was recomputed offline from frozen
artifacts and from code in this repository. All tests are zero-spend.

**V2 is untouched.** `SONNET46_HYPOTHESIS_V2 = FAIL` stands, permanently. No V2 artifact was
edited, rescored, rewritten or replaced. `schema.py`, `prompt.py`, `firewall.py`,
`evaluation.py` and `query_plan.py` are byte-identical to what produced the frozen run
(`validator.py` carries one strictly additive, provably inert change — §1.4). The V3
apparatus is built as new modules alongside, so the frozen run stays exactly reproducible.

**Architecture untouched.** No change to CHAMPION, `p_model`, calibration, production
prediction, prospective publication or market comparison. No LLM hypothesis becomes a
predictive feature. No deterministic effect estimation was added. Every new module imports
only from within `research.hypothesis_engine` (verified).

---

## 1. Exact files changed

### New — V3 apparatus (`src/research/hypothesis_engine/`)

| File | Lines | Purpose |
|---|---|---|
| `condition_contract.py` | 437 | **The canonical typed contract.** Single source of truth for condition canonicalization, projected from `vocabulary.DIMENSIONS`. |
| `schema_v2.py` | 59 | `hypothesis_set_schema_v2` — closed per-dimension `value` enum + `axis` cross-field rule, *generated* from the contract. |
| `firewall_v2.py` | 281 | `numerical_authority_firewall_v2` — A/B/C classification over the unchanged v1 pattern set. |
| `availability.py` | 454 | `hypothesis_availability_v1` — the availability-gated research ontology, exposure surface, depth and restraint measures. |
| `validator_v2.py` | 139 | V3 wiring: canonicalize → schema-v2 → firewall-v2 → unchanged grounding gate. |
| `prompt_v2.py` | 279 | `hypothesis_analyst_prompt_v2` — no static availability claim, stated casing contract, first-class `axis`, structural evidence-reference channel. |
| `evaluation_v2.py` | 397 | `hypothesis_evaluation_v2` — discipline / depth / restraint kept on three separate axes; two corrected scoring definitions. |

### Modified — one file, one additive change

| File | Change |
|---|---|
| `src/research/hypothesis_engine/validator.py` | `_check()` gained support for `const` / `allOf` / `if` / `then` / `not`, plus a new `validate_schema_against(schema_doc, payload)` entry point. |

Why this is safe: `hypothesis_set_schema_v1` contains **none** of those keywords (asserted by
`test_v1_schema_contains_no_combinator_so_the_added_checker_branch_is_inert`), so the block is
unreachable on the v1 path. `validate_schema()` still points at schema v1. All 64 frozen V2
responses still validate identically (asserted by
`test_frozen_v2_responses_still_schema_validate_exactly_as_before`).

### New — tests (`tests/research/hypothesis_engine/`)

| File | Tests |
|---|---|
| `test_condition_contract_v3.py` | 96 |
| `test_firewall_v2_classification.py` | 24 |
| `test_availability_gating_v3.py` | 22 |
| `test_evaluation_v2_corrections.py` | 14 |

### New — replay (analysis only, no LLM)

| File | Purpose |
|---|---|
| `research/hypothesis_engine/_replay_v2_counterfactual.py` | The counterfactual replay analyzer. |
| `research/hypothesis_engine/out/V2_COUNTERFACTUAL_REPLAY_v3contract/counterfactual_replay_report.json` | The replay artifact. |
| `research/hypothesis_engine/out/V2_COUNTERFACTUAL_REPLAY_v3contract/per_call_original_vs_counterfactual.json` | Per-call original-vs-counterfactual detail (all 64 recorded calls). |

---

## 2. Canonical condition contract design

### The defect being eliminated

```python
# schema.py  (v1)                     # query_plan.py (v1)
"value": {"type": "string"}           if val not in spec["values"]:   # UPPERCASE enum
                                          fail(UNSUPPORTED_DIMENSION)
```

A free string on one side, a closed uppercase enum on the other. `venue=home` satisfied the
schema and died at the compiler. **40 of 43** observed reference compile failures were exactly
this.

### One source of truth, three consumers

`vocabulary.DIMENSIONS` remains the only place a condition enum is **defined**.
`condition_contract` is the canonicalization + projection layer over it, and every consumer
takes its notion of "legal" from there:

```
vocabulary.DIMENSIONS            (definition — unchanged, not duplicated anywhere)
        │
        ▼
condition_contract               (canonicalization + schema projection)
        ├──► schema_v2.build_schema()          — enums GENERATED, never typed out
        ├──► canonicalize_payload()            — normalization boundary
        ├──► query_plan.compile_hypothesis()   — UNCHANGED; already checked vocabulary
        └──► availability / evaluation_v2      — read the contract, declare nothing
```

Drift is not a matter of discipline; it is tested. For **every** dimension,
`test_schema_v2_value_enum_equals_vocabulary_enum_for_every_dimension` asserts the schema's
per-dimension enum is element-identical to `vocabulary.DIMENSIONS[dim]["values"]`, and
`test_compiler_accepts_exactly_the_contracts_canonical_values` asserts the compiler's accepted
set equals the contract's legal set.

**The compiler was deliberately NOT changed.** Its enum check was always correct. Canonicalizing
at the boundary makes the mismatch unreachable, and leaving the compiler frozen is what makes the
counterfactual replay credible — both arms run the identical compiler.

### Alias policy at the external boundary

Accepted — **mechanical folding only**: case, hyphen→underscore, space→underscore, surrounding
whitespace. So `home`, `HOME`, `Home`, `back-three`, `back three` all resolve.

Rejected — **all semantic aliasing**. `high_possession` does *not* become
(band=`HIGH`, axis=`possession_for`). Repairing that would be the engine inventing the model's
intent and would make a real research error invisible
(`test_no_semantic_aliasing_is_performed`).

Order is fixed: **canonicalize → validate → compile**. After canonicalization there is exactly
one internal representation — `test_alias_spellings_collapse_to_one_intent_key_and_one_plan_hash`
asserts that seven spellings of `HOME` produce **one** intent key and **one** plan hash.

### Fail-closed, with a precise named reason

`UNKNOWN_DIMENSION` · `UNKNOWN_VALUE` · `MISSING_AXIS` · `UNKNOWN_AXIS` ·
`AXIS_NOT_APPLICABLE` · `MALFORMED_CONDITION`

A condition that fails is left **verbatim** in the payload and recorded — never dropped, never
repaired — so it still fails downstream rather than being laundered into a passing response
(`test_failed_conditions_are_preserved_verbatim_not_dropped_or_repaired`).

### Shape note (a trap avoided)

The flat `{dimension, value, axis}` object is preserved deliberately.
`firewall._FIELD_NAME_EXEMPT_PATHS` contains `"$.hypotheses.conditions.value"` and
`vocabulary.BAND_EXEMPT_PATH_SUFFIXES` contains `"conditions.value"`. Restructuring conditions
into a per-family object (design doc §6 option b) would have silently turned every cohort value
into a `forbidden_field` violation and every `HIGH` band into a `level_grade`. Cross-field rules
use JSON-Schema `if/then` on the flat shape instead, and
`test_canonical_conditions_produce_no_firewall_violation_in_either_version` sweeps all 28
dimension×value pairs through both firewall versions to pin it.

---

## 3. Exhaustive contract tests

**The required invariant, as implemented:**

> Anything accepted as a valid hypothesis condition must either compile, or fail for a documented
> semantic / data-capability reason — never because two internal components disagree about
> encoding.

Enforced as a **whitelist of allowed failures**, not as "everything compiles":

- allowed: `UNSUPPORTED_CONTEXT_SOURCE`, `UNSUPPORTED_GRANULARITY`, `UNSUPPORTED_METRIC`
- never allowed: `UNSUPPORTED_DIMENSION`, `QUERY_INVALID`

The sweep covers **all 8 dimensions × all 28 legal (dimension, value) pairs × 7 alias spellings each**, not only
venue, through canonicalize → schema-v2 → compile, with `manifest=None` and again against **all
52 frozen fixture manifests**.

The asymmetry is the invariant, so two combinations are asserted to **keep failing**:
`period=FIRST_HALF` against a full-match-only metric → `UNSUPPORTED_GRANULARITY`; a
manifest-withheld dimension → `UNSUPPORTED_CONTEXT_SOURCE`
(`test_the_two_documented_semantic_failures_are_the_only_ones_and_still_fail`).

The exact V2 defect is pinned in both directions: v1 accepts `venue=home`, v2 rejects it with the
path `$.hypotheses[0].conditions[0].value`
(`test_v1_schema_accepted_lowercase_venue_and_v2_does_not`).

**96 tests in `test_condition_contract_v3.py`, all passing** (156 across all four new test files).

---

## 4. Numerical-firewall classification changes

Every v1 prose pattern is still applied, the structural layers are reused verbatim, match
semantics are identical (first match per pattern per field), and **nothing is relaxed**.
Probabilities, estimated percentage effects, odds, EV/edge, stakes and latent advantage grades
remain banned outright. What changed is that a hit is now **classified**:

| Class | Meaning | Blocking? |
|---|---|---|
| **A** `GENERATED_NUMERIC` | the model produced a number carrying predictive authority | **yes** |
| **B** `EVIDENCE_VALUE_REPRODUCTION` | the model copied a value it was *supplied* into prose | **yes** — tracked separately |
| **C** `METRIC_LEXICAL` | match is an approved-metric-name artefact carrying no number | no — never was a violation |

**Class B stays blocking.** The task separates B for *tracking*, not absolution, and the design
doc is explicit that the 44.6%/55.4% breach "is still a real discipline breach… E is a true
FAIL." The architectural fix is the structural evidence-reference channel in `prompt_v2`, not
leniency.

**A-vs-B is a label, never a licence.** The *blocking* decision is made without the packet; the
packet is consulted only to assign the label. An unresolvable literal is labelled **A** — the
conservative direction — with `evidence_resolved=False` recorded so a fallback-A is always
distinguishable.

**Class C is generic, not a `"chances at"` patch.** Every approved metric name from
`capability.METRICS` is masked out of the prose before the patterns run, so a future colliding
metric is covered by construction.

**An over-correction found and fixed during the build.** Masking alone suppressed
`"+0.6 corners"` — a genuine effect-size claim — because `corners` is an approved metric name.
Class C is now defined as *strictly lexical*: a match containing **any** numeric literal is
classified A/B on the raw match, whatever masking does to it. Pinned by
`test_a_match_containing_a_number_is_never_suppressed_as_metric_lexical`.

**Precision-aware B resolution.** `"below 50%"` initially resolved as class B because an
unrelated evidence item was `50.4552`. A bare integer must now *be* the value (tolerance 0.05),
not a rounding of it, and `sample_n` is excluded from the resolution surface. `"50%"` is
correctly class A.

---

## 5. Availability-gating implementation and tests

`availability.build_ontology(packet, manifest)` derives, per fixture, what may be **selected**
and — separately — what depth may be **measured**.

Two kinds of "available", kept apart because conflating them is how the V2 matrix went wrong:

- **compile-available** — the engine could measure it (manifest + `capability.CONTEXT_SOURCES`);
- **evidence-supported** — the packet actually *showed* something that could motivate it.

Statuses: `AVAILABLE` · `AVAILABLE_LOW_CONTRAST` · `COMPILE_AVAILABLE_NO_EVIDENCE` · `WITHHELD`.
Only `AVAILABLE` enters a depth denominator. Everything else is **excluded** — `utilization` is
`None`, never `0.0`.

### The gated matrix, recomputed from the frozen packets

| Dimension / comparison | Status across the 12 reference fixtures |
|---|---|
| `venue`, `competition`, `opponent_profile` | AVAILABLE in 12/12 |
| `own_formation_family`, `opponent_formation_family` | WITHHELD 3 · LOW_CONTRAST 6 · **AVAILABLE 3** |
| `half_score_state`, `period` | **WITHHELD in 12/12** |
| `SUBJECT_RECENT_VS_LONG_BASELINE` | **NO_EVIDENCE in 12/12** |
| `LEAGUE_ENVIRONMENT_BASELINE` | **NO_EVIDENCE in 12/12** |
| `SUBJECT_VENUE_BASELINE` | COMPILE_AVAILABLE_NO_EVIDENCE in 12/12 |

### Two corrections to the accepted diagnosis

The diagnosis is the design basis, but building the apparatus surfaced two factual refinements
to its §2 matrix. Both are recomputed, not argued:

1. **Recent-vs-long was *not* available.** Every one of the 3,662 evidence items across all 52
   materialized packets carries `scope.window = ALL_PRIOR`. There is no second horizon anywhere.
   §2 recorded recent/long as `Y` in all 12; it is evidence-unsupported in all 12. The same holds
   for `LEAGUE_ENVIRONMENT_BASELINE` (no league-scope evidence) and for venue *splits* (every
   evidence scope is `venue=ALL`).
2. **Formation coverage overstated formation usability.** Coverage is only half the story;
   contrast is the other half. `mt_013233190` had the *best* coverage (0.25) but recorded exactly
   one formation family per side — a condition on it compares a cohort with itself. Formation is
   genuinely measurable in **3 of 12**, not 9.

### Prompt-level gating, and a hardcoded lie removed

`prompt.py` asserted in **static text**: *"Half-time score state (leading / level / trailing at
HT) is available"*, and listed it again under "the corpus you have". It was withheld by all 12
manifests. This is plausibly the mechanical reason gating never happened. `prompt_v2` states
**no** dimension as available anywhere in static text; availability comes from the per-fixture
ontology and nowhere else (`test_prompt_v1_asserted_score_state_availability_and_prompt_v2_does_not`).

Withheld dimensions are **absent** from the exposed space, not listed as forbidden — naming a
dimension in order to forbid it still teaches the model the dimension is worth reaching for. A
leak was found and closed: the raw `capability_manifest` dump inside the untrusted evidence block
re-leaked withheld names through its own `notes` ("period and half_score_state dimensions
withheld"). It is now excluded from the dump, being trusted engine metadata already rendered —
gated — above.

### Restraint is first-class

`restraint_profile()` reads **raw** hypotheses, not normalized intents, because `normalize` drops
`ANY`-valued conditions (correct for intent identity) which would hide exactly the padding being
measured. It reports `any_padding_conditions`, `conditions_on_withheld_dimensions`,
`gratuitous_condition_rate`, and separates `interaction_rate` from `justified_interaction_rate`
(both legs manifest-available).

### Anti-circularity

The grammar examples in `prompt_v2` are structural only — no team, no fixture, no metric, no
family, and the unconditional shape listed **first** and on equal footing. Asserted by
`test_prompt_v2_worked_examples_name_no_team_metric_or_football_story`, which fails if any
approved metric name or research family appears in the example block.

---

## 6. V2 immutable counterfactual replay artifact

`research/hypothesis_engine/out/V2_COUNTERFACTUAL_REPLAY_v3contract/`

**Provenance — nothing under `out/hypothesis_v1_sonnet46_v2/` was written.** The replay artifact
is a new, separately-named sibling directory inside `out/`; the frozen V2 run directory is opened
**read-only** and is unmodified. Verifiable three ways:

- the only write-mode opens in `_replay_v2_counterfactual.py` are `open(f"{DEST}/…", "w")`, where
  `DEST` is the new directory (`grep -n 'open(' research/hypothesis_engine/_replay_v2_counterfactual.py`);
- every file in `out/hypothesis_v1_sonnet46_v2/` retains its pre-session mtime (latest `15:01`),
  while every file produced by this task is `15:20` or later;
- `research/hypothesis_engine/` is untracked in git as a whole, so mtime + read-only access is the
  available proof; no `git checkout`/`git restore` was run against it.

- `is_a_corrected_v2_verdict: false`
- `frozen_verdict_unchanged: "SONNET46_HYPOTHESIS_V2 = FAIL"`
- `bedrock_calls_made: 0`

**What it measures, and what it cannot.** It measures what the *already-recorded text* would have
done under the corrected contract. It cannot measure what the model would have **written** had it
been shown the corrected contract, the gated ontology and the evidence-reference channel — those
change the input, and only a new run can measure them. Every depth number below is a **lower
bound** on what a de-confounded experiment could observe, not a prediction of one.

**Harness validation.** The replay's ORIGINAL arm reproduces the frozen
`query_compile_rate = 0.4880952380952381` exactly, to the last digit. The counterfactual arm
differs from it in exactly one variable.

---

## 7. Original vs replay compiler diagnostics

### Compile rate — both denominators

| Arm | Accepted | Compilable | Rate |
|---|---|---|---|
| **Frozen V2 reported** | — | — | **0.4881** |
| ORIGINAL, recomputed (12 reference) | 84 | 41 | **0.4881** ✓ reproduces |
| **Same-survivor** (the 7 responses surviving firewall v1; denominator held fixed, *only* variable = canonicalization) | 84 | **81** | **0.9643** |
| **Full arm** (all 11 reference responses surviving firewall v2) | 132 | **127** | **0.9621** |

Both are reported because fixing the class-C false positive changes *which* responses survive to
be compiled, so a single number would not be apples-to-apples.

### Failures removed by canonicalization

| | Original | Counterfactual |
|---|---|---|
| Reference compiler failures | **43** (all `UNSUPPORTED_DIMENSION`) | **5** |
| Removed by canonicalization | — | **38** |

Alias resolutions applied across the 12 reference responses: `venue: home → HOME` ×49,
`venue: away → AWAY` ×41 (**90 total**).

### Remaining genuine failures (5) — none is an encoding artefact

| Reason | n | Detail |
|---|---|---|
| `MISSING_AXIS` | 3 | `opponent_profile` with no `axis` — `mt_010244159/H12`, `mt_013233190/H12`, `mt_010443150/H10`. Their values were *also* mis-cased, but the missing axis makes them semantically incomplete regardless of spelling. |
| `UNKNOWN_VALUE` | 1 | `opponent_profile = high_possession` — band conflated with axis (`mt_010441491/H11`). |
| `UNKNOWN_VALUE` | 1 | `competition = COMPETITION` — the literal word, not `SAME`/`ANY` (`mt_012232411/H12`). |

Note: the compiler reports these as `UNSUPPORTED_DIMENSION` because the failed condition is
preserved verbatim (still lower-cased). The **contract** names the true reason first, which is
precisely the diagnostic improvement.

### Firewall reclassification

| | Reference (12) | All controls (64) |
|---|---|---|
| v1 hits | 6 | 30 |
| v2 class **C** (suppressed) | 5 | 24 |
| v2 class **B** (blocking) | 1 | 4 |
| v2 class **A** (blocking) | 0 | 2 |
| **v2 blocking total** | **1** | **6** |
| Responses rejected whole | **5 → 1** | — |

**Over-correction check passes.** Every `"chances at"` hit was `big chances at` — the approved
metric `big_chances` — and is class C. The genuine Gate-E breach
(`seq03 · reference · mt_010243938`, `44.6%`) **still blocks**, reclassified B, not removed. If
the replay had reported zero violations, the recommendation would have been inflated by an
instrument that stopped measuring.

---

## 8. Corrected interpretation of research-depth evidence

> **After removing known infrastructure defects, what evidence of Sonnet research depth actually
> remains in the already-recorded V2 outputs?**

146 normalized intents over 132 accepted hypotheses from the 12 reference responses.

### What was an artefact

- **Compilability was overwhelmingly an encoding artefact.** 0.488 → 0.964 with the model's text
  unchanged. The questions were answerable; the *strings* were not.
- **Venue conditioning was Sonnet's dominant conditional structure and it almost entirely
  vanished.** 90 of 146 intents carry a venue condition; nearly all of it was previously
  destroyed at compile, making the research look both uncompilable *and* thin.
- **5 of 12 responses were destroyed by an instrumentation false positive**, not by any
  misconduct.
- **Score-state absence was correct behaviour**, not shallowness. It was withheld in 12/12.

### What survives de-confounding — and is genuinely positive

- **Restraint is perfect, and V2 could not see it.**
  `any_padding_conditions = 0`, `conditions_on_withheld_dimensions = 0`,
  `gratuitous_condition_rate = 0.0` in **every** fixture. The model never padded a hypothesis
  with `ANY`, and never once asked for a dimension its packet withheld. Under the corrected
  ontology that is a clean pass on the restraint axis.
- **Capability discipline held.** Zero unavailable-context requests.

### What survives de-confounding — and is genuinely negative

- **Interaction depth is exactly zero.** `n_two_condition_interactions = 0` out of 132
  hypotheses, in all 12 fixtures. Not one hypothesis combined two conditions. This is *not* an
  infrastructure artefact: a two-condition hypothesis would have compiled.
- **Conditional breadth beyond venue is 6%.** Only **9 of 146** intents carry a non-venue
  condition (`opponent_profile` 7, `own_formation_family` 1, `competition` 1).
- **The comparison space collapsed.** 140 of 146 intents name `SUBJECT_OVERALL_BASELINE`;
  Shannon entropy **0.2987 bits** out of a possible 2.32. The 152/159 collapse the diagnosis
  identified survives the correction almost untouched.
- **Availability-gated utilization** (denominators exclude impossible dimensions):

  | Dimension | Fixtures where expectable | Using it | Utilization |
  |---|---|---|---|
  | `venue` | 12 | 11 | **0.917** |
  | `opponent_profile` | 12 | 4 | **0.333** |
  | `own_formation_family` | 3 | 1 | 0.333 |
  | `opponent_formation_family` | 3 | 0 | 0.000 |
  | `competition` | 12 | 1 | 0.083 |

- **Evidence-driven vs generic:** 101/146 = **0.692** evidence-driven — but that headline is
  carried almost entirely by venue, and *no packet supplies a venue-split evidence item*. The
  honest reading is the beyond-venue rate: **0.062**.

### The corrected reading

The shallowness V2 reported was **substantially, but not wholly, an instrumentation artefact**.
The mechanical confounds were large and are now removed. What remains is a **sharper and more
specific** finding than V2 could state: the model conditioned readily on the one dimension the
prompt named (venue), essentially never on the ones it did not (`axis`, formation, competition),
and **never combined two conditions at all** — while showing flawless restraint and capability
discipline.

That residual is **still entangled with prompt scaffolding**, and that entanglement is exactly
what V3 changes: V2's prompt never mentioned `axis`, never stated the casing contract, gave no
conditional grammar, and *actively asserted a false availability*. So the residual is real
evidence of thin conditional depth **under V2's prompt**, and is not yet evidence about the
model's judgement under a correct, exposed contract.

---

## 9. Unresolved risks

1. **Strict schema × no-salvage is the main live risk.** schema-v2 closes the condition enum and
   the package rejects a response WHOLE on any schema error. Recomputed over the frozen set,
   **5 of 12** reference responses (16 of 64 calls) carry at least one contract-invalid condition
   and would be rejected outright rather than losing one hypothesis each. In a real V3 run the
   model is *shown* this schema in the tool spec — which V2's model never was — but Bedrock
   tool-use does not hard-enforce a schema. Pinned by
   `test_a_contract_invalid_condition_rejects_the_whole_response_under_schema_v2`. **Recommended policy:
   keep whole-response rejection.** It is the package's existing no-salvage discipline, and the
   decisive change is that the V3 model is *shown* the closed enum in its tool spec — V2's model
   was shown a free string and had no way to know the contract. **Fallback trigger:** if the first
   V3 batch shows a schema-rejection rate above roughly 1 in 6 responses (the 16/64 base rate
   observed here), stop and switch to per-hypothesis contract-failure reporting before spending
   further, rather than absorbing another confounded depth reading.
2. **The replay measures the apparatus, not the model.** It cannot predict what Sonnet would
   write under the new prompt. The depth numbers in §8 are lower bounds.
3. **A-class fallback includes domain constants.** `"below 50%"` is class A by fallback. It is
   not an effect estimate; it is an unsourced number in prose. It blocks either way, and
   `evidence_resolved=False` marks it, but "class A" should not be read as "predictive claim" in
   every instance.
4. **Venue is a weak depth signal here.** Venue is the only condition the v1 prompt named, and no
   packet carries venue-split evidence. A V3 venue-utilization reading should not be treated as
   evidence-driven depth without the beyond-venue breakdown alongside it.
5. **Named-team-similarity cohorts remain unsupported** (`similarity.py` is
   `PENDING_VALIDATION`). V3 must not propose them.
6. **Score-state remains impossible on this corpus.** V3 must either exclude it from all depth
   claims or first build the provenance-tracked FootyStats HT-goals join (separate, zero-inference
   work).
7. **The profile-axis perturbation control (design doc §7) is designed, not built.** Without it,
   V3 can observe *whether* axis selection happens but not whether it is evidence-responsive. This
   should be built before spend, since it directly probes the §1-G residual.
8. **Fixture count is small.** 12 fixtures, one corpus, one competition family. Utilization
   denominators of 3 (formation) carry essentially no statistical weight.
9. **The evidence layout tilt (diagnosis cause A) is unaddressed.** Packets still present a menu
   of subject-level overall facts with no cohort-conditioned evidence item to cite, so
   "grounded + conditional" remains harder to express than "grounded + unconditional". V3 will
   measure depth against an evidence surface that still favours the baseline question.

---

## 10. Recommendation

**A paid V3 experiment is warranted.**

- **The infrastructure defects were real, large, and are now removed by construction.** Compile
  rate on unchanged text moves 0.488 → 0.964; 5 of 12 responses were destroyed by an
  instrumentation false positive; a hardcoded prompt claim asserted a dimension that was withheld
  in 12/12 fixtures. Re-running Sonnet *without* these fixes would have re-bought the same
  confounded result.
- **The apparatus is validated, not merely written.** 156 zero-spend tests pass; the exhaustive
  sweep covers every dimension × value × alias spelling through the full path; the replay's
  ORIGINAL arm reproduces the frozen metric to the last digit; the over-correction check confirms
  V2's genuine violation still blocks.
- **One clean negative signal survives, and it is precisely what V3 can resolve.** Across 132
  accepted hypotheses in all 12 fixtures, the model produced **zero** two-condition hypotheses.
  This is the single most decisive number in the replay, because it has **no infrastructure escape
  hatch**: a two-condition hypothesis would have compiled perfectly well under V2's own apparatus.
  Nothing broke it; it was never attempted. The same holds, less starkly, for 6% beyond-venue
  conditioning and 0.30 bits of comparison entropy.

  But that signal was produced under a prompt that never mentioned `axis`, never stated the casing
  contract, gave no conditional grammar, and *asserted a false availability*. Venue — the one
  dimension the prompt named — was used in 11 of 12 fixtures; the dimensions it did not name were
  used almost never. So the zero is uncontaminated by the compiler and the firewall, and
  **entirely contaminated by prompt scaffolding** — which is the one confound V3 removes and the
  replay cannot. Whether that zero is the model's judgement or the contract it was handed is the
  question that decides its suitability for this role, and it is now cleanly askable for the first
  time.
- **Outcome C is not supported.** The frozen responses show flawless restraint, flawless
  capability discipline, and one genuine compliance breach whose architectural cause (no legal
  channel to reference an observed value) is now fixed. That is not sufficient evidence of
  unsuitability.
- **Outcome B was seriously considered and addressed rather than deferred.** The two known
  measurement defects in the evaluation layer — abstention scoring an ideal empty set as 0.0, and
  invariance judged against an absolute 0.80 when the generator's own same-input floor measured
  0.333 — are now corrected in `evaluation_v2`, with no threshold moved. Risk 1 (strict schema ×
  no-salvage) and risk 7 (the profile-axis control) should be settled before spend; both are
  zero-inference decisions.

**Scope constraints for the paid run:** exclude score-state/period and named-team-similarity
entirely; report depth only over availability-gated denominators; report restraint alongside
depth so over-forcing is visible; and report the beyond-venue conditional rate next to any
headline utilization figure.

---

## Test status — reported in full, nothing hidden

```
tests/research/hypothesis_engine/ :  428 passed, 1 failed
```

**The single failure is pre-existing and environmental**, present before any change in this task
(baseline captured first, deliberately):

```
test_architecture_isolation.py::test_champion_produces_p_model_with_the_llm_packages_uninstalled
ModuleNotFoundError: No module named 'sklearn'
```

Baseline before this work: **272 passed, 1 failed** (same test, same cause).
After this work: **428 passed, 1 failed** (same test, same cause). No regressions; +156 tests.

**Repo-wide collection errors — all pre-existing, all missing third-party packages**, in files
untouched by this task: `sklearn` (3 files), `asyncpg` (`tests/integration`), `hypothesis`
(`tests/asymmetric`, 7 files). 4,107 tests collect; 14 collection errors, none attributable here.

---

**V3_INFRASTRUCTURE_VALIDATED_PAID_EXPERIMENT_RECOMMENDED**
