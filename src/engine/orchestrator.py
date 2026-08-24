"""Backtest orchestrator — wires provenance into the execution pipeline.

Wraps XMetricBacktester with full provenance chain construction:
    Strategy → StrategyIdentity → DatasetVersion → FeatureVersion → ModelVersion
    → XMetricBacktester.run() → BacktestRun + PredictionEvents

This is the integration layer that connects the domain model to the
existing execution engine without modifying either.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

import pandas as pd

from src.domain.backtest_run import BacktestRun
from src.domain.provenance import DatasetVersion, FeatureVersion, ModelVersion
from src.domain.provenance_builder import ProvenanceBuilder
from src.engine.backtest import (
    StrategyIdentityInfo,
    XBacktestConfig,
    XBacktestResult,
    XMetricBacktester,
)
from src.engine.evaluator import Strategy, StrategyEvaluator
from src.engine.strategy_identity import StrategyIdentity, StrategyRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OrchestratedBacktestResult:
    """Full backtest result with provenance chain attached.

    Contains both the raw XBacktestResult (unchanged behavior) and
    the domain provenance objects that link this run to its inputs.
    """

    backtest_result: XBacktestResult
    backtest_run: BacktestRun
    dataset_version: DatasetVersion
    feature_version: FeatureVersion
    model_version: ModelVersion
    strategy_identities: tuple[StrategyIdentity, ...]

    def summary(self) -> dict:
        """Return a summary including provenance IDs."""
        base = self.backtest_result.summary()
        base["dataset_id"] = self.dataset_version.dataset_id
        base["feature_version_id"] = self.feature_version.feature_version_id
        base["model_version_id"] = self.model_version.model_version_id
        base["backtest_run_id"] = self.backtest_run.run_id
        base["n_prediction_events"] = len(self.backtest_result.prediction_events)
        return base


class BacktestOrchestrator:
    """Orchestrates backtesting with full provenance chain.

    Usage:
        orchestrator = BacktestOrchestrator()
        result = orchestrator.run(df, strategies)
        # result.backtest_result — same as XMetricBacktester.run() output
        # result.backtest_run — domain BacktestRun record
        # result.dataset_version — provenance: what data was used
        # result.model_version — provenance: what model config was used
    """

    def __init__(
        self,
        config: XBacktestConfig | None = None,
        evaluator: StrategyEvaluator | None = None,
        registry: StrategyRegistry | None = None,
        source: str = "unknown",
    ) -> None:
        """Initialize orchestrator.

        Args:
            config: Backtest configuration.
            evaluator: Strategy evaluator (shared with backtester).
            registry: Strategy registry for identity management.
            source: Data source identifier for provenance (e.g., "footystats").
        """
        self.config = config or XBacktestConfig()
        self.evaluator = evaluator or StrategyEvaluator()
        self.registry = registry or StrategyRegistry()
        self.source = source

    def run(
        self,
        df: pd.DataFrame,
        strategies: List[Strategy],
        outcome_col: str = "actual_total",
        line_col: str = "market_line",
        league_id: int | None = None,
        season: str | None = None,
        xg_rolling_window: int = 5,
        form_rolling_window: int = 6,
        referee_min_matches: int = 5,
        xmetric_coefficients: dict[str, float] | None = None,
    ) -> OrchestratedBacktestResult:
        """Execute backtest with full provenance chain.

        Args:
            df: DataFrame with canonical schema (match_id, date_unix, etc.).
            strategies: Strategies to evaluate.
            outcome_col: Column for settlement outcome.
            line_col: Column for market line.
            league_id: League ID (inferred from data if not provided).
            season: Season string (inferred from data if not provided).
            xg_rolling_window: Feature parameter for provenance.
            form_rolling_window: Feature parameter for provenance.
            referee_min_matches: Feature parameter for provenance.
            xmetric_coefficients: Optional xMetric coefficients for provenance.

        Returns:
            OrchestratedBacktestResult with full provenance chain.
        """
        # Step 1: Build provenance chain
        dataset_version = self._create_dataset_version(
            df, league_id=league_id, season=season
        )
        feature_version = self._create_feature_version(
            dataset_version,
            xg_rolling_window=xg_rolling_window,
            form_rolling_window=form_rolling_window,
            referee_min_matches=referee_min_matches,
            xmetric_coefficients=xmetric_coefficients,
        )

        # Step 2: Register strategies and build identity map
        identities: List[StrategyIdentity] = []
        identity_map: dict[str, StrategyIdentityInfo] = {}

        for strategy in strategies:
            identity = self.registry.register(strategy)
            identities.append(identity)

            model_version = self._create_model_version(identity, feature_version)

            identity_map[strategy.name] = StrategyIdentityInfo(
                strategy_id=identity.strategy_id,
                strategy_version=identity.strategy_version,
                content_hash=identity.content_hash,
                model_version_id=model_version.model_version_id,
            )

        # Use the model_version from the last (or only) strategy for the run record.
        # For multi-strategy backtests, the model_version represents the evaluation context.
        # Each strategy's individual model_version_id is embedded in its PredictionEvents.
        primary_model_version = self._create_model_version(identities[0], feature_version)

        # Step 3: Run backtest with identity info wired in
        backtester = XMetricBacktester(
            config=self.config,
            evaluator=self.evaluator,
            strategy_identities=identity_map,
        )

        backtest_result = backtester.run(
            df, strategies, outcome_col=outcome_col, line_col=line_col
        )

        # Step 4: Create BacktestRun domain record
        backtest_run = ProvenanceBuilder.create_backtest_run(
            model_version=primary_model_version,
            dataset_version=dataset_version,
            feature_version=feature_version,
            total_bets=backtest_result.total_bets,
            net_roi_pct=backtest_result.net_roi_pct,
            win_rate=backtest_result.win_rate,
            max_drawdown_pct=backtest_result.max_drawdown_pct,
            avg_model_edge_pct=backtest_result.avg_model_edge_pct,
            total_profit_loss=backtest_result.total_profit_loss,
            n_folds=len(backtest_result.folds),
        )

        logger.info(
            "Orchestrated backtest complete: run_id=%s, %d bets, %d predictions, ROI=%.2f%%",
            backtest_run.run_id[:8],
            backtest_result.total_bets,
            len(backtest_result.prediction_events),
            backtest_result.net_roi_pct,
        )

        return OrchestratedBacktestResult(
            backtest_result=backtest_result,
            backtest_run=backtest_run,
            dataset_version=dataset_version,
            feature_version=feature_version,
            model_version=primary_model_version,
            strategy_identities=tuple(identities),
        )

    def _create_dataset_version(
        self,
        df: pd.DataFrame,
        league_id: int | None = None,
        season: str | None = None,
    ) -> DatasetVersion:
        """Create DatasetVersion from DataFrame metadata."""
        import uuid
        from datetime import datetime, timezone

        # Extract match IDs for content hash
        if "match_id" in df.columns:
            match_ids = df["match_id"].dropna().astype(int).tolist()
        else:
            # Fallback: use row indices
            match_ids = list(range(len(df)))

        content_hash = DatasetVersion.compute_content_hash(match_ids)

        # Infer metadata
        resolved_league = league_id
        if resolved_league is None and "league_id" in df.columns:
            resolved_league = int(df["league_id"].iloc[0]) if len(df) > 0 else 0
        resolved_league = resolved_league or 0

        resolved_season = season
        if resolved_season is None and "season" in df.columns:
            resolved_season = str(df["season"].iloc[0]) if len(df) > 0 else "unknown"
        resolved_season = resolved_season or "unknown"

        date_col = df["date_unix"] if "date_unix" in df.columns else pd.Series([0])
        date_range_start = int(date_col.min()) if len(date_col) > 0 else 0
        date_range_end = int(date_col.max()) if len(date_col) > 0 else 0

        now = datetime.now(timezone.utc).isoformat()

        return DatasetVersion(
            dataset_id=str(uuid.uuid4()),
            source=self.source,
            league_id=resolved_league,
            season=resolved_season,
            n_matches=len(df),
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            content_hash=content_hash,
            created_at=now,
        )

    def _create_feature_version(
        self,
        dataset_version: DatasetVersion,
        xg_rolling_window: int,
        form_rolling_window: int,
        referee_min_matches: int,
        xmetric_coefficients: dict[str, float] | None = None,
    ) -> FeatureVersion:
        """Create FeatureVersion from dataset and feature params."""
        import uuid
        from datetime import datetime, timezone

        content_hash = FeatureVersion.compute_content_hash(
            dataset_id=dataset_version.dataset_id,
            xg_rolling_window=xg_rolling_window,
            form_rolling_window=form_rolling_window,
            referee_min_matches=referee_min_matches,
            xmetric_coefficients=xmetric_coefficients,
        )

        now = datetime.now(timezone.utc).isoformat()

        return FeatureVersion(
            feature_version_id=str(uuid.uuid4()),
            dataset_id=dataset_version.dataset_id,
            xg_rolling_window=xg_rolling_window,
            form_rolling_window=form_rolling_window,
            referee_min_matches=referee_min_matches,
            xmetric_coefficients=xmetric_coefficients,
            content_hash=content_hash,
            created_at=now,
        )

    def _create_model_version(
        self,
        identity: StrategyIdentity,
        feature_version: FeatureVersion,
    ) -> ModelVersion:
        """Create ModelVersion from strategy identity and feature version."""
        import uuid
        from datetime import datetime, timezone

        content_hash = ModelVersion.compute_content_hash(
            strategy_content_hash=identity.content_hash,
            feature_version_id=feature_version.feature_version_id,
            train_window=self.config.train_window,
            test_window=self.config.test_window,
            step_size=self.config.step_size,
            min_odds=self.config.min_odds,
            max_odds=self.config.max_odds,
        )

        now = datetime.now(timezone.utc).isoformat()

        return ModelVersion(
            model_version_id=str(uuid.uuid4()),
            strategy_id=identity.strategy_id,
            strategy_version=identity.strategy_version,
            strategy_content_hash=identity.content_hash,
            feature_version_id=feature_version.feature_version_id,
            train_window=self.config.train_window,
            test_window=self.config.test_window,
            step_size=self.config.step_size,
            min_odds=self.config.min_odds,
            max_odds=self.config.max_odds,
            content_hash=content_hash,
            created_at=now,
        )
