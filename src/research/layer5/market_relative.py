"""Layer 5 market-relative benchmark and incremental-information arm.

This module is separate from the standalone QFE p_model. Market prices never
modify the Layer 4 model or calibration. The routines here operate only on
pre-protected matched rows and are intended for the preregistered secondary
market-relative research comparison.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, log
from typing import Iterable, Optional

import numpy as np
from scipy.optimize import minimize

from src.research.layer4.calibrators import (
    IdentityCalibrator,
    PlattGlobal,
    calibrator_from_spec,
    weighted_brier,
    weighted_log_loss,
)

MIN_MATCHED_UNIQUE_FIXTURES = 250
MARKET_ONLY_BRIER_NONINFERIORITY_TOLERANCE = 0.001
MARKET_ANCHORED_RIDGE_LAMBDA = 1.0
PROBABILITY_CLIP = 1e-6


@dataclass(frozen=True, slots=True)
class MarketRelativeRow:
    fixture_key: str
    phase: str
    group: str
    p_market: float
    p_model: float
    outcome_over: bool
    role: Optional[str] = None
    line: Optional[float] = None


@dataclass(frozen=True, slots=True)
class MarketOnlyBenchmarkResult:
    status: str
    reason: Optional[str]
    fit_unique_fixtures: int
    select_unique_fixtures: int
    total_unique_fixtures: int
    identity_select_log_loss: Optional[float]
    identity_select_brier: Optional[float]
    platt_select_log_loss: Optional[float]
    platt_select_brier: Optional[float]
    selected_candidate: Optional[str]
    selected_spec: Optional[dict]


@dataclass(frozen=True, slots=True)
class MarketAnchoredLogisticStack:
    intercept: float
    beta_market: float
    beta_qfe: float
    ridge_lambda: float
    eps: float

    def transform(self, p_market: float, p_model: float) -> float:
        z = (
            self.intercept
            + self.beta_market * _logit(p_market, self.eps)
            + self.beta_qfe * _logit(p_model, self.eps)
        )
        return _sigmoid(z)

    def to_spec(self) -> dict:
        return {
            "method": "MARKET_ANCHORED_LOGISTIC_STACK",
            "intercept": self.intercept,
            "beta_market": self.beta_market,
            "beta_qfe": self.beta_qfe,
            "ridge_lambda": self.ridge_lambda,
            "eps": self.eps,
            "penalty_anchor": {"beta_market": 1.0, "beta_qfe": 0.0},
        }


@dataclass(frozen=True, slots=True)
class IncrementalInformationResult:
    status: str
    reason: Optional[str]
    market_only: MarketOnlyBenchmarkResult
    stack_spec: Optional[dict]
    baseline_select_log_loss: Optional[float]
    baseline_select_brier: Optional[float]
    stack_select_log_loss: Optional[float]
    stack_select_brier: Optional[float]
    log_loss_improvement_market_minus_stack: Optional[float]
    brier_improvement_market_minus_stack: Optional[float]


def _clip(p: float, eps: float = PROBABILITY_CLIP) -> float:
    p = float(p)
    if not 0.0 <= p <= 1.0:
        raise ValueError("probability must be in [0, 1]")
    return min(max(p, eps), 1.0 - eps)


def _logit(p: float, eps: float = PROBABILITY_CLIP) -> float:
    q = _clip(p, eps)
    return log(q / (1.0 - q))


def _sigmoid(z: float) -> float:
    if z >= 0:
        e = exp(-min(float(z), 700.0))
        return 1.0 / (1.0 + e)
    e = exp(max(float(z), -700.0))
    return e / (1.0 + e)


def _validate_rows(rows: list[MarketRelativeRow]) -> None:
    for row in rows:
        if row.phase not in {"CALIBRATION_FIT", "CALIBRATION_SELECT"}:
            raise ValueError(f"unsupported pre-protected phase: {row.phase}")
        if not row.fixture_key or not row.group:
            raise ValueError("fixture_key and group are required")
        _clip(row.p_market)
        _clip(row.p_model)


def _fixture_balanced_weights(rows: list[MarketRelativeRow]) -> list[float]:
    """Give every fixture total weight one, then equal weight to its cells."""
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.fixture_key] = counts.get(row.fixture_key, 0) + 1
    return [1.0 / counts[row.fixture_key] for row in rows]


def _metrics(probabilities: list[float], rows: list[MarketRelativeRow]) -> tuple[float, float]:
    outcomes = [bool(row.outcome_over) for row in rows]
    weights = _fixture_balanced_weights(rows)
    return (
        weighted_log_loss(probabilities, outcomes, weights),
        weighted_brier(probabilities, outcomes, weights),
    )


def fit_market_only_benchmark(
    rows: Iterable[MarketRelativeRow],
    *,
    minimum_unique_fixtures: int = MIN_MATCHED_UNIQUE_FIXTURES,
    brier_tolerance: float = MARKET_ONLY_BRIER_NONINFERIORITY_TOLERANCE,
    eps: float = PROBABILITY_CLIP,
) -> MarketOnlyBenchmarkResult:
    """Fit IDENTITY vs global Platt exactly on FIT and score on SELECT.

    The 0.001 Brier tolerance is deliberately inherited from the already
    frozen Layer 4 calibration protocol, avoiding a new data-driven tolerance.
    This comparator remains diagnostic and never replaces primary p_market.
    """
    data = list(rows)
    _validate_rows(data)
    groups = {row.group for row in data}
    if len(groups) != 1:
        raise ValueError("market-only benchmark must be fit separately by group")

    fit = [row for row in data if row.phase == "CALIBRATION_FIT"]
    select = [row for row in data if row.phase == "CALIBRATION_SELECT"]
    total_unique = len({row.fixture_key for row in data})
    fit_unique = len({row.fixture_key for row in fit})
    select_unique = len({row.fixture_key for row in select})
    if total_unique < minimum_unique_fixtures:
        return MarketOnlyBenchmarkResult(
            "INELIGIBLE", "INSUFFICIENT_MATCHED_PREPROTECTED_FIXTURES",
            fit_unique, select_unique, total_unique,
            None, None, None, None, None, None,
        )
    if not fit or not select:
        return MarketOnlyBenchmarkResult(
            "INELIGIBLE", "MISSING_FIT_OR_SELECT_PHASE",
            fit_unique, select_unique, total_unique,
            None, None, None, None, None, None,
        )
    fit_outcomes = [bool(row.outcome_over) for row in fit]
    if len(set(fit_outcomes)) < 2:
        return MarketOnlyBenchmarkResult(
            "INELIGIBLE", "ONE_CLASS_FIT",
            fit_unique, select_unique, total_unique,
            None, None, None, None, None, None,
        )

    identity = IdentityCalibrator()
    fit_weights = _fixture_balanced_weights(fit)
    platt = PlattGlobal.fit(
        [row.p_market for row in fit],
        fit_outcomes,
        fit_weights,
        eps,
    )
    identity_probs = [identity.transform(row.p_market) for row in select]
    platt_probs = [platt.transform(row.p_market) for row in select]
    id_ll, id_brier = _metrics(identity_probs, select)
    platt_ll, platt_brier = _metrics(platt_probs, select)
    platt_eligible = (
        platt_ll < id_ll
        and platt_brier <= id_brier + float(brier_tolerance)
    )
    selected = platt if platt_eligible else identity

    return MarketOnlyBenchmarkResult(
        status="OK",
        reason=None,
        fit_unique_fixtures=fit_unique,
        select_unique_fixtures=select_unique,
        total_unique_fixtures=total_unique,
        identity_select_log_loss=float(id_ll),
        identity_select_brier=float(id_brier),
        platt_select_log_loss=float(platt_ll),
        platt_select_brier=float(platt_brier),
        selected_candidate=selected.name,
        selected_spec=selected.to_spec(),
    )


def fit_market_anchored_stack(
    rows: Iterable[MarketRelativeRow],
    *,
    ridge_lambda: float = MARKET_ANCHORED_RIDGE_LAMBDA,
    eps: float = PROBABILITY_CLIP,
) -> MarketAnchoredLogisticStack:
    """Fit market + QFE stack on FIT rows, regularized toward market-only.

    The penalty is centered on beta_market=1 and beta_qfe=0. This implements
    the intended 'market as prior, QFE as incremental signal' structure rather
    than shrinking both coefficients toward zero.
    """
    data = list(rows)
    _validate_rows(data)
    if not data:
        raise ValueError("empty fit rows")
    if len({row.group for row in data}) != 1:
        raise ValueError("incremental stack must be fit separately by group")
    outcomes = np.asarray([float(row.outcome_over) for row in data])
    if len(set(outcomes.tolist())) < 2:
        raise ValueError("ONE_CLASS_FIT")
    weights = np.asarray(_fixture_balanced_weights(data), dtype=float)
    market_x = np.asarray([_logit(row.p_market, eps) for row in data], dtype=float)
    qfe_x = np.asarray([_logit(row.p_model, eps) for row in data], dtype=float)

    def objective(v: np.ndarray) -> float:
        z = v[0] + v[1] * market_x + v[2] * qfe_x
        probs = [_sigmoid(float(value)) for value in z]
        loss = weighted_log_loss(probs, outcomes, weights, eps) * float(weights.sum())
        penalty = float(ridge_lambda) * ((float(v[1]) - 1.0) ** 2 + float(v[2]) ** 2)
        return float(loss + penalty)

    result = minimize(
        objective,
        np.asarray([0.0, 1.0, 0.0]),
        method="L-BFGS-B",
        bounds=[(None, None), (1e-6, None), (None, None)],
        options={"maxiter": 2000},
    )
    if not result.success:
        raise RuntimeError(result.message)
    return MarketAnchoredLogisticStack(
        intercept=float(result.x[0]),
        beta_market=float(result.x[1]),
        beta_qfe=float(result.x[2]),
        ridge_lambda=float(ridge_lambda),
        eps=float(eps),
    )


def run_incremental_information_experiment(
    rows: Iterable[MarketRelativeRow],
) -> IncrementalInformationResult:
    """Score fixed market-anchored stack versus selected market-only comparator.

    No threshold is promoted here. The output is a research comparison; later
    uncertainty estimation and protected/prospective confirmation remain
    separate gates.
    """
    data = list(rows)
    _validate_rows(data)
    market_only = fit_market_only_benchmark(data)
    if market_only.status != "OK":
        return IncrementalInformationResult(
            market_only.status,
            market_only.reason,
            market_only,
            None, None, None, None, None, None, None,
        )

    fit = [row for row in data if row.phase == "CALIBRATION_FIT"]
    select = [row for row in data if row.phase == "CALIBRATION_SELECT"]
    stack = fit_market_anchored_stack(fit)

    assert market_only.selected_spec is not None
    baseline_calibrator = calibrator_from_spec(market_only.selected_spec)
    baseline_probs = [baseline_calibrator.transform(row.p_market) for row in select]
    stack_probs = [stack.transform(row.p_market, row.p_model) for row in select]
    baseline_ll, baseline_brier = _metrics(baseline_probs, select)
    stack_ll, stack_brier = _metrics(stack_probs, select)

    return IncrementalInformationResult(
        status="OK",
        reason=None,
        market_only=market_only,
        stack_spec=stack.to_spec(),
        baseline_select_log_loss=float(baseline_ll),
        baseline_select_brier=float(baseline_brier),
        stack_select_log_loss=float(stack_ll),
        stack_select_brier=float(stack_brier),
        log_loss_improvement_market_minus_stack=float(baseline_ll - stack_ll),
        brier_improvement_market_minus_stack=float(baseline_brier - stack_brier),
    )
