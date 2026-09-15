# V5A2 — Packet Surface Contract Audit

**ZERO SPEND.** Every result here comes from the frozen packets and the deterministic
validator; no model was called.

Artifacts: `out/v5a2/surface_battery.json`, `roundtrip_audit.json`,
`availability_audit.json`, `walkthrough.json`.

---

## 1. Why the tests are generated rather than written

V5A.1 shipped 47 passing hand-written pre-spend tests and **D1 survived every one of them**.
Not because the tests were careless, but because every synthetic hypothesis in them either
left `required_capabilities` empty or happened to contain a correct context-source name.
Nobody wrote the one case that mattered — *"use the term the packet advertises"* — because
from the inside that case looks too obvious to be worth writing down.

So the battery does not enumerate cases. It **generates** them from the packets:

```
for every term the packet advertises
  × every field that term is legal in
  × every legal value / axis of that term
  × both arms × every fixture
```

If a term is added, renamed or re-exposed, the battery grows to cover it without anyone
remembering to update a list. **If you find yourself typing a term literal into a test, that
test would not have caught D1.**

## 2. The hard rule

> **A structurally correct use of an advertised term must never return `SCHEMA_INVALID`.**

It may be rejected downstream — an exposed term can still be inadmissible for a given
packet, and a rejection there is a real scientific observation. But the model must never be
told its response was *malformed* for using a word the packet handed it.

A second rule covers the inverse: no case may be classified
`INFRASTRUCTURE_CONTRACT_FAILURE`. That class counts *our* defects; its expected value after
this closure is zero.

## 3. Results

| Measure | Value |
|---|---|
| cases generated | **3,680** |
| rule violations | **0** |
| advertised term returning `SCHEMA_INVALID` | **0** |
| `INFRASTRUCTURE_CONTRACT_FAILURE` | **0** |
| `MODEL_VISIBLE_ENUM_COVERAGE` | **121 / 121 = 100 %** |

Case breakdown:

| Surface | Cases |
|---|---|
| `conditions` (term × value × axis) | 1,680 |
| `target_metrics` | 540 |
| `required_capabilities` | 400 |
| `research_family` | 260 |
| negative (must-reject) | 240 |
| abstention contract | 120 |
| `subject` | 120 |
| `comparison` | 100 |
| `window` / `priority` / `side` / `sufficiency` | 220 |

The 200 `SCHEMA_INVALID` outcomes are **all** intentional negatives — 9 of the 12 negative
case types — and none involves an advertised term.

## 4. Round-trip invariant (§4)

Every one of the 20 terms is checked for: presence in the capability enum where its role
permits, declaration in **every** packet's availability map, and deterministic translation
to the internal namespace.

```
n_terms: 20    n_broken: 0
```

All 8 conditionable terms round-trip `term → internal → term` unchanged.
`test_no_two_terms_share_an_internal_dimension` guards the property the inverse depends on.

## 5. Negative contract (§9)

All 240 negative cases rejected, each for its stated reason:

| Case | Outcome |
|---|---|
| `unknown_dimension` | SCHEMA_INVALID |
| `retired_bare_venue` (`venue`) | SCHEMA_INVALID |
| `internal_namespace_leak` (`venue` as capability) | SCHEMA_INVALID |
| `internal_ctx_source_leak` (`historical_formation`) | SCHEMA_INVALID |
| `cross_dimension_value` (venue term = `HIGH`) | SCHEMA_INVALID |
| `profile_without_axis` | SCHEMA_INVALID |
| `axis_on_axisless_dimension` | SCHEMA_INVALID |
| `unknown_metric` | SCHEMA_INVALID |
| `extra_property` | SCHEMA_INVALID |
| `excluded_metric` (`npxg`) | UNSUPPORTED_CONTEXT_SOURCE |
| `fabricated_evidence` | INSUFFICIENT_EVIDENCE |
| `numeric_claim_in_question` | NUMERICAL_AUTHORITY_VIOLATION |

