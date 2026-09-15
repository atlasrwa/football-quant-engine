# V6 — Call Order and Stop Rule Audit (§6, §7, §8)

**Zero spend.** `v6_schedule` + `v6_stop`, asserted at freeze in `call_schedule.json`.

## 1. The V5A.2 seam this fixes

`_freeze_v5a2.py` emitted a fixture-major manifest with repeats folded into a count; `_execute_v5a2.py` expanded that count in place. The realised order was `fixture1/base ×4, fixture1/research ×4, fixture2/...`. The rate stop became eligible at call 6 — and **calls 1–6 were all one fixture**. It fired on 2/2 research responses from a single fixture and halted a ten-fixture experiment.

Neither file was wrong alone: the manifest never said the order, and the driver invented one.

## 2. The V6 schedule (§6)

`v6_schedule.build_sequence` emits a **flat list with an explicit `seq`**; the driver consumes it verbatim (`driver_may_expand_counts: False`). There is no count to expand.

Ordering: round-robin over fixtures, A and B adjacent within a fixture, repeats deferred to later rounds.

```
round 1   f1/A f1/B  f2/A f2/B  ...  f10/A f10/B     one primary pair per fixture
round 2   g1/A g1/B  g2/A g2/B  g3/A g3/B  g4/A g4/B repeat 1 on the 4 repeat fixtures
round 3   g1/A g1/B  ...                              repeat 2
```

**36 calls** total (20 primaries + 16 repeats). A/B adjacent so a mid-round halt still leaves whole paired samples.

## 3. Properties asserted at freeze (`freeze_assertions`)

At the eligibility point (`seq = 6`):
- prefix contains **both arms** ✓
- prefix spans **≥ 3 distinct fixtures** ✓
- A and B **adjacent within each fixture** ✓
- **no fixture dominates** the prefix ✓
- ≥ 3 repeat groups of size ≥ 2 **per arm** (4 scheduled) ✓

`freeze_problems: []` — the sequence is freezable. A sequence that failed these is never written into a preregistration, so §37's "call ordering is fixture-dominated" is enforced mechanically.

## 4. Diversity-gated stop rules (§7)

No model-behaviour rate rule is even *evaluated* until ALL of:
- ≥ 3 distinct fixtures observed (`MIN_STOP_FIXTURES`)
- ≥ 2 valid calls in EACH arm (`MIN_STOP_VALID_CALLS_PER_ARM`)
- ≥ 6 calls charged (`MIN_CALLS_BEFORE_RATE_STOP`)

Verified in `test_stop_rule_requires_fixture_diversity`: a 40/50 schema-invalid rate on ONE fixture does **not** fire (rules gated); the same rate across 3 fixtures and both arms DOES fire.

## 5. Per-category numerators (§8)

V5A.2 had one rule whose numerator was `failure_class == MODEL_SCHEMA_INVALID`, a field also stamped on firewall violations — so a rule named for schema invalidity fired on zero schema-invalid responses. V6 has one rule per §8 category, each reading its own count and naming its category:
`V6_STOP_MODEL_FIREWALL_VIOLATION_RATE`, `..._NUMERIC_CONTRACT_...`, `..._GROUNDING_...`, `..._SCHEMA_INVALID_RATE`, `V6_STOP_RESPONSE_PARSE_FATAL_RATE`, all at threshold 0.30 on the hypothesis denominator.

**No availability-violation stop rule exists** — the base arm produces conditioned-hypothesis inadmissibility by construction (§18); a rate rule there would halt on the arm definition, not on model behaviour. The category is counted and reported, never a stop.

## 6. Apparatus rules are NOT diversity-gated

`V6_STOP_INFRASTRUCTURE_FAILURE` (n≥1) and `V6_STOP_TRANSPORT` (3 consecutive) fire immediately — our defect does not become more real with more fixtures. Verified in `test_apparatus_stop_is_not_diversity_gated`.
