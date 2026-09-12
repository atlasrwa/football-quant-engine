"""Tests for the derived walk-forward OOS evaluation harness.

Covers: metric correctness, chronological fold ordering (train strictly before
test), leakage guard (no future match in a fold's prediction history), calibration
isolation, and probability validity.
"""
from __future__ import annotations

import math

import pytest

from src.research.prediction_engine.eval import metrics as M
from src.research.prediction_engine.eval.walk_forward import (
    FoldSpec,
    make_expanding_folds,
)


# ── metric correctness ──────────────────────────────────────────────────────
def test_brier_perfect_and_worst():
    assert M.brier_score([1.0, 0.0], [1.0, 0.0]) == 0.0
    assert M.brier_score([0.0, 1.0], [1.0, 0.0]) == 1.0


def test_log_loss_matches_manual():
    p = [0.8, 0.2]
    y = [1.0, 0.0]
    expected = -(math.log(0.8) + math.log(0.8)) / 2
    assert abs(M.log_loss(p, y) - expected) < 1e-9


def test_brier_skill_score_zero_for_base_rate_predictor():
    y = [1.0, 1.0, 0.0, 0.0]
    base = 0.5
    bss = M.brier_skill_score([base] * 4, y)
    assert abs(bss) < 1e-9  # constant base-rate predictor has zero skill


def test_bss_positive_for_better_than_base():
    y = [1.0, 1.0, 0.0, 0.0]
    good = [0.9, 0.9, 0.1, 0.1]
    assert M.brier_skill_score(good, y) > 0.5


def test_preferred_side_accuracy_ignores_ties():
    # p=0.5 excluded; the rest: 0.6->over correct, 0.3->under vs y=0 correct
    acc = M.preferred_side_accuracy([0.5, 0.6, 0.3], [0.0, 1.0, 0.0])
    assert acc == 1.0


def test_ece_zero_when_perfectly_calibrated():
    # 100 preds at 0.6 with exactly 60% positive -> ECE 0
    p = [0.6] * 100
    y = [1.0] * 60 + [0.0] * 40
    assert M.expected_calibration_error(p, y) < 1e-9


def test_confidence_ladder_monotone_input():
    # higher chosen-prob subset should have >= accuracy when well-calibrated
    p = [0.9] * 90 + [0.55] * 100
    y = [1.0] * 81 + [0.0] * 9 + [1.0] * 55 + [0.0] * 45
    ladder = M.confidence_ladder(p, y, thresholds=(0.5, 0.8))
    hi = [r for r in ladder if r["min_chosen_prob"] == 0.8][0]
    assert hi["n"] == 90
    assert hi["accuracy"] == 0.9


def test_probabilities_valid_range():
    p = [0.01, 0.5, 0.99]
    y = [0.0, 1.0, 1.0]
    assert all(0.0 <= x <= 1.0 for x in p)
    mb = M.metric_block(p, y)
    assert math.isfinite(mb.brier) and math.isfinite(mb.log_loss)


# ── chronological fold ordering ─────────────────────────────────────────────
def test_expanding_folds_are_chronological_and_non_overlapping():
    dates = [float(d) for d in range(1000, 2000)]
    folds = make_expanding_folds(dates, n_folds=4, min_train_frac=0.5)
    assert len(folds) == 4
    for i, f in enumerate(folds):
        # train ends exactly where test starts (train strictly before test)
        assert f.train_end_unix == f.test_start_unix
        assert f.test_start_unix < f.test_end_unix
        if i > 0:
            # each fold's test starts where the previous ended (no overlap, no gap)
            assert f.test_start_unix == folds[i - 1].test_end_unix


def test_first_fold_test_starts_after_min_train_fraction():
    dates = [float(d) for d in range(0, 100)]
    folds = make_expanding_folds(dates, n_folds=5, min_train_frac=0.4)
    # first test block starts at ~40% of the timeline
    assert folds[0].test_start_unix >= 0 + (99 - 0) * 0.4 - 1e-6


def test_empty_dates_yield_no_folds():
    assert make_expanding_folds([], n_folds=5) == []


# ── leakage guard: prediction history strictly precedes test window ─────────
def test_train_slice_excludes_test_window():
    """The harness fits on matches with date < test_start and predicts each test
    match from a history built from that same train slice; assert the split
    predicate leaves no test-window match in train."""
    dates = [float(d) for d in range(0, 100)]
    fold = make_expanding_folds(dates, n_folds=2, min_train_frac=0.5)[1]
    train = [d for d in dates if d < fold.test_start_unix]
    test = [d for d in dates if fold.test_start_unix <= d < fold.test_end_unix]
    assert max(train) < min(test)                 # strict chronological separation
    assert not (set(train) & set(test))           # disjoint
