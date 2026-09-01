"""Unit tests for the named profile dimensions and reduced-profile map.

Covers the declarative specification in
``src.research.asymmetric.profile_dimensions``:

    - Exactly five attacking and five defensive named dimensions
      (Req 1.6-1.15).
    - ``gk_contribution`` does NOT *require* ``goals_prevented``; it is
      buildable from ``saves`` alone and declares ``goals_prevented`` as
      optional/unavailable (audit, Req 17.1, 17.2).
    - ``central_penetration`` is flagged reduced-confidence for the
      Championship because ``touches_in_penalty_area`` is thin there
      (Req 17.3).
    - The Broad_Corpus reduced-profile map excludes rich-only dimensions and
      derives width from corners, directness from the attacks-vs-dangerous
      ratio, and discipline from fouls and cards (Req 4.3).

Requirements: 1.6-1.15, 4.3, 17.1, 17.2, 17.3.
"""

from __future__ import annotations

from src.research.asymmetric import profile_dimensions as pd


# --- 5 + 5 named dimensions (Req 1.6-1.15) ---------------------------------


def test_five_attacking_and_five_defensive_dimensions():
    assert len(pd.ATTACKING_DIMENSIONS) == 5
    assert len(pd.DEFENSIVE_DIMENSIONS) == 5


def test_attacking_dimension_names():
    assert set(pd.ATTACKING_DIMENSIONS) == {
        "width",
        "central_penetration",
        "volume_vs_quality",
        "set_piece_reliance",
        "directness",
    }


def test_defensive_dimension_names():
    assert set(pd.DEFENSIVE_DIMENSIONS) == {
        "block_orientation",
        "aerial_vs_ground",
        "shot_suppression",
        "gk_contribution",
        "discipline",
    }


def test_every_spec_declares_its_side_and_requirement():
    for spec in pd.ATTACKING_DIMENSIONS.values():
        assert spec.side == "attacking"
        assert spec.requirement
    for spec in pd.DEFENSIVE_DIMENSIONS.values():
        assert spec.side == "defensive"
        assert spec.requirement


# --- gk_contribution: goals_prevented is optional/unavailable (Req 17.1/2) --


def test_gk_contribution_does_not_require_goals_prevented():
    gk = pd.DEFENSIVE_DIMENSIONS["gk_contribution"]
    assert "goals_prevented" not in gk.required_fields
    assert pd.requires_goals_prevented() is False


def test_gk_contribution_buildable_from_saves():
    gk = pd.DEFENSIVE_DIMENSIONS["gk_contribution"]
    # saves is the required field, so the dimension is buildable from saves alone.
    assert "saves" in gk.required_fields


def test_gk_contribution_marks_goals_prevented_optional_and_unavailable():
    gk = pd.DEFENSIVE_DIMENSIONS["gk_contribution"]
    assert "goals_prevented" in gk.optional_fields
    assert "goals_prevented" in gk.unavailable_fields
    # high_claims is the where-present enrichment.
    assert "high_claims" in gk.optional_fields


# --- central_penetration reduced-confidence for the Championship (Req 17.3) --


def test_central_penetration_flagged_reduced_confidence_for_championship():
    cp = pd.ATTACKING_DIMENSIONS["central_penetration"]
    assert "Championship" in cp.thin_in_leagues
    assert cp.is_reduced_confidence_in("Championship") is True
    assert pd.is_reduced_confidence("Championship", "central_penetration") is True


def test_central_penetration_not_reduced_confidence_elsewhere():
    assert pd.is_reduced_confidence("EPL", "central_penetration") is False


def test_reduced_confidence_flags_contains_expected_pair():
    assert ("Championship", "central_penetration") in pd.REDUCED_CONFIDENCE_FLAGS


# --- Reduced-profile map excludes rich-only dimensions (Req 4.3) -----------


def test_reduced_profile_contains_only_broad_dimensions():
    assert set(pd.REDUCED_PROFILE_DIMENSIONS) == {"width", "directness", "discipline"}


def test_reduced_profile_excludes_rich_only_dimensions():
    rich_only = {
        "central_penetration",
        "volume_vs_quality",
        "set_piece_reliance",
        "block_orientation",
        "aerial_vs_ground",
        "shot_suppression",
        "gk_contribution",
    }
    assert set(pd.RICH_ONLY_DIMENSIONS) == rich_only
    for name in rich_only:
        assert name not in pd.REDUCED_PROFILE_DIMENSIONS


def test_reduced_width_derived_from_corners():
    assert pd.source_fields("width", corpus=pd.BROAD_CORPUS) == ("corners_won",)


def test_reduced_directness_from_attacks_vs_dangerous_ratio():
    fields = pd.source_fields("directness", corpus=pd.BROAD_CORPUS)
    assert "attacks" in fields
    assert "dangerous_attacks" in fields


def test_reduced_discipline_from_fouls_and_cards():
    fields = pd.source_fields("discipline", corpus=pd.BROAD_CORPUS)
    assert "fouls_conceded" in fields
    assert "cards" in fields


# --- Sanity: required-field helpers reflect the design tables --------------


def test_width_required_fields_match_design():
    assert pd.required_source_fields("width") == (
        "accurate_crosses",
        "wide_entries",
        "corners_won",
    )
