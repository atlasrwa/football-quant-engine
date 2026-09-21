"""PROVIDER-SAFETY tests: unsupported concepts are rejected; half-state claims require
half-resolution provider backing; schema firewall blocks numeric-authority fields.
"""
from __future__ import annotations

import pytest

from src.research.item6.formalizer import formalize
from src.research.item6.provider_vocab import (
    FUTURE_LEAKAGE_CONCEPTS,
    PROVIDER_UNSAFE_CONCEPTS,
    is_supported_metric,
    resolution_of,
)
from src.research.item6.schema import Mechanism, validate_response


def _m(mid, stmt, vars_, cond="c", rel="r", why="w", refs=("ev1",), res="match"):
    return Mechanism(mid, stmt, list(vars_), cond, rel, why, list(refs), res, list(vars_))


@pytest.mark.parametrize("concept", list(PROVIDER_UNSAFE_CONCEPTS))
def test_each_unsafe_concept_is_rejected(concept):
    m = _m("m", f"Whether shots depend on {concept}", ["shots"], cond=f"uses {concept}")
    f = formalize(m, allowed_evidence_refs=["ev1"])
    assert f.f_class == "F2_GROUNDED_BUT_NOT_PROVIDER_MEASURABLE"
    assert not f.provider_safe


@pytest.mark.parametrize("concept", list(FUTURE_LEAKAGE_CONCEPTS))
def test_each_future_concept_is_rejected(concept):
    m = _m("m", f"Whether shots depend on {concept}", ["shots"], cond=f"uses {concept}")
    f = formalize(m, allowed_evidence_refs=["ev1"])
    assert f.future_leakage
    assert f.f_class == "F2_GROUNDED_BUT_NOT_PROVIDER_MEASURABLE"


def test_half_state_requires_half_resolution():
    # 'shots' is match-resolution only; a half-state construction on it must be rejected.
    m = _m("m", "Whether second-half shots rise when trailing at half-time",
           ["shots"], cond="second half split, trailing game state", res="match")
    f = formalize(m, allowed_evidence_refs=["ev1"])
    # half-state signal present but no half-resolution backing -> F2
    assert f.f_class == "F2_GROUNDED_BUT_NOT_PROVIDER_MEASURABLE"


def test_half_state_with_half_metric_is_allowed():
    # 'cards_2h' is half-resolution; a half-state construction is measurable.
    m = _m("m", "Whether second-half cards_2h rise when trailing at half-time",
           ["cards_2h"], cond="second half split, trailing game state", res="half")
    f = formalize(m, allowed_evidence_refs=["ev1"])
    assert f.f_class == "F4_MEASURABLE_WITH_SAFE_ADDITIVE_GRAMMAR_EXTENSION"
    assert f.required_extension == "GX_HALF_STATE_INTERACTION"


def test_schema_firewall_blocks_forbidden_numeric_keys():
    payload = {
        "fixture_id": "f1",
        "mechanisms": [{
            "mechanism_id_local": "m1", "mechanism_statement": "s",
            "observable_variables": ["shots"], "conditioning_logic": "c",
            "expected_relationship_to_test": "r", "why_not_baseline_equivalent": "w",
            "evidence_refs": ["ev1"], "data_resolution_required": "match",
            "provider_requirements": ["shots"], "self_overlap_with": [],
            "probability": 0.7,  # <-- forbidden
        }],
    }
    vr = validate_response(payload)
    assert not vr.ok
    assert any("forbidden_key" in e for e in vr.errors)


def test_schema_blocks_numeric_claim_in_semantic_field():
    payload = {
        "fixture_id": "f1",
        "mechanisms": [{
            "mechanism_id_local": "m1",
            "mechanism_statement": "shots exceed with 0.73 probability",  # numeric claim
            "observable_variables": ["shots"], "conditioning_logic": "c",
            "expected_relationship_to_test": "r", "why_not_baseline_equivalent": "w",
            "evidence_refs": ["ev1"], "data_resolution_required": "match",
            "provider_requirements": ["shots"], "self_overlap_with": [],
        }],
    }
    vr = validate_response(payload)
    assert not vr.ok
    assert any("numeric_claim_in" in e for e in vr.errors)


def test_provider_vocab_consistency():
    assert is_supported_metric("shots")
    assert not is_supported_metric("injury_index")
    assert resolution_of("cards_2h") == "half"
    assert resolution_of("shots") == "match"
