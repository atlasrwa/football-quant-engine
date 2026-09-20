"""Leakage / temporal-integrity / orientation tests for the matchup research layer.

These are the load-bearing correctness guarantees. Run with the repo venv:
    .venv/bin/python -m pytest tests/research/test_matchup_leakage.py -q
"""
import math
import sys

import numpy as np
import pytest

from src.research.matchup.corpus import MatchRecord, season_of
from src.research.matchup import features as F
from src.research.matchup.design import DesignBuilder, outcome


def _rec(fid, comp, season, t, home, away, **base):
    b = {"homeGoalCount": None, "awayGoalCount": None, "overallGoalCount": None,
         "team_a_xg": None, "team_b_xg": None, "team_a_shotsOnTarget": None,
         "team_b_shotsOnTarget": None, "team_a_yellow_cards": None, "team_b_yellow_cards": None,
         "team_a_red_cards": 0, "team_b_red_cards": 0, "team_a_fouls": None, "team_b_fouls": None}
    b.update(base)
    return MatchRecord(fixture_id=fid, competition=comp, competition_id=comp, season_id=season,
                       kickoff_unix=t, home=home, away=away, home_id=home, away_id=away,
                       base=b, rich={"corner_kicks": base.get("_ck")}, extra={})


def _mk(fid, comp, season, t, h, a, hck, ack, hxg=1.0, axg=1.0):
    return _rec(fid, comp, season, t, h, a,
                homeGoalCount=1, awayGoalCount=1, overallGoalCount=2,
                team_a_xg=hxg, team_b_xg=axg,
                team_a_shotsOnTarget=4, team_b_shotsOnTarget=4,
                team_a_yellow_cards=2, team_b_yellow_cards=2,
                team_a_fouls=10, team_b_fouls=10, _ck=(hck, ack))


def test_roll_excludes_self_and_future():
    # A plays 3 prior matches then the target; roll for target must not see target or future
    recs = [
        _mk("m1", "L", "S", 100, "A", "X", 5, 3),
        _mk("m2", "L", "S", 200, "A", "Y", 7, 2),
        _mk("m3", "L", "S", 300, "A", "Z", 6, 4),
        _mk("mT", "L", "S", 400, "A", "B", 99, 99),   # target (huge values must be ignored)
        _mk("mF", "L", "S", 500, "A", "C", 1, 1),      # future
    ]
    idx = F.HistoryIndex(recs)
    season = idx.current_season("A", 400)
    r = F._roll(idx, "A", "corner_kicks", "for", None, 400, season)
    assert abs(r - (5 + 7 + 6) / 3) < 1e-9, f"expected mean of prior 3, got {r}"


def test_against_reads_opponent_value():
    recs = [
        _mk("m1", "L", "S", 100, "A", "X", 5, 3),   # A home, opp took 3
        _mk("m2", "L", "S", 200, "Y", "A", 8, 2),   # A away, opp(Y) took 8
        _mk("m3", "L", "S", 300, "A", "Z", 6, 4),   # A home, opp took 4
        _mk("mT", "L", "S", 400, "A", "B", 0, 0),
    ]
    idx = F.HistoryIndex(recs)
    season = idx.current_season("A", 400)
    against = F._roll(idx, "A", "corner_kicks", "against", None, 400, season)
    # A conceded: 3 (vs X), 8 (vs Y, A was away so opp=home=8), 4 (vs Z) -> mean 5
    assert abs(against - (3 + 8 + 4) / 3) < 1e-9, f"got {against}"


def test_windows_never_span_seasons():
    # prior season has many matches; current season has < window -> abstain
    recs = [_mk(f"p{i}", "L", "S1", 10 + i, "A", f"O{i}", 5, 5) for i in range(10)]
    recs += [_mk("c1", "L", "S2", 1000, "A", "P", 6, 6), _mk("cT", "L", "S2", 1100, "A", "B", 0, 0)]
    idx = F.HistoryIndex(recs)
    season = idx.current_season("A", 1100)
    assert season == "L:S2"
    w5 = F._roll(idx, "A", "corner_kicks", "for", 5, 1100, season)
    assert w5 is None, "w5 must abstain when current season has <5 matches (no cross-season backfill)"


def test_min_history_cold_start_fails_closed():
    recs = [_mk("c1", "L", "S", 100, "A", "P", 6, 6), _mk("cT", "L", "S", 200, "A", "B", 0, 0)]
    idx = F.HistoryIndex(recs)
    season = idx.current_season("A", 200)
    std = F._roll(idx, "A", "corner_kicks", "for", None, 200, season)
    assert std is None, "std must abstain below MIN_HISTORY prior matches"


