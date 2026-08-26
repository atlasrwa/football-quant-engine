"""Paper Trade Model — immutable prediction + lifecycle tracking.

Identity:
    Deterministic based on (strategy_id, hypothesis_id, fixture_id,
    market, selection, snapshot_id, odds_snapshot_id).
    No random UUIDs for primary identity.

State Machine:
    GENERATED → APPROVED_FOR_PAPER → OPEN → SETTLED
    GENERATED → REJECTED
    APPROVED_FOR_PAPER → CANCELLED
    OPEN → VOID

Original prediction inputs are IMMUTABLE.
Closing odds do NOT replace prediction odds.
Settlement does NOT alter the original prediction.

Paper trading is research evaluation ONLY.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Optional


class PaperTradeStatus(Enum):
    """Paper trade lifecycle states."""
    GENERATED = "GENERATED"
    APPROVED_FOR_PAPER = "APPROVED_FOR_PAPER"
    OPEN = "OPEN"
    SETTLED = "SETTLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    VOID = "VOID"


# Valid state transitions
_TRADE_TRANSITIONS: dict[PaperTradeStatus, set[PaperTradeStatus]] = {
    PaperTradeStatus.GENERATED: {PaperTradeStatus.APPROVED_FOR_PAPER, PaperTradeStatus.REJECTED},
    PaperTradeStatus.APPROVED_FOR_PAPER: {PaperTradeStatus.OPEN, PaperTradeStatus.CANCELLED},
    PaperTradeStatus.OPEN: {PaperTradeStatus.SETTLED, PaperTradeStatus.VOID},
    PaperTradeStatus.SETTLED: set(),  # Terminal
    PaperTradeStatus.REJECTED: set(),  # Terminal
    PaperTradeStatus.CANCELLED: set(),  # Terminal
    PaperTradeStatus.VOID: set(),  # Terminal
}


@dataclass(frozen=True)
class PaperTrade:
    """Immutable paper trade record.

    Original prediction fields are frozen at creation.
    Settlement, closing odds, and CLV are added via new instances (replace).

    This is NOT a real bet. No money changes hands.
    """
    # ═══ Identity ═══
    strategy_id: str = ""
    hypothesis_id: str = ""
    research_run_id: str = ""
    fixture_id: str = ""

    # ═══ Market ═══
    market: str = ""
    selection: str = ""  # OVER, UNDER, HOME, DRAW, AWAY, YES, NO
    line: float = 0.0

    # ═══ Prediction (immutable at creation) ═══
    model_probability: float = 0.0  # Model's predicted probability
    market_probability: float = 0.0  # Implied from odds (1/odds)
    odds_at_prediction: float = 0.0  # Decimal odds when prediction was made
    edge: float = 0.0  # model_probability - market_probability
    expected_value: float = 0.0  # (model_prob * odds) - 1

    # ═══ Staking ═══
    stake: float = 0.0
    bankroll_before: float = 0.0

    # ═══ Timestamps ═══
    prediction_timestamp: float = 0.0
    kickoff_timestamp: float = 0.0

    # ═══ Provenance ═══
    snapshot_id: str = ""  # PreMatchSnapshot identity
    odds_snapshot_id: str = ""  # OddsSnapshot identity

    # ═══ Lifecycle ═══
    status: PaperTradeStatus = PaperTradeStatus.GENERATED

    # ═══ Post-settlement (added later, does NOT modify original prediction) ═══
    closing_odds: Optional[float] = None
    clv: Optional[float] = None
    settlement_result: Optional[str] = None  # "WIN", "LOSS", "VOID"
    settlement_timestamp: Optional[float] = None
    profit_loss: Optional[float] = None

    @property
    def trade_id(self) -> str:
        """Deterministic trade identity.

        Based on research content — NOT random.
        Same inputs always produce same trade ID.
        """
        canonical = json.dumps({
            "strategy_id": self.strategy_id,
            "hypothesis_id": self.hypothesis_id,
            "fixture_id": self.fixture_id,
            "market": self.market,
            "selection": self.selection,
            "line": self.line,
            "snapshot_id": self.snapshot_id,
            "odds_snapshot_id": self.odds_snapshot_id,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    @property
    def content_hash(self) -> str:
        """Full content hash including all prediction fields."""
        canonical = json.dumps({
            "trade_id": self.trade_id,
            "model_probability": self.model_probability,
            "odds_at_prediction": self.odds_at_prediction,
            "stake": self.stake,
            "prediction_timestamp": self.prediction_timestamp,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    @property
    def is_terminal(self) -> bool:
        """Whether trade is in a terminal state."""
        return self.status in (
            PaperTradeStatus.SETTLED,
            PaperTradeStatus.REJECTED,
            PaperTradeStatus.CANCELLED,
            PaperTradeStatus.VOID,
        )

    @property
    def is_profitable(self) -> Optional[bool]:
        """Whether the trade was profitable. None if not settled."""
        if self.profit_loss is None:
            return None
        return self.profit_loss > 0

    def transition(self, new_status: PaperTradeStatus) -> "PaperTrade":
        """Create new trade with updated status.

        Raises:
            ValueError: If transition is invalid.
        """
        valid = _TRADE_TRANSITIONS.get(self.status, set())
        if new_status not in valid:
            raise ValueError(
                f"Invalid trade transition: {self.status.value} → {new_status.value}. "
                f"Valid: {[s.value for s in valid]}"
            )
        return replace(self, status=new_status)

    def settle(
        self,
        result: str,
        profit_loss: float,
        settlement_timestamp: float,
        closing_odds: Optional[float] = None,
        clv: Optional[float] = None,
    ) -> "PaperTrade":
        """Settle the trade with outcome.

        The original prediction fields remain unchanged.
        Settlement adds new information but NEVER modifies the prediction.

        Args:
            result: "WIN", "LOSS", or "VOID".
            profit_loss: Realized P&L.
            settlement_timestamp: When settlement occurred.
            closing_odds: Final odds at kickoff (for CLV, not prediction).
            clv: Closing line value.

        Returns:
            New PaperTrade with settlement data.

        Raises:
            ValueError: If trade is not OPEN.
        """
        if self.status != PaperTradeStatus.OPEN:
            raise ValueError(f"Cannot settle trade in status {self.status.value}")

        return replace(
            self,
            status=PaperTradeStatus.SETTLED,
            settlement_result=result,
            profit_loss=profit_loss,
            settlement_timestamp=settlement_timestamp,
            closing_odds=closing_odds,
            clv=clv,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "strategy_id": self.strategy_id,
            "hypothesis_id": self.hypothesis_id,
            "research_run_id": self.research_run_id,
            "fixture_id": self.fixture_id,
            "market": self.market,
            "selection": self.selection,
            "line": self.line,
            "model_probability": self.model_probability,
            "market_probability": self.market_probability,
            "odds_at_prediction": self.odds_at_prediction,
            "edge": self.edge,
            "expected_value": self.expected_value,
            "stake": self.stake,
            "bankroll_before": self.bankroll_before,
            "prediction_timestamp": self.prediction_timestamp,
            "kickoff_timestamp": self.kickoff_timestamp,
            "snapshot_id": self.snapshot_id,
            "odds_snapshot_id": self.odds_snapshot_id,
            "status": self.status.value,
            "closing_odds": self.closing_odds,
            "clv": self.clv,
            "settlement_result": self.settlement_result,
            "settlement_timestamp": self.settlement_timestamp,
            "profit_loss": self.profit_loss,
            "content_hash": self.content_hash,
        }
