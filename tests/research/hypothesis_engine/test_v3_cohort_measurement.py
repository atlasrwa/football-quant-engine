"""Deterministic historical measurement of the frozen V3 hypothesis corpus.

OFFLINE, ZERO SPEND. No Bedrock import anywhere in this module's import graph. The
leakage tests are POSITIVE tests: they feed deliberately leaked observations and assert
the measurement layer refuses, rather than merely observing that clean input stays clean.

Run: .venv/bin/python -m pytest tests/research/hypothesis_engine/test_v3_cohort_measurement.py -q
"""
import json
import os
import sys

import pytest

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/src")

from research.hypothesis_engine import cohort_measurement as CM
from research.hypothesis_engine import query_plan, similarity, vocabulary

OUT = "/home/ubuntu/research/hypothesis_engine/out/v3_hypothesis_measurement"
CUTOFF = 1_700_000_000
DAY = 86_400


def obs(i, *, value=1.0, venue="HOME", opponent="OPP", comp="epl", offset=None,
        own_form="BACK_FOUR", opp_form="BACK_FOUR"):
    return CM.Obs(
        fixture_id=f"f{i}", kickoff_unix=CUTOFF - (offset if offset is not None else (i + 1) * DAY),
        competition=comp, opponent=opponent, value=value,
        dimensions={"venue": venue, "own_formation_family": own_form,
                    "opponent_formation_family": opp_form})


def spec(**kw):
    base = dict(
        spec_version=CM.COHORT_MEASUREMENT_VERSION, hypothesis_id="H1",
        fixture_id="TARGET", subject_label="HOME_TEAM", subject_team="Team A",
        target_metric="corners", side="FOR", window="ALL_PRIOR", period="ALL",
        granularity="FULL_MATCH", venue_condition=None, competition_condition=None,
        own_formation_condition=None, opponent_formation_condition=None,
        opponent_profile_band=None, opponent_profile_axis=None,
        profile_band_semantics=None, comparison_cohort="SUBJECT_OVERALL_BASELINE",
        target_competition="epl", cutoff_unix=CUTOFF, provider="thestatsapi",
        required_fields=("rich", "corner_kicks"), plan_hash="deadbeef")
    base.update(kw)
    return CM.MeasurementSpec(**base)


# ======================================================================================
# §3 point-in-time safety -- positive leakage tests
# ======================================================================================
def test_observation_at_cutoff_is_rejected_not_silently_dropped():
    """kickoff == cutoff is INSIDE the forbidden region: the rule is strict `<`."""
    hist = [obs(i) for i in range(12)] + [obs(99, offset=0)]
    r = CM.execute(spec(), subject_history=hist)
    assert r.outcome == CM.LEAKAGE_REJECTED
    assert r.difference is None and r.conditional is None


def test_observation_after_cutoff_is_rejected():
    hist = [obs(i) for i in range(12)] + [obs(99, offset=-DAY)]
    r = CM.execute(spec(), subject_history=hist)
    assert r.outcome == CM.LEAKAGE_REJECTED


def test_clean_history_measures_and_never_silently_masks_a_leak():
    hist = [obs(i, value=float(i), venue="HOME" if i % 2 else "AWAY") for i in range(24)]
    r = CM.execute(spec(venue_condition="HOME"), subject_history=hist)
    assert r.outcome == CM.MEASURED
    # one leaked row flips the SAME input to a refusal -- proving the test above bites
    r2 = CM.execute(spec(venue_condition="HOME"),
                    subject_history=hist + [obs(99, offset=0)])
    assert r2.outcome == CM.LEAKAGE_REJECTED


def test_recorded_pit_audit_is_clean_and_excludes_the_target_fixture():
    path = f"{OUT}/pit_audit.json"
    if not os.path.exists(path):
        pytest.skip("measurement run artifacts not present")
    a = json.load(open(path))
    assert a["violations"] == []
    assert a["target_fixture_in_cohort"] == 0
    assert a["clean"] is True
    assert a["max_delta_seconds"] is not None and a["max_delta_seconds"] < 0


# ======================================================================================
# §6 three-valued condition logic
# ======================================================================================
def test_unrecorded_dimension_is_undetermined_not_a_non_member():
    """Missing formation must NOT be counted as 'formation differed'."""
    hist = ([obs(i, own_form="BACK_THREE") for i in range(6)]
            + [obs(50 + i, own_form=None) for i in range(6)])
    r = CM.execute(spec(own_formation_condition="BACK_THREE"), subject_history=hist)
    assert r.undetermined_n == 6
    assert r.conditional.usable_n == 6
    assert r.dimension_coverage["own_formation_family"]["missing_n"] == 6


