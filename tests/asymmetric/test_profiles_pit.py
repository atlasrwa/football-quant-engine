# Feature: asymmetric-matchup-engine, Property 2: Point-in-time invariance
"""Property 2: Point-in-time invariance of the Team_Profiler (task 3.4).

**Property 2: Point-in-time invariance** — for any match M, the profile computed
for M is identical whether or not later matches are present. Equivalently, the
profile for M built from the *full* history equals the profile built from the
history truncated strictly before M.

Validates: Requirements 1.4, 6.5, 11.1, 11.3.

NOTE: ``hypothesis`` is not yet installed (added as a dev dependency in task
12.1). This is therefore written as a deterministic ``pytest`` test over
hand-built histories that exercise the same invariant a Hypothesis strategy
would. When task 12.1 lands, convert this to a ``@given(match_histories())``
property test with ``@settings(max_examples=100)`` — the assertions below map
directly onto the per-example check.
"""

from __future__ import annotations

from src.research.asymmetric.models import TeamMatchProfiles
from src.research.asymmetric.profiles import TeamProfiler
from src.research.data_source import ResearchMatch


def _mk(mid: int, d: int, home: str, away: str, hg: int, ag: int, **kw) -> ResearchMatch:
    base = dict(
        corners_home=kw.get("ch", 5),
        corners_away=kw.get("ca", 4),
        shots_on_target_home=kw.get("soth", 4),
        shots_on_target_away=kw.get("sota", 3),
        fouls_home=kw.get("fh", 10),
        fouls_away=kw.get("fa", 11),
        yellow_cards_home=kw.get("yh", 1),
        yellow_cards_away=kw.get("ya", 2),
        attacks_home=kw.get("ath", 100),
        attacks_away=kw.get("ata", 90),
        dangerous_attacks_home=kw.get("dah", 40),
        dangerous_attacks_away=kw.get("daa", 30),
    )
    return ResearchMatch(
        match_id=mid, date_unix=d, league_id=kw.get("lid", 1), season="s",
        home_team=home, away_team=away, home_goals=hg, away_goals=ag, **base,
    )


def _profiles_equal(a: TeamMatchProfiles, b: TeamMatchProfiles) -> bool:
    return (
        a.team == b.team
        and a.n_history == b.n_history
        and a.insufficient == b.insufficient
        and a.attacking.vector() == b.attacking.vector()
        and a.defensive.vector() == b.defensive.vector()
    )


def _history() -> list[ResearchMatch]:
    """A chronological history where team X appears home and away, mixed leagues."""
    return [
        _mk(1, 100, "X", "B", 2, 1, ch=5, ca=3),
        _mk(2, 200, "C", "X", 0, 0, ch=4, ca=6),
        _mk(3, 300, "X", "D", 1, 1, ch=7, ca=2, lid=2),
        _mk(4, 400, "E", "X", 3, 2, ch=2, ca=8),
        _mk(5, 500, "X", "F", 0, 2, ch=3, ca=5, lid=2),
        _mk(6, 600, "G", "X", 2, 2, ch=6, ca=4),
        _mk(7, 700, "X", "H", 1, 0, ch=8, ca=1),
    ]


def test_profile_for_M_unchanged_by_presence_of_later_matches():
    """Truncating history strictly before M yields the identical profile for M."""
    profiler = TeamProfiler()
    matches = _history()

    for cut in range(1, len(matches)):
        target = matches[cut]  # match M
        full_map = profiler.compute_profiles_map(matches)
        # History strictly before M (all earlier matches) plus M itself, so M is
        # present in both runs but no *later* match is in the truncated run.
        truncated = matches[: cut + 1]
        trunc_map = profiler.compute_profiles_map(truncated)

        # Home-team profile for M is keyed by +match_id, away by -match_id.
        for key in (target.match_id, -target.match_id):
            assert _profiles_equal(full_map[key], trunc_map[key]), (
                f"profile for match {target.match_id} (key {key}) changed when "
                "later matches were added"
            )


def test_profile_for_team_at_matches_map_value():
    """The CLI path (profile_for_team_at) equals the map value for the same M."""
    profiler = TeamProfiler()
    matches = _history()
    full_map = profiler.compute_profiles_map(matches)

    # For match 5, X is the home team -> keyed by +5.
    m5 = matches[4]
    at = profiler.profile_for_team_at("X", m5.date_unix, matches)
    from_map = full_map[m5.match_id]
    assert at.attacking.vector() == from_map.attacking.vector()
    assert at.defensive.vector() == from_map.defensive.vector()
    assert at.n_history == from_map.n_history


def test_appending_future_match_does_not_alter_earlier_profile():
    """A concrete leak check: adding a much-later match cannot alter match 3."""
    profiler = TeamProfiler()
    base = _history()[:3]  # matches 1..3
    m3_key = base[2].match_id

    before = profiler.compute_profiles_map(base)[m3_key]
    with_future = base + [
        _mk(99, 9_999, "X", "Z", 5, 0, ch=9, ca=9),  # far-future match
    ]
    after = profiler.compute_profiles_map(with_future)[m3_key]
    assert _profiles_equal(before, after)
