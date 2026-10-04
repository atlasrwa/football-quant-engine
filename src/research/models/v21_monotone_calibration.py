"""Additive V2.1 monotone calibration challengers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
from scipy.optimize import minimize

from src.research.layer4.calibrators import (
    Calibrator,
    PlattGlobal,
    WeightedIsotonic,
    _clip,
    _logit,
    _sigmoid,
    weighted_log_loss,
)


def _weighted_quantile(values, weights, quantiles):
    x = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    q = np.asarray(quantiles, dtype=float)
    if len(x) != len(w) or not len(x):
        raise ValueError("values and weights must be aligned and non-empty")
    if np.any(w < 0) or float(w.sum()) <= 0:
        raise ValueError("weights must be non-negative with positive total")
    order = np.argsort(x, kind="mergesort")
    sx, sw = x[order], w[order]
    cumulative = np.cumsum(sw)
    centers = (cumulative - 0.5 * sw) / float(sw.sum())
    return [
        float(np.interp(float(qq), centers, sx, left=sx[0], right=sx[-1]))
        for qq in q
    ]


def _unique_increasing(values, minimum_points=3):
    out = []
    for value in values:
        v = float(value)
        if not out or v > out[-1] + 1e-12:
            out.append(v)
    if len(out) < minimum_points:
        raise ValueError("insufficient distinct calibration score support")
    return tuple(out)


@dataclass(frozen=True)
class PlattIsotonicBlend(Calibrator):
    platt: PlattGlobal
    isotonic: WeightedIsotonic
    alpha: float
    name = "PLATT_ISOTONIC_BLEND"

    def __post_init__(self):
        if not 0.0 <= self.alpha <= 1.0:
            raise ValueError("alpha must be in [0,1]")

    @classmethod
    def fit(cls, probs, outcomes, weights, *, alpha, eps):
        return cls(
            platt=PlattGlobal.fit(probs, outcomes, weights, eps),
            isotonic=WeightedIsotonic.fit(probs, outcomes, weights),
            alpha=float(alpha),
        )

    def transform(self, p, **kwargs):
        qp = self.platt.transform(p)
        qi = self.isotonic.transform(p)
        return float((1.0 - self.alpha) * qp + self.alpha * qi)

    def to_spec(self):
        return {
            "method": self.name,
            "alpha": self.alpha,
            "platt": self.platt.to_spec(),
            "isotonic": self.isotonic.to_spec(),
        }


@dataclass(frozen=True)
class MonotoneLogitSpline(Calibrator):
    input_knots: tuple[float, ...]
    output_knots: tuple[float, ...]
    eps: float
    ridge_lambda: float
    curvature_multiplier: float
    reference_platt: dict[str, Any]
    name = "PLATT_CENTERED_MONOTONE_LOGIT_SPLINE"

    def __post_init__(self):
        if len(self.input_knots) != len(self.output_knots):
            raise ValueError("input/output knots must align")
        if len(self.input_knots) < 3:
            raise ValueError("at least three knots required")
        if any(
            self.input_knots[i + 1] <= self.input_knots[i]
            for i in range(len(self.input_knots) - 1)
        ):
            raise ValueError("input knots must be strictly increasing")
        if any(
            self.output_knots[i + 1] <= self.output_knots[i]
            for i in range(len(self.output_knots) - 1)
        ):
            raise ValueError("output knots must be strictly increasing")

    @staticmethod
    def _map_logit_scalar(z, xk, yk):
        z = float(z)
        if z <= xk[0]:
            slope = (yk[1] - yk[0]) / (xk[1] - xk[0])
            return float(yk[0] + slope * (z - xk[0]))
        if z >= xk[-1]:
            slope = (yk[-1] - yk[-2]) / (xk[-1] - xk[-2])
            return float(yk[-1] + slope * (z - xk[-1]))
        return float(np.interp(z, np.asarray(xk), np.asarray(yk)))


    @classmethod
    def fit(
        cls,
        probs,
        outcomes,
        weights,
        *,
        eps,
        ridge_lambda,
        curvature_multiplier,
        quantiles,
        minimum_logit_increment,
    ):
        p = np.asarray([_clip(x, eps) for x in probs], dtype=float)
        y = np.asarray(outcomes, dtype=float)
        w = np.asarray(weights, dtype=float)
        if len(p) < 10 or len(set(bool(v) for v in y)) < 2:
            raise ValueError("insufficient calibration support")
        z = np.asarray([_logit(x, eps) for x in p], dtype=float)
        xk = _unique_increasing(_weighted_quantile(z, w, quantiles))
        platt = PlattGlobal.fit(p, y, w, eps)
        base = np.asarray(
            [platt.intercept + platt.slope * knot for knot in xk],
            dtype=float,
        )
        dx = np.diff(np.asarray(xk))
        minimum = max(float(minimum_logit_increment), 1e-12)

        def mapped_logits(v):
            return np.asarray(
                [cls._map_logit_scalar(float(zz), xk, v) for zz in z],
                dtype=float,
            )

        def objective(v):
            qz = mapped_logits(v)
            q = np.asarray([_sigmoid(float(a)) for a in qz], dtype=float)
            ll = weighted_log_loss(q, y, w, eps) * float(w.sum())
            deviation = float(np.dot(v - base, v - base))
            slopes = np.diff(v) / dx
            curvature = (
                float(np.dot(np.diff(slopes), np.diff(slopes)))
                if len(slopes) > 1
                else 0.0
            )
            return float(
                ll
                + float(ridge_lambda)
                * (
                    deviation
                    + float(curvature_multiplier) * curvature
                )
            )

        constraints = [
            {
                "type": "ineq",
                "fun": (
                    lambda v, i=i: float(
                        v[i + 1] - v[i] - minimum
                    )
                ),
            }
            for i in range(len(xk) - 1)
        ]
        result = minimize(
            objective,
            base.copy(),
            method="SLSQP",
            constraints=constraints,
            options={"maxiter": 3000, "ftol": 1e-11},
        )
        if not result.success or not np.all(np.isfinite(result.x)):
            raise RuntimeError(
                f"monotone spline fit failed: {result.message}"
            )
        if any(
            result.x[i + 1] <= result.x[i]
            for i in range(len(result.x) - 1)
        ):
            raise RuntimeError("optimizer returned non-monotone spline")
        return cls(
            input_knots=tuple(float(v) for v in xk),
            output_knots=tuple(float(v) for v in result.x),
            eps=float(eps),
            ridge_lambda=float(ridge_lambda),
            curvature_multiplier=float(curvature_multiplier),
            reference_platt=platt.to_spec(),
        )

    def transform(self, p, **kwargs):
        z = _logit(float(p), self.eps)
        qz = self._map_logit_scalar(
            z,
            self.input_knots,
            self.output_knots,
        )
        return _sigmoid(qz)

    def to_spec(self):
        return {
            "method": self.name,
            "input_knots": list(self.input_knots),
            "output_knots": list(self.output_knots),
            "eps": self.eps,
            "ridge_lambda": self.ridge_lambda,
            "curvature_multiplier": self.curvature_multiplier,
            "reference_platt": self.reference_platt,
        }


def assert_monotone_transform(
    calibrator,
    *,
    grid_size=2001,
    tolerance=1e-12,
):
    if grid_size < 3:
        raise ValueError("grid_size must be >=3")
    grid = np.linspace(1e-6, 1.0 - 1e-6, grid_size)
    values = [float(calibrator.transform(float(p))) for p in grid]
    if any(
        values[i + 1] + tolerance < values[i]
        for i in range(len(values) - 1)
    ):
        raise ValueError("calibration transform is not monotone")
