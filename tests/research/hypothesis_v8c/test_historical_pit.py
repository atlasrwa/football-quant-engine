"""P1-K: a HISTORICAL match H must be classified from information strictly BEFORE H.

The two mandatory adversarial tests:
  * appending extreme matches for an opponent AFTER H but BEFORE T must not move H's band;
  * mutating H's OWN measured statistic must not move its own conditioning profile.

Plus a live control, so the suite cannot pass on an apparatus that ignores its inputs.
"""
from __future__ import annotations

import pytest

from src.research.hypothesis_v71 import invariants as INV
from src.research.hypothesis_v8c import golden as G
from src.research.hypothesis_v8c import historical_pit as HP

AXIS = "goals_against"
METRIC, SIDE = INV.axis_metric_perspective(AXIS)


def _pick_H(env, min_prior=HP.MIN_PRIOR_MATCHES_FOR_PROFILE):
    """A historical match H whose opponent already has >= the floor of prior matches, so a
    band genuinely exists as of H and the test is not vacuous."""
    idx = env.index
    T = int(idx.kick[env.target_pos])
    subj = "tm_subject"
    for e in idx.series[subj]:
        pos, kick, comp, _is_home, opp = e
        if kick >= T or opp is None:
            continue
        prior = [x for x in idx.series[str(opp)] if x[2] == comp and x[1] < kick]
        if len(prior) >= min_prior:
            return e
    return None


#: `single_competition=True` is REQUIRED here, not incidental: the default environment cycles
#: six competitions, so no (opponent, competition) cell reaches the >=6 prior-match floor and
#: no band exists as of H -- every test below would be vacuous.
ENV_KW = dict(n_prior_blocks=80, n_opponents=6, single_competition=True,
              metrics=("goals", "yellow_cards"))


@pytest.fixture(scope="module")
def env():
    return G.build_environment(**ENV_KW)


def test_h_time_index_builds_and_is_cheap(env):
    hp = HP.HistoricalProfileIndex(env.index)
    s = hp.stats()
    assert s["n_cells"] > 0
    assert s["profile_semantic"] == "(team, competition, axis, strictly-before-H)"


def test_profile_before_H_excludes_H_and_everything_after(env):
    """The exact defect: H itself and post-H matches used to feed H's own classification."""
    hp = HP.HistoricalProfileIndex(env.index)
    idx = env.index
    Hm = _pick_H(env)
    assert Hm is not None, "no suitable historical match in the fixture environment"
    h_pos, h_kick, h_comp, _ih, opp = Hm

    got = hp.profile_before(opp, h_comp, AXIS, h_kick)
    assert got is not None

    prior = [x for x in idx.series[str(opp)] if x[2] == h_comp and x[1] < h_kick]
    vals = [idx.team_value(x[0], str(opp), METRIC, SIDE) for x in prior]
    vals = [v for v in vals if v is not None]
    assert abs(got - sum(vals) / len(vals)) < 1e-12

    # and it differs from the as-of-T value whenever post-H matches exist
    T = int(idx.kick[env.target_pos])
    post = [x for x in idx.series[str(opp)] if x[2] == h_comp and h_kick <= x[1] < T]
    assert post, "environment has no post-H matches; the test would be vacuous"
    as_of_T = hp.profile_before(opp, h_comp, AXIS, T)
    assert as_of_T is not None
    assert abs(as_of_T - got) > 1e-12, (
        "as-of-T and as-of-H profiles coincide; the defect could not be detected here")
    assert all(x[0] != h_pos for x in prior), "H itself fed its own profile"


