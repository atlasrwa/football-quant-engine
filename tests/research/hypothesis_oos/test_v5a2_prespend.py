"""V5A.2 pre-spend regression suite (task S27). ZERO SPEND -- nothing here calls a network.

Every test is named for the defect or invariant it protects. The four defects V5A.1's live
run exposed each have a test that FAILS against the V5A.1 apparatus and passes here, so the
suite is a regression suite in the literal sense rather than a restatement of the design.
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/research/hypothesis_engine")

from src.research.hypothesis_engine import firewall_v3, firewall_v4, lifecycle
from src.research.hypothesis_engine import schema as schema_v1, schema_v2, schema_v3
from src.research.hypothesis_engine import validator_v4 as V4
from src.research.hypothesis_oos import v5a1_evaluator as EV1
from src.research.hypothesis_oos import v5a1_evidence as E
from src.research.hypothesis_oos import v5a2_admissibility as ADM
from src.research.hypothesis_oos import v5a2_contract as C
from src.research.hypothesis_oos import v5a2_evaluator as EV
from src.research.hypothesis_oos import v5a2_ontology as O
from src.research.hypothesis_oos import v5a2_packet as P2
from src.research.hypothesis_oos import v5a2_prompt as PR
from src.research.hypothesis_oos import v5a2_transport as T
from src.research.hypothesis_oos import v5a2_translate as TR

V5A2_OUT = "/home/ubuntu/research/hypothesis_oos/out/v5a2"
V5A1_OUT = "/home/ubuntu/research/hypothesis_oos/out/v5a1"


@pytest.fixture(scope="module")
def packets():
    return {arm: json.load(open(f"{V5A2_OUT}/packets_{arm}.json"))
            for arm in ("base", "research")}


@pytest.fixture(scope="module")
def one(packets):
    fid = sorted(packets["research"])[0]
    return packets["base"][fid], packets["research"][fid]


@pytest.fixture(scope="module")
def battery():
    mod = importlib.import_module("_v5a2_surface_battery")
    rep = mod.run(limit_fixtures=1)
    rep["coverage"] = mod.coverage(rep["results"])
    return rep


def _hyp(packet, **kw):
    ids = sorted(E.resolve_evidence_ids(packet))
    ref = next((i for i in ids if i.startswith("SUMMARY:HOME")), ids[0])
    h = {"hypothesis_id": "H1", "research_family": "ATTACK_VOLUME", "subject": "HOME_TEAM",
         "question": "Does the subject's shot volume differ from its overall prior "
                     "baseline in the cohort this hypothesis describes?",
         "target_metrics": ["total_shots"], "side": "FOR", "window": "ALL_PRIOR",
         "conditions": [], "comparison": "SUBJECT_OVERALL_BASELINE",
         "evidence_refs": [ref], "candidate_confounders": [],
         "required_capabilities": [], "sufficiency": "SUFFICIENT", "priority": "MEDIUM"}
    h.update(kw)
    return h


def _run(packet, h):
    return V4.validate({"fixture_id": packet["fixture_id"],
                        "packet_hash": packet["packet_hash"], "hypotheses": [h]},
                       packet=packet, expected_packet_hash=packet["packet_hash"],
                       expected_fixture_id=packet["fixture_id"])


# ========================================================================================
# S3 / S4 -- one authoritative ontology
# ========================================================================================
def test_schema_enums_are_the_ontology():
    """The schema must PROJECT the ontology, not restate it. Identity, not equality."""
    item = schema_v3.build_schema()["properties"]["hypotheses"]["items"]["properties"]
    assert item["conditions"]["items"]["properties"]["dimension"]["enum"] == \
        O.condition_dimension_terms()
    assert item["required_capabilities"]["items"]["enum"] == O.capability_terms()


def test_condition_and_capability_enums_share_one_namespace():
    """THE D1 TEST. Under schema_v2 these were disjoint vocabularies."""
    item = schema_v3.build_schema()["properties"]["hypotheses"]["items"]["properties"]
    dims = set(item["conditions"]["items"]["properties"]["dimension"]["enum"])
    caps = set(item["required_capabilities"]["items"]["enum"])
    assert dims <= caps, f"conditionable terms missing from capability enum: {dims - caps}"

    v2item = schema_v2.build_schema()["properties"]["hypotheses"]["items"]["properties"]
    v2dims = set(v2item["conditions"]["items"]["properties"]["dimension"]["enum"])
    v2caps = set(v2item["required_capabilities"]["items"]["enum"])
    assert not v2dims <= v2caps, ("schema_v2 is supposed to exhibit the D1 defect; if it "
                                  "no longer does, a frozen module was edited")


def test_availability_map_declares_every_model_visible_term(packets):
    for arm in ("base", "research"):
        for fid, pk in packets[arm].items():
            declared = sorted(ADM.exposure_states(pk))
            assert declared == O.all_terms(), f"{arm}/{fid} declares {declared}"


def test_every_condition_term_round_trips():
    for term in O.condition_dimension_terms():
        assert TR.round_trip_dimension(term), term


def test_no_two_terms_share_an_internal_dimension():
    """`from_internal_dimension` is only unambiguous while this holds."""
    seen = {}
    for term in O.condition_dimension_terms():
        internal = O.to_internal_dimension(term)
        assert internal not in seen, f"{term} and {seen.get(internal)} both -> {internal}"
        seen[internal] = term


def test_every_capability_term_translates_or_is_declared_dropped():
    from src.research.hypothesis_engine import capability
    for term in O.capability_terms():
        internal = O.to_internal_context_source(term)
        if internal is None:
            continue           # honest drop, recorded by the translation report
        assert internal in capability.CONTEXT_SOURCES, (term, internal)


def test_d1_regression_advertised_capability_term_is_accepted(one):
    """The EXACT response that killed V5A.1: condition on a term, declare needing it."""
    _, research = one
    ids = sorted(E.resolve_evidence_ids(research))
    prof = next(i for i in ids if i.startswith("PROFILE:HOME:"))
    h = _hyp(research,
             conditions=[{"dimension": "opponent_profile", "value": "HIGH",
                          "axis": "shots_on_target_against"}],
             required_capabilities=["opponent_profile"], evidence_refs=[prof])
    res = _run(research, h)
    assert res.accepted and res.verdicts[0].accepted, res.verdicts[0].reasons
    assert res.accepted_hypotheses[0]["required_capabilities"] == ["competition"]


def test_internal_namespace_is_not_model_visible(one):
    """A model writing the ENGINE's word must be rejected, not silently accepted."""
    _, research = one
    for leaked in ("venue", "historical_formation", "lineup_composition", "competition"):
        if leaked in O.capability_terms():
            continue          # `competition` is a term in BOTH namespaces; not a leak
        res = _run(research, _hyp(research, required_capabilities=[leaked]))
        assert res.failure == lifecycle.SCHEMA_INVALID, leaked
        assert res.failure_class == "MODEL_SCHEMA_INVALID", leaked


