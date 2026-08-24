"""Temporal cross-validation fold splitting for walk-forward backtesting.

Implements expanding and sliding window fold generation that respects
chronological ordering (no future data leakage).
"""

from __future__ import annotations

import logging
from typing import List, NamedTuple, Optional

from src.models.config import StrategyConfig
from src.models.features import MatchFeatures

logger = logging.getLogger(__name__)


class Fold(NamedTuple):
    """A single train/test fold with indices and data."""

    fold_index: int
    train_start: int
    train_end: int  # exclusive
    test_start: int
    test_end: int  # exclusive
    train_data: List[MatchFeatures]
    test_data: List[MatchFeatures]


class TemporalCrossValidator:
    """Generates walk-forward temporal folds for backtesting.

    Walk-forward approach:
    - Training window: fixed-size sliding window of recent matches.
    - Test window: the next N matches after training.
    - Step size: how far to advance between folds.

    This ensures no future data leakage and mimics real-world deployment.
    """

    def __init__(self, config: Optional[StrategyConfig] = None) -> None:
        """Initialize with strategy configuration.

        Args:
            config: Strategy config with train_window, test_window, step_size.
        """
        self._config = config or StrategyConfig()
        self._train_window = self._config.train_window
        self._test_window = self._config.test_window
        self._step_size = self._config.step_size

    @property
    def train_window(self) -> int:
        """Training window size."""
        return self._train_window

    @property
    def test_window(self) -> int:
        """Test window size."""
        return self._test_window

    @property
    def step_size(self) -> int:
        """Step size between folds."""
        return self._step_size

    def generate_folds(self, data: List[MatchFeatures]) -> List[Fold]:
        """Generate walk-forward folds from chronologically sorted data.

        Args:
            data: List of MatchFeatures sorted by date_unix.

        Returns:
            List of Fold objects. Empty if data is too small for even one fold.
        """
        n = len(data)
        min_required = self._train_window + self._test_window

        if n < min_required:
            logger.warning(
                "Insufficient data for walk-forward: have %d, need %d (train=%d + test=%d)",
                n, min_required, self._train_window, self._test_window,
            )
            return []

        folds: List[Fold] = []
        fold_index = 0
        start = 0

        while start + self._train_window + self._test_window <= n:
            train_start = start
            train_end = start + self._train_window
            test_start = train_end
            test_end = min(test_start + self._test_window, n)

            fold = Fold(
                fold_index=fold_index,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                train_data=data[train_start:train_end],
                test_data=data[test_start:test_end],
            )
            folds.append(fold)

            fold_index += 1
            start += self._step_size

        logger.info(
            "Generated %d folds (train=%d, test=%d, step=%d, total_data=%d)",
            len(folds), self._train_window, self._test_window,
            self._step_size, n,
        )
        return folds

    def compute_fold_count(self, data_size: int) -> int:
        """Compute how many folds will be generated for a given data size.

        Args:
            data_size: Number of data points.

        Returns:
            Expected number of folds.
        """
        min_required = self._train_window + self._test_window
        if data_size < min_required:
            return 0

        count = 0
        start = 0
        while start + self._train_window + self._test_window <= data_size:
            count += 1
            start += self._step_size
        return count
