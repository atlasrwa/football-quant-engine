"""Tests for the 30-day evaluation window.

Most of these assert *refusals*. A preregistered window is only worth having if it
cannot be moved, shortened, or read early once results start arriving, so each of
those three routes is closed and each closure is tested.
"""

from __future__ import annotations

import json

import pytest

from src.research.prediction_engine.evaluation_window import (
    WINDOW_CONTRACT,
    WINDOW_DAYS,
    EvaluationWindowError,
    SettledObservation,
    load_settled,
    load_window,
    open_window,
    projected_power,
    record_settled,
    settled_counts,
    window_report,
)
from src.research.prediction_engine.scope import MIN_SETTLED_FOR_CALIBRATION

EPOCH = 1_789_128_000
DAY = 86_400


@pytest.fixture()
def window_path(tmp_path):
    return tmp_path / "evaluation_window.json"


@pytest.fixture()
def settled_path(tmp_path):
    return tmp_path / "settled_forecasts.jsonl"


def _open(window_path, **overrides):
    kwargs = {
        "commitment_hash": "first-post-fix-hash",
        "generated_at_utc": "2026-09-07T12:00:00+00:00",
        "generated_at_unix": EPOCH,
        "model_version": "hierarchical-count/v1",
        "corpus_content_hash": "corpus-abc",
        "path": window_path,
    }
    kwargs.update(overrides)
    return open_window(**kwargs)


