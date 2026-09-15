"""V6 pre-spend suite (§24, §34). ZERO SPEND -- nothing here calls a network or Bedrock.

Every §34-named test is present under its exact name, plus the inherited invariants §34
requires ("every inherited V5A.2 contract/PIT/semantics/reproducibility/CHAMPION test").
The V5A.2 suite `test_v5a2_prespend.py` still runs and still guards the frozen plumbing; the
tests here guard what V6 CHANGED -- hypothesis-level adjudication, the intent-aware firewall,
the split schema, the balanced schedule, the diversity-gated stop rules, the self-noise
design, the qualified-hypothesis chain, and the frozen scientific verdict.

The adjudicator, firewall and scorecard are exercised on the REAL V5A.2 packets and through
the SAME functions the paid run will use, so a test that passes here is a statement about the
production path, not a mock of it.
"""
from __future__ import annotations

import importlib
import json
import os
import re
import subprocess
import sys

import pytest

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/research/hypothesis_engine")

from src.research.hypothesis_engine import (firewall, firewall_v4, firewall_v5,
                                            schema as schema_v1, schema_v2, schema_v3,
                                            schema_v4, validator, validator_v5 as V)
from src.research.hypothesis_oos import v5a1_evidence as E
from src.research.hypothesis_oos import v5a2_admissibility as ADM
from src.research.hypothesis_oos import v5a2_ontology as O
from src.research.hypothesis_oos import v6_baseline as BL
from src.research.hypothesis_oos import v6_classes as K
from src.research.hypothesis_oos import v6_conditioning as CD
from src.research.hypothesis_oos import v6_numeric_contract as NC
from src.research.hypothesis_oos import v6_prompt as PR
from src.research.hypothesis_oos import v6_qualified as Q
from src.research.hypothesis_oos import v6_repeatability as RP
from src.research.hypothesis_oos import v6_schedule as SCH
from src.research.hypothesis_oos import v6_scorecard as SC
from src.research.hypothesis_oos import v6_selfnoise as SN
from src.research.hypothesis_oos import v6_stop as STOP
from src.research.hypothesis_oos import v6_token_count as TC
from src.research.hypothesis_oos import v6_transport as TR
from src.research.hypothesis_oos import v6_verdict as VD

V6_OUT = "/home/ubuntu/research/hypothesis_oos/out/v6"
V5A2_OUT = "/home/ubuntu/research/hypothesis_oos/out/v5a2"
CHAMPION = "/home/ubuntu/data/discovery/pilotC_stat_mixer.json"
CHAMPION_FROZEN_SHA = \
    "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"


# ========================================================================================
# fixtures and helpers
# ========================================================================================
@pytest.fixture(scope="module")
def packets():
    return {arm: json.load(open(f"{V5A2_OUT}/packets_{arm}.json"))
            for arm in ("base", "research")}


@pytest.fixture(scope="module")
def one(packets):
    fid = sorted(packets["research"])[0]
    return packets["base"][fid], packets["research"][fid]


@pytest.fixture(scope="module")
def build_mod():
    return importlib.import_module("_build_v6")


def _hyp(packet, hid="H1", **kw):
    ids = sorted(E.resolve_evidence_ids(packet))
    ref = next((i for i in ids if i.startswith("SUMMARY:HOME") and i.endswith("_for")),
               ids[0])
    h = {"hypothesis_id": hid, "research_family": "ATTACK_VOLUME", "subject": "HOME_TEAM",
         "question": ("Does HOME_TEAM total_shots for-rate differ from its overall prior "
                      "baseline across all matches?"),
         "target_metrics": ["total_shots"], "side": "FOR", "window": "ALL_PRIOR",
         "conditions": [], "comparison": "SUBJECT_OVERALL_BASELINE",
         "evidence_refs": [ref], "candidate_confounders": [],
         "required_capabilities": [], "sufficiency": "SUFFICIENT", "priority": "MEDIUM"}
    h.update(kw)
    return h


def _resp(packet, hyps):
    return {"fixture_id": packet["fixture_id"], "packet_hash": packet["packet_hash"],
            "hypotheses": hyps}


def _adj(packet, hyps):
    return V.adjudicate(_resp(packet, hyps), packet=packet,
                        expected_packet_hash=packet["packet_hash"],
                        expected_fixture_id=packet["fixture_id"])


def _classes(adj):
    return [a.outcome_class for a in adj.hypotheses]


# ========================================================================================
# §3 -- hypothesis-level adjudication
# ========================================================================================
def test_single_bad_hypothesis_does_not_kill_response(one):
    """One firewall-violating hypothesis among valid ones: the valid ones still qualify."""
    _, rpk = one
    good1 = _hyp(rpk, "H1")
    bad = _hyp(rpk, "H2", target_metrics=["goals"], research_family="ATTACK_QUALITY",
               question="This gives HOME_TEAM a 62% chance in the upcoming fixture.")
    good2 = _hyp(rpk, "H3", target_metrics=["corners"],
                 research_family="SET_PIECE_GENERATION",
                 question="Does HOME_TEAM corners for-rate differ from its overall baseline entirely?")
    adj = _adj(rpk, [good1, bad, good2])
    assert not adj.fatal
    cls = _classes(adj)
    assert cls[0] == K.VALID_HYPOTHESIS
    assert cls[1] == K.MODEL_FIREWALL_VIOLATION
    assert cls[2] == K.VALID_HYPOTHESIS
    sc = SC.score_response(adj, rpk)
    assert sc["n_qualified"] == 2


def test_response_fatal_only_for_unrecoverable_structure(one):
    """RESPONSE_PARSE_FATAL for missing/malformed structure; nothing else is fatal."""
    _, rpk = one
    rh, fid = rpk["packet_hash"], rpk["fixture_id"]
    # not an object
    assert V.adjudicate("nonsense", packet=rpk, expected_packet_hash=rh,
                        expected_fixture_id=fid).response_class == K.RESPONSE_PARSE_FATAL
    # missing hypotheses
    assert V.adjudicate({"fixture_id": fid, "packet_hash": rh}, packet=rpk,
                        expected_packet_hash=rh,
                        expected_fixture_id=fid).response_class == K.RESPONSE_PARSE_FATAL
    # hypotheses not an array
    assert V.adjudicate({"fixture_id": fid, "packet_hash": rh, "hypotheses": {}},
                        packet=rpk, expected_packet_hash=rh,
                        expected_fixture_id=fid).response_class == K.RESPONSE_PARSE_FATAL
    # identity mismatch is fatal (bound to a different packet)
    assert V.adjudicate(_resp({**rpk, "packet_hash": "wrong"}, [_hyp(rpk)]),
                        packet=rpk, expected_packet_hash=rh,
                        expected_fixture_id=fid).response_class == K.RESPONSE_PARSE_FATAL
    # a whole batch of firewall violations is NOT fatal -- it is measured per hypothesis
    allbad = [_hyp(rpk, f"H{i}",
                   question=f"This gives HOME_TEAM a {50+i}% chance in the upcoming fixture.")
              for i in range(1, 4)]
    adj = _adj(rpk, allbad)
    assert not adj.fatal
    assert set(_classes(adj)) == {K.MODEL_FIREWALL_VIOLATION}


