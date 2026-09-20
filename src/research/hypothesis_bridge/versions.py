"""Version pins for the hypothesis -> validation -> shadow-record bridge.

Every artifact this bridge emits is stamped with these. They are separate from the LLM
evidence lineage (`llm_matchup/versions.py`) on purpose: the bridge can change without
redefining what an evidence packet is, and vice versa.
"""
from __future__ import annotations

PROPOSAL_SCHEMA_VERSION = "hypothesis_proposal_v1"
CANONICAL_IR_VERSION = "canonical_hypothesis_ir_v1"
VALIDATOR_VERSION = "hypothesis_validator_v1"
COMPILER_VERSION = "hypothesis_compiler_v1"
MEASUREMENT_VERSION = "deterministic_measurement_v1"
SHADOW_RECORD_VERSION = "shadow_research_record_v1"
CAPABILITY_REGISTRY_VERSION = "provider_capability_registry_v1"


def bridge_version_stamp() -> dict[str, str]:
    return {
        "proposal_schema_version": PROPOSAL_SCHEMA_VERSION,
        "canonical_ir_version": CANONICAL_IR_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "compiler_version": COMPILER_VERSION,
        "measurement_version": MEASUREMENT_VERSION,
        "shadow_record_version": SHADOW_RECORD_VERSION,
        "capability_registry_version": CAPABILITY_REGISTRY_VERSION,
    }
