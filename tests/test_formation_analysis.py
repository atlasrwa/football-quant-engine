"""
Guards for the formation analysis (scripts/formation_analysis.py).

These do not hit the network. They lock in the two things that could silently
corrupt the descriptive result:

  1. per_side_outcomes parses the corpus schema correctly and returns per-side
     tuples (home, away) for each outcome, using -1 as "not recorded".
  2. the within-team contrast is genuinely WITHIN team — a pure between-team
     quality difference (team A always high, team B always low, each on a single
     formation) must NOT register as a formation effect, because no team plays
     both arms. This is the team-quality-control invariant.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import formation_analysis as fa  # noqa: E402


def _mk(mid, hid, aid, hf, af, corners, cards_home, cards_away, fouls_home, fouls_away):
    """Minimal joined-style corpus match dict the analysis reads."""
    return {
        "match_id": mid,
        "date_unix": 1_700_000_000 + hash(mid) % 10_000,
        "home_id": hid, "away_id": aid,
        "_rich": {
            "corner_kicks": (corners[0], corners[1]),
            "shots_on_target": (4, 4),
            "blocked_shots": (2, 2),
            "clearances": (20, 20),
            "accurate_crosses": (4, 4),
        },
        "team_a_fouls": fouls_home, "team_b_fouls": fouls_away,
        "team_a_yellow_cards": cards_home, "team_b_yellow_cards": cards_away,
        "team_a_red_cards": 0, "team_b_red_cards": 0,
        "home_formation": hf, "away_formation": af,
    }


def _rec(m):
    return {
        "match_id": m["match_id"], "date_unix": m["date_unix"],
        "home_id": m["home_id"], "away_id": m["away_id"],
        "home_formation": m["home_formation"], "away_formation": m["away_formation"],
        "confirmed": True, "outcomes": fa.per_side_outcomes(m),
    }


def test_per_side_outcomes_parsing():
    m = _mk("m1", "H", "A", "4-3-3", "4-4-2",
            corners=(6, 3), cards_home=2, cards_away=1, fouls_home=10, fouls_away=12)
    oc = fa.per_side_outcomes(m)
    assert oc["corners"] == (6, 3)
    assert oc["cards"] == (2, 1)          # yellow+red per side
    assert oc["fouls"] == (10, 12)
    assert oc["sot"] == (4, 4)


def test_minus_one_is_not_recorded():
    m = _mk("m2", "H", "A", "4-3-3", "4-4-2",
            corners=(-1, 3), cards_home=1, cards_away=1, fouls_home=-1, fouls_away=9)
    oc = fa.per_side_outcomes(m)
    assert oc["corners"] is None     # a -1 side voids the pair
    assert oc["fouls"] is None


def test_within_team_ignores_pure_between_team_quality():
    """A pure quality gap with NO within-team switching must not read as a formation
    effect. Team HI always plays 4-3-3 and always high cards; team LO always plays
    4-4-2 and always low cards. No team plays both arms -> contrast returns None."""
    recs = []
    for i in range(12):
        recs.append(_rec(_mk(f"hi{i}", "HI", f"opp{i}", "4-3-3", "4-4-2",
                             corners=(5, 5), cards_home=5, cards_away=1,
                             fouls_home=10, fouls_away=10)))
        recs.append(_rec(_mk(f"lo{i}", "LO", f"opq{i}", "4-4-2", "4-3-3",
                             corners=(5, 5), cards_home=1, cards_away=5,
                             fouls_home=10, fouls_away=10)))
    rng = np.random.default_rng(0)
    # neither HI nor LO ever plays BOTH formations -> no within-team pair exists
    res = fa.within_team_contrast(recs, "4-3-3", "4-4-2", "cards", rng)
    assert res is None


def test_within_team_detects_genuine_within_team_shift():
    """When the SAME teams play both formations and take more cards under 4-3-3, the
    within-team contrast should be positive and its CI computable."""
    recs = []
    rng_teams = [f"T{i}" for i in range(10)]
    for t in rng_teams:
        # each team: 3 matches at 4-3-3 (high cards) + 3 at 4-4-2 (low cards), at home
        for j in range(3):
            recs.append(_rec(_mk(f"{t}_a{j}", t, f"o{t}{j}", "4-3-3", "5-3-2",
                                 corners=(5, 5), cards_home=4, cards_away=2,
                                 fouls_home=10, fouls_away=10)))
            recs.append(_rec(_mk(f"{t}_b{j}", t, f"p{t}{j}", "4-4-2", "5-3-2",
                                 corners=(5, 5), cards_home=1, cards_away=2,
                                 fouls_home=10, fouls_away=10)))
    rng = np.random.default_rng(0)
    res = fa.within_team_contrast(recs, "4-3-3", "4-4-2", "cards", rng)
    assert res is not None
    assert res["within_team_diff"] > 0
    assert res["n_teams"] == 10
    assert res["ci95"][0] > 0  # clearly positive


if __name__ == "__main__":
    test_per_side_outcomes_parsing()
    test_minus_one_is_not_recorded()
    test_within_team_ignores_pure_between_team_quality()
    test_within_team_detects_genuine_within_team_shift()
    print("all formation analysis guards pass")
