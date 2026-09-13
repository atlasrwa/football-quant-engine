"""LLM_MATCHUP_V3 — identity-neutral evidence processing generation (V3 patch SS1, SS51).

LLM_MATCHUP_V2 (versions_v2.py) is PRESERVED, untouched, and stays the scientific record of
the failed identity-sensitive generation (freeze: research/llm_matchup/out/FREEZE_LLM_MATCHUP_V2.json,
report: research/llm_matchup/PRE_PHASE_C_HARDENING.md). This module defines a NEW generation
without mutating anything V2.

What changes vs V2 (V3 patch SS3-SS23):
  * PACKET_SCHEMA_VERSION bumps to the identity-neutral LLM-facing packet type
    (neutral_llm_evidence_packet_v1) -- team/competition names replaced with fixture-local
    neutral tokens (unchanged behavior from V2's runtime default, now STRUCTURALLY enforced
    via a distinct packet type + adapter guard, SS20-SS23), and formation exact-string/family
    label replaced with neutral formation_id/family_id + explicit structural attributes
    (NEW in V3 -- V2 never neutralized formation at all, which is exactly what tripped the
    75% formation-label trip rate).
  * PROMPT_VERSION bumps to sonnet_prompt_v4 (SS15): explicit "entity identifiers are
    anonymous" contract + formation-structure interpretation guidance.
  * NEUTRALIZATION_POLICY_VERSION (new axis): the neutralize_for_llm() transform version.
  * FORMATION_STRUCTURE_VERSION (new axis): the formation_id + structural-attribute mapping.

What does NOT change (V3 patch SS49, SS50, and: do not touch the probability engine):
  * SCHEMA_VERSION (the Bedrock OUTPUT tool schema, football_state_schema_v3) is reused
    unchanged -- it only constrains mechanism/level/confidence/evidence-id shape, which is
    untouched by packet-level identity neutralization.
  * ONTOLOGY_VERSION, COHORT_POLICY_VERSION, FORMATION_POLICY_VERSION, FORMATION_FAMILY_VERSION
    (the underlying family TAXONOMY is unchanged; only its LLM-facing representation is).
  * Bedrock model identity, inference config, repeatability-call count.
"""
from __future__ import annotations
import hashlib, json
from src.research.llm_matchup.hardening import versions_v2 as V_V2

GENERATION_ID = "LLM_MATCHUP_V3"

# unchanged from V2 (which inherited them unchanged from frozen Phase-B versions.py)
ONTOLOGY_VERSION = V_V2.ONTOLOGY_VERSION
SCHEMA_VERSION = V_V2.SCHEMA_VERSION                    # football_state_schema_v3 (output, reused)
COHORT_POLICY_VERSION = V_V2.COHORT_POLICY_VERSION
FORMATION_POLICY_VERSION = V_V2.FORMATION_POLICY_VERSION
FORMATION_FAMILY_VERSION = V_V2.FORMATION_FAMILY_VERSION

# new / bumped for V3
PROMPT_VERSION = "sonnet_prompt_v4"                     # identity-neutral contract (SS15)
PACKET_SCHEMA_VERSION = "neutral_llm_evidence_packet_v1"  # LLM-facing packet TYPE (SS20-SS23)
NEUTRALIZATION_POLICY_VERSION = "neutralization_policy_v1"
FORMATION_STRUCTURE_VERSION = "formation_structure_v1"

# unchanged
DEFAULT_BEDROCK_MODEL_ID = V_V2.DEFAULT_BEDROCK_MODEL_ID
DEFAULT_BEDROCK_REGION = V_V2.DEFAULT_BEDROCK_REGION
INFERENCE_CONFIG = dict(V_V2.INFERENCE_CONFIG)
REPEATABILITY_CALLS = V_V2.REPEATABILITY_CALLS

# The runtime MUST send only the neutralized packet type (SS22 hard interface guard); there
# is no "default" toggle in V3 -- it is the only packet shape the V4 adapter accepts.
NEUTRAL_IDENTIFIERS_DEFAULT = True


def version_stamp() -> dict[str, str]:
    return {
        "generation_id": GENERATION_ID,
        "ontology_version": ONTOLOGY_VERSION,
        "schema_version": SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "cohort_policy_version": COHORT_POLICY_VERSION,
        "packet_schema_version": PACKET_SCHEMA_VERSION,
        "formation_policy_version": FORMATION_POLICY_VERSION,
        "formation_family_version": FORMATION_FAMILY_VERSION,
        "neutralization_policy_version": NEUTRALIZATION_POLICY_VERSION,
        "formation_structure_version": FORMATION_STRUCTURE_VERSION,
    }


def generation_hash(extra: dict | None = None) -> str:
    payload = {
        **version_stamp(),
        "default_bedrock_model_id": DEFAULT_BEDROCK_MODEL_ID,
        "default_bedrock_region": DEFAULT_BEDROCK_REGION,
        "inference_config": INFERENCE_CONFIG,
        "neutral_identifiers_default": NEUTRAL_IDENTIFIERS_DEFAULT,
    }
    if extra:
        payload["content_hashes"] = extra
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
