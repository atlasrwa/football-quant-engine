"""Dispatch data models — shared between dispatcher and adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True, slots=True)
class DispatchResult:
    """Normalized result from a dispatch attempt.

    Attributes:
        success: Whether delivery succeeded.
        status: Result status (DISPATCHED, DELIVERED, FAILED).
        dispatched_at: When the dispatch occurred.
        error_code: Machine-readable error code (if failed).
        error_message: Human-readable error message (if failed).
    """
    success: bool
    status: str
    dispatched_at: Optional[datetime] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
