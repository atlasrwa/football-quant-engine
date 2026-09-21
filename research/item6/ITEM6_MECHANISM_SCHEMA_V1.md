# ITEM6_MECHANISM_SCHEMA_V1

`item6_mechanism_schema_v1` · code: `src/research/item6/schema.py` · `K_MECHANISMS_PER_FIXTURE = 5`

Structured-output contract for the model's mechanism-discovery response. Two-phase object:

- **PHASE A — mechanism discovery**: a list of proposed mechanisms (or explicit abstention).
- **PHASE B — research specification**: per-mechanism measurable-relationship description.
- **PHASE C — deterministic formalization** is NOT part of this schema; code owns it.

## Response shape

```json
{"fixture_id": "<id>", "mechanisms": [ <mechanism>, ... ]}
```

or abstention:

```json
{"fixture_id": "<id>", "abstention": "NO_NOVEL_GROUNDED_MECHANISM", "mechanisms": []}
```

## Mechanism fields (all required)

| field | type | meaning |
|---|---|---|
| `mechanism_id_local` | str | local id, unique within the response |
| `mechanism_statement` | str (controlled free text) | the relationship, in words |
| `observable_variables` | list[str] | bounded provider observables invoked |
| `conditioning_logic` | str (controlled free text) | what context/condition matters |
| `expected_relationship_to_test` | str | qualitative direction/relationship (no magnitude) |
| `why_not_baseline_equivalent` | str | why it is not reducible to the covered class |
| `evidence_refs` | list[str] | evidence-ref ids from the packet (non-empty) |
| `data_resolution_required` | "match" \| "half" | temporal resolution needed |
| `provider_requirements` | list[str] | observables the engine must have |
| `self_overlap_with` | list[str] | descriptive self-novelty check (deterministic dedup is authoritative) |

## Hard prohibitions (enforced, tested)

- **`FORBIDDEN_KEYS`** — no `probability`, `p_model`, `effect`, `effect_size`, `magnitude`,
  `confidence`, `novelty_score`, `quality_score`, `expected_value`, `ev`, `edge`, `odds`,
  `stake`, `p_value`, `similarity_score`, `distance`, `score`, `prediction`, `coefficient`,
  `weight`, `expected_predictive_value` — anywhere in the response (key or token).
- **No numeric prediction claims** inside semantic fields (e.g. "0.73 probability", "p<0.05",
  "effect size = 0.4") — rejected by a numeric-claim regex.
- **Controlled free text** is allowed only in the four semantic fields; observable concepts are
  bounded and auditable downstream against `provider_vocab`.

## Why not over-constrain with enums (key lesson)

If every field were a narrow enum mirroring the existing grammar, the model could not expand the
search space — the experiment would just re-test the grammar. Mechanism semantics are therefore
controlled free text, while provider concepts remain bounded and machine-auditable. Deterministic
parsing/formalization happens downstream (`formalizer.py`).
