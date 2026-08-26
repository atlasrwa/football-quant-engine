"""Parameter space definitions for bounded candidate generation.

Provides structured parameter ranges, grids, and value sets that
enable systematic search while preventing unbounded explosion.

Every parameter has:
- Name
- Bounded domain (discrete values, numeric range, or explicit set)
- Deterministic iteration order
"""

from __future__ import annotations

import hashlib
import itertools
import json
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass(frozen=True, slots=True)
class ParameterValue:
    """A single parameter name-value pair."""

    name: str
    value: Any

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "value": self.value}


@dataclass(frozen=True, slots=True)
class ParameterRange:
    """A bounded numeric parameter range.

    Generates values from start to stop (inclusive) with given step.
    Always produces a deterministic sequence.

    Attributes:
        name: Parameter name.
        start: Lower bound (inclusive).
        stop: Upper bound (inclusive).
        step: Step size between values.
    """

    name: str
    start: float
    stop: float
    step: float

    def __post_init__(self):
        if self.step <= 0:
            raise ValueError(f"step must be > 0, got {self.step}")
        if self.stop < self.start:
            raise ValueError(f"stop ({self.stop}) must be >= start ({self.start})")

    @property
    def values(self) -> list[float]:
        """Generate all values in the range."""
        result = []
        current = self.start
        while current <= self.stop + self.step * 0.001:  # float tolerance
            result.append(round(current, 10))
            current += self.step
        return result

    @property
    def count(self) -> int:
        """Number of values in this range."""
        return len(self.values)


@dataclass(frozen=True, slots=True)
class ParameterSet:
    """A discrete set of parameter values.

    Attributes:
        name: Parameter name.
        values: Explicit values (must be sorted for determinism).
    """

    name: str
    values: tuple[Any, ...]

    @property
    def count(self) -> int:
        return len(self.values)


@dataclass(frozen=True, slots=True)
class ParameterGrid:
    """A multi-dimensional parameter grid for systematic search.

    Produces the Cartesian product of all parameter dimensions.
    Total combinations = product of all dimension sizes.

    Attributes:
        dimensions: List of parameter ranges or sets.
        max_combinations: Hard cap on total combinations (safety limit).
    """

    dimensions: tuple[ParameterRange | ParameterSet, ...]
    max_combinations: int = 1000

    @property
    def total_combinations(self) -> int:
        """Total number of parameter combinations."""
        total = 1
        for dim in self.dimensions:
            total *= dim.count
        return total

    @property
    def is_within_budget(self) -> bool:
        """Whether total combinations respect the budget cap."""
        return self.total_combinations <= self.max_combinations

    def iterate(self) -> Iterator[dict[str, Any]]:
        """Iterate over all parameter combinations (deterministic order).

        Yields dicts of {param_name: value} for each combination.
        Stops at max_combinations to prevent runaway.
        """
        dim_values = []
        dim_names = []
        for dim in self.dimensions:
            dim_names.append(dim.name)
            if isinstance(dim, ParameterRange):
                dim_values.append(dim.values)
            else:
                dim_values.append(list(dim.values))

        count = 0
        for combo in itertools.product(*dim_values):
            if count >= self.max_combinations:
                return
            yield dict(zip(dim_names, combo))
            count += 1

    def content_hash(self) -> str:
        """Deterministic hash of the grid definition."""
        canonical = json.dumps(
            {
                "dimensions": [
                    {"name": d.name, "values": list(d.values) if isinstance(d, ParameterSet) else d.values}
                    for d in self.dimensions
                ],
                "max_combinations": self.max_combinations,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


# ═══════════════════════════════════════════════════════════════
# DEFAULT PARAMETER SPACES
# ═══════════════════════════════════════════════════════════════


def rolling_window_params() -> ParameterSet:
    """Standard rolling window sizes."""
    return ParameterSet(name="window", values=(3, 5, 8, 10))


def threshold_quantile_params() -> ParameterSet:
    """Standard quantile thresholds for data-driven thresholds."""
    return ParameterSet(name="quantile", values=(0.25, 0.50, 0.75))


def difference_threshold_params() -> ParameterSet:
    """Standard difference thresholds."""
    return ParameterSet(name="diff_threshold", values=(-10.0, -5.0, 0.0, 5.0, 10.0))


def ratio_threshold_params() -> ParameterSet:
    """Standard ratio thresholds."""
    return ParameterSet(name="ratio_threshold", values=(0.8, 1.0, 1.1, 1.25, 1.5))