The last one is **D5**, found here on the battery's first run. The frozen prose patterns
catch `"probability of 0.62"` but not `"There is a 0.62 probability…"`, because the pattern
requires the noun to be followed by `of|is|are|at`. `question` is the only free-text field in
the schema and therefore the only place a number can appear at all, so this was the single
surface the firewall exists to cover — with a hole in it, present since V2 and never
exercised because no hand-written test phrased a probability that way.

`firewall_v4` closes it **additively**: v3's verdict is taken as-is and the new patterns can
only add violations. `test_firewall_v4_is_a_strict_superset_of_v3` asserts `v3 ⊆ v4` across a
16-question corpus, and `test_firewall_v4_adds_no_new_flags_on_legitimate_questions` bounds
the false-positive cost at zero over the nine legitimate research questions in it.

## 6. Abstention contract (§5)

All six cells behave as specified, on every packet:

| Case | Expected | Observed |
|---|---|---|
| abstain, no refs | accept | accept |
| abstain, valid refs | accept | accept |
| abstain, fabricated refs | reject | reject |
| sufficient, no refs | reject | reject |
| sufficient, valid refs | accept | accept |
| sufficient, fabricated refs | reject | reject |

## 7. Availability map, per arm

All 20 terms are declared in every packet in both arms — `declared == O.all_terms()` is
asserted per packet.

| Term | Base arm | Research arm |
|---|---|---|
| `target_fixture_venue_context` | EXPOSED | EXPOSED |
| `xg` | EXPOSED | EXPOSED |
| `formation_recorded_history` | EXPOSED_LOW_COVERAGE | EXPOSED_LOW_COVERAGE |
| `match_level_observations` | NOT_EXPOSED_IN_PACKET | EXPOSED |
| `historical_venue_conditioning` | NOT_EXPOSED_IN_PACKET | EXPOSED |
| `recent_window_summaries` | NOT_EXPOSED_IN_PACKET | EXPOSED |
| `opponent_profile` | NOT_EXPOSED_IN_PACKET | EXPOSED |
| `competition` | NOT_EXPOSED_IN_PACKET | EXPOSED |
| `own_formation_family` | NOT_EXPOSED_IN_PACKET | EXPOSED_LOW_COVERAGE |
| `opponent_formation_family` | NOT_EXPOSED_IN_PACKET | EXPOSED_LOW_COVERAGE |
| `expected_formation`, `injuries`, `weather`, `referee`, `half_time_score_state`, `match_period`, `minute_level_events`, `player_ratings`, `market_prices` | NOT_PROVIDED_BY_SOURCE | NOT_PROVIDED_BY_SOURCE |
| `lineup` | NOT_DERIVABLE_PIT_SAFE | NOT_DERIVABLE_PIT_SAFE |

**Conditionable terms: base = 0, research = 5.** The base arm is a summary-only packet; it
supports unconditioned questions and honest abstention, and nothing else. V5A.1 advertised
`competition` there, which was false.

## 8. Human walkthrough (§11)

Seven hypothesis types, hand-written, both arms, fixture `mt_010243515`:

| Type | Base | Research |
|---|---|---|
| 1 unconditioned volume | ACCEPT | ACCEPT |
| 2 historical venue split | reject — *comparison requires `historical_venue_conditioning`, packet declares `NOT_EXPOSED_IN_PACKET`* | ACCEPT |
| 3 recent vs long | reject — *requires `recent_window_summaries`* | ACCEPT |
| 4 opponent profile | reject — *declares it requires `opponent_profile`* | ACCEPT |
| 5 formation | reject — *declares it requires `own_formation_family`* | ACCEPT |
| 6 interaction | reject — *requires `historical_venue_conditioning`* | ACCEPT |
| 7 abstention citing the gap | ACCEPT | ACCEPT |

Base 2/7, research 7/7. Every base rejection **names the term the model wrote and the state
the packet declared for it**. This is the readable half of the audit: the generated battery
proves nothing is malformed; the walkthrough shows the apparatus behaves sensibly.

`V5A2_PACKET_SCHEMA_ROUNDTRIP_VALIDATED`
`V5A2_SYNTHETIC_SURFACE_COVERAGE_100_PERCENT`
