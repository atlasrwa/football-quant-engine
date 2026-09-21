# NOVEL_FAMILY_REGISTRY_SCHEMA_V1 + additive grammar extensions

`item6_novel_family_registry_v1` · code: `src/research/item6/registry.py`

The versioned registry of accepted novel families, built from the corpus of F3/F4
formalizations. This is the object that gets **frozen** if Stage 1 passes, and the sole surface
Stage 2 may draw novel families from.

## Registry entry schema

| field | meaning |
|---|---|
| `family_id` | `NF_000`, `NF_001`, … (stable, signature-ordered) |
| `family_signature` | deterministic identity `(metrics, novelty_signals, bands)` |
| `semantic_description` | canonical mechanism statement |
| `required_measurable_variables` | provider metrics the family needs |
| `conditioning_dimensions` | e.g. venue / opponent_profile / competition / match_state / threshold |
| `temporal_resolution_requirement` | "match" or "half" |
| `provider_requirements` | union of provider observables across members |
| `formalization_rule` | `F3_MEASURABLE_WITH_EXISTING_GRAMMAR` or `F4_...EXTENSION` |
| `existing_grammar_supported` | bool (true only for F3) |
| `required_additive_extension` | `GX_*` id or null |
| `novelty_signals` | escape-hatch structures present |
| `member_mechanism_ids`, `n_members` | provenance |

## Frozen invariant: NO predictive result

A registry entry may **never** contain an effect, p-value, OOS status, survival, score, Brier,
log-loss, coefficient, edge, or EV. This is asserted in code (`build_registry` raises if any key
resembles a predictive-result field) and tested (`test_point_in_time.py`).

## Additive grammar extensions (Item-6-only, versioned)

If a useful mechanism requires a new representational construct, we create a **versioned Item-6
extension** and never mutate the V2/V3 grammar. Each maps from an escape-hatch structural signal:

| extension_id | from signal | construct |
|---|---|---|
| `GX_CROSS_METRIC_JOINT` | `US_MULTI_METRIC_INTERACTION` | joint relationship over ≥2 distinct metrics |
| `GX_TWO_AXIS_PROFILE_INTERSECTION` | `US_TWO_DIM_OPP_PROFILE_INTERSECTION` | intersection over two profile axes |
| `GX_THRESHOLD_CONDITION` | `US_THRESHOLD_NONLINEARITY` | threshold / piecewise condition on a continuous observable |
| `GX_HALF_STATE_INTERACTION` | `US_HALF_STATE_OR_GAME_STATE` | half-level / prior-game-state interaction (half-resolution required) |
| `GX_CROSS_METRIC_ASYMMETRY` | `US_CROSS_METRIC_ASYMMETRY` | asymmetric relationship across different metrics |
| `GX_SEQUENCE_REGIME` | `US_SEQUENCING_REGIME` | sequence / regime over ordered prior matches |

Every extension must be deterministic, provider-safe, point-in-time-safe, fully testable, and NOT
tailored using future results. Half-state extensions are only admitted when a half-resolution
provider metric backs them (enforced by the formalizer; tested).
