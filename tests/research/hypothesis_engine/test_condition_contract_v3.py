"""Exhaustive contract tests for the V3 measurement apparatus. ZERO SPEND.

THE INVARIANT UNDER TEST
------------------------
    Anything accepted as a valid hypothesis condition must either COMPILE, or FAIL for a
    documented SEMANTIC / DATA-CAPABILITY reason -- never because two internal components
    disagree about encoding.

V2 violated it: `schema.py` typed `conditions[].value` as a free string, `query_plan.py`
checked it against an uppercase closed enum, and 40 of 43 observed reference compile
failures were `venue=home` passing one layer and dying at the other.

These tests sweep EVERY dimension x EVERY legal value x EVERY accepted alias spelling --
not only venue -- through the full boundary path:

    canonicalize (condition_contract)
      -> schema-validate (schema_v2, via the project's own checker)
        -> compile (query_plan, UNCHANGED from V2)

and assert that no result is ever `UNSUPPORTED_DIMENSION` or `QUERY_INVALID`. The compiler
is deliberately the frozen v1 compiler: its enum check was always correct, and leaving it
untouched is what makes the counterfactual replay credible.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, "/home/ubuntu/src")

from research.hypothesis_engine import (availability, capability, condition_contract,
                                        firewall, firewall_v2, lifecycle, normalize,
                                        prompt, prompt_v2, query_plan, schema,
                                        schema_v2, validator, vocabulary)

CUTOFF = 1776711600

#: Failure states a condition is ALLOWED to produce. Each is a statement about the DATA or
#: the METRIC, never about encoding.
SEMANTIC_FAILURES = frozenset({
    lifecycle.UNSUPPORTED_CONTEXT_SOURCE,   # this fixture's packet does not carry it
    lifecycle.UNSUPPORTED_GRANULARITY,      # metric has no half split for a half question
    lifecycle.UNSUPPORTED_METRIC,           # metric not in the inventory / not in manifest
})

#: Failure states that would mean the layers disagree about encoding. Never acceptable.
CONTRACT_FAILURES = frozenset({
    lifecycle.UNSUPPORTED_DIMENSION,
    lifecycle.QUERY_INVALID,
})


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def alias_spellings(token: str) -> list[str]:
    """Every spelling the external boundary is documented to accept for `token`."""
    return [
        token,
        token.lower(),
        token.title(),
        token.capitalize(),
        token.replace("_", "-").lower(),
        token.replace("_", " ").lower(),
        f"  {token.lower()}  ",
    ]


def hypothesis_with(condition, *, metric="corners", family="VENUE_EFFECT"):
    return {
        "hypothesis_id": "H1",
        "research_family": family,
        "subject": "HOME_TEAM",
        "question": "Does the subject's rate in this cohort differ from its own baseline?",
        "target_metrics": [metric],
        "side": "FOR",
        "window": "ALL_PRIOR",
        "conditions": [condition] if condition is not None else [],
        "comparison": "SUBJECT_OVERALL_BASELINE",
        "evidence_refs": [],
        "candidate_confounders": [],
        "required_capabilities": [],
        "sufficiency": "SUFFICIENT",
        "priority": "MEDIUM",
    }


def payload_with(condition, **kw):
    return {"fixture_id": "mt_test", "packet_hash": "0" * 64,
            "hypotheses": [hypothesis_with(condition, **kw)]}


def axis_for(dimension):
    axes = condition_contract.dimension_axes(dimension)
    return axes[0] if axes else None


ALL_DIMENSION_VALUE_PAIRS = [
    (dim, val)
    for dim in sorted(vocabulary.DIMENSIONS)
    for val in condition_contract.dimension_values(dim)
]


# --------------------------------------------------------------------------------------
# 1. ONE SOURCE OF TRUTH -- the layers cannot drift apart
# --------------------------------------------------------------------------------------
def test_contract_projects_vocabulary_without_redeclaring_it():
    """The contract must PROJECT `vocabulary.DIMENSIONS`, never restate it."""
    for dim, spec in vocabulary.DIMENSIONS.items():
        assert condition_contract.dimension_values(dim) == tuple(spec["values"])
        assert condition_contract.dimension_axes(dim) == tuple(spec.get("axes") or ())


@pytest.mark.parametrize("dim", sorted(vocabulary.DIMENSIONS))
def test_schema_v2_value_enum_equals_vocabulary_enum_for_every_dimension(dim):
    """schema-v2's per-dimension `value` enum IS the vocabulary's, element for element.

    This is the test that makes "no layer independently duplicates the enum" checkable
    rather than merely asserted in a docstring.
    """
    branch = next(b for b in condition_contract.condition_schema()["allOf"]
                  if b["if"]["properties"]["dimension"]["const"] == dim)
    assert branch["then"]["properties"]["value"]["enum"] == list(
        vocabulary.DIMENSIONS[dim]["values"])


@pytest.mark.parametrize("dim", sorted(vocabulary.DIMENSIONS))
def test_schema_v2_axis_rule_matches_the_compilers_axis_rule(dim):
    """`axis` required exactly where the compiler requires it, forbidden where it rejects."""
    branch = next(b for b in condition_contract.condition_schema()["allOf"]
                  if b["if"]["properties"]["dimension"]["const"] == dim)
    axes = condition_contract.dimension_axes(dim)
    if axes:
        assert branch["then"].get("required") == ["axis"]
        assert branch["then"]["properties"]["axis"]["enum"] == list(axes)
    else:
        assert branch["then"].get("not") == {"type": "object", "required": ["axis"]}


def test_compiler_accepts_exactly_the_contracts_canonical_values():
    """The compiler's notion of legal and the contract's are the same set, per dimension."""
    for dim in sorted(vocabulary.DIMENSIONS):
        legal = set(condition_contract.dimension_values(dim))
        accepted = set()
        for val in legal | {"NOT_A_VALUE", "home", "HIGHER"}:
            cond = {"dimension": dim, "value": val}
            axis = axis_for(dim)
            if axis:
                cond["axis"] = axis
            res = query_plan.compile_hypothesis(
                hypothesis_with(cond), fixture_id="mt_test", cutoff_unix=CUTOFF)
            if not any(r.failure == lifecycle.UNSUPPORTED_DIMENSION for r in res):
                accepted.add(val)
        assert accepted == legal, f"{dim}: compiler accepts {accepted}, contract says {legal}"


# --------------------------------------------------------------------------------------
# 2. THE COMPLETE PATH -- schema -> normalization -> compiler, exhaustively
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize("dim,val", ALL_DIMENSION_VALUE_PAIRS)
def test_every_canonical_condition_passes_schema_and_reaches_the_compiler(dim, val):
    cond = {"dimension": dim, "value": val}
    axis = axis_for(dim)
    if axis:
        cond["axis"] = axis

    errs = validator.validate_schema_against(schema_v2.build_schema(), payload_with(cond))
    assert errs == [], f"{dim}={val} rejected by schema-v2: {errs}"

    res = query_plan.compile_hypothesis(
        hypothesis_with(cond), fixture_id="mt_test", cutoff_unix=CUTOFF)
    for r in res:
        assert r.failure not in CONTRACT_FAILURES, (
            f"{dim}={val} produced a CONTRACT failure {r.failure}: {r.reasons}")
        if not r.ok:
            assert r.failure in SEMANTIC_FAILURES, (
                f"{dim}={val} failed with undocumented state {r.failure}: {r.reasons}")


@pytest.mark.parametrize("dim,val", ALL_DIMENSION_VALUE_PAIRS)
def test_every_alias_spelling_canonicalizes_then_takes_the_canonical_path(dim, val):
    """The venue-casing defect, swept over every dimension and every value.

    Under V2 `venue=home` passed schema and died at compile. Here every accepted alias
    spelling of every value of every dimension must canonicalize, then pass schema-v2,
    then compile with no contract failure.
    """
    axis = axis_for(dim)
    for spelling in alias_spellings(val):
        raw = {"dimension": dim, "value": spelling}
        if axis:
            raw["axis"] = axis.upper()          # aliased axis casing too

        got = condition_contract.canonicalize_condition(raw)
        assert isinstance(got, condition_contract.CanonicalCondition), (
            f"{dim}={spelling!r} failed to canonicalize: {got}")
        assert got.value == val
        assert got.dimension == dim
        assert got.axis == axis

        errs = validator.validate_schema_against(
            schema_v2.build_schema(), payload_with(got.to_dict()))
        assert errs == [], f"canonicalized {dim}={spelling!r} rejected by schema: {errs}"

        res = query_plan.compile_hypothesis(
            hypothesis_with(got.to_dict()), fixture_id="mt_test", cutoff_unix=CUTOFF)
        for r in res:
            assert r.failure not in CONTRACT_FAILURES, (
                f"{dim}={spelling!r} -> {got.value}: contract failure {r.failure}")


def test_the_two_documented_semantic_failures_are_the_only_ones_and_still_fail():
    """The asymmetry IS the invariant: some conditions must still fail, for DATA reasons.

    A test that asserted "everything compiles" would have been satisfied by deleting the
    capability checks. These two must keep failing, and for the right named reason.
    """
    # half-period question against a FULL_MATCH-only metric -> granularity, not encoding
    res = query_plan.compile_hypothesis(
        hypothesis_with({"dimension": "period", "value": "FIRST_HALF"}, metric="npxg"),
        fixture_id="mt_test", cutoff_unix=CUTOFF)
    assert [r.failure for r in res] == [lifecycle.UNSUPPORTED_GRANULARITY]

    # a dimension the fixture manifest withholds -> context source, not encoding
    manifest = capability.FixtureCapabilityManifest(
        fixture_id="mt_test",
        available_metrics=tuple(capability.metric_names()),
        available_dimensions=("venue", "competition"))
    res = query_plan.compile_hypothesis(
        hypothesis_with({"dimension": "half_score_state", "value": "TRAILING_AT_HT"}),
        fixture_id="mt_test", cutoff_unix=CUTOFF, manifest=manifest)
    assert [r.failure for r in res] == [lifecycle.UNSUPPORTED_CONTEXT_SOURCE]


def test_full_path_over_a_frozen_fixture_manifest_never_produces_a_contract_failure():
    """Same sweep, but against every REAL frozen V2 fixture manifest."""
    packets = json.load(open("/home/ubuntu/research/hypothesis_engine/out/"
                             "MATERIALIZED_PACKETS_sonnet46_v2.json"))
    for key, packet in sorted(packets.items()):
        cm = packet["capability_manifest"]
        manifest = capability.FixtureCapabilityManifest(
            fixture_id=cm["fixture_id"],
            available_metrics=tuple(cm["available_metrics"]),
            available_dimensions=tuple(cm["available_dimensions"]),
            unsupported_context=dict(cm.get("unsupported_context") or {}),
            coverage=dict(cm.get("coverage") or {}),
            notes=tuple(cm.get("notes") or ()))
        metric = cm["available_metrics"][0]
        for dim, val in ALL_DIMENSION_VALUE_PAIRS:
            cond = {"dimension": dim, "value": val}
            axis = axis_for(dim)
            if axis:
                cond["axis"] = axis
            res = query_plan.compile_hypothesis(
                hypothesis_with(cond, metric=metric),
                fixture_id=cm["fixture_id"], cutoff_unix=CUTOFF, manifest=manifest)
            for r in res:
                assert r.failure not in CONTRACT_FAILURES, (
                    f"{key} {dim}={val}: {r.failure} -- {r.reasons}")
                if not r.ok:
                    assert r.failure in SEMANTIC_FAILURES, (
                        f"{key} {dim}={val}: undocumented {r.failure}")


# --------------------------------------------------------------------------------------
# 3. EXACTLY ONE INTERNAL REPRESENTATION
# --------------------------------------------------------------------------------------
def test_alias_spellings_collapse_to_one_intent_key_and_one_plan_hash():
    keys = set()
    hashes = set()
    for spelling in alias_spellings("HOME"):
        payload = payload_with({"dimension": "venue", "value": spelling})
        canon, report = condition_contract.canonicalize_payload(payload)
        assert report.ok
        keys |= normalize.intent_key_set(canon)
        res = query_plan.compile_hypothesis(
            canon["hypotheses"][0], fixture_id="mt_test", cutoff_unix=CUTOFF)
        hashes |= {r.plan.plan_hash() for r in res if r.ok}
    assert len(keys) == 1, f"aliases produced {len(keys)} distinct intents"
    assert len(hashes) == 1, f"aliases produced {len(hashes)} distinct plan hashes"


def test_canonicalization_is_idempotent():
    for dim, val in ALL_DIMENSION_VALUE_PAIRS:
        raw = {"dimension": dim, "value": val.lower()}
        axis = axis_for(dim)
        if axis:
            raw["axis"] = axis
        once = condition_contract.canonicalize_condition(raw)
        twice = condition_contract.canonicalize_condition(once.to_dict())
        assert once.to_dict() == twice.to_dict()


# --------------------------------------------------------------------------------------
# 4. UNKNOWN VALUES FAIL CLOSED, WITH A PRECISE REASON
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize("raw,reason", [
    ({"dimension": "not_a_dimension", "value": "HOME"},
     condition_contract.UNKNOWN_DIMENSION),
    # the real V2 emission: the competition dimension given the literal word COMPETITION
    ({"dimension": "competition", "value": "COMPETITION"},
     condition_contract.UNKNOWN_VALUE),
    ({"dimension": "venue", "value": "NEUTRAL"},
     condition_contract.UNKNOWN_VALUE),
    # a cross-dimension value: HIGH is legal for opponent_profile, never for venue
    ({"dimension": "venue", "value": "HIGH"},
     condition_contract.UNKNOWN_VALUE),
    # the real V2 emission: a band conflated with an axis
    ({"dimension": "opponent_profile", "value": "high_possession", "axis": None},
     condition_contract.UNKNOWN_VALUE),
    # the real V2 emission: a profile band with no axis at all
    ({"dimension": "opponent_profile", "value": "MID"},
     condition_contract.MISSING_AXIS),
    ({"dimension": "opponent_profile", "value": "HIGH", "axis": "vibes"},
     condition_contract.UNKNOWN_AXIS),
    ({"dimension": "venue", "value": "HOME", "axis": "corners_against"},
     condition_contract.AXIS_NOT_APPLICABLE),
    ({"dimension": "venue", "value": 3},
     condition_contract.MALFORMED_CONDITION),
    ("venue=HOME", condition_contract.MALFORMED_CONDITION),
])
def test_unknown_input_fails_closed_with_a_named_reason(raw, reason):
    got = condition_contract.canonicalize_condition(raw)
    assert isinstance(got, condition_contract.ContractFailure)
    assert got.reason == reason
    assert got.detail, "a fail-closed result must carry a precise reason string"


def test_no_semantic_aliasing_is_performed():
    """The boundary folds SPELLING. It never guesses MEANING.

    `high_possession` must not become (band=HIGH, axis=possession_for): repairing it would
    be the engine inventing the model's intent, and would make a real research error
    invisible.
    """
    got = condition_contract.canonicalize_condition(
        {"dimension": "opponent_profile", "value": "high_possession"})
    assert isinstance(got, condition_contract.ContractFailure)


def test_failed_conditions_are_preserved_verbatim_not_dropped_or_repaired():
    payload = payload_with({"dimension": "competition", "value": "COMPETITION"})
    canon, report = condition_contract.canonicalize_payload(payload)
    assert not report.ok and report.n_failed == 1
    assert canon["hypotheses"][0]["conditions"] == [
        {"dimension": "competition", "value": "COMPETITION"}]
    res = query_plan.compile_hypothesis(
        canon["hypotheses"][0], fixture_id="mt_test", cutoff_unix=CUTOFF)
    assert all(not r.ok for r in res), "a contract failure must still fail downstream"


# --------------------------------------------------------------------------------------
# 5. THE EXACT V2 DEFECT IS NOW A SCHEMA REJECTION
# --------------------------------------------------------------------------------------
def test_v1_schema_accepted_lowercase_venue_and_v2_does_not():
    """The regression that cost V2 40 of 43 compile failures, pinned in both directions."""
    payload = payload_with({"dimension": "venue", "value": "home"})
    assert validator.validate_schema_against(schema.build_schema(), payload) == [], (
        "v1 is frozen and must keep its documented (defective) behaviour")
    errs = validator.validate_schema_against(schema_v2.build_schema(), payload)
    assert errs, "schema-v2 must reject a wrong-cased condition value"
    assert any("conditions[0].value" in e for e in errs)


def test_v2_schema_rejects_profile_without_axis_and_axis_where_it_does_not_belong():
    no_axis = payload_with({"dimension": "opponent_profile", "value": "HIGH"})
    errs = validator.validate_schema_against(schema_v2.build_schema(), no_axis)
    assert any("axis" in e for e in errs)

    stray_axis = payload_with(
        {"dimension": "venue", "value": "HOME", "axis": "corners_against"})
    assert validator.validate_schema_against(schema_v2.build_schema(), stray_axis)


# --------------------------------------------------------------------------------------
# 6. THE FROZEN V1 PATH IS UNCHANGED
# --------------------------------------------------------------------------------------
def test_v1_schema_contains_no_combinator_so_the_added_checker_branch_is_inert():
    blob = json.dumps(schema.build_schema())
    for kw in ('"allOf"', '"if"', '"then"', '"not"', '"const"'):
        assert kw not in blob


def test_frozen_v2_responses_still_schema_validate_exactly_as_before():
    """Every recorded V2 response must still pass the FROZEN v1 schema unchanged."""
    path = ("/home/ubuntu/research/hypothesis_engine/out/hypothesis_v1_sonnet46_v2/"
            "hypothesis_states.jsonl")
    n = 0
    for line in open(path):
        if not line.strip():
            continue
        raw = json.loads(line).get("raw_response")
        if raw is None:
            continue
        n += 1
        assert validator.validate_schema(raw) == []
    assert n == 64, f"expected all 64 frozen responses, saw {n}"


def test_v1_prompt_and_schema_content_hashes_are_untouched():
    """Provenance pinning: the frozen V2 run's prompt/schema identity must not move."""
    assert schema.SCHEMA_VERSION == "hypothesis_set_schema_v1"
    assert prompt.PROMPT_VERSION == "hypothesis_analyst_prompt_v1"
    assert schema.schema_content_hash() != schema_v2.schema_content_hash()
    assert prompt.prompt_content_hash() != prompt_v2.prompt_content_hash()


