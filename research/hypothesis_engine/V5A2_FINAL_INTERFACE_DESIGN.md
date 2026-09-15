# V5A2_FINAL_INTERFACE_CLOSURE — Final Interface Design

**Status:** ZERO SPEND. No Bedrock call, no LLM call, no network call was made in this task.
**Scope:** infrastructure closure only. V2, V3, V4, V5A, V5A.1, CHAMPION, `p_model`,
calibration, prospective predictions and production feature paths are unmodified.

---

## 1. The problem this iteration exists to solve

V5A.1 was correctly built, correctly frozen, correctly authorized, and it died on its
second research-arm call. The cause was not football, not evidence quality, and not the
model. **The apparatus spoke three different languages at the model at the same time.**

For one single concept — "the opponent's profile" — the model saw:

| Where | String |
|---|---|
| packet availability map | `opponent_profile_response` |
| `conditions[].dimension` enum | `opponent_profile` |
| `required_capabilities` enum | `competition` |

`schema.py:52` types `dimension` from `vocabulary.dimension_names()`. `schema.py:102` types
`required_capabilities` from `sorted(capability.CONTEXT_SOURCES)`. Those are **two disjoint
vocabularies that happen to share some spellings**. A model that read `opponent_profile` in
the packet, conditioned on `opponent_profile`, and then declared that it required
`opponent_profile` was rejected as `SCHEMA_INVALID` — because the correct capability token
for that concept was the entirely unguessable `competition`, and **nothing in the packet or
the prompt contained that mapping**.

Two of the first six paid calls were lost to this. 24 hypotheses were discarded unread. The
stop rule fired at 2/6 > 0.30 and reported the run as a model discipline problem.

The governing rule of this iteration: **the model must speak exactly one language, and that
language must be the one the packet hands it.**

## 2. The single authoritative ontology

`src/research/hypothesis_oos/v5a2_ontology.py` defines **20 terms**. Every string the model
reads in a packet and every string it writes in a response is one of them. Three previously
independent vocabularies are now projections of this one dict:

```
v5a2_ontology.TERMS
   ├── all_terms()                  → the packet AVAILABILITY_MAP (all 20, always)
   ├── condition_dimension_terms()  → schema_v3 conditions[].dimension enum (8)
   └── capability_terms()           → schema_v3 required_capabilities enum (19)
```

`schema_v3.build_schema()` obtains both enums by **calling those functions**, so
`test_schema_enums_are_the_ontology` asserts *identity*, not equality of content. A
hand-maintained fourth copy cannot appear, because no layer declares an enum of its own.

`condition_dimension_terms() ⊆ capability_terms()` is asserted by
`test_condition_and_capability_enums_share_one_namespace`.

That same test also asserts the property **fails** for `schema_v2`. This is deliberate and
worth calling out: the test encodes the original defect as a *required* property of the
frozen module. If anyone ever "fixes" `schema_v2` in place, the test that documents why
V5A.2 exists breaks loudly, rather than V5A.2 silently becoming redundant against a mutated
baseline that the V2/V3/V5A preregistrations still claim to hash.

### The one exclusion

`market_prices` is declared in the availability map (so the packet can state the absence is
deliberate) but is **not** a legal `required_capabilities` value. `injuries` and `weather`
are legitimate football-research concepts this corpus lacks; odds are never legitimate input
to a research-question layer at all. A model naming it has broken a contract it was shown —
so it is classified a MODEL error, not an apparatus defect.

## 3. Translation happens after acceptance, never before

The engine's internal namespaces (`vocabulary.DIMENSIONS`, `capability.CONTEXT_SOURCES`)
are frozen — hashed into the V3 and V5A preregistrations — and are **not edited**. They are
reached by deterministic translation in `v5a2_translate`, applied strictly **after** schema
acceptance:

```
conditions[].dimension    ontology term  →  vocabulary.DIMENSIONS key
required_capabilities     ontology term  →  capability.CONTEXT_SOURCES member
```

The model is never asked to perform that translation and never sees either internal name. A
model writing the *engine's* word (`venue`, `historical_formation`) is rejected —
`test_internal_namespace_is_not_model_visible`.

**Honest dropping.** Four terms (`match_level_observations`, `recent_window_summaries`,
`xg`, `market_prices`) name real evidence for which the engine has no `context_source`
concept. They translate to *nothing*, and the drop is recorded in the translation report.
Mapping them onto a plausible-looking source would hand the compiler a claim the model never
made. `required_capabilities` has `minItems: 0`, so an emptied list is legal and a hypothesis
is never punished for declaring its dependencies honestly.

**Verified end to end before any of this was built.** The first thing checked was whether
`opponent_profile → competition` actually survives `query_plan.compile_hypothesis` after
translation. It does — validator accepts, compiler returns a plan. Had it not, the ontology
would have needed per-term compiler adapters and the whole design would have changed.

## 4. The venue split (D3)

V5A.1's base arm rejected 30 venue-conditioned hypotheses at
`unsupported_dimension_rate = 1.0`, and **that number was not interpretable**, because one
term `venue` carried two different meanings:

