"""Count regression models for corners and cards prediction.

Implements Poisson and Negative-Binomial regression for count markets
(corners, cards, offsides). Uses team-level modeling with feature
conditioning.

Key design decisions:
- NB regression when variance > mean (overdispersed per-team counts)
- Poisson when variance ≈ mean (total counts, cards)
- Feature-conditioned: dangerous_attacks, shots, fouls, possession, referee
- Team strength adjustments via team-level random effects
- Implements ProbabilityModel ABC for research pipeline integration

The model predicts P(count > line) for over/under markets at any line.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import nbinom, poisson

from src.research.probability import (
    ModelIdentity,
    PredictionResult,
    PredictionStatus,
    ProbabilityEstimate,
    ProbabilityModel,
    TrainingMetadata,
)


# ═══════════════════════════════════════════════════════════════
# DISTRIBUTION TYPE
# ═══════════════════════════════════════════════════════════════


class DistributionType:
    """Distribution selection based on overdispersion."""

    POISSON = "poisson"
    NEGATIVE_BINOMIAL = "negative_binomial"
    AUTO = "auto"  # Select based on variance/mean ratio


# ═══════════════════════════════════════════════════════════════
# COUNT REGRESSION MODEL
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class CountRegressionParams:
    """Fitted count regression parameters."""

    intercept: float
    feature_weights: dict[str, float]
    team_effects: dict[str, float]  # team_id → adjustment
    dispersion: float  # NB dispersion (alpha); 0 for Poisson
    distribution: str  # "poisson" or "negative_binomial"
    n_observations: int
    feature_names: tuple[str, ...]
    mean_target: float
    std_target: float


class CountRegressionModel(ProbabilityModel):
    """Poisson/Negative-Binomial regression for count markets.

    Models the target count (corners, cards) as:
        log(lambda) = intercept + sum(w_i * x_i) + team_effect

    Where lambda is the expected count, and the distribution is either:
    - Poisson(lambda) if variance ≈ mean
    - NegBin(r, p) if variance > mean (overdispersed)

    Features used (when available):
    - dangerous_attacks_{home,away}: Attack pressure proxy
    - shots_{home,away}: Shooting volume
    - fouls_{home,away}: Foul tendency (for cards)
    - possession_{home,away}: Ball dominance
    - referee volatility (if available)

    Parameters:
        target_field: Which count to predict (e.g., "total_corners").
        line: The O/U line (e.g., 9.5 for corners).
        distribution: "poisson", "negative_binomial", or "auto".
        feature_fields: Which features to use for conditioning.
        use_team_effects: Whether to fit per-team adjustments.
        overdispersion_threshold: Var/mean ratio above which NB is chosen (auto mode).
    """

    def __init__(
        self,
        target_field: str = "total_corners",
        line: float = 9.5,
        distribution: str = DistributionType.AUTO,
        feature_fields: Optional[tuple[str, ...]] = None,
        use_team_effects: bool = True,
        overdispersion_threshold: float = 1.2,
    ) -> None:
        self._target_field = target_field
        self._line = line
        self._distribution_choice = distribution
        self._use_team_effects = use_team_effects
        self._overdispersion_threshold = overdispersion_threshold

        # Default features based on target
        if feature_fields is not None:
            self._feature_fields = feature_fields
        elif "corner" in target_field.lower():
            self._feature_fields = (
                "dangerous_attacks_home", "dangerous_attacks_away",
                "attacks_home", "attacks_away",
                "possession_home", "possession_away",
                "shots_home", "shots_away",
            )
        elif "card" in target_field.lower():
            self._feature_fields = (
                "fouls_home", "fouls_away",
                "dangerous_attacks_home", "dangerous_attacks_away",
                "possession_home", "possession_away",
            )
        else:
            self._feature_fields = (
                "dangerous_attacks_home", "dangerous_attacks_away",
                "possession_home", "possession_away",
            )

        # Fitted state
        self._params: Optional[CountRegressionParams] = None
        self._fitted = False
        self._training_metadata: Optional[TrainingMetadata] = None

    @property
    def name(self) -> str:
        return f"count_regression_{self._target_field}"

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    @property
    def training_metadata(self) -> Optional[TrainingMetadata]:
        return self._training_metadata

    @property
    def params(self) -> Optional[CountRegressionParams]:
        return self._params

    @property
    def distribution_used(self) -> Optional[str]:
        """Which distribution was selected after fitting."""
        return self._params.distribution if self._params else None

    def _get_parameters(self) -> dict[str, Any]:
        return {
            "target_field": self._target_field,
            "line": self._line,
            "distribution": self._distribution_choice,
            "feature_fields": self._feature_fields,
            "use_team_effects": self._use_team_effects,
        }

    def fit(
        self,
        features: list[dict[str, float]],
        outcomes: list[bool],
        training_start: Optional[int] = None,
        training_end: Optional[int] = None,
    ) -> None:
        """Fit count regression model.

        Extracts target counts from feature dicts. The `outcomes` parameter
        is accepted for interface compatibility but the model uses actual
        counts from the target_field.

        Required keys in features:
        - target_field (e.g., "total_corners"): the count to predict
        - Feature fields for conditioning
        - Optionally home_team_id/away_team_id for team effects
        """
        if not features:
            self._fitted = True
            return

        # Extract target values and features
        targets = []
        feature_matrix = []
        team_ids = []

        for feat in features:
            target_val = feat.get(self._target_field)
            if target_val is None or target_val < 0:
                continue

            targets.append(int(target_val))

            # Extract conditioning features
            row = []
            for f_name in self._feature_fields:
                row.append(feat.get(f_name, 0.0))
            feature_matrix.append(row)

            # Team identifier for team effects
            if self._use_team_effects:
                home_id = feat.get("home_team_id")
                away_id = feat.get("away_team_id")
                team_ids.append((
                    str(int(home_id)) if home_id is not None else None,
                    str(int(away_id)) if away_id is not None else None,
                ))

        if len(targets) < 20:
            self._fit_simple_mean(targets)
            self._fitted = True
            return

        targets_arr = np.array(targets, dtype=float)
        X = np.array(feature_matrix, dtype=float)

        # Determine distribution
        distribution = self._select_distribution(targets_arr)

        # Standardize features
        feature_mean = X.mean(axis=0)
        feature_std = X.std(axis=0)
        feature_std[feature_std == 0] = 1.0
        X_std = (X - feature_mean) / feature_std

        # Fit team effects
        team_effects: dict[str, float] = {}
        if self._use_team_effects and team_ids:
            team_effects = self._fit_team_effects(targets_arr, team_ids)

        # Fit regression
        params = self._fit_regression(
            targets_arr, X_std, team_ids, team_effects, distribution
        )

        # Store with original scale info for prediction
        # Convert weights back to original feature scale
        weights_original = {}
        for i, f_name in enumerate(self._feature_fields):
            if feature_std[i] > 0:
                weights_original[f_name] = params["weights"][i] / feature_std[i]
            else:
                weights_original[f_name] = 0.0

        # Adjust intercept for standardization
        intercept_adj = params["intercept"]
        for i, f_name in enumerate(self._feature_fields):
            intercept_adj -= params["weights"][i] * feature_mean[i] / feature_std[i]

        self._params = CountRegressionParams(
            intercept=float(intercept_adj),
            feature_weights=weights_original,
            team_effects=team_effects,
            dispersion=float(params.get("dispersion", 0.0)),
            distribution=distribution,
            n_observations=len(targets),
            feature_names=self._feature_fields,
            mean_target=float(np.mean(targets_arr)),
            std_target=float(np.std(targets_arr)),
        )
        self._fitted = True

        if training_start is not None and training_end is not None:
            self._training_metadata = TrainingMetadata(
                training_start=training_start,
                training_end=training_end,
                sample_size=len(targets),
                feature_names=self._feature_fields,
            )

    def predict(self, features: dict[str, float]) -> ProbabilityEstimate:
        """Predict P(over) and P(under) for the configured line."""
        if self._params is None:
            return ProbabilityEstimate(p_over=0.5, p_under=0.5, model_name=self.name)

        # Compute expected count (lambda)
        lam = self._predict_lambda(features)

        # Compute P(count > line)
        p_over = self._compute_p_over(lam)
        p_over = max(0.01, min(0.99, p_over))

        return ProbabilityEstimate(
            p_over=p_over,
            p_under=1.0 - p_over,
            model_name=self.name,
        )

    def predict_expected_count(self, features: dict[str, float]) -> float:
        """Return expected count (lambda) for a match."""
        if self._params is None:
            return self._line  # Fallback to line as prior
        return self._predict_lambda(features)

    def predict_over_under(
        self, features: dict[str, float], line: float
    ) -> tuple[float, float]:
        """Predict P(over) and P(under) for an arbitrary line."""
        if self._params is None:
            return 0.5, 0.5
        lam = self._predict_lambda(features)
        p_over = self._compute_p_over_at_line(lam, line)
        return p_over, 1.0 - p_over

    # ──────────────────────────────────────────────────────────
    # Internal: Distribution selection
    # ──────────────────────────────────────────────────────────

    def _select_distribution(self, targets: np.ndarray) -> str:
        """Select Poisson vs NB based on overdispersion."""
        if self._distribution_choice != DistributionType.AUTO:
            return self._distribution_choice

        mean_val = np.mean(targets)
        var_val = np.var(targets, ddof=1)

        if mean_val > 0 and var_val / mean_val > self._overdispersion_threshold:
            return DistributionType.NEGATIVE_BINOMIAL
        return DistributionType.POISSON

    # ──────────────────────────────────────────────────────────
    # Internal: Team effects
    # ──────────────────────────────────────────────────────────

    def _fit_team_effects(
        self, targets: np.ndarray, team_ids: list[tuple]
    ) -> dict[str, float]:
        """Fit per-team additive effects on log-lambda."""
        team_sums: dict[str, float] = defaultdict(float)
        team_counts: dict[str, int] = defaultdict(int)
        global_mean = np.mean(targets)

        for i, (home_id, away_id) in enumerate(team_ids):
            val = targets[i]
            if home_id is not None:
                team_sums[home_id] += val
                team_counts[home_id] += 1
            if away_id is not None:
                team_sums[away_id] += val
                team_counts[away_id] += 1

        team_effects = {}
        for team_id, total in team_sums.items():
            count = team_counts[team_id]
            if count >= 3:
                team_mean = total / count
                # Shrink toward global mean (regularization)
                shrinkage = count / (count + 10.0)
                effect_mean = shrinkage * team_mean + (1 - shrinkage) * global_mean
                # Effect on log scale
                if effect_mean > 0 and global_mean > 0:
                    team_effects[team_id] = math.log(effect_mean / global_mean)
                else:
                    team_effects[team_id] = 0.0

        return team_effects

    # ──────────────────────────────────────────────────────────
    # Internal: Regression fitting
    # ──────────────────────────────────────────────────────────

    def _fit_regression(
        self,
        targets: np.ndarray,
        X: np.ndarray,
        team_ids: list[tuple],
        team_effects: dict[str, float],
        distribution: str,
    ) -> dict[str, Any]:
        """Fit regression parameters via MLE."""
        n, k = X.shape

        # Compute team effect offsets
        team_offset = np.zeros(n)
        if self._use_team_effects and team_ids:
            for i, (home_id, away_id) in enumerate(team_ids):
                effect = 0.0
                if home_id and home_id in team_effects:
                    effect += team_effects[home_id] * 0.5
                if away_id and away_id in team_effects:
                    effect += team_effects[away_id] * 0.5
                team_offset[i] = effect

        if distribution == DistributionType.POISSON:
            return self._fit_poisson(targets, X, team_offset)
        else:
            return self._fit_negative_binomial(targets, X, team_offset)

    def _fit_poisson(
        self, targets: np.ndarray, X: np.ndarray, team_offset: np.ndarray
    ) -> dict[str, Any]:
        """Fit Poisson regression via MLE."""
        n, k = X.shape

        def neg_ll(params):
            intercept = params[0]
            weights = params[1:]
            log_lambda = intercept + X @ weights + team_offset
            log_lambda = np.clip(log_lambda, -5, 5)
            lam = np.exp(log_lambda)
            # Poisson log-likelihood: y*log(lam) - lam - log(y!)
            ll = np.sum(targets * log_lambda - lam - gammaln(targets + 1))
            # L2 regularization
            ll -= 0.01 * np.sum(weights ** 2)
            return -ll

        x0 = np.zeros(k + 1)
        x0[0] = math.log(max(0.1, np.mean(targets)))

        result = minimize(neg_ll, x0, method="L-BFGS-B",
                         options={"maxiter": 300, "ftol": 1e-6})

        return {
            "intercept": float(result.x[0]),
            "weights": result.x[1:].tolist(),
            "dispersion": 0.0,
        }

    def _fit_negative_binomial(
        self, targets: np.ndarray, X: np.ndarray, team_offset: np.ndarray
    ) -> dict[str, Any]:
        """Fit Negative-Binomial regression via MLE.

        NB2 parameterization: Var = mu + alpha * mu^2
        where alpha is the dispersion parameter.
        """
        n, k = X.shape

        def neg_ll(params):
            intercept = params[0]
            weights = params[1:k + 1]
            log_alpha = params[k + 1]  # log dispersion

            log_mu = intercept + X @ weights + team_offset
            log_mu = np.clip(log_mu, -5, 5)
            mu = np.exp(log_mu)
            alpha = np.exp(np.clip(log_alpha, -5, 5))

            # NB log-likelihood (NB2 parameterization)
            r = 1.0 / alpha  # shape parameter
            p = r / (r + mu)  # success probability

            # log P(Y=y) = log(Gamma(y+r)) - log(Gamma(r)) - log(y!)
            #              + r*log(p) + y*log(1-p)
            ll = np.sum(
                gammaln(targets + r) - gammaln(r) - gammaln(targets + 1)
                + r * np.log(np.clip(p, 1e-10, 1.0))
                + targets * np.log(np.clip(1 - p, 1e-10, 1.0))
            )
            # L2 regularization
            ll -= 0.01 * np.sum(weights ** 2)
            return -ll

        x0 = np.zeros(k + 2)
        x0[0] = math.log(max(0.1, np.mean(targets)))
        x0[k + 1] = math.log(0.5)  # initial dispersion

        result = minimize(neg_ll, x0, method="L-BFGS-B",
                         options={"maxiter": 300, "ftol": 1e-6})

        alpha = np.exp(np.clip(result.x[k + 1], -5, 5))

        return {
            "intercept": float(result.x[0]),
            "weights": result.x[1:k + 1].tolist(),
            "dispersion": float(alpha),
        }

    def _fit_simple_mean(self, targets: list[int]) -> None:
        """Fallback: predict mean count (no conditioning)."""
        mean_val = np.mean(targets) if targets else self._line
        self._params = CountRegressionParams(
            intercept=math.log(max(0.1, mean_val)),
            feature_weights={f: 0.0 for f in self._feature_fields},
            team_effects={},
            dispersion=0.0,
            distribution=DistributionType.POISSON,
            n_observations=len(targets),
            feature_names=self._feature_fields,
            mean_target=float(mean_val),
            std_target=float(np.std(targets)) if len(targets) > 1 else 1.0,
        )

    # ──────────────────────────────────────────────────────────
    # Internal: Prediction
    # ──────────────────────────────────────────────────────────

    def _predict_lambda(self, features: dict[str, float]) -> float:
        """Compute expected count from features."""
        params = self._params
        assert params is not None

        # Linear predictor
        log_lambda = params.intercept
        for f_name, weight in params.feature_weights.items():
            log_lambda += weight * features.get(f_name, 0.0)

        # Team effects
        if params.team_effects:
            home_id = features.get("home_team_id")
            away_id = features.get("away_team_id")
            if home_id is not None:
                effect = params.team_effects.get(str(int(home_id)), 0.0)
                log_lambda += effect * 0.5
            if away_id is not None:
                effect = params.team_effects.get(str(int(away_id)), 0.0)
                log_lambda += effect * 0.5

        # Clip to reasonable range
        log_lambda = max(-3.0, min(4.0, log_lambda))
        return math.exp(log_lambda)

    def _compute_p_over(self, lam: float) -> float:
        """Compute P(count > line) using configured line and distribution."""
        return self._compute_p_over_at_line(lam, self._line)

    def _compute_p_over_at_line(self, lam: float, line: float) -> float:
        """Compute P(count > line) for given lambda and line."""
        params = self._params
        if params is None:
            return 0.5

        if params.distribution == DistributionType.NEGATIVE_BINOMIAL and params.dispersion > 0:
            # NB2: Var = mu + alpha * mu^2
            alpha = params.dispersion
            r = 1.0 / alpha  # shape
            p = r / (r + lam)  # success probability

            # P(X > line) = 1 - P(X <= floor(line))
            # scipy nbinom uses (n, p) where n=r, p=p
            p_under = nbinom.cdf(int(line), r, p)
            return 1.0 - p_under
        else:
            # Poisson
            p_under = poisson.cdf(int(line), lam)
            return 1.0 - p_under

    # ──────────────────────────────────────────────────────────
    # Confidence
    # ──────────────────────────────────────────────────────────

    def prediction_confidence(self, features: dict[str, float]) -> float:
        """Estimate confidence based on feature availability and team history."""
        if self._params is None:
            return 0.0

        # Check how many features are available
        available = sum(
            1 for f in self._feature_fields if features.get(f) is not None
        )
        feature_confidence = available / max(1, len(self._feature_fields))

        # Check team is known
        team_confidence = 1.0
        if self._params.team_effects:
            home_id = features.get("home_team_id")
            away_id = features.get("away_team_id")
            home_known = str(int(home_id)) in self._params.team_effects if home_id else False
            away_known = str(int(away_id)) in self._params.team_effects if away_id else False
            if not home_known or not away_known:
                team_confidence = 0.6

        # Model training size
        size_confidence = min(1.0, self._params.n_observations / 150.0)

        return feature_confidence * team_confidence * size_confidence


# ═══════════════════════════════════════════════════════════════
# CONVENIENCE FACTORIES
# ═══════════════════════════════════════════════════════════════


def create_corners_model(line: float = 9.5) -> CountRegressionModel:
    """Create a pre-configured model for total corners O/U."""
    return CountRegressionModel(
        target_field="total_corners",
        line=line,
        distribution=DistributionType.AUTO,
        feature_fields=(
            "dangerous_attacks_home", "dangerous_attacks_away",
            "attacks_home", "attacks_away",
            "possession_home", "possession_away",
            "shots_home", "shots_away",
        ),
        use_team_effects=True,
    )


def create_cards_model(line: float = 3.5) -> CountRegressionModel:
    """Create a pre-configured model for total cards O/U."""
    return CountRegressionModel(
        target_field="total_cards",
        line=line,
        distribution=DistributionType.AUTO,
        feature_fields=(
            "fouls_home", "fouls_away",
            "dangerous_attacks_home", "dangerous_attacks_away",
            "possession_home", "possession_away",
        ),
        use_team_effects=True,
    )
