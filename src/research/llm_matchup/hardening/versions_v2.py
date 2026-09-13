"""LLM_MATCHUP_V2 — the hardened research generation identity (patch §28).

The hardening patch changes the prompt (V3, two-pass adversarial contract), the schema
(V3, counter_evidence_search + neutral-identifier context), and the runtime packet
(neutral identifiers by default). Per the freeze rule (patch §1), any such change creates a
NEW generation. This module defines that generation WITHOUT mutating the frozen Phase-B
`versions.py`.

We deliberately keep the frozen ontology_version unchanged: the mechanism *taxonomy* is not
being redefined by this patch (patch §8 asks us to review/clarify definitions only if a
mechanism is unstable, not to churn the taxonomy). If a future step merges/clarifies
mechanisms, bump ONTOLOGY_VERSION_V2 here and re-freeze.

Nothing here is imported by the frozen Phase-B modules; it is additive.
"""
from __future__ import annotations
import hashlib, json
from src.research.llm_matchup import versions as V_FROZEN

GENERATION_ID = "LLM_MATCHUP_V2"

# --- Hardened version pins ------------------------------------------------------
# Ontology taxonomy is unchanged from the frozen v2; the prompt/schema/packet change.
ONTOLOGY_VERSION = V_FROZEN.ONTOLOGY_VERSION            # football_ontology_v2 (unchanged)
SCHEMA_VERSION = "football_state_schema_v3"            # + counter_evidence_search
PROMPT_VERSION = "sonnet_prompt_v3"                    # two-pass adversarial contract
COHORT_POLICY_VERSION = V_FROZEN.COHORT_POLICY_VERSION  # unchanged (patch §41, §42: no re-tune)
PACKET_SCHEMA_VERSION = "fixture_evidence_packet_v3"   # neutral identifiers by default
FORMATION_POLICY_VERSION = V_FROZEN.FORMATION_POLICY_VERSION
FORMATION_FAMILY_VERSION = V_FROZEN.FORMATION_FAMILY_VERSION

# Bedrock identity is inherited from the frozen defaults (no model change, patch §2). The
# resolved model id is still recorded per call.
DEFAULT_BEDROCK_MODEL_ID = V_FROZEN.DEFAULT_BEDROCK_MODEL_ID
DEFAULT_BEDROCK_REGION = V_FROZEN.DEFAULT_BEDROCK_REGION

# Analytical inference config unchanged (temperature 0 does NOT guarantee determinism;
# that is precisely what the repeatability study measures). Aggregation over k calls is the
# controlled mitigation (patch §31-§33), not a temperature tweak (patch §3).
INFERENCE_CONFIG = dict(V_FROZEN.INFERENCE_CONFIG)

# Number of identical calls for the hardening repeatability study (patch §6: prefer 3).
REPEATABILITY_CALLS = 3

# Neutral-identifier runtime default (patch §25): the runtime LLM packet uses TEAM_A/TEAM_B
# and a neutral competition id by default. Real names are only ever used in the offline
# name-control experiment.
NEUTRAL_IDENTIFIERS_DEFAULT = True


def version_stamp() -> dict[str, str]:
    """Immutable version fingerprint for the hardened generation."""
    return {
        "generation_id": GENERATION_ID,
        "ontology_version": ONTOLOGY_VERSION,
        "schema_version": SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "cohort_policy_version": COHORT_POLICY_VERSION,
        "packet_schema_version": PACKET_SCHEMA_VERSION,
        "formation_policy_version": FORMATION_POLICY_VERSION,
        "formation_family_version": FORMATION_FAMILY_VERSION,
    }


def generation_hash(extra: dict | None = None) -> str:
    """Deterministic hash over the full generation identity (versions + model + inference +
    optionally the prompt/schema content hashes supplied by the caller). Used to prove no
    silent change after freeze (patch §28)."""
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
