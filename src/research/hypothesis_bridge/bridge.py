"""The bridge: proposal -> canonical IR -> validation -> measurement -> shadow record.

Deterministic and offline. It makes NO model call: the LLM's only role is upstream, producing
the structured proposal. `run_proposal` never invokes a provider, a model or the network, and
the rehearsal harness relies on that.
"""
from __future__ import annotations

from typing import Any, Optional

from src.research.matchup.corpus import MatchRecord
from src.research.llm_matchup import cohorts as CH
from src.research.hypothesis_bridge import (canonical, measurement, packet_binding as PB,
                                            proposal as P, shadow, status as ST, validation)


class BridgeContext:
    """Holds the corpus-derived index once; runs many proposals against it."""

    def __init__(self, recs: list[MatchRecord], *,
                 producer_commit: Optional[str] = None):
        self.recs = recs
        self.idx = CH.HistoryIndex(recs)
        self.by_fixture = {r.fixture_id: r for r in recs}
        self.producer_commit = producer_commit or shadow.producer_code_commit()

    def _record(self, prop, target, vr, ir=None, meas=None, packet_identity=None,
                vintage=None):
        return shadow.build_record(
            proposal=prop, target=target, packet_identity=packet_identity, validation=vr,
            ir=ir, measurement=meas, data_vintage=vintage,
            producer_commit=self.producer_commit)

    def run_proposal(self, raw: dict, *, packet: dict,
                     proposal_source: str = PB.SOURCE_LLM_PROPOSAL) -> dict:
        """Always returns a shadow record. A rejection IS a research result.

        `packet` is REQUIRED and is the actual evidence packet, not a hash string. There is
        no NO_PACKET path: a hypothesis measured without the evidence it claims to be
        grounded in is exactly what this bridge exists to refuse, so a missing or
        non-binding packet is PACKET_BINDING_FAILED rather than a default.
        """
        # 1. Parse + numerical firewall. A prohibited field is its own status, not AMBIGUOUS:
        #    the proposal was well-formed and was refused for trying to carry a prediction.
        try:
            prop = P.parse_proposal(raw)
        except P.ProposalError as e:
            detail = str(e)
            st = (ST.FORBIDDEN_PREDICTION_FIELD if "prediction_field:" in detail
                  else ST.AMBIGUOUS_PROPOSAL)
            stub = P.HypothesisProposal(
                fixture_id=str(raw.get("fixture_id", "UNKNOWN")) if isinstance(raw, dict) else "UNKNOWN",
                subject="home_team", target_metric="UNKNOWN", perspective="for",
                comparator="team_season_baseline",
                research_reason=(str(raw.get("research_reason", "")) if isinstance(raw, dict) else ""))
            target = self.by_fixture.get(stub.fixture_id)
            if target is None:
                target = MatchRecord(fixture_id=stub.fixture_id, competition="UNKNOWN",
                                     competition_id="UNKNOWN", season_id="UNKNOWN",
                                     kickoff_unix=0, home="?", away="?", home_id="?",
                                     away_id="?", base={}, rich={}, extra={})
            return self._record(stub, target, validation.ValidationResult(st, detail))

        target = self.by_fixture.get(prop.fixture_id)
        if target is None:
            return self._record(prop, MatchRecord(
                fixture_id=prop.fixture_id, competition="UNKNOWN", competition_id="UNKNOWN",
                season_id="UNKNOWN", kickoff_unix=0, home="?", away="?", home_id="?",
                away_id="?", base={}, rich={}, extra={}),
                validation.ValidationResult(ST.MISSING_DATA, "fixture not in corpus"))

        # 2. Packet binding, BEFORE canonicalization: a hypothesis is only meaningful
        #    against the evidence it was grounded in, and the hash is RECOMPUTED here rather
        #    than trusted from the caller.
        try:
            packet_identity = PB.verify_packet(
                packet, target, fixture_id=prop.fixture_id,
                evidence_refs=prop.evidence_refs, proposal_source=proposal_source)
        except PB.PacketBindingError as e:
            return self._record(prop, target,
                                validation.ValidationResult(ST.PACKET_BINDING_FAILED, str(e)))

        # 3. Canonicalization. No fuzzy fallback: unmappable is COMPILER_REFUSED.
        try:
            ir = canonical.canonicalize(prop)
        except canonical.CanonicalizationRefused as e:
            return self._record(prop, target,
                                validation.ValidationResult(ST.COMPILER_REFUSED, str(e)),
                                packet_identity=packet_identity)

        # 4. Provider / PIT / support.
        vr = validation.validate(self.idx, target, ir)
        vintage = measurement.target_bounded_vintage(self.idx, target, ir)
        if not vr.ok:
            return self._record(prop, target, vr, ir=ir, packet_identity=packet_identity,
                                vintage=vintage)

        # 5. Deterministic measurement, only now.
        try:
            meas = measurement.measure(self.idx, target, ir)
        except measurement.MeasurementFailed as e:
            return self._record(prop, target,
                                validation.ValidationResult(
                                    ST.MEASUREMENT_FAILED, str(e), raw_n=vr.raw_n,
                                    effective_n=vr.effective_n, coverage=vr.coverage),
                                ir=ir, packet_identity=packet_identity, vintage=vintage)

        return self._record(prop, target, vr, ir=ir, meas=meas,
                            packet_identity=packet_identity, vintage=vintage)
