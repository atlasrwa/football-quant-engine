"""LLM-matchup hybrid research layer (Phase A: architecture only).

Research-only. No production wiring, no champion mutation, no publication, no
canonical/prospective ledger access. The deployed analytical LLM (Claude Sonnet on
AWS Bedrock) is a *football interpretation* layer that converts a deterministic,
PIT-safe Fixture Evidence Packet into a strictly-validated structured football state.
It NEVER produces probabilities and NEVER roams the database.

Responsibility separation (see ARCHITECTURE.md):
  deterministic data layer  -> all numbers, cohorts, provenance, PIT safety
  LLM layer                 -> semantic interpretation into a versioned ontology
  quant layer               -> probabilities, calibration, OOS falsification

Everything the LLM emits is derived, versioned research data with full provenance.
"""
from .versions import (
    ONTOLOGY_VERSION,
    SCHEMA_VERSION,
    PROMPT_VERSION,
    COHORT_POLICY_VERSION,
    PACKET_SCHEMA_VERSION,
    DEFAULT_BEDROCK_MODEL_ID,
)

__all__ = [
    "ONTOLOGY_VERSION",
    "SCHEMA_VERSION",
    "PROMPT_VERSION",
    "COHORT_POLICY_VERSION",
    "PACKET_SCHEMA_VERSION",
    "DEFAULT_BEDROCK_MODEL_ID",
]
