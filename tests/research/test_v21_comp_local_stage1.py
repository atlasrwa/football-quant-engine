from src.research.evaluation.v21_comp_local_stage1 import evaluate_gate


def _metrics(nll, ll=0.60, brier=0.21, mae=1.0):
    return {
        "n_fixtures": 100,
        "side_poisson_nll": nll,
        "side_mae": mae,
        "binary_log_loss": ll,
        "brier": brier,
    }


def test_gate_requires_primary_improvement_and_three_fold_wins():
    result = evaluate_gate(
        reference=_metrics(1.0),
        candidate=_metrics(0.99, ll=0.6005),
        fold_primary_wins=3,
    )
    assert result["passes_stage1_gate"] is True
    assert result["decision"] == "LAYER2_DEVELOPMENT_CANDIDATE_NOT_PROMOTED"

    failed = evaluate_gate(
        reference=_metrics(1.0),
        candidate=_metrics(0.99, ll=0.6005),
        fold_primary_wins=2,
    )
    assert failed["passes_stage1_gate"] is False


def test_gate_rejects_binary_log_loss_regression_above_frozen_tolerance():
    result = evaluate_gate(
        reference=_metrics(1.0, ll=0.60),
        candidate=_metrics(0.98, ll=0.60101),
        fold_primary_wins=4,
    )
    assert result["passes_stage1_gate"] is False


def test_gate_never_advances_primary_regression():
    result = evaluate_gate(
        reference=_metrics(1.0),
        candidate=_metrics(1.00001, ll=0.59),
        fold_primary_wins=4,
    )
    assert result["passes_stage1_gate"] is False