def test_retired_bare_venue_fails_closed_with_guidance(one):
    """`venue` is deliberately not a term; the failure must name both replacements."""
    _, research = one
    _, rep = C.canonicalize_payload(
        {"hypotheses": [_hyp(research,
                             conditions=[{"dimension": "venue", "value": "HOME"}])]})
    detail = json.dumps(rep.to_dict())
    assert "UNKNOWN_DIMENSION" in detail
    assert O.HISTORICAL_VENUE_CONDITIONING in detail
    assert O.TARGET_FIXTURE_VENUE_CONTEXT in detail


# ========================================================================================
# S5 -- the abstention contract (D2)
# ========================================================================================
def test_abstention_may_cite_valid_evidence(one):
    """THE D2 TEST. validator_v3 rejected exactly this and no prompt said so."""
    _, research = one
    res = _run(research, _hyp(research, sufficiency="INSUFFICIENT_EVIDENCE"))
    assert res.verdicts[0].accepted, res.verdicts[0].reasons


def test_abstention_without_refs_is_accepted(one):
    _, research = one
    res = _run(research, _hyp(research, sufficiency="INSUFFICIENT_EVIDENCE",
                              evidence_refs=[]))
    assert res.verdicts[0].accepted


def test_abstention_with_fabricated_refs_is_still_rejected(one):
    """Permissiveness on abstention must not become permissiveness on fabrication."""
    _, research = one
    res = _run(research, _hyp(research, sufficiency="INSUFFICIENT_EVIDENCE",
                              evidence_refs=["MATCH:HOME:M99:goals_for"]))
    assert not res.verdicts[0].accepted
    assert res.verdicts[0].failure == lifecycle.INSUFFICIENT_EVIDENCE


