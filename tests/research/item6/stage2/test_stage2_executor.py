"""ITEM 6 STAGE 2 executor tests. SYNTHETIC DATA ONLY: no real corpus label is read, no real
fold is fit, no LLM is called."""
from __future__ import annotations

import numpy as np
import pytest

from src.research.item6.stage2 import evaluation as EV
from src.research.item6.stage2 import executor as X
from src.research.item6.stage2 import model_specs as MS


def _synthetic(n=600, p=6, seed=1):
    rng = np.random.default_rng(seed)
    Xm = rng.normal(size=(n, p))
    logit = 0.8 * Xm[:, 0] - 0.5 * Xm[:, 1]
    y = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(float)
    Xm[rng.random((n, p)) < 0.05] = np.nan
    return Xm, y


def test_fit_arm_uses_frozen_grid_calibrates_on_inner_oof_and_clips():
    Xm, y = _synthetic()
    r = X.fit_arm(Xm[:500], y[:500], Xm[500:])
    assert r["status"] == "FIT"
    assert r["selected_C"] in MS.C_GRID and r["selected_l1_ratio"] in MS.L1_RATIO_GRID
    # OOF pairs = the 4 inner validation splits = strictly fewer than the training rows
    from sklearn.model_selection import TimeSeriesSplit
    n_val = sum(len(v) for _, v in TimeSeriesSplit(n_splits=4).split(Xm[:500]))
    assert r["n_calibration_pairs"] == n_val < 500
    lo, hi = MS.PROBABILITY_CLIP
    assert r["final"].min() >= lo and r["final"].max() <= hi
    assert np.allclose(r["final"], np.clip(r["calibrated"], lo, hi))


def test_fit_arm_is_deterministic():
    Xm, y = _synthetic()
    a = X.fit_arm(Xm[:500], y[:500], Xm[500:])
    b = X.fit_arm(Xm[:500], y[:500], Xm[500:])
    assert np.array_equal(a["final"], b["final"]) and a["selected_C"] == b["selected_C"]


def test_single_class_training_labels_is_unfit_not_refit():
    Xm, _ = _synthetic()
    r = X.fit_arm(Xm[:500], np.zeros(500), Xm[500:])
    assert r["status"] == "UNFIT_SINGLE_CLASS_TRAINING_LABELS"


def test_arms_differ_only_in_llm_columns_and_have_no_group_penalty():
    m0 = ["a", "b", "c"]
    fam = {"x1": "SF_THRESHOLD_NONLINEARITY", "x2": "SF_MULTIMETRIC_INTERACTION",
           "x3": "SF_HALF_OR_GAME_STATE_INTERACTION",
           "x4": "SF_TWO_AXIS_OPPONENT_PROFILE_INTERSECTION"}
    llm = list(fam)
    assert X.arm_columns("M0", m0, llm, fam) == m0
    assert X.arm_columns("M1_ALL", m0, llm, fam) == m0 + llm
    for arm, f in X.ABLATION_FAMILY.items():
        cols = X.arm_columns(arm, m0, llm, fam)
        assert cols[:3] == m0 and [fam[c] for c in cols[3:]] == [f]
    pipe = X.make_pipeline()
    lr = pipe.named_steps["model"]
    assert (lr.solver, lr.max_iter, lr.tol, lr.random_state) == ("saga", 4000, 1e-4, 0)
    assert X.PRIMARY_ARMS == ("M0", "M1_ALL", "M1_THRESHOLD_ONLY", "M1_MULTIMETRIC_ONLY",
                              "M1_HALF_STATE_ONLY", "M1_PROFILE_ONLY")


def test_coverage_screen_is_the_inherited_060_rule():
    A = np.array([[1, np.nan], [2, np.nan], [3, 1.0], [4, np.nan], [5, 1.0]], float)
    assert X.coverage_keep(A) == [0]          # col1 = 0.4 < 0.6


