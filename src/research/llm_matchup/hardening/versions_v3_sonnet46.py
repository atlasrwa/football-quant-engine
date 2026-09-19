"""LLM_MATCHUP_V3_SONNET46 — the Sonnet 4.6 arm of the V3 identity-neutral generation.

This module defines a SECOND, INDEPENDENT scientific generation that isolates exactly ONE
variable versus `versions_v3` (LLM_MATCHUP_V3 / Sonnet 4.5): the Bedrock model identity.

LLM_MATCHUP_V3 (versions_v3.py) is PRESERVED, untouched, and remains the scientific record
of the Sonnet 4.5 arm (frozen fixture manifest + partially-complete golden batch interrupted
by an external AWS daily-token quota). Nothing here mutates it.

WHAT CHANGES vs LLM_MATCHUP_V3 (exactly one scientific axis):
  * DEFAULT_BEDROCK_MODEL_ID -> us.anthropic.claude-sonnet-4-6  (verified ACTIVE,
    SYSTEM_DEFINED cross-region inference profile; the 4.5 arm pins
    us.anthropic.claude-sonnet-4-5-20250929-v1:0)
  * GENERATION_ID -> LLM_MATCHUP_V3_SONNET46, so every artifact, cache key and freeze is
    attributable to a specific model generation ("model identity is part of the scientific
    generation").

WHAT IS DELIBERATELY IDENTICAL (imported by reference from versions_v3, never re-declared,
so the two arms cannot silently drift apart):
  * ONTOLOGY_VERSION, SCHEMA_VERSION (output tool schema), PROMPT_VERSION (sonnet_prompt_v4),
    COHORT_POLICY_VERSION, PACKET_SCHEMA_VERSION, FORMATION_POLICY_VERSION,
    FORMATION_FAMILY_VERSION, NEUTRALIZATION_POLICY_VERSION, FORMATION_STRUCTURE_VERSION
  * DEFAULT_BEDROCK_REGION, INFERENCE_CONFIG (temperature/topP/maxTokens), REPEATABILITY_CALLS

CRITICAL CONSEQUENCE OF REUSING PACKET_SCHEMA_VERSION: because `neutralize_v3` stamps the
LLM-facing packet with `PACKET_SCHEMA_VERSION` and NOT with `generation_id`, the neutralized
evidence packet — and therefore the literal serialized request text — is BYTE-IDENTICAL
between the 4.5 and 4.6 arms for the same fixture. The two arms receive semantically and
literally identical instructions and data. This is a MODEL change, not a MODEL+PROMPT change.
"""
from __future__ import annotations
import hashlib
import json

from src.research.llm_matchup.hardening import versions_v3 as V3

GENERATION_ID = "LLM_MATCHUP_V3_SONNET46"

# --- unchanged from LLM_MATCHUP_V3 (by reference, so drift is impossible) -----------
ONTOLOGY_VERSION = V3.ONTOLOGY_VERSION
SCHEMA_VERSION = V3.SCHEMA_VERSION
PROMPT_VERSION = V3.PROMPT_VERSION
COHORT_POLICY_VERSION = V3.COHORT_POLICY_VERSION
PACKET_SCHEMA_VERSION = V3.PACKET_SCHEMA_VERSION
FORMATION_POLICY_VERSION = V3.FORMATION_POLICY_VERSION
FORMATION_FAMILY_VERSION = V3.FORMATION_FAMILY_VERSION
NEUTRALIZATION_POLICY_VERSION = V3.NEUTRALIZATION_POLICY_VERSION
FORMATION_STRUCTURE_VERSION = V3.FORMATION_STRUCTURE_VERSION

DEFAULT_BEDROCK_REGION = V3.DEFAULT_BEDROCK_REGION
INFERENCE_CONFIG = dict(V3.INFERENCE_CONFIG)
REPEATABILITY_CALLS = V3.REPEATABILITY_CALLS
NEUTRAL_IDENTIFIERS_DEFAULT = V3.NEUTRAL_IDENTIFIERS_DEFAULT

