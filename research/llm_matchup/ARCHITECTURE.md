# LLM-Matchup Hybrid Architecture (Phase A — architecture only)

**Status:** Phase A complete (architecture, ontology, evidence engine, schema, Bedrock
adapter, validator, cache, versioning, golden tests). **No historical LLM backfill. No
Bedrock calls made. No model/champion/canonical/prospective changes. Research-only.**

## 1. Purpose
Combine (1) deterministic PIT football evidence, (2) structured conditional history, (3)
an LLM football *interpreter* (Claude Sonnet on Bedrock), and (4) a quant probability layer
that measures, calibrates and can *reject* the LLM's interpretations. The LLM is an
interpretation layer, **never** the probability authority.

## 2. Dataflow
```
RAW TheStatsAPI cache (PIT)                     [data/thestatsapi/championship, cache-only]
    ↓  src/research/matchup/corpus.py  +  cohorts.py half-split enrichment
DETERMINISTIC PIT COHORT ENGINE  (cohort_policy_v1)
    ↓  evidence.py  (hierarchical shrinkage, provenance, packet hash)
FIXTURE EVIDENCE PACKET  (fixture_evidence_packet_v1)   ← bounded factual universe
    ↓  bedrock_adapter.analyze_matchup()  (closed-world prompt, strict tool schema, temp≈0)
CLAUDE SONNET (Bedrock Converse)
    ↓  structured tool output
STRICT STRUCTURED FOOTBALL STATE  (football_state_schema_v1)
    ↓  validator.validate()  ← schema + evidence-id + PIT + ontology + orientation gate
VALIDATED FOOTBALL STATE  (immutable, versioned, provenance-stamped)
    ↓  [Phase C+] quant layer: deterministic features  +  LLM states  →  probabilities
GOALS / CORNERS / CARDS distributions   →   chronological OOS evaluation
```

## 3. Responsibility separation (never blurred)
| Layer | Owns | Must NOT do |
|---|---|---|
| Deterministic data | all numbers, cohorts, rolling stats, provenance, PIT safety, provider semantics | interpret tactics |
| LLM (Claude) | semantic interpretation → versioned ontology states, uncertainty/abstention | compute stats, output probabilities, roam the DB, write code |
| Quant | parameter/probability estimation, calibration, OOS ablation, accept/reject | trust LLM prose |

## 4. Modules (`src/research/llm_matchup/`)
- `versions.py` — version pins + per-call model recording (no silent drift).
- `ontology.py` — `football_ontology_v1`: 24 mechanisms across attack/defense/discipline/matchup, enum levels, UNKNOWN/CONFLICTED, per-mechanism allowed evidence.
- `cohorts.py` — `cohort_policy_v1`: PIT history index, FOR/AGAINST extraction, half-splits, empirical-Bayes shrinkage (`n/(n+K)`, K=6), data-driven style tags.
- `evidence.py` — `EvidencePacketBuilder`: provenance-carrying evidence items + stable ids + `packet_hash`; formation→FORMATION_UNKNOWN; fail-closed on missing data.
- `schema.py` — `football_state_schema_v1`: strict JSON schema, `additionalProperties:false`, enum labels, evidence-id + counter-evidence arrays, no probability fields.
- `prompt.py` — `matchup_analyst_prompt_v1`: closed-world system prompt; evidence delivered as fenced untrusted DATA (injection boundary).
- `bedrock_adapter.py` — narrow `analyze_matchup()`; Converse API + strict tool schema; cache by (model, versions, packet hash); fail-closed → `LLM_STATE_UNAVAILABLE`.
- `validator.py` — deterministic gate; any failure → `LLM_OUTPUT_REJECTED` (no salvage).
- `stub.py` — offline deterministic producer for **tests only** (never manufactures research features).
- `golden.py` / `gen_artifacts.py` — golden cases and machine-readable artifact writer.

## 5. What Phase A deliberately does NOT do
- No full historical LLM feature generation (cost + must prove value first, brief §51-§52).
- No quant integration / OOS numbers yet (Phase C; `oos_results.csv` is headed-empty).
- No production wiring, no publication, no champion touch.

## 6. Verified on the real corpus
Built a packet for a real La Liga fixture from the 5,319-match dual-provider corpus:
60 PIT-safe evidence items including 14 second-half-shift metrics, league environment
(corners 9.59, cards 4.57 per match), data-driven style tags; packet hash reproducible;
the deterministic stub produced a schema- and provenance-valid football state.
