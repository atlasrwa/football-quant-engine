"""Positive leakage tests for the V4 OOS RECONSTRUCTION path (not just the design).

$0.00. Proves HDFeatureBuilder refuses to let a target or future fixture enter its own
feature, and that origin fixtures are mechanically excluded. Must pass BEFORE scoring.
"""
from __future__ import annotations

import importlib.util
import sys

import pytest

ROOT = "/home/ubuntu"
sys.path.insert(0, ROOT + "/src")
sys.path.insert(0, ROOT)

spec = importlib.util.spec_from_file_location(
    "_run_v4_oos", f"{ROOT}/research/hypothesis_oos/_run_v4_oos.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

from src.research.matchup.corpus import MatchRecord


def _rec(fid, k, home_id, away_id, comp="L1", ck=(5, 4)):
    return MatchRecord(
        fixture_id=fid, competition=comp, competition_id="c", season_id="s",
        kickoff_unix=k, home="H", away="A", home_id=home_id, away_id=away_id,
        base={"homeGoalCount": 1, "awayGoalCount": 1, "overallGoalCount": 2,
              "team_a_yellow_cards": 2, "team_b_yellow_cards": 2,
              "team_a_red_cards": 0, "team_b_red_cards": 0},
        rich={"corner_kicks": ck, "accurate_crosses": (10, 8), "big_chances": (2, 1)},
        extra={"possession": (55, 45), "total_shots": (12, 9)})


def _corpus():
    # team T plays 10 prior matches vs varied opponents, then a target at t=10000
    recs = []
    opps = [f"O{i}" for i in range(10)]
    for i, opp in enumerate(opps):
        recs.append(_rec(f"h{i}", 100 + i * 100, "T", opp, ck=(3 + i % 5, 4)))
        # give each opponent its own prior history so it is bandable
        for j in range(5):
            recs.append(_rec(f"o{i}_{j}", 50 + i * 100 + j, opp, f"X{i}_{j}",
                             ck=(2 + (i + j) % 6, 3)))
    target = _rec("TARGET", 10000, "T", "O0")
    recs.append(target)
    return recs, target


def test_hd_feature_is_pit_safe_target_excluded():
    recs, target = _corpus()
    fb = runner.HDFeatureBuilder(recs, frozenset())
    v, state = fb.hd_shrunk_diff(
        team_id="T", competition="L1", cutoff=target.kickoff_unix,
        target_fid=target.fixture_id, target_stat="corner_kicks", side="for",
        axis="corners_against", band="HIGH")
    # target must not enter; observations are strictly before cutoff
    obs = fb._observations("T", "corner_kicks", "for", target.kickoff_unix,
                           target.fixture_id)
    assert all(o.kickoff_unix < target.kickoff_unix for o in obs)
    assert all(o.fixture_id != target.fixture_id for o in obs)


def test_hd_feature_future_does_not_change_past():
    """Adding a FUTURE match after the cutoff must not change the feature value."""
    recs, target = _corpus()
    fb1 = runner.HDFeatureBuilder(recs, frozenset())
    v1, _ = fb1.hd_shrunk_diff(
        team_id="T", competition="L1", cutoff=target.kickoff_unix,
        target_fid=target.fixture_id, target_stat="corner_kicks", side="for",
        axis="corners_against", band="HIGH")
    recs2 = recs + [_rec("FUTURE", 99999, "T", "O0", ck=(99, 99))]
    fb2 = runner.HDFeatureBuilder(recs2, frozenset())
    v2, _ = fb2.hd_shrunk_diff(
        team_id="T", competition="L1", cutoff=target.kickoff_unix,
        target_fid=target.fixture_id, target_stat="corner_kicks", side="for",
        axis="corners_against", band="HIGH")
    assert v1 == v2, "a future match changed a point-in-time feature -> LEAKAGE"


def test_origin_fixtures_mechanically_excluded_from_builder():
    recs, target = _corpus()
    q = frozenset({"h3", "h7"})   # pretend two priors are origin fixtures
    fb = runner.HDFeatureBuilder(recs, q)
    obs = fb._observations("T", "corner_kicks", "for", target.kickoff_unix,
                           target.fixture_id)
    assert all(o.fixture_id not in q for o in obs), "quarantined fixture entered feature"
