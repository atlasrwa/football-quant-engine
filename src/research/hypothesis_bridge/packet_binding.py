"""Packet binding: the bridge must be handed the ACTUAL evidence packet, and verify it.

The first implementation accepted `packet_hash="NO_PACKET"` by default, so the executed path
was corpus -> proposal -> measurement, with packet provenance and `evidence_refs` never
structurally bound. A caller-supplied hash was trusted without recomputation.

Nothing here is inferred: the hash is RECOMPUTED from the packet's own contents with the same
helper that produced it, and every binding is an equality check against the target.
"""
from __future__ import annotations

from typing import Any, Optional

from src.research.matchup.corpus import MatchRecord
from src.research.llm_matchup.evidence import packet_hash as recompute_packet_hash, valid_evidence_ids
from src.research.llm_matchup.versions import PACKET_SCHEMA_VERSION, COHORT_POLICY_VERSION

#: Proposal sources. A deterministic rehearsal stub may legitimately carry no evidence_refs;
#: an LLM-generated proposal may not, because an ungrounded hypothesis is exactly what this
#: bridge exists to refuse. The two modes are explicit and never conflated.
SOURCE_DETERMINISTIC_REHEARSAL = "DETERMINISTIC_REHEARSAL"
SOURCE_LLM_PROPOSAL = "LLM_PROPOSAL"
PROPOSAL_SOURCES = frozenset({SOURCE_DETERMINISTIC_REHEARSAL, SOURCE_LLM_PROPOSAL})


class PacketBindingError(ValueError):
    """The supplied packet does not bind to this proposal/target, or is not this lineage."""


def verify_packet(packet: Any, target: MatchRecord, *, fixture_id: str,
                  evidence_refs: tuple[str, ...] = (),
                  proposal_source: str = SOURCE_LLM_PROPOSAL) -> dict[str, Any]:
    """Verify a packet binds to this proposal and target, or raise. Returns its identity."""
    if not isinstance(packet, dict):
        raise PacketBindingError("packet_missing_or_not_a_mapping")
    if proposal_source not in PROPOSAL_SOURCES:
        raise PacketBindingError(f"unknown_proposal_source:{proposal_source}")

    # --- lineage: a packet from the old semantics must not be measured as if corrected ---
    if packet.get("packet_schema_version") != PACKET_SCHEMA_VERSION:
        raise PacketBindingError(
            f"packet_schema_version:{packet.get('packet_schema_version')!r}"
            f"!={PACKET_SCHEMA_VERSION!r}")
    if packet.get("cohort_policy_version") != COHORT_POLICY_VERSION:
        raise PacketBindingError(
            f"cohort_policy_version:{packet.get('cohort_policy_version')!r}"
            f"!={COHORT_POLICY_VERSION!r}")

    fx = (packet.get("fixture") or {})
    if fx.get("fixture_id") != fixture_id:
        raise PacketBindingError(
            f"packet_fixture!=proposal_fixture:{fx.get('fixture_id')!r}!={fixture_id!r}")
    if fx.get("fixture_id") != target.fixture_id:
        raise PacketBindingError(
            f"packet_fixture!=target_fixture:{fx.get('fixture_id')!r}!={target.fixture_id!r}")
    if fx.get("kickoff_unix") != target.kickoff_unix:
        raise PacketBindingError(
            f"packet_kickoff!=target_kickoff:{fx.get('kickoff_unix')!r}"
            f"!={target.kickoff_unix!r}")

    declared = packet.get("packet_hash")
    if not declared:
        raise PacketBindingError("packet_hash_absent")
    # RECOMPUTED, never trusted: a tampered packet carrying its old hash is refused here.
    actual = recompute_packet_hash(packet)
    if declared != actual:
        raise PacketBindingError(f"packet_hash_mismatch:declared={declared[:12]}"
                                 f"..recomputed={actual[:12]}..")

    cutoff = packet.get("information_cutoff_unix")
    if cutoff is None:
        raise PacketBindingError("information_cutoff_absent")
    if cutoff > target.kickoff_unix:
        raise PacketBindingError(
            f"information_cutoff_after_kickoff:{cutoff}>{target.kickoff_unix}")

    # --- evidence_refs must exist in THIS packet -------------------------------------
    known = valid_evidence_ids(packet)
    unknown = sorted(set(evidence_refs) - known)
    if unknown:
        raise PacketBindingError(f"evidence_refs_not_in_packet:{unknown[:5]}")
    if not evidence_refs and proposal_source == SOURCE_LLM_PROPOSAL:
        raise PacketBindingError(
            "llm_proposal_requires_at_least_one_evidence_ref")

    return {
        "packet_schema_version": packet["packet_schema_version"],
        "cohort_policy_version": packet["cohort_policy_version"],
        "packet_hash": actual,
        "packet_fixture_id": fx["fixture_id"],
        "packet_kickoff_unix": fx["kickoff_unix"],
        "information_cutoff_unix": cutoff,
        "n_evidence_ids": len(known),
        "evidence_refs_bound": list(evidence_refs),
        "proposal_source": proposal_source,
    }
