"""Edge-case unit tests for the Team_Profiler (task 3.7).

Covers:
  * the min-history *insufficient* boundary: exactly 4 completed matches is
    insufficient, exactly 5 is sufficient (Req 1.16); and
  * the reduced-profile dimension set for the Broad_Corpus contains only
    ``{width, directness, discipline}`` as populated dimensions, with rich-only
    dimensions emitted as not-populated/absent (Req 4.3).

Requirements: 1.16, 4.3.
"""

from __future__ import annotations

from src.research.asymmetric import profile_dimensions as pdims
from src.research.asymmetric.profiles import TeamProfiler
from src.research.data_source import ResearchMatch


def _mk(mid: int, d: int, home: str, away: str, **kw) -> ResearchMatch:
    return ResearchMatch(
        match_id=mid, date_unix=d, league_id=1, season="s",
        home_team=home, away_team=away, home_goals=1, away_goals=0,
        corners_home=5, corners_away=4,
        shots_on_target_home=4, shots_on_target_away=3,
        fouls_home=10, fouls_away=9,
        yellow_cards_home=1, yellow_cards_away=2,
        attacks_home=100, attacks_away=80,
        dangerous_attacks_home=40, dangerous_attacks_away=20,
    )


def _history_of_length(n: int) -> list[ResearchMatch]:
    """n completed X matches followed by a target match (X home in target)."""
    matches = [_mk(i + 1, (i + 1) * 100, "X", f"O{i}", ) for i in range(n)]
    matches.append(_mk(1000, 10_000, "X", "TARGET"))
    return matches


# --- min-history insufficient boundary (Req 1.16) --------------------------


def test_exactly_four_completed_matches_is_insufficient():
    profiler = TeamProfiler(min_history=5)
    matches = _history_of_length(4)
    tmp = profiler.compute_profiles_map(matches)[1000]
    assert tmp.n_history == 4
    assert tmp.insufficient is True


def test_exactly_five_completed_matches_is_sufficient():
    profiler = TeamProfiler(min_history=5)
    matches = _history_of_length(5)
    tmp = profiler.compute_profiles_map(matches)[1000]
    assert tmp.n_history == 5
    assert tmp.insufficient is False


def test_boundary_is_strict_less_than_min_history():
    """Sanity: 0..4 insufficient, 5+ sufficient with default min_history=5."""
    profiler = TeamProfiler(min_history=5)
    for n, expect_insufficient in [(0, True), (3, True), (4, True), (5, False), (6, False)]:
        matches = _history_of_length(n)
        tmp = profiler.compute_profiles_map(matches)[1000]
        assert tmp.n_history == n
        assert tmp.insufficient is expect_insufficient


# --- reduced-profile dimension set for the Broad_Corpus (Req 4.3) ----------


def test_reduced_profile_populates_only_width_directness_discipline():
    """In reduced mode only the three broad dimensions carry populated values."""
    profiler = TeamProfiler(reduced=True, min_history=1)
    matches = _history_of_length(3)
    tmp = profiler.compute_profiles_map(matches)[1000]

    populated = set()
    for name in ("width", "central_penetration", "volume_vs_quality",
                 "set_piece_reliance", "directness"):
        if getattr(tmp.attacking, name).n_matches_used > 0:
            populated.add(name)
    for name in ("block_orientation", "aerial_vs_ground", "shot_suppression",
                 "gk_contribution", "discipline"):
        if getattr(tmp.defensive, name).n_matches_used > 0:
            populated.add(name)

    assert populated == {"width", "directness", "discipline"}


def test_reduced_profile_marks_rich_only_dimensions_absent():
    """Rich-only dimensions in a reduced profile are absent (all fields missing)."""
    profiler = TeamProfiler(reduced=True, min_history=1)
    tmp = profiler.compute_profiles_map(_history_of_length(3))[1000]

    for name in pdims.RICH_ONLY_DIMENSIONS:
        dim = getattr(tmp.attacking, name, None) or getattr(tmp.defensive, name)
        assert dim.n_matches_used == 0
        # All the dimension's required fields are recorded as missing/absent.
        for f in pdims.get_dimension(name).required_fields:
            assert f in dim.missing_fields


def test_reduced_flag_carried_on_profiles():
    """Emitted profiles carry reduced=True so reporting can compare rich vs broad (Req 4.5)."""
    profiler = TeamProfiler(reduced=True, min_history=1)
    tmp = profiler.compute_profiles_map(_history_of_length(3))[1000]
    assert tmp.attacking.reduced is True
    assert tmp.defensive.reduced is True


def test_non_reduced_flag_default_false():
    profiler = TeamProfiler(min_history=1)
    tmp = profiler.compute_profiles_map(_history_of_length(3))[1000]
    assert tmp.attacking.reduced is False
    assert tmp.defensive.reduced is False
