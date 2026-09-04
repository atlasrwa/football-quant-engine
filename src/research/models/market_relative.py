"""Market-relative (residual-vs-market) count model — the "market as prior" angle.

WHY THIS EXISTS
===============
Every prior-only experiment in this repo modelled the outcome INDEPENDENTLY and then
compared the result to a *naive* base-rate climatology. The honest finding was a
persistent null: prior-only corners/cards BSS ~ -1.8% vs naive, and adding more raw
aggregate stats made it WORSE (overfitting), see RICH_FIELDS_LEAKFREE_REPORT.md.

But "beat naive" is the wrong finish line (executive review, section 3). The market's
de-vigged probability already embeds most public information. The right question is:

    Does adding prior-only raw-stat information to the DE-VIGGED MARKET PRICE improve
    on the market price itself?

This module implements that. The de-vigged market probability is converted to an
implied expected count (``lambda_market``) and used as a fixed per-match OFFSET on the
Poisson linear predictor. Prior-only raw-stat features may then only move the
prediction RELATIVE to the market:

    log(lambda) = log(lambda_market) + beta . x_residual        (offset model)

Properties that make this the correct, honest framing:
  * With beta = 0 the model reproduces the market EXACTLY (its BSS-vs-market is 0).
    So any measured skill is INCREMENTAL over the price, not re-derived climatology.
  * Features are centred (mean-0 within the training fold) so the offset is not
    silently re-estimated by the intercept; the intercept is pinned to 0.
  * Strong L2 shrinkage is the default because the prior expectation (from every
    experiment to date) is that raw stats carry little residual signal. Shrinkage
    means "when in doubt, defer to the market", which is the economically safe bias.
  * It consumes the SAME leak-free prior-only feature schema (build_prior_only_features
    / build_rich_prior_only_features) and the SAME de-vig math (MarketProbabilityNormalizer),
    so no new leakage surface and no new odds handling is introduced.

This module adds NO product/EV/"beats the market" claim. It is a research estimator
whose whole purpose is to MEASURE, honestly, whether raw stats add anything the price
does not already have. If they do not, that is the answer and it is reported as such.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaincc, gammaln

from src.research.ev_calculator import DevigMethod, MarketProbabilityNormalizer


def _pois_p_over(k: int, lam: float) -> float:
    """Return ``P(Poisson(lam) > k)`` using SciPy's fast gamma ufunc."""
    return 1.0 - float(gammaincc(k + 1, lam))


def _finite_float(value: object) -> Optional[float]:
    """Convert a scalar to a finite float, returning ``None`` for unusable values."""
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    return converted if math.isfinite(converted) else None


# ═══════════════════════════════════════════════════════════════
# MARKET LAMBDA INVERSION
# ═══════════════════════════════════════════════════════════════


def implied_lambda_from_p_over(
    p_over: float, line: float, *, lam_lo: float = 0.05, lam_hi: float = 60.0
) -> Optional[float]:
    """Invert a Poisson over-probability to its implied expected count.

    ``p_over`` is interpreted as ``P(count > line)``. Invalid or degenerate
    probabilities return ``None`` so callers can abstain instead of fabricating a
    market prior. Targets outside the configured lambda search interval are mapped to
    the nearest bound.
    """
    p_over = _finite_float(p_over)
    line = _finite_float(line)
    if p_over is None or line is None or not (0.0 < p_over < 1.0):
        return None
    lam_lo = float(lam_lo)
    lam_hi = float(lam_hi)
    if not (0.0 < lam_lo < lam_hi and math.isfinite(lam_hi)):
        raise ValueError("lambda bounds must satisfy 0 < lam_lo < lam_hi")

    k = int(math.floor(line))

    def p_over_at(lam: float) -> float:
        return _pois_p_over(k, lam)

    lo, hi = lam_lo, lam_hi
    if p_over <= p_over_at(lo):
        return lo
    if p_over >= p_over_at(hi):
        return hi
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if p_over_at(mid) < p_over:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ═══════════════════════════════════════════════════════════════
# FITTED PARAMS
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class MarketRelativeParams:
    """Fitted residual-vs-market parameters and fit diagnostics."""

    feature_weights: dict[str, float]
    feature_means: dict[str, float]
    l2: float
    n_observations: int
    feature_names: tuple[str, ...]
    beta_l2_norm: float
    optimization_success: Optional[bool]
    optimization_message: str