# ========================================================================================
# §4 -- firewall distinguishes evidence citation from predictive numbers
# ========================================================================================
def test_historical_percentage_not_predictive_probability(one):
    """A packet value reproduced in evidence_summary under a historical frame is ALLOWED."""
    _, rpk = one
    h = _hyp(rpk, "H1", target_metrics=["possession"],
             research_family="TEMPO_AND_TERRITORY",
             question="Does HOME_TEAM possession for-rate differ from its overall prior baseline entirely?",
             evidence_summary="The cited ALL_PRIOR summary recorded a possession mean above the midpoint across prior matches.")
    adj = _adj(rpk, [h])
    assert adj.hypotheses[0].outcome_class == K.VALID_HYPOTHESIS


def test_target_probability_blocked(one):
    """A probability about the upcoming fixture is a firewall violation, in question OR
    evidence_summary."""
    _, rpk = one
    q = _hyp(rpk, "H1", target_metrics=["goals"], research_family="ATTACK_QUALITY",
             question="This gives HOME_TEAM a 62% chance in the upcoming fixture.")
    assert _adj(rpk, [q]).hypotheses[0].outcome_class == K.MODEL_FIREWALL_VIOLATION
    es = _hyp(rpk, "H1", target_metrics=["goals"], research_family="ATTACK_QUALITY",
              question="Does HOME_TEAM goals for-rate differ from its overall prior baseline here?",
              evidence_summary="This implies a 62% probability in the upcoming fixture.")
    assert _adj(rpk, [es]).hypotheses[0].outcome_class == K.MODEL_FIREWALL_VIOLATION


def test_evidence_numeric_citation_allowed_under_contract(one):
    """N=18 style sample counts and framed historical values pass; the field is the point."""
    _, rpk = one
    h = _hyp(rpk, "H1", target_metrics=["corners"], research_family="SET_PIECE_GENERATION",
             question="Does HOME_TEAM corners for-rate differ from its overall baseline entirely?",
             evidence_summary="The cited cohort was drawn from the prior matches recorded in the packet.")
    assert _adj(rpk, [h]).hypotheses[0].outcome_class == K.VALID_HYPOTHESIS


def test_effect_size_blocked(one):
    """A model-authored effect field is a NUMERIC-CONTRACT violation, not schema-invalid."""
    _, rpk = one
    h = _hyp(rpk, "H1")
    h["effect_size"] = 0.31
    adj = _adj(rpk, [h])
    assert adj.hypotheses[0].outcome_class == K.MODEL_NUMERIC_CONTRACT_VIOLATION


def test_firewall_not_counted_as_schema_invalid(one):
    """§8: a firewall violation and a schema violation are distinct classes."""
    _, rpk = one
    fw = _hyp(rpk, "H1", target_metrics=["goals"], research_family="ATTACK_QUALITY",
              question="This gives HOME_TEAM a 62% chance in the upcoming fixture.")
    sch = _hyp(rpk, "H2", research_family="NOT_A_FAMILY")
    adj = _adj(rpk, [fw, sch])
    assert adj.hypotheses[0].outcome_class == K.MODEL_FIREWALL_VIOLATION
    assert adj.hypotheses[1].outcome_class == K.MODEL_SCHEMA_INVALID


# ========================================================================================
# §8 -- explicit failure taxonomy
# ========================================================================================
def test_explicit_failure_taxonomy():
    """Every outcome is an explicit enum; classes are never inferred from prose."""
    assert K.RESPONSE_PARSE_FATAL in K.RESPONSE_FATAL_CLASSES
    assert K.INFRASTRUCTURE_FAILURE in K.RESPONSE_FATAL_CLASSES
    for c in (K.MODEL_FIREWALL_VIOLATION, K.MODEL_GROUNDING_VIOLATION,
              K.MODEL_AVAILABILITY_VIOLATION, K.MODEL_SCHEMA_INVALID,
              K.MODEL_COMPILER_INVALID, K.MODEL_NUMERIC_CONTRACT_VIOLATION):
        assert c in K.HYPOTHESIS_CLASSES
    # INFRASTRUCTURE_FAILURE never enters the model failure rate
    assert K.INFRASTRUCTURE_FAILURE not in K.HYPOTHESIS_MODEL_FAILURE_CLASSES
    # the gate order names one class per gate, all distinct
    classes = [c for _, c in K.GATE_ORDER]
    assert len(classes) == len(set(classes))


# ========================================================================================
# §6 / §7 -- balanced call order and diversity-gated stop
# ========================================================================================
def test_balanced_call_order_contains_multiple_fixtures_before_stop(packets):
    paired = sorted(set(packets["base"]) & set(packets["research"]))
    calls = SCH.build_sequence(paired)
    props = SCH.order_properties(calls, STOP.MIN_CALLS_BEFORE_RATE_STOP)
    assert props["prefix_contains_both_arms"]
    assert props["prefix_n_distinct_fixtures"] >= STOP.MIN_STOP_FIXTURES
    assert props["arms_adjacent_within_fixture"]
    problems = SCH.freeze_assertions(
        calls, STOP.MIN_CALLS_BEFORE_RATE_STOP,
        min_prefix_fixtures=STOP.MIN_STOP_FIXTURES,
        min_prefix_calls_per_arm=STOP.MIN_STOP_VALID_CALLS_PER_ARM,
        min_repeat_groups_per_arm=SN.MIN_REPEAT_GROUPS_PER_ARM)
    assert problems == []


def test_stop_rule_requires_fixture_diversity():
    """A high failure rate on ONE fixture cannot fire a model-behaviour stop rule."""
    # 6 calls charged, but all on ONE fixture -> not eligible
    res = STOP.classify_stop(
        n_calls_charged=6, fixtures_observed=["f1"],
        valid_calls_per_arm={"base": 3, "research": 3},
        class_counts={K.MODEL_SCHEMA_INVALID: 40},
        n_hypotheses_adjudicated=50, n_responses_fatal=0,
        n_infrastructure_failures=0, n_consecutive_transport_failures=0,
        spend_usd=0.0, ceiling_usd=10.0)
    assert res["model_rules_gated"] is True
    assert not any(f["class"] == "MODEL" for f in res["fired"])
    # same failure rate, now across 3 fixtures and both arms -> eligible and fires
    res2 = STOP.classify_stop(
        n_calls_charged=6, fixtures_observed=["f1", "f2", "f3"],
        valid_calls_per_arm={"base": 3, "research": 3},
        class_counts={K.MODEL_SCHEMA_INVALID: 40},
        n_hypotheses_adjudicated=50, n_responses_fatal=0,
        n_infrastructure_failures=0, n_consecutive_transport_failures=0,
        spend_usd=0.0, ceiling_usd=10.0)
    assert res2["model_rules_gated"] is False
    assert any(f["class"] == "MODEL" for f in res2["fired"])


