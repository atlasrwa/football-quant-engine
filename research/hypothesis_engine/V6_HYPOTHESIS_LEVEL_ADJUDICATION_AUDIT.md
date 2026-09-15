# V6 — Hypothesis-Level Adjudication Audit (§3, §8, §19)

**Zero spend.** All results below come from running the production adjudicator
(`validator_v5.adjudicate`) on real V5A.2 packets and on synthetic responses.

## 1. The V5A.2 failure this fixes

`validator_v4.validate` had four early returns *before* the per-hypothesis loop — schema, identity, numerical-authority firewall, latent grading. In the V5A.2 live run the firewall return fired twice on a single `'50%'` in one question, and **24 hypotheses with 183 well-formed evidence references were discarded unread**. One bad hypothesis destroyed its siblings.

## 2. The fix, in three places

- **`schema_v4`** splits the whole-document schema into `envelope_schema()` (identity + `hypotheses` is an array of objects) and `hypothesis_item_schema()` (the full closed item contract, applied to ONE element). Only the envelope can be response-fatal.
- **`firewall_v5.scan_hypothesis`** scans ONE hypothesis in isolation, not the whole payload.
- **`validator_v5.adjudicate`** runs every gate for every hypothesis and records every result; the class is the FIRST failed gate (`v6_classes.GATE_ORDER`) while diagnostics stay complete (§19).

## 3. The only RESPONSE_FATAL conditions (§3)

1. payload is not an object
2. `hypotheses` missing or not an array
3. an element of `hypotheses` is not an object
4. identity binding fails (`fixture_id`/`packet_hash` ≠ the packet sent)

Every other failure is adjudicated per hypothesis. Verified in `test_response_fatal_only_for_unrecoverable_structure`: a batch where **every** hypothesis carries a firewall violation is NOT fatal — each is measured.

## 4. The failure taxonomy (§8) — explicit enums, never inferred from prose

Response: `RESPONSE_PARSE_FATAL`, `VALID_MODEL_RESPONSE`, `INFRASTRUCTURE_FAILURE`.
Hypothesis: `VALID_HYPOTHESIS`, `VALID_ABSTENTION`, `MODEL_NUMERIC_CONTRACT_VIOLATION`, `MODEL_SCHEMA_INVALID`, `MODEL_GROUNDING_VIOLATION`, `MODEL_AVAILABILITY_VIOLATION`, `MODEL_FIREWALL_VIOLATION`, `MODEL_COMPARATOR_INVALID`, `MODEL_DEGENERATE_HYPOTHESIS`, `MODEL_REDUNDANT_HYPOTHESIS`, `MODEL_COMPILER_INVALID`.

`INFRASTRUCTURE_FAILURE` is **excluded** from `HYPOTHESIS_MODEL_FAILURE_CLASSES` — our defect never enters a model failure rate. Firewall and schema are separate classes (fixes the V5A.2 conflation).

## 5. Adversarial battery result (`adversarial_battery.json`, §33)

A 12-hypothesis response: 6 valid (one opponent-profile interaction, one evidence-backed abstention, one historical value reproduced in `evidence_summary`) and 6 deliberate one-each violations.

| observed | count |
|---|---|
| VALID_HYPOTHESIS | 5 |
| VALID_ABSTENTION | 1 |
| MODEL_SCHEMA_INVALID | 1 |
| MODEL_GROUNDING_VIOLATION | 1 |
| MODEL_AVAILABILITY_VIOLATION | 1 |
| MODEL_FIREWALL_VIOLATION | 1 |
| MODEL_COMPARATOR_INVALID | 1 |
| MODEL_REDUNDANT_HYPOTHESIS | 1 |

- **class mismatches: 0** — every hypothesis received exactly its intended class
- **valid siblings survived: 6/6**
- **response fatal: no**

Every §8 class appears distinctly; none is conflated with `MODEL_SCHEMA_INVALID`.

## 6. Zero/unmeasured distinction (§20)

A fatal response produces a scorecard whose measurements are `None` (not `0.0`) with `measured=False`. Verified in `test_fatal_response_scorecard_is_none_not_zero`. V5A.2's `_blank_score()` returned zeros, which its own report had to footnote as placeholders; V6 cannot do that.