# --------------------------------------------------------------------------------------
# 7. THE CONTRACT DOES NOT COLLIDE WITH THE FIREWALL'S PATH EXEMPTIONS
# --------------------------------------------------------------------------------------
def test_canonical_conditions_produce_no_firewall_violation_in_either_version():
    """The flat {dimension, value, axis} shape is load-bearing.

    `firewall._FIELD_NAME_EXEMPT_PATHS` and `vocabulary.BAND_EXEMPT_PATH_SUFFIXES` key on
    the literal path `conditions.value`. Restructuring conditions would turn every cohort
    value into a `forbidden_field` and every band into a `level_grade`.
    """
    for dim, val in ALL_DIMENSION_VALUE_PAIRS:
        cond = {"dimension": dim, "value": val}
        axis = axis_for(dim)
        if axis:
            cond["axis"] = axis
        payload = payload_with(cond)
        assert firewall.scan(payload) == [], f"{dim}={val} tripped firewall v1"
        assert firewall_v2.blocking(firewall_v2.scan(payload)) == [], (
            f"{dim}={val} tripped firewall v2")
    assert "$.hypotheses.conditions.value" in firewall._FIELD_NAME_EXEMPT_PATHS
    assert "conditions.value" in vocabulary.BAND_EXEMPT_PATH_SUFFIXES
