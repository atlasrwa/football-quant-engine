import json
from pathlib import Path

from src.research.dataset.manifest import sha256_json
from src.research.layer5.protocol import (
    LAYER5_PROTOCOL_HASH,
    protocol_v1,
)


def test_protocol_hash_matches_frozen_evidence():
    d = protocol_v1()
    assert sha256_json(d) == LAYER5_PROTOCOL_HASH
    artifact = json.loads(
        Path("evidence/layer5/QFE_LAYER5_PROTOCOL_V1.json").read_text()
    )
    assert artifact["protocol_hash"] == LAYER5_PROTOCOL_HASH
    assert {
        key: value for key, value in artifact.items() if key != "protocol_hash"
    } == d


def test_protected_and_p_model_boundaries_are_hard():
    b = protocol_v1()["scientific_boundary"]
    assert b["protected_outcomes_allowed_before_policy_freeze"] is False
    assert b["protected_market_relative_scoring_allowed_before_policy_freeze"] is False
    assert b["market_prices_may_modify_p_model"] is False
    assert b["market_prices_may_modify_layer4_calibration"] is False
    assert b["disagreement_policy_tuning_on_protected"] is False


def test_market_scope_matches_frozen_layer4_capabilities():
    s = protocol_v1()["initial_market_scope"]
    assert s["GOALS_TOTAL"]["lines"] == [2.5]
    assert s["GOALS_TOTAL"]["surface_mode"] == "SINGLE_LINE_ONLY"
    assert s["CORNERS_SIDE"]["lines"] == [2.5, 3.5, 4.5, 5.5, 6.5, 7.5]
    assert s["CORNERS_SIDE"]["roles"] == ["HOME", "AWAY"]
    assert s["CORNERS_TOTAL"]["lines"] == [7.5, 8.5, 9.5, 10.5, 11.5, 12.5]
    assert s["bookings"] == "UNSUPPORTED_IN_LAYER5_V1"


def test_market_horizon_is_point_in_time_and_fail_closed():
    h = protocol_v1()["market_horizon"]
    assert h["target_seconds_before_kickoff"] == 21600
    assert h["future_quotes_forbidden"] is True
    assert h["same_bookmaker_required"] is True
    assert h["cross_book_blending_forbidden"] is True
    assert h["timestamp_provenance_required"] is True
    assert h["reconstructed_or_unproven_quote_time"] == "ABSTAIN"


def test_devig_method_is_preregistered_and_not_cherry_picked():
    d = protocol_v1()["no_vig"]
    assert d["primary_method"] == "MULTIPLICATIVE_PROPORTIONAL"
    assert d["sensitivity_method"] == "SHIN_DIAGNOSTIC_ONLY"
    assert d["method_cherry_pick_forbidden"] is True
    assert d["two_sided_quote_required"] is True


def test_market_surface_repair_is_bounded_and_raw_quotes_are_preserved():
    s = protocol_v1()["market_surface"]
    assert s["minimum_adjacent_lines"] == 3
    assert s["coherence_repair"] == "equal_weight_isotonic_projection_non_increasing"
    assert s["raw_quotes_always_preserved"] is True
    assert s["max_abs_isotonic_adjustment"] == 0.03
    assert s["max_mean_abs_isotonic_adjustment"] == 0.01
    assert "NOT_REPORTED" in s["implied_mean"]


def test_disagreement_policy_cannot_rank_by_maximum_gap():
    d = protocol_v1()["disagreement_policy"]
    l = protocol_v1()["line_selection"]
    assert d["minimum_selected_line_absolute_gap"] == 0.05
    assert d["surface_supporting_line_absolute_gap"] == 0.03
    assert d["surface_min_adjacent_corroborating_lines"] == 2
    assert d["rank_by_gap_forbidden"] is True
    assert d["larger_gap_not_automatically_better"] is True
    assert l["maximum_gap_is_never_a_selection_tiebreaker"] is True
    assert any("closest to 0.50" in step for step in l["surface_algorithm"])


def test_reliability_adjusted_gap_is_not_a_fake_fixture_confidence_interval():
    g = protocol_v1()["model_support_gate"]
    assert g["calibration_bin_min_unique_fixtures"] == 30
    assert g["calibration_reliability_band_required"] is True
    assert g["hard_ood_flags_allowed"] is False
    assert g["component_gap_ood_allowed"] is False
    assert "NOT a fixture probability confidence bound" in g["reliability_adjusted_gap_definition"]
    assert g["minimum_reliability_adjusted_gap"] == 0.02


def test_market_only_calibration_cannot_replace_primary_market_probability():
    b = protocol_v1()["market_only_benchmark"]
    assert b["primary"] == "unmodified primary no-vig probability"
    challenger = b["optional_calibrated_challenger"]
    assert challenger["candidates"] == ["IDENTITY", "PLATT_GLOBAL"]
    assert "never replaces primary no-vig p_market" in challenger["role_in_disagreement_policy"]


