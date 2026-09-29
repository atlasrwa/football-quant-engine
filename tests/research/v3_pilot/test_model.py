import math

from src.research.v3_pilot.model import (
    fit_goal_calibrators,
    predict_goals,
    predict_corners,
    poisson_over,
)

def _goal_history():
    rows = []
    teams = ["A","B","C","D"]
    mid = 0
    # season s1: 130 matches, enough prehistory
    for i in range(130):
        h = teams[i % 4]
        a = teams[(i + 1) % 4]
        rows.append({
            "match_id": f"s1_{i}", "competition_id": "c", "season_id": "s1",
            "ts": 1_000_000 + i * 3600,
            "home_id": h, "away_id": a,
            "score": {"home": (i % 3), "away": ((i + 1) % 2)},
        })
    # season s2: 6 matchdays x 10 matches = 60 calibration targets.
    base = 2_000_000
    for day in range(6):
        ts = base + day * 86400
        for j in range(10):
            i = day*10+j
            h = teams[i % 4]
            a = teams[(i + 2) % 4]
            rows.append({
                "match_id": f"s2_{i}", "competition_id": "c", "season_id": "s2",
                "ts": ts,
                "home_id": h, "away_id": a,
                "score": {"home": 1 + (i % 2), "away": (i % 2)},
            })
    return rows

def test_goal_model_calibrates_chronologically_and_predicts():
    rows = _goal_history()
    cal = fit_goal_calibrators(rows, "s3")
    assert cal["calibration_season_id"] == "s2"
    assert cal["calibrators"]["2.5"]["n"] >= 50
    target = {
        "match_id": "target", "competition_id": "c", "season_id": "s3",
        "ts": 3_000_000, "home_id": "A", "away_id": "B",
    }
    pred = predict_goals(rows, target, cal)
    for line in ("2.5","3.5"):
        p = pred["probabilities"][line]["p_over"]
        assert 0 < p < 1
    assert len(pred["distribution_hash"]) == 64

def test_corner_distribution_is_provider_history_only():
    rows = []
    teams = ["A","B","C","D"]
    for i in range(40):
        rows.append({
            "match_id": f"m{i}", "competition_id": "c", "season_id": "s",
            "ts": 1000 + i*100,
            "home_id": teams[i % 4], "away_id": teams[(i+1) % 4],
            "corners_home": float(4 + i % 4),
            "corners_away": float(3 + (i+1) % 3),
        })
    target = {
        "match_id": "t", "competition_id": "c", "season_id": "s",
        "ts": 10_000, "home_id": "A", "away_id": "B",
    }
    pred = predict_corners(rows, rows, target)
    assert pred["lambda_total"] > 0
    p = poisson_over(9.5, pred["lambda_total"])
    assert 0 < p < 1
