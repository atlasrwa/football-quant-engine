"""Research Governance Classifier.

Implements the research state machine:
    DISCOVERED → PROMISING → WALK_FORWARD_VALIDATED → FDR_VALIDATED
    → QUARANTINE_ELIGIBLE → QUARANTINED → REJECTED

Transitions are based on configurable governance criteria.
These are research standards, NOT universal truths.

Do NOT optimize governance thresholds against the same
test data they are used to judge.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from src.research.fdr.adapter import FDRHypothesisResult, FDRStatus
from src.research.walkforward.result import WalkForwardResult, WalkForwardStatus


class GovernanceState(Enum):
    """Research governance lifecycle states.

    Each state represents a level of validation evidence.
    Only QUARANTINE_ELIGIBLE candidates may enter quarantine.
    """

    DISCOVERED = "DISCOVERED"                     # Candidate generated
    PROMISING = "PROMISING"                       # Single experiment shows signal
    WALK_FORWARD_VALIDATED = "WALK_FORWARD_VALIDATED"  # Multi-fold OOS evidence
    FDR_VALIDATED = "FDR_VALIDATED"               # Survives multiple-testing
    QUARANTINE_ELIGIBLE = "QUARANTINE_ELIGIBLE"   # Meets all criteria for quarantine
    QUARANTINED = "QUARANTINED"                   # Currently in paper-trading quarantine
    REJECTED = "REJECTED"                         # Failed validation


@dataclass(frozen=True)
class GovernanceCriteria:
    """Configurable governance criteria.

    These define the minimum evidence required for each transition.
    Different research standards can use different criteria.

    IMPORTANT: Do NOT hard-code these as universal truths.
    """

    # Walk-forward criteria
    minimum_folds: int = 5
    minimum_positive_fold_ratio: float = 0.6
    minimum_sample_size: int = 50
    maximum_p_value: float = 0.05

    # FDR criteria
    maximum_fdr_q_value: float = 0.10  # More lenient than raw alpha

    # Effect size and calibration
    minimum_effect_size: float = 0.01
    minimum_calibration_quality: float = 0.30  # max acceptable Brier score

    # Economic criteria (when odds available)
    minimum_mean_ev: Optional[float] = None  # None = no economic gate
    maximum_allowed_drawdown: Optional[float] = None  # None = no drawdown gate

    # Stability
    maximum_roi_std: Optional[float] = None  # None = no stability gate
    maximum_consecutive_negative: int = 5

    def to_dict(self) -> dict[str, Any]:
        return {
            "minimum_folds": self.minimum_folds,
            "minimum_positive_fold_ratio": self.minimum_positive_fold_ratio,
            "minimum_sample_size": self.minimum_sample_size,
            "maximum_p_value": self.maximum_p_value,
            "maximum_fdr_q_value": self.maximum_fdr_q_value,
            "minimum_effect_size": self.minimum_effect_size,
            "minimum_calibration_quality": self.minimum_calibration_quality,
            "minimum_mean_ev": self.minimum_mean_ev,
            "maximum_allowed_drawdown": self.maximum_allowed_drawdown,
            "maximum_roi_std": self.maximum_roi_std,
            "maximum_consecutive_negative": self.maximum_consecutive_negative,
        }

    @property
    def content_hash(self) -> str:
        """Deterministic identity for these criteria."""
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class GovernanceDecision:
    """Result of governance classification.

    Documents the state transition and reasoning.
    """

    hypothesis_id: str
    candidate_hash: str
    previous_state: GovernanceState
    new_state: GovernanceState
    reasons: tuple[str, ...] = ()
    evidence_summary: dict[str, Any] = field(default_factory=dict)
    criteria_used: Optional[GovernanceCriteria] = None

    @property
    def is_promoted(self) -> bool:
        """Whether the decision advances the candidate."""
        state_order = list(GovernanceState)
        return state_order.index(self.new_state) > state_order.index(self.previous_state)

    @property
    def is_rejected(self) -> bool:
        """Whether the candidate was rejected."""
        return self.new_state == GovernanceState.REJECTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "candidate_hash": self.candidate_hash,
            "previous_state": self.previous_state.value,
            "new_state": self.new_state.value,
            "reasons": list(self.reasons),
            "evidence_summary": self.evidence_summary,
        }


class GovernanceClassifier:
    """Classifies research candidates through governance states.

    Applies configurable criteria to determine state transitions.
    Separates statistical evidence from economic evidence.

    IMPORTANT:
    - Statistical significance != profitability
    - FDR pass != production readiness
    - Quarantine eligible != validated profitable
    """

    def __init__(self, criteria: Optional[GovernanceCriteria] = None) -> None:
        """Initialize with governance criteria.

        Args:
            criteria: Configurable criteria (uses defaults if None).
        """
        self._criteria = criteria or GovernanceCriteria()

    @property
    def criteria(self) -> GovernanceCriteria:
        return self._criteria

    def classify_walk_forward(
        self,
        wf_result: WalkForwardResult,
        previous_state: GovernanceState = GovernanceState.PROMISING,
    ) -> GovernanceDecision:
        """Classify based on walk-forward validation evidence.

        Evaluates:
        - Sufficient folds
        - Positive fold ratio
        - Sample size
        - P-value
        - Effect size
        - Calibration quality
        - Stability

        Args:
            wf_result: Walk-forward result to evaluate.
            previous_state: Current governance state.

        Returns:
            GovernanceDecision with new state and reasoning.
        """
        reasons: list[str] = []
        c = self._criteria

        # Check completion
        if wf_result.status != WalkForwardStatus.COMPLETED:
            reasons.append(f"Walk-forward not completed: {wf_result.status.value}")
            return GovernanceDecision(
                hypothesis_id=wf_result.hypothesis_hash,
                candidate_hash=wf_result.candidate_hash,
                previous_state=previous_state,
                new_state=GovernanceState.REJECTED,
                reasons=tuple(reasons),
                evidence_summary=self._build_wf_summary(wf_result),
                criteria_used=c,
            )

        # Check minimum folds
        if wf_result.successful_folds < c.minimum_folds:
            reasons.append(
                f"Insufficient folds: {wf_result.successful_folds} < {c.minimum_folds}"
            )
            return GovernanceDecision(
                hypothesis_id=wf_result.hypothesis_hash,
                candidate_hash=wf_result.candidate_hash,
                previous_state=previous_state,
                new_state=GovernanceState.REJECTED,
                reasons=tuple(reasons),
                evidence_summary=self._build_wf_summary(wf_result),
                criteria_used=c,
            )

        # Check sample size
        if wf_result.total_predictions < c.minimum_sample_size:
            reasons.append(
                f"Insufficient predictions: {wf_result.total_predictions} < {c.minimum_sample_size}"
            )
            return GovernanceDecision(
                hypothesis_id=wf_result.hypothesis_hash,
                candidate_hash=wf_result.candidate_hash,
                previous_state=previous_state,
                new_state=GovernanceState.REJECTED,
                reasons=tuple(reasons),
                evidence_summary=self._build_wf_summary(wf_result),
                criteria_used=c,
            )

        # Check positive fold ratio
        pfr = wf_result.stability.positive_fold_ratio
        if pfr < c.minimum_positive_fold_ratio:
            reasons.append(
                f"Low positive fold ratio: {pfr:.2f} < {c.minimum_positive_fold_ratio}"
            )
            return GovernanceDecision(
                hypothesis_id=wf_result.hypothesis_hash,
                candidate_hash=wf_result.candidate_hash,
                previous_state=previous_state,
                new_state=GovernanceState.REJECTED,
                reasons=tuple(reasons),
                evidence_summary=self._build_wf_summary(wf_result),
                criteria_used=c,
            )

        # Check combined p-value
        p_value = wf_result.p_value_for_fdr
        if p_value is not None and p_value > c.maximum_p_value:
            reasons.append(f"P-value too high: {p_value:.4f} > {c.maximum_p_value}")
            return GovernanceDecision(
                hypothesis_id=wf_result.hypothesis_hash,
                candidate_hash=wf_result.candidate_hash,
                previous_state=previous_state,
                new_state=GovernanceState.REJECTED,
                reasons=tuple(reasons),
                evidence_summary=self._build_wf_summary(wf_result),
                criteria_used=c,
            )

        # Check effect size
        effect_size = wf_result.aggregate_evidence.mean_effect_size
        if effect_size is not None and effect_size < c.minimum_effect_size:
            reasons.append(
                f"Effect size too small: {effect_size:.4f} < {c.minimum_effect_size}"
            )
            return GovernanceDecision(
                hypothesis_id=wf_result.hypothesis_hash,
                candidate_hash=wf_result.candidate_hash,
                previous_state=previous_state,
                new_state=GovernanceState.REJECTED,
                reasons=tuple(reasons),
                evidence_summary=self._build_wf_summary(wf_result),
                criteria_used=c,
            )

        # Check calibration (Brier score — lower is better)
        brier = wf_result.aggregate_brier_score
        if brier is not None and brier > c.minimum_calibration_quality:
            reasons.append(
                f"Poor calibration (Brier): {brier:.4f} > {c.minimum_calibration_quality}"
            )
            return GovernanceDecision(
                hypothesis_id=wf_result.hypothesis_hash,
                candidate_hash=wf_result.candidate_hash,
                previous_state=previous_state,
                new_state=GovernanceState.REJECTED,
                reasons=tuple(reasons),
                evidence_summary=self._build_wf_summary(wf_result),
                criteria_used=c,
            )

        # Check stability (consecutive negatives)
        if wf_result.stability.max_consecutive_negative > c.maximum_consecutive_negative:
            reasons.append(
                f"Too many consecutive negative folds: "
                f"{wf_result.stability.max_consecutive_negative} > {c.maximum_consecutive_negative}"
            )
            return GovernanceDecision(
                hypothesis_id=wf_result.hypothesis_hash,
                candidate_hash=wf_result.candidate_hash,
                previous_state=previous_state,
                new_state=GovernanceState.REJECTED,
                reasons=tuple(reasons),
                evidence_summary=self._build_wf_summary(wf_result),
                criteria_used=c,
            )

        # Check optional economic criteria
        if c.maximum_allowed_drawdown is not None and wf_result.max_drawdown is not None:
            if wf_result.max_drawdown > c.maximum_allowed_drawdown:
                reasons.append(
                    f"Excessive drawdown: {wf_result.max_drawdown:.2f} > {c.maximum_allowed_drawdown}"
                )
                return GovernanceDecision(
                    hypothesis_id=wf_result.hypothesis_hash,
                    candidate_hash=wf_result.candidate_hash,
                    previous_state=previous_state,
                    new_state=GovernanceState.REJECTED,
                    reasons=tuple(reasons),
                    evidence_summary=self._build_wf_summary(wf_result),
                    criteria_used=c,
                )

        if c.maximum_roi_std is not None and wf_result.stability.roi_std is not None:
            if wf_result.stability.roi_std > c.maximum_roi_std:
                reasons.append(
                    f"Unstable ROI (std): {wf_result.stability.roi_std:.2f} > {c.maximum_roi_std}"
                )
                return GovernanceDecision(
                    hypothesis_id=wf_result.hypothesis_hash,
                    candidate_hash=wf_result.candidate_hash,
                    previous_state=previous_state,
                    new_state=GovernanceState.REJECTED,
                    reasons=tuple(reasons),
                    evidence_summary=self._build_wf_summary(wf_result),
                    criteria_used=c,
                )

        # All criteria passed
        reasons.append("Walk-forward validation criteria met")
        reasons.append(f"Folds: {wf_result.successful_folds}, PFR: {pfr:.2f}")
        if p_value is not None:
            reasons.append(f"Combined p-value: {p_value:.6f}")

        return GovernanceDecision(
            hypothesis_id=wf_result.hypothesis_hash,
            candidate_hash=wf_result.candidate_hash,
            previous_state=previous_state,
            new_state=GovernanceState.WALK_FORWARD_VALIDATED,
            reasons=tuple(reasons),
            evidence_summary=self._build_wf_summary(wf_result),
            criteria_used=c,
        )

    def classify_fdr(
        self,
        fdr_result: FDRHypothesisResult,
        previous_state: GovernanceState = GovernanceState.WALK_FORWARD_VALIDATED,
    ) -> GovernanceDecision:
        """Classify based on FDR correction result.

        Args:
            fdr_result: FDR result for this hypothesis.
            previous_state: Current governance state.

        Returns:
            GovernanceDecision with new state.
        """
        reasons: list[str] = []

        if fdr_result.fdr_status == FDRStatus.INSUFFICIENT_DATA:
            reasons.append("Insufficient data for FDR evaluation")
            return GovernanceDecision(
                hypothesis_id=fdr_result.hypothesis_id,
                candidate_hash=fdr_result.candidate_hash,
                previous_state=previous_state,
                new_state=GovernanceState.REJECTED,
                reasons=tuple(reasons),
                criteria_used=self._criteria,
            )

        if fdr_result.fdr_status == FDRStatus.INVALID_P_VALUE:
            reasons.append(f"Invalid p-value: {fdr_result.raw_p_value}")
            return GovernanceDecision(
                hypothesis_id=fdr_result.hypothesis_id,
                candidate_hash=fdr_result.candidate_hash,
                previous_state=previous_state,
                new_state=GovernanceState.REJECTED,
                reasons=tuple(reasons),
                criteria_used=self._criteria,
            )

        if fdr_result.fdr_status == FDRStatus.FDR_FAIL:
            reasons.append(
                f"Failed FDR correction (rank {fdr_result.rank}, "
                f"threshold {fdr_result.adjusted_threshold:.6f}, "
                f"p={fdr_result.raw_p_value:.6f})"
            )
            return GovernanceDecision(
                hypothesis_id=fdr_result.hypothesis_id,
                candidate_hash=fdr_result.candidate_hash,
                previous_state=previous_state,
                new_state=GovernanceState.REJECTED,
                reasons=tuple(reasons),
                criteria_used=self._criteria,
            )

        # FDR_PASS
        reasons.append(
            f"Passed FDR correction (rank {fdr_result.rank}/{fdr_result.number_of_tests}, "
            f"p={fdr_result.raw_p_value:.6f}, "
            f"threshold={fdr_result.adjusted_threshold:.6f})"
        )
        return GovernanceDecision(
            hypothesis_id=fdr_result.hypothesis_id,
            candidate_hash=fdr_result.candidate_hash,
            previous_state=previous_state,
            new_state=GovernanceState.FDR_VALIDATED,
            reasons=tuple(reasons),
            criteria_used=self._criteria,
        )

    def determine_quarantine_eligibility(
        self,
        wf_result: WalkForwardResult,
        fdr_result: FDRHypothesisResult,
        previous_state: GovernanceState = GovernanceState.FDR_VALIDATED,
    ) -> GovernanceDecision:
        """Final determination of quarantine eligibility.

        Requires both walk-forward validation AND FDR validation.
        This is the terminal research state before quarantine.

        Args:
            wf_result: Walk-forward evidence.
            fdr_result: FDR correction result.
            previous_state: Current state (should be FDR_VALIDATED).

        Returns:
            GovernanceDecision: QUARANTINE_ELIGIBLE or REJECTED.
        """
        reasons: list[str] = []

        # Must be FDR validated
        if not fdr_result.is_significant:
            reasons.append("Not FDR validated")
            return GovernanceDecision(
                hypothesis_id=fdr_result.hypothesis_id,
                candidate_hash=fdr_result.candidate_hash,
                previous_state=previous_state,
                new_state=GovernanceState.REJECTED,
                reasons=tuple(reasons),
                criteria_used=self._criteria,
            )

        # Must have valid walk-forward
        if not wf_result.is_valid:
            reasons.append("Walk-forward validation invalid")
            return GovernanceDecision(
                hypothesis_id=fdr_result.hypothesis_id,
                candidate_hash=fdr_result.candidate_hash,
                previous_state=previous_state,
                new_state=GovernanceState.REJECTED,
                reasons=tuple(reasons),
                criteria_used=self._criteria,
            )

        # Optional: check minimum EV
        if self._criteria.minimum_mean_ev is not None:
            if wf_result.mean_fold_ev is not None:
                if wf_result.mean_fold_ev < self._criteria.minimum_mean_ev:
                    reasons.append(
                        f"Mean EV below threshold: {wf_result.mean_fold_ev:.4f} "
                        f"< {self._criteria.minimum_mean_ev}"
                    )
                    return GovernanceDecision(
                        hypothesis_id=fdr_result.hypothesis_id,
                        candidate_hash=fdr_result.candidate_hash,
                        previous_state=previous_state,
                        new_state=GovernanceState.REJECTED,
                        reasons=tuple(reasons),
                        criteria_used=self._criteria,
                    )

        # All eligibility criteria met
        reasons.append("Walk-forward validated + FDR validated")
        reasons.append(f"Combined p-value: {wf_result.p_value_for_fdr}")
        reasons.append(f"FDR rank: {fdr_result.rank}/{fdr_result.number_of_tests}")
        reasons.append(f"Positive fold ratio: {wf_result.positive_fold_ratio:.2f}")

        return GovernanceDecision(
            hypothesis_id=fdr_result.hypothesis_id,
            candidate_hash=fdr_result.candidate_hash,
            previous_state=previous_state,
            new_state=GovernanceState.QUARANTINE_ELIGIBLE,
            reasons=tuple(reasons),
            evidence_summary={
                "combined_p_value": wf_result.p_value_for_fdr,
                "fdr_rank": fdr_result.rank,
                "fdr_total": fdr_result.number_of_tests,
                "positive_fold_ratio": wf_result.positive_fold_ratio,
                "successful_folds": wf_result.successful_folds,
                "total_predictions": wf_result.total_predictions,
            },
            criteria_used=self._criteria,
        )

    def _build_wf_summary(self, wf_result: WalkForwardResult) -> dict[str, Any]:
        """Build evidence summary from walk-forward result."""
        return {
            "status": wf_result.status.value,
            "successful_folds": wf_result.successful_folds,
            "total_predictions": wf_result.total_predictions,
            "positive_fold_ratio": wf_result.stability.positive_fold_ratio,
            "combined_p_value": wf_result.p_value_for_fdr,
            "mean_effect_size": wf_result.aggregate_evidence.mean_effect_size,
            "aggregate_brier": wf_result.aggregate_brier_score,
            "median_roi": wf_result.median_fold_roi,
            "max_drawdown": wf_result.max_drawdown,
        }
