"""Paper Eligibility — determines which strategies may generate paper trades.

Only strategies satisfying governance requirements may enter paper trading.
Eligibility is evaluated deterministically — AI CANNOT approve paper trading.

Criteria (all configurable, all documented):
- Walk-forward validation passed
- Minimum folds completed
- Minimum sample size
- Positive fold ratio threshold
- FDR result passed
- Calibration quality threshold
- Statistical evidence threshold
- Expected value threshold
- Maximum drawdown limit
- Season stability (optional)

AI confidence is NEVER used as statistical evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class EligibilityCriteria:
    """Configurable criteria for paper trading eligibility.

    All thresholds are documented. None means "not required".
    Conservative defaults are used.
    """
    require_walkforward_pass: bool = True
    min_folds: int = 5
    min_sample_size: int = 50
    min_positive_fold_ratio: float = 0.6
    require_fdr_pass: bool = True
    max_brier_score: Optional[float] = 0.30
    min_evidence_classification: str = "PROMISING"  # PROMISING or STRONG_SIGNAL
    min_expected_value: Optional[float] = 0.0  # Must have positive EV
    max_drawdown: Optional[float] = None  # None = no drawdown limit
    require_season_stability: bool = False
    min_seasons: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "require_walkforward_pass": self.require_walkforward_pass,
            "min_folds": self.min_folds,
            "min_sample_size": self.min_sample_size,
            "min_positive_fold_ratio": self.min_positive_fold_ratio,
            "require_fdr_pass": self.require_fdr_pass,
            "max_brier_score": self.max_brier_score,
            "min_evidence_classification": self.min_evidence_classification,
            "min_expected_value": self.min_expected_value,
            "max_drawdown": self.max_drawdown,
            "require_season_stability": self.require_season_stability,
            "min_seasons": self.min_seasons,
        }


@dataclass(frozen=True)
class EligibilityResult:
    """Result of eligibility evaluation."""
    eligible: bool
    strategy_id: str
    reasons: tuple[str, ...] = ()  # Why rejected (empty if eligible)
    warnings: tuple[str, ...] = ()  # Non-blocking warnings
    criteria_used: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "strategy_id": self.strategy_id,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
        }


class PaperEligibility:
    """Evaluates whether a strategy is eligible for paper trading.

    Uses ONLY deterministic governance results.
    AI confidence is NEVER a criterion.
    """

    def __init__(self, criteria: Optional[EligibilityCriteria] = None) -> None:
        self._criteria = criteria or EligibilityCriteria()

    @property
    def criteria(self) -> EligibilityCriteria:
        return self._criteria

    def evaluate(
        self,
        strategy_id: str,
        walkforward_passed: bool = False,
        folds_completed: int = 0,
        sample_size: int = 0,
        positive_fold_ratio: float = 0.0,
        fdr_passed: bool = False,
        brier_score: Optional[float] = None,
        evidence_classification: str = "",
        expected_value: Optional[float] = None,
        max_drawdown: Optional[float] = None,
        seasons_tested: int = 0,
        season_stable: bool = False,
    ) -> EligibilityResult:
        """Evaluate paper trading eligibility.

        Args:
            strategy_id: Strategy identifier.
            walkforward_passed: Whether walk-forward validation passed.
            folds_completed: Number of walk-forward folds completed.
            sample_size: Total sample size across folds.
            positive_fold_ratio: Fraction of positive folds.
            fdr_passed: Whether FDR correction passed.
            brier_score: Brier score (lower = better calibration).
            evidence_classification: Statistical evidence level.
            expected_value: Average expected value.
            max_drawdown: Maximum observed drawdown.
            seasons_tested: Number of seasons tested.
            season_stable: Whether strategy shows season stability.

        Returns:
            EligibilityResult (eligible=True/False with reasons).
        """
        reasons: list[str] = []
        warnings: list[str] = []
        c = self._criteria

        # Walk-forward
        if c.require_walkforward_pass and not walkforward_passed:
            reasons.append("Walk-forward validation not passed")

        # Folds
        if folds_completed < c.min_folds:
            reasons.append(f"Insufficient folds: {folds_completed} < {c.min_folds}")

        # Sample size
        if sample_size < c.min_sample_size:
            reasons.append(f"Insufficient sample size: {sample_size} < {c.min_sample_size}")

        # Positive fold ratio
        if positive_fold_ratio < c.min_positive_fold_ratio:
            reasons.append(
                f"Low positive fold ratio: {positive_fold_ratio:.2f} < {c.min_positive_fold_ratio}"
            )

        # FDR
        if c.require_fdr_pass and not fdr_passed:
            reasons.append("FDR correction not passed")

        # Calibration (Brier score)
        if c.max_brier_score is not None and brier_score is not None:
            if brier_score > c.max_brier_score:
                reasons.append(f"Poor calibration: Brier {brier_score:.3f} > {c.max_brier_score}")

        # Evidence classification
        _EVIDENCE_ORDER = {
            "INSUFFICIENT_DATA": 0,
            "NEGATIVE": 1,
            "NEUTRAL": 2,
            "PROMISING": 3,
            "STRONG_SIGNAL": 4,
        }
        min_level = _EVIDENCE_ORDER.get(c.min_evidence_classification, 3)
        actual_level = _EVIDENCE_ORDER.get(evidence_classification, 0)
        if actual_level < min_level:
            reasons.append(
                f"Insufficient evidence: {evidence_classification} < {c.min_evidence_classification}"
            )

        # Expected value
        if c.min_expected_value is not None and expected_value is not None:
            if expected_value < c.min_expected_value:
                reasons.append(f"Negative EV: {expected_value:.4f} < {c.min_expected_value}")

        # Drawdown
        if c.max_drawdown is not None and max_drawdown is not None:
            if max_drawdown > c.max_drawdown:
                warnings.append(f"High drawdown: {max_drawdown:.2f} > {c.max_drawdown}")

        # Season stability
        if c.require_season_stability:
            if seasons_tested < c.min_seasons:
                reasons.append(f"Insufficient seasons: {seasons_tested} < {c.min_seasons}")
            elif not season_stable:
                reasons.append("Season stability not achieved")

        eligible = len(reasons) == 0

        return EligibilityResult(
            eligible=eligible,
            strategy_id=strategy_id,
            reasons=tuple(reasons),
            warnings=tuple(warnings),
            criteria_used=c.to_dict() if not eligible else None,
        )
