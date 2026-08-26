"""Fold generation for walk-forward validation.

Generates deterministic chronological folds from data boundaries.
Supports expanding and rolling training windows.

CRITICAL: Temporal ordering is strictly enforced.
    training_end < validation_start < validation_end < test_start < test_end

No overlap between segments within a fold.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.research.walkforward.config import WalkForwardConfig, WindowType


@dataclass(frozen=True)
class FoldSpec:
    """Specification for a single walk-forward fold.

    Defines the temporal boundaries for train/validation/test segments.
    All timestamps are unix timestamps (seconds).
    """

    fold_index: int

    train_start: int
    train_end: int  # exclusive

    validation_start: Optional[int] = None  # None if no validation
    validation_end: Optional[int] = None

    test_start: int = 0
    test_end: int = 0  # exclusive

    @property
    def has_validation(self) -> bool:
        """Whether this fold has a validation segment."""
        return self.validation_start is not None and self.validation_end is not None

    @property
    def training_duration(self) -> int:
        """Training segment duration in seconds."""
        return self.train_end - self.train_start

    @property
    def test_duration(self) -> int:
        """Test segment duration in seconds."""
        return self.test_end - self.test_start

    @property
    def validation_duration(self) -> int:
        """Validation segment duration in seconds (0 if no validation)."""
        if self.validation_start is None or self.validation_end is None:
            return 0
        return self.validation_end - self.validation_start

    def validate_temporal_order(self) -> tuple[bool, str]:
        """Validate strict chronological ordering.

        Ensures: train_end <= validation_start <= validation_end <= test_start <= test_end
        """
        if self.train_start >= self.train_end:
            return False, f"Fold {self.fold_index}: train_start >= train_end"

        if self.test_start >= self.test_end:
            return False, f"Fold {self.fold_index}: test_start >= test_end"

        if self.has_validation:
            if self.train_end > self.validation_start:
                return False, (
                    f"Fold {self.fold_index}: train_end ({self.train_end}) > "
                    f"validation_start ({self.validation_start})"
                )
            if self.validation_start >= self.validation_end:
                return False, f"Fold {self.fold_index}: validation_start >= validation_end"
            if self.validation_end > self.test_start:
                return False, (
                    f"Fold {self.fold_index}: validation_end ({self.validation_end}) > "
                    f"test_start ({self.test_start})"
                )
        else:
            if self.train_end > self.test_start:
                return False, (
                    f"Fold {self.fold_index}: train_end ({self.train_end}) > "
                    f"test_start ({self.test_start})"
                )

        return True, "Valid"


class FoldGenerator:
    """Generates walk-forward fold specifications.

    Produces deterministic fold boundaries given a data timespan
    and a WalkForwardConfig.

    EXPANDING mode: training start is fixed, training end advances.
    ROLLING mode: training start advances, training window is fixed size.
    """

    def __init__(self, config: WalkForwardConfig) -> None:
        self._config = config

    @property
    def config(self) -> WalkForwardConfig:
        return self._config

    def generate(self, data_start: int, data_end: int) -> list[FoldSpec]:
        """Generate fold specifications for the given data span.

        Args:
            data_start: Earliest available data timestamp.
            data_end: Latest available data timestamp.

        Returns:
            List of FoldSpec, chronologically ordered.
            Empty list if data span is insufficient.
        """
        if data_end - data_start < self._config.minimum_data_span:
            return []

        folds: list[FoldSpec] = []
        cfg = self._config

        fold_idx = 0
        step = 0  # number of steps taken

        while fold_idx < cfg.maximum_folds:
            # Compute training boundaries
            if cfg.window_type == WindowType.EXPANDING:
                train_start = data_start
                train_end = data_start + cfg.initial_training_period + step * cfg.step_period
            else:  # ROLLING
                train_start = data_start + step * cfg.step_period
                train_end = train_start + cfg.initial_training_period

            # Apply gap after training
            segment_start = train_end + cfg.gap_period

            # Compute validation boundaries (if configured)
            if cfg.validation_period > 0:
                val_start = segment_start
                val_end = val_start + cfg.validation_period
                # Gap between validation and test
                test_start = val_end + cfg.gap_period
            else:
                val_start = None
                val_end = None
                test_start = segment_start

            # Compute test boundaries
            test_end = test_start + cfg.test_period

            # Check if we've exceeded data bounds
            if test_end > data_end:
                break

            fold = FoldSpec(
                fold_index=fold_idx,
                train_start=train_start,
                train_end=train_end,
                validation_start=val_start,
                validation_end=val_end,
                test_start=test_start,
                test_end=test_end,
            )

            # Validate temporal ordering
            valid, msg = fold.validate_temporal_order()
            if not valid:
                # This should never happen with correct generation logic
                raise RuntimeError(f"Fold generation produced invalid fold: {msg}")

            folds.append(fold)
            fold_idx += 1
            step += 1

        return folds

    def estimate_fold_count(self, data_start: int, data_end: int) -> int:
        """Estimate the number of folds without generating them.

        Useful for performance estimation.
        """
        span = data_end - data_start
        if span < self._config.minimum_data_span:
            return 0

        cfg = self._config
        # After initial training + validation + test, how many steps fit?
        remaining = span - cfg.minimum_data_span
        if cfg.step_period <= 0:
            return 1
        additional = remaining // cfg.step_period
        total = 1 + additional
        return min(total, cfg.maximum_folds)
