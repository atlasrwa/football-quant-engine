"""SONNET46_HYPOTHESIS_V3 preregistration artifacts. ZERO SPEND.

Everything asserted here is frozen BEFORE inference: the battery layout, the control
transforms, the eligibility denominators, the thresholds, the stop rule and the verdict
function. If any of it changed after authorization the preregistration would be worthless,
so it is pinned in tests rather than only in a document.
"""
from __future__ import annotations

import copy
import json
import sys

import pytest

sys.path.insert(0, "/home/ubuntu/src")

from research.hypothesis_engine import (availability, battery_v3, capability,
                                        condition_contract, context_packet as CP,
                                        controls, controls_v3, lifecycle, prompt_v2,
                                        verdict_v3)

OUT = "/home/ubuntu/research/hypothesis_engine/out"


@pytest.fixture(scope="module")
def battery():
    return json.load(open(f"{OUT}/hypothesis_golden_battery_v1.json"))


@pytest.fixture(scope="module")
def frozen_packets():
    return json.load(open(f"{OUT}/frozen_packets_v1.json"))


@pytest.fixture(scope="module")
def built(battery, frozen_packets):
    return battery_v3.build_manifest(battery, copy.deepcopy(frozen_packets))


# ======================================================================================
# Battery composition
# ======================================================================================
def test_the_battery_is_56_calls_in_the_frozen_layout(built):
    manifest, _ = built
    assert manifest["total_planned_calls"] == 56
    assert manifest["planned_calls_by_control"] == {
        "reference": 12, "repeatability": 12, "identity_alias": 6,
        "irrelevant_field": 6, "profile_axis_perturbation": 6,
        "availability_ablation": 6, "evidence_starvation": 4,
        "unsupported_data_trap": 4}


def test_the_battery_is_not_a_copy_of_v2s_64(built):
    """V2's shape was not reused by default; two arms are dropped with stated reasons."""
    manifest, _ = built
    assert manifest["total_planned_calls"] < 64
    assert set(manifest["dropped_v2_arms"]) == {"venue_flip", "formation_ablation"}
    for reason in manifest["dropped_v2_arms"].values():
        assert len(reason) > 40, "a dropped arm needs a stated scientific reason"


def test_repeatability_is_oversampled_because_it_is_a_gate_denominator(built):
    manifest, _ = built
    rs = manifest["repeatability_structure"]
    assert rs["n_fixtures"] == 6 and rs["repeat_calls_per_fixture"] == 2
    assert rs["samples_per_fixture_including_reference"] == 3
    assert rs["same_input_pairs"] == 18
    for key in ("D12_identity_invariance_relative", "D13_irrelevant_invariance_relative"):
        c = next(c for c in verdict_v3.DISCIPLINE if c.key == key)
        assert "repeatability floor" in c.denominator or "same-input" in c.denominator


def test_every_call_spec_is_fully_frozen(built):
    manifest, materialized = built
    for s in manifest["call_specs"]:
        assert s["resulting_packet_hash"]
        assert materialized[s["packet_key"]]["packet_hash"] == s["resulting_packet_hash"]
        assert s["serialized_request_sha256"]
        assert s["input_tokens"] > 0
        assert s["expected_property"]


def test_the_manifest_hash_covers_everything_else(built):
    import hashlib
    manifest, _ = built
    recomputed = hashlib.sha256(json.dumps(
        {k: v for k, v in manifest.items() if k != "manifest_hash"},
        sort_keys=True, default=str).encode()).hexdigest()
    assert recomputed == manifest["manifest_hash"]


# ======================================================================================
# Controls
# ======================================================================================
def test_v3_controls_are_deterministic_and_non_mutating(frozen_packets):
    for fid, ref in sorted(frozen_packets.items()):
        before = copy.deepcopy(ref)
        a, ch_a = controls_v3.profile_axis_perturbation(ref, raise_band=True)
        b, ch_b = controls_v3.profile_axis_perturbation(ref, raise_band=True)
        assert a["packet_hash"] == b["packet_hash"]
        assert CP.packet_hash(a) == a["packet_hash"]
        assert ch_a == ch_b
        c = controls_v3.availability_ablation(ref)
        assert c["packet_hash"] == controls_v3.availability_ablation(ref)["packet_hash"]
        assert CP.packet_hash(c) == c["packet_hash"]
        assert ref == before, f"{fid}: control mutated its input packet"


