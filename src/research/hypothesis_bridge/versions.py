"""Version pins for the hypothesis -> validation -> shadow-record bridge.

Every artifact this bridge emits is stamped with these. They are separate from the LLM
evidence lineage (`llm_matchup/versions.py`) on purpose: the bridge can change without
redefining what an evidence packet is, and vice versa.
"""
from __future__ import annotations

# Bumped where the MEANING changed, left alone where it did not. Every decision is stated so
# an unchanged version is as auditable as a changed one.
#
#   UNCHANGED  proposal schema  -- the proposal SHAPE is unchanged. Proposals are now parsed
#              AFTER the packet envelope instead of before it, but that is execution order in
#              the bridge, not a change to what a proposal is; a v1 proposal still parses to
#              the same object and hashes the same.
#   UNCHANGED  canonical IR     -- canonical hypothesis semantics and the id derivation are
#              untouched, so an id minted before this change still means the same thing.
#   UNCHANGED  compiler         -- canonicalization logic did not change.
#
#   BUMPED  validator v2 -> v3
#              Two semantic changes, either of which alone would require it. (a) Packet
#              verification is SPLIT: the envelope is verified before the proposal is parsed,
#              so a malformed proposal no longer destroys packet provenance, and the
#              rejection PRECEDENCE between PACKET_BINDING_FAILED and a parse failure is now
#              defined. (b) `information_cutoff_unix` must EQUAL the target kickoff; v2
#              accepted any cutoff at or before it, which admitted packets conditioned on a
#              different information set than the deterministic measurement.
#   BUMPED  measurement v2 -> v3
#              Provider identity is now bound into the measurement source hashes. The same
#              numeric value traced to a different provider capability can no longer produce
#              the same provenance hash. `cohort_identity_hash` and the target-bounded
#              vintage embed MEASUREMENT_VERSION, so they move with it -- intended: a v2
#              hash asserted a weaker provenance claim than a v3 hash and the two must not
#              be comparable.
#   BUMPED  shadow record v2 -> v3
#              The record gained `measurement_provider`, `provider_policy`,
#              `provider_capability_id`, `provider_capability_hash` and
#              `provider_source_field`, and its packet-identity semantics changed: a record
#              rejected at parse time now carries VERIFIED packet identity rather than None.
#   BUMPED  registry v2 -> v3
#              The registry is re-keyed from `metric -> capability` to
#              `(provider, canonical_metric) -> capability`. This is a change of identity,
#              not of content: under v2 a metric had ONE capability and the second provider
#              was unrepresentable.
PROPOSAL_SCHEMA_VERSION = "hypothesis_proposal_v1"
CANONICAL_IR_VERSION = "canonical_hypothesis_ir_v1"
VALIDATOR_VERSION = "hypothesis_validator_v3"
COMPILER_VERSION = "hypothesis_compiler_v1"
MEASUREMENT_VERSION = "deterministic_measurement_v3"
SHADOW_RECORD_VERSION = "shadow_research_record_v3"
CAPABILITY_REGISTRY_VERSION = "provider_capability_registry_v3"


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
