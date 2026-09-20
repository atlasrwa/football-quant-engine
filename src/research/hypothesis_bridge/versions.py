"""Version pins for the hypothesis -> validation -> shadow-record bridge.

Every artifact this bridge emits is stamped with these. They are separate from the LLM
evidence lineage (`llm_matchup/versions.py`) on purpose: the bridge can change without
redefining what an evidence packet is, and vice versa.
"""
from __future__ import annotations

# Bumped where the MEANING changed, left alone where it did not. Every decision is stated so
# an unchanged version is as auditable as a changed one.
#
#   UNCHANGED  proposal schema  -- the proposal SHAPE is identical; `proposal_source` is a
#              call-site argument, not a proposal field.
#   UNCHANGED  canonical IR     -- canonical hypothesis semantics and the id derivation are
#              untouched, so an id minted before this change still means the same thing.
#   UNCHANGED  compiler         -- canonicalization logic did not change.
#   BUMPED     validator v2     -- validation now requires and verifies the actual evidence
#              packet (lineage, fixture/kickoff binding, recomputed hash, evidence_refs).
#   BUMPED     measurement v2   -- provenance now binds the measured VALUES
#              (cohort/baseline source hashes, target-bounded vintage), not just membership.
#   BUMPED     shadow record v2 -- the record schema gained verified packet identity and the
#              new source-hash fields.
#   BUMPED     registry v2      -- provider provenance is now an explicit traced table; the
#              previous container-based inference reported `yellow_cards` as footystats when
#              it is read from the TheStatsAPI /stats payload.
PROPOSAL_SCHEMA_VERSION = "hypothesis_proposal_v1"
CANONICAL_IR_VERSION = "canonical_hypothesis_ir_v1"
VALIDATOR_VERSION = "hypothesis_validator_v2"
COMPILER_VERSION = "hypothesis_compiler_v1"
MEASUREMENT_VERSION = "deterministic_measurement_v2"
SHADOW_RECORD_VERSION = "shadow_research_record_v2"
CAPABILITY_REGISTRY_VERSION = "provider_capability_registry_v2"


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