def test_profile_axis_perturbation_uses_a_surface_disjoint_from_v2s(frozen_packets):
    """V2 moved a DEFENSIVE wide-play surface; V3 moves an OFFENSIVE shot surface.

    Disjointness is what makes this a test of AXIS SELECTION rather than a rerun of V2's
    sensitivity control.
    """
    assert not (set(controls_v3.PROFILE_AXIS_PERTURBATION_METRICS)
                & set(controls.PROFILE_PERTURBATION_AXES))
    ref = frozen_packets["mt_010243938"]
    _p, changed = controls_v3.profile_axis_perturbation(ref, raise_band=True)
    assert changed, "the perturbation must actually move something"
    assert {c["metric"] for c in changed} == set(
        controls_v3.PROFILE_AXIS_PERTURBATION_METRICS)
    assert all(c["id"].startswith("AWAY_") for c in changed)
    assert all(c["after"] > c["before"] for c in changed)


def test_the_perturbation_target_axis_is_actually_selectable(frozen_packets):
    """A model with evidence-driven axis selection needs a legal axis to move TO."""
    ont = availability.build_ontology(frozen_packets["mt_010243938"])
    axes = set(ont.dimensions["opponent_profile"].available_axes)
    assert controls_v3.PROFILE_AXIS_TARGET_AXES & axes


def test_the_perturbation_adds_no_note_that_would_label_the_control(frozen_packets):
    """A note saying "this was perturbed" would be an instruction, not evidence."""
    ref = frozen_packets["mt_010243938"]
    p, _ = controls_v3.profile_axis_perturbation(ref, raise_band=True)
    assert p.get("notes") == ref.get("notes")


def test_availability_ablation_withdraws_capability_and_keeps_evidence(frozen_packets):
    ref = frozen_packets["mt_010243938"]
    abl = controls_v3.availability_ablation(ref)
    assert abl["evidence"] == ref["evidence"], "evidence must be untouched"
    ont = availability.build_ontology(abl)
    assert ont.dimensions["opponent_profile"].status == availability.WITHHELD
    assert "opponent_profile" not in availability.fixture_condition_space(
        ont)["dimensions"]
    assert "opponent_profile" not in prompt_v2.build_user_message(abl, ont)


def test_context_addition_is_rejected_with_recorded_reasons():
    """The decision not to fabricate context is part of the preregistration."""
    r = controls_v3.CONTEXT_ADDITION_REJECTION
    assert r["decision"] == "REJECTED_AS_SYNTHETIC"
    assert len(r["reasons"]) >= 3
    assert "untouched frozen reference packet" in r["clean_substitute"]


# ======================================================================================
# Eligibility matrix
# ======================================================================================
def test_the_capability_matrix_gives_eligibility_aware_denominators(battery,
                                                                   frozen_packets):
    m = battery_v3.fixture_capability_matrix(battery, frozen_packets)
    assert m["n_fixtures"] == 12
    d = m["depth_denominators"]
    assert d["venue"] == 12 and d["competition"] == 12 and d["opponent_profile"] == 12
    assert d.get("own_formation_family") == 3, (
        "formation is contrastive in only 3 fixtures; the denominator must say so")
    assert "half_score_state" not in d and "period" not in d, (
        "a dimension withheld everywhere must have NO denominator, not a zero numerator")


def test_formation_denominator_matches_the_frozen_contrastive_fixture_set(battery,
                                                                         frozen_packets):
    m = battery_v3.fixture_capability_matrix(battery, frozen_packets)
    assert m["eligible_fixtures_by_dimension"]["own_formation_family"] == [
        "mt_010244193", "mt_010441320", "mt_010444904"]


