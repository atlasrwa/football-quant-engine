# V5A.1 Evidence Interface Design

**Experiment:** `V5A.1_FULL_FIDELITY_EVIDENCE_INTERFACE`
**Predecessor:** `V5A` — **`ABORTED_PRE_SPEND`**, preserved unchanged, never re-run
**Date:** 2026-09-14 · **Spend:** $0 · **Bedrock/LLM/network calls:** 0

---

## 1. The abort this design answers

`research/hypothesis_oos/out/v5a/` is preserved byte-for-byte. Nothing in V5A.1 modifies,
overwrites or reinterprets it. `PREREGISTRATION.json` records:

```
V5A_PREVIOUS_VERSION = ABORTED_PRE_SPEND
```

with the defects exactly as the packet inspection found them, not reinterpreted:

1. Arm B evidence references incompatible with shared validator/firewall
2. A/B comparison not isolated to evidence representation
3. shared prompt invited unavailable dimensions
4. raw rows buried behind summary volume
5. opponent-profile semantics ambiguous
6. match alias collisions
7. unresolved xG/npxG semantic conflict

One correction of *mechanism* (not of the finding) is recorded in the provider-semantics
audit: V5A's M-8 attributed the xG/npxG inconsistency to a cross-provider merge. Both fields
are in fact TheStatsAPI's. The inconsistency is real; the cause is inside the provider feed.

---

## 2. Governing architecture

The LLM is the **research-question layer only**. It receives the PIT-safe historical record
and answers one question: *what should the deterministic engine measure?*

It may not produce probabilities, `p_model`, odds, EV, stake, numerical predictive effects,
probability adjustments or latent matchup scores. The engine computes every effect; OOS
validation decides generalisation; the quant model alone owns probabilities. Enforced by
`firewall_v3` (delegating every classification decision to the frozen `firewall_v2`) and by
`test_no_llm_to_p_model_path`, which checks the import graph of all eight V5A.1 modules.

---

## 3. The central fix — one evidence contract, one resolver

### 3.1 What went wrong in V5A

`validator_v2` and `firewall_v2` both resolve references through a V3-shaped key:

```python
valid_ids = {it.get("id") for it in (packet.get("evidence") or []) if it.get("id")}
```

V5A's Arm B packets had no `evidence` key. Measured: **76 resolvable ids for Arm A, 0 for
Arm B**, on all 10 fixtures. Every `SUFFICIENT` hypothesis in the treatment arm was therefore
rejected whatever it cited, and an empty `evidence_refs` was rejected too — so the arm's
maximum grounded-acceptance rate was exactly zero before a token was generated.

### 3.2 `EvidenceRecord`

Every model-visible fact in **both** arms is one `EvidenceRecord`
(`src/research/hypothesis_oos/v5a1_evidence.py`), carrying:

`evidence_id` · `evidence_type` · `subject` · `metric` · `side` · `value` · `units` ·
`window` · `venue_scope` · `fixture_ref` · `opponent_ref` · `competition_ref` · `formation` ·
`sample_n` · `coverage` · `reliability` · `provider_provenance` · `cutoff` · `derivation_type`

Five evidence types, none overloaded to stand in for another:

| type | what it is | derivation |
|---|---|---|
| `MATCH_OBSERVATION` | one real prior match, or one canonical cell of it | `RAW_OBSERVATION` |
| `DERIVED_SUMMARY` | a deterministic aggregate over those cells | `UNWEIGHTED_MEAN` |
| `OPPONENT_PROFILE_SUMMARY` | a cohort response next to the subject's own baseline | `COHORT_UNWEIGHTED_MEAN` |
| `FORMATION_CONTEXT` | recorded-formation coverage and histogram | `COUNT` |
| `AVAILABILITY_DECLARATION` | what this packet does and does not expose | `DECLARATION` |

### 3.3 The id grammar

Deterministic, collision-free, machine-validated, human-readable, **arm-neutral**. Every id
is produced by a constructor in `v5a1_evidence`; nothing formats one by hand.

```
MATCH:HOME:M01                                    one historical match observation
MATCH:HOME:M01:corners_for                        one canonical cell of that match
SUMMARY:HOME:ALL_PRIOR:ANY:corners_for            a deterministic aggregate
SUMMARY:HOME:ALL_PRIOR:HOME_ONLY:corners_for      venue-conditioned
SUMMARY:AWAY:W5:ANY:shots_on_target_against       short-window
PROFILE:HOME:ATK_VS_DEFSIM:shots_on_target_against:total_shots_for
FORMATION:HOME                                    formation coverage context
AVAIL:venue_splits                                an availability declaration
```

