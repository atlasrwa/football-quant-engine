"""Mandate §23 -- evidence grounding and the leakage guard.

Grounding is what stops latent football knowledge becoming a scientific claim: a
hypothesis may only rest on evidence that was actually in the packet.

Leakage is what stops the research proposal being contaminated by the future, the market
or the settled result.
"""
from __future__ import annotations

import copy
import sys

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/tests/research/hypothesis_engine")

import pytest

import fixtures as F
from src.research.hypothesis_engine import leakage, lifecycle, validator


@pytest.fixture()
def packet():
    return F.real_identity_packet()


@pytest.fixture()
def response(packet):
    return F.valid_response(packet)


def _validate(resp, packet):
    return validator.validate(resp, packet=packet,
                              expected_packet_hash=packet["packet_hash"],
                              expected_fixture_id=packet["fixture_id"])


# ------------------------------------------------------------------------- grounding
def test_valid_evidence_refs_accepted(packet, response):
    r = _validate(response, packet)
    assert r.accepted and r.n_accepted == len(response["hypotheses"])


def test_fabricated_evidence_ref_rejects_that_hypothesis(packet, response):
    bad = copy.deepcopy(response)
    bad["hypotheses"][0]["evidence_refs"] = ["HOME_ATK_corners_deadbe"]
    r = _validate(bad, packet)
    assert r.accepted, "whole response survives; the hypothesis does not"
    v = next(v for v in r.verdicts if v.hypothesis_id == "H1")
    assert not v.accepted
    assert v.failure == lifecycle.INSUFFICIENT_EVIDENCE
    assert r.n_accepted == len(response["hypotheses"]) - 1


def test_missing_evidence_refs_on_a_sufficient_hypothesis_is_rejected(packet, response):
    bad = copy.deepcopy(response)
    bad["hypotheses"][0]["evidence_refs"] = []
    r = _validate(bad, packet)
    v = next(v for v in r.verdicts if v.hypothesis_id == "H1")
    assert not v.accepted
    assert v.failure == lifecycle.INSUFFICIENT_EVIDENCE


def test_abstention_must_not_cite_evidence(packet):
    """Citing evidence while declaring the evidence insufficient is incoherent."""
    bad = F.abstention_response(packet)
    bad["hypotheses"][0]["evidence_refs"] = [F.evidence_ids(packet)[0]]
    r = _validate(bad, packet)
    v = r.verdicts[0]
    assert not v.accepted
    assert v.failure == lifecycle.INSUFFICIENT_EVIDENCE


def test_partial_fabrication_is_caught_even_when_some_refs_are_real(packet, response):
    bad = copy.deepcopy(response)
    real = F.evidence_ids(packet)[0]
    bad["hypotheses"][0]["evidence_refs"] = [real, "TOTALLY_MADE_UP_ID"]
    r = _validate(bad, packet)
    v = next(v for v in r.verdicts if v.hypothesis_id == "H1")
    assert not v.accepted


# --------------------------------------------------------------------------- leakage
def test_clean_packet_passes_the_guard(packet):
    assert leakage.audit_packet(packet) == []
    leakage.assert_packet_clean(packet)          # must not raise


@pytest.mark.parametrize("key", [
    "odds", "closing_line", "settlement", "p_model", "market_prob", "clv",
    "bookmaker_price", "final_score", "winning_team", "implied_prob",
])
def test_market_or_settlement_field_refuses_transmission(packet, key):
    bad = copy.deepcopy(packet)
    bad[key] = "anything at all"
    findings = leakage.audit_packet(bad)
    assert findings, f"{key!r} was not detected"
    with pytest.raises(leakage.LeakageRejected):
        leakage.assert_packet_clean(bad)


def test_future_evidence_is_refused(packet):
    bad = copy.deepcopy(packet)
    bad["evidence"][0]["max_source_time_unix"] = bad["information_cutoff_unix"] + 3600
    findings = leakage.audit_packet(bad)
    assert any(f.kind == "FUTURE_INFORMATION" for f in findings)


def test_non_pit_safe_evidence_is_refused(packet):
    bad = copy.deepcopy(packet)
    bad["evidence"][0]["temporal_status"] = "POST_KICKOFF"
    assert any(f.kind == "FUTURE_INFORMATION" for f in leakage.audit_packet(bad))


@pytest.mark.parametrize("text", [
    "The closing line moved before kickoff.",
    "The settled result was a home win.",
    "Implied probability from the book was high.",
    "The match ended after ninety minutes.",
])
def test_forbidden_prose_in_packet_is_refused(packet, text):
    bad = copy.deepcopy(packet)
    bad["notes"] = [text]
    assert any(f.kind == "FORBIDDEN_TEXT" for f in leakage.audit_packet(bad))


def test_serialized_request_audit_catches_tokens_reintroduced_at_serialization():
    """Object-level audits miss a token a serializer reintroduces. The literal bytes are
    audited too, exactly as the legacy request auditor did."""
    text = '{"fixture":"x","closing_line":1.85}'
    findings = leakage.audit_serialized_request(text)
    assert findings
    assert any("closing" in f.detail for f in findings)


def test_serialized_audit_is_clean_on_a_real_packet(packet):
    import json
    assert leakage.audit_serialized_request(json.dumps(packet, default=str)) == []