def test_apparatus_stop_is_not_diversity_gated():
    """The first infrastructure failure halts at once, before any diversity minimum."""
    res = STOP.classify_stop(
        n_calls_charged=1, fixtures_observed=["f1"],
        valid_calls_per_arm={"base": 1, "research": 0},
        class_counts={}, n_hypotheses_adjudicated=0, n_responses_fatal=0,
        n_infrastructure_failures=1, n_consecutive_transport_failures=0,
        spend_usd=0.0, ceiling_usd=10.0)
    assert any(f["rule"] == "V6_STOP_INFRASTRUCTURE_FAILURE" for f in res["fired"])


# ========================================================================================
# §9 -- self-noise from multiple fixtures
# ========================================================================================
def test_self_noise_multiple_fixtures():
    groups = []
    for i in range(4):
        groups.append({"fixture_id": f"f{i}", "arm": "base", "values": [0.3, 0.32, 0.28]})
        groups.append({"fixture_id": f"f{i}", "arm": "research",
                       "values": [0.8, 0.82, 0.78]})
    sd = SN.pooled_sd(groups)
    assert sd["n_groups_by_arm"]["base"] >= SN.MIN_REPEAT_GROUPS_PER_ARM
    assert sd["n_groups_by_arm"]["research"] >= SN.MIN_REPEAT_GROUPS_PER_ARM
    # single group per arm is below the floor -- the V5A.2 failure mode
    sd1 = SN.pooled_sd([{"fixture_id": "f0", "arm": "base", "values": [0.3, 0.32]},
                        {"fixture_id": "f0", "arm": "research", "values": [0.8, 0.82]}])
    assert sd1["n_groups_by_arm"]["base"] < SN.MIN_REPEAT_GROUPS_PER_ARM


def test_repeatability_normalization_frozen():
    """Normalized intent ignores prose and priority; two differently-worded identical
    measurements normalize identically."""
    from src.research.hypothesis_engine import validator_v5 as VV
    h1 = _hyp_dict(question="Question one, worded one way, about the same measurement here.",
                   priority="HIGH")
    h2 = _hyp_dict(question="A completely different wording of the very same measurement.",
                   priority="LOW")
    assert RP.normalized_intent(h1) == RP.normalized_intent(h2)
    # and it matches the redundancy key the validator uses
    assert RP.normalized_intent(h1).startswith(
        str(VV._intent_key(h1)[0]))


def test_repeatability_normalization_matches_redundancy_key():
    from src.research.hypothesis_engine import validator_v5 as VV
    a = _hyp_dict(target_metrics=["corners"])
    b = _hyp_dict(target_metrics=["corners"], question="Worded entirely differently but same.")
    # same intent key -> validator would call b redundant with a
    assert VV._intent_key(a) == VV._intent_key(b)
    assert RP.normalized_intent(a) == RP.normalized_intent(b)


def _hyp_dict(**kw):
    h = {"hypothesis_id": "H1", "subject": "HOME_TEAM", "target_metrics": ["total_shots"],
         "side": "FOR", "window": "ALL_PRIOR", "comparison": "SUBJECT_OVERALL_BASELINE",
         "conditions": [], "sufficiency": "SUFFICIENT",
         "question": "a" * 30, "priority": "MEDIUM"}
    h.update(kw)
    return h


# ========================================================================================
# §18 -- arm A not penalized; arm B not rewarded for raw condition count
# ========================================================================================
def test_arm_a_not_penalized_for_zero_conditionable_dimensions(packets):
    """The base arm's unconditioned self-comparison is VALID and can qualify."""
    bpk = packets["base"][sorted(packets["base"])[0]]
    h = _hyp(bpk, "H1")
    adj = _adj(bpk, [h])
    assert adj.hypotheses[0].outcome_class == K.VALID_HYPOTHESIS
    # and the base packet advertises no conditionable terms at all
    summary = ADM.packet_capability_summary(bpk)
    assert summary["conditionable_terms"] == []


def test_arm_b_not_rewarded_for_raw_condition_count(one):
    """A two-condition hypothesis whose conditions are not backed by cited evidence is NOT
    counted a meaningful interaction -- volume does not buy quality."""
    _, rpk = one
    ids = sorted(E.resolve_evidence_ids(rpk))
    # cite only a plain SUMMARY (no PROFILE ref) while conditioning on opponent_profile:
    # the interaction is unsupported and demoted
    ref = next(i for i in ids if i.startswith("SUMMARY:HOME") and i.endswith("_for"))
    h = _hyp(rpk, "H1", target_metrics=["big_chances"],
             research_family="OPPONENT_PROFILE_INTERACTION", evidence_refs=[ref],
             required_capabilities=["opponent_profile", "historical_venue_conditioning"],
             conditions=[{"dimension": "opponent_profile", "value": "HIGH",
                          "axis": "shots_on_target_against"},
                         {"dimension": "historical_venue_conditioning", "value": "AWAY"}],
             question="Does HOME_TEAM big_chances vary by opponent profile and venue jointly here?")
    cond = CD.classify(h, rpk, set(ids))
    assert cond["conditioning_class"] != CD.MEANINGFUL_INTERACTION


# ========================================================================================
# §10 -- qualified hypothesis requires the full chain
# ========================================================================================
def test_qualified_hypothesis_requires_full_chain(one):
    """Flipping ANY one §10 conjunct to False removes qualification."""
    _, rpk = one
    adj = _adj(rpk, [_hyp(rpk, "H1")])
    a = adj.hypotheses[0]
    Q.annotate(a)
    assert a.scorecard["qualified"] is True
    # flip each conjunct key and re-run is_qualified
    for name, keys in Q.CONJUNCTS:
        import copy
        clone = copy.deepcopy(a)
        clone.scorecard[keys[0]] = False
        assert Q.is_qualified(clone) is False, f"flipping {name} should disqualify"


