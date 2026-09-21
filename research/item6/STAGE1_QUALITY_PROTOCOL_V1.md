# STAGE1_QUALITY_PROTOCOL_V1

`item6_quality_protocol_v1` · code: `src/research/item6/quality_protocol.py`

A corrected successor to the previous quality audit. Two defects are fixed:

1. **Unreachable aggregate category.** The prior audit had an aggregate "Q" bucket (Q2) that was
   structurally unreachable, and used aggregate Q categories as the scientific endpoint. Here,
   **no aggregate category is the endpoint.** Scoring is dimension-level; each dimension is
   reported independently.
2. **Single LLM rater.** The prior audit had one LLM rater. Here, rating uses **two independent
   passes** with reported agreement.

## Frozen dimensions (each scored 0/1/2)

`fixture_specificity`, `grounding`, `information_gain`, `interaction_depth`,
`mechanistic_plausibility`, `novelty`, `synthesis`, `falsifiability`, `statistical_discipline`,
`grammar_transcendence`, `actionability`, `baseline_equivalence` (scored inverted: 2 = clearly
non-equivalent).

## Rater independence

- **PASS A — deterministic structural classifier** (`pass_a_score`). Fully reproducible, no
  model. Scores each dimension from the mechanism's structure + its formalization result.
- **PASS B — blinded semantic rater.** In the LIVE experiment this is a **separately
  cost-authorized** semantic pass. It sees ONLY the pre-target packet, the mechanism, the
  evidence refs, and the baseline coverage spec. It NEVER sees OOS outcomes, markets, settlement,
  or ARM-D performance. For zero-spend rehearsal, `pass_b_stub` provides a deterministic,
  semantic-flavoured stand-in so the agreement machinery is exercised offline — this stub is
  never used to make a scientific claim.

Per-dimension exact-agreement between the two passes is computed (`agreement`) and reported.
Semantic scores are **not** claimed to be objective truth.

## Blinding

The Stage-1 novelty/quality grader is OOS-blind by construction: its only inputs are the
pre-target packet, the generated mechanism, evidence refs, and the coverage spec.

## Relationship to the gate

The quality protocol is **diagnostic and interpretive**. The frozen PASS/FAIL decision is made by
`STAGE1_GATE_V1` on the structural endpoints. The dimension scores support interpretation and
surface where a generator is strong/weak, but the gate — not the rubric — decides.
