"""P0-SIMSELF: a historical match H must not help decide its own cohort membership.

Fully synthetic -- no corpus row, no outcome, no model call.

The invariant, stated as the mission states it: the information used to decide whether
historical fixture H is an analogue must not include H's own measured observation, nor any
information occurring after H that would change H's membership.

These tests pin BOTH halves:
  * mutating H's own measured values must not move membership;
  * appending extreme post-H (pre-T) rows must not move membership.

`test_unrepaired_engine_leaks` is the regression witness. It asserts the AS-OF-T engine
really does leak, so that if someone ever reverts the compiler to `similarity`, the suite
says why the repair existed rather than quietly going green.
"""
from __future__ import annotations

import json

import pytest

from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v71 import corpus_index as CI
from src.research.hypothesis_v71 import similarity as SIM
from src.research.hypothesis_v8c import historical_similarity as HSIM
from src.research.matchup import corpus as MC

DAY = 86400
K0 = 1_600_000_000
COMP = "champ"
SUBJ, TOPP = "tm_subj", "tm_topp"
OPPS = [f"tm_o{i}" for i in range(10)]
H_FIXTURE = "mt_H"
H_OPPONENT = "tm_o0"
TARGET = "mt_TARGET"

CLEAN_H = dict(hg=1, ag=1, hy=2, ay=2, hsot=4, asot=4, hsib=3, asib=3, hf=10, af=10)
#: H's OWN measured observation, made extreme. Nothing else in the corpus changes.
MUTATED_H = {**CLEAN_H, "hg": 80, "hsot": 80, "hsib": 80, "hy": 9}


def _rec(fid, k, home, away, *, hg, ag, hy, ay, hsot, asot, hsib, asib, hf, af):
    return MC.MatchRecord(
        fixture_id=fid, competition=COMP, competition_id="c", season_id="s",
        kickoff_unix=k, home=home, away=away, home_id=home, away_id=away,
        base={"homeGoalCount": hg, "awayGoalCount": ag,
              "team_a_yellow_cards": hy, "team_b_yellow_cards": ay},
        rich={"shots_on_target": (hsot, asot), "shots_inside_box": (hsib, asib),
              "fouls": (hf, af)},
        extra={})


def _build(*, h_values=None, extreme_post_h=0):
    """A corpus where H's opponent sits inside the k=8 similar set on clean data."""
    recs, i = [], 0
    for oi, opp in enumerate(OPPS):                    # graded conceded profiles
        for j in range(7):
            i += 1
            recs.append(_rec(f"mt_{opp}_{j}", K0 + i * DAY, opp, f"tm_filler{oi}_{j}",
                             hg=1, ag=1 + oi * 0.3, hy=2, ay=2,
                             hsot=4, asot=4 + oi * 0.5, hsib=3, asib=3 + oi * 0.4,
                             hf=10, af=10))
    for j in range(7):                                  # the target opponent's own history
        i += 1
        recs.append(_rec(f"mt_topp_{j}", K0 + i * DAY, TOPP, f"tm_tfill{j}",
                         hg=1, ag=1.0, hy=2, ay=2, hsot=4, asot=4.0,
                         hsib=3, asib=3.0, hf=10, af=10))
    i += 1
    recs.append(_rec(H_FIXTURE, K0 + i * DAY, SUBJ, H_OPPONENT, **(h_values or CLEAN_H)))
    for n in range(extreme_post_h):                     # strictly after H, strictly before T
        i += 1
        recs.append(_rec(f"mt_post_{n}", K0 + i * DAY, "tm_postfill", H_OPPONENT,
                         hg=60, ag=0, hy=9, ay=9, hsot=60, asot=0,
                         hsib=60, asib=0, hf=60, af=0))
    for j in range(6):
        i += 1
        recs.append(_rec(f"mt_subj_{j}", K0 + i * DAY, SUBJ, f"tm_sfill{j}", **CLEAN_H))
    i += 20
    recs.append(_rec(TARGET, K0 + i * DAY, SUBJ, TOPP, **CLEAN_H))
    return recs


