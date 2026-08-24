"""False Discovery Rate (FDR) control and quarantine tracking.

Implements Benjamini-Hochberg procedure to prevent p-hacking from
repeated strategy submissions, and enforces a 90-day live quarantine
before leaderboard promotion.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FDRResult:
    """Result of FDR correction for a single hypothesis."""

    original_p: float
    adjusted_threshold: float
    rank: int
    total_hypotheses: int
    rejected: bool  # True = significant after BH correction


class FDRController:
    """Benjamini-Hochberg False Discovery Rate controller.

    Adjusts significance thresholds based on the number of hypotheses
    tested, preventing p-hacking through repeated submissions.
    """

    def __init__(self, alpha: float = 0.05) -> None:
        """Initialize with target FDR level.

        Args:
            alpha: Target false discovery rate (default 0.05).
        """
        if not 0 < alpha < 1:
            raise ValueError(f"alpha must be in (0, 1), got {alpha}")
        self.alpha = alpha

    def correct(self, p_values: List[float]) -> List[FDRResult]:
        """Apply Benjamini-Hochberg procedure to a batch of p-values.

        BH procedure:
        1. Sort p-values in ascending order.
        2. For each rank i (1-indexed), compute threshold = (i/m) * alpha.
        3. Find largest i where p_i <= threshold_i.
        4. Reject all hypotheses with rank <= that cutoff.

        Args:
            p_values: List of raw p-values to correct.

        Returns:
            List of FDRResult in original order.
        """
        m = len(p_values)
        if m == 0:
            return []

        # Create indexed pairs and sort by p-value
        indexed = sorted(enumerate(p_values), key=lambda x: x[1])

        # Compute BH thresholds and find cutoff
        thresholds = [(i + 1) / m * self.alpha for i in range(m)]

        # Find the largest rank where p <= threshold (BH step-up)
        cutoff_rank = 0
        for rank_idx, (orig_idx, p) in enumerate(indexed):
            if p <= thresholds[rank_idx]:
                cutoff_rank = rank_idx + 1

        # Build results in original order
        results: List[FDRResult | None] = [None] * m
        for rank_idx, (orig_idx, p) in enumerate(indexed):
            rank = rank_idx + 1
            results[orig_idx] = FDRResult(
                original_p=p,
                adjusted_threshold=thresholds[rank_idx],
                rank=rank,
                total_hypotheses=m,
                rejected=(rank <= cutoff_rank),
            )

        return results  # type: ignore[return-value]

    def adjusted_threshold(self, rank: int, total: int) -> float:
        """Get BH-adjusted threshold for a specific rank.

        Args:
            rank: 1-indexed rank of this hypothesis.
            total: Total number of hypotheses tested.

        Returns:
            Adjusted significance threshold.
        """
        if rank < 1 or total < 1:
            raise ValueError("rank and total must be >= 1")
        return (rank / total) * self.alpha

    def is_significant(self, p_value: float, submission_count: int) -> bool:
        """Quick check: is a single p-value significant given k submissions?

        Uses the most conservative BH threshold (rank=1, total=k).
        This is appropriate when evaluating one strategy that has been
        re-submitted k times.

        Args:
            p_value: The p-value to test.
            submission_count: Number of submissions in the strategy family.

        Returns:
            True if significant after FDR correction.
        """
        if submission_count <= 1:
            return p_value <= self.alpha
        threshold = self.adjusted_threshold(1, submission_count)
        return p_value <= threshold


class QuarantineStatus(Enum):
    """Lifecycle status for validated strategies."""

    PENDING_QUARANTINE = "PENDING_QUARANTINE"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"


@dataclass
class QuarantineEntry:
    """Tracks a strategy through the quarantine lifecycle."""

    strategy_name: str
    status: QuarantineStatus
    entry_date: datetime
    promotion_date: datetime | None = None
    paper_pnl: float = 0.0
    paper_bets: int = 0


class QuarantineTracker:
    """Manages 90-day live quarantine for validated strategies.

    Strategies passing historical backtests enter quarantine where they
    are paper-traded. Only after 90 days of positive paper P&L are they
    promoted to the live leaderboard.
    """

    QUARANTINE_DAYS: int = 90

    def __init__(self) -> None:
        self._entries: dict[str, QuarantineEntry] = {}

    @property
    def entries(self) -> dict[str, QuarantineEntry]:
        """Read-only access to quarantine entries."""
        return dict(self._entries)

    def enter_quarantine(
        self, strategy_name: str, entry_date: datetime
    ) -> QuarantineEntry:
        """Place a strategy into quarantine.

        Args:
            strategy_name: Unique strategy identifier.
            entry_date: Date the strategy enters quarantine.

        Returns:
            The created QuarantineEntry.
        """
        if strategy_name in self._entries:
            existing = self._entries[strategy_name]
            if existing.status == QuarantineStatus.PROMOTED:
                raise ValueError(
                    f"Strategy '{strategy_name}' is already promoted"
                )
            # Re-entering quarantine resets the clock
            logger.info("Re-entering quarantine for '%s'", strategy_name)

        entry = QuarantineEntry(
            strategy_name=strategy_name,
            status=QuarantineStatus.PENDING_QUARANTINE,
            entry_date=entry_date,
        )
        self._entries[strategy_name] = entry
        logger.info(
            "Strategy '%s' entered quarantine on %s (expires %s)",
            strategy_name,
            entry_date.date(),
            (entry_date + timedelta(days=self.QUARANTINE_DAYS)).date(),
        )
        return entry

    def check_status(
        self, strategy_name: str, current_date: datetime
    ) -> QuarantineStatus:
        """Check the current quarantine status of a strategy.

        Args:
            strategy_name: Strategy identifier.
            current_date: Current date for expiry check.

        Returns:
            Current QuarantineStatus.
        """
        if strategy_name not in self._entries:
            raise KeyError(f"Strategy '{strategy_name}' not in quarantine")

        entry = self._entries[strategy_name]
        return entry.status

    def is_eligible_for_promotion(
        self, strategy_name: str, current_date: datetime
    ) -> bool:
        """Check if quarantine period has elapsed.

        Args:
            strategy_name: Strategy identifier.
            current_date: Current date to check against.

        Returns:
            True if 90 days have passed since entry.
        """
        if strategy_name not in self._entries:
            return False

        entry = self._entries[strategy_name]
        if entry.status != QuarantineStatus.PENDING_QUARANTINE:
            return False

        elapsed = (current_date - entry.entry_date).days
        return elapsed >= self.QUARANTINE_DAYS

    def promote(self, strategy_name: str, current_date: datetime) -> bool:
        """Promote a strategy if quarantine has elapsed.

        Args:
            strategy_name: Strategy identifier.
            current_date: Current date.

        Returns:
            True if promotion succeeded, False otherwise.
        """
        if not self.is_eligible_for_promotion(strategy_name, current_date):
            return False

        entry = self._entries[strategy_name]
        entry.status = QuarantineStatus.PROMOTED
        entry.promotion_date = current_date
        logger.info("Strategy '%s' PROMOTED on %s", strategy_name, current_date.date())
        return True

    def reject(self, strategy_name: str) -> bool:
        """Reject a strategy (failed paper trading).

        Args:
            strategy_name: Strategy identifier.

        Returns:
            True if rejection succeeded.
        """
        if strategy_name not in self._entries:
            return False

        self._entries[strategy_name].status = QuarantineStatus.REJECTED
        logger.info("Strategy '%s' REJECTED", strategy_name)
        return True

    def update_paper_pnl(
        self, strategy_name: str, pnl_delta: float, bets: int = 1
    ) -> None:
        """Update paper trading P&L for a quarantined strategy.

        Args:
            strategy_name: Strategy identifier.
            pnl_delta: Profit/loss to add.
            bets: Number of bets to add.
        """
        if strategy_name not in self._entries:
            raise KeyError(f"Strategy '{strategy_name}' not in quarantine")

        entry = self._entries[strategy_name]
        if entry.status != QuarantineStatus.PENDING_QUARANTINE:
            raise ValueError(
                f"Cannot update P&L for strategy with status {entry.status.value}"
            )

        entry.paper_pnl += pnl_delta
        entry.paper_bets += bets