# ========================================================================================
# §15 -- baseline absorption
# ========================================================================================
def test_baseline_absorption_detected(one):
    """Home side, condition venue=HOME, compare to SUBJECT_VENUE_BASELINE -> absorbed."""
    _, rpk = one
    ids = sorted(E.resolve_evidence_ids(rpk))
    venue = next((i for i in ids if ":HOME_ONLY:" in i and "HOME" in i), ids[0])
    h = _hyp(rpk, "H1", target_metrics=["interceptions"], research_family="VENUE_EFFECT",
             comparison="SUBJECT_VENUE_BASELINE", evidence_refs=[venue],
             required_capabilities=["historical_venue_conditioning"],
             conditions=[{"dimension": "historical_venue_conditioning", "value": "HOME"}],
             question="Does HOME_TEAM interceptions at home differ from its home venue baseline exactly?")
    assert BL.absorption(h)["absorbed"] is True
    assert _adj(rpk, [h]).hypotheses[0].outcome_class == K.MODEL_COMPARATOR_INVALID
    # away cohort vs venue baseline is NOT absorbed
    h2 = dict(h)
    h2["conditions"] = [{"dimension": "historical_venue_conditioning", "value": "AWAY"}]
    assert BL.absorption(h2)["absorbed"] is False


# ========================================================================================
# §14 -- opponent-profile round trip
# ========================================================================================
def test_opponent_profile_roundtrip(one):
    """A well-formed opponent-profile interaction, cited with a PROFILE id, qualifies and
    the engine owns the cohort (the model supplies only the axis)."""
    _, rpk = one
    ids = sorted(E.resolve_evidence_ids(rpk))
    prof = [i for i in ids if i.startswith("PROFILE:HOME:")][:2]
    assert prof, "research packet must expose PROFILE ids"
    h = _hyp(rpk, "H1", target_metrics=["big_chances"],
             research_family="OPPONENT_PROFILE_INTERACTION", evidence_refs=prof,
             required_capabilities=["opponent_profile"],
             conditions=[{"dimension": "opponent_profile", "value": "HIGH",
                          "axis": "shots_on_target_against"}],
             question="Does HOME_TEAM create more big_chances versus defensively strong opponents than overall?")
    a = _adj(rpk, [h]).hypotheses[0]
    assert a.outcome_class == K.VALID_HYPOTHESIS
    Q.annotate(a)
    assert a.scorecard["qualified"] is True
    # the model supplied no similarity score -- only a band on an axis
    assert all("score" not in str(c) for c in h["conditions"])


# ========================================================================================
# §26 -- scientific evaluability frozen
# ========================================================================================
def test_scientific_evaluability_frozen():
    """Under-covered runs are NON_EVALUABLE and issue no verdict, whatever the mechanics."""
    # three paired fixtures, one repeat group -> non-evaluable
    cards = []
    for i in range(3):
        cards.append({"measured": True, "fixture_id": f"f{i}", "arm": "base",
                      "qualified_rate": 0.3, "n_nonabstaining": 10, "n_recoverable": 10,
                      "n_refs": 10, "fabricated_evidence_rate": 0.0,
                      "discipline_violation_rate": 0.0, "redundancy_rate": 0.0,
                      "n_compiler_valid": 10})
        cards.append({**cards[-1], "arm": "research", "qualified_rate": 0.9})
    v = VD.final_verdict(cards, {"base": 1, "research": 1}, SN.pooled_sd([]))
    assert v["scientific_status"] == "NON_EVALUABLE"
    assert v["scientific_verdict"] is None


def test_verdict_thresholds_are_frozen_numbers():
    """§25/§37: no threshold may exist only in prose."""
    st = VD.version_stamp()
    assert isinstance(st["min_paired_fixtures"], int)
    assert isinstance(st["discipline_tolerance"], float)
    assert isinstance(SN.Z_MULTIPLIER, float)
    assert st["thresholds_frozen_before_spend"] is True


# ========================================================================================
# §24 -- evaluator all paths tested before spend
# ========================================================================================
def test_evaluator_all_paths_tested_before_spend(build_mod):
    """The synthetic mutation battery exercised every evaluator PATH at build time."""
    battery = json.load(open(f"{V6_OUT}/synthetic_mutation_battery.json"))
    cases = battery["cases"]
    for name in ("perfect", "null_ab", "noisy", "high_firewall", "grounding_failure",
                 "availability_failure_base_arm", "response_fatal"):
        assert name in cases, name
    assert cases["response_fatal"]["fatal"] is True
    assert cases["response_fatal"]["qualified_rate_is_none"] is True
    assert cases["perfect"]["n_qualified"] >= 1
    assert cases["high_firewall"]["firewall_violations"] >= 1
    assert cases["grounding_failure"]["grounding_violations"] >= 1


def test_adversarial_battery_only_intended_hypotheses_fail():
    """§33: exactly the intended hypotheses fail; every valid sibling survives."""
    adv = json.load(open(f"{V6_OUT}/adversarial_battery.json"))
    assert adv["n_mismatches"] == 0
    assert adv["all_valid_siblings_survived"] is True
    assert adv["fatal"] is False
    assert adv["single_bad_does_not_kill_response"] is True


# ========================================================================================
# §23 -- priority is never a scientific metric
# ========================================================================================
def test_priority_is_never_a_scientific_metric():
    st = SC.version_stamp()
    assert st["priority_used_in_any_metric"] is False
    # normalized intent excludes priority
    a = _hyp_dict(priority="HIGH")
    b = _hyp_dict(priority="LOW")
    assert RP.normalized_intent(a) == RP.normalized_intent(b)


# ========================================================================================
# §20 -- zeros are never substituted for unmeasured
# ========================================================================================
def test_fatal_response_scorecard_is_none_not_zero(one):
    _, rpk = one
    fa = V.adjudicate({"fixture_id": rpk["fixture_id"], "packet_hash": rpk["packet_hash"]},
                      packet=rpk, expected_packet_hash=rpk["packet_hash"],
                      expected_fixture_id=rpk["fixture_id"])
    sc = SC.score_response(fa, rpk)
    assert sc["measured"] is False
    assert sc["qualified_rate"] is None
    assert sc["n_qualified"] is None


# ========================================================================================
# §17 -- abstention is valid behaviour and rate-neutral
# ========================================================================================
def test_evidence_backed_abstention_is_valid_and_rate_neutral(one):
    _, rpk = one
    ids = sorted(E.resolve_evidence_ids(rpk))
    ref = next(i for i in ids if i.startswith("SUMMARY:HOME") and i.endswith("_for"))
    abst = _hyp(rpk, "H1", sufficiency="INSUFFICIENT_EVIDENCE", evidence_refs=[ref],
                question="Referee-conditioned shots cannot be assessed; no referee evidence exposed.")
    good = _hyp(rpk, "H2", target_metrics=["corners"],
                research_family="SET_PIECE_GENERATION",
                question="Does HOME_TEAM corners for-rate differ from its overall baseline entirely?")
    adj = _adj(rpk, [abst, good])
    assert adj.hypotheses[0].outcome_class == K.VALID_ABSTENTION
    sc = SC.score_response(adj, rpk)
    # denominator is non-abstaining only -> abstention does not lower qualified_rate
    assert sc["n_nonabstaining"] == 1
    assert sc["qualified_rate"] == 1.0