Two deliberate properties:

- **Match slots are subject-qualified.** `HOME_M01` and `AWAY_M01` can never collide. V5A
  used the bare provider match id, which named two rows of *opposite* FOR/AGAINST
  orientation whenever the two teams had met — 9 collisions across 7 of 10 fixtures.
- **The similarity axis is part of the profile id.** Two axes describing the same subject,
  direction and response metric are different evidence. The duplicate-id guard caught this
  during construction and the grammar was widened rather than the collision tolerated.

`assert_unique()` raises `DuplicateEvidenceId` at **construction**, never warns: a duplicate
id makes a citation ambiguous, which is the defect this interface exists to remove.

The grammar is serialized into every packet as its final section, with examples and the rule
*"a reference that does not appear in this packet is not evidence."*

### 3.4 One resolver, both arms

`v5a1_evidence.resolve_evidence_ids(packet)` and `.resolve_evidence_values(packet)` walk the
packet's sections. **There is no arm-specific branch in either function**, and
`test_both_arms_resolve_through_the_same_function` asserts the string `packet.get("evidence")`
appears nowhere in `validator_v3.py`.

`validator_v3` and `firewall_v3` are **new modules**. `validator_v2.py` and `firewall_v2.py`
are hashed into the frozen V3 and V5A preregistrations and are left byte-identical; every
gate is reused from them unchanged, and only the resolution line differs.

### 3.5 Compression without losing the citation space

Row and summary blocks are serialized with shared metadata declared **once** and a compact
value matrix — `columns` + `rows`, `shared` + `rows`. The resolver *derives* the cell ids
rather than serializing them. So `MATCH:HOME:M01:corners_for` is citable without 2,760
metadata-bearing objects existing in the prompt. That is what keeps the citation space
complete while the real evidence stays at 30% of the packet instead of V5A's 11%.

### 3.6 Proof (§19, run before any packet was frozen)

| case | base arm | research arm |
|---|---|---|
| cite one summary | **accepted** | **accepted** |
| cite one match row | n/a (arm has none) | **accepted** |
| cite several match cells | n/a | **accepted** |
| cite a venue summary + venue condition | n/a | **accepted** |
| cite a W5 summary, recent-vs-long comparison | n/a | **accepted** |
| cite opponent-profile evidence | n/a | **accepted** |
| cite formation context | **accepted** | **accepted** |
| invalid reference | rejected | rejected |
| cross-fixture payload | rejected (identity binding) | rejected |
| empty refs + `SUFFICIENT` | rejected | rejected |
| empty refs + `INSUFFICIENT_EVIDENCE` (abstention) | **accepted** | **accepted** |
| duplicate ids | raises at construction | raises at construction |
| excluded metric (`npxg`) | rejected | rejected |
| unsupported comparison (`LEAGUE_ENVIRONMENT_BASELINE`) | rejected | rejected |

Every accepted case also compiles under `query_plan.compile_hypothesis`.

`VALID_EVIDENCE_IDS > 0` holds for every packet: **107–109** (base), **2,601–3,361**
(research).

---

## 4. The shared base universe (§4) — the HS-2 fix

V5A compared **Arm A's shrunk means over up to 104 matches** with **Arm B's plain means over
30**. The arms summarised different data, so no measured difference could be attributed to
representation.

V5A.1 separates two policies that V5A had conflated:

| policy | value | scope |
|---|---|---|
| `BASELINE_UNIVERSE` | `ALL_PIT_SAFE_PRIOR_MATCHES_UNCAPPED` | **both arms**, identical |
| `MAX_RAW_ROWS_PER_TEAM` | 30 | row **visibility** only, research arm |
| `SUMMARY_ESTIMATOR` | `UNSHRUNK_ARITHMETIC_MEAN` | **both arms**, identical |

So for a team with 104 PIT-safe prior matches, the `ALL_PRIOR` summary in **both** arms
aggregates all 104; the research arm additionally shows the most recent 30 as rows. The
packet says this in `TARGET_FIXTURE_CONTEXT.history_note` and reports
`pit_safe_prior_matches`, `matches_serialized_as_rows` and `rows_not_serialized` per team, so
the model is never left to assume the rows are the whole record.

