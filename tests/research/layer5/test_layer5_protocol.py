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
