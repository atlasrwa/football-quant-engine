"""Post-hoc probability calibration for model outputs.

Raw model outputs are frequently overconfident even when the underlying
model is otherwise sound. Calibration transforms raw probabilities into
well-calibrated ones where "predicted 70%" means the event happens ~70%
of the time.

Implements two standard calibration methods:
1. Platt scaling — logistic regression on raw probabilities (parametric)
2. Isotonic regression — non-parametric monotone mapping

Both are implemented without sklearn dependency, using only numpy/scipy.

These calibrators are mapping primitives only. Under QFE V2 they must be fit
on externally constructed chronological OOF prediction/outcome pairs; this
module does not split or refit a base prediction model.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

# ═══════════════════════════════════════════════════════════════
# PLATT SCALING
# ═══════════════════════════════════════════════════════════════


class PlattScaler:
    """Platt scaling: logistic regression on raw probabilities.

    Fits sigmoid parameters A, B such that:
        calibrated_p = 1 / (1 + exp(A * raw_p + B))

    This is the standard parametric calibration method. Works well when
    the calibration curve is approximately sigmoid-shaped (common for
    models that are systematically over/under-confident).

    Requires at least ~30 calibration samples to be stable.
    """

    def __init__(self) -> None:
        self._a: float = -1.0  # Default: identity-ish mapping
        self._b: float = 0.0
        self._fitted: bool = False

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    def fit(self, raw_probs: list[float], actuals: list[bool]) -> None:
        """Fit Platt scaling parameters.

        Uses the Platt (1999) algorithm with regularization.

        Args:
            raw_probs: Raw model probabilities in [0, 1].
            actuals: True outcomes (True = event happened).
        """
        if len(raw_probs) < 10:
            # Too few samples — use identity
            self._a = -1.0
            self._b = 0.0
            self._fitted = True
            return

        # Convert to log-odds space for stability
        # We fit: P(y=1 | f) = 1 / (1 + exp(A*f + B))
        # where f is the raw probability

        n = len(raw_probs)
        f = np.array(raw_probs, dtype=np.float64)
        y = np.array([1.0 if a else 0.0 for a in actuals], dtype=np.float64)

        # Target values (Platt's smoothed targets)
        n_pos = np.sum(y)
        n_neg = n - n_pos
        t_pos = (n_pos + 1) / (n_pos + 2) if n_pos > 0 else 0.5
        t_neg = 1.0 / (n_neg + 2) if n_neg > 0 else 0.5
        t = np.where(y > 0.5, t_pos, t_neg)

        # Optimize A and B via Newton's method (simplified)
        # Minimize: -sum(t*log(p) + (1-t)*log(1-p))
        # where p = 1/(1+exp(A*f + B))

        def neg_log_likelihood(params):
            a, b = params
            z = a * f + b
            z = np.clip(z, -30, 30)
            p = 1.0 / (1.0 + np.exp(z))
            p = np.clip(p, 1e-10, 1 - 1e-10)
            nll = -np.sum(t * np.log(p) + (1 - t) * np.log(1 - p))
            # Light regularization toward identity
            nll += 0.01 * (a + 1.0) ** 2 + 0.01 * b ** 2
            return nll

        from scipy.optimize import minimize
        result = minimize(
            neg_log_likelihood,
            x0=np.array([-1.0, 0.0]),
            method="Nelder-Mead",
            options={"maxiter": 1000, "xatol": 1e-6},
        )

        self._a = float(result.x[0])
        self._b = float(result.x[1])
        self._fitted = True

    def transform(self, raw_prob: float) -> float:
        """Apply Platt scaling to a single probability."""
        if not self._fitted:
            return raw_prob
        z = self._a * raw_prob + self._b
        z = max(-30.0, min(30.0, z))
        return 1.0 / (1.0 + math.exp(z))

    def transform_batch(self, raw_probs: list[float]) -> list[float]:
        """Apply Platt scaling to a list of probabilities."""
        return [self.transform(p) for p in raw_probs]


# ═══════════════════════════════════════════════════════════════
# ISOTONIC REGRESSION
# ═══════════════════════════════════════════════════════════════


class IsotonicCalibrator:
    """Isotonic regression calibration (non-parametric).

    Fits a monotone non-decreasing step function that maps raw
    probabilities to calibrated probabilities. Uses the Pool Adjacent
    Violators (PAV) algorithm.

    More flexible than Platt scaling — handles any shape of miscalibration.
    Requires more data (~50+ samples) to avoid overfitting.

    For prediction: interpolates between fitted points.
    """

    def __init__(self, min_samples_per_bin: int = 5) -> None:
        self._x_points: Optional[np.ndarray] = None  # Raw probs (sorted)
        self._y_points: Optional[np.ndarray] = None  # Calibrated values
        self._min_samples = min_samples_per_bin
        self._fitted: bool = False

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    def fit(self, raw_probs: list[float], actuals: list[bool]) -> None:
        """Fit isotonic calibration using PAV algorithm.

        Args:
            raw_probs: Raw model probabilities in [0, 1].
            actuals: True outcomes.
        """
        if len(raw_probs) < 10:
            self._fitted = True
            self._x_points = np.array([0.0, 1.0])
            self._y_points = np.array([0.0, 1.0])
            return

        x = np.array(raw_probs, dtype=np.float64)
        y = np.array([1.0 if a else 0.0 for a in actuals], dtype=np.float64)

        # Sort by raw probability
        order = np.argsort(x)
        x_sorted = x[order]
        y_sorted = y[order]

        # Pool Adjacent Violators (PAV) algorithm
        calibrated = self._pav(y_sorted)

        # Reduce to unique x-points (average duplicates)
        unique_x, unique_y = self._reduce_points(x_sorted, calibrated)

        self._x_points = unique_x
        self._y_points = unique_y
        self._fitted = True

    def transform(self, raw_prob: float) -> float:
        """Apply isotonic calibration via linear interpolation."""
        if not self._fitted or self._x_points is None:
            return raw_prob

        # Clip to calibration range
        if raw_prob <= self._x_points[0]:
            return float(self._y_points[0])
        if raw_prob >= self._x_points[-1]:
            return float(self._y_points[-1])

        # Linear interpolation
        idx = np.searchsorted(self._x_points, raw_prob) - 1
        idx = max(0, min(idx, len(self._x_points) - 2))

        x0, x1 = self._x_points[idx], self._x_points[idx + 1]
        y0, y1 = self._y_points[idx], self._y_points[idx + 1]

        if x1 == x0:
            return float(y0)

        t = (raw_prob - x0) / (x1 - x0)
        return float(y0 + t * (y1 - y0))

    def transform_batch(self, raw_probs: list[float]) -> list[float]:
        """Apply isotonic calibration to a list of probabilities."""
        return [self.transform(p) for p in raw_probs]

    @staticmethod
    def _pav(y: np.ndarray) -> np.ndarray:
        """Pool Adjacent Violators algorithm.

        Returns isotonic (non-decreasing) regression of y.
        """
        n = len(y)
        result = y.copy()
        # Each "block" is (start, end, value, weight)
        blocks = [[i, i + 1, result[i], 1.0] for i in range(n)]

        i = 0
        while i < len(blocks) - 1:
            if blocks[i][2] > blocks[i + 1][2]:
                # Violation: pool blocks
                w1, w2 = blocks[i][3], blocks[i + 1][3]
                new_val = (blocks[i][2] * w1 + blocks[i + 1][2] * w2) / (w1 + w2)
                blocks[i] = [blocks[i][0], blocks[i + 1][1], new_val, w1 + w2]
                blocks.pop(i + 1)
                # Check backward
                if i > 0:
                    i -= 1
            else:
                i += 1

        # Expand blocks back to full array
        result = np.zeros(n)
        for start, end, val, _ in blocks:
            result[start:end] = val

        return result

    def _reduce_points(
        self, x: np.ndarray, y: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Reduce to representative points by binning."""
        n = len(x)
        n_bins = max(10, n // self._min_samples)
        n_bins = min(n_bins, 100)  # Cap at 100 points

        bin_edges = np.linspace(x[0], x[-1], n_bins + 1)
        unique_x = []
        unique_y = []

        for i in range(n_bins):
            mask = (x >= bin_edges[i]) & (x < bin_edges[i + 1])
            if i == n_bins - 1:
                mask = (x >= bin_edges[i]) & (x <= bin_edges[i + 1])
            if np.sum(mask) > 0:
                unique_x.append(float(np.mean(x[mask])))
                unique_y.append(float(np.mean(y[mask])))

        # Ensure monotonicity of reduced points
        if unique_y:
            unique_y_arr = np.array(unique_y)
            unique_y_arr = self._pav(unique_y_arr)
            unique_y = unique_y_arr.tolist()

        return np.array(unique_x), np.array(unique_y)
