"""Hypothesis engine -- the LLM's ONLY sanctioned role in football-quant-engine.

GOVERNING PRINCIPLE
-------------------
    The LLM proposes what to measure.
    The deterministic engine measures it.
    Statistical validation determines whether it generalizes.
    The quantitative model produces the probability.
    The market and prospective outcomes determine whether the resulting model adds value.

The LLM does not own any downstream numerical conclusion.

WHAT THE LLM IS
---------------
A fixture-context research agent. Given structured, leakage-safe fixture evidence, it
generates grounded, testable football hypotheses and comparison questions. Its job ends at
"grounded hypothesis -> validated deterministic query plan".

WHAT THE LLM IS NOT
-------------------
Not a predictor. It does not generate probabilities, estimate hidden matchup strength,
output ordinal advantage labels, or decide the size or direction of any model adjustment.

ARCHITECTURAL INVARIANT (enforced by tests, not convention)
-----------------------------------------------------------
NOTHING in this package imports the prediction, calibration, market, forecast, prospective,
shadow, settlement or broadcast layers, and nothing in those layers imports this package.
The champion produces p_model with this package uninstalled. See
`tests/research/hypothesis_engine/test_architecture_isolation.py`.

The forbidden architecture this package exists to prevent:

    features -> LLM estimates advantage/strength -> ordinal score -> quant model

is not merely discouraged here; `schema.py` gives a magnitude nowhere to live, `firewall.py`
rejects one that appears anyway, and `lifecycle.py` has no edge from any LLM output to a
model feature.

MODULES
-------
  capability      what CAN be asked -- audited provider inventory, context sources
  vocabulary      closed enums for every value the LLM may name
  schema          hypothesis_set_schema_v1, the entire output contract
  firewall        numerical-authority + latent-grading rejection
  leakage         future / market / settlement information guard
  validator       schema + firewall + evidence-grounding gate (no salvage)
  query_plan      typed plan + compiler, with the cutoff injected by the engine
  measurement     deterministic executor; every number in the record is produced here
  similarity      opponent-cohort resolution; distance metrics PENDING_VALIDATION
  normalize       scientific intent, for identity/repeatability controls on structure
  lifecycle       research funnel states, legal transitions, append-only provenance
  context_packet  fixture context packet + per-fixture capability manifest
  prompt          hypothesis_analyst_prompt_v1

LEGACY
------
`src/research/llm_matchup/` is the LLM_LATENT_STATE_EXPERIMENT: a preserved, frozen
research generation that asked whether an LLM could act as a stable estimator of
contextual football mechanism levels. That is no longer the intended role. Its artifacts
are retained as evidence and its ordinal state outputs must never enter this pipeline --
see `LEGACY_CLASSIFICATION.md`.
"""
from __future__ import annotations

ENGINE_VERSION = "hypothesis_engine_v1"

GOVERNING_PRINCIPLE = (
    "The LLM proposes what to measure. The deterministic engine measures it. Statistical "
    "validation determines whether it generalizes. The quantitative model produces the "
    "probability. The market and prospective outcomes determine whether the resulting "
    "model adds value."
)

__all__ = [
    "ENGINE_VERSION", "GOVERNING_PRINCIPLE",
    "capability", "vocabulary", "schema", "firewall", "leakage", "validator",
    "query_plan", "measurement", "similarity", "normalize", "lifecycle",
    "context_packet", "prompt",
]
