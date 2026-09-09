"""Metrics for the provider comparison (Phase 9).

Reuses the champion's CalibrationEvaluator for Brier / log loss / ECE / MCE and
adds Brier Skill Score (vs a reference set of probabilities) and a logistic
calibration slope/intercept. Every metric bundle carries its N so no metric is
ever reported without a denominator.

Per-fixture loss arrays (squared error / log loss) are exposed so the paired
block bootstrap (bootstrap.py) can operate on identical fixture keys.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

from src.research.calibration import CalibrationEvaluator

_EPS = 1e-15


def _clip(p: float) -> float:
    return max(_EPS, min(1 - _EPS, p))


def brier_losses(probs: Sequence[float], outcomes: Sequence[bool]) -> list[float]:
    return [(p - (1.0 if y else 0.0)) ** 2 for p, y in zip(probs, outcomes)]


def log_losses(probs: Sequence[float], outcomes: Sequence[bool]) -> list[float]:
    out = []
    for p, y in zip(probs, outcomes):
        pc = _clip(p)
        out.append(-(math.log(pc) if y else math.log(1 - pc)))
    return out


def brier_skill_score(
    probs: Sequence[float], outcomes: Sequence[bool], reference_probs: Sequence[float]
) -> Optional[float]:
    """BSS = 1 - Brier(model) / Brier(reference). >0 means better than reference."""
    if not probs:
        return None
    bm = sum(brier_losses(probs, outcomes)) / len(probs)
    br = sum(brier_losses(reference_probs, outcomes)) / len(reference_probs)
    if br <= 0:
        return None
    return 1.0 - bm / br


def calibration_slope_intercept(
    probs: Sequence[float], outcomes: Sequence[bool], *, iters: int = 200, lr: float = 0.1
) -> tuple[Optional[float], Optional[float]]:
    """Logistic recalibration slope/intercept: fit y ~ sigmoid(a + b*logit(p)).

    Perfect calibration => slope b≈1, intercept a≈0. Simple gradient descent
    (no scipy dependency). Returns (slope, intercept) or (None, None) if
    undefined (e.g. all outcomes identical).
    """
    n = len(probs)
    if n < 10:
        return None, None
    ys = [1.0 if y else 0.0 for y in outcomes]
    if len(set(ys)) < 2:
        return None, None
    logits = [math.log(_clip(p) / (1 - _clip(p))) for p in probs]
    a, b = 0.0, 1.0
    for _ in range(iters):
        ga = gb = 0.0
        for x, y in zip(logits, ys):
            pred = 1.0 / (1.0 + math.exp(-(a + b * x)))
            err = pred - y
            ga += err
            gb += err * x
        a -= lr * ga / n
        b -= lr * gb / n
    return b, a


@dataclass
class MetricBundle:
    policy: str
    market: str
    line: Optional[float]
    n: int
    brier: Optional[float] = None
    log_loss: Optional[float] = None
    ece: Optional[float] = None
    mce: Optional[float] = None
    calibration_slope: Optional[float] = None
    calibration_intercept: Optional[float] = None
    mean_prob: Optional[float] = None
    base_rate: Optional[float] = None
    bss_vs_base_rate: Optional[float] = None  # skill vs constant base-rate forecast

    def to_dict(self) -> dict:
        def r(x, k=4):
            return None if x is None else round(x, k)
        return {
            "policy": self.policy, "market": self.market, "line": self.line, "n": self.n,
            "brier": r(self.brier), "log_loss": r(self.log_loss),
            "ece": r(self.ece), "mce": r(self.mce),
            "calibration_slope": r(self.calibration_slope),
            "calibration_intercept": r(self.calibration_intercept),
            "mean_prob": r(self.mean_prob), "base_rate": r(self.base_rate),
            "bss_vs_base_rate": r(self.bss_vs_base_rate),
        }


def compute_metrics(
    probs: Sequence[float], outcomes: Sequence[bool], *,
    policy: str, market: str, line: Optional[float], n_bins: int = 10,
) -> MetricBundle:
    n = len(probs)
    mb = MetricBundle(policy=policy, market=market, line=line, n=n)
    if n == 0:
        return mb
    ev = CalibrationEvaluator(n_bins=n_bins, min_samples=1)
    res = ev.evaluate(list(probs), list(outcomes))
    mb.brier = res.brier_score
    mb.log_loss = res.log_loss
    mb.ece = res.ece
    mb.mce = res.mce
    mb.mean_prob = sum(probs) / n
    mb.base_rate = sum(1 for y in outcomes if y) / n
    mb.calibration_slope, mb.calibration_intercept = calibration_slope_intercept(probs, outcomes)
    # Skill vs the constant base-rate forecast (climatology).
    base = [mb.base_rate] * n
    mb.bss_vs_base_rate = brier_skill_score(probs, outcomes, base)
    return mb
