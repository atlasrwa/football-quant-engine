"""Mandate §23 -- provider semantics must remain explicit and must fail closed.

These tests exist because the cheapest way to produce a wrong research result is to let
two similarly-named provider fields be treated as one concept.
"""
from __future__ import annotations

import copy
import sys

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/tests/research/hypothesis_engine")

import pytest

import fixtures as F
from src.research.hypothesis_engine import capability, lifecycle, query_plan, validator


@pytest.fixture()
def packet():
    return F.real_identity_packet()


@pytest.fixture()
def response(packet):
    return F.valid_response(packet)


# ------------------------------------------------------------------- accurate crosses
def test_accurate_crosses_keeps_its_accuracy_semantics():
    spec = capability.metric("accurate_crosses")
    assert spec is not None
    assert spec.source_fields[capability.THESTATSAPI] == "passes/accurate_crosses"
    assert "NOT total crosses" in spec.definition
    assert spec.caveat and "attempt" in spec.caveat.lower()


def test_there_is_no_total_crosses_metric_to_confuse_it_with():
    """If cross ATTEMPTS were queryable, a question about 'crossing volume' would silently
    get completed crosses instead. The concept must simply not exist."""
    assert not capability.is_supported_metric("crosses")
    assert not capability.is_supported_metric("total_crosses")
    assert not capability.is_supported_metric("crosses_attempted")


# ------------------------------------------------------- dangerous attacks vs touches
def test_dangerous_attacks_and_touches_in_box_are_distinct_metrics():
    da = capability.metric("dangerous_attacks")
    tb = capability.metric("touches_in_box")
    assert da is not None and tb is not None
    assert da.canonical != tb.canonical
    assert da.providers == (capability.FOOTYSTATS,)
    assert tb.providers == (capability.THESTATSAPI,)
    assert da.source_fields != tb.source_fields


def test_dangerous_attacks_equivalence_is_explicitly_denied():
    assert "touches_in_box" in (capability.metric("dangerous_attacks").caveat or "")
    assert "touches_in_box" in capability.metric("dangerous_attacks").caveat
    conflicts = capability.semantic_conflicts()
    assert "dangerous_attacks~touches_in_box" in conflicts
    assert "not equivalent" in conflicts["dangerous_attacks~touches_in_box"].lower()


def test_touches_in_box_caveat_names_the_proxy_trap():
    assert "proxy" in (capability.metric("touches_in_box").caveat or "").lower()


# ---------------------------------------------------------------- non-mergeable concepts
@pytest.mark.parametrize("metric_name", ["total_shots", "xg"])
def test_measured_disagreement_metrics_are_never_mergeable(metric_name):
    assert not capability.may_merge_providers(metric_name)
    assert capability.metric(metric_name).comparability == capability.DO_NOT_MERGE
    assert "corr" in (capability.metric(metric_name).caveat or "").lower()


def test_unmeasured_agreement_is_treated_as_not_mergeable():
    """'Never checked' must be as safe as 'measured to disagree', while staying labelled
    differently so the distinction is not lost."""
    spec = capability.metric("throw_ins")
    assert spec.comparability == capability.UNMEASURED
    assert not capability.may_merge_providers("throw_ins")


@pytest.mark.parametrize("metric_name", ["goals", "corners", "shots_on_target",
                                         "possession", "fouls", "yellow_cards"])
def test_measured_agreement_metrics_are_mergeable(metric_name):
    assert capability.may_merge_providers(metric_name)


def test_compiler_pins_exactly_one_provider_and_never_merges(packet, response):
    out = query_plan.compile_set(response, cutoff_unix=F.CUTOFF)
    for hid, results in out["results"].items():
        for r in results:
            if r["ok"]:
                prov = r["plan"]["provider"]
                assert prov in capability.PROVIDERS
                assert isinstance(prov, str), "a plan carries ONE provider, never a list"


def test_compiler_refuses_a_provider_the_inventory_does_not_supply(packet, response):
    """A manifest that pins FootyStats for a TheStatsAPI-only metric must fail closed."""
    res = query_plan.compile_hypothesis(
        response["hypotheses"][1], fixture_id="fx_0001", cutoff_unix=F.CUTOFF,
        manifest_providers={"blocked_shots": capability.FOOTYSTATS})
    assert any(r.failure == lifecycle.PROVIDER_SEMANTICS_CONFLICT for r in res)


# ------------------------------------------------------------------ unsupported context
def test_injuries_are_unsupported_but_not_architecturally_banned():
    spec = capability.context_source("injuries")
    assert spec.status == capability.UNSUPPORTED_CONTEXT_SOURCE
    assert spec.providers == ()
    assert "not banned architecturally" in spec.note.lower()
    assert "injuries" in capability.unsupported_context_sources()


def test_injury_conditioned_hypothesis_fails_closed(packet, response):
    bad = copy.deepcopy(response)
    bad["hypotheses"][0]["required_capabilities"] = ["injuries"]
    r = validator.validate(bad, packet=packet,
                           expected_packet_hash=packet["packet_hash"],
                           expected_fixture_id=packet["fixture_id"])
    v = next(v for v in r.verdicts if v.hypothesis_id == "H1")
    assert not v.accepted
    assert v.failure == lifecycle.UNSUPPORTED_CONTEXT_SOURCE
    assert "injur" in " ".join(v.reasons).lower()


def test_unsupported_context_is_declared_to_the_model_in_every_packet(packet):
    unsupported = packet["capability_manifest"]["unsupported_context"]
    for name in ("injuries", "expected_formation", "minute_level_events"):
        assert name in unsupported
        assert unsupported[name], "each unsupported source must explain itself"


def test_hallucinated_metric_is_rejected_not_approximated(packet, response):
    bad = copy.deepcopy(response)
    bad["hypotheses"][0]["target_metrics"] = ["expected_threat"]
    r = validator.validate(bad, packet=packet,
                           expected_packet_hash=packet["packet_hash"],
                           expected_fixture_id=packet["fixture_id"])
    # Rejected by the enum in the closed schema, before it can reach anything.
    assert not r.accepted
    assert r.failure == lifecycle.SCHEMA_INVALID


def test_unsupported_metric_failure_state_exists_for_manifest_gating(packet, response):
    """A metric can be globally supported yet unavailable for one fixture."""
    manifest = capability.FixtureCapabilityManifest(
        fixture_id="fx_0001",
        available_metrics=("corners",),          # deliberately narrow
        available_dimensions=("venue", "opponent_formation_family"),
    )
    res = query_plan.compile_hypothesis(
        response["hypotheses"][0], fixture_id="fx_0001",
        cutoff_unix=F.CUTOFF, manifest=manifest)
    assert any(r.failure == lifecycle.UNSUPPORTED_METRIC for r in res)
