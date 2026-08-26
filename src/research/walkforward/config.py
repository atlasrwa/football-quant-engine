"""Walk-Forward Configuration.

Defines the complete configuration for multi-period walk-forward validation.
Supports both expanding and rolling training windows with strict temporal ordering.

EXPANDING:
    Fold 1: Train [Jan-Jun],  Test [Jul]
    Fold 2: Train [Jan-Jul],  Test [Aug]
    Fold 3: Train [Jan-Aug],  Test [Sep]

ROLLING:
    Fold 1: Train [Jan-Jun],  Test [Jul]
    Fold 2: Train [Feb-Jul],  Test [Aug]
    Fold 3: Train [Mar-Aug],  Test [Sep]

Both preserve strict chronological causality.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class WindowType(Enum):
    """Training window expansion strategy."""

    EXPANDING = "EXPANDING"  # Training window grows each fold
    ROLLING = "ROLLING"      # Training window slides (fixed size)


@dataclass(frozen=True)
class WalkForwardConfig:
    """Complete walk-forward validation configuration.

    All periods are in seconds (unix timestamp deltas).

    Attributes:
        initial_training_period: Minimum training window (seconds).
        validation_period: Validation window per fold (seconds). 0 = no validation.
        test_period: Test window per fold (seconds).
        step_period: How far to advance between folds (seconds).
        minimum_training_observations: Min matches required in training.
        minimum_test_observations: Min matches required in test.
        window_type: EXPANDING or ROLLING.
        minimum_folds: Minimum folds required for valid result.
        maximum_folds: Maximum folds to generate (cap for performance).
        gap_period: Gap between train end and validation/test start (seconds).
            Prevents information leakage from matches at boundary.
    """

    initial_training_period: int  # seconds
    test_period: int              # seconds
    step_period: int              # seconds
    validation_period: int = 0    # seconds (0 = no validation split)
    minimum_training_observations: int = 50
    minimum_test_observations: int = 10
    window_type: WindowType = WindowType.EXPANDING
    minimum_folds: int = 3
    maximum_folds: int = 50
    gap_period: int = 0           # seconds between segments

    def __post_init__(self) -> None:
        """Validate configuration invariants."""
        errors = self.validate()
        if errors:
            raise ValueError(f"Invalid WalkForwardConfig: {'; '.join(errors)}")

    def validate(self) -> list[str]:
        """Validate configuration. Returns list of error messages."""
        errors: list[str] = []

        if self.initial_training_period <= 0:
            errors.append("initial_training_period must be > 0")
        if self.test_period <= 0:
            errors.append("test_period must be > 0")
        if self.step_period <= 0:
            errors.append("step_period must be > 0")
        if self.validation_period < 0:
            errors.append("validation_period must be >= 0")
        if self.minimum_training_observations < 1:
            errors.append("minimum_training_observations must be >= 1")
        if self.minimum_test_observations < 1:
            errors.append("minimum_test_observations must be >= 1")
        if self.minimum_folds < 1:
            errors.append("minimum_folds must be >= 1")
        if self.maximum_folds < self.minimum_folds:
            errors.append("maximum_folds must be >= minimum_folds")
        if self.gap_period < 0:
            errors.append("gap_period must be >= 0")

        return errors

    @property
    def content_hash(self) -> str:
        """Deterministic identity hash.

        Same configuration always produces the same hash.
        Does NOT include runtime values.
        """
        canonical = json.dumps(
            {
                "initial_training_period": self.initial_training_period,
                "test_period": self.test_period,
                "step_period": self.step_period,
                "validation_period": self.validation_period,
                "minimum_training_observations": self.minimum_training_observations,
                "minimum_test_observations": self.minimum_test_observations,
                "window_type": self.window_type.value,
                "minimum_folds": self.minimum_folds,
                "maximum_folds": self.maximum_folds,
                "gap_period": self.gap_period,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    @property
    def minimum_data_span(self) -> int:
        """Minimum data timespan (seconds) needed for at least one fold."""
        return (
            self.initial_training_period
            + self.gap_period
            + self.validation_period
            + self.gap_period
            + self.test_period
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize for provenance."""
        return {
            "initial_training_period": self.initial_training_period,
            "test_period": self.test_period,
            "step_period": self.step_period,
            "validation_period": self.validation_period,
            "minimum_training_observations": self.minimum_training_observations,
            "minimum_test_observations": self.minimum_test_observations,
            "window_type": self.window_type.value,
            "minimum_folds": self.minimum_folds,
            "maximum_folds": self.maximum_folds,
            "gap_period": self.gap_period,
            "content_hash": self.content_hash,
        }
