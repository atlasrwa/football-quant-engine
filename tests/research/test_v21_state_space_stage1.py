from src.research.models.hierarchical_state_space import (
    HierarchicalStateSpaceConfig,
)
from src.research.evaluation.v21_state_space_stage1 import _selection


def _cell(nll, bll=0.60, brier=0.21):
    return {
        "side_poisson_nll": nll,
        "side_mae": 1.0,
        "binary_log_loss": bll,
        "brier": brier,
        "latent_log_sd_home": 0.2,
        "latent_log_sd_away": 0.2,
        "home_interval_90": [1.0, 2.0],
        "away_interval_90": [1.0, 2.0],
        "effective_support": 10.0,
        "supported": True,
    }


def _rows(candidate_nlls, candidate_bll=0.599):
    rows = []
    for i, fold in enumerate(("D1", "D2", "D3", "D4")):
        for j in range(2):
            row = {
                "fixture_key": f"{fold}-{j}",
                "fold_id": fold,
                "target": "goals",
                "REFERENCE": _cell(1.0, 0.60),
            }
            for profile in ("CONSERVATIVE", "BALANCED", "RESPONSIVE"):
                row[profile] = _cell(
                    candidate_nlls[profile][i],
                    candidate_bll,
                )
            rows.append(row)
    return rows


def test_selection_requires_three_of_four_fold_primary_wins():
    protocol = {"evaluation": {}}
    rows = _rows(
        {
            "CONSERVATIVE": [0.99, 0.99, 0.99, 1.02],
            "BALANCED": [0.98, 1.01, 1.01, 0.98],
            "RESPONSIVE": [1.01, 1.01, 1.01, 0.90],
        }
    )
    result = _selection(protocol=protocol, rows=rows, target_name="goals")
    cons = next(
        x for x in result["candidates"] if x["profile"] == "CONSERVATIVE"
    )
    assert cons["fold_primary_wins"] == 3
    assert cons["qualifies_stage1_gate"] is True


def test_selection_blocks_binary_log_loss_regression_over_tolerance():
    protocol = {"evaluation": {}}
    rows = _rows(
        {
            "CONSERVATIVE": [0.95, 0.95, 0.95, 0.95],
            "BALANCED": [0.96, 0.96, 0.96, 0.96],
            "RESPONSIVE": [0.97, 0.97, 0.97, 0.97],
        },
        candidate_bll=0.602,
    )
    result = _selection(protocol=protocol, rows=rows, target_name="goals")
    assert result["stage1_advances"] is False


def test_state_space_config_type_is_importable_for_runner_contract():
    assert HierarchicalStateSpaceConfig is not None