def test_protected_open_requires_full_layer5_freeze():
    requirements = protocol_v1()["protected_evaluation"]["may_open_only_after"]
    assert "Layer5 protocol committed" in requirements
    assert "market-surface implementation tests pass" in requirements
    assert "disagreement/abstention/line-selection implementation freeze committed" in requirements
    assert "matched-market manifest frozen" in requirements
    assert "exact-state repository integrity audit passes" in requirements


def test_v1_1_repairs_bookmaker_selection_without_opening_protected():
    from src.research.layer5.protocol import (
        LAYER5_PROTOCOL_V1_1_HASH,
        protocol_active,
        protocol_v1_1,
    )
    d = protocol_v1_1()
    assert d != protocol_active()
    assert sha256_json(d) == LAYER5_PROTOCOL_V1_1_HASH
    assert d["supersedes"]["status"] == "ABORTED_PRE_PROTECTED_DESIGN_DEFECT"
    assert d["bookmaker_selection"]["hierarchy"] == [
        "pinnacle", "bet365", "betmgm-uk", "paddy-power"
    ]
    assert "never fall through" in d["bookmaker_selection"]["algorithm"][-1]
    assert d["market_source"]["fallback_sources_allowed"] is False
    assert d["market_source"]["registered_concept_mapping"]["CORNERS_SIDE"].startswith("UNSUPPORTED")


def test_v1_1_evidence_matches_active_protocol():
    from src.research.layer5.protocol import LAYER5_PROTOCOL_V1_1_HASH, protocol_v1_1
    artifact = json.loads(Path("evidence/layer5/QFE_LAYER5_PROTOCOL_V1_1.json").read_text())
    assert artifact["protocol_hash"] == LAYER5_PROTOCOL_V1_1_HASH
    assert {k: v for k, v in artifact.items() if k != "protocol_hash"} == protocol_v1_1()


def test_v1_2_is_active_and_binds_certified_layer4_v3():
    from src.research.layer5.protocol import (
        LAYER5_PROTOCOL_V1_2_HASH,
        active_protocol_hash,
        protocol_active,
        protocol_v1_2,
    )
    d=protocol_v1_2()
    assert protocol_active()==d
    assert active_protocol_hash()==LAYER5_PROTOCOL_V1_2_HASH
    assert sha256_json(d)==LAYER5_PROTOCOL_V1_2_HASH
    assert d["bindings"]["layer4_model_freeze_hash"]=="bce2cbdb6fd3ecf1d664439116d1666b9fc4b4172c2838bf29428d07d2713bd2"
    assert d["bindings"]["layer4_v3_certification_hash"]=="1a0e34e1473b22088b9d9340393034a2e2f829ad93790afbbd5f66bb7c560503"


def test_v1_2_preserves_v1_1_numeric_market_policy_exactly():
    from src.research.layer5.protocol import protocol_v1_1, protocol_v1_2
    old=protocol_v1_1(); new=protocol_v1_2()
    keys=(
        "market_horizon","no_vig","market_surface","model_support_gate",
        "disagreement_policy","line_selection","bookmaker_selection","market_only_benchmark",
    )
    for key in keys:
        assert new[key]==old[key]
    assert new["frozen_numeric_policy_fingerprint"]=="0871ae9c1eb92d858b5f11551b339959e63870b52a1c936069236eb493ef5e51"


def test_v1_2_requires_new_future_cohort_and_retires_legacy_317():
    from src.research.layer5.protocol import protocol_v1_2
    d=protocol_v1_2()
    e=d["prospective_evaluation"]
    assert e["legacy_317_status"]=="EXPOSED_DIAGNOSTIC_ONLY_NOT_A_FINAL_HOLDOUT"
    assert any("new future prospective cohort" in x for x in e["may_open_outcomes_only_after"])
    assert d["scientific_boundary"]["legacy_317_outcomes_or_market_relative_scores_for_final_validation_forbidden"] is True


def test_v1_2_corner_bookmaker_comparison_is_fail_closed():
    from src.research.layer5.protocol import protocol_v1_2
    d=protocol_v1_2()
    assert d["initial_market_scope"]["GOALS_TOTAL"]["market_comparison_eligible"] is True
    assert d["initial_market_scope"]["CORNERS_TOTAL"]["market_comparison_eligible"] is False
    assert d["initial_market_scope"]["CORNERS_SIDE"]["market_comparison_eligible"] is False
    assert d["market_source"]["registered_concept_mapping"]["CORNERS_TOTAL"].startswith("UNVERIFIED")
    assert "SETTLEMENT_SEMANTICS_UNVERIFIED" in d["abstention_reason_codes"]


def test_v1_2_evidence_matches_frozen_protocol():
    from src.research.layer5.protocol import LAYER5_PROTOCOL_V1_2_HASH, protocol_v1_2
    artifact=json.loads(Path("evidence/layer5/QFE_LAYER5_PROTOCOL_V1_2.json").read_text())
    assert artifact["protocol_hash"]==LAYER5_PROTOCOL_V1_2_HASH
    assert {k:v for k,v in artifact.items() if k!="protocol_hash"}==protocol_v1_2()
