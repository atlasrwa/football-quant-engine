# Final Recommendation (end of Phase A)

## What was built
A complete, research-only **Phase A architecture** for a hybrid LLM+quant football engine:
- deterministic PIT conditional-cohort **evidence engine** (`cohort_policy_v1`) with
  hierarchical empirical-Bayes shrinkage, FOR/AGAINST orientation, 1H/2H half-splits, and
  data-driven style clusters — verified on the real 5,319-match dual-provider corpus
  (60 PIT-safe evidence items incl. 14 second-half-shift metrics + league environment);
- a finite **versioned football ontology** (`football_ontology_v1`, 24 behavioral mechanisms);
- a **fixture evidence packet** with full provenance and a reproducible hash;
- a **strict structured-output schema** (`football_state_schema_v1`, closed objects, no probabilities);
- a **Bedrock Converse adapter** (narrow interface, temp≈0, forced tool schema, versioned cache, fail-closed);
- a **deterministic validator** enforcing schema + evidence-id existence + PIT-safety + ontology
  allow-lists + orientation + closed-world honesty + abstention (any failure → reject, no salvage);
- **26 passing tests** (12 contract, 5 evidence-PIT, 9 pre-existing matchup-leakage regression),
  including prompt-injection, future-dated, tiny-sample and orientation adversarial cases;
- all required reports + machine-readable artifacts (`out/ontology.json`, `schema.json`,
  `prompt_manifest.json`, `golden_cases.jsonl`, headed manifests for Phase B/C).

## Honest findings that shaped the design
- **Half-splits (1H/2H) ARE available** from the raw TheStatsAPI `/stats` payload (dropped by
  the normalizer) — enabling the second-half-pressure mechanisms the brief prioritizes.
- **Formation is NOT PIT-safe** (cached lineups lack an announcement timestamp) → classified
  `FORMATION_UNKNOWN`; behavioral style clusters carry the tactical load instead.
- **Score-state conditioning is unavailable** at the interval level → 2H-shift mechanisms are
  confounded and must be confidence-discounted until an interval source exists.
- **Neutral venue and referee** are available and are cheap, safe follow-ups.

## Recommendation
**PROCEED TO PHASE B (controlled pilot) ONLY, under a strict Bedrock budget cap — do NOT
backfill and do NOT integrate into any model yet.** Rationale:
1. The contextual-matchup research already proved *structure beats raw-stat dumps*; therefore the
   LLM's bar is the **contextual quant challenger**, not the base champion. That bar is set in
   `OOS_INCREMENTAL_VALUE.md`.
2. No LLM value has been demonstrated yet — Phase A only makes the value *measurable and safe*.
3. Cost/hallucination must be characterised on ≤300 fixtures (corners first) before any scale.

## Explicit non-goals honored
No champion/canonical/prospective mutation; no publication; no gates changed; no auto-promotion;
no LLM probabilities; no LLM database access; no LLM code generation; no fabricated context.

## Decision gates ahead (unchanged, pre-committed)
- Phase B pilot must show ~100% schema validity, sensible abstention, no external-knowledge
  leakage, high repeatability.
- Phase C must show LLM states lower chronological OOS loss **beyond the quant challenger** on
  common support with acceptable uncertainty, calibration preserved, broad across leagues/folds.
- Only then: `CANDIDATE_WORTH_PROSPECTIVE_TEST` — never a champion, never auto-promoted.
