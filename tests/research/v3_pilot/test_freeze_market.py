from src.research.v3_pilot.freeze import freeze_hash
from src.research.v3_pilot.market import goal_comparisons, corner_comparison

def test_freeze_hash_is_pinned():
    assert len(freeze_hash()) == 64

def test_goal_market_gate_uses_frozen_probability():
    dist = {
        "probabilities": {
            "2.5": {"p_over": 0.66},
            "3.5": {"p_over": 0.42},
        }
    }
    odds = {"data": {"bookmakers": [{
        "bookmaker": "Bet365",
        "markets": {"total_goals": {
            "2.5": {
                "over": {"last_seen": "2.10", "opening": "2.20"},
                "under": {"last_seen": "1.75", "opening": "1.70"},
            },
            "3.5": {
                "over": {"last_seen": "2.60", "opening": None},
                "under": {"last_seen": "1.50", "opening": None},
            },
        }},
    }]}}
    rows = goal_comparisons(dist, odds)
    row = next(r for r in rows if r["line"] == 2.5)
    assert row["side"] == "OVER"
    assert row["qualifies"] is True
    assert row["p_model_selected"] == 0.66
    assert row["opening"] is not None

def test_corner_main_line_is_closest_to_fifty_fifty_novig():
    dist = {"lambda_total": 10.2}
    odds = {"data": {"bookmakers": [{
        "bookmaker": "Bet365",
        "markets": {"match_corners": {
            "9.5": {
                "over": {"last_seen": "1.65", "opening": None},
                "under": {"last_seen": "2.20", "opening": None},
            },
            "10.5": {
                "over": {"last_seen": "1.91", "opening": None},
                "under": {"last_seen": "1.91", "opening": None},
            },
        }},
    }]}}
    row = corner_comparison(dist, odds)
    assert row is not None
    assert row["line"] == 10.5