**The shrinkage decision is explicit:** shrinkage is a modelling choice, and this packet is a
research-question input, so the honest quantity is the plain mean with its `sample_n`
attached. V3/V5A Arm A used `SHRUNK` values; mixing a shrunk scalar in one arm with a plain
mean in the other was the other half of HS-2.

`test_same_base_history_universe` asserts the `ALL_PRIOR` sample sizes are identical across
arms, per evidence_id, on every fixture.

Everything else is shared and asserted: target fixtures, cutoff, provider corpus, canonical
metrics, team/opponent/competition aliases, system prompt (SHA-256 asserted equal), schema,
validator, firewall, compiler, model, temperature, max hypotheses, evidence id format and
evaluation.

---

## 5. The treatment (§5)

```
research = base + additional exposed evidence
```

Built literally that way, then **proven** rather than asserted:

| arm | receives |
|---|---|
| **base** | `ALL_PRIOR` / `venue=ANY` summaries over the full PIT-safe history · formation coverage context · availability map · metric semantics · fixture context · citation instructions |
| **research** | **everything in base, byte-identical at the evidence-record level**, plus: match-level rows · `W5`/`W10` summaries · `HOME_ONLY`/`AWAY_ONLY` venue summaries · opponent-profile response summaries |

Measured across all 10 fixtures:

- `RESEARCH_SUPERSET_OF_BASE`: **true, 10/10**
- `BASE_IDS_NOT_IN_RESEARCH`: **empty, 10/10** — the research arm omits nothing the base arm receives
- `N_UNEXPECTED_SHARED_VALUE_MISMATCHES`: **0**
- research-only ids: 2,492–3,252 per fixture

The only shared records that differ are the **4 availability declarations** whose value is
the exposure state (`match_level_observations`, `venue_splits`, `recent_vs_long`,
`opponent_profile_response`) — 40 across 10 fixtures. §7 *requires* them to differ: the base
arm must truthfully say it does not carry that evidence. They are classified separately in
the audit as `EXPECTED_AVAILABILITY_DIFFERENCES` and are content statements, not condition
labels.

---

## 6. No arm labels (§6)

`"arm": "B_full_fidelity"` was the **first key** of every V5A Arm B payload. In V5A.1 the arm
selects the evidence set and is never serialized.

`test_no_visible_treatment_label` checks structurally, not by substring: it walks every key
and every non-disclaimer string value. Hard labels (`arm_a`, `arm_b`, `full_fidelity`,
`condition_a`, …) must appear nowhere; generic words (`control`, `treatment`, `compressed`,
`arm`) must not be a field name or a standalone value. Disclaimer prose may still say "this
is not a controlled comparison", because that is a statement about the evidence.

`packet_schema_version` and `evidence_interface_version` are **identical across arms**
(`research_evidence_packet_v1`), so the arms are not distinguishable by version string.
Section presence necessarily differs — that is the treatment — and the availability map
declares it in the packet's own terms.

---

## 7. Capability-driven prompt (§7, §21, §22) — the HS-3 fix

One prompt, byte-identical across arms (SHA-256 recorded in the manifest). It **promises no
section**. `test_no_prompt_invited_unsupported_dimension` asserts the strings
`"You will receive"`, `match_level_history`, `derived_summaries`, `opponent_profile_context`
and `availability_map:` appear nowhere in it.

It instructs instead: *"AVAILABILITY_MAP is authoritative about what THIS packet contains …
Act ONLY on EXPOSED_TO_LLM … Different packets expose different evidence types, so do not
assume a section exists because you have seen one before."*

On priming: the prompt names available dimensions as a **boundary, not a checklist**, and
says explicitly that *"a packet exposing a dimension is not a reason to use it"* and that
*"Marking a hypothesis INSUFFICIENT_EVIDENCE is a correct and valued answer."* The priming
scan runs against the prompt and all 20 payloads; the four terms that appear in the prompt
(`advantage`, `exploit`, `favourable`, `favorable`) are asserted to occur **only inside the
HARD RULES prohibition list** — forbidding a thing is not priming for it.

---

## 8. Three kinds of availability (§8)

