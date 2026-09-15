# V6 — Firewall Semantics Audit (§4, §5)

**Zero spend.** `firewall_v5` + `v6_numeric_contract`, verified on real packets and synthetics.

## 1. The problem §4 forbids solving by loosening

Both V5A.2 research responses were rejected whole on one token: `'50%'` inside a question. The rule (`firewall_v2` CLASS_B, EVIDENCE_VALUE_REPRODUCTION) predates V5A.2, was correctly applied, and the model did write the number. The naive fix — stop blocking class B — is wrong in both directions:

- `+0.6 corner advantage` would be **allowed** if 0.6 happened to resolve against a packet value (an effect size slips through).
- `recorded 60% possession` would be **blocked** because a bare integer's ±0.05 tolerance fails against a true 60.3 (the mandate's own ALLOWED example is denied).

Resolution is the wrong discriminator.

## 2. The distinction V6 draws (§4)

`firewall_v5` classifies on the **frame** the number sits in — the words around it and the field it was written into — not on whether it resolves:

`EVIDENCE_VALUE_REPRODUCTION` vs `MODEL_AUTHORED_PREDICTIVE_QUANTIFICATION`.

Three-step decision, in order:
1. **DENY** on any predictive/target marker in the sentence (`probability`, `chance`, `odds`, `advantage`, forward-looking verbs, "in the upcoming fixture", "+N by", "percentage points"). Unconditional — `+0.6 corner advantage` cannot be rescued by a coincidental resolution.
2. **ALLOW** only if a historical marker is present AND every literal resolves at its written precision AND the field's contract permits a reproduced value.
3. **DENY** everything else (conservative default).

Detection is a **strict superset** of `firewall_v4` (verified: every v4 and base pattern is present in `firewall_v5._ALL_PATTERNS`). What changes is disposition, only in the one direction §4 authorises.

## 3. Field contract

| field | policy |
|---|---|
| `question` | the research question; NO number allowed. A predictive number and a reproduced historical value both reject the hypothesis (a value belongs in `evidence_summary` or an evidence id). |
| `evidence_summary` | OPTIONAL (schema_v4). May reproduce a packet-supplied value under the frame contract. Policed literal-by-literal — every numeric literal must be framed and resolved. |

The blast radius of any violation is **one hypothesis** (§3). §4's "a copied value must not automatically destroy an otherwise valid response" holds by construction.

## 4. The numeric-authority FIELD contract (§5)

`v6_numeric_contract` runs **before** the schema gate, so a model that writes `effect_size: 0.31` is recorded as `MODEL_NUMERIC_CONTRACT_VIOLATION`, not as a generic malformed object. It bans, additive over the frozen `firewall.FORBIDDEN_FIELD_NAMES`: `effect_size`, `expected_delta`, `confidence_score`, `advantage_score`, `edge`, `uplift`, `coefficient`, `p_value`, and their spellings. A model-authored `sample_n` is deliberately NOT permitted (the engine computes N; a copy belongs in `evidence_summary`).

No field of a hypothesis may carry a bare numeric literal (`NUMERIC_ALLOWED_LEAVES = ∅`).

## 5. Verified cases (test suite)

| test | result |
|---|---|
| `historical_percentage_not_predictive_probability` | framed value in `evidence_summary` → VALID |
| `target_probability_blocked` | "62% chance in the upcoming fixture" → FIREWALL, in question OR evidence_summary |
| `effect_size_blocked` | `effect_size` field → NUMERIC_CONTRACT (not schema) |
| `evidence_numeric_citation_allowed_under_contract` | cohort-provenance summary → VALID |
| `firewall_not_counted_as_schema_invalid` | firewall and schema are distinct classes |
| `firewall_v5_denies_everything_v4_denied_in_question` | `'50%'` in a question still denied |