def test_every_fixture_row_records_available_and_withheld_axes(battery, frozen_packets):
    m = battery_v3.fixture_capability_matrix(battery, frozen_packets)
    for row in m["per_fixture"]:
        prof = row["dimensions"]["opponent_profile"]
        assert prof["available_axes"]
        for axis in condition_contract.unresolvable_axes():
            assert axis not in prof["available_axes"]
            assert axis in prof["withheld_axes"]


# ======================================================================================
# Thresholds
# ======================================================================================
def test_every_threshold_is_fully_specified():
    for c in verdict_v3.ALL_CRITERIA:
        assert c.statement and c.numerator and c.denominator
        assert c.direction in (">=", "<=", "==")
        assert c.minimum_n > 0, f"{c.key} has no minimum N"
        assert len(c.rationale) > 40, f"{c.key} has no real rationale"
        assert c.fail_closed


def test_criterion_keys_are_unique():
    keys = [c.key for c in verdict_v3.ALL_CRITERIA]
    assert len(keys) == len(set(keys))


def test_a_criterion_below_minimum_n_scores_not_met_never_excluded():
    c = next(c for c in verdict_v3.DEPTH
             if c.key == "P1_meaningful_multi_condition_rate")
    r = c.evaluate(0.99, n=1)
    assert r["met"] is False and "below the preregistered minimum" in r["reason"]


def test_a_missing_measurement_is_not_a_pass():
    report = verdict_v3.compute({})
    assert report.verdict == verdict_v3.FAIL
    assert all(r["met"] is False for r in report.discipline)


def test_one_multi_condition_hypothesis_is_not_sufficient_for_pass():
    """Explicitly required by the design: a single lucky interaction must not pass."""
    r = verdict_v3.compute({"P1_meaningful_multi_condition_rate":
                            {"value": 1 / 144, "n": 144}})
    assert r.verdict == verdict_v3.FAIL
    assert r.depth_met == 0


def test_universal_interaction_generation_is_not_required():
    """Meeting the depth bar must be possible without conditioning everywhere."""
    r = verdict_v3.compute({
        "P1_meaningful_multi_condition_rate": {"value": 0.12, "n": 144},
        "P2_beyond_venue_condition_rate": {"value": 0.22, "n": 144},
        "P3_opponent_profile_fixture_utilization": {"value": 0.50, "n": 12},
        "P4_comparison_entropy": {"value": 0.61, "n": 144},
    })
    assert r.depth_outcome == verdict_v3.PASS
    assert r.depth_met == 4


def test_gratuitous_complexity_cannot_buy_a_pass():
    """Depth criteria met, but a restraint gate failed -> FAIL, not PASS."""
    measurements = {c.key: {"value": c.threshold, "n": max(c.minimum_n, 100)}
                    for c in verdict_v3.ALL_CRITERIA}
    measurements["R3_any_padding"] = {"value": 0.40, "n": 144}
    r = verdict_v3.compute(measurements)
    assert r.depth_outcome == verdict_v3.PASS
    assert r.verdict == verdict_v3.FAIL


def test_mixed_is_a_reachable_landing_zone():
    measurements = {c.key: {"value": c.threshold, "n": max(c.minimum_n, 100)}
                    for c in verdict_v3.DISCIPLINE + verdict_v3.RESTRAINT}
    measurements.update({
        "P1_meaningful_multi_condition_rate": {"value": 0.12, "n": 144},
        "P2_beyond_venue_condition_rate": {"value": 0.25, "n": 144},
        "P3_opponent_profile_fixture_utilization": {"value": 0.25, "n": 12},
        "P4_comparison_entropy": {"value": 0.30, "n": 144},
    })
    r = verdict_v3.compute(measurements)
    assert r.depth_met == 2
    assert r.verdict == verdict_v3.MIXED


def test_zero_tolerance_gates_are_still_zero():
    for key in ("D5_no_fabricated_evidence", "D7_numerical_authority",
                "D8_no_latent_grading", "D9_no_leakage",
                "R1_no_withheld_dimension_conditions", "R4_unsupported_data_trap"):
        c = next(c for c in verdict_v3.ALL_CRITERIA if c.key == key)
        assert c.direction == "==" and c.threshold == 0.0


