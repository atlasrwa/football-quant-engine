"""Information decomposition experiment (M0-M6) — leakage-safe, common support.

Before training any residual model we quantify WHERE information enters, by
scoring a ladder of chronological models on a COMMON SUPPORT set of
(fixture, market, line, selection) keys:

    M0 = climatology            (base rate of the selection)
    M1 = team/league identity   (base rate conditioned on league)
    M2 = current champion       (fundamental probability)
    M3 = market only            (market prior probability)
    M4 = market + fundamental disagreement   (residual on disagreement)
    M5 = M4 + confirmed lineup delta          (only if PIT-provable)
    M6 = M5 + referee/context                 (where justified)

Primary metrics: log loss, Brier, calibration slope/intercept (reusing the
provider-comparison metrics module) plus a resolution / sharpness measure and a
Murphy (uncertainty / resolution / reliability) decomposition of the Brier
score, so a model is never rewarded merely for shrinking toward 0.5.

Every model is scored on the SAME fixtures. Comparing models on different
fixtures and calling the difference skill is explicitly disallowed here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

import numpy as np

from src.research.experiments.provider_comparison.metrics import (
    brier_losses,
    calibration_slope_intercept,
    log_losses,
)


@dataclass(frozen=True)
class ResolutionReport:
    """Sharpness + Murphy decomposition of the Brier score.

    Brier = Uncertainty - Resolution + Reliability  (Murphy 1973), computed on
    binned forecasts. Higher resolution = better discrimination; lower
    reliability term = better calibration.
    """

    std_p: float
    iqr_p: float
    frac_confident: float  # fraction with |p - base_rate| > threshold
    uncertainty: float
    resolution: float
    reliability: float

    def to_dict(self) -> dict[str, float]:
        return {
            "std_p": self.std_p,
            "iqr_p": self.iqr_p,
            "frac_confident": self.frac_confident,
            "uncertainty": self.uncertainty,
            "resolution": self.resolution,
            "reliability": self.reliability,
        }


def compute_resolution(
    probs: Sequence[float],
    outcomes: Sequence[bool],
    *,
    n_bins: int = 10,
    confident_threshold: float = 0.1,
) -> ResolutionReport:
    """Sharpness measures + Murphy Brier decomposition."""
    p = np.asarray(list(probs), dtype=float)
    y = np.asarray([1.0 if o else 0.0 for o in outcomes], dtype=float)
    n = len(p)
    if n == 0:
        return ResolutionReport(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    base = float(y.mean())
    std_p = float(p.std())
    iqr_p = float(np.subtract(*np.percentile(p, [75, 25]))) if n > 1 else 0.0
    frac_conf = float(np.mean(np.abs(p - base) > confident_threshold))

    uncertainty = base * (1.0 - base)
    # Bin forecasts; resolution = sum n_k/N (obar_k - obar)^2; reliability =
    # sum n_k/N (p_k - obar_k)^2 using the bin mean forecast.
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)
    resolution = 0.0
    reliability = 0.0
    for k in range(n_bins):
        mask = idx == k
        nk = int(mask.sum())
        if nk == 0:
            continue
        obar_k = float(y[mask].mean())
        pbar_k = float(p[mask].mean())
        resolution += nk / n * (obar_k - base) ** 2
        reliability += nk / n * (pbar_k - obar_k) ** 2
    return ResolutionReport(std_p, iqr_p, frac_conf, uncertainty, resolution, reliability)


@dataclass(frozen=True)
class LayerScore:
    """Scores for one model layer on the common support."""

    layer: str
    n: int
    log_loss: float
    brier: float
    calibration_slope: Optional[float]
    calibration_intercept: Optional[float]
    resolution: ResolutionReport
    delta_log_loss_vs_prev: Optional[float] = None
    delta_brier_vs_prev: Optional[float] = None

    def to_dict(self) -> dict[str, object]:
        return {
            "layer": self.layer,
            "n": self.n,
            "log_loss": self.log_loss,
            "brier": self.brier,
            "calibration_slope": self.calibration_slope,
            "calibration_intercept": self.calibration_intercept,
            "resolution": self.resolution.to_dict(),
            "delta_log_loss_vs_prev": self.delta_log_loss_vs_prev,
            "delta_brier_vs_prev": self.delta_brier_vs_prev,
        }


def score_layer(
    layer: str,
    probs: Sequence[float],
    outcomes: Sequence[bool],
    *,
    prev: Optional["LayerScore"] = None,
) -> LayerScore:
    """Score one layer and compute incremental deltas vs the previous layer."""
    ll = float(np.mean(log_losses(probs, outcomes))) if probs else float("nan")
    br = float(np.mean(brier_losses(probs, outcomes))) if probs else float("nan")
    slope, intercept = calibration_slope_intercept(probs, outcomes)
    res = compute_resolution(probs, outcomes)
    d_ll = None if prev is None else ll - prev.log_loss
    d_br = None if prev is None else br - prev.brier
    return LayerScore(
        layer=layer, n=len(probs), log_loss=ll, brier=br,
        calibration_slope=slope, calibration_intercept=intercept, resolution=res,
        delta_log_loss_vs_prev=d_ll, delta_brier_vs_prev=d_br,
    )


def common_support(*keyed_probs: Mapping[tuple, float]) -> list[tuple]:
    """Return the sorted intersection of keys present in every model's outputs.

    Ensures all layers are compared on the SAME (fixture, market, line,
    selection) keys.
    """
    if not keyed_probs:
        return []
    common = set(keyed_probs[0].keys())
    for kp in keyed_probs[1:]:
        common &= set(kp.keys())
    return sorted(common)


def run_decomposition(
    layer_probs: Mapping[str, Mapping[tuple, float]],
    outcomes: Mapping[tuple, bool],
    *,
    layer_order: Sequence[str],
) -> list[LayerScore]:
    """Score an ordered ladder of layers on their common support.

    Args:
        layer_probs: layer name -> {key -> probability}.
        outcomes: key -> realized outcome.
        layer_order: the ordered layer names to score (e.g. M0..M4).

    Only keys present in EVERY listed layer AND in ``outcomes`` are scored, so
    incremental deltas reflect information, not changing fixture sets.
    """
    present = [layer_probs[name] for name in layer_order if name in layer_probs]
    keys = common_support(*present, outcomes)  # type: ignore[arg-type]
    scores: list[LayerScore] = []
    prev: Optional[LayerScore] = None
    for name in layer_order:
        if name not in layer_probs:
            continue
        kp = layer_probs[name]
        probs = [kp[k] for k in keys]
        outs = [outcomes[k] for k in keys]
        score = score_layer(name, probs, outs, prev=prev)
        scores.append(score)
        prev = score
    return scores
