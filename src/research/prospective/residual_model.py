"""Ridge-logistic residual model with the market logit as a fixed offset.

The target is NOT an outcome probability from scratch. It is a small, strongly
regularized correction on top of the market prior:

    z_market = logit(p_market)                     # offset (coefficient fixed 1)
    delta    = beta0 + beta . X                     # ridge-logistic residual
    z_final  = z_market + lambda * delta
    p_final  = sigmoid(z_final)

Where ``X`` is the feature vector (fundamental-minus-market disagreement,
lineup deltas, context). Key safety properties:

- beta = 0 (and beta0 = 0)  =>  delta = 0  =>  p_final = p_market.
  "Trust the market completely" is the natural default and the failure mode
  when signal is weak: L2 shrinkage pulls coefficients toward 0, i.e. toward
  the market, never toward 0.5 or climatology.
- A missing optional feature is imputed to 0 (its centered mean under
  standardization), so an absent feature contributes nothing and cannot make a
  forecast more extreme.
- Standardization statistics and the ridge penalty are fit INSIDE the training
  fold only; ``predict`` reuses the frozen training statistics.

Implemented from first principles (numpy only) to avoid any heavy black-box
dependency (no XGBoost, no neural nets).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

import numpy as np

_EPS = 1e-9


def _logit(p: float) -> float:
    p = min(max(p, _EPS), 1.0 - _EPS)
    return math.log(p / (1.0 - p))


def _sigmoid(z: float) -> float:
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


@dataclass(frozen=True)
class ResidualSample:
    """One training/eval row.

    Attributes:
        p_market: Market prior probability of the selection (the offset source).
        features: Named residual features (disagreement, lineup deltas, ...).
        outcome: Realized binary outcome (True if selection occurred). None for
            prediction-only rows.
    """

    p_market: float
    features: Mapping[str, float]
    outcome: Optional[bool] = None


@dataclass
class RidgeLogisticResidualModel:
    """Market-offset ridge-logistic residual model.

    Attributes:
        l2: Ridge penalty strength (>0). Larger => stronger shrinkage to market.
        lam: The lambda multiplier on the delta (defaults to 1.0).
        max_iter / lr: Gradient-descent controls (deterministic).
        feature_names: Frozen feature order (set at fit).
        _mean / _std: Standardization stats frozen at fit (training fold only).
        _beta0 / _beta: Fitted intercept and coefficients.
        fitted: Whether fit has run.
    """

    l2: float = 1.0
    lam: float = 1.0
    max_iter: int = 500
    lr: float = 0.1
    #: Whether to fit a global intercept. Default False so that, with no
    #: features (or all features missing), the model reproduces the market
    #: prior EXACTLY. Enable only for explicit, documented market-bias
    #: correction; when enabled the intercept is also L2-penalised toward 0.
    fit_intercept: bool = False
    feature_names: tuple[str, ...] = ()
    _mean: Optional[np.ndarray] = None
    _std: Optional[np.ndarray] = None
    _beta0: float = 0.0
    _beta: Optional[np.ndarray] = None
    fitted: bool = False

    # -- feature assembly -------------------------------------------------

    def _matrix(self, samples: Sequence[ResidualSample]) -> np.ndarray:
        """Assemble the raw feature matrix in ``feature_names`` order.

        A feature absent from a sample is imputed to 0.0 (post-standardization
        this is the training mean, i.e. neutral). Missing features never make a
        prediction more extreme.
        """
        rows = []
        for s in samples:
            rows.append([float(s.features.get(name, 0.0)) for name in self.feature_names])
        return np.asarray(rows, dtype=float) if rows else np.empty((0, len(self.feature_names)))

    def _standardize(self, X: np.ndarray) -> np.ndarray:
        if self._mean is None or self._std is None:
            raise RuntimeError("model not fitted")
        std = np.where(self._std < _EPS, 1.0, self._std)
        return (X - self._mean) / std

    # -- fit --------------------------------------------------------------

    def fit(self, samples: Sequence[ResidualSample]) -> "RidgeLogisticResidualModel":
        """Fit the residual on labelled samples (offset = market logit).

        Standardization and the ridge fit happen entirely within these
        (training-fold) samples. Raises ValueError if a sample lacks an outcome.
        """
        labelled = [s for s in samples if s.outcome is not None]
        if not labelled:
            raise ValueError("residual model requires labelled samples")

        if not self.feature_names:
            names: list[str] = []
            seen = set()
            for s in labelled:
                for k in s.features.keys():
                    if k not in seen:
                        seen.add(k)
                        names.append(k)
            self.feature_names = tuple(names)

        X = self._matrix(labelled)
        self._mean = X.mean(axis=0) if X.size else np.zeros(len(self.feature_names))
        self._std = X.std(axis=0) if X.size else np.ones(len(self.feature_names))
        Xs = self._standardize(X)

        offset = np.array([_logit(s.p_market) for s in labelled], dtype=float)
        y = np.array([1.0 if s.outcome else 0.0 for s in labelled], dtype=float)

        n, d = Xs.shape if Xs.size else (len(labelled), len(self.feature_names))
        beta0 = 0.0
        beta = np.zeros(d)

        for _ in range(self.max_iter):
            z = offset + self.lam * (beta0 + (Xs @ beta if d else 0.0))
            p = 1.0 / (1.0 + np.exp(-np.clip(z, -35, 35)))
            resid = p - y
            grad0 = float(np.mean(resid)) * self.lam + self.l2 * beta0 / n
            if d:
                grad = (Xs.T @ resid) / n * self.lam + self.l2 * beta / n
            if self.fit_intercept:
                beta0 -= self.lr * grad0
            if d:
                beta -= self.lr * grad

        self._beta0 = beta0
        self._beta = beta if d else np.zeros(0)
        self.fitted = True
        return self

    # -- predict ----------------------------------------------------------

    def delta(self, sample: ResidualSample) -> float:
        """The residual delta (before lambda) for one sample."""
        if not self.fitted:
            return 0.0
        X = self._matrix([sample])
        Xs = self._standardize(X)
        d = Xs.shape[1]
        return float(self._beta0 + (Xs[0] @ self._beta if d else 0.0))

    def predict(self, sample: ResidualSample) -> float:
        """Final probability: sigmoid(logit(p_market) + lambda * delta).

        Unfitted, or all-zero coefficients, reproduces the market prior exactly.
        """
        z = _logit(sample.p_market) + self.lam * self.delta(sample)
        return _sigmoid(z)

    def predict_many(self, samples: Sequence[ResidualSample]) -> list[float]:
        return [self.predict(s) for s in samples]
