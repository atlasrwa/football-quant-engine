# LLM-Matchup Hybrid Engine — Research Package (Phase A)

Research-only architecture for a hybrid **LLM (football interpreter) + quant (probability
authority)** engine. **Nothing here is production.** No champion/canonical/prospective state
was modified; no Bedrock calls were made; nothing is auto-promoted; the LLM never produces
probabilities, never roams the database, never writes code.

## Read in this order
1. `ARCHITECTURE.md` — dataflow + responsibility separation + module map.
2. `EVIDENCE_PACKET_SPEC.md` — the deterministic bounded factual universe.
3. `FOOTBALL_ONTOLOGY.md` — the finite `football_ontology_v1` the LLM is confined to.
4. `STRUCTURED_OUTPUT_SCHEMA.md` — `football_state_schema_v1` (no probabilities, closed objects).
5. `HALLUCINATION_CONTROLS.md` + `TEMPORAL_SAFETY.md` — how hallucination is made unusable and PIT enforced.
6. `BEDROCK_CONFIGURATION.md` — model pinning, IAM boundary, guardrails, failure modes.
7. `GOLDEN_TESTS.md` + `LLM_REGRESSION.md` — the test/regression contract.
8. `COST_REPORT.md` — estimates + why we do not backfill.
9. `PILOT_RESULTS.md` (Phase B, pending) + `OOS_INCREMENTAL_VALUE.md` (Phase C, pending).
10. `UNAVAILABLE_CONTEXT.md` — what we still cannot know (formation, injuries, weather, score-state).
11. `FINAL_RECOMMENDATION.md` — proceed to a capped pilot only; bar = contextual quant challenger.

## Code (`src/research/llm_matchup/`)
`versions.py`, `ontology.py`, `cohorts.py`, `evidence.py`, `schema.py`, `prompt.py`,
`bedrock_adapter.py`, `validator.py`, `stub.py` (tests only), `golden.py`, `gen_artifacts.py`.

## Machine-readable (`out/`)
`ontology.json`, `schema.json`, `prompt_manifest.json`, `golden_cases.jsonl`,
`ontology_mechanisms.csv`, `EVIDENCE_METRIC_DICTIONARY.csv`, `PHASE_A_SUMMARY.json`, and
headed-empty `llm_call_manifest.csv` / `llm_state_features.csv` / `oos_results.csv` for Phase B/C.

## Reproduce
```bash
.venv/bin/python -m pytest tests/research/test_llm_matchup_contract.py \
  tests/research/test_llm_matchup_evidence_pit.py \
  tests/research/test_matchup_leakage.py -q          # 26 passed
.venv/bin/python -m src.research.llm_matchup.gen_artifacts
# build a real packet (no LLM call):
.venv/bin/python -c "from src.research.matchup.corpus import load_corpus; \
from src.research.llm_matchup.evidence import EvidencePacketBuilder; \
r=load_corpus(); print(EvidencePacketBuilder(r).build(r[-200])['data_quality'])"
```

## One-line status
Phase A architecture complete and tested; **no LLM value demonstrated yet** — Phase A only makes
that value measurable and safe. Recommendation: capped Phase-B pilot (corners first), no backfill.