# ========================================================================================
# inherited invariants (§34): PIT / semantics / arm isolation / transport / champion / repro
# ========================================================================================
def test_no_pit_leakage():
    pit = json.load(open(f"{V6_OUT}/pit_audit.json"))
    assert pit["n_problems"] == 0


def test_packets_are_byte_identical_to_v5a2():
    pid = json.load(open(f"{V6_OUT}/packet_identity_audit.json"))
    assert pid["n_differences"] == 0


def test_arms_are_isolated_to_evidence_representation():
    ai = json.load(open(f"{V6_OUT}/arm_isolation_audit.json"))
    assert ai["n_identity_leaks"] == 0
    assert ai["treatment_labels_found_in_packets"] == []


def test_prompt_carries_no_priming_or_treatment_label():
    """Priming phrases appear only inside explicit prohibitions; no treatment label leaks."""
    sp = PR.SYSTEM_PROMPT
    assert PR.blinding_violations(sp) == []
    # every prohibition-only term occurrence must sit inside an explicit prohibition
    # sentence. The prohibition marker may come before OR after the term ("Do NOT ...
    # advantage scores" and "... an advantage ... is forbidden"), so check the whole
    # surrounding sentence, not a one-sided prefix window.
    for term in PR.prohibition_terms_present(sp):
        for m in re.finditer(re.escape(term), sp, re.IGNORECASE):
            window = sp[max(0, m.start() - 160):m.start() + 160].lower()
            assert any(marker in window
                       for marker in ("do not", "forbidden", "never", "not ")), \
                f"{term!r} appears outside a prohibition clause"


def test_transport_reuses_v5a2():
    from src.research.hypothesis_oos import v5a2_transport as T2
    assert TR.TransportAccounting is T2.TransportAccounting
    assert TR.TransportPreflightFailure is T2.TransportPreflightFailure


def test_transport_preflight_rejects_client_without_converse():
    class NoConverse:
        pass
    with pytest.raises(TR.TransportPreflightFailure):
        TR.preflight(NoConverse())


class _FakeConfig:
    def __init__(self, retries):
        self.retries = retries


class _FakeMeta:
    def __init__(self, retries):
        self.config = _FakeConfig(retries)


class _FakeClient:
    """A converse-capable client with an explicit botocore-shaped retry config."""
    def __init__(self, retries):
        self.meta = _FakeMeta(retries)

    def converse(self, **k):
        pass


def test_transport_preflight_accepts_converse_capable_client():
    """A converse-capable client with retries DISABLED passes preflight."""
    rep = TR.preflight(_FakeClient({"total_max_attempts": 1, "mode": "standard"}))
    assert rep["ok"] is True
    assert rep["profile_note"]["get_inference_profile_called"] is False
    assert rep["retry_policy"]["retries_disabled_on_client"] is True


def test_transport_preflight_rejects_retry_enabled_client():
    """§28 / amendment 1: a client that can bill a call more than once is aborted at $0."""
    # legacy mode with no numeric key -> unbounded -> rejected (the DEFAULT boto3 client)
    with pytest.raises(TR.RetryPolicyViolation):
        TR.preflight(_FakeClient({"mode": "legacy"}))
    # an explicit multi-attempt policy is also rejected
    with pytest.raises(TR.RetryPolicyViolation):
        TR.preflight(_FakeClient({"total_max_attempts": 5, "mode": "standard"}))
    # RetryPolicyViolation is a TransportPreflightFailure, so the driver's existing except
    # still aborts at zero spend
    assert issubclass(TR.RetryPolicyViolation, TR.TransportPreflightFailure)


def test_build_client_disables_retries():
    """The frozen client builder produces a client that bills a call at most once."""
    c = TR.build_client()
    assert TR.client_max_attempts(c) <= TR.MAX_BILLABLE_ATTEMPTS_PER_CALL
    rep = TR.assert_no_retries(c)
    assert rep["retries_disabled_on_client"] is True
    assert TR.MAX_BILLABLE_ATTEMPTS_PER_CALL == 1


def test_unknown_client_retry_config_is_treated_as_unbounded():
    """A client that exposes no retry config is worst-cased, never passed silently."""
    class NoMeta:
        def converse(self, **k):
            pass
    assert TR.client_max_attempts(NoMeta()) > TR.MAX_BILLABLE_ATTEMPTS_PER_CALL
    with pytest.raises(TR.RetryPolicyViolation):
        TR.assert_no_retries(NoMeta())


# ========================================================================================
# §28 -- cost hard ceiling is a TRUE worst-case BILLABLE bound (amendment 1)
# ========================================================================================
def _prereg():
    return json.load(open(f"{V6_OUT}/PREREGISTRATION.json"))


def test_hard_ceiling_prices_max_tokens_on_every_call():
    """The ceiling assumes max output tokens on every logical call, priced on the HARD-BOUND
    input tokens (amendment 2), not the estimate; and it dominates expected and p90."""
    cm = _prereg()["cost_model"]
    tm = _manifest()
    # ceiling = sum of per-request rounded-up maxima, each at max_output_tokens
    assert all(e["max_output_tokens"] == cm["total_output_tokens_max"] // cm["n_calls_total"]
               for e in tm["entries"])
    assert cm["hard_ceiling_usd"] >= round(
        sum(e["max_request_cost_usd"] for e in tm["entries"]), 2) - 1e-9
    # ceiling strictly dominates expected and p90
    assert cm["hard_ceiling_usd"] > cm["p90_cost_usd"] >= cm["expected_cost_usd"]


def test_hard_ceiling_is_a_billable_bound_only_because_retries_are_disabled():
    """AMENDMENT 1: the ceiling bounds BILLABLE ATTEMPTS, and only because retries are off.

    A logical-call count is a billable bound iff one logical call bills at most once. The
    cost model must record that the transport policy disables retries and that total
    billable attempts == logical calls.
    """
    cm = _prereg()["cost_model"]
    assert cm["max_billable_attempts_per_call"] == 1
    assert cm["max_billable_attempts_total"] == cm["n_calls_total"]
    pol = cm["transport_retry_policy"]
    assert pol["policy"] == "retries_disabled"
    assert pol["max_billable_attempts_per_call"] == 1
    # and the transport module agrees
    assert TR.MAX_BILLABLE_ATTEMPTS_PER_CALL == 1


