# V5A2 — Full Packet Audit

**ZERO SPEND.** Every claim here is computed from the frozen packets by
`_build_v5a2.py` and recorded in machine-readable form.

Artifacts: `evidence_identity_audit.json`, `availability_audit.json`,
`arm_isolation_audit.json`, `pit_audit.json`, `roundtrip_audit.json`,
`ontology_snapshot.json`, `packets_base.json`, `packets_research.json`.

---

## 1. The evidence is V5A.1's, unchanged (§2)

The packets are **not rebuilt from the corpus**. They are the frozen V5A.1 packets with the
availability map re-surfaced. That makes "the evidence is identical" a provable byte-level
claim rather than a promise:

```
packets compared            20  (10 fixtures × 2 arms)
evidence differences         0
```

Every section except `AVAILABILITY_MAP` hashes identically to the V5A.1 packet it came from.
Each packet also carries `derived_from_v5a1_packet_hash`, so the lineage is checkable from
the artifact alone.

Unchanged from V5A.1 and not revisited: the history policy, the 23 canonical metrics and 4
exclusions, `BASELINE_UNIVERSE = ALL_PIT_SAFE_PRIOR_MATCHES_UNCAPPED`,
`MAX_RAW_ROWS_PER_TEAM = 30`, `SUMMARY_ESTIMATOR = UNSHRUNK_ARITHMETIC_MEAN`, the evidence-id
grammar, the opponent-profile banding, raw-cell fidelity, and section order.

## 2. Structure

| | Base arm | Research arm |
|---|---|---|
| sections | 6 | 8 |
| payload bytes | 44,774 – 45,176 | 129,305 – 141,265 |
| est. input tokens | 16,680 – 16,830 | 54,917 – 59,996 |
| citable evidence ids | 112 – 114 | 2,606 – 3,366 |
| conditionable terms | **0** | **5** |

Section order (load-bearing, unchanged): fixture context → availability map → metric
semantics → *[match rows]* → derived summaries → *[opponent-profile cohorts]* → formation
context → citation instructions. Raw football record before the aggregates.

## 3. Availability map

All **20** ontology terms are declared in **every** packet in both arms —
`declared == O.all_terms()` is asserted per packet by
`test_availability_map_declares_every_model_visible_term`. The per-arm state table is in
`V5A2_PACKET_SURFACE_CONTRACT_AUDIT.md` §7.

Three states, kept separate and never collapsed: `PROVIDER_AVAILABLE`,
`DERIVABLE_PIT_SAFE`, `EXPOSED_TO_LLM`. The prompt instructs the model to act **only** on
`EXPOSED_TO_LLM`; the other two exist so an absence is visibly deliberate.

The map now also carries the ontology snapshot and the term rule, so the single-language
guarantee is something the model is **told**, not something we hope it infers.

## 4. Arm isolation (§26)

```
fixtures compared                    10
identity leaks                        0
treatment labels found in packets     0
```

`packet_schema_version`, `evidence_interface_version`, `packet_surface_version`,
`ontology_version`, `fixture_id` and `information_cutoff_unix` are identical across arms. The
arms differ **only** in which evidence sections are present and what the availability map
declares.

The blinding check was corrected during this audit. It previously substring-matched
treatment labels, so `control` matched inside *"the cohort is not a controlled comparison"* —
a statistical caveat in a static disclaimer, present only in the research arm because that
arm carries the opponent-profile section the disclaimer belongs to. `blinding_violations()`
now matches whole words. **The fix is to match what the rule means, not to add the phrase to
an exemption list** — `test_blinding_check_discriminates_words_from_substrings` pins both
directions.

## 5. PIT safety and leakage (§25)

```
problems found: 0
```

Checked per packet: no packet names its own target fixture outside the declared `fixture_id`
field, and every match-level observation kicked off **strictly before** the information
cutoff. Inherited unchanged from V5A.1, which built the evidence.

## 6. Numerical authority

No field in the response schema is of type `number`. A probability, edge, odds quote or
effect size has **no legal place to be written** — a structural impossibility, not a filtered
string. The single free-text field (`question`) is covered by the prose firewall, now
`firewall_v4` (see D5 in the surface contract audit).

## 7. Byte reproducibility (§24)

`test_frozen_artifacts_agree_across_seeds` re-derives the research packet hash, the
`schema_v3` content hash, the ontology snapshot hash and the evaluator version stamp in
subprocesses at `PYTHONHASHSEED` ∈ {1, 2, 3, 12345}, asserts all four agree, **and** asserts
the result matches the packet hash actually on disk. A frozen artifact whose bytes depend on
the interpreter's hash seed is not frozen — V5A.1 shipped exactly such a defect
(`Counter` over a `set`) and it was caught the same way.

## 8. Frozen-module protection

`PREREGISTRATION.json` records `frozen_upstream_module_hashes` for 17 modules —
`schema.py`, `schema_v2.py`, `validator{,_v2,_v3}.py`, `firewall{,_v2,_v3}.py`,
`vocabulary.py`, `capability.py`, `condition_contract.py`, `query_plan.py`, and the V5A.1
oos modules. The execution driver re-verifies all of them at $0.00 and aborts on any change.

```
schema_v2 content hash   7879c6ad5a2ba926…   (unchanged)
CHAMPION artifact        matches frozen sha  (unchanged, read-only)
```

## 9. Test suite

```
V5A.2 pre-spend suite   44 tests
V5A.1 pre-spend suite   47 tests   (still passing, no regressions)
full oos suite         127 tests   all passing
```

`V5A2_INTERFACE_CONTRACT_VALIDATED`
