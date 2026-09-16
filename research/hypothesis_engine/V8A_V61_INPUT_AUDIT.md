# V8A — Audit of the Actual V6.1 Research Input

**Status:** development-only. Zero spend to produce this document. No V7.1 artifact was
modified, reinterpreted or re-run.

**Method.** This audit reads the *frozen V6.1 request artifacts themselves*, not the V6.1 or
V7.1 reports. Every claim below is recomputed from
`research/hypothesis_oos/out/v6_1/` at commit `4506600516184179ab26119d06489cd4761e0ea3`.
Per the V8A brief §4, nothing here is inferred from a narrative report, and the V7.1 *result*
is not used to characterise what V6.1 saw.

---

## 0. Reproducibility proof (prerequisite for Arm A)

The V8A brief §19 permits Arm A only if the historical V6.1 protocol can be reproduced
**faithfully**, and forbids reconstructing a "similar" old prompt.

| Check | Result |
|---|---|
| All 8 artifacts in `PREREGISTRATION.artifact_hashes` re-hash to their frozen values | **8/8 OK** |
| V6.1 request objects rebuilt via `v6_token_count.canonical_converse_request(...)` and hashed with `request_sha256` | **36/36 byte-identical** to `EXACT_INPUT_TOKEN_MANIFEST.entries[].request_sha256` |
| Conservative UTF-8 byte bound recomputed per request | **36/36 identical** |
| `v6_prompt.SYSTEM_PROMPT` sha256 | `e5a4529dfa69b8f4437e2f45ea7a9522304c5377abe927cc6373acdf271e244b` |

**Verdict: `V61_PROTOCOL_REPRODUCIBLE = true`.** The escape hatch
`V61_PROTOCOL_NOT_REPRODUCIBLE` does **not** apply. Arm A will run the genuine
`v6_prompt_v1` system prompt, the genuine `v5a2_packet_v1` packet surface, the genuine
`hypothesis_set_schema_v4`, at the genuine `temperature=0.0`, `max_tokens=8192`.

### Frozen V6.1 stack (from `PREREGISTRATION.shared_stack`)

| Element | Value |
|---|---|
| model_id | `us.anthropic.claude-sonnet-4-6` |
| temperature | `0.0` |
| max_tokens | `8192` |
| max_hypotheses | `12` |
| prompt | `v6_prompt_v1` |
| packet surface | `v5a2_packet_v1` |
| schema | `hypothesis_set_schema_v4` |
| firewall | `firewall_v5` |
| validator | `validator_v5` |

---

## 1. Evidence depth — what V6.1 *actually* exposed

V6.1 ran two arms over 10 fixtures. The **base** arm is a deliberately impoverished control;
the **research** arm is the one that matters for the V8A question. Exposure states are read
from each packet's `AVAILABILITY_MAP` section, aggregated over all 10 fixtures.

| Dimension | base arm | research arm |
|---|---|---|
| `match_level_observations` | NOT_EXPOSED_IN_PACKET ×10 | **EXPOSED ×10** |
| `historical_venue_conditioning` | NOT_EXPOSED_IN_PACKET ×10 | **EXPOSED ×10** |
| `recent_window_summaries` | NOT_EXPOSED_IN_PACKET ×10 | **EXPOSED ×9**, EXPOSED_LOW_COVERAGE ×1 |
| `opponent_profile` | NOT_EXPOSED_IN_PACKET ×10 | **EXPOSED ×9**, EXPOSED_LOW_COVERAGE ×1 |
| `competition` | NOT_EXPOSED_IN_PACKET ×10 | **EXPOSED ×10** |
| `own_formation_family` | NOT_EXPOSED_IN_PACKET ×10 | EXPOSED_LOW_COVERAGE ×10 |
| `opponent_formation_family` | NOT_EXPOSED_IN_PACKET ×10 | EXPOSED_LOW_COVERAGE ×10 |
| `formation_recorded_history` | EXPOSED_LOW_COVERAGE ×10 | EXPOSED_LOW_COVERAGE ×10 |
| `target_fixture_venue_context` | EXPOSED ×10 | EXPOSED ×10 |
| `xg` | EXPOSED ×9, LOW ×1 | EXPOSED ×9, LOW ×1 |
| `half_time_score_state` | **NOT_PROVIDED_BY_SOURCE ×10** | **NOT_PROVIDED_BY_SOURCE ×10** |
| `match_period` | NOT_PROVIDED_BY_SOURCE ×10 | NOT_PROVIDED_BY_SOURCE ×10 |
| `minute_level_events` | NOT_PROVIDED_BY_SOURCE ×10 | NOT_PROVIDED_BY_SOURCE ×10 |
| `expected_formation` | NOT_PROVIDED_BY_SOURCE ×10 | NOT_PROVIDED_BY_SOURCE ×10 |
| `lineup` | NOT_DERIVABLE_PIT_SAFE ×10 | NOT_DERIVABLE_PIT_SAFE ×10 |
| `injuries`, `weather`, `referee`, `player_ratings`, `market_prices` | NOT_PROVIDED_BY_SOURCE ×10 | NOT_PROVIDED_BY_SOURCE ×10 |