`PROVIDER_AVAILABLE` · `DERIVABLE_PIT_SAFE` · `EXPOSED_TO_LLM` are three separate flags on
every declaration. V5A conflated them: Arm A's `data_quality.n_unavailable: 0` asserted that
nothing was unavailable while four whole evidence classes were withheld.

Worked example, `venue_splits`:

| | base arm | research arm |
|---|---|---|
| `PROVIDER_AVAILABLE` | true | true |
| `DERIVABLE_PIT_SAFE` | true | true |
| `EXPOSED_TO_LLM` | **`NOT_EXPOSED_IN_PACKET`** | **`EXPOSED`** |

The states are `EXPOSED`, `EXPOSED_LOW_COVERAGE`, `NOT_EXPOSED_IN_PACKET`,
`NOT_DERIVABLE_PIT_SAFE`, `NOT_PROVIDED_BY_SOURCE` — so "we could compute this but did not
include it" is a different statement from "no provider supplies it", and `lineup` is
correctly `NOT_DERIVABLE_PIT_SAFE` rather than simply missing.

`test_truthful_availability_map` and `test_availability_matches_what_the_packet_actually_contains`
assert each declaration matches what the packet really carries — section presence, summary
windows, venue-scoped rows.

The declaration is not advisory. `v5a1_admissibility` narrows `schema_v2`'s frozen (and
wider) enums to the packet's exposed surface, so a venue-conditioned question against a base
packet is **rejected**, not silently accepted:

| | base arm | research arm |
|---|---|---|
| windows | `ALL_PRIOR` | `ALL_PRIOR`, `W5`, `W10` |
| dimensions | `competition` | `competition`, `venue`, `opponent_profile`, `own_formation_family`, `opponent_formation_family` |
| comparisons | `SUBJECT_OVERALL_BASELINE` | + `SUBJECT_VENUE_BASELINE`, `SUBJECT_RECENT_VS_LONG_BASELINE` |
| always unsupported | `LEAGUE_ENVIRONMENT_BASELINE`, `SUBJECT_COMPETITION_BASELINE`, `half_score_state`, `period`, `referee` | same |

Formation is a special case worth stating: **both** arms carry the coverage record, but only
the research arm carries formation on each observation. A coverage summary tells you how much
formation data exists; it does not let anyone split a cohort by it. So formation
*conditioning* requires `match_level_observations` to be exposed. Without that rule a
formation-conditioned hypothesis would have been admitted against a packet with no per-match
formation at all — the HS-3 failure mode returning by a side door. It was found and closed
during the build; `test_formation_restraint` now guards it.

---

## 9. Opponent-profile semantics (§14, §15) — the M-2 fix

V5A's profile block was `axes.<axis>.HOME` / `.AWAY`, where the key was a **subject** label
in a packet where `HOME`/`AWAY` meant venue everywhere else — the natural reading was
inverted. It carried a band and nothing else: no cohort, no response, no baseline. Its own
builder docstring described a response cohort the code never constructed.

V5A.1 constructs it. Each cohort is declared once:

```json
{"subject": "HOME",
 "semantic_label": "HOME_TEAM_ATTACK_VS_OPPONENTS_DEFENSIVELY_SIMILAR_TO_AWAY_TEAM",
 "response_direction": "ATK_VS_DEFSIM",
 "similarity_axis": "shots_on_target_against",
 "similarity_method": "RANK_BAND_TERCILE_v5a1",
 "upcoming_opponent_band_on_axis": "HIGH",
 "cohort_definition": "the subject's prior matches against opponents whose
   shots_on_target_against was in the HIGH tercile of this competition, each opponent
   measured using only matches before that cohort match",
 "cohort_n": 35, "cohort_share_of_prior_matches": 0.3365}
```

and each response row carries the response metric, the cohort value, `cohort_n`, the
**baseline value**, `baseline_n` and reliability:

```
["PROFILE:HOME:ATK_VS_DEFSIM:shots_on_target_against:total_shots_for",
 "HOME", "HOME|ATK_VS_DEFSIM|shots_on_target_against", "total_shots_for", "FOR",
 14.8571, 35, 13.1456, 103, "HIGH"]
```

Every §14 requirement is present: profile dimension, direction, cohort N, response metric,
response value, baseline, baseline N, coverage, availability. Direction is spelled out in a
full sentence, and the four `semantic_label` values name both teams explicitly.

