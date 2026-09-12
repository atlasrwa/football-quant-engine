"""Proper probabilistic evaluation metrics (pure, dependency-light).

All metrics operate on paired arrays of predicted probabilities ``p`` (for the
positive class = over the line) and binary outcomes ``y`` in {0,1}. No metric
here optimizes for market agreement; these describe how well ``p`` predicts the
actual football event.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

_EPS = 1e-12


def brier_score(p: Sequence[float], y: Sequence[float]) -> float:
    """Mean squared error of probability vs binary outcome (lower is better)."""
    n = len(p)
    if n == 0:
        return float("nan")
    return sum((float(pi) - float(yi)) ** 2 for pi, yi in zip(p, y)) / n


def log_loss(p: Sequence[float], y: Sequence[float]) -> float:
    """Mean negative log-likelihood (lower is better). Clipped for safety."""
    n = len(p)
    if n == 0:
        return float("nan")
    total = 0.0
    for pi, yi in zip(p, y):
        pc = min(max(float(pi), _EPS), 1.0 - _EPS)
        total += -(float(yi) * math.log(pc) + (1.0 - float(yi)) * math.log(1.0 - pc))
    return total / n


def brier_skill_score(p: Sequence[float], y: Sequence[float]) -> float:
    """Brier skill vs the constant base-rate predictor (>0 means beats base rate)."""
    n = len(y)
    if n == 0:
        return float("nan")
    base = sum(float(yi) for yi in y) / n
    bs_ref = sum((base - float(yi)) ** 2 for yi in y) / n
    if bs_ref <= 0:
        return float("nan")
    return 1.0 - brier_score(p, y) / bs_ref


def expected_calibration_error(
    p: Sequence[float], y: Sequence[float], *, n_bins: int = 10
) -> float:
    """ECE: sample-weighted mean |mean_pred - observed_freq| across bins."""
    n = len(p)
    if n == 0:
        return float("nan")
    ece = 0.0
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        idx = [
            i
            for i in range(n)
            if (p[i] >= lo and (p[i] < hi if b < n_bins - 1 else p[i] <= hi))
        ]
        if not idx:
            continue
        mean_p = sum(p[i] for i in idx) / len(idx)
        obs = sum(float(y[i]) for i in idx) / len(idx)
        ece += (len(idx) / n) * abs(mean_p - obs)
    return ece


def preferred_side_accuracy(p: Sequence[float], y: Sequence[float]) -> float:
    """Directional accuracy of the model's MOST-LIKELY side.

    For each observation the model predicts over iff ``p > 0.5``. Accuracy is the
    fraction of observations where the predicted most-likely side matches the
    realized side. Ties (``p == 0.5``) are excluded (no preferred side).
    """
    correct = total = 0
    for pi, yi in zip(p, y):
        if pi == 0.5:
            continue
        pred_over = pi > 0.5
        actual_over = float(yi) >= 0.5
        total += 1
        if pred_over == actual_over:
            correct += 1
    return correct / total if total else float("nan")


@dataclass
class ReliabilityBin:
    lo: float
    hi: float
    n: int
    mean_pred: Optional[float]
    observed_freq: Optional[float]

    def to_dict(self) -> dict:
        return {
            "bucket": f"{self.lo:.2f}-{self.hi:.2f}",
            "n": self.n,
            "mean_pred": round(self.mean_pred, 4) if self.mean_pred is not None else None,
            "observed_freq": round(self.observed_freq, 4) if self.observed_freq is not None else None,
            "diff": round(self.mean_pred - self.observed_freq, 4)
            if self.mean_pred is not None and self.observed_freq is not None
            else None,
        }


def reliability_bins(
    p: Sequence[float], y: Sequence[float], *, n_bins: int = 10
) -> list[ReliabilityBin]:
    """Reliability table: mean predicted vs observed frequency per probability bin."""
    out: list[ReliabilityBin] = []
    n = len(p)
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        idx = [
            i
            for i in range(n)
            if (p[i] >= lo and (p[i] < hi if b < n_bins - 1 else p[i] <= hi))
        ]
        if idx:
            out.append(
                ReliabilityBin(
                    lo, hi, len(idx),
                    sum(p[i] for i in idx) / len(idx),
                    sum(float(y[i]) for i in idx) / len(idx),
                )
            )
        else:
            out.append(ReliabilityBin(lo, hi, 0, None, None))
    return out


#: Confidence ladder thresholds on the MOST-LIKELY side (|p-0.5|). Reports, for
#: each min-probability threshold on the model's chosen side, the realized
#: accuracy of that side. This is the "does accuracy rise with confidence" test.
def confidence_ladder(
    p: Sequence[float], y: Sequence[float],
    thresholds: Sequence[float] = (0.50, 0.55, 0.60, 0.65, 0.70),
) -> list[dict]:
    """For each threshold t: among observations where the chosen side has
    probability >= t, report N, mean chosen-side probability, and realized
    accuracy of the chosen side."""
    rows = []
    for t in thresholds:
        chosen = []  # (chosen_side_prob, correct)
        for pi, yi in zip(p, y):
            side_p = max(pi, 1.0 - pi)  # prob of the model's chosen side
            if side_p < t:
                continue
            pred_over = pi >= 0.5
            actual_over = float(yi) >= 0.5
            chosen.append((side_p, pred_over == actual_over))
        n = len(chosen)
        rows.append({
            "min_chosen_prob": t,
            "n": n,
            "mean_chosen_prob": round(sum(c[0] for c in chosen) / n, 4) if n else None,
            "accuracy": round(sum(1 for c in chosen if c[1]) / n, 4) if n else None,
        })
    return rows


@dataclass
class MetricBlock:
    n: int
    base_rate: float
    accuracy: float
    brier: float
    log_loss: float
    bss: float
    ece: float
    mean_pred: float

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "base_rate": round(self.base_rate, 4),
            "accuracy": round(self.accuracy, 4),
            "brier": round(self.brier, 5),
            "log_loss": round(self.log_loss, 5),
            "bss_pct": round(self.bss * 100, 3),
            "ece": round(self.ece, 4),
            "mean_pred": round(self.mean_pred, 4),
        }


def metric_block(p: Sequence[float], y: Sequence[float]) -> MetricBlock:
    n = len(p)
    base = sum(float(yi) for yi in y) / n if n else float("nan")
    return MetricBlock(
        n=n,
        base_rate=base,
        accuracy=preferred_side_accuracy(p, y),
        brier=brier_score(p, y),
        log_loss=log_loss(p, y),
        bss=brier_skill_score(p, y),
        ece=expected_calibration_error(p, y),
        mean_pred=sum(p) / n if n else float("nan"),
    )