def test_depth_and_restraint_are_separate_families_and_depth_is_never_a_hard_gate():
    assert {c.family for c in verdict_v3.DEPTH} == {"DEPTH"}
    assert {c.family for c in verdict_v3.RESTRAINT} == {"RESTRAINT"}
    # depth alone can never produce a PASS
    r = verdict_v3.compute({c.key: {"value": c.threshold, "n": 1000}
                            for c in verdict_v3.DEPTH})
    assert r.depth_outcome == verdict_v3.PASS and r.verdict == verdict_v3.FAIL


def test_thresholds_are_anchored_to_the_measured_v2_replay_baseline():
    b = verdict_v3.V2_REPLAY_BASELINE
    for key, base in (("P1_meaningful_multi_condition_rate",
                       b["meaningful_multi_condition_rate"]),
                      ("P2_beyond_venue_condition_rate",
                       b["beyond_venue_condition_rate"]),
                      ("P3_opponent_profile_fixture_utilization",
                       b["opponent_profile_fixture_utilization"]),
                      ("P4_comparison_entropy", b["comparison_entropy_bits"])):
        c = next(c for c in verdict_v3.DEPTH if c.key == key)
        assert c.threshold > base, f"{key}: bar must exceed the V2 baseline"


def test_the_v2_replay_meets_zero_depth_criteria():
    """The bar is a real bar: V2's recorded behaviour clears none of it."""
    b = verdict_v3.V2_REPLAY_BASELINE
    r = verdict_v3.compute({
        "P1_meaningful_multi_condition_rate": {
            "value": b["meaningful_multi_condition_rate"], "n": 132},
        "P2_beyond_venue_condition_rate": {
            "value": b["beyond_venue_condition_rate"], "n": 146},
        "P3_opponent_profile_fixture_utilization": {
            "value": b["opponent_profile_fixture_utilization"], "n": 12},
        "P4_comparison_entropy": {"value": b["comparison_entropy_bits"], "n": 146},
    })
    assert r.depth_met == 0


# ======================================================================================
# Stop rule
# ======================================================================================
def test_the_stop_rule_counts_only_schema_invalid():
    """A numerical-authority rejection is a RESULT; halting on it destroys the measurement."""
    sr = verdict_v3.STOP_RULE
    assert lifecycle.SCHEMA_INVALID in sr["numerator_definition"]
    assert lifecycle.NUMERICAL_AUTHORITY_VIOLATION in sr["numerator_definition"]
    assert "does NOT count" in sr["numerator_definition"]


def test_the_stop_rule_is_fully_frozen():
    sr = verdict_v3.STOP_RULE
    assert sr["threshold"] == 0.25
    assert sr["threshold_direction"] == ">="
    assert sr["minimum_n_before_evaluation"] == 12
    assert sr["checkpoints_after_call_number"] == [12, 24, 36, 48, 56]
    assert "16 of the 64" in sr["threshold_rationale"]
    joined = " ".join(sr["on_trip"])
    assert "DO NOT salvage" in joined
    assert "new experiment id" in joined


def test_a_tripped_stop_rule_produces_no_pass_mixed_or_fail():
    r = verdict_v3.compute({}, stop_triggered=True)
    assert r.verdict == "INFRASTRUCTURE_OR_PROMPT_FAILURE"
    assert r.verdict not in (verdict_v3.PASS, verdict_v3.MIXED, verdict_v3.FAIL)


# ======================================================================================
# Provenance and protection
# ======================================================================================
def test_the_manifest_pins_every_module_that_can_change_a_result(built):
    manifest, _ = built
    for key in ("condition_contract", "schema_v2", "availability", "firewall_v2",
                "normalize", "query_plan", "validator_v2", "evaluation_v2",
                "multicondition", "verdict_v3", "controls", "controls_v3", "prompt_v2",
                "battery_v3"):
        assert len(manifest["module_hashes"][key]) == 64, key


def test_the_manifest_records_the_full_lifecycle(built):
    manifest, _ = built
    assert manifest["lifecycle"] == [
        "manifest", "call spec", "packet hash", "serialized request", "raw response",
        "validation", "normalized intent", "compiled query plan", "evaluation", "verdict"]