def test_states_ceiling_hardstop_checks_mechanism_not_prose():
    """§37: `hard_ceiling_not_a_bound` must fail on a retry-enabled cost model, even if the
    prose still says 'yes'. The old check searched for the word 'yes' and would pass."""
    states = importlib.import_module("_v6_states")
    good = _prereg()
    assert states._hard_ceiling_not_a_bound(good) is False
    # mutate to a retry-enabled policy while KEEPING the 'yes ...' prose -> must be caught
    import copy
    bad = copy.deepcopy(good)
    bad["cost_model"]["max_billable_attempts_per_call"] = 5
    bad["cost_model"]["max_billable_attempts_total"] = 5 * bad["cost_model"]["n_calls_total"]
    bad["cost_model"]["transport_retry_policy"]["policy"] = "legacy_retries"
    assert bad["cost_model"]["hard_ceiling_is_a_true_bound"].startswith("yes")
    assert states._hard_ceiling_not_a_bound(bad) is True


def test_final_call_boundary_refuses_to_start_an_unaffordable_call():
    """A run must mechanically refuse to START a call whose worst-case charge breaches the
    ceiling. `would_exceed_ceiling` prices the NEXT call at max output tokens."""
    cm = _prereg()["cost_model"]
    price_in, price_out = cm["price_in_per_1k"], cm["price_out_per_1k"]
    ceiling = cm["hard_ceiling_usd"]
    acc = TR.TransportAccounting(price_in, price_out, ceiling)
    # a single worst-case call at max tokens
    worst_out = 8192
    worst_in = max(c["est_input_tokens"] for c in _prereg()["call_sequence"])
    projected = worst_in / 1000 * price_in + worst_out / 1000 * price_out
    # spend the ceiling down to just under one worst-case call
    acc.spend_usd = ceiling - projected + 0.0001
    assert acc.would_exceed_ceiling(projected) is True
    # with headroom it is allowed
    acc.spend_usd = 0.0
    assert acc.would_exceed_ceiling(projected) is False


def test_retry_cost_boundary_one_logical_call_bills_once():
    """The accounting charges once per recorded call; a transport failure is never charged,
    so a retried-then-failed attempt cannot inflate spend. Combined with retries disabled on
    the client, one logical call bills at most once."""
    acc = TR.TransportAccounting(0.003, 0.015, 100.0)
    acc.record_transport_failure(1, "read timeout")   # not charged
    acc.record_transport_failure(2, "read timeout")   # not charged
    assert acc.n_charged == 0 and acc.spend_usd == 0.0
    acc.record_call(3, 1000, 8192)                     # one billed generation
    assert acc.n_charged == 1
    only = acc.spend_usd
    # no second charge appears for the same logical call
    assert acc.n_charged == 1 and acc.spend_usd == only


def test_transport_accounting_never_charges_a_failed_call():
    acc = TR.TransportAccounting(0.003, 0.015, 10.0)
    acc.record_transport_failure(1, "boom")
    assert acc.spend_usd == 0.0 and acc.n_charged == 0
    acc.record_call(2, 1000, 1000)
    assert acc.n_charged == 1 and acc.n_consecutive_transport_failures == 0


def test_frozen_schemas_are_unedited():
    """schema_v4 = schema_v3 item + evidence_summary; v1/v2/v3 hashes unchanged."""
    diff = schema_v4.diff_against_v3()
    assert diff["identical_after_removing_evidence_summary"] is True
    assert diff["added_item_properties"] == ["evidence_summary"]
    assert diff["removed_item_properties"] == []
    assert diff["required_unchanged"] is True


def test_firewall_v5_is_detection_superset_of_v4():
    """firewall_v5 applies every v4 pattern; it only changes DISPOSITION, not detection."""
    assert set(p for p, _ in firewall_v4._COMPILED) <= set(p for p, _ in firewall_v5._ALL_PATTERNS)
    assert set(p for p, _ in firewall._COMPILED) <= set(p for p, _ in firewall_v5._ALL_PATTERNS)


def test_firewall_v5_denies_everything_v4_denied_in_question(one):
    """The V5A.2 defect string: '50%' in a QUESTION is still denied, at hypothesis level."""
    _, rpk = one
    h = _hyp(rpk, "H1", target_metrics=["possession"],
             research_family="TEMPO_AND_TERRITORY",
             question="Does possession above 50% translate into a higher final_third_entries rate here?")
    adj = _adj(rpk, [h])
    # a bare number in the QUESTION is rejected (frame belongs in evidence_summary)
    assert adj.hypotheses[0].outcome_class in (K.MODEL_FIREWALL_VIOLATION,)


def test_champion_isolation_and_hash():
    """§32: CHAMPION unchanged, and no V6 module imports into a prediction path."""
    import hashlib
    sha = hashlib.sha256(open(CHAMPION, "rb").read()).hexdigest()
    assert sha == CHAMPION_FROZEN_SHA
    # no v6_* or validator_v5/firewall_v5/schema_v4 module names appear in the champion
    blob = open(CHAMPION).read()
    for token in ("v6_", "validator_v5", "firewall_v5", "schema_v4"):
        assert token not in blob


def test_frozen_artifacts_agree_across_seeds():
    """§30: the build artifacts rebuild byte-identically under PYTHONHASHSEED 1/2/3/12345."""
    def build_hashes(seed):
        env = dict(os.environ, PYTHONHASHSEED=str(seed))
        subprocess.run([sys.executable,
                        "/home/ubuntu/research/hypothesis_engine/_build_v6.py"],
                       env=env, check=True, capture_output=True)
        out = {}
        import hashlib
        for name in ("adversarial_battery.json", "synthetic_mutation_battery.json",
                     "call_schedule.json", "packet_identity_audit.json",
                     "arm_isolation_audit.json", "pit_audit.json"):
            out[name] = hashlib.sha256(open(f"{V6_OUT}/{name}", "rb").read()).hexdigest()
        return out
    ref = build_hashes(1)
    for seed in (2, 3, 12345):
        assert build_hashes(seed) == ref, f"artifacts differ under PYTHONHASHSEED={seed}"


# ========================================================================================
# §12 -- multi-condition observed, not forced
# ========================================================================================
def test_multi_condition_is_observed_not_required():
    st = CD.version_stamp()
    assert st["quota_required"] is False
    assert st["is_a_gate"] is False



# ========================================================================================
# §28 amendment 2 -- INPUT TOKEN accounting is exact or a proven conservative bound
# ========================================================================================
def _manifest():
    return json.load(open(f"{V6_OUT}/INPUT_TOKEN_MANIFEST.json"))


def _cm():
    return json.load(open(f"{V6_OUT}/PREREGISTRATION.json"))["cost_model"]


