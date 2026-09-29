import pytest

from src.research.v3_pilot import audit

def test_metrics_compare_model_to_same_entry_market_rows():
    rows = [
        {
            "result": "WIN", "p_model": 0.75, "p_market_entry_novig": 0.55,
            "price_decimal": 1.8,
            "closing_benchmark": {
                "movement_toward_selection": 0.04,
                "genuine_close_window": True,
            },
        },
        {
            "result": "LOSS", "p_model": 0.62, "p_market_entry_novig": 0.52,
            "price_decimal": 2.0,
            "closing_benchmark": {
                "movement_toward_selection": 0.01,
                "genuine_close_window": True,
            },
        },
    ]
    out = audit._metrics(rows)
    assert out["proper_score_coverage"] == 2
    assert out["genuine_close_coverage"] == 1.0
    assert out["mean_clv_probability_movement_toward_selection"] == 0.025
    assert out["unit_stake_pnl"] == pytest.approx(-0.2)
    assert out["model_log_loss"] is not None
    assert out["market_entry_log_loss"] is not None

def test_adjudication_waits_for_complete_primary_cohort():
    primary = {
        "declared": 4, "pending": 4,
        "paired_log_loss_improvement": 0.01,
        "paired_brier_improvement": 0.01,
        "mean_clv_probability_movement_toward_selection": 0.01,
        "unit_stake_pnl": 1.0,
        "genuine_close_coverage": 1.0,
    }
    assert audit._adjudicate(primary, {"status": "PASS"}) == "NOT_READY"

def test_adjudication_is_directional_and_predeclared():
    primary = {
        "declared": 20, "pending": 0,
        "paired_log_loss_improvement": 0.01,
        "paired_brier_improvement": 0.01,
        "mean_clv_probability_movement_toward_selection": 0.01,
        "unit_stake_pnl": 1.0,
        "genuine_close_coverage": 0.9,
    }
    assert audit._adjudicate(primary, {"status": "PASS"}) == "DIRECTIONAL_PASS"
    primary["unit_stake_pnl"] = -1.0
    assert audit._adjudicate(primary, {"status": "PASS"}) == "INCONCLUSIVE"