### 1.1 Answering the brief's evidence-depth checklist

The V8A brief §4 asks, item by item, whether V6.1 exposed enough to study each of the
following. Answers are for the **research arm**, which is the correct comparator for a new
research protocol:

| Asked about | Exposed in V6.1 research arm? | Evidence |
|---|---|---|
| individual historical fixture rows | **YES** | `MATCH_LEVEL_OBSERVATIONS`, 2 blocks/fixture (HOME, AWAY), 8–30 rows each, mean 25.9, 518 rows total |
| shots FOR / AGAINST | **YES** | `total_shots_for`, `total_shots_against` on every row; 0.4% null |
| SoT FOR / AGAINST | **YES** | `shots_on_target_for/against`; 0.4% null |
| corners FOR / AGAINST | **YES** | `corners_for/against`; 0.4% null |
| possession | **YES** | `possession_for/against`, percent; 0.4% null |
| crosses (provider-safe) | **YES** | `accurate_crosses_for/against`; 0.4% null. Completion **count**, no attempts denominator |
| tackles / fouls / cards | **YES** | `tackles_*` 0.4%, `fouls_*` 1.0%, `yellow_cards_*` 4.4%, `red_cards_*` 0.0% null (but see §1.3) |
| home / away | **YES** | `venue` on every row + `historical_venue_conditioning` EXPOSED |
| competition | **YES** | `competition_ref` on every row + `competition` EXPOSED |
| recent vs longer-run behaviour | **YES** | `DERIVED_SUMMARIES` carried 460 rows/fixture incl. windowed summaries; `recent_window_summaries` EXPOSED |
| formation where available | **PARTIAL / SPARSE** | `own_formation_recorded` present on **86/518 rows = 16.6%**; declared EXPOSED_LOW_COVERAGE with the note "coverage 0.137. Below 0.5 this is too sparse to condition on." |
| half-state where supported | **NO — NOT SUPPORTED AT ALL** | `half_time_score_state` and `match_period` are `NOT_PROVIDED_BY_SOURCE` in every packet |
| opponent profiles | **YES** | `OPPONENT_PROFILE_SUMMARIES`, 64 rows/fixture |

### 1.2 The finding that matters most

**V6.1's research arm was not evidence-starved.** It already carried, per fixture, 2 blocks
of real per-match rows with **46 columns = 23 canonical metrics × {FOR, AGAINST}** aligned on
each row, plus date, venue, competition, opponent reference and recorded formations; on top of
460 derived summary rows and 64 opponent-profile rows.

This directly constrains the V8A hypothesis. The post-V7.1 conjecture is that the previous
protocol "underused the model's football reasoning capability by asking it to move too
directly from evidence to structured hypotheses." The evidence audit says the shortfall was
**not** an evidence-availability shortfall. Whatever V8A improves, it cannot be *"the model
finally gets to see raw rows"* — it already did. If V8A shows a difference, it must come from
**procedure**, not from evidence depth. Section 2 shows the procedural surface was indeed
close to empty.

This also sets a real constraint on V8A's own design: adding more raw rows is not expected to
be the active ingredient, and V8A must not claim it as one.

### 1.3 Two provider caveats that V8A must carry forward

* **`red_cards` shows 0.0% null but is `NULL_COERCED_TO_ZERO_AT_ADAPTER`.** Per
  `v5a1_semantics`, the provider omits the field in 2988/3312 team-matches. A `0` in this
  column may be a provider omission, not an observed zero. The brief's "NULL != zero" rule
  applies to this field specifically, and the apparent 0.0% null rate is an artifact of the
  coercion, not evidence of complete coverage.
* **`accurate_crosses` is a completion COUNT with no attempts denominator.** No completion
  percentage can be formed. Any V8A candidate phrased as cross *accuracy* is unmeasurable.

---

## 2. Research procedure — what V6.1 forced the model to do

The brief §4 asks whether V6.1 explicitly forced six things. Answers are read from
`v6_prompt.SYSTEM_PROMPT` and from the required fields of `hypothesis_set_schema_v4`.

`schema_v4` required exactly these item fields:

```
hypothesis_id, research_family, subject, question, target_metrics, side, window,
conditions, comparison, evidence_refs, candidate_confounders, required_capabilities,
sufficiency, priority
```

