import json
from pathlib import Path

import pytest

from src.research.team_corners_v1.config import MODEL_FREEZE, SPEC
from src.research.team_corners_v1.market import (
    best_qualifier, compare_probability, comparisons, team_corner_pair,
)
from src.research.team_corners_v1.model import freeze, predict_fixture

KAZ = {
    "match_id": "mt_159946133", "competition_id": "comp_574977",
    "season_id": "sn_4571664", "ts": 1790949600.0, "kickoff_ts": 1790949600.0,
    "utc_date": "2026-10-02T14:00:00.000Z", "kickoff": "2026-10-02T14:00:00.000Z",
    "home_id": "tm_94197", "home_name": "Kazakhstan",
    "away_id": "tm_94208", "away_name": "Moldova",
    "is_neutral": False, "context": {"is_neutral": False},
}

def odds_payload():
    return {"data": {"match_id": KAZ["match_id"], "bookmakers": [{
        "bookmaker": "Bet365", "markets": {"team_corners": {
            "home": {"5.5": {"over": {"last_seen": "2.100"}, "under": {"last_seen": "1.667"}}},
            "away": {"3.5": {"over": {"last_seen": "2.200"}, "under": {"last_seen": "1.615"}}},
        }}
    }]}}
def test_spec_is_independent_and_preregistered():
    spec = json.loads(SPEC.read_text())
    assert spec["experiment"] == "QFE Team Corners V1"
    assert spec["independence"]["v371_unchanged"] is True
    assert spec["independence"]["v381_unchanged"] is True
    assert spec["independence"]["champion_unchanged"] is True
    assert spec["independence"]["llm_probability_path"] is False
    assert "latest valid" in spec["market"]["final_capture_policy"]

def test_model_freeze_integrity_and_untouched_holdout():
    art = freeze()
    assert art["freeze_sha256"] == json.loads(MODEL_FREEZE.read_text())["freeze_sha256"]
    assert art["split"]["holdout_side_rows"] >= 1000
    hold = art["untouched_holdout"]
    assert hold["binary_calibrated"]["log_loss"] < hold["binary_raw"]["log_loss"]
    assert hold["binary_calibrated"]["brier"] < hold["binary_raw"]["brier"]
    assert hold["count_metrics"]["ensemble"]["poisson_nll"] < hold["count_metrics"]["structural"]["poisson_nll"]

def test_model_is_monotone_across_team_corner_lines():
    pred = predict_fixture(KAZ)
    assert set(pred["sides"]) == {"home", "away"}
    for side in pred["sides"].values():
        probs = [side["probabilities"][str(x)]["p_over"] for x in (2.5,3.5,4.5,5.5,6.5,7.5)]
        assert all(a >= b for a, b in zip(probs, probs[1:]))
        assert side["mu"] > 0
def test_bet365_team_corner_parser_reads_each_side():
    payload = odds_payload()
    assert team_corner_pair(payload, "home", 5.5) == pytest.approx((2.1, 1.667))
    assert team_corner_pair(payload, "away", 3.5) == pytest.approx((2.2, 1.615))
    assert team_corner_pair(payload, "home", 4.5) is None

def test_frozen_gate_requires_probability_delta_and_break_even():
    good = compare_probability(0.68, 2.0, 1.8, role="home", line=4.5)
    assert good["qualifies"] is True
    low_probability = compare_probability(0.56, 2.0, 1.8, role="home", line=4.5)
    assert low_probability["qualifies"] is False
    no_price_edge = compare_probability(0.62, 1.5, 2.5, role="home", line=4.5)
    assert no_price_edge["qualifies"] is False

def test_only_provider_quoted_model_lines_are_compared():
    pred = predict_fixture(KAZ)
    rows = comparisons(pred, odds_payload())
    assert {(r["role"], r["line"]) for r in rows} == {("home", 5.5), ("away", 3.5)}
    assert all(r["team_name"] in {"Kazakhstan", "Moldova"} for r in rows)

def test_best_qualifier_is_largest_delta_within_team_side():
    rows = [
        {"role": "home", "qualifies": True, "delta": .06, "line": 3.5, "side": "OVER"},
        {"role": "home", "qualifies": True, "delta": .09, "line": 4.5, "side": "OVER"},
        {"role": "away", "qualifies": True, "delta": .20, "line": 2.5, "side": "UNDER"},
    ]
    assert best_qualifier(rows, "home")["line"] == 4.5
