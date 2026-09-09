"""Provider comparison harness — apples-to-apples evaluation, no verdict.

An *arm* is a labeled set of probabilistic predictions from one configuration
(e.g. "footystats_only", "thestatsapi_only", "combined", "market"). Each
prediction is keyed by a fixture id (canonical) so arms can be aligned on the
EXACT SAME fixtures. The harness:

1. Intersects fixtures across the arms being compared so every metric is
   computed on an identical subset (fair comparison).
2. Computes Brier, log loss, and calibration (reusing CalibrationEvaluator)
   plus Brier skill score vs a chosen reference arm, and RPS when predictions
   are ordered multi-outcome distributions.
3. Reports per-arm coverage (how many of the union fixtures each arm predicted)
   so missing-data effects are visible rather than hidden.

It NEVER declares a winner: ``ProviderComparisonReport.verdict`` is always
"NO_CLAIM". Ranking arms by a metric is the analyst's job, out of sample.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from src.research.calibration import CalibrationEvaluator


@dataclass(frozen=True)
class ArmPredictions:
    """Predictions for one evaluation arm.

    Attributes:
        name: Arm label (e.g. "footystats_only").
        binary: fixture_id -> P(positive outcome) for a binary market
            (e.g. P(OVER)). Used for Brier/log loss/calibration.
        outcomes: fixture_id -> actual boolean outcome (settled).
        ordered: optional fixture_id -> (probabilities, outcome_index) for an
            ORDERED multi-outcome market (e.g. exact totals ladder), used for
            RPS. Probabilities must sum to ~1 and be in outcome order.
    """
    name: str
    binary: dict[str, float] = field(default_factory=dict)
    outcomes: dict[str, bool] = field(default_factory=dict)
    ordered: dict[str, tuple[Sequence[float], int]] = field(default_factory=dict)


@dataclass(frozen=True)
class ArmMetrics:
    """Computed metrics for one arm on the aligned fixture subset."""
    name: str
    n_evaluated: int
    coverage: float  # fraction of the union fixtures this arm predicted
    brier: Optional[float] = None
    log_loss: Optional[float] = None
    ece: Optional[float] = None
    mce: Optional[float] = None
    brier_skill_score: Optional[float] = None  # vs reference arm
    mean_rps: Optional[float] = None
    calibration_status: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "n_evaluated": self.n_evaluated,
            "coverage": round(self.coverage, 4),
            "brier": self.brier,
            "log_loss": self.log_loss,
            "ece": self.ece,
            "mce": self.mce,
            "brier_skill_score": self.brier_skill_score,
            "mean_rps": self.mean_rps,
            "calibration_status": self.calibration_status,
        }


@dataclass(frozen=True)
class ProviderComparisonReport:
    """Comparison report. verdict is ALWAYS 'NO_CLAIM'."""
    arms: list[ArmMetrics]
    aligned_fixture_count: int
    reference_arm: Optional[str]
    verdict: str = "NO_CLAIM"
    note: str = (
        "Comparative metrics only. No arm is declared superior. Any claim "
        "requires an explicit out-of-sample study on identical fixtures and cutoffs."
    )

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "note": self.note,
            "aligned_fixture_count": self.aligned_fixture_count,
            "reference_arm": self.reference_arm,
            "arms": [a.to_dict() for a in self.arms],
        }


def ranked_probability_score(probabilities: Sequence[float], outcome_index: int) -> float:
    """Ranked Probability Score for a single ordered multi-outcome prediction.

    RPS = (1/(K-1)) * sum_{k=1}^{K-1} (CDF_pred(k) - CDF_obs(k))^2

    Lower is better. Requires K >= 2 categories and a valid outcome index.
    """
    k = len(probabilities)
    if k < 2:
        raise ValueError("RPS requires at least 2 ordered categories")
    if not (0 <= outcome_index < k):
        raise ValueError(f"outcome_index {outcome_index} out of range for {k} categories")
    cum_pred = 0.0
    cum_obs = 0.0
    total = 0.0
    for i in range(k - 1):
        cum_pred += probabilities[i]
        cum_obs += 1.0 if i >= outcome_index else 0.0
        total += (cum_pred - cum_obs) ** 2
    return total / (k - 1)


class ProviderComparisonHarness:
    """Computes aligned, verdict-free comparison metrics across arms."""

    def __init__(self, n_bins: int = 10, min_samples: int = 1) -> None:
        self._evaluator = CalibrationEvaluator(n_bins=n_bins, min_samples=min_samples)

    def compare(
        self,
        arms: list[ArmPredictions],
        *,
        reference_arm: Optional[str] = None,
        align: bool = True,
    ) -> ProviderComparisonReport:
        """Compare arms on an identical fixture subset.

        Args:
            arms: Arms to compare. Each supplies binary predictions/outcomes
                and optionally ordered predictions.
            reference_arm: Arm name used as the Brier skill-score baseline
                (e.g. "market"). If None, no skill score is computed.
            align: When True (default), metrics are computed only on fixtures
                present in ALL arms' binary predictions AND with a settled
                outcome — guaranteeing an apples-to-apples subset.

        Returns:
            ProviderComparisonReport (verdict always NO_CLAIM).
        """
        if not arms:
            return ProviderComparisonReport(arms=[], aligned_fixture_count=0, reference_arm=reference_arm)

        # Union of all fixtures (for coverage) and intersection (for fairness).
        union: set[str] = set()
        per_arm_fixtures: dict[str, set[str]] = {}
        for arm in arms:
            fx = set(arm.binary.keys()) & set(arm.outcomes.keys())
            per_arm_fixtures[arm.name] = fx
            union |= fx

        if align:
            aligned = set.intersection(*per_arm_fixtures.values()) if per_arm_fixtures else set()
        else:
            aligned = union

        aligned_sorted = sorted(aligned)

        # Reference Brier for skill score.
        ref_brier: Optional[float] = None
        if reference_arm is not None:
            ref_arm = next((a for a in arms if a.name == reference_arm), None)
            if ref_arm is not None and aligned_sorted:
                ref_brier = _brier_on(ref_arm, aligned_sorted)

        metrics: list[ArmMetrics] = []
        for arm in arms:
            preds = [arm.binary[f] for f in aligned_sorted if f in arm.binary and f in arm.outcomes]
            outs = [arm.outcomes[f] for f in aligned_sorted if f in arm.binary and f in arm.outcomes]
            n = len(preds)
            coverage = (len(per_arm_fixtures[arm.name]) / len(union)) if union else 0.0

            brier = log_loss = ece = mce = None
            status = "NO_PREDICTIONS"
            if n > 0:
                result = self._evaluator.evaluate(preds, outs)
                status = result.status.value if hasattr(result.status, "value") else str(result.status)
                brier = result.brier_score
                log_loss = result.log_loss
                ece = result.ece
                mce = result.mce

            bss = None
            if ref_brier is not None and brier is not None and ref_brier > 0:
                bss = 1.0 - (brier / ref_brier)

            mean_rps = _mean_rps_on(arm, aligned_sorted)

            metrics.append(ArmMetrics(
                name=arm.name, n_evaluated=n, coverage=coverage,
                brier=brier, log_loss=log_loss, ece=ece, mce=mce,
                brier_skill_score=bss, mean_rps=mean_rps, calibration_status=status,
            ))

        return ProviderComparisonReport(
            arms=metrics,
            aligned_fixture_count=len(aligned_sorted),
            reference_arm=reference_arm,
        )


def _brier_on(arm: ArmPredictions, fixtures: list[str]) -> Optional[float]:
    pairs = [(arm.binary[f], arm.outcomes[f]) for f in fixtures
             if f in arm.binary and f in arm.outcomes]
    if not pairs:
        return None
    return sum((p - (1.0 if y else 0.0)) ** 2 for p, y in pairs) / len(pairs)


def _mean_rps_on(arm: ArmPredictions, fixtures: list[str]) -> Optional[float]:
    vals = []
    for f in fixtures:
        if f in arm.ordered:
            probs, idx = arm.ordered[f]
            try:
                vals.append(ranked_probability_score(probs, idx))
            except ValueError:
                continue
    if not vals:
        return None
    return sum(vals) / len(vals)