def _observation(index: int, *, generated_at_unix: int, league="L", line=9.5, p=0.5, y=1.0):
    return SettledObservation(
        fixture_id=f"f{index}",
        league=league,
        family="corners",
        line=line,
        p_over=p,
        outcome=y,
        commitment_hash=f"h{index}",
        generated_at_unix=generated_at_unix,
        kickoff_unix=generated_at_unix + 8 * 3600,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Opening and marking the epoch
# ─────────────────────────────────────────────────────────────────────────────
def test_window_marks_the_first_post_fix_forecast(window_path) -> None:
    window = _open(window_path)
    assert window.contract == WINDOW_CONTRACT
    assert window.epoch_commitment_hash == "first-post-fix-hash"
    assert window.window_days == WINDOW_DAYS == 30
    assert window.closes_at_unix == EPOCH + 30 * DAY
    persisted = json.loads(window_path.read_text())
    assert persisted["epoch_commitment_hash"] == "first-post-fix-hash"
    assert "stale corpus" in persisted["note"]


def test_reopening_with_the_same_forecast_is_idempotent(window_path) -> None:
    first = _open(window_path)
    second = _open(window_path)
    assert second.epoch_unix == first.epoch_unix
    assert second.epoch_commitment_hash == first.epoch_commitment_hash


def test_remarking_the_epoch_is_refused(window_path) -> None:
    """Moving the start after publication began would let it suit the results."""
    _open(window_path)
    with pytest.raises(EvaluationWindowError, match="already open"):
        _open(window_path, commitment_hash="a-later-forecast", generated_at_unix=EPOCH + DAY)


def test_shortening_an_open_window_is_refused(window_path) -> None:
    window = _open(window_path)
    with pytest.raises(EvaluationWindowError, match="refusing to change"):
        window.with_days(14)
    assert window.with_days(30) is window


def test_reserved_ledger_basenames_are_refused(tmp_path) -> None:
    """Pilot C, the manual predictor and the scanner keep their own records."""
    for reserved in (
        "pilotC_commitments.jsonl",
        "manual_predictions.jsonl",
        "scanner_scorecard.json",
        "commitments.jsonl",
    ):
        with pytest.raises(ValueError, match="refusing to use"):
            _open(tmp_path / reserved)


def test_window_round_trips_through_disk(window_path) -> None:
    written = _open(window_path)
    loaded = load_window(window_path)
    assert loaded == written


def test_missing_window_loads_as_none(window_path) -> None:
    assert load_window(window_path) is None


# ─────────────────────────────────────────────────────────────────────────────
# Pre-epoch exclusion
# ─────────────────────────────────────────────────────────────────────────────
def test_pre_epoch_forecasts_are_excluded(window_path) -> None:
    window = _open(window_path)
    assert window.includes(EPOCH - 1) is False
    assert window.includes(EPOCH) is True
    assert window.includes(EPOCH + 29 * DAY) is True
    assert window.includes(window.closes_at_unix + 1) is False


def test_report_counts_and_excludes_stale_corpus_forecasts(window_path) -> None:
    window = _open(window_path)
    observations = [
        _observation(1, generated_at_unix=EPOCH - 10 * DAY),
        _observation(2, generated_at_unix=EPOCH - DAY),
        _observation(3, generated_at_unix=EPOCH + DAY),
        _observation(4, generated_at_unix=EPOCH + 2 * DAY),
    ]
    report = window_report(
        now_unix=EPOCH + 31 * DAY, window=window, observations=observations
    )
    assert report["n_settled_in_window"] == 2
    assert report["n_excluded_pre_epoch"] == 2
    assert "diagnostic only" in report["exclusion_rule"]


def test_settled_counts_exclude_pre_epoch_observations(window_path) -> None:
    window = _open(window_path)
    observations = [
        _observation(1, generated_at_unix=EPOCH - DAY),
        _observation(2, generated_at_unix=EPOCH + DAY),
        _observation(3, generated_at_unix=EPOCH + DAY, line=10.5),
    ]
    counts = settled_counts(observations, window)
    assert counts[("L", "corners", 9.5)] == 1
    assert counts[("L", "corners", 10.5)] == 1


# ─────────────────────────────────────────────────────────────────────────────
# No verdict before the window closes
# ─────────────────────────────────────────────────────────────────────────────
def test_no_calibration_figure_before_the_window_closes(window_path) -> None:
    window = _open(window_path)
    observations = [
        _observation(i, generated_at_unix=EPOCH + DAY, p=0.5, y=float(i % 2))
        for i in range(400)
    ]
    report = window_report(
        now_unix=EPOCH + 10 * DAY, window=window, observations=observations
    )
    assert report["status"] == "window_open"
    assert "cells" not in report
    assert report["days_remaining"] == pytest.approx(20.0, abs=0.01)
    assert "preregistered" in report["detail"]


def test_counts_only_mode_still_publishes_no_calibration(window_path) -> None:
    window = _open(window_path)
    observations = [
        _observation(i, generated_at_unix=EPOCH + DAY) for i in range(400)
    ]
    report = window_report(
        now_unix=EPOCH + 10 * DAY,
        window=window,
        observations=observations,
        allow_open_window=True,
    )
    assert report["status"] == "window_open_counts_only"
    assert "cells" not in report
    assert report["n_settled_in_window"] == 400
    assert report["settled_per_cell"]


def test_closed_window_reports_per_cell_calibration_above_the_gate(window_path) -> None:
    window = _open(window_path)
    observations = [
        _observation(
            i,
            generated_at_unix=EPOCH + DAY,
            p=0.5,
            y=float(i % 2),
        )
        for i in range(MIN_SETTLED_FOR_CALIBRATION + 20)
    ]
    report = window_report(
        now_unix=EPOCH + 31 * DAY, window=window, observations=observations
    )
    assert report["status"] == "closed"
    cell = report["cells"][0]
    assert cell["gate_met"] is True
    assert cell["calibration"] is not None
    assert cell["calibration"]["ece"] == pytest.approx(0.0, abs=1e-9)
    assert cell["reliability_curve"]
    assert cell["skill_claim_blocked"] is True
    assert report["power_summary"]["n_cells_with_enough_settled"] == 1


def test_the_minimum_sample_gate_suppresses_thin_cells(window_path) -> None:
    """The existing gate is kept: an ECE on a handful of settlements is noise."""
    window = _open(window_path)
    observations = [
        _observation(i, generated_at_unix=EPOCH + DAY) for i in range(25)
    ]
    report = window_report(
        now_unix=EPOCH + 31 * DAY, window=window, observations=observations
    )
    cell = report["cells"][0]
    assert cell["gate_met"] is False
    assert cell["calibration"] is None
    assert cell["reliability_curve"] == []
    assert cell["n_settled"] == 25
    assert cell["shortfall"] == MIN_SETTLED_FOR_CALIBRATION - 25
    assert "insufficient settled predictions" in cell["gate_notice"]


def test_underpowered_cells_are_reported_as_such_not_as_a_verdict(window_path) -> None:
    window = _open(window_path)
    observations = [
        _observation(i, generated_at_unix=EPOCH + DAY, league=f"L{i % 4}")
        for i in range(40)
    ]
    report = window_report(
        now_unix=EPOCH + 31 * DAY, window=window, observations=observations
    )
    summary = report["power_summary"]
    assert summary["n_cells"] == 4
    assert summary["n_cells_with_enough_settled"] == 0
    assert summary["n_cells_underpowered"] == 4
    assert summary["verdict_available"] is False
    assert "underpowered" in summary["expectation"]
    assert "sample-size report first" in summary["honest_reading"]


def test_report_before_any_window_is_opened(window_path, settled_path) -> None:
    report = window_report(
        now_unix=EPOCH, window_path=window_path, settled_path=settled_path
    )
    assert report["status"] == "not_opened"
    assert report["window_days"] == WINDOW_DAYS


# ─────────────────────────────────────────────────────────────────────────────
# Settled ledger
# ─────────────────────────────────────────────────────────────────────────────
def test_settled_observations_round_trip(settled_path) -> None:
    written = [
        _observation(1, generated_at_unix=EPOCH + DAY, p=0.61, y=1.0),
        _observation(2, generated_at_unix=EPOCH + 2 * DAY, p=0.4, y=0.0, line=None),
    ]
    for observation in written:
        record_settled(observation, path=settled_path)
    loaded = load_settled(settled_path)
    assert loaded == written
    assert loaded[1].line is None


def test_settled_ledger_refuses_reserved_basenames(tmp_path) -> None:
    with pytest.raises(ValueError, match="refusing to use"):
        record_settled(
            _observation(1, generated_at_unix=EPOCH),
            path=tmp_path / "pilotC_settled.jsonl",
        )


def test_misses_are_recorded_as_well_as_hits(settled_path) -> None:
    record_settled(_observation(1, generated_at_unix=EPOCH, y=0.0), path=settled_path)
    record_settled(_observation(2, generated_at_unix=EPOCH, y=1.0), path=settled_path)
    outcomes = sorted(item.outcome for item in load_settled(settled_path))
    assert outcomes == [0.0, 1.0]


# ─────────────────────────────────────────────────────────────────────────────
# Power arithmetic, stated in advance
# ─────────────────────────────────────────────────────────────────────────────
def test_projection_says_up_front_that_30_days_is_underpowered() -> None:
    projection = projected_power(
        n_leagues=4, fixtures_per_league_per_month=40, n_cells_per_fixture=21
    )
    assert projection["expected_settled_per_cell"] < MIN_SETTLED_FOR_CALIBRATION
    assert projection["expected_cells_clearing_gate"] == "none"
    assert projection["months_to_fill_one_cell"] > 1
    assert "not reachable in one 30-day window" in projection["reading"]
