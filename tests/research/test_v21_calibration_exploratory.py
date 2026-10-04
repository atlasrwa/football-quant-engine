from src.research.evaluation.v21_calibration_exploratory import (
    _assert_ladder_coherence,
    _select_family,
)


class Identity:
    def transform(self, p, **kwargs):
        return float(p)


def test_ladder_coherence_accepts_monotone_over_probabilities():
    rows = [
        {
            "fixture_key": "f1",
            "group": "CORNERS_TOTAL",
            "role": None,
            "line": 7.5,
            "raw_probability": 0.7,
        },
        {
            "fixture_key": "f1",
            "group": "CORNERS_TOTAL",
            "role": None,
            "line": 8.5,
            "raw_probability": 0.5,
        },
        {
            "fixture_key": "f1",
            "group": "CORNERS_TOTAL",
            "role": None,
            "line": 9.5,
            "raw_probability": 0.3,
        },
    ]
    _assert_ladder_coherence(Identity(), rows)


def test_blend_tie_prefers_smaller_alpha():
    records = [
        {
            "candidate": "a",
            "family": "PLATT_ISOTONIC_BLEND",
            "parameter_value": 0.25,
            "metrics": {"log_loss": 0.6004, "brier": 0.20},
        },
        {
            "candidate": "b",
            "family": "PLATT_ISOTONIC_BLEND",
            "parameter_value": 0.75,
            "metrics": {"log_loss": 0.6000, "brier": 0.20},
        },
    ]
    selected = _select_family(
        records,
        "PLATT_ISOTONIC_BLEND",
        reference_brier=0.20,
    )
    assert selected["candidate"] == "a"


def test_spline_tie_prefers_stronger_regularization():
    records = [
        {
            "candidate": "a",
            "family": "PLATT_CENTERED_MONOTONE_LOGIT_SPLINE",
            "parameter_value": 1.0,
            "metrics": {"log_loss": 0.6000, "brier": 0.20},
        },
        {
            "candidate": "b",
            "family": "PLATT_CENTERED_MONOTONE_LOGIT_SPLINE",
            "parameter_value": 100.0,
            "metrics": {"log_loss": 0.6004, "brier": 0.20},
        },
    ]
    selected = _select_family(
        records,
        "PLATT_CENTERED_MONOTONE_LOGIT_SPLINE",
        reference_brier=0.20,
    )
    assert selected["candidate"] == "b"
