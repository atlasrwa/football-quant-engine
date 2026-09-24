import pytest

from src.research.target_aware_market_panel import support_v12 as S


def test_training_coverage_uses_only_original_scored_rows_before_fold_start():
    fixtures = [{"kickoff": i} for i in range(5)]
    fold = {"test_start": 3, "n_train": 3}
    got = S.training_coverage([1.0, None, 2.0, 3.0, 4.0], fixtures, fold)
    assert got == {"n_train": 3, "n_nonnull": 2, "coverage": 2 / 3}


def test_training_coverage_fails_on_denominator_drift():
    with pytest.raises(ValueError, match="training denominator mismatch"):
        S.training_coverage([1.0], [{"kickoff": 0}], {"test_start": 1, "n_train": 2})


def _item(family, fold_cov, similarity, sig):
    return {
        "family": family,
        "template_type": S.SIMILARITY_TYPE if similarity else "ROLLING_PROFILE",
        "canonical_signature_sha256": sig,
        "training_fold_coverage": {str(i): {"coverage": c} for i, c in enumerate(fold_cov)},
    }


def test_gate_requires_similarity_for_every_family_and_fold():
    folds = {"folds": {"0": {}, "1": {}}}
    rows = [
        _item("GOALS", [0.8, 0.8], True, "g-sim"),
        _item("CORNERS", [0.8, 0.8], True, "c-sim"),
        _item("BOOKINGS", [0.8, 0.8], True, "b-sim"),
        _item("TEAM_TOTALS", [0.8, 0.8], False, "t-nonsim"),
    ]
    details, passed = S.evaluability_gate(rows, folds)
    assert passed is False
    assert details["TEAM_TOTALS"]["0"]["n_class_c_pass"] == 1
    assert details["TEAM_TOTALS"]["0"]["n_similarity_pass"] == 0


def test_gate_passes_only_when_every_family_fold_has_similarity():
    folds = {"folds": {"0": {}, "1": {}}}
    rows = [_item(f, [0.6, 0.7], True, f) for f in
            ("GOALS", "CORNERS", "BOOKINGS", "TEAM_TOTALS")]
    _, passed = S.evaluability_gate(rows, folds)
    assert passed is True


def test_gate_rejects_threshold_change():
    with pytest.raises(ValueError, match="frozen at 0.60"):
        S.evaluability_gate([], {"folds": {}}, threshold=0.59)
