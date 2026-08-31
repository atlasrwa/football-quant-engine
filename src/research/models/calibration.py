"""Post-hoc probability calibration for model outputs.

Raw model outputs are frequently overconfident even when the underlying
model is otherwise sound. Calibration transforms raw probabilities into
well-calibrated ones where "predicted 70%" means the event happens ~70%
of the time.

Implements two standard calibration methods:
1. Platt scaling — logistic regression on raw probabilities (parametric)
2. Isotonic regression — non-parametric monotone mapping

Both are implemented without sklearn dependency, using only numpy/scipy.

Usage:
    # Wrap any model with calibration
    calibrated = CalibratedModel(base_model, method="isotonic")
    calibrated.fit(train_features, train_outcomes)  # fits base + calibration
    pred = calibrated.predict(features)  # returns calibrated probabilities

The calibration step uses a held-out portion of training data (or can be
fitted on separate calibration data) to avoid overfitting the calibration
curve to training data.
"""

from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np
from scipy.optimize import minimize_scalar

from src.research.probability import (
    ProbabilityEstimate,
    ProbabilityModel,
    TrainingMetadata,
)


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


# ═══════════════════════════════════════════════════════════════
# CALIBRATED MODEL WRAPPER
# ═══════════════════════════════════════════════════════════════


class CalibratedModel(ProbabilityModel):
    """Wrapper that applies post-hoc calibration to any ProbabilityModel.

    Calibration is fitted on a held-out portion of the training data
    (last 20% by default) to avoid overfitting the calibration curve.

    Usage:
        base_model = DixonColesModel(line=2.5)
        calibrated = CalibratedModel(base_model, method="isotonic")
        calibrated.fit(features, outcomes)
        pred = calibrated.predict(features)  # calibrated probability

    Methods:
        "platt" — Platt scaling (parametric sigmoid)
        "isotonic" — Isotonic regression (non-parametric)
    """

    def __init__(
        self,
        base_model: ProbabilityModel,
        method: str = "isotonic",
        calibration_fraction: float = 0.2,
    ) -> None:
        """Initialize calibrated model.

        Args:
            base_model: The underlying probability model.
            method: "platt" or "isotonic".
            calibration_fraction: Fraction of training data reserved for
                calibration fitting (default 0.2 = last 20%).
        """
        self._base_model = base_model
        self._method = method
        self._calibration_fraction = calibration_fraction

        if method == "platt":
            self._calibrator = PlattScaler()
        elif method == "isotonic":
            self._calibrator = IsotonicCalibrator()
        else:
            raise ValueError(f"method must be 'platt' or 'isotonic', got '{method}'")

        self._fitted = False

    @property
    def name(self) -> str:
        return f"{self._base_model.name}_calibrated_{self._method}"

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    @property
    def training_metadata(self) -> Optional[TrainingMetadata]:
        return self._base_model.training_metadata

    @property
    def base_model(self) -> ProbabilityModel:
        """The underlying uncalibrated model."""
        return self._base_model

    @property
    def calibration_method(self) -> str:
        return self._method

    def _get_parameters(self) -> dict[str, Any]:
        return {
            "base_model": self._base_model.name,
            "calibration_method": self._method,
            "calibration_fraction": self._calibration_fraction,
        }

    def fit(
        self,
        features: list[dict[str, float]],
        outcomes: list[bool],
        training_start: Optional[int] = None,
        training_end: Optional[int] = None,
    ) -> None:
        """Fit base model + calibration.

        Splits data:
        - First (1 - calibration_fraction) → fit base model
        - Last calibration_fraction → fit calibration mapping

        This ensures calibration is fitted on data the base model
        hasn't seen during training (avoids overfit).
        """
        n = len(features)
        if n < 30:
            # Too few samples — fit base model on all data, skip calibration
            self._base_model.fit(
                features, outcomes,
                training_start=training_start,
                training_end=training_end,
            )
            self._fitted = True
            return

        # Split: train base model on first portion, calibrate on rest
        cal_start = int(n * (1 - self._calibration_fraction))
        train_features = features[:cal_start]
        train_outcomes = outcomes[:cal_start]
        cal_features = features[cal_start:]
        cal_outcomes = outcomes[cal_start:]

        # Fit base model
        self._base_model.fit(
            train_features, train_outcomes,
            training_start=training_start,
            training_end=training_end,
        )

        # Generate raw predictions on calibration set
        raw_probs = []
        cal_actuals = []
        for feat, outcome in zip(cal_features, cal_outcomes):
            try:
                estimate = self._base_model.predict(feat)
                raw_probs.append(estimate.p_over)
                cal_actuals.append(outcome)
            except Exception:
                continue

        # Fit calibration mapping
        if len(raw_probs) >= 10:
            self._calibrator.fit(raw_probs, cal_actuals)

        self._fitted = True

    def predict(self, features: dict[str, float]) -> ProbabilityEstimate:
        """Predict with calibrated probability."""
        raw_estimate = self._base_model.predict(features)

        if not self._calibrator.is_fitted:
            return raw_estimate

        # Calibrate p_over
        cal_p_over = self._calibrator.transform(raw_estimate.p_over)
        cal_p_over = max(0.01, min(0.99, cal_p_over))

        return ProbabilityEstimate(
            p_over=cal_p_over,
            p_under=1.0 - cal_p_over,
            model_name=self.name,
        )

    def predict_raw_and_calibrated(
        self, features: dict[str, float]
    ) -> tuple[float, float]:
        """Return both raw and calibrated p_over for comparison.

        Useful for calibration analysis and debugging.
        """
        raw_estimate = self._base_model.predict(features)
        raw_p = raw_estimate.p_over

        if not self._calibrator.is_fitted:
            return raw_p, raw_p

        cal_p = self._calibrator.transform(raw_p)
        return raw_p, cal_p