# ═══════════════════════════════════════════════════════════════
# MODEL
# ═══════════════════════════════════════════════════════════════


class MarketRelativeCountModel:
    """Poisson count model anchored on the de-vigged market lambda as an offset.

    ``log(lambda_i) = log(lambda_market_i) + sum(beta_j * (x_ij - mean_j))``

    There is no free intercept or team effect. Missing market priors cause abstention;
    insufficient data or optimizer failure causes an explicit market-only fallback.
    """

    def __init__(
        self,
        target_field: str = "total_corners",
        line: float = 9.5,
        feature_fields: Sequence[str] = (),
        l2: float = 5.0,
        devig_method: DevigMethod = DevigMethod.MULTIPLICATIVE,
    ) -> None:
        self._target_field = target_field
        self._line = float(line)
        self._feature_fields = tuple(feature_fields)
        self._l2 = float(l2)
        self._devig_method = devig_method
        self._normalizer = MarketProbabilityNormalizer(method=devig_method)
        self._params: Optional[MarketRelativeParams] = None
        self._fitted = False

    @property
    def name(self) -> str:
        return f"market_relative_{self._target_field}"

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    @property
    def params(self) -> Optional[MarketRelativeParams]:
        return self._params

    def _odds_pair(self, feat: dict) -> Optional[tuple[float, float]]:
        """Read validated odds and reject metadata for a different target or line."""
        attached_target = feat.get("market_target")
        if attached_target is not None and attached_target != self._target_field:
            return None
        if "market_line" in feat:
            attached_line = _finite_float(feat.get("market_line"))
            if attached_line is None or not math.isclose(
                attached_line, self._line, rel_tol=0.0, abs_tol=1e-9
            ):
                return None

        over = _finite_float(feat.get("market_over_odds"))
        under = _finite_float(feat.get("market_under_odds"))
        if over is None or under is None or over <= 1.0 or under <= 1.0:
            return None
        return over, under

    # ──────────────────────────────────────────────────────────
    # De-vig helpers
    # ──────────────────────────────────────────────────────────

    def devig_p_over(self, feat: dict) -> Optional[float]:
        """Return the de-vigged fair P(over), or ``None`` for unusable odds."""
        odds = self._odds_pair(feat)
        if odds is None:
            return None
        result = self._normalizer.normalize_two_way(*odds)
        return None if result is None else result[0]

    def market_lambda(self, feat: dict) -> Optional[float]:
        """Return the market-implied lambda using an odds-aware per-row cache."""
        odds = self._odds_pair(feat)
        if odds is None:
            return None
        method = getattr(self._devig_method, "value", str(self._devig_method))
        cache_key = f"_mkt_lambda_{self._target_field}_{self._line}_{method}"
        cached = feat.get(cache_key)
        if (
            isinstance(cached, tuple)
            and len(cached) == 3
            and cached[0] == odds[0]
            and cached[1] == odds[1]
        ):
            return cached[2]

        p_over = self.devig_p_over(feat)
        lam = implied_lambda_from_p_over(p_over, self._line)
        try:
            feat[cache_key] = (odds[0], odds[1], lam)
        except (AttributeError, TypeError):
            pass
        return lam

    def _set_market_only_params(
        self,
        *,
        n_observations: int,
        feature_means: Optional[dict[str, float]] = None,
        optimization_success: Optional[bool],
        optimization_message: str,
    ) -> None:
        means = feature_means or {field: 0.0 for field in self._feature_fields}
        self._params = MarketRelativeParams(
            feature_weights={field: 0.0 for field in self._feature_fields},
            feature_means=means,
            l2=self._l2,
            n_observations=n_observations,
            feature_names=self._feature_fields,
            beta_l2_norm=0.0,
            optimization_success=optimization_success,
            optimization_message=optimization_message,
        )
        self._fitted = True

    # ──────────────────────────────────────────────────────────
    # Fit
    # ──────────────────────────────────────────────────────────

    def fit(self, features: list[dict], outcomes: Optional[list[bool]] = None) -> None:
        """Fit residual weights by penalized Poisson MLE with a market offset.

        The optional ``outcomes`` argument is accepted for interface parity; labels are
        actual counts from ``target_field``. Missing/non-finite predictors are imputed to
        the training-fold mean, matching prediction-time behavior. Any optimization
        failure, including an exception, installs an explicit market-only fallback.
        """
        del outcomes
        # A failed refit must never leave parameters from an earlier successful fit.
        self._params = None
        self._fitted = False
        rows_x: list[list[float]] = []
        rows_y: list[float] = []
        rows_offset: list[float] = []

        for feat in features:
            y_value = _finite_float(feat.get(self._target_field))
            if y_value is None or y_value < 0:
                continue
            if not y_value.is_integer():
                raise ValueError(
                    f"{self._target_field} must be a non-negative integer count; "
                    f"got {y_value!r}"
                )
            lam_market = self.market_lambda(feat)
            if lam_market is None or lam_market <= 0:
                continue
            rows_x.append(
                [
                    value if (value := _finite_float(feat.get(field))) is not None else math.nan
                    for field in self._feature_fields
                ]
            )
            rows_y.append(float(int(y_value)))
            rows_offset.append(math.log(lam_market))

        n_observations = len(rows_y)
        if n_observations < 30 or not self._feature_fields:
            self._set_market_only_params(
                n_observations=n_observations,
                optimization_success=None,
                optimization_message="market-only fallback: insufficient observations or features",
            )
            return

        X = np.asarray(rows_x, dtype=float)
        y = np.asarray(rows_y, dtype=float)
        offset = np.asarray(rows_offset, dtype=float)

        feature_mean = np.zeros(X.shape[1], dtype=float)
        for column in range(X.shape[1]):
            finite = np.isfinite(X[:, column])
            if finite.any():
                feature_mean[column] = float(X[finite, column].mean())
            X[~finite, column] = feature_mean[column]
        feature_std = X.std(axis=0)
        feature_std[~np.isfinite(feature_std) | (feature_std == 0.0)] = 1.0
        X_centered = (X - feature_mean) / feature_std
        feature_means = {
            field: float(feature_mean[index])
            for index, field in enumerate(self._feature_fields)
        }

        def negative_log_likelihood(beta: np.ndarray) -> float:
            log_lam = np.clip(offset + X_centered @ beta, -6.0, 6.0)
            lam = np.exp(log_lam)
            log_likelihood = np.sum(y * log_lam - lam - gammaln(y + 1.0))
            log_likelihood -= self._l2 * float(np.sum(beta**2))
            return -float(log_likelihood)

        try:
            result = minimize(
                negative_log_likelihood,
                np.zeros(X_centered.shape[1]),
                method="L-BFGS-B",
                options={"maxiter": 400, "ftol": 1e-8},
            )
            if not result.success or not np.all(np.isfinite(result.x)):
                raise RuntimeError(str(result.message))
        except Exception as exc:
            self._set_market_only_params(
                n_observations=n_observations,
                feature_means=feature_means,
                optimization_success=False,
                optimization_message=f"market-only fallback: {type(exc).__name__}: {exc}",
            )
            return

        beta_standardized = result.x
        feature_weights = {
            field: float(beta_standardized[index] / feature_std[index])
            for index, field in enumerate(self._feature_fields)
        }
        self._params = MarketRelativeParams(
            feature_weights=feature_weights,
            feature_means=feature_means,
            l2=self._l2,
            n_observations=n_observations,
            feature_names=self._feature_fields,
            beta_l2_norm=float(np.linalg.norm(beta_standardized)),
            optimization_success=True,
            optimization_message=str(result.message),
        )
        self._fitted = True

    # ──────────────────────────────────────────────────────────
    # Predict
    # ──────────────────────────────────────────────────────────

    def predict_p_over(self, feat: dict) -> Optional[float]:
        """Return P(count > line), abstaining when no valid market prior exists."""
        p_market = self.devig_p_over(feat)
        if p_market is None:
            return None
        lam_market = self.market_lambda(feat)
        if lam_market is None:
            return None
        if self._params is None:
            return p_market

        residual = 0.0
        for field, weight in self._params.feature_weights.items():
            if weight == 0.0:
                continue
            mean = self._params.feature_means.get(field, 0.0)
            value = _finite_float(feat.get(field))
            residual += weight * ((mean if value is None else value) - mean)

        # Preserve the defining invariant exactly, without an inversion/reprojection
        # round trip or probability clipping when the fitted residual is zero.
        if residual == 0.0:
            return p_market

        log_lam = max(-6.0, min(6.0, math.log(lam_market) + residual))
        probability = _pois_p_over(int(math.floor(self._line)), math.exp(log_lam))
        return max(0.0, min(1.0, probability))
