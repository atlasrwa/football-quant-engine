"""Quarantine settlement bridge — wires settlement outcomes into quarantine P&L.

When a PAPER_TRADE prediction is settled, this bridge updates the
QuarantineTracker with the realized P&L, driving the 90-day paper
trading lifecycle that determines strategy promotion or rejection.

Architecture:
    PredictionSettlementService → on_settlement callback → QuarantineSettlementBridge
        → QuarantineTracker.update_paper_pnl()

This replaces the previous Gap #5 where QuarantineTracker.update_paper_pnl()
was never called by any system. Now it is driven by actual settlement results.

Scope: this bridges the in-memory QuarantineTracker (src/engine/fdr.py) to
the in-memory PredictionSettlementService (src/engine/settlement_service.py).
Neither is instantiated by any live orchestrator/scheduler/API route — this
is a backtest/research-time simulation pair, not the production path. The
live equivalent is src/services/settlement_service.py updating
src/persistence/pg_quarantine_repository.py directly (see its step 9b),
wired to the real API in src/api/routes/quarantine.py. If you are looking
for where live paper-trade settlements actually update quarantine state,
that's it, not this file.
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
        # Defense-in-depth: track which settlement_ids have been applied
        # to prevent double P&L even if the bridge is called outside
        # the normal service callback path.
        self._processed_ids: set[str] = set()

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
        Idempotent: a settlement_id that has already been processed is skipped.

        Args:
            prediction: The original prediction that was settled.
            settlement: The settlement result.
        """
        # Only paper trades affect quarantine
        if prediction.source != PredictionSource.PAPER_TRADE:
            return

        # IDEMPOTENCY: Skip if this settlement has already been applied
        if settlement.settlement_id in self._processed_ids:
            logger.debug(
                "Settlement %s already processed (idempotent skip)",
                settlement.settlement_id[:8],
            )
            return

        # QuarantineTracker keys are opaque strings — whatever the caller
        # passed to enter_quarantine(). We use str(prediction.strategy_id)
        # here, so the entry MUST have been created with that same key
        # (e.g. via tracker.enter_quarantine(str(strategy_id), ...)). A
        # strategy entered under a different key scheme — e.g. the research
        # governance flow's generated "research_{hash}_{hyp}" names
        # (src/research/governance/quarantine_adapter.py) — will not be
        # found here; update_paper_pnl() will KeyError and be swallowed
        # below as "not in quarantine yet". This bridge and the governance
        # adapter are not interchangeable without a shared key convention.
        strategy_key = str(prediction.strategy_id)

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
            self._processed_ids.add(settlement.settlement_id)

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
