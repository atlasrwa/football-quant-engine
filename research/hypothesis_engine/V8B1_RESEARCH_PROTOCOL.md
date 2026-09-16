# V8B.1 — research protocol (`v8b1_protocol_v1`)

**Status: frozen design. Governs the single Bedrock Converse call made per target fixture.**

## 1. What Sonnet receives, in order

1. **System prompt** (§2 below) — role, numerical firewall, the explicit 10-phase research
   process, and the canonical-ID-only output contract.
2. **Evidence packet** (`V8B1_EVIDENCE_PACKET_SPEC.md`) — fenced as untrusted data.
3. **Tool spec** for `search_hypotheses` (wraps `src/research/hypothesis_v8b1/search.py`) and
   `submit_selections` (the final structured output, §5).

Sonnet may call `search_hypotheses` any number of times (bounded only by the model's own
turn/token budget — no artificial call-count cap is imposed, since the search tool is local
computation with zero marginal dollar cost) before calling `submit_selections` exactly once.

## 2. Numerical firewall (§3 of the V8B instructions, carried unchanged into V8B.1)

Sonnet MUST NOT produce: `p_model`, match/event probabilities, probability adjustments, odds,
EV, edge, stakes, bets, numerical similarity scores, numerical latent-strength scores, or
invented effect estimates. It MAY quote a descriptive number already present in the evidence
packet when explaining why a question deserves investigation, citing it via `evidence_refs`
(§30 of the V8B instructions) rather than restating the number as a predicted effect.
Structurally enforced by the schema (§5): there is no field a probability/effect could be
written into that survives validation, and `submit_selections`' own field set contains no
numeric-effect slot at all — the firewall is a consequence of the schema's shape, not merely a
prompt instruction the model could ignore.

## 3. The ten-phase process (§14-§22 of the V8B instructions), restated for V8B.1

Sonnet must work through these phases per fixture, in order, before calling
`submit_selections`. The phases are carried into the `research_trace` output object (§6),
which is a structured record of evidence-grounded conclusions — not private chain-of-thought,
and not free prose.

1. **Team A behavioral map** — attack (volume, SoT relationship, wide pressure, corners,
   possession, recent-vs-long, home/away, opponent dependence) and defense (shots/SoT/corners
   conceded, territorial concession, discipline, recent-vs-long), each observation citing
   `evidence_refs` into the packet. No prediction.
2. **Team B behavioral map** — the identical process, same rigor, same evidence-citation
   requirement. (The packet's own symmetric construction, §7 of the packet spec's test suite,
   makes an unequal Team A/B treatment a genuine choice by Sonnet, not something forced by
   asymmetric evidence.)
3. **A attack × B defense** — compatibility, suppression, conflicting metrics, volume-vs-
   accuracy tensions, conditional mechanisms. Uses the search tool's `mechanism_type=
   "attack_x_defense"` filter to see what the deterministic universe can actually test for
   this kind of question before proposing one.
4. **B attack × A defense** — the symmetric analysis. Not optional; not skippable because Team
   A is the home team or the nominal favorite (favorite/underdog status is not represented
   anywhere in the packet or the ontology, so there is nothing for Sonnet to lean on to skip
   this phase — a structural, not merely instructional, safeguard).
5. **Contradiction search** — explicit look for statistical tensions across the two behavioral
   maps (high shots/ordinary SoT, high possession/low volume, etc.).
6. **Similar-opponent analysis** — query `search_hypotheses` with `mechanism_type=
   "similar_opponent"`; read the packet's `similar_to_fixture_opponent` membership (identities
   only, never a score) for each team; ask which axis of similarity is worth conditioning on.
   Sonnet chooses the axis; it never computes or asserts a similarity value.
7. **Recent regime analysis** — using the packet's own `recent_vs_long` fields (already
   computed, side by side, so Sonnet is not asked to compute a delta itself): is a recent
   figure genuinely divergent, or explainable by the same packet's home/away or competition-
   environment context? Recent-vs-long is not automatically selected merely because the tool
   exists (§20 of the V8B instructions: "Do not automatically select recent-v-long
   comparisons").
8. **Context** — venue, competition, half-state/formation where the capability envelope
   actually admits them for this fixture (most will not — see §11 of the packet spec).
   Context modifies raw-behavior reasoning; it never substitutes for it, and it never licenses
   an unsupported "formation → tactical outcome" leap (no such relationship exists anywhere in
   the ontology for Sonnet to invoke).
9. **Hard question generation** — only now, candidate questions are formed, each with
   OBSERVATION / MECHANISM / TEST / FALSIFIER (§22 of the V8B instructions), each grounded in
   a `search_hypotheses` result (so every candidate already has a `hypothesis_id` before this
   phase ends).
10. **Adversarial self-critic** — for every candidate, the checklist in §23 of the V8B
    instructions (simple-average check, target==condition check, cohort==baseline check,
    opponent-strength-artifact check, venue/competition confounding check, over-conditioning
    check, dataset-support check, duplicate-of-another-candidate check, "would a blind
    heuristic pick the same thing" check). Weak candidates are discarded and recorded in
    `discarded_candidates` (§6), not silently dropped.

## 4. Abstention

Returning zero selections is a valid, correct answer to a fixture whose evidence does not
support any grounded question (unchanged from `hypothesis_engine/prompt_v2.py`'s own existing
and audited abstention policy — reused, not reinvented). `submit_selections` accepts an empty
`final_selections` array without error.

## 5. Output contract — `submit_selections` tool schema (sketch; formalized alongside
`V8B1_PROMPT_FREEZE.json`)

```json
{
  "research_trace": {
    "behavioral_map": {"team_a_attack": [...], "team_a_defense": [...],
                       "team_b_attack": [...], "team_b_defense": [...]},
    "matchup_tensions": [...],
    "similar_opponent_insights": [...],
    "regime_questions": [...],
    "context_notes": [...],
    "discarded_candidates": [{"reason": "...", "hypothesis_id_considered": "..."}],
  },
  "final_selections": [
    {
      "hypothesis_id": "<must be an ID search_hypotheses actually returned this session>",
      "evidence_refs": ["team_a.raw_rows[3].for.long_run_mean", ...],
      "research_reason": "...",
      "mechanism_summary": "...",
      "why_simple_average_is_insufficient": "...",
      "support_warning": "..."
    }
  ]
}
```

Every substantive claim in `research_trace` (not only `final_selections`) must carry
`evidence_refs` pointing into the packet's own JSON paths (§30 of the V8B instructions,
"Unknown evidence references fail validation" — enforced by a validator that walks the packet
structure and rejects any ref that does not resolve to a real path, symmetric to how
`search.resolve()` rejects an unrecognized `hypothesis_id`).

**Selection budget**: 0–8 per fixture (§31 of the V8B instructions). Not required to be 8.

## 6. What must be frozen before any paid call

- This document's ten phases and their required evidence-citation discipline.
- The exact `submit_selections` JSON schema (formalized in `V8B1_PROMPT_FREEZE.json`,
  content-hashed exactly as `hypothesis_engine/schema_v2.py::schema_content_hash()` already
  does for the existing pipeline).
- The system prompt text itself, content-hashed and bound into the Bedrock cache key
  (mirroring `bedrock_adapter.py`'s existing `_cache_key` construction: model_id + version
  stamp + prompt/schema content hash + packet hash + call index).

None of these may change after the first real target call, per the no-mid-run-tuning rule.