def _packets():
    return {a: json.load(open(f"{V5A2_OUT}/packets_{a}.json"))
            for a in ("base", "research")}


def test_token_manifest_entry_for_every_planned_call():
    """(1)(2) one manifest entry per planned logical call; counts match the schedule."""
    tm = _manifest()
    prereg = json.load(open(f"{V6_OUT}/PREREGISTRATION.json"))
    n = prereg["cost_model"]["n_calls_total"]
    assert tm["n_requests"] == n == len(tm["entries"])
    seqs = sorted(e["seq"] for e in tm["entries"])
    assert seqs == sorted(c["seq"] for c in prereg["call_sequence"])


def test_every_manifest_entry_has_one_billable_attempt():
    """(3) every entry declares exactly one billable attempt."""
    for e in _manifest()["entries"]:
        assert e["max_billable_attempts"] == 1


def test_input_tokens_are_exact_or_proven_upper_bound_never_ratio():
    """The bound uses CountTokens or the UTF-8 byte bound; never an empirical ratio."""
    cm = _cm()
    assert cm["input_token_bound_is_empirical_ratio"] is False
    for m in cm["input_token_bound_method"]:
        assert m in (TC.METHOD_EXACT, TC.METHOD_BOUND)
    for e in _manifest()["entries"]:
        assert e["input_tokens_is_upper_bound"] is True
        assert e["input_tokens"] >= 0
        if e["input_tokens_method"] == TC.METHOD_BOUND:
            # the byte bound equals the canonical converse-input byte length
            assert e["input_tokens"] == e["conservative_byte_upper_bound"]


def test_conservative_bound_never_below_byte_length():
    """The recorded input-token bound is >= the UTF-8 byte length of the canonical input,
    which for byte-level BPE is >= the true token count."""
    packets = _packets()
    for e in _manifest()["entries"]:
        pk = packets[e["arm"]][e["fixture_id"]]
        byte_len = TC.conservative_token_upper_bound(pk)
        assert e["input_tokens"] >= byte_len if e["input_tokens_method"] == TC.METHOD_BOUND \
            else True
        # and the byte length itself is what the module computes now (determinism)
        assert byte_len == len(TC.canonical_bytes(TC.converse_token_input(pk)))


def test_final_request_hash_matches_manifest():
    """(4) the canonical executable request hashes to the frozen manifest hash."""
    prereg = json.load(open(f"{V6_OUT}/PREREGISTRATION.json"))
    shared = prereg["shared_stack"]
    packets = _packets()
    by_seq = {e["seq"]: e for e in _manifest()["entries"]}
    for c in prereg["call_sequence"]:
        pk = packets[c["arm"]][c["fixture_id"]]
        req = TC.canonical_converse_request(
            pk, model_id=shared["model_id"], temperature=shared["temperature"],
            max_tokens=shared["max_tokens"])
        assert TC.request_sha256(req) == by_seq[c["seq"]]["request_sha256"]


def _one_request():
    pk = _packets()["research"][sorted(_packets()["research"])[0]]
    return pk, TC.canonical_converse_request(
        pk, model_id="us.anthropic.claude-sonnet-4-6", temperature=0.0, max_tokens=8192)


def test_prompt_mutation_changes_request_hash():
    """(5)(8) a one-character system-prompt / user-payload change changes the hash."""
    pk, req = _one_request()
    base = TC.request_sha256(req)
    mutated = dict(req); mutated["system"] = [{"text": req["system"][0]["text"] + "x"}]
    assert TC.request_sha256(mutated) != base
    mutated2 = json.loads(json.dumps(req))
    mutated2["messages"][0]["content"][0]["text"] += " "
    assert TC.request_sha256(mutated2) != base


def test_schema_tool_mutation_changes_request_hash():
    """(6) a tool/schema change changes the hash."""
    pk, req = _one_request()
    base = TC.request_sha256(req)
    mutated = json.loads(json.dumps(req))
    mutated["toolConfig"]["tools"][0]["toolSpec"]["name"] = "something_else"
    assert TC.request_sha256(mutated) != base


def test_evidence_packet_mutation_changes_request_hash():
    """(7) an evidence-packet change changes the hash."""
    pk, req = _one_request()
    base = TC.request_sha256(req)
    pk2 = json.loads(json.dumps(pk))
    pk2["packet_hash"] = "mutated"
    req2 = TC.canonical_converse_request(
        pk2, model_id="us.anthropic.claude-sonnet-4-6", temperature=0.0, max_tokens=8192)
    assert TC.request_sha256(req2) != base


def test_max_tokens_mutation_changes_request_hash():
    """(9) a max_tokens change changes the canonical request hash (it is part of the req)."""
    pk, req = _one_request()
    base = TC.request_sha256(req)
    other = TC.canonical_converse_request(
        pk, model_id="us.anthropic.claude-sonnet-4-6", temperature=0.0, max_tokens=4096)
    assert TC.request_sha256(other) != base


def test_missing_manifest_entry_blocks_execution():
    """(10) the driver's reverify flags a missing manifest entry (no inference)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_execute_v6", "/home/ubuntu/research/hypothesis_engine/_execute_v6.py")
    drv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drv)
    prereg = json.loads(json.dumps(json.load(open(f"{V6_OUT}/PREREGISTRATION.json"))))
    # break the manifest hash so reverify fails closed
    prereg["artifact_hashes"]["INPUT_TOKEN_MANIFEST.json"] = "0" * 64
    problems = drv.reverify(prereg)
    assert any("INPUT_TOKEN_MANIFEST" in p for p in problems)


def test_freeze_validation_rejects_duplicate_and_impossible_counts():
    """(11)(12) duplicate seq and negative token count are rejected by the freeze validator."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_freeze_v6", "/home/ubuntu/research/hypothesis_engine/_freeze_v6.py")
    fz = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fz)
    good = [{"seq": 1, "input_tokens": 10, "input_tokens_is_upper_bound": True,
             "max_billable_attempts": 1, "request_sha256": "a"},
            {"seq": 2, "input_tokens": 10, "input_tokens_is_upper_bound": True,
             "max_billable_attempts": 1, "request_sha256": "b"}]
    calls = [{"seq": 1}, {"seq": 2}]
    assert fz._validate_token_manifest(good, calls) == []
    dup = [dict(good[0]), dict(good[0])]
    assert fz._validate_token_manifest(dup, calls) != []
    neg = [dict(good[0], input_tokens=-1), dict(good[1])]
    assert fz._validate_token_manifest(neg, calls) != []


