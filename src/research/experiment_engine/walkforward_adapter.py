"""Walk-Forward Engine compatibility adapter.

Does NOT modify the frozen WalkForwardEngine.

Documents the integration boundary for Batch 5:
- Batch 4 produces ExperimentResult with single temporal split
- Batch 5 will connect: Candidate → Experiment → WalkForwardEngine → FDR → Quarantine

This adapter demonstrates compatibility by providing the interface
that Batch 5 will use to bridge the experiment engine into the
production walk-forward infrastructure.

INTEGRATION BOUNDARY (Batch 5):
1. ExperimentRunner produces evidence for a single split
2. WalkForwardAdapter will run multiple temporal splits
3. Each split result feeds into FDRController
4. FDR-corrected results feed into QuarantineTracker

For Batch 4: Only the adapter interface is defined.
The actual integration requires verifying that the frozen
WalkForwardEngine can safely consume experiment outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.research.experiment_engine.config import ExperimentConfig
from src.research.experiment_engine.result import ExperimentResult, StatisticalEvidence


@dataclass(frozen=True)
class WalkForwardFold:
    """A single fold in walk-forward evaluation.

    Represents one train/test split in a rolling window scheme.
    """

    fold_index: int
    training_start: int
    training_end: int
    evaluation_start: int
    evaluation_end: int
    result: Optional[ExperimentResult] = None


@dataclass(frozen=True)
class WalkForwardResult:
    """Aggregated walk-forward evaluation result.

    Collects results across multiple temporal folds.
    Ready for FDRController consumption in Batch 5.
    """

    folds: tuple[WalkForwardFold, ...] = ()
    aggregate_evidence: Optional[StatisticalEvidence] = None
    aggregate_p_value: Optional[float] = None
    total_predictions: int = 0
    completed_folds: int = 0
    failed_folds: int = 0

    @property
    def p_value_for_fdr(self) -> Optional[float]:
        """The p-value ready for FDRController.correct().

        This is the interface point for Batch 5 FDR integration.
        """
        return self.aggregate_p_value


class WalkForwardAdapter:
    """Adapter for walk-forward evaluation using the experiment engine.

    BATCH 5 INTEGRATION PLAN:
    - This adapter will orchestrate multiple ExperimentRunner.run() calls
    - Each call uses a different temporal fold
    - Results are aggregated and p-values fed to FDRController
    - FDR-corrected results determine quarantine eligibility

    For Batch 4: Demonstrates the interface and validates compatibility.
    Does NOT modify the frozen WalkForwardEngine in src/backtest/engine.py.
    """

    def __init__(
        self,
        train_window_days: int = 365,
        test_window_days: int = 90,
        step_days: int = 90,
    ) -> None:
        """Initialize walk-forward adapter.

        Args:
            train_window_days: Training window size in days.
            test_window_days: Test window size in days.
            step_days: Step size between folds in days.
        """
        self._train_window = train_window_days * 86400
        self._test_window = test_window_days * 86400
        self._step = step_days * 86400

    def generate_folds(
        self, data_start: int, data_end: int
    ) -> list[WalkForwardFold]:
        """Generate walk-forward fold specifications.

        Creates chronological folds suitable for experiment execution.

        Args:
            data_start: Earliest data timestamp.
            data_end: Latest data timestamp.

        Returns:
            List of WalkForwardFold specifications.
        """
        folds = []
        fold_idx = 0
        train_start = data_start

        while train_start + self._train_window + self._test_window <= data_end:
            train_end = train_start + self._train_window
            eval_start = train_end
            eval_end = eval_start + self._test_window

            folds.append(WalkForwardFold(
                fold_index=fold_idx,
                training_start=train_start,
                training_end=train_end,
                evaluation_start=eval_start,
                evaluation_end=eval_end,
            ))

            fold_idx += 1
            train_start += self._step

        return folds

    def create_fold_config(
        self, base_config: ExperimentConfig, fold: WalkForwardFold
    ) -> ExperimentConfig:
        """Create an experiment config for a specific fold.

        Adjusts the training and evaluation periods while
        preserving all other configuration.

        Args:
            base_config: The base experiment configuration.
            fold: The fold specification.

        Returns:
            New ExperimentConfig with adjusted periods.
        """
        # Create new config with fold-specific periods
        # Using dataclass replace pattern (frozen dataclass workaround)
        from dataclasses import replace
        # ExperimentConfig is frozen, so we reconstruct
        return ExperimentConfig(
            experiment_version=base_config.experiment_version,
            hypothesis=base_config.hypothesis,
            market_type=base_config.market_type,
            dataset_version=base_config.dataset_version,
            model_type=base_config.model_type,
            model_parameters=base_config.model_parameters,
            training_start=fold.training_start,
            training_end=fold.training_end,
            evaluation_start=fold.evaluation_start,
            evaluation_end=fold.evaluation_end,
            minimum_observations=base_config.minimum_observations,
            odds_mode=base_config.odds_mode,
            thresholds=base_config.thresholds,
            random_seed=base_config.random_seed,
            features=base_config.features,
        )
