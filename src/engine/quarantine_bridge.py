"""Quarantine settlement bridge — wires settlement outcomes into quarantine P&L.

When a PAPER_TRADE prediction is settled, this bridge updates the
QuarantineTracker with the realized P&L, driving the 90-day paper
trading lifecycle that determines strategy promotion or rejection.

Architecture:
    PredictionSettlementService → on_settlement callback → QuarantineSettlementBridge
        → QuarantineTracker.update_paper_pnl()

This replaces the previous Gap #5 where QuarantineTracker.update_paper_pnl()
was never called by any system. Now it is driven by actual settlement results.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.domain.prediction import PredictionEvent, PredictionSource
from src.domain.settlement import Settlement, SettlementOutcome
from src.engine.fdr import QuarantineTracker

if TYPE_CHECKING:
    from src.engine.settlement_service import PredictionSettlementService

logger = logging.getLogger(__name__)


class QuarantineSettlementBridge:
    """Bridges settlement outcomes to quarantine paper P&L tracking.

    Listens for settlements of PAPER_TRADE predictions and updates
    the QuarantineTracker with realized P&L. Only PAPER_TRADE predictions
    affect quarantine — LIVE_SIGNAL and BACKTEST are ignored.

    Usage:
        tracker = QuarantineTracker()
        service = PredictionSettlementService()
        bridge = QuarantineSettlementBridge(tracker)
        bridge.attach(service)

        # Now when service.settle_match() settles a PAPER_TRADE prediction,
        # tracker.update_paper_pnl() is called automatically.
    """

    def __init__(self, tracker: QuarantineTracker) -> None:
        """Initialize bridge with target quarantine tracker.

        Args:
            tracker: The QuarantineTracker to update on paper trade settlements.
        """
        self._tracker = tracker
        self._settlements_processed = 0
        self._total_paper_pnl = 0.0

    @property
    def settlements_processed(self) -> int:
        """Number of paper trade settlements processed by this bridge."""
        return self._settlements_processed

    @property
    def total_paper_pnl(self) -> float:
        """Cumulative paper P&L routed through this bridge."""
        return self._total_paper_pnl

    def attach(self, service: "PredictionSettlementService") -> None:
        """Attach this bridge to a settlement service.

        Registers the settlement callback so future settlements
        automatically flow to the quarantine tracker.

        Args:
            service: The PredictionSettlementService to listen to.
        """
        service.on_settlement(self._on_settlement)
        logger.info("QuarantineSettlementBridge attached to settlement service")

    def _on_settlement(
        self, prediction: PredictionEvent, settlement: Settlement
    ) -> None:
        """Handle a settlement event.

        Only processes PAPER_TRADE predictions. Other sources are ignored.

        Args:
            prediction: The original prediction that was settled.
            settlement: The settlement result.
        """
        # Only paper trades affect quarantine
        if prediction.source != PredictionSource.PAPER_TRADE:
            return

        # Map strategy_id to strategy_name for quarantine lookup.
        # QuarantineTracker uses strategy_name as key.
        # The prediction carries strategy_id — we use it as the lookup key.
        strategy_key = prediction.strategy_id

        # Skip void/push settlements (no P&L impact)
        if settlement.outcome in (SettlementOutcome.VOID, SettlementOutcome.PUSH):
            logger.debug(
                "Skipping VOID/PUSH settlement for strategy %s (match %d)",
                strategy_key[:8], prediction.match_id,
            )
            return

        try:
            self._tracker.update_paper_pnl(
                strategy_name=strategy_key,
                pnl_delta=settlement.profit_loss,
                bets=1,
            )
            self._settlements_processed += 1
            self._total_paper_pnl += settlement.profit_loss

            logger.debug(
                "Updated quarantine for strategy %s: P&L=%+.2f (match %d, %s)",
                strategy_key[:8],
                settlement.profit_loss,
                prediction.match_id,
                settlement.outcome.value,
            )
        except KeyError:
            # Strategy not in quarantine — this is expected for strategies
            # that haven't entered quarantine yet (e.g., not validated)
            logger.debug(
                "Strategy %s not in quarantine, skipping P&L update",
                strategy_key[:8],
            )
        except ValueError as e:
            # Strategy is promoted/rejected — can't update P&L
            logger.warning(
                "Cannot update quarantine P&L for strategy %s: %s",
                strategy_key[:8], e,
            )
