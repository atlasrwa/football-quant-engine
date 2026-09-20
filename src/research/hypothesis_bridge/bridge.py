"""The bridge: packet -> proposal -> canonical IR -> validation -> measurement -> shadow.

Deterministic and offline. It makes NO model call: the LLM's only role is upstream, producing
the structured proposal. `run_proposal` never invokes a provider, a model or the network, and
the rehearsal harness relies on that.
"""
from __future__ import annotations

from typing import Any, Optional

from src.research.matchup.corpus import MatchRecord
from src.research.llm_matchup import cohorts as CH
from src.research.reconciliation.policy import ReconciliationPolicy
from src.research.hypothesis_bridge import (canonical, firewall, measurement,
                                            packet_binding as PB, proposal as P, registry,
                                            shadow, status as ST, validation)


class BridgeContext:
    """Holds the corpus-derived index once; runs many proposals against it.

    `provider_policy` is FROZEN per context, never inferred per proposal. It defaults to the
    policy that describes this corpus (`THESTATSAPI_ONLY`) and is checked against the corpus's
    traced lineage at construction, so a context cannot be built that would label
    TheStatsAPI-derived rows with FootyStats provenance.
    """

    def __init__(self, recs: list[MatchRecord], *,
                 producer_commit: Optional[str] = None,
                 provider_policy: ReconciliationPolicy = registry.FROZEN_REHEARSAL_POLICY,
                 corpus_provider_lineage: str = registry.CORPUS_PROVIDER_LINEAGE):
        self.recs = recs
        self.idx = CH.HistoryIndex(recs)
        self.by_fixture = {r.fixture_id: r for r in recs}
        self.producer_commit = producer_commit or shadow.producer_code_commit()
        self.provider_policy = provider_policy
        # Raises on a policy the bridge does not implement -- no silent fallback, no blend.
        self.measurement_provider = registry.resolve_measurement_provider(provider_policy)
        if self.measurement_provider != corpus_provider_lineage:
            raise registry.UnknownProvider(
                f"policy_resolves_to_{self.measurement_provider!r} but this corpus is loaded "
                f"from {corpus_provider_lineage!r}; measuring it under another provider's "
                f"capability would fabricate provenance")

    def _record(self, prop, target, vr, ir=None, meas=None, packet_identity=None,
                vintage=None, capability=None):
        return shadow.build_record(
            proposal=prop, target=target, packet_identity=packet_identity, validation=vr,
            ir=ir, measurement=meas, data_vintage=vintage,
            producer_commit=self.producer_commit,
            measurement_provider=self.measurement_provider,
            provider_policy=self.provider_policy, capability=capability)

    @staticmethod
    def _raw_fixture_id(raw: Any) -> Optional[str]:
        """The fixture id off an UNPARSED payload, or None when it has none to read.

        Deliberately tolerant: the payload may be malformed in every other respect and this
        still has to work, because a forbidden or broken response must not be allowed to bind
        to a packet for a different fixture. A non-mapping payload simply has no id, which is
        not a binding failure -- it is a parse failure, and Stage A leaves it to the parser.
        """
        if not isinstance(raw, dict) or "fixture_id" not in raw:
            return None
        try:
            return str(raw["fixture_id"])
        except Exception:                                # pragma: no cover - defensive
            return None

    @staticmethod
    def _unbound_target(fixture_id: str) -> MatchRecord:
        """A placeholder target for a record that never established packet binding."""
        return MatchRecord(fixture_id=fixture_id, competition="UNKNOWN",
                           competition_id="UNKNOWN", season_id="UNKNOWN", kickoff_unix=0,
                           home="?", away="?", home_id="?", away_id="?",
                           base={}, rich={}, extra={})

    def run_proposal(self, raw: dict, *, packet: dict,
                     proposal_source: str = PB.SOURCE_LLM_PROPOSAL) -> dict:
        """Always returns a shadow record. A rejection IS a research result.

        `packet` is REQUIRED and is the actual evidence packet, not a hash string. There is
        no NO_PACKET path: a hypothesis measured without the evidence it claims to be
        grounded in is exactly what this bridge exists to refuse.

        FAILURE PRECEDENCE, decided rather than emergent:

            invalid packet                          -> PACKET_BINDING_FAILED
            valid packet + forbidden field          -> FORBIDDEN_PREDICTION_FIELD, packet kept
            valid packet + malformed proposal       -> AMBIGUOUS_PROPOSAL,         packet kept
            valid packet + valid proposal + bad ref -> PACKET_BINDING_FAILED

        The packet outranks the proposal because it is the INSTRUMENT: a response judged
        against the wrong evidence tells us nothing, whatever else is wrong with it. One
        consequence is deliberate and is pinned by a test: a payload carrying BOTH a forbidden
        field AND a mismatched fixture id reports PACKET_BINDING_FAILED, losing the
        forbidden-field status. The rejection reason names both causes so the signal is not
        lost, but the status reflects the more fundamental fault.
        """
        # 1. STAGE A -- packet envelope. Runs BEFORE parsing, and depends on nothing the
        #    proposal provides, so a malformed response still ends up attributable to the
        #    exact packet it was shown.
        try:
            packet_identity, target = PB.verify_packet_envelope(
                packet, self.by_fixture, raw_fixture_id=self._raw_fixture_id(raw))
        except PB.PacketBindingError as e:
            detail = str(e)
            raw_fid = self._raw_fixture_id(raw)
            # Name a co-occurring forbidden field so the precedence choice above does not
            # silently destroy the "the LLM tried to predict" signal.
            if isinstance(raw, dict):
                hits = firewall.prohibited_fields(raw)
                if hits:
                    detail += f"; ALSO prediction_field:{sorted(hits)[0]}"
            stub = P.HypothesisProposal(
                fixture_id=raw_fid or "UNKNOWN", subject="home_team",
                target_metric="UNKNOWN", perspective="for",
                comparator="team_season_baseline",
                research_reason=(str(raw.get("research_reason", ""))
                                 if isinstance(raw, dict) else ""))
            return self._record(stub, self._unbound_target(stub.fixture_id),
                                validation.ValidationResult(ST.PACKET_BINDING_FAILED, detail))

        # 2. Parse + numerical firewall. The packet is ALREADY verified, so whatever happens
        #    here the record still carries real packet provenance.
        try:
            prop = P.parse_proposal(raw)
        except P.ProposalError as e:
            detail = str(e)
            st = (ST.FORBIDDEN_PREDICTION_FIELD if "prediction_field:" in detail
                  else ST.AMBIGUOUS_PROPOSAL)
            stub = P.HypothesisProposal(
                fixture_id=packet_identity["packet_fixture_id"], subject="home_team",
                target_metric="UNKNOWN", perspective="for",
                comparator="team_season_baseline",
                research_reason=(str(raw.get("research_reason", ""))
                                 if isinstance(raw, dict) else ""))
            return self._record(stub, target, validation.ValidationResult(st, detail),
                                packet_identity=packet_identity)

        # 3. STAGE B -- bind the parsed proposal's evidence_refs into the verified identity.
        try:
            packet_identity = PB.verify_proposal_evidence_refs(
                packet, packet_identity, evidence_refs=prop.evidence_refs,
                proposal_source=proposal_source)
        except PB.PacketBindingError as e:
            return self._record(prop, target,
                                validation.ValidationResult(ST.PACKET_BINDING_FAILED, str(e)),
                                packet_identity=packet_identity)

        # 4. Canonicalization. No fuzzy fallback: unmappable is COMPILER_REFUSED.
        try:
            ir = canonical.canonicalize(prop)
        except canonical.CanonicalizationRefused as e:
            return self._record(prop, target,
                                validation.ValidationResult(ST.COMPILER_REFUSED, str(e)),
                                packet_identity=packet_identity)

        # 5. Provider / PIT / support, under the context's FROZEN provider policy.
        vr = validation.validate(self.idx, target, ir, provider=self.measurement_provider)
        capability = registry.capability_for(self.measurement_provider, ir.metric)
        vintage = measurement.target_bounded_vintage(self.idx, target, ir)
        if not vr.ok:
            return self._record(prop, target, vr, ir=ir, packet_identity=packet_identity,
                                vintage=vintage, capability=capability)

        # 6. Deterministic measurement, only now.
        try:
            meas = measurement.measure(self.idx, target, ir, capability=capability)
        except measurement.MeasurementFailed as e:
            return self._record(prop, target,
                                validation.ValidationResult(
                                    ST.MEASUREMENT_FAILED, str(e), raw_n=vr.raw_n,
                                    effective_n=vr.effective_n, coverage=vr.coverage),
                                ir=ir, packet_identity=packet_identity, vintage=vintage,
                                capability=capability)

        return self._record(prop, target, vr, ir=ir, meas=meas,
                            packet_identity=packet_identity, vintage=vintage,
                            capability=capability)