plus one optional field, `evidence_summary`.

| Forced by V6.1? | Verdict | Basis |
|---|---|---|
| 1. team behavioural analysis | **NO** | No prompt phase requires it. No schema field carries an observation about team behaviour. The only free-text fields are `question` and the optional `evidence_summary` |
| 2. attack-v-defense matchup analysis | **NO** | The words attack/defense appear nowhere in the prompt as an analytic step. `side` is a single FOR/AGAINST enum on one subject — the schema cannot even *express* a Team-A-attack × Team-B-defense pairing as a first-class object |
| 3. mechanism search | **NO** | No `mechanism` field exists and the prompt never asks why a pattern might occur |
| 4. generic-baseline comparison | **NO** | The model was never shown any generic hypothesis, never asked whether enumeration already covers its question, and there was no second pass of any kind |
| 5. self-criticism | **NO** | No critic step. `candidate_confounders` is a required *list field*, which is a partial and purely declarative relative — it asks what might confound, never asks the model to reject its own candidate |
| 6. abstention | **YES — genuinely** | The prompt states that marking a hypothesis `INSUFFICIENT_EVIDENCE` "is a correct and valued answer", permits citing evidence that shows why, and `sufficiency` is a required field |

### 2.1 What the V6.1 prompt *did* enforce well

The audit should not be read as a criticism of V6.1's discipline, which was strong:

* a hard numeric firewall (no probabilities, odds, EV, edges, stakes, advantage scores,
  latent strength, matchup scores, effect sizes);
* a single shared vocabulary between `AVAILABILITY_MAP`, `conditions[].dimension` and
  `required_capabilities`;
* mandatory evidence grounding via `evidence_refs` copied exactly from the packet;
* an explicit cohort≠baseline contrast rule;
* an explicit anti-priming stance — the prompt deliberately refuses to say what is
  interesting, and both arms receive a byte-identical system prompt.

V8A inherits all six of these unchanged.

### 2.2 The structural gap V8A targets

V6.1's response schema has **no surface on which reasoning could occur before the structured
answer.** The model was asked to emit a list of up to 12 fully-formed structured hypothesis
objects, and nothing else. There is no place to record what it observed, no place to state a
mechanism, no place to state a falsifier, no place to compare against enumeration, and no
second pass.

That is precisely the shape of "moved too directly from evidence to structured hypotheses,"
and it is confirmed here **structurally** — from the schema's `required` list and the prompt
text — rather than inferred from outcomes.

---

## 3. Output limits and model parameters (frozen V6.1 values)

| Parameter | V6.1 |
|---|---|
| max hypotheses per response | 12 |
| max_tokens | 8192 |
| temperature | 0.0 |
| calls | 36 (10 fixtures × 2 arms + repeats per `v6_schedule_v1`) |
| exact input tokens | provider-native `CountTokens`, e.g. 17,892 for the first base request |
| passes | **one** |

V8A sets max hypotheses to **8** (brief §21) — deliberately *lower* than V6.1's 12, because
the brief states abstention is successful behaviour and filling slots is not rewarded.

---

## 4. Consequences carried into the V8A design

1. **Arm A is admissible and will be run for real** — the exact V6.1 prompt, surface, schema
   and parameters, on the V8A development fixtures.
2. **Half-state is not researchable in this corpus.** `half_time_score_state` and
   `match_period` are `NOT_PROVIDED_BY_SOURCE`. V8A's capability envelope must say
   `UNAVAILABLE`, the prompt must not invite half-state questions as though they were
   supported, and any half-state rate in the V8A report is expected to be structurally zero —
   which is a property of the corpus, not a failure of a model.
3. **Formation is sparse (16.6% of rows), not absent.** It is legitimate as *context* but the
   brief's §3 warning applies with force: at this coverage a formation-conditioned cohort will
   usually be too thin to measure. V8A must treat formation availability as a per-fixture
   quantity and expose the real coverage number to the model.
4. **xg is SUPPORTED here (~90% row coverage), contrary to the brief's illustrative example.**
   Brief §5 says explicitly "do not hard-code the example; use actual provider/corpus
   semantics." Marking xg UNSUPPORTED would misdescribe this corpus and corrupt every
   `unsupported_metric` and `insufficient_capability` rate in §22.
5. **The active ingredient under test is procedure, not evidence.** V8A's evidence packet is
   therefore built to be *at least* as rich as V6.1's research arm, and the difference between
   Arm A and Arm B is concentrated in the protocol: phased reconnaissance, an explicit
   attack×defense interaction map, a mechanism and falsifier requirement, a self-critic, and a
   second-pass generic novelty challenge.