def test_sufficient_without_refs_is_rejected(one):
    _, research = one
    res = _run(research, _hyp(research, evidence_refs=[]))
    assert not res.verdicts[0].accepted


def test_abstention_contract_is_stated_in_the_prompt():
    """A rule the model is judged against must be a rule the model was told."""
    assert "MAY cite the evidence" in PR.SYSTEM_PROMPT


# ========================================================================================
# S6 -- the venue distinction (D3 preserved, made measurable)
# ========================================================================================
def test_target_fixture_venue_context_is_exposed_in_both_arms(packets):
    for arm in ("base", "research"):
        for fid, pk in packets[arm].items():
            assert ADM.is_exposed(pk, O.TARGET_FIXTURE_VENUE_CONTEXT), f"{arm}/{fid}"


def test_historical_venue_conditioning_is_withheld_in_the_base_arm(packets):
    for fid, pk in packets["base"].items():
        assert not ADM.is_exposed(pk, O.HISTORICAL_VENUE_CONDITIONING), fid
    for fid, pk in packets["research"].items():
        assert ADM.is_exposed(pk, O.HISTORICAL_VENUE_CONDITIONING), fid


def test_d3_preserved_venue_conditioning_still_rejected_in_base_arm(one):
    """Task S6 says PRESERVE the rejection. It is now a measurement, not an artefact."""
    base, _ = one
    res = _run(base, _hyp(base, conditions=[
        {"dimension": O.HISTORICAL_VENUE_CONDITIONING, "value": "HOME"}]))
    assert not res.verdicts[0].accepted
    assert any("availability map" in r or "NOT_EXPOSED" in r
               for r in res.verdicts[0].reasons)


def test_base_arm_advertises_no_conditionable_terms(packets):
    """A summary-only packet supports no cohort split at all. V5A.1 claimed `competition`."""
    for fid, pk in packets["base"].items():
        assert ADM.packet_capability_summary(pk)["conditionable_terms"] == [], fid


def test_base_arm_competition_conditioning_is_refused(one):
    """The latent defect V5A.1 carried: competition admissible against a packet with no
    competition data anywhere."""
    base, _ = one
    res = _run(base, _hyp(base, conditions=[{"dimension": "competition",
                                             "value": "SAME"}]))
    assert not res.verdicts[0].accepted


# ========================================================================================
# S7 / S9 / S10 -- the generated surface battery
# ========================================================================================
def test_advertised_term_is_never_schema_invalid(battery):
    """THE HARD RULE. A structurally correct use of an advertised term is never malformed."""
    bad = [v for v in battery["violations"]
           if v["rule"] == "ADVERTISED_TERM_SCHEMA_INVALID"]
    assert not bad, bad[:5]


def test_no_infrastructure_contract_failure_anywhere(battery):
    bad = [v for v in battery["violations"]
           if v["rule"] == "INFRASTRUCTURE_CONTRACT_FAILURE"]
    assert not bad, bad[:5]


def test_model_visible_enum_coverage_is_100_percent(battery):
    cov = battery["coverage"]
    assert cov["model_visible_enum_coverage"] == 1.0, {
        k: v["uncovered"] for k, v in cov["per_enum"].items() if v["uncovered"]}


def test_every_negative_case_is_rejected(battery):
    bad = [v for v in battery["violations"] if v["rule"] == "NEGATIVE_CASE_ACCEPTED"]
    assert not bad, bad[:5]