def test_any_value_is_not_a_condition():
    hist = [obs(i, venue="HOME" if i % 2 else "AWAY") for i in range(12)]
    a = CM.execute(spec(venue_condition="ANY"), subject_history=hist)
    b = CM.execute(spec(), subject_history=hist)
    assert a.conditional.n == b.conditional.n == 12


# ======================================================================================
# §6 the EXACT comparison the plan encodes
# ======================================================================================
def test_every_frozen_comparison_is_implemented():
    """No frozen comparison may fall through to UNSUPPORTED_COMPARISON."""
    hist = [obs(i, value=float(i), venue="HOME" if i % 2 else "AWAY") for i in range(24)]
    for c in vocabulary.COMPARISONS:
        r = CM.execute(spec(comparison_cohort=c, window="W5" if "RECENT" in c else "ALL_PRIOR"),
                       subject_history=hist,
                       league_values=[1.0] * 40 if "LEAGUE" in c else None)
        assert r.outcome != CM.UNSUPPORTED_COMPARISON, c


def test_venue_baseline_against_the_same_venue_is_not_distinct():
    """A venue condition matching the subject's upcoming venue encodes no contrast."""
    hist = [obs(i, venue="HOME" if i % 2 else "AWAY") for i in range(24)]
    r = CM.execute(spec(venue_condition="HOME", comparison_cohort="SUBJECT_VENUE_BASELINE"),
                   subject_history=hist)
    assert r.outcome == CM.NOT_DISTINCT
    r2 = CM.execute(spec(venue_condition="AWAY", comparison_cohort="SUBJECT_VENUE_BASELINE"),
                    subject_history=hist)
    assert r2.outcome != CM.NOT_DISTINCT


def test_recent_vs_long_contrasts_the_window_not_the_conditions():
    hist = [obs(i, value=1.0) for i in range(30)]
    r = CM.execute(spec(window="W5", comparison_cohort="SUBJECT_RECENT_VS_LONG_BASELINE"),
                   subject_history=hist)
    assert r.conditional.n == 5 and r.comparison.n == 30


def test_league_environment_without_values_is_typed_unsupported():
    hist = [obs(i) for i in range(12)]
    r = CM.execute(spec(comparison_cohort="LEAGUE_ENVIRONMENT_BASELINE"),
                   subject_history=hist, league_values=None)
    assert r.outcome == CM.UNSUPPORTED_COMPARISON


# ======================================================================================
# §4 provider discipline -- typed unsupported, never a silent proxy
# ======================================================================================
def test_unsupported_is_distinct_from_insufficient():
    assert CM.UNSUPPORTED_METRIC in CM.UNSUPPORTED_OUTCOMES
    assert CM.INSUFFICIENT_DATA not in CM.UNSUPPORTED_OUTCOMES


def test_axis_without_a_backing_metric_is_typed_unsupported():
    """`shots_for` / `shots_against` are in the frozen vocabulary but have no metric."""
    for axis in ("shots_for", "shots_against"):
        assert CM.axis_to_metric_side(axis) is None
    r = CM.execute(spec(opponent_profile_band="HIGH", opponent_profile_axis="shots_for"),
                   subject_history=[obs(i) for i in range(12)],
                   band_resolver=lambda *a: None)
    assert r.outcome == CM.UNSUPPORTED_PROFILE_AXIS


def test_every_axis_used_in_the_corpus_resolves_or_is_typed():
    for axis in vocabulary.PROFILE_AXES:
        got = CM.axis_to_metric_side(axis)
        assert got is None or got[1] in ("FOR", "AGAINST")


def test_provenance_is_carried_on_every_measurement():
    r = CM.execute(spec(), subject_history=[obs(i) for i in range(12)])
    assert r.provenance["provider"] == "thestatsapi"
    assert r.provenance["required_fields"] == ["rich", "corner_kicks"]


