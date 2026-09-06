"""Early-season feature discipline for the stat-mixer (failure ledger F026).

A rolling "recent form" window must describe the CURRENT season. Before this fix the
feature builder drew each team's window from a history that was never reset at the
season boundary, so a team early in a new season had its w5/w10 window silently
filled with prior-season matches — a "form" feature that was mostly last season's
squad, presented as current form. That is the same class of error as the stale
corpus it followed.

These tests pin the fixed behaviour on synthetic histories (no corpus on disk
needed):

* a window never draws from a prior season-instance;
* a fixed window (w5/w10) abstains rather than backfill when the current season
  cannot fill it;
* the season-to-date window is genuinely current-season-to-date, gated at the
  declared minimum;
* the per-fixture provenance states each team's current-season match count and which
  windows applied, so a 3-match forecast is distinguishable from a 10-match one.
"""

import sys

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

import pilotC_stat_mixer as mix


DAY = 86400


def _match(mid, comp, season, kickoff, home, away, *, shots_home, shots_away):
    """A minimal completed corpus row carrying the fields roll()/features read."""
    return {
        "id": mid,
        "competition_id": comp,       # per-season id -> season-instance key
        "season": season,             # human label, reporting only
        "date_unix": kickoff,
        "home_name": home,
        "away_name": away,
        "status": "complete",
        "team_a_shots": shots_home,
        "team_b_shots": shots_away,
    }


def _history_for_team(team, prior_n, current_n, *, prior_comp="1000",
                      current_comp="2000", base=1_700_000_000):
    """Build a corpus where ``team`` has ``prior_n`` prior-season and ``current_n``
    current-season completed matches, all at home for simplicity."""
    rows = []
    t = base
    for i in range(prior_n):
        rows.append(_match(f"p{i}", prior_comp, "2025/2026", t, team, f"Opp{i}",
                           shots_home=10.0, shots_away=8.0))
        t += DAY
    # a clear gap, then the new season
    t += 60 * DAY
    for i in range(current_n):
        rows.append(_match(f"c{i}", current_comp, "2026/2027", t, team, f"New{i}",
                           shots_home=20.0, shots_away=6.0))
        t += DAY
    return rows, t + DAY  # (matches, a 'before' after the last current match)


def test_window_never_draws_from_prior_season():
    rows, before = _history_for_team("Arsenal", prior_n=76, current_n=2)
    hist = mix.build_histories(rows)
    # current-season key is the new season, count is 2
    assert mix.current_season_key(hist, "Arsenal", before) == "2000"
    assert mix.current_season_match_count(hist, "Arsenal", before) == 2
    # w5 / w10 cannot be filled from 2 current matches -> abstain, NOT backfilled to
    # the prior-season value of 10.0
    assert mix.roll(hist, "Arsenal", "shots", "for", 5, before) is None
    assert mix.roll(hist, "Arsenal", "shots", "for", 10, before) is None
    # season-to-date also abstains below the minimum-history floor
    assert mix.roll(hist, "Arsenal", "shots", "for", None, before) is None


def test_std_window_is_current_season_only():
    rows, before = _history_for_team("Coventry", prior_n=90, current_n=3)
    hist = mix.build_histories(rows)
    # 3 current matches clears the min-3 floor; the mean is the CURRENT value (20.0),
    # never blended with the prior-season 10.0
    val = mix.roll(hist, "Coventry", "shots", "for", None, before)
    assert val == 20.0


def test_full_window_uses_only_current_season_when_available():
    rows, before = _history_for_team("Leeds", prior_n=40, current_n=12)
    hist = mix.build_histories(rows)
    # w10 is now fillable from the current season alone -> current value, no prior
    assert mix.roll(hist, "Leeds", "shots", "for", 10, before) == 20.0
    assert mix.current_season_match_count(hist, "Leeds", before) == 12


def test_brand_new_team_with_no_prior_still_abstains_on_full_window():
    rows, before = _history_for_team("Castellon", prior_n=0, current_n=3)
    hist = mix.build_histories(rows)
    assert mix.roll(hist, "Castellon", "shots", "for", 5, before) is None
    # but season-to-date is available at 3
    assert mix.roll(hist, "Castellon", "shots", "for", None, before) == 20.0


def test_history_provenance_marks_min_gate_and_windows():
    home_rows, before_home = _history_for_team("Arsenal", prior_n=76, current_n=2,
                                               current_comp="2000")
    away_rows, before_away = _history_for_team("Chelsea", prior_n=76, current_n=8,
                                               current_comp="2001", base=1_700_100_000)
    hist = mix.build_histories(home_rows + away_rows)
    before = max(before_home, before_away)
    prov = mix.history_provenance(hist, "Arsenal", "Chelsea", before)
    assert prov["min_current_season_matches"] == mix.MIN_CURRENT_SEASON_MATCHES == 3
    assert prov["home"]["current_season_matches"] == 2
    assert prov["home"]["meets_min_history"] is False
    assert prov["away"]["current_season_matches"] == 8
    assert prov["away"]["meets_min_history"] is True
    # a fixture is only "sufficient" when BOTH teams clear the floor
    assert prov["sufficient"] is False
    # window labels: Arsenal (2 matches) abstains on every window; Chelsea (8) has
    # w5 populated but w10 abstain
    assert prov["home"]["windows"]["w5"] == "abstain"
    assert prov["home"]["windows"]["std"] == "abstain"
    assert prov["away"]["windows"]["w5"] == "populated"
    assert prov["away"]["windows"]["w10"] == "abstain"
    assert prov["away"]["windows"]["std"] == "populated"


def test_sufficient_when_both_teams_clear_the_floor():
    home_rows, before_home = _history_for_team("Leeds", prior_n=0, current_n=4,
                                               current_comp="3000")
    away_rows, before_away = _history_for_team("Burnley", prior_n=0, current_n=5,
                                               current_comp="3001", base=1_700_200_000)
    hist = mix.build_histories(home_rows + away_rows)
    before = max(before_home, before_away)
    prov = mix.history_provenance(hist, "Leeds", "Burnley", before)
    assert prov["sufficient"] is True
