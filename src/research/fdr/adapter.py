"""FDR Adapter — bridges research layer to frozen FDRController.

Does NOT recreate FDR logic.
Adapts research walk-forward results to the existing
Benjamini-Hochberg interface in src/engine/fdr.py.

Flow:
    WalkForwardResult[] → extract p-values → FDRController.correct()
    → map back to hypothesis identifiers → FDRHypothesisResult[]
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from src.engine.analysis.fdr import FDRController, FDRResult
from src.research.fdr.family import ResearchFamily
from src.research.walkforward.result import WalkForwardResult


class FDRStatus(Enum):
    """FDR correction status for a hypothesis."""

    FDR_PASS = "FDR_PASS"                # Survives multiple-testing correction
    FDR_FAIL = "FDR_FAIL"                # Does not survive correction
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"  # No valid p-value available
    INVALID_P_VALUE = "INVALID_P_VALUE"  # P-value out of range


@dataclass(frozen=True)
class FDRHypothesisResult:
    """FDR correction result for a single hypothesis.

    IMPORTANT: FDR_PASS does NOT mean profitable.
    It only means the hypothesis survives the configured
    multiple-testing threshold.
    """

    hypothesis_id: str
    candidate_hash: str
    raw_p_value: Optional[float]
    adjusted_threshold: Optional[float]
    rank: Optional[int]
    family_id: str
    number_of_tests: int
    alpha: float
    fdr_status: FDRStatus
    fdr_result: Optional[FDRResult] = None  # Original FDR engine result

    @property
    def is_significant(self) -> bool:
        """Whether this hypothesis passed FDR correction."""
        return self.fdr_status == FDRStatus.FDR_PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "candidate_hash": self.candidate_hash,
            "raw_p_value": self.raw_p_value,
            "adjusted_threshold": self.adjusted_threshold,
            "rank": self.rank,
            "family_id": self.family_id,
            "number_of_tests": self.number_of_tests,
            "alpha": self.alpha,
            "fdr_status": self.fdr_status.value,
        }


@dataclass(frozen=True)
class ResearchFDRResult:
    """Complete FDR correction result for a research family.

    Contains the family context and all hypothesis-level results.
    """

    family: ResearchFamily
    alpha: float
    total_hypotheses: int
    valid_hypotheses: int
    rejected_count: int  # Number that passed FDR
    accepted_count: int  # Number that failed FDR (null not rejected)
    insufficient_data_count: int
    invalid_p_value_count: int
    hypothesis_results: tuple[FDRHypothesisResult, ...] = ()

    @property
    def content_hash(self) -> str:
        """Deterministic hash of FDR results."""
        canonical = json.dumps(
            {
                "family_id": self.family.family_id,
                "alpha": self.alpha,
                "total_hypotheses": self.total_hypotheses,
                "rejected_count": self.rejected_count,
                "hypothesis_ids": sorted(
                    h.hypothesis_id for h in self.hypothesis_results
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    @property
    def fdr_pass_rate(self) -> float:
        """Fraction of valid hypotheses that passed FDR."""
        if self.valid_hypotheses == 0:
            return 0.0
        return self.rejected_count / self.valid_hypotheses

    def get_passing_hypotheses(self) -> list[FDRHypothesisResult]:
        """Get hypotheses that passed FDR correction."""
        return [h for h in self.hypothesis_results if h.is_significant]

    def get_failing_hypotheses(self) -> list[FDRHypothesisResult]:
        """Get hypotheses that failed FDR correction."""
        return [
            h for h in self.hypothesis_results
            if h.fdr_status == FDRStatus.FDR_FAIL
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family.to_dict(),
            "alpha": self.alpha,
            "total_hypotheses": self.total_hypotheses,
            "valid_hypotheses": self.valid_hypotheses,
            "rejected_count": self.rejected_count,
            "accepted_count": self.accepted_count,
            "insufficient_data_count": self.insufficient_data_count,
            "invalid_p_value_count": self.invalid_p_value_count,
            "fdr_pass_rate": self.fdr_pass_rate,
            "content_hash": self.content_hash,
            "hypothesis_results": [h.to_dict() for h in self.hypothesis_results],
        }


class FDRAdapter:
    """Adapts research walk-forward results to the frozen FDRController.

    Does NOT modify or recreate FDR logic.
    Validates inputs, extracts p-values, calls FDRController.correct(),
    and maps results back to research hypothesis identifiers.
    """

    def __init__(self, alpha: float = 0.05) -> None:
        """Initialize with target FDR level.

        Args:
            alpha: Target false discovery rate (passed to FDRController).
        """
        if not 0 < alpha < 1:
            raise ValueError(f"alpha must be in (0, 1), got {alpha}")
        self._controller = FDRController(alpha=alpha)
        self._alpha = alpha

    @property
    def alpha(self) -> float:
        return self._alpha

    def correct(
        self,
        walkforward_results: list[WalkForwardResult],
        family: ResearchFamily,
    ) -> ResearchFDRResult:
        """Apply FDR correction to a family of walk-forward results.

        Args:
            walkforward_results: Walk-forward results for each hypothesis.
            family: The research family these hypotheses belong to.

        Returns:
            ResearchFDRResult with per-hypothesis FDR decisions.
        """
        if not walkforward_results:
            return ResearchFDRResult(
                family=family,
                alpha=self._alpha,
                total_hypotheses=0,
                valid_hypotheses=0,
                rejected_count=0,
                accepted_count=0,
                insufficient_data_count=0,
                invalid_p_value_count=0,
            )

        # Extract and validate p-values
        hypothesis_meta: list[dict[str, Any]] = []
        valid_indices: list[int] = []
        valid_p_values: list[float] = []

        for i, wf_result in enumerate(walkforward_results):
            p_val = wf_result.p_value_for_fdr
            meta = {
                "index": i,
                "hypothesis_id": wf_result.hypothesis_hash,
                "candidate_hash": wf_result.candidate_hash,
                "p_value": p_val,
            }
            hypothesis_meta.append(meta)

            if p_val is None:
                meta["status"] = FDRStatus.INSUFFICIENT_DATA
            elif not (0 < p_val <= 1):
                # p=0 is technically invalid for Fisher's method downstream
                # p must be in (0, 1]
                if p_val == 0:
                    # Treat extremely small p-values as valid (use machine epsilon)
                    valid_indices.append(i)
                    valid_p_values.append(1e-300)
                    meta["status"] = None
                else:
                    meta["status"] = FDRStatus.INVALID_P_VALUE
            else:
                valid_indices.append(i)
                valid_p_values.append(p_val)
                meta["status"] = None

        # Apply FDR correction via frozen controller
        fdr_results: list[FDRResult] = []
        if valid_p_values:
            fdr_results = self._controller.correct(valid_p_values)

        # Map FDR results back to hypothesis identifiers
        hypothesis_results: list[FDRHypothesisResult] = []
        fdr_result_idx = 0
        rejected_count = 0
        accepted_count = 0
        insufficient_count = 0
        invalid_count = 0

        for i, meta in enumerate(hypothesis_meta):
            if meta["status"] == FDRStatus.INSUFFICIENT_DATA:
                insufficient_count += 1
                hypothesis_results.append(FDRHypothesisResult(
                    hypothesis_id=meta["hypothesis_id"],
                    candidate_hash=meta["candidate_hash"],
                    raw_p_value=None,
                    adjusted_threshold=None,
                    rank=None,
                    family_id=family.family_id,
                    number_of_tests=len(valid_p_values),
                    alpha=self._alpha,
                    fdr_status=FDRStatus.INSUFFICIENT_DATA,
                ))
            elif meta["status"] == FDRStatus.INVALID_P_VALUE:
                invalid_count += 1
                hypothesis_results.append(FDRHypothesisResult(
                    hypothesis_id=meta["hypothesis_id"],
                    candidate_hash=meta["candidate_hash"],
                    raw_p_value=meta["p_value"],
                    adjusted_threshold=None,
                    rank=None,
                    family_id=family.family_id,
                    number_of_tests=len(valid_p_values),
                    alpha=self._alpha,
                    fdr_status=FDRStatus.INVALID_P_VALUE,
                ))
            else:
                # Has valid p-value — find corresponding FDR result
                # valid_indices maps back to hypothesis_meta indices
                fdr_idx = valid_indices.index(i)
                fdr_res = fdr_results[fdr_idx]

                if fdr_res.rejected:
                    status = FDRStatus.FDR_PASS
                    rejected_count += 1
                else:
                    status = FDRStatus.FDR_FAIL
                    accepted_count += 1

                hypothesis_results.append(FDRHypothesisResult(
                    hypothesis_id=meta["hypothesis_id"],
                    candidate_hash=meta["candidate_hash"],
                    raw_p_value=valid_p_values[fdr_idx],
                    adjusted_threshold=fdr_res.adjusted_threshold,
                    rank=fdr_res.rank,
                    family_id=family.family_id,
                    number_of_tests=fdr_res.total_hypotheses,
                    alpha=self._alpha,
                    fdr_status=status,
                    fdr_result=fdr_res,
                ))

        return ResearchFDRResult(
            family=family,
            alpha=self._alpha,
            total_hypotheses=len(walkforward_results),
            valid_hypotheses=len(valid_p_values),
            rejected_count=rejected_count,
            accepted_count=accepted_count,
            insufficient_data_count=insufficient_count,
            invalid_p_value_count=invalid_count,
            hypothesis_results=tuple(hypothesis_results),
        )
