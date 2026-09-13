# Pilot Results (Phase B) — PENDING

**Status: NOT STARTED.** Phase A is architecture-only; no LLM calls were made (offline
sandbox, fail-closed). This document defines exactly what the pilot will measure so the audit
metrics (brief §56) are pre-specified, not chosen after seeing results.

## Pilot design (to run once Bedrock access + budget cap exist)
- **Sample:** a representative, chronologically-bounded ≤300-fixture slice (corners first,
  brief §53). Drawn deterministically; recorded in `llm_call_manifest.csv`.
- **Prompt/ontology/model frozen** for the whole pilot.

## Required audit metrics (`out/` tables, currently headed-empty)
| Metric | Target/interpretation |
|---|---|
| total calls | denominator |
| valid schema % | expect ≈ 100 (else reject) |
| rejected % | investigate any non-trivial rate |
| unsupported evidence-id % | must be ~0 (validator blocks) |
| abstention (UNKNOWN) % | should track genuinely sparse cohorts |
| conflicted % | sanity |
| repeatability % | same packet twice → same labels (temp≈0 + cache) |
| avg input/output tokens, latency | cost/perf |
| estimated cost | vs COST_REPORT |

## Manual stratified inspection
Sample across leagues, sample sizes, provider-agreement states, and abstention outcomes;
confirm cited evidence is football-coherent and no external knowledge leaked.

## Gate to Phase C
Proceed to predictive OOS only if: schema-valid ≈100%, abstention behaves sensibly, no
external-knowledge leakage in the manual sample, and repeatability is high.
