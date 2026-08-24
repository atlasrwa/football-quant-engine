"""BacktestRun and ValidationRun domain types.

These capture the execution context and results of backtests and
validation runs, linking them to their provenance chain.

BacktestRun = "I ran this strategy against this data with these parameters and got these results"
ValidationRun = "I applied statistical validation to this backtest's results and got this verdict"
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any


class BacktestStatus(Enum):
    """Lifecycle status of a backtest run."""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class BacktestRun:
    """Immutable record of a single backtest execution.

    Links a strategy version to a specific dataset/feature/model version
    and captures the aggregate results. Individual bet records are stored
    separately (as XBetRecord tuples in XBacktestResult).

    Attributes:
        run_id: Unique identifier for this backtest run.
        model_version_id: The ModelVersion that was evaluated.
        strategy_id: Strategy identifier (from StrategyIdentity).
        strategy_version: Strategy version number.
        dataset_id: Dataset used.
        feature_version_id: Feature configuration used.
        status: RUNNING, COMPLETED, or FAILED.
        total_bets: Number of bets generated.
        net_roi_pct: Net return on investment percentage.
        win_rate: Win rate (0-1).
        max_drawdown_pct: Maximum drawdown as percentage.
        avg_model_edge_pct: Average model edge percentage.
        total_profit_loss: Net P&L in stake units.
        n_folds: Number of walk-forward folds.
        content_hash: Deterministic hash of the run configuration.
        started_at: ISO 8601 timestamp when run started.
        completed_at: ISO 8601 timestamp when run completed (or None).
    """

    run_id: str
    model_version_id: str
    strategy_id: str
    strategy_version: int
    dataset_id: str
    feature_version_id: str
    status: BacktestStatus
    total_bets: int
    net_roi_pct: float
    win_rate: float
    max_drawdown_pct: float
    avg_model_edge_pct: float
    total_profit_loss: float
    n_folds: int
    content_hash: str
    started_at: str
    completed_at: str | None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "run_id": self.run_id,
            "model_version_id": self.model_version_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "dataset_id": self.dataset_id,
            "feature_version_id": self.feature_version_id,
            "status": self.status.value,
            "total_bets": self.total_bets,
            "net_roi_pct": self.net_roi_pct,
            "win_rate": self.win_rate,
            "max_drawdown_pct": self.max_drawdown_pct,
            "avg_model_edge_pct": self.avg_model_edge_pct,
            "total_profit_loss": self.total_profit_loss,
            "n_folds": self.n_folds,
            "content_hash": self.content_hash,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @staticmethod
    def compute_content_hash(
        model_version_id: str,
        dataset_id: str,
    ) -> str:
        """Compute deterministic run hash from model + dataset.

        Same model on same dataset should produce the same hash,
        enabling deduplication of redundant runs.

        Returns:
            SHA-256 hex digest.
        """
        canonical = json.dumps({
            "model_version_id": model_version_id,
            "dataset_id": dataset_id,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


class ValidationStatus(Enum):
    """Outcome of a validation run."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True, slots=True)
class ValidationRun:
    """Immutable record of a statistical validation execution.

    Captures the full validation context: which backtest was validated,
    what criteria were applied, and what the verdict was.

    Attributes:
        validation_id: Unique identifier.
        backtest_run_id: The BacktestRun that was validated.
        strategy_id: Strategy identifier.
        strategy_version: Strategy version.
        status: PASSED, FAILED, or INSUFFICIENT_DATA.
        p_value: Statistical significance (1-tailed t-test).
        roi_pct: Observed ROI percentage.
        sample_size: Number of settled bets evaluated.
        effect_size: Cohen's d effect size.
        confidence_interval_lower: Lower bound of mean profit CI.
        confidence_interval_upper: Upper bound of mean profit CI.
        min_sample_required: Minimum sample size criterion.
        min_roi_required: Minimum ROI criterion.
        max_p_value: Maximum p-value criterion.
        fdr_submission_count: Number of hypotheses tested (for BH correction).
        fdr_adjusted_threshold: BH-adjusted significance threshold.
        reason: Human-readable explanation of verdict.
        validated_at: ISO 8601 timestamp.
    """

    validation_id: str
    backtest_run_id: str
    strategy_id: str
    strategy_version: int
    status: ValidationStatus
    p_value: float
    roi_pct: float
    sample_size: int
    effect_size: float
    confidence_interval_lower: float
    confidence_interval_upper: float
    min_sample_required: int
    min_roi_required: float
    max_p_value: float
    fdr_submission_count: int
    fdr_adjusted_threshold: float | None
    reason: str
    validated_at: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "validation_id": self.validation_id,
            "backtest_run_id": self.backtest_run_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "status": self.status.value,
            "p_value": self.p_value,
            "roi_pct": self.roi_pct,
            "sample_size": self.sample_size,
            "effect_size": self.effect_size,
            "confidence_interval_lower": self.confidence_interval_lower,
            "confidence_interval_upper": self.confidence_interval_upper,
            "min_sample_required": self.min_sample_required,
            "min_roi_required": self.min_roi_required,
            "max_p_value": self.max_p_value,
            "fdr_submission_count": self.fdr_submission_count,
            "fdr_adjusted_threshold": self.fdr_adjusted_threshold,
            "reason": self.reason,
            "validated_at": self.validated_at,
        }

    @property
    def passed(self) -> bool:
        """Whether this validation resulted in a PASS verdict."""
        return self.status == ValidationStatus.PASSED
