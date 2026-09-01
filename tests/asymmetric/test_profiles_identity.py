# Feature: asymmetric-matchup-engine, Property 3: Team-identity relabel-invariance and all-leagues aggregation
"""Property 3: identity relabel-invariance and all-leagues aggregation (task 3.5).

**Property 3** — relabelling a team's identity (only) yields identical profile
vectors (team identity is an aggregation key, never a feature value); and a
team's aggregated match count equals its completed-match count across ALL
leagues (history is not filtered by league).

Validates: Requirements 1.3, 1.5, 1.18, 11.4.

NOTE: ``hypothesis`` is not yet installed (task 12.1). Written here as a
deterministic ``pytest`` test over hand-built histories. Convert to
``@given(match_histories())`` with ``@settings(max_examples=100)`` in task 12.1;
the relabel and cross-league assertions map directly onto the per-example check.
"""

from __future__ import annotations

from src.research.asymmetric.profiles import TeamProfiler
from src.research.data_source import ResearchMatch


def _mk(mid: int, d: int, home: str, away: str, lid: int = 1) -> ResearchMatch:
    return ResearchMatch(
        match_id=mid, date_unix=d, league_id=lid, season="s",
        home_team=home, away_team=away, home_goals=1, away_goals=0,
        corners_home=5, corners_away=3,
        shots_on_target_home=4, shots_on_target_away=2,
        fouls_home=10, fouls_away=9,
        yellow_cards_home=1, yellow_cards_away=2,
        attacks_home=100, attacks_away=80,
        dangerous_attacks_home=40, dangerous_attacks_away=20,
    )


def _relabel(matches: list[ResearchMatch], old: str, new: str) -> list[ResearchMatch]:
    """Return a copy of matches with team ``old`` renamed to ``new`` everywhere."""
    out: list[ResearchMatch] = []
    for m in matches:
        home = new if m.home_team == old else m.home_team
        away = new if m.away_team == old else m.away_team
        # frozen dataclass -> rebuild via to_dict then construct
        d = m.to_dict()
        d["home_team"] = home
        d["away_team"] = away
        out.append(ResearchMatch(**d))
    return out


def _history() -> list[ResearchMatch]:
    # X plays across two leagues, both home and away; a 6th match to profile.
    return [
        _mk(1, 100, "X", "B", lid=1),
        _mk(2, 200, "C", "X", lid=2),
        _mk(3, 300, "X", "D", lid=1),
        _mk(4, 400, "E", "X", lid=2),
        _mk(5, 500, "X", "F", lid=1),
        _mk(6, 600, "X", "G", lid=1),  # match to profile (X home -> key +6)
    ]


def test_relabelling_identity_yields_identical_vectors():
    """Renaming X -> Q leaves X's profile vectors unchanged (identity-free, 1.3)."""
    profiler = TeamProfiler()
    matches = _history()
    relabelled = _relabel(matches, "X", "Q")

    orig = profiler.compute_profiles_map(matches)[6]        # X home in match 6
    ren = profiler.compute_profiles_map(relabelled)[6]      # Q home in match 6

    assert orig.team == "X"
    assert ren.team == "Q"                                  # only the key changed
    assert orig.attacking.vector() == ren.attacking.vector()
    assert orig.defensive.vector() == ren.defensive.vector()
    assert orig.n_history == ren.n_history
    assert orig.insufficient == ren.insufficient


def test_identity_never_appears_in_the_feature_vector():
    """The continuous vectors are pure numbers; identity is not encoded (1.3)."""
    profiler = TeamProfiler()
    tmp = profiler.compute_profiles_map(_history())[6]
    for value in tmp.attacking.vector() + tmp.defensive.vector():
        assert isinstance(value, float)


def test_all_leagues_aggregation_match_count():
    """n_history equals X's completed matches across ALL leagues (1.18, 1.5)."""
    profiler = TeamProfiler()
    matches = _history()
    # X's completed matches strictly before match 6: matches 1..5 across leagues.
    tmp = profiler.compute_profiles_map(matches)[6]
    assert tmp.n_history == 5

    # A single-league filter under-counts: limiting to league 1 keeps only
    # matches 1, 3, 5, 6; before match 6 that is 3 preceding X matches, not 5.
    league1_only = [m for m in matches if m.league_id == 1]
    tmp_l1 = profiler.compute_profiles_map(league1_only)[6]
    assert tmp_l1.n_history == 3


def test_all_leagues_count_exceeds_single_league_count():
    """Cross-league aggregation strictly includes matches a league filter drops."""
    profiler = TeamProfiler()
    matches = _history()
    all_leagues = profiler.compute_profiles_map(matches)[6].n_history

    league1_only = [m for m in matches if m.league_id == 1]
    single = profiler.compute_profiles_map(league1_only)[6].n_history

    assert all_leagues == 5
    assert single < all_leagues  # league-2 matches were correctly aggregated too
