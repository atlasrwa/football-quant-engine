"""The bridge: proposal -> canonical IR -> validation -> measurement -> shadow record.

Deterministic and offline. It makes NO model call: the LLM's only role is upstream, producing
the structured proposal. `run_proposal` never invokes a provider, a model or the network, and
the rehearsal harness relies on that.
"""
from __future__ import annotations

from typing import Any, Optional

from src.research.matchup.corpus import MatchRecord
from src.research.llm_matchup import cohorts as CH
from src.research.hypothesis_bridge import (canonical, measurement, proposal as P,
                                            shadow, status as ST, validation)


class BridgeContext:
    """Holds the corpus-derived index once; runs many proposals against it."""

    def __init__(self, recs: list[MatchRecord], *, packet_version: str = "UNKNOWN_PACKET",
                 producer_commit: Optional[str] = None):
        self.recs = recs
        self.idx = CH.HistoryIndex(recs)
        self.by_fixture = {r.fixture_id: r for r in recs}
        self.packet_version = packet_version
        self.corpus_identity = shadow.corpus_vintage(recs)
        self.producer_commit = producer_commit or shadow.producer_code_commit()

    def _record(self, prop, target, vr, ir=None, meas=None, packet_hash="NO_PACKET"):
        return shadow.build_record(
            proposal=prop, target=target, packet_version=self.packet_version,
            packet_hash=packet_hash, validation=vr, ir=ir, measurement=meas,
            corpus_identity=self.corpus_identity, producer_commit=self.producer_commit)

    def run_proposal(self, raw: dict, *, packet_hash: str = "NO_PACKET") -> dict:
        """Always returns a shadow record. A rejection IS a research result.

        Dropping rejections would make the rejection-reason distribution unmeasurable, which
        is the main structural diagnostic this apparatus exists to produce.
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
            return self._record(stub, target,
                                validation.ValidationResult(st, detail), packet_hash=packet_hash)

        target = self.by_fixture.get(prop.fixture_id)
        if target is None:
            return self._record(prop, MatchRecord(
                fixture_id=prop.fixture_id, competition="UNKNOWN", competition_id="UNKNOWN",
                season_id="UNKNOWN", kickoff_unix=0, home="?", away="?", home_id="?",
                away_id="?", base={}, rich={}, extra={}),
                validation.ValidationResult(ST.MISSING_DATA, "fixture not in corpus"),
                packet_hash=packet_hash)

        # 2. Canonicalization. No fuzzy fallback: unmappable is COMPILER_REFUSED.
        try:
            ir = canonical.canonicalize(prop)
        except canonical.CanonicalizationRefused as e:
            return self._record(prop, target,
                                validation.ValidationResult(ST.COMPILER_REFUSED, str(e)),
                                packet_hash=packet_hash)

        # 3. Provider / PIT / support.
        vr = validation.validate(self.idx, target, ir)
        if not vr.ok:
            return self._record(prop, target, vr, ir=ir, packet_hash=packet_hash)

        # 4. Deterministic measurement, only now.
        try:
            meas = measurement.measure(self.idx, target, ir)
        except measurement.MeasurementFailed as e:
            return self._record(prop, target,
                                validation.ValidationResult(
                                    ST.MEASUREMENT_FAILED, str(e), raw_n=vr.raw_n,
                                    effective_n=vr.effective_n, coverage=vr.coverage),
                                ir=ir, packet_hash=packet_hash)

        return self._record(prop, target, vr, ir=ir, meas=meas, packet_hash=packet_hash)
