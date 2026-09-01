"""DirectionalCountModel — elastic-net Poisson/NB count model.

Responsibility
==============
One direction, one ``Per_Side_Target``. This module reuses the count-regression
MLE machinery from :mod:`src.research.models.count_regression` — the same
``scipy.optimize.minimize`` L-BFGS-B inner loop and the dispersion-driven
``DistributionType.AUTO`` selection (NB when ``var/mean`` exceeds a threshold,
Poisson otherwise) — but makes three deliberate changes required by the design
("DirectionalCountModel — model layer"):

1. **Elastic-net penalty (replaces the L2-only penalty).**
   The reused model penalised the neg-log-likelihood with ``0.01 * sum(w^2)``
   (pure L2). Here that term is replaced by an *elastic-net* penalty::

       lam * ( alpha_mix * sum(sqrt(w**2 + eps)) + (1 - alpha_mix) * sum(w**2) )

   with defaults ``lam=0.05``, ``alpha_mix=0.5`` and a small ``eps=1e-8``. The
   L1 sub-gradient at ``w = 0`` is undefined, so the absolute value is smoothed
   as ``sqrt(w**2 + eps)`` to keep the L-BFGS-B optimiser stable. Because
   ``alpha_mix < 1`` there is always a strictly-convex L2 component, so this is
   genuine elastic-net and never degenerates to pure L1 — which is exactly why
   two strongly correlated informative features both retain non-zero weight
   instead of one being arbitrarily zeroed (Req 5.4, 5.5).

2. **No team-identity effect layer; shrinkage moves onto the profile inputs.**
   The reused model fitted per-team *identity* effects and shrank them with
   ``count/(count+10.0)``. Req 1.3 forbids team identity as a model feature, so
   that layer is **removed entirely**. The mandatory ``n/(n+k)`` shrinkage
   (Req 5.6) is instead applied to the **per-team profile-feature estimates**
   that feed the linear predictor: each per-team profile input is shrunk toward
   the global (all-team) mean of that same dimension by weight ``n/(n+k)``
   (``k=10.0``), where ``n`` is the team's completed-match count. See
   :func:`shrink_profile_features` and :meth:`DirectionalCountModel.fit` for the
   precise application point. Team identity is used *only* to look up ``n`` and
   to aggregate the per-team/global means — never as a coefficient.

3. **Full predictive distributions.**
   :meth:`predict_distribution` returns a full PMF over counts
   ``[P(X=0), ..., P(X=max_k)]`` via the Poisson or NB PMF (Req 2.4-2.7), and
   :meth:`predict_expected_count` returns ``lambda``. Fitted coefficients remain
   directly readable via :attr:`feature_weights` / :attr:`coefficients` for
   reporting (Req 10.3), and the empirical dispersion ratio is exposed via
   :attr:`dispersion_ratio` (Req 5.3).

The class implements the :class:`~src.research.probability.ProbabilityModel`
interface (``name``, ``fit``, ``predict``) so it slots into the existing
pipelines and factory, while its primary outputs are the full predictive
distribution, the expected count, the readable coefficients, the dispersion
ratio, and the chosen distribution.

Requirements: 5.1, 5.3, 5.4, 5.5, 5.6, 10.3 (task 4.1); 5.2 (task 4.2).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import nbinom, poisson

from src.research.models.count_regression import DistributionType
from src.research.probability import (
    LogisticRegressionModel,
    ProbabilityEstimate,
    ProbabilityModel,
    TrainingMetadata,
)

# Default hyper-parameters (documented in the module docstring).
DEFAULT_LAMBDA = 0.05
DEFAULT_ALPHA_MIX = 0.5
ELASTIC_NET_EPS = 1e-8
SHRINKAGE_K = 10.0
OVERDISPERSION_THRESHOLD = 1.2


# ═══════════════════════════════════════════════════════════════
# Team-level profile-feature shrinkage (Req 5.6)
# ═══════════════════════════════════════════════════════════════


def shrinkage_weight(n: int, k: float = SHRINKAGE_K) -> float:
    """Return the ``n/(n+k)`` shrinkage weight.

    ``n`` is a team's completed-match count and ``k`` the shrinkage constant
    (default 10.0, matching the existing ``count/(count+10.0)`` pattern). The
    weight is 0 at ``n=0``, strictly increasing in ``n``, and approaches 1 as
    ``n -> infinity`` (Property 8).
    """
    if n < 0:
        raise ValueError(f"n must be >= 0, got {n}")
    return n / (n + k)


def shrink_estimate(
    team_value: float, global_value: float, n: int, k: float = SHRINKAGE_K
) -> float:
    """Shrink a per-team profile estimate toward the global mean (Req 5.6).

    Returns ``w * team_value + (1 - w) * global_value`` where
    ``w = n/(n+k)``. As ``n`` increases the result moves monotonically toward
    ``team_value`` and never away from it (Property 8).
    """
    w = shrinkage_weight(n, k)
    return w * team_value + (1.0 - w) * global_value


def shrink_profile_features(
    row: dict[str, float],
    n: int,
    global_means: dict[str, float],
    k: float = SHRINKAGE_K,
) -> dict[str, float]:
    """Shrink every profile input in ``row`` toward its global mean.

    This is the precise point at which the mandatory ``n/(n+k)`` team-level
    shrinkage (Req 5.6) is applied: it acts on the **profile-feature inputs**
    that feed the linear predictor, NOT on any team-identity effect (which this
    model does not have). ``n`` is the team's completed-match count; each feature
    is shrunk toward the corresponding all-team global mean by weight
    ``n/(n+k)``. Features absent from ``global_means`` are shrunk toward 0.
    """
    w = shrinkage_weight(n, k)
    shrunk: dict[str, float] = {}
    for name, value in row.items():
        g = global_means.get(name, 0.0)
        shrunk[name] = w * value + (1.0 - w) * g
    return shrunk


# ═══════════════════════════════════════════════════════════════
# Fitted parameters
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class DirectionalParams:
    """Fitted DirectionalCountModel parameters (readable for reporting)."""

    intercept: float
    feature_weights: dict[str, float]
    dispersion: float  # NB dispersion (alpha); 0.0 for Poisson
    distribution: str  # "poisson" or "negative_binomial"
    dispersion_ratio: float  # empirical var/mean of the target (Req 5.3)
    n_observations: int
    feature_names: tuple[str, ...]
    mean_target: float
    std_target: float


# ═══════════════════════════════════════════════════════════════
# DirectionalCountModel
# ═══════════════════════════════════════════════════════════════


class DirectionalCountModel(ProbabilityModel):
    """Elastic-net Poisson/NB count model for one direction × one target.

    Args:
        target_field: key in each feature dict holding the observed count.
        line: default O/U line used by the ``predict`` (P(over)) interface.
        distribution: ``DistributionType.AUTO`` (default), ``POISSON`` or
            ``NEGATIVE_BINOMIAL``.
        lam: elastic-net penalty strength (default ``0.05``).
        alpha_mix: elastic-net L1/L2 mix in ``[0, 1)``; ``0.5`` by default.
            ``alpha_mix < 1`` guarantees a non-pure-L1 penalty (Req 5.5).
        k: team-level shrinkage constant ``n/(n+k)`` (default ``10.0``).
        eps: smoothing for the L1 term (default ``1e-8``).
        overdispersion_threshold: ``var/mean`` ratio above which NB is chosen in
            AUTO mode.
        feature_fields: optional explicit feature ordering; when omitted the
            model uses the sorted intersection of keys across the fit rows
            (excluding the target and the shrinkage bookkeeping keys).
    """

    # Keys that are bookkeeping, never model features.
    _RESERVED_KEYS = frozenset({"team", "n_matches", "home_team_id", "away_team_id"})

    def __init__(
        self,
        target_field: str = "count",
        line: float = 2.5,
        distribution: str = DistributionType.AUTO,
        lam: float = DEFAULT_LAMBDA,
        alpha_mix: float = DEFAULT_ALPHA_MIX,
        k: float = SHRINKAGE_K,
        eps: float = ELASTIC_NET_EPS,
        overdispersion_threshold: float = OVERDISPERSION_THRESHOLD,
        feature_fields: Optional[tuple[str, ...]] = None,
    ) -> None:
        if not (0.0 <= alpha_mix < 1.0):
            raise ValueError(
                f"alpha_mix must be in [0, 1) to stay elastic-net (not pure L1), "
                f"got {alpha_mix}"
            )
        if lam < 0.0:
            raise ValueError(f"lam must be >= 0, got {lam}")
        self._target_field = target_field
        self._line = line
        self._distribution_choice = distribution
        self._lam = lam
        self._alpha_mix = alpha_mix
        self._k = k
        self._eps = eps
        self._overdispersion_threshold = overdispersion_threshold
        self._feature_fields_override = feature_fields

        self._params: Optional[DirectionalParams] = None
        self._feature_fields: tuple[str, ...] = feature_fields or ()
        self._global_means: dict[str, float] = {}
        self._fitted = False
        self._training_metadata: Optional[TrainingMetadata] = None

    # ── ProbabilityModel identity ───────────────────────────────
    @property
    def name(self) -> str:
        return f"directional_count_{self._target_field}"

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    @property
    def training_metadata(self) -> Optional[TrainingMetadata]:
        return self._training_metadata

    def _get_parameters(self) -> dict[str, Any]:
        return {
            "target_field": self._target_field,
            "line": self._line,
            "distribution": self._distribution_choice,
            "lam": self._lam,
            "alpha_mix": self._alpha_mix,
            "k": self._k,
        }

    # ── Readable reporting surface (Req 10.3, 5.3) ──────────────
    @property
    def params(self) -> Optional[DirectionalParams]:
        return self._params

    @property
    def feature_weights(self) -> dict[str, float]:
        """Fitted per-feature coefficients on the original feature scale."""
        return dict(self._params.feature_weights) if self._params else {}

    # Alias so reporting code can use either name.
    coefficients = feature_weights

    @property
    def intercept(self) -> float:
        return self._params.intercept if self._params else 0.0

    @property
    def distribution_used(self) -> Optional[str]:
        """Which distribution was selected after fitting (Req 5.1)."""
        return self._params.distribution if self._params else None

    @property
    def dispersion_ratio(self) -> Optional[float]:
        """Empirical variance/mean of the target counts (Req 5.3)."""
        return self._params.dispersion_ratio if self._params else None

    @property
    def dispersion(self) -> Optional[float]:
        """Fitted NB dispersion (alpha); 0.0 for Poisson."""
        return self._params.dispersion if self._params else None

    # ── Fitting ─────────────────────────────────────────────────
    def fit(
        self,
        features: list[dict[str, float]],
        outcomes: Optional[list[bool]] = None,
        training_start: Optional[int] = None,
        training_end: Optional[int] = None,
    ) -> None:
        """Fit the elastic-net Poisson/NB model.

        ``features`` are per-direction rows. Each row holds the observed count
        under ``target_field`` and continuous profile-feature inputs (attacker
        profile + defender profile + named interaction terms). A row may also
        carry a ``"team"`` key and an ``"n_matches"`` key: when present, the
        mandatory ``n/(n+k)`` team-level shrinkage (Req 5.6) is applied to that
        row's profile inputs toward the all-team global mean before fitting.
        Rows without ``n_matches`` are used unshrunk (weight treated as 1).

        ``outcomes`` is accepted for :class:`ProbabilityModel` interface
        compatibility and is ignored — the model learns from the actual counts.
        """
        if not features:
            self._fitted = True
            return

        # Resolve the feature ordering (exclude target + reserved bookkeeping).
        feature_fields = self._resolve_feature_fields(features)
        self._feature_fields = feature_fields

        # Global (all-team) mean per feature, used as the shrinkage target.
        self._global_means = _compute_global_means(features, feature_fields)

        targets: list[int] = []
        rows: list[list[float]] = []
        for feat in features:
            target_val = feat.get(self._target_field)
            if target_val is None or target_val < 0:
                continue
            targets.append(int(round(target_val)))

            # Apply team-level shrinkage to the profile inputs (Req 5.6).
            raw_row = {name: float(feat.get(name, 0.0)) for name in feature_fields}
            n_matches = feat.get("n_matches")
            if n_matches is not None:
                shrunk = shrink_profile_features(
                    raw_row, int(n_matches), self._global_means, self._k
                )
            else:
                shrunk = raw_row
            rows.append([shrunk[name] for name in feature_fields])

        if not targets:
            self._fitted = True
            return

        targets_arr = np.asarray(targets, dtype=float)
        dispersion_ratio = _dispersion_ratio(targets_arr)

        if len(targets) < 20 or not feature_fields:
            # Too little data (or no features) to fit a stable regression:
            # fall back to an intercept-only model at the mean count.
            self._fit_simple_mean(targets_arr, feature_fields, dispersion_ratio)
            self._finalise_metadata(len(targets), training_start, training_end)
            self._fitted = True
            return

        X = np.asarray(rows, dtype=float)

        distribution = self._select_distribution(targets_arr, dispersion_ratio)

        # Standardize features for a well-conditioned optimisation, then convert
        # the fitted weights back to the original feature scale so coefficients
        # stay readable (Req 10.3).
        feature_mean = X.mean(axis=0)
        feature_std = X.std(axis=0)
        feature_std[feature_std == 0] = 1.0
        X_std = (X - feature_mean) / feature_std

        if distribution == DistributionType.POISSON:
            raw = self._fit_poisson(targets_arr, X_std)
        else:
            raw = self._fit_negative_binomial(targets_arr, X_std)

        weights_std = np.asarray(raw["weights"], dtype=float)
        weights_original: dict[str, float] = {}
        intercept_adj = float(raw["intercept"])
        for i, name in enumerate(feature_fields):
            w_orig = weights_std[i] / feature_std[i]
            weights_original[name] = float(w_orig)
            intercept_adj -= weights_std[i] * feature_mean[i] / feature_std[i]

        self._params = DirectionalParams(
            intercept=float(intercept_adj),
            feature_weights=weights_original,
            dispersion=float(raw.get("dispersion", 0.0)),
            distribution=distribution,
            dispersion_ratio=float(dispersion_ratio),
            n_observations=len(targets),
            feature_names=feature_fields,
            mean_target=float(targets_arr.mean()),
            std_target=float(targets_arr.std()),
        )
        self._finalise_metadata(len(targets), training_start, training_end)
        self._fitted = True

    # ── Prediction ──────────────────────────────────────────────
    def predict_expected_count(self, features: dict[str, float]) -> float:
        """Return the expected count ``lambda`` for a feature row."""
        if self._params is None:
            return float(self._line)
        return self._predict_lambda(features)

    def predict_distribution(
        self, features: dict[str, float], max_k: int = 20
    ) -> list[float]:
        """Return the full predictive PMF ``[P(X=0), ..., P(X=max_k)]``.

        The PMF is produced from the Poisson or NB PMF (Req 2.4-2.7). Entries are
        each in ``[0, 1]`` and are renormalised so the truncated distribution
        sums to 1 within floating-point tolerance (Property 4), which keeps the
        returned distribution a valid PMF even when ``max_k`` truncates a small
        tail mass.
        """
        if max_k < 0:
            raise ValueError(f"max_k must be >= 0, got {max_k}")
        params = self._params
        # Before fitting, fall back to the configured line as a prior lambda so
        # the method still returns a valid PMF (Property 4).
        lam = self._predict_lambda(features) if params is not None else float(self._line)

        if (
            params is not None
            and params.distribution == DistributionType.NEGATIVE_BINOMIAL
            and params.dispersion > 0.0
        ):
            alpha = params.dispersion
            r = 1.0 / alpha
            p = r / (r + lam)
            pmf = [float(nbinom.pmf(kk, r, p)) for kk in range(max_k + 1)]
        else:
            pmf = [float(poisson.pmf(kk, lam)) for kk in range(max_k + 1)]

        # Clip tiny negatives from floating point and renormalise to a valid PMF.
        pmf = [v if v > 0.0 else 0.0 for v in pmf]
        total = math.fsum(pmf)
        if total <= 0.0:
            # Degenerate fallback: put all mass on 0 (should not occur for lam>0).
            out = [0.0] * (max_k + 1)
            out[0] = 1.0
            return out
        return [v / total for v in pmf]

    def predict(self, features: dict[str, float]) -> ProbabilityEstimate:
        """P(over)/P(under) at the configured line (ProbabilityModel API)."""
        if self._params is None:
            return ProbabilityEstimate(p_over=0.5, p_under=0.5, model_name=self.name)
        p_over = self._compute_p_over_at_line(
            self._predict_lambda(features), self._line
        )
        p_over = max(0.01, min(0.99, p_over))
        return ProbabilityEstimate(
            p_over=p_over, p_under=1.0 - p_over, model_name=self.name
        )

    def predict_over_under(
        self, features: dict[str, float], line: float
    ) -> tuple[float, float]:
        """P(over)/P(under) for an arbitrary line."""
        if self._params is None:
            return 0.5, 0.5
        p_over = self._compute_p_over_at_line(self._predict_lambda(features), line)
        return p_over, 1.0 - p_over

    # ── Internal: feature resolution / global means ─────────────
    def _resolve_feature_fields(
        self, features: list[dict[str, float]]
    ) -> tuple[str, ...]:
        if self._feature_fields_override is not None:
            return self._feature_fields_override
        common: Optional[set[str]] = None
        for feat in features:
            keys = set(feat.keys())
            common = keys if common is None else (common & keys)
        common = common or set()
        common.discard(self._target_field)
        common -= self._RESERVED_KEYS
        return tuple(sorted(common))

    # ── Internal: distribution selection (reused pattern) ───────
    def _select_distribution(
        self, targets: np.ndarray, dispersion_ratio: float
    ) -> str:
        """Reuse the dispersion-driven AUTO selection (Req 5.1, 5.3)."""
        if self._distribution_choice != DistributionType.AUTO:
            return self._distribution_choice
        mean_val = float(targets.mean())
        if mean_val > 0 and dispersion_ratio > self._overdispersion_threshold:
            return DistributionType.NEGATIVE_BINOMIAL
        return DistributionType.POISSON

    # ── Internal: MLE inner loops (reused from count_regression) ─
    def _elastic_net_penalty(self, weights: np.ndarray) -> float:
        """Elastic-net penalty added to the neg-log-likelihood (Req 5.4, 5.5).

        ``lam * (alpha_mix * sum(sqrt(w^2 + eps)) + (1 - alpha_mix) * sum(w^2))``.
        The smoothed absolute value keeps L-BFGS-B stable at ``w = 0``; the
        ``(1 - alpha_mix)`` L2 term guarantees this is not pure L1.
        """
        l1 = np.sum(np.sqrt(weights ** 2 + self._eps))
        l2 = np.sum(weights ** 2)
        return self._lam * (self._alpha_mix * l1 + (1.0 - self._alpha_mix) * l2)

    def _fit_poisson(self, targets: np.ndarray, X: np.ndarray) -> dict[str, Any]:
        n, k = X.shape

        def neg_ll(params: np.ndarray) -> float:
            intercept = params[0]
            weights = params[1:]
            log_lambda = np.clip(intercept + X @ weights, -5, 5)
            lam = np.exp(log_lambda)
            ll = np.sum(targets * log_lambda - lam - gammaln(targets + 1))
            ll -= self._elastic_net_penalty(weights)
            return -ll

        x0 = np.zeros(k + 1)
        x0[0] = math.log(max(0.1, float(targets.mean())))
        result = minimize(
            neg_ll, x0, method="L-BFGS-B", options={"maxiter": 300, "ftol": 1e-6}
        )
        return {
            "intercept": float(result.x[0]),
            "weights": result.x[1:].tolist(),
            "dispersion": 0.0,
        }

    def _fit_negative_binomial(
        self, targets: np.ndarray, X: np.ndarray
    ) -> dict[str, Any]:
        n, k = X.shape

        def neg_ll(params: np.ndarray) -> float:
            intercept = params[0]
            weights = params[1:k + 1]
            log_alpha = params[k + 1]
            log_mu = np.clip(intercept + X @ weights, -5, 5)
            mu = np.exp(log_mu)
            alpha = np.exp(np.clip(log_alpha, -5, 5))
            r = 1.0 / alpha
            p = r / (r + mu)
            ll = np.sum(
                gammaln(targets + r) - gammaln(r) - gammaln(targets + 1)
                + r * np.log(np.clip(p, 1e-10, 1.0))
                + targets * np.log(np.clip(1 - p, 1e-10, 1.0))
            )
            ll -= self._elastic_net_penalty(weights)
            return -ll

        x0 = np.zeros(k + 2)
        x0[0] = math.log(max(0.1, float(targets.mean())))
        x0[k + 1] = math.log(0.5)
        result = minimize(
            neg_ll, x0, method="L-BFGS-B", options={"maxiter": 300, "ftol": 1e-6}
        )
        alpha = float(np.exp(np.clip(result.x[k + 1], -5, 5)))
        return {
            "intercept": float(result.x[0]),
            "weights": result.x[1:k + 1].tolist(),
            "dispersion": alpha,
        }

    def _fit_simple_mean(
        self,
        targets: np.ndarray,
        feature_fields: tuple[str, ...],
        dispersion_ratio: float,
    ) -> None:
        mean_val = float(targets.mean()) if targets.size else float(self._line)
        self._params = DirectionalParams(
            intercept=math.log(max(0.1, mean_val)),
            feature_weights={f: 0.0 for f in feature_fields},
            dispersion=0.0,
            distribution=DistributionType.POISSON,
            dispersion_ratio=float(dispersion_ratio),
            n_observations=int(targets.size),
            feature_names=feature_fields,
            mean_target=mean_val,
            std_target=float(targets.std()) if targets.size > 1 else 1.0,
        )

    def _finalise_metadata(
        self,
        n: int,
        training_start: Optional[int],
        training_end: Optional[int],
    ) -> None:
        if training_start is not None and training_end is not None:
            self._training_metadata = TrainingMetadata(
                training_start=training_start,
                training_end=training_end,
                sample_size=n,
                feature_names=self._feature_fields,
            )

    # ── Internal: prediction helpers ────────────────────────────
    def _predict_lambda(self, features: dict[str, float]) -> float:
        params = self._params
        assert params is not None
        log_lambda = params.intercept
        for name, weight in params.feature_weights.items():
            log_lambda += weight * float(features.get(name, 0.0))
        log_lambda = max(-3.0, min(4.0, log_lambda))
        return math.exp(log_lambda)

    def _compute_p_over_at_line(self, lam: float, line: float) -> float:
        params = self._params
        if params is None:
            return 0.5
        if (
            params.distribution == DistributionType.NEGATIVE_BINOMIAL
            and params.dispersion > 0.0
        ):
            alpha = params.dispersion
            r = 1.0 / alpha
            p = r / (r + lam)
            return float(1.0 - nbinom.cdf(int(line), r, p))
        return float(1.0 - poisson.cdf(int(line), lam))


# ═══════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════


def _compute_global_means(
    features: list[dict[str, float]], feature_fields: tuple[str, ...]
) -> dict[str, float]:
    """All-team global mean of each profile feature (shrinkage target)."""
    sums: dict[str, float] = {name: 0.0 for name in feature_fields}
    counts: dict[str, int] = {name: 0 for name in feature_fields}
    for feat in features:
        for name in feature_fields:
            v = feat.get(name)
            if v is not None:
                sums[name] += float(v)
                counts[name] += 1
    return {
        name: (sums[name] / counts[name] if counts[name] else 0.0)
        for name in feature_fields
    }


def _dispersion_ratio(targets: np.ndarray) -> float:
    """Empirical variance/mean ratio of the count target (Req 5.3)."""
    if targets.size < 2:
        return 1.0
    mean_val = float(targets.mean())
    if mean_val <= 0:
        return 1.0
    var_val = float(np.var(targets, ddof=1))
    return var_val / mean_val


# ═══════════════════════════════════════════════════════════════
# TASK 4.2 — binary derived outcomes via the existing logistic model
# ═══════════════════════════════════════════════════════════════


def create_binary_outcome_model(
    learning_rate: float = 0.01,
    max_iter: int = 1000,
    seed: Optional[int] = None,
) -> LogisticRegressionModel:
    """Return a configured logistic model for a binary Derived_Outcome (Req 5.2).

    Binary Derived_Outcomes such as both-teams-to-score (BTTS) and clean sheet
    are modelled with the existing
    :class:`~src.research.probability.LogisticRegressionModel` rather than a
    count model. This thin factory keeps that wiring inside the asymmetric
    package so the Interaction_Model / derived layer can obtain a correctly
    configured logistic estimator without importing the probability module
    directly, and so the choice of logistic-for-binary is explicit and auditable.

    The returned model exposes the standard ``fit(features, outcomes)`` /
    ``predict(features)`` interface where ``outcomes[i]`` is ``True`` when the
    binary event occurred (e.g. BTTS = yes) for observation ``i``.
    """
    return LogisticRegressionModel(
        learning_rate=learning_rate, max_iter=max_iter, seed=seed
    )
