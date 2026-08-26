"""Experiment results, metrics, and classification.

Separates:
- Predictive metrics (calibration, accuracy)
- Economic metrics (EV, ROI)
- Statistical evidence (significance, effect size)

A model can be well calibrated without being profitable.
A strategy can have high ROI while being poorly calibrated.
These are distinct dimensions that must not be collapsed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


# ═══════════════════════════════════════════════════════════════
# RESULT STATUS
# ═══════════════════════════════════════════════════════════════


class ExperimentResultStatus(Enum):
    """Experiment outcome status."""

    COMPLETED = "COMPLETED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    MODEL_FAILURE = "MODEL_FAILURE"
    MODEL_NOT_COMPATIBLE = "MODEL_NOT_COMPATIBLE"
    MISSING_TARGET = "MISSING_TARGET"
    MISSING_ODDS = "MISSING_ODDS"
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"
    TEMPORAL_VIOLATION = "TEMPORAL_VIOLATION"


class EvidenceClassification(Enum):
    """Research classification of experiment evidence.

    These are RESEARCH LABELS, not production approval.
    They do NOT mean 'validated', 'production-ready', or 'profitable'.
    """

    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    PROMISING = "PROMISING"
    STRONG_SIGNAL = "STRONG_SIGNAL"


class EVStatus(Enum):
    """Status of EV calculation."""

    VALID = "VALID"
    MISSING_ODDS = "MISSING_ODDS"
    INVALID_ODDS = "INVALID_ODDS"


# ═══════════════════════════════════════════════════════════════
# INDIVIDUAL PREDICTION RECORD
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ExperimentPrediction:
    """A single prediction within an experiment.

    Preserves the complete prediction context for audit.
    """

    match_id: int
    prediction_timestamp: int
    information_timestamp: int
    outcome_timestamp: int
    model_probability: float
    actual_outcome: Optional[str]  # "OVER", "UNDER", "YES", "NO", etc.
    is_hit: Optional[bool]
    market_odds: Optional[float] = None
    fair_odds: Optional[float] = None
    implied_probability: Optional[float] = None
    expected_value: Optional[float] = None
    ev_status: EVStatus = EVStatus.MISSING_ODDS
    direction: str = "OVER"
    conditions_met: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "match_id": self.match_id,
            "prediction_timestamp": self.prediction_timestamp,
            "model_probability": round(self.model_probability, 6),
            "actual_outcome": self.actual_outcome,
            "is_hit": self.is_hit,
            "market_odds": self.market_odds,
            "expected_value": round(self.expected_value, 6) if self.expected_value is not None else None,
            "ev_status": self.ev_status.value,
            "direction": self.direction,
        }


# ═══════════════════════════════════════════════════════════════
# METRICS
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class PredictiveMetrics:
    """Model predictive quality metrics.

    These measure how well the model's probabilities
    correspond to actual outcomes.
    """

    sample_size: int = 0
    hit_rate: Optional[float] = None
    model_probability_mean: Optional[float] = None
    actual_frequency: Optional[float] = None
    brier_score: Optional[float] = None
    log_loss: Optional[float] = None
    ece: Optional[float] = None
    mce: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_size": self.sample_size,
            "hit_rate": self.hit_rate,
            "model_probability_mean": self.model_probability_mean,
            "actual_frequency": self.actual_frequency,
            "brier_score": self.brier_score,
            "log_loss": self.log_loss,
            "ece": self.ece,
            "mce": self.mce,
        }


@dataclass(frozen=True)
class EconomicMetrics:
    """Economic performance metrics.

    Only valid when odds are available.
    MISSING_ODDS is distinct from zero — never fabricate.
    """

    odds_available: bool = False
    mean_ev: Optional[float] = None
    median_ev: Optional[float] = None
    positive_ev_rate: Optional[float] = None
    mean_odds: Optional[float] = None
    roi_pct: Optional[float] = None
    yield_pct: Optional[float] = None
    number_of_bets: int = 0
    total_profit_loss: Optional[float] = None
    max_drawdown: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "odds_available": self.odds_available,
            "mean_ev": self.mean_ev,
            "median_ev": self.median_ev,
            "positive_ev_rate": self.positive_ev_rate,
            "mean_odds": self.mean_odds,
            "roi_pct": self.roi_pct,
            "yield_pct": self.yield_pct,
            "number_of_bets": self.number_of_bets,
            "total_profit_loss": self.total_profit_loss,
            "max_drawdown": self.max_drawdown,
        }


@dataclass(frozen=True)
class BaselineComparison:
    """Comparison of candidate model against baseline.

    Answers: 'Does this candidate actually add information?'
    Not merely: 'Does this candidate correlate with the outcome?'
    """

    baseline_name: str = ""
    baseline_frequency: Optional[float] = None
    candidate_frequency: Optional[float] = None
    improvement: Optional[float] = None
    baseline_brier: Optional[float] = None
    candidate_brier: Optional[float] = None
    brier_improvement: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_name": self.baseline_name,
            "baseline_frequency": self.baseline_frequency,
            "candidate_frequency": self.candidate_frequency,
            "improvement": self.improvement,
            "baseline_brier": self.baseline_brier,
            "candidate_brier": self.candidate_brier,
            "brier_improvement": self.brier_improvement,
        }


@dataclass(frozen=True)
class StatisticalEvidence:
    """Statistical evidence from the experiment.

    Produces a structure that Batch 5 can feed into FDRController.

    RawExperimentResult → StatisticalEvidence → FDRController (future)
    """

    sample_size: int = 0
    mean_outcome: Optional[float] = None
    baseline_outcome: Optional[float] = None
    difference: Optional[float] = None
    confidence_interval_lower: Optional[float] = None
    confidence_interval_upper: Optional[float] = None
    effect_size: Optional[float] = None
    p_value: Optional[float] = None
    is_significant: bool = False
    significance_level: float = 0.05

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_size": self.sample_size,
            "mean_outcome": self.mean_outcome,
            "baseline_outcome": self.baseline_outcome,
            "difference": self.difference,
            "confidence_interval_lower": self.confidence_interval_lower,
            "confidence_interval_upper": self.confidence_interval_upper,
            "effect_size": self.effect_size,
            "p_value": self.p_value,
            "is_significant": self.is_significant,
            "significance_level": self.significance_level,
        }


@dataclass(frozen=True)
class ObservationCounts:
    """Tracks observation eligibility and exclusions.

    Never silently discards observations.
    """

    total_rows: int = 0
    eligible_rows: int = 0
    missing_rows: int = 0
    invalid_rows: int = 0
    insufficient_history_rows: int = 0
    excluded_odds_filter: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_rows": self.total_rows,
            "eligible_rows": self.eligible_rows,
            "missing_rows": self.missing_rows,
            "invalid_rows": self.invalid_rows,
            "insufficient_history_rows": self.insufficient_history_rows,
            "excluded_odds_filter": self.excluded_odds_filter,
        }


# ═══════════════════════════════════════════════════════════════
# EXPERIMENT RESULT
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ExperimentResult:
    """Complete result of a research experiment.

    Contains all evidence produced by running an experiment.
    Mutable runtime state (created_at) is excluded from identity.

    Attributes:
        experiment_id: Deterministic experiment hash.
        candidate_hash: Source candidate content hash.
        hypothesis_hash: Source hypothesis content hash.
        market_type: Target market.
        dataset_version: Dataset content hash.
        model_identity: Model type + version identifier.
        training_period: (start, end) timestamps.
        evaluation_period: (start, end) timestamps.
        validation_period: Optional (start, end) timestamps.
        observation_counts: Detailed observation tracking.
        predictions: Individual prediction records.
        predictive_metrics: Calibration and accuracy metrics.
        economic_metrics: EV and profitability metrics.
        calibration_metrics: Detailed calibration result (from Batch 2).
        baseline_comparison: Comparison against baseline model.
        statistical_evidence: Significance and effect size.
        classification: Research evidence classification.
        status: Result status.
        warnings: Any warnings generated.
        limitations: Known limitations of this result.
        created_at: ISO timestamp (not in identity hash).
    """

    experiment_id: str
    candidate_hash: str
    hypothesis_hash: str
    market_type: str
    dataset_version: str
    model_identity: str

    training_period: tuple[int, int]
    evaluation_period: tuple[int, int]
    validation_period: Optional[tuple[int, int]] = None

    observation_counts: ObservationCounts = field(default_factory=ObservationCounts)
    predictions: tuple[ExperimentPrediction, ...] = ()

    predictive_metrics: PredictiveMetrics = field(default_factory=PredictiveMetrics)
    economic_metrics: EconomicMetrics = field(default_factory=EconomicMetrics)
    baseline_comparison: BaselineComparison = field(default_factory=BaselineComparison)
    statistical_evidence: StatisticalEvidence = field(default_factory=StatisticalEvidence)

    classification: EvidenceClassification = EvidenceClassification.INSUFFICIENT_DATA
    status: ExperimentResultStatus = ExperimentResultStatus.COMPLETED

    warnings: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def prediction_count(self) -> int:
        return len(self.predictions)

    @property
    def sample_size(self) -> int:
        return self.observation_counts.eligible_rows

    def to_dict(self) -> dict[str, Any]:
        """Full serialization for storage."""
        return {
            "experiment_id": self.experiment_id,
            "candidate_hash": self.candidate_hash,
            "hypothesis_hash": self.hypothesis_hash,
            "market_type": self.market_type,
            "dataset_version": self.dataset_version,
            "model_identity": self.model_identity,
            "training_period": list(self.training_period),
            "evaluation_period": list(self.evaluation_period),
            "validation_period": list(self.validation_period) if self.validation_period else None,
            "observation_counts": self.observation_counts.to_dict(),
            "prediction_count": self.prediction_count,
            "predictive_metrics": self.predictive_metrics.to_dict(),
            "economic_metrics": self.economic_metrics.to_dict(),
            "baseline_comparison": self.baseline_comparison.to_dict(),
            "statistical_evidence": self.statistical_evidence.to_dict(),
            "classification": self.classification.value,
            "status": self.status.value,
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
            "created_at": self.created_at,
        }


# ═══════════════════════════════════════════════════════════════
# EVIDENCE CLASSIFIER
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ClassificationThresholds:
    """Configurable thresholds for evidence classification.

    These are research labels for prioritization, NOT production approval.
    """

    min_sample_for_evaluation: int = 30
    strong_signal_p_value: float = 0.01
    strong_signal_effect_size: float = 0.05
    promising_p_value: float = 0.05
    promising_effect_size: float = 0.02
    negative_p_value: float = 0.05  # significant but wrong direction


class EvidenceClassifier:
    """Classifies experiment evidence into research categories.

    Classification is based on configurable thresholds.
    These are research labels, not production approval.
    """

    def __init__(
        self, thresholds: Optional[ClassificationThresholds] = None
    ) -> None:
        self._thresholds = thresholds or ClassificationThresholds()

    def classify(
        self,
        evidence: StatisticalEvidence,
        predictive_metrics: PredictiveMetrics,
    ) -> EvidenceClassification:
        """Classify experiment evidence.

        Args:
            evidence: Statistical evidence from experiment.
            predictive_metrics: Predictive quality metrics.

        Returns:
            Research classification label.
        """
        t = self._thresholds

        # Insufficient data
        if evidence.sample_size < t.min_sample_for_evaluation:
            return EvidenceClassification.INSUFFICIENT_DATA

        # No p-value available
        if evidence.p_value is None:
            return EvidenceClassification.INSUFFICIENT_DATA

        # Check direction of effect
        if evidence.difference is not None and evidence.difference < 0:
            # Effect is in wrong direction
            if evidence.p_value < t.negative_p_value:
                return EvidenceClassification.NEGATIVE
            return EvidenceClassification.NEUTRAL

        # Strong signal
        if (
            evidence.p_value < t.strong_signal_p_value
            and evidence.effect_size is not None
            and evidence.effect_size >= t.strong_signal_effect_size
        ):
            return EvidenceClassification.STRONG_SIGNAL

        # Promising
        if (
            evidence.p_value < t.promising_p_value
            and evidence.effect_size is not None
            and evidence.effect_size >= t.promising_effect_size
        ):
            return EvidenceClassification.PROMISING

        # Not significant
        return EvidenceClassification.NEUTRAL