def test_abstention_contract_matches_the_stated_cells(battery):
    bad = [v for v in battery["violations"]
           if v["rule"] == "ABSTENTION_CONTRACT_MISMATCH"]
    assert not bad, bad[:5]


def test_surface_battery_is_not_trivially_small(battery):
    """A battery that generates nothing passes every rule vacuously."""
    assert battery["n_cases"] >= 300, battery["n_cases"]


# ========================================================================================
# S16 -- transport preflight (D4)
# ========================================================================================
def test_transport_preflight_rejects_client_without_converse():
    """THE D4 TEST. Asserts the CHECK works without needing boto3 1.34.46 installed."""
    class OldStyleClient:
        def invoke_model(self, **kw):
            raise AssertionError("must never be reached")

    with pytest.raises(T.TransportPreflightFailure) as exc:
        T.preflight(OldStyleClient())
    assert "converse" in str(exc.value)


def test_transport_preflight_accepts_converse_capable_client():
    class NewClient:
        def converse(self, **kw):
            return {}

    rep = T.preflight(NewClient())
    assert rep["ok"] and rep["has_converse"]
    assert rep["python_executable"] and rep["boto3_version"]


def test_transport_accounting_never_charges_a_failed_call():
    acct = T.TransportAccounting(0.003, 0.015, 7.6947)
    acct.record_transport_failure(1, "AttributeError: no attribute 'converse'")
    acct.record_transport_failure(2, "AttributeError")
    assert acct.spend_usd == 0.0 and acct.n_charged == 0
    assert acct.n_consecutive_transport_failures == 2
    acct.record_call(3, 1000, 1000)
    assert acct.n_consecutive_transport_failures == 0
    assert acct.spend_usd == pytest.approx(0.018)


# ========================================================================================
# S13 / S14 / S15 -- evaluator, evaluability, stop rules
# ========================================================================================
def test_evaluator_thresholds_are_inherited_unchanged():
    """Task S14: no threshold may move in a way that could rescue V5A.1."""
    assert EV.DISCIPLINE_TOLERANCE == EV1.DISCIPLINE_TOLERANCE
    assert EV.MIN_SELF_NOISE_FLOOR == EV1.MIN_SELF_NOISE_FLOOR
    assert EV.PRIMARY_METRIC == EV1.PRIMARY_METRIC


def test_v5a1_run_would_be_non_evaluable():
    """The evaluability gate must describe V5A.1 honestly, not retroactively rescue it."""
    r = EV.evaluability(0, 1, 0, 0, 0)
    assert r["scientific_status"] == "NON_EVALUABLE"
    assert len(r["reasons"]) >= 3


def test_stop_rule_separates_model_from_infrastructure():
    """V5A.1's stop fired on 2 INFRASTRUCTURE failures and reported a MODEL rate."""
    fired = EV.classify_stop(6, 0, 2, 0, 0.9084, 7.6947)
    assert [f["rule"] for f in fired] == ["V5A2_STOP_INFRASTRUCTURE_CONTRACT_FAILURE"]
    assert fired[0]["class"] == "APPARATUS"

    model = EV.classify_stop(10, 4, 0, 0, 0.0, 7.6947)
    assert [f["rule"] for f in model] == ["V5A2_STOP_MODEL_SCHEMA_INVALID_RATE"]
    assert model[0]["class"] == "MODEL"


def test_model_schema_invalid_rate_cannot_fire_below_minimum_calls():
    assert EV.classify_stop(2, 1, 0, 0, 0.0, 7.6947) == []


def test_no_scientific_verdict_is_issued_when_non_evaluable():
    r = EV.final_verdict("STOPPED", EV.evaluability(0, 1, 0, 0, 0), [], 0.5,
                         {"compilability_delta": 0.0, "firewall_clean_delta": 0.0,
                          "fabricated_evidence_delta": 0.0,
                          "unsupported_dimension_delta": 0.0})
    assert r["scientific_verdict"] is None
    assert r["scientific_status"] == "NON_EVALUABLE"
    assert r["execution_status"] == "STOPPED"