def test_ece_matches_champion_formula():
    rng = np.random.default_rng(3)
    p = rng.random(1000); y = (rng.random(1000) < p).astype(float)
    e = 0.0
    for b in range(10):
        lo, hi = b / 10, (b + 1) / 10
        mk = (p >= lo) & (p < hi if b < 9 else p <= hi)
        if mk.sum():
            e += (mk.sum() / len(p)) * abs(p[mk].mean() - y[mk].mean())
    assert X.ece(p, y) == pytest.approx(e)


def test_bootstrap_is_seeded_blocked_and_percentile():
    d = np.r_[np.full(50, 0.01), np.full(50, -0.002)]
    blocks = [f"W{i // 10:02d}" for i in range(100)]
    a, b = X.block_bootstrap(d, blocks), X.block_bootstrap(d, blocks)
    assert a == b and a["n_blocks"] == 10 and a["n_resamples"] == 10000
    assert a["ci_lower"] <= d.mean() <= a["ci_upper"]


def test_bh_adjust_known_values():
    q = X.bh_adjust([0.01, 0.04, 0.03, 0.50])
    assert q == pytest.approx([0.04, 0.16 / 3, 0.16 / 3, 0.5])


def _rows(p, y, blocks):
    return {f"k{i}": {"p_final": float(p[i]), "y": float(y[i]), "iso_week_block": blocks[i]}
            for i in range(len(y))}


def test_compare_uses_paired_intersection_and_sign_convention():
    rng = np.random.default_rng(5)
    y = (rng.random(400) < 0.5).astype(float)
    blocks = [f"W{i // 20:02d}" for i in range(400)]
    good = np.clip(np.where(y == 1, 0.7, 0.3), 0.01, 0.99)
    a = _rows(np.full(400, 0.5), y, blocks)
    b = _rows(good, y, blocks)
    b.pop("k0")                               # M1 missing one fixture -> dropped from BOTH
    c = X.compare(a, b)
    assert c["n_paired"] == 399 and c["n_dropped_from_a"] == 1
    assert c["delta_logloss_a_minus_b"] > 0   # positive = M1 (b) better
    assert X.decision(c)["S2P1_DELTA_POSITIVE"] is True


def test_decision_rule_is_conjunctive():
    base = {"delta_logloss_a_minus_b": 0.002, "bootstrap": {"ci_lower": 0.0001},
            "ece_a": 0.01, "ece_b": 0.012}
    assert X.decision(base)["ITEM6_STAGE2_PRIMARY_GATE"] == "PASS"
    for mut in ({"delta_logloss_a_minus_b": 0.0009}, {"bootstrap": {"ci_lower": -0.0001}},
                {"ece_b": 0.0151}):
        assert X.decision({**base, **mut})["ITEM6_STAGE2_PRIMARY_GATE"] == "FAIL"
    assert EV.MINIMUM_PRACTICAL_LOGLOSS_IMPROVEMENT == 0.001


def test_precision_reading_never_changes_the_gate():
    cmp = {"delta_logloss_a_minus_b": 0.0005,
           "bootstrap": {"ci_lower": -0.002, "ci_upper": 0.003, "bootstrap_se": 0.0013}}
    r = X.precision_reading(cmp, "FAIL")
    assert r["FAIL_INTERPRETATION"] == "FAIL_AT_FROZEN_GATE_WITH_LIMITED_POWER_AT_0.0010"
    assert r["POWER_AT_TRUE_DELTA_EQUAL_MPI_UNDER_REALIZED_SE"] <= 0.5
    assert "ITEM6_STAGE2_PRIMARY_GATE" not in r


def test_gate_refuses_unauthorized_head():
    with pytest.raises(X.GateError):
        X.verify_git_state("0" * 40)


def test_executor_makes_no_llm_or_network_call_and_never_writes_champion():
    src = open("src/research/item6/stage2/executor.py").read()
    for banned in ("boto3", "bedrock", "anthropic", "requests.", "urllib", "Converse("):
        assert banned not in src
    assert "CHAMPION_PATH" in src and ".write_text" in src
    assert "(ROOT / CHAMPION_PATH).write" not in src and "open(CHAMPION_PATH" not in src
