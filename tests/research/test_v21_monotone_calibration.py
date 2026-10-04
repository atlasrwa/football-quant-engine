import pytest

from src.research.models.v21_monotone_calibration import (
    MonotoneLogitSpline,
    PlattIsotonicBlend,
    assert_monotone_transform,
)


def _sample():
    probs = [
        0.1,0.15,0.2,0.25,0.3,0.35,0.4,0.45,0.5,
        0.55,0.6,0.65,0.7,0.75,0.8,0.85,0.9
    ] * 8
    outcomes = []
    for p in probs:
        outcomes.append(
            (int(round(p * 10)) + len(outcomes)) % 10
            < int(round(p * 10))
        )
    return probs, outcomes, [1.0] * len(probs)


def test_platt_isotonic_blend_is_monotone():
    p,y,w = _sample()
    cal = PlattIsotonicBlend.fit(p,y,w,alpha=0.5,eps=1e-6)
    assert_monotone_transform(cal)
    assert cal.to_spec()["alpha"] == 0.5


def test_monotone_logit_spline_fits_and_is_monotone():
    p,y,w = _sample()
    cal = MonotoneLogitSpline.fit(
        p,y,w,
        eps=1e-6,
        ridge_lambda=10.0,
        curvature_multiplier=1.0,
        quantiles=(0.0,0.2,0.4,0.6,0.8,1.0),
        minimum_logit_increment=1e-6,
    )
    assert_monotone_transform(cal)
    assert len(cal.input_knots) >= 3


def test_spline_tail_extrapolation_remains_ordered():
    p,y,w = _sample()
    cal = MonotoneLogitSpline.fit(
        p,y,w,
        eps=1e-6,
        ridge_lambda=1.0,
        curvature_multiplier=1.0,
        quantiles=(0.0,0.2,0.4,0.6,0.8,1.0),
        minimum_logit_increment=1e-6,
    )
    values = [
        cal.transform(x)
        for x in (1e-5,0.01,0.5,0.99,1-1e-5)
    ]
    assert values == sorted(values)
    assert all(0.0 < x < 1.0 for x in values)


def test_blend_rejects_invalid_alpha():
    p,y,w = _sample()
    with pytest.raises(ValueError):
        PlattIsotonicBlend.fit(p,y,w,alpha=1.2,eps=1e-6)