def test_home_away_venue_orientation():
    # A at home should only average A's HOME matches for venue='home'
    recs = [
        _mk("m1", "L", "S", 100, "A", "X", 9, 1),   # A home -> 9
        _mk("m2", "L", "S", 150, "Y", "A", 1, 2),   # A away -> for=2
        _mk("m3", "L", "S", 200, "A", "Z", 7, 1),   # A home -> 7
        _mk("m4", "L", "S", 250, "A", "W", 8, 1),   # A home -> 8
        _mk("mT", "L", "S", 400, "A", "B", 0, 0),
    ]
    idx = F.HistoryIndex(recs)
    season = idx.current_season("A", 400)
    home_for = F._roll(idx, "A", "corner_kicks", "for", None, 400, season, venue="home")
    assert abs(home_for - (9 + 7 + 8) / 3) < 1e-9, f"home venue for should ignore away match, got {home_for}"


def test_league_env_uses_prior_only():
    recs = [_mk(f"m{i}", "L", "S", 100 + i, f"H{i}", f"A{i}", 5, 4) for i in range(25)]
    tgt = _mk("mT", "L", "S", 100 + 25, "A", "B", 99, 99)
    recs.append(tgt)
    env = F.LeagueEnvironment(recs)
    e = env.env(tgt, "corner_kicks", min_matches=20)
    assert abs(e - 9.0) < 1e-9, f"league env = mean prior total corners (5+4)=9, got {e}"


def test_strength_rating_is_pit():
    # ratings snapshot for a fixture must not incorporate that fixture's own result
    recs = [_mk(f"m{i}", "L", "S", 100 + i, "A", f"O{i}", 5, 2) for i in range(6)]
    recs += [_mk("mT", "L", "S", 500, "A", "B", 50, 0)]  # A explodes in target
    R = F.StrengthRatings(recs, "corner_kicks")
    att_before = R.attack("mT", "A")
    # target's 50 corners must NOT inflate the snapshot used AT the target
    # snapshot reflects only the 6 prior matches (5 for A each) -> attack >1 but bounded
    assert att_before is None or att_before < 3.0, f"rating leaked target result: {att_before}"


def test_outcome_semantics():
    r = _mk("m", "L", "S", 1, "A", "B", 6, 5)  # 11 corners
    assert outcome(r, "corners", 9.5) == 1.0
    assert outcome(r, "corners", 10.5) == 1.0
    r2 = _mk("m", "L", "S", 1, "A", "B", 3, 3)  # 6 corners
    assert outcome(r2, "corners", 9.5) == 0.0
    # goals from base
    assert outcome(r, "goals", 1.5) == 1.0   # 2 goals


def test_no_same_match_leakage_end_to_end():
    # Two identical fixtures except target result differs; features must be identical.
    prior = [_mk(f"m{i}", "L", "S", 100 + i, "A", f"O{i}", 5, 3) for i in range(6)]
    prior += [_mk(f"n{i}", "L", "S", 200 + i, "B", f"P{i}", 4, 4) for i in range(6)]
    tA = _mk("T", "L", "S", 900, "A", "B", 20, 20)
    tB = _mk("T", "L", "S", 900, "A", "B", 0, 0)
    dbA = DesignBuilder(prior + [tA]); dbB = DesignBuilder(prior + [tB])
    fA = dbA.f_matchup(tA, "corners"); fB = dbB.f_matchup(tB, "corners")
    for k in fA:
        if fA[k] is not None and fB.get(k) is not None:
            assert abs(fA[k] - fB[k]) < 1e-9, f"feature {k} depends on target result!"


if __name__ == "__main__":
    import subprocess
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-q"]))


# =========================================================================================
# Temporal-integrity counterexamples. Both were reproduced against the previous builders and
# both are reachable in the real corpus (5319 matches): 56.55% of matches share a kickoff
# with another match, and 134 of 10638 (fixture, team) pairs sit across a season boundary.
# =========================================================================================

def _sim_fixture_set():
    """History for two teams, then TWO fixtures at the SAME kickoff instant.

    `SIM1` is a blow-out, so if it leaks into `SIM2`'s snapshot it moves the league mean
    enough to be unmistakable. Totals in the history are deliberately uniform so the league
    mean is otherwise flat and the only thing that can shift it is the leak.
    """
    hist = [_mk(f"h{i}", "L", "S", 100 + i, "A", f"O{i}", 5, 5) for i in range(3)]
    hist += [_mk(f"g{i}", "L", "S", 100 + i, "C", f"P{i}", 5, 5) for i in range(3)]
    sim1 = _mk("SIM1", "L", "S", 200, "A", "Z", 40, 40)
    sim2 = _mk("SIM2", "L", "S", 200, "C", "W", 5, 5)
    return hist, sim1, sim2