def test_post_H_extreme_matches_cannot_move_H_band(env):
    """MANDATORY: append extreme matches for the opponent AFTER H but BEFORE T."""
    hp = HP.HistoricalProfileIndex(env.index)
    Hm = _pick_H(env)
    h_pos, h_kick, h_comp, _ih, opp = Hm
    before = hp.band_before(opp, h_comp, AXIS, h_kick)
    assert before is not None, "no band as of H; test would be vacuous"

    # a second environment identical except for extreme opponent matches inserted in (H, T)
    env2 = G.build_environment(**ENV_KW)
    idx2 = env2.index
    T2 = int(idx2.kick[env2.target_pos])
    injected = 0
    for x in idx2.series[str(opp)]:
        if h_kick < x[1] < T2:
            pair = idx2.vals[METRIC][x[0]]
            if pair is not None:
                idx2.vals[METRIC][x[0]] = (99.0, 99.0)
                injected += 1
    assert injected > 0, "nothing was injected; test would be vacuous"

    hp2 = HP.HistoricalProfileIndex(idx2)
    after = hp2.band_before(opp, h_comp, AXIS, h_kick)
    assert after == before, (
        f"post-H data changed H's band: {before} -> {after} (hindsight leak)")
    assert abs(hp2.profile_before(opp, h_comp, AXIS, h_kick)
               - hp.profile_before(opp, h_comp, AXIS, h_kick)) < 1e-12


def test_H_own_observation_cannot_move_its_conditioning_profile(env):
    """MANDATORY: mutating H's own measured statistic must not move H's conditioning profile."""
    hp = HP.HistoricalProfileIndex(env.index)
    Hm = _pick_H(env)
    h_pos, h_kick, h_comp, _ih, opp = Hm
    before_profile = hp.profile_before(opp, h_comp, AXIS, h_kick)
    before_band = hp.band_before(opp, h_comp, AXIS, h_kick)

    env2 = G.build_environment(**ENV_KW)
    env2.index.vals[METRIC][h_pos] = (99.0, 99.0)      # obliterate H's own observation
    hp2 = HP.HistoricalProfileIndex(env2.index)

    assert abs(hp2.profile_before(opp, h_comp, AXIS, h_kick) - before_profile) < 1e-12, (
        "H's own observation moved its own conditioning profile (self-inclusion)")
    assert hp2.band_before(opp, h_comp, AXIS, h_kick) == before_band


def test_LIVE_CONTROL_pre_H_data_DOES_move_the_profile(env):
    """Without this, the two null results above would also hold for an inert index."""
    hp = HP.HistoricalProfileIndex(env.index)
    Hm = _pick_H(env)
    _hp_pos, h_kick, h_comp, _ih, opp = Hm
    before = hp.profile_before(opp, h_comp, AXIS, h_kick)

    env2 = G.build_environment(**ENV_KW)
    moved = 0
    for x in env2.index.series[str(opp)]:
        if x[2] == h_comp and x[1] < h_kick:
            env2.index.vals[METRIC][x[0]] = (99.0, 99.0)
            moved += 1
    assert moved > 0
    hp2 = HP.HistoricalProfileIndex(env2.index)
    after = hp2.profile_before(opp, h_comp, AXIS, h_kick)
    assert abs(after - before) > 1e-9, (
        "changing STRICTLY-PRIOR history changed nothing -- the index is inert")


def test_terciles_are_also_as_of_H(env):
    """Both halves are required: as-of-H profile with as-of-T thresholds would still leak."""
    hp = HP.HistoricalProfileIndex(env.index)
    Hm = _pick_H(env)
    _p, h_kick, h_comp, _ih, _opp = Hm
    T = int(env.index.kick[env.target_pos])
    t_h = hp.terciles_before(h_comp, AXIS, h_kick)
    t_T = hp.terciles_before(h_comp, AXIS, T)
    assert t_h is not None and t_T is not None
    assert t_h != t_T, "tercile bounds are identical at H and T; the test cannot discriminate"


def test_unclassifiable_match_is_excluded_not_imputed(env):
    """A cell below the prior-match floor yields None -- never MID."""
    hp = HP.HistoricalProfileIndex(env.index)
    earliest = min(int(k) for k in env.index.kick)
    assert hp.profile_before("tm_opp0", "champ", AXIS, earliest) is None
    assert hp.band_before("tm_opp0", "champ", AXIS, earliest) is None
