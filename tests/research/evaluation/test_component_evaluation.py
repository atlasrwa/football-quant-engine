from src.research.evaluation.component_evaluation import _decision


def _metric(mean, lo, hi):
    return {"mean_improvement": mean, "ci_low": lo, "ci_high": hi}


def test_mixed_binary_candidate_is_not_called_consistent_win():
    metrics = {
        "total_count_nll": _metric(-0.01, -0.02, -0.001),
        "binary_log_loss": _metric(0.002, 0.001, 0.004),
        "brier": _metric(0.001, 0.0002, 0.002),
    }
    assert _decision(metrics) == "BINARY_MARKET_CANDIDATE_MIXED_TOTAL_DISTRIBUTION"


def test_all_positive_means_with_crossing_cis_remain_weak():
    metrics = {
        "total_count_nll": _metric(0.002, -0.002, 0.006),
        "binary_log_loss": _metric(0.001, -0.002, 0.004),
        "brier": _metric(0.0005, -0.001, 0.002),
    }
    assert _decision(metrics) == "WEAK_MIXED_SIGNAL_CIS_CROSS_ZERO"


def test_materially_worse_candidate_is_rejected():
    metrics = {
        "total_count_nll": _metric(-0.02, -0.03, -0.01),
        "binary_log_loss": _metric(-0.01, -0.02, -0.005),
        "brier": _metric(-0.005, -0.008, -0.002),
    }
    assert _decision(metrics) == "REJECT_MATERIALLY_WORSE"