def test_strength_rating_ignores_a_simultaneous_match():
    """A fixture's PIT snapshot must not contain a match that kicked off at the same instant.

    The control is what makes this decisive: moving `SIM1` strictly later must not change
    `SIM2`'s snapshot. Order-invariance alone would be satisfied by an implementation that
    leaked identically in both orderings.
    """
    hist, sim1, sim2 = _sim_fixture_set()
    simultaneous = F.StrengthRatings(hist + [sim1, sim2], "corner_kicks").attack("SIM2", "C")

    later = _mk("SIM1", "L", "S", 300, "A", "Z", 40, 40)          # same match, strictly after
    control = F.StrengthRatings(hist + [later, sim2], "corner_kicks").attack("SIM2", "C")

    assert simultaneous == control, (
        "SIM1 kicked off at the same instant as SIM2 and still moved SIM2's snapshot "
        f"({simultaneous} vs {control})")


def test_strength_rating_is_independent_of_simultaneous_input_order():
    """Snapshots must not depend on the order simultaneous matches happen to be listed in.

    `sorted(recs, key=kickoff_unix)` is stable, so the input list silently decided which of
    a 15:00 round was processed first — and therefore which ones saw the others' results.
    """
    hist, sim1, sim2 = _sim_fixture_set()
    forward = F.StrengthRatings(hist + [sim1, sim2], "corner_kicks")
    reverse = F.StrengthRatings(hist + [sim2, sim1], "corner_kicks")

    for fid, team in (("SIM1", "A"), ("SIM2", "C")):
        assert forward.attack(fid, team) == reverse.attack(fid, team), f"attack {fid}/{team}"
        assert forward.defense(fid, team) == reverse.defense(fid, team), f"defense {fid}/{team}"


def test_league_env_ignores_a_simultaneous_match():
    """The same simultaneity question for the league-environment baseline."""
    recs = [_mk(f"m{i}", "L", "S", 100 + i, f"H{i}", f"A{i}", 5, 4) for i in range(21)]
    t1 = _mk("T1", "L", "S", 500, "A", "B", 99, 99)
    t2 = _mk("T2", "L", "S", 500, "C", "D", 99, 99)
    env = F.LeagueEnvironment(recs + [t1, t2])

    e1, e2 = env.env(t1, "corner_kicks", 20), env.env(t2, "corner_kicks", 20)
    assert e1 == e2 == 9.0, f"simultaneous fixtures must see the same prior-only baseline: {e1}, {e2}"


def test_target_season_is_the_fixtures_own_season_not_the_last_played():
    """Season-boundary contamination: prior-season form must not be served as current-season.

    Team A has six matches in S1 and none yet in S2. `current_season()` answers "S1" — the
    season A last played in — so the previous builders returned S1 form for an S2 fixture and
    satisfied the cold-start floor with stale data.
    """
    recs = [_mk(f"p{i}", "L", "S1", 10 + i, "A", f"O{i}", 7, 7) for i in range(6)]
    tgt = _mk("T", "L", "S2", 1000, "A", "B", 0, 0)
    recs.append(tgt)
    idx = F.HistoryIndex(recs)

    assert F.HistoryIndex.target_season(tgt) == "L:S2"
    # `current_season` is deliberately unchanged — it answers a different question.
    assert idx.current_season("A", 1000) == "L:S1"

    stale = F._roll(idx, "A", "corner_kicks", "for", None, 1000, idx.current_season("A", 1000))
    assert stale == 7.0, "precondition: the old season is what made the stale value available"

    fresh = F._roll(idx, "A", "corner_kicks", "for", None, 1000, F.HistoryIndex.target_season(tgt))
    assert fresh is None, "no current-season history means abstain, not prior-season form"


def test_design_builder_abstains_across_a_season_boundary():
    """End-to-end through the builder that consumes these features."""
    recs = [_mk(f"p{i}", "L", "S1", 10 + i, "A", f"O{i}", 7, 7) for i in range(6)]
    recs += [_mk(f"q{i}", "L", "S1", 20 + i, "B", f"R{i}", 7, 7) for i in range(6)]
    tgt = _mk("T", "L", "S2", 1000, "A", "B", 0, 0)
    recs.append(tgt)

    feats = DesignBuilder(recs).f_champ(tgt, "corners")
    assert feats, "the family must still be emitted, with abstentions rather than silence"
    assert all(v is None for v in feats.values()), (
        f"prior-season values leaked into an S2 fixture: "
        f"{{k: v for k, v in feats.items() if v is not None}}")
