from research.evidence_v32.run_v34_stacking import (
    fit_stack_weight, stack_predictions, v3_goal_rows
)


def _pred(mid, target, event, p):
    return {
        "match_id": mid, "competition_id": "c1", "date": "2026-01-01",
        "target": target, "event": event, "p": p,
    }


def test_stack_weight_moves_to_better_parent_on_calibration():
    ref = [_pred("a", "total>2.5", 1, 0.55),
           _pred("b", "total>2.5", 0, 0.45),
           _pred("c", "total>2.5", 1, 0.52),
           _pred("d", "total>2.5", 0, 0.48)]
    chal = [_pred("a", "total>2.5", 1, 0.80),
            _pred("b", "total>2.5", 0, 0.20),
            _pred("c", "total>2.5", 1, 0.75),
            _pred("d", "total>2.5", 0, 0.25)]
    w = fit_stack_weight(ref, chal)
    assert w > 0.9


def test_stack_predictions_preserve_common_fixture_and_event():
    ref = [_pred("a", "total>9.5", 1, 0.60)]
    chal = [_pred("a", "total>9.5", 1, 0.70)]
    a, b, s = stack_predictions(ref, chal, 0.5, 3)
    assert len(a) == len(b) == len(s) == 1
    assert s[0]["fold"] == 3
    assert s[0]["event"] == 1
    assert 0.60 < s[0]["p"] < 0.70


def test_v3_goal_rows_are_competition_scoped():
    rows = [
        {
            "competition_id":"c1", "match_id":"m1", "kickoff_ts":1,
            "home_id":"h", "away_id":"a", "season_id":"s1",
            "targets":{"goals.home":{"value":2},"goals.away":{"value":1}},
        },
        {
            "competition_id":"c2", "match_id":"m2", "kickoff_ts":2,
            "home_id":"x", "away_id":"y", "season_id":"s2",
            "targets":{"goals.home":{"value":0},"goals.away":{"value":0}},
        },
    ]
    grouped = v3_goal_rows(rows)
    assert set(grouped) == {"c1","c2"}
    assert grouped["c1"][0]["score"] == {"home":2,"away":1}
