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
# --- corrected evidence lineage (target-season semantics) ------------------------
# The evidence builders previously filtered "current-season" team state by the season each
# team LAST PLAYED IN (`cohorts.HistoryIndex.current_season`). For a fixture early in a new
# season-instance that is the PREVIOUS season, so prior-season history was served as
# current-season state and cold-start floors were met by stale data. The builders now key on
# `cohorts.HistoryIndex.target_season(target)` -- the season of the fixture being predicted.
#
# That is a different scientific instrument, so it gets a new lineage rather than reusing the
# old identity:
#
#   OLD_LINEAGE  cohort_policy_v1 / fixture_evidence_packet_v2   HISTORICAL_FROZEN
#   NEW_LINEAGE  cohort_policy_v2 / fixture_evidence_packet_v4   CORRECTED_SUCCESSOR
#
# `cohort_policy_v2` propagates through `hardening/versions_v2` -> `versions_v3` ->
# `versions_v3_sonnet46`, because those arms build their packets through the very builder
# that was corrected (`phaseb_harness` -> `EvidencePacketBuilderV2` -> `evidence.py`). That
# propagation is the intended signal, not collateral damage: it changes `version_stamp()`,
# so `adapter_v4._cache_key` changes and no corrected packet can ever read a cache entry
# written under the old semantics.
#
# `fixture_evidence_packet_v4` skips v3: `hardening/versions_v2.PACKET_SCHEMA_VERSION` is
# already `fixture_evidence_packet_v3`, and two different packet types must not share a name.
#
# The frozen 4.5/4.6 artifacts are NOT regenerated and remain byte-identical on disk. They
# are historical evidence produced under the old lineage and are labelled as such.
COHORT_POLICY_VERSION = "cohort_policy_v2"
PACKET_SCHEMA_VERSION = "fixture_evidence_packet_v4"
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
