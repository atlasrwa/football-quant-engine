"""Temporal split abstraction — strict chronological evaluation.

CRITICAL: Never evaluate a candidate using information unavailable
at prediction time.

For every match T:
- Training data: timestamp < prediction_timestamp(T)
- Features: information_timestamp <= prediction_timestamp(T)
- Outcome: only available AFTER prediction

The default experiment MUST be chronological.
Random splitting exists only as an explicitly labeled utility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from src.research.data_source import ResearchMatch


class SplitType(Enum):
    """Type of temporal split."""

    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    TEST = "TEST"


class SplitMethod(Enum):
    """Method used for splitting."""

    CHRONOLOGICAL = "CHRONOLOGICAL"  # Default — strict time ordering
    RANDOM = "RANDOM"  # Explicitly labeled — for ablation only


@dataclass(frozen=True)
class TemporalBoundary:
    """A time boundary for a split segment.

    Attributes:
        start_timestamp: Inclusive start (unix timestamp).
        end_timestamp: Exclusive end (unix timestamp).
        split_type: Which segment this boundary defines.
    """

    start_timestamp: int
    end_timestamp: int
    split_type: SplitType

    def contains(self, timestamp: int) -> bool:
        """Check if a timestamp falls within this boundary."""
        return self.start_timestamp <= timestamp < self.end_timestamp

    @property
    def duration_days(self) -> float:
        """Duration in days."""
        return (self.end_timestamp - self.start_timestamp) / 86400.0

    def validate(self) -> tuple[bool, str]:
        """Validate boundary integrity."""
        if self.start_timestamp >= self.end_timestamp:
            return False, f"Start ({self.start_timestamp}) >= End ({self.end_timestamp})"
        return True, "Valid"


@dataclass(frozen=True)
class TemporalSplit:
    """A complete temporal split specification.

    Enforces chronological ordering:
    TRAIN < VALIDATION < TEST

    Not all segments are required — validation is optional.

    Attributes:
        train: Training period boundary.
        validation: Optional validation period boundary.
        test: Test/evaluation period boundary.
        method: How the split was determined.
    """

    train: TemporalBoundary
    test: TemporalBoundary
    validation: Optional[TemporalBoundary] = None
    method: SplitMethod = SplitMethod.CHRONOLOGICAL

    def validate(self) -> tuple[bool, str]:
        """Validate temporal ordering and integrity.

        Ensures:
        - No overlaps
        - Chronological ordering (train < validation < test)
        - Each boundary is internally valid
        """
        # Validate individual boundaries
        valid, msg = self.train.validate()
        if not valid:
            return False, f"Train boundary invalid: {msg}"

        valid, msg = self.test.validate()
        if not valid:
            return False, f"Test boundary invalid: {msg}"

        if self.validation is not None:
            valid, msg = self.validation.validate()
            if not valid:
                return False, f"Validation boundary invalid: {msg}"

        # Chronological ordering
        if self.validation is not None:
            if self.train.end_timestamp > self.validation.start_timestamp:
                return False, (
                    f"Train end ({self.train.end_timestamp}) > "
                    f"Validation start ({self.validation.start_timestamp}): temporal violation"
                )
            if self.validation.end_timestamp > self.test.start_timestamp:
                return False, (
                    f"Validation end ({self.validation.end_timestamp}) > "
                    f"Test start ({self.test.start_timestamp}): temporal violation"
                )
        else:
            if self.train.end_timestamp > self.test.start_timestamp:
                return False, (
                    f"Train end ({self.train.end_timestamp}) > "
                    f"Test start ({self.test.start_timestamp}): temporal violation"
                )

        return True, "Valid"

    def assign_match(self, match: ResearchMatch) -> Optional[SplitType]:
        """Assign a match to its temporal segment.

        Args:
            match: A research match record.

        Returns:
            SplitType or None if match falls outside all segments.
        """
        ts = match.date_unix
        if self.train.contains(ts):
            return SplitType.TRAIN
        if self.validation is not None and self.validation.contains(ts):
            return SplitType.VALIDATION
        if self.test.contains(ts):
            return SplitType.TEST
        return None

    def split_matches(
        self, matches: list[ResearchMatch]
    ) -> dict[SplitType, list[ResearchMatch]]:
        """Split matches into temporal segments.

        Args:
            matches: All available matches (any ordering).

        Returns:
            Dict mapping SplitType to list of matches in that segment,
            each sorted chronologically.
        """
        result: dict[SplitType, list[ResearchMatch]] = {
            SplitType.TRAIN: [],
            SplitType.TEST: [],
        }
        if self.validation is not None:
            result[SplitType.VALIDATION] = []

        for match in matches:
            segment = self.assign_match(match)
            if segment is not None:
                result[segment].append(match)

        # Sort each segment chronologically
        for segment in result:
            result[segment].sort(key=lambda m: m.date_unix)

        return result

    def to_dict(self) -> dict[str, Any]:
        """Serialize for provenance."""
        d: dict[str, Any] = {
            "method": self.method.value,
            "train": {
                "start": self.train.start_timestamp,
                "end": self.train.end_timestamp,
            },
            "test": {
                "start": self.test.start_timestamp,
                "end": self.test.end_timestamp,
            },
        }
        if self.validation is not None:
            d["validation"] = {
                "start": self.validation.start_timestamp,
                "end": self.validation.end_timestamp,
            }
        return d


class TemporalSplitFactory:
    """Factory for creating temporal splits from data.

    Provides convenience methods for common split patterns.
    """

    @staticmethod
    def from_ratios(
        matches: list[ResearchMatch],
        train_ratio: float = 0.6,
        validation_ratio: float = 0.2,
        test_ratio: float = 0.2,
    ) -> TemporalSplit:
        """Create temporal split from ratio of matches.

        Splits are determined by position in chronological ordering,
        NOT by random assignment.

        Args:
            matches: All matches (will be sorted internally).
            train_ratio: Fraction of data for training.
            validation_ratio: Fraction for validation (0 to skip).
            test_ratio: Fraction for testing.

        Returns:
            TemporalSplit with boundaries derived from data timestamps.

        Raises:
            ValueError: If ratios don't sum to ~1.0 or data is empty.
        """
        total = train_ratio + validation_ratio + test_ratio
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Ratios must sum to 1.0, got {total}")
        if not matches:
            raise ValueError("Cannot create split from empty matches")

        sorted_matches = sorted(matches, key=lambda m: m.date_unix)
        n = len(sorted_matches)

        train_end_idx = int(n * train_ratio)
        if validation_ratio > 0:
            val_end_idx = int(n * (train_ratio + validation_ratio))
        else:
            val_end_idx = train_end_idx

        # Ensure at least 1 match in each segment
        train_end_idx = max(1, min(train_end_idx, n - 1))
        if validation_ratio > 0:
            val_end_idx = max(train_end_idx + 1, min(val_end_idx, n - 1))

        train_boundary = TemporalBoundary(
            start_timestamp=sorted_matches[0].date_unix,
            end_timestamp=sorted_matches[train_end_idx].date_unix,
            split_type=SplitType.TRAIN,
        )

        if validation_ratio > 0 and val_end_idx > train_end_idx:
            validation_boundary = TemporalBoundary(
                start_timestamp=sorted_matches[train_end_idx].date_unix,
                end_timestamp=sorted_matches[val_end_idx].date_unix,
                split_type=SplitType.VALIDATION,
            )
            test_boundary = TemporalBoundary(
                start_timestamp=sorted_matches[val_end_idx].date_unix,
                end_timestamp=sorted_matches[-1].date_unix + 1,  # inclusive of last
                split_type=SplitType.TEST,
            )
            return TemporalSplit(
                train=train_boundary,
                validation=validation_boundary,
                test=test_boundary,
                method=SplitMethod.CHRONOLOGICAL,
            )
        else:
            test_boundary = TemporalBoundary(
                start_timestamp=sorted_matches[train_end_idx].date_unix,
                end_timestamp=sorted_matches[-1].date_unix + 1,
                split_type=SplitType.TEST,
            )
            return TemporalSplit(
                train=train_boundary,
                test=test_boundary,
                method=SplitMethod.CHRONOLOGICAL,
            )

    @staticmethod
    def from_timestamps(
        train_start: int,
        train_end: int,
        test_start: int,
        test_end: int,
        validation_start: Optional[int] = None,
        validation_end: Optional[int] = None,
    ) -> TemporalSplit:
        """Create temporal split from explicit timestamps.

        Args:
            train_start: Training period start (inclusive).
            train_end: Training period end (exclusive).
            test_start: Test period start (inclusive).
            test_end: Test period end (exclusive).
            validation_start: Optional validation start.
            validation_end: Optional validation end.

        Returns:
            TemporalSplit.
        """
        train = TemporalBoundary(
            start_timestamp=train_start,
            end_timestamp=train_end,
            split_type=SplitType.TRAIN,
        )
        test = TemporalBoundary(
            start_timestamp=test_start,
            end_timestamp=test_end,
            split_type=SplitType.TEST,
        )
        validation = None
        if validation_start is not None and validation_end is not None:
            validation = TemporalBoundary(
                start_timestamp=validation_start,
                end_timestamp=validation_end,
                split_type=SplitType.VALIDATION,
            )
        return TemporalSplit(
            train=train,
            test=test,
            validation=validation,
            method=SplitMethod.CHRONOLOGICAL,
        )
