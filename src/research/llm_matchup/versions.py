"""Central version pins for the LLM-matchup research layer.

Every artifact the LLM layer produces is stamped with these versions. Changing any of
them creates a NEW derived-feature generation (football_state_vN); historical LLM
features are never silently regenerated in place (brief §24-§26, §50).

The Bedrock model identity is pinned here as a *default*; the actual resolved model /
inference profile used for any call is persisted per-call (brief §25 "no silent model
drift"). We deliberately do not hard-depend on a moving alias.
"""
from __future__ import annotations

# --- Research artifact versions -------------------------------------------------
# Phase B introduces formation as a football-RESOLUTION variable. The ontology, schema,
# prompt and packet gain formation dimensions, so they are bumped to v2. formation_policy_v1
# governs the two-concept RESOLVED vs PREMATCH model. Historical v1 features are never
# regenerated in place; v2 is a new derived-feature generation (brief §25 freeze rule).
ONTOLOGY_VERSION = "football_ontology_v2"
SCHEMA_VERSION = "football_state_schema_v2"
PROMPT_VERSION = "sonnet_prompt_v2"
COHORT_POLICY_VERSION = "cohort_policy_v1"
PACKET_SCHEMA_VERSION = "fixture_evidence_packet_v2"
FORMATION_POLICY_VERSION = "formation_policy_v1"
FORMATION_FAMILY_VERSION = "formation_family_v1"

# --- Bedrock model default (research). The resolved model is persisted per call. --
# Claude Sonnet on Bedrock, accessed via a cross-region INFERENCE PROFILE (on-demand
# throughput for the base model id is not enabled in this account, so the profile id is
# required). Pinned to a concrete versioned profile so historical features stay
# reproducible. Operators may override via BEDROCK_MODEL_ID; whatever resolves is recorded
# in the per-call manifest (brief §15, §25 — no silent model drift).
DEFAULT_BEDROCK_MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
DEFAULT_BEDROCK_REGION = "us-east-1"

# Inference config for analytical (low-stochasticity) use. temperature≈0 does NOT
# guarantee determinism, hence output caching by (model, versions, packet hash).
INFERENCE_CONFIG = {
    "temperature": 0.0,
    "topP": 1.0,
    "maxTokens": 8192,
}


def version_stamp() -> dict[str, str]:
    """Immutable version fingerprint stamped onto every persisted LLM output."""
    return {
        "ontology_version": ONTOLOGY_VERSION,
        "schema_version": SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "cohort_policy_version": COHORT_POLICY_VERSION,
        "packet_schema_version": PACKET_SCHEMA_VERSION,
        "formation_policy_version": FORMATION_POLICY_VERSION,
        "formation_family_version": FORMATION_FAMILY_VERSION,
    }
