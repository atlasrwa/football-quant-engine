"""Calibration metrics for the prediction engine — ECE, reliability, Brier, BSS.

Calibration is the product claim, so this module is deliberately strict:

* **ECE and the reliability curve are primary.** Brier and BSS-vs-naive are
  supporting figures. Every reported number carries its sample size, shown at
  equal prominence.
* **Minimum-sample gate.** Below :data:`~src.research.prediction_engine.scope.MIN_SETTLED_FOR_CALIBRATION`
  settled predictions, NO calibration figure is published — the report says
  "insufficient settled predictions — N of ~200" instead. An ECE on 20
  predictions is noise.
* **Base-rate-collapse flag.** A zero-feature constant predictor is trivially
  calibrated. If a model collapses to (near) base-rate prediction, that is
  flagged rather than reported as good ECE.

Measurement reuses the existing, out-of-sample-only
:class:`src.research.calibration.CalibrationEvaluator` (Brier / log-loss / ECE /
MCE / reliability bins). This module adds the BSS-vs-naive figure, the sample
gate, and the collapse check on top of it — it does not re-derive calibration
maths.

NO STAKE SIZING: this module reports how trustworthy a probability is. It never
converts a probability into a stake, and nothing downstream of it may either.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

from src.research.calibration import CalibrationEvaluator, CalibrationResult
from src.research.prediction_engine.scope import (
    MIN_SETTLED_FOR_CALIBRATION,
    insufficient_sample_notice,
)


# ─────────────────────────────────────────────────────────────────────────────
# BSS vs naive base rate (supporting figure)
# ─────────────────────────────────────────────────────────────────────────────
def _brier(predicted: Sequence[float], outcomes: Sequence[bool]) -> float:
    """Mean squared error of predicted probability vs realised {0, 1}."""
    n = len(predicted)
    if n == 0:
        return 0.0
    total = 0.0
    for p, y in zip(predicted, outcomes):
        yv = 1.0 if y else 0.0
        total += (float(p) - yv) ** 2
    return total / n


def naive_base_rate_brier(outcomes: Sequence[bool]) -> float:
    """Brier score of the naive predictor that always predicts the base rate.

    The base rate is the realised frequency of the positive outcome over the same
    sample. This is the honest "no-skill" reference: a constant predictor equal to
    the observed mean.
    """
    n = len(outcomes)
    if n == 0:
        return 0.0
    base = sum(1.0 for y in outcomes if y) / n
    return _brier([base] * n, outcomes)


@dataclass(frozen=True)
class BSSResult:
    """Brier Skill Score of a model vs the naive base-rate predictor.

    ``bss = 1 - Brier(model) / Brier(naive)``. Positive means the model's
    probabilities are sharper than always predicting the base rate; zero means no
    skill over the base rate; negative means worse than the base rate.
    """

    bss: Optional[float]
    brier_model: float
    brier_naive: float
    n: int

    @property
    def has_skill(self) -> bool:
        """True iff BSS is positive (some skill over the base rate)."""
        return self.bss is not None and self.bss > 0.0


def brier_skill_score(
    predicted: Sequence[float], outcomes: Sequence[bool]
) -> BSSResult:
    """Compute the Brier Skill Score vs the naive base-rate predictor.

    Both the model and the naive reference are scored on the SAME sample; the
    reference is the constant base-rate predictor from that sample. Returns
    ``bss = None`` when the naive Brier is degenerate (all outcomes identical, so
    the base rate is a perfect constant predictor and the ratio is undefined).
    """
    predicted = list(predicted)
    outcomes = list(outcomes)
    if len(predicted) != len(outcomes):
        raise ValueError("predicted and outcomes must have equal length")
    n = len(outcomes)
    brier_model = _brier(predicted, outcomes)
    brier_naive = naive_base_rate_brier(outcomes)
    if brier_naive <= 1e-12:
        return BSSResult(bss=None, brier_model=brier_model, brier_naive=brier_naive, n=n)
    return BSSResult(
        bss=1.0 - brier_model / brier_naive,
        brier_model=brier_model,
        brier_naive=brier_naive,
        n=n,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Base-rate-collapse detection
# ─────────────────────────────────────────────────────────────────────────────

#: A model whose predictions vary by less than this (std-dev) around their mean is
#: treated as having collapsed to a near-constant (base-rate) predictor.
DEFAULT_COLLAPSE_STD_TOLERANCE = 1e-3


@dataclass(frozen=True)
class CollapseResult:
    """Whether a set of predicted probabilities has collapsed to a constant.

    A zero-feature constant predictor is trivially calibrated, so good ECE from a
    collapsed model is meaningless. ``collapsed`` True means the report must flag
    the model as base-rate-collapsed rather than celebrate its ECE.
    """

    collapsed: bool
    predicted_std: float
    predicted_mean: float
    detail: str


def base_rate_collapse(
    predicted: Sequence[float],
    *,
    std_tolerance: float = DEFAULT_COLLAPSE_STD_TOLERANCE,
) -> CollapseResult:
    """Detect whether predicted probabilities have collapsed to a constant.

    Uses the spread (population std-dev) of the predicted probabilities: a model
    that always emits (essentially) the same probability regardless of input has
    collapsed to a base-rate predictor. This is a property of the PREDICTIONS, so
    it works for any model without introspection.
    """
    vals = [float(p) for p in predicted]
    n = len(vals)
    if n == 0:
        return CollapseResult(
            collapsed=False, predicted_std=0.0, predicted_mean=0.0,
            detail="no predictions",
        )
    mean = math.fsum(vals) / n
    var = math.fsum((v - mean) ** 2 for v in vals) / n
    std = math.sqrt(var)
    collapsed = std <= std_tolerance
    detail = (
        f"predicted std {std:.6f} <= tolerance {std_tolerance:g}: predictions are "
        "effectively constant (base-rate collapse); a constant predictor is "
        "trivially calibrated, so ECE is not evidence of skill"
        if collapsed
        else f"predicted std {std:.6f} > tolerance {std_tolerance:g}: not collapsed"
    )
    return CollapseResult(
        collapsed=collapsed, predicted_std=std, predicted_mean=mean, detail=detail
    )


# ─────────────────────────────────────────────────────────────────────────────
# The gated calibration report
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class CalibrationReport:
    """A calibration figure for one market/league cell, gated for honesty.

    Attributes:
        market: the market key.
        league_label: the league (``None`` for pooled).
        n_settled: number of settled predictions scored.
        gate_met: True iff ``n_settled >= minimum``; when False no calibration
            figure is published and :attr:`gate_notice` explains why.
        gate_notice: the "insufficient settled predictions — N of ~200" notice
            when the gate is not met (else empty).
        calibration: the reused :class:`CalibrationResult` (ECE/reliability/Brier)
            — only populated when the gate is met.
        bss: BSS-vs-naive supporting figure — only populated when the gate is met.
        collapse: base-rate-collapse check on the predictions.
    """

    market: str
    league_label: Optional[str]
    n_settled: int
    gate_met: bool
    gate_notice: str
    calibration: Optional[CalibrationResult]
    bss: Optional[BSSResult]
    collapse: CollapseResult

    @property
    def publishable(self) -> bool:
        """True iff a calibration figure may be shown for this cell."""
        return self.gate_met and self.calibration is not None and self.calibration.is_valid

    @property
    def ece(self) -> Optional[float]:
        return self.calibration.ece if self.calibration else None


def calibration_report(
    market: str,
    predicted: Sequence[float],
    outcomes: Sequence[bool],
    *,
    league_label: Optional[str] = None,
    minimum: int = MIN_SETTLED_FOR_CALIBRATION,
    n_bins: int = 10,
    collapse_std_tolerance: float = DEFAULT_COLLAPSE_STD_TOLERANCE,
) -> CalibrationReport:
    """Build a minimum-sample-gated calibration report for one market/league cell.

    Behaviour:

    * If fewer than ``minimum`` settled predictions are supplied, NO calibration
      figure is computed; the report carries the "insufficient settled
      predictions — N of ~{minimum}" notice (:func:`insufficient_sample_notice`).
    * Otherwise ECE / reliability / Brier are computed via the reused
      :class:`CalibrationEvaluator` (out-of-sample only), and the BSS-vs-naive
      supporting figure is added.
    * The base-rate-collapse check always runs on the predictions so a
      trivially-calibrated constant predictor is flagged rather than celebrated.

    Args:
        market: market key (for labelling only; not validated here).
        predicted: out-of-sample predicted probabilities for the market outcome.
        outcomes: realised binary outcomes (same length as ``predicted``).
        league_label: league for this cell (``None`` for pooled).
        minimum: minimum-sample gate (default ~200).
        n_bins: reliability-curve bins.
        collapse_std_tolerance: std-dev tolerance for base-rate-collapse.

    Raises:
        ValueError: if ``predicted`` and ``outcomes`` differ in length.
    """
    predicted = list(predicted)
    outcomes = list(outcomes)
    if len(predicted) != len(outcomes):
        raise ValueError("predicted and outcomes must have equal length")

    n_settled = len(outcomes)
    collapse = base_rate_collapse(predicted, std_tolerance=collapse_std_tolerance)

    if n_settled < minimum:
        return CalibrationReport(
            market=market,
            league_label=league_label,
            n_settled=n_settled,
            gate_met=False,
            gate_notice=insufficient_sample_notice(n_settled, minimum),
            calibration=None,
            bss=None,
            collapse=collapse,
        )

    evaluator = CalibrationEvaluator(n_bins=n_bins, min_samples=min(minimum, n_settled))
    result = evaluator.evaluate(predicted, [bool(o) for o in outcomes])
    bss = brier_skill_score(predicted, outcomes)
    return CalibrationReport(
        market=market,
        league_label=league_label,
        n_settled=n_settled,
        gate_met=True,
        gate_notice="",
        calibration=result,
        bss=bss,
        collapse=collapse,
    )