PIT safety: tercile thresholds come from the competition measured strictly before the target
cutoff; each historical opponent is measured using only matches before **that cohort match**.

§15 (descriptive, not predictive) is enforced, not just intended. The section's
`interpretation` says these are *"not expected effects, advantages, favourable matchups or
predictions, and the cohort is not a controlled comparison: cohort and baseline differ in
opponent quality, venue mix and period."*
`test_opponent_profile_is_descriptive_not_predictive` scans every key and every
non-disclaimer value for `advantage`, `edge`, `favourable`, `expected effect`,
`positive matchup`, `will `, `predict`.

---

## 10. Packet order (§11) and summary bloat (§12)

V5A serialized with `sort_keys=True`. Alphabetical order put ~480 summary objects (80% of
bytes) ahead of the match rows, which landed at **81.5–95.9%** of the prompt; the `fixture`
block naming the teams sat at 81%, and `row_encoding` — the key explaining how to read the
rows — at 97.7%, *after* them.

V5A.1 serializes with `sort_keys=False` and an explicit section list. Order is now
semantically load-bearing, so `packet_hash` is order-sensitive by design.

Measured (research arm, `mt_010244159`):

| § | section | bytes | position |
|---|---|---:|---|
| 1 | TARGET_FIXTURE_CONTEXT | 1,250 | 0.1%–1.1% |
| 2 | AVAILABILITY_MAP | 6,979 | 1.1%–6.4% |
| 3 | METRIC_SEMANTICS | 11,558 | 6.4%–15.2% |
| 4 | **MATCH_LEVEL_OBSERVATIONS** | **39,328** | **15.2%–45.1%** |
| 5 | DERIVED_SUMMARIES | 52,239 | 45.1%–84.8% |
| 6 | OPPONENT_PROFILE_SUMMARIES | 16,267 | 84.8%–97.2% |
| 7 | FORMATION_CONTEXT | 1,368 | 97.2%–98.3% |
| 8 | EVIDENCE_CITATION_INSTRUCTIONS | 2,192 | 98.3%–99.9% |

**Both teams' entire raw record ends at 45.1%, before the first byte of any derived
summary.** `test_raw_rows_before_summary_majority` asserts this on every fixture.

Compression was structural, not achieved by dropping football content (§12): shared row and
summary metadata is declared once; metric semantics are defined once instead of repeated per
cell; `units` is a property of the metric, not a column on 460 summary rows. Raw:summary
moved from V5A's **1 : 5.5 – 1 : 7.2** to **1 : 1.7 – 1 : 2.2**. No metric was removed to
improve the ratio; `npxg` was removed for the semantic reason in the provider audit.

---

## 11. Module inventory

| file | status | role |
|---|---|---|
| `src/research/hypothesis_oos/v5a1_evidence.py` | **new** | `EvidenceRecord`, id grammar, exposure triple, resolver, serializer |
| `src/research/hypothesis_oos/v5a1_semantics.py` | **new** | provider semantics registry, exclusions, unsupported context |
| `src/research/hypothesis_oos/v5a1_packet.py` | **new** | both arms, sections, summaries, profile cohorts |
| `src/research/hypothesis_oos/v5a1_prompt.py` | **new** | shared capability-driven prompt |
| `src/research/hypothesis_oos/v5a1_admissibility.py` | **new** | per-packet narrowing of the frozen enums |
| `src/research/hypothesis_oos/v5a1_ontology.py` | **new** | projects a V5A.1 packet into the frozen `availability` builder's view |
| `src/research/hypothesis_engine/validator_v3.py` | **new** | v2's gates + arm-neutral resolution + admissibility |
| `src/research/hypothesis_engine/firewall_v3.py` | **new** | v2's classification + arm-neutral provenance |
| `validator_v2.py`, `firewall_v2.py`, `schema_v2.py`, `query_plan.py`, `vocabulary.py`, `corpus_adapter.py`, `availability.py` | **UNCHANGED** | hashes asserted equal to the V5A freeze |

---

## 12. Downstream boundary

V5A.1 stops at hypothesis-generation evaluation. No predictive coefficients, no candidate
features, no OOS search, no shrinkage tuning, no thresholds, no prospective betting. A PASS
triggers a separate preregistered stage.

**`V5A1_FULL_FIDELITY_INTERFACE_VALIDATED`**
