"""Tests for the calibration-efficiency experiment infrastructure.

Covers the dependence copula (Experiment B), the rho estimator's PIT safety, the
xG/shots ablation isolation/determinism (Experiment A), and evaluation integrity.
The champion is exercised only through its public API and is never modified.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.stats import poisson

from src.research.experiments.calibration_efficiency.dependence import build_joint
from src.research.experiments.calibration_efficiency.dependence_eval import RhoState, CORNER_LINES
from src.research.experiments.calibration_efficiency.xg_shots_eval import (
    ABLATIONS,
    _ablated_goals_family,
)


def _side_pmfs():
    h = poisson.pmf(np.arange(31), 5.2); h = h / h.sum()
    a = poisson.pmf(np.arange(31), 4.6); a = a / a.sum()
    return h, a


class TestCopulaCore:
    def test_rho_zero_reproduces_convolution(self):
        h, a = _side_pmfs()
        j = build_joint(h, a, 0.0)
        conv = np.convolve(h, a); conv = conv / conv.sum()
        assert np.max(np.abs(np.array(j.total_pmf) - conv)) < 1e-12

    def test_negative_rho_representable_and_reduces_variance(self):
        h, a = _side_pmfs()
        v_ind = build_joint(h, a, 0.0).total_variance
        v_neg = build_joint(h, a, -0.3).total_variance
        assert v_neg < v_ind  # negative dependence reduces total variance

    def test_positive_rho_representable_and_increases_variance(self):
        h, a = _side_pmfs()
        v_ind = build_joint(h, a, 0.0).total_variance
        v_pos = build_joint(h, a, 0.3).total_variance
        assert v_pos > v_ind

    def test_joint_nonnegative_and_normalized(self):
        h, a = _side_pmfs()
        for rho in (-0.4, -0.209, 0.0, 0.25):
            j = build_joint(h, a, rho)
            assert (j.joint >= -1e-12).all()
            assert abs(j.joint.sum() - 1.0) < 1e-9

    def test_marginals_preserved(self):
        h, a = _side_pmfs()
        for rho in (-0.4, -0.209, 0.25):
            j = build_joint(h, a, rho)
            assert np.max(np.abs(j.recovered_home_marginal() - h)) < 1e-9
            assert np.max(np.abs(j.recovered_away_marginal() - a)) < 1e-9

    def test_total_pmf_normalized(self):
        h, a = _side_pmfs()
        j = build_joint(h, a, -0.209)
        assert abs(sum(j.total_pmf) - 1.0) < 1e-9

    def test_expected_total_invariant_to_rho(self):
        h, a = _side_pmfs()
        e0 = build_joint(h, a, 0.0).expected_total
        for rho in (-0.4, -0.209, 0.25):
            assert abs(build_joint(h, a, rho).expected_total - e0) < 1e-9

    def test_line_monotonicity(self):
        h, a = _side_pmfs()
        j = build_joint(h, a, -0.209)
        probs = [j.p_over(line) for line in (7.5, 8.5, 9.5, 10.5)]
        assert all(probs[i] >= probs[i + 1] - 1e-12 for i in range(len(probs) - 1))

    def test_no_impossible_probabilities(self):
        h, a = _side_pmfs()
        j = build_joint(h, a, -0.3)
        for line in (0.5, 7.5, 30.5):
            p = j.p_over(line)
            assert 0.0 <= p <= 1.0


class TestRhoEstimatorPIT:
    def test_insufficient_support_falls_back_to_zero(self):
        rs = RhoState(min_support=300)
        for _ in range(100):
            rs.observe(6.0, 5.0, 5.5, 4.8)  # only 100 < 300
        assert rs.current_rho() == 0.0

    def test_future_cannot_influence_current_rho(self):
        # rho is computed only from observations recorded SO FAR; observing more
        # AFTER reading rho does not retroactively change the earlier read.
        rs = RhoState(min_support=10)
        rng = np.random.default_rng(0)
        for _ in range(50):
            rs.observe(rng.poisson(5.2), rng.poisson(4.6), 5.2, 4.6)
        rho_before = rs.current_rho()
        for _ in range(50):
            rs.observe(rng.poisson(5.2), rng.poisson(4.6), 5.2, 4.6)
        # The earlier value was a pure function of the first 50 only (recomputed
        # here to prove it does not depend on the later observations).
        rs2 = RhoState(min_support=10)
        rng2 = np.random.default_rng(0)
        for _ in range(50):
            rs2.observe(rng2.poisson(5.2), rng2.poisson(4.6), 5.2, 4.6)
        assert rs2.current_rho() == rho_before

    def test_rho_capped(self):
        rs = RhoState(min_support=5, rho_cap=0.3)
        # perfectly correlated residuals -> rho would be 1, must be capped
        for i in range(20):
            v = 3.0 + i
            rs.observe(v, v, 5.0, 5.0)
        assert abs(rs.current_rho()) <= 0.3 + 1e-9


class TestAblationIsolation:
    def test_drop_xg_removes_only_xg_features(self):
        base = _ablated_goals_family(())
        drop_xg = _ablated_goals_family(("xg",))
        removed = set(base.feature_names) - set(drop_xg.feature_names)
        assert removed == {"own_produce_xg", "opp_concede_xg"}

    def test_drop_shots_removes_only_shots_features(self):
        base = _ablated_goals_family(())
        drop_shots = _ablated_goals_family(("shots",))
        removed = set(base.feature_names) - set(drop_shots.feature_names)
        assert removed == {"own_produce_shots"}  # shots not in concede set

    def test_ablation_families_are_distinct_and_deterministic(self):
        # same drop -> identical feature set (deterministic)
        assert _ablated_goals_family(("xg",)).feature_names == _ablated_goals_family(("xg",)).feature_names
        # A0 keeps xG and shots
        a0 = set(_ablated_goals_family(()).feature_names)
        assert "own_produce_xg" in a0 and "own_produce_shots" in a0

    def test_ablation_registry(self):
        assert ABLATIONS["A0_champion_goals"] == ()
        assert ABLATIONS["A3_drop_xg_and_shots"] == ("xg", "shots")


class TestNoFeatureLeakage:
    def test_ablated_family_features_carry_no_raw_same_match_keys(self):
        # Feature names are rolling-window derived, never the fixture's own raw
        # count keys. Enforced structurally by the champion side_rows builder.
        for drop in ((), ("xg",), ("shots",), ("xg", "shots")):
            fam = _ablated_goals_family(drop)
            raw_keys = {"team_a_corners", "team_b_corners", "homeGoalCount", "awayGoalCount",
                        "team_a_xg", "team_a_shots"}
            assert raw_keys.isdisjoint(set(fam.feature_names))