# ======================================================================================
# §5 opponent similarity is deterministic and never LLM-supplied
# ======================================================================================
def test_unbandable_opponent_is_undetermined_not_excluded_as_a_non_member():
    res = similarity.CohortResolution(
        axis="corners_for", requested_band="HIGH", cutoff_unix=CUTOFF,
        members=("OPP_A",),
        assignments=(similarity.BandAssignment("OPP_A", "corners_for", "HIGH", 5.0, 9, CUTOFF),
                     similarity.BandAssignment("OPP_B", "corners_for", "LOW", 1.0, 9, CUTOFF)))
    hist = ([obs(i, opponent="OPP_A") for i in range(5)]
            + [obs(10 + i, opponent="OPP_B") for i in range(5)]
            + [obs(20 + i, opponent="OPP_C") for i in range(4)])     # never banded
    r = CM.execute(spec(opponent_profile_band="HIGH", opponent_profile_axis="corners_for"),
                   subject_history=hist, band_resolver=lambda *a: res)
    assert r.conditional.n == 5              # OPP_A only
    assert r.undetermined_n == 4             # OPP_C is missing data, not a non-member

def test_pending_similarity_methods_cannot_produce_a_result():
    with pytest.raises(similarity.SimilarityMethodPending):
        similarity.resolve_band(axis="corners_for", requested_band="HIGH",
                                cutoff_unix=CUTOFF, candidates=["A"],
                                axis_value_fn=lambda o, c: (1.0, 9),
                                method="LEARNED_EMBEDDING")


def test_band_semantics_are_recorded_on_every_profile_spec():
    s = spec(opponent_profile_band="HIGH", opponent_profile_axis="corners_for",
             profile_band_semantics=CM.PROFILE_BAND_SEMANTICS)
    assert s.to_dict()["profile_band_semantics"] == "AS_OF_TARGET_CUTOFF"


# ======================================================================================
# §7 canonical thresholds are reused, never invented here
# ======================================================================================
def test_thresholds_match_the_canonical_project_values():
    from research.hypothesis_engine import measurement as M
    from research.llm_matchup import cohorts as CH
    assert CM.SHRINK_K == M.SHRINK_K == CH.SHRINK_K == 6.0
    assert CM.MIN_CONDITIONAL_N == M.MIN_CONDITIONAL_N == 4
    assert CM.MIN_COMPARISON_N == M.MIN_BASELINE_N == 8
    assert CM.MIN_PRIOR_MATCHES == similarity.MIN_PRIOR_MATCHES == 4


def test_small_n_is_reported_not_discarded():
    hist = [obs(i, venue="HOME" if i < 2 else "AWAY") for i in range(14)]
    r = CM.execute(spec(venue_condition="HOME"), subject_history=hist)
    assert r.outcome == CM.INSUFFICIENT_DATA
    assert r.conditional.usable_n == 2          # the cohort is still reported in full
    assert r.difference is None                 # but no effect is estimated


# ======================================================================================
# §1 corpus eligibility cannot see an outcome
# ======================================================================================
def test_frozen_corpus_matches_the_frozen_v3_denominators():
    path = f"{OUT}/frozen_hypothesis_corpus.json"
    if not os.path.exists(path):
        pytest.skip("measurement run artifacts not present")
    c = json.load(open(path))
    assert c["inclusion_rule"] == {"control": "reference",
                                   "whole_response_failure": None,
                                   "hypothesis_in": "validator_v2.accepted_hypotheses"}
    # P1's frozen denominator was 112 accepted hypotheses over 11 clean reference calls.
    assert c["n_included"] == 112
    assert len({r["seq"] for r in c["included"]}) == 11


def test_no_outcome_or_market_field_reaches_a_specification():
    path = f"{OUT}/measurement_specs.json"
    if not os.path.exists(path):
        pytest.skip("measurement run artifacts not present")
    blob = json.dumps(json.load(open(path))).lower()
    for banned in ("closing", "odds", "price", "settle", "p_model", "edge",
                   "probability", "result", "fulltime", "ft_score"):
        assert banned not in blob, banned


def test_measurements_are_labelled_descriptive_not_causal():
    path = f"{OUT}/cohort_measurements.json"
    if not os.path.exists(path):
        pytest.skip("measurement run artifacts not present")
    for m in json.load(open(path)):
        assert m["association_type"] == "DESCRIPTIVE_ASSOCIATION"


# ======================================================================================
# Architecture firewall
# ======================================================================================
def test_measurement_layer_imports_no_bedrock_and_no_production_path():
    """Checked on the IMPORT GRAPH, not on prose: the docstring legitimately says
    'walk-forward', which a naive substring scan would flag."""
    import ast
    import research.hypothesis_engine.cohort_measurement as mod
    tree = ast.parse(open(mod.__file__).read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    blob = " ".join(imported)
    for banned in ("boto3", "bedrock", "prediction_engine", "research.forward",
                   "broadcast", "edge_scanner"):
        assert banned not in blob, banned
    assert "CHAMPION" not in open(mod.__file__).read()