# --- THE ONLY SCIENTIFIC CHANGE -----------------------------------------------------
# Independently verified 2026-09-13 against the live account (865147226910 / us-east-1):
#
#   aws bedrock get-foundation-model --model-identifier anthropic.claude-sonnet-4-6
#     -> modelName          "Claude Sonnet 4.6"
#        modelLifecycle     ACTIVE (startOfLifeTime 2026-02-17T18:00:00+00:00)
#        inferenceTypes     ["INFERENCE_PROFILE"]      <-- base id is NOT directly invocable
#
#   aws bedrock list-inference-profiles
#     -> inferenceProfileId   us.anthropic.claude-sonnet-4-6
#        inferenceProfileName "US Anthropic Claude Sonnet 4.6"
#        status               ACTIVE
#        type                 SYSTEM_DEFINED
#        inferenceProfileArn  arn:aws:bedrock:us-east-1:865147226910:
#                               inference-profile/us.anthropic.claude-sonnet-4-6
#        models               anthropic.claude-sonnet-4-6 in us-east-1 / us-east-2 / us-west-2
#
# NOTE ON VERIFICATION METHOD: `bedrock:GetInferenceProfile` is DENIED for this IAM principal
# (arn:aws:iam::865147226910:user/atlas-ubuntu-deployer), so the profile facts above come from
# `list-inference-profiles`, which this principal CAN read and which returns the authoritative
# ARN and member-model ARNs. Do not re-add a claim that GetInferenceProfile was used.
#
# Because the base model is INFERENCE_PROFILE-only, the profile id is the ONLY invocable
# identifier. This is the exact structural analogue of the 4.5 arm, which likewise pins a
# `us.` SYSTEM_DEFINED cross-region profile (us.anthropic.claude-sonnet-4-5-20250929-v1:0)
# fronting the same three US regions -- so routing topology is held constant across the arms
# and only the model version varies.
#
# SCIENTIFIC CAVEAT (must be carried into the freeze): the 4.5 arm pins a DATE-STAMPED,
# version-suffixed id (`...-20250929-v1:0`), whereas the only 4.6 id AWS exposes in this
# account is UNDATED and unversioned (`anthropic.claude-sonnet-4-6`; no dated variant exists
# in list-foundation-models). An undated alias is not guaranteed to be weight-stable over
# calendar time, so the 4.6 arm's reproducibility guarantee is inherently weaker than the
# 4.5 arm's. We therefore capture whatever resolved model identity Bedrock echoes back per
# call, and stamp the observation date into the freeze.
DEFAULT_BEDROCK_MODEL_ID = "us.anthropic.claude-sonnet-4-6"
MODEL_ID_IS_DATE_PINNED = False          # contrast: the 4.5 arm's id IS date-pinned
MODEL_VERIFIED_UNIX = 1789310000         # 2026-09-13, account 865147226910, us-east-1

BEDROCK_INFERENCE_PROFILE_ARN = (
    "arn:aws:bedrock:us-east-1:865147226910:inference-profile/us.anthropic.claude-sonnet-4-6")
BEDROCK_BASE_MODEL_ID = "anthropic.claude-sonnet-4-6"


def version_stamp() -> dict[str, str]:
    """Same axes as V3.version_stamp(); only generation_id differs."""
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


def diff_vs_v45() -> dict:
    """Explicit, auditable statement of what differs between the two arms. Used by the
    freeze/report so the single-variable claim is machine-checkable, not prose."""
    a, b = V3.version_stamp(), version_stamp()
    differing = {k: {"sonnet45": a.get(k), "sonnet46": b.get(k)}
                 for k in set(a) | set(b) if a.get(k) != b.get(k)}
    return {
        "version_stamp_differences": differing,
        "model_id": {"sonnet45": V3.DEFAULT_BEDROCK_MODEL_ID,
                     "sonnet46": DEFAULT_BEDROCK_MODEL_ID},
        "region_identical": V3.DEFAULT_BEDROCK_REGION == DEFAULT_BEDROCK_REGION,
        "inference_config_identical": dict(V3.INFERENCE_CONFIG) == dict(INFERENCE_CONFIG),
        "prompt_version_identical": V3.PROMPT_VERSION == PROMPT_VERSION,
        "schema_version_identical": V3.SCHEMA_VERSION == SCHEMA_VERSION,
        "packet_schema_version_identical": V3.PACKET_SCHEMA_VERSION == PACKET_SCHEMA_VERSION,
        "neutralization_identical": (
            V3.NEUTRALIZATION_POLICY_VERSION == NEUTRALIZATION_POLICY_VERSION),
        "formation_structure_identical": (
            V3.FORMATION_STRUCTURE_VERSION == FORMATION_STRUCTURE_VERSION),
    }
