"""Closing Line Value (CLV) calculator.

CLV measures the movement from entry price to closing price.
It requires ACTUAL market data — never model edge approximations.

CLV is UNAVAILABLE unless both entry_odds and closing_odds are provided.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CLVResult:
    """Result of a CLV calculation for a single prediction."""

    entry_odds: float | None
    closing_odds: float | None
    clv_pct: float | None  # None = unavailable (missing market data)
    available: bool

    @property
    def beat_closing_line(self) -> bool | None:
        """Whether entry odds beat the closing line. None if unavailable."""
        if self.clv_pct is None:
            return None
        return self.clv_pct > 0.0


class CLVCalculator:
    """Computes real Closing Line Value from actual market data.

    CLV = (entry_odds / closing_odds - 1) * 100

    Positive CLV means the bettor got better odds than the market close.
    This is the gold-standard measure of betting edge.

    Requirements:
    - entry_odds must be actual odds at signal generation time
    - closing_odds must be actual odds at market close
    - Both must be decimal odds > 1.0
    - CLV is UNAVAILABLE if either is missing
    """

    @staticmethod
    def compute(entry_odds: float | None, closing_odds: float | None) -> CLVResult:
        """Compute CLV from entry and closing odds.

        Args:
            entry_odds: Decimal odds at signal generation (e.g., 2.10).
            closing_odds: Decimal odds at market close (e.g., 1.95).

        Returns:
            CLVResult with clv_pct if computable, None otherwise.
        """
        if entry_odds is None or closing_odds is None:
            return CLVResult(
                entry_odds=entry_odds,
                closing_odds=closing_odds,
                clv_pct=None,
                available=False,
            )

        if entry_odds <= 1.0 or closing_odds <= 1.0:
            return CLVResult(
                entry_odds=entry_odds,
                closing_odds=closing_odds,
                clv_pct=None,
                available=False,
            )

        clv_pct = (entry_odds / closing_odds - 1.0) * 100.0

        return CLVResult(
            entry_odds=entry_odds,
            closing_odds=closing_odds,
            clv_pct=clv_pct,
            available=True,
        )

    @classmethod
    def compute_batch(
        cls,
        entry_odds: List[float | None],
        closing_odds: List[float | None],
    ) -> List[CLVResult]:
        """Compute CLV for a batch of predictions.

        Args:
            entry_odds: List of entry odds (parallel to closing_odds).
            closing_odds: List of closing odds.

        Returns:
            List of CLVResult objects.
        """
        n = min(len(entry_odds), len(closing_odds))
        return [cls.compute(entry_odds[i], closing_odds[i]) for i in range(n)]

    @classmethod
    def aggregate_clv(cls, results: List[CLVResult]) -> float | None:
        """Compute average CLV across results where CLV is available.

        Returns None if no results have available CLV.
        """
        available = [r.clv_pct for r in results if r.available and r.clv_pct is not None]
        if not available:
            return None
        return sum(available) / len(available)
