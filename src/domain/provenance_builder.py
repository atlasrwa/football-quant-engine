"""Provenance chain builder.

Constructs the full reproducibility chain from raw inputs:
    Strategy → Dataset → Features → Model → Backtest → Validation

This is the orchestration layer that creates properly-linked provenance
objects from the existing engine's inputs and outputs.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List

from src.domain.backtest_run import BacktestRun, BacktestStatus, ValidationRun, ValidationStatus
from src.domain.provenance import DatasetVersion, FeatureVersion, ModelVersion
from src.engine.analysis.strategy_identity import StrategyIdentity
from src.models.config import StrategyConfig
from src.models.match import Match


class ProvenanceBuilder:
    """Builds provenance chain objects from existing engine types.

    Usage:
        builder = ProvenanceBuilder()
        dataset_v = builder.create_dataset_version(matches, source="footystats")
        feature_v = builder.create_feature_version(dataset_v, config)
        model_v = builder.create_model_version(strategy_identity, feature_v, backtest_config)
        backtest_run = builder.create_backtest_run(model_v, dataset_v, feature_v, results)
    """

    @staticmethod
    def create_dataset_version(
        matches: List[Match],
        source: str,
        league_id: int | None = None,
        season: str | None = None,
    ) -> DatasetVersion:
        """Create a DatasetVersion from a list of Match objects.

        Args:
            matches: The matches comprising this dataset.
            source: Data source identifier.
            league_id: League ID (inferred from first match if not provided).
            season: Season string (inferred from first match if not provided).

        Returns:
            A DatasetVersion with content hash computed from match IDs.
        """
        if not matches:
            raise ValueError("Cannot create DatasetVersion from empty match list")

        sorted_matches = sorted(matches, key=lambda m: m.date_unix)
        match_ids = [m.id for m in sorted_matches]
        content_hash = DatasetVersion.compute_content_hash(match_ids)

        # Infer metadata from matches if not provided
        resolved_league = league_id or sorted_matches[0].league_id
        resolved_season = season or sorted_matches[0].season

        now = datetime.now(timezone.utc).isoformat()

        return DatasetVersion(
            dataset_id=str(uuid.uuid4()),
            source=source,
            league_id=resolved_league,
            season=resolved_season,
            n_matches=len(matches),
            date_range_start=sorted_matches[0].date_unix,
            date_range_end=sorted_matches[-1].date_unix,
            content_hash=content_hash,
            created_at=now,
        )

    @staticmethod
    def create_feature_version(
        dataset_version: DatasetVersion,
        config: StrategyConfig,
        xmetric_coefficients: dict[str, float] | None = None,
    ) -> FeatureVersion:
        """Create a FeatureVersion from dataset + config.

        Args:
            dataset_version: The dataset features will be computed from.
            config: Strategy configuration with feature parameters.
            xmetric_coefficients: Optional xMetric engine coefficients.

        Returns:
            A FeatureVersion capturing the feature computation parameters.
        """
        content_hash = FeatureVersion.compute_content_hash(
            dataset_id=dataset_version.dataset_id,
            xg_rolling_window=config.xg_rolling_window,
            form_rolling_window=config.form_rolling_window,
            referee_min_matches=config.referee_min_matches,
            xmetric_coefficients=xmetric_coefficients,
        )

        now = datetime.now(timezone.utc).isoformat()

        return FeatureVersion(
            feature_version_id=str(uuid.uuid4()),
            dataset_id=dataset_version.dataset_id,
            xg_rolling_window=config.xg_rolling_window,
            form_rolling_window=config.form_rolling_window,
            referee_min_matches=config.referee_min_matches,
            xmetric_coefficients=xmetric_coefficients,
            content_hash=content_hash,
            created_at=now,
        )

    @staticmethod
    def create_model_version(
        strategy_identity: StrategyIdentity,
        feature_version: FeatureVersion,
        train_window: int = 200,
        test_window: int = 50,
        step_size: int = 50,
        min_odds: float = 1.50,
        max_odds: float = 5.00,
    ) -> ModelVersion:
        """Create a ModelVersion from strategy + feature config + backtest params.

        Args:
            strategy_identity: The strategy being evaluated.
            feature_version: Feature computation config.
            train_window: Walk-forward training window.
            test_window: Walk-forward test window.
            step_size: Walk-forward step size.
            min_odds: Minimum odds filter.
            max_odds: Maximum odds filter.

        Returns:
            A ModelVersion capturing the full evaluation context.
        """
        content_hash = ModelVersion.compute_content_hash(
            strategy_content_hash=strategy_identity.content_hash,
            feature_version_id=feature_version.feature_version_id,
            train_window=train_window,
            test_window=test_window,
            step_size=step_size,
            min_odds=min_odds,
            max_odds=max_odds,
        )

        now = datetime.now(timezone.utc).isoformat()

        return ModelVersion(
            model_version_id=str(uuid.uuid4()),
            strategy_id=strategy_identity.strategy_id,
            strategy_version=strategy_identity.strategy_version,
            strategy_content_hash=strategy_identity.content_hash,
            feature_version_id=feature_version.feature_version_id,
            train_window=train_window,
            test_window=test_window,
            step_size=step_size,
            min_odds=min_odds,
            max_odds=max_odds,
            content_hash=content_hash,
            created_at=now,
        )

    @staticmethod
    def create_backtest_run(
        model_version: ModelVersion,
        dataset_version: DatasetVersion,
        feature_version: FeatureVersion,
        total_bets: int,
        net_roi_pct: float,
        win_rate: float,
        max_drawdown_pct: float,
        avg_model_edge_pct: float,
        total_profit_loss: float,
        n_folds: int,
    ) -> BacktestRun:
        """Create a BacktestRun from model version and results.

        Args:
            model_version: The model configuration used.
            dataset_version: The dataset used.
            feature_version: The feature configuration used.
            total_bets: Number of bets generated.
            net_roi_pct: Net ROI percentage.
            win_rate: Win rate (0-1).
            max_drawdown_pct: Maximum drawdown percentage.
            avg_model_edge_pct: Average model edge.
            total_profit_loss: Net P&L.
            n_folds: Number of walk-forward folds.

        Returns:
            A completed BacktestRun.
        """
        content_hash = BacktestRun.compute_content_hash(
            model_version_id=model_version.model_version_id,
            dataset_id=dataset_version.dataset_id,
        )

        now = datetime.now(timezone.utc).isoformat()

        return BacktestRun(
            run_id=str(uuid.uuid4()),
            model_version_id=model_version.model_version_id,
            strategy_id=model_version.strategy_id,
            strategy_version=model_version.strategy_version,
            dataset_id=dataset_version.dataset_id,
            feature_version_id=feature_version.feature_version_id,
            status=BacktestStatus.COMPLETED,
            total_bets=total_bets,
            net_roi_pct=net_roi_pct,
            win_rate=win_rate,
            max_drawdown_pct=max_drawdown_pct,
            avg_model_edge_pct=avg_model_edge_pct,
            total_profit_loss=total_profit_loss,
            n_folds=n_folds,
            content_hash=content_hash,
            started_at=now,
            completed_at=now,
        )

    @staticmethod
    def create_validation_run(
        backtest_run: BacktestRun,
        p_value: float,
        roi_pct: float,
        sample_size: int,
        effect_size: float,
        ci_lower: float,
        ci_upper: float,
        min_sample_required: int = 250,
        min_roi_required: float = 3.0,
        max_p_value: float = 0.05,
        fdr_submission_count: int = 1,
        fdr_adjusted_threshold: float | None = None,
        reason: str = "",
    ) -> ValidationRun:
        """Create a ValidationRun from backtest results and validation output.

        Args:
            backtest_run: The backtest being validated.
            p_value: Statistical p-value.
            roi_pct: Observed ROI.
            sample_size: Number of settled bets.
            effect_size: Cohen's d.
            ci_lower: Confidence interval lower bound.
            ci_upper: Confidence interval upper bound.
            min_sample_required: Minimum sample criterion.
            min_roi_required: Minimum ROI criterion.
            max_p_value: Maximum p-value criterion.
            fdr_submission_count: Number of hypotheses tested.
            fdr_adjusted_threshold: BH-adjusted threshold (None if not applied).
            reason: Human-readable explanation.

        Returns:
            A ValidationRun with appropriate status.
        """
        # Determine validation status
        effective_threshold = fdr_adjusted_threshold or max_p_value

        if sample_size < min_sample_required:
            status = ValidationStatus.INSUFFICIENT_DATA
            if not reason:
                reason = f"Insufficient data: {sample_size} < {min_sample_required} required"
        elif roi_pct < min_roi_required:
            status = ValidationStatus.FAILED
            if not reason:
                reason = f"ROI {roi_pct:.2f}% below minimum {min_roi_required}%"
        elif p_value > effective_threshold:
            status = ValidationStatus.FAILED
            if not reason:
                reason = f"p-value {p_value:.4f} > threshold {effective_threshold:.4f}"
        else:
            status = ValidationStatus.PASSED
            if not reason:
                reason = f"All gates passed: N={sample_size}, ROI={roi_pct:.2f}%, p={p_value:.4f}"

        now = datetime.now(timezone.utc).isoformat()

        return ValidationRun(
            validation_id=str(uuid.uuid4()),
            backtest_run_id=backtest_run.run_id,
            strategy_id=backtest_run.strategy_id,
            strategy_version=backtest_run.strategy_version,
            status=status,
            p_value=p_value,
            roi_pct=roi_pct,
            sample_size=sample_size,
            effect_size=effect_size,
            confidence_interval_lower=ci_lower,
            confidence_interval_upper=ci_upper,
            min_sample_required=min_sample_required,
            min_roi_required=min_roi_required,
            max_p_value=max_p_value,
            fdr_submission_count=fdr_submission_count,
            fdr_adjusted_threshold=fdr_adjusted_threshold,
            reason=reason,
            validated_at=now,
        )