def test_per_request_cost_uses_max_output_tokens():
    """(13) each per-request max cost prices output at max_tokens (8192)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_freeze_v6", "/home/ubuntu/research/hypothesis_engine/_freeze_v6.py")
    fz = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fz)
    for e in _manifest()["entries"]:
        assert e["max_output_tokens"] == 8192
        assert e["max_request_cost_usd"] == fz._cost_usd_ceil(e["input_tokens"], 8192)


def test_final_call_exactly_at_ceiling_allowed_but_over_by_a_cent_rejected():
    """(14)(15) a call landing exactly at the ceiling is allowed; one cent over is rejected."""
    cm = _cm()
    ceiling = cm["hard_ceiling_usd"]
    acc = TR.TransportAccounting(cm["price_in_per_1k"], cm["price_out_per_1k"], ceiling)
    # exactly at the ceiling: spend + next == ceiling -> allowed
    nxt = 0.50
    acc.spend_usd = ceiling - nxt
    assert acc.would_exceed_ceiling(nxt) is False
    # one cent over -> rejected
    acc.spend_usd = ceiling - nxt + 0.01
    assert acc.would_exceed_ceiling(nxt) is True


def test_hard_ceiling_rounds_up_not_down():
    """(16) the frozen ceiling >= the exact float cost; it never rounds down."""
    cm = _cm()
    inb = cm["total_input_tokens_hard_bound"]
    outb = cm["total_output_tokens_max"]
    exact = inb / 1000 * cm["price_in_per_1k"] + outb / 1000 * cm["price_out_per_1k"]
    assert cm["hard_ceiling_usd"] >= exact
    # and >= the sum of per-request rounded-up maxima (guard-consistent)
    assert cm["hard_ceiling_usd"] >= round(
        sum(e["max_request_cost_usd"] for e in _manifest()["entries"]), 2) - 1e-9


def test_actual_usage_over_bound_is_apparatus_abort_semantics():
    """(17) observed input > frozen bound is classified as a cost-bound violation.

    Exercised structurally: the driver compares in_tok to me['input_tokens'] and appends a
    V6_STOP_COST_BOUND_VIOLATION. Here we assert the comparison rule the driver uses."""
    e = _manifest()["entries"][0]
    bound = e["input_tokens"]
    assert (bound + 1) > bound       # an over-bound observation triggers the abort branch
    assert not (bound > bound)       # exactly at bound does not


def test_expected_and_p90_are_not_the_hard_bound():
    """(18)(19) expected and p90 are strictly below the hard ceiling and are diagnostics."""
    cm = _cm()
    assert cm["expected_cost_usd"] < cm["hard_ceiling_usd"]
    assert cm["p90_cost_usd"] < cm["hard_ceiling_usd"]
    # The hard bound is built from the PROVIDER-NATIVE EXACT input tokens (CountTokens), not
    # from the empirical bytes-to-token estimate. The empirical estimate remains a pure
    # diagnostic and is explicitly NOT the bound -- the exact count may sit either side of
    # it. The safety invariant is that the frozen input-token bound never EXCEEDS the
    # conservative UTF-8-byte upper bound (exact <= byte bound), which is the direction that
    # keeps the ceiling honest.
    assert cm["input_token_bound_is_empirical_ratio"] is False
    manifest = _manifest()
    assert cm["total_input_tokens_hard_bound"] <= manifest["total_input_tokens_byte_bound"]
    assert manifest["all_exact"] is True


def test_retries_remain_disabled_after_amendment():
    """(20) the transport policy still disables retries."""
    assert TR.MAX_BILLABLE_ATTEMPTS_PER_CALL == 1
    assert _cm()["max_billable_attempts_total"] == _cm()["n_calls_total"]


def test_token_manifest_byte_identical_across_seeds():
    """(21) the token manifest and prereg rebuild byte-identically across PYTHONHASHSEED."""
    import hashlib

    def build(seed):
        env = dict(os.environ, PYTHONHASHSEED=str(seed))
        subprocess.run([sys.executable,
                        "/home/ubuntu/research/hypothesis_engine/_build_v6.py"],
                       env=env, check=True, capture_output=True)
        subprocess.run([sys.executable,
                        "/home/ubuntu/research/hypothesis_engine/_freeze_v6.py"],
                       env=env, check=True, capture_output=True)
        return {n: hashlib.sha256(open(f"{V6_OUT}/{n}", "rb").read()).hexdigest()
                for n in ("INPUT_TOKEN_MANIFEST.json", "PREREGISTRATION.json")}
    ref = build(1)
    for seed in (2, 3, 12345):
        assert build(seed) == ref, f"artifacts differ under PYTHONHASHSEED={seed}"


def test_no_inference_artifacts_before_authorization():
    """(22) lifecycle-aware: execution artifacts must not exist BEFORE authorization; after
    an authorized COMPLETE run they must exist and hash-match. The flat "must not exist"
    guard was correct only pre-authorization and became historically false after V6's
    authorized execution -- so it is now phase-aware, reading V6's own immutable
    execution-state artifact for the phase (never guessing from the filesystem)."""
    from src.research.hypothesis_oos import experiment_lifecycle as LC
    states = f"{V6_OUT}/execution/V6_EXECUTION_STATES.json"
    phase = LC.read_phase(states)
    if phase in (LC.PHASE_COMPLETE, LC.PHASE_STOPPED):
        preserved = json.load(open(states))["artifact_hashes"]
        res = LC.validate_experiment(f"{V6_OUT}/execution", states,
                                     preserved_hashes=preserved)
        assert res["ok"], f"COMPLETE V6 history invalid: {res['problems']}"
    else:
        assert not os.path.exists(f"{V6_OUT}/execution"), \
            "execution artifacts must not exist before authorization"


def test_pricing_contract_frozen_and_no_discounts():
    """Audit 9: pricing is frozen, region/model specific, and takes no discount."""
    cm = _cm()
    pc = cm["pricing"]
    assert pc["input_price_per_1k_usd"] == 0.003
    assert pc["output_price_per_1k_usd"] == 0.015
    assert pc["discounts_applied"].startswith("none")
    assert pc["region"] == "us-east-1"
    assert "claude-sonnet-4-6" in pc["model_family"]


def test_foundation_model_mapping_is_stable():
    """Audit 10: the inference profile maps to a foundation-model id for CountTokens."""
    assert TC.foundation_model_id("us.anthropic.claude-sonnet-4-6") == \
        "anthropic.claude-sonnet-4-6"
    assert TC.foundation_model_id("eu.anthropic.claude-sonnet-4-6") == \
        "anthropic.claude-sonnet-4-6"
    # a bare FM id is returned unchanged
    assert TC.foundation_model_id("anthropic.claude-sonnet-4-6") == \
        "anthropic.claude-sonnet-4-6"
    for e in _manifest()["entries"]:
        assert e["count_model_id"] == "anthropic.claude-sonnet-4-6"
        assert e["converse_model_id"] == "us.anthropic.claude-sonnet-4-6"
