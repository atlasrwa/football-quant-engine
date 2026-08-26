"""Walk-Forward Orchestrator — runs experiments across multiple folds.

The orchestrator:
1. Generates fold specifications from config
2. For each fold: creates a fresh model, runs ExperimentRunner
3. Collects fold results
4. Aggregates into WalkForwardResult

CRITICAL:
- Model is REFITTED for each fold (no shared state)
- Training data is strictly before test data
- Each fold produces independent statistical evidence
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Callable, Optional, Type

from src.research.experiment_engine.config import ExperimentConfig, OddsMode
from src.research.experiment_engine.dataset import ResearchDataset
from src.research.experiment_engine.hypothesis import ExperimentHypothesis
from src.research.experiment_engine.result import ExperimentResult, ExperimentResultStatus
from src.research.experiment_engine.runner import ExperimentRunner
from src.research.probability import (
    HistoricalFrequencyModel,
    LogisticRegressionModel,
    PoissonModel,
    ProbabilityModel,
)
from src.research.walkforward.config import WalkForwardConfig
from src.research.walkforward.folds import FoldGenerator, FoldSpec
from src.research.walkforward.result import (
    FoldResult,
    FoldStatus,
    WalkForwardResult,
    WalkForwardStatus,
    aggregate_fold_results,
)

logger = logging.getLogger(__name__)


# Model factory type: creates a fresh model instance for each fold
ModelFactory = Callable[[], ProbabilityModel]


def _default_model_factory(model_type: str, model_parameters: dict[str, Any]) -> ModelFactory:
    """Create a model factory from type name and parameters.

    Returns a callable that creates a new model instance each time.
    This ensures no state leaks between folds.
    """
    def factory() -> ProbabilityModel:
        if model_type == "historical_frequency":
            return HistoricalFrequencyModel(**model_parameters)
        elif model_type == "logistic_regression":
            return LogisticRegressionModel(**model_parameters)
        elif model_type == "poisson":
            return PoissonModel(**model_parameters)
        else:
            # Default to historical frequency
            return HistoricalFrequencyModel()
    return factory


class WalkForwardOrchestrator:
    """Orchestrates multi-fold walk-forward validation.

    For each hypothesis:
    1. Generates chronological folds
    2. Runs ExperimentRunner on each fold with a fresh model
    3. Aggregates results

    The orchestrator does NOT:
    - Modify the dataset
    - Share model state between folds
    - Use test data for any training/selection
    - Apply FDR (that's a separate layer)
    """

    def __init__(
        self,
        wf_config: WalkForwardConfig,
        runner: Optional[ExperimentRunner] = None,
    ) -> None:
        """Initialize orchestrator.

        Args:
            wf_config: Walk-forward configuration.
            runner: ExperimentRunner instance (creates default if None).
        """
        self._wf_config = wf_config
        self._runner = runner or ExperimentRunner()
        self._fold_generator = FoldGenerator(wf_config)

    @property
    def config(self) -> WalkForwardConfig:
        return self._wf_config

    def run(
        self,
        hypothesis: ExperimentHypothesis,
        dataset: ResearchDataset,
        model_factory: ModelFactory,
        experiment_config_base: ExperimentConfig,
    ) -> WalkForwardResult:
        """Run walk-forward validation for a hypothesis.

        Args:
            hypothesis: The hypothesis to evaluate.
            dataset: Research dataset.
            model_factory: Callable that creates a fresh model per fold.
            experiment_config_base: Base experiment config (periods will be overridden).

        Returns:
            WalkForwardResult with aggregated evidence.
        """
        # Determine data bounds
        match_dicts = dataset.match_dicts
        if not match_dicts:
            return WalkForwardResult(
                experiment_id=experiment_config_base.experiment_id,
                candidate_hash=hypothesis.candidate_hash,
                hypothesis_hash=hypothesis.content_hash,
                market_type=experiment_config_base.market_type,
                status=WalkForwardStatus.INSUFFICIENT_DATA,
                walkforward_config_hash=self._wf_config.content_hash,
            )

        timestamps = sorted(d.get("date_unix", 0) for d in match_dicts)
        data_start = timestamps[0]
        data_end = timestamps[-1] + 1  # exclusive upper bound

        # Generate fold specifications
        fold_specs = self._fold_generator.generate(data_start, data_end)

        if not fold_specs:
            return WalkForwardResult(
                experiment_id=experiment_config_base.experiment_id,
                candidate_hash=hypothesis.candidate_hash,
                hypothesis_hash=hypothesis.content_hash,
                market_type=experiment_config_base.market_type,
                status=WalkForwardStatus.INSUFFICIENT_DATA,
                walkforward_config_hash=self._wf_config.content_hash,
            )

        # Execute each fold
        fold_results: list[FoldResult] = []
        for fold_spec in fold_specs:
            fold_result = self._execute_fold(
                fold_spec=fold_spec,
                hypothesis=hypothesis,
                dataset=dataset,
                model_factory=model_factory,
                base_config=experiment_config_base,
            )
            fold_results.append(fold_result)

        # Aggregate results
        return aggregate_fold_results(
            folds=fold_results,
            experiment_id=experiment_config_base.experiment_id,
            candidate_hash=hypothesis.candidate_hash,
            hypothesis_hash=hypothesis.content_hash,
            market_type=experiment_config_base.market_type,
            walkforward_config_hash=self._wf_config.content_hash,
            minimum_folds=self._wf_config.minimum_folds,
        )

    def _execute_fold(
        self,
        fold_spec: FoldSpec,
        hypothesis: ExperimentHypothesis,
        dataset: ResearchDataset,
        model_factory: ModelFactory,
        base_config: ExperimentConfig,
    ) -> FoldResult:
        """Execute a single walk-forward fold.

        Creates a fresh model, configures the experiment for this fold's
        temporal boundaries, and runs ExperimentRunner.
        """
        # Count observations in each segment
        match_dicts = dataset.match_dicts
        train_obs = sum(
            1 for d in match_dicts
            if fold_spec.train_start <= d.get("date_unix", 0) < fold_spec.train_end
        )
        test_obs = sum(
            1 for d in match_dicts
            if fold_spec.test_start <= d.get("date_unix", 0) < fold_spec.test_end
        )
        val_obs = 0
        if fold_spec.has_validation:
            val_obs = sum(
                1 for d in match_dicts
                if fold_spec.validation_start <= d.get("date_unix", 0) < fold_spec.validation_end
            )

        # Check minimum observations
        if train_obs < self._wf_config.minimum_training_observations:
            return FoldResult(
                fold_spec=fold_spec,
                status=FoldStatus.INSUFFICIENT_TRAINING_DATA,
                training_observations=train_obs,
                test_observations=test_obs,
                validation_observations=val_obs,
            )

        if test_obs < self._wf_config.minimum_test_observations:
            return FoldResult(
                fold_spec=fold_spec,
                status=FoldStatus.INSUFFICIENT_TEST_DATA,
                training_observations=train_obs,
                test_observations=test_obs,
                validation_observations=val_obs,
            )

        # Create a FRESH model for this fold (no state leakage)
        try:
            model = model_factory()
        except Exception as e:
            logger.warning("Model creation failed for fold %d: %s", fold_spec.fold_index, e)
            return FoldResult(
                fold_spec=fold_spec,
                status=FoldStatus.MODEL_FAILURE,
                training_observations=train_obs,
                test_observations=test_obs,
                validation_observations=val_obs,
            )

        # Create fold-specific experiment config
        fold_config = ExperimentConfig(
            experiment_version=base_config.experiment_version,
            hypothesis=hypothesis,
            market_type=base_config.market_type,
            dataset_version=base_config.dataset_version,
            model_type=base_config.model_type,
            model_parameters=base_config.model_parameters,
            training_start=fold_spec.train_start,
            training_end=fold_spec.train_end,
            evaluation_start=fold_spec.test_start,
            evaluation_end=fold_spec.test_end,
            minimum_observations=base_config.minimum_observations,
            odds_mode=base_config.odds_mode,
            thresholds=base_config.thresholds,
            random_seed=base_config.random_seed,
            features=base_config.features,
        )

        # Run the experiment
        try:
            result = self._runner.run(fold_config, dataset, model)
        except Exception as e:
            logger.warning("Experiment failed for fold %d: %s", fold_spec.fold_index, e)
            return FoldResult(
                fold_spec=fold_spec,
                status=FoldStatus.MODEL_FAILURE,
                training_observations=train_obs,
                test_observations=test_obs,
                validation_observations=val_obs,
            )

        # Map ExperimentResult status to FoldStatus
        if result.status == ExperimentResultStatus.COMPLETED:
            fold_status = FoldStatus.COMPLETED
        elif result.status == ExperimentResultStatus.INSUFFICIENT_DATA:
            fold_status = FoldStatus.INSUFFICIENT_TEST_DATA
        elif result.status == ExperimentResultStatus.MODEL_FAILURE:
            fold_status = FoldStatus.MODEL_FAILURE
        elif result.status == ExperimentResultStatus.TEMPORAL_VIOLATION:
            fold_status = FoldStatus.TEMPORAL_VIOLATION
        else:
            fold_status = FoldStatus.NO_PREDICTIONS

        # Get model identity
        model_id = ""
        if hasattr(model, "model_identity") and model.model_identity is not None:
            model_id = str(model.model_identity)
        elif hasattr(model, "name"):
            model_id = model.name

        return FoldResult(
            fold_spec=fold_spec,
            status=fold_status,
            experiment_result=result if fold_status == FoldStatus.COMPLETED else None,
            model_identity=model_id,
            training_observations=train_obs,
            test_observations=test_obs,
            validation_observations=val_obs,
        )
