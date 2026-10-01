"""Exceptions for deterministic TheStatsAPI payload normalization."""


class TheStatsAPIError(Exception):
    """Base class for retained TheStatsAPI evidence-provider errors."""


class TheStatsAPIResponseError(TheStatsAPIError):
    """Raised when a provider payload is structurally invalid."""
