# V6 — Full Packet Audit and Human Walkthrough (§31, §35)

**Zero spend.** Backed by `out/v6/packet_identity_audit.json`, `pit_audit.json`, `arm_isolation_audit.json`, `evidence_family_audit.json`, `human_walkthrough.json`.

## 1. Packets are the frozen V5A.2 packets (§2, §31)

`packet_identity_audit.json`: **0 differences** across 20 packets (10 fixtures × 2 arms) vs the frozen V5A.2 packets. V6 re-derives and re-keys nothing.

## 2. PIT and provider safety (§31)

`pit_audit.json`: **0 problems**. Every serialized observation has `kickoff_unix < information_cutoff`; no packet names its own target fixture outside the `fixture_id` field. No target outcome, closing line, future market, or future lineup/injury is present (inherited from the V5A.1/V5A.2 provider-semantics audits, which remain frozen and passing).

## 3. Arm isolation (§2)

`arm_isolation_audit.json`: **0 identity leaks**, **no treatment labels** found across the entire serialized packet set. `packet_schema_version`, `evidence_interface_version`, `ontology_version`, `fixture_id`, `information_cutoff_unix` are identical across arms. The arms differ only in which evidence sections are present.

## 4. Evidence families by arm (§13)

`evidence_family_audit.json`, fixture mt_010243515:

| arm | id kinds |
|---|---|
| base | SUMMARY, FORMATION, AVAIL (114 ids) |
| research | + MATCH, PROFILE (3366 ids) |

## 5. Human walkthrough (§35) — one Arm A packet, one Arm B packet, exact prompt, exact schema

`human_walkthrough.json`. A five-shape response was run through the production path on real packet mt_010243515:

| id | shape | expected | observed | match |
|---|---|---|---|---|
| H1 | valid | VALID_HYPOTHESIS | VALID_HYPOTHESIS | ✓ |
| H2 | opponent-profile | VALID_HYPOTHESIS | VALID_HYPOTHESIS | ✓ |
| H3 | firewall (predictive %) | MODEL_FIREWALL_VIOLATION | MODEL_FIREWALL_VIOLATION | ✓ |
| H4 | unavailable dimension | MODEL_AVAILABILITY_VIOLATION | MODEL_AVAILABILITY_VIOLATION | ✓ |
| H5 | evidence-backed abstention | VALID_ABSTENTION | VALID_ABSTENTION | ✓ |

- response_class: `VALID_MODEL_RESPONSE`, not fatal
- **valid siblings H1/H2/H5 survived** rejected H3/H4
- only intended hypotheses failed
- scorecard: n_qualified 2, qualified_rate 0.5, 1 abstention

Exact system prompt sha and exact output schema (`hypothesis_set_schema_v4`) are recorded in the artifact.

## 6. Exact output schema (§35)

`schema_v4` = `schema_v3` item + one optional `evidence_summary` field. `diff_against_v3`: identical after removing `evidence_summary`; no item property removed; `required` unchanged; `evidence_summary` is optional. `schema.py`, `schema_v2.py`, `schema_v3.py` are unedited (hashes in `frozen_upstream_module_hashes`).