| Term | Meaning | Base arm | Research arm |
|---|---|---|---|
| `target_fixture_venue_context` | which side is at home in the **upcoming** fixture | EXPOSED | EXPOSED |
| `historical_venue_conditioning` | splitting **prior** matches by where they were played | NOT_EXPOSED_IN_PACKET | EXPOSED |

A model that read "HOME_TEAM plays at home" and concluded venue conditioning was licensed
was making a reasonable inference from an ambiguous term — not ignoring the availability map.
Splitting the term lets the base arm truthfully expose the first while withholding the
second. **The rejection itself is preserved** (task §6); what changes is that it now measures
restraint rather than our own naming.

## 5. The abstention contract (D2)

`validator._validate_one` rejects an `INSUFFICIENT_EVIDENCE` hypothesis that cites any
evidence. **No prompt, schema or packet ever stated that rule.** Six V5A.1 rejections were
exactly this.

Task §5's *preferred* contract is adopted. It is strictly more permissive than the frozen
rule, so `validator.py` and `validator_v2.py` are **not edited**:

| Sufficiency | Refs | Outcome |
|---|---|---|
| INSUFFICIENT_EVIDENCE | none | accepted |
| INSUFFICIENT_EVIDENCE | present in packet | **accepted** — the D2 fix |
| INSUFFICIENT_EVIDENCE | not in packet | rejected (fabrication) |
| SUFFICIENT | none | rejected |

The permission is stated in the prompt **in the same sentence that invites abstention**, and
`test_abstention_contract_is_stated_in_the_prompt` asserts it is there. A rule the model is
judged against must be a rule the model was told.

## 6. Layer map

| Layer | Module | Frozen predecessor left untouched |
|---|---|---|
| ontology | `v5a2_ontology` | — (new) |
| condition contract | `v5a2_contract` | `condition_contract.py` |
| schema | `schema_v3` | `schema.py`, `schema_v2.py` |
| validator | `validator_v4` | `validator.py`, `validator_v2.py`, `validator_v3.py` |
| firewall | `firewall_v4` | `firewall.py`, `firewall_v2.py`, `firewall_v3.py` |
| packet surface | `v5a2_packet` | `v5a1_packet.py` (evidence reused verbatim) |
| admissibility | `v5a2_admissibility` | `v5a1_admissibility.py` |
| ontology view | `v5a2_view` | `v5a1_ontology.py` |
| evaluator | `v5a2_evaluator` | `v5a1_evaluator.py` |
| transport | `v5a2_transport` | — (new) |

Validator pipeline, in binding order:

```
0 canonicalize   v5a2_contract     mechanical spelling folds, ONTOLOGY language
1 schema         schema_v3         enums projected from the ontology
2 identity       fixture + packet-hash binding
3 firewall       firewall_v4       numerical authority + latent grading
4 contract       abstention + grounding      ← MODEL language
5 admissibility  v5a2_admissibility          ← MODEL language
6 TRANSLATE      v5a2_translate    → frozen internal namespaces
7 engine gates   capability / metric / axis  ← ENGINE language
```

Gates 4–5 run **before** translation deliberately: every rejection reason quotes the terms
the model actually wrote, so a rejection is legible to the thing that was rejected.

## 7. Defects closed

| ID | Defect | Closure | Regression test |
|---|---|---|---|
| D1 | packet/schema namespace mismatch | one ontology, both enums projected | `test_d1_regression_advertised_capability_term_is_accepted` |
| D2 | undeclared abstention rule | §5 preferred contract, stated in prompt | `test_abstention_may_cite_valid_evidence` |
| D3 | `venue` ambiguity | term split; rejection preserved | `test_d3_preserved_venue_conditioning_still_rejected_in_base_arm` |
| D4 | boto3 without Converse | asserted preflight at spend 0 | `test_transport_preflight_rejects_client_without_converse` |
| D5 | prose firewall missed `<number> probability` | `firewall_v4` additive patterns | `test_d5_numeric_probability_claim_in_prose_is_blocked` |
| D6 | cost ceiling was not a bound | ceiling uses the request's real `max_tokens` | see authorization report |

**D5 and D6 were found by this iteration, not by the live run.** D5 was found by the
generated battery on its first pass; D6 by recomputing the cost model.

## 8. Two latent defects found while re-surfacing the packet

Neither was reachable in V5A.1's live run, and both are now closed:

1. **`competition` was advertised in an arm that has no competition data.**
   `v5a1_admissibility.packet_capability_summary` appended `"competition"` unconditionally.
   The base arm has no match rows and its summaries carry no competition column, so a
   competition-conditioned hypothesis was *admissible against a packet that could not answer
   it*. The V5A.2 availability map derives the state from the packet, so the base arm now
   declares `competition: NOT_EXPOSED_IN_PACKET`.

2. **The blinding audit substring-matched treatment labels.** `control` matched inside
   *"the cohort is not a controlled comparison"* — a statistical caveat in a static
   disclaimer. `blinding_violations()` now matches whole words. The fix is to match what the
   rule means, not to add the phrase to an exemption list.

Consequence worth stating plainly: **the base arm now declares zero conditionable terms.**
That is the honest description of a summary-only packet, and it sharpens the experimental
contrast rather than weakening it.

`V5A2_INTERFACE_CONTRACT_VALIDATED`
