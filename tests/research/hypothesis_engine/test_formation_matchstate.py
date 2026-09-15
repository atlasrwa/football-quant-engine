"""Mandate §7, §8, §9, §23 -- formation as fixture context, and match-state limits.

The governing correction here: the absence of a formation ANNOUNCEMENT TIMESTAMP restricts
temporal claims only. It must not block historical formation-conditioned analysis, which is
a statement about completed fixtures. Formation coverage is a sample-size question, and the
engine reports it rather than silently excluding formation work.
"""
from __future__ import annotations

import copy
import sys

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/tests/research/hypothesis_engine")

import pytest

import fixtures as F
from src.research.hypothesis_engine import (
    capability, context_packet as CP, lifecycle, query_plan, validator, vocabulary)


@pytest.fixture()
def packet():
    return F.real_identity_packet()


@pytest.fixture()
def response(packet):
    return F.valid_response(packet)


# ------------------------------------------------- formation usable without timestamps
def test_historical_formation_is_a_supported_context_source():
    spec = capability.context_source("historical_formation")
    assert spec.status == capability.SUPPORTED
    assert "no announcement timestamp" in spec.note.lower()
    assert "does NOT restrict use as" in spec.note


def test_formation_conditioned_hypothesis_compiles_without_any_timestamp(packet, response):
    """The headline requirement of §7."""
    h = response["hypotheses"][0]
    assert any(c["dimension"] == "opponent_formation_family" for c in h["conditions"])
    res = query_plan.compile_hypothesis(h, fixture_id=packet["fixture_id"],
                                        cutoff_unix=F.CUTOFF)
    assert all(r.ok for r in res), [r.reasons for r in res if not r.ok]
    assert res[0].plan.conditions[1].dimension == "opponent_formation_family"


def test_temporal_claim_rules_allow_context_and_forbid_only_timing_claims():
    rules = capability.TEMPORAL_CLAIM_RULES
    assert rules["historical_formation_as_fixture_context"].startswith("ALLOWED")
    assert rules["formation_switch_timing"].startswith("FORBIDDEN")
    assert rules["post_switch_rate_change"].startswith("FORBIDDEN")
    assert rules["prematch_formation_availability_time"].startswith("FORBIDDEN")


def test_minute_level_formation_switch_claim_has_no_representable_query():
    """There is deliberately no dimension through which a minute-window claim could be
    expressed, so it cannot be smuggled in as a cohort condition."""
    for name in vocabulary.dimension_names():
        assert "minute" not in name
        assert "switch" not in name
    assert capability.context_source("minute_level_events").status == \
        capability.UNSUPPORTED_CONTEXT_SOURCE


def test_minute_level_capability_request_fails_closed(packet, response):
    bad = copy.deepcopy(response)
    bad["hypotheses"][0]["required_capabilities"] = ["minute_level_events"]
    r = validator.validate(bad, packet=packet,
                           expected_packet_hash=packet["packet_hash"],
                           expected_fixture_id=packet["fixture_id"])
    v = next(v for v in r.verdicts if v.hypothesis_id == "H1")
    assert not v.accepted
    assert v.failure == lifecycle.UNSUPPORTED_CONTEXT_SOURCE


# --------------------------------------------------------------- coverage is reported
def test_formation_coverage_is_reported_not_assumed(packet):
    cov = packet["capability_manifest"]["coverage"]
    for dim in ("own_formation_family", "opponent_formation_family"):
        c = cov[dim]
        assert set(c) == {"candidate_n", "usable_n", "missing_n", "coverage_rate"}
        assert c["candidate_n"] == c["usable_n"] + c["missing_n"]
        assert 0.0 <= c["coverage_rate"] <= 1.0


def test_coverage_helper_computes_missingness_correctly():
    rep = CP.formation_coverage(["4-3-3", None, "3-4-3", None, None])
    assert rep == {"candidate_n": 5, "usable_n": 2, "missing_n": 3, "coverage_rate": 0.4}


def test_sparse_formation_withholds_the_dimension_with_a_stated_reason():
    p = F.sparse_formation_packet()
    dims = p["capability_manifest"]["available_dimensions"]
    assert "own_formation_family" not in dims
    assert "opponent_formation_family" not in dims
    notes = " ".join(p["capability_manifest"]["notes"])
    assert "coverage" in notes
    assert "not a rule against formation analysis" in notes


