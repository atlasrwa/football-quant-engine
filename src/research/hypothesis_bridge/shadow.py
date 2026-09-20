"""ShadowResearchRecord — the immutable, versioned output of the bridge.

Every record, VALID or REJECTED, is emitted: a rejection is a research result, and dropping
it would make the rejection-reason distribution unmeasurable. No record may carry a
predictive quantity; `firewall.assert_outbound_clean` is the last gate before one is returned.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from typing import Any, Optional

from src.research.matchup.corpus import MatchRecord
from src.research.hypothesis_bridge import firewall, registry
from src.research.hypothesis_bridge.canonical import CanonicalHypothesis
from src.research.hypothesis_bridge.proposal import HypothesisProposal
from src.research.hypothesis_bridge.validation import ValidationResult
from src.research.hypothesis_bridge.versions import (
    SHADOW_RECORD_VERSION, CANONICAL_IR_VERSION, VALIDATOR_VERSION, COMPILER_VERSION,
    MEASUREMENT_VERSION, bridge_version_stamp)


def producer_code_commit() -> str:
    """The commit that produced this record, or an explicit unknown marker."""
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                             timeout=10)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:                                    # pragma: no cover - environment
        pass
    return "UNKNOWN_PRODUCER_COMMIT"


def build_record(*, proposal: HypothesisProposal, target: MatchRecord,
                 validation: ValidationResult,
                 packet_identity: Optional[dict[str, Any]] = None,
                 ir: Optional[CanonicalHypothesis] = None,
                 measurement: Optional[dict[str, Any]] = None,
                 data_vintage: Optional[str] = None,
                 producer_commit: Optional[str] = None,
                 measurement_provider: Optional[str] = None,
                 provider_policy: Optional[Any] = None,
                 capability: Optional[Any] = None) -> dict:
    """Assemble and firewall-check a shadow record. Raises if anything predictive is present.

    `packet_identity` is the VERIFIED identity returned by `packet_binding`, never a
    caller-supplied hash. Since the envelope is now verified BEFORE the proposal is parsed, a
    record rejected for a forbidden or malformed proposal still carries real packet identity;
    `packet_identity` is None only when the PACKET ITSELF failed, and
    `packet_binding_verified` states which case a reader is looking at rather than leaving it
    to be inferred from a placeholder.

    `measurement_provider` / `provider_policy` / `capability` record the provider ACTUALLY
    resolved for this record, so provenance is never re-derived from a field name later.
    """
    pid = packet_identity or {}
    record = {
        "record_version": SHADOW_RECORD_VERSION,
        "fixture_id": target.fixture_id,
        "target_kickoff": target.kickoff_unix,

        "proposal_id": proposal.proposal_id,
        "proposal_hash": proposal.proposal_hash(),

        # Verified packet identity. Recomputed from the packet's own contents at bind time.
        "packet_binding_verified": bool(packet_identity),
        "packet_schema_version": pid.get("packet_schema_version"),
        "packet_cohort_policy_version": pid.get("cohort_policy_version"),
        "packet_hash": pid.get("packet_hash"),
        "packet_fixture_id": pid.get("packet_fixture_id"),
        "packet_kickoff_unix": pid.get("packet_kickoff_unix"),
        "packet_information_cutoff_unix": pid.get("information_cutoff_unix"),
        "evidence_refs_bound": pid.get("evidence_refs_bound"),
        "evidence_refs_verified": bool(pid.get("evidence_refs_verified")),
        "proposal_source": pid.get("proposal_source"),

        "canonical_hypothesis_id": (ir.canonical_hypothesis_id if ir else None),
        "canonical_ir": (ir.to_dict() if ir else None),
        "canonical_ir_version": CANONICAL_IR_VERSION,

        # --- provider provenance: which provider's numbers this record is about --------
        # Recorded explicitly because the corpus is shaped into a FootyStats SCHEMA while the
        # values come from TheStatsAPI. A later reader must never have to infer the provider
        # from a storage field name.
        "measurement_provider": measurement_provider,
        "provider_policy": (provider_policy.value if hasattr(provider_policy, "value")
                            else provider_policy),
        "provider_capability_id": (capability.capability_id if capability else None),
        "provider_source_field": (capability.provider_source_field if capability else None),
        "provider_capability_status": (capability.status if capability else None),
        "corpus_storage_schema": registry.CORPUS_STORAGE_SCHEMA,
        "provider_capability_hash": registry.registry_hash(),
        "capability_hash": registry.registry_hash(),
        "provider_registry_version": bridge_version_stamp()["capability_registry_version"],
        # Target-bounded: rows appended after the target cannot move it, so a record stays
        # stable as the corpus grows forward.
        "data_vintage_target_bounded": data_vintage,
        # Value identities, lifted out of the measurement payload so a rejected record that
        # never measured still shows which surface it was validated against.
        "cohort_source_hash": (measurement or {}).get("cohort_source_hash"),
        "baseline_source_hash": (measurement or {}).get("baseline_source_hash"),
        "measurement_input_hash": (measurement or {}).get("measurement_input_hash"),
        "cohort_identity_hash": (measurement or {}).get("cohort_identity_hash"),

        "validator_version": VALIDATOR_VERSION,
        "compiler_version": COMPILER_VERSION,
        "measurement_version": MEASUREMENT_VERSION,
        "bridge_version_stamp": bridge_version_stamp(),

        "validation_status": validation.status,
        "rejection_reason": validation.rejection_reason,

        "raw_n": validation.raw_n,
        "effective_n": validation.effective_n,
        "coverage": validation.coverage,

        "measurement": measurement,

        "research_reason": proposal.research_reason,
        "evidence_refs": list(proposal.evidence_refs),

        "producer_code_commit": producer_commit or producer_code_commit(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # Last gate. A record that reached storage carrying an edge would afterwards be
    # indistinguishable from a legitimate one, so this raises rather than filtering.
    firewall.assert_outbound_clean(record)
    return record