def test_evaluator_availability_dimensions_use_ontology_terms(one):
    """V5A.1's keys would silently score every dimension as zero against a V5A.2 packet."""
    _, research = one
    states = ADM.exposure_states(research)
    for term in EV.AVAILABILITY_DIMENSIONS.values():
        assert term in states, term


# ========================================================================================
# S26 / S25 / S2 -- isolation, PIT safety, evidence preservation
# ========================================================================================
def test_evidence_is_byte_identical_to_v5a1():
    a = json.load(open(f"{V5A2_OUT}/evidence_identity_audit.json"))
    assert a["n_evidence_differences"] == 0, a["differences"][:3]


def test_arms_are_isolated_to_evidence_representation():
    a = json.load(open(f"{V5A2_OUT}/arm_isolation_audit.json"))
    assert a["n_identity_leaks"] == 0
    assert a["treatment_labels_found_in_packets"] == []


def test_blinding_check_discriminates_words_from_substrings():
    """The corrected check: `controlled` is not the treatment label `control`."""
    assert PR.blinding_violations("the cohort is not a controlled comparison") == []
    assert "control" in PR.blinding_violations("this is the control arm")


def test_no_pit_leakage():
    a = json.load(open(f"{V5A2_OUT}/pit_audit.json"))
    assert a["n_problems"] == 0, a["problems"][:3]


def test_prompt_carries_no_priming_or_treatment_label():
    sp = PR.SYSTEM_PROMPT
    assert PR.blinding_violations(sp) == []
    leaked = [p for p in PR.PRIMING_PHRASES
              if p.lower() in sp.lower() and p not in PR.PROHIBITION_ONLY_TERMS]
    assert leaked == []


# ========================================================================================
# Frozen-module protection and firewall superset
# ========================================================================================
def test_frozen_schemas_are_unedited():
    """V2/V3/V5A/V5A.1 preregistrations hash these; they must not move."""
    assert schema_v1.SCHEMA_VERSION == "hypothesis_set_schema_v1"
    assert schema_v2.SCHEMA_VERSION == "hypothesis_set_schema_v2"
    assert schema_v2.schema_content_hash() != schema_v3.schema_content_hash()


#: A question corpus wide enough for the subset claim to mean something: legitimate
#: research questions (where a false positive would be the damage), the phrasings the
#: frozen patterns already catch, and the phrasings D5 is about.
_QUESTION_CORPUS = (
    "Does HOME_TEAM generate more shots at home than in its overall prior baseline?",
    "Does AWAY_TEAM concede more corners against back-three opponents?",
    "Does HOME_TEAM's shot volume over its five most recent matches differ from its "
    "full-history baseline?",
    "Is HOME_TEAM's share of shots taken inside the box higher against HIGH-band "
    "opponents on shots on target conceded?",
    "Does the subject's yellow-card count vary with the opponent's recorded formation "
    "family?",
    "Whether the opponent's announced formation matters cannot be assessed from this "
    "packet.",
    "Does HOME_TEAM take 3 or more corners per match more often at home?",
    "Does the back four concede more than the back three?",
    "Is possession for HOME_TEAM above 55% in prior home matches?",
    "There is a 0.62 probability the subject exceeds its baseline shot volume.",
    "The likelihood the subject wins is around 0.55.",
    "I expect about 4.5 shots on target for HOME_TEAM.",
    "Back the over 2.5 in this fixture.",
    "Fair odds of 1.85 imply an edge here.",
    "The probability of a home win is 0.61.",
    "HOME_TEAM has a HIGH advantage over AWAY_TEAM.",
)


def _payload(question):
    return {"fixture_id": "f", "packet_hash": "0" * 64,
            "hypotheses": [{"hypothesis_id": "H1", "question": question,
                            "evidence_refs": []}]}