def test_missing_formation_does_not_invalidate_non_formation_hypotheses():
    """The whole pipeline must still work for a fixture with almost no formation data."""
    p = F.sparse_formation_packet()
    r = F.valid_response(p)
    # Drop the formation-conditioned hypothesis; the rest must survive untouched.
    r["hypotheses"] = [h for h in r["hypotheses"]
                       if not any(c["dimension"].endswith("formation_family")
                                  for c in h["conditions"])]
    v = validator.validate(r, packet=p, expected_packet_hash=p["packet_hash"],
                           expected_fixture_id=p["fixture_id"])
    assert v.accepted and v.n_accepted == len(r["hypotheses"]) >= 3

    manifest = capability.FixtureCapabilityManifest(
        fixture_id=p["fixture_id"],
        available_metrics=tuple(p["capability_manifest"]["available_metrics"]),
        available_dimensions=tuple(p["capability_manifest"]["available_dimensions"]))
    for h in r["hypotheses"]:
        res = query_plan.compile_hypothesis(
            h, fixture_id=p["fixture_id"], cutoff_unix=F.CUTOFF, manifest=manifest)
        assert all(x.ok for x in res), [x.reasons for x in res if not x.ok]


def test_formation_family_reads_structure_not_style():
    assert CP.formation_family("3-4-2-1") == "BACK_THREE"
    assert CP.formation_family("4-2-3-1") == "BACK_FOUR"
    assert CP.formation_family("5-3-2") == "BACK_FIVE"
    assert CP.formation_family(None) == "OTHER"
    assert CP.formation_family("weird") == "OTHER"


# ------------------------------------------------------------------- future formation
def test_expected_formation_is_unsupported_and_says_so():
    spec = capability.context_source("expected_formation")
    assert spec.status == capability.UNSUPPORTED_CONTEXT_SOURCE
    assert "UNKNOWN" in spec.note
    assert "recent formation distribution" in spec.note.lower()


def test_packet_supplies_an_observed_distribution_instead_of_asserting_one(packet):
    dist = packet["formation_distribution"]
    assert set(dist) == {"HOME_TEAM", "AWAY_TEAM"}
    for subj, d in dist.items():
        assert sum(d.values()) > 0
        assert len(d) >= 1, "a distribution, not a single asserted formation"


def test_expected_formation_capability_request_fails_closed(packet, response):
    bad = copy.deepcopy(response)
    bad["hypotheses"][0]["required_capabilities"] = ["expected_formation"]
    r = validator.validate(bad, packet=packet,
                           expected_packet_hash=packet["packet_hash"],
                           expected_fixture_id=packet["fixture_id"])
    assert not next(v for v in r.verdicts if v.hypothesis_id == "H1").accepted


# ------------------------------------------------------------------------ match state
def test_half_time_score_state_is_supported_and_needs_no_event_feed():
    spec = capability.context_source("half_time_score_state")
    assert spec.status == capability.SUPPORTED
    assert "requires no minute-level event feed" in spec.note or \
           "ht_goals" in spec.note


def test_ht_state_hypothesis_compiles_when_half_metrics_exist(packet, response):
    h = next(x for x in response["hypotheses"] if x["hypothesis_id"] == "H3")
    res = query_plan.compile_hypothesis(h, fixture_id=packet["fixture_id"],
                                        cutoff_unix=F.CUTOFF)
    assert all(r.ok for r in res), [r.reasons for r in res if not r.ok]
    plan = res[0].plan
    assert plan.period == "SECOND_HALF"
    assert plan.required_granularity == capability.GRAN_HALF


def test_half_period_query_on_a_full_match_only_metric_fails_closed(packet, response):
    """xg has no half split. Asking a second-half xg question must produce
    UNSUPPORTED_GRANULARITY, not a silently full-match answer."""
    bad = copy.deepcopy(next(x for x in response["hypotheses"]
                             if x["hypothesis_id"] == "H3"))
    bad["target_metrics"] = ["xg"]
    res = query_plan.compile_hypothesis(bad, fixture_id=packet["fixture_id"],
                                        cutoff_unix=F.CUTOFF)
    assert any(r.failure == lifecycle.UNSUPPORTED_GRANULARITY for r in res)


def test_ht_state_withheld_when_the_fixture_has_no_half_level_history():
    p = F.no_half_level_packet()
    dims = p["capability_manifest"]["available_dimensions"]
    assert "half_score_state" not in dims
    assert "period" not in dims
    assert any("half-level" in n for n in p["capability_manifest"]["notes"])


def test_half_metric_inventory_matches_the_verified_half_split_list():
    """Guards against someone adding a half split the raw payload does not have."""
    half_capable = set(capability.metrics_with_granularity(capability.GRAN_HALF))
    # Verified present with first_half/second_half in the raw payload.
    for m in ("corners", "total_shots", "shots_on_target", "possession", "fouls",
              "yellow_cards", "tackles", "touches_in_box", "blocked_shots",
              "accurate_crosses", "clearances", "interceptions", "final_third_entries",
              "throw_ins", "shots_inside_box"):
        assert m in half_capable, f"{m} should support a half split"
    # Verified NOT to have one.
    for m in ("xg", "npxg", "big_chances", "saves", "shots_outside_box",
              "shots_off_target", "red_cards", "attacks", "dangerous_attacks"):
        assert m not in half_capable, f"{m} must not claim a half split"
