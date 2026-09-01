"""Unit tests for the Asymmetric Matchup Engine pydantic data models.

Covers:
    - Frozen immutability: mutating any model field raises.
    - ``vector()`` ordering and length for both profiles (length == 5).
    - ``Estimate.spans_zero`` / ``Estimate.is_result`` boundary behaviour,
      including a CI that exactly touches zero (counts as spanning).

Requirements: 1.2, 10.8, 10.9.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.research.asymmetric.models import (
    AttackingProfile,
    DefensiveProfile,
    Estimate,
    ProfileDimension,
    TeamMatchProfiles,
)


def _dim(name: str, value: float) -> ProfileDimension:
    return ProfileDimension(
        name=name,
        value=value,
        source_fields=("f1", "f2"),
        n_matches_used=7,
    )


def _attacking() -> AttackingProfile:
    return AttackingProfile(
        team="Leeds",
        as_of_unix=1_700_000_000,
        width=_dim("width", 1.0),
        central_penetration=_dim("central_penetration", 2.0),
        volume_vs_quality=_dim("volume_vs_quality", 3.0),
        set_piece_reliance=_dim("set_piece_reliance", 4.0),
        directness=_dim("directness", 5.0),
    )


def _defensive() -> DefensiveProfile:
    return DefensiveProfile(
        team="Leeds",
        as_of_unix=1_700_000_000,
        block_orientation=_dim("block_orientation", 10.0),
        aerial_vs_ground=_dim("aerial_vs_ground", 20.0),
        shot_suppression=_dim("shot_suppression", 30.0),
        gk_contribution=_dim("gk_contribution", 40.0),
        discipline=_dim("discipline", 50.0),
    )


# --- Frozen immutability (Req 1.2 value-object discipline) -----------------


def test_profile_dimension_is_frozen():
    dim = _dim("width", 1.0)
    with pytest.raises(ValidationError):
        dim.value = 2.0


def test_attacking_profile_is_frozen():
    profile = _attacking()
    with pytest.raises(ValidationError):
        profile.team = "Norwich"


def test_defensive_profile_is_frozen():
    profile = _defensive()
    with pytest.raises(ValidationError):
        profile.reduced = True


def test_team_match_profiles_is_frozen():
    tmp = TeamMatchProfiles(
        team="Leeds",
        n_history=7,
        insufficient=False,
        attacking=_attacking(),
        defensive=_defensive(),
    )
    with pytest.raises(ValidationError):
        tmp.insufficient = True


def test_estimate_is_frozen():
    est = Estimate(point=1.0, ci_low=0.5, ci_high=1.5)
    with pytest.raises(ValidationError):
        est.point = 2.0


# --- vector() ordering and length (Req 1.2) --------------------------------


def test_attacking_vector_order_and_length():
    profile = _attacking()
    vec = profile.vector()
    assert vec == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert len(vec) == 5


def test_defensive_vector_order_and_length():
    profile = _defensive()
    vec = profile.vector()
    assert vec == [10.0, 20.0, 30.0, 40.0, 50.0]
    assert len(vec) == 5


def test_vector_excludes_team_identity():
    # Two profiles differing only by team identity produce identical vectors.
    a = _attacking()
    b = AttackingProfile(
        team="A_DIFFERENT_TEAM",
        as_of_unix=a.as_of_unix,
        width=a.width,
        central_penetration=a.central_penetration,
        volume_vs_quality=a.volume_vs_quality,
        set_piece_reliance=a.set_piece_reliance,
        directness=a.directness,
    )
    assert a.vector() == b.vector()


# --- Estimate.spans_zero / is_result boundary behaviour (Req 10.9) ---------


def test_estimate_ci_strictly_above_zero_is_result():
    est = Estimate(point=0.5, ci_low=0.1, ci_high=0.9)
    assert est.spans_zero is False
    assert est.is_result is True


def test_estimate_ci_strictly_below_zero_is_result():
    est = Estimate(point=-0.5, ci_low=-0.9, ci_high=-0.1)
    assert est.spans_zero is False
    assert est.is_result is True


def test_estimate_ci_straddling_zero_spans():
    est = Estimate(point=0.1, ci_low=-0.2, ci_high=0.4)
    assert est.spans_zero is True
    assert est.is_result is False


def test_estimate_ci_low_exactly_zero_spans():
    # Closed interval: touching zero at the lower bound counts as spanning.
    est = Estimate(point=0.5, ci_low=0.0, ci_high=1.0)
    assert est.spans_zero is True
    assert est.is_result is False


def test_estimate_ci_high_exactly_zero_spans():
    # Closed interval: touching zero at the upper bound counts as spanning.
    est = Estimate(point=-0.5, ci_low=-1.0, ci_high=0.0)
    assert est.spans_zero is True
    assert est.is_result is False


def test_estimate_degenerate_ci_at_zero_spans():
    est = Estimate(point=0.0, ci_low=0.0, ci_high=0.0)
    assert est.spans_zero is True
    assert est.is_result is False