def test_firewall_v4_is_a_strict_superset_of_v3():
    """Every v3 finding must survive in v4, on every question in the corpus.

    The earlier form of this test asserted equality on one benign payload, which proves
    only "no false positive here" -- it could not have caught v4 dropping a v3 finding.
    """
    strictly_more = 0
    for q in _QUESTION_CORPUS:
        v3 = {(f.layer, f.kind, f.path) for f in firewall_v3.scan(_payload(q),
                                                                  packet=None)}
        v4 = {(f.layer, f.kind, f.path) for f in firewall_v4.scan(_payload(q))}
        assert v3 <= v4, f"v4 DROPPED a v3 finding on {q!r}: {v3 - v4}"
        if v4 > v3:
            strictly_more += 1
    assert strictly_more >= 1, "v4 adds nothing anywhere; D5 would be unclosed"


def test_firewall_v4_adds_no_new_flags_on_legitimate_questions():
    """The cost of tightening is false positives; bound it against v3, not absolutely.

    Some of these questions are ALREADY flagged by the frozen v3 patterns -- "above 55%"
    hits the percentage rule, which is v3 behaviour this iteration does not touch. What
    must be true is that v4 adds nothing NEW on a legitimate research question.
    """
    legitimate = _QUESTION_CORPUS[:9]
    added = {}
    for q in legitimate:
        v3 = {(f.layer, f.kind, f.path) for f in firewall_v3.scan(_payload(q),
                                                                  packet=None)}
        v4 = {(f.layer, f.kind, f.path) for f in firewall_v4.scan(_payload(q))}
        if v4 - v3:
            added[q] = sorted(v4 - v3)
    assert added == {}, added


def test_d5_numeric_probability_claim_in_prose_is_blocked():
    """Found by the generated battery; the frozen patterns miss this phrasing."""
    q = ("There is a 0.62 probability the subject exceeds its baseline shot volume "
         "in the upcoming fixture.")
    payload = {"fixture_id": "f", "packet_hash": "0" * 64,
               "hypotheses": [{"hypothesis_id": "H1", "question": q,
                               "evidence_refs": []}]}
    assert firewall_v3.blocking(firewall_v3.scan(payload, packet=None)) == [], (
        "firewall_v3 is expected to MISS this; if it no longer does, a frozen module "
        "was edited")
    assert firewall_v4.blocking(firewall_v4.scan(payload)), "firewall_v4 must catch it"


# ========================================================================================
# S24 -- byte reproducibility across interpreter hash seeds
# ========================================================================================
def test_frozen_artifacts_agree_across_seeds():
    """All four seeds must agree with each other AND with the on-disk frozen packet."""
    script = (
        "import sys,json,hashlib;"
        "sys.path.insert(0,'/home/ubuntu/src');sys.path.insert(0,'/home/ubuntu');"
        "from src.research.hypothesis_oos import v5a2_ontology as O,v5a2_packet as P2,"
        "v5a2_evaluator as EV;"
        "from src.research.hypothesis_engine import schema_v3 as S3;"
        "pk=json.load(open('/home/ubuntu/research/hypothesis_oos/out/v5a1/"
        "packets_research.json'))['mt_010243515'];"
        "up=P2.upgrade_packet(pk);"
        "h=lambda o:hashlib.sha256(json.dumps(o,sort_keys=True,default=str)"
        ".encode()).hexdigest();"
        "print(json.dumps([up['packet_hash'],S3.schema_content_hash(),"
        "h(O.ontology_snapshot()),h(EV.version_stamp())]))")
    seen = set()
    for seed in ("1", "2", "3", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        out = subprocess.run([sys.executable, "-c", script], env=env,
                             capture_output=True, text=True, timeout=300)
        assert out.returncode == 0, out.stderr[-2000:]
        seen.add(out.stdout.strip().splitlines()[-1])
    assert len(seen) == 1, f"artifacts vary with PYTHONHASHSEED: {seen}"

    frozen = json.load(open(f"{V5A2_OUT}/packets_research.json"))["mt_010243515"]
    assert json.loads(list(seen)[0])[0] == frozen["packet_hash"]
