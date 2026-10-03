from src.research.evaluation.structured_oof import STRUCTURED_OOF_VERSION
from src.research.models.dynamic_count_strength import DynamicCountConfig
from src.research.models.structured_distributions import (
    nb2_total_pmf_from_sides,
    nb2_total_under_probability_from_sides,
)


def test_structured_oof_version_is_explicit():
    assert STRUCTURED_OOF_VERSION == "qfe-layer3-structured-oof-v2"


def test_selected_target_configs_are_distinct_by_contract():
    goals = DynamicCountConfig(
        half_life_days=360.0,
        team_influence=1.0,
        team_comp_prior_weight=4.0,
    )
    corners = DynamicCountConfig(
        half_life_days=180.0,
        team_influence=1.0,
        team_comp_prior_weight=4.0,
    )
    assert goals.identity_hash != corners.identity_hash


def test_side_nb2_total_distribution_is_coherent():
    alpha = 0.1
    mass = sum(
        nb2_total_pmf_from_sides(total, 5.0, 4.0, alpha)
        for total in range(60)
    )
    assert abs(mass - 1.0) < 1e-8
    under = nb2_total_under_probability_from_sides(
        9.5, 5.0, 4.0, alpha
    )
    expected = sum(
        nb2_total_pmf_from_sides(total, 5.0, 4.0, alpha)
        for total in range(10)
    )
    assert abs(under - expected) < 1e-12