def _index(recs):
    metrics = [m for m, r in CAP.METRIC_SEMANTICS.items() if r.get("block")]
    return CI.PITIndex(recs, metrics, CAP.METRIC_SEMANTICS)


def _membership_h_time(recs):
    """Membership as the REPAIRED compiler resolves it: strictly before H."""
    index = _index(recs)
    h_kick = int(index.recs[index.pos_of_fixture[H_FIXTURE]].kickoff_unix)
    return H_OPPONENT in HSIM.HistoricalSimilarityIndex(index).similar_ids_before(
        TOPP, COMP, h_kick)


def _membership_as_of_t(recs):
    """Membership as the UNREPAIRED engine resolved it: as of the target fixture."""
    index = _index(recs)
    pos = index.pos_of_fixture[TARGET]
    return H_OPPONENT in SIM.SimilarityEngine(index).similar_opponent_ids(
        index, TOPP, index.recs[pos], pos)


# --------------------------------------------------------------------- the invariant
def test_h_own_observation_does_not_change_its_own_membership():
    base = _membership_h_time(_build())
    assert base is True, "construction must place H's opponent inside the cohort to be a test"
    assert _membership_h_time(_build(h_values=MUTATED_H)) == base, (
        "H's own measured observation changed whether H enters its own cohort")


def test_post_h_data_does_not_change_h_membership():
    base = _membership_h_time(_build())
    assert _membership_h_time(_build(extreme_post_h=6)) == base, (
        "data occurring after H changed whether H enters its own cohort")


def test_membership_is_identical_across_both_mutations():
    """Both adversarial arms at once: one H-time answer, three corpora."""
    answers = {
        _membership_h_time(_build()),
        _membership_h_time(_build(h_values=MUTATED_H)),
        _membership_h_time(_build(extreme_post_h=6)),
    }
    assert len(answers) == 1, f"membership is not invariant: {answers}"


# --------------------------------------------------------------------- regression witness
def test_unrepaired_engine_leaks():
    """Documents WHY the repair exists. If this ever fails, the as-of-T engine changed and
    the P0-SIMSELF rationale must be re-derived rather than assumed."""
    base = _membership_as_of_t(_build())
    mutated = _membership_as_of_t(_build(h_values=MUTATED_H))
    post = _membership_as_of_t(_build(extreme_post_h=6))
    assert (base != mutated) or (base != post), (
        "the as-of-T engine no longer leaks on this construction; re-derive P0-SIMSELF")


# --------------------------------------------------------------------- no silent fallback
def test_compiler_refuses_similarity_without_h_time_index():
    """A caller that forgets to wire the H-time index must FAIL, never silently fall back to
    the leaky as-of-T set."""
    from src.research.hypothesis_v8c import compiler as CO

    class _Sel:
        entity_role = "SUBJECT"
        similar_to_opponent = "SIMILAR"
        filters = ()
        complement = False
        window = "ALL_PRIOR"
        weighting = "UNIFORM"

    index = _index(_build())
    pos = index.pos_of_fixture[TARGET]
    rec = index.recs[pos]
    with pytest.raises(CO.CompileRefused, match="P0-SIMSELF"):
        CO._select(index, _Sel(), None, rec, pos, SUBJ, {}, None, None,
                   hist_similarity=None)


def test_version_stamp_records_the_repair():
    st = HSIM.version_stamp()
    assert "P0-SIMSELF" in st["repairs"]
    assert st["frozen_v7_spec_reused_verbatim"] is True
    assert st["spec_redesigned"] is False
    assert st["k_neighbors"] == SIM.K_NEIGHBORS
    assert st["min_profile_history_matches"] == SIM.MIN_PROFILE_HISTORY_MATCHES
