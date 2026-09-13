# Structured Output Schema (`football_state_schema_v1`)

Strict contract for the LLM's only output. Machine-readable: `out/schema.json`. Used both as
the Bedrock tool `inputSchema` and by the deterministic validator. **No probabilities** (brief
§32). Every object sets `additionalProperties:false` (brief §22).

## Top level
```jsonc
{
  "fixture_id": string,
  "information_cutoff_unix": integer,
  "context_flags": {           // all enums; must match packet honesty
    "formation_status", "injury_status", "neutral_venue",
    "score_state_conditioning", "provider_agreement"
  },
  "team_a_states": [ StateItem ],
  "team_b_states": [ StateItem ],
  "matchup_states": [ MatchupItem ]
}
```

## StateItem (team-state)
```jsonc
{
  "mechanism": enum(ontology mechanism ids),
  "level": enum(VERY_LOW..VERY_HIGH, UNKNOWN),
  "confidence": enum(LOW..HIGH, UNKNOWN),
  "evidence_ids": [string],            // must exist in packet & be PIT_SAFE & allowed for mechanism
  "counter_evidence_ids": [string],
  "uncertainty_factors": [enum],
  "preferred_evidence_level": enum(EVIDENCE_LEVELS)
}
```

## MatchupItem (interaction)
```jsonc
{
  "mechanism": enum,
  "assessment": enum(ADVANTAGE_LEVELS ∪ LEVELS),   // e.g. A_ADVANTAGE, CONFLICTED, UNKNOWN
  "confidence": enum,
  "supporting_evidence_ids": [string],
  "counter_evidence_ids": [string],                 // counter-evidence required (brief §20)
  "uncertainty_factors": [enum]
}
```

## Enforced invariants (validator)
1. Structure/type/enum valid; `additionalProperties:false` recursively (enforced even without
   the optional `jsonschema` package by a hand walker).
2. `fixture_id` and `information_cutoff_unix` match the packet.
3. Every cited id exists in the packet.
4. Every **supporting** cited id has `temporal_status == PIT_SAFE`.
5. Cited evidence metric is in the mechanism's ontology allow-list.
6. A state with zero PIT-safe supporting evidence must be `UNKNOWN/CONFLICTED/NEUTRAL`.
7. `formation_status`/`injury_status` must equal the packet's `unsupported_context`.
8. No probability/betting keys anywhere (`probability, prob, p_over, odds, prediction,
   recommended_bet`).
9. Version stamps present before persist.

Any violation → `LLM_OUTPUT_REJECTED` with the offending field path; **no partial salvage**.
