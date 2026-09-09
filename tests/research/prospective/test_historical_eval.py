"""Smoke test for the M0-M4 historical decomposition on synthetic corpus dicts.

Uses tiny hand-built match dicts (no network, no real corpus) to verify the
ladder runs, common support is enforced, and M5 is reported UNSUPPORTED.
"""

from __future__ import annotations

from src.research.prospective.historical_eval import run_historical_eval


def _match(i, home_goals, away_goals, o_odds, u_odds, league="L"):
    return {
        "id": f"mt_{i}",
        "date_unix": 1_600_000_000 + i * 86400,
        "_league": league,
        "_season": "2023",
        "homeID": 100 + (i % 6),
        "awayID": 200 + ((i + 3) % 6),
        "home_name": f"H{i % 6}",
        "away_name": f"A{(i + 3) % 6}",
        "status": "complete",
        "homeGoalCount": home_goals,
        "awayGoalCount": away_goals,
        "odds_ft_over25": o_odds,
        "odds_ft_under25": u_odds,
    }


def test_historical_eval_reports_m5_unsupported_and_degrades_gracefully():
    # Tiny synthetic slice: the champion cannot fit (too few labelled rows),
    # so the eval must degrade gracefully (empty scores) rather than raise, and
    # still report the M5 status. The full ladder is exercised against the real
    # corpus in scripts/prospective_historical_eval.py (committed artifacts).
    matches = [_match(i, i % 3, (i + 1) % 3, 1.9, 2.0) for i in range(30)]
    result = run_historical_eval(matches, family="goals", train_fraction=0.5)
    assert result.m5_status == "M5 HISTORICAL PIT UNSUPPORTED"
    assert result.scores == []  # graceful: champion could not fit this slice
    assert result.n_common == 0


def test_historical_eval_common_support_scores_equal_n():
    # Directly exercise the decomposition scorer's common-support guarantee
    # (independent of the champion's minimum-rows requirement).
    from src.research.prospective.decomposition import run_decomposition

    layers = {
        "M0": {("f1",): 0.5, ("f2",): 0.5, ("f3",): 0.5},
        "M3": {("f1",): 0.6, ("f2",): 0.4},  # f3 absent
    }
    outcomes = {("f1",): True, ("f2",): False}
    scores = run_decomposition(layers, outcomes, layer_order=["M0", "M3"])
    assert {s.n for s in scores} == {2}


def test_historical_eval_empty_input():
    result = run_historical_eval([], family="goals")
    assert result.n_common == 0
    assert result.scores == []
