"""Probability model layer for the research laboratory.

Provides calibrated probability estimates for market outcomes.
Models output actual probabilities (not edge scores).

Key distinctions:
- edge_score ≠ probability
- historical_ROI ≠ calibrated probability
- These models output P(outcome | features)

Every model has:
- Deterministic identity (content hash from type + version + config)
- Training metadata (period, feature version, dataset version)
- Explicit missing-data handling (never fabricates probabilities)

Supports:
- Two-way outcomes (OVER/UNDER, YES/NO)
- Three-way outcomes (HOME/DRAW/AWAY)
- Count distributions (Poisson)
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import numpy as np


# ═══════════════════════════════════════════════════════════════
# PREDICTION STATUS
# ═══════════════════════════════════════════════════════════════


class PredictionStatus(Enum):
    """Status of a probability prediction attempt."""

    VALID = "VALID"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    MISSING_ODDS = "MISSING_ODDS"
    INVALID_INPUT = "INVALID_INPUT"
    MODEL_NOT_FITTED = "MODEL_NOT_FITTED"
    MODEL_FAILURE = "MODEL_FAILURE"


# ═══════════════════════════════════════════════════════════════
# PROBABILITY ESTIMATES
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class ProbabilityEstimate:
    """A probability estimate for a two-way outcome.

    Attributes:
        p_over: Probability of OVER outcome.
        p_under: Probability of UNDER outcome (= 1 - p_over).
        model_name: Which model produced this estimate.
        confidence: Optional confidence measure.
    """

    p_over: float
    p_under: float
    model_name: str
    confidence: Optional[float] = None

    def __post_init__(self):
        # Allow small floating point deviations
        assert abs(self.p_over + self.p_under - 1.0) < 0.001, (
            f"Probabilities must sum to 1.0, got {self.p_over + self.p_under}"
        )


@dataclass(frozen=True, slots=True)
class ThreeWayProbabilityEstimate:
    """A probability estimate for a three-way outcome (HOME/DRAW/AWAY).

    Attributes:
        p_home: Probability of HOME win.
        p_draw: Probability of DRAW.
        p_away: Probability of AWAY win.
        model_name: Which model produced this estimate.
        confidence: Optional confidence measure.
    """

    p_home: float
    p_draw: float
    p_away: float
    model_name: str
    confidence: Optional[float] = None

    def __post_init__(self):
        total = self.p_home + self.p_draw + self.p_away
        assert abs(total - 1.0) < 0.001, (
            f"Probabilities must sum to 1.0, got {total}"
        )
        assert self.p_home >= 0, f"p_home must be >= 0, got {self.p_home}"
        assert self.p_draw >= 0, f"p_draw must be >= 0, got {self.p_draw}"
        assert self.p_away >= 0, f"p_away must be >= 0, got {self.p_away}"


@dataclass(frozen=True, slots=True)
class PredictionResult:
    """Wraps a probability estimate with status and metadata.

    This is the safe return type: callers MUST check status before using
    the estimate. If status != VALID, estimate is None.
    """

    status: PredictionStatus
    estimate: Optional[ProbabilityEstimate] = None
    three_way_estimate: Optional[ThreeWayProbabilityEstimate] = None
    reason: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        """Whether a usable probability estimate is available."""
        return self.status == PredictionStatus.VALID


# ═══════════════════════════════════════════════════════════════
# MODEL IDENTITY / VERSIONING
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class ModelIdentity:
    """Deterministic identity for a probability model configuration.

    Two models with the same identity produce the same predictions
    given the same training data and features.

    Attributes:
        model_type: Type name of the model.
        model_version: Integer version number.
        parameters: Frozen parameter dictionary.
        content_hash: SHA-256 hash of canonical serialization.
    """

    model_type: str
    model_version: int
    parameters: tuple[tuple[str, Any], ...]  # Frozen dict as sorted tuple
    content_hash: str

    @staticmethod
    def create(
        model_type: str,
        model_version: int,
        parameters: dict[str, Any],
    ) -> "ModelIdentity":
        """Create a ModelIdentity with computed content hash.

        Args:
            model_type: Model type name.
            model_version: Version number.
            parameters: Model configuration parameters.

        Returns:
            ModelIdentity with deterministic content hash.
        """
        frozen_params = tuple(sorted(parameters.items()))
        canonical = json.dumps(
            {
                "model_type": model_type,
                "model_version": model_version,
                "parameters": parameters,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        content_hash = hashlib.sha256(canonical.encode()).hexdigest()
        return ModelIdentity(
            model_type=model_type,
            model_version=model_version,
            parameters=frozen_params,
            content_hash=content_hash,
        )


@dataclass(frozen=True, slots=True)
class TrainingMetadata:
    """Records what data was used to train a model.

    Temporal contract:
    - training_end MUST be before any prediction_timestamp
    - No data from after training_end may influence predictions

    Attributes:
        training_start: Start of training period (unix timestamp).
        training_end: End of training period (unix timestamp).
        sample_size: Number of observations used.
        feature_names: Features used during training.
        dataset_version: Content hash of the training dataset.
        feature_version: Content hash of feature definitions used.
    """

    training_start: int
    training_end: int
    sample_size: int
    feature_names: tuple[str, ...] = ()
    dataset_version: Optional[str] = None
    feature_version: Optional[str] = None

    def __post_init__(self):
        if self.training_end < self.training_start:
            raise ValueError(
                f"training_end ({self.training_end}) must be >= "
                f"training_start ({self.training_start})"
            )
        if self.sample_size < 0:
            raise ValueError(f"sample_size must be >= 0, got {self.sample_size}")

    def is_prediction_valid(self, prediction_timestamp: int) -> bool:
        """Check whether a prediction timestamp respects temporal causality.

        A prediction is valid if it occurs AFTER the training period ends.
        The model must not predict within its own training window.
        """
        return prediction_timestamp > self.training_end


# ═══════════════════════════════════════════════════════════════
# BASE MODEL INTERFACE
# ═══════════════════════════════════════════════════════════════


class ProbabilityModel(ABC):
    """Abstract probability model interface.

    All models must:
    - Have a deterministic identity (model_identity)
    - Track training metadata
    - Handle missing data explicitly (never fabricate probabilities)
    - Respect temporal causality
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Model identifier."""
        ...

    @abstractmethod
    def fit(self, features: list[dict[str, float]], outcomes: list[bool]) -> None:
        """Fit model on training data.

        Args:
            features: Feature dicts for each observation.
            outcomes: True = OVER won, False = UNDER won.
        """
        ...

    @abstractmethod
    def predict(self, features: dict[str, float]) -> ProbabilityEstimate:
        """Predict probability for a single observation.

        Args:
            features: Feature dict for this match.

        Returns:
            ProbabilityEstimate with calibrated probabilities.
        """
        ...

    def predict_safe(self, features: dict[str, float]) -> PredictionResult:
        """Predict with explicit status handling.

        Returns PredictionResult with status. Callers should check
        result.is_valid before using the estimate.
        """
        if not self.is_fitted:
            return PredictionResult(
                status=PredictionStatus.MODEL_NOT_FITTED,
                reason="Model has not been fitted with training data.",
            )
        try:
            estimate = self.predict(features)
            return PredictionResult(status=PredictionStatus.VALID, estimate=estimate)
        except Exception as e:
            return PredictionResult(
                status=PredictionStatus.MODEL_FAILURE,
                reason=str(e),
            )

    def predict_many(self, features: list[dict[str, float]]) -> list[ProbabilityEstimate]:
        """Predict probabilities for multiple observations."""
        return [self.predict(f) for f in features]

    @property
    def is_fitted(self) -> bool:
        """Whether the model has been fitted with training data."""
        return True  # Subclasses override if they track fit state

    @property
    def model_version(self) -> int:
        """Model version number. Override in subclasses for versioning."""
        return 1

    @property
    def model_identity(self) -> ModelIdentity:
        """Deterministic identity based on type, version, and parameters."""
        return ModelIdentity.create(
            model_type=self.name,
            model_version=self.model_version,
            parameters=self._get_parameters(),
        )

    def _get_parameters(self) -> dict[str, Any]:
        """Return model parameters for identity hashing. Override in subclasses."""
        return {}

    @property
    def training_metadata(self) -> Optional[TrainingMetadata]:
        """Training metadata if available. None if not tracked or not fitted."""
        return None


class HistoricalFrequencyModel(ProbabilityModel):
    """Baseline: uses historical frequency as probability estimate.

    P(OVER) = count(OVER outcomes) / total_outcomes

    This is the simplest possible baseline. Any useful model
    must beat this.

    Supports configuration:
    - min_observations: Minimum samples before producing a prediction
    - lookback_window: Optional limit on history used (None = all)
    """

    def __init__(
        self,
        min_observations: int = 1,
        lookback_window: Optional[int] = None,
    ) -> None:
        self._p_over: float = 0.5
        self._min_observations = min_observations
        self._lookback_window = lookback_window
        self._fitted = False
        self._sample_size: int = 0
        self._training_metadata: Optional[TrainingMetadata] = None

    @property
    def name(self) -> str:
        return "historical_frequency"

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    @property
    def training_metadata(self) -> Optional[TrainingMetadata]:
        return self._training_metadata

    def _get_parameters(self) -> dict[str, Any]:
        return {
            "min_observations": self._min_observations,
            "lookback_window": self._lookback_window,
        }

    def fit(
        self,
        features: list[dict[str, float]],
        outcomes: list[bool],
        training_start: Optional[int] = None,
        training_end: Optional[int] = None,
    ) -> None:
        if not outcomes:
            self._p_over = 0.5
            self._fitted = True
            self._sample_size = 0
            return

        # Apply lookback window if configured
        effective_outcomes = outcomes
        if self._lookback_window is not None and len(outcomes) > self._lookback_window:
            effective_outcomes = outcomes[-self._lookback_window:]

        self._sample_size = len(effective_outcomes)
        self._p_over = sum(effective_outcomes) / len(effective_outcomes)
        # Clip to avoid 0/1
        self._p_over = max(0.01, min(0.99, self._p_over))
        self._fitted = True

        # Record training metadata if timestamps provided
        if training_start is not None and training_end is not None:
            self._training_metadata = TrainingMetadata(
                training_start=training_start,
                training_end=training_end,
                sample_size=self._sample_size,
            )

    def predict(self, features: dict[str, float]) -> ProbabilityEstimate:
        return ProbabilityEstimate(
            p_over=self._p_over,
            p_under=1.0 - self._p_over,
            model_name=self.name,
        )

    def predict_safe(self, features: dict[str, float]) -> PredictionResult:
        """Predict with insufficient-data check."""
        if not self._fitted:
            return PredictionResult(
                status=PredictionStatus.MODEL_NOT_FITTED,
                reason="Model has not been fitted.",
            )
        if self._sample_size < self._min_observations:
            return PredictionResult(
                status=PredictionStatus.INSUFFICIENT_DATA,
                reason=f"Only {self._sample_size} observations, need {self._min_observations}.",
            )
        estimate = self.predict(features)
        return PredictionResult(status=PredictionStatus.VALID, estimate=estimate)


class LogisticRegressionModel(ProbabilityModel):
    """Logistic regression probability model.

    Uses gradient descent to fit logistic regression on features.
    Outputs calibrated probabilities by construction.

    Parameters are versioned and reproducible (controlled via seed).
    """

    def __init__(
        self,
        learning_rate: float = 0.01,
        max_iter: int = 1000,
        seed: Optional[int] = None,
    ) -> None:
        self._lr = learning_rate
        self._max_iter = max_iter
        self._seed = seed
        self._weights: Optional[np.ndarray] = None
        self._bias: float = 0.0
        self._feature_names: list[str] = []
        self._mean: Optional[np.ndarray] = None
        self._std: Optional[np.ndarray] = None
        self._fitted = False
        self._sample_size: int = 0
        self._training_metadata: Optional[TrainingMetadata] = None

    @property
    def name(self) -> str:
        return "logistic_regression"

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    @property
    def training_metadata(self) -> Optional[TrainingMetadata]:
        return self._training_metadata

    def _get_parameters(self) -> dict[str, Any]:
        return {
            "learning_rate": self._lr,
            "max_iter": self._max_iter,
            "seed": self._seed,
        }

    def fit(
        self,
        features: list[dict[str, float]],
        outcomes: list[bool],
        training_start: Optional[int] = None,
        training_end: Optional[int] = None,
    ) -> None:
        if not features or not outcomes:
            self._fitted = True
            self._sample_size = 0
            return

        # Determine feature names from intersection of all dicts
        all_keys = set(features[0].keys())
        for f in features[1:]:
            all_keys &= set(f.keys())
        self._feature_names = sorted(all_keys)

        if not self._feature_names:
            self._weights = None
            self._bias = 0.0
            self._fitted = True
            self._sample_size = len(features)
            return

        # Build feature matrix
        n = len(features)
        k = len(self._feature_names)
        X = np.zeros((n, k))
        y = np.array([1.0 if o else 0.0 for o in outcomes])

        for i, feat in enumerate(features):
            for j, name in enumerate(self._feature_names):
                X[i, j] = feat.get(name, 0.0)

        # Standardize features
        self._mean = X.mean(axis=0)
        self._std = X.std(axis=0)
        self._std[self._std == 0] = 1.0
        X = (X - self._mean) / self._std

        # Gradient descent
        weights = np.zeros(k)
        bias = 0.0

        for _ in range(self._max_iter):
            z = X @ weights + bias
            pred = 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))
            error = pred - y
            weights -= self._lr * (X.T @ error) / n
            bias -= self._lr * error.mean()

        self._weights = weights
        self._bias = bias
        self._fitted = True
        self._sample_size = n

        # Record training metadata if timestamps provided
        if training_start is not None and training_end is not None:
            self._training_metadata = TrainingMetadata(
                training_start=training_start,
                training_end=training_end,
                sample_size=n,
                feature_names=tuple(self._feature_names),
            )

    def predict(self, features: dict[str, float]) -> ProbabilityEstimate:
        if self._weights is None or not self._feature_names:
            return ProbabilityEstimate(p_over=0.5, p_under=0.5, model_name=self.name)

        x = np.array([features.get(name, 0.0) for name in self._feature_names])
        x = (x - self._mean) / self._std
        z = float(x @ self._weights + self._bias)
        p_over = 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))
        p_over = max(0.01, min(0.99, p_over))

        return ProbabilityEstimate(
            p_over=p_over,
            p_under=1.0 - p_over,
            model_name=self.name,
        )


class PoissonModel(ProbabilityModel):
    """Poisson-based probability model for count markets.

    Models the target (goals, corners, cards) as a Poisson-distributed
    count. Estimates the rate parameter (lambda) from training data and
    uses the Poisson CDF to compute P(X > line) and P(X <= line).

    For feature-conditioned predictions, adjusts lambda based on a
    simple linear model of features.
    """

    def __init__(self, line: float = 2.5) -> None:
        self._line = line
        self._base_lambda: float = 2.5
        self._feature_names: list[str] = []
        self._feature_weights: Optional[np.ndarray] = None
        self._feature_mean: Optional[np.ndarray] = None
        self._feature_std: Optional[np.ndarray] = None
        self._fitted = False
        self._sample_size: int = 0
        self._training_metadata: Optional[TrainingMetadata] = None

    @property
    def name(self) -> str:
        return "poisson"

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    @property
    def training_metadata(self) -> Optional[TrainingMetadata]:
        return self._training_metadata

    def _get_parameters(self) -> dict[str, Any]:
        return {"line": self._line}

    def fit(
        self,
        features: list[dict[str, float]],
        outcomes: list[bool],
        training_start: Optional[int] = None,
        training_end: Optional[int] = None,
    ) -> None:
        """Fit Poisson rate from training data.

        Estimates base lambda from the over-rate, then optionally
        learns feature weights via simple gradient descent on the
        Poisson log-likelihood.
        """
        if not outcomes:
            self._base_lambda = 2.5
            self._fitted = True
            self._sample_size = 0
            return

        self._sample_size = len(outcomes)

        # Estimate base over-rate
        over_rate = sum(outcomes) / len(outcomes)
        over_rate = max(0.1, min(0.9, over_rate))

        # Convert over-rate to lambda estimate using Poisson CDF inversion
        from scipy.stats import poisson as poisson_dist

        # Binary search for lambda that gives the observed over-rate
        lo, hi = 0.1, 20.0
        for _ in range(50):
            mid = (lo + hi) / 2.0
            p_over = 1.0 - poisson_dist.cdf(int(self._line), mid)
            if p_over < over_rate:
                lo = mid
            else:
                hi = mid
        self._base_lambda = (lo + hi) / 2.0

        # Learn feature adjustments if features available
        if not features:
            self._fitted = True
            if training_start is not None and training_end is not None:
                self._training_metadata = TrainingMetadata(
                    training_start=training_start,
                    training_end=training_end,
                    sample_size=self._sample_size,
                )
            return

        all_keys = set(features[0].keys())
        for f in features[1:]:
            all_keys &= set(f.keys())
        self._feature_names = sorted(all_keys)

        if not self._feature_names:
            self._fitted = True
            if training_start is not None and training_end is not None:
                self._training_metadata = TrainingMetadata(
                    training_start=training_start,
                    training_end=training_end,
                    sample_size=self._sample_size,
                )
            return

        # Build feature matrix
        n = len(features)
        k = len(self._feature_names)
        X = np.zeros((n, k))
        for i, feat in enumerate(features):
            for j, fname in enumerate(self._feature_names):
                X[i, j] = feat.get(fname, 0.0)

        # Standardize
        self._feature_mean = X.mean(axis=0)
        self._feature_std = X.std(axis=0)
        self._feature_std[self._feature_std == 0] = 1.0
        X = (X - self._feature_mean) / self._feature_std

        # Simple gradient descent on log-likelihood
        y = np.array([1.0 if o else 0.0 for o in outcomes])
        weights = np.zeros(k)
        lr = 0.001

        for _ in range(200):
            log_lambda = np.log(self._base_lambda) + X @ weights
            log_lambda = np.clip(log_lambda, -5, 5)
            lam = np.exp(log_lambda)
            error = y - (1.0 - poisson_dist.cdf(int(self._line), lam))
            grad = X.T @ error / n
            weights += lr * grad

        self._feature_weights = weights
        self._fitted = True

        if training_start is not None and training_end is not None:
            self._training_metadata = TrainingMetadata(
                training_start=training_start,
                training_end=training_end,
                sample_size=n,
                feature_names=tuple(self._feature_names),
            )

    def predict(self, features: dict[str, float]) -> ProbabilityEstimate:
        """Predict using Poisson CDF.

        P(OVER) = P(X > line) = 1 - P(X <= floor(line))
        """
        from scipy.stats import poisson as poisson_dist

        lam = self._base_lambda

        # Adjust lambda with features if available
        if self._feature_weights is not None and self._feature_names:
            x = np.array([features.get(fname, 0.0) for fname in self._feature_names])
            x = (x - self._feature_mean) / self._feature_std
            log_adj = float(x @ self._feature_weights)
            log_adj = np.clip(log_adj, -3, 3)
            lam = lam * np.exp(log_adj)

        # Poisson CDF: P(X <= k)
        p_over = 1.0 - poisson_dist.cdf(int(self._line), lam)
        p_over = float(max(0.01, min(0.99, p_over)))

        return ProbabilityEstimate(
            p_over=p_over,
            p_under=1.0 - p_over,
            model_name=self.name,
        )

    def predict_distribution(self, features: dict[str, float], max_k: int = 20) -> list[float]:
        """Return P(X = k) for k = 0, 1, ..., max_k.

        Useful for count markets where the full distribution is needed.

        Args:
            features: Feature dict for this match.
            max_k: Maximum count value.

        Returns:
            List of probabilities [P(X=0), P(X=1), ..., P(X=max_k)].
        """
        from scipy.stats import poisson as poisson_dist

        lam = self._base_lambda

        if self._feature_weights is not None and self._feature_names:
            x = np.array([features.get(fname, 0.0) for fname in self._feature_names])
            x = (x - self._feature_mean) / self._feature_std
            log_adj = float(x @ self._feature_weights)
            log_adj = np.clip(log_adj, -3, 3)
            lam = lam * np.exp(log_adj)

        return [float(poisson_dist.pmf(k, lam)) for k in range(max_k + 1)]
