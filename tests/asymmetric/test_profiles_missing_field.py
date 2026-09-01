# Feature: asymmetric-matchup-engine, Property 11: Missing-field exclusion
"""Property 11: Missing-field exclusion in the Team_Profiler (task 3.6).

**Property 11** — each affected feature is computed only from the matches whose
required field is present, and equals the feature over exactly that subset; the
absent field is recorded in the dimension's ``missing_fields`` (Req 1.17).

Validates: Requirements 1.17.

NOTE: ``hypothesis`` is not yet installed (task 12.1). Written as a
deterministic ``pytest`` test that plants ``None`` in a required raw field for a
subset of matches and checks the surviving-subset mean and the recorded missing
field. Convert to ``@given(match_histories())`` with ``@settings(max_examples=100)``
in task 12.1; the subset-mean and ``missing_fields`` assertions carry over.
"""

from __future__ import annotations

from src.research.asymmetric.profiles import TeamProfiler
from src.research.data_source import ResearchMatch


def _mk(mid: int, d: int, home: str, away: str, *, ch=5, ca=4, soth=4, sota=3) -> ResearchMatch:
    return ResearchMatch(
        match_id=mid, date_unix=d, league_id=1, season="s",
        home_team=home, away_team=away, home_goals=1, away_goals=0,
        corners_home=ch, corners_away=ca,
        shots_on_target_home=soth, shots_on_target_away=sota,
        fouls_home=10, fouls_away=9,
        yellow_cards_home=1, yellow_cards_away=1,
    )


def test_width_excludes_matches_missing_corners_and_records_field():
    """A match with corners=None is excluded from width; width = mean over present."""
    profiler = TeamProfiler(min_history=1)
    # X is home in every match here for simplicity; width reads corners_home.
    matches = [
        _mk(1, 100, "X", "B", ch=6),
        _mk(2, 200, "X", "C", ch=None),   # missing required corners -> excluded
        _mk(3, 300, "X", "D", ch=10),
        _mk(4, 400, "X", "E", ch=2),      # target match (X home -> key +4)
    ]
    tmp = profiler.compute_profiles_map(matches)[4]
    width = tmp.attacking.width

    # Present corners before match 4: matches 1 (6) and 3 (10); match 2 excluded.
    assert width.n_matches_used == 2
    assert width.value == (6 + 10) / 2
    # The excluded required field is recorded.
    assert "corners_won" in width.missing_fields


def test_feature_over_subset_equals_direct_subset_mean():
    """width equals the mean over exactly the present-field subset (Property 11)."""
    profiler = TeamProfiler(min_history=1)
    corners = [3, None, 7, None, 5]
    matches = [
        _mk(i + 1, (i + 1) * 100, "X", f"O{i}", ch=c) for i, c in enumerate(corners)
    ]
    # profile the 6th match so all five precede it
    matches.append(_mk(6, 600, "X", "Z", ch=1))
    tmp = profiler.compute_profiles_map(matches)[6]
    width = tmp.attacking.width

    present = [c for c in corners if c is not None]  # [3, 7, 5]
    assert width.n_matches_used == len(present)
    assert width.value == sum(present) / len(present)


def test_all_missing_yields_not_populated_default():
    """When no match has the required field, the dimension is a transparent 0.0."""
    profiler = TeamProfiler(min_history=1)
    matches = [
        _mk(1, 100, "X", "B", ch=None),
        _mk(2, 200, "X", "C", ch=None),
        _mk(3, 300, "X", "D", ch=1),  # target
    ]
    tmp = profiler.compute_profiles_map(matches)[3]
    width = tmp.attacking.width
    assert width.n_matches_used == 0
    assert width.value == 0.0
    # Every required field recorded as missing (nothing derivable).
    for f in ("accurate_crosses", "wide_entries", "corners_won"):
        assert f in width.missing_fields


def test_missing_field_affects_only_that_feature():
    """Excluding a match from width does not shrink an unrelated feature's count."""
    profiler = TeamProfiler(min_history=1)
    matches = [
        _mk(1, 100, "X", "B", ch=6, soth=4),
        _mk(2, 200, "X", "C", ch=None, soth=8),  # width excludes; SOT keeps it
        _mk(3, 300, "X", "D", ch=10, soth=2),
        _mk(4, 400, "X", "E", ch=1, soth=1),     # target
    ]
    tmp = profiler.compute_profiles_map(matches)[4]
    # width used 2 matches (1,3); volume_vs_quality (SOT) used all 3 (1,2,3).
    assert tmp.attacking.width.n_matches_used == 2
    assert tmp.attacking.volume_vs_quality.n_matches_used == 3
