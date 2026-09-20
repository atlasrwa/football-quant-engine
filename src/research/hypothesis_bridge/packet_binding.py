"""Packet binding: the bridge must be handed the ACTUAL evidence packet, and verify it.

Verification is split into TWO STAGES, and the split is the point.

    Stage A  verify_packet_envelope(packet, corpus)
             Depends on NOTHING from the proposal. Establishes that the packet is a real,
             untampered, correct-lineage packet for a fixture the corpus knows, and returns
             its verified identity.

    Stage B  verify_proposal_evidence_refs(packet, evidence_refs, proposal_source)
             Runs only once a proposal has parsed, and binds its `evidence_refs`.

WHY THE SPLIT EXISTS
====================
Previously the proposal was parsed first, so a malformed or forbidden LLM response produced a
rejection record with NO packet provenance at all. That is scientifically wrong: invalid model
output is still a TREATMENT RESULT, and it has to stay attributable to the exact evidence the
model saw. If it does not, the rejection-reason distribution cannot be tied to any instrument.
Stage A therefore cannot depend on the proposal parsing, and it resolves the target from the
PACKET's own `fixture_id`.

Nothing here is inferred: the hash is RECOMPUTED from the packet's own contents with the same
helper that produced it, and every binding is an equality check.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

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


def verify_packet_envelope(packet: Any, by_fixture: Mapping[str, MatchRecord], *,
                           raw_fixture_id: Optional[str] = None) -> tuple[dict[str, Any],
                                                                          MatchRecord]:
    """STAGE A. Verify the packet on its own terms and resolve its target from the corpus.

    Takes NO parsed proposal. `raw_fixture_id` is the fixture id read off the RAW payload
    when one is present and readable -- even a payload that is otherwise malformed must not
    be measured against a packet for a different fixture.

    Returns `(packet_identity, target)` or raises `PacketBindingError`.
    """
    if not isinstance(packet, dict):
        raise PacketBindingError("packet_missing_or_not_a_mapping")

    # --- lineage: a packet from the old semantics must not be measured as if corrected ---
    if packet.get("packet_schema_version") != PACKET_SCHEMA_VERSION:
        raise PacketBindingError(
            f"packet_schema_version:{packet.get('packet_schema_version')!r}"
            f"!={PACKET_SCHEMA_VERSION!r}")
    if packet.get("cohort_policy_version") != COHORT_POLICY_VERSION:
        raise PacketBindingError(
            f"cohort_policy_version:{packet.get('cohort_policy_version')!r}"
            f"!={COHORT_POLICY_VERSION!r}")

    fx = packet.get("fixture")
    if not isinstance(fx, dict) or not fx.get("fixture_id"):
        raise PacketBindingError("packet_fixture_absent")
    packet_fixture_id = fx["fixture_id"]

    declared = packet.get("packet_hash")
    if not declared:
        raise PacketBindingError("packet_hash_absent")
    # RECOMPUTED, never trusted: a tampered packet carrying its old hash is refused here.
    actual = recompute_packet_hash(packet)
    if declared != actual:
        raise PacketBindingError(f"packet_hash_mismatch:declared={str(declared)[:12]}"
                                 f"..recomputed={actual[:12]}..")

    # --- the packet's OWN fixture resolves the target; the proposal does not get a vote ---
    target = by_fixture.get(packet_fixture_id)
    if target is None:
        raise PacketBindingError(f"packet_fixture_not_in_corpus:{packet_fixture_id!r}")
    if fx.get("kickoff_unix") != target.kickoff_unix:
        raise PacketBindingError(
            f"packet_kickoff!=target_kickoff:{fx.get('kickoff_unix')!r}"
            f"!={target.kickoff_unix!r}")

    # --- EXACT cutoff equality --------------------------------------------------------
    # v2 allowed `cutoff <= kickoff`. That is leak-free but NOT sufficient: the deterministic
    # measurement consumes every row with `kickoff_unix < target.kickoff_unix`, so a packet
    # cut at 14:00 for a 15:00 kickoff would condition the LLM on a strictly smaller
    # information set than the measurement it is compared against. For THIS confirmatory
    # experiment the two information sets must be identical, so equality is required. An
    # internally consistent, correctly-rehashed, earlier-cut packet is still the wrong
    # instrument. A future experiment wanting genuine snapshot times versions a new protocol;
    # it does not relax this line.
    cutoff = packet.get("information_cutoff_unix")
    if cutoff is None:
        raise PacketBindingError("information_cutoff_absent")
    if cutoff != target.kickoff_unix:
        raise PacketBindingError(
            f"information_cutoff_must_equal_target_kickoff:{cutoff}!={target.kickoff_unix}")

    # --- the raw payload's own fixture id, when it has a readable one ------------------
    if raw_fixture_id is not None and raw_fixture_id != packet_fixture_id:
        raise PacketBindingError(
            f"raw_fixture!=packet_fixture:{raw_fixture_id!r}!={packet_fixture_id!r}")

    identity = {
        "packet_binding_verified": True,
        "packet_schema_version": packet["packet_schema_version"],
        "cohort_policy_version": packet["cohort_policy_version"],
        "packet_hash": actual,
        "packet_fixture_id": packet_fixture_id,
        "packet_kickoff_unix": fx["kickoff_unix"],
        "information_cutoff_unix": cutoff,
        "n_evidence_ids": len(valid_evidence_ids(packet)),
        # Stage B fills these. Present as explicit "not reached yet" rather than absent, so a
        # parse-rejected record does not look like one whose refs were checked and found empty.
        "evidence_refs_bound": None,
        "evidence_refs_verified": False,
        "proposal_source": None,
    }
    return identity, target


def verify_proposal_evidence_refs(packet: Mapping[str, Any], identity: dict[str, Any], *,
                                  evidence_refs: tuple[str, ...] = (),
                                  proposal_source: str = SOURCE_LLM_PROPOSAL
                                  ) -> dict[str, Any]:
    """STAGE B. Bind a PARSED proposal's `evidence_refs` into the verified identity."""
    if proposal_source not in PROPOSAL_SOURCES:
        raise PacketBindingError(f"unknown_proposal_source:{proposal_source}")

    known = valid_evidence_ids(packet)
    unknown = sorted(set(evidence_refs) - known)
    if unknown:
        raise PacketBindingError(f"evidence_refs_not_in_packet:{unknown[:5]}")
    if not evidence_refs and proposal_source == SOURCE_LLM_PROPOSAL:
        raise PacketBindingError("llm_proposal_requires_at_least_one_evidence_ref")

    bound = dict(identity)
    bound["evidence_refs_bound"] = list(evidence_refs)
    bound["evidence_refs_verified"] = True
    bound["proposal_source"] = proposal_source
    return bound
