"""Provider-specific exceptions for TheStatsAPI.

A small, explicit hierarchy so callers can distinguish transport failures,
authentication problems, rate limiting, and malformed payloads without
catching bare ``Exception``. Mirrors the intent of the FootyStats research
client's error handling.
"""

from __future__ import annotations


class TheStatsAPIError(Exception):
    """Base class for all TheStatsAPI provider errors."""


class TheStatsAPIConfigurationError(TheStatsAPIError):
    """Raised when the provider is used without required configuration.

    Example: no API key available in the environment when a live request is
    attempted. This is distinct from the provider being *unavailable* — an
    unconfigured provider should degrade gracefully (return nothing) in the
    orchestration layer rather than raise, but the low-level client raises so
    misuse is visible in tests.
    """


class TheStatsAPIAuthenticationError(TheStatsAPIError):
    """Raised on HTTP 401/403 — credentials rejected by the provider."""


class TheStatsAPIRateLimitError(TheStatsAPIError):
    """Raised on HTTP 429 after retries are exhausted."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class TheStatsAPITransportError(TheStatsAPIError):
    """Raised on network/timeout errors after retries are exhausted."""


class TheStatsAPIResponseError(TheStatsAPIError):
    """Raised when a response cannot be parsed or is structurally invalid."""
