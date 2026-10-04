from src.research.evaluation.v21_cmp_distribution_stage1 import _decision


def _metrics(joint, total_rps=1.0, binary=0.60):
    return {
        "n_fixtures": 100,
        "joint_log_score": joint,
        "total_log_score": 2.0,
        "side_mean_rps": 1.0,
        "total_rps": total_rps,
        "binary_log_loss": binary,
        "brier": 0.21,
    }


def test_cmp_gate_requires_primary_fold_and_distribution_support():
    result = _decision(
        _metrics(2.0, total_rps=1.0, binary=0.60),
        _metrics(1.99, total_rps=0.99, binary=0.6005),
        3,
    )
    assert result["passes_stage1_gate"] is True

    no_folds = _decision(
        _metrics(2.0),
        _metrics(1.99, total_rps=0.99, binary=0.59),
        2,
    )
    assert no_folds["passes_stage1_gate"] is False


def test_cmp_gate_rejects_rps_or_binary_regression():
    rps_bad = _decision(
        _metrics(2.0, total_rps=1.0),
        _metrics(1.99, total_rps=1.00001, binary=0.59),
        4,
    )
    assert rps_bad["passes_stage1_gate"] is False

    binary_bad = _decision(
        _metrics(2.0, total_rps=1.0, binary=0.60),
        _metrics(1.99, total_rps=0.99, binary=0.60101),
        4,
    )
    assert binary_bad["passes_stage1_gate"] is False
