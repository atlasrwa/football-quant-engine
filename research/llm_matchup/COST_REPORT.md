# Cost Report (estimates — no calls made in Phase A)

No Bedrock calls have been made (offline sandbox; fail-closed). These are **planning
estimates** so we do not spend thousands of calls before proving incremental value (brief §51).

## Token footprint (measured from the built packet + prompt, not billed)
- System prompt: ~1.6 KB (≈ 400 tokens).
- Ontology reference block (trimmed to 6 KB) + schema-guided tool: ≈ 1.5–2.0 K tokens.
- A real fixture packet (60 evidence items): serialized ≈ 9–12 KB (≈ 3.0–3.5 K input tokens).
- **Input per fixture:** ≈ 5–6 K tokens. **Output** (structured state, ~10–16 states): ≈ 0.8–1.2 K tokens.

## Order-of-magnitude cost (Claude 3.5 Sonnet on Bedrock; verify current pricing at run time)
Using widely-quoted Sonnet rates (~$3 / 1M input, ~$15 / 1M output tokens):
- Per fixture ≈ (5.5K × $3 + 1.0K × $15)/1e6 ≈ **$0.016–0.033 / fixture**.
- Pilot sample (Phase B, ~300 fixtures): ≈ **$5–10**.
- Corners-only pilot corpus (~4.0K fixtures): ≈ **$65–130**.
- Full 5,319-fixture backfill (one prompt/ontology/model version): ≈ **$85–175**.
*(Indicative only — confirm live Bedrock pricing before any backfill; costs recur per version.)*

## Cost controls
- Deterministic cache by `(model, versions, packet_hash)`: re-runs are free.
- Phase gating: pilot (≤300) → measured value → only then scale (brief §52).
- "Does a deterministic feature already capture this?" test before paying for LLM states — the
  matchup research already showed structure > raw dumps, so LLM states must beat the deterministic
  contextual challenger, not just the champion.
- Second-pass verifier deferred until it demonstrably improves reliability (doubles cost).

## Recommendation
Do **not** backfill. Start with a ≤300-fixture corners pilot (Phase B/C) under a strict Bedrock
budget cap, measure hallucination/abstention/repeatability + OOS incremental value, and decide
from evidence.