def test_v2_artifacts_are_on_the_do_not_touch_list(built):
    manifest, _ = built
    joined = " ".join(manifest["artifacts_that_must_not_be_touched"])
    assert "hypothesis_v1_sonnet46_v2" in joined
    assert "V2_COUNTERFACTUAL_REPLAY_v3contract" in joined
    assert "CHAMPION_FREEZE.json" in joined


def test_the_run_writes_to_its_own_namespace(built):
    manifest, _ = built
    assert manifest["namespace_isolation"]["cache_namespace"] == "hypothesis_v3_sonnet46"
    for path in manifest["artifacts_to_be_written"]:
        assert "hypothesis_v3_sonnet46" in path


def test_leakage_audit_is_clean_on_every_planned_request(built):
    manifest, _ = built
    assert manifest["request_leakage_audit"]["status"] == "CLEAN"
    assert manifest["request_leakage_audit"]["total_findings"] == 0
    assert manifest["request_leakage_audit"]["packets_audited"] == 44


def test_the_cost_estimate_is_calibrated_against_v2s_actual_billing(built):
    manifest, _ = built
    t = manifest["token_and_cost_estimate"]
    assert t["input_token_calibration_factor"] == 1.5938
    assert t["total_input_tokens_all_calls_calibrated"] > t[
        "total_input_tokens_all_calls_chars_over_4"]
    assert t["hard_spend_ceiling_usd"] > t["p90_cost_usd"] > t["expected_cost_usd"]
    assert t["ceiling_output_tokens_per_call"] == 8192


def test_no_bedrock_client_in_any_v3_module():
    import inspect
    for module in (battery_v3, controls_v3, verdict_v3, prompt_v2):
        src = inspect.getsource(module)
        for banned in ("boto3", "invoke_model", "bedrock_client"):
            assert banned not in src, f"{module.__name__} references {banned}"


# ======================================================================================
# The WRITTEN manifest, not just the builder
# ======================================================================================
def test_the_written_manifest_on_disk_matches_the_builder(built):
    """Every other test here exercises the BUILDER. This one exercises the ARTIFACT.

    The preregistration's guarantee is that the file on disk is what gets executed, so a
    hand-edited or stale `PRESPEND_MANIFEST_sonnet46_v3.json` must fail here even though
    the builder is fine.
    """
    import hashlib
    written = json.load(open(f"{OUT}/PRESPEND_MANIFEST_sonnet46_v3.json"))
    manifest, _ = built

    # 1. the file's own hash is self-consistent
    recomputed = hashlib.sha256(json.dumps(
        {k: v for k, v in written.items() if k != "manifest_hash"},
        sort_keys=True, default=str).encode()).hexdigest()
    assert recomputed == written["manifest_hash"], "the written manifest was edited"

    # 2. and it is the hash the current code produces
    assert written["manifest_hash"] == manifest["manifest_hash"], (
        "the written manifest is stale relative to the current modules; "
        "re-run research/hypothesis_engine/_build_v3.py")

    # 3. the pinned module hashes match the modules that would actually run
    assert written["module_hashes"] == manifest["module_hashes"]
    assert written["prompt_content_hash"] == manifest["prompt_content_hash"]
    assert written["schema_content_hash"] == manifest["schema_content_hash"]
    assert written["status"] == "SONNET46_HYPOTHESIS_V3_SPEND_AUTHORIZATION_REQUIRED"
    assert written["authorization_required"] is True


def test_the_written_materialized_packets_match_the_written_call_specs():
    written = json.load(open(f"{OUT}/PRESPEND_MANIFEST_sonnet46_v3.json"))
    packets = json.load(open(f"{OUT}/MATERIALIZED_PACKETS_sonnet46_v3.json"))
    for s in written["call_specs"]:
        assert packets[s["packet_key"]]["packet_hash"] == s["resulting_packet_hash"]
        assert CP.packet_hash(packets[s["packet_key"]]) == s["resulting_packet_hash"]
